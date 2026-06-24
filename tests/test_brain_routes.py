"""
tests.test_brain_routes — endpoints REST de configuración del cerebro.

Cubre:
  - GET  /api/settings/brain → estado activo + catálogo + ollama + gemini
  - PUT  /api/settings/brain → persist + bus event + 400 si provider raro
  - PUT  /api/settings/brain/providers/{name}/key → guarda/borra key
  - GET  /api/settings/brain/ollama → detector
  - POST /api/settings/brain/test → ping ok / sin creds / excepción
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Aísla brain.json + providers.json en tmp y resetea caches."""
    from orion.core import chat_brain
    from orion.core.llm import base as llm_base
    from orion.server.routes import brain as brain_route

    monkeypatch.setattr(chat_brain, "BRAIN_CONFIG_PATH", tmp_path / "brain.json")
    chat_brain.reset_cache_for_tests()

    # providers.json: parchamos BASE_DIR para que el writer/reader usen tmp
    fake_config_dir = tmp_path / "config"
    fake_config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(llm_base, "BASE_DIR", tmp_path)
    llm_base.reset_config_cache()

    # Ollama detect: stub que devuelve "no corriendo" para no depender de red
    monkeypatch.setattr(
        brain_route,
        "_ollama_detect",
        lambda: {"running": False, "base_url": "http://localhost:11434", "models": []},
    )

    yield tmp_path

    chat_brain.reset_cache_for_tests()
    llm_base.reset_config_cache()


@pytest.fixture
def client(isolated):
    from orion.server.app import build_app
    from orion.server.event_bus import OrionEventBus

    bus = OrionEventBus()
    app = build_app(bus)
    with TestClient(app) as tc:
        yield tc, bus


# ── GET /api/settings/brain ──────────────────────────────────────────────


def test_get_brain_default_is_gemini(client):
    tc, _ = client
    r = tc.get("/api/settings/brain")
    assert r.status_code == 200
    data = r.json()
    assert data["active"]["provider"] == "gemini"
    assert data["active"]["is_live"] is True
    # El catálogo expone deepseek/ollama/etc.
    ids = {p["id"] for p in data["providers"]}
    assert {"gemini", "deepseek", "ollama", "openrouter"}.issubset(ids)
    # Estructura ollama presente
    assert data["ollama"]["running"] is False
    assert data["ollama"]["base_url"] == "http://localhost:11434"
    # Estructura gemini
    assert "configured" in data["gemini"]


def test_get_brain_marks_keyed_providers_as_available(client, tmp_path):
    """Si guardamos una key en providers.json, la disponibilidad cambia."""
    from orion.core.llm import base as llm_base

    llm_base.set_provider_key("deepseek", "sk-test")

    tc, _ = client
    data = tc.get("/api/settings/brain").json()
    deepseek = next(p for p in data["providers"] if p["id"] == "deepseek")
    assert deepseek["available"] is True
    assert deepseek["needs_key"] is True


# ── PUT /api/settings/brain ──────────────────────────────────────────────


