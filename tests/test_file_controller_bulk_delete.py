"""
tests.test_file_controller_bulk_delete — Borrado masivo con safety
===================================================================
Cubre las tres acciones nuevas:

  * ``delete_bulk``           — por pattern/extension/edad/tamaño
  * ``delete_duplicates``     — limpieza tras find_duplicates
  * ``delete_empty_folders``  — recursivo bottom-up

Y especialmente el **safety pattern**:

  - dry_run=True por default → solo PREVIEW, no borra
  - Para ejecutar: dry_run=False + confirm=True
  - dry_run=False sin confirm → REFUSE
  - delete_bulk sin filtros → REFUSE
  - Hard cap de 10k archivos por operación
  - Todo va a la papelera (send2trash), no destrucción permanente
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import actions.file_controller as fc

# ── Helpers ─────────────────────────────────────────────────────────────


def _write(p: Path, content: bytes = b"x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def _backdate(p: Path, days_ago: float) -> None:
    """Modifica mtime para simular un archivo de hace N días."""
    ts = time.time() - days_ago * 86400
    import os

    os.utime(p, (ts, ts))


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(fc, "_safe_roots", lambda: [tmp_path])
    monkeypatch.setattr(
        fc,
        "_resolve_path",
        lambda raw: tmp_path / raw if raw and raw != str(tmp_path) else tmp_path,
    )
    return tmp_path


@pytest.fixture
def trash_spy(monkeypatch):
    """Reemplaza _safe_trash por uno que solo registra qué se hubiera borrado
    (los tests no deberían tocar la papelera real de Windows)."""
    deleted: list[Path] = []

    def fake_trash(target: Path):
        deleted.append(target)
        try:
            target.unlink() if target.is_file() else target.rmdir()
        except Exception:
            pass
        return f"Mock-trashed: {target.name}"

    monkeypatch.setattr(fc, "_safe_trash", fake_trash)
    return deleted


# ══════════════════════════════════════════════════════════════════════
#  delete_bulk
# ══════════════════════════════════════════════════════════════════════


def test_bulk_dry_run_does_not_delete(sandbox, trash_spy):
    _write(sandbox / "a.log", b"x" * 10)
    _write(sandbox / "b.log", b"x" * 10)
    out = fc.delete_bulk(path=str(sandbox), extension="log", dry_run=True)
    assert "PREVIEW" in out
    assert "2 archivo" in out
    assert trash_spy == []  # no se tocó nada
    assert (sandbox / "a.log").exists()


def test_bulk_dry_run_includes_explanation_for_next_step(sandbox):
    _write(sandbox / "a.tmp", b"x")
    out = fc.delete_bulk(path=str(sandbox), pattern="*.tmp", dry_run=True)
    assert "dry_run=false" in out and "confirm=true" in out


def test_bulk_requires_confirm_when_executing(sandbox, trash_spy):
    _write(sandbox / "a.log", b"x")
    out = fc.delete_bulk(path=str(sandbox), extension="log", dry_run=False, confirm=False)
    assert "Bloqueado" in out
    assert trash_spy == []
    assert (sandbox / "a.log").exists()


def test_bulk_executes_when_dry_run_false_and_confirm_true(sandbox, trash_spy):
    _write(sandbox / "a.log", b"x")
    _write(sandbox / "b.log", b"x")
    _write(sandbox / "c.txt", b"x")  # no debe tocarse
    out = fc.delete_bulk(path=str(sandbox), extension="log", dry_run=False, confirm=True)
    assert "Listo" in out
    assert "2/2" in out
    names = {p.name for p in trash_spy}
    assert names == {"a.log", "b.log"}
    assert (sandbox / "c.txt").exists()


def test_bulk_refuses_without_any_filter(sandbox, trash_spy):
    _write(sandbox / "a", b"x")
    out = fc.delete_bulk(path=str(sandbox), dry_run=False, confirm=True)
    assert "requiere AL MENOS un filtro" in out
    assert trash_spy == []
    assert (sandbox / "a").exists()


def test_bulk_pattern_filter(sandbox):
    _write(sandbox / "Thumbs.db", b"x")
    _write(sandbox / "a~", b"x")
    _write(sandbox / "real.txt", b"x")
    out = fc.delete_bulk(path=str(sandbox), pattern="Thumbs.db", dry_run=True)
    assert "Thumbs.db" in out
    assert "real.txt" not in out


def test_bulk_older_than_days(sandbox):
    new_file = _write(sandbox / "new.bin", b"x")
    old_file = _write(sandbox / "old.bin", b"x")
    _backdate(old_file, 90)
    out = fc.delete_bulk(path=str(sandbox), older_than_days=30, dry_run=True)
    assert "old.bin" in out
    assert "new.bin" not in out


def test_bulk_larger_than_mb(sandbox):
    _write(sandbox / "small.bin", b"x" * 1024)
    _write(sandbox / "big.bin", b"x" * (3 * 1024 * 1024))
    out = fc.delete_bulk(path=str(sandbox), larger_than_mb=1.0, dry_run=True)
    assert "big.bin" in out
    assert "small.bin" not in out


def test_bulk_smaller_than_mb(sandbox):
    _write(sandbox / "small.bin", b"x" * 1024)
    _write(sandbox / "big.bin", b"x" * (3 * 1024 * 1024))
    out = fc.delete_bulk(path=str(sandbox), smaller_than_mb=1.0, dry_run=True)
    assert "small.bin" in out
    assert "big.bin" not in out


def test_bulk_combines_filters_with_AND(sandbox):
    _write(sandbox / "small.log", b"x" * 100)
    _write(sandbox / "big.log", b"x" * (3 * 1024 * 1024))
    _write(sandbox / "big.txt", b"x" * (3 * 1024 * 1024))
    out = fc.delete_bulk(path=str(sandbox), extension="log", larger_than_mb=1.0, dry_run=True)
    # solo big.log cumple AMBOS (ext=log AND >1MB)
    assert "big.log" in out
    assert "small.log" not in out
    assert "big.txt" not in out


def test_bulk_friendly_empty_when_nothing_matches(sandbox):
    _write(sandbox / "a.txt", b"x")
    out = fc.delete_bulk(path=str(sandbox), extension="pdf", dry_run=True)
    assert "Nada que borrar" in out


# ══════════════════════════════════════════════════════════════════════
#  delete_duplicates
# ══════════════════════════════════════════════════════════════════════


def test_dup_dry_run_lists_what_would_be_deleted(sandbox, trash_spy):
    same = b"S" * 4096
    _write(sandbox / "original.bin", same)
    _write(sandbox / "deep" / "nested" / "copy.bin", same)
    out = fc.delete_duplicates(path=str(sandbox), min_size_kb=0.1, dry_run=True)
    assert "PREVIEW" in out
    assert trash_spy == []
    # Por default keep=shortest_path → conserva el del root, borra el del nested
    assert "copy.bin" in out
    assert "original.bin" not in out.split("PREVIEW", 1)[1].split("Para ejecutar")[0]


def test_dup_keep_shortest_path_default(sandbox, trash_spy):
    same = b"X" * 4096
    short = _write(sandbox / "x.bin", same)
    long_path = _write(sandbox / "very" / "deeply" / "nested" / "x.bin", same)
    out = fc.delete_duplicates(path=str(sandbox), min_size_kb=0.1, dry_run=False, confirm=True)
    assert "Listo" in out
    assert long_path in trash_spy
    assert short not in trash_spy


def test_dup_keep_newest_keeps_newer_file(sandbox, trash_spy):
    same = b"X" * 4096
    older = _write(sandbox / "a.bin", same)
    newer = _write(sandbox / "b.bin", same)
    _backdate(older, 30)  # older = 30 días atrás
    # newer queda con mtime actual
    fc.delete_duplicates(
        path=str(sandbox), keep="newest", min_size_kb=0.1, dry_run=False, confirm=True
    )
    assert older in trash_spy
    assert newer not in trash_spy


def test_dup_keep_oldest_keeps_older_file(sandbox, trash_spy):
    same = b"X" * 4096
    older = _write(sandbox / "a.bin", same)
    newer = _write(sandbox / "b.bin", same)
    _backdate(older, 30)
    fc.delete_duplicates(
        path=str(sandbox), keep="oldest", min_size_kb=0.1, dry_run=False, confirm=True
    )
    assert newer in trash_spy
    assert older not in trash_spy


def test_dup_invalid_keep_policy_refuses(sandbox, trash_spy):
    _write(sandbox / "a", b"x")
    out = fc.delete_duplicates(path=str(sandbox), keep="random")
    assert "Política 'keep' inválida" in out
    assert trash_spy == []


def test_dup_refuses_without_confirm(sandbox, trash_spy):
    same = b"X" * 4096
    _write(sandbox / "a.bin", same)
    _write(sandbox / "b.bin", same)
    out = fc.delete_duplicates(path=str(sandbox), min_size_kb=0.1, dry_run=False, confirm=False)
    assert "Bloqueado" in out
    assert trash_spy == []


def test_dup_friendly_empty_when_no_duplicates(sandbox, trash_spy):
    _write(sandbox / "a.bin", b"unique-a" * 100)
    _write(sandbox / "b.bin", b"unique-b" * 100)
    out = fc.delete_duplicates(path=str(sandbox), min_size_kb=0.1, dry_run=True)
    assert "Nada que borrar" in out
    assert trash_spy == []


# ══════════════════════════════════════════════════════════════════════
#  delete_empty_folders
# ══════════════════════════════════════════════════════════════════════


def test_empty_folders_dry_run(sandbox, trash_spy):
    # Estructura: empty1/, empty2/, with_file/(.keep), full/file.txt
    (sandbox / "empty1").mkdir()
    (sandbox / "empty2").mkdir()
    _write(sandbox / "full" / "file.txt", b"x")
    out = fc.delete_empty_folders(path=str(sandbox), dry_run=True)
    assert "PREVIEW" in out
    assert "empty1" in out
    assert "empty2" in out
    assert "full" not in out.split("PREVIEW", 1)[1]
    assert trash_spy == []


def test_empty_folders_executes_with_confirm(sandbox, trash_spy):
    (sandbox / "ghost").mkdir()
    _write(sandbox / "real" / "file.txt", b"x")
    out = fc.delete_empty_folders(path=str(sandbox), dry_run=False, confirm=True)
    assert "Listo" in out
    assert any(p.name == "ghost" for p in trash_spy)
    assert (sandbox / "real").exists()


def test_empty_folders_never_deletes_root(sandbox, trash_spy):
    """Aunque la raíz esté vacía, NUNCA debe entrar al kill-list."""
    # sandbox está vacío
    out = fc.delete_empty_folders(path=str(sandbox), dry_run=False, confirm=True)
    assert "No hay carpetas vacías" in out
    assert trash_spy == []
    assert sandbox.exists()


def test_empty_folders_bottom_up_chain(sandbox, trash_spy):
    """outer/middle/inner sin archivos → las tres deben listarse en preview."""
    (sandbox / "outer" / "middle" / "inner").mkdir(parents=True)
    out = fc.delete_empty_folders(path=str(sandbox), dry_run=True)
    assert "inner" in out
    assert "middle" in out
    assert "outer" in out


def test_empty_folders_refuses_without_confirm(sandbox, trash_spy):
    (sandbox / "ghost").mkdir()
    out = fc.delete_empty_folders(path=str(sandbox), dry_run=False, confirm=False)
    assert "Bloqueado" in out
    assert (sandbox / "ghost").exists()


# ══════════════════════════════════════════════════════════════════════
#  Dispatcher wiring
# ══════════════════════════════════════════════════════════════════════


def test_dispatcher_routes_delete_bulk(sandbox, trash_spy):
    _write(sandbox / "a.tmp", b"x")
    out = fc.file_controller(
        parameters={
            "action": "delete_bulk",
            "path": str(sandbox),
            "extension": "tmp",
            "dry_run": True,
        }
    )
    assert "PREVIEW" in out


def test_dispatcher_routes_delete_duplicates(sandbox, trash_spy):
    same = b"R" * 2048
    _write(sandbox / "a.bin", same)
    _write(sandbox / "b.bin", same)
    out = fc.file_controller(
        parameters={
            "action": "delete_duplicates",
            "path": str(sandbox),
            "min_size_kb": 0.1,
            "dry_run": True,
        }
    )
    assert "PREVIEW" in out


def test_dispatcher_routes_delete_empty_folders(sandbox, trash_spy):
    (sandbox / "ghost").mkdir()
    out = fc.file_controller(
        parameters={
            "action": "delete_empty_folders",
            "path": str(sandbox),
            "dry_run": True,
        }
    )
    assert "PREVIEW" in out
    assert "ghost" in out


# ══════════════════════════════════════════════════════════════════════
#  Registry schema advertises the new actions
# ══════════════════════════════════════════════════════════════════════


def test_registry_advertises_bulk_delete_actions():
    from core.tool_registry import ToolRegistry
    from core.tools_bootstrap import register_builtin_tools

    ToolRegistry._reset()
    register_builtin_tools()
    decl, _ = ToolRegistry().get("file_controller")
    action_desc = decl.parameters["properties"]["action"]["description"]
    for a in ("delete_bulk", "delete_duplicates", "delete_empty_folders"):
        assert a in action_desc, f"Falta '{a}' en el schema"
    # Y los flags de safety
    props = decl.parameters["properties"]
    assert "dry_run" in props
    assert "confirm" in props
    # El description top-level menciona el patrón dry-run para que el LLM lo siga
    assert "dry_run" in decl.description.lower()
