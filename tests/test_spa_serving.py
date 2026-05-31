"""
tests.test_spa_serving
=======================
Verifica que cuando ``web/dist/index.html`` existe, el backend FastAPI
lo sirve en ``/`` y hace SPA fallback para rutas desconocidas.

Sólo se ejecuta si el bundle está construido (``npm run build`` en web/).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DIST = PROJECT_ROOT / "web" / "dist"
INDEX = DIST / "index.html"


@pytest.fixture
def client():
    if not INDEX.is_file():
        pytest.skip("web/dist no construido. Ejecuta `npm run build` en web/.")
    from server.event_bus import OrionEventBus
    from server.app import build_app
    bus = OrionEventBus()
    app = build_app(bus)
    with TestClient(app) as tc:
        yield tc


def test_root_serves_spa(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<!doctype html" in r.text.lower()
    assert "id=\"root\"" in r.text


def test_assets_route_exists_or_skips(client):
    """Si Vite generó /assets, deben servirse con MIME correcto."""
    assets_dir = DIST / "assets"
    if not assets_dir.is_dir():
        pytest.skip("Sin /assets en dist")
    # Tomamos cualquier .js del bundle
    js_files = list(assets_dir.glob("*.js"))
    if not js_files:
        pytest.skip("Sin .js en dist/assets")
    r = client.get(f"/assets/{js_files[0].name}")
    assert r.status_code == 200
    assert "javascript" in r.headers.get("content-type", "").lower()


def test_unknown_path_returns_index(client):
    """SPA fallback: rutas que no son API ni archivos reales devuelven index."""
    r = client.get("/no-existe-esta-ruta")
    assert r.status_code == 200
    assert "<!doctype html" in r.text.lower()


def test_api_routes_still_work_with_spa_mounted(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_path_traversal_blocked(client):
    """Defensa: la fallback no debe servir archivos fuera de dist."""
    r = client.get("/../requirements.txt")
    # Lo importante es que NO devuelva contenido de requirements.txt.
    # Aceptamos cualquier código que no sea 200 con el texto sensible.
    assert "fastapi" not in r.text.lower() or "<!doctype html" in r.text.lower()
