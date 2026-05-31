"""
tests.test_packaging
=====================
Fase 6 — verificación del scaffolding de empaquetado nativo.

No requiere Rust ni PyInstaller instalados; solo valida que:
  - El spec de PyInstaller existe y parsea como Python.
  - tauri.conf.json es JSON válido y declara los campos clave.
  - Cargo.toml es TOML válido (parseo con tomllib stdlib en 3.11+).
  - src-tauri/src/main.rs existe y declara el sidecar correcto.
  - Los scripts de build existen y son ejecutables (shebang correcto).
  - requirements-dev.txt lista pyinstaller.

Si todo esto pasa, alguien con Rust + PyInstaller en su máquina puede
ejecutar ``scripts/build.{ps1,sh}`` y obtener un instalador.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── PyInstaller spec ────────────────────────────────────────────────────
def test_pyinstaller_spec_exists():
    spec = PROJECT_ROOT / "packaging" / "orion_backend.spec"
    assert spec.is_file(), "packaging/orion_backend.spec no existe"


def test_pyinstaller_spec_is_parsable_python():
    """No corremos el spec; solo verificamos que tiene sintaxis válida."""
    import ast
    spec = (PROJECT_ROOT / "packaging" / "orion_backend.spec").read_text(encoding="utf-8")
    ast.parse(spec)


def test_pyinstaller_spec_excludes_qt():
    spec = (PROJECT_ROOT / "packaging" / "orion_backend.spec").read_text(encoding="utf-8")
    # En modo web no queremos arrastrar Qt en el bundle.
    assert '"PyQt6"' in spec or "'PyQt6'" in spec, "El spec debe excluir PyQt6"


def test_pyinstaller_spec_includes_web_dist_as_data():
    spec = (PROJECT_ROOT / "packaging" / "orion_backend.spec").read_text(encoding="utf-8")
    assert "web" in spec and "dist" in spec, "El spec debe incluir web/dist como data"


# ── Tauri config ────────────────────────────────────────────────────────
def test_tauri_config_is_valid_json():
    cfg = PROJECT_ROOT / "src-tauri" / "tauri.conf.json"
    assert cfg.is_file(), "src-tauri/tauri.conf.json no existe"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    # Campos clave
    assert data["package"]["productName"] == "Orion"
    assert data["build"]["distDir"] == "../web/dist"
    assert "127.0.0.1:8765" in data["tauri"]["windows"][0]["url"]
    assert "binaries/orion-backend" in data["tauri"]["bundle"]["externalBin"]


def test_tauri_cargo_toml_valid():
    toml_path = PROJECT_ROOT / "src-tauri" / "Cargo.toml"
    assert toml_path.is_file()
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    assert data["package"]["name"] == "orion"
    assert data["package"]["edition"] == "2021"
    # Dependencias mínimas
    deps = data["dependencies"]
    assert "tauri" in deps
    tauri_dep = deps["tauri"]
    if isinstance(tauri_dep, dict):
        features = set(tauri_dep.get("features") or [])
        assert "shell-sidecar" in features, (
            "Tauri necesita feature shell-sidecar para spawnear el backend"
        )


def test_tauri_main_rs_exists_and_spawns_sidecar():
    main_rs = PROJECT_ROOT / "src-tauri" / "src" / "main.rs"
    assert main_rs.is_file()
    src = main_rs.read_text(encoding="utf-8")
    assert "new_sidecar" in src, "main.rs debe usar tauri ... new_sidecar"
    assert "orion-backend" in src, "main.rs debe referir al sidecar orion-backend"
    assert "127.0.0.1:8765" in src or "8765" in src, (
        "main.rs debe esperar al backend en :8765"
    )


def test_tauri_build_rs_calls_tauri_build():
    build_rs = PROJECT_ROOT / "src-tauri" / "build.rs"
    assert build_rs.is_file()
    assert "tauri_build::build()" in build_rs.read_text(encoding="utf-8")


def test_icons_readme_present():
    readme = PROJECT_ROOT / "src-tauri" / "icons" / "README.md"
    assert readme.is_file(), "Falta src-tauri/icons/README.md con instrucciones"


# ── Scripts de build ────────────────────────────────────────────────────
def test_windows_script_exists():
    s = PROJECT_ROOT / "scripts" / "build.ps1"
    assert s.is_file()
    content = s.read_text(encoding="utf-8")
    for token in ("npm run build", "PyInstaller", "cargo tauri build"):
        assert token in content, f"build.ps1 debe ejecutar {token}"


def test_unix_script_exists_and_has_shebang():
    s = PROJECT_ROOT / "scripts" / "build.sh"
    assert s.is_file()
    content = s.read_text(encoding="utf-8")
    assert content.startswith("#!/usr/bin/env bash"), "build.sh necesita shebang bash"
    for token in ("npm run build", "PyInstaller", "cargo tauri build"):
        assert token in content


# ── Dev requirements ────────────────────────────────────────────────────
def test_requirements_dev_lists_pyinstaller():
    req = PROJECT_ROOT / "requirements-dev.txt"
    assert req.is_file()
    assert "pyinstaller" in req.read_text(encoding="utf-8").lower()
