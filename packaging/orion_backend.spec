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
# detecta por análisis estático. Post Fase 2: todo bajo orion/.
hidden = []
for pkg in (
    "orion",
    "orion.server", "orion.server.routes",
    # Adapters por dominio (Fase 3 R5): system / google / web / iot.
    # `collect_submodules` es recursivo, así que listar el paquete padre
    # también funcionaría; los listamos explícitos para que el bundle no
    # arrastre por error subpkgs futuros que no queramos empacar.
    "orion.adapters",
    "orion.adapters.system",
    "orion.adapters.google", "orion.adapters.google.notifications",
    "orion.adapters.web",
    "orion.adapters.iot", "orion.adapters.iot.transports",
    "orion.agent", "orion.domain.memory", "orion.plugins", "orion.core",
    "orion.config", "orion.utils", "orion.storage",
):
    hidden += collect_submodules(pkg)

# google-genai a veces oculta submódulos en runtime.
hidden += collect_submodules("google.genai")
hidden += collect_submodules("google.api_core")

# ── Data files ──────────────────────────────────────────────────────────
# Las rutas-destino dentro del bundle conservan la estructura post Fase 2
# (orion/core/ y orion/plugins/) para que get_resources_dir() las resuelva
# con el mismo path que en dev.
datas = [
    # Prompt del sistema
    (str(ROOT / "orion" / "core" / "prompt.txt"),     "orion/core"),
    # Frontend compilado
    (str(ROOT / "web" / "dist"),                      "web/dist"),
    # Configs por defecto (templates — el usuario los completa).
    # `config/` queda en root, no bajo orion/ (es data, no código).
    (str(ROOT / "config" / "api_keys.example.json"),  "config"),
    (str(ROOT / "config" / "iot_config.json"),        "config"),
    (str(ROOT / "config" / "browser.json"),           "config"),
    (str(ROOT / "config" / "hotkeys.json"),           "config"),
    # Nota Fase 7: el asset github-logo.png se movió a web/public/ y va
    # dentro del bundle del frontend (web/dist/).
]

# ── Tools auxiliares (binarios externos) ────────────────────────────────
# Bundleamos `gog.exe` para que Gmail/Classroom/Drive/etc. funcionen out-
# of-the-box en el .exe distribuido, sin pedirle al usuario que baje
# binarios por separado. El runtime los busca en este orden:
#   1. BASE_DIR/tools/<name>/<bin>      (user-writable; upgrades manuales)
#   2. RESOURCES_DIR/tools/<name>/<bin> (esto — bundled, read-only)
#   3. PATH del sistema
#
# Excluidos a propósito:
#   - tools/gog/client_secret.json  (secreto OAuth del dev — el usuario
#                                    crea el suyo en GCP, ver docs/SETUP_GOOGLE_OAUTH.md)
#   - tools/classroom/token.json    (token del usuario)
#   - tools/__pycache__             (caché de Python)
#   - tools/*.py                    (scripts de testing del dev, no
#                                    necesarios en runtime)
_gog = ROOT / "tools" / "gog"
if (_gog / "gog.exe").exists():
    datas += [
        (str(_gog / "gog.exe"),      "tools/gog"),
    ]
    # LICENSE/README/CHANGELOG van para compliance + transparencia con
    # los usuarios. Tamaño insignificante.
    for _aux in ("LICENSE", "README.md", "CHANGELOG.md"):
        if (_gog / _aux).exists():
            datas.append((str(_gog / _aux), "tools/gog"))
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
    [str(ROOT / "orion" / "__main__.py")],
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
    a.binaries,
    a.datas,
    [],
    name="orion-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,        # mantiene logs visibles en stderr/stdout
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
