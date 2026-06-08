"""
core.llm.gemini_provider — Adapter LLMProvider sobre core.gemini.

Reusa el cliente Gemini cacheado que ya existe en el proyecto (sin
duplicar la inicialización del SDK). Convierte la lista de
:class:`LLMMessage` al formato que espera ``google.genai`` (system
instruction separado del prompt).
"""

from __future__ import annotations

from core import gemini
from core.llm.base import LLMMessage, LLMProvider, LLMResponse


class GeminiProvider(LLMProvider):
    name = "gemini"

    def is_available(self) -> bool:
        try:
            from config import get_api_key
            return bool(get_api_key())
        except Exception:
            return False

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        model: str = gemini.FLASH,
        temperature: float = 0.7,
        max_tokens: int | None = None,  # Gemini lo ignora aquí; usa config interna
    ) -> LLMResponse:
        system_parts = [m.content for m in messages if m.role == "system"]
        convo_parts  = [m.content for m in messages if m.role != "system"]

        system_instruction = "\n\n".join(p for p in system_parts if p) or None
        contents = "\n\n".join(p for p in convo_parts if p) or ""

        resp = gemini.generate(
            contents,
            model=model,
            system_instruction=system_instruction,
            temperature=temperature,
        )
        text = (getattr(resp, "text", "") or "").strip()

        usage = None
        meta = getattr(resp, "usage_metadata", None)
        if meta is not None:
            usage = {
                "prompt_tokens":     getattr(meta, "prompt_token_count", None),
                "completion_tokens": getattr(meta, "candidates_token_count", None),
                "total_tokens":      getattr(meta, "total_token_count", None),
            }

        return LLMResponse(text=text, model=model, provider=self.name, usage=usage)
