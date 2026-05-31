"""
actions.iot.transports — Capa de transporte (Serial / MQTT / ...)
=================================================================
Cada transporte implementa la interfaz :class:`Transport` y se registra
aquí. La fábrica :func:`get_transport` devuelve una instancia cacheada
por ``transport_id`` para que conectar al Arduino o al broker MQTT
ocurra una sola vez por proceso.

Cómo añadir un transporte nuevo
-------------------------------
1. Crear ``actions/iot/transports/<nombre>.py`` con una clase que herede
   de :class:`Transport`.
2. Registrar la clase en :data:`_TRANSPORT_TYPES` aquí abajo.
3. Documentar el bloque de config esperado en el docstring de la clase.

Las importaciones de cada implementación son **lazy** para que MQTT no
arrastre ``paho-mqtt`` si el usuario solo usa serial, y viceversa.
"""

from __future__ import annotations

import threading
from typing import Optional

from .base import Transport


# Mapa `type` (del config) → import lazy `(módulo, clase)`
_TRANSPORT_TYPES = {
    "serial": ("actions.iot.transports.serial_tx", "SerialTransport"),
    "mqtt":   ("actions.iot.transports.mqtt_tx",   "MQTTTransport"),
}


_instances: dict[str, Transport] = {}
_lock = threading.Lock()


def get_transport(transport_id: str, cfg: dict) -> Optional[Transport]:
    """Devuelve la instancia del transporte (cacheada).

    :param transport_id: clave única del transporte (ej. "main_arduino").
    :param cfg: bloque de configuración del transporte (con ``type`` y
        los parámetros específicos).
    :returns: instancia conectada, o ``None`` si el tipo es desconocido o
        la dependencia opcional no está instalada.
    """
    with _lock:
        if transport_id in _instances:
            return _instances[transport_id]

        ttype = (cfg.get("type") or "").lower()
        target = _TRANSPORT_TYPES.get(ttype)
        if target is None:
            print(f"[IoT-Transport] Tipo desconocido: '{ttype}' para {transport_id}")
            return None

        module_path, class_name = target
        try:
            module = __import__(module_path, fromlist=[class_name])
            klass  = getattr(module, class_name)
        except ImportError as e:
            print(f"[IoT-Transport] '{ttype}' no disponible: {e}")
            return None

        try:
            instance = klass(transport_id, cfg)
            _instances[transport_id] = instance
            return instance
        except Exception as e:
            print(f"[IoT-Transport] No se pudo construir {transport_id}: {e}")
            return None


def close_all() -> None:
    """Cierra todos los transportes abiertos (usado al apagar ORION)."""
    with _lock:
        for tid, t in list(_instances.items()):
            try:
                t.close()
            except Exception as e:
                print(f"[IoT-Transport] Error cerrando {tid}: {e}")
        _instances.clear()


__all__ = ["Transport", "get_transport", "close_all"]
