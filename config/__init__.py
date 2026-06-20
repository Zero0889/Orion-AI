"""
config — Módulo central de configuración de O.R.I.O.N
=====================================================
Provee: rutas base, carga de API key (env var > archivo),
helpers de OS, y acceso a configuración general.
"""

import json
import os
import sys
from pathlib import Path

# ── Ruta base del proyecto ──────────────────────────────────────────────────


def get_base_dir() -> Path:
    """User-writable root (config, memory). Next to exe in frozen mode."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def get_resources_dir() -> Path:
    """Read-only bundled assets (web/dist, prompt.txt, plugins).

    En PyInstaller onefile las datas se extraen a ``sys._MEIPASS``,
    no junto al exe. Para que el server encuentre el frontend
    compilado hay que apuntar ahí.
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
RESOURCES_DIR = get_resources_dir()
CONFIG_DIR = BASE_DIR / "config"
MEMORY_DIR = BASE_DIR / "memory"
DATA_DIR = (
    BASE_DIR / "data"
)  # State runtime (SQLite). Separate from config/ (schema) and memory/ (modules+legacy json).
CORE_DIR = RESOURCES_DIR / "core"
PLUGINS_DIR = RESOURCES_DIR / "plugins"

API_CONFIG_PATH = CONFIG_DIR / "api_keys.json"
BROWSER_CONFIG_PATH = CONFIG_DIR / "browser.json"
HOTKEYS_CONFIG_PATH = CONFIG_DIR / "hotkeys.json"
IOT_CONFIG_PATH = CONFIG_DIR / "iot_config.json"
MEMORY_PATH = MEMORY_DIR / "long_term.json"
PROMPT_PATH = CORE_DIR / "prompt.txt"
SQLITE_DB_PATH = DATA_DIR / "orion.sqlite"  # Fase 3B: state migrado a SQLite


# Carpetas de runtime overridables por env var. PROJECTS_DIR la usa
# ``actions/dev_agent.py`` para clonar/scaffold proyectos generados por el
# Coder; UPLOADS_DIR la usa ``server/routes/files.py`` para drop-zone.
# Defaults pensados para Windows + OneDrive sin asumir que Desktop existe.
def _default_projects_dir() -> Path:
    env = os.environ.get("ORION_PROJECTS_DIR", "").strip()
    if env:
        return Path(env)
    desktop = Path.home() / "Desktop"
    if desktop.exists():
        return desktop / "OrionProjects"
    return BASE_DIR / "projects"


PROJECTS_DIR = _default_projects_dir()
UPLOADS_DIR = Path(os.environ.get("ORION_UPLOADS_DIR", "").strip() or (BASE_DIR / "uploads"))


# ── Carga de configuración ──────────────────────────────────────────────────


def load_config() -> dict:
    if not API_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    API_CONFIG_PATH.write_text(
        json.dumps(data, indent=4, ensure_ascii=False),
        encoding="utf-8",
    )


# ── API Key (env var ORION_GEMINI_KEY tiene prioridad) ──────────────────────

_ENV_KEY_NAME = "ORION_GEMINI_KEY"


def get_api_key() -> str:
    env_key = os.environ.get(_ENV_KEY_NAME, "").strip()
    if env_key:
        return env_key

    cfg = load_config()
    key = cfg.get("gemini_api_key", "").strip()
    if not key:
        raise RuntimeError(
            f"No se encontró API key de Gemini. "
            f"Define la variable de entorno {_ENV_KEY_NAME} o "
            f"configúrala en {API_CONFIG_PATH}."
        )
    return key


# ── OS helpers ──────────────────────────────────────────────────────────────


def get_os() -> str:
    return load_config().get("os_system", "windows").lower()


def is_windows() -> bool:
    return get_os() == "windows"


def is_mac() -> bool:
    return get_os() == "mac"


def is_linux() -> bool:
    return get_os() == "linux"


# Nota Fase 7: la antigua función ``get_ui_mode()`` se eliminó al
# completarse la migración web. Orion ahora es web-only — la UI vive en
# ``web/`` y se sirve desde FastAPI. La variable de entorno
# ``ORION_NO_BROWSER`` sigue siendo útil (Tauri / sidecar la usan para
# no abrir el navegador del sistema).
