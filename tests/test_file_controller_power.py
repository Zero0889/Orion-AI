"""
tests.test_file_controller_power — Operaciones pesadas de file_controller
==========================================================================
Cubre las tres acciones nuevas que reemplazan al server-filesystem MCP
para casos de uso power-user:

  * ``duplicates`` — busca archivos con contenido idéntico (3 etapas:
    tamaño → hash de cabecera → hash completo).
  * ``tree_size`` — suma recursiva por subcarpeta, ordenada.
  * ``largest`` con filtros nuevos (``extension``, ``min_size_mb``).

Usamos ``tmp_path`` para crear árboles controlados y monkeypatch sobre
``_safe_roots`` / ``_resolve_path`` para que las funciones acepten el
tmp como ruta válida.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import actions.file_controller as fc   # noqa: E402


# ── Helper: tree builder ───────────────────────────────────────────────


def _write(p: Path, content: bytes) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Permite que ``_is_safe_path`` y ``_resolve_path`` traten ``tmp_path``
    como una raíz válida durante el test."""
    monkeypatch.setattr(fc, "_safe_roots", lambda: [tmp_path])
    monkeypatch.setattr(fc, "_resolve_path", lambda raw: tmp_path / raw if raw and raw != str(tmp_path) else tmp_path)
    return tmp_path


# ── duplicates ─────────────────────────────────────────────────────────


def test_duplicates_finds_identical_pairs(sandbox):
    content_a = b"A" * 5000
    content_b = b"B" * 5000
    _write(sandbox / "dir1" / "copy1.bin", content_a)
    _write(sandbox / "dir2" / "copy2.bin", content_a)   # duplicado
    _write(sandbox / "dir2" / "copy3.bin", content_a)   # triplicado
    _write(sandbox / "unique.bin", content_b)           # único

    out = fc.find_duplicates(path=str(sandbox), min_size_kb=0.1)
    assert "Duplicados" in out
    assert "copy1.bin" in out
    assert "copy2.bin" in out
    assert "copy3.bin" in out
    assert "unique.bin" not in out
    assert "× 3 copias" in out


def test_duplicates_skips_files_below_min_size(sandbox):
    _write(sandbox / "tiny_a.txt", b"hi")
    _write(sandbox / "tiny_b.txt", b"hi")
    out = fc.find_duplicates(path=str(sandbox), min_size_kb=1.0)
    assert "Sin duplicados" in out


def test_duplicates_distinguishes_same_size_different_content(sandbox):
    """Dos archivos del mismo tamaño pero contenido distinto NO son duplicados."""
    _write(sandbox / "a.bin", b"X" * 4096)
    _write(sandbox / "b.bin", b"Y" * 4096)
    out = fc.find_duplicates(path=str(sandbox), min_size_kb=1.0)
    assert "Sin duplicados" in out
    assert "a.bin" not in out and "b.bin" not in out


def test_duplicates_filters_by_extension(sandbox):
    same = b"SAME" * 1024
    _write(sandbox / "a.pdf", same)
    _write(sandbox / "b.pdf", same)
    _write(sandbox / "c.txt", same)  # mismo contenido, otra extensión
    out = fc.find_duplicates(path=str(sandbox), min_size_kb=0.1, extension="pdf")
    assert "a.pdf" in out
    assert "b.pdf" in out
    assert "c.txt" not in out


def test_duplicates_handles_large_files(sandbox):
    """Archivos > _HASH_CHUNK_SIZE bajan a la etapa 3 (hash completo).
    Probamos con tamaño justo arriba del threshold."""
    big = (b"Z" * (fc._HASH_CHUNK_SIZE + 100))
    _write(sandbox / "big1.bin", big)
    _write(sandbox / "big2.bin", big)
    out = fc.find_duplicates(path=str(sandbox), min_size_kb=0.1)
    assert "× 2 copias" in out
    assert "big1.bin" in out
    assert "big2.bin" in out


def test_duplicates_skips_blocked_dirs(sandbox):
    """No-go directories como node_modules son skipped."""
    same = b"X" * 4096
    _write(sandbox / "a.bin", same)
    _write(sandbox / "node_modules" / "deep" / "b.bin", same)
    out = fc.find_duplicates(path=str(sandbox), min_size_kb=0.1)
    # 'a.bin' está solo (node_modules ignorado) → no duplicados
    assert "Sin duplicados" in out


