"""
server.routes.notes — Notas rápidas (solo lectura en Fase 1)
=============================================================
Endpoints:
  GET /api/notes        → lista completa de notas rápidas
  GET /api/notes/count  → cuántas notas hay
"""

from __future__ import annotations

from fastapi import APIRouter

from memory.quick_notes import count_notes, list_notes

router = APIRouter()


@router.get("")
async def get_notes() -> list[dict]:
    return list_notes()


@router.get("/count")
async def get_notes_count() -> dict:
    return {"count": count_notes()}
