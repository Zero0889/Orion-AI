"""
server.routes.iot — Dashboard IoT
==================================
Endpoints:
  GET  /api/iot/devices                    → dispositivos + capabilities
  GET  /api/iot/scenes                     → escenas configuradas
  GET  /api/iot/sensors                    → última lectura cacheada de cada sensor
  POST /api/iot/devices/{id}/action        → on/off/dim/rgb/timed sobre el dispositivo
  POST /api/iot/scenes/{id}/run            → ejecutar una escena

Las mutaciones (action / scene run) delegan en ``iot_control``, el
mismo punto de entrada que Gemini Live usa como herramienta. Eso
garantiza paridad de comportamiento entre voz y web. Cada acción
publica ``iot.action`` en el bus.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from actions.iot import get_system, iot_control
from actions.iot.sensors import get_cache
from actions.iot.scenes import list_scenes

router = APIRouter()


# ── Schemas ─────────────────────────────────────────────────────────────
class DeviceAction(BaseModel):
    action:   str = Field(..., description="on | off | dim | rgb | timed")
    value:    Optional[int] = Field(default=None, description="0-100 para dim")
    color:    Optional[str] = Field(default=None, description="Color para rgb")
    duration: Optional[int] = Field(default=None, description="Segundos para timed")


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
            "value":   reading.raw_value,
            "numeric": reading.numeric(),
            "age_s":   reading.age_seconds(),
        }
    return out


@router.get("/status")
async def get_transport_status() -> dict:
    """Estado de conexión de los transports configurados."""
    result = iot_control({"action": "status"})
    return {"status": result}


# ── Write endpoints ─────────────────────────────────────────────────────
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
    _publish(request, {"device": device_id, **params, "result": result})
    return {"ok": True, "device": device_id, "action": body.action, "result": result}


@router.post("/scenes/{scene_id}/run")
async def scene_run(scene_id: str, request: Request) -> dict:
    if scene_id not in get_system().cfg.scenes:
        raise HTTPException(status_code=404, detail=f"Escena '{scene_id}' no existe")
    result = iot_control({"action": "scene", "scene": scene_id})
    _publish(request, {"scene": scene_id, "result": result})
    return {"ok": True, "scene": scene_id, "result": result}


# ── helpers ─────────────────────────────────────────────────────────────
def _publish(request: Request, payload: dict) -> None:
    bus = getattr(request.app.state, "bus", None)
    if bus is None:
        return
    try:
        bus.publish("iot.action", payload)
    except Exception:
        pass
