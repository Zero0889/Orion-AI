"""
server.event_bus — OrionEventBus
=================================
Reemplazo drop-in de :class:`ui.OrionUI` para el modo web (React + WS).

Estado en Fase 0
----------------
Esta clase se crea aquí pero **todavía no se conecta** en :mod:`main`.
La UI Qt actual sigue siendo la activa. El objetivo de la Fase 0 es:

  1. Dejar la API estable y testeada (ver
     :mod:`tests.test_event_bus_contract`).
  2. Hacer que el día que ``main.OrionLive`` reciba un bus en lugar de
     ``OrionUI`` no haya que tocar ni una sola acción ni un plugin.

Compatibilidad con la fachada actual ``OrionUI``
------------------------------------------------
El bus expone **exactamente** los mismos atributos y métodos que el
``OrionUI`` activo usa desde :mod:`main` y desde las 21 acciones:

  - propiedades R/W : ``muted``, ``on_text_command``, ``on_interrupt``
  - propiedades R   : ``current_file``, ``current_files``
  - métodos         : ``set_state``, ``write_log``, ``wait_for_api_key``,
                      ``start_speaking``, ``stop_speaking``,
                      ``notes_changed``

Y añade la superficie nueva específica del modo web (no usada por las
acciones, sólo por el futuro hub WebSocket):

  - ``publish(event_type, payload)``
  - ``subscribe(client)`` / ``unsubscribe(client)``
  - ``submit_user_text(text)``
  - ``trigger_interrupt()``
  - ``set_live_loop(loop)``
  - ``mark_ready()``
  - ``new_conversation()`` / ``load_conversation(conv_id)``
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable

from core.logger import get_logger
from memory.conversations import ConversationSession, get_conversation
import contextlib

log = get_logger("event_bus")


# Tipos auxiliares
TextCommandCallback = Callable[[str], None]
InterruptCallback = Callable[[], None]


# ============================================================================
#  OrionEventBus
# ============================================================================
class OrionEventBus:
    """Bus de eventos + fachada compatible con :class:`ui.OrionUI`.

    Patrón de uso (Fase 1 en adelante)::

        bus = OrionEventBus()
        orion = OrionLive(bus)          # pasa bus en lugar de OrionUI
        bus.set_live_loop(loop_b)        # OrionLive informa su event loop
        await uvicorn.run(...)           # FastAPI consume bus.publish

    Reglas de concurrencia (resumen del informe de auditoría):
      - ``publish`` es seguro desde **cualquier** hilo o loop. Internamente
        usa ``loop_A.call_soon_threadsafe`` apuntando al loop de uvicorn.
      - ``submit_user_text`` y ``trigger_interrupt`` saltan al loop B
        (``OrionLive._loop``) con ``run_coroutine_threadsafe``.
      - ``_outbound_queue`` tiene ``maxsize=512`` con política drop-oldest
        para evitar OOM si un cliente WS se atasca.
    """

    OUTBOUND_QUEUE_MAX = 512
    _instance: OrionEventBus | None = None

    @classmethod
    def get_instance(cls) -> OrionEventBus | None:
        return cls._instance

    # ── Constructor ──────────────────────────────────────────────────────
    def __init__(self) -> None:
        OrionEventBus._instance = self
        # Estado equivalente a OrionUI
        self._muted: bool = False
        self._current_file: str | None = None
        self._current_files: list[str] = []

        self._on_text_command: TextCommandCallback | None = None
        self._on_interrupt: InterruptCallback | None = None

        # Persistencia de conversaciones (movida desde MainWindow, R-01)
        self._conversation: ConversationSession | None = None

        # Sincronización del wizard de API key (sustituye self._win._ready)
        self._api_key_ready = threading.Event()

        # Cola de salida fan-out → consumer async la drena en Loop A
        self._outbound_queue: asyncio.Queue | None = None
        self._server_loop: asyncio.AbstractEventLoop | None = None  # Loop A
        self._live_loop: asyncio.AbstractEventLoop | None = None  # Loop B

        # Estado de OrionLive (para el frontend)
        self._state: str = "ESCUCHANDO"

        # Compatibilidad con OrionUI.root._RootShim (algunos puntos llaman
        # ui.root.mainloop()). En modo web no hace nada.
        self.root = _NullRoot()

    # ── Configuración (Fase 1) ───────────────────────────────────────────
    def attach_server_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Llamado por FastAPI al arrancar uvicorn. Crea la outbound queue
        en el contexto del loop correcto."""
        self._server_loop = loop
        self._outbound_queue = asyncio.Queue(maxsize=self.OUTBOUND_QUEUE_MAX)

    def set_live_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """OrionLive informa su loop B nada más arrancar. Necesario para
        :meth:`submit_user_text` y :meth:`trigger_interrupt`."""
        self._live_loop = loop

    # ── API pública compatible con OrionUI ───────────────────────────────
    # Propiedades R/W
    @property
    def muted(self) -> bool:
        return self._muted

    @muted.setter
    def muted(self, value: bool) -> None:
        if value == self._muted:
            return
        self._muted = bool(value)
        self.publish("mute", {"value": self._muted})

    @property
    def current_file(self) -> str | None:
        return self._current_file

    @current_file.setter
    def current_file(self, path: str | None) -> None:
        self._current_file = path
        if path:
            self._current_files = [path]
            self.publish("file.attached", {"path": path})
        else:
            self._current_files = []
            self.publish("file.cleared", {})

    @property
    def current_files(self) -> list[str]:
        return list(self._current_files)

    @current_files.setter
    def current_files(self, paths: list[str]) -> None:
        self._current_files = list(paths or [])
        self._current_file = self._current_files[0] if self._current_files else None
        if self._current_files:
            self.publish("files.attached", {"paths": list(self._current_files)})

    @property
    def on_text_command(self) -> TextCommandCallback | None:
        return self._on_text_command

    @on_text_command.setter
    def on_text_command(self, cb: TextCommandCallback | None) -> None:
        self._on_text_command = cb

    @property
    def on_interrupt(self) -> InterruptCallback | None:
        return self._on_interrupt

    @on_interrupt.setter
    def on_interrupt(self, cb: InterruptCallback | None) -> None:
        self._on_interrupt = cb

    # Métodos
    def set_state(self, state: str) -> None:
        """Equivalente a ``OrionUI.set_state``. Publica ``state`` en el WS."""
        self._state = state
        self.publish("state", {"value": state})

    def write_log(self, text: str) -> None:
        """Equivalente a ``OrionUI.write_log``. Persiste la conversación
        (R-01: lógica movida desde ``MainWindow._persist_log``) y publica
        ``log`` en el WS."""
        if not text:
            return
        self._persist_log(text)
        self.publish("log", {"text": text, "ts": time.time()})

    def stream_chunk(
        self,
        role: str,
        delta: str,
        turn_id: str,
        final: bool = False,
    ) -> None:
        """Publica un chunk parcial al frontend para streaming en el chat.

        Usado para que el texto aparezca palabra-por-palabra a medida que
        Gemini Live lo va generando, en sync con el audio. No persiste —
        la persistencia se hace al cerrar el turno con :meth:`persist_log_only`.

        Args:
            role:    "orion" o "user".
            delta:   texto nuevo a anexar al mensaje en construcción.
            turn_id: identificador estable del turno (mismo en todos los chunks).
            final:   True en el último chunk para marcar el mensaje como cerrado.
        """
        self.publish(
            "chat.stream",
            {
                "role": role,
                "delta": delta,
                "turn_id": turn_id,
                "final": final,
                "ts": time.time(),
            },
        )

    def persist_log_only(self, text: str) -> None:
        """Persiste un log SIN publicar al WS — útil al cerrar un turno
        que ya se mandó al frontend vía stream_chunk. Evita duplicación de
        mensajes en el chat."""
        if not text:
            return
        self._persist_log(text)

    def wait_for_api_key(self) -> None:
        """Bloquea hasta que la UI/REST confirme que hay API key.

        En el modo web esto se desbloquea con :meth:`mark_ready`, invocado
        normalmente por ``POST /api/settings/api_key`` (o por la Qt UI durante
        la coexistencia)."""
        self._api_key_ready.wait()

    def start_speaking(self) -> None:
        self.set_state("HABLANDO")

    def stop_speaking(self) -> None:
        if not self._muted:
            self.set_state("ESCUCHANDO")

    def notes_changed(self) -> None:
        """Notificación de que el panel de notas debe refrescar.

        En la UI Qt se traduce a panel.reload(); en el modo web es un evento
        WS que el frontend escucha. Esta superficie sustituye el reach-in
        prohibido (R-02) que existía en ``main.py:1140-1147``."""
        self.publish("note.changed", {})

    # ── Superficie nueva (modo web) ──────────────────────────────────────
    def publish(self, event_type: str, payload: dict | None = None) -> None:
        """Encola un evento para fan-out a todos los clientes WS.

        Seguro desde cualquier hilo. Si todavía no hay loop de servidor
        (Fase 0: el bus está creado pero uvicorn no corre), simplemente
        descarta el evento — pasarán a notificarse cuando el servidor
        arranque."""
        if self._outbound_queue is None or self._server_loop is None:
            return  # Fase 0: nadie escucha aún
        msg = {"type": event_type, "payload": payload or {}}
        # El loop puede estar cerrándose en shutdown.
        with contextlib.suppress(RuntimeError):
            self._server_loop.call_soon_threadsafe(self._enqueue_outbound, msg)

    def _enqueue_outbound(self, msg: dict) -> None:
        """Inserta en _outbound_queue con política drop-oldest."""
        q = self._outbound_queue
        if q is None:
            return
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            with contextlib.suppress(Exception):
                q.get_nowait()  # drop oldest
            with contextlib.suppress(Exception):
                q.put_nowait(msg)

    def submit_user_text(self, text: str) -> None:
        """Inyecta texto al modelo Live. Salta de Loop A → Loop B con
        ``run_coroutine_threadsafe`` como exige el informe (R-15)."""
        cb = self._on_text_command
        if cb is None:
            log.warning("submit_user_text recibido sin on_text_command")
            return
        # Reusamos el patrón histórico: llamamos al callback en un thread
        # daemon (igual que hace ui.MainWindow hoy). El callback es el que
        # internamente hace run_coroutine_threadsafe contra OrionLive._loop.
        threading.Thread(target=cb, args=(text,), daemon=True).start()

    def trigger_interrupt(self) -> None:
        cb = self._on_interrupt
        if cb is None:
            return
        threading.Thread(target=cb, daemon=True).start()

    def mark_ready(self) -> None:
        """Desbloquea :meth:`wait_for_api_key`."""
        self._api_key_ready.set()
        self.publish("system.ready", {})

    # ── Persistencia de conversaciones (R-01) ────────────────────────────
    # Lógica portada literal desde ui.MainWindow._persist_log (ui.py:1731-1753)
    def new_conversation(self) -> None:
        self._conversation = ConversationSession()

    def close_conversation(self) -> None:
        self._conversation = None

    def load_conversation(self, conv_id: str) -> dict | None:
        conv = get_conversation(conv_id)
        if not conv:
            return None
        # Tras cargar, iniciamos una sesión nueva como hace la UI Qt
        self._conversation = ConversationSession()
        self.publish("conversation.load", conv)
        return conv

    def _persist_log(self, text: str) -> None:
        if not text or self._conversation is None:
            return
        t = text.strip()
        tl = t.lower()
        try:
            if tl.startswith(("tú:", "tu:")):
                role, body = "user", t.split(":", 1)[1].strip()
            elif tl.startswith(("orion:", "o.r.i.o.n:")):
                role, body = "ai", t.split(":", 1)[1].strip()
            elif tl.startswith(("sistema:", "sys:")):
                role, body = "sys", t.split(":", 1)[1].strip()
            elif tl.startswith("error"):
                role, body = "err", t
            elif tl.startswith("archivo:"):
                role, body = "file", t.split(":", 1)[1].strip()
            else:
                role, body = "sys", t
        except (IndexError, ValueError):
            role, body = "sys", t
        if not body:
            return
        self._conversation.add(role, body)


# ============================================================================
#  Compatibilidad con OrionUI.root
# ============================================================================
class _NullRoot:
    """Sustituto de ``OrionUI.root`` (un ``_RootShim`` de PyQt) cuando no hay
    UI Qt. ``main.py`` actualmente llama ``ui.root.mainloop()`` desde el thread
    principal; en modo web ese hilo lo ocupa uvicorn."""

    def mainloop(self) -> None:
        pass

    def protocol(self, *_args, **_kwargs) -> None:
        pass

    def quit(self) -> None:
        pass
