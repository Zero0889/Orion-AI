"""
tests.test_agent_registry — Tests del catálogo de agentes.

Verifica:
  - El registry carga los 8 roles núcleo desde config/agents.json.
  - ``agent_can_use`` respeta la whitelist y el comodín ``*``.
  - ``agent_for_tool`` devuelve el primer agente capaz para una tool.
  - ``ask_agent`` enruta al provider correcto (mockeado).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from orion.agent import registry
from orion.core.llm.base import LLMResponse


@pytest.fixture(autouse=True)
def _fresh_cache():
    registry.reset_cache()
    yield
    registry.reset_cache()


# ── Estructura del catálogo ────────────────────────────────────────────────


def test_los_8_roles_nucleo_existen():
    ids = {a.id for a in registry.list_agents()}
    expected = {
        "director",
        "researcher",
        "coder",
        "mathematician",
        "writer",
        "analyst",
        "fileops",
        "iot",
    }
    assert expected.issubset(ids), f"Faltan agentes: {expected - ids}"


def test_director_tiene_acceso_total_a_tools():
    assert registry.agent_can_use("director", "web_search")
    assert registry.agent_can_use("director", "file_controller")
    assert registry.agent_can_use("director", "generated_code")


def test_fileops_no_puede_generar_codigo():
    # FileOps no debe tener generated_code en su whitelist
    assert not registry.agent_can_use("fileops", "generated_code")


def test_coder_puede_generar_codigo():
    assert registry.agent_can_use("coder", "generated_code")


def test_agent_for_tool_encuentra_especialista():
    # Algún agente debe poder hacer web_search (researcher típicamente)
    assert registry.agent_for_tool("web_search") is not None
    # Tool inventada → ningún agente, pero director con "*" debe ganar
    assert registry.agent_for_tool("tool_inventada_xyz") == "director"


def test_agente_inexistente_lanza_keyerror():
    with pytest.raises(KeyError):
        registry.get_agent("inexistente")


# ── ask_agent: routing al provider ─────────────────────────────────────────


class _FakeProvider:
    def __init__(self, name: str, text: str = "fake-response", available: bool = True):
        self.name = name
        self._text = text
        self._available = available
        self.last_call = None

    def is_available(self) -> bool:
        return self._available

    def complete(self, messages, *, model, temperature=0.7, max_tokens=None):
        self.last_call = {"messages": messages, "model": model, "temperature": temperature}
        return LLMResponse(text=self._text, model=model, provider=self.name)


def test_ask_agent_usa_provider_y_modelo_del_agente():
    coder = registry.get_agent("coder")
    fake = _FakeProvider(coder.provider, text="print('hi')")

    with patch("orion.agent.registry.get_provider", return_value=fake):
        out = registry.ask_agent("coder", "escribe un print")

    assert out == "print('hi')"
    assert fake.last_call["model"] == coder.model
    assert fake.last_call["temperature"] == coder.temperature
    # El system prompt del agente debe haberse inyectado primero.
    assert fake.last_call["messages"][0].role == "system"
    assert coder.system in fake.last_call["messages"][0].content


def test_ask_agent_cae_a_fallback_si_primario_no_disponible():
    coder = registry.get_agent("coder")
    assert coder.fallback_provider and coder.fallback_model

    primary = _FakeProvider(coder.provider, available=False)
    fallback = _FakeProvider(coder.fallback_provider, text="fallback-said-hi")

    def fake_get(name):
        if name == coder.provider:
            return primary
        if name == coder.fallback_provider:
            return fallback
        raise KeyError(name)

    with patch("orion.agent.registry.get_provider", side_effect=fake_get):
        out = registry.ask_agent("coder", "escribe algo")

    assert out == "fallback-said-hi"
    assert fallback.last_call["model"] == coder.fallback_model
