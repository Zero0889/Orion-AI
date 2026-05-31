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

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from config.theme_tokens import (
    DEFAULT_THEME, THEMES, get_theme, list_themes, load_theme_name,
    save_theme_name,
)

router = APIRouter()


class ThemePatch(BaseModel):
    name: str = Field(..., min_length=1)


@router.get("/theme")
async def get_theme_endpoint() -> dict:
    name = load_theme_name() or DEFAULT_THEME
    return {
        "name":      name,
        "theme":     get_theme(name),
        "available": [{"id": tid, "name": tname} for tid, tname in list_themes()],
    }


@router.patch("/theme")
async def patch_theme(body: ThemePatch, request: Request) -> dict:
    if body.name not in THEMES:
        raise HTTPException(
            status_code=400,
            detail=f"Tema '{body.name}' no existe. Disponibles: {sorted(THEMES.keys())}",
        )
    save_theme_name(body.name)
    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        try:
            bus.publish("settings.theme", {
                "name":  body.name,
                "theme": get_theme(body.name),
            })
        except Exception:
            pass
    return {"ok": True, "name": body.name, "theme": get_theme(body.name)}
