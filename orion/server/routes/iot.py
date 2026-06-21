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

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from orion.actions.iot import get_system, iot_control, sensor_log, sheets_sync
from orion.actions.iot.config import (
    IoTConfig,
    save_config,
    validate_device,
    validate_transport,
)
from orion.actions.iot.devices import Device
from orion.actions.iot.scenes import list_scenes
from orion.actions.iot.sensors import get_cache
from orion.core.logger import get_logger
from orion.server import safe_error_detail

log = get_logger("server.routes.iot")

router = APIRouter()


# ── Schemas ─────────────────────────────────────────────────────────────
class DeviceAction(BaseModel):
    action: str = Field(..., description="on | off | dim | rgb | timed")
    value: int | None = Field(default=None, description="0-100 para dim")
    color: str | None = Field(default=None, description="Color para rgb")
    duration: int | None = Field(default=None, description="Segundos para timed")


class CapabilitiesBody(BaseModel):
    on_off: bool = False
    dimmable: bool = False
    rgb: bool = False
    sensor: str | None = None


class DeviceBody(BaseModel):
    """Payload para crear/actualizar un dispositivo en iot_config.json."""

    id: str | None = Field(default=None, description="solo en POST")
    name: str
    transport: str
    capabilities: CapabilitiesBody
    serial: dict[str, Any] | None = None
    mqtt: dict[str, Any] | None = None


class TransportBody(BaseModel):
    """Payload para crear/actualizar un transport."""

    type: str = Field(..., description="'serial' o 'mqtt'")
    # Serial
    port: str | None = None
    baud: int | None = None
    # MQTT
    host: str | None = None
    port_mqtt: int | None = Field(default=None, alias="mqtt_port")
    username: str | None = None
    password: str | None = None
    client_id: str | None = None
    tls: bool | None = None

    model_config = {"populate_by_name": True}


# ── Read endpoints ──────────────────────────────────────────────────────
@router.get("/devices")
def get_devices() -> list[dict]:
    sys = get_system()
    devices = []
    for dev in sys.cfg.devices.values():
        devices.append(
            {
                "id": dev.id,
                "name": dev.name,
                "transport": dev.transport,
                "capabilities": dev.capabilities.to_dict(),
                # Devolvemos la config específica para que el modal de edición
                # pueda mostrar topics/comandos sin tener que pegar JSON
                "serial": dev.serial or None,
                "mqtt": dev.mqtt or None,
            }
        )
    return devices


@router.get("/scenes")
def get_scenes() -> list[dict]:
    return list_scenes(get_system().cfg)


@router.get("/sensors")
def get_sensors() -> dict:
    cache = get_cache()
    out = {}
    for dev_id, reading in cache.all().items():
        out[dev_id] = {
            "value": reading.value,
            "numeric": reading.numeric(),
            "age_s": reading.age_seconds(),
        }
    return out


@router.get("/status")
def get_transport_status() -> dict:
    """Estado de conexión de los transports configurados."""
    result = iot_control({"action": "status"})
    return {"status": result}


@router.get("/config")
def get_full_config() -> dict:
    """Devuelve el config completo (transports + devices + scenes).

    Útil para que el frontend muestre los detalles de cada transport
    al editar y al elegir 'a qué transport conectar este dispositivo'.
    """
    sys = get_system()
    return sys.cfg.to_dict()


# ── Write endpoints (acciones, no config) ───────────────────────────────
@router.post("/devices/{device_id}/action")
def device_action(
    device_id: str,
    body: DeviceAction,
    request: Request,
) -> dict:
    if device_id not in get_system().cfg.devices:
        raise HTTPException(status_code=404, detail=f"Dispositivo '{device_id}' no existe")

    params: dict[str, Any] = {"action": body.action, "device": device_id}
    if body.value is not None:
        params["value"] = body.value
    if body.color is not None:
        params["color"] = body.color
    if body.duration is not None:
        params["duration"] = body.duration

    result = iot_control(params)
    _publish(request, "iot.action", {"device": device_id, **params, "result": result})
    return {"ok": True, "device": device_id, "action": body.action, "result": result}


