"""
tools/esp32_sensor_simulator.py — ESP32 virtual de SENSORES
============================================================
Simula el ESP32-S3 que tendrás conectado a DHT22 + LDR.
Publica los mismos topics MQTT con los mismos payloads que el sketch
real de wokwi/sensores/sketch.ino, así puedes probar todo el flujo
ORION ← MQTT ← sensores sin necesitar Wokwi ni hardware todavía.

Topics publicados (cada 5 s):
    orion/zahir/esp_sensores/dht  → {"temperatura":24.1,"humedad":55.3}
    orion/zahir/esp_sensores/ldr  → "742"   (0..4095 simulando ADC)

Los valores varían suavemente (random walk) para que se vea bonito
en el dashboard, en lugar de ser constantes.

Uso
---
    pip install paho-mqtt
    python tools/esp32_sensor_simulator.py
    python tools/esp32_sensor_simulator.py --interval 2   # más rápido
    python tools/esp32_sensor_simulator.py --host localhost
"""

from __future__ import annotations

import argparse
import json
import random
import signal
import sys
import time
from datetime import datetime

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: paho-mqtt no está instalado. Ejecuta: pip install paho-mqtt")
    sys.exit(1)


# ── Colores ANSI ───────────────────────────────────────────────────────────
RESET, BOLD, GREEN, CYAN, DIM, YELLOW, RED = (
    "\033[0m", "\033[1m", "\033[92m", "\033[96m", "\033[2m", "\033[93m", "\033[91m"
)


def _build_client(client_id: str):
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    except AttributeError:
        return mqtt.Client(client_id=client_id)


def main() -> None:
    ap = argparse.ArgumentParser(description="ESP32 virtual de sensores (DHT22 + LDR)")
    ap.add_argument("--host",     default="broker.hivemq.com")
    ap.add_argument("--port",     type=int, default=1883)
    ap.add_argument("--base",     default="orion/zahir/esp_sensores",
                    help="Prefijo de topics (default: orion/zahir/esp_sensores)")
    ap.add_argument("--interval", type=float, default=5.0,
                    help="Segundos entre publicaciones (default: 5)")
    args = ap.parse_args()

    topic_dht = f"{args.base}/dht"
    topic_ldr = f"{args.base}/ldr"

    client = _build_client("orion-esp-sensores-sim")

    def on_connect(c, *_):
        print(f"{BOLD}{GREEN}✓ Conectado a {args.host}:{args.port}{RESET}")
        print(f"   PUB → {CYAN}{topic_dht}{RESET}  cada {args.interval}s")
        print(f"   PUB → {CYAN}{topic_ldr}{RESET}  cada {args.interval}s")
        print(f"{DIM}   (Ctrl+C para parar){RESET}\n")

    def on_disconnect(*_):
        print(f"{YELLOW}⚠ Desconectado del broker — reintentando...{RESET}")

    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect

    try:
        client.connect(args.host, args.port, keepalive=30)
    except Exception as e:
        print(f"{RED}✗ No se pudo conectar a {args.host}:{args.port}: {e}{RESET}")
        sys.exit(1)

    client.loop_start()

    # Estado inicial de los "sensores"
    temperatura = 23.5
    humedad     = 50.0
    luz         = 2000  # 0..4095

    def _stop(*_):
        print(f"\n{DIM}Cerrando simulador.{RESET}")
        client.loop_stop()
        client.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)

    try:
        while True:
            # Random walk realista
            temperatura = max(15.0, min(35.0,
                temperatura + random.uniform(-0.3, 0.3)))
            humedad = max(20.0, min(95.0,
                humedad + random.uniform(-1.5, 1.5)))
            luz = max(0, min(4095,
                luz + random.randint(-150, 150)))

            payload_dht = json.dumps({
                "temperatura": round(temperatura, 1),
                "humedad":     round(humedad, 1),
            })
            payload_ldr = str(luz)

            ts = datetime.now().strftime("%H:%M:%S")
            client.publish(topic_dht, payload_dht)
            client.publish(topic_ldr, payload_ldr)
            print(f"{DIM}[{ts}]{RESET} "
                  f"{CYAN}DHT{RESET} {payload_dht}   "
                  f"{CYAN}LDR{RESET} {payload_ldr}")

            time.sleep(args.interval)
    except KeyboardInterrupt:
        _stop()


if __name__ == "__main__":
    main()
