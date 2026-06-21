"""
tests.test_files_upload
========================
Fase 4 — POST /api/files/upload + GET/DELETE /api/files/current.

Verifica:
  - Subir un archivo lo guarda en uploads/ y setea bus.current_file
  - Publica el evento file.attached por WS
  - GET /current refleja el archivo actual
  - DELETE /current limpia y emite file.cleared
  - El nombre se sanea (path traversal imposible)
  - Cap de tamaño defensivo (413 si > 50MB) — verificado bajando el cap
  - Sin file → 422 (validación)
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Apunta uploads a tmp_path (no contaminar el repo real)
    import orion.server.routes.files as files_route

    monkeypatch.setattr(files_route, "UPLOADS_DIR", tmp_path / "uploads")

    from orion.server.app import build_app
    from orion.server.event_bus import OrionEventBus

    bus = OrionEventBus()
    app = build_app(bus)
    with TestClient(app) as tc:
        yield tc, bus, tmp_path


# ── upload ──────────────────────────────────────────────────────────────
def test_upload_creates_file_and_sets_bus_current(client):
    tc, bus, tmp = client
    payload = io.BytesIO(b"hola desde el test")
    r = tc.post(
        "/api/files/upload",
        files={"file": ("notas.txt", payload, "text/plain")},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["ok"] is True
    assert data["original"] == "notas.txt"
    assert data["size"] == len(b"hola desde el test")
    assert data["name"].endswith("_notas.txt")
    assert Path(data["path"]).is_file()
    assert bus.current_file == data["path"]


def test_upload_publishes_file_attached(client):
    tc, _, _ = client
    with tc.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()  # saludo state + mute
        tc.post(
            "/api/files/upload",
            files={"file": ("doc.pdf", io.BytesIO(b"x" * 10), "application/pdf")},
        )
        evt = ws.receive_json()
        assert evt["type"] == "file.attached"
        assert evt["payload"]["path"].endswith("_doc.pdf")


def test_upload_sanitizes_filename(client):
    tc, _, tmp = client
    # Nombre malicioso con path traversal
    bad = "../../../etc/passwd"
    r = tc.post(
        "/api/files/upload",
        files={"file": (bad, io.BytesIO(b"x"), "text/plain")},
    )
    assert r.status_code == 201
    saved = Path(r.json()["path"])
    # Debe estar dentro de uploads/, jamás fuera.
    uploads = (tmp / "uploads").resolve()
    assert saved.resolve().is_relative_to(uploads)
    # Y el nombre no debe contener "/" ni ".."
    assert ".." not in saved.name
    assert "/" not in saved.name


def test_upload_size_cap_enforced(client, monkeypatch):
    """Forzamos un cap pequeño para no generar 50 MB en RAM."""
    import orion.server.routes.files as files_route

    monkeypatch.setattr(files_route, "MAX_BYTES", 10)

    tc, _, _ = client
    r = tc.post(
        "/api/files/upload",
        files={"file": ("big.bin", io.BytesIO(b"x" * 100), "application/octet-stream")},
    )
    assert r.status_code == 413


def test_upload_without_file_returns_validation_error(client):
    tc, _, _ = client
    r = tc.post("/api/files/upload", data={})
    assert r.status_code == 422


# ── current ─────────────────────────────────────────────────────────────
def test_get_current_when_empty(client):
    tc, _, _ = client
    r = tc.get("/api/files/current")
    assert r.status_code == 200
    assert r.json() == {"current": None}


def test_get_current_after_upload(client):
    tc, _, _ = client
    tc.post(
        "/api/files/upload",
        files={"file": ("x.txt", io.BytesIO(b"abc"), "text/plain")},
    )
    r = tc.get("/api/files/current")
    cur = r.json()["current"]
    assert cur is not None
    assert cur["name"].endswith("_x.txt")
    assert cur["size"] == 3
    assert cur["exists"] is True


def test_delete_current_clears_and_emits_event(client):
    tc, bus, _ = client
    tc.post(
        "/api/files/upload",
        files={"file": ("z.bin", io.BytesIO(b"xx"), "application/octet-stream")},
    )
    assert bus.current_file is not None

    with tc.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()  # saludo
        r = tc.delete("/api/files/current")
        assert r.status_code == 204
        evt = ws.receive_json()
        assert evt["type"] == "file.cleared"
    assert bus.current_file is None


def test_current_files_property_is_kept_in_sync(client):
    tc, bus, _ = client
    tc.post(
        "/api/files/upload",
        files={"file": ("a.txt", io.BytesIO(b"y"), "text/plain")},
    )
    assert bus.current_files == [bus.current_file]
    tc.delete("/api/files/current")
    assert bus.current_files == []
