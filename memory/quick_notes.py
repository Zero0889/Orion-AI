"""
memory.quick_notes — Notas rápidas persistentes (SQLite, Fase 3B)
==================================================================
Migración del JSON plano (memory/quick_notes.json) a SQLite. API
pública intacta: list_notes / add_note / update_note / delete_note /
count_notes — los routes REST y el panel siguen funcionando idéntico.

Schema
------

::

    CREATE TABLE quick_notes (
        id      TEXT PRIMARY KEY,        -- uuid4 hex[:8]
        text    TEXT NOT NULL,
        color   TEXT NOT NULL DEFAULT '',
        pinned  INTEGER NOT NULL DEFAULT 0,
        created TEXT NOT NULL,           -- ISO 8601 seconds
        updated TEXT NOT NULL
    );
    CREATE INDEX idx_notes_sort ON quick_notes(pinned DESC, updated DESC);

Migración automática
--------------------
Al primer uso, si existe el JSON viejo lo importa y lo archiva como
``quick_notes.json.migrated_to_sqlite_<ts>.bak``. Idempotente.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime

from config import MEMORY_DIR
from core.logger import get_logger
from storage import get_connection

log = get_logger("memory.quick_notes")

_NOTES_PATH = MEMORY_DIR / "quick_notes.json"
MAX_NOTES = 500
MAX_LEN = 4000

_LOCK = threading.Lock()
_initialized = False


# ── Schema + migración ──────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS quick_notes (
            id      TEXT PRIMARY KEY,
            text    TEXT NOT NULL,
            color   TEXT NOT NULL DEFAULT '',
            pinned  INTEGER NOT NULL DEFAULT 0,
            created TEXT NOT NULL,
            updated TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_notes_sort
            ON quick_notes(pinned DESC, updated DESC);
    """)
    conn.commit()


def _maybe_migrate_legacy_json(conn: sqlite3.Connection) -> int:
    if not _NOTES_PATH.exists():
        return 0
    cur = conn.execute("SELECT COUNT(*) FROM quick_notes")
    if cur.fetchone()[0] > 0:
        return 0
    try:
        raw = json.loads(_NOTES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("No pude leer quick_notes.json legacy: %s", e)
        return 0

    if not isinstance(raw, list):
        return 0

    rows = []
    for n in raw:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id") or uuid.uuid4().hex[:8])
        rows.append(
            (
                nid,
                str(n.get("text") or ""),
                str(n.get("color") or ""),
                1 if n.get("pinned") else 0,
                str(n.get("created") or _now_iso()),
                str(n.get("updated") or _now_iso()),
            )
        )

    if rows:
        conn.executemany(
            """INSERT OR IGNORE INTO quick_notes
               (id, text, color, pinned, created, updated)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
        log.info("Migradas %d notas de JSON legacy a SQLite", len(rows))

    _archive_legacy_json()
    return len(rows)


def _archive_legacy_json() -> None:
    if not _NOTES_PATH.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = _NOTES_PATH.with_suffix(f".json.migrated_to_sqlite_{stamp}.bak")
    try:
        _NOTES_PATH.rename(bak)
    except OSError as e:
        log.warning("No pude renombrar quick_notes.json legacy: %s", e)


def _enforce_cap(conn: sqlite3.Connection) -> None:
    cur = conn.execute("SELECT COUNT(*) FROM quick_notes")
    total = cur.fetchone()[0]
    if total <= MAX_NOTES:
        return
    # Borramos los más viejos por `updated`. Pinned-first sort solo aplica
    # al display — el cap es por edad pura.
    conn.execute(
        """DELETE FROM quick_notes
           WHERE id IN (
               SELECT id FROM quick_notes
               ORDER BY updated ASC
               LIMIT ?
           )""",
        (total - MAX_NOTES,),
    )
    conn.commit()


def _init_if_needed() -> None:
    global _initialized
    if _initialized:
        return
    with _LOCK:
        if _initialized:
            return
        conn = get_connection()
        _ensure_schema(conn)
        _maybe_migrate_legacy_json(conn)
        _enforce_cap(conn)
        _initialized = True


def _reset_for_tests() -> None:
    """Permite que los tests reinicialicen el módulo contra un DB fresco."""
    global _initialized
    with _LOCK:
        _initialized = False


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "text": row["text"],
        "color": row["color"] or "",
        "pinned": bool(row["pinned"]),
        "created": row["created"],
        "updated": row["updated"],
    }


# ── API pública ─────────────────────────────────────────────────────────


def list_notes() -> list[dict]:
    """Retorna todas las notas, pinneadas primero, luego por updated desc."""
    _init_if_needed()
    conn = get_connection()
    cur = conn.execute("SELECT * FROM quick_notes ORDER BY pinned DESC, updated DESC")
    return [_row_to_dict(r) for r in cur]


def add_note(text: str, color: str | None = None) -> dict:
    text = (text or "").strip()
    if not text:
        return {}
    text = text[:MAX_LEN]
    _init_if_needed()
    conn = get_connection()
    nid = uuid.uuid4().hex[:8]
    now = _now_iso()
    conn.execute(
        """INSERT INTO quick_notes (id, text, color, pinned, created, updated)
           VALUES (?, ?, ?, 0, ?, ?)""",
        (nid, text, color or "", now, now),
    )
    conn.commit()
    _enforce_cap(conn)
    return {
        "id": nid,
        "text": text,
        "color": color or "",
        "pinned": False,
        "created": now,
        "updated": now,
    }


def update_note(
    note_id: str,
    *,
    text: str | None = None,
    color: str | None = None,
    pinned: bool | None = None,
) -> bool:
    _init_if_needed()
    conn = get_connection()
    sets: list[str] = []
    params: list = []
    if text is not None:
        sets.append("text = ?")
        params.append(text.strip()[:MAX_LEN])
    if color is not None:
        sets.append("color = ?")
        params.append(color)
    if pinned is not None:
        sets.append("pinned = ?")
        params.append(1 if pinned else 0)
    if not sets:
        return False
    sets.append("updated = ?")
    params.append(_now_iso())
    params.append(note_id)
    cur = conn.execute(
        f"UPDATE quick_notes SET {', '.join(sets)} WHERE id = ?",
        params,
    )
    conn.commit()
    return cur.rowcount > 0


def delete_note(note_id: str) -> bool:
    _init_if_needed()
    conn = get_connection()
    cur = conn.execute("DELETE FROM quick_notes WHERE id = ?", (note_id,))
    conn.commit()
    return cur.rowcount > 0


def count_notes() -> int:
    _init_if_needed()
    conn = get_connection()
    cur = conn.execute("SELECT COUNT(*) FROM quick_notes")
    return int(cur.fetchone()[0])
