"""
tests.test_mcp_registry_proxy — Proxy + normalización del registry MCP
=======================================================================
El backend hace de intermediario entre el frontend y
``registry.modelcontextprotocol.io``. Estos tests cubren:

  * Normalización de packages (npm / pypi / oci / runtimeHint custom)
  * Filtrado: packages no-stdio se descartan
  * Mapeo de runtimeArguments + identifier + packageArguments → args
  * Pasaje de query string a upstream
  * Cache TTL (segunda llamada con la misma URL no pega de nuevo)
  * Graceful degradation cuando el upstream falla
"""

from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient   # noqa: E402

import server.routes.mcp as mcp_route       # noqa: E402
from server.routes.mcp import _normalize_package, _normalize_server  # noqa: E402


# ── Unit tests de _normalize_package ────────────────────────────────────


def test_normalize_npm_package_basic():
    pkg = {
        "registryType": "npm",
        "identifier":   "remote-filesystem-mcp-server",
        "version":      "0.1.2",
        "runtimeHint":  "npx",
        "transport":    {"type": "stdio"},
        "runtimeArguments": [{"value": "-y", "type": "positional"}],
        "environmentVariables": [],
    }
    out = _normalize_package(pkg)
    assert out is not None
    assert out["command"] == "npx"
    assert out["args"] == ["-y", "remote-filesystem-mcp-server"]
    assert out["env_required"] == []
    assert out["version"] == "0.1.2"


def test_normalize_falls_back_to_npx_when_no_runtime_hint():
    pkg = {
        "registryType": "npm",
        "identifier":   "@anthropic/mcp-server-github",
        "transport":    {"type": "stdio"},
    }
    out = _normalize_package(pkg)
    assert out is not None
    assert out["command"] == "npx"
    assert out["args"] == ["@anthropic/mcp-server-github"]


def test_normalize_pypi_uses_uvx():
    pkg = {
        "registryType": "pypi",
        "identifier":   "mcp-server-git",
        "transport":    {"type": "stdio"},
    }
    out = _normalize_package(pkg)
    assert out is not None
    assert out["command"] == "uvx"


def test_normalize_unknown_registry_returns_none():
    pkg = {
        "registryType": "weird-format",
        "identifier":   "x",
        "transport":    {"type": "stdio"},
    }
    assert _normalize_package(pkg) is None


def test_normalize_skips_non_stdio_transport():
    pkg = {
        "registryType": "npm",
        "identifier":   "x",
        "transport":    {"type": "sse"},  # ORION solo soporta stdio
    }
    assert _normalize_package(pkg) is None


def test_normalize_includes_package_arguments_after_identifier():
    pkg = {
        "registryType": "npm",
        "identifier":   "@mcp/server-filesystem",
        "transport":    {"type": "stdio"},
        "runtimeArguments": [{"value": "-y"}],
        "packageArguments": [{"value": "/data"}, {"value": "/work"}],
    }
    out = _normalize_package(pkg)
    assert out["args"] == ["-y", "@mcp/server-filesystem", "/data", "/work"]


def test_normalize_env_vars_carry_required_flag():
    pkg = {
        "registryType": "npm",
        "identifier":   "@mcp/server-github",
        "transport":    {"type": "stdio"},
        "environmentVariables": [
            {"name": "GITHUB_PERSONAL_ACCESS_TOKEN",
             "description": "Token con scope repo",
             "isRequired": True},
            {"name": "GITHUB_API_URL",
             "description": "GHE base URL",
             "isRequired": False},
        ],
    }
    out = _normalize_package(pkg)
    assert len(out["env_required"]) == 2
    assert out["env_required"][0]["name"] == "GITHUB_PERSONAL_ACCESS_TOKEN"
    assert out["env_required"][0]["required"] is True
    assert out["env_required"][1]["required"] is False


# ── Unit tests de _normalize_server ─────────────────────────────────────


def test_normalize_server_unwraps_official_envelope():
    """Desde sep-2025 el registry oficial usa el shape
    ``{"server": {...}, "_meta": {...}}``. Debemos leer del subdoc."""
    entry = {
        "server": {
            "name":        "@mcp/server-fs",
            "title":       "Filesystem",
            "description": "FS ops",
            "version":     "0.1.0",
            "repository":  {"url": "https://github.com/x/y"},
            "packages": [{
                "registryType": "npm",
                "identifier":   "@mcp/server-fs",
                "transport":    {"type": "stdio"},
                "runtimeHint":  "npx",
                "runtimeArguments": [{"value": "-y"}],
            }],
        },
        "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}},
    }
    out = _normalize_server(entry)
    assert out["name"] == "@mcp/server-fs"
    assert out["title"] == "Filesystem"
    assert out["repository"] == "https://github.com/x/y"
    assert out["installable"] is True
    assert out["remote"] is False
    assert len(out["packages"]) == 1
    assert out["packages"][0]["command"] == "npx"


