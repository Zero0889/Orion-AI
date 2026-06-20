"""
actions.notifications.store — Persistencia de notificaciones (SQLite)
=====================================================================
Backend: SQLite via ``storage.get_connection()``. Reemplaza al JSON
plano ``config/notifications_store.json`` que sufría de full-rewrite en
cada mutación y crecía sin control (127KB al momento de la migración).

Esquema
-------

::

    CREATE TABLE notifications (
        uid           TEXT PRIMARY KEY,
        source        TEXT NOT NULL,
        title         TEXT NOT NULL,
        summary       TEXT NOT NULL DEFAULT '',
        url           TEXT,
        received_ts   REAL NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        unread        INTEGER NOT NULL DEFAULT 1
    );
    CREATE INDEX idx_notif_received ON notifications(received_ts DESC);
    CREATE INDEX idx_notif_source   ON notifications(source);

El "seen list" del backend viejo desaparece: ``uid`` es PRIMARY KEY, así
que la deduplicación es ``INSERT OR IGNORE``. Si en el futuro queremos
recordar uids de items expirados sin guardar su body completo, agregamos
una segunda tabla ``seen_uids(uid TEXT PRIMARY KEY, source, ts)``.

Migración automática
--------------------
Al instanciar ``NotificationStore`` por primera vez, si existe el JSON
viejo lo importamos y lo renombramos a
``notifications_store.json.migrated_to_sqlite.bak`` (no se borra para
que el usuario pueda inspeccionar/revertir si quisiera).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime

from config import CONFIG_DIR
from core.logger import get_logger
from storage import get_connection

from .base import NotificationItem

log = get_logger("notifications.store")

_LEGACY_JSON_PATH = CONFIG_DIR / "notifications_store.json"
_MAX_ITEMS = 1000


# ── Schema ──────────────────────────────────────────────────────────────


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS notifications (
            uid           TEXT PRIMARY KEY,
            source        TEXT NOT NULL,
            title         TEXT NOT NULL,
            summary       TEXT NOT NULL DEFAULT '',
            url           TEXT,
            received_ts   REAL NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            unread        INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_notif_received
            ON notifications(received_ts DESC);
        CREATE INDEX IF NOT EXISTS idx_notif_source
            ON notifications(source);
    """)
    conn.commit()


# ── Migración one-shot del JSON viejo ───────────────────────────────────


