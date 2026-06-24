"""Tests del wizard de primer arranque (/api/onboarding/{status,save})."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from orion.server.app import build_app
from orion.server.event_bus import OrionEventBus


@pytest.fixture
def isolated_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Re-rutea config/data del test a ``tmp_path`` sin recargar módulos.

    Recargar `orion.config` rompería el fixture autouse `_isolated_sqlite_db`
    de conftest (resetea el singleton del SQLite y se pierden los handlers).
    En lugar de reload, monkeypatcheamos los símbolos *donde se leen*: el
    módulo de la ruta tiene su propia referencia importada al top.
    """
    monkeypatch.delenv("ORION_GEMINI_KEY", raising=False)

    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    api_path = config_dir / "api_keys.json"

    import orion.config as cfg_mod
    import orion.server.routes.onboarding as onb_mod

    # Símbolos consumidos por load_config/save_config (lazy lookup desde el
    # módulo cfg_mod).
    monkeypatch.setattr(cfg_mod, "BASE_DIR", tmp_path)
    monkeypatch.setattr(cfg_mod, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cfg_mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(cfg_mod, "API_CONFIG_PATH", api_path)
    # Símbolos importados directo por el router (snapshot al import time).
    monkeypatch.setattr(onb_mod, "API_CONFIG_PATH", api_path)
    monkeypatch.setattr(onb_mod, "BASE_DIR", tmp_path)
    monkeypatch.setattr(onb_mod, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(onb_mod, "DATA_DIR", data_dir)

    yield tmp_path


@pytest.fixture
def client(isolated_appdata: Path):
    bus = OrionEventBus()
    app = build_app(bus)
    with TestClient(app) as tc:
        yield tc, bus


# ── /status ───────────────────────────────────────────────────────────────


def test_status_reports_not_ready_when_no_key(client) -> None:
    tc, _ = client
    r = tc.get("/api/onboarding/status")
    assert r.status_code == 200
    data = r.json()
    assert data["ready"] is False
    assert data["has_api_key"] is False
    assert data["base_dir"]
    assert data["api_keys_path"].endswith("api_keys.json")


def test_status_reports_ready_when_env_key_present(client, monkeypatch: pytest.MonkeyPatch) -> None:
    tc, _ = client
    monkeypatch.setenv("ORION_GEMINI_KEY", "fake-env-test-key")
    r = tc.get("/api/onboarding/status")
    assert r.status_code == 200
    assert r.json()["ready"] is True


# ── /save ─────────────────────────────────────────────────────────────────


def test_save_rejects_short_key(client) -> None:
    tc, _ = client
    r = tc.post("/api/onboarding/save", json={"gemini_api_key": "short"})
    # 422 viene del validador de pydantic (min_length=10).
    assert r.status_code == 422


def test_save_persists_key_and_marks_ready_when_validation_disabled(client) -> None:
    tc, bus = client
    r = tc.post(
        "/api/onboarding/save",
        json={"gemini_api_key": "fake-test-api-key-not-real", "validate_remote": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert "api_keys_path" in body

    # Estado en el bus desbloqueado (mark_ready flipea _api_key_ready).
    assert bus._api_key_ready.is_set()

    # El siguiente status debe reflejar ready=True.
    r2 = tc.get("/api/onboarding/status")
    assert r2.json()["ready"] is True


def test_save_with_remote_validation_rejects_invalid_key(client) -> None:
    tc, _ = client

    def fake_validate(_key: str) -> str | None:
        return "Google rechazó la API key (API_KEY_INVALID)."

    with patch(
        "orion.server.routes.onboarding._validate_gemini_key",
        side_effect=fake_validate,
    ):
        r = tc.post(
            "/api/onboarding/save",
            json={"gemini_api_key": "fake-rejected-test-key"},
        )
    assert r.status_code == 400
    assert "API_KEY_INVALID" in r.json()["detail"]


def test_save_with_remote_validation_accepts_valid_key(client) -> None:
    tc, _ = client

    with patch(
        "orion.server.routes.onboarding._validate_gemini_key",
        return_value=None,
    ):
        r = tc.post(
            "/api/onboarding/save",
            json={"gemini_api_key": "fake-valid-test-key-9"},
        )
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_save_writes_to_isolated_appdata(client, isolated_appdata: Path) -> None:
    tc, _ = client
    r = tc.post(
        "/api/onboarding/save",
        json={"gemini_api_key": "fake-isolated-test-key", "validate_remote": False},
    )
    assert r.status_code == 200
    # El archivo debe haberse creado bajo tmp_path/config/, no en el repo.
    expected = isolated_appdata / "config" / "api_keys.json"
    assert expected.exists()
    assert "gemini_api_key" in expected.read_text(encoding="utf-8")
