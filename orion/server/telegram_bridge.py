"""
server.telegram_bridge — Puente bidireccional entre Telegram y el bus.

Responsabilidades:
  1. **Inbound**: long-polling de ``getUpdates`` en un thread daemon.
     Cada mensaje del usuario se inyecta como ``bus.submit_user_text``,
     con ``ClientInfo(device="mobile")`` para que el prompt builder use
     el hint corto (orientado a chat).
  2. **Outbound**: hook registrado en el bus que reenvía a Telegram:
     - Respuestas de Orion (``log`` con prefijo "Orion:") al chat_id que
       originó la pregunta (FIFO de pendientes).
     - Notificaciones (``notification.new``) al chat por defecto, si el
       usuario activó ``forward_notifications`` en la config.

Lifecycle:
  - ``start(bus)`` en el ``lifespan`` de FastAPI si la config dice
    ``enabled=true`` Y hay token+chat_id.
  - ``stop()`` en el ``shutdown`` — el thread es daemon y muere solo,
    pero limpiamos el hook del bus para no acumular en hot-reload de tests.
  - ``reload(bus)`` para aplicar cambios desde Settings sin reiniciar Orion.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime
from typing import Any


def _now_local() -> datetime:
    """Datetime con timezone local — fácil de mockear en tests."""
    return datetime.now().astimezone()


from orion.adapters.messaging.telegram import (
    LONG_POLL_TIMEOUT_S,
    TelegramClient,
    TelegramConfig,
    load_telegram_config,
)
from orion.core.logger import get_logger

log = get_logger("telegram.bridge")

# Si el long-poll falla, esperamos un poco antes de reintentar. Backoff
# corto porque getUpdates es barato y queremos recuperar rápido tras
# una caída temporal de red.
RETRY_BACKOFF_S = 5.0
# Cap del histórico de chat_ids "pendientes de respuesta" — si por algún
# motivo el bus nunca emite el log de respuesta, no acumulamos para siempre.
PENDING_CAP = 20


# ── Singleton ─────────────────────────────────────────────────────────────


_bridge: TelegramBridge | None = None


def get_bridge() -> TelegramBridge | None:
    return _bridge


def init_bridge(bus: Any) -> TelegramBridge:
    """Crea (o reusa) el bridge global y lo arranca si la config lo permite."""
    global _bridge
    if _bridge is None:
        _bridge = TelegramBridge(bus)
    else:
        _bridge.bus = bus
    _bridge.reload()
    return _bridge


def shutdown_bridge() -> None:
    if _bridge is not None:
        _bridge.stop()


# ── Bridge ────────────────────────────────────────────────────────────────


class TelegramBridge:
    """Vive una sola instancia mientras Orion corre. Idempotente:
    ``reload()`` tantas veces como haga falta sin acumular threads."""

    def __init__(self, bus: Any) -> None:
        self.bus = bus
        self._cfg: TelegramConfig | None = None
        self._client: TelegramClient | None = None
        self._stop = threading.Event()
        self._poll_thread: threading.Thread | None = None
        self._summary_thread: threading.Thread | None = None
        self._summary_last_run_day: str | None = None  # YYYY-MM-DD
        self._last_update_id: int = 0
        # Cola de (chat_id, thread_id) esperando respuesta del brain. FIFO
        # porque mensajes llegan ordenados; el thread_id se preserva para
        # responder al mismo topic del supergrupo de donde vino la
        # pregunta (chat privado → thread_id None, Telegram lo ignora).
        self._pending: deque[tuple[int, int | None]] = deque(maxlen=PENDING_CAP)
        self._pending_lock = threading.Lock()
        # Buffers de streaming por turn_id. chat_brain emite stream_chunk
        # con `delta` parcial y `final=True` para cerrar. Acumulamos por
        # turn_id y, al cerrar, mandamos el texto completo a Telegram.
        # Live emite muchos deltas chicos; chat_brain emite uno solo con el
        # texto completo + un chunk vacío con final=True. Ambos quedan
        # cubiertos por el mismo buffer.
        self._stream_buffers: dict[str, list[str]] = {}
        self._stream_lock = threading.Lock()
        self._hook_installed = False

    # ── Lifecycle ────────────────────────────────────────────────────────

    def reload(self) -> None:
        """Re-lee config y arranca/para el polling según corresponda."""
        new_cfg = load_telegram_config()
        self._cfg = new_cfg
        running = self._poll_thread is not None and self._poll_thread.is_alive()

        should_run = new_cfg.enabled and new_cfg.is_configured
        if should_run and not running:
            self._start_polling()
        elif not should_run and running:
            self._stop_polling()
        elif should_run and running:
            # Cambio de token → reciclar cliente. Cambio de chat_id solo
            # afecta defaults — el thread sigue con el mismo cliente y
            # los nuevos sends usan el cfg fresco directamente.
            if self._client is None or self._client.token != new_cfg.bot_token:
                self._stop_polling()
                self._start_polling()

        # Hook al bus (idempotente)
        if should_run and not self._hook_installed:
            self.bus.register_publish_hook(self._on_bus_event)
            self._hook_installed = True
        elif not should_run and self._hook_installed:
            self.bus.unregister_publish_hook(self._on_bus_event)
            self._hook_installed = False

    def _start_polling(self) -> None:
        assert self._cfg is not None
        try:
            self._client = TelegramClient(self._cfg.bot_token)
        except ValueError as e:
            log.warning("Telegram bridge no arrancó: %s", e)
            return
        self._stop.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="TelegramBridge",
        )
        self._poll_thread.start()
        # Arrancar también el scheduler del resumen diario (idempotente:
        # si ya hay un thread vivo, no duplica).
        self._start_summary_scheduler()
        log.info("Telegram bridge iniciado")

    def _start_summary_scheduler(self) -> None:
        """Arranca el thread que postea el resumen diario al topic Estado.
        No-op si el config no tiene topic ``status`` mapeado."""
        if self._summary_thread is not None and self._summary_thread.is_alive():
            return
        cfg = self._cfg
        if cfg is None or cfg.group is None or "status" not in cfg.group.topics:
            log.debug("Sin topic status configurado — scheduler de resumen NO arranca")
            return
        self._summary_thread = threading.Thread(
            target=self._summary_loop,
            daemon=True,
            name="TelegramSummary",
        )
        self._summary_thread.start()
        log.info("Scheduler de resumen diario iniciado")

    def _stop_polling(self) -> None:
        self._stop.set()
        # No join — el thread está bloqueado en long-poll, no podemos
        # esperarlo razonablemente. Es daemon, muere con el proceso.
        self._poll_thread = None
        log.info("Telegram bridge detenido")

    def stop(self) -> None:
        if self._hook_installed:
            self.bus.unregister_publish_hook(self._on_bus_event)
            self._hook_installed = False
        self._stop_polling()

    # ── Polling loop ─────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        client = self._client
        if client is None:
            return
        while not self._stop.is_set():
            try:
                updates = client.get_updates(
                    offset=self._last_update_id + 1 if self._last_update_id else 0,
                    timeout_s=LONG_POLL_TIMEOUT_S,
                    allowed_updates=["message"],
                )
            except Exception as e:
                # Si el token quedó inválido o la red rompió, no spammear
                # logs — backoff y reintentar.
                log.warning("getUpdates falló: %s — reintentando en %.0fs", e, RETRY_BACKOFF_S)
                if self._stop.wait(RETRY_BACKOFF_S):
                    return
                continue

            for u in updates:
                self._last_update_id = max(self._last_update_id, u.update_id)
                if u.chat_id is None or not u.text:
                    continue
                self._handle_inbound(
                    u.chat_id,
                    u.text,
                    u.from_first_name or u.from_username,
                    u.message_thread_id,
                    u.from_user_id,
                )

    # ── Scheduler del resumen diario ─────────────────────────────────────

    def _summary_loop(self) -> None:
        """Despierta cada minuto. Si llegó la hora configurada Y aún no
        posteamos el resumen de hoy, lo posteamos al topic Estado.

        Hora de envío: ``cfg.daily_summary_hour`` (default 21, ver
        ``TelegramConfig``). Comparación a nivel de DÍA local — un solo
        envío por día aunque el thread despierte varias veces.
        """
        from orion.server.status_summary import build_daily_summary

        while not self._stop.is_set():
            try:
                cfg = self._cfg
                if cfg is None or cfg.group is None or "status" not in cfg.group.topics:
                    # Config se modificó y el topic dejó de existir → exit
                    return
                now = _now_local()
                target_hour = cfg.daily_summary_hour
                today = now.strftime("%Y-%m-%d")
                if now.hour >= target_hour and self._summary_last_run_day != today:
                    log.info("Disparando resumen diario para %s", today)
                    try:
                        text = build_daily_summary(day=today)
                        chat_id = cfg.group.chat_id
                        thread_id = cfg.group.topics["status"]
                        try:
                            chat_target: int | str = int(chat_id)
                        except ValueError:
                            chat_target = chat_id
                        self._send_async(chat_target, text, thread_id=thread_id)
                        self._summary_last_run_day = today
                    except Exception:
                        log.exception("build/send resumen falló — reintento mañana")
                        # Marcamos como hecho de todos modos: si falló, no
                        # queremos spam de reintentos hasta el día siguiente.
                        self._summary_last_run_day = today
            except Exception:
                log.exception("summary_loop ciclo crasheó — sigo igual")
            # Dormir 60s o salir si el stop event se activa
            if self._stop.wait(60.0):
                return

    # ── Inbound: TG → bus ────────────────────────────────────────────────

    def _handle_inbound(
        self,
        chat_id: int,
        text: str,
        sender: str | None,
        thread_id: int | None = None,
        from_user_id: int | None = None,
    ) -> None:
        """Mensaje del usuario en Telegram → texto al cerebro o slash command."""
        text = text.strip()
        if not text:
            return

        log.info(
            "TG inbound: chat_id=%s thread_id=%s from_user_id=%s sender=%r len=%d text=%r",
            chat_id,
            thread_id,
            from_user_id,
            sender or "?",
            len(text),
            text[:80],
        )

        # ── Slash commands: si el msg viene del topic Comandos del
        #    supergrupo Y empieza con "/", lo dispatcheamos en vez de
        #    mandarlo al cerebro.
        if self._should_dispatch_command(text, chat_id, thread_id):
            self._dispatch_slash_command(text, chat_id, thread_id, from_user_id)
            return

        # ── Forward al brain: solo si viene del chat privado del user
        #    o del topic Chat del supergrupo. Topics de notifs (access /
        #    status / comandos) NO disparan el LLM aunque manden texto
        #    libre, así nadie por error termina conversando con Orion
        #    desde el topic Acceso.
        if not self._should_forward_to_brain(chat_id, thread_id):
            log.debug(
                "TG ignorado (no es chat privado ni topic Chat): chat_id=%s thread_id=%s",
                chat_id,
                thread_id,
            )
            return

        # Auth: solo el user autorizado puede chatear con el brain.
        # Sin esto, cualquiera del supergrupo podría hablarle a Orion y
        # gastar tokens del LLM.
        if not self._is_authorized_user(from_user_id):
            log.warning("TG chat rechazado: from_user_id=%s no autorizado", from_user_id)
            return

        # Marcar device para que el prompt builder use el hint "móvil".
        # Importante: importamos acá adentro para no engancharnos al
        # client_context al cargar el módulo (evita ciclos en tests).
        try:
            from orion.core.client_context import ClientInfo, set_last_client

            set_last_client(
                ClientInfo(device="mobile", client_id=f"tg:{chat_id}"),
            )
        except Exception as e:
            log.debug("set_last_client falló (sigo igual): %s", e)

        with self._pending_lock:
            self._pending.append((chat_id, thread_id))

        try:
            self.bus.submit_user_text(text)
        except Exception:
            log.exception("submit_user_text crasheó desde Telegram")

    def _should_forward_to_brain(self, chat_id: int, thread_id: int | None) -> bool:
        """Decide si el mensaje (no-comando) debe ir al brain.

        Reglas:
          1. Chat privado con el bot (chat_id == default_chat_id, sin thread).
          2. Topic Chat del supergrupo (chat_id == group.chat_id Y
             thread_id == group.topics["chat"]).
        Cualquier otro topic (access/status/commands) NO dispara brain.
        """
        cfg = self._cfg
        if cfg is None:
            return False
        if cfg.default_chat_id and str(chat_id) == str(cfg.default_chat_id):
            return True
        if cfg.group and str(chat_id) == str(cfg.group.chat_id):
            chat_thread = cfg.group.topics.get("chat")
            if chat_thread is not None and thread_id == chat_thread:
                return True
        return False

    def _is_authorized_user(self, from_user_id: int | None) -> bool:
        """True si el sender es el user autorizado (`default_chat_id`)."""
        cfg = self._cfg
        if cfg is None or from_user_id is None:
            return False
        try:
            return int(from_user_id) == int(cfg.default_chat_id)
        except (TypeError, ValueError):
            return False

    def _should_dispatch_command(
        self,
        text: str,
        chat_id: int,
        thread_id: int | None,
    ) -> bool:
        """Decide si el mensaje es un slash command que debe ir al dispatcher.

        Regla: viene del topic mapeado como ``"commands"`` en el supergrupo
        Y empieza con ``"/"``. En chats privados ALSO permitimos slash
        commands (más fácil de testear desde el chat 1:1 con el bot).
        """
        from orion.server import telegram_commands as tc

        if not tc.is_command(text):
            return False

        cfg = self._cfg
        if cfg is None:
            return False

        # Chat privado con el bot: siempre permitir comandos.
        if cfg.default_chat_id and str(chat_id) == str(cfg.default_chat_id):
            return True

        # Supergrupo: solo desde el topic Comandos.
        if cfg.group and str(chat_id) == str(cfg.group.chat_id):
            commands_thread = cfg.group.topics.get("commands")
            if commands_thread is not None and thread_id == commands_thread:
                return True

        return False

    def _dispatch_slash_command(
        self,
        text: str,
        chat_id: int,
        thread_id: int | None,
        from_user_id: int | None,
    ) -> None:
        """Ejecuta un slash command y responde al mismo topic/chat."""
        from orion.server import telegram_commands as tc

        cfg = self._cfg
        sender_for_auth = from_user_id if from_user_id is not None else chat_id
        authorized = cfg.default_chat_id if cfg is not None else None

        reply = tc.dispatch(
            text,
            sender_chat_id=int(sender_for_auth),
            authorized_chat_id=authorized,
        )

        # Mandar la respuesta al mismo chat/topic de donde vino.
        self._send_async(chat_id, reply, thread_id=thread_id)

    # ── Outbound: bus → TG ───────────────────────────────────────────────

    def _on_bus_event(self, event_type: str, payload: dict) -> None:
        """Hook sync llamado desde ``bus.publish``. Mantenerlo rápido —
        cualquier I/O lenta debería ir a un thread."""
        if event_type == "log":
            # Path legacy — algunos paths emiten `log` con "Orion: ..."
            self._maybe_forward_orion_reply(payload)
        elif event_type == "chat.stream":
            # Path moderno: `chat_brain` y Live emiten chunks via
            # `bus.stream_chunk` y NO `log` (para evitar el bug del chat
            # duplicado, ver commit 8664938). Acumulamos por turn_id.
            self._handle_chat_stream(payload)
        elif event_type == "notification.new":
            self._maybe_forward_notification(payload)

    def _handle_chat_stream(self, payload: dict) -> None:
        """Acumula chunks de la respuesta del brain por ``turn_id`` y
        envía a Telegram cuando llega el chunk con ``final=True``."""
        if payload.get("role") != "orion":
            return
        turn_id = str(payload.get("turn_id") or "")
        if not turn_id:
            return
        delta = str(payload.get("delta") or "")
        is_final = bool(payload.get("final"))

        with self._stream_lock:
            buf = self._stream_buffers.setdefault(turn_id, [])
            if delta:
                buf.append(delta)
            if is_final:
                text = _smart_join(self._stream_buffers.pop(turn_id, []))
            else:
                text = None

        if text is None:
            return  # aún no es el chunk final
        text = text.strip()
        if not text:
            return

        with self._pending_lock:
            if not self._pending:
                return
            chat_id, thread_id = self._pending.popleft()
        self._send_async(chat_id, text, thread_id=thread_id)

    def _maybe_forward_orion_reply(self, payload: dict) -> None:
        """Si llega un log de Orion y tenemos un chat pendiente, lo
        reenviamos al mismo chat/topic de donde vino la pregunta."""
        text = str(payload.get("text") or "")
        tl = text.lower()
        if not (tl.startswith("orion:") or tl.startswith("o.r.i.o.n:")):
            return
        # Cortamos el prefijo "Orion: ".
        body = text.split(":", 1)[1].strip()
        if not body:
            return
        with self._pending_lock:
            if not self._pending:
                return
            chat_id, thread_id = self._pending.popleft()
        self._send_async(chat_id, body, thread_id=thread_id)

    def _maybe_forward_notification(self, payload: dict) -> None:
        cfg = self._cfg
        if cfg is None or not cfg.forward_notifications:
            return
        if not cfg.default_chat_id:
            return
        text = self._format_notification(payload)
        if not text:
            return
        # default_chat_id puede ser numérico como string o "@channel".
        target: int | str
        try:
            target = int(cfg.default_chat_id)
        except ValueError:
            target = cfg.default_chat_id
        self._send_async(target, text)

    @staticmethod
    def _format_notification(payload: dict) -> str:
        """Convierte un payload de notification.new en texto legible.
        El shape varía según la fuente (Gmail, IoT, custom) — extraemos
        los campos comunes y caemos a una representación cruda si nada
        matchea."""
        if not isinstance(payload, dict):
            return ""
        # Campo `text` directo (lo que usan tools custom).
        if isinstance(payload.get("text"), str) and payload["text"].strip():
            return f"🔔 *Orion*\n{payload['text'].strip()}"
        # Source + count (Gmail/Classroom poller).
        source = payload.get("source")
        count = payload.get("count")
        if source and count:
            return f"🔔 *{source}*: {count} nuevo(s)"
        return ""

    # ── HTTP fire-and-forget ─────────────────────────────────────────────

    def _send_async(
        self,
        chat_id: int | str,
        text: str,
        *,
        thread_id: int | None = None,
    ) -> None:
        """Manda en un thread daemon para no bloquear al productor del
        evento (que puede ser el WS drain loop o el thread del LLM).

        ``thread_id`` propaga al ``message_thread_id`` de Telegram — útil
        para responder a un topic específico dentro de un supergrupo.
        """
        client = self._client
        if client is None:
            return

        def _go() -> None:
            try:
                client.send_message(chat_id, text, message_thread_id=thread_id)
            except Exception as e:
                log.warning("Telegram send falló (chat_id=%s): %s", chat_id, e)

        threading.Thread(target=_go, daemon=True).start()

    # ── Status para REST ─────────────────────────────────────────────────

    def status(self) -> dict:
        cfg = self._cfg or load_telegram_config()
        running = self._poll_thread is not None and self._poll_thread.is_alive()
        bot_username: str | None = None
        bot_ok: bool = False
        bot_error: str | None = None
        if cfg.bot_token:
            try:
                client = TelegramClient(cfg.bot_token)
                me = client.get_me()
                if me.get("ok"):
                    bot_username = (me.get("result") or {}).get("username")
                    bot_ok = True
                else:
                    bot_error = me.get("description") or "respuesta sin ok=true"
            except Exception as e:
                bot_error = str(e)[:200]
        return {
            "enabled": cfg.enabled,
            "configured": cfg.is_configured,
            "has_token": bool(cfg.bot_token),
            "default_chat_id": cfg.default_chat_id,
            "forward_notifications": cfg.forward_notifications,
            "running": running,
            "bot_username": bot_username,
            "bot_ok": bot_ok,
            "bot_error": bot_error,
        }


# Pequeña pausa para que las primeras polls hagan ruido pero no spam
# durante test runs con módulos que reusan el bus.
_BOOT_SETTLE_S = 0.5


def settle() -> None:
    time.sleep(_BOOT_SETTLE_S)


def _smart_join(chunks: list[str]) -> str:
    """Joinea chunks de streaming preservando espacios cuando faltan.

    Live (Gemini) emite cada palabra/token como chunk separado y
    `_clean_transcript` les hace `.strip()`, así que las palabras llegan
    sin espacios entre sí. Un naive `"".join()` produciría
    "Sonlas11:31deldomingo".

    chat_brain en cambio emite UN chunk con el texto completo + un chunk
    vacío con `final=True`. Ahí ya viene con sus espacios.

    Heurística: agregamos un espacio entre dos chunks **solo si el nuevo
    chunk empieza con alfanumérico Y el chunk anterior no terminaba en
    whitespace**. La puntuación de cierre (",", ".", "?", etc.) queda
    pegada a la palabra anterior; la siguiente palabra recibe su espacio.

      ["Son", "las", "11:31"]      → "Son las 11:31"
      ["Hola.", "Son"]              → "Hola. Son"
      ["Hola Zahir", ", ", "qué"]   → "Hola Zahir, qué"
      ["Hola Zahir, qué tal?"]      → "Hola Zahir, qué tal?"  (chunk único)
      ["domingo,", "de", "junio"]   → "domingo, de junio"
    """
    result = ""
    for chunk in chunks:
        if not chunk:
            continue
        if result and not result[-1].isspace() and (chunk[0].isalnum() or chunk[0] in "¿¡"):
            result += " "
        result += chunk
    return result
