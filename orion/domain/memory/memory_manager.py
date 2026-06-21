"""
memory.memory_manager — Memoria long-term del usuario (SQLite, Fase 3B)
========================================================================
Migración del JSON anidado (memory/long_term.json) a una tabla SQLite
plana `memory_entries(category, key, value, updated)`.

API pública intacta:
    - ``load_memory()``                    → dict de cat → key → {value, updated}
    - ``update_memory(updates: dict)``     → merge recursivo + persist
    - ``save_memory(memory: dict)``        → reemplaza el contenido entero
    - ``format_memory_for_prompt(memory)`` → texto para el system prompt
    - ``remember(key, value, category)``
    - ``forget(key, category)``

Schema
------

::

    CREATE TABLE memory_entries (
        category TEXT NOT NULL,           -- identity | preferences | ...
        key      TEXT NOT NULL,
        value    TEXT NOT NULL,
        updated  TEXT NOT NULL,           -- YYYY-MM-DD
        PRIMARY KEY (category, key)
    );

Migración del JSON viejo al primer uso, idempotente.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime

from orion.config import MEMORY_PATH
from orion.core.logger import get_logger
from orion.storage import get_connection

log = get_logger("memory.long_term")

MAX_VALUE_LENGTH = 380
MEMORY_MAX_CHARS = 2200

# Categorías canónicas — load_memory() siempre las garantiza presentes.
_CATEGORIES = ("identity", "preferences", "projects", "relationships", "wishes", "notes")

_LOCK = threading.Lock()
_initialized = False


# ── Schema + migración ──────────────────────────────────────────────────


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memory_entries (
            category TEXT NOT NULL,
            key      TEXT NOT NULL,
            value    TEXT NOT NULL,
            updated  TEXT NOT NULL,
            PRIMARY KEY (category, key)
        );
    """)
    conn.commit()


