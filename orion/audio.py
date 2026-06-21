"""orion.audio — I/O de audio y bridge con la sesión Live.

Contiene el ``AudioMixin`` que ``OrionLive`` compone via herencia.
Métodos asíncronos: ``_send_realtime``, ``_listen_audio``,
``_receive_audio``, ``_play_audio``.

NO maneja la conexión a Gemini Live (eso es ``orion.live_session``) ni
el bootstrap (eso es ``orion.bootstrap``). Solo audio + el receiver del
WS de Live (porque está acoplado a la cola de audio).
"""

from __future__ import annotations

import asyncio
import contextlib

import sounddevice as sd

from orion._helpers import _clean_transcript, _first_real_exception
from orion.core.logger import get_logger

log = get_logger("orion.audio")

# ── Audio constants ────────────────────────────────────────────────────
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024


class AudioMixin:
    """Mixin con los loops de I/O de audio.

    Espera que ``self`` (la clase host, e.g. OrionLive) tenga inicializados:
      - ``self.session`` (genai.live session)
      - ``self.audio_in_queue`` (asyncio.Queue)
      - ``self.out_queue`` (asyncio.Queue)
      - ``self._loop`` (asyncio loop)
      - ``self._is_speaking``, ``self._speaking_lock``
      - ``self._state_lock``, ``self._last_activity_ts``
      - ``self._turn_done_event``
      - ``self.ui`` (event bus con muted/write_log/stream_chunk/persist_log_only)
      - ``self._execute_tool`` (método de la clase host)
      - ``self.set_speaking`` (método de la clase host)
    """

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        log.info("Micrófono iniciado")
        loop = asyncio.get_event_loop()

        def _enqueue(payload):
            """Encola el chunk. Si la cola está llena, descarta el más antiguo
            (evita el bug en el que ``put_nowait`` lanzaba QueueFull y la
            sesión quedaba ‘pensando’ sin recibir audio)."""
            try:
                self.out_queue.put_nowait(payload)
            except asyncio.QueueFull:
                with contextlib.suppress(Exception):
                    self.out_queue.get_nowait()
                with contextlib.suppress(Exception):
                    self.out_queue.put_nowait(payload)

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                orion_speaking = self._is_speaking
            # No enviar audio mientras ORION habla (evita feedback)
            if not orion_speaking and not self.ui.muted:
                data = indata.tobytes()
                loop.call_soon_threadsafe(_enqueue, {"data": data, "mime_type": "audio/pcm"})

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                log.info("Stream de micrófono abierto")
                while True:
                    await asyncio.sleep(0.1)
        except sd.PortAudioError as e:
            log.error("Error de audio en micrófono: %s", e)
            raise
        except OSError as e:
            log.error("Error de sistema en micrófono: %s", e)
            raise

    async def _receive_audio(self):
        log.info("Recepción de audio iniciada")
        out_buf, in_buf = [], []
        # turn_id por mensaje en streaming. Generamos uno nuevo al primer
        # chunk de cada turno y lo limpiamos al turn_complete. El frontend
        # usa este id para identificar al mensaje y anexar deltas en lugar
        # de crear uno nuevo por chunk.
        import uuid as _uuid

        out_turn_id: str | None = None
        in_turn_id: str | None = None

        try:
            while True:
                async for response in self.session.receive():
                    if response.data:
                        import time

                        with self._state_lock:
                            self._last_activity_ts = time.time()
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        # NUNCA droppear chunks de audio: si dropeamos,
                        # faltan pedazos del waveform y el oído lo percibe
                        # como "lee acelerado" porque las pausas naturales
                        # desaparecen. Mejor hacer backpressure: si la cola
                        # está llena, esperamos a que _play_audio drene
                        # algo. La cola tiene maxsize=1000 (cubre ~20s de
                        # audio a 24kHz int16), así que solo bloquearía si
                        # el sistema está realmente saturado.
                        await self.audio_in_queue.put(response.data)

                    if response.server_content:
                        sc = response.server_content

                        # Model turn (text responses — may include error messages)
                        if sc.model_turn:
                            for part in sc.model_turn.parts or []:
                                if hasattr(part, "text") and part.text:
                                    txt = part.text.strip()
                                    if txt and txt.lower().startswith(
                                        ("error", "cannot", "i can't")
                                    ):
                                        log.warning("Modelo respondió error: %s", txt[:120])
                                        self.ui.write_log(f"ORION: {txt}")

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)
                                if out_turn_id is None:
                                    out_turn_id = _uuid.uuid4().hex[:12]
                                # Emitimos el delta al frontend para streaming
                                # palabra-por-palabra en el chat, en sync con
                                # el audio que está reproduciendo.
                                self.ui.stream_chunk(
                                    role="orion",
                                    delta=txt,
                                    turn_id=out_turn_id,
                                    final=False,
                                )

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)
                                if in_turn_id is None:
                                    in_turn_id = _uuid.uuid4().hex[:12]
                                self.ui.stream_chunk(
                                    role="user",
                                    delta=txt,
                                    turn_id=in_turn_id,
                                    final=False,
                                )

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            # Cerrar streaming + persistir el log SIN re-publicarlo
                            # al WS. Antes acá se usaba `write_log` (que publica
                            # `log` event) como "safety-net para frontend cacheado
                            # viejo". El frontend actual SIEMPRE consume
                            # `chat.stream`, y el dedup contra el `log`
                            # tradicional falla cuando user+orion comparten turno
                            # (mira sólo el último mensaje, no encuentra match,
                            # pushea duplicado). Resultado visible: cada turno
                            # aparecía dos veces en el chat. Con `persist_log_only`
                            # el chat ve un solo evento (`chat.stream` final=True)
                            # y la conversación queda persistida igual.
                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                if in_turn_id:
                                    self.ui.stream_chunk(
                                        role="user",
                                        delta="",
                                        turn_id=in_turn_id,
                                        final=True,
                                    )
                                self.ui.persist_log_only(f"Tú: {full_in}")
                            in_buf = []
                            in_turn_id = None

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                if out_turn_id:
                                    self.ui.stream_chunk(
                                        role="orion",
                                        delta="",
                                        turn_id=out_turn_id,
                                        final=True,
                                    )
                                self.ui.persist_log_only(f"ORION: {full_out}")
                            out_buf = []
                            out_turn_id = None

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            log.debug("Function call: %s", fc.name)
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(function_responses=fn_responses)
        except Exception as e:
            real = _first_real_exception(e)
            msg = str(real)[:200]
            log.error("Error en recepción de audio: %s", msg)
            self.ui.write_log("SISTEMA: Error de conexión — reconectando…")
            raise

    async def _play_audio(self):
        log.info("Reproducción de audio iniciada")

        # blocksize=0 deja que PortAudio elija el tamaño óptimo según el
        # device. latency='high' usa un buffer interno generoso (típico
        # ~100-300ms) — para TTS no nos importa la latencia, sí evitar
        # underruns que se perciben como aceleración/saltos del audio.
        # Antes blocksize=1024 + latency default causaba glitches en Windows.
        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=0,
            latency="high",
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(self.audio_in_queue.get(), timeout=0.1)
                except TimeoutError:
                    # Sin chunks y el turno terminó → ORION dejó de hablar
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
        except sd.PortAudioError as e:
            log.error("Error de audio en reproducción: %s", e)
            raise
        except OSError as e:
            log.error("Error de sistema en reproducción: %s", e)
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()


__all__ = ["CHANNELS", "CHUNK_SIZE", "RECEIVE_SAMPLE_RATE", "SEND_SAMPLE_RATE", "AudioMixin"]
