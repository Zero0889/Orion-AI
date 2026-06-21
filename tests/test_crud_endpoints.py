"""
tests.test_crud_endpoints
==========================
Verifica el CRUD añadido en Fase 3 sobre los endpoints existentes:
  - POST/PATCH/DELETE /api/notes
  - PUT/DELETE /api/memory/{cat}/{key}
  - DELETE /api/conversations/{id}
  - PATCH /api/settings/theme

Cada mutación que toca el bus también debe publicar el evento correcto
(verificado conectando un WS cliente).
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


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    import orion.domain.memory.conversations as cv
    import orion.domain.memory.memory_manager as mm
    import orion.domain.memory.quick_notes as qn

    mem_file = tmp_path / "long_term.json"
    mem_file.write_text(
        json.dumps(
            {
                "identity": {"nombre": {"value": "Zahir"}},
                "preferences": {},
                "projects": {},
                "relationships": {},
                "wishes": {},
                "notes": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mm, "MEMORY_PATH", mem_file)

    notes_file = tmp_path / "quick_notes.json"
    notes_file.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(qn, "_NOTES_PATH", notes_file)

    convs_file = tmp_path / "conversations.json"
    convs_file.write_text(
        json.dumps(
            [
                {"id": "c1", "started": "2026-05-30T10:00:00", "title": "T1", "messages": []},
                {"id": "c2", "started": "2026-05-30T11:00:00", "title": "T2", "messages": []},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cv, "_CONVERSATIONS_PATH", convs_file)

    theme_file = tmp_path / "theme.json"
    import orion.config.theme as theme_mod

    monkeypatch.setattr(theme_mod, "_THEME_CONFIG_PATH", theme_file)

    return tmp_path


@pytest.fixture
def client(isolated):
    from orion.server.app import build_app
    from orion.server.event_bus import OrionEventBus

    bus = OrionEventBus()
    app = build_app(bus)
    with TestClient(app) as tc:
        yield tc, bus


# ── Notes CRUD ──────────────────────────────────────────────────────────
def test_notes_create(client):
    tc, _ = client
    r = tc.post("/api/notes", json={"text": "comprar pan"})
    assert r.status_code == 201
    note = r.json()
    assert note["text"] == "comprar pan"
    assert note["pinned"] is False
    assert note["id"]


def test_notes_create_pinned(client):
    tc, _ = client
    r = tc.post("/api/notes", json={"text": "x", "pinned": True})
    assert r.status_code == 201
    assert r.json()["pinned"] is True


def test_notes_patch(client):
    tc, _ = client
    note = tc.post("/api/notes", json={"text": "v1"}).json()
    r = tc.patch(f"/api/notes/{note['id']}", json={"text": "v2", "pinned": True})
    assert r.status_code == 200
    listed = tc.get("/api/notes").json()
    found = [n for n in listed if n["id"] == note["id"]][0]
    assert found["text"] == "v2"
    assert found["pinned"] is True


def test_notes_patch_not_found(client):
    tc, _ = client
    r = tc.patch("/api/notes/zzz", json={"text": "x"})
    assert r.status_code == 404


def test_notes_delete(client):
    tc, _ = client
    note = tc.post("/api/notes", json={"text": "borrar"}).json()
    r = tc.delete(f"/api/notes/{note['id']}")
    assert r.status_code == 204
    assert tc.get("/api/notes").json() == []


def test_notes_create_publishes_event(client):
    tc, _ = client
    with tc.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()  # saludo
        tc.post("/api/notes", json={"text": "ping"})
        evt = ws.receive_json()
        assert evt["type"] == "note.changed"
        assert evt["payload"]["op"] == "created"


# ── Memory CRUD ─────────────────────────────────────────────────────────
def test_memory_put(client):
    tc, _ = client
    r = tc.put("/api/memory/preferences/color", json={"value": "azul"})
    assert r.status_code == 200
    mem = tc.get("/api/memory").json()
    assert mem["preferences"]["color"]["value"] == "azul"


def test_memory_put_invalid_category(client):
    tc, _ = client
    r = tc.put("/api/memory/inventada/key", json={"value": "x"})
    assert r.status_code == 400


def test_memory_delete(client):
    tc, _ = client
    tc.put("/api/memory/preferences/color", json={"value": "azul"})
    r = tc.delete("/api/memory/preferences/color")
    assert r.status_code == 204
    mem = tc.get("/api/memory").json()
    assert "color" not in mem["preferences"]


def test_memory_delete_not_found(client):
    tc, _ = client
    r = tc.delete("/api/memory/preferences/no_existe")
    assert r.status_code == 404


def test_memory_publishes_event(client):
    tc, _ = client
    with tc.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()
        tc.put("/api/memory/identity/nombre", json={"value": "Z"})
        evt = ws.receive_json()
        assert evt["type"] == "memory.updated"
        assert evt["payload"]["category"] == "identity"
        assert evt["payload"]["key"] == "nombre"


# ── Conversations DELETE ────────────────────────────────────────────────
def test_conversation_delete(client):
    tc, _ = client
    r = tc.delete("/api/conversations/c1")
    assert r.status_code == 204
    ids = {c["id"] for c in tc.get("/api/conversations").json()}
    assert ids == {"c2"}


def test_conversation_delete_not_found(client):
    tc, _ = client
    r = tc.delete("/api/conversations/zzz")
    assert r.status_code == 404


def test_conversation_delete_publishes_event(client):
    tc, _ = client
    with tc.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()
        tc.delete("/api/conversations/c1")
        evt = ws.receive_json()
        assert evt["type"] == "conversation.deleted"
        assert evt["payload"]["id"] == "c1"


# ── Settings PATCH theme ────────────────────────────────────────────────
def test_settings_patch_theme(client):
    tc, _ = client
    available = tc.get("/api/settings/theme").json()["available"]
    candidate = next((t["id"] for t in available if t["id"] != "red"), None)
    if candidate is None:
        pytest.skip("Solo hay un tema disponible")
    r = tc.patch("/api/settings/theme", json={"name": candidate})
    assert r.status_code == 200
    assert r.json()["name"] == candidate
    assert tc.get("/api/settings/theme").json()["name"] == candidate


def test_settings_patch_invalid_theme(client):
    tc, _ = client
    r = tc.patch("/api/settings/theme", json={"name": "inventado"})
    assert r.status_code == 400


def test_settings_patch_publishes_event(client):
    tc, _ = client
    available = tc.get("/api/settings/theme").json()["available"]
    candidate = next((t["id"] for t in available if t["id"] != "red"), None)
    if candidate is None:
        pytest.skip("Solo hay un tema disponible")
    with tc.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()
        tc.patch("/api/settings/theme", json={"name": candidate})
        evt = ws.receive_json()
        assert evt["type"] == "settings.theme"
        assert evt["payload"]["name"] == candidate
