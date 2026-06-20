"""
core.ask_user — Round-trip de preguntas interactivas al usuario
================================================================
Mecanismo que permite a un agente/tool **pausar** su ejecución y
preguntarle algo al usuario con opciones tipo menú (igual al
``AskUserQuestion`` de Claude Code), recibir la respuesta y continuar.

Flujo
-----
1. El agente invoca la tool ``ask_user(question, options, allow_other)``.
2. El handler llama a :meth:`AskUserManager.ask` que:
   - genera un ``question_id`` corto,
   - publica un evento ``ask_user.start`` al WS via el callback inyectado,
   - bloquea el thread hasta que llegue la respuesta o expire el timeout.
3. El frontend renderiza el menú, el usuario hace click, y el WS manda
   un ``ask_user.response`` que el handler de :func:`server.ws` enruta a
   :meth:`AskUserManager.submit_answer`.
4. :meth:`ask` desbloquea y devuelve la respuesta como string — eso vuelve
   a Gemini Live (o al executor) como tool-response y la conversación
   continúa con la info ya capturada.

Singleton para que el handler (que se registra una sola vez en el
ToolRegistry) y el WS (que recibe respuestas) compartan el mismo state
de preguntas pendientes.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
import contextlib

# Tipo del callback que publica al bus. Lo inyecta OrionLive.__init__.
PublishCallback = Callable[[str, str, list, bool], None]

_DEFAULT_TIMEOUT_S = 300  # 5 min — la tool registra timeout=320 para tener margen


class AskUserManager:
    """Singleton thread-safe que orquesta preguntas interactivas."""

    _instance: AskUserManager | None = None

    def __new__(cls) -> AskUserManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self) -> None:
        self._lock = threading.Lock()
        # qid → {event, answer, expires_at}
        self._pending: dict[str, dict] = {}
        self._publish: PublishCallback | None = None

    def set_publisher(self, cb: PublishCallback) -> None:
        """Lo llama OrionLive.__init__ una vez que el bus existe."""
        self._publish = cb

    def ask(
        self,
        question: str,
        options: list[dict],
        allow_other: bool = True,
        timeout: float | None = None,
    ) -> str:
        """Bloquea hasta que el usuario responda o expire el timeout.

        Devuelve siempre un string — la label elegida, el texto libre
        ingresado en "Otro", o un mensaje de "no hubo respuesta" si
        expiró. Nunca lanza excepción para no romper al agente.
        """
        if timeout is None:
            timeout = _DEFAULT_TIMEOUT_S

        qid = uuid.uuid4().hex[:12]
        event = threading.Event()
        with self._lock:
            self._pending[qid] = {
                "event": event,
                "answer": None,
                "expires_at": time.time() + timeout,
            }

        # Publica al frontend. Si el publisher no está seteado (ej. el
        # backend arrancó sin Live), no hay UI que responda y caeremos
        # al fallback de timeout — devolvemos "Sin respuesta" para que
        # el agente al menos no se cuelgue eternamente.
        if self._publish is not None:
            with contextlib.suppress(Exception):
                self._publish(qid, question, options, allow_other)

        got_answer = event.wait(timeout=timeout)
        with self._lock:
            entry = self._pending.pop(qid, None)

        if not got_answer or entry is None:
            return (
                f"[Sin respuesta del usuario tras {int(timeout)}s — "
                f"continúo con valores por defecto razonables.]"
            )
        return str(entry.get("answer") or "").strip() or "[Respuesta vacía]"

    def submit_answer(self, question_id: str, answer: str) -> bool:
        """El WS llama acá cuando el usuario clickea una opción."""
        with self._lock:
            entry = self._pending.get(question_id)
            if entry is None:
                return False
            entry["answer"] = answer
            entry["event"].set()
        return True

    def cancel(self, question_id: str) -> bool:
        """Cancelación explícita desde la UI. El agente recibe un
        marcador especial para que sepa que el usuario abortó."""
        return self.submit_answer(question_id, "[Cancelado por el usuario]")

    def pending_ids(self) -> list[str]:
        """Útil para debug / cleanup."""
        with self._lock:
            return list(self._pending.keys())


# ── Singleton accessor ──────────────────────────────────────────────────

_singleton: AskUserManager | None = None


def get_ask_user() -> AskUserManager:
    global _singleton
    if _singleton is None:
        _singleton = AskUserManager()
    return _singleton
