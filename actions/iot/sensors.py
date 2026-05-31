"""
actions.iot.sensors — Cache de últimas lecturas de sensores
============================================================
Cuando un transporte recibe un dato de sensor (línea serial o mensaje
MQTT), lo guarda aquí. ORION después responde "hay 24°C" leyendo del
cache, sin tener que pedirle al Arduino la lectura en ese momento (que
sería lento y serializaría el bus serial).

Cada lectura guarda valor + timestamp para que el orquestador pueda
decir "hace 12 minutos" si la lectura es vieja.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SensorReading:
    device_id: str
    value:     str       # crudo, como llegó del transporte
    ts:        float     # epoch seconds

    def age_seconds(self) -> float:
        return time.time() - self.ts

    def numeric(self) -> Optional[float]:
        try:
            return float(self.value.replace(",", "."))
        except (ValueError, AttributeError):
            return None


class SensorCache:
    """Cache thread-safe de la última lectura por dispositivo."""

    def __init__(self) -> None:
        self._values: dict[str, SensorReading] = {}
        self._lock   = threading.Lock()

    def update(self, device_id: str, raw_value: str) -> None:
        reading = SensorReading(device_id, raw_value.strip(), time.time())
        with self._lock:
            self._values[device_id] = reading

    def get(self, device_id: str) -> Optional[SensorReading]:
        with self._lock:
            return self._values.get(device_id)

    def all(self) -> dict[str, SensorReading]:
        with self._lock:
            return dict(self._values)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()


# Singleton del proceso (un solo cache para todo ORION)
_cache: Optional[SensorCache] = None


def get_cache() -> SensorCache:
    global _cache
    if _cache is None:
        _cache = SensorCache()
    return _cache
