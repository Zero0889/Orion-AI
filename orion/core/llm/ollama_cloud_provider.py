"""
core.llm.ollama_cloud_provider — Adapter para la API nativa de Ollama Cloud.

Ollama Cloud (https://ollama.com) tiene un free tier con varios modelos
fuertes (GLM, Kimi, MiniMax, Nemotron, GPT-OSS, DeepSeek, etc.) marcados
con sufijo ``:cloud``. La API documentada es la **nativa de Ollama**:

  POST https://ollama.com/api/chat
  Authorization: Bearer <ollama_api_key>

A diferencia de OpenAI-compat (``/v1/chat/completions``), este endpoint
está oficialmente garantizado para cloud — el wrapper OpenAI funciona
para muchos deployments locales pero **no está documentado** para el
servicio gestionado.

Decisiones de diseño
--------------------
- **Sin dep externa.** Solo ``urllib`` stdlib, igual que el OpenAICompat.
- **Schema de tools idéntico a OpenAI**: ``{"type":"function", "function":{...}}``.
  Ollama usa el mismo formato — reusamos ``_normalize_openai_schema`` para
  bajar los tipos de Gemini-uppercase a JSON Schema lowercase.
- **Streaming SSE-like**: el endpoint nativo de Ollama devuelve NDJSON
  (un JSON por línea) con ``message.content`` parcial en cada línea y
  ``done: true`` en la última. Sin SSE prefix ``data:``.
- **Retry con backoff** para 429 / 5xx, mismo patrón que OpenAICompat.
"""

from __future__ import annotations

import contextlib
import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterator

from orion.core.llm.base import (
    LLMMessage,
    LLMProvider,
    LLMResponse,
    ToolSpec,
    get_api_key,
    get_base_url,
)
from orion.core.llm.openai_compat import _normalize_openai_schema, _turns_to_openai

DEFAULT_BASE_URL = "https://ollama.com"


