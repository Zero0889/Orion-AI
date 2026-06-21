"""server.routes.memory — Memoria largo plazo (CRUD).

Endpoints:
  GET    /api/memory                       → JSON completo
  GET    /api/memory/{category}            → solo esa categoría
  PUT    /api/memory/{category}/{key}      → upsert (body: {value})
  DELETE /api/memory/{category}/{key}      → borra

La lógica vive en :class:`~orion.services.memory_service.MemoryService`
(incluye validación de categoría + publicación del evento ``memory.updated``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from orion.services.memory_service import (
    CategoryNotFound,
    EntryNotFound,
    InvalidCategory,
    MemoryService,
)

router = APIRouter()


class MemoryEntry(BaseModel):
    value: str = Field(..., min_length=1, max_length=400)


def _service(request: Request) -> MemoryService:
    return MemoryService(bus=getattr(request.app.state, "bus", None))


@router.get("")
def get_all_memory(svc: MemoryService = Depends(_service)) -> dict:
    return svc.load_all()


@router.get("/{category}")
def get_memory_category(
    category: str,
    svc: MemoryService = Depends(_service),
) -> dict:
    try:
        return svc.load_category(category)
    except CategoryNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/{category}/{key}")
def put_memory_entry(
    category: str,
    key: str,
    body: MemoryEntry,
    svc: MemoryService = Depends(_service),
) -> dict:
    try:
        svc.upsert(category, key, body.value)
    except InvalidCategory as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "category": category, "key": key}


@router.delete("/{category}/{key}", status_code=204)
def delete_memory_entry(
    category: str,
    key: str,
    svc: MemoryService = Depends(_service),
) -> None:
    try:
        svc.delete(category, key)
    except InvalidCategory as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except EntryNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
