"""Persistencia simple de:
* IDs vistos (para deduplicar entre polls).
* Notificaciones actuales (cache en memoria + dump a disco para sobrevivir
  reinicios).
* Estado read/unread.

Archivo: ``config/notifications_store.json``. Formato:
``{
    "seen":   ["uid1", "uid2", …],   # IDs ya entregados al frontend
    "unread": ["uid3", …],            # subset de seen que el user aún no leyó
    "items":  {uid: NotificationItem-dict}  # cache de los últimos 200
 }``

Decisiones:
* Tope duro de 1000 ``seen`` y 200 ``items`` en cache para que el JSON no
  crezca infinito. Cuando se pasa, se descarta lo más viejo por
  ``received_ts``.
* El dump a disco se hace en cada mutación (operaciones N pequeñas — bien).
* Lock thread-safe porque el poller corre en otro hilo que el endpoint REST.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional

from config import CONFIG_DIR
from .base import NotificationItem


_STORE_PATH = CONFIG_DIR / "notifications_store.json"
_MAX_SEEN   = 1000
_MAX_ITEMS  = 200


class NotificationStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seen:   list[str] = []
        self._unread: set[str]  = set()
        self._items:  dict[str, dict] = {}   # uid → NotificationItem.to_dict()
        self._load()

    # ── Persistencia ────────────────────────────────────────────────────
    def _load(self) -> None:
        if not _STORE_PATH.exists():
            return
        try:
            data = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
            self._seen   = list(data.get("seen", []))[-_MAX_SEEN:]
            self._unread = set(data.get("unread", []))
            self._items  = dict(data.get("items", {}))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[NotifStore] ⚠️ load falló, parto vacío: {e}")

    def _save_locked(self) -> None:
        # Escritura atómica para evitar archivo corrupto si crasheamos.
        tmp = _STORE_PATH.with_suffix(".tmp")
        try:
            payload = {
                "seen":   self._seen,
                "unread": sorted(self._unread),
                "items":  self._items,
            }
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                          encoding="utf-8")
            tmp.replace(_STORE_PATH)
        except OSError as e:
            print(f"[NotifStore] ⚠️ save falló: {e}")

    # ── API ─────────────────────────────────────────────────────────────
    def is_seen(self, uid: str) -> bool:
        with self._lock:
            return uid in self._items

    def add_many(self, items: list[NotificationItem]) -> list[NotificationItem]:
        """Filtra los ya vistos y registra los nuevos. Devuelve sólo los
        nuevos (lo que el poller publica al bus)."""
        new: list[NotificationItem] = []
        if not items:
            return new
        with self._lock:
            for it in items:
                if it.uid in self._items:
                    continue
                new.append(it)
                self._seen.append(it.uid)
                self._unread.add(it.uid)
                self._items[it.uid] = it.to_dict()
            # Cota dura para evitar JSON gigante.
            if len(self._seen) > _MAX_SEEN:
                self._seen = self._seen[-_MAX_SEEN:]
            if len(self._items) > _MAX_ITEMS:
                # Por received_ts ascendente — descartamos lo más viejo.
                ordered = sorted(self._items.items(),
                               key=lambda kv: kv[1].get("received_ts", 0))
                excess  = len(self._items) - _MAX_ITEMS
                for uid, _ in ordered[:excess]:
                    self._items.pop(uid, None)
                    self._unread.discard(uid)
            if new:
                self._save_locked()
        return new

    def list_all(self, *, source: Optional[str] = None,
                 unread_only: bool = False) -> list[dict]:
        with self._lock:
            out = list(self._items.values())
        if source:
            out = [it for it in out if it.get("source") == source]
        if unread_only:
            unread = self._unread
            out = [it for it in out if it.get("uid") in unread]
        out.sort(key=lambda it: it.get("received_ts", 0), reverse=True)
        return out

    def unread_count(self, *, source: Optional[str] = None) -> int:
        with self._lock:
            if source is None:
                return len(self._unread)
            return sum(
                1 for uid in self._unread
                if self._items.get(uid, {}).get("source") == source
            )

    def mark_read(self, uids: list[str]) -> int:
        with self._lock:
            n = 0
            for uid in uids:
                if uid in self._unread:
                    self._unread.discard(uid)
                    n += 1
            if n:
                self._save_locked()
            return n

    def mark_all_read(self, *, source: Optional[str] = None) -> int:
        with self._lock:
            if source is None:
                n = len(self._unread)
                self._unread.clear()
            else:
                to_remove = [uid for uid in self._unread
                            if self._items.get(uid, {}).get("source") == source]
                for uid in to_remove:
                    self._unread.discard(uid)
                n = len(to_remove)
            if n:
                self._save_locked()
            return n


_store: Optional[NotificationStore] = None
_lock  = threading.Lock()


def get_store() -> NotificationStore:
    global _store
    with _lock:
        if _store is None:
            _store = NotificationStore()
        return _store
