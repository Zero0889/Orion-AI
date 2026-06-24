"""
core.llm.base — Interfaz LLMProvider y resolución de credenciales.

El registro es perezoso: ``get_provider("openrouter")`` instancia el
adapter la primera vez y lo cachea. Las API keys se resuelven en este
orden:

  1. Variable de entorno ``{PROVIDER}_API_KEY`` (ej. ``OPENROUTER_API_KEY``)
  2. Campo del mismo nombre en ``config/providers.json``

Si una key no aparece en ningún sitio, el provider queda "no disponible"
y los agentes que dependen de él caen al fallback que decida el
``executor`` (típicamente el Director con Gemini).
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import lru_cache

from orion.config import BASE_DIR

# ── Tipos de datos ──────────────────────────────────────────────────────────


@dataclass
class LLMMessage:
    """Un turno de la conversación. ``role`` ∈ {system, user, assistant}."""

    role: str
    content: str


@dataclass
class LLMResponse:
    """Respuesta normalizada de cualquier proveedor."""

    text: str
    model: str
    provider: str
    usage: dict | None = field(default=None)
    # Tool-calls que el modelo decidió disparar en este turno. Vacío si la
    # respuesta es solo texto. Cada item: {"id": str, "name": str, "arguments": dict}.
    tool_calls: list[dict] = field(default_factory=list)


@dataclass
class ToolSpec:
    """Descripción de una tool tal como la ve el LLM (function-calling).

    Campos minimalistas para que cada provider pueda traducirlos al formato
    nativo de su API (OpenAI tools, Gemini function_declarations, etc.).
    """

    name: str
    description: str
    parameters: dict = field(default_factory=dict)


# ── Interfaz ────────────────────────────────────────────────────────────────


class LLMProvider(ABC):
    """Contrato común para todos los proveedores LLM de la orquesta."""

    name: str = "unknown"

    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Genera una respuesta. Cada adapter convierte ``messages`` al
        formato nativo de su API y devuelve un :class:`LLMResponse`."""

    def stream(
        self,
        messages: list[LLMMessage],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        """Genera respuesta como stream de chunks de texto.

        Default: fallback que llama a ``complete`` y emite la respuesta
        completa como un solo chunk. Los providers que soportan SSE
        nativo (OpenAI-compat, Anthropic) deben sobrescribir esto.
        """
        resp = self.complete(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        yield resp.text

    def is_available(self) -> bool:
        """¿El provider tiene credenciales y se puede usar?"""
        return True

    def complete_with_tools(
        self,
        turns: list[dict],
        tools: list[ToolSpec],
        *,
        model: str,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Variante function-calling de :meth:`complete`.

        ``turns`` usa el formato OpenAI extendido para que el provider lo
        convierta a su formato nativo. Cada turno:

          - ``{"role": "system",    "content": str}``
          - ``{"role": "user",      "content": str}``
          - ``{"role": "assistant", "content": str|None,
                "tool_calls": [{"id", "name", "arguments": dict}] | None}``
          - ``{"role": "tool",      "tool_call_id": str, "name": str, "content": str}``

        El provider devuelve ``LLMResponse`` cuyo ``tool_calls`` puede tener
        0..N entradas. Si tiene 0, la respuesta es final (``text``). Si tiene
        N, el caller debe ejecutar las tools, añadir los resultados como
        turnos ``role="tool"`` y volver a llamar.

        Default: providers que no implementen function-calling pueden caer
        al ``complete`` plano (perdiendo el tool-use).
        """
        raise NotImplementedError(f"Provider '{self.name}' no soporta function-calling todavía.")


# ── Resolución de credenciales ──────────────────────────────────────────────


@lru_cache(maxsize=1)
def _providers_file() -> dict:
    path = BASE_DIR / "config" / "providers.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def get_api_key(provider: str) -> str:
    """Env var > config/providers.json. Strings vacíos = no configurada."""
    if key := os.environ.get(f"{provider.upper()}_API_KEY"):
        return key.strip()
    value = _providers_file().get(provider, "")
    return str(value).strip() if value else ""


def get_base_url(provider: str) -> str:
    return _providers_file().get("_endpoints", {}).get(provider, "")


def reset_config_cache() -> None:
    """Invalida el cache si editas providers.json en caliente."""
    _providers_file.cache_clear()
    # También limpiamos los provider singletons: si la key cambió, la nueva
    # instancia toma el valor nuevo en su constructor (los OpenAICompat
    # leen la key en __init__). Sin esto, set_provider_key seguía usando
    # la instancia vieja con la key vacía.
    _INSTANCES.clear()


def set_provider_key(provider: str, key: str) -> None:
    """Persiste la API key de ``provider`` en ``config/providers.json``.

    Si el archivo no existe lo crea con la estructura mínima (provider
    como key, valor como key). Preserva el resto de campos. Invalida los
    caches al terminar para que la próxima llamada a ``get_provider`` use
    la key nueva sin reiniciar la app.

    Pasar ``key=""`` borra la entrada (no la deja como string vacío).
    """
    provider = (provider or "").strip().lower()
    if not provider:
        raise ValueError("provider obligatorio")
    path = BASE_DIR / "config" / "providers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except (json.JSONDecodeError, OSError):
            data = {}
    key = (key or "").strip()
    if key:
        data[provider] = key
    else:
        data.pop(provider, None)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    reset_config_cache()


# ── Registro perezoso ───────────────────────────────────────────────────────

_INSTANCES: dict[str, LLMProvider] = {}

_OPENAI_COMPAT = {"openrouter", "groq", "openai", "mistral", "ollama", "ollama_cloud", "deepseek"}


def get_provider(name: str) -> LLMProvider:
    """Devuelve el adapter ya instanciado (lo crea la primera vez)."""
    if name in _INSTANCES:
        return _INSTANCES[name]

    if name == "gemini":
        from orion.core.llm.gemini_provider import GeminiProvider

        _INSTANCES[name] = GeminiProvider()
    elif name in _OPENAI_COMPAT:
        from orion.core.llm.openai_compat import OpenAICompatProvider

        _INSTANCES[name] = OpenAICompatProvider(name)
    else:
        raise KeyError(
            f"Provider '{name}' desconocido. Conocidos: gemini, {', '.join(sorted(_OPENAI_COMPAT))}"
        )

    return _INSTANCES[name]
