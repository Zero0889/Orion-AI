"""
server.access_auth — shared-secret para el endpoint `/api/access/event`
======================================================================
El ESP32 vive en la LAN, no en loopback ni en Tailscale. El
``SharingMiddleware`` por defecto le devolvería 403. Este módulo le da
un bypass *autenticado*: si el POST trae el header
``X-Orion-Access-Token`` con el valor de ``config/access.json``, el
middleware lo deja pasar; cualquier otra request al mismo endpoint
sigue las reglas normales de filtrado por IP.

El secreto se compara en tiempo constante (``hmac.compare_digest``)
para no filtrar info por side-channel timing.
"""

from __future__ import annotations

import hmac
import json
import logging
import threading
from pathlib import Path

from orion.config import CONFIG_DIR

log = logging.getLogger("orion.access_auth")

ACCESS_CONFIG_PATH: Path = CONFIG_DIR / "access.json"

# Solo este path queda bypaseable por shared-secret. Si en el futuro
# agregamos más (ej. /api/access/heartbeat), van acá.
AUTHED_PATHS: frozenset[str] = frozenset({"/api/access/event"})

# Header donde el ESP32 manda el token. Case-insensitive en HTTP, pero
# guardamos la versión lowercase porque scope["headers"] de ASGI siempre
# llega en bytes lowercase.
TOKEN_HEADER_NAME: bytes = b"x-orion-access-token"

_state_lock = threading.Lock()
_cached_secret: str | None = None
_cached_mtime: float | None = None


def _load_secret_from_disk() -> str | None:
    """Lee el secreto del JSON. Devuelve ``None`` si falta o está vacío."""
    try:
        raw = ACCESS_CONFIG_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as e:
        log.warning("No pude leer %s: %s", ACCESS_CONFIG_PATH, e)
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning("config/access.json malformado: %s", e)
        return None

    secret = data.get("shared_secret")
    if not isinstance(secret, str) or not secret.strip():
        return None
    return secret.strip()


def get_secret() -> str | None:
    """Devuelve el secreto cacheado. Re-lee del disco si el archivo cambió
    (hot-reload sin reiniciar el server).

    ``None`` significa "no hay secreto configurado" → el bypass queda
    deshabilitado y el endpoint solo responde a loopback/Tailscale.
    """
    global _cached_secret, _cached_mtime
    try:
        mtime = ACCESS_CONFIG_PATH.stat().st_mtime
    except FileNotFoundError:
        with _state_lock:
            _cached_secret = None
            _cached_mtime = None
        return None
    except OSError:
        return _cached_secret

    with _state_lock:
        if _cached_mtime == mtime:
            return _cached_secret
        _cached_secret = _load_secret_from_disk()
        _cached_mtime = mtime
        return _cached_secret


def is_authed_request(scope: dict) -> bool:
    """Determina si el ASGI scope corresponde a una request autenticada por
    shared-secret. Devuelve True solo si:

    1. Es HTTP POST.
    2. El path está en ``AUTHED_PATHS``.
    3. Trae el header ``X-Orion-Access-Token`` con el valor exacto del
       config (comparación en tiempo constante).
    """
    if scope.get("type") != "http":
        return False
    if scope.get("method", "").upper() != "POST":
        return False
    if scope.get("path") not in AUTHED_PATHS:
        return False

    expected = get_secret()
    if not expected:
        # No hay secreto configurado → no se puede autenticar.
        return False

    headers = scope.get("headers") or ()
    provided: bytes | None = None
    for raw_name, raw_value in headers:
        if raw_name == TOKEN_HEADER_NAME:
            provided = raw_value
            break

    if provided is None:
        return False

    try:
        provided_str = provided.decode("ascii")
    except UnicodeDecodeError:
        return False

    return hmac.compare_digest(provided_str, expected)
