"""
core.llm — Capa de abstracción multi-proveedor para LLMs.

Cada agente de la orquesta (config/agents.json) declara qué proveedor y
modelo usa. Esta capa unifica Gemini, OpenRouter, Groq, OpenAI, Mistral
y Ollama detrás de la misma interfaz LLMProvider.complete(...).

Uso típico:

    from core.llm import LLMMessage, get_provider

    provider = get_provider("openrouter")
    resp = provider.complete(
        [LLMMessage("system", "..."), LLMMessage("user", "...")],
        model="deepseek/deepseek-chat-v3.1:free",
        temperature=0.3,
    )
    print(resp.text)
"""

from core.llm.base import (
    LLMMessage,
    LLMProvider,
    LLMResponse,
    ToolSpec,
    get_api_key,
    get_base_url,
    get_provider,
    reset_config_cache,
)

__all__ = [
    "LLMMessage",
    "LLMProvider",
    "LLMResponse",
    "ToolSpec",
    "get_api_key",
    "get_base_url",
    "get_provider",
    "reset_config_cache",
]
