"""
Tests del generador de resúmenes diarios (Fase 4 supergrupo).

Cubren:
  - Resumen con DB vacía → menciona "Sin eventos hoy".
  - Resumen con eventos GRANTED y DENIED → counts correctos.
  - Entradas del día agrupadas por usuario, ordenadas por hora del
    primer ingreso.
  - Sección IoT skipea si no hay CSV o datos del día.
  - Sección IoT formatea promedio por sensor + unidad si está presente.
  - Slash command `/resumen` invoca al generador y devuelve el texto.
"""

from __future__ import annotations

from pathlib import Path

from orion.adapters.iot import access_control as ac
from orion.server import status_summary as ss
from orion.server import telegram_commands as tc


# ── build_daily_summary — sin eventos ───────────────────────────────────


def test_summary_empty_db():
    text = ss.build_daily_summary()
    assert "Resumen del" in text
    assert "Sin eventos hoy" in text


# ── build_daily_summary — con eventos ──────────────────────────────────


def test_summary_with_events():
    ac.add_user(fingerprint_id=1, name="Zahir Test", phone="")
    ac.add_user(fingerprint_id=2, name="María Test", phone="")

    # Eventos del día actual
    ac.record_event(fingerprint_id=1, event_type="GRANTED", esp_id="puerta", confidence=150)
    ac.record_event(fingerprint_id=2, event_type="GRANTED", esp_id="puerta", confidence=180)
    ac.record_event(fingerprint_id=-1, event_type="DENIED", esp_id="puerta", confidence=0)

    text = ss.build_daily_summary()

    # Header de Acceso
    assert "Acceso" in text
    # Counts correctos: 2 granted + 1 denied = 3 totales
    assert "3" in text
    assert "2" in text
    assert "1" in text
    # Nombres aparecen
    assert "Zahir Test" in text
    assert "María Test" in text
    # Huellas no enroladas NO aparecen en "Entradas del día"
    assert "Huella #-1" not in text


def test_summary_groups_by_user_keeps_first_entry():
    """Si un usuario entra varias veces, solo aparece UNA vez en el
    resumen, con la hora más temprana."""
    ac.add_user(fingerprint_id=5, name="Multi", phone="")
    # Tres entradas del mismo usuario en el mismo día
    ac.record_event(
        fingerprint_id=5,
        event_type="GRANTED",
        esp_id="p",
        confidence=100,
        timestamp="2026-06-28T08:00:00-05:00",
    )
    ac.record_event(
        fingerprint_id=5,
        event_type="GRANTED",
        esp_id="p",
        confidence=100,
        timestamp="2026-06-28T13:30:00-05:00",
    )
    ac.record_event(
        fingerprint_id=5,
        event_type="GRANTED",
        esp_id="p",
        confidence=100,
        timestamp="2026-06-28T20:15:00-05:00",
    )

    text = ss.build_daily_summary(day="2026-06-28")
    # "Multi" aparece UNA sola vez en la lista de entradas
    assert text.count("— Multi") == 1
    # Y debe ser la hora más temprana (08:00, no 13:30 ni 20:15)
    assert "08:00" in text


# ── IoT block ──────────────────────────────────────────────────────────


def test_iot_block_none_when_csv_missing(monkeypatch, tmp_path):
    """Sin CSV de sensores, el resumen no incluye sección IoT."""
    monkeypatch.setattr(ss, "_IOT_SENSOR_LOG", tmp_path / "no_existe.csv")
    text = ss.build_daily_summary()
    assert "Sensores" not in text


def test_iot_block_includes_averages(monkeypatch, tmp_path):
    """CSV con datos del día → promedio por sensor."""
    csv_path = tmp_path / "sensor.csv"
    csv_path.write_text(
        "timestamp,sensor,value,unit\n"
        "2026-06-28T08:00:00,temp,22.5,°C\n"
        "2026-06-28T12:00:00,temp,24.5,°C\n"
        "2026-06-28T08:00:00,humedad,55,%\n"
        "2026-06-27T08:00:00,temp,20.0,°C\n",  # día anterior, debe ignorarse
        encoding="utf-8",
    )
    monkeypatch.setattr(ss, "_IOT_SENSOR_LOG", csv_path)

    text = ss.build_daily_summary(day="2026-06-28")
    assert "Sensores" in text
    # Promedio temp: (22.5 + 24.5) / 2 = 23.5
    assert "temp: *23.5 °C*" in text
    # n=2 (porque el del día anterior queda fuera)
    assert "(n=2)" in text
    # Humedad
    assert "humedad: *55.0 %*" in text


def test_iot_block_skips_invalid_values(monkeypatch, tmp_path):
    """Rows con valor no numérico se ignoran en el promedio."""
    csv_path = tmp_path / "sensor.csv"
    csv_path.write_text(
        "timestamp,sensor,value,unit\n"
        "2026-06-28T08:00:00,temp,22.0,°C\n"
        "2026-06-28T09:00:00,temp,ERROR,°C\n"
        "2026-06-28T10:00:00,temp,24.0,°C\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ss, "_IOT_SENSOR_LOG", csv_path)

    text = ss.build_daily_summary(day="2026-06-28")
    # Promedio sobre los 2 válidos
    assert "*23.0 °C*" in text
    assert "(n=2)" in text


def test_iot_block_no_header(monkeypatch, tmp_path):
    """Si el CSV NO tiene header (la primera fila es data), también
    debería parsearse correctamente."""
    csv_path = tmp_path / "sensor.csv"
    csv_path.write_text(
        "2026-06-28T08:00:00,temp,22.5,°C\n2026-06-28T12:00:00,temp,24.5,°C\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ss, "_IOT_SENSOR_LOG", csv_path)

    text = ss.build_daily_summary(day="2026-06-28")
    assert "temp" in text
    assert "(n=2)" in text


# ── Slash command /resumen ─────────────────────────────────────────────


def test_resumen_command_invokes_generator():
    """`/resumen` (con auth) debe llamar build_daily_summary y devolver
    el texto del resumen."""
    AUTHED = 8341210361
    reply = tc.dispatch("/resumen", sender_chat_id=AUTHED, authorized_chat_id=AUTHED)
    assert "Resumen del" in reply


def test_resumen_command_requires_auth():
    """`/resumen` requiere auth — un sender desconocido recibe rechazo."""
    AUTHED = 8341210361
    reply = tc.dispatch("/resumen", sender_chat_id=99999, authorized_chat_id=AUTHED)
    assert "No autorizado" in reply
