"""
core.logger — Logging centralizado de O.R.I.O.N
================================================
Reemplaza print() dispersos por un logger estructurado con niveles,
formato consistente y rotación automática de archivos.

Uso:
    from core.logger import get_logger
    log = get_logger(__name__)
    log.info("Mensaje informativo")
    log.warning("Algo no esperado")
    log.error("Fallo en operación", exc_info=True)
"""

import logging
import re
import sys
from logging.handlers import RotatingFileHandler

from config import BASE_DIR

_LOG_DIR = BASE_DIR / "logs"
_LOG_FILE = _LOG_DIR / "orion.log"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 3
_INITIALIZED = False


def _ensure_log_dir() -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


# ── Enmascaramiento de secretos ─────────────────────────────────────────────
# Defensa en profundidad: hoy no loggeamos keys a propósito, pero un futuro
# `log.error("Request fallida: %s", req_body)` o un traceback de google-genai
# puede arrastrar la key en el payload. Este filter las redacta antes de que
# lleguen al disco o a la consola.
#
# Cubre los formatos más comunes:
#   - Google:   AIzaSy[A-Za-z0-9_-]{33}
#   - OpenAI:   sk-[A-Za-z0-9]{20,}
#   - OpenRouter: sk-or-v1-[A-Za-z0-9]{40,}
#   - Anthropic: sk-ant-[A-Za-z0-9-]{90,}
#   - Bearer / Authorization headers
#   - JWT-like (xxx.yyy.zzz con base64)
_SECRET_PATTERNS = [
    (re.compile(r"AIzaSy[A-Za-z0-9_-]{33}"), "AIzaSy<redacted>"),
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), "sk-ant-<redacted>"),
    (re.compile(r"sk-or-v1-[A-Za-z0-9_-]{20,}"), "sk-or-v1-<redacted>"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "sk-<redacted>"),
    (re.compile(r"(?i)(authorization:\s*bearer\s+)\S+"), r"\1<redacted>"),
    (re.compile(r"(?i)(\"api[_-]?key\"\s*:\s*\")[^\"]+"), r"\1<redacted>"),
    (re.compile(r"(?i)(api[_-]?key=)[^\s&]+"), r"\1<redacted>"),
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), "<jwt-redacted>"),
]


class _SecretFilter(logging.Filter):
    """Redacta secretos en el `msg` y en cualquier arg que sea str."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._maybe_redact(v) for k, v in record.args.items()}
            else:
                record.args = tuple(self._maybe_redact(a) for a in record.args)
        return True

    @staticmethod
    def _maybe_redact(value):
        return _SecretFilter._redact(value) if isinstance(value, str) else value

    @staticmethod
    def _redact(text: str) -> str:
        for pattern, repl in _SECRET_PATTERNS:
            text = pattern.sub(repl, text)
        return text


_CONSOLE_FMT = logging.Formatter(
    fmt="[%(name)s] %(levelname)s: %(message)s",
)

_FILE_FMT = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def setup_logging(level: int = logging.INFO) -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    _ensure_log_dir()

    root = logging.getLogger("orion")
    root.setLevel(level)

    secret_filter = _SecretFilter()

    if not root.handlers:
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(level)
        console.setFormatter(_CONSOLE_FMT)
        console.addFilter(secret_filter)
        root.addHandler(console)

        try:
            file_h = RotatingFileHandler(
                str(_LOG_FILE),
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_h.setLevel(logging.DEBUG)
            file_h.setFormatter(_FILE_FMT)
            file_h.addFilter(secret_filter)
            root.addHandler(file_h)
        except OSError:
            root.warning("No se pudo crear el archivo de log: %s", _LOG_FILE)


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    if not name.startswith("orion."):
        name = f"orion.{name}"
    return logging.getLogger(name)
