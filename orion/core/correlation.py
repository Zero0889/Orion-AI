"""orion.core.correlation — Correlation ID por request.

ContextVar que vive en el async context (request HTTP, task de
TaskGroup, etc). El middleware del server (FastAPI) lo setea al
entrar al request handler y lo limpia al salir. El logger lo lee y
lo agrega como kv a cada log line, así un grep `corr_id=abc123` da
todos los logs del mismo request.

Lo aceptan tanto chains async como threads — ``ContextVar`` es seguro
en ambos contextos (cada thread tiene su copia, y dentro del thread
``run_coroutine_threadsafe`` propaga el valor al loop destino).

API:
  - :func:`set_correlation_id` — set explícito (middleware lo usa).
  - :func:`get_correlation_id` — lee el actual; devuelve "-" si no hay.
  - :func:`new_correlation_id` — genera + setea un UUIDv4 corto.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_NO_CORR = "-"

# Default = "-" para que los logs fuera de un request (background
# tasks, arranque, etc.) se vean limpios sin ID inventado.
_correlation_id: ContextVar[str] = ContextVar("orion_correlation_id", default=_NO_CORR)


def get_correlation_id() -> str:
    return _correlation_id.get()


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value or _NO_CORR)


def new_correlation_id() -> str:
    """Genera un nuevo correlation-id (8 chars hex), lo setea y lo devuelve."""
    cid = uuid.uuid4().hex[:8]
    _correlation_id.set(cid)
    return cid


def clear_correlation_id() -> None:
    _correlation_id.set(_NO_CORR)
