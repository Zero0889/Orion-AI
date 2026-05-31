"""
server.routes.memory — Memoria largo plazo (solo lectura en Fase 1)
====================================================================
Endpoints:
  GET /api/memory               → JSON completo de long_term.json
  GET /api/memory/{category}    → sólo esa categoría

La estructura del JSON está definida en :mod:`memory.memory_manager`:

    {
        "identity":      { "key": {"value": "..."} , ... },
        "preferences":   { ... },
        "projects":      { ... },
        "relationships": { ... },
        "wishes":        { ... },
        "notes":         { ... },
    }
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from memory.memory_manager import load_memory

router = APIRouter()


@router.get("")
async def get_all_memory() -> dict:
    """Devuelve la memoria de largo plazo completa."""
    return load_memory()


@router.get("/{category}")
async def get_memory_category(category: str) -> dict:
    mem = load_memory()
    if category not in mem:
        raise HTTPException(status_code=404, detail=f"Categoría '{category}' no existe")
    return {category: mem[category]}
