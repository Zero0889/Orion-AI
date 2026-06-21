"""
Tests del NotificationStore backed por SQLite (Fase 3B).

Cubre:
- Inserción + deduplicación (intra-batch y cross-batch).
- Read/unread state, mark_read y mark_all_read.
- Cap de items (LIFO sobre received_ts).
- Migración one-shot del JSON legacy.

La fixture autouse `_isolated_sqlite_db` (conftest.py) ya garantiza un
DB fresco en `tmp_path` por test y resetea el singleton del store. Acá
solo importamos y ejercitamos.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orion.actions.notifications.base import NotificationItem


@pytest.fixture
def store():
    from orion.actions.notifications import store as store_mod

    store_mod._reset_for_tests()
    return store_mod.NotificationStore()


def _mk(uid: str, *, source: str = "gmail", ts: float = 0.0, title: str = "T") -> NotificationItem:
    return NotificationItem(uid=uid, source=source, title=title, received_ts=ts)


# ── Inserción + dedup ──────────────────────────────────────────────────


def test_add_many_dedupes_cross_batch(store):
    new1 = store.add_many([_mk("a", ts=1.0), _mk("b", ts=2.0)])
    assert sorted(n.uid for n in new1) == ["a", "b"]

    # Segundo batch: re-envío los mismos + uno nuevo.
    new2 = store.add_many([_mk("a", ts=10.0), _mk("c", ts=3.0)])
    assert [n.uid for n in new2] == ["c"]

    # Total en DB: a, b, c.
    assert {it["uid"] for it in store.list_all()} == {"a", "b", "c"}


def test_add_many_dedupes_intra_batch(store):
    """Si el mismo uid llega dos veces en un solo batch, contamos uno."""
    new = store.add_many(
        [
            _mk("a", ts=1.0),
            _mk("b", ts=2.0),
            _mk("a", ts=3.0, title="dup"),  # mismo uid
        ]
    )
    assert sorted(n.uid for n in new) == ["a", "b"]
    assert len(store.list_all()) == 2


def test_add_many_empty_is_noop(store):
    assert store.add_many([]) == []
    assert store.list_all() == []


# ── Listado ────────────────────────────────────────────────────────────


def test_list_all_orders_by_received_ts_desc(store):
    store.add_many([_mk("a", ts=1.0), _mk("b", ts=3.0), _mk("c", ts=2.0)])
    assert [it["uid"] for it in store.list_all()] == ["b", "c", "a"]


def test_list_all_filters_by_source(store):
    store.add_many(
        [
            _mk("g1", source="gmail", ts=1.0),
            _mk("c1", source="classroom", ts=2.0),
            _mk("g2", source="gmail", ts=3.0),
        ]
    )
    gmails = store.list_all(source="gmail")
    assert {it["uid"] for it in gmails} == {"g1", "g2"}


def test_list_all_filters_unread_only(store):
    store.add_many([_mk("a", ts=1.0), _mk("b", ts=2.0)])
    store.mark_read(["a"])
    unread = store.list_all(unread_only=True)
    assert [it["uid"] for it in unread] == ["b"]


# ── Read state ─────────────────────────────────────────────────────────


def test_unread_count_total_and_by_source(store):
    store.add_many(
        [
            _mk("g1", source="gmail", ts=1.0),
            _mk("c1", source="classroom", ts=2.0),
        ]
    )
    assert store.unread_count() == 2
    assert store.unread_count(source="gmail") == 1
    assert store.unread_count(source="classroom") == 1


def test_mark_read_returns_affected_count(store):
    store.add_many([_mk("a", ts=1.0), _mk("b", ts=2.0), _mk("c", ts=3.0)])
    n = store.mark_read(["a", "b", "nonexistent"])
    assert n == 2
    # Re-marcar lo mismo: no cambia nada.
    n2 = store.mark_read(["a"])
    assert n2 == 0


def test_mark_all_read_global(store):
    store.add_many([_mk("a", ts=1.0), _mk("b", ts=2.0)])
    n = store.mark_all_read()
    assert n == 2
    assert store.unread_count() == 0


def test_mark_all_read_by_source(store):
    store.add_many(
        [
            _mk("g1", source="gmail", ts=1.0),
            _mk("c1", source="classroom", ts=2.0),
        ]
    )
    n = store.mark_all_read(source="gmail")
    assert n == 1
    assert store.unread_count(source="gmail") == 0
    assert store.unread_count(source="classroom") == 1


# ── Cap de items ───────────────────────────────────────────────────────


def test_enforce_cap_drops_oldest(store, monkeypatch):
    """Forzamos un cap chico para verificar la lógica sin generar 1000 items."""
    from orion.actions.notifications import store as store_mod

    monkeypatch.setattr(store_mod, "_MAX_ITEMS", 3)
    store.add_many([_mk("a", ts=1.0), _mk("b", ts=2.0), _mk("c", ts=3.0)])
    # 3 caben.
    assert len(store.list_all()) == 3
    # 4to dispara el cap — sale 'a' (el más viejo por ts).
    store.add_many([_mk("d", ts=4.0)])
    uids = {it["uid"] for it in store.list_all()}
    assert uids == {"b", "c", "d"}


# ── is_seen ────────────────────────────────────────────────────────────


def test_is_seen(store):
    store.add_many([_mk("a", ts=1.0)])
    assert store.is_seen("a") is True
    assert store.is_seen("nope") is False


# ── Migración del JSON legacy ──────────────────────────────────────────


def test_legacy_json_import(tmp_path, monkeypatch):
    """Si el JSON legacy existe en su path canónico, el store lo
    importa una vez al instanciar y luego lo archiva como .bak.
    """
    from orion.actions.notifications import store as store_mod

    legacy = tmp_path / "notifications_store.json"
    legacy.write_text(
        json.dumps(
            {
                "items": {
                    "old1": {
                        "uid": "old1",
                        "source": "gmail",
                        "title": "Viejo",
                        "summary": "del JSON",
                        "url": None,
                        "received_ts": 100.0,
                        "metadata": {"foo": "bar"},
                    },
                    "old2": {
                        "uid": "old2",
                        "source": "classroom",
                        "title": "Otro",
                        "received_ts": 200.0,
                    },
                },
                "unread": ["old1"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(store_mod, "_LEGACY_JSON_PATH", legacy)
    store_mod._reset_for_tests()

    s = store_mod.NotificationStore()

    items = s.list_all()
    uids = {it["uid"] for it in items}
    assert uids == {"old1", "old2"}

    # Metadata sobrevivió el round-trip JSON.
    old1 = next(it for it in items if it["uid"] == "old1")
    assert old1["metadata"] == {"foo": "bar"}

    # old1 estaba en unread, old2 no.
    assert s.unread_count() == 1
    unread_uids = {it["uid"] for it in s.list_all(unread_only=True)}
    assert unread_uids == {"old1"}

    # JSON original renombrado.
    assert not legacy.exists()
    bak_files = list(tmp_path.glob("notifications_store.json.migrated_to_sqlite_*.bak"))
    assert len(bak_files) == 1


def test_legacy_json_import_skipped_when_table_has_data(tmp_path, monkeypatch):
    """Si la tabla ya tiene datos, NO re-importamos del JSON (idempotencia)."""
    from orion.actions.notifications import store as store_mod

    # Primer arranque sin legacy: insertamos algo a mano.
    store_mod._reset_for_tests()
    s = store_mod.NotificationStore()
    s.add_many([_mk("real1", ts=1.0)])
    assert len(s.list_all()) == 1

    # Aparece un JSON legacy en disco.
    legacy = tmp_path / "notifications_store.json"
    legacy.write_text(
        json.dumps(
            {
                "items": {
                    "old1": {
                        "uid": "old1",
                        "source": "gmail",
                        "title": "Vieja",
                        "received_ts": 100.0,
                    }
                },
                "unread": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(store_mod, "_LEGACY_JSON_PATH", legacy)

    # Segundo arranque (nuevo store sobre el mismo DB): NO importa
    # porque ya hay data.
    store_mod._reset_for_tests()
    s2 = store_mod.NotificationStore()
    uids = {it["uid"] for it in s2.list_all()}
    assert uids == {"real1"}, "No debió re-importar el JSON legacy"
    # Y el JSON NO se archivó porque no se procesó.
    assert legacy.exists()


def test_legacy_json_missing_is_noop(tmp_path, monkeypatch):
    """Sin JSON legacy en disco, init del store no crashea."""
    from orion.actions.notifications import store as store_mod

    monkeypatch.setattr(store_mod, "_LEGACY_JSON_PATH", Path(tmp_path) / "no_such_file.json")
    store_mod._reset_for_tests()
    s = store_mod.NotificationStore()
    assert s.list_all() == []
