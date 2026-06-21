"""Helper compartido: publish con guard para que un fallo del bus no
rompa la mutación que ya está commiteada en SQLite.

Antes vivía duplicado en cada route (``_publish_change`` en notes,
memory, conversations, …). Acá centraliza el patrón. Las services lo
importan y lo usan via composición (``self._publisher.fire(...)``).
"""

from __future__ import annotations

from typing import Any

from orion.core.logger import get_logger

log = get_logger("orion.services.bus")


class BusPublisher:
    """Adaptador thin sobre ``bus.publish(...)``.

    El bus es ``orion.server.event_bus.OrionEventBus`` (in-proc + WS
    broadcast). Lo aceptamos como ``Any`` para que los services no
    importen al server — la inversión de dependencia la fija el caller
    (route → service → publisher; bus se pasa por constructor).

    ``bus=None`` significa "no hay publisher disponible" (caso típico
    en tests unitarios sin app montada). Las llamadas pasan a no-op.
    """

    def __init__(self, bus: Any | None) -> None:
        self._bus = bus

    def fire(self, event_type: str, payload: dict[str, Any]) -> None:
        if self._bus is None:
            return
        try:
            self._bus.publish(event_type, payload)
        except Exception as e:
            # No re-raise: la mutación ya pasó. El bus que falle es
            # observabilidad, no datos. Logueamos a debug porque pasa
            # naturalmente cuando no hay clientes WS conectados.
            log.debug("publish %s falló: %s", event_type, e)
