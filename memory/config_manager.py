"""
config_manager — Wrapper de compatibilidad sobre config central.
"""

from config import (
    API_CONFIG_PATH as CONFIG_FILE,
)
from config import (
    CONFIG_DIR,
    get_api_key,
    load_config,
    save_config,
)


def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def config_exists() -> bool:
    return CONFIG_FILE.exists()


def save_api_keys(gemini_api_key: str) -> None:
    ensure_config_dir()
    data = load_config()
    data["gemini_api_key"] = gemini_api_key.strip()
    save_config(data)


def load_api_keys() -> dict:
    return load_config()


def get_gemini_key() -> str | None:
    try:
        return get_api_key()
    except RuntimeError:
        return None


def is_configured() -> bool:
    key = get_gemini_key()
    return bool(key and len(key) > 15)
