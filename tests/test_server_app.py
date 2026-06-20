"""
tests.test_server_app
======================
Tests de integración de la Fase 1 contra la app FastAPI usando
``TestClient`` (no abre puerto real, no hace requests de red).

Cubre:
  - /api/health             devuelve estado del bus.
  - /api/memory             refleja load_memory().
  - /api/memory/{category}  404 para categorías inexistentes.
  - /api/notes              lista de notas, /count cuenta.
  - /api/conversations      resumen + detalle.
  - /api/settings/theme     paleta + lista de disponibles.
  - /ws                     handshake + estado inicial + recibe evento publicado.

Importante: usamos ``monkeypatch`` para apuntar los JSON de datos a un
``tmp_path`` y no tocar los reales del usuario.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── Fixtures ────────────────────────────────────────────────────────────
@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    """Apunta los paths de memoria/notas/convs a tmp_path con datos seed."""
    import memory.conversations as cv
    import memory.memory_manager as mm
    import memory.quick_notes as qn

    mem_file = tmp_path / "long_term.json"
    mem_file.write_text(
        json.dumps(
            {
                "identity": {"nombre": {"value": "Zahir"}},
                "preferences": {"comida_favorita": {"value": "pizza"}},
                "projects": {},
                "relationships": {},
                "wishes": {},
                "notes": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mm, "MEMORY_PATH", mem_file)

    notes_file = tmp_path / "quick_notes.json"
    notes_file.write_text(
        json.dumps(
            [
                {
                    "id": "n1",
                    "text": "comprar pan",
                    "pinned": False,
                    "color": None,
                    "created": "2026-05-31T10:00:00",
                    "updated": "2026-05-31T10:00:00",
                },
                {
                    "id": "n2",
                    "text": "regar plantas",
                    "pinned": True,
                    "color": None,
                    "created": "2026-05-31T11:00:00",
                    "updated": "2026-05-31T11:00:00",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(qn, "_NOTES_PATH", notes_file)

    convs_file = tmp_path / "conversations.json"
    convs_file.write_text(
        json.dumps(
            [
                {
                    "id": "abc123",
                    "started": "2026-05-30T10:00:00",
                    "title": "Charla de prueba",
                    "messages": [
                        {"role": "user", "text": "hola", "ts": "2026-05-30T10:00:00"},
                        {"role": "ai", "text": "hola!", "ts": "2026-05-30T10:00:01"},
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cv, "_CONVERSATIONS_PATH", convs_file)

    return tmp_path


@pytest.fixture
def client(isolated_data):
    """TestClient con app + bus reales, datos en tmp_path."""
    from server.app import build_app
    from server.event_bus import OrionEventBus

    bus = OrionEventBus()
    app = build_app(bus)
    with TestClient(app) as tc:
        yield tc, bus


# ── Tests ───────────────────────────────────────────────────────────────
def test_health(client):
    tc, bus = client
    r = tc.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["service"] == "orion-backend"
    assert data["muted"] is False
    assert data["state"] in {"ESCUCHANDO", "PENSANDO", "HABLANDO"}


def test_memory_full(client):
    tc, _ = client
    r = tc.get("/api/memory")
    assert r.status_code == 200
    mem = r.json()
    assert "identity" in mem
    assert mem["identity"]["nombre"]["value"] == "Zahir"
    assert mem["preferences"]["comida_favorita"]["value"] == "pizza"


def test_memory_by_category(client):
    tc, _ = client
    r = tc.get("/api/memory/identity")
    assert r.status_code == 200
    assert r.json()["identity"]["nombre"]["value"] == "Zahir"


def test_memory_unknown_category(client):
    tc, _ = client
    r = tc.get("/api/memory/no_existe")
    assert r.status_code == 404


def test_notes(client):
    tc, _ = client
    r = tc.get("/api/notes")
    assert r.status_code == 200
    notes = r.json()
    assert len(notes) == 2
    ids = {n["id"] for n in notes}
    assert ids == {"n1", "n2"}


def test_notes_count(client):
    tc, _ = client
    r = tc.get("/api/notes/count")
    assert r.status_code == 200
    assert r.json() == {"count": 2}


def test_conversations_summary(client):
    tc, _ = client
    r = tc.get("/api/conversations")
    assert r.status_code == 200
    summary = r.json()
    assert len(summary) == 1
    assert summary[0]["id"] == "abc123"
    assert summary[0]["messages"] == 2  # contador, no array
    assert summary[0]["title"] == "Charla de prueba"


def test_conversation_detail(client):
    tc, _ = client
    r = tc.get("/api/conversations/abc123")
    assert r.status_code == 200
    conv = r.json()
    assert len(conv["messages"]) == 2
    assert conv["messages"][0]["role"] == "user"


def test_conversation_not_found(client):
    tc, _ = client
    r = tc.get("/api/conversations/zzz999")
    assert r.status_code == 404


def test_settings_theme(client):
    tc, _ = client
    r = tc.get("/api/settings/theme")
    assert r.status_code == 200
    data = r.json()
    assert "name" in data
    assert "theme" in data
    assert "PRI" in data["theme"]  # paleta del tema
    assert isinstance(data["available"], list)
    assert all("id" in t and "name" in t for t in data["available"])


# ── WebSocket ───────────────────────────────────────────────────────────
def test_ws_handshake_and_initial_state(client):
    """Al conectar el WS, el hub debe enviar state + mute como saludo."""
    tc, _ = client
    with tc.websocket_connect("/ws") as ws:
        msg1 = ws.receive_json()
        msg2 = ws.receive_json()
        types = {m["type"] for m in (msg1, msg2)}
        assert types == {"state", "mute"}


def test_ws_broadcast_published_event(client):
    """Cuando algo publica en el bus, el cliente WS lo recibe."""
    tc, bus = client
    with tc.websocket_connect("/ws") as ws:
        # consume saludo
        ws.receive_json()
        ws.receive_json()
        # publicar desde el bus (igual que haría una acción)
        bus.publish("log", {"text": "Hola desde test", "ts": 0})
        msg = ws.receive_json()
        assert msg["type"] == "log"
        assert msg["payload"]["text"] == "Hola desde test"


def test_ws_text_command_calls_callback(client):
    """Enviar {type:text} debe invocar bus.on_text_command."""
    tc, bus = client
    received = []
    bus.on_text_command = lambda t: received.append(t)
    with tc.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "text", "payload": {"text": "abre Spotify"}})
        # submit_user_text usa un thread daemon, esperamos un poco
        import time

        for _ in range(40):
            if received:
                break
            time.sleep(0.05)
    assert received == ["abre Spotify"]


def test_ws_mute_toggle(client):
    tc, bus = client
    with tc.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "mute", "payload": {"value": True}})
        # consumir el broadcast del setter del bus
        msg = ws.receive_json()
        assert msg["type"] == "mute"
        assert msg["payload"]["value"] is True
    assert bus.muted is True
