"""orion.core.logger — Logging estructurado con structlog + correlation-id.

Reemplaza print() dispersos por un logger:
  - **Estructurado** via ``structlog`` — los kwargs se renderean como
    `key=value` en la línea.
  - **Compatible** con el stdlib logging — todo `log.info("msg", arg)`
    existente sigue funcionando porque usamos el ``stdlib.BoundLogger``
    bridge y el processor chain de structlog se aplica encima.
  - **Correlation-aware** — cada request HTTP setea un ``corr_id`` en
    el context (ver ``orion.core.correlation``) que aparece en cada log
    line de ese request. Permite ``grep corr_id=abc12345 logs/orion.log``
    para reconstruir un request entero.
  - **Secret-safe** — el ``_SecretFilter`` original (Fase 1) sigue
    activo como handler-level filter sobre el bridge a stdlib.

Uso:
    from orion.core.logger import get_logger
    log = get_logger(__name__)
    log.info("Mensaje informativo")
    log.warning("Algo no esperado")
    log.error("Fallo en operación", exc_info=True)

    # Idem con kwargs (structlog):
    log.info("note_created", note_id=42, pinned=True)
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import MutableMapping
from logging.handlers import RotatingFileHandler
from typing import Any

import structlog

from orion.config import BASE_DIR
from orion.core.correlation import get_correlation_id

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


def _redact(text: str) -> str:
    for pattern, repl in _SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


class _SecretFilter(logging.Filter):
    """Redacta secretos en el msg + args del LogRecord (stdlib side).

    Vive en los handlers stdlib (console + rotating file). El processor
    de structlog `_add_correlation_id` corre antes, así que cuando el
    record llega al handler ya tiene `corr_id=...` formateado en el msg
    final — y este filter sólo redacta lo que sea secreto en el texto
    final, sin tocar el correlation-id.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._maybe(v) for k, v in record.args.items()}
            else:
                record.args = tuple(self._maybe(a) for a in record.args)
        return True

    @staticmethod
    def _maybe(value: Any) -> Any:
        return _redact(value) if isinstance(value, str) else value


# ── structlog processor: inyectar correlation-id ────────────────────────
def _add_correlation_id(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Añade ``corr_id`` al event_dict si hay uno en el ContextVar.

    Default `"-"` se omite para no ensuciar logs fuera de requests.

    La firma respeta el ``Processor`` protocol de structlog (mypy lo
    valida vía el `list-item` de la lista `processors=`).
    """
    cid = get_correlation_id()
    if cid and cid != "-":
        event_dict["corr_id"] = cid
    return event_dict


# Formatters stdlib — se aplican DESPUÉS del processor chain de structlog,
# así que `%(message)s` ya contiene los kvs formateados (`event corr_id=ab12 …`).
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

    # ── Configurar el root stdlib logger (handlers + filter) ────────────
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

    # ── Configurar structlog para usar el bridge stdlib ────────────────
    # Los loggers que se obtienen via `get_logger()` son BoundLogger →
    # PrintLogger via stdlib. Los kvs se serializan con KeyValueRenderer
    # al campo `message` final que llega al handler stdlib.
    # OJO: NO agregamos `add_logger_name` ni `add_log_level` al chain —
    # los formatters stdlib (console/file de arriba) ya pintan `name` y
    # `levelname`. Si los agregáramos también acá, salen duplicados en
    # la línea (`[orion.x] INFO: [info ] msg [orion.x] ...`).
    #
    # El renderer KeyValueRenderer produce solo `event + kvs`:
    #   "msg corr_id=ab12 user=zahir"
    # que el formatter envuelve a:
    #   "[orion.x] INFO: msg corr_id=ab12 user=zahir"
    structlog.configure(
        processors=[
            # Filtra DEBUG cuando el root está en INFO (no se procesa lo que
            # no se va a escribir — ahorra CPU en hot loops como _watchdog).
            structlog.stdlib.filter_by_level,
            # Permite `log.info("Hi %s", "world")` estilo printf.
            structlog.stdlib.PositionalArgumentsFormatter(),
            # Inyecta corr_id si hay request activo (nuestro processor).
            _add_correlation_id,
            # Stack info / traceback si exc_info=True.
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # Renderer minimal: solo "event key1=val1 key2=val2".
            structlog.processors.KeyValueRenderer(
                key_order=["event"],
                sort_keys=True,
            ),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    """Devuelve un logger structlog wrappeado sobre stdlib.

    El nombre se prefija con ``orion.`` si no lo tiene, así todos los
    loggers heredan de la jerarquía ``orion.*`` que controlamos.

    El tipo de retorno es ``Any`` (en runtime es un
    ``structlog.stdlib.BoundLogger``) — devolver el tipo concreto
    obliga a mypy a importar structlog en cada consumer, y no aporta
    porque la API se mantiene 100% compatible con stdlib Logger.
    """
    setup_logging()
    if not name.startswith("orion."):
        name = f"orion.{name}"
    return structlog.stdlib.get_logger(name)
