"""
actions.iot.devices — Modelo de dispositivo con capabilities
============================================================
Cada dispositivo IoT declara qué puede hacer mediante un set de capacidades
opt-in. Esto permite que un mismo `iot_control` maneje focos simples,
dimmers PWM, tiras RGB, sensores, relés, etc. sin tener que ramificar la
lógica por tipo.

Capabilities soportadas
-----------------------
on_off    : encender/apagar (la más común; default true)
dimmable  : intensidad 0-100 (PWM). Si es false, el comando `dim` falla
            con un mensaje claro en vez de simular el cambio.
rgb       : color RGB. Si es false, `rgb` falla.
sensor    : si no es None, el dispositivo emite lecturas (ej. "temperature",
            "humidity", "motion", "light", "gas"). Los sensores no aceptan
            on_off por defecto a menos que también lo declaren.

Transports
----------
Cada dispositivo se asocia a UN transporte (definido en
``Config.transports``). El bloque transport-específico (``serial`` o
``mqtt``) guarda los detalles del protocolo (comandos, topics, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Capabilities:
    """Qué puede hacer un dispositivo. Todas las flags son opt-in."""

    on_off: bool = True
    dimmable: bool = False
    rgb: bool = False
    sensor: str | None = None  # "temperature", "humidity", "motion", ...

    @classmethod
    def from_dict(cls, data: dict | None) -> Capabilities:
        data = data or {}
        return cls(
            on_off=bool(data.get("on_off", True)),
            dimmable=bool(data.get("dimmable", False)),
            rgb=bool(data.get("rgb", False)),
            sensor=data.get("sensor") or None,
        )

    def to_dict(self) -> dict:
        return {
            "on_off": self.on_off,
            "dimmable": self.dimmable,
            "rgb": self.rgb,
            "sensor": self.sensor,
        }


@dataclass
class Device:
    """Un dispositivo IoT con su transporte y capacidades."""

    id: str
    name: str
    transport: str  # clave en Config.transports
    capabilities: Capabilities
    # Configuración específica del transporte. Para serial: cmd_on/off/dim/rgb.
    # Para mqtt: topics y payloads. Se valida al construir el transport adapter.
    serial: dict = field(default_factory=dict)
    mqtt: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, dev_id: str, data: dict) -> Device:
        return cls(
            id=dev_id,
            name=data.get("name", dev_id),
            transport=data.get("transport", "main_arduino"),
            capabilities=Capabilities.from_dict(data.get("capabilities")),
            serial=dict(data.get("serial", {})),
            mqtt=dict(data.get("mqtt", {})),
        )

    def to_dict(self) -> dict:
        out: dict = {
            "name": self.name,
            "transport": self.transport,
            "capabilities": self.capabilities.to_dict(),
        }
        if self.serial:
            out["serial"] = dict(self.serial)
        if self.mqtt:
            out["mqtt"] = dict(self.mqtt)
        return out

    # ── Helpers de capability con error legible ──────────────────────────
    def require(self, capability: str) -> str | None:
        """Devuelve None si la capacidad existe, o un mensaje de error si no.

        Se usa antes de ejecutar dim/rgb/etc. para fallar pronto y dar al
        usuario un mensaje claro en vez de mandar un comando que el dispo-
        sitivo no entiende.
        """
        caps = self.capabilities
        if capability == "on_off" and caps.on_off:
            return None
        if capability == "dimmable" and caps.dimmable:
            return None
        if capability == "rgb" and caps.rgb:
            return None
        if capability == "sensor" and caps.sensor:
            return None

        nice = {
            "on_off": "encenderse o apagarse",
            "dimmable": "regulación de intensidad",
            "rgb": "cambio de color",
            "sensor": "lectura de sensores",
        }.get(capability, capability)
        return f"El dispositivo '{self.name}' no soporta {nice}."
