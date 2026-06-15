"""
O.R.I.O.N — Operador de Redes Inteligentes y Optimización Neural
================================================================
Núcleo principal del asistente. Se conecta a Gemini Live, maneja el
audio bidireccional, ejecuta herramientas y se sincroniza con la UI.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

# ── UTF-8 stdout/stderr (Windows fix) ────────────────────────────────
# La consola por defecto en Windows decodifica con cp1252, que NO sabe
# leer la mayoría de emojis ni caracteres unicode (⏸, —, ✅, etc). Hay
# decenas de print() con emojis dispersos por el codebase (browser,
# code_helper, iot, etc); cuando alguno se ejecuta bajo un request HTTP,
# UnicodeEncodeError revienta el handler entero y el cliente recibe 500.
# Reconfigurar acá una sola vez resuelve TODOS de un saque, sin tocar
# cada print individual. `errors="replace"` evita que un caracter raro
# de un futuro print rompa nada (lo cambia por "?").
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    # En entornos donde stdout no soporta reconfigure (pythonw, sidecar
    # sin consola), no es bloqueante — los print() simplemente no salen.
    pass

import sounddevice as sd
from google import genai
from google.genai import types

from config import get_api_key, PROMPT_PATH
from core.logger import get_logger
from plugins.base import PluginRegistry
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)

# Desde la Fase 7 Orion es web-only: la UI vive en web/ y el "player"
# que reciben main.OrionLive y las acciones es el OrionEventBus
# directamente (no hay UI Qt ni FanOut).

# ── Tool registry ───────────────────────────────────────────────────────────
# Las acciones builtin se registran en core.tools_bootstrap; sus imports
# son lazy (dentro de cada handler) para no penalizar el arranque ni los
# tests que no toquen una tool concreta.
# Los servidores MCP externos se conectan en OrionLive.__init__ y añaden
# sus tools al MISMO registry — Gemini Live, executor y planner las ven
# automáticamente.
from core.tool_registry  import ToolDeclaration, ToolRegistry
from core.tools_bootstrap import register_builtin_tools
from core.mcp_client      import MCPManager, set_mcp_manager

register_builtin_tools()

log = get_logger("main")

# ── PATH para subprocesses (Windows fix) ────────────────────────────────────
# En Windows, subprocess.run([bin, ...], env={...PATH...}) NO usa el PATH del
# env kwarg — CreateProcessW resuelve binarios consultando el PATH del proceso
# padre. Por eso inyectamos tools/<x>/ a os.environ una sola vez al arrancar,
# así los subprocesses (gog, etc.) heredan el PATH correctamente sin tocar
# nada más.
try:
    import os as _os
    from core.cli_installer import extra_path_dirs as _extra_path_dirs
    _extras = _extra_path_dirs()
    if _extras:
        _cur = _os.environ.get("PATH", "")
        _missing = [d for d in _extras if d not in _cur.split(_os.pathsep)]
        if _missing:
            _os.environ["PATH"] = _os.pathsep.join(_missing + [_cur])
            log.info("PATH extendido con tools/: %s", _missing)
except Exception as _e:
    log = get_logger("main")
    log.warning("No pude extender PATH con tools/: %s", _e)

LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024


def _load_system_prompt() -> str:
    """Carga el prompt del sistema. Si no existe, usa uno por defecto en español."""
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        log.warning("Prompt no encontrado en %s, usando default", PROMPT_PATH)
        return (
            "You are ORION (Operador de Redes Inteligentes y Optimización Neural), "
            "a personal voice assistant. Be concise, direct, and always use "
            "the available tools to complete tasks. "
            "Never simulate or fabricate results — always call the "
            "appropriate tool.\n\n"
            "LANGUAGE: ALWAYS respond ONLY in Spanish. Never English, never mixed. "
            "If a tool returns English content, translate the summary to Spanish "
            "before speaking. Every reply — including time, date, math, errors — "
            "must be 100% Spanish."
        )


# Limpieza de transcripciones (caracteres de control que a veces emite el modelo)
_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)
# Tokens espurios que el modelo a veces transcribe a partir de ruido ambiental
# (chasquidos, micro-ruido, etc.). Si la transcripción entera es uno de éstos,
# se descarta.
_TRANSCRIPT_NOISE = {
    "noice", "noise", "[noise]", "[ruido]", "(noise)", "(ruido)",
    "uh", "um", "uhm", "hmm", "mmh", "mm", "ah", "eh",
    "...", "…", ".", "-",
}
# Limpieza de marcadores estilo [BLANK_AUDIO], (background noise), [música], etc.
_BRACKET_RE = re.compile(r"[\[\(\<](?:blank[_ ]?audio|background|music|música|silencio|ruido|noise|inaudible|aplausos|applause)[^\]\)\>]*[\]\)\>]", re.IGNORECASE)

def _first_real_exception(exc: BaseException) -> BaseException:
    """Desempaqueta ``ExceptionGroup`` para devolver la primera excepción
    "real" (no-grupo). Si el argumento ya es una excepción normal, la
    devuelve tal cual. Si está anidado (group dentro de group), busca en
    profundidad hasta encontrar la raíz."""
    while isinstance(exc, BaseExceptionGroup):
        inner = exc.exceptions
        if not inner:
            return exc
        exc = inner[0]
    return exc


def _clean_transcript(text: str) -> str:
    text = _CTRL_RE.sub("", text)
    text = _BRACKET_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    text = text.strip()
    if text.lower() in _TRANSCRIPT_NOISE:
        return ""
    # Una sola palabra muy corta sin letras alfabéticas → ruido
    if text and len(text) <= 2 and not any(c.isalpha() for c in text):
        return ""
    return text


# ============================================================================
#  Declaración de herramientas para Gemini
#  Autogenerada desde el ToolRegistry. Las descripciones se mantienen en
#  inglés (Gemini las entiende mejor) y el comportamiento sigue siendo en
#  español. Para añadir/modificar una tool edita ``core/tools_bootstrap.py``.
# ============================================================================
TOOL_DECLARATIONS = ToolRegistry().to_gemini_declarations()



# ============================================================================
#  Núcleo Live de ORION
# ============================================================================
class OrionLive:
    """Maneja la sesión Live con Gemini: audio bidireccional, ejecución de
    herramientas y sincronización con la interfaz."""

    def __init__(self, ui):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command
        self.ui.on_interrupt    = self.interrupt
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
        from core.ask_user import get_ask_user
        def _publish_ask(qid: str, question: str, options: list, allow_other: bool) -> None:
            try:
                self.ui.publish("ask_user.start", {
                    "question_id": qid,
                    "question":    question,
                    "options":     options,
                    "allow_other": allow_other,
                })
            except Exception as e:
                log.warning("publish ask_user.start falló: %s", e)
        get_ask_user().set_publisher(_publish_ask)

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
                session.send_client_content(
                    turns={"parts": [{"text": text}]},
                    turn_complete=True
                ),
                loop
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
                session.send_client_content(
                    turns={"parts": [{"text": text}]},
                    turn_complete=True
                ),
                loop
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
            try:
                self._loop.call_soon_threadsafe(self._turn_done_event.set)
            except Exception:
                pass

        self.set_speaking(False)

        # Avisar al modelo que pare (le enviamos un mensaje vacío de turno)
        loop = self._loop
        session = self.session
        if loop and session:
            try:
                asyncio.run_coroutine_threadsafe(
                    session.send_client_content(
                        turns={"parts": [{"text": "[INTERRUPCIÓN_USUARIO] El usuario te ha pedido detenerte. No continúes."}]},
                        turn_complete=True
                    ),
                    loop,
                )
            except Exception as e:
                log.warning("Interrupción remota falló: %s", e)

    # ── Configuración de la sesión ───────────────────────────────────────
    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        # Nombres de días/meses en español para el contexto temporal
        dias  = ["Lunes", "Martes", "Miércoles", "Jueves",
                 "Viernes", "Sábado", "Domingo"]
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                 "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

        now      = datetime.now()
        time_str = (
            f"{dias[now.weekday()]}, {now.day} de {meses[now.month - 1]} de {now.year} "
            f"— {now.strftime('%H:%M')}"
        )
        time_ctx = (
            f"[CURRENT DATE AND TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this information to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)

        # Catálogo de skills — Gemini Live necesita saber qué hay instalado
        # para decidir cuándo invocar use_skill. Sin este bloque, ve la tool
        # genérica pero no los skill_ids disponibles.
        try:
            from core.skills import build_skill_catalog_prompt
            skills_cat = build_skill_catalog_prompt()
            if skills_cat:
                parts.append("\n" + skills_cat)
        except Exception as e:
            log.warning("No pude inyectar catálogo de skills: %s", e)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            # Leemos del registry en vivo (no de la constante module-level)
            # porque el MCPManager pudo haber añadido tools después del
            # import. Plugins out-of-tree se concatenan aparte como antes.
            tools=[{"function_declarations":
                    self._tool_registry.to_gemini_declarations()
                    + self._plugin_registry.get_tool_declarations()}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                ),
                # CRÍTICO: sin language_code el TTS usa prosodia inglesa por
                # default y lee español rápido y artificial. Setearlo a es-US
                # fuerza al modelo a ajustar el ritmo, las pausas y la
                # entonación al castellano latinoamericano.
                language_code="es-US",
            ),
        )

    # ── Ejecución de herramientas ────────────────────────────────────────
    # Timeout por defecto (segundos) para evitar que ORION quede congelado
    # esperando una herramienta que no responde. Los overrides por tool
    # viven en ``core/tools_bootstrap.py`` (ToolDeclaration.timeout).
    _DEFAULT_TOOL_TIMEOUT = 60

    def _inject_live_only_handlers(self) -> None:
        """Sobrescribe los stubs Live-only registrados por tools_bootstrap.

        Estos handlers necesitan acceso al ``OrionLive`` (task queue, speak,
        ui.notes_changed) y por eso no pueden vivir en el bootstrap puro.
        """
        # ── agent_task: encola una goal en el agente autónomo ──
        # Modo semi-síncrono: espera hasta SYNC_TIMEOUT por el resultado real
        # para devolverlo como tool_response (el patrón nativo de function
        # calling que Gemini procesa correctamente). Si la tarea tarda más,
        # cae al fallback async que inyecta el resultado vía send_client_content
        # cuando finalmente termina.
        AGENT_TASK_SYNC_TIMEOUT = 110  # debe ser < timeout del ToolDeclaration

        # Sanitizer del output: arregla mojibake UTF-8/cp1252 si quedó algo
        # crudo, elimina IDs hexadecimales largos (ruido para TTS), y
        # convierte fechas ISO a formato hablado natural para que Gemini Live
        # no se tropiece al leerlas en voz alta.
        def _sanitize_for_voice(text: str) -> str:
            import re as _re
            if not text:
                return text

            # 1) Reparar mojibake común (Ã³ → ó, Ã± → ñ, Ã¡ → á, Ã© → é,
            # Ã­ → í, Ãº → ú, Ã‘ → Ñ). Se da cuando UTF-8 se decodificó como
            # Latin-1/cp1252 — por si algo escapó al fix de PYTHONUTF8.
            try:
                # Heurística: si vemos "Ã" seguido de char ascii, probablemente
                # es mojibake. Lo más limpio es re-encode→decode.
                if "Ã" in text:
                    fixed = text.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
                    if fixed and "Ã" not in fixed:
                        text = fixed
            except Exception:
                pass

            # 2) Quitar IDs largos opacos — los TTS se atoran leyéndolos
            # char por char. Dos pasadas:
            #   a) Hex puro ≥12 chars (Gmail message IDs como 19ea794571e9c265)
            #   b) Alfanum ≥18 chars con ≥2 dígitos (Calendar IDs como
            #      47s3sarhgr0lurqlnmdbdu47f0, evita comerse palabras largas
            #      reales como "supercalifragilisticoexpialidocious").
            text = _re.sub(r"\b[0-9a-f]{12,}\b", "", text, flags=_re.IGNORECASE)
            def _looks_like_id(m: "_re.Match") -> str:
                s = m.group(0)
                return "" if sum(c.isdigit() for c in s) >= 2 else s
            text = _re.sub(r"\b[a-z0-9]{18,}\b", _looks_like_id, text, flags=_re.IGNORECASE)

            # 3) Fechas ISO a algo más hablable: "2026-06-09T14:45:00Z" →
            # "2026-06-09 14:45". El TTS lee mejor con espacio que con "T" y "Z".
            text = _re.sub(
                r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(?::\d{2})?Z?",
                r"\1 \2",
                text,
            )

            # 4) Colapsar runs largos de espacios (las tablas ASCII de gog
            # tienen columnas alineadas con muchos espacios → confunde al TTS).
            text = _re.sub(r" {3,}", "  ", text)
            # Borra cabeceras "ID  DATE..." si ya no aportan (la col ID se fue)
            text = _re.sub(r"^\s*ID\s+", "", text, flags=_re.MULTILINE)

            return text.strip()

        def h_agent_task(parameters: dict, **_kwargs) -> str:
            from agent.task_queue import get_queue, TaskPriority
            priority_map = {
                "low":    TaskPriority.LOW,
                "normal": TaskPriority.NORMAL,
                "high":   TaskPriority.HIGH,
            }
            priority = priority_map.get(
                (parameters.get("priority") or "normal").lower(),
                TaskPriority.NORMAL,
            )
            goal = parameters.get("goal", "")

            holder: dict[str, Any] = {
                "result":         None,
                "done":           threading.Event(),
                "sync_returned":  False,
            }

            def _on_done(task_id: str, result: Any) -> None:
                holder["result"] = result
                holder["done"].set()
                log.info("agent_task[%s] completed (result_len=%s, sync_returned=%s)",
                         task_id,
                         len(result) if isinstance(result, str) else "n/a",
                         holder["sync_returned"])
                # Fallback async: solo si el handler ya retornó por timeout
                # (Gemini ya recibió "tarea sigue corriendo" como tool_response
                # y se cerró el turn). Inyectamos como user-turn para reactivar.
                if holder["sync_returned"] and isinstance(result, str) and result.strip():
                    trimmed = _sanitize_for_voice(result.strip())
                    if len(trimmed) > 4000:
                        trimmed = trimmed[:4000] + "\n…[truncado]"
                    synthetic = (
                        f"[Resultado de la tarea anterior '{goal[:80]}':\n"
                        f"{trimmed}\n"
                        f"Resúmemelo al usuario hablando NATURAL en español, como conversación. "
                        f"NUNCA leas IDs hexadecimales (ej: 19ea794571e9c265, 47s3sarhgr...) — son ruido para el TTS. "
                        f"Convertí fechas ISO (2026-06-09T14:45:00Z) a lenguaje hablado ('martes 9 a las 14:45'). "
                        f"Si hay mojibake (AcciÃ³n, Ã±, etc.), interpretalo y leelo correcto (Acción, ñ). "
                        f"No digas 'se han listado' ni frases vacías.]"
                    )
                    try:
                        self._on_text_command(synthetic)
                    except Exception as e:
                        log.warning("Fallback async falló: %s", e)

            task_id = get_queue().submit(
                goal=goal,
                priority=priority,
                speak=self.speak,
                on_complete=_on_done,
            )
            log.info("agent_task[%s] queued, esperando hasta %ds sync…", task_id, AGENT_TASK_SYNC_TIMEOUT)

            # Espera bloqueante. h_agent_task corre en run_in_executor, así
            # que bloquear aquí NO bloquea el event loop de asyncio.
            if holder["done"].wait(timeout=AGENT_TASK_SYNC_TIMEOUT):
                result = holder["result"]
                if isinstance(result, str) and result.strip():
                    cleaned = _sanitize_for_voice(result)
                    log.info("agent_task[%s] devuelto sync (%d→%d chars) a Gemini",
                             task_id, len(result), len(cleaned))
                    return cleaned
                return "La tarea terminó sin producir salida visible."

            # Timeout: marcamos para que el on_complete inyecte el resultado
            # cuando finalmente llegue.
            holder["sync_returned"] = True
            log.warning("agent_task[%s] timeout sync (%ds) — fallback async", task_id, AGENT_TASK_SYNC_TIMEOUT)
            return (
                f"La tarea está tomando más de {AGENT_TASK_SYNC_TIMEOUT} segundos. "
                f"Sigue corriendo en background — te aviso con el resultado en cuanto termine."
            )

        # ── shutdown_orion: apaga el proceso tras un breve aviso ──
        def h_shutdown(parameters: dict, **_kwargs) -> str:
            self.ui.write_log("SISTEMA: Apagado solicitado.")
            self.speak("Hasta luego.")

            def _shutdown():
                import os, time
                time.sleep(1.5)
                # Para los subprocesses MCP antes del exit duro — os._exit
                # bypassea atexit y dejaría huérfanos.
                try:
                    self._mcp_manager.stop_all()
                except Exception:
                    pass
                os._exit(0)

            threading.Thread(target=_shutdown, daemon=True).start()
            return "Apagando ORION."

        # Preservamos las ToolDeclaration originales (timeouts, schemas)
        # y solo cambiamos el handler.
        agent_decl = self._tool_registry.get("agent_task")
        if agent_decl is not None:
            self._tool_registry.register(agent_decl[0], h_agent_task)
        shutdown_decl = self._tool_registry.get("shutdown_orion")
        if shutdown_decl is not None:
            self._tool_registry.register(shutdown_decl[0], h_shutdown)

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        log.info("Tool call: %s  %s", name, args)
        self._ui_state("PENSANDO")
        # Notifica al frontend que hay una tool en ejecución. El bus lo
        # propaga al WS y el OrbHUD entra en modo "tool" + aparece banner.
        try:
            self.ui.publish("tool.call.start", {
                "name": name,
                "args": {k: str(v)[:80] for k, v in args.items()},
            })
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
                    id=fc.id, name=name,
                    response={"result": "No se proporcionó texto para la nota."}
                )
            try:
                from memory.quick_notes import add_note, update_note
                n = add_note(text)
                if pinned and n.get("id"):
                    update_note(n["id"], pinned=True)
                # Refresca el panel de notas (Qt) o emite evento WS (bus).
                # Sustituye el reach-in previo a ``_win._notes_panel`` (R-02).
                try:
                    self.ui.notes_changed()
                except AttributeError:
                    pass
                self.ui.write_log(f"NOTA guardada: {text[:80]}")
                result_msg = "Nota guardada en el panel de notas rápidas."
            except Exception as e:
                log.warning("quick_note falló: %s", e)
                result_msg = f"No se pudo guardar la nota: {e}"
            if not self.ui.muted:
                self._ui_state("ESCUCHANDO")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": result_msg}
            )

        # save_memory se ejecuta de forma silenciosa (caso especial)
        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                log.info("Memoria guardada: %s/%s = %s", category, key, value)
            if not self.ui.muted:
                self._ui_state("ESCUCHANDO")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        # Despacho unificado: primero el ToolRegistry (builtin + Live-only
        # overrides), después los plugins out-of-tree. Cada call sync se
        # ejecuta en el thread pool con un timeout — el registry no maneja
        # threading, eso es responsabilidad de este caller.
        result = "Listo."
        loop   = asyncio.get_event_loop()
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
                except asyncio.TimeoutError:
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
                                name, args,
                                player=self.ui,
                                speak=self.speak,
                                current_file=current_file,
                            ),
                        ),
                        timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    result = (
                        f"La herramienta '{name}' tardó más de {timeout}s y fue cancelada."
                    )
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
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    # ── Loops de audio ───────────────────────────────────────────────────
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
                try:
                    self.out_queue.get_nowait()
                except Exception:
                    pass
                try:
                    self.out_queue.put_nowait(payload)
                except Exception:
                    pass

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                orion_speaking = self._is_speaking
            # No enviar audio mientras ORION habla (evita feedback)
            if not orion_speaking and not self.ui.muted:
                data = indata.tobytes()
                loop.call_soon_threadsafe(_enqueue,
                    {"data": data, "mime_type": "audio/pcm"}
                )

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
        in_turn_id:  str | None = None

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
                                    if txt and txt.lower().startswith(("error", "cannot", "i can't")):
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
                                    role="orion", delta=txt,
                                    turn_id=out_turn_id, final=False,
                                )

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)
                                if in_turn_id is None:
                                    in_turn_id = _uuid.uuid4().hex[:12]
                                self.ui.stream_chunk(
                                    role="user", delta=txt,
                                    turn_id=in_turn_id, final=False,
                                )

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            # Cerrar streaming + emitir log con el texto
                            # completo. Usamos write_log (no persist_log_only)
                            # como safety-net: si el frontend está cacheado
                            # con la versión vieja y no procesa chat.stream,
                            # al menos verá el mensaje completo vía el evento
                            # `log` tradicional. El frontend nuevo deduplica
                            # comparando con el último mensaje en streaming.
                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                if in_turn_id:
                                    self.ui.stream_chunk(
                                        role="user", delta="",
                                        turn_id=in_turn_id, final=True,
                                    )
                                self.ui.write_log(f"Tú: {full_in}")
                            in_buf = []
                            in_turn_id = None

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                if out_turn_id:
                                    self.ui.stream_chunk(
                                        role="orion", delta="",
                                        turn_id=out_turn_id, final=True,
                                    )
                                self.ui.write_log(f"ORION: {full_out}")
                            out_buf = []
                            out_turn_id = None

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            log.debug("Function call: %s", fc.name)
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except Exception as e:
            real = _first_real_exception(e)
            msg = str(real)[:200]
            log.error("Error en recepción de audio: %s", msg)
            self.ui.write_log(f"SISTEMA: Error de conexión — reconectando…")
            raise

    async def _watchdog(self):
        """Detecta cuelgues: si ORION queda en PENSANDO sin actividad de
        audio durante demasiado tiempo, fuerza ESCUCHANDO para que el usuario
        pueda volver a hablar.

        También resetea ``_is_speaking`` si no llega audio nuevo durante un
        rato y el turno está marcado como terminado.
        """
        import time
        STUCK_LIMIT_S = 12.0       # PENSANDO sin audio durante 12s → desbloquear
        SPEAKING_TIMEOUT_S = 1.5   # _is_speaking sin audio en 1.5s → resetear
        # (antes 6s, demasiado lento — el usuario perdía la primera pregunta
        # post-turno porque el mic seguía bloqueado mientras ORION ya había
        # terminado de hablar).
        while True:
            try:
                await asyncio.sleep(0.5)  # antes 2s, polling más frecuente
                now = time.time()
                # Snapshot atómico del estado bajo locks — evita decisiones
                # basadas en mezclas inconsistentes de timestamps escritos
                # por otros threads (callback de audio, executor pool, etc.).
                with self._speaking_lock:
                    speaking = self._is_speaking
                with self._state_lock:
                    pensando_since = self._pensando_since
                    last_activity = self._last_activity_ts

                # 1) Si _is_speaking sigue True pero la cola está vacía y el
                #    turno terminó, resetea.
                if speaking and self.audio_in_queue and self.audio_in_queue.empty():
                    if (now - last_activity) > SPEAKING_TIMEOUT_S:
                        # Es el flujo normal — el flag queda True después de
                        # que Gemini terminó de hablar hasta que el watchdog
                        # lo limpia. No es un error, ruido en WARNING.
                        log.debug("Watchdog: _is_speaking stuck, reset.")
                        self.set_speaking(False)
                        if self._turn_done_event:
                            try:
                                self._turn_done_event.set()
                            except Exception:
                                pass
                # 2) Si PENSANDO se prolonga sin actividad, vuelve a ESCUCHANDO
                if pensando_since is not None:
                    elapsed = now - pensando_since
                    no_audio = (
                        self.audio_in_queue is None
                        or self.audio_in_queue.empty()
                    )
                    if elapsed > STUCK_LIMIT_S and no_audio:
                        log.warning(
                            "Watchdog: PENSANDO bloqueado %.1fs → ESCUCHANDO",
                            elapsed,
                        )
                        with self._state_lock:
                            self._pensando_since = None
                        if not self.ui.muted:
                            self.ui.set_state("ESCUCHANDO")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.debug("watchdog tick error: %s", e)

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
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
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

    # ── Loop principal ───────────────────────────────────────────────────
    async def run(self):
        try:
            client = genai.Client(
                api_key=get_api_key(),
                http_options={"api_version": "v1beta"}
            )
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
                    self.session          = session
                    self._loop            = asyncio.get_event_loop()
                    # maxsize=200: si el driver de audio se atasca, la cola
                    # crecería sin tope. 200 chunks @ 24kHz/PCM16 ≈ 8s de
                    # audio bufferizado — suficiente para sobrevivir a un
                    # hipo del SO sin OOM.
                    # 1000 chunks ≈ 20s de audio (a 24kHz/int16, chunks de
                    # 480 samples). Suficiente para que el receiver no
                    # bloquee durante una respuesta normal y dé tiempo a
                    # _play_audio a drenar. Antes era 200 + drop-oldest, lo
                    # que causaba aceleración perceptible del TTS.
                    self.audio_in_queue   = asyncio.Queue(maxsize=1000)
                    self.out_queue        = asyncio.Queue(maxsize=10)
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
                    self.ui.write_log(
                        "SISTEMA: Conexión a Gemini lenta o bloqueada. Reintentando…"
                    )
                elif isinstance(root, (ConnectionError, OSError)):
                    # DNS, conexión rechazada, host inalcanzable. Transient.
                    log.warning(
                        "Error de red conectando a Gemini Live: %s. Reintentando…",
                        root,
                    )
                    self.ui.write_log(
                        "SISTEMA: Sin conexión a Gemini. Reintentando…"
                    )
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


# ============================================================================
#  Punto de entrada — Fase 7: arquitectura web-only
# ============================================================================
def _build_uvicorn_server(bus):
    """Devuelve un ``uvicorn.Server`` listo para servir el backend Orion."""
    import uvicorn
    from server.app import DEFAULT_HOST, DEFAULT_PORT, build_app

    app = build_app(bus)
    config = uvicorn.Config(
        app,
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        log_level="warning",
        access_log=False,
        loop="asyncio",
        lifespan="on",
    )
    return uvicorn.Server(config), DEFAULT_HOST, DEFAULT_PORT


def _spawn_orion_live(bus) -> None:
    """Arranca ``OrionLive`` en un thread daemon usando el bus como player."""
    def runner():
        bus.wait_for_api_key()
        orion = OrionLive(bus)

        def _attach_live_loop():
            import time
            for _ in range(100):
                if getattr(orion, "_loop", None) is not None:
                    bus.set_live_loop(orion._loop)
                    return
                time.sleep(0.05)
        threading.Thread(target=_attach_live_loop, daemon=True).start()

        try:
            asyncio.run(orion.run())
        except KeyboardInterrupt:
            log.info("Cerrando ORION...")

    threading.Thread(target=runner, daemon=True, name="OrionLiveRunner").start()


def main() -> None:
    """Arranca el backend FastAPI + frontend React.

    El main thread lo bloquea uvicorn; ``OrionLive`` corre en un thread
    daemon. El wizard de API key se atiende desde el frontend vía
    ``POST /api/settings/api_key``.
    """
    from server.event_bus import OrionEventBus

    log.info("Iniciando Orion (modo web)")
    bus = OrionEventBus()

    # Si la API key ya está configurada (env o archivo), desbloquea el
    # wait_for_api_key() del bus de inmediato. Si no, el frontend mostrará
    # el wizard y POST /api/settings/api_key llamará a bus.mark_ready().
    try:
        get_api_key()
        bus.mark_ready()
    except RuntimeError:
        log.info("API key no configurada — esperando wizard web")
    except Exception:
        pass

    _spawn_orion_live(bus)

    server, host, port = _build_uvicorn_server(bus)
    # `host` puede ser "0.0.0.0" (bindea todas las interfaces para que
    # Tailscale alcance), pero los navegadores no pueden navegar a esa
    # dirección. Para el log y el auto-open usamos siempre 127.0.0.1.
    browse_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{browse_host}:{port}"
    log.info("Frontend disponible en %s", url)
    if host in ("0.0.0.0", "::"):
        log.info("Backend escucha en %s:%d (Tailscale + localhost)", host, port)

    # Abrir el navegador automáticamente (mejor primera experiencia).
    # En entornos sin GUI (Tauri / sidecar / servidor) esto es no-op.
    if not os.environ.get("ORION_NO_BROWSER"):
        try:
            import webbrowser
            webbrowser.open(url, new=2)
        except Exception:
            pass

    # uvicorn bloquea el main thread hasta Ctrl+C
    try:
        asyncio.run(server.serve())
    except KeyboardInterrupt:
        log.info("Cerrando ORION...")


if __name__ == "__main__":
    main()