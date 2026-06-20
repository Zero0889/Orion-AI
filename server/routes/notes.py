"""
server.routes.notes — Notas rápidas (CRUD en Fase 3)
=====================================================
Endpoints:
  GET    /api/notes              → lista completa
  GET    /api/notes/count        → cuántas
  POST   /api/notes              → crea {text, pinned?, color?}
  PATCH  /api/notes/{id}         → actualiza {text?, pinned?, color?}
  DELETE /api/notes/{id}         → borra

Cada mutación publica ``note.changed`` en el bus para que la UI Qt y
los clientes WS refresquen sin polling.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.logger import get_logger
from memory.quick_notes import (
    add_note,
    count_notes,
    delete_note,
    list_notes,
    update_note,
)

log = get_logger("server.routes.notes")
router = APIRouter()


class NoteCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    pinned: bool = False
    color: str | None = None


class NoteUpdate(BaseModel):
    text: str | None = Field(default=None, max_length=4000)
    pinned: bool | None = None
    color: str | None = None


@router.get("")
def get_notes() -> list[dict]:
    return list_notes()


@router.get("/count")
def get_notes_count() -> dict:
    return {"count": count_notes()}


@router.post("", status_code=201)
def create_note(body: NoteCreate, request: Request) -> dict:
    n = add_note(body.text, color=body.color)
    if not n:
        raise HTTPException(status_code=400, detail="Texto vacío")
    if body.pinned and n.get("id"):
        update_note(n["id"], pinned=True)
        n["pinned"] = True
    _publish_change(request, "created", note_id=n.get("id"))
    return n


@router.patch("/{note_id}")
def patch_note(note_id: str, body: NoteUpdate, request: Request) -> dict:
    ok = update_note(
        note_id,
        text=body.text,
        color=body.color,
        pinned=body.pinned,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"Nota '{note_id}' no encontrada")
    _publish_change(request, "updated", note_id=note_id)
    return {"ok": True, "id": note_id}


@router.delete("/{note_id}", status_code=204)
def remove_note(note_id: str, request: Request) -> None:
    ok = delete_note(note_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Nota '{note_id}' no encontrada")
    _publish_change(request, "deleted", note_id=note_id)


# ── helpers ─────────────────────────────────────────────────────────────
def _publish_change(request: Request, op: str, *, note_id: str | None) -> None:
    bus = getattr(request.app.state, "bus", None)
    if bus is None:
        return
    try:
        bus.publish("note.changed", {"op": op, "id": note_id})
    except Exception as e:
        log.debug("publish note.changed falló: %s", e)
