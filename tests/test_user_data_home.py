"""Tests para la resolución de paths de config/data: dev vs frozen,
override por env var, y el seeding de templates en primer arranque."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


def _reload_config():
    """Recarga `orion.config` para que los module-level paths se recomputen
    con los valores actuales de env vars y `sys.frozen`."""
    import orion.config as cfg

    return importlib.reload(cfg)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Limpia env vars que influyen en `_user_data_home()` para que cada
    test parta de un estado conocido."""
    for k in ("ORION_DATA_HOME", "APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME"):
        monkeypatch.delenv(k, raising=False)


def test_dev_mode_uses_repo_root(monkeypatch: pytest.MonkeyPatch, clean_env: None) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    cfg = _reload_config()
    # Repo root = parent de orion/.
    expected = Path(cfg.__file__).resolve().parent.parent.parent
    assert cfg.BASE_DIR == expected


def test_orion_data_home_override_in_dev(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: None
) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setenv("ORION_DATA_HOME", str(tmp_path))
    cfg = _reload_config()
    assert cfg.BASE_DIR == tmp_path
    assert cfg.CONFIG_DIR == tmp_path / "config"
    assert cfg.DATA_DIR == tmp_path / "data"


def test_frozen_mode_uses_appdata_on_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: None
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cfg = _reload_config()
    assert cfg.BASE_DIR == tmp_path / "Orion"
    assert cfg.CONFIG_DIR == tmp_path / "Orion" / "config"


def test_frozen_falls_back_to_localappdata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: None
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    cfg = _reload_config()
    # Sin APPDATA, debe caer a LOCALAPPDATA.
    assert cfg.BASE_DIR == tmp_path / "Orion"


def test_frozen_mode_uses_app_support_on_mac(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: None
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    # Path.home() lee USERPROFILE/HOME según el OS host, no respeta solo
    # HOME en Windows. Monkeypatch directo a Path.home garantiza el path.
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    cfg = _reload_config()
    assert cfg.BASE_DIR == tmp_path / "Library" / "Application Support" / "Orion"


def test_frozen_mode_uses_xdg_on_linux(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: None
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    cfg = _reload_config()
    assert cfg.BASE_DIR == tmp_path / "orion"


def test_has_valid_api_key_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: None
) -> None:
    monkeypatch.setenv("ORION_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("ORION_GEMINI_KEY", "fake-test-key-env-only")
    cfg = _reload_config()
    assert cfg.has_valid_api_key() is True


def test_has_valid_api_key_from_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: None
) -> None:
    monkeypatch.delenv("ORION_GEMINI_KEY", raising=False)
    monkeypatch.setenv("ORION_DATA_HOME", str(tmp_path))
    cfg = _reload_config()
    cfg.save_config({"gemini_api_key": "fake-test-key-file-only"})
    assert cfg.has_valid_api_key() is True


def test_has_valid_api_key_returns_false_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: None
) -> None:
    monkeypatch.delenv("ORION_GEMINI_KEY", raising=False)
    monkeypatch.setenv("ORION_DATA_HOME", str(tmp_path))
    cfg = _reload_config()
    # Aseguramos que el archivo no exista o esté vacío.
    if cfg.API_CONFIG_PATH.exists():
        cfg.API_CONFIG_PATH.unlink()
    assert cfg.has_valid_api_key() is False


def test_seed_default_configs_copies_templates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: None
) -> None:
    """Cuando RESOURCES_DIR/config/ tiene templates y CONFIG_DIR está vacío,
    el seed los copia. NO copia api_keys.json — esa la pide el wizard."""
    # Aislamos el BASE_DIR
    monkeypatch.setenv("ORION_DATA_HOME", str(tmp_path))
    cfg = _reload_config()

    # Forzamos RESOURCES_DIR a un dir nuevo con templates fake.
    res = tmp_path / "_resources"
    (res / "config").mkdir(parents=True)
    (res / "config" / "api_keys.example.json").write_text('{"gemini_api_key":""}', encoding="utf-8")
    (res / "config" / "iot_config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cfg, "RESOURCES_DIR", res)

    created = cfg.seed_default_configs()
    names = sorted(p.name for p in created)
    assert "api_keys.example.json" in names
    assert "iot_config.json" in names
    # api_keys.json (real, no .example) NO se copia.
    assert not (cfg.CONFIG_DIR / "api_keys.json").exists()


def test_seed_is_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: None
) -> None:
    monkeypatch.setenv("ORION_DATA_HOME", str(tmp_path))
    cfg = _reload_config()
    res = tmp_path / "_resources"
    (res / "config").mkdir(parents=True)
    (res / "config" / "iot_config.json").write_text('{"v":1}', encoding="utf-8")
    monkeypatch.setattr(cfg, "RESOURCES_DIR", res)

    first = cfg.seed_default_configs()
    assert any(p.name == "iot_config.json" for p in first)
    # Segunda vez: no toca lo que ya existe.
    second = cfg.seed_default_configs()
    assert second == []


@pytest.fixture(autouse=True)
def _restore_config_module():
    """Tras cada test, restauramos el módulo a su estado normal del repo
    para que tests downstream no vean BASE_DIR alterado."""
    yield
    # Limpiar overrides que pudieron quedar y recargar una vez.
    for k in ("ORION_DATA_HOME",):
        os.environ.pop(k, None)
    _reload_config()
