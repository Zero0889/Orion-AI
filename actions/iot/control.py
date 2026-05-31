"""
actions.iot.control — Orquestador y entry point ``iot_control``
================================================================
Pega todas las piezas (config + devices + transports + rules + sensors
+ scenes) tras una sola función ``iot_control(parameters, player, speak)``
que el modelo Gemini Live llama como herramienta.

Compatibilidad
--------------
La firma y los ``action`` originales (``on / off / all_on / all_off /
timed / status / auto``) siguen funcionando igual que en el ``iot.py``
viejo. Encima se añaden:

- ``dim``           — intensidad 0-100 (requiere device.dimmable)
- ``rgb``           — color (requiere device.rgb)
- ``scene``         — ejecuta una escena por id o nombre
- ``read_sensor``   — última lectura cacheada del sensor del dispositivo
- ``list_devices``  — resumen de dispositivos y capabilities
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from .config import IoTConfig, load_config
from .devices import Device
from .rules import (
    detect_intent_local, detect_intent_with_gemini,
    normalize, parse_duration, parse_color, parse_percent,
)
from .scenes import execute_scene, find_scene, list_scenes
from .sensors import get_cache
from .transports import get_transport
from .transports.serial_tx import SerialTransport
from .transports.mqtt_tx import MQTTTransport


# ── Singleton del sistema ────────────────────────────────────────────────────


class IoTSystem:
    """Wraps config + transports + sensores en un objeto reutilizable.

    Se inicializa lazy en :func:`get_system`. Re-cargar la config (tras
    editar desde la UI) se hará con :meth:`reload` (no implementado en
    esta primera entrega — pendiente cuando llegue el UI dashboard).
    """

    def __init__(self) -> None:
        self.cfg = load_config()
        self._init_transports()
        self._wire_sensors()

    # ── Setup interno ────────────────────────────────────────────────────
    def _init_transports(self) -> None:
        for tid, tcfg in self.cfg.transports.items():
            # Mete los global_commands del config raíz dentro del cfg del
            # transporte serial, para que SerialTransport.broadcast()
            # pueda usarlos sin saber del config global.
            if tcfg.get("type") == "serial":
                tcfg.setdefault("all_on",  self.cfg.global_commands.get("all_on"))
                tcfg.setdefault("all_off", self.cfg.global_commands.get("all_off"))
            get_transport(tid, tcfg)  # construye y cachea

    def _wire_sensors(self) -> None:
        cache = get_cache()
        for dev in self.cfg.devices.values():
            if not dev.capabilities.sensor:
                continue
            t = get_transport(dev.transport, self.cfg.transports.get(dev.transport, {}))
            if t is None:
                continue
            t.register_sensor_listener(
                dev.id,
                lambda dev_id, raw: cache.update(dev_id, raw),
            )
            if isinstance(t, SerialTransport):
                prefix = (dev.serial or {}).get("sensor_prefix") or dev.id.upper()
                t.register_sensor_prefix(prefix, dev.id)
            elif isinstance(t, MQTTTransport):
                t.subscribe_device_state(dev)

    # ── Operaciones ──────────────────────────────────────────────────────
    def transport_for(self, dev: Device):
        return get_transport(dev.transport, self.cfg.transports.get(dev.transport, {}))


_system: Optional[IoTSystem] = None
_system_lock = threading.Lock()


def get_system() -> IoTSystem:
    """Devuelve la instancia única del sistema IoT (lazy)."""
    global _system
    with _system_lock:
        if _system is None:
            _system = IoTSystem()
        return _system


# ── Helpers de ejecución por acción ─────────────────────────────────────────


def _exec_on_off(sys: IoTSystem, dev: Device, on: bool) -> str:
    err = dev.require("on_off")
    if err:
        return err
    t = sys.transport_for(dev)
    if t is None:
        return f"Transport '{dev.transport}' no disponible."
    if t.send(dev, "on" if on else "off"):
        verb = "encendido" if on else "apagado"
        return f"{dev.name.capitalize()} {verb}."
    return f"No se pudo enviar el comando a {dev.name}."


def _exec_broadcast(sys: IoTSystem, on: bool) -> str:
    """Encender/apagar TODO: itera los transportes que lo soporten y, en
    los que no, manda on/off por dispositivo uno a uno."""
    ok_total, fail_total = 0, 0
    for tid, tcfg in sys.cfg.transports.items():
        t = get_transport(tid, tcfg)
        if t is None:
            continue
        if t.broadcast("on" if on else "off"):
            ok_total += 1
            continue
        # Fallback: enviar a cada dispositivo on/off de este transporte
        for d in sys.cfg.devices_by_transport(tid):
            if d.capabilities.on_off and t.send(d, "on" if on else "off"):
                ok_total += 1
            else:
                fail_total += 1

    if ok_total == 0:
        return "No se pudo enviar el comando global."
    verb = "encendidos" if on else "apagados"
    return f"Todos los focos {verb}."


def _exec_dim(sys: IoTSystem, dev: Device, value) -> str:
    err = dev.require("dimmable")
    if err:
        return err
    try:
        pct = max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return "El nivel de intensidad debe ser un número entre 0 y 100."
    t = sys.transport_for(dev)
    if t is None or not t.send(dev, "dim", pct):
        return f"No se pudo regular la intensidad de {dev.name}."
    return f"{dev.name.capitalize()} al {pct}%."


def _exec_rgb(sys: IoTSystem, dev: Device, color) -> str:
    err = dev.require("rgb")
    if err:
        return err
    # color puede venir como list/tuple o como string ("rojo", "#ff00aa")
    rgb: Optional[tuple[int, int, int]] = None
    if isinstance(color, (list, tuple)) and len(color) == 3:
        try:
            rgb = (int(color[0]), int(color[1]), int(color[2]))
        except (TypeError, ValueError):
            rgb = None
    elif isinstance(color, str):
        rgb = parse_color(color)

    if rgb is None:
        return "No reconocí el color. Prueba con 'rojo', 'azul', '#ff00aa' o [255,0,170]."

    t = sys.transport_for(dev)
    if t is None or not t.send(dev, "rgb", rgb):
        return f"No se pudo cambiar el color de {dev.name}."
    return f"{dev.name.capitalize()} en color RGB({rgb[0]},{rgb[1]},{rgb[2]})."


def _exec_scene(sys: IoTSystem, query: str) -> str:
    found = find_scene(sys.cfg, query)
    if not found:
        scenes = list_scenes(sys.cfg)
        if not scenes:
            return "No hay escenas configuradas todavía."
        names = ", ".join(s["name"] for s in scenes)
        return f"No encontré la escena '{query}'. Disponibles: {names}."

    _sid, scene = found

    def runner(device_id: str, command: str, **kwargs) -> str:
        return _dispatch_action(sys, command, {"device": device_id, **kwargs})

    return execute_scene(scene, runner)


def _exec_read_sensor(sys: IoTSystem, dev: Device) -> str:
    err = dev.require("sensor")
    if err:
        return err
    reading = get_cache().get(dev.id)
    if reading is None:
        return f"Aún no hay lecturas de {dev.name}."
    age = int(reading.age_seconds())
    unit_hint = dev.capabilities.sensor or ""
    if age < 60:
        when = f"hace {age}s"
    elif age < 3600:
        when = f"hace {age // 60} min"
    else:
        when = f"hace {age // 3600} h"
    return f"{dev.name.capitalize()} [{unit_hint}] = {reading.value} ({when})."


def _exec_list_devices(sys: IoTSystem) -> str:
    if not sys.cfg.devices:
        return "No hay dispositivos configurados."
    lines = []
    for d in sys.cfg.devices.values():
        caps = []
        if d.capabilities.on_off:   caps.append("on/off")
        if d.capabilities.dimmable: caps.append("dim")
        if d.capabilities.rgb:      caps.append("rgb")
        if d.capabilities.sensor:   caps.append(f"sensor:{d.capabilities.sensor}")
        lines.append(f"  • {d.name} (id={d.id}, transport={d.transport}, caps={', '.join(caps) or 'ninguna'})")
    return "Dispositivos IoT:\n" + "\n".join(lines)


def _exec_status(sys: IoTSystem) -> str:
    parts = [f"{len(sys.cfg.devices)} dispositivo(s) en {len(sys.cfg.transports)} transporte(s)."]
    for tid, tcfg in sys.cfg.transports.items():
        t = get_transport(tid, tcfg)
        if t:
            parts.append(t.describe())
        else:
            parts.append(f"{tid} [{tcfg.get('type')}] no disponible")
    return "\n".join(parts)


# ── Timer de auto-off ───────────────────────────────────────────────────────


def _schedule_auto_off(sys: IoTSystem, dev_ids: list[str], duration: int,
                      speak: Optional[Callable] = None) -> None:
    """Apaga ``dev_ids`` después de ``duration`` segundos en un hilo."""
    if duration <= 0 or not dev_ids:
        return

    def _worker():
        if speak:
            if duration >= 60:
                mins = duration // 60
                speak(f"Se apagarán automáticamente en {mins} minuto{'s' if mins > 1 else ''}.")
            else:
                u = "segundo" if duration == 1 else "segundos"
                speak(f"Se apagarán automáticamente en {duration} {u}.")
        time.sleep(duration)
        for did in dev_ids:
            dev = sys.cfg.get_device(did)
            if dev and dev.capabilities.on_off:
                t = sys.transport_for(dev)
                if t:
                    t.send(dev, "off")
        if speak:
            speak("Focos apagados automáticamente.")

    threading.Thread(target=_worker, daemon=True, name="IoT-AutoOff").start()


# ── Dispatcher central ──────────────────────────────────────────────────────


def _dispatch_action(sys: IoTSystem, action: str, params: dict,
                    speak: Optional[Callable] = None) -> str:
    """Núcleo: ejecuta UNA acción ya resuelta (sin natural language)."""
    action = (action or "").lower().strip()

    if action == "status":
        return _exec_status(sys)

    if action == "list_devices":
        return _exec_list_devices(sys)

    if action == "all_on":
        msg = _exec_broadcast(sys, on=True)
        duration = params.get("duration")
        if duration:
            ids = [d.id for d in sys.cfg.devices.values() if d.capabilities.on_off]
            _schedule_auto_off(sys, ids, int(duration), speak)
            msg += f" Se apagarán en {int(duration)}s."
        return msg

    if action == "all_off":
        return _exec_broadcast(sys, on=False)

    if action == "scene":
        return _exec_scene(sys, params.get("scene") or params.get("name") or "")

    # Acciones que requieren un dispositivo concreto
    dev_id = params.get("device") or ""
    dev = sys.cfg.get_device(dev_id)
    if dev is None and dev_id:
        # Permitir "device": "all" como atajo histórico
        if dev_id.lower() == "all":
            return _exec_broadcast(sys, on=(action == "on"))
        return f"Dispositivo '{dev_id}' no encontrado. Usa list_devices para ver los disponibles."

    if action in ("on", "off") and dev:
        msg = _exec_on_off(sys, dev, on=(action == "on"))
        duration = params.get("duration")
        if action == "on" and duration:
            _schedule_auto_off(sys, [dev.id], int(duration), speak)
            msg += f" Se apagará en {int(duration)}s."
        return msg

    if action == "timed" and dev:
        # alias histórico: "timed" = "on" con duration obligatoria
        msg = _exec_on_off(sys, dev, on=True)
        duration = int(params.get("duration") or 30)
        _schedule_auto_off(sys, [dev.id], duration, speak)
        return f"{msg} Se apagará en {duration}s."

    if action == "dim" and dev:
        return _exec_dim(sys, dev, params.get("value"))

    if action == "rgb" and dev:
        return _exec_rgb(sys, dev, params.get("color"))

    if action == "read_sensor" and dev:
        return _exec_read_sensor(sys, dev)

    return f"Acción '{action}' no reconocida o falta el parámetro 'device'."


# ── Entry point público ─────────────────────────────────────────────────────


def iot_control(parameters: dict, player=None, speak: Optional[Callable] = None) -> str:
    """Punto de entrada que Gemini Live invoca como herramienta.

    Acciones soportadas (todas opcionales — el default es 'auto')::

        on, off, all_on, all_off, timed,
        dim, rgb, scene, read_sensor,
        list_devices, status, auto

    Si ``action == "auto"`` se interpreta ``description`` con reglas
    locales y, si fallan, con Gemini.
    """
    parameters = parameters or {}
    action      = (parameters.get("action") or "auto").lower().strip()
    description = (parameters.get("description") or "").strip()

    try:
        sys = get_system()
    except Exception as e:
        return f"Sistema IoT no disponible: {e}"

    if player:
        player.write_log(f"[IoT] action={action} params={parameters}")

    # ── Modo automático: lenguaje natural → intent → dispatch ─────────────
    if action == "auto":
        if not description:
            return "No se proporcionó descripción del comando IoT."

        intent = detect_intent_local(description, sys.cfg)
        if intent is None:
            print("[IoT] Sin regla local, consultando Gemini...")
            intent = detect_intent_with_gemini(description, sys.cfg)
        if intent is None:
            return ("No pude interpretar la orden. Intenta ser más específico, "
                    "por ejemplo: 'enciende el foco 1' o 'pon la tira al 30%'.")

        return _dispatch_action(sys, intent.get("action"), intent, speak=speak)

    # ── Modo explícito (LLM o programático) ───────────────────────────────
    return _dispatch_action(sys, action, parameters, speak=speak)