@router.post("/scenes/{scene_id}/run")
def scene_run(scene_id: str, request: Request) -> dict:
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
    import hashlib
    import json as _json

    from orion.config import IOT_CONFIG_PATH

    new_serialized = _json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False, sort_keys=True)
    new_hash = hashlib.sha256(new_serialized.encode("utf-8")).hexdigest()

    old_hash: str | None = None
    try:
        if IOT_CONFIG_PATH.exists():
            old_serialized = _json.dumps(
                _json.loads(IOT_CONFIG_PATH.read_text(encoding="utf-8")),
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            old_hash = hashlib.sha256(old_serialized.encode("utf-8")).hexdigest()
    except (OSError, ValueError) as e:
        log.warning("no pude leer hash de iot_config: %s", e)
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
        log.warning("Hot-reload IoT falló: %s", e)
    _publish(request, "iot.config", event)


@router.post("/admin/devices", status_code=201)
def create_device(body: DeviceBody, request: Request) -> dict:
    if not body.id:
        raise HTTPException(status_code=400, detail="Falta 'id' del dispositivo")

    sys = get_system()
    if body.id in sys.cfg.devices:
        raise HTTPException(status_code=409, detail=f"Ya existe '{body.id}'")

    dev_data = {
        "name": body.name,
        "transport": body.transport,
        "capabilities": body.capabilities.model_dump(),
        "serial": body.serial or {},
        "mqtt": body.mqtt or {},
    }
    errs = validate_device(dev_data, sys.cfg.transports)
    if errs:
        raise HTTPException(status_code=400, detail="; ".join(errs))

    sys.cfg.devices[body.id] = Device.from_dict(body.id, dev_data)
    _persist_and_reload(request, sys.cfg, {"action": "create", "device": body.id})
    return {"ok": True, "id": body.id}


@router.put("/admin/devices/{device_id}")
def update_device(device_id: str, body: DeviceBody, request: Request) -> dict:
    sys = get_system()
    if device_id not in sys.cfg.devices:
        raise HTTPException(status_code=404, detail=f"'{device_id}' no existe")

    dev_data = {
        "name": body.name,
        "transport": body.transport,
        "capabilities": body.capabilities.model_dump(),
        "serial": body.serial or {},
        "mqtt": body.mqtt or {},
    }
    errs = validate_device(dev_data, sys.cfg.transports)
    if errs:
        raise HTTPException(status_code=400, detail="; ".join(errs))

    sys.cfg.devices[device_id] = Device.from_dict(device_id, dev_data)
    _persist_and_reload(request, sys.cfg, {"action": "update", "device": device_id})
    return {"ok": True, "id": device_id}


@router.delete("/admin/devices/{device_id}")
def delete_device(device_id: str, request: Request) -> dict:
    sys = get_system()
    if device_id not in sys.cfg.devices:
        raise HTTPException(status_code=404, detail=f"'{device_id}' no existe")

    del sys.cfg.devices[device_id]
    _persist_and_reload(request, sys.cfg, {"action": "delete", "device": device_id})
    return {"ok": True, "id": device_id}


@router.put("/admin/transports/{transport_id}")
def upsert_transport(transport_id: str, body: TransportBody, request: Request) -> dict:
    tcfg = _transport_dict_from_body(body)
    sys = get_system()
    errs = validate_transport(tcfg, existing=sys.cfg.transports, self_id=transport_id)
    if errs:
        raise HTTPException(status_code=400, detail="; ".join(errs))

    sys.cfg.transports[transport_id] = tcfg
    _persist_and_reload(request, sys.cfg, {"action": "upsert", "transport": transport_id})
    return {"ok": True, "id": transport_id}


@router.delete("/admin/transports/{transport_id}")
def delete_transport(transport_id: str, request: Request) -> dict:
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
def reload_system(request: Request) -> dict:
    """Recarga el config desde disco sin escribir nada. Útil si editaste
    iot_config.json a mano y quieres aplicar sin reiniciar ORION."""
    try:
        get_system().reload()
    except Exception as e:
        log.exception("Reload IoT falló")
        raise HTTPException(
            status_code=500,
            detail=f"Reload falló: {safe_error_detail(e)}",
        ) from e
    _publish(request, "iot.config", {"action": "reload"})
    return {"ok": True}


# ── Pausar / reanudar TODOS los sensores (corta transports) ─────────────
@router.post("/admin/disconnect")
def disconnect_all(request: Request) -> dict:
    """Cierra TODOS los transports IoT (serial + MQTT) sin tocar el config.
    Útil cuando no querés que ORION conecte al COM o al broker al arrancar.
    Persiste el estado en :file:`config/iot_paused.flag` para que sobreviva
    al reinicio."""
    from orion.actions.iot.transports import close_all
    from orion.config import IOT_CONFIG_PATH

    close_all()
    # Reset del singleton para que un futuro get_system() respete el flag.
    import orion.actions.iot.control as _ctrl

    with _ctrl._system_lock:
        _ctrl._system = None

    flag = IOT_CONFIG_PATH.parent / "iot_paused.flag"
    try:
        flag.write_text("1", encoding="utf-8")
    except OSError as e:
        log.warning("No pude persistir flag de pausa: %s", e)

    _publish(request, "iot.config", {"action": "disconnect", "paused": True})
    return {"ok": True, "paused": True}


@router.post("/admin/connect")
def connect_all(request: Request) -> dict:
    """Reanuda los transports. Borra el flag de pausa y reabre."""
    from orion.config import IOT_CONFIG_PATH

    flag = IOT_CONFIG_PATH.parent / "iot_paused.flag"
    try:
        if flag.exists():
            flag.unlink()
    except Exception:
        pass
    try:
        get_system().reload()
    except Exception as e:
        log.exception("Reconectar IoT falló")
        raise HTTPException(
            status_code=500,
            detail=f"Reconectar falló: {safe_error_detail(e)}",
        ) from e
    _publish(request, "iot.config", {"action": "connect", "paused": False})
    return {"ok": True, "paused": False}


@router.get("/admin/paused")
def get_paused() -> dict:
    """Estado actual del flag (true = transports cerrados)."""
    from orion.config import IOT_CONFIG_PATH

    flag = IOT_CONFIG_PATH.parent / "iot_paused.flag"
    return {"paused": flag.exists()}


# ── Descarga del log de sensores ────────────────────────────────────────
@router.get("/sensor_log/csv")
def download_sensor_log_csv() -> Response:
    """Descarga el log persistente como CSV. Una fila por dispositivo
    por minuto (promedio de las lecturas de ese minuto)."""
    data = sensor_log.read_csv_bytes()
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="orion_iot_sensores.csv"'},
    )


