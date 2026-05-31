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
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR    = get_base_dir()
CONFIG_DIR  = BASE_DIR / "config"
MEMORY_DIR  = BASE_DIR / "memory"
CORE_DIR    = BASE_DIR / "core"
PLUGINS_DIR = BASE_DIR / "plugins"

API_CONFIG_PATH    = CONFIG_DIR / "api_keys.json"
BROWSER_CONFIG_PATH = CONFIG_DIR / "browser.json"
HOTKEYS_CONFIG_PATH = CONFIG_DIR / "hotkeys.json"
IOT_CONFIG_PATH    = CONFIG_DIR / "iot_config.json"
MEMORY_PATH        = MEMORY_DIR / "long_term.json"
PROMPT_PATH        = CORE_DIR / "prompt.txt"


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

def is_windows() -> bool: return get_os() == "windows"
def is_mac()     -> bool: return get_os() == "mac"
def is_linux()   -> bool: return get_os() == "linux"


# ── Modo de UI (Fase 5: switch web/qt/both) ─────────────────────────────────
#
# La variable de entorno ``ORION_UI`` tiene prioridad sobre el archivo de
# config. Valores admitidos:
#
#   - "qt"   : solo PyQt6 (modo legacy, sin backend web).
#   - "web"  : solo backend FastAPI + frontend React. Abre el navegador
#              automáticamente. NO carga PyQt6.
#   - "both" : ambos a la vez (default — comportamiento desde Fase 1).
#
# Cualquier otro valor cae a "both" con un warning silencioso.
_ENV_UI_MODE = "ORION_UI"
_VALID_UI_MODES = {"qt", "web", "both"}


def get_ui_mode() -> str:
    raw = (os.environ.get(_ENV_UI_MODE) or "").strip().lower()
    if not raw:
        raw = (load_config().get("ui_mode") or "both").strip().lower()
    return raw if raw in _VALID_UI_MODES else "both"
