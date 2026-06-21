"""Service de notas rápidas.

Encapsula las 5 operaciones que expone ``/api/notes`` + la publicación
del evento ``note.changed`` al bus.

La route correspondiente (``orion.server.routes.notes``) queda thin:
parse Pydantic → instancia service → mapea errores a HTTPException.
"""

from __future__ import annotations

from typing import Any

from orion.domain.memory.quick_notes import (
    add_note,
    count_notes,
    delete_note,
    list_notes,
    update_note,
)
from orion.services._bus_publisher import BusPublisher

EVENT_TYPE = "note.changed"


class NotesService:
    def __init__(self, bus: Any | None = None) -> None:
        self._publisher = BusPublisher(bus)

    def list_all(self) -> list[dict]:
        return list_notes()

    def count(self) -> int:
        return count_notes()

    def create(
        self,
        text: str,
        *,
        pinned: bool = False,
        color: str | None = None,
    ) -> dict:
        """Crea una nota. Devuelve el dict de la nota nueva.

        Si ``text`` resulta vacío post-trim, ``add_note`` devuelve {}; el
        caller HTTP traduce ese caso a 400.
        """
        note = add_note(text, color=color)
        if not note:
            raise NoteCreateFailed("Texto vacío")
        if pinned and note.get("id"):
            update_note(note["id"], pinned=True)
            note["pinned"] = True
        self._publisher.fire(EVENT_TYPE, {"op": "created", "id": note.get("id")})
        return note

    def update(
        self,
        note_id: str,
        *,
        text: str | None = None,
        pinned: bool | None = None,
        color: str | None = None,
    ) -> None:
        """Actualiza campos parciales. Lanza ``NoteNotFound`` si no existe."""
        ok = update_note(note_id, text=text, pinned=pinned, color=color)
        if not ok:
            raise NoteNotFound(note_id)
        self._publisher.fire(EVENT_TYPE, {"op": "updated", "id": note_id})

    def delete(self, note_id: str) -> None:
        ok = delete_note(note_id)
        if not ok:
            raise NoteNotFound(note_id)
        self._publisher.fire(EVENT_TYPE, {"op": "deleted", "id": note_id})


class NoteNotFound(LookupError):
    """La nota con ese id no existe."""

    def __init__(self, note_id: str) -> None:
        super().__init__(f"Nota '{note_id}' no encontrada")
        self.note_id = note_id


class NoteCreateFailed(ValueError):
    """El backend rechazó la creación (típicamente texto vacío)."""
