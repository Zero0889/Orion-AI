"""
actions.iot.transports.base — Interfaz común de transporte
==========================================================
Cualquier medio físico/lógico para hablar con dispositivos IoT
(Serial-USB al Arduino, MQTT al broker, futuro Zigbee, etc.) implementa
esta clase para que :mod:`actions.iot.control` no tenga que saber el
protocolo concreto.

Contrato
--------
- ``send(device, kind, value)`` ejecuta una acción sobre UN dispositivo.
  ``kind`` ∈ {"on", "off", "dim", "rgb", "raw"} y ``value`` depende:
    * ``dim``  → int 0–100 (porcentaje)
    * ``rgb``  → tuple (r, g, b) cada uno 0–255
    * ``raw``  → str con el comando crudo (escape hatch)
- ``broadcast(kind)`` ejecuta el comando global all_on / all_off del
  transporte (los dispositivos individuales no entran).
- ``register_sensor_listener(device, callback)`` para sensores: el
  transport entrega lecturas asíncronas al callback ``(name, value)``.
- ``close()`` libera recursos (puerto serial, cliente MQTT, etc.).

Las implementaciones deben ser **thread-safe** porque varios actions
pueden llamar al mismo transporte en paralelo.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from ..devices import Device

SensorCallback = Callable[[str, str], None]  # (device_id, raw_value) → None


class Transport(ABC):
    """Interfaz que cumple cada implementación de transporte."""

    def __init__(self, transport_id: str, cfg: dict) -> None:
        self.id = transport_id
        self.cfg = dict(cfg)
        self._sensor_listeners: dict[str, list[SensorCallback]] = {}

    # ── Acciones ─────────────────────────────────────────────────────────
    @abstractmethod
    def send(self, device: Device, kind: str, value=None) -> bool:
        """Ejecuta ``kind`` sobre ``device``. Devuelve True si se envió.

        Implementaciones deben **no** validar capabilities — eso lo hace el
        orquestador antes. Aquí solo se traduce a bytes/payload y se envía.
        """

    def broadcast(self, kind: str) -> bool:
        """Comando global (all_on / all_off). Por defecto: no soportado.
        Las implementaciones que sí lo soportan lo sobreescriben.
        """
        return False

    # ── Sensores ─────────────────────────────────────────────────────────
    def register_sensor_listener(
        self,
        device_id: str,
        callback: SensorCallback,
    ) -> None:
        """Suscribe ``callback`` a las lecturas del sensor ``device_id``."""
        self._sensor_listeners.setdefault(device_id, []).append(callback)

    def _dispatch_sensor(self, device_id: str, raw_value: str) -> None:
        """Implementaciones llaman esto cuando llega un dato del dispositivo."""
        for cb in self._sensor_listeners.get(device_id, []):
            try:
                cb(device_id, raw_value)
            except Exception as e:
                print(f"[IoT-Transport:{self.id}] sensor callback error: {e}")

    # ── Estado ───────────────────────────────────────────────────────────
    @abstractmethod
    def is_connected(self) -> bool:
        """¿El transporte está listo para enviar?"""

    @abstractmethod
    def close(self) -> None:
        """Libera el recurso subyacente."""

    # ── Resumen para debugging / status ──────────────────────────────────
    def describe(self) -> str:
        state = "conectado" if self.is_connected() else "desconectado"
        return f"{self.id} [{type(self).__name__}] {state}"
