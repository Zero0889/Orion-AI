"""server.routes.conversations — Historial.

Endpoints:
  GET    /api/conversations              → lista resumida
  GET    /api/conversations/{conv_id}    → conversación completa
  DELETE /api/conversations/{conv_id}    → borra una
  POST   /api/conversations/bulk_delete  → borra varias por id
  DELETE /api/conversations              → wipe completo

La lógica (listar/borrar + publish ``conversation.deleted``) vive en
:class:`~orion.services.conversations_service.ConversationsService`.
Las inserciones NO van por HTTP — las hace ``ConversationSession``
directo desde OrionLive durante la sesión.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from orion.services.conversations_service import (
    ConversationNotFound,
    ConversationsService,
)


class BulkDeleteBody(BaseModel):
    ids: list[str]


router = APIRouter()


def _service(request: Request) -> ConversationsService:
    return ConversationsService(bus=getattr(request.app.state, "bus", None))


@router.get("")
def get_all_conversations(
    svc: ConversationsService = Depends(_service),
) -> list[dict]:
    return svc.list_summaries()


@router.get("/{conv_id}")
def get_one_conversation(
    conv_id: str,
    svc: ConversationsService = Depends(_service),
) -> dict:
    try:
        return svc.get(conv_id)
    except ConversationNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{conv_id}", status_code=204)
def remove_conversation(
    conv_id: str,
    svc: ConversationsService = Depends(_service),
) -> None:
    try:
        svc.delete(conv_id)
    except ConversationNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/bulk_delete")
def bulk_remove_conversations(
    body: BulkDeleteBody,
    svc: ConversationsService = Depends(_service),
) -> dict:
    """Borra varias conversaciones por id. Devuelve ``{deleted: N}``."""
    return {"deleted": svc.delete_bulk(body.ids)}


@router.delete("", status_code=200)
def remove_all_conversations(
    svc: ConversationsService = Depends(_service),
) -> dict:
    """Wipe completo del historial."""
    return {"deleted": svc.delete_all()}
