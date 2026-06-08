"""
tests.test_llm_providers — Tests del adapter OpenAI-compatible.

No hacen llamadas HTTP reales. Mockeamos ``urllib.request.urlopen``
con un objeto que devuelve la respuesta canónica del esquema OpenAI,
y verificamos:

  - Que el payload enviado lleva ``model`` y ``messages``.
  - Que ``is_available()`` distingue Ollama (sin auth) del resto (con key).
  - Que un 429 con ``Retry-After`` activa el backoff y reintenta.
  - Que un 4xx no reintentable propaga ``RuntimeError`` con detalle.
"""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest

from core.llm.base import LLMMessage
from core.llm.openai_compat import OpenAICompatProvider


# ── Helpers ────────────────────────────────────────────────────────────────

class _FakeResp:
    """Imita ``http.client.HTTPResponse`` lo suficiente para urlopen."""

    def __init__(self, body: dict):
        self._buf = io.BytesIO(json.dumps(body).encode("utf-8"))

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _openai_response(text: str = "hola") -> dict:
    return {
        "id": "chatcmpl-x",
        "model": "test-model",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


@pytest.fixture
def provider(monkeypatch):
    """Provider OpenRouter con key fake — no se hace red real."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    from core.llm import base as base_mod
    base_mod.reset_config_cache()
    return OpenAICompatProvider("openrouter")


# ── Tests ──────────────────────────────────────────────────────────────────

def test_complete_envia_payload_correcto(provider):
    captured = {}

    def fake_urlopen(req, timeout=60):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResp(_openai_response("Hola, mundo."))

    with patch("urllib.request.urlopen", fake_urlopen):
        resp = provider.complete(
            [LLMMessage("system", "sé conciso"), LLMMessage("user", "hi")],
            model="deepseek/deepseek-chat-v3.1:free",
            temperature=0.3,
        )

    assert resp.text == "Hola, mundo."
    assert resp.provider == "openrouter"
    assert resp.model == "deepseek/deepseek-chat-v3.1:free"
    assert captured["url"].endswith("/chat/completions")
    assert captured["body"]["model"] == "deepseek/deepseek-chat-v3.1:free"
    assert captured["body"]["messages"][0] == {"role": "system", "content": "sé conciso"}
    assert captured["body"]["temperature"] == 0.3
    # Bearer del key
    auth = {k.lower(): v for k, v in captured["headers"].items()}.get("authorization")
    assert auth == "Bearer sk-test"


def test_is_available_ollama_no_requiere_key(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    from core.llm import base as base_mod
    base_mod.reset_config_cache()
    p = OpenAICompatProvider("ollama")
    assert p.is_available() is True


def test_is_available_openrouter_requiere_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    from core.llm import base as base_mod
    # Forzamos providers.json vacío para esta llamada.
    monkeypatch.setattr(base_mod, "_providers_file", lambda: {"openrouter": ""})
    p = OpenAICompatProvider("openrouter")
    assert p.is_available() is False


def test_429_con_retry_after_reintenta(provider, monkeypatch):
    import urllib.error

    calls = {"n": 0}
    delays = []

    def fake_urlopen(req, timeout=60):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(
                req.full_url, 429, "rate limit",
                {"Retry-After": "0"}, io.BytesIO(b"slow down"),
            )
        return _FakeResp(_openai_response("ok tras retry"))

    monkeypatch.setattr("time.sleep", lambda s: delays.append(s))
    with patch("urllib.request.urlopen", fake_urlopen):
        resp = provider.complete(
            [LLMMessage("user", "x")],
            model="m",
        )

    assert resp.text == "ok tras retry"
    assert calls["n"] == 2
    assert delays == [0.0]  # respetó Retry-After: 0


def test_4xx_no_reintentable_propaga_runtime(provider, monkeypatch):
    import urllib.error

    def fake_urlopen(req, timeout=60):
        raise urllib.error.HTTPError(
            req.full_url, 401, "unauthorized",
            {}, io.BytesIO(b'{"error":"bad key"}'),
        )

    monkeypatch.setattr("time.sleep", lambda s: None)
    with patch("urllib.request.urlopen", fake_urlopen):
        with pytest.raises(RuntimeError) as exc:
            provider.complete([LLMMessage("user", "x")], model="m")

    assert "401" in str(exc.value)


def test_provider_sin_credenciales_lanza_runtime(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    from core.llm import base as base_mod
    monkeypatch.setattr(base_mod, "_providers_file", lambda: {"openrouter": ""})
    p = OpenAICompatProvider("openrouter")
    with pytest.raises(RuntimeError) as exc:
        p.complete([LLMMessage("user", "x")], model="m")
    assert "credenciales" in str(exc.value).lower()
