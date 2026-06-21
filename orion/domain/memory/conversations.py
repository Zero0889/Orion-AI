"""
memory.conversations — Persistencia de conversaciones (SQLite, Fase 3B)
========================================================================
Migración de memory/conversations.json a SQLite con dos tablas
relacionales (conversations + conversation_messages, FK ON DELETE CASCADE).

API pública intacta:
- ``list_conversations()``  → metadata ligera (sin messages)
- ``get_conversation(id)``  → conversación completa con messages[]
- ``delete_conversation(id)``
- ``delete_conversations_bulk(ids)``
- ``delete_all_conversations()``
- ``ConversationSession``   → sesión activa, persiste en cada add()

Schemas
-------

::

    CREATE TABLE conversations (
        id      TEXT PRIMARY KEY,
        started TEXT NOT NULL,           -- ISO 8601
        title   TEXT NOT NULL DEFAULT 'Conversación'
    );
    CREATE INDEX idx_conv_started ON conversations(started DESC);

    CREATE TABLE conversation_messages (
        conv_id TEXT NOT NULL,
        seq     INTEGER NOT NULL,        -- orden dentro de la conv
        role    TEXT NOT NULL,           -- "user" | "ai" | "sys" | ...
        text    TEXT NOT NULL,
        ts      TEXT NOT NULL,
        PRIMARY KEY (conv_id, seq),
        FOREIGN KEY (conv_id) REFERENCES conversations(id) ON DELETE CASCADE
    );

Migración automática del JSON viejo al primer uso, idempotente.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime

from orion.config import MEMORY_DIR
from orion.core.logger import get_logger
from orion.storage import get_connection

log = get_logger("memory.conversations")

_CONVERSATIONS_PATH = MEMORY_DIR / "conversations.json"
MAX_CONVERSATIONS = 50
MAX_MESSAGES_PER_CONV = 500

_LOCK = threading.Lock()
_initialized = False


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ── Schema + migración ──────────────────────────────────────────────────


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id      TEXT PRIMARY KEY,
            started TEXT NOT NULL,
            title   TEXT NOT NULL DEFAULT 'Conversación'
        );
        CREATE INDEX IF NOT EXISTS idx_conv_started
            ON conversations(started DESC);

        CREATE TABLE IF NOT EXISTS conversation_messages (
            conv_id TEXT NOT NULL,
            seq     INTEGER NOT NULL,
            role    TEXT NOT NULL,
            text    TEXT NOT NULL,
            ts      TEXT NOT NULL,
            PRIMARY KEY (conv_id, seq),
            FOREIGN KEY (conv_id) REFERENCES conversations(id) ON DELETE CASCADE
        );
    """)
    conn.commit()


def _maybe_migrate_legacy_json(conn: sqlite3.Connection) -> int:
    if not _CONVERSATIONS_PATH.exists():
        return 0
    cur = conn.execute("SELECT COUNT(*) FROM conversations")
    if cur.fetchone()[0] > 0:
        return 0
    try:
        raw = json.loads(_CONVERSATIONS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("No pude leer conversations.json legacy: %s", e)
        return 0

    if not isinstance(raw, list):
        return 0

    imported = 0
    for c in raw:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or uuid.uuid4().hex[:8])
        conn.execute(
            "INSERT OR IGNORE INTO conversations (id, started, title) VALUES (?, ?, ?)",
            (cid, str(c.get("started") or _now_iso()), str(c.get("title") or "Conversación")),
        )
        msgs = c.get("messages") or []
        if isinstance(msgs, list):
            rows = []
            for seq, m in enumerate(msgs):
                if not isinstance(m, dict):
                    continue
                rows.append(
                    (
                        cid,
                        seq,
                        str(m.get("role") or ""),
                        str(m.get("text") or ""),
                        str(m.get("ts") or _now_iso()),
                    )
                )
            if rows:
                conn.executemany(
                    """INSERT OR IGNORE INTO conversation_messages
                       (conv_id, seq, role, text, ts) VALUES (?, ?, ?, ?, ?)""",
                    rows,
                )
        imported += 1

    conn.commit()
    if imported:
        log.info("Migradas %d conversaciones de JSON legacy a SQLite", imported)
    _archive_legacy_json()
    return imported


def _archive_legacy_json() -> None:
    if not _CONVERSATIONS_PATH.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = _CONVERSATIONS_PATH.with_suffix(f".json.migrated_to_sqlite_{stamp}.bak")
    try:
        _CONVERSATIONS_PATH.rename(bak)
    except OSError as e:
        log.warning("No pude renombrar conversations.json legacy: %s", e)