def _maybe_migrate_legacy_json(conn: sqlite3.Connection) -> int:
    if not MEMORY_PATH.exists():
        return 0
    cur = conn.execute("SELECT COUNT(*) FROM memory_entries")
    if cur.fetchone()[0] > 0:
        return 0
    try:
        raw = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("No pude leer long_term.json legacy: %s", e)
        return 0

    if not isinstance(raw, dict):
        return 0

    today = datetime.now().strftime("%Y-%m-%d")
    rows = []
    for cat, items in raw.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                value = str(entry.get("value") or "")
                updated = str(entry.get("updated") or today)
            else:
                value = str(entry)
                updated = today
            if value:
                rows.append((str(cat), str(key), value, updated))

    if rows:
        conn.executemany(
            """INSERT OR IGNORE INTO memory_entries
               (category, key, value, updated) VALUES (?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
        log.info("Migradas %d entries de long_term.json a SQLite", len(rows))

    _archive_legacy_json()
    return len(rows)


def _archive_legacy_json() -> None:
    if not MEMORY_PATH.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = MEMORY_PATH.with_suffix(f".json.migrated_to_sqlite_{stamp}.bak")
    try:
        MEMORY_PATH.rename(bak)
    except OSError as e:
        log.warning("No pude renombrar long_term.json legacy: %s", e)


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
        _initialized = True


def _reset_for_tests() -> None:
    global _initialized
    with _LOCK:
        _initialized = False


# ── Helpers ─────────────────────────────────────────────────────────────


def _empty_memory() -> dict:
    return {cat: {} for cat in _CATEGORIES}


def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "…"
    return val


# ── API pública (read) ──────────────────────────────────────────────────


def load_memory() -> dict:
    """Devuelve el dict canónico con todas las categorías presentes."""
    _init_if_needed()
    conn = get_connection()
    out = _empty_memory()
    cur = conn.execute("SELECT category, key, value, updated FROM memory_entries")
    for r in cur:
        cat = r["category"]
        if cat not in out:
            out[cat] = {}
        out[cat][r["key"]] = {"value": r["value"], "updated": r["updated"]}
    return out


# ── API pública (write) ─────────────────────────────────────────────────


def _trim_to_limit(conn: sqlite3.Connection) -> None:
    """Si el dump JSON > MEMORY_MAX_CHARS, borra las entries más viejas."""
    memory = load_memory()
    if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
        return
    # Ordenamos todas las entries por updated asc; borramos hasta caber.
    cur = conn.execute("SELECT category, key, updated FROM memory_entries ORDER BY updated ASC")
    candidates = list(cur)
    while candidates:
        if len(json.dumps(load_memory(), ensure_ascii=False)) <= MEMORY_MAX_CHARS:
            break
        c = candidates.pop(0)
        conn.execute(
            "DELETE FROM memory_entries WHERE category = ? AND key = ?",
            (c["category"], c["key"]),
        )
        conn.commit()
        log.info("Trim memory: %s/%s", c["category"], c["key"])


def save_memory(memory: dict) -> None:
    """Reemplaza el contenido entero con el dict provisto.

    Útil cuando un caller hace `m = load_memory(); m[...] = ...; save_memory(m)`.
    El recorrido es: borrar todo + insertar todo en una transacción.
    """
    if not isinstance(memory, dict):
        return
    _init_if_needed()
    conn = get_connection()
    today = datetime.now().strftime("%Y-%m-%d")
    rows = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict):
                value = _truncate_value(str(entry.get("value", "")))
                updated = str(entry.get("updated") or today)
            else:
                value = _truncate_value(str(entry))
                updated = today
            if value:
                rows.append((str(cat), str(key), value, updated))
    with _LOCK:
        conn.execute("DELETE FROM memory_entries")
        if rows:
            conn.executemany(
                """INSERT INTO memory_entries (category, key, value, updated)
                   VALUES (?, ?, ?, ?)""",
                rows,
            )
        conn.commit()
        _trim_to_limit(conn)


def _flatten_updates(updates: dict, _prefix_cat: str = "") -> list[tuple]:
    """Convierte un dict anidado al modelo plano (cat, key, value).

    Acepta dos formas (compat con la API histórica):
    - ``{cat: {key: "valor"}}``                         (valor directo)
    - ``{cat: {key: {"value": "valor"}}}``              (con metadata)
    """
    today = datetime.now().strftime("%Y-%m-%d")
    rows: list[tuple] = []
    for cat, items in updates.items():
        if not isinstance(items, dict):
            continue
        for key, val in items.items():
            if val is None:
                continue
            if isinstance(val, dict):
                if "value" not in val:
                    # Anidado más profundo — caso raro, lo ignoramos
                    # silenciosamente (el modelo histórico tampoco lo
                    # manejaba bien).
                    continue
                value_raw = val["value"]
            else:
                value_raw = val
            if isinstance(value_raw, str) and not value_raw.strip():
                continue
            value = _truncate_value(str(value_raw))
            rows.append((str(cat), str(key), value, today))
    return rows


def update_memory(memory_update: dict) -> dict:
    """Merge: inserta/actualiza solo las entries del dict provisto.

    A diferencia de ``save_memory()`` (que reemplaza todo), esto preserva
    el resto del contenido. Es el flow normal del LLM cuando llama a la
    tool `save_memory(category, key, value)`.
    """
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
    _init_if_needed()
    conn = get_connection()
    rows = _flatten_updates(memory_update)
    if rows:
        conn.executemany(
            """INSERT INTO memory_entries (category, key, value, updated)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(category, key) DO UPDATE SET
                   value = excluded.value,
                   updated = excluded.updated""",
            rows,
        )
        conn.commit()
        _trim_to_limit(conn)
        log.info("Memoria actualizada: %s", [(r[0], r[1]) for r in rows])
    return load_memory()


def remember(key: str, value: str, category: str = "notes") -> str:
    valid = set(_CATEGORIES)
    if category not in valid:
        category = "notes"
    update_memory({category: {key: {"value": value}}})
    return f"Recordado: {category}/{key} = {value}"


def forget(key: str, category: str = "notes") -> str:
    _init_if_needed()
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM memory_entries WHERE category = ? AND key = ?",
        (category, key),
    )
    conn.commit()
    if cur.rowcount > 0:
        return f"Olvidado: {category}/{key}"
    return f"No encontrado: {category}/{key}"


forget_memory = forget


# ── Formatter para el system prompt ─────────────────────────────────────


def format_memory_for_prompt(memory: dict | None) -> str:
    """Sin cambios respecto a la versión JSON — opera sobre el dict que
    devuelve ``load_memory()``."""
    if not memory:
        return ""

    lines = []

    identity = memory.get("identity", {})
    id_fields = ["name", "age", "birthday", "city", "job", "language", "school", "nationality"]
    for field in id_fields:
        entry = identity.get(field)
        if entry:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"{field.title()}: {val}")
    for key, entry in identity.items():
        if key in id_fields:
            continue
        val = entry.get("value") if isinstance(entry, dict) else entry
        if val:
            lines.append(f"{key.replace('_', ' ').title()}: {val}")

    prefs = memory.get("preferences", {})
    if prefs:
        lines.append("")
        lines.append("Preferences:")
        for key, entry in list(prefs.items())[:15]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    projects = memory.get("projects", {})
    if projects:
        lines.append("")
        lines.append("Active Projects / Goals:")
        for key, entry in list(projects.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    rels = memory.get("relationships", {})
    if rels:
        lines.append("")
        lines.append("People in their life:")
        for key, entry in list(rels.items())[:10]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    wishes = memory.get("wishes", {})
    if wishes:
        lines.append("")
        lines.append("Wishes / Plans / Wants:")
        for key, entry in list(wishes.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    notes = memory.get("notes", {})
    if notes:
        lines.append("")
        lines.append("Other notes:")
        for key, entry in list(notes.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key}: {val}")

    if not lines:
        return ""

    header = "[WHAT YOU KNOW ABOUT THIS PERSON — use naturally, never recite like a list]\n"
    result = header + "\n".join(lines)
    if len(result) > 2000:
        result = result[:1997] + "…"

    return result + "\n"
