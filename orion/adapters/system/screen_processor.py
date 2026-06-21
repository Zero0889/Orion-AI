from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import threading
import time

import numpy as np
import sounddevice as sd

try:
    import cv2

    _CV2 = True
except ImportError:
    _CV2 = False

try:
    import mss
    import mss.tools

    _MSS = True
except ImportError:
    _MSS = False

try:
    import PIL.Image

    _PIL = True
except ImportError:
    _PIL = False

from google import genai
from google.genai import types as gtypes

from orion.config import API_CONFIG_PATH as _CONFIG_PATH
from orion.config import get_api_key
import contextlib


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config_key(key: str, value) -> None:
    try:
        cfg = _load_config()
        cfg[key] = value
        _CONFIG_PATH.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
    except Exception as e:
        print(f"[Vision] ⚠️  No se pudo guardar la clave de configuración '{key}': {e}")


def _get_os() -> str:
    return _load_config().get("os_system", "windows").lower()


_LIVE_MODEL = "models/gemini-2.5-flash"
_CHANNELS = 1
_RECEIVE_SAMPLE_RATE = 24_000
_CHUNK_SIZE = 1_024

_IMG_MAX_W = 640
_IMG_MAX_H = 360
_JPEG_Q = 60

_SYSTEM_PROMPT = (
    "You are O.R.I.O.N, an advanced AI assistant. "
    "Analyze the provided image with precision and intelligence. "
    "Be concise and direct — two sentences maximum unless the user's question "
    "requires more detail. "
    "Address the user respectfully as 'señor'. "
    "Always respond in Spanish. "
    "Always invoke the appropriate tool; never simulate results."
)


def _compress(img_bytes: bytes, source_format: str = "PNG") -> tuple[bytes, str]:
    if not _PIL:
        return img_bytes, f"image/{source_format.lower()}"

    try:
        img = PIL.Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q, optimize=False)
        return buf.getvalue(), "image/jpeg"
    except Exception as e:
        print(f"[Vision] ⚠️  La compresión de imagen falló: {e}")
        return img_bytes, f"image/{source_format.lower()}"


def _capture_screen() -> tuple[bytes, str]:

    if not _MSS:
        raise RuntimeError("mss no está instalado. Ejecuta: pip install mss")

    with mss.mss() as sct:
        monitors = sct.monitors  # [0] = all combined, [1..n] = real screens
        target = monitors[1] if len(monitors) > 1 else monitors[0]
        shot = sct.grab(target)
        png = mss.tools.to_png(shot.rgb, shot.size)

    return _compress(png, "PNG")


def _cv2_backend() -> int:
    """Devuelve el mejor backend de cámara de OpenCV para el SO actual."""
    if not _CV2:
        return 0
    os_name = _get_os()
    if os_name == "windows":
        return cv2.CAP_DSHOW
    if os_name == "mac":
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_ANY


def _probe_camera(index: int, backend: int, warmup: int = 5) -> bool:

    if not _CV2:
        return False
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        return False
    for _ in range(warmup):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        return False
    return bool(np.mean(frame) > 8)


def _detect_camera_index() -> int:

    backend = _cv2_backend()
    print("[Vision] 🔍 Detectando cámara automáticamente...")
    for idx in range(6):
        if _probe_camera(idx, backend):
            print(f"[Vision] ✅ Cámara encontrada en el índice {idx}")
            _save_config_key("camera_index", idx)
            return idx
        print(f"[Vision] ⚠️  Índice de cámara {idx}: sin frame utilizable")

    print("[Vision] ⚠️  No se encontró cámara — usando índice 0 por defecto")
    _save_config_key("camera_index", 0)
    return 0


def _get_camera_index() -> int:
    cfg = _load_config()
    if "camera_index" in cfg:
        return int(cfg["camera_index"])
    return _detect_camera_index()


def _capture_camera() -> tuple[bytes, str]:
    if not _CV2:
        raise RuntimeError("OpenCV (cv2) no está instalado. Ejecuta: pip install opencv-python")

    index = _get_camera_index()
    backend = _cv2_backend()
    cap = cv2.VideoCapture(index, backend)

    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir la cámara con el índice {index}.")

    for _ in range(10):
        cap.read()

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise RuntimeError("La cámara no devolvió ningún frame.")

    if _PIL:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(rgb)
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q)
        return buf.getvalue(), "image/jpeg"

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_Q])
    return buf.tobytes(), "image/jpeg"


