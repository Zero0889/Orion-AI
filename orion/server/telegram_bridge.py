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
from typing import Any

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
        self._last_update_id: int = 0
        # Cola de chat_ids esperando respuesta. FIFO porque mensajes
        # llegan ordenados; mantenemos un cap defensivo.
        self._pending: deque[int] = deque(maxlen=PENDING_CAP)
        self._pending_lock = threading.Lock()
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
        log.info("Telegram bridge iniciado")

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
                )

    # ── Inbound: TG → bus ────────────────────────────────────────────────

    def _handle_inbound(
        self,
        chat_id: int,
        text: str,
        sender: str | None,
        thread_id: int | None = None,
    ) -> None:
        """Mensaje del usuario en Telegram → texto al cerebro."""
        text = text.strip()
        if not text:
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
            self._pending.append(chat_id)

        log.info(
            "TG inbound: chat_id=%s thread_id=%s sender=%r len=%d text=%r",
            chat_id,
            thread_id,
            sender or "?",
            len(text),
            text[:80],
        )
        try:
            self.bus.submit_user_text(text)
        except Exception:
            log.exception("submit_user_text crasheó desde Telegram")

    # ── Outbound: bus → TG ───────────────────────────────────────────────

    def _on_bus_event(self, event_type: str, payload: dict) -> None:
        """Hook sync llamado desde ``bus.publish``. Mantenerlo rápido —
        cualquier I/O lenta debería ir a un thread."""
        if event_type == "log":
            self._maybe_forward_orion_reply(payload)
        elif event_type == "notification.new":
            self._maybe_forward_notification(payload)

    def _maybe_forward_orion_reply(self, payload: dict) -> None:
        """Si llega un log de Orion y tenemos un chat pendiente, lo
        reenviamos al usuario por Telegram."""
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
            chat_id = self._pending.popleft()
        self._send_async(chat_id, body)

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

    def _send_async(self, chat_id: int | str, text: str) -> None:
        """Manda en un thread daemon para no bloquear al productor del
        evento (que puede ser el WS drain loop o el thread del LLM)."""
        client = self._client
        if client is None:
            return

        def _go() -> None:
            try:
                client.send_message(chat_id, text)
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