def test_put_brain_persists_and_publishes(client):
    tc, bus = client
    captured: list[dict] = []
    original_publish = bus.publish
    bus.publish = lambda evt, payload=None: (
        captured.append({"evt": evt, "payload": payload or {}}),
        original_publish(evt, payload),
    )[1]

    r = tc.put(
        "/api/settings/brain",
        json={"provider": "deepseek", "model": "deepseek-chat"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"]["provider"] == "deepseek"
    assert body["active"]["is_live"] is False

    # GET subsiguiente devuelve lo nuevo
    after = tc.get("/api/settings/brain").json()
    assert after["active"] == {"provider": "deepseek", "model": "deepseek-chat", "is_live": False}

    # Bus debe haber visto settings.brain
    brain_events = [e for e in captured if e["evt"] == "settings.brain"]
    assert brain_events, f"esperaba settings.brain en {captured}"
    assert brain_events[-1]["payload"] == {"provider": "deepseek", "model": "deepseek-chat"}


def test_put_brain_rejects_unknown_provider(client):
    tc, _ = client
    r = tc.put("/api/settings/brain", json={"provider": "skynet", "model": "tm-2000"})
    assert r.status_code == 400
    assert "skynet" in r.text.lower() or "no soportado" in r.text.lower()


def test_put_brain_rejects_empty_model(client):
    tc, _ = client
    r = tc.put("/api/settings/brain", json={"provider": "deepseek", "model": ""})
    assert r.status_code == 422  # pydantic min_length


# ── PUT /api/settings/brain/providers/{name}/key ─────────────────────────


def test_set_provider_key_writes_to_providers_json(client, isolated):
    tc, _ = client
    r = tc.put("/api/settings/brain/providers/deepseek/key", json={"key": "sk-real"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["configured"] is True
    assert body["available"] is True

    # Persiste
    raw = (isolated / "config" / "providers.json").read_text(encoding="utf-8")
    assert "sk-real" in raw


def test_set_provider_key_empty_clears(client, isolated):
    tc, _ = client
    # Primero set
    tc.put("/api/settings/brain/providers/deepseek/key", json={"key": "sk-real"})
    # Después clear
    r = tc.put("/api/settings/brain/providers/deepseek/key", json={"key": ""})
    assert r.status_code == 200
    assert r.json()["configured"] is False
    raw = (isolated / "config" / "providers.json").read_text(encoding="utf-8")
    assert "sk-real" not in raw


def test_set_provider_key_rejects_unknown(client):
    tc, _ = client
    r = tc.put("/api/settings/brain/providers/skynet/key", json={"key": "x"})
    assert r.status_code == 400


# ── GET /api/settings/brain/ollama ───────────────────────────────────────


def test_get_ollama_endpoint(client):
    tc, _ = client
    r = tc.get("/api/settings/brain/ollama")
    assert r.status_code == 200
    body = r.json()
    assert body["running"] is False
    assert body["base_url"] == "http://localhost:11434"


# ── POST /api/settings/brain/test ────────────────────────────────────────


def test_brain_test_returns_provider_response(client, monkeypatch):
    """El test endpoint llama al provider y devuelve su texto."""
    from orion.core.llm.base import LLMResponse
    from orion.server.routes import brain as brain_route

    class StubProvider:
        name = "deepseek"

        def is_available(self) -> bool:
            return True

        def complete(self, messages, *, model, temperature=0.7, max_tokens=None):
            return LLMResponse(text="pong", model=model, provider="deepseek")

    monkeypatch.setattr(brain_route, "get_provider", lambda _n: StubProvider())

    tc, _ = client
    r = tc.post(
        "/api/settings/brain/test",
        json={"provider": "deepseek", "model": "deepseek-chat"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["text"] == "pong"


def test_brain_test_signals_missing_credentials(client, monkeypatch):
    from orion.server.routes import brain as brain_route

    class StubProvider:
        name = "deepseek"

        def is_available(self) -> bool:
            return False

        def complete(self, *args, **kwargs):
            raise AssertionError("no debería llamarse")

    monkeypatch.setattr(brain_route, "get_provider", lambda _n: StubProvider())

    tc, _ = client
    r = tc.post(
        "/api/settings/brain/test",
        json={"provider": "deepseek", "model": "deepseek-chat"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body.get("actionable") is True
    assert "credenciales" in body["error"].lower() or "sin" in body["error"].lower()


def test_brain_test_handles_provider_exception(client, monkeypatch):
    from orion.server.routes import brain as brain_route

    class BoomProvider:
        name = "deepseek"

        def is_available(self) -> bool:
            return True

        def complete(self, *args, **kwargs):
            raise RuntimeError("HTTP 401: API key invalid")

    monkeypatch.setattr(brain_route, "get_provider", lambda _n: BoomProvider())

    tc, _ = client
    r = tc.post(
        "/api/settings/brain/test",
        json={"provider": "deepseek", "model": "deepseek-chat"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "401" in body["error"] or "key" in body["error"].lower()
