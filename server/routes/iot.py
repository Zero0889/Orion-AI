"""
server.routes.iot — Dashboard IoT
==================================
Endpoints de **lectura**:
  GET    /api/iot/devices                    → dispositivos + capabilities
  GET    /api/iot/scenes                     → escenas configuradas
  GET    /api/iot/sensors                    → última lectura cacheada de cada sensor
  GET    /api/iot/status                     → estado de los transports
  GET    /api/iot/config                     → config completo (transports + devices)

Endpoints de **mutación** (delegan en ``iot_control``):
  POST   /api/iot/devices/{id}/action        → on/off/dim/rgb/timed sobre el dispositivo
  POST   /api/iot/scenes/{id}/run            → ejecutar una escena

Endpoints de **administración** (escriben ``iot_config.json``):
  POST   /api/iot/admin/devices              → crear dispositivo nuevo
  PUT    /api/iot/admin/devices/{id}         → actualizar dispositivo existente
  DELETE /api/iot/admin/devices/{id}         → borrar dispositivo
  PUT    /api/iot/admin/transports/{id}      → crear/actualizar transport
  DELETE /api/iot/admin/transports/{id}      → borrar transport (debe estar vacío)
  POST   /api/iot/admin/reload               → reload manual sin tocar config

Cada cambio admin:
  1. Valida con :func:`validate_device` / :func:`validate_transport`
  2. Escribe ``iot_config.json`` atómicamente con backup
  3. Recarga el ``IoTSystem`` en caliente (cierra transports viejos, abre nuevos)
  4. Publica ``iot.config`` en el bus para que el frontend recargue
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from actions.iot import get_system, iot_control
from actions.iot.config import (
    IoTConfig, save_config, validate_device, validate_transport,
)
from actions.iot.devices import Device
from actions.iot.sensors import get_cache
from actions.iot.scenes import list_scenes

router = APIRouter()


# ── Schemas ─────────────────────────────────────────────────────────────
class DeviceAction(BaseModel):
    action:   str = Field(..., description="on | off | dim | rgb | timed")
    value:    Optional[int] = Field(default=None, description="0-100 para dim")
    color:    Optional[str] = Field(default=None, description="Color para rgb")
    duration: Optional[int] = Field(default=None, description="Segundos para timed")


class CapabilitiesBody(BaseModel):
    on_off:   bool = False
    dimmable: bool = False
    rgb:      bool = False
    sensor:   Optional[str] = None


class DeviceBody(BaseModel):
    """Payload para crear/actualizar un dispositivo en iot_config.json."""
    id:           Optional[str] = Field(default=None, description="solo en POST")
    name:         str
    transport:    str
    capabilities: CapabilitiesBody
    serial:       Optional[dict[str, Any]] = None
    mqtt:         Optional[dict[str, Any]] = None


class TransportBody(BaseModel):
    """Payload para crear/actualizar un transport."""
    type:      str = Field(..., description="'serial' o 'mqtt'")
    # Serial
    port:      Optional[str] = None
    baud:      Optional[int] = None
    # MQTT
    host:      Optional[str] = None
    port_mqtt: Optional[int] = Field(default=None, alias="mqtt_port")
    username:  Optional[str] = None
    password:  Optional[str] = None
    client_id: Optional[str] = None
    tls:       Optional[bool] = None

    model_config = {"populate_by_name": True}


# ── Read endpoints ──────────────────────────────────────────────────────
@router.get("/devices")
async def get_devices() -> list[dict]:
    sys = get_system()
    devices = []
    for dev in sys.cfg.devices.values():
        devices.append({
            "id":           dev.id,
            "name":         dev.name,
            "transport":    dev.transport,
            "capabilities": dev.capabilities.to_dict(),
            # Devolvemos la config específica para que el modal de edición
            # pueda mostrar topics/comandos sin tener que pegar JSON
            "serial":       dev.serial or None,
            "mqtt":         dev.mqtt or None,
        })
    return devices


@router.get("/scenes")
async def get_scenes() -> list[dict]:
    return list_scenes(get_system().cfg)


@router.get("/sensors")
async def get_sensors() -> dict:
    cache = get_cache()
    out = {}
    for dev_id, reading in cache.all().items():
        out[dev_id] = {
            "value":   reading.value,
            "numeric": reading.numeric(),
            "age_s":   reading.age_seconds(),
        }
    return out


@router.get("/status")
async def get_transport_status() -> dict:
    """Estado de conexión de los transports configurados."""
    result = iot_control({"action": "status"})
    return {"status": result}


@router.get("/config")
async def get_full_config() -> dict:
    """Devuelve el config completo (transports + devices + scenes).

    Útil para que el frontend muestre los detalles de cada transport
    al editar y al elegir 'a qué transport conectar este dispositivo'.
    """
    sys = get_system()
    return sys.cfg.to_dict()


# ── Write endpoints (acciones, no config) ───────────────────────────────
@router.post("/devices/{device_id}/action")
async def device_action(
    device_id: str, body: DeviceAction, request: Request,
) -> dict:
    if device_id not in get_system().cfg.devices:
        raise HTTPException(status_code=404, detail=f"Dispositivo '{device_id}' no existe")

    params: dict[str, Any] = {"action": body.action, "device": device_id}
    if body.value    is not None: params["value"]    = body.value
    if body.color    is not None: params["color"]    = body.color
    if body.duration is not None: params["duration"] = body.duration

    result = iot_control(params)
    _publish(request, "iot.action", {"device": device_id, **params, "result": result})
    return {"ok": True, "device": device_id, "action": body.action, "result": result}


@router.post("/scenes/{scene_id}/run")
async def scene_run(scene_id: str, request: Request) -> dict:
    if scene_id not in get_system().cfg.scenes:
        raise HTTPException(status_code=404, detail=f"Escena '{scene_id}' no existe")
    result = iot_control({"action": "scene", "scene": scene_id})
    _publish(request, "iot.action", {"scene": scene_id, "result": result})
    return {"ok": True, "scene": scene_id, "result": result}


# ── Admin endpoints (mutan iot_config.json) ─────────────────────────────


def _transport_dict_from_body(body: TransportBody) -> dict:
    """Convierte el body Pydantic a dict, dropeando None y mapeando port."""
    raw = body.model_dump(by_alias=False, exclude_none=True)
    # En MQTT 'port_mqtt' (alias 'mqtt_port' en JSON) representa el puerto;
    # en serial 'port' es el COM. Normalizamos al esquema final:
    if raw.get("type") == "mqtt":
        if "port_mqtt" in raw:
            raw["port"] = raw.pop("port_mqtt")
        # En MQTT no aplica 'port' como COM ni 'baud'
        raw.pop("baud", None)
    elif raw.get("type") == "serial":
        # En serial no aplican los campos MQTT
        for k in ("host", "username", "password", "client_id", "tls", "port_mqtt"):
            raw.pop(k, None)
    return raw


def _persist_and_reload(request: Request, cfg: IoTConfig, event: dict) -> None:
    """Escribe el config y recarga el sistema SOLO si hubo cambios reales.

    Sin esta comprobación, cualquier PUT/POST idempotente (p. ej. guardar
    sin cambiar nada) dispararía un reload completo de transports →
    desconecta MQTT, libera y reabre el COM, etc. — caro y ruidoso.
    """
    import hashlib, json as _json
    from config import IOT_CONFIG_PATH

    new_serialized = _json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False, sort_keys=True)
    new_hash = hashlib.sha256(new_serialized.encode("utf-8")).hexdigest()

    old_hash: str | None = None
    try:
        if IOT_CONFIG_PATH.exists():
            old_serialized = _json.dumps(
                _json.loads(IOT_CONFIG_PATH.read_text(encoding="utf-8")),
                indent=2, ensure_ascii=False, sort_keys=True,
            )
            old_hash = hashlib.sha256(old_serialized.encode("utf-8")).hexdigest()
    except Exception:
        old_hash = None

    if old_hash == new_hash:
        # No-op: ni escribimos ni recargamos. Publicamos un evento "soft"
        # para que el frontend refresque la UI si necesita.
        _publish(request, "iot.config", {**event, "noop": True})
        return

    save_config(cfg)
    try:
        get_system().reload()
    except Exception as e:
        print(f"[IoT-Admin] ⚠️ Hot-reload falló: {e}")
    _publish(request, "iot.config", event)


@router.post("/admin/devices", status_code=201)
async def create_device(body: DeviceBody, request: Request) -> dict:
    if not body.id:
        raise HTTPException(status_code=400, detail="Falta 'id' del dispositivo")

    sys = get_system()
    if body.id in sys.cfg.devices:
        raise HTTPException(status_code=409, detail=f"Ya existe '{body.id}'")

    dev_data = {
        "name":         body.name,
        "transport":    body.transport,
        "capabilities": body.capabilities.model_dump(),
        "serial":       body.serial or {},
        "mqtt":         body.mqtt or {},
    }
    errs = validate_device(dev_data, sys.cfg.transports)
    if errs:
        raise HTTPException(status_code=400, detail="; ".join(errs))

    sys.cfg.devices[body.id] = Device.from_dict(body.id, dev_data)
    _persist_and_reload(request, sys.cfg, {"action": "create", "device": body.id})
    return {"ok": True, "id": body.id}


@router.put("/admin/devices/{device_id}")
async def update_device(device_id: str, body: DeviceBody, request: Request) -> dict:
    sys = get_system()
    if device_id not in sys.cfg.devices:
        raise HTTPException(status_code=404, detail=f"'{device_id}' no existe")

    dev_data = {
        "name":         body.name,
        "transport":    body.transport,
        "capabilities": body.capabilities.model_dump(),
        "serial":       body.serial or {},
        "mqtt":         body.mqtt or {},
    }
    errs = validate_device(dev_data, sys.cfg.transports)
    if errs:
        raise HTTPException(status_code=400, detail="; ".join(errs))

    sys.cfg.devices[device_id] = Device.from_dict(device_id, dev_data)
    _persist_and_reload(request, sys.cfg, {"action": "update", "device": device_id})
    return {"ok": True, "id": device_id}


@router.delete("/admin/devices/{device_id}")
async def delete_device(device_id: str, request: Request) -> dict:
    sys = get_system()
    if device_id not in sys.cfg.devices:
        raise HTTPException(status_code=404, detail=f"'{device_id}' no existe")

    del sys.cfg.devices[device_id]
    _persist_and_reload(request, sys.cfg, {"action": "delete", "device": device_id})
    return {"ok": True, "id": device_id}


@router.put("/admin/transports/{transport_id}")
async def upsert_transport(transport_id: str, body: TransportBody, request: Request) -> dict:
    tcfg = _transport_dict_from_body(body)
    sys = get_system()
    errs = validate_transport(tcfg, existing=sys.cfg.transports, self_id=transport_id)
    if errs:
        raise HTTPException(status_code=400, detail="; ".join(errs))

    sys.cfg.transports[transport_id] = tcfg
    _persist_and_reload(request, sys.cfg, {"action": "upsert", "transport": transport_id})
    return {"ok": True, "id": transport_id}


@router.delete("/admin/transports/{transport_id}")
async def delete_transport(transport_id: str, request: Request) -> dict:
    sys = get_system()
    if transport_id not in sys.cfg.transports:
        raise HTTPException(status_code=404, detail=f"'{transport_id}' no existe")

    using = [d.id for d in sys.cfg.devices.values() if d.transport == transport_id]
    if using:
        raise HTTPException(
            status_code=409,
            detail=f"Transport en uso por: {', '.join(using)}. "
                   f"Reasigna o borra esos dispositivos primero.",
        )

    del sys.cfg.transports[transport_id]
    _persist_and_reload(request, sys.cfg, {"action": "delete", "transport": transport_id})
    return {"ok": True, "id": transport_id}


@router.post("/admin/reload")
async def reload_system(request: Request) -> dict:
    """Recarga el config desde disco sin escribir nada. Útil si editaste
    iot_config.json a mano y quieres aplicar sin reiniciar ORION."""
    try:
        get_system().reload()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reload falló: {e}")
    _publish(request, "iot.config", {"action": "reload"})
    return {"ok": True}


# ── helpers ─────────────────────────────────────────────────────────────
def _publish(request: Request, topic: str, payload: dict) -> None:
    bus = getattr(request.app.state, "bus", None)
    if bus is None:
        return
    try:
        bus.publish(topic, payload)
    except Exception:
        pass
