"""
Tests del SecretFilter de core.logger.

Garantiza que API keys, OAuth tokens y JWTs no escapen al disco ni a la
consola si alguien (o un traceback de una dep) los pone en un log line.
"""

from __future__ import annotations

import logging

from orion.core.logger import _SecretFilter


def _apply(msg: str, *args) -> str:
    """Pasa msg+args por el filter y devuelve el `getMessage()` redactado."""
    record = logging.LogRecord(
        name="orion.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=msg,
        args=args or None,
        exc_info=None,
    )
    _SecretFilter().filter(record)
    return record.getMessage()


def test_redacts_google_api_key():
    key = "AIzaSy" + "A" * 33
    out = _apply("error con key %s", key)
    assert key not in out
    assert "AIzaSy<redacted>" in out


def test_redacts_openai_key():
    key = "sk-" + "x" * 40
    out = _apply(f"creds: {key}")
    assert key not in out
    assert "<redacted>" in out


def test_redacts_anthropic_key():
    key = "sk-ant-" + "y" * 95
    out = _apply("anthropic auth: %s", key)
    assert key not in out


def test_redacts_openrouter_key():
    key = "sk-or-v1-" + "z" * 45
    out = _apply(key)
    assert key not in out


def test_redacts_bearer_header():
    out = _apply("headers: Authorization: Bearer abc.def.ghi-XYZ_123")
    assert "abc.def.ghi" not in out
    assert "<redacted>" in out


def test_redacts_json_api_key_field():
    out = _apply('payload: {"api_key": "supersecret-value-12345"}')
    assert "supersecret" not in out


def test_redacts_jwt_like():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.signature_part_here"
    out = _apply("token=%s", jwt)
    assert jwt not in out
    assert "<jwt-redacted>" in out


def test_normal_text_unchanged():
    out = _apply("hola mundo, sin secretos acá")
    assert out == "hola mundo, sin secretos acá"


def test_non_string_args_passthrough():
    out = _apply("count=%d, ok=%s", 42, True)
    assert "42" in out and "True" in out
