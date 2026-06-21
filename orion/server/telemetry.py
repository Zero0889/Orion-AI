"""
server.telemetry — Broadcaster periódico de métricas del sistema
=================================================================
Publica eventos ``telemetry`` en el bus cada 2 segundos con:

    {
        "cpu":     0.42,        # 0..1
        "ram":     0.61,        # 0..1
        "disk":    0.55,        # 0..1
        "ts":      1748694321.4 # epoch
    }

Diseño
------
- Una sola coroutine ``run`` vinculada al lifespan de la app.
- Si no hay clientes WS suscritos, sigue calculando pero el bus ya
  descarta silenciosamente porque el ``_outbound_queue`` se drena.
  Aceptable: las llamadas a psutil son baratas en esta cadencia.
- Resistente a fallos: si psutil revienta puntualmente, loggea y sigue.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import psutil

from orion.config import BASE_DIR
from orion.core.logger import get_logger
import contextlib

log = get_logger("server.telemetry")

TICK_INTERVAL_S = 2.0


async def run(bus: Any) -> None:
    """Loop infinito. Se cancela limpiamente con CancelledError."""
    log.info("Telemetry broadcaster iniciado (cada %.1fs)", TICK_INTERVAL_S)
    # Primer cpu_percent siempre devuelve 0 — lo precalentamos.
    with contextlib.suppress(Exception):
        psutil.cpu_percent(interval=None)
    while True:
        try:
            await asyncio.sleep(TICK_INTERVAL_S)
            payload = _sample()
            if payload is not None:
                bus.publish("telemetry", payload)
        except asyncio.CancelledError:
            log.info("Telemetry broadcaster detenido")
            raise
        except Exception as e:
            log.debug("Telemetry tick error: %s", e)


# Disco a medir: el que aloja el proyecto. En Windows con C: como sistema
# y BASE_DIR en otra unidad, medir "/" daba un porcentaje irrelevante.
_DISK_PATH = str(BASE_DIR)


def _sample() -> dict | None:
    try:
        cpu = psutil.cpu_percent(interval=None) / 100.0
        vmem = psutil.virtual_memory()
        ram = vmem.percent / 100.0
        disk = psutil.disk_usage(_DISK_PATH).percent / 100.0
    except Exception as e:
        log.debug("psutil falló: %s", e)
        return None
    return {
        "cpu": round(cpu, 4),
        "ram": round(ram, 4),
        "disk": round(disk, 4),
        "ts": time.time(),
    }