class OllamaCloudProvider(LLMProvider):
    """Cliente HTTP de la API nativa de Ollama Cloud."""

    name = "ollama_cloud"

    def __init__(self) -> None:
        # Si el config trae un base_url con sufijo ``/v1`` (legacy de la
        # config OpenAI-compat) lo strippeamos — el endpoint nativo no
        # vive bajo /v1. Esto hace que upgrades sin tocar providers.json
        # sigan funcionando.
        raw = (get_base_url("ollama_cloud") or DEFAULT_BASE_URL).rstrip("/")
        if raw.endswith("/v1"):
            raw = raw[:-3]
        self._base_url = raw
        self._api_key = get_api_key("ollama_cloud")

    def is_available(self) -> bool:
        return bool(self._api_key)

    # ── chat (sin tools) ────────────────────────────────────────────────
    def complete(
        self,
        messages: list[LLMMessage],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        if not self.is_available():
            raise RuntimeError(
                "Ollama Cloud sin API key. Generá una en "
                "https://ollama.com/settings/keys y guardala en config/providers.json "
                "bajo 'ollama_cloud', o exportá OLLAMA_CLOUD_API_KEY."
            )

        payload: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature},
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        data = self._post(f"{self._base_url}/api/chat", payload)

        msg = data.get("message") or {}
        text = (msg.get("content") or "").strip()
        usage = self._extract_usage(data)
        return LLMResponse(
            text=text,
            model=model,
            provider=self.name,
            usage=usage,
        )

    # ── chat con tool-calling ───────────────────────────────────────────
    def complete_with_tools(
        self,
        turns: list[dict],
        tools: list[ToolSpec],
        *,
        model: str,
        temperature: float = 0.7,
    ) -> LLMResponse:
        if not self.is_available():
            raise RuntimeError("Ollama Cloud sin API key.")

        payload: dict = {
            "model": model,
            "messages": _turns_to_openai(turns),
            "stream": False,
            "options": {"temperature": temperature},
        }
        if tools:
            # Ollama acepta el schema de OpenAI textualmente. Reusamos el
            # normalizer del OpenAICompat para que GEMINI_UPPERCASE → lower.
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": _normalize_openai_schema(t.parameters)
                        or {"type": "object", "properties": {}},
                    },
                }
                for t in tools
            ]

        data = self._post(f"{self._base_url}/api/chat", payload)

        msg = data.get("message") or {}
        text = (msg.get("content") or "").strip()

        # Ollama devuelve tool_calls con el mismo shape de OpenAI:
        # [{ "function": { "name": "...", "arguments": {...} } }]
        # Diferencia: arguments puede venir como dict o como JSON string.
        raw_calls = msg.get("tool_calls") or []
        tool_calls: list[dict] = []
        for i, tc in enumerate(raw_calls):
            fn = tc.get("function") or {}
            args_raw = fn.get("arguments") or {}
            if isinstance(args_raw, str):
                try:
                    args = json.loads(args_raw)
                except json.JSONDecodeError:
                    args = {}
            elif isinstance(args_raw, dict):
                args = args_raw
            else:
                args = {}
            tool_calls.append(
                {
                    # Ollama no asigna IDs por call — fabricamos uno estable
                    # combinando turn index + nombre. El chat_brain solo
                    # los usa para correlacionar la respuesta con el call.
                    "id": tc.get("id") or f"call_{i}_{fn.get('name', 'tool')}",
                    "name": fn.get("name") or "",
                    "arguments": args,
                }
            )

        return LLMResponse(
            text=text,
            model=model,
            provider=self.name,
            usage=self._extract_usage(data),
            tool_calls=tool_calls,
        )

    # ── stream NDJSON ───────────────────────────────────────────────────
    def stream(
        self,
        messages: list[LLMMessage],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        """Stream NDJSON nativo de Ollama. Cada línea es un JSON con
        ``message.content`` (delta) y ``done: bool``."""
        if not self.is_available():
            raise RuntimeError("Ollama Cloud sin API key.")

        payload: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "options": {"temperature": temperature},
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        url = f"{self._base_url}/api/chat"
        body = json.dumps(payload).encode("utf-8")
        headers = self._headers()

        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=120) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = chunk.get("message") or {}
                    delta = msg.get("content") or ""
                    if delta:
                        yield delta
                    if chunk.get("done"):
                        return
        except urllib.error.HTTPError as e:
            detail = ""
            with contextlib.suppress(Exception):
                detail = e.read().decode("utf-8")[:300]
            raise RuntimeError(f"Ollama Cloud stream HTTP {e.code}: {detail or e.reason}") from e
        except urllib.error.URLError as e:
            # Fallback al modo no-stream si la conexión rompe.
            resp_obj = self.complete(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if resp_obj.text:
                yield resp_obj.text
            raise RuntimeError(f"Ollama Cloud red: {e.reason}") from e

    # ── HTTP helpers ─────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

    def _post(self, url: str, payload: dict, *, max_attempts: int = 4) -> dict:
        body = json.dumps(payload).encode("utf-8")
        headers = self._headers()
        last_err: Exception | None = None

        for attempt in range(max_attempts):
            try:
                req = urllib.request.Request(url, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read().decode("utf-8"))

            except urllib.error.HTTPError as e:
                last_err = e
                # 429/5xx → reintentar con backoff. Otros 4xx → error final.
                if e.code in (429, 500, 502, 503, 504) and attempt < max_attempts - 1:
                    delay = self._retry_delay(attempt, e.headers.get("Retry-After"))
                    time.sleep(delay)
                    continue
                detail = ""
                with contextlib.suppress(Exception):
                    detail = e.read().decode("utf-8")[:300]
                raise RuntimeError(f"Ollama Cloud HTTP {e.code}: {detail or e.reason}") from e

            except urllib.error.URLError as e:
                last_err = e
                if attempt < max_attempts - 1:
                    time.sleep(self._retry_delay(attempt, None))
                    continue
                raise RuntimeError(f"Ollama Cloud red: {e.reason}") from e

        raise RuntimeError(f"Ollama Cloud agotó reintentos: {last_err}")

    @staticmethod
    def _retry_delay(attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return float(retry_after)
            except (TypeError, ValueError):
                pass
        return min(1.5**attempt, 8.0)

    @staticmethod
    def _extract_usage(data: dict) -> dict | None:
        """Ollama devuelve métricas con campos ``prompt_eval_count`` /
        ``eval_count`` (tokens). Las normalizamos al shape de OpenAI para
        que el frontend pueda mostrarlas igual sin caso especial."""
        pe = data.get("prompt_eval_count")
        ec = data.get("eval_count")
        if pe is None and ec is None:
            return None
        return {
            "prompt_tokens": int(pe or 0),
            "completion_tokens": int(ec or 0),
            "total_tokens": int((pe or 0) + (ec or 0)),
        }
