"""
tools/esp32_simulator.py — Simulador de dispositivo MQTT (ESP32 virtual)
=========================================================================
Hace de cuenta que eres un ESP32 con un foco/tira LED conectada. Sirve
para probar el camino completo de ORION → broker MQTT → dispositivo
sin tener hardware todavía.

Qué simula
----------
- Se conecta a un broker MQTT (Mosquitto local por defecto).
- Se suscribe al topic de comandos del dispositivo.
- Cuando recibe un comando, "aplica" el cambio al foco virtual y lo
  muestra en la terminal con colores ANSI (verde encendido, atenuado
  apagado, RGB con la tupla, una barra de brillo si es dimmable).
- Publica el estado nuevo al topic de state (igual que los dispositivos
  reales tipo Tasmota / ESPHome) para que ORION pueda leerlo después.

Acepta los dos formatos que ORION envía
---------------------------------------
- Strings sueltos:  "ON" / "OFF"
- JSON:             {"state":"ON"}
                    {"state":"ON","brightness":127}
                    {"state":"ON","color":{"r":255,"g":0,"b":0}}

Uso
---
    pip install paho-mqtt
    python tools/esp32_simulator.py                       # foco simple
    python tools/esp32_simulator.py --device tira --dim --rgb
    python tools/esp32_simulator.py --host 192.168.1.10 --port 1883
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
from datetime import datetime

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: paho-mqtt no está instalado. Ejecuta: pip install paho-mqtt")
    sys.exit(1)


# ── Colores ANSI (Windows 10+, PowerShell y terminales Unix los soportan) ──
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
DIM    = "\033[2m"


class VirtualDevice:
    """Representa el estado del foco virtual en memoria."""

    def __init__(self, device_id: str, base_topic: str,
                 rgb: bool, dimmable: bool):
        self.id            = device_id
        self.topic_command = f"{base_topic}/set"
        self.topic_state   = f"{base_topic}/state"
        self.rgb_capable   = rgb
        self.dim_capable   = dimmable

        # Estado del foco
        self.on         = False
        self.brightness = 100              # 0–100 %
        self.color      = (255, 255, 255)  # blanco

    # ── Render visual ────────────────────────────────────────────────────
    def render(self) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        if not self.on:
            print(f"{DIM}[{ts}] 💡 {self.id}: OFF{RESET}")
            return

        # Barra de brillo simple (0..20 caracteres)
        bar = "█" * max(1, self.brightness // 5)
        rgb_str = ""
        if self.rgb_capable:
            r, g, b = self.color
            rgb_str = f"RGB({r:3},{g:3},{b:3}) "

        dim_str = f"brillo={self.brightness:3}% {bar}" if self.dim_capable else ""

        print(
            f"{GREEN}[{ts}] 💡 {self.id}: ON  {rgb_str}{dim_str}{RESET}"
        )

    # ── Aplicar comando entrante ─────────────────────────────────────────
    def apply(self, payload: str) -> bool:
        """Aplica el payload al estado. Devuelve True si algo cambió."""
        payload = payload.strip()
        if not payload:
            return False

        # ── Caso 1: payload JSON (formato preferido por Tasmota/ESPHome) ──
        if payload.startswith("{"):
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                print(f"{RED}  ⚠ JSON inválido: {payload}{RESET}")
                return False

            state = str(data.get("state", "")).upper()
            if state == "ON":
                self.on = True
            elif state == "OFF":
                self.on = False

            if "brightness" in data and self.dim_capable:
                b = int(data["brightness"])
                # ORION envía 0–255 cuando hace JSON (estándar HA/Tasmota).
                # Aceptamos también 0–100 por si llegan de otro lado.
                self.brightness = round(b * 100 / 255) if b > 100 else b

            if "color" in data and self.rgb_capable:
                c = data["color"]
                try:
                    self.color = (int(c["r"]), int(c["g"]), int(c["b"]))
                except (KeyError, TypeError, ValueError):
                    print(f"{YELLOW}  ⚠ Color malformado: {c}{RESET}")
            return True

        # ── Caso 2: string simple "ON" / "OFF" / "N" / "r,g,b" ──
        up = payload.upper()
        if up == "ON":
            self.on = True
            return True
        if up == "OFF":
            self.on = False
            return True
        if up.isdigit() and self.dim_capable:
            self.brightness = max(0, min(100, int(up)))
            return True
        if "," in payload and self.rgb_capable:
            try:
                r, g, b = [int(x.strip()) for x in payload.split(",")[:3]]
                self.color = (
                    max(0, min(255, r)),
                    max(0, min(255, g)),
                    max(0, min(255, b)),
                )
                return True
            except ValueError:
                pass

        print(f"{YELLOW}  ↪ payload ignorado: {payload}{RESET}")
        return False

    # ── Estado a publicar (para que ORION pueda leerlo) ──────────────────
    def state_payload(self) -> str:
        data: dict = {"state": "ON" if self.on else "OFF"}
        if self.dim_capable:
            data["brightness"] = self.brightness
        if self.rgb_capable:
            r, g, b = self.color
            data["color"] = {"r": r, "g": g, "b": b}
        return json.dumps(data)


def _build_client(client_id: str):
    """paho 2.x cambió la API. Compatibilidad con 1.x y 2.x."""
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    except AttributeError:
        return mqtt.Client(client_id=client_id)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Simula un dispositivo IoT MQTT (ESP32 virtual)"
    )
    ap.add_argument("--device",     default="esp32_foco",
                    help="ID del dispositivo (default: esp32_foco)")
    ap.add_argument("--base-topic", default=None,
                    help="Topic base. Default: home/<device>")
    ap.add_argument("--host",       default="localhost",
                    help="Broker MQTT (default: localhost)")
    ap.add_argument("--port",       type=int, default=1883,
                    help="Puerto MQTT (default: 1883)")
    ap.add_argument("--user",       default="",
                    help="Usuario MQTT (opcional)")
    ap.add_argument("--password",   default="",
                    help="Contraseña MQTT (opcional)")
    ap.add_argument("--rgb",        action="store_true",
                    help="Dispositivo con capability RGB")
    ap.add_argument("--dim",        action="store_true",
                    help="Dispositivo con capability dimming")
    args = ap.parse_args()

    base = args.base_topic or f"home/{args.device}"
    dev  = VirtualDevice(args.device, base,
                         rgb=args.rgb, dimmable=args.dim)

    client = _build_client(f"sim-{args.device}")
    if args.user:
        client.username_pw_set(args.user, args.password)

    # ── Callbacks ────────────────────────────────────────────────────────
    def on_connect(c, *_):
        print(f"{BOLD}{GREEN}✓ Conectado a {args.host}:{args.port}{RESET}")
        print(f"   SUB  ← {CYAN}{dev.topic_command}{RESET}")
        print(f"   PUB  → {CYAN}{dev.topic_state}{RESET}")
        caps = []
        if dev.dim_capable: caps.append("dim")
        if dev.rgb_capable: caps.append("rgb")
        print(f"   Capacidades: {', '.join(caps) if caps else 'solo on/off'}\n")
        c.subscribe(dev.topic_command)
        c.publish(dev.topic_state, dev.state_payload(), retain=True)
        dev.render()

    def on_message(_c, _ud, msg):
        try:
            payload = msg.payload.decode("utf-8", errors="replace")
        except Exception:
            payload = str(msg.payload)
        print(f"{DIM}  PUB ← {msg.topic}  =  {payload}{RESET}")
        if dev.apply(payload):
            client.publish(dev.topic_state, dev.state_payload(), retain=True)
            dev.render()

    def on_disconnect(*_):
        print(f"{YELLOW}⚠ Desconectado del broker — reintentando...{RESET}")

    client.on_connect    = on_connect
    client.on_message    = on_message
    client.on_disconnect = on_disconnect

    # ── Conexión ─────────────────────────────────────────────────────────
    try:
        client.connect(args.host, args.port, keepalive=30)
    except Exception as e:
        print(f"{RED}✗ No se pudo conectar a {args.host}:{args.port}: {e}{RESET}")
        print("  ¿Tienes Mosquitto corriendo? Prueba en otra consola: mosquitto -v")
        sys.exit(1)

    # ── Salida limpia con Ctrl+C ─────────────────────────────────────────
    def _stop(*_):
        print(f"\n{DIM}Cerrando simulador.{RESET}")
        client.loop_stop()
        client.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)

    client.loop_forever()


if __name__ == "__main__":
    main()
