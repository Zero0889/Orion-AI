"""
actions.iot.transports.mqtt_tx — Transporte MQTT (WiFi/IoT)
============================================================
Para dispositivos basados en ESP32/ESP8266 con firmware tipo Tasmota,
ESPHome, MicroPython o cualquier sketch que hable MQTT.

Bloque de config esperado
-------------------------
```json
"casa_mqtt": {
  "type": "mqtt",
  "host": "192.168.1.10",
  "port": 1883,
  "username": "",            // opcional
  "password": "",            // opcional
  "client_id": "orion",      // opcional
  "tls": false               // opcional
}
```

Bloque ``device.mqtt`` por capability
-------------------------------------
on_off (siempre)
  ``topic_command``  — topic donde se publican comandos.
  ``payload_on``     — payload para encender (default: ``"ON"``).
  ``payload_off``    — payload para apagar  (default: ``"OFF"``).

dimmable
  ``topic_brightness`` — topic separado para el brillo, **o**
  ``payload_format: "json"`` y entonces se publica ``{"state":"ON","brightness":N}``
  en ``topic_command``.

rgb
  Igual que dimming: ``topic_color`` separado o JSON unificado:
  ``{"state":"ON","color":{"r":255,"g":0,"b":0}}``.

sensor
  ``topic_state`` — topic al que se suscribe. Si el payload es JSON
  con el campo ``sensor_field``, se extrae; si no, se entrega el
  payload entero como string.

Esta implementación es **opt-in**: si ``paho-mqtt`` no está instalado,
la fábrica lo detecta y devuelve None sin romper el resto del sistema.
"""

from __future__ import annotations

import json
import threading

try:
    import paho.mqtt.client as mqtt  # type: ignore

    _PAHO_OK = True
except ImportError:
    _PAHO_OK = False

from ..devices import Device
from .base import Transport


