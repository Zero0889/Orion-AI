"""
core.llm.gemini_provider — Adapter LLMProvider sobre core.gemini.

Reusa el cliente Gemini cacheado que ya existe en el proyecto (sin
duplicar la inicialización del SDK). Convierte la lista de
:class:`LLMMessage` al formato que espera ``google.genai`` (system
instruction separado del prompt).

Soporta function-calling vía :meth:`complete_with_tools` traduciendo el
formato OpenAI-extendido de turnos al esquema nativo de ``google.genai``
(``types.Content`` con ``function_call`` / ``function_response`` parts).
"""

from __future__ import annotations

import uuid

from google.genai import types

from core import gemini
from core.llm.base import LLMMessage, LLMProvider, LLMResponse, ToolSpec
from core.tool_registry import _sanitize_gemini_schema


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
        convo_parts = [m.content for m in messages if m.role != "system"]

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
                "prompt_tokens": getattr(meta, "prompt_token_count", None),
                "completion_tokens": getattr(meta, "candidates_token_count", None),
                "total_tokens": getattr(meta, "total_token_count", None),
            }

        return LLMResponse(text=text, model=model, provider=self.name, usage=usage)

    # ── Function-calling ───────────────────────────────────────────────

    def complete_with_tools(
        self,
        turns: list[dict],
        tools: list[ToolSpec],
        *,
        model: str = gemini.FLASH,
        temperature: float = 0.7,
    ) -> LLMResponse:
        system_instruction, contents = _turns_to_gemini(turns)

        function_declarations = [
            {
                "name": t.name,
                "description": t.description,
                "parameters": _sanitize_gemini_schema(t.parameters or {}),
            }
            for t in tools
        ]

        config_kwargs: dict = {"temperature": temperature}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if function_declarations:
            config_kwargs["tools"] = [types.Tool(function_declarations=function_declarations)]

        config = types.GenerateContentConfig(**config_kwargs)

        client = gemini.get_client()
        resp = client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        # Parse: junta texto y function_calls de los parts
        text_chunks: list[str] = []
        tool_calls: list[dict] = []
        candidates = getattr(resp, "candidates", None) or []
        if candidates:
            parts = getattr(candidates[0].content, "parts", None) or []
            for part in parts:
                fc = getattr(part, "function_call", None)
                if fc is not None:
                    name = getattr(fc, "name", "") or ""
                    args = dict(getattr(fc, "args", None) or {})
                    tool_calls.append(
                        {
                            "id": f"call_{uuid.uuid4().hex[:12]}",
                            "name": name,
                            "arguments": args,
                        }
                    )
                else:
                    txt = getattr(part, "text", None)
                    if txt:
                        text_chunks.append(txt)

        text = "".join(text_chunks).strip()

        usage = None
        meta = getattr(resp, "usage_metadata", None)
        if meta is not None:
            usage = {
                "prompt_tokens": getattr(meta, "prompt_token_count", None),
                "completion_tokens": getattr(meta, "candidates_token_count", None),
                "total_tokens": getattr(meta, "total_token_count", None),
            }

        return LLMResponse(
            text=text,
            model=model,
            provider=self.name,
            usage=usage,
            tool_calls=tool_calls,
        )


# ── Conversión de turns (OpenAI-ext) → contents (Gemini) ────────────────


def _turns_to_gemini(turns: list[dict]) -> tuple[str | None, list]:
    """Devuelve (system_instruction, contents).

    Reglas:
      - role=system → se concatena en system_instruction (Gemini lo separa).
      - role=user → ``types.Content(role="user", parts=[Part.from_text(...)])``
      - role=assistant con tool_calls → Content role="model" + Parts con function_call.
      - role=assistant solo texto → Content role="model" + Part text.
      - role=tool → Content role="user" + Part.from_function_response(name, response).
        (Gemini espera el resultado en rol user.)
    """
    system_parts: list[str] = []
    contents: list = []

    for turn in turns:
        role = turn.get("role")
        if role == "system":
            txt = (turn.get("content") or "").strip()
            if txt:
                system_parts.append(txt)
            continue

        if role == "user":
            txt = turn.get("content") or ""
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=txt)],
                )
            )
            continue

        if role == "assistant":
            parts = []
            content_txt = turn.get("content")
            if content_txt:
                parts.append(types.Part.from_text(text=content_txt))
            for tc in turn.get("tool_calls") or []:
                parts.append(
                    types.Part(
                        function_call=types.FunctionCall(
                            name=tc.get("name", ""),
                            args=tc.get("arguments") or {},
                        )
                    )
                )
            if parts:
                contents.append(types.Content(role="model", parts=parts))
            continue

        if role == "tool":
            name = turn.get("name") or ""
            result = turn.get("content") or ""
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name=name,
                            response={"result": result},
                        )
                    ],
                )
            )
            continue

    system_instruction = "\n\n".join(system_parts) if system_parts else None
    return system_instruction, contents