class SheetsConnectBody(BaseModel):
    account: str = Field(..., description="Email Google asociado a gog")
    title: str | None = Field(default=None, description="Nombre del Sheet (opcional)")


@router.get("/sheets/status")
def sheets_status() -> dict:
    """Estado actual del sync a Google Sheets."""
    return sheets_sync.status()


@router.post("/sheets/connect")
def sheets_connect(body: SheetsConnectBody, request: Request) -> dict:
    """Crea un Sheet nuevo y arranca el sync continuo."""
    try:
        state = sheets_sync.connect(body.account.strip(), body.title)
    except Exception as e:
        log.exception("Sheets connect falló")
        raise HTTPException(status_code=400, detail=safe_error_detail(e)) from e
    _publish(request, "iot.sheets", {"action": "connect", "state": state})
    return state


@router.post("/sheets/disconnect")
def sheets_disconnect(request: Request) -> dict:
    """Para el sync. NO borra el Sheet en Drive."""
    state = sheets_sync.disconnect()
    _publish(request, "iot.sheets", {"action": "disconnect", "state": state})
    return state


@router.post("/sheets/sync_now")
def sheets_sync_now(request: Request) -> dict:
    """Fuerza un sync inmediato sin esperar al próximo tick."""
    sheets_sync.request_sync_now()
    return {"ok": True}


class SheetsIntervalBody(BaseModel):
    sync_interval_s: int = Field(
        ..., ge=10, le=3600, description="Segundos entre cada sync (10..3600)"
    )


@router.put("/sheets/interval")
def sheets_set_interval(body: SheetsIntervalBody, request: Request) -> dict:
    """Actualiza la cadencia de sync a Sheets. Persiste y despierta el loop."""
    result = sheets_sync.update_sync_interval(body.sync_interval_s)
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=result.get("reason") or "invalid",
        )
    _publish(request, "iot.sheets", {"action": "interval", "value": body.sync_interval_s})
    return sheets_sync.status()


@router.post("/sheets/reformat")
def sheets_reformat(request: Request) -> dict:
    """Re-aplica el formato bonito (cabecera, freeze, fechas, bandas) al
    Sheet conectado. No mueve datos."""
    result = sheets_sync.reformat()
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error") or result.get("reason") or "reformat falló",
        )
    _publish(request, "iot.sheets", {"action": "reformat"})
    return result


@router.get("/sensor_log/xlsx")
def download_sensor_log_xlsx() -> Response:
    """Descarga el log como Excel formateado: hoja `all` con todo +
    una hoja por dispositivo."""
    try:
        data = sensor_log.read_xlsx_bytes()
    except Exception as e:
        log.exception("Generar XLSX falló")
        raise HTTPException(status_code=500, detail=f"XLSX: {safe_error_detail(e)}") from e
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="orion_iot_sensores.xlsx"'},
    )


# ── helpers ─────────────────────────────────────────────────────────────
def _publish(request: Request, topic: str, payload: dict) -> None:
    bus = getattr(request.app.state, "bus", None)
    if bus is None:
        return
    try:
        bus.publish(topic, payload)
    except Exception as e:
        log.debug("publish %s falló: %s", topic, e)
