"""
actions.iot.config — Carga, validación y migración del iot_config.json
======================================================================
Maneja DOS formatos:

v1 (legado, lo que tenías hasta hoy)
------------------------------------
```json
{
  "serial_port": "COM1",
  "baud_rate": 9600,
  "devices": {
    "foco_1": {"name": "foco 1", "cmd_on": "FOCO1_ON", "cmd_off": "FOCO1_OFF"}
  },
  "cmd_all_on": "TODOS_ON",
  "cmd_all_off": "TODOS_OFF"
}
```

v2 (actual)
-----------
```json
{
  "version": 2,
  "transports": {
    "main_arduino": {"type": "serial", "port": "COM1", "baud": 9600}
  },
  "devices": {
    "foco_1": {
      "name": "foco 1",
      "transport": "main_arduino",
      "capabilities": {"on_off": true, "dimmable": false, "rgb": false},
      "serial": {"cmd_on": "FOCO1_ON", "cmd_off": "FOCO1_OFF"}
    }
  },
  "global_commands": {"all_on": "TODOS_ON", "all_off": "TODOS_OFF"},
  "scenes": {}
}
```

Si encuentra v1, lo migra **en memoria** y reescribe el archivo en disco
con un backup `iot_config.v1.bak.json` por si acaso.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config import IOT_CONFIG_PATH

from .devices import Device


SCHEMA_VERSION = 2

# Nombre del transport por defecto cuando se migra desde v1 (un Arduino único)
DEFAULT_TRANSPORT_ID = "main_arduino"


# ── Estructura en memoria ───────────────────────────────────────────────────


@dataclass
class IoTConfig:
    """Configuración IoT completa cargada del JSON."""

    version:         int                = SCHEMA_VERSION
    transports:      dict               = field(default_factory=dict)
    devices:         dict[str, Device]  = field(default_factory=dict)
    global_commands: dict               = field(default_factory=dict)
    scenes:          dict               = field(default_factory=dict)

    # ── Convertir a/desde dict ───────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "version":         self.version,
            "transports":      self.transports,
            "devices":         {k: v.to_dict() for k, v in self.devices.items()},
            "global_commands": self.global_commands,
            "scenes":          self.scenes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IoTConfig":
        return cls(
            version         = int(data.get("version", SCHEMA_VERSION)),
            transports      = dict(data.get("transports", {})),
            devices         = {
                k: Device.from_dict(k, v) for k, v in data.get("devices", {}).items()
            },
            global_commands = dict(data.get("global_commands", {})),
            scenes          = dict(data.get("scenes", {})),
        )

    # ── Atajos ───────────────────────────────────────────────────────────
    def get_device(self, dev_id: str) -> Optional[Device]:
        return self.devices.get(dev_id)

    def devices_by_transport(self, transport_id: str) -> list[Device]:
        return [d for d in self.devices.values() if d.transport == transport_id]


# ── Detección y migración v1 → v2 ───────────────────────────────────────────


def _is_v1(data: dict) -> bool:
    """v1 no tiene 'version' ni 'transports', pero sí 'serial_port' o
    'cmd_all_on' al nivel raíz."""
    if "version" in data or "transports" in data:
        return False
    return "serial_port" in data or "cmd_all_on" in data or (
        "devices" in data and data["devices"] and "cmd_on" in next(
            iter(data["devices"].values()), {}
        )
    )


def _migrate_v1_to_v2(v1: dict) -> dict:
    """Convierte el dict v1 al esquema v2. NO toca disco."""
    port = v1.get("serial_port", "COM1")
    baud = v1.get("baud_rate", 9600)

    transports = {
        DEFAULT_TRANSPORT_ID: {
            "type": "serial",
            "port": port,
            "baud": baud,
        }
    }

    devices: dict = {}
    for dev_id, dev_v1 in (v1.get("devices") or {}).items():
        devices[dev_id] = {
            "name":         dev_v1.get("name", dev_id),
            "transport":    DEFAULT_TRANSPORT_ID,
            "capabilities": {
                "on_off":   True,   # los focos v1 son simples on/off
                "dimmable": False,  # opt-in: el usuario lo habilita después
                "rgb":      False,
                "sensor":   None,
            },
            "serial": {
                "cmd_on":  dev_v1.get("cmd_on",  f"{dev_id.upper()}_ON"),
                "cmd_off": dev_v1.get("cmd_off", f"{dev_id.upper()}_OFF"),
            },
        }

    global_commands = {
        "all_on":  v1.get("cmd_all_on",  "TODOS_ON"),
        "all_off": v1.get("cmd_all_off", "TODOS_OFF"),
    }

    return {
        "version":         SCHEMA_VERSION,
        "transports":      transports,
        "devices":         devices,
        "global_commands": global_commands,
        "scenes":          {},
    }


# ── Config por defecto (cuando el archivo no existe) ────────────────────────


def _default_config() -> dict:
    return {
        "version": SCHEMA_VERSION,
        "transports": {
            DEFAULT_TRANSPORT_ID: {
                "type": "serial",
                "port": "COM1",
                "baud": 9600,
            }
        },
        "devices": {
            "foco_1": {
                "name": "foco 1",
                "transport": DEFAULT_TRANSPORT_ID,
                "capabilities": {
                    "on_off": True, "dimmable": False, "rgb": False, "sensor": None,
                },
                "serial": {"cmd_on": "FOCO1_ON", "cmd_off": "FOCO1_OFF"},
            },
            "foco_2": {
                "name": "foco 2",
                "transport": DEFAULT_TRANSPORT_ID,
                "capabilities": {
                    "on_off": True, "dimmable": False, "rgb": False, "sensor": None,
                },
                "serial": {"cmd_on": "FOCO2_ON", "cmd_off": "FOCO2_OFF"},
            },
        },
        "global_commands": {"all_on": "TODOS_ON", "all_off": "TODOS_OFF"},
        "scenes": {},
    }


# ── API pública ─────────────────────────────────────────────────────────────


def load_config(path: Path | None = None) -> IoTConfig:
    """Carga, migra si hace falta, y devuelve un :class:`IoTConfig` válido.

    Si encuentra un v1, hace backup a ``iot_config.v1.bak.json`` y escribe
    el v2 en disco. Si el archivo no existe, lo crea con el default.
    """
    p = Path(path) if path else IOT_CONFIG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)

    if not p.exists():
        data = _default_config()
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[IoT-Config] Archivo creado: {p}")
        return IoTConfig.from_dict(data)

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        # No sobrescribimos un archivo corrupto: avisamos y caemos al default
        # en memoria para que el resto del sistema siga funcionando.
        print(f"[IoT-Config] ⚠️ Config corrupto ({e}). Usando default en memoria.")
        return IoTConfig.from_dict(_default_config())

    if _is_v1(raw):
        print("[IoT-Config] Detectado config v1 — migrando a v2")
        backup = p.with_name("iot_config.v1.bak.json")
        try:
            shutil.copy2(p, backup)
            print(f"[IoT-Config] Backup guardado en {backup.name}")
        except Exception as e:
            print(f"[IoT-Config] ⚠️ No se pudo hacer backup ({e}) — abortando migración")
            return IoTConfig.from_dict(raw)  # devuelve lo que se pueda

        raw = _migrate_v1_to_v2(raw)
        p.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[IoT-Config] Migrado y reescrito: {p}")

    return IoTConfig.from_dict(raw)


def save_config(cfg: IoTConfig, path: Path | None = None) -> None:
    """Escribe el config en disco (formateado, UTF-8)."""
    p = Path(path) if path else IOT_CONFIG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
