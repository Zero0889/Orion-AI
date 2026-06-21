"""server.routes.notes — Notas rápidas (CRUD).

Endpoints:
  GET    /api/notes              → lista completa
  GET    /api/notes/count        → cuántas
  POST   /api/notes              → crea {text, pinned?, color?}
  PATCH  /api/notes/{id}         → actualiza {text?, pinned?, color?}
  DELETE /api/notes/{id}         → borra

La lógica (call al domain + publish ``note.changed``) vive en
:class:`~orion.services.notes_service.NotesService`. Esta route quedó
thin: parse Pydantic → call service → map errores a HTTPException.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from orion.services.notes_service import (
    NoteCreateFailed,
    NoteNotFound,
    NotesService,
)

router = APIRouter()


class NoteCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    pinned: bool = False
    color: str | None = None


class NoteUpdate(BaseModel):
    text: str | None = Field(default=None, max_length=4000)
    pinned: bool | None = None
    color: str | None = None


def _service(request: Request) -> NotesService:
    return NotesService(bus=getattr(request.app.state, "bus", None))


@router.get("")
def get_notes(svc: NotesService = Depends(_service)) -> list[dict]:
    return svc.list_all()


@router.get("/count")
def get_notes_count(svc: NotesService = Depends(_service)) -> dict:
    return {"count": svc.count()}


@router.post("", status_code=201)
def create_note(body: NoteCreate, svc: NotesService = Depends(_service)) -> dict:
    try:
        return svc.create(body.text, pinned=body.pinned, color=body.color)
    except NoteCreateFailed as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.patch("/{note_id}")
def patch_note(
    note_id: str,
    body: NoteUpdate,
    svc: NotesService = Depends(_service),
) -> dict:
    try:
        svc.update(note_id, text=body.text, pinned=body.pinned, color=body.color)
    except NoteNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"ok": True, "id": note_id}


@router.delete("/{note_id}", status_code=204)
def remove_note(note_id: str, svc: NotesService = Depends(_service)) -> None:
    try:
        svc.delete(note_id)
    except NoteNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
