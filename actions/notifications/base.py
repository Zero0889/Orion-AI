"""Modelo común de notificaciones + interfaz que implementan los adapters."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class NotificationItem:
    """Una notificación lista para mostrar en el frontend o publicar al bus.

    ``uid`` es la clave de deduplicación — el store recuerda los ya vistos.
    Cada adapter elige cómo construirlo: Gmail usa el messageId, Classroom
    usa ``"<courseId>:<itemId>"``. Lo importante es que sea **estable**
    entre polls.
    """

    uid: str
    source: str  # "gmail" | "classroom" | "calendar" | ...
    title: str  # 1 línea, lo que ve el usuario
    summary: str = ""  # 2-3 líneas opcionales
    url: str | None = None  # Acción primaria: abrir en navegador
    received_ts: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class NotificationAdapter(ABC):
    """Interfaz de un origen de notificaciones.

    El poller llama :meth:`fetch` cada N minutos. El adapter debe ser
    idempotente: devolver TODAS las notificaciones recientes; la
    deduplicación la hace el store. Si la fuente está caída o sin auth,
    levantar ``RuntimeError`` con mensaje claro y el poller lo loggea sin
    romper los demás adapters.
    """

    @property
    @abstractmethod
    def source(self) -> str:
        """Identificador único del adapter (gmail, classroom, …)."""

    @abstractmethod
    def is_configured(self) -> bool:
        """¿Tiene credenciales y dependencias instaladas? El UI lo usa
        para marcar la fuente como 'pendiente de setup' en el panel."""

    @abstractmethod
    def fetch(self, *, max_items: int = 20) -> list[NotificationItem]:
        """Devuelve las notificaciones más recientes (sin deduplicar)."""
