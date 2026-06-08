"""
core.llm.openai_compat — Adapter para endpoints OpenAI-compatible.

Un solo adapter cubre OpenRouter, Groq, OpenAI, Mistral, Together,
Ollama local y cualquier servidor que implemente
``POST /chat/completions`` con el mismo esquema que OpenAI. Lo único
distinto entre proveedores es ``base_url`` y la API key.

Características:

- Retry con backoff exponencial ante 429 (rate limit) y 5xx.
- Sin dependencias externas: solo ``urllib`` stdlib, así que no añade
  paquetes al ``requirements.txt`` ni al bundle de PyInstaller.
- Cabeceras opcionales para OpenRouter (``HTTP-Referer`` y ``X-Title``)
  que mejoran cuotas y aparecen en su dashboard.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Iterator

from core.llm.base import (
    LLMMessage,
    LLMProvider,
    LLMResponse,
    get_api_key,
    get_base_url,
)


# Defaults si el provider no aparece en config/providers.json -> _endpoints.
_DEFAULT_ENDPOINTS = {
    "openrouter":   "https://openrouter.ai/api/v1",
    "groq":         "https://api.groq.com/openai/v1",
    "openai":       "https://api.openai.com/v1",
    "mistral":      "https://api.mistral.ai/v1",
    "ollama":       "http://localhost:11434/v1",      # local — sin auth
    "ollama_cloud": "https://ollama.com/v1",          # cloud (Turbo) — requiere key
    "deepseek":     "https://api.deepseek.com/v1",    # DeepSeek V3 / R1
}


class OpenAICompatProvider(LLMProvider):
    """Adapter genérico para APIs OpenAI-compatible."""

    def __init__(self, name: str):
        self.name = name
        self._base_url = (get_base_url(name) or _DEFAULT_ENDPOINTS.get(name, "")).rstrip("/")
        self._api_key = get_api_key(name)
        if not self._base_url:
            raise ValueError(f"Sin base_url para provider '{name}'")

    def is_available(self) -> bool:
        # Ollama LOCAL no requiere auth (corre en localhost:11434). Ollama
        # Cloud (Turbo) sí: el sufijo distingue ambos.
        if self.name == "ollama":
            return True
        return bool(self._api_key)

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
                f"Provider '{self.name}' sin credenciales. Añade la API key en "
                f"config/providers.json o exporta {self.name.upper()}_API_KEY."
            )

        payload: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if self.name == "openrouter":
            # Recomendados por OpenRouter para que aparezca tu app en su dashboard
            # y obtengas mejores cuotas en el tier gratuito.
            headers["HTTP-Referer"] = "https://github.com/zahir/ORION"
            headers["X-Title"]      = "O.R.I.O.N"

        url = f"{self._base_url}/chat/completions"
        body = json.dumps(payload).encode("utf-8")

        data = self._post_with_retry(url, body, headers)

        try:
            text = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(
                f"{self.name} devolvió formato inesperado: {str(data)[:200]}"
            ) from e

        return LLMResponse(
            text=text,
            model=model,
            provider=self.name,
            usage=data.get("usage"),
        )

    def stream(
        self,
        messages: list[LLMMessage],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        """Stream SSE de OpenAI-compat. Emite cada delta de texto a medida
        que llega. Si el provider no soporta streaming (raro), cae al
        ``complete`` y emite el resultado entero como un solo chunk."""
        if not self.is_available():
            raise RuntimeError(
                f"Provider '{self.name}' sin credenciales."
            )

        payload: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if self.name == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/zahir/ORION"
            headers["X-Title"]      = "O.R.I.O.N"

        url = f"{self._base_url}/chat/completions"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    try:
                        delta = chunk["choices"][0]["delta"].get("content")
                    except (KeyError, IndexError, TypeError, AttributeError):
                        delta = None
                    if delta:
                        yield delta
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8")[:300]
            except Exception:
                pass
            raise RuntimeError(f"{self.name} stream HTTP {e.code}: {detail or e.reason}") from e
        except urllib.error.URLError as e:
            # Fallback al modo no-stream si el endpoint no acepta SSE.
            resp_obj = self.complete(
                messages, model=model, temperature=temperature, max_tokens=max_tokens,
            )
            yield resp_obj.text

    # ── HTTP con retry/backoff ─────────────────────────────────────────────

    @staticmethod
    def _retry_delay(attempt: int, retry_after: str | None) -> float:
        """Backoff exponencial respetando ``Retry-After`` si viene en el 429."""
        if retry_after:
            try:
                return float(retry_after)
            except (TypeError, ValueError):
                pass
        return min(1.5 ** attempt, 8.0)

    def _post_with_retry(
        self, url: str, body: bytes, headers: dict, *, max_attempts: int = 4
    ) -> dict:
        last_err: Exception | None = None

        for attempt in range(max_attempts):
            try:
                req = urllib.request.Request(url, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read().decode("utf-8"))

            except urllib.error.HTTPError as e:
                last_err = e
                # 429 (rate limit) y 5xx -> reintentamos.
                if e.code in (429, 500, 502, 503, 504) and attempt < max_attempts - 1:
                    delay = self._retry_delay(attempt, e.headers.get("Retry-After"))
                    time.sleep(delay)
                    continue
                # Otros 4xx -> error definitivo con detalle del cuerpo.
                detail = ""
                try:
                    detail = e.read().decode("utf-8")[:300]
                except Exception:
                    pass
                raise RuntimeError(
                    f"{self.name} HTTP {e.code}: {detail or e.reason}"
                ) from e

            except urllib.error.URLError as e:
                last_err = e
                if attempt < max_attempts - 1:
                    time.sleep(self._retry_delay(attempt, None))
                    continue
                raise RuntimeError(f"{self.name} red: {e.reason}") from e

        raise RuntimeError(f"{self.name} agotó reintentos: {last_err}")
