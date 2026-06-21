"""Service de historial de conversaciones.

Read-only + deletes. Las inserciones las hace ``ConversationSession``
directamente desde el runtime de OrionLive (no via HTTP), por eso acá
no hay ``create``.
"""

from __future__ import annotations

from typing import Any

from orion.domain.memory.conversations import (
    delete_all_conversations,
    delete_conversation,
    delete_conversations_bulk,
    get_conversation,
    list_conversations,
)
from orion.services._bus_publisher import BusPublisher

EVENT_TYPE = "conversation.deleted"


class ConversationsService:
    def __init__(self, bus: Any | None = None) -> None:
        self._publisher = BusPublisher(bus)

    def list_summaries(self) -> list[dict]:
        """Devuelve la lista ligera (sin mensajes) con `messages` como
        contador. La route convertía ``msg_count`` → ``messages`` ad-hoc;
        ahora vive acá para que la transformación sea testeable sin HTTP.
        """
        return [
            {
                "id": c.get("id"),
                "started": c.get("started"),
                "title": c.get("title"),
                "messages": c.get("msg_count", 0),
            }
            for c in list_conversations()
        ]

    def get(self, conv_id: str) -> dict:
        conv = get_conversation(conv_id)
        if conv is None:
            raise ConversationNotFound(conv_id)
        return conv

    def delete(self, conv_id: str) -> None:
        ok = delete_conversation(conv_id)
        if not ok:
            raise ConversationNotFound(conv_id)
        self._publisher.fire(EVENT_TYPE, {"id": conv_id})

    def delete_bulk(self, ids: list[str]) -> int:
        deleted = delete_conversations_bulk(ids)
        if deleted:
            self._publisher.fire(EVENT_TYPE, {"ids": ids, "bulk": True})
        return deleted

    def delete_all(self) -> int:
        deleted = delete_all_conversations()
        if deleted:
            self._publisher.fire(EVENT_TYPE, {"all": True})
        return deleted


class ConversationNotFound(LookupError):
    def __init__(self, conv_id: str) -> None:
        super().__init__(f"Conversación '{conv_id}' no encontrada")
        self.conv_id = conv_id
