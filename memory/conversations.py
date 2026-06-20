"""
memory.conversations — Persistencia de conversaciones de O.R.I.O.N
====================================================================
Cada conversación es:
    {
        "id":       "uuid-corto",
        "started":  "2026-05-27T14:33:00",
        "title":    "Pregunta del usuario truncada como vista previa",
        "messages": [
            {"role": "user", "text": "...", "ts": "2026-05-27T14:33:01"},
            {"role": "ai",   "text": "...", "ts": "..."},
            ...
        ]
    }

Todas se guardan en memory/conversations.json (lista), manteniendo máximo
MAX_CONVERSATIONS (50). La sesión activa se va actualizando in-place y se
re-escribe en cada cambio (escritura atómica).
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

_CONVERSATIONS_PATH = MEMORY_DIR / "conversations.json"
MAX_CONVERSATIONS = 50
MAX_MESSAGES_PER_CONV = 500  # cap por seguridad
_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_all() -> list[dict]:
    if not _CONVERSATIONS_PATH.exists():
        return []
    try:
        data = json.loads(_CONVERSATIONS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_all(convs: list[dict]) -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    # Mantener solo las últimas MAX_CONVERSATIONS
    if len(convs) > MAX_CONVERSATIONS:
        convs = convs[-MAX_CONVERSATIONS:]
    payload = json.dumps(convs, indent=2, ensure_ascii=False)

    # tempfile en el mismo dir que el destino: `os.replace` falla
    # cross-filesystem en Windows (ver memory/quick_notes.py para detalle).
    target_dir = _CONVERSATIONS_PATH.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".conv_", suffix=".tmp", dir=str(target_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            with contextlib.suppress(OSError):
                os.fsync(f.fileno())
        os.replace(tmp, _CONVERSATIONS_PATH)
    except OSError as e:
        print(f"[Conversations] ⚠️  Save error: {e}")
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass


def list_conversations() -> list[dict]:
    """Retorna metadata ligera (sin todo el contenido) ordenada por fecha desc."""
    with _LOCK:
        convs = _load_all()
    out = []
    for c in convs:
        out.append(
            {
                "id": c.get("id", ""),
                "started": c.get("started", ""),
                "title": c.get("title", "Conversación"),
                "msg_count": len(c.get("messages", [])),
            }
        )
    out.sort(key=lambda x: x["started"], reverse=True)
    return out


def get_conversation(conv_id: str) -> dict | None:
    with _LOCK:
        for c in _load_all():
            if c.get("id") == conv_id:
                return c
    return None


def delete_conversation(conv_id: str) -> bool:
    with _LOCK:
        convs = _load_all()
        n = len(convs)
        convs = [c for c in convs if c.get("id") != conv_id]
        if len(convs) == n:
            return False
        _save_all(convs)
        return True


def delete_conversations_bulk(conv_ids: list[str]) -> int:
    """Borra varias conversaciones de una. Devuelve cuántas borró."""
    if not conv_ids:
        return 0
    ids = set(conv_ids)
    with _LOCK:
        convs = _load_all()
        before = len(convs)
        convs = [c for c in convs if c.get("id") not in ids]
        deleted = before - len(convs)
        if deleted:
            _save_all(convs)
        return deleted


def delete_all_conversations() -> int:
    """Wipe completo del historial. Devuelve cuántas borró."""
    with _LOCK:
        convs = _load_all()
        n = len(convs)
        if n == 0:
            return 0
        _save_all([])
        return n


class ConversationSession:
    """Sesión activa: agrupa los mensajes y persiste al disco en cada add()."""

    def __init__(self, conv_id: str | None = None):
        self.id = conv_id or uuid.uuid4().hex[:8]
        self._started = _now_iso()
        self._messages: list[dict] = []
        self._title: str | None = None

    @property
    def title(self) -> str:
        return self._title or "Conversación"

    def add(self, role: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self._messages.append({"role": role, "text": text, "ts": _now_iso()})
        # Cap defensivo
        if len(self._messages) > MAX_MESSAGES_PER_CONV:
            self._messages = self._messages[-MAX_MESSAGES_PER_CONV:]
        # Título: primer mensaje del usuario (truncado)
        if self._title is None and role == "user":
            self._title = text[:60] + ("…" if len(text) > 60 else "")
        self._persist()

    def _persist(self) -> None:
        with _LOCK:
            convs = _load_all()
            payload = {
                "id": self.id,
                "started": self._started,
                "title": self.title,
                "messages": list(self._messages),
            }
            # Reemplazar si existe, sino append
            for i, c in enumerate(convs):
                if c.get("id") == self.id:
                    convs[i] = payload
                    break
            else:
                convs.append(payload)
            _save_all(convs)

    def messages(self) -> list[dict]:
        return list(self._messages)
