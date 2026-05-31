"""
tests.test_event_bus_contract
=============================
Garantiza que ``server.event_bus.OrionEventBus`` es un reemplazo
**drop-in** de ``ui.OrionUI`` antes de cablearlo en main.py.

El contrato proviene de la auditoría técnica pre-Fase 0:
es exactamente la superficie que main.py + las 21 acciones + los plugins
consumen de la UI.

Estos tests son la red de seguridad de la Fase 0: si en el futuro alguien
añade un atributo a la UI Qt y se le olvida añadirlo al bus, este test rompe.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

# El test debe poder ejecutarse SIN PyQt6 instalado.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── Contrato esperado ───────────────────────────────────────────────────
#
# Cualquier objeto que pretenda ser "ui-like" para main.py / actions / plugins
# debe exponer estos miembros con estas semánticas.
PROPERTIES_RW = {
    "muted",
    "current_file",
    "current_files",
    "on_text_command",
    "on_interrupt",
}

METHODS = {
    "set_state",
    "write_log",
    "wait_for_api_key",
    "start_speaking",
    "stop_speaking",
    "notes_changed",
}

ATTRIBUTES = {
    "root",
}


# ── Tests ───────────────────────────────────────────────────────────────
def test_event_bus_importable_without_pyqt():
    """server.event_bus debe ser importable sin instalar PyQt6."""
    # Verifica que ni event_bus ni sus dependencias arrastran Qt.
    import server.event_bus  # noqa: F401
    # Si PyQt6 estuviera entre los imports transitivos (cosa que no
    # debería pasar), aparecería ya en sys.modules. Sólo lo prohibimos
    # como import directo del módulo del bus.
    src = (PROJECT_ROOT / "server" / "event_bus.py").read_text(encoding="utf-8")
    assert "PyQt6" not in src, (
        "server/event_bus.py NO debe importar PyQt6 — debe ser headless."
    )


def test_event_bus_exposes_all_properties():
    from server.event_bus import OrionEventBus
    bus = OrionEventBus()
    for prop in PROPERTIES_RW:
        assert hasattr(bus, prop), f"OrionEventBus no expone propiedad '{prop}'"


def test_event_bus_properties_are_writable():
    from server.event_bus import OrionEventBus
    bus = OrionEventBus()
    # muted
    bus.muted = True
    assert bus.muted is True
    bus.muted = False
    assert bus.muted is False
    # callbacks
    bus.on_text_command = lambda _t: None
    assert callable(bus.on_text_command)
    bus.on_interrupt = lambda: None
    assert callable(bus.on_interrupt)
    # current_file
    bus.current_file = "C:/tmp/x.png"
    assert bus.current_file == "C:/tmp/x.png"
    assert bus.current_files == ["C:/tmp/x.png"]


def test_event_bus_methods_callable():
    from server.event_bus import OrionEventBus
    bus = OrionEventBus()
    for name in METHODS:
        attr = getattr(bus, name, None)
        assert callable(attr), f"OrionEventBus.{name} debe ser callable"


def test_event_bus_set_state_and_write_log_no_op_without_server():
    """En Fase 0 el bus existe pero no hay loop. set_state/write_log
    deben ser no-op silenciosos (no excepciones)."""
    from server.event_bus import OrionEventBus
    bus = OrionEventBus()
    bus.set_state("ESCUCHANDO")
    bus.write_log("SISTEMA: hola")  # también ejercita _persist_log con conv=None
    bus.start_speaking()
    bus.stop_speaking()
    bus.notes_changed()


def test_event_bus_root_compat():
    """ui.OrionUI.root expone .mainloop()/.protocol()/.quit(). Lo
    necesitamos para que ``main.main()`` se mantenga compilable cuando
    cableemos el bus en Fase 1."""
    from server.event_bus import OrionEventBus
    bus = OrionEventBus()
    for m in ("mainloop", "protocol", "quit"):
        assert callable(getattr(bus.root, m, None)), (
            f"bus.root.{m} debe existir y ser callable"
        )


def test_persist_log_roles(tmp_path, monkeypatch):
    """_persist_log debe clasificar los prefijos igual que MainWindow
    (ui.py:1731-1753). Validamos el comportamiento, no la representación.

    Importante: ConversationSession.add() persiste a disco en cada llamada,
    así que apuntamos su path a un tmp_path para no tocar el JSON real.
    """
    import memory.conversations as conv_mod
    monkeypatch.setattr(conv_mod, "_CONVERSATIONS_PATH", tmp_path / "convs.json")

    from server.event_bus import OrionEventBus
    bus = OrionEventBus()
    bus.new_conversation()
    bus.write_log("Tú: hola")
    bus.write_log("ORION: qué tal")
    bus.write_log("SISTEMA: lista")
    bus.write_log("ERROR: x falló")
    bus.write_log("Archivo: foo.pdf")
    msgs = getattr(bus._conversation, "_messages", None)
    assert msgs is not None, "ConversationSession._messages cambió de nombre"
    roles = [m["role"] for m in msgs]
    assert roles == ["user", "ai", "sys", "err", "file"]


def test_publish_safe_without_server():
    """publish() desde cualquier hilo sin servidor activo debe ser inocuo."""
    from server.event_bus import OrionEventBus
    bus = OrionEventBus()
    bus.publish("custom", {"k": "v"})  # no debe lanzar


def test_subscribe_unsubscribe():
    from server.event_bus import OrionEventBus
    bus = OrionEventBus()
    async def sub(_t, _p):
        pass
    bus.subscribe(sub)
    bus.unsubscribe(sub)


def test_bus_exposes_full_contract():
    """Tras la Fase 7 la UI Qt fue eliminada. El bus es el único player —
    debe seguir cumpliendo la superficie completa que consumen
    main.OrionLive y las 21 acciones."""
    from server.event_bus import OrionEventBus
    for name in PROPERTIES_RW | METHODS:
        assert hasattr(OrionEventBus, name), f"OrionEventBus no expone '{name}'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
