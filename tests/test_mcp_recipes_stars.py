"""
tests.test_mcp_recipes_stars — Recetas curadas + estrellas de GitHub
======================================================================

Cubre:
  * Catálogo: shape de cada receta (campos obligatorios, tipos)
  * Endpoint GET /api/mcp/recipes
  * _parse_github_repo: extracción de owner/repo desde URLs variadas
  * GET /api/mcp/registry/stars: éxito, fallo silencioso, cache hit
"""

from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

import server.routes.mcp as mcp_route
from core.mcp_recipes import RECIPES, get_recipe, list_recipes
from server.routes.mcp import _fetch_github_stars, _parse_github_repo

# ── Catálogo ────────────────────────────────────────────────────────────


def test_catalog_not_empty():
    assert len(RECIPES) > 0


def test_every_recipe_has_required_fields():
    seen_ids = set()
    for r in RECIPES:
        assert r.recipe_id, "recipe_id vacío"
        assert r.title
        assert r.description
        assert r.category in {"files", "dev", "web", "ai", "system"}
        assert r.command
        assert isinstance(r.args_template, list)
        assert r.suggested_id
        assert r.recipe_id not in seen_ids, f"id duplicado: {r.recipe_id}"
        seen_ids.add(r.recipe_id)


def test_filesystem_recipe_present_and_official():
    r = get_recipe("filesystem")
    assert r is not None
    assert r.official is True
    # La receta debe tener un prompt para ROOT_PATH
    keys = {p.key for p in r.prompts}
    assert "ROOT_PATH" in keys
    # Y el placeholder debe aparecer literalmente en args
    assert any("{ROOT_PATH}" in a for a in r.args_template)


def test_github_recipe_requires_token_env():
    r = get_recipe("github")
    assert r is not None
    required = [e for e in r.env_required if e.required]
    assert any("GITHUB_PERSONAL_ACCESS_TOKEN" in e.name for e in required)


def test_list_recipes_returns_dicts():
    out = list_recipes()
    assert isinstance(out, list)
    for entry in out:
        assert isinstance(entry, dict)
        assert "recipe_id" in entry
        assert "args_template" in entry


# ── Endpoint /api/mcp/recipes ──────────────────────────────────────────


@pytest.fixture
def client(monkeypatch, tmp_path):
    # Aísla config + mock manager
    fake_path = tmp_path / "mcp_servers.json"
    monkeypatch.setattr(mcp_route, "MCP_CONFIG_PATH", fake_path)
    mgr = MagicMock()
    mgr.servers.return_value = {}
    monkeypatch.setattr(mcp_route, "get_mcp_manager", lambda: mgr)

    # Limpia el cache de stars
    mcp_route._GH_STAR_CACHE.clear()
    mcp_route._REGISTRY_CACHE.clear()

    from server.app import build_app
    from server.event_bus import OrionEventBus

    bus = OrionEventBus()
    app = build_app(bus)
    with TestClient(app) as tc:
        yield tc


def test_endpoint_recipes_returns_catalog(client):
    r = client.get("/api/mcp/recipes")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 5
    # Filesystem debe estar
    ids = {x["recipe_id"] for x in data}
    assert "filesystem" in ids


# ── _parse_github_repo ─────────────────────────────────────────────────


def test_parse_github_repo_basic():
    assert _parse_github_repo("https://github.com/foo/bar") == ("foo", "bar")


def test_parse_github_repo_with_tree_path():
    # URL del monorepo de mcp con /tree/main/src/X
    out = _parse_github_repo(
        "https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem"
    )
    assert out == ("modelcontextprotocol", "servers")


def test_parse_github_repo_with_www():
    assert _parse_github_repo("https://www.github.com/owner/repo") == ("owner", "repo")


def test_parse_github_repo_rejects_non_github():
    assert _parse_github_repo("https://gitlab.com/foo/bar") is None
    assert _parse_github_repo("https://example.com/anything") is None


def test_parse_github_repo_rejects_invalid():
    assert _parse_github_repo("") is None
    assert _parse_github_repo("not-a-url") is None
    assert _parse_github_repo("https://github.com/onlyowner") is None


# ── _fetch_github_stars ────────────────────────────────────────────────


def _mock_urlopen_json(payload: dict):
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def test_fetch_stars_returns_count():
    mcp_route._GH_STAR_CACHE.clear()
    with patch(
        "server.routes.mcp.urllib.request.urlopen",
        return_value=_mock_urlopen_json({"stargazers_count": 1234}),
    ):
        stars = _fetch_github_stars("https://github.com/foo/bar")
    assert stars == 1234


def test_fetch_stars_returns_none_on_network_error():
    mcp_route._GH_STAR_CACHE.clear()
    with patch(
        "server.routes.mcp.urllib.request.urlopen",
        side_effect=urllib.error.URLError("rate limited"),
    ):
        stars = _fetch_github_stars("https://github.com/foo/bar")
    assert stars is None


def test_fetch_stars_caches_positive_and_negative(client):
    mcp_route._GH_STAR_CACHE.clear()
    with patch(
        "server.routes.mcp.urllib.request.urlopen", side_effect=urllib.error.URLError("err")
    ) as m:
        _fetch_github_stars("https://github.com/foo/bar")
        _fetch_github_stars("https://github.com/foo/bar")
        _fetch_github_stars("https://github.com/foo/bar")
    # Una sola llamada al upstream, después cache hit (con None)
    assert m.call_count == 1


def test_fetch_stars_returns_none_for_non_github_url():
    mcp_route._GH_STAR_CACHE.clear()
    # No debe pegarle a GitHub si la URL es de otro lado
    with patch("server.routes.mcp.urllib.request.urlopen") as m:
        stars = _fetch_github_stars("https://gitlab.com/foo/bar")
    assert stars is None
    assert m.call_count == 0


# ── Endpoint /api/mcp/registry/stars ──────────────────────────────────


def test_endpoint_stars_returns_count(client):
    with patch(
        "server.routes.mcp.urllib.request.urlopen",
        return_value=_mock_urlopen_json({"stargazers_count": 999}),
    ):
        r = client.get("/api/mcp/registry/stars?repo_url=https://github.com/foo/bar")
    assert r.status_code == 200
    assert r.json() == {"repo_url": "https://github.com/foo/bar", "stars": 999}


def test_endpoint_stars_returns_null_when_unreachable(client):
    with patch(
        "server.routes.mcp.urllib.request.urlopen", side_effect=urllib.error.URLError("offline")
    ):
        r = client.get("/api/mcp/registry/stars?repo_url=https://github.com/foo/bar")
    assert r.status_code == 200
    assert r.json()["stars"] is None


def test_endpoint_stars_returns_null_for_non_github_url(client):
    r = client.get("/api/mcp/registry/stars?repo_url=https://gitlab.com/foo/bar")
    assert r.status_code == 200
    assert r.json()["stars"] is None
