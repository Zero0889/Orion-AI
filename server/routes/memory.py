"""
server.routes.memory — Memoria largo plazo (CRUD en Fase 3)
=============================================================
Endpoints:
  GET    /api/memory                       → JSON completo
  GET    /api/memory/{category}            → solo esa categoría
  PUT    /api/memory/{category}/{key}      → upsert (body: {value})
  DELETE /api/memory/{category}/{key}      → borra

Cada mutación publica ``memory.updated`` en el bus para que la UI Qt
y los clientes WS refresquen sin polling.

Categorías válidas (definidas en :mod:`memory.memory_manager`):
  identity | preferences | projects | relationships | wishes | notes
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.logger import get_logger
from memory.memory_manager import forget, load_memory, remember

log = get_logger("server.routes.memory")
router = APIRouter()

VALID_CATEGORIES = {
    "identity",
    "preferences",
    "projects",
    "relationships",
    "wishes",
    "notes",
}


class MemoryEntry(BaseModel):
    value: str = Field(..., min_length=1, max_length=400)


@router.get("")
def get_all_memory() -> dict:
    return load_memory()


@router.get("/{category}")
def get_memory_category(category: str) -> dict:
    mem = load_memory()
    if category not in mem:
        raise HTTPException(status_code=404, detail=f"Categoría '{category}' no existe")
    return {category: mem[category]}


@router.put("/{category}/{key}")
def put_memory_entry(
    category: str,
    key: str,
    body: MemoryEntry,
    request: Request,
) -> dict:
    if category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Categoría inválida. Usa una de: {sorted(VALID_CATEGORIES)}",
        )
    remember(key, body.value, category=category)
    _publish_change(request, "upserted", category=category, key=key, value=body.value)
    return {"ok": True, "category": category, "key": key}


@router.delete("/{category}/{key}", status_code=204)
def delete_memory_entry(category: str, key: str, request: Request) -> None:
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail="Categoría inválida")
    mem = load_memory()
    if key not in mem.get(category, {}):
        raise HTTPException(status_code=404, detail=f"Entrada '{category}/{key}' no existe")
    forget(key, category=category)
    _publish_change(request, "deleted", category=category, key=key, value=None)


# ── helpers ─────────────────────────────────────────────────────────────
def _publish_change(
    request: Request,
    op: str,
    *,
    category: str,
    key: str,
    value: str | None,
) -> None:
    bus = getattr(request.app.state, "bus", None)
    if bus is None:
        return
    try:
        bus.publish(
            "memory.updated",
            {
                "op": op,
                "category": category,
                "key": key,
                "value": value,
            },
        )
    except Exception as e:
        log.debug("publish memory.updated falló: %s", e)
