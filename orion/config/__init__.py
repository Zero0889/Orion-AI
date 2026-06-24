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


def _user_data_home() -> Path:
    """Carpeta convencional por SO para state del usuario (writable).

    El override por env var ``ORION_DATA_HOME`` sirve para tests y para
    usuarios power que quieran portabilizar la instalación. Si está seteada
    se usa tal cual sin importar el SO.
    """
    env = os.environ.get("ORION_DATA_HOME", "").strip()
    if env:
        return Path(env).expanduser()
    if sys.platform == "win32":
        # %APPDATA% es C:\Users\<user>\AppData\Roaming en Windows. Caemos
        # a LOCALAPPDATA si por alguna razón APPDATA no está seteada (sí
        # pasa en algunas SKUs server o en cuentas de servicio).
        appdata = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if appdata:
            return Path(appdata) / "Orion"
        return Path.home() / "AppData" / "Roaming" / "Orion"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Orion"
    # Linux y otros Unix → XDG_DATA_HOME o ~/.local/share/orion.
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg:
        return Path(xdg) / "orion"
    return Path.home() / ".local" / "share" / "orion"


def get_base_dir() -> Path:
    """Raíz writable para config/state del usuario.

    * En **dev** (``python -m orion`` desde el repo) → project root, así
      seguimos leyendo/escribiendo ``config/`` y ``data/`` del repo. Esto
      mantiene el flujo de desarrollo sin cambios.
    * En **frozen** (PyInstaller bundle dentro del .exe instalado) →
      ``%APPDATA%\\Orion\\`` en Windows, equivalentes por SO en mac/linux.
      Esto evita escribir en ``Program Files`` (que es read-only sin elevar)
      y persiste config entre updates del .exe.

    El path se puede forzar siempre con la env var ``ORION_DATA_HOME``,
    útil para tests y portabilización.
    """
    if getattr(sys, "frozen", False):
        return _user_data_home()
    # Dev: respetar override si está seteado, sino project root.
    if os.environ.get("ORION_DATA_HOME"):
        return _user_data_home()
    return Path(__file__).resolve().parent.parent.parent


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
    return Path(__file__).resolve().parent.parent.parent


BASE_DIR = get_base_dir()
RESOURCES_DIR = get_resources_dir()
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"  # State runtime (SQLite, CSVs, legacy json exports).

# En frozen mode garantizamos que las carpetas existan. En dev ya están
# versionadas (config/ y data/ en el repo), así que mkdir es no-op.
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
# MEMORY_DIR queda como alias de DATA_DIR — antes apuntaba a ``memory/``
# que existía en root. Post Fase 2 el directorio se eliminó (los .py se
# fueron a orion/domain/memory/, los .json/.csv a data/). Mantener el
# alias evita romper los consumidores que aún lo importan.
MEMORY_DIR = DATA_DIR
# Bundled assets: viven dentro de orion/ (core/, plugins/ se movieron en
# Fase 2). En frozen mode PyInstaller los empaca según packaging/spec.
CORE_DIR = RESOURCES_DIR / "orion" / "core"
PLUGINS_DIR = RESOURCES_DIR / "orion" / "plugins"

API_CONFIG_PATH = CONFIG_DIR / "api_keys.json"
BROWSER_CONFIG_PATH = CONFIG_DIR / "browser.json"
HOTKEYS_CONFIG_PATH = CONFIG_DIR / "hotkeys.json"
IOT_CONFIG_PATH = CONFIG_DIR / "iot_config.json"
MEMORY_PATH = DATA_DIR / "long_term.json"  # Legacy — backend ya usa SQLite (Fase 3B).
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


def has_valid_api_key() -> bool:
    """¿Hay una API key utilizable? — usado por el onboarding para decidir
    si mostrar el wizard. NO raise: silencioso por diseño.

    Acepta tanto la env var como el archivo. Considera válida cualquier
    string no-vacía — la validación real (HTTP 200 contra Gemini) corre
    en el endpoint ``/api/onboarding/save``.
    """
    if os.environ.get(_ENV_KEY_NAME, "").strip():
        return True
    cfg = load_config()
    return bool(cfg.get("gemini_api_key", "").strip())


def seed_default_configs() -> list[Path]:
    """Copia los templates ``*.example.json`` empacados a CONFIG_DIR si no
    existen aún sus contrapartes reales. Devuelve la lista de archivos
    creados (vacía si no hizo nada).

    Diseño: solo copia los archivos *no-secretos* (los que la app espera
    en disco para arrancar sin crashear). ``api_keys.json`` queda fuera
    deliberadamente — esa la pide el wizard de onboarding al usuario.
    """
    created: list[Path] = []
    # (template_name_in_resources, destination_name_in_config)
    pairs = [
        ("api_keys.example.json", "api_keys.example.json"),
        ("iot_config.json", "iot_config.json"),
        ("browser.json", "browser.json"),
        ("hotkeys.json", "hotkeys.json"),
    ]
    src_root = RESOURCES_DIR / "config"
    for src_name, dst_name in pairs:
        src = src_root / src_name
        dst = CONFIG_DIR / dst_name
        if dst.exists() or not src.exists():
            continue
        try:
            dst.write_bytes(src.read_bytes())
            created.append(dst)
        except OSError:
            # Si el seed falla seguimos — el onboarding va a detectar y
            # remediar (al menos para api_keys.json).
            continue
    return created


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
