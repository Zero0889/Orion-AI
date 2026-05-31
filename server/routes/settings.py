"""
server.routes.settings — Configuración (solo lectura en Fase 1)
================================================================
Endpoints:
  GET /api/settings/theme         → { name, theme, available: [...] }

Usa :mod:`config.theme_tokens` (fachada headless, sin Qt) — ver R-21 de
la auditoría pre-Fase 0.
"""

from __future__ import annotations

from fastapi import APIRouter

from config.theme_tokens import (
    DEFAULT_THEME, get_theme, list_themes, load_theme_name,
)

router = APIRouter()


@router.get("/theme")
async def get_theme_endpoint() -> dict:
    """Tema activo + paleta resuelta + lista de disponibles."""
    name = load_theme_name() or DEFAULT_THEME
    return {
        "name":      name,
        "theme":     get_theme(name),
        "available": [{"id": tid, "name": tname} for tid, tname in list_themes()],
    }
