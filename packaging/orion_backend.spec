# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — backend headless de O.R.I.O.N (Fase 6).

Objetivo
--------
Generar un binario portable de Orion que arranca en modo web puro
(ORION_UI=web) y sirve la UI desde web/dist/. Pensado para usarse como
sidecar de Tauri, pero también funciona standalone.

Build
-----
Desde la raíz del repo:

    pyinstaller packaging/orion_backend.spec --clean --noconfirm

El binario sale en ``dist/orion-backend/`` (modo onefile + carpeta de
data en ``dist/orion-backend/``). Para Tauri renombrarlo según el
target-triple (ver scripts/build.*).

Notas
-----
- ORION_UI se fija a "web" como variable de entorno en main; lo
  enforce-amos también desde el runner del sidecar Tauri para no depender
  del entorno del usuario.
- Excluimos PyQt6, tkinter, matplotlib (los dos primeros son la UI
  legacy; matplotlib solo lo usa latex_render.py que es Qt-only).
- Plugins se cargan vía importlib en runtime → necesitan
  ``--collect-submodules plugins`` para que entren en el bundle.
- web/dist/ se copia tal cual al bundle; el server.app lo monta al
  arrancar (ver server/app.py:build_app).
"""

from PyInstaller.utils.hooks import (
    collect_data_files, collect_submodules,
)
from pathlib import Path

ROOT = Path(SPECPATH).parent.resolve()  # noqa: F821 (SPECPATH lo inyecta PyInstaller)

# ── Hidden imports ──────────────────────────────────────────────────────
# Submódulos cargados dinámicamente (importlib) o que PyInstaller no
# detecta por análisis estático.
hidden = []
for pkg in (
    "server", "server.routes",
    "actions", "actions.iot", "actions.iot.transports",
    "agent", "memory", "plugins", "core", "config", "utils", "tools",
):
    hidden += collect_submodules(pkg)

# google-genai a veces oculta submódulos en runtime.
hidden += collect_submodules("google.genai")
hidden += collect_submodules("google.api_core")

# ── Data files ──────────────────────────────────────────────────────────
datas = [
    # Prompt del sistema
    (str(ROOT / "core" / "prompt.txt"),         "core"),
    # Frontend compilado
    (str(ROOT / "web" / "dist"),                "web/dist"),
    # Configs por defecto (templates — el usuario los completa)
    (str(ROOT / "config" / "api_keys.example.json"),  "config"),
    (str(ROOT / "config" / "iot_config.json"),        "config"),
    (str(ROOT / "config" / "browser.json"),           "config"),
    (str(ROOT / "config" / "hotkeys.json"),           "config"),
    (str(ROOT / "config" / "theme.json"),             "config"),
    # Asset usado por la UI Qt (por si el bundle se reutiliza para
    # modo "both"; en modo "web" no se necesita pero pesa poco).
    (str(ROOT / "assets" / "github-logo.png"),  "assets"),
]
# Algunos paquetes (google-genai, opencv, etc.) traen sus propios data.
for pkg in ("google.genai", "google.api_core"):
    datas += collect_data_files(pkg)

# ── Excludes (slim) ─────────────────────────────────────────────────────
excludes = [
    "PyQt6",        # web mode no necesita la UI Qt
    "PyQt5",
    "PySide6", "PySide2",
    "tkinter",
    "matplotlib",   # solo lo usa latex_render.py (Qt)
    "IPython", "jupyter",
    "pytest",       # test framework
]

# ── Analysis ────────────────────────────────────────────────────────────
a = Analysis(  # noqa: F821
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="orion-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,        # mantiene logs visibles en stderr/stdout
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="orion-backend",
)
