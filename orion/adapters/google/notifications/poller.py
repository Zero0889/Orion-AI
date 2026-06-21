"""Poller en background — corre cada N minutos por adapter."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable

from orion.config import CONFIG_DIR
from orion.core.logger import get_logger

from .base import NotificationAdapter
from .classroom import ClassroomAdapter
from .gmail import GmailAdapter
from .store import get_store

log = get_logger("notif_poller")

_CONFIG_PATH = CONFIG_DIR / "notifications.json"
_DEFAULT_CONFIG: dict = {
    "enabled": True,
    "interval_seconds": 600,  # 10 min
    "max_per_source": 20,
    "sources": {
        "gmail": {"enabled": True},
        "classroom": {"enabled": True},
    },
}

# Cache del config en memoria: 30s TTL. El poller llamaba _load_config()
# 4-5 veces por ciclo (status, poll_once, _loop) — esto reduce a 1 lectura
# de disco cada 30s. La invalidación manual se hace con _invalidate_config().
_CONFIG_TTL_S = 30.0
_config_cache: dict | None = None
_config_cache_ts: float = 0.0
_config_cache_lock = threading.Lock()


def _read_config_from_disk() -> dict:
    if not _CONFIG_PATH.exists():
        try:
            _CONFIG_PATH.write_text(
                json.dumps(_DEFAULT_CONFIG, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as e:
            log.warning("no pude escribir notifications.json: %s", e)
        return dict(_DEFAULT_CONFIG)
    try:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        return {**_DEFAULT_CONFIG, **data}
    except (json.JSONDecodeError, OSError) as e:
        log.warning("config inválida, uso defaults: %s", e)
        return dict(_DEFAULT_CONFIG)


def _load_config() -> dict:
    """Devuelve la config cacheada si está fresca, si no la relee."""
    global _config_cache, _config_cache_ts
    now = time.time()
    with _config_cache_lock:
        if _config_cache is not None and (now - _config_cache_ts) < _CONFIG_TTL_S:
            return _config_cache
        _config_cache = _read_config_from_disk()
        _config_cache_ts = now
        return _config_cache


def _invalidate_config() -> None:
    """Fuerza la próxima lectura desde disco. Llamar tras editar el JSON
    vía API."""
    global _config_cache
    with _config_cache_lock:
        _config_cache = None


# ── Singleton poller ─────────────────────────────────────────────────────


class NotificationPoller:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._adapters: dict[str, NotificationAdapter] = {
            "gmail": GmailAdapter(),
            "classroom": ClassroomAdapter(),
        }
        self._publish: Callable[[str, dict], None] | None = None
        self._last_status: dict[str, dict] = {}  # source → {ok, ts, error?}

    def set_publish(self, publish: Callable[[str, dict], None]) -> None:
        """``publish(event_type, payload)`` típicamente ``bus.publish``."""
        self._publish = publish

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        cfg = _load_config()
        if not cfg.get("enabled", True):
            log.info("deshabilitado en config")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="NotifPoller",
        )
        self._thread.start()
        log.info("iniciado")

    def stop(self) -> None:
        self._stop_event.set()
        log.info("parado")

    def poll_once(self, *, only_source: str | None = None) -> dict:
        """Una vuelta manual. Útil para el botón 'Refrescar ahora' del UI."""
        cfg = _load_config()
        max_per = int(cfg.get("max_per_source", 20))
        srcs = cfg.get("sources", {})
        store = get_store()
        results: dict[str, dict] = {}

        for src, adapter in self._adapters.items():
            if only_source and only_source != src:
                continue
            if not srcs.get(src, {}).get("enabled", True):
                results[src] = {"skipped": "disabled"}
                continue
            if not adapter.is_configured():
                results[src] = {"skipped": "not_configured"}
                self._last_status[src] = {
                    "ok": False,
                    "ts": time.time(),
                    "error": "no configurado",
                }
                continue
            try:
                items = adapter.fetch(max_items=max_per)
                new = store.add_many(items)
                results[src] = {"fetched": len(items), "new": len(new)}
                self._last_status[src] = {"ok": True, "ts": time.time()}
                if new and self._publish:
                    self._publish(
                        "notification.new",
                        {
                            "source": src,
                            "count": len(new),
                            "items": [it.to_dict() for it in new],
                        },
                    )
            except Exception as e:
                msg = str(e)
                log.warning("%s falló: %s", src, msg)
                results[src] = {"error": msg}
                self._last_status[src] = {
                    "ok": False,
                    "ts": time.time(),
                    "error": msg,
                }
        return results

    def status(self) -> dict:
        # is_configured se calcula on-demand: inspecciona el filesystem para
        # detectar si el adapter ya tiene credenciales/token guardado. Esto
        # evita depender de que el poller en background haya corrido al
        # menos una vez para saber si hay que mostrar el banner "Autorizar".
        is_configured: dict[str, bool] = {}
        for src, adapter in self._adapters.items():
            try:
                is_configured[src] = bool(adapter.is_configured())
            except Exception as e:
                log.warning("is_configured(%s) falló: %s", src, e)
                is_configured[src] = False
        return {
            "running": bool(self._thread and self._thread.is_alive()),
            "last_status": self._last_status,
            "is_configured": is_configured,
            "config": _load_config(),
        }

    # ── Loop interno ────────────────────────────────────────────────────
    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception as e:
                log.error("loop excepción: %s", e, exc_info=True)
            interval = max(60, int(_load_config().get("interval_seconds", 600)))
            self._stop_event.wait(interval)


_poller: NotificationPoller | None = None
_lock = threading.Lock()


def get_poller() -> NotificationPoller:
    global _poller
    with _lock:
        if _poller is None:
            _poller = NotificationPoller()
        return _poller


def start_poller() -> None:
    get_poller().start()


def stop_poller() -> None:
    get_poller().stop()