def _enforce_cap(conn: sqlite3.Connection) -> None:
    """Mantiene solo las últimas MAX_CONVERSATIONS por `started`."""
    cur = conn.execute("SELECT COUNT(*) FROM conversations")
    total = cur.fetchone()[0]
    if total <= MAX_CONVERSATIONS:
        return
    # ON DELETE CASCADE limpia los messages automáticamente.
    conn.execute(
        """DELETE FROM conversations
           WHERE id IN (
               SELECT id FROM conversations
               ORDER BY started ASC
               LIMIT ?
           )""",
        (total - MAX_CONVERSATIONS,),
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
    global _initialized
    with _LOCK:
        _initialized = False


# ── API pública (read) ──────────────────────────────────────────────────


def list_conversations() -> list[dict]:
    """Metadata ligera (sin messages) ordenada por started desc."""
    _init_if_needed()
    conn = get_connection()
    cur = conn.execute("""
        SELECT c.id, c.started, c.title,
               (SELECT COUNT(*) FROM conversation_messages m WHERE m.conv_id = c.id) AS msg_count
        FROM conversations c
        ORDER BY c.started DESC
    """)
    return [dict(r) for r in cur]


def get_conversation(conv_id: str) -> dict | None:
    _init_if_needed()
    conn = get_connection()
    cur = conn.execute(
        "SELECT id, started, title FROM conversations WHERE id = ?",
        (conv_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    msgs_cur = conn.execute(
        """SELECT role, text, ts FROM conversation_messages
           WHERE conv_id = ? ORDER BY seq ASC""",
        (conv_id,),
    )
    return {
        "id": row["id"],
        "started": row["started"],
        "title": row["title"],
        "messages": [dict(m) for m in msgs_cur],
    }


# ── API pública (delete) ────────────────────────────────────────────────


def delete_conversation(conv_id: str) -> bool:
    _init_if_needed()
    conn = get_connection()
    cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    conn.commit()
    return cur.rowcount > 0


def delete_conversations_bulk(conv_ids: list[str]) -> int:
    if not conv_ids:
        return 0
    _init_if_needed()
    conn = get_connection()
    cur = conn.execute(
        f"DELETE FROM conversations WHERE id IN ({','.join('?' * len(conv_ids))})",
        conv_ids,
    )
    conn.commit()
    return cur.rowcount or 0


def delete_all_conversations() -> int:
    _init_if_needed()
    conn = get_connection()
    cur = conn.execute("DELETE FROM conversations")
    conn.commit()
    return cur.rowcount or 0


# ── Sesión activa ───────────────────────────────────────────────────────


class ConversationSession:
    """Sesión activa: agrupa mensajes y persiste en cada ``add()``.

    Mantiene un buffer en memoria PARA el title-detection heuristic, pero
    cada mensaje se inserta directo al DB (sin re-escribir todo).
    """

    def __init__(self, conv_id: str | None = None):
        self.id = conv_id or uuid.uuid4().hex[:8]
        self._started = _now_iso()
        self._title: str | None = None
        self._seq = 0
        self._ensured = False

    @property
    def title(self) -> str:
        return self._title or "Conversación"

    def _ensure_row(self) -> None:
        if self._ensured:
            return
        _init_if_needed()
        conn = get_connection()
        conn.execute(
            """INSERT OR IGNORE INTO conversations (id, started, title)
               VALUES (?, ?, ?)""",
            (self.id, self._started, self.title),
        )
        conn.commit()
        # Si la conv ya existía (caso resume), continuamos numerando.
        cur = conn.execute(
            "SELECT COALESCE(MAX(seq), -1) FROM conversation_messages WHERE conv_id = ?",
            (self.id,),
        )
        self._seq = int(cur.fetchone()[0]) + 1
        self._ensured = True

    def add(self, role: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self._ensure_row()
        conn = get_connection()
        conn.execute(
            """INSERT INTO conversation_messages (conv_id, seq, role, text, ts)
               VALUES (?, ?, ?, ?, ?)""",
            (self.id, self._seq, role, text, _now_iso()),
        )
        self._seq += 1
        # Cap de mensajes: si superamos, borramos los más viejos.
        cur = conn.execute(
            "SELECT COUNT(*) FROM conversation_messages WHERE conv_id = ?",
            (self.id,),
        )
        n = int(cur.fetchone()[0])
        if n > MAX_MESSAGES_PER_CONV:
            conn.execute(
                """DELETE FROM conversation_messages
                   WHERE conv_id = ? AND seq IN (
                       SELECT seq FROM conversation_messages
                       WHERE conv_id = ?
                       ORDER BY seq ASC
                       LIMIT ?
                   )""",
                (self.id, self.id, n - MAX_MESSAGES_PER_CONV),
            )
        # Title: primer mensaje del usuario (truncado).
        if self._title is None and role == "user":
            self._title = text[:60] + ("…" if len(text) > 60 else "")
            conn.execute(
                "UPDATE conversations SET title = ? WHERE id = ?",
                (self._title, self.id),
            )
        conn.commit()

    def messages(self) -> list[dict]:
        if not self._ensured:
            return []
        conn = get_connection()
        cur = conn.execute(
            """SELECT role, text, ts FROM conversation_messages
               WHERE conv_id = ? ORDER BY seq ASC""",
            (self.id,),
        )
        return [dict(r) for r in cur]
