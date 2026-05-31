"""
server.routes.conversations — Historial (solo lectura en Fase 1)
=================================================================
Endpoints:
  GET /api/conversations          → lista resumida (sin mensajes)
  GET /api/conversations/{conv_id} → conversación completa con mensajes
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from memory.conversations import get_conversation, list_conversations

router = APIRouter()


@router.get("")
async def get_all_conversations() -> list[dict]:
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
async def get_one_conversation(conv_id: str) -> dict:
    conv = get_conversation(conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail=f"Conversación '{conv_id}' no encontrada")
    return conv
