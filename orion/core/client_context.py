"""orion.core.client_context — Contexto del cliente que está hablando.

Cada conexión WS reporta qué tipo de dispositivo es (PC, móvil, tablet,
reloj, etc.) y un ``client_id`` persistente. Esta info la usa el prompt
builder para que Orion adapte su respuesta — más corta y orientada a
voz desde el móvil, más detallada desde la PC, etc.

API mínima:
  - :class:`ClientInfo` — dataclass con device + client_id.
  - :func:`set_last_client` — el handler WS la setea al recibir un text.
  - :func:`get_last_client` — el prompt builder la lee.

Diseño: usamos estado *module-level* en lugar de un ``ContextVar``
porque la submisión del texto al :class:`OrionLive` cruza loops
(Loop A → Loop B) y el ContextVar no se propaga gratis a través de
``run_coroutine_threadsafe``. Como Orion atiende a un usuario por vez
en una sesión Live, una variable global con lock es suficiente y mucho
más simple. Si más adelante hay multi-tenant real, refactorizar a
ContextVar + propagación explícita.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Literal

DeviceKind = Literal["desktop", "mobile", "tablet", "watch", "tv", "unknown"]

_VALID_KINDS: frozenset[str] = frozenset({"desktop", "mobile", "tablet", "watch", "tv", "unknown"})


@dataclass(frozen=True, slots=True)
class ClientInfo:
    device: DeviceKind
    client_id: str  # opaco, generado por el browser y persistido en localStorage.

    @property
    def is_mobile(self) -> bool:
        return self.device in ("mobile", "watch")

    @property
    def is_small_screen(self) -> bool:
        """Pantallas chicas: móvil + reloj. Tablet/desktop/tv son grandes."""
        return self.device in ("mobile", "watch")


def normalize_device(raw: str | None) -> DeviceKind:
    """Acepta lo que mande el cliente y devuelve un kind válido."""
    if not raw:
        return "unknown"
    val = raw.strip().lower()
    if val in _VALID_KINDS:
        return val  # type: ignore[return-value]
    # Aliases comunes que podrían llegar de UA-CH o user-agent parsing.
    if val in ("phone", "ios", "android"):
        return "mobile"
    if val in ("ipad",):
        return "tablet"
    if val in ("pc", "laptop", "mac", "windows", "linux"):
        return "desktop"
    return "unknown"


_lock = threading.Lock()
_last_client: ClientInfo | None = None


def set_last_client(info: ClientInfo) -> None:
    global _last_client
    with _lock:
        _last_client = info


def get_last_client() -> ClientInfo | None:
    """Devuelve el último cliente que envió texto. ``None`` si nadie
    declaró su dispositivo todavía (cliente legacy, primera carga, etc.)."""
    with _lock:
        return _last_client


def clear_last_client() -> None:
    global _last_client
    with _lock:
        _last_client = None


# ── Hint para el system prompt ──────────────────────────────────────────


def build_device_hint(info: ClientInfo | None = None) -> str:
    """Devuelve un bloque corto en español para inyectar al system prompt
    según el dispositivo del usuario. Cadena vacía si no hay info o si el
    device es ``unknown`` (no queremos sesgar la respuesta sin datos).

    Mantenemos el hint breve a propósito: el prompt principal manda; esto
    sólo *ajusta tono*, no redefine el personaje.
    """
    if info is None:
        info = get_last_client()
    if info is None or info.device == "unknown":
        return ""

    if info.device == "mobile":
        body = (
            "El usuario te habla desde un MÓVIL. Respuestas más cortas y "
            "directas — pensá en alguien que escucha en altavoz o lee en "
            "una pantalla chica. Evitá listas largas. Si hay mucho que "
            "decir, resumí y ofrecé entrar en detalle si lo pide."
        )
    elif info.device == "watch":
        body = (
            "El usuario te habla desde un RELOJ. Máximo 1–2 frases. "
            "Siempre voz, nunca tablas. Si la respuesta requiere detalle, "
            "sugerile abrir Orion en el celu o la PC."
        )
    elif info.device == "tablet":
        body = (
            "El usuario te habla desde una TABLET. Tono balanceado — más "
            "detalle que en móvil pero sin saturar."
        )
    elif info.device == "tv":
        body = (
            "El usuario te habla desde una TV. Respuestas leíbles a "
            "distancia: breves, directas, sin tablas densas."
        )
    elif info.device == "desktop":
        body = (
            "El usuario te habla desde la PC. Podés extenderte cuando "
            "hace falta y usar formato (listas, código) sin restricción."
        )
    else:  # defensivo — los kinds están acotados por DeviceKind.
        return ""

    return f"[DEVICE CONTEXT]\n{body}\n"
