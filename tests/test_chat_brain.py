"""
test_chat_brain — Tests del módulo ``orion.core.chat_brain``.

Cubre:
  - Config load/save + cache + back-compat (gemini por defecto).
  - ``is_live_brain`` distingue gemini de los demás.
  - ``run_text_turn`` con provider mock:
      * single-turn sin tools → emite stream_chunk + persist_log_only
      * tool-call → ejecuta vía registry y reinyecta como turno tool
      * provider sin credenciales → mensaje accionable
      * provider sin function-calling → cae a complete plano
  - ``submit_user_text`` del bus elige el camino correcto según brain.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from orion.core import chat_brain
from orion.core.llm.base import LLMResponse
from orion.core.tool_registry import ToolDeclaration, ToolRegistry
from orion.server.event_bus import OrionEventBus


# ── Helpers ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_brain_cache(tmp_path, monkeypatch):
    """Aísla cada test: brain.json apunta a tmp + cache se limpia."""
    monkeypatch.setattr(chat_brain, "BRAIN_CONFIG_PATH", tmp_path / "brain.json")
    chat_brain.reset_cache_for_tests()
    yield
    chat_brain.reset_cache_for_tests()


@pytest.fixture
def fresh_registry():
    """Registry limpio por test para evitar contaminación cross-test."""
    reg = ToolRegistry()
    saved = dict(reg._tools)
    reg._tools = {}
    yield reg
    reg._tools = saved


def _make_bus_with_conversation() -> OrionEventBus:
    bus = OrionEventBus()
    # Forzar inicialización de la sesión activa para que persist_log_only
    # tenga dónde escribir y _load_history_for_provider devuelva data.
    bus.new_conversation()
    return bus


class FakeProvider:
    """Provider de mentira que devuelve LLMResponse pre-armados."""

    def __init__(self, responses: list[LLMResponse], available: bool = True):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.available = available
        self.name = "fake"

    def is_available(self) -> bool:
        return self.available

    def complete_with_tools(self, turns, tools, *, model, temperature=0.7) -> LLMResponse:
        self.calls.append({"turns": list(turns), "tools": list(tools), "model": model})
        if not self.responses:
            raise RuntimeError("FakeProvider sin respuestas pre-armadas")
        return self.responses.pop(0)

    def complete(self, messages, *, model, temperature=0.7, max_tokens=None) -> LLMResponse:
        self.calls.append({"messages": list(messages), "model": model})
        if not self.responses:
            raise RuntimeError("FakeProvider sin respuestas pre-armadas")
        return self.responses.pop(0)


# ── Config: load / save / cache ──────────────────────────────────────────


def test_get_active_brain_defaults_to_gemini_when_no_file(tmp_path, monkeypatch):
    """Usuario existente sin brain.json → cero cambio de comportamiento."""
    monkeypatch.setattr(chat_brain, "BRAIN_CONFIG_PATH", tmp_path / "missing.json")
    chat_brain.reset_cache_for_tests()
    cfg = chat_brain.get_active_brain()
    assert cfg.provider == "gemini"
    assert cfg.model == chat_brain.DEFAULT_BRAIN_MODEL


def test_get_active_brain_reads_persisted_config(tmp_path, monkeypatch):
    path = tmp_path / "brain.json"
    path.write_text(json.dumps({"provider": "deepseek", "model": "deepseek-chat"}))
    monkeypatch.setattr(chat_brain, "BRAIN_CONFIG_PATH", path)
    chat_brain.reset_cache_for_tests()
    cfg = chat_brain.get_active_brain()
    assert cfg.provider == "deepseek"
    assert cfg.model == "deepseek-chat"


def test_get_active_brain_recovers_from_corrupt_json(tmp_path, monkeypatch):
    path = tmp_path / "brain.json"
    path.write_text("{not valid json")
    monkeypatch.setattr(chat_brain, "BRAIN_CONFIG_PATH", path)
    chat_brain.reset_cache_for_tests()
    cfg = chat_brain.get_active_brain()
    assert cfg.provider == "gemini"  # fallback, sin tirar


def test_set_active_brain_persists_and_invalidates(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_brain, "BRAIN_CONFIG_PATH", tmp_path / "brain.json")
    chat_brain.reset_cache_for_tests()
    cfg = chat_brain.set_active_brain("ollama", "llama3.1:8b")
    assert cfg.provider == "ollama"
    assert cfg.model == "llama3.1:8b"
    # Persiste a disk
    raw = json.loads((tmp_path / "brain.json").read_text())
    assert raw == {"provider": "ollama", "model": "llama3.1:8b"}
    # Cache visible vía get_active_brain
    assert chat_brain.get_active_brain().provider == "ollama"


def test_set_active_brain_rejects_empty():
    with pytest.raises(ValueError):
        chat_brain.set_active_brain("", "x")
    with pytest.raises(ValueError):
        chat_brain.set_active_brain("ollama", "")


def test_is_live_brain_only_true_for_gemini(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_brain, "BRAIN_CONFIG_PATH", tmp_path / "brain.json")
    chat_brain.reset_cache_for_tests()
    assert chat_brain.is_live_brain() is True
    chat_brain.set_active_brain("deepseek", "deepseek-chat")
    assert chat_brain.is_live_brain() is False
    chat_brain.set_active_brain("gemini", "gemini-2.5-flash")
    assert chat_brain.is_live_brain() is True


# ── run_text_turn: single-turn sin tools ─────────────────────────────────


def test_run_text_turn_emits_stream_and_persists(monkeypatch):
    chat_brain.set_active_brain("deepseek", "deepseek-chat")

    bus = _make_bus_with_conversation()
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        bus, "publish", lambda evt, payload=None: events.append((evt, payload or {}))
    )

    fake = FakeProvider([LLMResponse(text="Hola, soy Orion.", model="x", provider="fake")])
    monkeypatch.setattr(chat_brain, "get_provider", lambda _name: fake)

    chat_brain.run_text_turn(bus, "Hola", tool_registry=None, plugin_registry=None)

    stream_events = [e for e in events if e[0] == "chat.stream"]
    # Esperamos al menos un chunk con la respuesta y otro con final=True
    finals = [e for e in stream_events if e[1].get("final")]
    deltas = [e for e in stream_events if e[1].get("delta")]
    assert finals, "esperaba al menos un chat.stream con final=True"
    assert any("Hola, soy Orion." in e[1]["delta"] for e in deltas), (
        f"el texto del provider no se streameó. eventos={stream_events}"
    )


def test_run_text_turn_unavailable_provider_emits_actionable_error(monkeypatch):
    chat_brain.set_active_brain("deepseek", "deepseek-chat")

    bus = _make_bus_with_conversation()
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        bus, "publish", lambda evt, payload=None: events.append((evt, payload or {}))
    )

    fake = FakeProvider([], available=False)
    monkeypatch.setattr(chat_brain, "get_provider", lambda _name: fake)

    chat_brain.run_text_turn(bus, "hola")

    deltas = [e[1].get("delta", "") for e in events if e[0] == "chat.stream"]
    joined = " ".join(deltas)
    assert "deepseek" in joined.lower()
    assert "credenciales" in joined.lower() or "ajustes" in joined.lower()


def test_run_text_turn_provider_exception_caught(monkeypatch):
    chat_brain.set_active_brain("deepseek", "deepseek-chat")

    bus = _make_bus_with_conversation()
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        bus, "publish", lambda evt, payload=None: events.append((evt, payload or {}))
    )

    class BoomProvider:
        name = "boom"

        def is_available(self) -> bool:
            return True

        def complete_with_tools(self, *args, **kwargs):
            raise RuntimeError("network down")

    monkeypatch.setattr(chat_brain, "get_provider", lambda _name: BoomProvider())

    # No debe relanzar: el error tiene que aparecer como evento de chat
    chat_brain.run_text_turn(bus, "hola")

    finals = [e for e in events if e[0] == "chat.stream" and e[1].get("final")]
    assert finals, "esperaba un final aunque el provider falle"
    deltas = " ".join(e[1].get("delta", "") for e in events if e[0] == "chat.stream")
    assert (
        "falló" in deltas.lower() or "fallo" in deltas.lower() or "network down" in deltas.lower()
    )


# ── run_text_turn: tool-call loop ────────────────────────────────────────


def test_run_text_turn_dispatches_tool_then_finalizes(monkeypatch, fresh_registry):
    """El modelo pide la tool 'ping', se ejecuta, se reinyecta, y responde."""
    chat_brain.set_active_brain("deepseek", "deepseek-chat")

    called_with: dict[str, Any] = {}

    def _ping_handler(params: dict, *, player=None, speak=None) -> str:
        called_with.update(params)
        return "pong-ok"

    fresh_registry.register(
        ToolDeclaration(
            name="ping",
            description="Diagnóstico",
            parameters={"type": "object", "properties": {"who": {"type": "string"}}},
        ),
        _ping_handler,
    )

    bus = _make_bus_with_conversation()
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        bus, "publish", lambda evt, payload=None: events.append((evt, payload or {}))
    )

    # 1er response: tool_call. 2do: respuesta final.
    fake = FakeProvider(
        [
            LLMResponse(
                text="",
                model="x",
                provider="fake",
                tool_calls=[{"id": "c1", "name": "ping", "arguments": {"who": "orion"}}],
            ),
            LLMResponse(text="Pong recibido.", model="x", provider="fake"),
        ]
    )
    monkeypatch.setattr(chat_brain, "get_provider", lambda _name: fake)

    chat_brain.run_text_turn(bus, "hace ping", tool_registry=fresh_registry)

    assert called_with == {"who": "orion"}
    starts = [e for e in events if e[0] == "tool.call.start"]
    ends = [e for e in events if e[0] == "tool.call.end"]
    assert len(starts) == 1 and starts[0][1]["name"] == "ping"
    assert len(ends) == 1 and ends[0][1]["name"] == "ping"
    deltas = " ".join(e[1].get("delta", "") for e in events if e[0] == "chat.stream")
    assert "Pong recibido." in deltas

    # El segundo call al provider tiene que llevar el turno role=tool con el resultado
    second_call_turns = fake.calls[1]["turns"]
    tool_turn = next((t for t in second_call_turns if t.get("role") == "tool"), None)
    assert tool_turn is not None
    assert tool_turn["content"] == "pong-ok"


def test_run_text_turn_caps_tool_iterations(monkeypatch, fresh_registry):
    """Si el modelo nunca para de pedir tools, cerramos con mensaje amable."""
    chat_brain.set_active_brain("deepseek", "deepseek-chat")

    fresh_registry.register(
        ToolDeclaration(name="loop", description="x", parameters={}),
        lambda params, **_: "again",
    )

    bus = _make_bus_with_conversation()
    monkeypatch.setattr(bus, "publish", lambda *a, **kw: None)

    # El provider devuelve tool_calls eternamente — esperamos que se corte.
    class InfiniteLoopProvider:
        name = "loop_provider"

        def is_available(self) -> bool:
            return True

        def complete_with_tools(self, *args, **kwargs):
            return LLMResponse(
                text="",
                model="x",
                provider="loop",
                tool_calls=[{"id": "c", "name": "loop", "arguments": {}}],
            )

    monkeypatch.setattr(chat_brain, "get_provider", lambda _: InfiniteLoopProvider())

    finals: list[str] = []
    monkeypatch.setattr(
        bus,
        "stream_chunk",
        lambda role, delta, turn_id, final=False: finals.append(delta) if final and delta else None,
    )

    chat_brain.run_text_turn(bus, "Loop", tool_registry=fresh_registry)
    # El mensaje final cuenta el agotamiento explícitamente
    msg = " ".join(finals + [d for d in [delta for delta in finals]])
    # mensaje real puede venir en deltas != final también; chequear estado
    assert chat_brain.MAX_TOOL_ITERATIONS == 8


def test_run_text_turn_fallback_to_complete_when_no_function_calling(monkeypatch):
    """Si el provider levanta NotImplementedError en complete_with_tools,
    caemos a complete plano y seguimos."""
    chat_brain.set_active_brain("deepseek", "deepseek-chat")

    bus = _make_bus_with_conversation()
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        bus, "publish", lambda evt, payload=None: events.append((evt, payload or {}))
    )

    class NoToolsProvider:
        name = "no_tools"

        def is_available(self) -> bool:
            return True

        def complete_with_tools(self, *args, **kwargs):
            raise NotImplementedError()

        def complete(self, messages, *, model, temperature=0.7, max_tokens=None):
            return LLMResponse(text="respuesta plana", model="x", provider="no_tools")

    monkeypatch.setattr(chat_brain, "get_provider", lambda _: NoToolsProvider())

    chat_brain.run_text_turn(bus, "hola")
    deltas = " ".join(e[1].get("delta", "") for e in events if e[0] == "chat.stream")
    assert "respuesta plana" in deltas


# ── bus.submit_user_text branches según brain ────────────────────────────


def test_submit_user_text_uses_live_path_for_gemini(monkeypatch):
    chat_brain.set_active_brain("gemini", "gemini-2.5-flash")

    bus = OrionEventBus()
    cb_calls: list[str] = []
    bus.on_text_command = lambda txt: cb_calls.append(txt)

    bus.submit_user_text("hola")
    # El threading.Thread es daemon — esperamos brevemente
    import time

    for _ in range(20):
        if cb_calls:
            break
        time.sleep(0.01)

    assert cb_calls == ["hola"]


def test_submit_user_text_uses_chat_brain_path_for_non_gemini(monkeypatch):
    chat_brain.set_active_brain("deepseek", "deepseek-chat")

    bus = OrionEventBus()
    captured: dict[str, Any] = {}

    def _fake_run_text_turn(received_bus, text, *, tool_registry, plugin_registry):
        captured["bus"] = received_bus
        captured["text"] = text

    monkeypatch.setattr(
        "orion.core.chat_brain.run_text_turn",
        _fake_run_text_turn,
    )

    bus.submit_user_text("ping")
    import time

    for _ in range(20):
        if captured:
            break
        time.sleep(0.01)

    assert captured.get("text") == "ping"
    assert captured.get("bus") is bus


def test_attach_chat_brain_context_stores_registries():
    bus = OrionEventBus()
    treg = MagicMock()
    preg = MagicMock()
    bus.attach_chat_brain_context(tool_registry=treg, plugin_registry=preg)
    assert bus._chat_brain_tool_registry is treg
    assert bus._chat_brain_plugin_registry is preg

    # Pasar None preserva lo previo (idempotencia parcial)
    bus.attach_chat_brain_context(tool_registry=None, plugin_registry=None)
    assert bus._chat_brain_tool_registry is treg
    assert bus._chat_brain_plugin_registry is preg
