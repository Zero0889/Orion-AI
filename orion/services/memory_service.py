"""Service de memoria largo-plazo.

Wrappea ``orion.domain.memory.memory_manager`` para que la route deje
de mezclar validación de categoría con publicación de eventos.
"""

from __future__ import annotations

from typing import Any

from orion.domain.memory.memory_manager import forget, load_memory, remember
from orion.services._bus_publisher import BusPublisher

EVENT_TYPE = "memory.updated"

# Categorías válidas definidas en :mod:`orion.domain.memory.memory_manager`.
# La route las usaba directo; las mantenemos acá para que el service
# pueda validar sin reach-in al domain.
VALID_CATEGORIES = {
    "identity",
    "preferences",
    "projects",
    "relationships",
    "wishes",
    "notes",
}


class MemoryService:
    def __init__(self, bus: Any | None = None) -> None:
        self._publisher = BusPublisher(bus)

    def load_all(self) -> dict:
        return load_memory()

    def load_category(self, category: str) -> dict:
        mem = load_memory()
        if category not in mem:
            raise CategoryNotFound(category)
        return {category: mem[category]}

    def upsert(self, category: str, key: str, value: str) -> None:
        self._validate_category(category)
        remember(key, value, category=category)
        self._publisher.fire(
            EVENT_TYPE,
            {"op": "upserted", "category": category, "key": key, "value": value},
        )

    def delete(self, category: str, key: str) -> None:
        self._validate_category(category)
        mem = load_memory()
        if key not in mem.get(category, {}):
            raise EntryNotFound(category, key)
        forget(key, category=category)
        self._publisher.fire(
            EVENT_TYPE,
            {"op": "deleted", "category": category, "key": key, "value": None},
        )

    def _validate_category(self, category: str) -> None:
        if category not in VALID_CATEGORIES:
            raise InvalidCategory(category)


class InvalidCategory(ValueError):
    def __init__(self, category: str) -> None:
        super().__init__(f"Categoría '{category}' inválida. Usa una de: {sorted(VALID_CATEGORIES)}")
        self.category = category


class CategoryNotFound(LookupError):
    def __init__(self, category: str) -> None:
        super().__init__(f"Categoría '{category}' no existe")
        self.category = category


class EntryNotFound(LookupError):
    def __init__(self, category: str, key: str) -> None:
        super().__init__(f"Entrada '{category}/{key}' no existe")
        self.category = category
        self.key = key