class MQTTTransport(Transport):
    """Cliente MQTT compartido para todos los dispositivos del broker."""

    def __init__(self, transport_id: str, cfg: dict) -> None:
        super().__init__(transport_id, cfg)

        if not _PAHO_OK:
            raise RuntimeError("paho-mqtt no está instalado. Ejecuta: pip install paho-mqtt")

        self._connected = threading.Event()
        # device_id → topic_state que se ha suscrito (para sensores)
        self._subscriptions: dict[str, dict] = {}
        # topic → [device_id, ...] (varios devices pueden compartir un topic,
        # ej. temperatura y humedad ambos leyendo del JSON de un DHT)
        self._topic_to_device: dict[str, list[str]] = {}
        self._lock = threading.Lock()

        client_id = cfg.get("client_id", "orion")
        # paho 2.x cambió el constructor; nos quedamos en el compatible.
        try:
            self._client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
            )  # paho >= 2
        except AttributeError:
            self._client = mqtt.Client(client_id=client_id)  # paho < 2

        user = cfg.get("username") or ""
        pwd = cfg.get("password") or ""
        if user:
            self._client.username_pw_set(user, pwd)

        if cfg.get("tls"):
            try:
                self._client.tls_set()
            except Exception as e:
                print(f"[IoT-MQTT:{self.id}] TLS no se pudo configurar: {e}")

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        host = cfg.get("host", "localhost")
        port = int(cfg.get("port", 1883))
        try:
            self._client.connect_async(host, port, keepalive=30)
            self._client.loop_start()
            # No bloqueamos demasiado: si el broker está caído, esperamos
            # 3s y seguimos. El cliente reintenta solo en segundo plano.
            self._connected.wait(timeout=3.0)
            if self._connected.is_set():
                print(f"[IoT-MQTT:{self.id}] Conectado a {host}:{port}")
            else:
                print(f"[IoT-MQTT:{self.id}] Conectando a {host}:{port}... (en background)")
        except Exception as e:
            print(f"[IoT-MQTT:{self.id}] Error conectando a {host}:{port}: {e}")

    # ── Callbacks de paho ────────────────────────────────────────────────
    def _on_connect(self, client, userdata, flags, rc, *args):
        self._connected.set()
        # Re-suscribir tras reconexión
        with self._lock:
            for sub in self._subscriptions.values():
                topic = sub.get("topic")
                if topic:
                    client.subscribe(topic)

    def _on_disconnect(self, client, userdata, *args):
        self._connected.clear()
        print(f"[IoT-MQTT:{self.id}] Desconectado")

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        dev_ids = self._topic_to_device.get(topic) or []
        if not dev_ids:
            return
        try:
            raw_payload = msg.payload.decode("utf-8", errors="replace")
        except Exception:
            raw_payload = str(msg.payload)

        # Cada device puede extraer un campo distinto del mismo payload
        # (típico: un DHT que publica {"temperatura":..,"humedad":..}).
        for dev_id in dev_ids:
            sub = self._subscriptions.get(dev_id, {})
            field = sub.get("sensor_field")
            payload = raw_payload
            if field:
                try:
                    data = json.loads(raw_payload)
                    payload = str(data.get(field, raw_payload))
                except json.JSONDecodeError:
                    pass  # se queda como string
            self._dispatch_sensor(dev_id, payload)

    # ── Conexión ─────────────────────────────────────────────────────────
    def is_connected(self) -> bool:
        return self._connected.is_set()

    def close(self) -> None:
        try:
            self._client.loop_stop()
            self._client.disconnect()
            print(f"[IoT-MQTT:{self.id}] Cerrado")
        except Exception:
            pass

    # ── Helpers de payload ───────────────────────────────────────────────
    @staticmethod
    def _publish_json(topic: str, data: dict) -> str:
        return json.dumps(data)

    def _publish(self, topic: str, payload: str) -> bool:
        if not topic:
            return False
        try:
            info = self._client.publish(topic, payload, qos=0, retain=False)
            print(f"[IoT-MQTT:{self.id}] PUB {topic} = {payload}")
            return info.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            print(f"[IoT-MQTT:{self.id}] Error publicando en {topic}: {e}")
            return False

    # ── Envío ────────────────────────────────────────────────────────────
    def send(self, device: Device, kind: str, value=None) -> bool:
        cfg = device.mqtt or {}
        topic_cmd = cfg.get("topic_command")
        is_json = (cfg.get("payload_format") or "string").lower() == "json"

        if kind == "on":
            payload = cfg.get("payload_on", "ON")
            if is_json:
                payload = self._publish_json(topic_cmd, {"state": payload})
            return self._publish(topic_cmd, payload)

        if kind == "off":
            payload = cfg.get("payload_off", "OFF")
            if is_json:
                payload = self._publish_json(topic_cmd, {"state": payload})
            return self._publish(topic_cmd, payload)

        if kind == "dim":
            try:
                pct = max(0, min(100, int(value)))
            except (TypeError, ValueError):
                return False
            topic_b = cfg.get("topic_brightness")
            if topic_b:
                return self._publish(topic_b, str(pct))
            if is_json:
                # Tasmota/ESPHome esperan 0–255 normalmente; convertimos.
                brightness = round(pct * 255 / 100)
                return self._publish(
                    topic_cmd,
                    self._publish_json(topic_cmd, {"state": "ON", "brightness": brightness}),
                )
            print(f"[IoT-MQTT:{self.id}] '{device.id}' no tiene topic_brightness ni JSON")
            return False

        if kind == "rgb":
            try:
                r, g, b = value
                r, g, b = int(r), int(g), int(b)
            except Exception:
                return False
            r, g, b = (max(0, min(255, v)) for v in (r, g, b))
            topic_c = cfg.get("topic_color")
            if topic_c:
                return self._publish(topic_c, f"{r},{g},{b}")
            if is_json:
                return self._publish(
                    topic_cmd,
                    self._publish_json(
                        topic_cmd,
                        {"state": "ON", "color": {"r": r, "g": g, "b": b}},
                    ),
                )
            print(f"[IoT-MQTT:{self.id}] '{device.id}' no tiene topic_color ni JSON")
            return False

        if kind == "raw":
            return self._publish(topic_cmd, str(value or ""))

        return False

    # ── Sensores ─────────────────────────────────────────────────────────
    def register_sensor_listener(self, device_id: str, callback) -> None:
        super().register_sensor_listener(device_id, callback)

    def subscribe_device_state(self, device: Device) -> None:
        """El orquestador llama esto para suscribirse al ``topic_state`` del
        dispositivo. Si ya está suscrito, no hace nada."""
        topic = (device.mqtt or {}).get("topic_state")
        if not topic:
            return
        with self._lock:
            if device.id in self._subscriptions:
                return
            self._subscriptions[device.id] = {
                "topic": topic,
                "sensor_field": (device.mqtt or {}).get("sensor_field"),
            }
            self._topic_to_device.setdefault(topic, []).append(device.id)
            already_subscribed = len(self._topic_to_device[topic]) > 1
        try:
            if not already_subscribed:
                self._client.subscribe(topic)
            print(f"[IoT-MQTT:{self.id}] SUB {topic} ← {device.id}")
        except Exception as e:
            print(f"[IoT-MQTT:{self.id}] Error suscribiéndose a {topic}: {e}")
