"""
adapters.iot.access_control — Control de acceso por huella dactilar
====================================================================
Pipeline ESP32 → Orion → SQLite + Telegram.

Hardware (diagrama del usuario)
-------------------------------
* ESP32 N16R8
* Sensor de huella AS608/R307 (UART2, GPIO 16/17)
* OLED 0.96" SSD1306 (I2C, GPIO 21/22)
* Relé 1 canal 5V (GPIO 4)
* LED verde / rojo (GPIO 27/26)
* Buzzer activo 5V (GPIO 25)
* Alimentación 2× 18650 + LM2596

El ESP32 hace POST a ``/api/access/event`` con::

    {"esp_id": "puerta_principal", "fingerprint_id": 12,
     "event_type": "GRANTED"|"DENIED"|"ENROLLED",
     "confidence": 142}

Tablas
------

``access_users`` — mapping huella_id → persona ::

    id              TEXT PRIMARY KEY (uuid8)
    fingerprint_id  INTEGER UNIQUE NOT NULL   -- 0-127 del AS608
    name            TEXT NOT NULL
    phone           TEXT NOT NULL DEFAULT ''
    active          INTEGER NOT NULL DEFAULT 1
    created         TEXT NOT NULL

``access_events`` — registros crudos ::

    id              TEXT PRIMARY KEY (uuid8)
    fingerprint_id  INTEGER NOT NULL
    event_type      TEXT NOT NULL   -- GRANTED | DENIED | ENROLLED
    esp_id          TEXT NOT NULL DEFAULT ''
    confidence      INTEGER NOT NULL DEFAULT 0
    timestamp       TEXT NOT NULL   -- ISO 8601 con TZ local

``access_daily`` (VIEW) — agrupa por usuario + fecha ::

    fingerprint_id, name, fecha (YYYY-MM-DD),
    entrada (HH:MM más temprano del día),
    salida  (HH:MM más tarde del día),
    tiempo_minutos (salida - entrada en minutos)

Convención entrada/salida
-------------------------
NO usamos un campo "tipo" explícito (ENTRADA vs SALIDA). En su lugar
inferimos: el PRIMER evento GRANTED del día = entrada, el ÚLTIMO = salida.
Es más robusto que pedirle al ESP32 que lleve estado y más simple para
el usuario (no hay que apretar botones distintos).
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from orion.core.logger import get_logger
from orion.core.tool_registry import tool
from orion.storage import get_connection

log = get_logger("access")

EventType = Literal["GRANTED", "DENIED", "ENROLLED"]
VALID_EVENT_TYPES: set[str] = {"GRANTED", "DENIED", "ENROLLED"}

_LOCK = threading.Lock()
_initialized = False


# ── Schema ──────────────────────────────────────────────────────────────


def _now_iso() -> str:
    """ISO 8601 con segundos y timezone local. Las queries de "hoy"
    parten esta string por los primeros 10 chars (YYYY-MM-DD)."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS access_users (
            id              TEXT PRIMARY KEY,
            fingerprint_id  INTEGER NOT NULL UNIQUE,
            name            TEXT NOT NULL,
            phone           TEXT NOT NULL DEFAULT '',
            active          INTEGER NOT NULL DEFAULT 1,
            created         TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS access_events (
            id              TEXT PRIMARY KEY,
            fingerprint_id  INTEGER NOT NULL,
            event_type      TEXT NOT NULL,
            esp_id          TEXT NOT NULL DEFAULT '',
            confidence      INTEGER NOT NULL DEFAULT 0,
            timestamp       TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_events_ts
            ON access_events(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_events_user_day
            ON access_events(fingerprint_id, substr(timestamp, 1, 10));

        -- VIEW agrupada por usuario + fecha. La calculamos al vuelo
        -- (no tabla materializada) — el volumen es bajo (decenas/día)
        -- y nos evita re-cómputo en cada update.
        DROP VIEW IF EXISTS access_daily;
        CREATE VIEW access_daily AS
        SELECT
            u.fingerprint_id                              AS fingerprint_id,
            u.name                                        AS name,
            substr(e.timestamp, 1, 10)                    AS fecha,
            substr(MIN(e.timestamp), 12, 5)               AS entrada,
            substr(MAX(e.timestamp), 12, 5)               AS salida,
            CAST(
                (julianday(MAX(e.timestamp)) - julianday(MIN(e.timestamp))) * 24 * 60
                AS INTEGER
            )                                             AS tiempo_minutos,
            COUNT(*)                                      AS eventos_dia
        FROM access_events e
        JOIN access_users u ON u.fingerprint_id = e.fingerprint_id
        WHERE e.event_type = 'GRANTED'
        GROUP BY u.fingerprint_id, fecha
        ORDER BY fecha DESC, entrada ASC;
    """)
    conn.commit()


def _init() -> None:
    global _initialized
    if _initialized:
        return
    with _LOCK:
        if _initialized:
            return
        conn = get_connection()
        _ensure_schema(conn)
        _initialized = True


def _reset_for_tests() -> None:
    """Resetea el flag de inicialización; útil cuando los tests reapuntan
    el path del SQLite singleton entre tests (ver tests/conftest.py)."""
    global _initialized
    with _LOCK:
        _initialized = False


# ── DTOs ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AccessUser:
    id: str
    fingerprint_id: int
    name: str
    phone: str
    active: bool
    created: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "fingerprint_id": self.fingerprint_id,
            "name": self.name,
            "phone": self.phone,
            "active": self.active,
            "created": self.created,
        }


@dataclass(frozen=True, slots=True)
class AccessEvent:
    id: str
    fingerprint_id: int
    event_type: str
    esp_id: str
    confidence: int
    timestamp: str
    user_name: str | None  # JOIN — null si la huella no está enrolada en Orion

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "fingerprint_id": self.fingerprint_id,
            "event_type": self.event_type,
            "esp_id": self.esp_id,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "user_name": self.user_name,
        }


@dataclass(frozen=True, slots=True)
class DailyReport:
    fingerprint_id: int
    name: str
    fecha: str  # YYYY-MM-DD
    entrada: str  # HH:MM
    salida: str  # HH:MM
    tiempo_minutos: int  # int total de minutos
    eventos_dia: int

    @property
    def tiempo_legible(self) -> str:
        """`8 h 57 min` o `42 min` si fue menos de una hora."""
        h, m = divmod(self.tiempo_minutos, 60)
        if h == 0:
            return f"{m} min"
        return f"{h} h {m:02d} min"

    def to_dict(self) -> dict:
        return {
            "fingerprint_id": self.fingerprint_id,
            "name": self.name,
            "fecha": self.fecha,
            "entrada": self.entrada,
            "salida": self.salida,
            "tiempo_minutos": self.tiempo_minutos,
            "tiempo_legible": self.tiempo_legible,
            "eventos_dia": self.eventos_dia,
        }


# ── Users CRUD ──────────────────────────────────────────────────────────


def list_users() -> list[AccessUser]:
    _init()
    conn = get_connection()
    rows = conn.execute("SELECT * FROM access_users ORDER BY fingerprint_id ASC").fetchall()
    return [_row_to_user(r) for r in rows]


def get_user_by_fingerprint(fingerprint_id: int) -> AccessUser | None:
    _init()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM access_users WHERE fingerprint_id = ?",
        (fingerprint_id,),
    ).fetchone()
    return _row_to_user(row) if row else None


def add_user(
    *,
    fingerprint_id: int,
    name: str,
    phone: str = "",
    active: bool = True,
) -> AccessUser:
    if not isinstance(fingerprint_id, int) or not (0 <= fingerprint_id <= 127):
        raise ValueError("fingerprint_id debe ser un entero 0-127 (AS608 admite 127 huellas).")
    name = name.strip()
    if not name:
        raise ValueError("name no puede estar vacío.")
    _init()
    conn = get_connection()
    try:
        user_id = _new_id()
        conn.execute(
            "INSERT INTO access_users(id, fingerprint_id, name, phone, active, created) "
            "VALUES(?,?,?,?,?,?)",
            (user_id, fingerprint_id, name, phone.strip(), 1 if active else 0, _now_iso()),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        raise ValueError(f"Ya existe un usuario para fingerprint_id={fingerprint_id}.") from e
    user = get_user_by_fingerprint(fingerprint_id)
    assert user is not None
    return user


def update_user(
    user_id: str,
    *,
    name: str | None = None,
    phone: str | None = None,
    active: bool | None = None,
) -> AccessUser:
    _init()
    conn = get_connection()
    sets: list[str] = []
    args: list[object] = []
    if name is not None:
        n = name.strip()
        if not n:
            raise ValueError("name no puede estar vacío.")
        sets.append("name = ?")
        args.append(n)
    if phone is not None:
        sets.append("phone = ?")
        args.append(phone.strip())
    if active is not None:
        sets.append("active = ?")
        args.append(1 if active else 0)
    if not sets:
        # nada para actualizar — devolver el usuario tal cual
        row = conn.execute("SELECT * FROM access_users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise ValueError(f"Usuario {user_id} no existe.")
        return _row_to_user(row)
    args.append(user_id)
    cur = conn.execute(
        f"UPDATE access_users SET {', '.join(sets)} WHERE id = ?",
        args,
    )
    if cur.rowcount == 0:
        raise ValueError(f"Usuario {user_id} no existe.")
    conn.commit()
    row = conn.execute("SELECT * FROM access_users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row)


def delete_user(user_id: str) -> bool:
    """Borra el mapeo huella→nombre. No borra los eventos históricos
    (quedan asociados al fingerprint_id, sin nombre joinable)."""
    _init()
    conn = get_connection()
    cur = conn.execute("DELETE FROM access_users WHERE id = ?", (user_id,))
    conn.commit()
    return cur.rowcount > 0


# ── Events ──────────────────────────────────────────────────────────────


def record_event(
    *,
    fingerprint_id: int,
    event_type: EventType,
    esp_id: str = "",
    confidence: int = 0,
    timestamp: str | None = None,
) -> AccessEvent:
    """Registra un evento crudo del ESP32. Idempotente NO — cada call
    crea un row nuevo (los duplicados rapidito son eventos válidos del
    sensor disparándose 2 veces).

    Si el sensor manda fingerprint_id=255 o -1 (convención AS608 para
    "no match"), lo aceptamos como DENIED registrando fingerprint_id=-1.
    """
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(
            f"event_type inválido: {event_type!r}. Esperaba uno de {sorted(VALID_EVENT_TYPES)}."
        )
    # Normalizamos "no match" del sensor
    if fingerprint_id < 0 or fingerprint_id > 127:
        fingerprint_id = -1
        if event_type == "GRANTED":
            event_type = "DENIED"  # GRANTED sin id reconocido no tiene sentido

    _init()
    conn = get_connection()
    ev_id = _new_id()
    ts = (timestamp or _now_iso()).strip()
    conn.execute(
        "INSERT INTO access_events(id, fingerprint_id, event_type, esp_id, confidence, timestamp) "
        "VALUES(?,?,?,?,?,?)",
        (ev_id, fingerprint_id, event_type, esp_id.strip(), int(confidence), ts),
    )
    conn.commit()
    # Releer con JOIN para devolver el nombre del usuario (si está enrolado)
    row = conn.execute(
        """
        SELECT e.*, u.name AS user_name
        FROM access_events e
        LEFT JOIN access_users u ON u.fingerprint_id = e.fingerprint_id
        WHERE e.id = ?
        """,
        (ev_id,),
    ).fetchone()
    return _row_to_event(row)


def list_events(
    *,
    limit: int = 200,
    offset: int = 0,
    fingerprint_id: int | None = None,
    since: str | None = None,
    event_type: EventType | None = None,
) -> list[AccessEvent]:
    _init()
    conn = get_connection()
    where: list[str] = []
    args: list[object] = []
    if fingerprint_id is not None:
        where.append("e.fingerprint_id = ?")
        args.append(fingerprint_id)
    if since:
        where.append("e.timestamp >= ?")
        args.append(since)
    if event_type:
        where.append("e.event_type = ?")
        args.append(event_type)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    args.extend([min(limit, 1000), max(offset, 0)])
    rows = conn.execute(
        f"""
        SELECT e.*, u.name AS user_name
        FROM access_events e
        LEFT JOIN access_users u ON u.fingerprint_id = e.fingerprint_id
        {where_sql}
        ORDER BY e.timestamp DESC
        LIMIT ? OFFSET ?
        """,
        args,
    ).fetchall()
    return [_row_to_event(r) for r in rows]


def count_events(
    *,
    fingerprint_id: int | None = None,
    since: str | None = None,
    event_type: EventType | None = None,
) -> int:
    _init()
    conn = get_connection()
    where: list[str] = []
    args: list[object] = []
    if fingerprint_id is not None:
        where.append("fingerprint_id = ?")
        args.append(fingerprint_id)
    if since:
        where.append("timestamp >= ?")
        args.append(since)
    if event_type:
        where.append("event_type = ?")
        args.append(event_type)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    row = conn.execute(f"SELECT COUNT(*) AS n FROM access_events {where_sql}", args).fetchone()
    return int(row["n"])


# ── Reporte diario (la "tabla excel" del usuario) ───────────────────────


def daily_report(
    *, since: str | None = None, fingerprint_id: int | None = None
) -> list[DailyReport]:
    """Lee la VIEW access_daily. Cada row es (usuario, día) con
    entrada/salida/tiempo. Esto es lo que el frontend exporta como XLSX.
    """
    _init()
    conn = get_connection()
    where: list[str] = []
    args: list[object] = []
    if since:
        where.append("fecha >= ?")
        args.append(since)
    if fingerprint_id is not None:
        where.append("fingerprint_id = ?")
        args.append(fingerprint_id)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = conn.execute(f"SELECT * FROM access_daily {where_sql}", args).fetchall()
    return [
        DailyReport(
            fingerprint_id=int(r["fingerprint_id"]),
            name=str(r["name"]),
            fecha=str(r["fecha"]),
            entrada=str(r["entrada"]),
            salida=str(r["salida"]),
            tiempo_minutos=int(r["tiempo_minutos"] or 0),
            eventos_dia=int(r["eventos_dia"] or 0),
        )
        for r in rows
    ]


# ── Tool LLM: consulta estado del acceso ────────────────────────────────


@tool(
    name="access_today_status",
    description=(
        "Devuelve quién entró hoy al lugar protegido por el control de acceso "
        "por huella. Útil cuando el usuario pregunta 'quién está hoy', 'a qué "
        "hora llegó X', 'cuánto tiempo estuvo Y'."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {},
    },
    fallback="No pude leer los registros de acceso.",
)
def access_today_status() -> str:
    """Tool que el LLM puede invocar para narrar el estado del día."""
    today = datetime.now().strftime("%Y-%m-%d")
    reports = daily_report(since=today)
    if not reports:
        return "Hoy nadie ha registrado entrada por huella."
    lines = ["Acceso de hoy:"]
    for r in reports:
        lines.append(
            f"• {r.name}: entró {r.entrada}, último registro {r.salida} ({r.tiempo_legible})."
        )
    return "\n".join(lines)


# ── Internos ────────────────────────────────────────────────────────────


def _row_to_user(row: sqlite3.Row | None) -> AccessUser:
    assert row is not None
    return AccessUser(
        id=str(row["id"]),
        fingerprint_id=int(row["fingerprint_id"]),
        name=str(row["name"]),
        phone=str(row["phone"]),
        active=bool(row["active"]),
        created=str(row["created"]),
    )


def _row_to_event(row: sqlite3.Row | None) -> AccessEvent:
    assert row is not None
    return AccessEvent(
        id=str(row["id"]),
        fingerprint_id=int(row["fingerprint_id"]),
        event_type=str(row["event_type"]),
        esp_id=str(row["esp_id"]),
        confidence=int(row["confidence"]),
        timestamp=str(row["timestamp"]),
        user_name=str(row["user_name"]) if row["user_name"] else None,
    )
