"""
server.routes.conversations — Historial (solo lectura en Fase 1)
=================================================================
Endpoints:
  GET /api/conversations          → lista resumida (sin mensajes)
  GET /api/conversations/{conv_id} → conversación completa con mensajes
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from core.logger import get_logger
from memory.conversations import (
    delete_conversation, get_conversation, list_conversations,
)

log = get_logger("server.routes.conversations")
router = APIRouter()


@router.get("")
def get_all_conversations() -> list[dict]:
    """Lista las conversaciones (resumidas, sin el cuerpo de mensajes).

    ``list_conversations()`` ya devuelve metadata ligera con ``msg_count``;
    aquí solo lo re-mapeamos a ``messages`` para que el frontend tenga
    un nombre más natural.
    """
    convs = list_conversations()
    return [
        {
            "id":       c.get("id"),
            "started":  c.get("started"),
            "title":    c.get("title"),
            "messages": c.get("msg_count", 0),
        }
        for c in convs
    ]


@router.get("/{conv_id}")
def get_one_conversation(conv_id: str) -> dict:
    conv = get_conversation(conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail=f"Conversación '{conv_id}' no encontrada")
    return conv


@router.delete("/{conv_id}", status_code=204)
def remove_conversation(conv_id: str, request: Request) -> None:
    ok = delete_conversation(conv_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Conversación '{conv_id}' no encontrada")
    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        try:
            bus.publish("conversation.deleted", {"id": conv_id})
        except Exception as e:
            log.debug("publish conversation.deleted falló: %s", e)
