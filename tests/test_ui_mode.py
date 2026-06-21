"""
tests.test_ui_mode
===================
Post Fase 7 — Orion es web-only. Este test ya no valida el switch
ORION_UI=qt|web|both (eliminado); en su lugar verifica que:

  - ``main`` se importa sin arrastrar PyQt6.
  - ``main.main`` existe y es la única entrada.
  - El grafo de ``server.*`` es 100% headless (sin Qt).
  - El bus es un player completo (cubierto también por
    ``tests/test_event_bus_contract.py``).
  - ``ORION_NO_BROWSER`` desactiva la apertura automática del navegador.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── orion.__main__ es web-only y no arrastra Qt ────────────────────────
def test_main_module_does_not_import_pyqt():
    for mod in list(sys.modules):
        if mod == "orion.__main__" or mod.startswith("PyQt6"):
            sys.modules.pop(mod, None)
    import orion.__main__ as main

    assert "PyQt6" not in sys.modules, (
        "orion/__main__.py no debe importar PyQt6 — la UI Qt fue eliminada en Fase 7."
    )
    # Solo queda main() como entry point
    assert callable(main.main)


def test_main_has_no_legacy_runners():
    """Fase 7: ya no existen _run_qt / _run_both."""
    import orion.__main__ as main

    assert not hasattr(main, "_run_qt"), "_run_qt debe estar eliminado"
    assert not hasattr(main, "_run_both"), "_run_both debe estar eliminado"
    assert not hasattr(main, "_run_web"), "_run_web se inlineó en main()"


def test_no_get_ui_mode_anymore():
    """El helper get_ui_mode se eliminó porque ya no hay multimodo."""
    import orion.config

    assert not hasattr(orion.config, "get_ui_mode")


# ── server.* sigue siendo headless puro ─────────────────────────────────
def test_server_imports_without_pyqt():
    for mod in list(sys.modules):
        if mod.startswith("PyQt6") or mod.startswith("server"):
            sys.modules.pop(mod, None)
    import orion.server.app
    import orion.server.event_bus
    import orion.server.ws
    from orion.server.routes import (
        agent,
        conversations,
        files,
        iot,
        memory,
        notes,
    )
    from orion.server.routes import (
        settings as settings_route,
    )

    assert "PyQt6" not in sys.modules


def test_no_fanout_module():
    """server.fanout fue eliminado en Fase 7 (ya no hace falta sin UI Qt)."""
    with pytest.raises(ImportError):
        import orion.server.fanout


# ── ORION_NO_BROWSER desactiva la apertura automática ───────────────────
def test_no_browser_env_var_skips_webbrowser_open(monkeypatch):
    """En modo Tauri / sidecar / servidor remoto, no queremos abrir el
    navegador del SO. La variable ``ORION_NO_BROWSER`` lo desactiva.
    Verificamos que main() respeta el flag — sin llegar a arrancar uvicorn.

    Post Fase 3 (R3): la lógica vive en ``orion.bootstrap``; ``main()``
    referencia los helpers por nombre local, así que patchear en bootstrap
    redirige las llamadas reales.
    """
    import orion.bootstrap as bootstrap

    monkeypatch.setenv("ORION_NO_BROWSER", "1")

    # Cortamos antes de que main() bloquee con uvicorn.serve(). Para eso
    # mockeamos _spawn_orion_live, _build_uvicorn_server y asyncio.run.
    with (
        patch.object(bootstrap, "_spawn_orion_live"),
        patch.object(bootstrap, "_build_uvicorn_server", return_value=(_DummyServer(), "h", 1)),
        patch.object(bootstrap.asyncio, "run"),
        patch("webbrowser.open") as wb,
    ):
        bootstrap.main()
    wb.assert_not_called()


def test_browser_opens_by_default(monkeypatch):
    monkeypatch.delenv("ORION_NO_BROWSER", raising=False)
    import orion.bootstrap as bootstrap

    with (
        patch.object(bootstrap, "_spawn_orion_live"),
        patch.object(bootstrap, "_build_uvicorn_server", return_value=(_DummyServer(), "h", 1)),
        patch.object(bootstrap.asyncio, "run"),
        patch("webbrowser.open") as wb,
    ):
        bootstrap.main()
    wb.assert_called_once()


# ── Bus es un player completo (cross-check con el contrato) ─────────────
def test_event_bus_can_be_player_for_actions():
    from orion.server.event_bus import OrionEventBus

    bus = OrionEventBus()
    for name in (
        "write_log",
        "set_state",
        "muted",
        "current_file",
        "on_text_command",
        "on_interrupt",
        "wait_for_api_key",
        "start_speaking",
        "stop_speaking",
        "notes_changed",
    ):
        assert hasattr(bus, name), f"OrionEventBus no expone '{name}'"


# ── Helper ──────────────────────────────────────────────────────────────
class _DummyServer:
    async def serve(self):
        pass
