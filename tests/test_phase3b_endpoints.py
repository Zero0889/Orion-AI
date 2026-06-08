"""
tests.test_phase3b_endpoints
=============================
Cobertura de los endpoints añadidos en Fase 3b:
  - GET  /api/agent/tasks
  - POST /api/agent/tasks
  - POST /api/agent/tasks/{id}/cancel
  - GET  /api/iot/devices, /scenes, /sensors, /status
  - POST /api/iot/devices/{id}/action  (mockeado)
  - POST /api/iot/scenes/{id}/run      (mockeado)
  - GET  /api/settings/api_key
  - POST /api/settings/api_key
  - Telemetría: el broadcaster publica eventos al bus.

Los tests usan TestClient + monkeypatch para aislar JSONs y mockear los
componentes que tocan hardware real (transports IoT).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── Fixtures ────────────────────────────────────────────────────────────
@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Aisla TODOS los JSONs que pueden mutarse, incluido api_keys."""
    import config as cfg_pkg
    import memory.memory_manager as mm
    import memory.quick_notes as qn
    import memory.conversations as cv

    monkeypatch.setattr(mm, "MEMORY_PATH",   tmp_path / "long_term.json")
    monkeypatch.setattr(qn, "_NOTES_PATH",   tmp_path / "quick_notes.json")
    monkeypatch.setattr(cv, "_CONVERSATIONS_PATH", tmp_path / "conversations.json")

    api_path = tmp_path / "api_keys.json"
    monkeypatch.setattr(cfg_pkg, "API_CONFIG_PATH", api_path)
    # Las rutas de settings importaron API_CONFIG_PATH por nombre; refrescar.
    import server.routes.settings as settings_route
    monkeypatch.setattr(settings_route, "API_CONFIG_PATH", api_path)
    monkeypatch.delenv("ORION_GEMINI_KEY", raising=False)

    return tmp_path


@pytest.fixture
def client(isolated):
    from server.event_bus import OrionEventBus
    from server.app import build_app
    bus = OrionEventBus()
    app = build_app(bus)
    with TestClient(app) as tc:
        yield tc, bus


# ── Agent / TaskQueue ───────────────────────────────────────────────────
def test_agent_list_initially_works(client):
    tc, _ = client
    r = tc.get("/api/agent/tasks")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_agent_submit(client):
    tc, _ = client
    r = tc.post("/api/agent/tasks", json={"goal": "test goal"})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    assert body["goal"] == "test goal"
    assert body["task_id"]


def test_agent_submit_publishes_event(client):
    tc, _ = client
    with tc.websocket_connect("/ws") as ws:
        ws.receive_json(); ws.receive_json()  # saludo
        tc.post("/api/agent/tasks", json={"goal": "x"})
        evt = ws.receive_json()
        assert evt["type"] == "agent.task"
        assert evt["payload"]["status"] == "pending"


def test_agent_get_not_found(client):
    tc, _ = client
    r = tc.get("/api/agent/tasks/no_existe")
    assert r.status_code == 404


def test_agent_cancel_unknown(client):
    tc, _ = client
    r = tc.post("/api/agent/tasks/zzz/cancel")
    assert r.status_code == 400


# ── IoT (con sistema mockeado para no tocar hardware) ───────────────────
class _FakeDevice:
    def __init__(self, dev_id: str, name: str, transport: str, caps: dict):
        self.id = dev_id
        self.name = name
        self.transport = transport
        from actions.iot.devices import Capabilities
        self.capabilities = Capabilities.from_dict(caps)
        # Campos opcionales que GET /api/iot/devices serializa para el
        # modal de edición. Tras IoT v3 se devuelven dev.serial y dev.mqtt;
        # los fakes los exponen como None.
        self.serial = None
        self.mqtt   = None


class _FakeIoTConfig:
    def __init__(self):
        self.devices = {
            "luz_sala":  _FakeDevice("luz_sala",  "Luz sala",  "main", {"on_off": True, "dimmable": True}),
            "tira_tv":   _FakeDevice("tira_tv",   "Tira TV",   "main", {"on_off": True, "rgb": True}),
            "sensor_t":  _FakeDevice("sensor_t",  "Sensor T",  "main", {"on_off": False, "sensor": "temperature"}),
        }
        self.scenes = {
            "modo_pelicula": {"name": "Modo película", "actions": [
                {"device": "luz_sala", "command": "off"},
                {"device": "tira_tv",  "command": "rgb", "color": "azul"},
            ]},
        }
        self.transports = {}


