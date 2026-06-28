"""
server.status_summary — Generador de resúmenes para el topic Estado.

Función principal: ``build_daily_summary()`` que arma un texto
multi-sección con:

  · Eventos de acceso del día (granted/denied + último).
  · Lista de personas que entraron + su primer acceso.
  · Sensores IoT recientes (si hay datos; si no, skipea la sección).

El generador es **stateless** — cada call relee de SQLite/CSV. Lo
publica el caller (slash command ``/resumen`` para on-demand, scheduler
diario para automático).
"""

from __future__ import annotations

from datetime import datetime

from orion.adapters.iot import access_control as ac
from orion.config import DATA_DIR
from orion.core.logger import get_logger

log = get_logger("status.summary")


_IOT_SENSOR_LOG = DATA_DIR / "iot_sensor_log.csv"


def build_daily_summary(*, day: str | None = None) -> str:
    """Devuelve el texto del resumen formateado para Telegram (Markdown).

    ``day`` es la fecha en formato ``YYYY-MM-DD`` para resumir un día
    específico; ``None`` = hoy (local timezone).
    """
    if day is None:
        day = datetime.now().astimezone().strftime("%Y-%m-%d")

    parts: list[str] = [f"📊 *Resumen del {_format_fecha(day)}*"]

    access_block = _build_access_block(day)
    parts.append(access_block)

    iot_block = _build_iot_block(day)
    if iot_block:
        parts.append(iot_block)

    return "\n\n".join(parts)


# ── Acceso ──────────────────────────────────────────────────────────────


def _build_access_block(day: str) -> str:
    since = f"{day}T00:00:00"
    until = f"{day}T23:59:59"

    granted = ac.count_events(since=since, event_type="GRANTED")
    denied = ac.count_events(since=since, event_type="DENIED")
    total = granted + denied

    if total == 0:
        return "🛡️ *Acceso*\n_Sin eventos hoy._"

    # Primer GRANTED por usuario (entrada del día). Usamos `list_events`
    # con since/until y nos quedamos con el más temprano por
    # fingerprint_id.
    events = ac.list_events(since=since, limit=500, event_type="GRANTED")
    # Filtrar al rango del día (limit por arriba, since por abajo)
    events = [e for e in events if e.timestamp <= until]

    first_by_user: dict[int, tuple[str, str]] = {}
    for ev in events:
        if ev.fingerprint_id < 0:
            continue
        name = ev.user_name or f"Huella #{ev.fingerprint_id}"
        hora = _format_hora(ev.timestamp)
        # Como list_events viene ORDER BY timestamp DESC, el último
        # iterado para cada user es el más temprano. Por eso pisamos
        # siempre.
        first_by_user[ev.fingerprint_id] = (name, hora)

    lines = ["🛡️ *Acceso*"]
    lines.append(f"Eventos: *{total}* (✅ {granted} · ⛔ {denied})")

    if first_by_user:
        lines.append("\n*Entradas del día:*")
        # Ordenar por hora de entrada (la 2da entry de la tupla)
        sorted_entries = sorted(first_by_user.values(), key=lambda x: x[1])
        for name, hora in sorted_entries:
            lines.append(f"  · `{hora}` — {name}")

    return "\n".join(lines)


# ── IoT ─────────────────────────────────────────────────────────────────


def _build_iot_block(day: str) -> str | None:
    """Lee últimas N lecturas del CSV de sensores y devuelve un bloque
    con promedios. Si el CSV no existe o no hay datos del día → None
    (caller skipea la sección)."""
    readings = _load_iot_readings_for_day(day)
    if not readings:
        return None

    # Agrupar por sensor (cada row: ts, sensor, value, unit)
    by_sensor: dict[str, list[float]] = {}
    units: dict[str, str] = {}
    for ts, sensor, value, unit in readings:
        if sensor not in by_sensor:
            by_sensor[sensor] = []
            units[sensor] = unit
        try:
            by_sensor[sensor].append(float(value))
        except (TypeError, ValueError):
            continue

    if not by_sensor:
        return None

    lines = ["🌡️ *Sensores (promedio del día)*"]
    for sensor in sorted(by_sensor.keys()):
        values = by_sensor[sensor]
        if not values:
            continue
        avg = sum(values) / len(values)
        unit = units.get(sensor, "")
        unit_str = f" {unit}" if unit else ""
        lines.append(f"  · {sensor}: *{avg:.1f}{unit_str}* (n={len(values)})")

    return "\n".join(lines)


def _load_iot_readings_for_day(day: str) -> list[tuple[str, str, str, str]]:
    """Lee `data/iot_sensor_log.csv` y devuelve filas del día indicado.

    El CSV tiene formato variable según el sketch; intentamos parsear las
    columnas comunes: timestamp ISO, sensor, value, unit. Si el archivo
    no existe → lista vacía.
    """
    if not _IOT_SENSOR_LOG.exists():
        return []
    try:
        import csv

        with _IOT_SENSOR_LOG.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)
    except OSError as e:
        log.warning("No pude leer %s: %s", _IOT_SENSOR_LOG, e)
        return []

    if not rows:
        return []

    # Detectar si hay header (la primera columna no parsea como ISO)
    start_idx = 0
    if rows[0] and not _is_iso_timestamp(rows[0][0]):
        start_idx = 1

    out: list[tuple[str, str, str, str]] = []
    for row in rows[start_idx:]:
        if len(row) < 3:
            continue
        ts = row[0].strip()
        if not ts.startswith(day):
            continue
        sensor = row[1].strip() if len(row) > 1 else ""
        value = row[2].strip() if len(row) > 2 else ""
        unit = row[3].strip() if len(row) > 3 else ""
        out.append((ts, sensor, value, unit))
    return out


def _is_iso_timestamp(s: str) -> bool:
    s = (s or "").strip()
    if len(s) < 10:
        return False
    return s[:4].isdigit() and s[4] == "-" and s[5:7].isdigit()


# ── Helpers de formato ──────────────────────────────────────────────────


def _format_fecha(iso_day: str) -> str:
    """`2026-06-28` → `28/06/2026` (formato latam)."""
    if len(iso_day) != 10:
        return iso_day
    y, m, d = iso_day.split("-")
    return f"{d}/{m}/{y}"


def _format_hora(iso_ts: str) -> str:
    """`2026-06-28T20:13:45-05:00` → `20:13`."""
    if len(iso_ts) >= 16:
        return iso_ts[11:16]
    return iso_ts
