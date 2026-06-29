"""orion.live_session — Configuración + handlers Live-only + watchdog.

Contiene el ``LiveSessionMixin`` que ``OrionLive`` compone. Responsable
de:
  - Construir el ``LiveConnectConfig`` que se manda a Gemini Live.
  - Inyectar handlers Live-only (``agent_task``, ``shutdown_orion``)
    sobre los stubs que registró ``tools_bootstrap``.
  - Watchdog asíncrono que detecta cuelgues en PENSANDO o speaking flag
    que quedó pegado.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from typing import Any

from google.genai import types

from orion._helpers import _load_system_prompt
from orion.core.logger import get_logger
from orion.domain.memory.memory_manager import format_memory_for_prompt, load_memory

log = get_logger("orion.live_session")

# Modelo Gemini Live en uso. Constante exportada para que el bootstrap
# pueda referenciarla en logs (no para que la cambien en runtime — el
# config se rebuildea en cada reconexión).
LIVE_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"


class LiveSessionMixin:
    """Mixin con todo lo Gemini-Live-específico.

    Espera atributos en self:
      - ``self._tool_registry``, ``self._plugin_registry``
      - ``self._mcp_manager`` (sólo para shutdown handler)
      - ``self.ui`` (event bus con write_log, set_state, muted)
      - ``self._speaking_lock``, ``self._is_speaking``
      - ``self._state_lock``, ``self._pensando_since``, ``self._last_activity_ts``
      - ``self.audio_in_queue``, ``self._turn_done_event``
      - ``self.speak``, ``self.set_speaking``, ``self._on_text_command`` (métodos host)
    """

    # Timeout por defecto (segundos) para evitar que ORION quede congelado
    # esperando una herramienta que no responde. Los overrides por tool
    # viven en ``core/tools_bootstrap.py`` (ToolDeclaration.timeout).
    _DEFAULT_TOOL_TIMEOUT = 60

    # ── Voz: leer config del usuario al armar la sesión Live ─────────────
    # Los defaults reflejan los valores legacy hardcoded antes de
    # introducir el panel Ajustes → Voz. Si el archivo de config no existe
    # o está corrupto, caemos a estos sin ruido.
    _VOICE_DEFAULT_NAME = "Charon"
    _VOICE_DEFAULT_LANGUAGE = "es-US"

    def _load_voice_settings(self) -> dict:
        import json

        from orion.config import VOICE_CONFIG_PATH

        if not VOICE_CONFIG_PATH.exists():
            return {}
        try:
            return json.loads(VOICE_CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _resolve_voice_name(self) -> str:
        return self._load_voice_settings().get("voice_name") or self._VOICE_DEFAULT_NAME

    def _resolve_language_code(self) -> str:
        return self._load_voice_settings().get("language_code") or self._VOICE_DEFAULT_LANGUAGE

    # ── Configuración de la sesión ───────────────────────────────────────
    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory = load_memory()
        mem_str = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        # Nombres de días/meses en español para el contexto temporal
        dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        meses = [
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        ]

        now = datetime.now()
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

        # Device hint: si la última conexión declaró su tipo de dispositivo
        # (móvil, reloj, tablet, etc.), agregamos un nudge corto al tono.
        # Vacío para clientes legacy o "unknown" — no sesgamos sin datos.
        # Nota: el Live config se arma una vez por sesión. Si el usuario
        # cambia de dispositivo, el nuevo hint aplica en la próxima
        # reconexión (acceptable trade-off para evitar reconfigurar la
        # sesión Live a mitad de turno).
        from orion.core.client_context import build_device_hint

        device_hint = build_device_hint()
        if device_hint:
            parts.append("\n" + device_hint)

        # Catálogo de skills — Gemini Live necesita saber qué hay instalado
        # para decidir cuándo invocar use_skill. Sin este bloque, ve la tool
        # genérica pero no los skill_ids disponibles.
        try:
            from orion.core.skills import build_skill_catalog_prompt

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
            tools=[
                {
                    "function_declarations": self._tool_registry.to_gemini_declarations()
                    + self._plugin_registry.get_tool_declarations()
                }
            ],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self._resolve_voice_name()
                    )
                ),
                # CRÍTICO: sin language_code el TTS usa prosodia inglesa por
                # default y lee español rápido y artificial. El default es-US
                # fuerza al modelo a ajustar el ritmo, las pausas y la
                # entonación al castellano latinoamericano. El usuario puede
                # cambiarlo desde el panel Ajustes → Voz.
                language_code=self._resolve_language_code(),
            ),
        )

    # ── Handlers Live-only (overriden sobre los stubs) ───────────────────
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

            def _looks_like_id(m: _re.Match) -> str:
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
            from orion.agent.task_queue import TaskPriority, get_queue

            priority_map = {
                "low": TaskPriority.LOW,
                "normal": TaskPriority.NORMAL,
                "high": TaskPriority.HIGH,
            }
            priority = priority_map.get(
                (parameters.get("priority") or "normal").lower(),
                TaskPriority.NORMAL,
            )
            goal = parameters.get("goal", "")

            holder: dict[str, Any] = {
                "result": None,
                "done": threading.Event(),
                "sync_returned": False,
            }

            def _on_done(task_id: str, result: Any) -> None:
                holder["result"] = result
                holder["done"].set()
                log.info(
                    "agent_task[%s] completed (result_len=%s, sync_returned=%s)",
                    task_id,
                    len(result) if isinstance(result, str) else "n/a",
                    holder["sync_returned"],
                )
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
            log.info(
                "agent_task[%s] queued, esperando hasta %ds sync…", task_id, AGENT_TASK_SYNC_TIMEOUT
            )

            # Espera bloqueante. h_agent_task corre en run_in_executor, así
            # que bloquear aquí NO bloquea el event loop de asyncio.
            if holder["done"].wait(timeout=AGENT_TASK_SYNC_TIMEOUT):
                result = holder["result"]
                if isinstance(result, str) and result.strip():
                    cleaned = _sanitize_for_voice(result)
                    log.info(
                        "agent_task[%s] devuelto sync (%d→%d chars) a Gemini",
                        task_id,
                        len(result),
                        len(cleaned),
                    )
                    return cleaned
                return "La tarea terminó sin producir salida visible."

            # Timeout: marcamos para que el on_complete inyecte el resultado
            # cuando finalmente llegue.
            holder["sync_returned"] = True
            log.warning(
                "agent_task[%s] timeout sync (%ds) — fallback async",
                task_id,
                AGENT_TASK_SYNC_TIMEOUT,
            )
            return (
                f"La tarea está tomando más de {AGENT_TASK_SYNC_TIMEOUT} segundos. "
                f"Sigue corriendo en background — te aviso con el resultado en cuanto termine."
            )

        # ── shutdown_orion: apaga el proceso tras un breve aviso ──
        def h_shutdown(parameters: dict, **_kwargs) -> str:
            self.ui.write_log("SISTEMA: Apagado solicitado.")
            self.speak("Hasta luego.")

            def _shutdown():
                import os
                import time

                time.sleep(1.5)
                # Para los subprocesses MCP antes del exit duro — os._exit
                # bypassea atexit y dejaría huérfanos.
                with contextlib.suppress(Exception):
                    self._mcp_manager.stop_all()
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

    # ── Watchdog ─────────────────────────────────────────────────────────
    async def _watchdog(self):
        """Detecta cuelgues: si ORION queda en PENSANDO sin actividad de
        audio durante demasiado tiempo, fuerza ESCUCHANDO para que el usuario
        pueda volver a hablar.

        También resetea ``_is_speaking`` si no llega audio nuevo durante un
        rato y el turno está marcado como terminado.
        """
        import time

        STUCK_LIMIT_S = 12.0  # PENSANDO sin audio durante 12s → desbloquear
        SPEAKING_TIMEOUT_S = 1.5  # _is_speaking sin audio en 1.5s → resetear
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
                            with contextlib.suppress(Exception):
                                self._turn_done_event.set()
                # 2) Si PENSANDO se prolonga sin actividad, vuelve a ESCUCHANDO
                if pensando_since is not None:
                    elapsed = now - pensando_since
                    no_audio = self.audio_in_queue is None or self.audio_in_queue.empty()
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


__all__ = ["LIVE_MODEL", "LiveSessionMixin"]