# ── tree_size ──────────────────────────────────────────────────────────


def test_tree_size_lists_subfolders_sorted_by_size(sandbox):
    _write(sandbox / "fat" / "a.bin", b"X" * (10 * 1024))     # 10 KB
    _write(sandbox / "fat" / "b.bin", b"X" * (20 * 1024))     # 20 KB
    _write(sandbox / "thin" / "c.bin", b"X" * 1024)           # 1 KB
    _write(sandbox / "empty" / ".keep", b"")

    out = fc.tree_size(path=str(sandbox), depth=1, top=10)
    assert "fat" in out
    assert "thin" in out
    # 'fat' debe aparecer antes que 'thin' (más grande)
    assert out.index("fat") < out.index("thin")


def test_tree_size_respects_top_limit(sandbox):
    for i in range(5):
        _write(sandbox / f"dir{i}" / "f.bin", b"X" * (100 * (i + 1)))
    out = fc.tree_size(path=str(sandbox), depth=1, top=2)
    assert "(+ 3 subcarpetas más)" in out


def test_tree_size_returns_friendly_msg_on_empty(sandbox):
    out = fc.tree_size(path=str(sandbox), depth=1)
    assert "No hay subcarpetas" in out


# ── largest con filtros nuevos ─────────────────────────────────────────


def test_largest_with_extension_filter(sandbox):
    _write(sandbox / "a.pdf", b"X" * 5000)
    _write(sandbox / "b.pdf", b"X" * 4000)
    _write(sandbox / "c.txt", b"X" * 10000)   # más grande, pero otra ext
    out = fc.get_largest_files(path=str(sandbox), count=5, extension="pdf")
    assert "a.pdf" in out
    assert "b.pdf" in out
    assert "c.txt" not in out


def test_largest_with_min_size_filter(sandbox):
    _write(sandbox / "small.bin", b"X" * 1024)              # 1 KB
    _write(sandbox / "big.bin",   b"X" * (3 * 1024 * 1024)) # 3 MB
    out = fc.get_largest_files(path=str(sandbox), count=5, min_size_mb=1.0)
    assert "big.bin" in out
    assert "small.bin" not in out


def test_largest_friendly_empty_message_with_filters(sandbox):
    _write(sandbox / "a.txt", b"X" * 100)
    out = fc.get_largest_files(path=str(sandbox), count=5, min_size_mb=10.0)
    assert "No se encontraron" in out


# ── Dispatcher: action wiring ──────────────────────────────────────────


def test_dispatcher_routes_duplicates_action(sandbox):
    same = b"R" * 2048
    _write(sandbox / "a.bin", same)
    _write(sandbox / "b.bin", same)
    out = fc.file_controller(parameters={
        "action": "duplicates",
        "path":   str(sandbox),
        "min_size_kb": 0.1,
    })
    assert "Duplicados" in out


def test_dispatcher_routes_tree_size_action(sandbox):
    _write(sandbox / "x" / "f.bin", b"X" * 2048)
    out = fc.file_controller(parameters={
        "action": "tree_size",
        "path":   str(sandbox),
    })
    assert "Tamaño" in out
    assert "x" in out


def test_dispatcher_passes_largest_filters(sandbox):
    _write(sandbox / "a.pdf", b"X" * 5000)
    _write(sandbox / "b.txt", b"X" * 5000)
    out = fc.file_controller(parameters={
        "action":    "largest",
        "path":      str(sandbox),
        "extension": "pdf",
    })
    assert "a.pdf" in out
    assert "b.txt" not in out


# ── Tool registry: schema actualizado ──────────────────────────────────


def test_registry_advertises_new_actions():
    """tools_bootstrap declara las nuevas actions en el schema para
    Gemini y el planner."""
    from core.tool_registry import ToolRegistry
    from core.tools_bootstrap import register_builtin_tools
    ToolRegistry._reset()
    register_builtin_tools()
    decl, _ = ToolRegistry().get("file_controller")
    action_desc = decl.parameters["properties"]["action"]["description"]
    assert "duplicates" in action_desc
    assert "tree_size" in action_desc
    # Y los params nuevos están en el schema
    props = decl.parameters["properties"]
    for p in ("min_size_mb", "min_size_kb", "max_groups", "depth", "top"):
        assert p in props, f"Falta el parámetro '{p}' en el schema"
