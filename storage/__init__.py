"""
storage — Capa de persistencia SQLite de O.R.I.O.N (Fase 3B).

Antes había varios módulos cada uno haciendo `json.dumps + atomic write`
sobre archivos planos. A medida que esos archivos crecen (en particular
``config/notifications_store.json``, 127KB y subiendo) la latencia y el
riesgo de corrupción aumentan. Acá centralizamos el acceso a un único
SQLite con WAL para concurrencia y queries reales.

Lo que NO está acá: los módulos de dominio (notificaciones, conversaciones,
quick_notes, long-term memory). Ellos consumen ``storage.get_connection()``
y manejan su propio schema.
"""

from __future__ import annotations

from .sqlite_db import get_connection, init_db, override_db_path_for_tests

__all__ = ["get_connection", "init_db", "override_db_path_for_tests"]
