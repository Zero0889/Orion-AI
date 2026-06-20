"""
server — Backend web (FastAPI + WebSocket) de O.R.I.O.N
========================================================
Paquete introducido en la Fase 0 de la migración a React/Tauri.

Estructura prevista
-------------------
- :mod:`server.event_bus` — OrionEventBus: reemplazo drop-in de OrionUI.
- (Fase 1) ``server.app``        — FastAPI app + montaje de /dist.
- (Fase 1) ``server.ws``         — hub de WebSockets.
- (Fase 1) ``server.routes.*``   — endpoints REST.

NO importar PyQt6 ni nada de :mod:`ui` / :mod:`ui_components` desde
este paquete. La regla está validada en :mod:`tests.test_event_bus_contract`.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from config import BASE_DIR

# ── Sanitización de mensajes de error (I-07) ─────────────────────────────
# Antes de devolver un str(e) al cliente, le quitamos:
#   - rutas absolutas (BASE_DIR del proyecto, HOME, OneDrive)
#   - el nombre de usuario en C:\Users\<x>\... / /home/<x>/...
# Los logs del server siguen viendo el mensaje original (con traza completa).
# El frontend solo ve la versión saneada.

_HOME = str(Path.home())
_BASE = str(BASE_DIR)
_ONEDRIVE = (os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer") or "").strip()

_USER_RE = re.compile(r"([A-Za-z]:\\Users\\|/(?:home|Users)/)[^\\/\s\"']+", re.IGNORECASE)


def safe_error_detail(exc: BaseException | str, *, fallback: str = "Error interno") -> str:
    """Devuelve una versión del error sin paths absolutos ni nombres de
    usuario. Pensada para usarse en ``HTTPException(detail=...)`` sin
    leakear info del filesystem.

    Ejemplo: ``"No such file: C:\\Users\\zahir\\config\\x.json"``
            → ``"No such file: <user>\\config\\x.json"``
    """
    msg = str(exc).strip()
    if not msg:
        return fallback
    if _BASE:
        msg = msg.replace(_BASE, "<orion>")
    if _ONEDRIVE:
        msg = msg.replace(_ONEDRIVE, "<onedrive>")
    if _HOME:
        msg = msg.replace(_HOME, "<home>")
    msg = _USER_RE.sub("<user>", msg)
    # Tope: cualquier error largo a 250 chars para no devolver tracebacks.
    if len(msg) > 250:
        msg = msg[:247] + "…"
    return msg