def test_normalize_server_legacy_flat_shape_still_works():
    """Tolerancia hacia atrás: si el upstream vuelve al shape plano,
    seguimos sirviendo."""
    server = {
        "name":        "@mcp/server-fs",
        "title":       "Filesystem",
        "description": "FS ops",
        "packages": [{
            "registryType": "npm",
            "identifier":   "@mcp/server-fs",
            "transport":    {"type": "stdio"},
            "runtimeHint":  "npx",
        }],
    }
    out = _normalize_server(server)
    assert out["installable"] is True
    assert out["title"] == "Filesystem"


def test_normalize_server_remote_only_streamable_http():
    """Servers que exponen 'remotes' sin packages → no instalable hoy
    (cliente solo stdio), pero los marcamos como remote para que la UI
    los liste con un tag claro."""
    entry = {
        "server": {
            "name": "ai.smithery/example-github",
            "title": "Smithery GitHub",
            "description": "Remote MCP server",
            "remotes": [
                {"type": "streamable-http",
                 "url": "https://server.smithery.ai/example/mcp"},
            ],
        },
        "_meta": {},
    }
    out = _normalize_server(entry)
    assert out["installable"] is False
    assert out["remote"] is True
    assert out["remote_kinds"] == ["streamable-http"]
    assert out["title"] == "Smithery GitHub"
    assert out["name"] == "ai.smithery/example-github"


def test_normalize_server_not_installable_when_only_unsupported_packages():
    server = {
        "name": "weird",
        "packages": [{"registryType": "oci", "identifier": "img",
                      "transport": {"type": "sse"}}],
    }
    out = _normalize_server(server)
    assert out["installable"] is False
    assert out["remote"] is False
    assert out["packages"] == []


# ── Endpoint integration con upstream mockeado ─────────────────────────


@pytest.fixture
def clear_cache():
    mcp_route._REGISTRY_CACHE.clear()
    yield
    mcp_route._REGISTRY_CACHE.clear()


@pytest.fixture
def client(monkeypatch, tmp_path, clear_cache):
    # Aísla config path (los endpoints CRUD también lo usan; no nos importa
    # aquí pero evita escrituras al archivo real)
    fake_path = tmp_path / "mcp_servers.json"
    monkeypatch.setattr(mcp_route, "MCP_CONFIG_PATH", fake_path)

    # Manager mockeado
    mgr = MagicMock()
    mgr.servers.return_value = {}
    monkeypatch.setattr(mcp_route, "get_mcp_manager", lambda: mgr)

    from server.event_bus import OrionEventBus
    from server.app import build_app
    bus = OrionEventBus()
    app = build_app(bus)
    with TestClient(app) as tc:
        yield tc


def _mock_urlopen(payload: dict):
    """Devuelve un context manager mock para urlopen."""
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__  = MagicMock(return_value=False)
    return response


def test_registry_search_returns_normalized_servers(client):
    payload = {
        "servers": [
            {
                "server": {
                    "name": "fs",
                    "title": "Filesystem",
                    "description": "FS ops",
                    "version": "1.0",
                    "packages": [{
                        "registryType": "npm",
                        "identifier": "@mcp/fs",
                        "transport": {"type": "stdio"},
                        "runtimeHint": "npx",
                        "runtimeArguments": [{"value": "-y"}],
                    }],
                },
                "_meta": {},
            }
        ],
        "metadata": {"nextCursor": "abc", "count": 1},
    }
    with patch("server.routes.mcp.urllib.request.urlopen",
               return_value=_mock_urlopen(payload)):
        r = client.get("/api/mcp/registry/search?q=fs&limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert data["next_cursor"] == "abc"
    assert data["servers"][0]["name"] == "fs"
    assert data["servers"][0]["installable"] is True
    assert data["servers"][0]["packages"][0]["command"] == "npx"


def test_registry_search_passes_query_to_upstream(client):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.get_full_url()
        return _mock_urlopen({"servers": [], "metadata": {}})

    with patch("server.routes.mcp.urllib.request.urlopen", fake_urlopen):
        r = client.get("/api/mcp/registry/search?q=github&limit=5")
    assert r.status_code == 200
    assert "search=github" in captured["url"]
    assert "limit=5" in captured["url"]


def test_registry_search_uses_cache(client):
    payload = {"servers": [], "metadata": {"count": 0}}
    with patch("server.routes.mcp.urllib.request.urlopen",
               return_value=_mock_urlopen(payload)) as m:
        client.get("/api/mcp/registry/search?q=cached")
        client.get("/api/mcp/registry/search?q=cached")
        client.get("/api/mcp/registry/search?q=cached")
    # Solo una vez salió al upstream
    assert m.call_count == 1


def test_registry_search_graceful_when_upstream_down(client):
    def fail(*a, **kw):
        raise urllib.error.URLError("connection refused")
    with patch("server.routes.mcp.urllib.request.urlopen", side_effect=fail):
        r = client.get("/api/mcp/registry/search?q=anything")
    assert r.status_code == 502
    assert "no disponible" in r.json()["detail"].lower() or "refused" in r.json()["detail"].lower()


def test_registry_search_graceful_on_invalid_json(client):
    response = MagicMock()
    response.read.return_value = b"<html>not json</html>"
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__  = MagicMock(return_value=False)
    with patch("server.routes.mcp.urllib.request.urlopen", return_value=response):
        r = client.get("/api/mcp/registry/search?q=x")
    assert r.status_code == 502
