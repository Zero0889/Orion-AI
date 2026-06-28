"""
Tests del bypass autenticado para ``POST /api/access/event``
============================================================
El endpoint debe aceptar requests desde IPs no-whitelisteadas (típico
caso: ESP32 en la LAN, ``192.168.x.x``) **solo si** traen el header
``X-Orion-Access-Token`` con el valor de ``config/access.json``.

Matriz de casos:
  · IP loopback        + sin header           → 201  (loopback whitelist)
  · IP loopback        + header bueno         → 201  (idem)
  · IP LAN (192.168.x) + sin header           → 403  (middleware filtra)
  · IP LAN (192.168.x) + header malo          → 403  (token incorrecto)
  · IP LAN (192.168.x) + header bueno         → 201  (bypass autenticado)
  · IP LAN (192.168.x) + header bueno + GET   → 403  (solo POST acepta bypass)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from orion.server import access_auth
from orion.server.app import build_app
from orion.server.event_bus import OrionEventBus


TEST_SECRET = "test-secret-fixed-no-rotation-needed-XYZ"


@pytest.fixture
def access_secret_file(tmp_path: Path, monkeypatch) -> Path:
    """Apunta access_auth al archivo en tmp y le escribe un secreto fijo."""
    cfg = tmp_path / "access.json"
    cfg.write_text(json.dumps({"shared_secret": TEST_SECRET}), encoding="utf-8")
    monkeypatch.setattr(access_auth, "ACCESS_CONFIG_PATH", cfg)
    # Invalidar cache para que el próximo get_secret() relea
    monkeypatch.setattr(access_auth, "_cached_secret", None)
    monkeypatch.setattr(access_auth, "_cached_mtime", None)
    return cfg


@pytest.fixture
def app(access_secret_file):
    return build_app(OrionEventBus())


@pytest.fixture
def loopback_client(app):
    """TestClient como si viniera de 127.0.0.1 (default del conftest)."""
    return TestClient(app)


@pytest.fixture
def lan_client(app):
    """TestClient simulando origen LAN no-whitelisteado."""
    return TestClient(app, client=("192.168.1.50", 50000))


VALID_EVENT = {
    "fingerprint_id": -1,
    "event_type": "DENIED",
    "esp_id": "test-esp",
    "confidence": 0,
}


# ── IP loopback: siempre pasa, con o sin header ────────────────────────


def test_loopback_without_header_ok(loopback_client):
    r = loopback_client.post("/api/access/event", json=VALID_EVENT)
    assert r.status_code == 201, r.text


def test_loopback_with_valid_token_ok(loopback_client):
    r = loopback_client.post(
        "/api/access/event",
        json=VALID_EVENT,
        headers={"X-Orion-Access-Token": TEST_SECRET},
    )
    assert r.status_code == 201, r.text


# ── IP LAN: depende del header ─────────────────────────────────────────


def test_lan_without_header_blocked(lan_client):
    r = lan_client.post("/api/access/event", json=VALID_EVENT)
    assert r.status_code == 403, r.text
    assert "Acceso denegado" in r.text


def test_lan_with_wrong_token_blocked(lan_client):
    r = lan_client.post(
        "/api/access/event",
        json=VALID_EVENT,
        headers={"X-Orion-Access-Token": "esto-no-es-el-token"},
    )
    assert r.status_code == 403, r.text


def test_lan_with_valid_token_ok(lan_client):
    r = lan_client.post(
        "/api/access/event",
        json=VALID_EVENT,
        headers={"X-Orion-Access-Token": TEST_SECRET},
    )
    assert r.status_code == 201, r.text


def test_lan_with_valid_token_but_get_blocked(lan_client):
    """GET /api/access/events NO entra en AUTHED_PATHS — el header no
    debe servir para listar eventos desde una IP no autorizada."""
    r = lan_client.get(
        "/api/access/events",
        headers={"X-Orion-Access-Token": TEST_SECRET},
    )
    assert r.status_code == 403, r.text


def test_lan_with_valid_token_post_other_path_blocked(lan_client):
    """POST /api/access/users (crear usuario) tampoco debe aceptar el
    header — solo /event lo hace."""
    r = lan_client.post(
        "/api/access/users",
        json={"fingerprint_id": 0, "name": "Hacker"},
        headers={"X-Orion-Access-Token": TEST_SECRET},
    )
    assert r.status_code == 403, r.text


# ── Sin secreto configurado: el bypass se desactiva ────────────────────


def test_lan_with_token_but_no_config_file(tmp_path, monkeypatch):
    """Si config/access.json no existe, ningún token vale → 403."""
    missing = tmp_path / "no-existe.json"
    monkeypatch.setattr(access_auth, "ACCESS_CONFIG_PATH", missing)
    monkeypatch.setattr(access_auth, "_cached_secret", None)
    monkeypatch.setattr(access_auth, "_cached_mtime", None)

    app = build_app(OrionEventBus())
    client = TestClient(app, client=("192.168.1.50", 50000))
    r = client.post(
        "/api/access/event",
        json=VALID_EVENT,
        headers={"X-Orion-Access-Token": "cualquier-cosa"},
    )
    assert r.status_code == 403, r.text
