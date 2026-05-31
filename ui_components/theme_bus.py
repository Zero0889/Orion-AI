"""
ui_components.theme_bus — Bus reactivo de temas para O.R.I.O.N
==============================================================
Permite que cualquier widget se suscriba a cambios de tema y se repinte
en vivo, sin necesidad de reiniciar la aplicación.

Uso desde un widget que quiera reaccionar al tema:

    from ui_components.theme_bus import theme_bus, current_theme

    class MyWidget(QWidget):
        def __init__(self):
            super().__init__()
            self._theme = current_theme()
            theme_bus.theme_changed.connect(self._on_theme)
            self._apply_theme()

        def _on_theme(self, theme: dict):
            self._theme = theme
            self._apply_theme()

        def _apply_theme(self):
            ...

Y desde el código que decide cambiar el tema:

    from ui_components.theme_bus import apply_theme

    apply_theme("orion_blue")   # guarda en disco + emite a todos los widgets

El bus es un singleton perezoso: se instancia al primer uso. Es seguro
desde el hilo de la GUI (no usar desde threads de fondo sin invokeMethod).

⚠️ NOTA DE MIGRACIÓN (auditoría pre-Fase 0 — R-20)
---------------------------------------------------
Este módulo es **Qt puro**: arrastra ``PyQt6.QtCore.pyqtSignal``. Está
prohibido importarlo desde:

  - ``server.*``           (backend FastAPI/WebSocket headless)
  - ``actions/*``          (acciones invocadas por Gemini Live)
  - ``agent/*``, ``memory/*``, ``core/*``, ``plugins/*``

El equivalente en el modo web es el evento WebSocket ``settings.theme``
emitido por ``OrionEventBus`` cuando el usuario cambia el tema desde el
frontend React.

Los **datos** de los temas (paletas, fuentes) viven en
:mod:`config.theme_tokens` y son consumibles desde cualquier capa sin Qt.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from config.theme import (
    THEMES, apply_theme_to_class, get_theme, load_theme_name, save_theme_name,
)


class _ThemeBus(QObject):
    """Singleton que emite señales cuando cambia el tema activo."""

    # Emite el dict completo del nuevo tema
    theme_changed = pyqtSignal(dict)

    # Emite solo el id del tema (para componentes que solo necesitan saber cuál)
    theme_id_changed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._active_id: str = load_theme_name()
        self._active_theme: dict = get_theme(self._active_id)

    @property
    def active_id(self) -> str:
        return self._active_id

    @property
    def active_theme(self) -> dict:
        return self._active_theme

    def emit_change(self, theme_id: str) -> bool:
        """Cambia el tema activo y notifica a todos los suscriptores.

        Devuelve True si el cambio fue aplicado, False si el id no existe.
        """
        if theme_id not in THEMES:
            return False
        if theme_id == self._active_id:
            return True
        self._active_id = theme_id
        self._active_theme = get_theme(theme_id)
        self.theme_id_changed.emit(theme_id)
        self.theme_changed.emit(self._active_theme)
        return True


# Singleton perezoso
_bus_instance: Optional[_ThemeBus] = None


def theme_bus() -> _ThemeBus:
    """Devuelve la instancia única del bus de temas."""
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = _ThemeBus()
    return _bus_instance


def current_theme() -> dict:
    """Devuelve el dict del tema activo actualmente."""
    return theme_bus().active_theme


def current_theme_id() -> str:
    """Devuelve el id del tema activo actualmente."""
    return theme_bus().active_id


def apply_theme(theme_id: str, *, persist: bool = True,
                target_class=None) -> bool:
    """Aplica un tema en vivo: persiste, actualiza target_class y notifica.

    Parámetros
    ----------
    theme_id : str
        Id del tema (clave en THEMES).
    persist : bool
        Si True, guarda el nombre en disco para que persista entre sesiones.
    target_class : type | None
        Si se pasa una clase (ej. la paleta global `C`), se le aplican los
        valores del tema con `apply_theme_to_class`. Útil para mantener la
        paleta estática legacy sincronizada con el bus.

    Devuelve True si el cambio se aplicó.
    """
    bus = theme_bus()
    if theme_id not in THEMES:
        return False

    if persist:
        try:
            save_theme_name(theme_id)
        except Exception:
            # No bloqueamos la aplicación en vivo por un fallo de I/O
            pass

    if target_class is not None:
        try:
            apply_theme_to_class(get_theme(theme_id), target_class)
        except Exception:
            pass

    return bus.emit_change(theme_id)
