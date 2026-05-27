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
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import BASE_DIR

_LOG_DIR  = BASE_DIR / "logs"
_LOG_FILE = _LOG_DIR / "orion.log"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 3
_INITIALIZED = False


def _ensure_log_dir() -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


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

    if not root.handlers:
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(level)
        console.setFormatter(_CONSOLE_FMT)
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
            root.addHandler(file_h)
        except OSError:
            root.warning("No se pudo crear el archivo de log: %s", _LOG_FILE)


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    if not name.startswith("orion."):
        name = f"orion.{name}"
    return logging.getLogger(name)
