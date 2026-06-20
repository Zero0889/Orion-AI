"""
memory.quick_notes — Notas rápidas persistentes
==================================================
Almacena notas en memory/quick_notes.json. Cada nota tiene:
    {
        "id":      "hexcorto",
        "text":    "contenido",
        "color":   "#hex" (opcional, para destacar),
        "pinned":  bool,
        "created": "2026-05-27T10:00:00",
        "updated": "2026-05-27T10:30:00",
    }
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime

from config import MEMORY_DIR
import contextlib

_NOTES_PATH = MEMORY_DIR / "quick_notes.json"
MAX_NOTES = 500
MAX_LEN = 4000
_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_all() -> list[dict]:
    if not _NOTES_PATH.exists():
        return []
    try:
        data = json.loads(_NOTES_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_all(notes: list[dict]) -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if len(notes) > MAX_NOTES:
        notes = notes[-MAX_NOTES:]
    payload = json.dumps(notes, indent=2, ensure_ascii=False)

    fd, tmp = tempfile.mkstemp(prefix=".notes_", suffix=".tmp", dir=str(MEMORY_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            with contextlib.suppress(OSError):
                os.fsync(f.fileno())
        os.replace(tmp, _NOTES_PATH)
    except OSError as e:
        print(f"[QuickNotes] ⚠️  Save error: {e}")
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass


def list_notes() -> list[dict]:
    """Retorna todas las notas, pinneadas primero, luego por updated desc."""
    with _LOCK:
        notes = _load_all()
    notes.sort(key=lambda n: (not n.get("pinned", False), -_ts(n.get("updated", ""))))
    return notes


def _ts(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso).timestamp()
    except Exception:
        return 0.0


def add_note(text: str, color: str | None = None) -> dict:
    text = (text or "").strip()
    if not text:
        return {}
    text = text[:MAX_LEN]
    with _LOCK:
        notes = _load_all()
        n = {
            "id": uuid.uuid4().hex[:8],
            "text": text,
            "color": color or "",
            "pinned": False,
            "created": _now_iso(),
            "updated": _now_iso(),
        }
        notes.append(n)
        _save_all(notes)
        return n


def update_note(
    note_id: str, *, text: str | None = None, color: str | None = None, pinned: bool | None = None
) -> bool:
    with _LOCK:
        notes = _load_all()
        for n in notes:
            if n.get("id") == note_id:
                if text is not None:
                    n["text"] = text.strip()[:MAX_LEN]
                if color is not None:
                    n["color"] = color
                if pinned is not None:
                    n["pinned"] = bool(pinned)
                n["updated"] = _now_iso()
                _save_all(notes)
                return True
    return False


def delete_note(note_id: str) -> bool:
    with _LOCK:
        notes = _load_all()
        new = [n for n in notes if n.get("id") != note_id]
        if len(new) == len(notes):
            return False
        _save_all(new)
        return True


def count_notes() -> int:
    with _LOCK:
        return len(_load_all())
