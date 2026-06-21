"""
utils.cache — Cache TTL ligero, thread-safe, para herramientas de O.R.I.O.N
============================================================================
Decorador `ttl_cache` que recuerda el resultado de una función durante un
tiempo determinado. Útil para evitar llamadas repetidas a APIs externas
(web_search, weather_report, etc.) cuando el usuario hace la misma consulta
varias veces en pocos minutos.

Uso:
    from orion.utils.cache import ttl_cache

    @ttl_cache(ttl_seconds=300, max_entries=128)
    def expensive_call(query: str) -> str:
        ...
"""

from __future__ import annotations

import functools
import hashlib
import json
import threading
import time
from collections.abc import Callable
from typing import Any
import contextlib


def _make_key(args: tuple, kwargs: dict) -> str:
    """Construye una clave estable para los argumentos.
    Usa JSON cuando se puede; si no, repr() como fallback. Hashea para
    mantener la clave compacta y comparable.
    """
    try:
        payload = json.dumps(
            {"a": args, "k": kwargs},
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
    except (TypeError, ValueError):
        payload = repr((args, kwargs))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


class _TTLEntry:
    __slots__ = ("expires_at", "value")

    def __init__(self, value: Any, expires_at: float):
        self.value = value
        self.expires_at = expires_at


def ttl_cache(
    ttl_seconds: int = 300,
    max_entries: int = 128,
    skip_if: Callable[[Any], bool] | None = None,
) -> Callable:
    """Decorador que cachea el resultado por `ttl_seconds`.

    Args:
        ttl_seconds : tiempo de vida de cada entrada (segundos).
        max_entries : tamaño máximo. Se evictan las más viejas (FIFO).
        skip_if     : función opcional aplicada al resultado; si retorna True
                       el resultado NO se guarda (ej. errores transitorios).
    """

    def decorator(func: Callable) -> Callable:
        store: dict[str, _TTLEntry] = {}
        order: list[str] = []  # FIFO de claves
        lock = threading.Lock()
        stats = {"hits": 0, "misses": 0}

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = _make_key(args, kwargs)
            now = time.time()

            with lock:
                entry = store.get(key)
                if entry is not None and entry.expires_at > now:
                    stats["hits"] += 1
                    return entry.value
                # expirada o ausente
                if entry is not None:
                    store.pop(key, None)
                    with contextlib.suppress(ValueError):
                        order.remove(key)

            # Llamada real (fuera del lock para no bloquear)
            result = func(*args, **kwargs)

            if skip_if is not None:
                try:
                    if skip_if(result):
                        return result
                except Exception:
                    pass

            with lock:
                stats["misses"] += 1
                store[key] = _TTLEntry(result, now + ttl_seconds)
                order.append(key)
                # Evict viejos si superamos el límite
                while len(order) > max_entries:
                    old = order.pop(0)
                    store.pop(old, None)

            return result

        def cache_clear() -> None:
            with lock:
                store.clear()
                order.clear()

        def cache_info() -> dict:
            with lock:
                return {
                    "size": len(store),
                    "hits": stats["hits"],
                    "misses": stats["misses"],
                    "ttl_s": ttl_seconds,
                    "max": max_entries,
                }

        wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
        wrapper.cache_info = cache_info  # type: ignore[attr-defined]
        return wrapper

    return decorator