def _maybe_migrate_legacy_json(conn: sqlite3.Connection) -> int:
    """Importa el JSON viejo a SQLite si existe y la tabla está vacía.

    Devuelve la cantidad de notificaciones importadas. Tras importar,
    renombra el JSON a ``.migrated_to_sqlite.bak`` para no re-importar
    en el próximo arranque (y para que el usuario tenga el backup).
    """
    if not _LEGACY_JSON_PATH.exists():
        return 0

    # Solo importamos si la tabla está vacía — evita pisar datos nuevos
    # si por algún motivo el JSON viejo volviera a aparecer.
    cur = conn.execute("SELECT COUNT(*) FROM notifications")
    if cur.fetchone()[0] > 0:
        return 0

    try:
        raw = json.loads(_LEGACY_JSON_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("No pude leer el JSON legacy: %s", e)
        return 0

    items = raw.get("items", {}) or {}
    unread_set = set(raw.get("unread", []) or [])

    rows: list[tuple] = []
    for uid, it in items.items():
        if not isinstance(it, dict):
            continue
        rows.append(
            (
                str(uid),
                str(it.get("source") or ""),
                str(it.get("title") or ""),
                str(it.get("summary") or ""),
                it.get("url"),  # puede ser None
                float(it.get("received_ts") or 0.0),
                json.dumps(it.get("metadata") or {}, ensure_ascii=False),
                1 if uid in unread_set else 0,
            )
        )

    if not rows:
        # JSON vacío — igual lo archivamos para no chequear cada arranque.
        _archive_legacy_json()
        return 0

    conn.executemany(
        """INSERT OR IGNORE INTO notifications
           (uid, source, title, summary, url, received_ts, metadata_json, unread)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    _archive_legacy_json()
    log.info("Migrados %d items de JSON legacy a SQLite", len(rows))
    return len(rows)


def _archive_legacy_json() -> None:
    if not _LEGACY_JSON_PATH.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = _LEGACY_JSON_PATH.with_suffix(f".json.migrated_to_sqlite_{stamp}.bak")
    try:
        _LEGACY_JSON_PATH.rename(bak)
    except OSError as e:
        log.warning("No pude renombrar JSON legacy: %s", e)


# ── Store ───────────────────────────────────────────────────────────────


class NotificationStore:
    """Misma API pública que la versión JSON anterior — el resto del
    código (poller, endpoints REST) no nota el cambio.
    """

    def __init__(self) -> None:
        conn = get_connection()
        _ensure_schema(conn)
        _maybe_migrate_legacy_json(conn)
        # Cap de items: limpia los más viejos si superamos el tope.
        self._enforce_cap(conn)

    # ── Helpers internos ───────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except json.JSONDecodeError:
            metadata = {}
        return {
            "uid": row["uid"],
            "source": row["source"],
            "title": row["title"],
            "summary": row["summary"] or "",
            "url": row["url"],
            "received_ts": row["received_ts"],
            "metadata": metadata,
        }

    @staticmethod
    def _enforce_cap(conn: sqlite3.Connection) -> None:
        """Si superamos MAX_ITEMS, borra los más viejos por received_ts.

        Hacemos el cap acá en lugar de un trigger por simplicidad — el
        poller corre cada N minutos, no es hot-path.
        """
        cur = conn.execute("SELECT COUNT(*) FROM notifications")
        total = cur.fetchone()[0]
        if total <= _MAX_ITEMS:
            return
        # DELETE de los más viejos. ROWID es estable para esto.
        conn.execute(
            """
            DELETE FROM notifications
            WHERE uid IN (
                SELECT uid FROM notifications
                ORDER BY received_ts ASC
                LIMIT ?
            )
        """,
            (total - _MAX_ITEMS,),
        )
        conn.commit()

    # ── API pública ─────────────────────────────────────────────────────

    def is_seen(self, uid: str) -> bool:
        conn = get_connection()
        cur = conn.execute(
            "SELECT 1 FROM notifications WHERE uid = ? LIMIT 1",
            (uid,),
        )
        return cur.fetchone() is not None

    def add_many(self, items: list[NotificationItem]) -> list[NotificationItem]:
        """Filtra los ya vistos (INSERT OR IGNORE) y devuelve los nuevos.

        Deduplica tanto contra el DB como **dentro del mismo batch** —
        si un poller devuelve 2 veces el mismo uid en una sola llamada
        (raro pero posible), solo lo contamos una vez.
        """
        if not items:
            return []
        conn = get_connection()
        new: list[NotificationItem] = []

        # Snapshot de uids ya presentes en el DB (1 query batch).
        existing_uids = {
            r["uid"]
            for r in conn.execute(
                f"SELECT uid FROM notifications WHERE uid IN ({','.join('?' * len(items))})",
                [it.uid for it in items],
            )
        }
        # Tracker de uids ya procesados EN ESTE batch — evita duplicados
        # intra-batch que sobrarían si el adapter devolvió el mismo item 2×.
        seen_in_batch: set[str] = set()

        rows: list[tuple] = []
        for it in items:
            if it.uid in existing_uids or it.uid in seen_in_batch:
                continue
            seen_in_batch.add(it.uid)
            new.append(it)
            d = it.to_dict()
            rows.append(
                (
                    it.uid,
                    it.source,
                    it.title,
                    it.summary or "",
                    it.url,
                    float(it.received_ts),
                    json.dumps(d.get("metadata") or {}, ensure_ascii=False),
                    1,  # unread por default
                )
            )

        if rows:
            conn.executemany(
                """INSERT OR IGNORE INTO notifications
                   (uid, source, title, summary, url, received_ts, metadata_json, unread)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            conn.commit()
            self._enforce_cap(conn)
        return new

    def list_all(
        self,
        *,
        source: str | None = None,
        unread_only: bool = False,
    ) -> list[dict]:
        conn = get_connection()
        where: list[str] = []
        params: list = []
        if source:
            where.append("source = ?")
            params.append(source)
        if unread_only:
            where.append("unread = 1")
        sql = "SELECT * FROM notifications"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY received_ts DESC"
        cur = conn.execute(sql, params)
        return [self._row_to_dict(r) for r in cur]

    def unread_count(self, *, source: str | None = None) -> int:
        conn = get_connection()
        if source is None:
            cur = conn.execute("SELECT COUNT(*) FROM notifications WHERE unread = 1")
        else:
            cur = conn.execute(
                "SELECT COUNT(*) FROM notifications WHERE unread = 1 AND source = ?",
                (source,),
            )
        return int(cur.fetchone()[0])

    def mark_read(self, uids: list[str]) -> int:
        if not uids:
            return 0
        conn = get_connection()
        cur = conn.execute(
            f"""UPDATE notifications SET unread = 0
                WHERE unread = 1 AND uid IN ({",".join("?" * len(uids))})""",
            uids,
        )
        conn.commit()
        return cur.rowcount or 0

    def mark_all_read(self, *, source: str | None = None) -> int:
        conn = get_connection()
        if source is None:
            cur = conn.execute("UPDATE notifications SET unread = 0 WHERE unread = 1")
        else:
            cur = conn.execute(
                "UPDATE notifications SET unread = 0 WHERE unread = 1 AND source = ?",
                (source,),
            )
        conn.commit()
        return cur.rowcount or 0


# ── Singleton acceso ────────────────────────────────────────────────────

_store: NotificationStore | None = None
_lock = threading.Lock()


def get_store() -> NotificationStore:
    global _store
    with _lock:
        if _store is None:
            _store = NotificationStore()
        return _store


def _reset_for_tests() -> None:
    """Limpia la instancia singleton — útil cuando un test cambia el
    path del DB y necesita una store fresca contra el nuevo path.
    """
    global _store
    with _lock:
        _store = None


__all__ = ["NotificationStore", "_reset_for_tests", "get_store"]
