"""orion.runtime — Núcleo Live de Orion.

Define la clase ``OrionLive`` que orquesta la sesión Gemini Live:
audio bidireccional + ejecución de herramientas + sincronización con
la UI. Los métodos pesados están repartidos en mixins para mantener
este archivo legible:

  - :class:`orion.audio.AudioMixin` — loops de I/O de audio.
  - :class:`orion.live_session.LiveSessionMixin` — config + handlers
    Live-only + watchdog.

Acá vive solamente:
  - ``__init__`` (cablea TODO el estado que los mixins leen).
  - Callbacks de UI (``_on_text_command``, ``_ui_state``).
  - Helpers de speaking (``set_speaking``, ``speak``, ``speak_error``,
    ``interrupt``).
  - Dispatcher de tools (``_execute_tool`` + ``_execute_tool_body``).
  - El loop ``run()`` que conecta a Live y arma el TaskGroup.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading

from google import genai
from google.genai import types

from orion._helpers import _first_real_exception
from orion.audio import AudioMixin
from orion.config import get_api_key
from orion.core.logger import get_logger
from orion.core.mcp_client import MCPManager, set_mcp_manager
from orion.core.tool_registry import ToolRegistry
from orion.domain.memory.memory_manager import update_memory
from orion.live_session import LIVE_MODEL, LiveSessionMixin
from orion.plugins.base import PluginRegistry

log = get_logger("orion.runtime")


class OrionLive(LiveSessionMixin, AudioMixin):
    """Maneja la sesión Live con Gemini: audio bidireccional, ejecución de
    herramientas y sincronización con la interfaz."""

    def __init__(self, ui):
        self.ui = ui
        self.session = None
        self.audio_in_queue = None
        self.out_queue = None
        self._loop = None
        self._is_speaking = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command
        self.ui.on_interrupt = self.interrupt
        self._turn_done_event: asyncio.Event | None = None
        # Watchdog: marcas de tiempo para detectar cuelgues en PENSANDO.
        # Protegidas con su propio lock porque las escriben varios threads
        # (callback de sounddevice, executor en threadpool, watchdog asyncio)
        # y el watchdog las lee periódicamente. Sin lock, lecturas "stale"
        # mantenían PENSANDO bloqueado o saltaban estados.
        import time

        self._state_lock = threading.Lock()
        self._pensando_since: float | None = None
        self._last_activity_ts: float = time.time()

        # ── Plugins ──
        self._plugin_registry = PluginRegistry()
        n = self._plugin_registry.discover_and_load()
        if n:
            log.info("Plugins disponibles: %s", list(self._plugin_registry.plugins.keys()))

        # ── Tool registry: inyecta los handlers Live-only ──
        # ``agent_task`` y ``shutdown_orion`` requieren acceso a la sesión
        # Live (task queue + speak + os._exit). Sobrescriben los stubs que
        # registró tools_bootstrap.
        self._tool_registry = ToolRegistry()
        self._inject_live_only_handlers()

        # ── MCP: conecta servidores externos del config ──
        # Carga config/mcp_servers.json y arranca cada subprocess MCP.
        # Las tools que expongan quedan en el mismo ToolRegistry, así que
        # aparecen junto a las builtin en Gemini Live, executor y planner.
        # Si el config está vacío o no existe, es no-op.
        self._mcp_manager = MCPManager()
        # Lo expone como singleton para que server/routes/mcp.py lo use.
        set_mcp_manager(self._mcp_manager)
        try:
            n_mcp = self._mcp_manager.start_all()
            if n_mcp:
                log.info("MCP: %d tools cargadas desde servidores externos", n_mcp)
        except Exception:
            log.exception("MCP: falló el arranque (continúo sin servidores externos)")

        # Cleanup de subprocesses MCP al salir (atexit cubre Ctrl+C y
        # cierres normales; el handler de shutdown_orion los para antes
        # del os._exit).
        import atexit

        atexit.register(self._mcp_manager.stop_all)

        # ── ask_user: conecta el manager singleton al bus ──
        # La tool `ask_user` (registrada en tools_bootstrap) usa este
        # publisher para emitir `ask_user.start` por WS y bloquear hasta
        # que el frontend devuelva la respuesta via `ask_user.response`
        # (manejado en server/ws.py).
        from orion.core.ask_user import get_ask_user

        def _publish_ask(qid: str, question: str, options: list, allow_other: bool) -> None:
            try:
                self.ui.publish(
                    "ask_user.start",
                    {
                        "question_id": qid,
                        "question": question,
                        "options": options,
                        "allow_other": allow_other,
                    },
                )
            except Exception as e:
                log.warning("publish ask_user.start falló: %s", e)

        get_ask_user().set_publisher(_publish_ask)

        # ── chat_brain context: el bus invoca run_text_turn con estos ──
        # registries cuando el cerebro activo no es Gemini. Sin esto, el
        # módulo cae al ToolRegistry singleton igual, pero sin plugins.
        try:
            self.ui.attach_chat_brain_context(
                tool_registry=self._tool_registry,
                plugin_registry=self._plugin_registry,
            )
        except AttributeError:
            # Bus viejo sin la API: no rompe la inicialización.
            log.debug("Bus sin attach_chat_brain_context — versión vieja del event_bus")

    # ── Callbacks de UI ──────────────────────────────────────────────────
    def _on_text_command(self, text: str):
        """Recibe texto desde la UI (input manual o eventos como archivo cargado).
        Captura locales para evitar race conditions con la reconexión.
        """
        loop = self._loop
        session = self.session
        if not loop or not session:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                session.send_client_content(turns={"parts": [{"text": text}]}, turn_complete=True),
                loop,
            )
        except Exception as e:
            log.warning("on_text_command falló: %s", e)

    def _ui_state(self, state: str):
        """Cambia el estado UI y mantiene el contador del watchdog."""
        import time

        now = time.time()
        with self._state_lock:
            self._pensando_since = now if state == "PENSANDO" else None
            self._last_activity_ts = now
        self.ui.set_state(state)

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self._ui_state("HABLANDO")
        elif not self.ui.muted:
            self._ui_state("ESCUCHANDO")

    def speak(self, text: str):
        """Hace que ORION diga algo (enviando el texto al modelo Live)."""
        loop = self._loop
        session = self.session
        if not loop or not session:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                session.send_client_content(turns={"parts": [{"text": text}]}, turn_complete=True),
                loop,
            )
        except Exception as e:
            log.warning("speak falló: %s", e)

    def speak_error(self, tool_name: str, error: str):
        """Informa al usuario de un error en una herramienta."""
        short = str(error)[:120]
        self.ui.write_log(f"ERROR: {tool_name} — {short}")
        self.speak(f"Hubo un problema al ejecutar {tool_name}. {short}")

    def interrupt(self):
        """Interrumpe inmediatamente la voz de ORION.

        - Vacía la cola de audio que está pendiente de reproducción.
        - Marca el turno como terminado y vuelve al estado ESCUCHANDO.
        """
        log.info("Interrupción del usuario solicitada")
        # Vaciar la cola de audio pendiente — la reproducción se detiene
        q = self.audio_in_queue
        if q is not None:
            try:
                while not q.empty():
                    q.get_nowait()
            except Exception:
                pass

        # Forzar el turno como terminado
        if self._turn_done_event is not None:
            with contextlib.suppress(Exception):
                self._loop.call_soon_threadsafe(self._turn_done_event.set)

        self.set_speaking(False)

        # Avisar al modelo que pare (le enviamos un mensaje vacío de turno)
        loop = self._loop
        session = self.session
        if loop and session:
            try:
                asyncio.run_coroutine_threadsafe(
                    session.send_client_content(
                        turns={
                            "parts": [
                                {
                                    "text": "[INTERRUPCIÓN_USUARIO] El usuario te ha pedido detenerte. No continúes."
                                }
                            ]
                        },
                        turn_complete=True,
                    ),
                    loop,
                )
            except Exception as e:
                log.warning("Interrupción remota falló: %s", e)

    # ── Ejecución de herramientas ────────────────────────────────────────
    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        log.info("Tool call: %s  %s", name, args)
        self._ui_state("PENSANDO")
        # Notifica al frontend que hay una tool en ejecución. El bus lo
        # propaga al WS y el OrbHUD entra en modo "tool" + aparece banner.
        try:
            self.ui.publish(
                "tool.call.start",
                {
                    "name": name,
                    "args": {k: str(v)[:80] for k, v in args.items()},
                },
            )
        except Exception as e:
            log.debug("publish tool.call.start falló: %s", e)

        try:
            return await self._execute_tool_body(fc, name, args)
        finally:
            # Garantiza que el banner desaparezca incluso en early-returns
            # o excepciones no atrapadas más arriba.
            try:
                self.ui.publish("tool.call.end", {"name": name})
            except Exception as e:
                log.debug("publish tool.call.end falló: %s", e)

    async def _execute_tool_body(self, fc, name: str, args: dict) -> types.FunctionResponse:
        # quick_note: guarda una nota en el panel de notas rápidas
        if name == "quick_note":
            text = (args.get("text") or "").strip()
            pinned = bool(args.get("pinned", False))
            if not text:
                if not self.ui.muted:
                    self.ui.set_state("ESCUCHANDO")
                return types.FunctionResponse(
                    id=fc.id,
                    name=name,
                    response={"result": "No se proporcionó texto para la nota."},
                )
            try:
                from orion.domain.memory.quick_notes import add_note, update_note

                n = add_note(text)
                if pinned and n.get("id"):
                    update_note(n["id"], pinned=True)
                # Refresca el panel de notas (Qt) o emite evento WS (bus).
                # Sustituye el reach-in previo a ``_win._notes_panel`` (R-02).
                with contextlib.suppress(AttributeError):
                    self.ui.notes_changed()
                self.ui.write_log(f"NOTA guardada: {text[:80]}")
                result_msg = "Nota guardada en el panel de notas rápidas."
            except Exception as e:
                log.warning("quick_note falló: %s", e)
                result_msg = f"No se pudo guardar la nota: {e}"
            if not self.ui.muted:
                self._ui_state("ESCUCHANDO")
            return types.FunctionResponse(id=fc.id, name=name, response={"result": result_msg})

        # save_memory se ejecuta de forma silenciosa (caso especial)
        if name == "save_memory":
            category = args.get("category", "notes")
            key = args.get("key", "")
            value = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                log.info("Memoria guardada: %s/%s = %s", category, key, value)
            if not self.ui.muted:
                self._ui_state("ESCUCHANDO")
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": "ok", "silent": True}
            )

        # Despacho unificado: primero el ToolRegistry (builtin + Live-only
        # overrides), después los plugins out-of-tree. Cada call sync se
        # ejecuta en el thread pool con un timeout — el registry no maneja
        # threading, eso es responsabilidad de este caller.
        result = "Listo."
        loop = asyncio.get_event_loop()
        plugin = None

        registry_entry = self._tool_registry.get(name)
        if registry_entry is None:
            plugin = self._plugin_registry.get(name)

        try:
            if registry_entry is None and plugin is None:
                result = f"Herramienta desconocida: {name}"
            elif plugin is not None:
                timeout = plugin.timeout
                try:
                    result = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda: plugin.execute(args, player=self.ui, speak=self.speak),
                        ),
                        timeout=timeout,
                    )
                except TimeoutError:
                    result = f"Plugin '{name}' tardó más de {timeout}s y fue cancelado."
                    log.warning("Timeout en plugin %s (%ds)", name, timeout)
                if not result:
                    result = "Listo."
            else:
                decl, _handler = registry_entry
                timeout = decl.timeout or self._DEFAULT_TOOL_TIMEOUT
                current_file = getattr(self.ui, "current_file", None)
                try:
                    result = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda: self._tool_registry.call_sync(
                                name,
                                args,
                                player=self.ui,
                                speak=self.speak,
                                current_file=current_file,
                            ),
                        ),
                        timeout=timeout,
                    )
                except TimeoutError:
                    result = f"La herramienta '{name}' tardó más de {timeout}s y fue cancelada."
                    log.warning("Timeout en %s (%ds)", name, timeout)
                if not result:
                    result = "Listo."

        except Exception as e:
            result = f"La herramienta '{name}' falló: {e}"
            log.error("Tool %s falló", name, exc_info=True)
            self.speak_error(name, e)

        if not self.ui.muted:
            self._ui_state("ESCUCHANDO")

        log.info("Tool result: %s → %s", name, str(result)[:80])
        return types.FunctionResponse(id=fc.id, name=name, response={"result": result})

    # ── Loop principal ───────────────────────────────────────────────────
    async def run(self):
        try:
            client = genai.Client(api_key=get_api_key(), http_options={"api_version": "v1beta"})
        except RuntimeError as e:
            log.error("Error de configuración: %s", e)
            self.ui.write_log(f"ERROR DE CONFIGURACIÓN: {e}")
            return

        # Backoff exponencial: 3s → 5s → 10s → 20s → 30s (máx)
        # Evita bombardear la API si Gemini está caído.
        backoff_s = 3
        max_backoff_s = 30

        while True:
            try:
                log.info("Conectando a Gemini Live...")
                self._ui_state("PENSANDO")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session = session
                    self._loop = asyncio.get_event_loop()
                    # maxsize=200: si el driver de audio se atasca, la cola
                    # crecería sin tope. 200 chunks @ 24kHz/PCM16 ≈ 8s de
                    # audio bufferizado — suficiente para sobrevivir a un
                    # hipo del SO sin OOM.
                    # 1000 chunks ≈ 20s de audio (a 24kHz/int16, chunks de
                    # 480 samples). Suficiente para que el receiver no
                    # bloquee durante una respuesta normal y dé tiempo a
                    # _play_audio a drenar. Antes era 200 + drop-oldest, lo
                    # que causaba aceleración perceptible del TTS.
                    self.audio_in_queue = asyncio.Queue(maxsize=1000)
                    self.out_queue = asyncio.Queue(maxsize=10)
                    self._turn_done_event = asyncio.Event()

                    log.info("Conectado a Gemini Live.")
                    self._ui_state("ESCUCHANDO")
                    self.ui.write_log("SISTEMA: ORION en línea.")

                    # Conexión exitosa → reset del backoff
                    backoff_s = 3

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._watchdog())

            except BaseException as e:
                # La conexión puede tirar TimeoutError directo (handshake
                # fallido antes de entrar al TaskGroup) o un ExceptionGroup
                # si el TaskGroup ya estaba activo y un task interno crasheó.
                # Desempaquetamos para clasificar igual en ambos casos.
                root = _first_real_exception(e)

                if isinstance(root, TimeoutError):
                    # Handshake a Gemini Live timeó. Causa habitual: red
                    # lenta / firewall / antivirus / proxy bloqueando wss://
                    # a generativelanguage.googleapis.com. NO es bug de Orion.
                    log.warning(
                        "Handshake a Gemini Live timeó. "
                        "Revisa red/firewall/antivirus. Reintentando…"
                    )
                    self.ui.write_log("SISTEMA: Conexión a Gemini lenta o bloqueada. Reintentando…")
                elif isinstance(root, (ConnectionError, OSError)):
                    # DNS, conexión rechazada, host inalcanzable. Transient.
                    log.warning(
                        "Error de red conectando a Gemini Live: %s. Reintentando…",
                        root,
                    )
                    self.ui.write_log("SISTEMA: Sin conexión a Gemini. Reintentando…")
                else:
                    # Cualquier otro error: SÍ logueamos con traza completa
                    # porque puede ser un bug real (auth, config, SDK).
                    log.warning("Sesión desconectada: %s", root, exc_info=root)

            self.set_speaking(False)
            self._ui_state("PENSANDO")
            log.info("Reconectando en %ds...", backoff_s)
            await asyncio.sleep(backoff_s)
            # Crece el backoff para el siguiente intento si vuelve a fallar
            backoff_s = min(int(backoff_s * 1.8), max_backoff_s)


__all__ = ["OrionLive"]
