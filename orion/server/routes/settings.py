"""
server.routes.settings — Configuración
========================================
Endpoints:
  GET    /api/settings/theme              → { name, theme, available: [...] }
  PATCH  /api/settings/theme              → { name } cambia el tema activo

Usa :mod:`config.theme_tokens` (fachada headless, sin Qt) — ver R-21 de
la auditoría pre-Fase 0. La UI Qt reacciona al cambio vía su propio
``theme_bus`` (se recargará al reiniciar; el evento WS notifica al
frontend para repintar en caliente).
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from orion.config import (
    API_CONFIG_PATH,
)
from orion.config import (
    load_config as load_api_config,
)
from orion.config import (
    save_config as save_api_config,
)
from orion.config.theme_tokens import (
    DEFAULT_THEME,
    THEMES,
    get_theme,
    list_themes,
    load_theme_name,
    save_theme_name,
)
import contextlib

router = APIRouter()


class ThemePatch(BaseModel):
    name: str = Field(..., min_length=1)


# Handlers con I/O sincrónico (load_theme_name, load_api_config) van como
# `def` para que FastAPI los despache al threadpool y no bloqueen el loop.


@router.get("/theme")
def get_theme_endpoint() -> dict:
    name = load_theme_name() or DEFAULT_THEME
    return {
        "name": name,
        "theme": get_theme(name),
        "available": [{"id": tid, "name": tname} for tid, tname in list_themes()],
    }


class ApiKeyBody(BaseModel):
    key: str = Field(..., min_length=10, max_length=400)


@router.get("/api_key")
def get_api_key_status() -> dict:
    """No expone la key, sólo si está configurada (en env var o archivo).

    Esto es lo que el wizard del frontend usa para decidir si mostrarse
    o no.
    """
    env_key = (os.environ.get("ORION_GEMINI_KEY") or "").strip()
    cfg = load_api_config()
    file_key = (cfg.get("gemini_api_key") or "").strip()
    configured = bool(env_key or file_key)
    return {
        "configured": configured,
        "source": "env" if env_key else ("file" if file_key else None),
        "path": str(API_CONFIG_PATH) if not env_key else None,
    }


@router.post("/api_key")
def set_api_key(body: ApiKeyBody, request: Request) -> dict:
    """Guarda la API key de Gemini en ``config/api_keys.json``.

    Si la key entra por env var ``ORION_GEMINI_KEY`` siempre toma
    prioridad sobre el archivo (ver :func:`config.get_api_key`).
    Después de guardar emite ``system.ready`` por el bus para
    desbloquear ``wait_for_api_key`` y notificar a la UI.
    """
    key = body.key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="API key vacía")

    cfg = load_api_config()
    cfg["gemini_api_key"] = key
    cfg.setdefault("os_system", "windows")
    save_api_config(cfg)

    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        with contextlib.suppress(Exception):
            bus.mark_ready()

    return {"ok": True, "configured": True}


class SharingBody(BaseModel):
    enabled: bool


@router.get("/sharing")
def get_sharing_endpoint() -> dict:
    """Devuelve el estado del toggle 'Compartir vía Tailscale' + la IP
    Tailscale detectada (si está) para mostrarla en la UI."""
    from orion.server.sharing import detect_tailscale_ip, get_sharing

    return {
        "enabled": get_sharing(),
        "tailscale_ip": detect_tailscale_ip(),
        "port": 8765,
    }


@router.post("/sharing")
def post_sharing_endpoint(body: SharingBody, request: Request) -> dict:
    """Activa/desactiva el filtro de IP. Persiste en config/sharing.json
    y notifica via bus (settings.sharing) para que el frontend re-renderice."""
    from orion.server.sharing import detect_tailscale_ip, set_sharing

    enabled = set_sharing(body.enabled)
    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        with contextlib.suppress(Exception):
            bus.publish("settings.sharing", {"enabled": enabled})
    return {
        "ok": True,
        "enabled": enabled,
        "tailscale_ip": detect_tailscale_ip(),
        "port": 8765,
    }


@router.patch("/theme")
def patch_theme(body: ThemePatch, request: Request) -> dict:
    if body.name not in THEMES:
        raise HTTPException(
            status_code=400,
            detail=f"Tema '{body.name}' no existe. Disponibles: {sorted(THEMES.keys())}",
        )
    save_theme_name(body.name)
    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        with contextlib.suppress(Exception):
            bus.publish(
                "settings.theme",
                {
                    "name": body.name,
                    "theme": get_theme(body.name),
                },
            )
    return {"ok": True, "name": body.name, "theme": get_theme(body.name)}
