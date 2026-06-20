"""
tests.test_mcp_routes — Endpoints REST de gestión de servidores MCP
====================================================================
Cubre los 7 endpoints de ``server/routes/mcp.py``:

  - GET    /api/mcp/servers
  - GET    /api/mcp/tools
  - POST   /api/mcp/servers
  - PUT    /api/mcp/servers/{id}
  - DELETE /api/mcp/servers/{id}
  - POST   /api/mcp/servers/{id}/restart
  - POST   /api/mcp/reload

Estrategia:
  * Redirigir ``MCP_CONFIG_PATH`` a un ``tmp_path`` para no tocar el
    config real.
  * Mockear ``get_mcp_manager`` con un fake que NO lanza subprocesses,
    solo cuenta llamadas (start_all/restart_server/stop).
  * Verificar que el JSON queda escrito atómicamente y los endpoints
    devuelven shapes consistentes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient


@pytest.fixture
def fake_manager(monkeypatch):
    """Reemplaza el MCPManager global por un mock que no spawnea nada."""
    mgr = MagicMock()
    mgr.servers.return_value = {}
    mgr.start_all.return_value = 0
    mgr.reload_all.return_value = 0
    mgr.restart_server.return_value = 0
    import core.mcp_client as mcp_mod

    monkeypatch.setattr(mcp_mod, "_GLOBAL_MANAGER", mgr)
    monkeypatch.setattr(mcp_mod, "get_mcp_manager", lambda: mgr)
    # También parcheamos el import directo en la route
    import server.routes.mcp as mcp_route

    monkeypatch.setattr(mcp_route, "get_mcp_manager", lambda: mgr)
    return mgr


@pytest.fixture
def isolated_config(monkeypatch, tmp_path):
    """Redirige MCP_CONFIG_PATH al tmp_path para que los POST no tocan
    el archivo real."""
    fake_path = tmp_path / "mcp_servers.json"
    import server.routes.mcp as mcp_route

    monkeypatch.setattr(mcp_route, "MCP_CONFIG_PATH", fake_path)
    return fake_path


@pytest.fixture
def client(fake_manager, isolated_config):
    """TestClient con app real, manager y config mockeados."""
    from server.app import build_app
    from server.event_bus import OrionEventBus

    bus = OrionEventBus()
    app = build_app(bus)
    with TestClient(app) as tc:
        yield tc


# ── GET endpoints ───────────────────────────────────────────────────────


def test_list_servers_empty(client, isolated_config):
    r = client.get("/api/mcp/servers")
    assert r.status_code == 200
    assert r.json() == []


def test_list_servers_returns_configured(client, isolated_config):
    isolated_config.write_text(
        json.dumps(
            {
                "servers": {
                    "fs": {
                        "command": "npx",
                        "args": ["-y", "@mcp/server-filesystem"],
                        "enabled": True,
                    },
                }
            }
        )
    )
    r = client.get("/api/mcp/servers")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["id"] == "fs"
    assert data[0]["command"] == "npx"
    assert data[0]["enabled"] is True
    assert data[0]["running"] is False  # fake manager no tiene servers vivos
    assert data[0]["tool_count"] == 0


def test_list_tools_excludes_builtins(client):
    # Builtins no tienen `__` en el nombre → no salen
    r = client.get("/api/mcp/tools")
    assert r.status_code == 200
    assert r.json() == []


# ── POST create ────────────────────────────────────────────────────────


def test_create_server_persists_config(client, isolated_config, fake_manager):
    body = {
        "id": "fs",
        "command": "echo",
        "args": ["hello"],
        "enabled": False,  # disabled → no intento de spawn
    }
    r = client.post("/api/mcp/servers", json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["id"] == "fs"
    assert data["enabled"] is False
    # No se llamó a restart_server porque está disabled
    fake_manager.restart_server.assert_not_called()
    # El archivo de config se escribió
    raw = json.loads(isolated_config.read_text())
    assert "fs" in raw["servers"]


def test_create_server_with_enabled_triggers_start(client, isolated_config, fake_manager):
    fake_manager.restart_server.return_value = 3
    body = {"id": "alpha", "command": "echo", "enabled": True}
    r = client.post("/api/mcp/servers", json=body)
    assert r.status_code == 201
    fake_manager.restart_server.assert_called_once_with("alpha")


def test_create_server_rejects_duplicate(client, isolated_config):
    isolated_config.write_text(json.dumps({"servers": {"fs": {"command": "echo"}}}))
    r = client.post("/api/mcp/servers", json={"id": "fs", "command": "echo"})
    assert r.status_code == 409


def test_create_server_rejects_missing_id(client):
    r = client.post("/api/mcp/servers", json={"command": "echo"})
    assert r.status_code == 400


def test_create_server_rejects_invalid_id_chars(client):
    r = client.post("/api/mcp/servers", json={"id": "foo bar!", "command": "echo"})
    assert r.status_code == 400


# ── PUT update ─────────────────────────────────────────────────────────


def test_update_server_writes_and_restarts(client, isolated_config, fake_manager):
    isolated_config.write_text(json.dumps({"servers": {"fs": {"command": "old"}}}))
    body = {"command": "newcmd", "args": ["-x"], "enabled": True}
    r = client.put("/api/mcp/servers/fs", json=body)
    assert r.status_code == 200
    fake_manager.restart_server.assert_called_once_with("fs")
    raw = json.loads(isolated_config.read_text())
    assert raw["servers"]["fs"]["command"] == "newcmd"


def test_update_server_disabled_stops(client, isolated_config, fake_manager):
    isolated_config.write_text(json.dumps({"servers": {"fs": {"command": "echo"}}}))
    fake_srv = MagicMock()
    fake_manager.servers.return_value = {"fs": fake_srv}
    fake_manager._servers = {"fs": fake_srv}
    body = {"command": "echo", "enabled": False}
    r = client.put("/api/mcp/servers/fs", json=body)
    assert r.status_code == 200
    fake_srv.stop.assert_called_once()
    fake_manager.restart_server.assert_not_called()


def test_update_server_not_found(client):
    r = client.put("/api/mcp/servers/nope", json={"command": "echo"})
    assert r.status_code == 404


# ── DELETE ─────────────────────────────────────────────────────────────


def test_delete_server_removes_config_and_stops(client, isolated_config, fake_manager):
    isolated_config.write_text(
        json.dumps(
            {
                "servers": {
                    "fs": {"command": "echo"},
                    "other": {"command": "echo"},
                }
            }
        )
    )
    fake_srv = MagicMock()
    fake_manager.servers.return_value = {"fs": fake_srv}
    fake_manager._servers = {"fs": fake_srv}

    r = client.delete("/api/mcp/servers/fs")
    assert r.status_code == 204
    fake_srv.stop.assert_called_once()
    raw = json.loads(isolated_config.read_text())
    assert "fs" not in raw["servers"]
    assert "other" in raw["servers"]


def test_delete_server_not_found(client):
    r = client.delete("/api/mcp/servers/nope")
    assert r.status_code == 404


# ── Restart / reload ───────────────────────────────────────────────────


def test_restart_server_calls_manager(client, isolated_config, fake_manager):
    isolated_config.write_text(json.dumps({"servers": {"fs": {"command": "echo"}}}))
    fake_manager.restart_server.return_value = 5
    r = client.post("/api/mcp/servers/fs/restart")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["tool_count"] == 5
    fake_manager.restart_server.assert_called_once_with("fs")


def test_restart_server_not_found(client):
    r = client.post("/api/mcp/servers/zzz/restart")
    assert r.status_code == 404


def test_reload_all_calls_manager(client, fake_manager):
    fake_manager.reload_all.return_value = 7
    r = client.post("/api/mcp/reload")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "tool_count": 7}
    fake_manager.reload_all.assert_called_once()