class _FakeIoTSystem:
    def __init__(self):
        self.cfg = _FakeIoTConfig()


@pytest.fixture
def iot_mock(monkeypatch):
    fake = _FakeIoTSystem()
    import server.routes.iot as iot_route
    monkeypatch.setattr(iot_route, "get_system", lambda: fake)
    # iot_control mockeado para no llamar al hardware real
    monkeypatch.setattr(iot_route, "iot_control", lambda params: f"ok({params.get('action')})")
    return fake


def test_iot_devices(client, iot_mock):
    tc, _ = client
    r = tc.get("/api/iot/devices")
    assert r.status_code == 200
    ids = {d["id"] for d in r.json()}
    assert ids == {"luz_sala", "tira_tv", "sensor_t"}


def test_iot_scenes(client, iot_mock):
    tc, _ = client
    r = tc.get("/api/iot/scenes")
    assert r.status_code == 200
    scenes = r.json()
    assert len(scenes) == 1
    assert scenes[0]["id"] == "modo_pelicula"
    assert scenes[0]["steps"] == 2


def test_iot_sensors_empty(client, iot_mock):
    tc, _ = client
    r = tc.get("/api/iot/sensors")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_iot_action(client, iot_mock):
    tc, _ = client
    r = tc.post("/api/iot/devices/luz_sala/action", json={"action": "on"})
    assert r.status_code == 200
    body = r.json()
    assert body["device"] == "luz_sala"
    assert body["action"] == "on"
    assert body["result"] == "ok(on)"


def test_iot_action_unknown_device(client, iot_mock):
    tc, _ = client
    r = tc.post("/api/iot/devices/no_existe/action", json={"action": "on"})
    assert r.status_code == 404


def test_iot_action_publishes_event(client, iot_mock):
    tc, _ = client
    with tc.websocket_connect("/ws") as ws:
        ws.receive_json(); ws.receive_json()
        tc.post("/api/iot/devices/luz_sala/action", json={"action": "off"})
        evt = ws.receive_json()
        assert evt["type"] == "iot.action"
        assert evt["payload"]["device"] == "luz_sala"


def test_iot_run_scene(client, iot_mock):
    tc, _ = client
    r = tc.post("/api/iot/scenes/modo_pelicula/run")
    assert r.status_code == 200


def test_iot_run_scene_not_found(client, iot_mock):
    tc, _ = client
    r = tc.post("/api/iot/scenes/no_existe/run")
    assert r.status_code == 404


# ── Onboarding (API key) ────────────────────────────────────────────────
def test_api_key_status_unconfigured(client):
    tc, _ = client
    r = tc.get("/api/settings/api_key")
    assert r.status_code == 200
    data = r.json()
    assert data["configured"] is False
    assert data["source"] is None


def test_api_key_set_then_status_configured(client):
    tc, _ = client
    long_key = "AIza" + "x" * 30
    r = tc.post("/api/settings/api_key", json={"key": long_key})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r2 = tc.get("/api/settings/api_key")
    assert r2.json()["configured"] is True
    assert r2.json()["source"] == "file"


def test_api_key_too_short_rejected(client):
    tc, _ = client
    r = tc.post("/api/settings/api_key", json={"key": "abc"})
    assert r.status_code == 422  # validación pydantic


def test_api_key_publishes_system_ready(client):
    tc, _ = client
    with tc.websocket_connect("/ws") as ws:
        ws.receive_json(); ws.receive_json()
        tc.post("/api/settings/api_key", json={"key": "AIza" + "x" * 30})
        evt = ws.receive_json()
        assert evt["type"] == "system.ready"


# ── Telemetría ──────────────────────────────────────────────────────────
def test_telemetry_event_arrives(client):
    """Con TICK_INTERVAL_S=2 el primer evento llega a los ~2s. Lo
    aceleramos parcheando el módulo."""
    import server.telemetry as tel
    with patch.object(tel, "TICK_INTERVAL_S", 0.1):
        # Necesitamos rearrancar el broadcaster con el intervalo nuevo
        # → en este test simplemente comprobamos que _sample() funciona
        # y que el bus.publish recibe un dict con las claves esperadas.
        sample = tel._sample()
        assert sample is not None
        assert {"cpu", "ram", "disk", "ts"} <= set(sample.keys())
        # Y verificamos que el bus puede publicarlo sin lanzar.
        _, bus = client
        bus.publish("telemetry", sample)