class _VisionSession:
    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._session = None
        self._out_queue: asyncio.Queue | None = None
        self._audio_in: asyncio.Queue | None = None
        self._ready_evt: threading.Event = threading.Event()
        self._player = None
        self._lock: threading.Lock = threading.Lock()

    def start(self, player=None, timeout: float = 25.0) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                if player is not None:
                    self._player = player
                return
            self._player = player
            self._thread = threading.Thread(
                target=self._run_event_loop,
                daemon=True,
                name="VisionSessionThread",
            )
            self._thread.start()

        if not self._ready_evt.wait(timeout=timeout):
            raise RuntimeError(f"La sesión de visión no se conectó en {timeout}s.")
        print("[Vision] ✅ Sesión lista")

    def analyze(self, image_bytes: bytes, mime_type: str, user_text: str) -> None:
        if not self._loop or not self._out_queue:
            print("[Vision] ⚠️  Sesión no iniciada — descartando la petición")
            return
        asyncio.run_coroutine_threadsafe(
            self._out_queue.put((image_bytes, mime_type, user_text)),
            self._loop,
        )

    def is_ready(self) -> bool:
        return self._session is not None

    def _run_event_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._session_loop())

    async def _session_loop(self) -> None:
        self._out_queue = asyncio.Queue(maxsize=30)
        self._audio_in = asyncio.Queue()

        client = genai.Client(
            api_key=get_api_key(),
            http_options={"api_version": "v1beta"},
        )
        config = gtypes.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            system_instruction=_SYSTEM_PROMPT,
            speech_config=gtypes.SpeechConfig(
                voice_config=gtypes.VoiceConfig(
                    prebuilt_voice_config=gtypes.PrebuiltVoiceConfig(voice_name="Charon")
                )
            ),
        )

        backoff = 2.0
        while True:
            try:
                print("[Vision] 🔌 Conectando...")
                async with client.aio.live.connect(model=_LIVE_MODEL, config=config) as session:
                    self._session = session
                    self._ready_evt.set()
                    backoff = 2.0
                    print("[Vision] ✅ Conectado")

                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self._send_loop())
                        tg.create_task(self._recv_loop())
                        tg.create_task(self._play_loop())

            except* Exception as eg:
                for exc in eg.exceptions:
                    print(f"[Vision] ⚠️  Error de sesión: {exc}")
            finally:
                self._session = None
                self._ready_evt.clear()

            print(f"[Vision] 🔄 Reconectando en {backoff:.0f}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 1.5, 30.0)
            self._ready_evt.set()

    async def _send_loop(self) -> None:
        while True:
            image_bytes, mime_type, user_text = await self._out_queue.get()
            if not self._session:
                print("[Vision] ⚠️  Sin sesión — descartando imagen")
                continue
            try:
                b64 = base64.b64encode(image_bytes).decode("ascii")
                await self._session.send_client_content(
                    turns={
                        "parts": [
                            {"inline_data": {"mime_type": mime_type, "data": b64}},
                            {"text": user_text},
                        ]
                    },
                    turn_complete=True,
                )
                print(f"[Vision] 📤 Enviados {len(image_bytes):,} bytes — '{user_text[:60]}'")
            except Exception as e:
                err_msg = str(e)[:200]
                print(f"[Vision] ⚠️  Error de envío: {err_msg}")
                if self._player:
                    with contextlib.suppress(Exception):
                        self._player.write_log(
                            f"ERROR: No se pudo enviar la imagen al modelo Vision. {err_msg}"
                        )
                # Don't crash — continue processing next images
                await asyncio.sleep(0.5)

    async def _recv_loop(self) -> None:
        transcript: list[str] = []
        try:
            async for response in self._session.receive():
                if response.data:
                    await self._audio_in.put(response.data)

                sc = response.server_content
                if not sc:
                    continue

                # Handle model errors gracefully (e.g. unsupported input)
                if sc.model_turn:
                    for part in sc.model_turn.parts or []:
                        if hasattr(part, "text") and part.text:
                            chunk = part.text.strip()
                            if chunk:
                                transcript.append(chunk)

                if sc.output_transcription and sc.output_transcription.text:
                    chunk = sc.output_transcription.text.strip()
                    if chunk:
                        transcript.append(chunk)

                if sc.turn_complete:
                    if transcript and self._player:
                        full = re.sub(r"\s+", " ", " ".join(transcript)).strip()
                        if full:
                            self._player.write_log(f"O.R.I.O.N: {full}")
                            print(f"[Vision] 💬 {full}")
                    transcript = []

        except Exception as e:
            err_msg = str(e)[:200]
            print(f"[Vision] ⚠️  Error de recepción: {err_msg}")
            if self._player:
                with contextlib.suppress(Exception):
                    self._player.write_log(f"ERROR: Visión desconectada — {err_msg}")
            raise

    async def _play_loop(self) -> None:
        stream = sd.RawOutputStream(
            samplerate=_RECEIVE_SAMPLE_RATE,
            channels=_CHANNELS,
            dtype="int16",
            blocksize=_CHUNK_SIZE,
        )
        stream.start()
        try:
            while True:
                chunk = await self._audio_in.get()
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[Vision] ❌ Error de reproducción: {e}")
            raise
        finally:
            stream.stop()
            stream.close()


_session = _VisionSession()
_session_lock = threading.Lock()
_session_up = False


def _ensure_session(player=None) -> None:
    global _session_up
    with _session_lock:
        if not _session_up:
            _session.start(player=player)
            _session_up = True
        elif player is not None:
            _session._player = player


from orion.core.tool_registry import tool


@tool(
    name="screen_process",
    description=(
        "Captures and analyzes the screen or webcam image. "
        "MUST be called when user asks what is on screen, what you see, "
        "analyze my screen, look at camera, etc. "
        "You have NO visual ability without this tool. "
        "After calling this tool, stay SILENT — the vision module speaks directly."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "angle": {
                "type": "STRING",
                "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'",
            },
            "text": {
                "type": "STRING",
                "description": "The question or instruction about the captured image",
            },
        },
        "required": ["text"],
    },
    runs_in_thread=True,
    fallback=(
        "Vision module activated. Stay silent — the vision module will speak directly to the user."
    ),
)
def screen_process(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> bool:

    params = parameters or {}
    user_text = (params.get("text") or params.get("user_text") or "").strip()
    angle = params.get("angle", "screen").lower().strip()

    if not user_text:
        print("[Vision] ⚠️  No se proporcionó pregunta — abortando")
        return False

    print(f"[Vision] ▶ angle={angle!r}  pregunta='{user_text[:80]}'")

    try:
        _ensure_session(player=player)
    except Exception as e:
        print(f"[Vision] ❌ No se pudo iniciar la sesión: {e}")
        return False

    try:
        if angle == "camera":
            image_bytes, mime_type = _capture_camera()
            print(f"[Vision] 📷 Cámara: {len(image_bytes):,} bytes")
        else:
            image_bytes, mime_type = _capture_screen()
            print(f"[Vision] 🖥️  Pantalla: {len(image_bytes):,} bytes")
    except Exception as e:
        print(f"[Vision] ❌ Error de captura: {e}")
        return False

    _session.analyze(image_bytes, mime_type, user_text)
    return True


def warmup_session(player=None) -> None:
    try:
        _ensure_session(player=player)
    except Exception as e:
        print(f"[Vision] ⚠️  El precalentamiento falló: {e}")


if __name__ == "__main__":
    print("[TEST] screen_processor.py")
    print("=" * 52)
    mode = input("angle — screen / camera (predeterminado: screen): ").strip().lower() or "screen"
    q = input("Pregunta (Enter = por defecto): ").strip() or "¿Qué ves? Sé breve."

    t0 = time.perf_counter()
    warmup_session()
    print(f"Sesión lista en {time.perf_counter() - t0:.2f}s\n")

    t1 = time.perf_counter()
    ok = screen_process({"angle": mode, "text": q})
    print(f"En cola en {time.perf_counter() - t1:.3f}s — esperando audio...")
    time.sleep(10)
    print("Listo." if ok else "Falló.")
