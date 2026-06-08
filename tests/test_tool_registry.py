"""
tests.test_tool_registry
========================
Red de seguridad para el refactor de unificación del registro de tools.

Verifica:
    1. Las 22 tools builtin + 4 stubs Live-only quedan registradas.
    2. Cada declaración tiene el shape correcto para Gemini Live
       (type=OBJECT, properties, required).
    3. ``call_sync`` despacha al handler correcto y respeta la firma
       normalizada (player / speak / current_file).
    4. Los timeouts que main.py tenía hardcoded se preservan.
    5. ``to_planner_text`` lista las tools no-silent.
    6. ``to_gemini_declarations`` produce el formato exacto que la
       LiveConnectConfig espera.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.tool_registry import ToolDeclaration, ToolRegistry  # noqa: E402
from core.tools_bootstrap import register_builtin_tools        # noqa: E402


# Las 22 tools que main.py tenía en TOOL_DECLARATIONS antes del refactor.
EXPECTED_TOOLS = {
    "open_app", "web_search", "weather_report", "send_message",
    "reminder", "youtube_video", "screen_process", "computer_settings",
    "browser_control", "file_controller", "desktop_control", "code_helper",
    "dev_agent", "agent_task", "computer_control", "game_updater",
    "flight_finder", "shutdown_orion", "file_processor", "quick_note",
    "save_memory", "iot_control", "google_drive", "classroom",
}

# Stub Live-only — main.py reemplaza estos handlers al arrancar.
LIVE_ONLY_TOOLS = {"agent_task", "shutdown_orion", "quick_note", "save_memory"}

# Timeouts que main.py tenía en _TOOL_TIMEOUTS (los != 60).
EXPECTED_TIMEOUTS = {
    "dev_agent":      300,
    "game_updater":   300,
    "agent_task":     30,
    "code_helper":    180,
    "file_processor": 180,
    "google_drive":   120,
    "flight_finder":  90,
}


@pytest.fixture
def fresh_registry():
    """Cada test arranca con un registry recién inicializado."""
    ToolRegistry._reset()
    register_builtin_tools()
    yield ToolRegistry()
    ToolRegistry._reset()


def test_all_expected_tools_registered(fresh_registry):
    names = set(fresh_registry.names())
    missing = EXPECTED_TOOLS - names
    extra = names - EXPECTED_TOOLS
    assert not missing, f"Faltan tools en el registry: {missing}"
    assert not extra, f"Tools inesperadas en el registry: {extra}"


def test_every_tool_has_valid_gemini_schema(fresh_registry):
    for decl in fresh_registry.all():
        params = decl.parameters
        assert isinstance(params, dict), f"{decl.name}: parameters debe ser dict"
        assert params.get("type") == "OBJECT", \
            f"{decl.name}: parameters.type debe ser OBJECT (Gemini), no '{params.get('type')}'"
        assert "properties" in params, f"{decl.name}: falta 'properties'"
        # 'required' es opcional pero si está debe ser lista
        if "required" in params:
            assert isinstance(params["required"], list), \
                f"{decl.name}: 'required' debe ser lista"


def test_property_types_are_uppercase_gemini(fresh_registry):
    """Gemini Live exige tipos en MAYÚSCULAS: STRING, INTEGER, BOOLEAN, NUMBER, ARRAY."""
    valid_types = {"STRING", "INTEGER", "BOOLEAN", "NUMBER", "ARRAY", "OBJECT"}
    for decl in fresh_registry.all():
        props = decl.parameters.get("properties", {})
        for pname, pdef in props.items():
            t = pdef.get("type")
            assert t in valid_types, \
                f"{decl.name}.{pname}: tipo '{t}' inválido para Gemini"


def test_to_gemini_declarations_shape(fresh_registry):
    decls = fresh_registry.to_gemini_declarations()
    assert len(decls) == len(EXPECTED_TOOLS)
    for d in decls:
        assert set(d.keys()) == {"name", "description", "parameters"}
        assert isinstance(d["name"], str)
        assert isinstance(d["description"], str)
        assert isinstance(d["parameters"], dict)


def test_timeouts_preserved(fresh_registry):
    timeouts = fresh_registry.timeouts()
    for name, expected in EXPECTED_TIMEOUTS.items():
        assert timeouts.get(name) == expected, \
            f"{name}: timeout esperado {expected}s, registrado {timeouts.get(name)}s"


def test_live_only_stubs_return_explanatory_message(fresh_registry):
    for name in LIVE_ONLY_TOOLS:
        result = fresh_registry.call_sync(name, {})
        assert "Live" in result or "voz" in result, \
            f"{name}: stub debe mencionar Live/voz, devolvió: {result}"


def test_call_sync_raises_on_unknown_tool(fresh_registry):
    with pytest.raises(KeyError, match="desconocida"):
        fresh_registry.call_sync("does_not_exist", {})


def test_call_sync_dispatches_to_handler(fresh_registry):
    """Verifica que call_sync llama al handler real y le pasa los kwargs
    correctos. Usamos open_app porque tiene una firma simple."""
    sentinel = object()

    def fake_open_app(parameters=None, response=None, player=None):
        # Verifica que el registry pasa player y NO pasa speak/current_file
        assert parameters == {"app_name": "Notepad"}
        assert response is None
        assert player is sentinel
        return "MOCKED-OK"

    with patch("actions.open_app.open_app", fake_open_app):
        result = fresh_registry.call_sync(
            "open_app",
            {"app_name": "Notepad"},
            player=sentinel,
        )
    assert result == "MOCKED-OK"


def test_call_sync_passes_speak_when_declared(fresh_registry):
    """code_helper declara needs_speak=True; el registry debe pasarlo."""
    speak_mock = lambda msg: None

    def fake_code(parameters=None, player=None, speak=None):
        assert speak is speak_mock
        return "CODE-OK"

    with patch("actions.code_helper.code_helper", fake_code):
        result = fresh_registry.call_sync(
            "code_helper",
            {"action": "write", "description": "x"},
            speak=speak_mock,
        )
    assert result == "CODE-OK"


def test_call_sync_omits_speak_when_not_declared(fresh_registry):
    """open_app no declara needs_speak=True; el handler NO debe recibir speak."""
    def fake_open_app(parameters=None, response=None, player=None, **kwargs):
        # 'speak' no debe estar en kwargs
        assert "speak" not in kwargs, f"speak no debería pasarse: {kwargs}"
        return "OK"

    with patch("actions.open_app.open_app", fake_open_app):
        fresh_registry.call_sync(
            "open_app",
            {"app_name": "X"},
            speak=lambda _: None,  # pasamos speak pero la tool no lo declara
        )


def test_call_sync_injects_current_file(fresh_registry):
    """file_processor declara needs_current_file=True. Si parameters no
    trae file_path y el registry recibe current_file, se inyecta."""
    captured = {}

    def fake_fp(parameters=None, player=None, speak=None):
        captured["params"] = parameters
        return "FP-OK"

    with patch("actions.file_processor.file_processor", fake_fp):
        fresh_registry.call_sync(
            "file_processor",
            {"action": "summarize"},
            current_file=r"C:\tmp\foo.pdf",
        )
    assert captured["params"]["file_path"] == r"C:\tmp\foo.pdf"


def test_call_sync_respects_explicit_file_path(fresh_registry):
    """Si parameters ya trae file_path, current_file NO debe sobreescribirlo."""
    captured = {}

    def fake_fp(parameters=None, player=None, speak=None):
        captured["params"] = parameters
        return "FP-OK"

    with patch("actions.file_processor.file_processor", fake_fp):
        fresh_registry.call_sync(
            "file_processor",
            {"action": "summarize", "file_path": r"C:\explicit.pdf"},
            current_file=r"C:\should_be_ignored.pdf",
        )
    assert captured["params"]["file_path"] == r"C:\explicit.pdf"


def test_to_planner_text_lists_non_silent_tools(fresh_registry):
    text = fresh_registry.to_planner_text()
    # save_memory está marcada silent — NO debe aparecer
    assert "save_memory" not in text
    # Tools normales sí
    for name in ("open_app", "web_search", "file_controller", "iot_control"):
        assert name in text, f"{name} debería estar en el planner text"


def test_to_planner_text_excludes_live_only_meta_tools(fresh_registry):
    """agent_task / shutdown_orion / quick_note llevan
    include_in_planner=False — el planner no debe verlos para no
    meta-orquestarse a sí mismo ni tomar notas."""
    text = fresh_registry.to_planner_text()
    for name in ("agent_task", "shutdown_orion", "quick_note"):
        assert name not in text, \
            f"{name} no debería aparecer en el planner text"


def test_to_planner_text_includes_param_descriptions(fresh_registry):
    text = fresh_registry.to_planner_text()
    # open_app tiene app_name como required string
    assert "app_name" in text
    assert "required" in text


def test_register_replaces_duplicate_name(fresh_registry):
    """Re-registrar con el mismo name reemplaza (último gana)."""
    fresh_registry.register(
        ToolDeclaration(name="open_app", description="OVERRIDDEN", parameters={"type": "OBJECT"}),
        lambda params, **_: "NEW",
    )
    result = fresh_registry.call_sync("open_app", {})
    assert result == "NEW"


def test_register_rejects_empty_name(fresh_registry):
    with pytest.raises(ValueError, match="name"):
        fresh_registry.register(
            ToolDeclaration(name="", description="x", parameters={}),
            lambda p, **_: "x",
        )


def test_singleton_persists(fresh_registry):
    """ToolRegistry() devuelve siempre la misma instancia."""
    a = ToolRegistry()
    b = ToolRegistry()
    assert a is b is fresh_registry
