"""
actions.iot.transports.serial_tx — Transporte por puerto serie (Arduino)
=========================================================================
Implementa :class:`Transport` sobre ``pyserial``. Es la evolución del
``iot.py`` original: ahora soporta dimming (PWM), RGB y lectura de
sensores en un hilo de fondo.

Bloque de config esperado
-------------------------
```json
"main_arduino": {
  "type": "serial",
  "port": "COM1",
  "baud": 9600,
  "all_on":  "TODOS_ON",      // opcional, para broadcast
  "all_off": "TODOS_OFF"      // opcional
}
```

Bloque ``device.serial`` esperado por capability
------------------------------------------------
on_off (siempre)
  ``cmd_on`` / ``cmd_off``       — strings literales que se envían tal cual.

dimmable
  ``cmd_dim`` — template con ``{value}`` (0–100). Ej: ``"FOCO1_DIM_{value}"``.

rgb
  ``cmd_rgb`` — template con ``{r}``, ``{g}``, ``{b}``.
  Ej: ``"FOCO1_RGB_{r}_{g}_{b}"``.

sensor
  ``sensor_prefix`` — prefijo de las líneas que emite el Arduino.
  Ej: si pones ``"TEMP_SALA"`` y el Arduino imprime ``"TEMP_SALA:24.5"``,
  la lectura ``"24.5"`` se entrega al cache de sensores.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

try:
    import serial  # type: ignore
    _PYSERIAL_OK = True
except ImportError:
    _PYSERIAL_OK = False

from .base import Transport
from ..devices import Device


class SerialTransport(Transport):
    """Conexión USB-Serial a un Arduino (u otro micro)."""

    def __init__(self, transport_id: str, cfg: dict) -> None:
        super().__init__(transport_id, cfg)

        if not _PYSERIAL_OK:
            raise RuntimeError(
                "pyserial no está instalado. Ejecuta: pip install pyserial"
            )

        self._conn: Optional["serial.Serial"] = None
        self._send_lock = threading.Lock()
        self._reader_thread: Optional[threading.Thread] = None
        self._reader_stop = threading.Event()
        # Prefijos registrados: prefix → device_id
        self._sensor_prefixes: dict[str, str] = {}

        self._open_port()

    # ── Conexión ─────────────────────────────────────────────────────────
    def _open_port(self) -> None:
        port = self.cfg.get("port", "COM1")
        baud = int(self.cfg.get("baud", 9600))
        try:
            self._conn = serial.Serial(port, baud, timeout=1)
            # Damos al Arduino tiempo para resetearse tras abrir el puerto,
            # PERO fuera del lock (estamos en __init__, nada compite todavía).
            time.sleep(2)
            print(f"[IoT-Serial:{self.id}] Conectado a {port} @ {baud}")
        except Exception as e:
            print(f"[IoT-Serial:{self.id}] Error abriendo {port}: {e}")
            self._conn = None

    def is_connected(self) -> bool:
        return self._conn is not None and self._conn.is_open

    def close(self) -> None:
        self._reader_stop.set()
        with self._send_lock:
            if self._conn and self._conn.is_open:
                try:
                    self._conn.close()
                    print(f"[IoT-Serial:{self.id}] Cerrado")
                except Exception:
                    pass
            self._conn = None

    # ── Envío ────────────────────────────────────────────────────────────
    def _write_raw(self, cmd: str) -> bool:
        if not self.is_connected():
            print(f"[IoT-Serial:{self.id}] No conectado, descarto '{cmd}'")
            return False
        cmd = cmd.strip()
        if not cmd:
            return False
        try:
            with self._send_lock:
                self._conn.write((cmd + "\n").encode("utf-8"))
            print(f"[IoT-Serial:{self.id}] >>> {cmd}")
            return True
        except Exception as e:
            print(f"[IoT-Serial:{self.id}] Error enviando '{cmd}': {e}")
            return False

    def send(self, device: Device, kind: str, value=None) -> bool:
        sercfg = device.serial or {}

        if kind == "on":
            cmd = sercfg.get("cmd_on")
            return self._write_raw(cmd) if cmd else False

        if kind == "off":
            cmd = sercfg.get("cmd_off")
            return self._write_raw(cmd) if cmd else False

        if kind == "dim":
            template = sercfg.get("cmd_dim")
            if not template:
                print(f"[IoT-Serial:{self.id}] '{device.id}' no tiene cmd_dim")
                return False
            try:
                pct = max(0, min(100, int(value)))
            except (TypeError, ValueError):
                return False
            return self._write_raw(template.format(value=pct))

        if kind == "rgb":
            template = sercfg.get("cmd_rgb")
            if not template:
                print(f"[IoT-Serial:{self.id}] '{device.id}' no tiene cmd_rgb")
                return False
            try:
                r, g, b = value
                r, g, b = int(r), int(g), int(b)
            except Exception:
                return False
            r = max(0, min(255, r))
            g = max(0, min(255, g))
            b = max(0, min(255, b))
            return self._write_raw(template.format(r=r, g=g, b=b))

        if kind == "raw":
            return self._write_raw(str(value or ""))

        print(f"[IoT-Serial:{self.id}] kind desconocido: {kind}")
        return False

    def broadcast(self, kind: str) -> bool:
        if kind == "on":
            cmd = self.cfg.get("all_on")
        elif kind == "off":
            cmd = self.cfg.get("all_off")
        else:
            return False
        return bool(cmd) and self._write_raw(cmd)

    # ── Sensores ─────────────────────────────────────────────────────────
    def register_sensor_listener(self, device_id: str, callback) -> None:
        super().register_sensor_listener(device_id, callback)
        self._maybe_start_reader()

    def register_sensor_prefix(self, prefix: str, device_id: str) -> None:
        """El orquestador llama esto al cargar la config para que sepamos
        qué línea del puerto serial corresponde a qué dispositivo-sensor.
        """
        if not prefix:
            return
        self._sensor_prefixes[prefix.upper()] = device_id
        self._maybe_start_reader()

    def _maybe_start_reader(self) -> None:
        if self._reader_thread and self._reader_thread.is_alive():
            return
        if not self._sensor_prefixes:
            return  # nada que leer
        self._reader_stop.clear()
        self._reader_thread = threading.Thread(
            target=self._read_loop, daemon=True,
            name=f"IoT-Serial-Reader-{self.id}",
        )
        self._reader_thread.start()

    def _read_loop(self) -> None:
        print(f"[IoT-Serial:{self.id}] Reader iniciado ({len(self._sensor_prefixes)} sensores)")
        while not self._reader_stop.is_set():
            try:
                if not self.is_connected():
                    time.sleep(0.5)
                    continue
                # readline() es bloqueante con timeout=1s, así que no necesi-
                # tamos sleep extra. NO se mezcla con _send_lock porque la
                # lectura usa su propio buffer en pyserial.
                line = self._conn.readline().decode("utf-8", errors="replace").strip()
                if not line or ":" not in line:
                    continue
                prefix, _, value = line.partition(":")
                dev_id = self._sensor_prefixes.get(prefix.upper())
                if dev_id:
                    self._dispatch_sensor(dev_id, value.strip())
            except Exception as e:
                print(f"[IoT-Serial:{self.id}] reader error: {e}")
                time.sleep(1)
        print(f"[IoT-Serial:{self.id}] Reader detenido")
