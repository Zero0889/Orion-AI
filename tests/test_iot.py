"""
tests.test_iot — Tests del subsistema domótico
==============================================
Cubre la lógica pura (sin Arduino, sin red, sin Gemini):

- Migración de iot_config.json v1 → v2
- Modelo Device + capabilities (require / opt-in)
- Parsers de rules (duración, porcentaje, color, find_device)
- Detección de intent local (sin llamar a Gemini)
- Cache de sensores

Para correrlo desde la raíz del repo::

    python -m unittest tests.test_iot -v
"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from actions.iot.config import IoTConfig, _is_v1, _migrate_v1_to_v2, load_config
from actions.iot.devices import Capabilities, Device
from actions.iot.rules import (
    detect_intent_local,
    find_device,
    normalize,
    parse_color,
    parse_duration,
    parse_percent,
)
from actions.iot.scenes import execute_scene, find_scene, list_scenes
from actions.iot.sensors import SensorCache

# ── Fixtures ────────────────────────────────────────────────────────────────


V1_SAMPLE = {
    "serial_port": "COM3",
    "baud_rate": 115200,
    "devices": {
        "foco_1": {"name": "foco 1", "cmd_on": "FOCO1_ON", "cmd_off": "FOCO1_OFF"},
        "foco_2": {"name": "foco 2", "cmd_on": "FOCO2_ON", "cmd_off": "FOCO2_OFF"},
    },
    "cmd_all_on": "TODOS_ON",
    "cmd_all_off": "TODOS_OFF",
}


def sample_v2_cfg() -> IoTConfig:
    """Config v2 con un foco simple, una tira RGB dimmable y un sensor."""
    return IoTConfig.from_dict(
        {
            "version": 2,
            "transports": {
                "main_arduino": {"type": "serial", "port": "COM1", "baud": 9600},
            },
            "devices": {
                "foco_1": {
                    "name": "foco 1",
                    "transport": "main_arduino",
                    "capabilities": {"on_off": True, "dimmable": False, "rgb": False},
                    "serial": {"cmd_on": "FOCO1_ON", "cmd_off": "FOCO1_OFF"},
                },
                "tira_led": {
                    "name": "tira led",
                    "transport": "main_arduino",
                    "capabilities": {"on_off": True, "dimmable": True, "rgb": True},
                    "serial": {
                        "cmd_on": "TIRA_ON",
                        "cmd_off": "TIRA_OFF",
                        "cmd_dim": "TIRA_DIM_{value}",
                        "cmd_rgb": "TIRA_RGB_{r}_{g}_{b}",
                    },
                },
                "temp_sala": {
                    "name": "termómetro sala",
                    "transport": "main_arduino",
                    "capabilities": {"on_off": False, "sensor": "temperature"},
                    "serial": {"sensor_prefix": "TEMP_SALA"},
                },
            },
            "global_commands": {"all_on": "TODOS_ON", "all_off": "TODOS_OFF"},
            "scenes": {
                "modo_pelicula": {
                    "name": "Modo Película",
                    "actions": [
                        {"device": "foco_1", "command": "off"},
                        {"device": "tira_led", "command": "rgb", "color": [50, 0, 100]},
                    ],
                },
            },
        }
    )


# ── Migración v1 → v2 ──────────────────────────────────────────────────────


class TestConfigMigration(unittest.TestCase):
    def test_detects_v1(self):
        self.assertTrue(_is_v1(V1_SAMPLE))
        self.assertFalse(_is_v1({"version": 2, "transports": {}, "devices": {}}))

    def test_migrate_v1_keeps_port_and_baud(self):
        v2 = _migrate_v1_to_v2(V1_SAMPLE)
        tx = v2["transports"]["main_arduino"]
        self.assertEqual(tx["port"], "COM3")
        self.assertEqual(tx["baud"], 115200)

    def test_migrate_v1_keeps_devices(self):
        v2 = _migrate_v1_to_v2(V1_SAMPLE)
        self.assertIn("foco_1", v2["devices"])
        self.assertEqual(v2["devices"]["foco_1"]["serial"]["cmd_on"], "FOCO1_ON")
        # Capabilities por defecto: on/off sí, dim/rgb no (opt-in)
        caps = v2["devices"]["foco_1"]["capabilities"]
        self.assertTrue(caps["on_off"])
        self.assertFalse(caps["dimmable"])
        self.assertFalse(caps["rgb"])

    def test_migrate_keeps_global_commands(self):
        v2 = _migrate_v1_to_v2(V1_SAMPLE)
        self.assertEqual(v2["global_commands"]["all_on"], "TODOS_ON")

    def test_load_v1_file_writes_v2_and_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "iot_config.json"
            p.write_text(json.dumps(V1_SAMPLE), encoding="utf-8")
            cfg = load_config(p)
            self.assertEqual(cfg.version, 2)
            # Backup creado
            self.assertTrue((p.parent / "iot_config.v1.bak.json").exists())
            # Archivo principal ya está en v2 en disco
            disk = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(disk["version"], 2)
            self.assertIn("transports", disk)

    def test_load_corrupt_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "iot_config.json"
            p.write_text("{ not valid json", encoding="utf-8")
            cfg = load_config(p)  # NO debe lanzar
            self.assertIsInstance(cfg, IoTConfig)
            # El archivo corrupto se queda como está (no se sobreescribe)
            self.assertTrue(p.read_text(encoding="utf-8").startswith("{ not"))


# ── Devices + capabilities ─────────────────────────────────────────────────


class TestDevices(unittest.TestCase):
    def test_default_capabilities_are_on_off_only(self):
        caps = Capabilities.from_dict({})
        self.assertTrue(caps.on_off)
        self.assertFalse(caps.dimmable)
        self.assertFalse(caps.rgb)
        self.assertIsNone(caps.sensor)

    def test_require_returns_error_message_when_missing(self):
        dev = Device(
            id="x",
            name="X",
            transport="t",
            capabilities=Capabilities(on_off=True, dimmable=False),
        )
        self.assertIsNone(dev.require("on_off"))
        msg = dev.require("dimmable")
        self.assertIsNotNone(msg)
        self.assertIn("X", msg)
        self.assertIn("intensidad", msg)

    def test_dimmable_opt_in_succeeds(self):
        dev = Device(
            id="x",
            name="X",
            transport="t",
            capabilities=Capabilities(dimmable=True),
        )
        self.assertIsNone(dev.require("dimmable"))


# ── Parsers de rules ───────────────────────────────────────────────────────


class TestRulesParsers(unittest.TestCase):
    def test_normalize_number_words(self):
        self.assertIn("30", normalize("treinta segundos"))
        self.assertIn("3", normalize("por tres segundos"))

    def test_parse_duration_seconds(self):
        n, clean = parse_duration("enciende foco por 30 segundos")
        self.assertEqual(n, 30)
        self.assertNotIn("30", clean)

    def test_parse_duration_minutes(self):
        n, _ = parse_duration("apaga en 2 minutos")
        self.assertEqual(n, 120)

    def test_parse_duration_none(self):
        n, _ = parse_duration("enciende el foco")
        self.assertIsNone(n)

    def test_parse_percent_with_symbol(self):
        self.assertEqual(parse_percent("pon la luz al 30%"), 30)

    def test_parse_percent_with_al(self):
        self.assertEqual(parse_percent("pon el foco al 75"), 75)

    def test_parse_percent_out_of_range(self):
        self.assertIsNone(parse_percent("pon al 200"))

    def test_parse_color_word(self):
        self.assertEqual(parse_color("luz azul"), (0, 0, 255))
        self.assertEqual(parse_color("color rojo"), (255, 0, 0))

    def test_parse_color_hex(self):
        self.assertEqual(parse_color("ponla en #ff00aa"), (255, 0, 170))

    def test_parse_color_none(self):
        self.assertIsNone(parse_color("enciende el foco"))


# ── Resolución de dispositivo y detect_intent_local ────────────────────────


class TestIntentLocal(unittest.TestCase):
    def setUp(self):
        self.cfg = sample_v2_cfg()

    def test_find_device_by_name(self):
        d = find_device("enciende la tira led", self.cfg)
        self.assertIsNotNone(d)
        self.assertEqual(d.id, "tira_led")

    def test_find_device_prefers_longer_match(self):
        # "foco" matchearía pero "tira led" es más largo
        d = find_device("prende la tira led", self.cfg)
        self.assertEqual(d.id, "tira_led")

    def test_intent_simple_on(self):
        i = detect_intent_local("enciende el foco 1", self.cfg)
        self.assertEqual(i["action"], "on")
        self.assertEqual(i["device"], "foco_1")

    def test_intent_simple_off(self):
        i = detect_intent_local("apaga el foco 1", self.cfg)
        self.assertEqual(i["action"], "off")
        self.assertEqual(i["device"], "foco_1")

    def test_intent_all_off(self):
        i = detect_intent_local("apaga todo", self.cfg)
        self.assertEqual(i["action"], "all_off")

    def test_intent_all_on_dark(self):
        i = detect_intent_local("está muy oscuro", self.cfg)
        self.assertEqual(i["action"], "all_on")

    def test_intent_dim_on_dimmable(self):
        i = detect_intent_local("pon la tira al 30%", self.cfg)
        self.assertEqual(i["action"], "dim")
        self.assertEqual(i["device"], "tira_led")
        self.assertEqual(i["value"], 30)

    def test_intent_dim_falls_back_when_not_dimmable(self):
        # foco_1 no es dimmable → no debe devolver "dim"
        i = detect_intent_local("pon el foco 1 al 50%", self.cfg)
        self.assertNotEqual(i and i.get("action"), "dim")

    def test_intent_rgb_on_rgb_device(self):
        i = detect_intent_local("pon la tira azul", self.cfg)
        self.assertEqual(i["action"], "rgb")
        self.assertEqual(i["device"], "tira_led")
        self.assertEqual(list(i["color"]), [0, 0, 255])

    def test_intent_rgb_falls_back_when_not_rgb(self):
        i = detect_intent_local("pon el foco 1 azul", self.cfg)
        self.assertNotEqual(i and i.get("action"), "rgb")

    def test_intent_scene_by_name(self):
        i = detect_intent_local("activa modo película", self.cfg)
        self.assertEqual(i["action"], "scene")
        self.assertEqual(i["scene"], "modo_pelicula")


# ── Escenas ────────────────────────────────────────────────────────────────


class TestScenes(unittest.TestCase):
    def setUp(self):
        self.cfg = sample_v2_cfg()

    def test_list_scenes(self):
        listed = list_scenes(self.cfg)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["id"], "modo_pelicula")
        self.assertEqual(listed[0]["steps"], 2)

    def test_find_scene_by_id_exact(self):
        found = find_scene(self.cfg, "modo_pelicula")
        self.assertIsNotNone(found)
        self.assertEqual(found[0], "modo_pelicula")

    def test_find_scene_by_name_case_insensitive(self):
        found = find_scene(self.cfg, "Modo Película")
        self.assertIsNotNone(found)

    def test_find_scene_partial(self):
        found = find_scene(self.cfg, "película")
        self.assertIsNotNone(found)

    def test_find_scene_none(self):
        self.assertIsNone(find_scene(self.cfg, "inexistente"))

    def test_execute_scene_calls_runner_per_step(self):
        calls = []

        def fake_runner(device, command, **kw):
            calls.append((device, command, kw))
            return f"{device}:{command} ok"

        scene = self.cfg.scenes["modo_pelicula"]
        result = execute_scene(scene, fake_runner)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], ("foco_1", "off", {}))
        self.assertEqual(calls[1], ("tira_led", "rgb", {"color": [50, 0, 100]}))
        self.assertIn("2 pasos", result)

    def test_execute_scene_continues_on_failure(self):
        def flaky(device, command, **kw):
            if device == "foco_1":
                raise RuntimeError("offline")
            return "ok"

        scene = self.cfg.scenes["modo_pelicula"]
        result = execute_scene(scene, flaky)
        self.assertIn("1 con error", result)
        self.assertIn("1 pasos OK", result)


# ── Cache de sensores ──────────────────────────────────────────────────────


class TestSensorCache(unittest.TestCase):
    def test_update_and_get(self):
        c = SensorCache()
        c.update("temp_sala", "24.5")
        r = c.get("temp_sala")
        self.assertIsNotNone(r)
        self.assertEqual(r.value, "24.5")
        self.assertAlmostEqual(r.numeric(), 24.5)

    def test_age_seconds(self):
        c = SensorCache()
        c.update("x", "1")
        time.sleep(0.05)
        r = c.get("x")
        self.assertGreater(r.age_seconds(), 0)
        self.assertLess(r.age_seconds(), 1)

    def test_numeric_handles_comma_decimal(self):
        c = SensorCache()
        c.update("x", "23,7")
        self.assertAlmostEqual(c.get("x").numeric(), 23.7)

    def test_numeric_none_when_not_a_number(self):
        c = SensorCache()
        c.update("x", "MOTION")
        self.assertIsNone(c.get("x").numeric())


if __name__ == "__main__":
    unittest.main()
