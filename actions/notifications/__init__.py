"""
actions.notifications — Sistema de notificaciones (Gmail, Classroom, …)
=======================================================================
Cada **adapter** (gmail, classroom) sabe consultar una fuente y devolver
una lista de :class:`NotificationItem`. El **poller** (:mod:`.poller`)
los ejecuta cada N minutos en background, deduplica con un **store** de
IDs vistos, y publica ``notification.new`` por el bus para que el frontend
muestre la campana.

Layout
------
- :mod:`actions.notifications.base`     — modelo + interfaz de adapter
- :mod:`actions.notifications.store`    — persistencia de IDs vistos
- :mod:`actions.notifications.gmail`    — adapter que envuelve `gog gmail`
- :mod:`actions.notifications.classroom`— adapter con google-api-python-client
- :mod:`actions.notifications.poller`   — hilo en background

Las acciones expuestas como tools al agente (mark_read, etc.) viven en
otro módulo para no acoplar el bus con la API REST.
"""

from .base import NotificationAdapter, NotificationItem
from .poller import get_poller, start_poller, stop_poller
from .store import NotificationStore, get_store

__all__ = [
    "NotificationAdapter",
    "NotificationItem",
    "NotificationStore",
    "get_poller",
    "get_store",
    "start_poller",
    "stop_poller",
]
