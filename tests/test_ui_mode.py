"""
tests.test_ui_mode
===================
Fase 5 — switch ORION_UI=qt|web|both.

Verifica:
  - get_ui_mode() lee ORION_UI con prioridad sobre el archivo.
  - Default es "both" cuando nada está configurado.
  - Valores inválidos caen a "both".
  - main.py NO importa PyQt6 al ser cargado (pereza confirmada).
  - main.main() despacha al runner correcto sin llegar a ejecutar nada
    pesado (mockeamos _run_qt/_run_web/_run_both para no abrir UI ni
    arrancar uvicorn de verdad).
  - El modo web puede importar TODO el grafo de server.* sin PyQt6.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── get_ui_mode ─────────────────────────────────────────────────────────
def test_default_is_both(monkeypatch):
    monkeypatch.delenv("ORION_UI", raising=False)
    import config
    # Asegúrate de que el archivo de config tampoco fija ui_mode.
    monkeypatch.setattr(config, "load_config", lambda: {})
    assert config.get_ui_mode() == "both"


def test_env_var_wins(monkeypatch):
    import config
    monkeypatch.setenv("ORION_UI", "web")
    assert config.get_ui_mode() == "web"
    monkeypatch.setenv("ORION_UI", "qt")
    assert config.get_ui_mode() == "qt"
    monkeypatch.setenv("ORION_UI", "BOTH")  # case-insensitive
    assert config.get_ui_mode() == "both"


def test_invalid_falls_back_to_both(monkeypatch):
    import config
    monkeypatch.setenv("ORION_UI", "no-existe")
    assert config.get_ui_mode() == "both"


def test_config_file_used_if_env_missing(monkeypatch):
    import config
    monkeypatch.delenv("ORION_UI", raising=False)
    monkeypatch.setattr(config, "load_config", lambda: {"ui_mode": "web"})
    assert config.get_ui_mode() == "web"


# ── main.py: no carga PyQt6 ─────────────────────────────────────────────
def test_main_module_does_not_import_pyqt():
    # Forzar reimport limpio.
    for mod in list(sys.modules):
        if mod == "main" or mod.startswith("PyQt6"):
            sys.modules.pop(mod, None)
    import main  # noqa: F401
    assert "PyQt6" not in sys.modules, (
        "main.py NO debe importar PyQt6 al cargar (los modos deben "
        "hacerlo lazy)."
    )


# ── Despachador ─────────────────────────────────────────────────────────
def test_main_dispatches_to_qt(monkeypatch):
    import main
    monkeypatch.setattr(main, "get_ui_mode", lambda: "qt")
    with patch.object(main, "_run_qt") as qt, \
         patch.object(main, "_run_web") as web, \
         patch.object(main, "_run_both") as both:
        main.main()
    qt.assert_called_once()
    web.assert_not_called()
    both.assert_not_called()


def test_main_dispatches_to_web(monkeypatch):
    import main
    monkeypatch.setattr(main, "get_ui_mode", lambda: "web")
    with patch.object(main, "_run_qt") as qt, \
         patch.object(main, "_run_web") as web, \
         patch.object(main, "_run_both") as both:
        main.main()
    web.assert_called_once()
    qt.assert_not_called()
    both.assert_not_called()


def test_main_dispatches_to_both_by_default(monkeypatch):
    import main
    monkeypatch.setattr(main, "get_ui_mode", lambda: "both")
    with patch.object(main, "_run_qt") as qt, \
         patch.object(main, "_run_web") as web, \
         patch.object(main, "_run_both") as both:
        main.main()
    both.assert_called_once()
    qt.assert_not_called()
    web.assert_not_called()


# ── server.* es headless puro ───────────────────────────────────────────
def test_server_imports_without_pyqt():
    """Modo web debe poder importar todo el grafo de server.* sin Qt."""
    for mod in list(sys.modules):
        if mod.startswith("PyQt6") or mod.startswith("server"):
            sys.modules.pop(mod, None)
    import server.app  # noqa: F401
    import server.event_bus  # noqa: F401
    import server.fanout  # noqa: F401
    import server.ws  # noqa: F401
    from server.routes import agent, conversations, files, iot, memory, notes  # noqa: F401
    from server.routes import settings as settings_route  # noqa: F401
    assert "PyQt6" not in sys.modules, (
        "server.* no debe arrastrar PyQt6. Si este test falla, alguien "
        "metió un import Qt en el backend."
    )


def test_event_bus_can_be_player_for_actions():
    """Modo web pasa el bus directo como player. Cumple las superficies
    que main.OrionLive y las actions consumen."""
    from server.event_bus import OrionEventBus
    bus = OrionEventBus()
    # Mismo set verificado en tests/test_event_bus_contract.py.
    for name in (
        "write_log", "set_state", "muted", "current_file",
        "on_text_command", "on_interrupt", "wait_for_api_key",
        "start_speaking", "stop_speaking", "notes_changed",
    ):
        assert hasattr(bus, name), f"OrionEventBus no expone '{name}'"
