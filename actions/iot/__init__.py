"""
actions.iot — Subsistema domótico de O.R.I.O.N
==============================================
Reexporta ``iot_control`` desde :mod:`actions.iot.control` para mantener
el import histórico ``from actions.iot import iot_control`` (que es el
único que usa el resto del proyecto: ``main.py`` y ``agent/executor.py``).

Estructura del paquete
----------------------
- :mod:`actions.iot.devices`     — modelo Device + Capabilities
- :mod:`actions.iot.config`      — load/save/migración v1→v2
- :mod:`actions.iot.transports`  — Serial (Arduino) y MQTT (WiFi)
- :mod:`actions.iot.sensors`     — cache de lecturas
- :mod:`actions.iot.scenes`      — agrupar acciones en escenas
- :mod:`actions.iot.rules`       — interpretación NL (local + Gemini)
- :mod:`actions.iot.control`     — orquestador + entry point público
"""

from .control import iot_control, get_system

__all__ = ["iot_control", "get_system"]
