"""
storage.sqlite_db — Conexión central a la base SQLite de O.R.I.O.N
==================================================================
Una sola instancia de :class:`sqlite3.Connection` por proceso. WAL mode
para que múltiples hilos (poller + endpoints REST + Live session) puedan
leer simultáneo mientras alguien escribe.

Decisiones de diseño
--------------------

* **Singleton por path**: ``get_connection()`` cachea la conexión bajo
  el path actual del DB. Tests pueden cambiar el path con
  ``override_db_path_for_tests()`` y la próxima llamada abre uno fresco
  en ``tmp_path``.

* **``check_same_thread=False``**: el poller corre en otro hilo que el
  endpoint REST. Coordinamos vía WAL + transacciones cortas; el GIL
  serializa las operaciones SQLite (no hace falta nuestro propio lock).

* **Pragmas fijos** en cada apertura: WAL, foreign_keys, sincronización
  NORMAL (no FULL — WAL ya garantiza durabilidad), busy_timeout 5s.

* **Schema lazy**: cada subsistema (notificaciones, conversaciones, …)
  ejecuta su propio ``CREATE TABLE IF NOT EXISTS`` al inicializarse —
  no hay archivo central de schema porque cada dominio es independiente.
  Si en el futuro hace falta versionado, agregamos una tabla
  ``schema_migrations``.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from orion.config import SQLITE_DB_PATH
import contextlib

# ── Estado interno ──────────────────────────────────────────────────────

# Path actualmente activo. Tests pueden cambiarlo vía override.
_current_path: Path = SQLITE_DB_PATH
_connection: sqlite3.Connection | None = None
_lock = threading.Lock()


# ── API pública ─────────────────────────────────────────────────────────


def get_connection() -> sqlite3.Connection:
    """Devuelve la conexión SQLite cacheada.

    Primera llamada: abre la conexión, aplica pragmas, asegura el
    directorio padre. Siguientes llamadas: cache hit, mismo objeto.
    """
    global _connection
    with _lock:
        if _connection is None:
            _connection = _open(_current_path)
        return _connection


def init_db() -> None:
    """Fuerza la apertura (útil para inicializar en startup antes de que
    haya tráfico). Idempotente.
    """
    get_connection()


def override_db_path_for_tests(path: Path) -> None:
    """Cierra la conexión actual (si la hay) y apunta el cache a un
    nuevo path. La próxima ``get_connection()`` abre uno fresco contra
    ese path.

    SOLO usar desde tests. Producción consume ``SQLITE_DB_PATH`` del
    módulo config.
    """
    global _current_path, _connection
    with _lock:
        if _connection is not None:
            with contextlib.suppress(Exception):
                _connection.close()
            _connection = None
        _current_path = path


# ── Internos ────────────────────────────────────────────────────────────


def _open(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(path),
        # Compartido entre poller + endpoint REST + Live session.
        check_same_thread=False,
        # Permite que SELECTs muy frecuentes no bloqueen escrituras.
        timeout=5.0,
        # Devolver filas como dicts-like (acceso por nombre de columna).
        detect_types=sqlite3.PARSE_DECLTYPES,
    )
    conn.row_factory = sqlite3.Row

    # WAL: lectores no bloquean al escritor. Crítico para nuestro caso
    # (poller en background reescribe seguido mientras el frontend lee).
    conn.execute("PRAGMA journal_mode = WAL")
    # NORMAL es seguro con WAL — FULL solo añade fsync extra sin valor.
    conn.execute("PRAGMA synchronous = NORMAL")
    # Habilitamos foreign keys (off por default en sqlite).
    conn.execute("PRAGMA foreign_keys = ON")
    # 5 segundos antes de tirar SQLITE_BUSY en contención.
    conn.execute("PRAGMA busy_timeout = 5000")

    return conn
