"""
server.fanout — FanOutUI
=========================
Wrapper que se pasa a ``OrionLive`` y a las acciones como ``player`` /
``ui``. Reenvía cada llamada **a la vez** a la UI Qt actual y al
``OrionEventBus``, de forma que durante la coexistencia (Fase 1-4) las
dos UIs se mantienen sincronizadas sin que ninguna lo sepa.

Estrategia
----------
- **Escrituras** (``write_log``, ``set_state``, ``notes_changed``,
  ``start_speaking``, ``stop_speaking``) → se replican a ambos.
- **Lecturas** (``muted``, ``current_file``, ``current_files``) → la
  UI Qt es la fuente de verdad (el drop-zone vive ahí). El bus las
  expone como atributos derivados sólo si la UI Qt no está presente.
- **Callbacks** (``on_text_command``, ``on_interrupt``) → cuando
  ``main.OrionLive`` los setea, se asignan a ambos (Qt y bus). Cuando
  cualquiera los dispara, llaman al callback original.
- **Wizard de API key** (``wait_for_api_key``) → espera la UI Qt
  (es la que muestra el wizard) y, en cuanto pasa, propaga
  ``mark_ready()`` al bus para que el frontend web también se desbloquee.

Si en Fase 5 desactivamos la UI Qt, ``FanOutUI`` se construye con
``ui=None`` y todo el tráfico cae sólo en el bus.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from core.logger import get_logger

log = get_logger("fanout")


class FanOutUI:
    """Proxy dual UI Qt ↔ EventBus.

    Implementa la misma superficie pública que :class:`ui.OrionUI`
    (la que consumen ``main.py`` y las 21 acciones), pero internamente
    se desdobla en dos destinos.
    """

    # ── Constructor ──────────────────────────────────────────────────────
    def __init__(self, ui: Any, bus: Any):
        """:param ui:  instancia de ``OrionUI`` (Qt) o ``None`` si modo web puro.
        :param bus: instancia de ``OrionEventBus``."""
        self._ui  = ui
        self._bus = bus
        # Cache local de callbacks para asegurar que ambos destinos los ven.
        self._on_text_command: Optional[Callable[[str], None]] = None
        self._on_interrupt:    Optional[Callable[[], None]]    = None

    # ── root (compat con `ui.root.mainloop()` desde main.py) ─────────────
    @property
    def root(self) -> Any:
        if self._ui is not None:
            return self._ui.root
        return self._bus.root  # _NullRoot

    # ── Estado mute ──────────────────────────────────────────────────────
    @property
    def muted(self) -> bool:
        if self._ui is not None:
            return bool(self._ui.muted)
        return bool(self._bus.muted)

    @muted.setter
    def muted(self, v: bool) -> None:
        if self._ui is not None:
            self._ui.muted = bool(v)
        self._bus.muted = bool(v)

    # ── Archivo cargado (drop-zone vive en la UI Qt) ────────────────────
    @property
    def current_file(self) -> Optional[str]:
        if self._ui is not None:
            val = self._ui.current_file
            # Mantenemos el bus al día para los suscriptores WS
            if val != self._bus.current_file:
                self._bus.current_file = val
            return val
        return self._bus.current_file

    @property
    def current_files(self) -> list[str]:
        if self._ui is not None:
            try:
                vals = list(self._ui.current_files)
            except AttributeError:
                vals = []
            return vals
        return self._bus.current_files

    # ── Callbacks (on_text_command, on_interrupt) ───────────────────────
    @property
    def on_text_command(self) -> Optional[Callable[[str], None]]:
        return self._on_text_command

    @on_text_command.setter
    def on_text_command(self, cb: Optional[Callable[[str], None]]) -> None:
        self._on_text_command = cb
        if self._ui is not None:
            self._ui.on_text_command = cb
        self._bus.on_text_command = cb

    @property
    def on_interrupt(self) -> Optional[Callable[[], None]]:
        return self._on_interrupt

    @on_interrupt.setter
    def on_interrupt(self, cb: Optional[Callable[[], None]]) -> None:
        self._on_interrupt = cb
        if self._ui is not None:
            self._ui.on_interrupt = cb
        self._bus.on_interrupt = cb

    # ── Métodos de escritura: replicar en ambos ─────────────────────────
    def set_state(self, state: str) -> None:
        if self._ui is not None:
            try:
                self._ui.set_state(state)
            except Exception as e:
                log.debug("set_state(ui) error: %s", e)
        try:
            self._bus.set_state(state)
        except Exception as e:
            log.debug("set_state(bus) error: %s", e)

    def write_log(self, text: str) -> None:
        if self._ui is not None:
            try:
                self._ui.write_log(text)
            except Exception as e:
                log.debug("write_log(ui) error: %s", e)
        try:
            self._bus.write_log(text)
        except Exception as e:
            log.debug("write_log(bus) error: %s", e)

    def start_speaking(self) -> None:
        self.set_state("HABLANDO")

    def stop_speaking(self) -> None:
        if not self.muted:
            self.set_state("ESCUCHANDO")

    def notes_changed(self) -> None:
        if self._ui is not None:
            try:
                self._ui.notes_changed()
            except Exception as e:
                log.debug("notes_changed(ui) error: %s", e)
        try:
            self._bus.notes_changed()
        except Exception as e:
            log.debug("notes_changed(bus) error: %s", e)

    # ── Wizard de API key ───────────────────────────────────────────────
    def wait_for_api_key(self) -> None:
        """Espera la UI Qt (es la que muestra el wizard) y luego propaga
        ``mark_ready`` al bus para que el frontend también se desbloquee."""
        if self._ui is not None:
            self._ui.wait_for_api_key()
        else:
            # Sin UI Qt: bloquea hasta que el frontend confirme via REST.
            self._bus.wait_for_api_key()
        # En ambos casos marcamos el bus como ready (idempotente).
        try:
            self._bus.mark_ready()
        except Exception:
            pass
