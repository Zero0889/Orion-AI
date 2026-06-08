"""
tests.test_mcp_client — Suite del cliente MCP
=============================================

Cubre:

  * Parsing de ``MCPServerConfig`` desde dict (defaults, enabled flag,
    timeouts).
  * ``load_servers_config`` con archivo inexistente, JSON inválido,
    config válida con servers enabled/disabled.
  * ``_convert_schema`` — conversión MCP (lowercase) → Gemini (UPPER),
    recursión, items de array, default OBJECT cuando hay properties.
  * ``_make_tool_name`` — namespacing + sanitización para Gemini.
  * ``MCPServer`` end-to-end con el fake server de
    ``tests/fixtures/fake_mcp_server.py``: handshake, list, call, error,
    stop.
  * ``MCPManager.start_all()`` registra las tools del fake server en el
    ``ToolRegistry`` con nombres namespaceados.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.mcp_client import (   # noqa: E402
    MCPManager,
    MCPServer,
    MCPServerConfig,
    MCPServerError,
    _convert_schema,
    _make_tool_name,
    load_servers_config,
)
from core.tool_registry import ToolRegistry  # noqa: E402


FAKE_SERVER = PROJECT_ROOT / "tests" / "fixtures" / "fake_mcp_server.py"


# ── Config parsing ──────────────────────────────────────────────────────


def test_config_from_dict_defaults():
    cfg = MCPServerConfig.from_dict("foo", {"command": "echo"})
    assert cfg.server_id == "foo"
    assert cfg.command == "echo"
    assert cfg.args == []
    assert cfg.env == {}
    assert cfg.enabled is True
    assert cfg.cwd is None
    assert cfg.startup_timeout == 15.0
    assert cfg.call_timeout == 60.0


def test_config_from_dict_full():
    raw = {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        "env": {"TOKEN": "abc"},
        "enabled": False,
        "cwd": "/work",
        "startup_timeout": 5,
        "call_timeout": 30,
    }
    cfg = MCPServerConfig.from_dict("fs", raw)
    assert cfg.command == "npx"
    assert cfg.args == ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    assert cfg.env == {"TOKEN": "abc"}
    assert cfg.enabled is False
    assert cfg.cwd == "/work"
    assert cfg.startup_timeout == 5.0
    assert cfg.call_timeout == 30.0


def test_load_config_missing_file(tmp_path):
    assert load_servers_config(tmp_path / "nope.json") == []


def test_load_config_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ not json")
    # No debe explotar — devuelve lista vacía y loggea
    assert load_servers_config(p) == []


def test_load_config_filters_disabled(tmp_path):
    p = tmp_path / "ok.json"
    p.write_text(json.dumps({
        "servers": {
            "alpha": {"command": "echo", "enabled": True},
            "beta":  {"command": "echo", "enabled": False},
            "gamma": {"command": "echo"},  # enabled=True default
        }
    }))
    cfgs = load_servers_config(p)
    ids = {c.server_id for c in cfgs}
    assert ids == {"alpha", "gamma"}


def test_load_config_skips_malformed_entries(tmp_path):
    p = tmp_path / "mixed.json"
    p.write_text(json.dumps({
        "servers": {
            "ok":  {"command": "echo"},
            "bad": {"no_command_here": True},
        }
    }))
    cfgs = load_servers_config(p)
    assert [c.server_id for c in cfgs] == ["ok"]


# ── Schema conversion ──────────────────────────────────────────────────


def test_convert_schema_basic_types():
    src = {
        "type": "object",
        "properties": {
            "name":  {"type": "string"},
            "age":   {"type": "integer"},
            "ok":    {"type": "boolean"},
            "price": {"type": "number"},
        },
        "required": ["name"],
    }
    out = _convert_schema(src)
    assert out["type"] == "OBJECT"
    assert out["properties"]["name"]["type"] == "STRING"
    assert out["properties"]["age"]["type"] == "INTEGER"
    assert out["properties"]["ok"]["type"] == "BOOLEAN"
    assert out["properties"]["price"]["type"] == "NUMBER"
    # 'required' se preserva tal cual
    assert out["required"] == ["name"]


def test_convert_schema_nested_array_items():
    src = {
        "type": "object",
        "properties": {
            "tags": {"type": "array", "items": {"type": "string"}},
        },
    }
    out = _convert_schema(src)
    assert out["properties"]["tags"]["type"] == "ARRAY"
    assert out["properties"]["tags"]["items"]["type"] == "STRING"


def test_convert_schema_defaults_to_object_when_properties_present():
    # Algunos servidores omiten 'type' y solo listan 'properties'
    src = {"properties": {"x": {"type": "string"}}}
    out = _convert_schema(src)
    assert out["type"] == "OBJECT"


def test_convert_schema_preserves_descriptions():
    src = {"type": "object", "properties": {
        "msg": {"type": "string", "description": "Hello"},
    }}
    out = _convert_schema(src)
    assert out["properties"]["msg"]["description"] == "Hello"


def test_convert_schema_non_dict_passthrough():
    assert _convert_schema("string") == "string"
    assert _convert_schema(42) == 42
    assert _convert_schema(None) is None


# ── Tool naming ────────────────────────────────────────────────────────


def test_make_tool_name_namespaces():
    assert _make_tool_name("fs", "list_directory") == "fs__list_directory"


def test_make_tool_name_sanitizes_invalid_chars():
    # Gemini exige [a-zA-Z_][a-zA-Z0-9_]*
    name = _make_tool_name("my-server", "do.thing!")
    assert name == "my_server__do_thing_"
    assert all(c.isalnum() or c == "_" for c in name)


# ── MCPServer end-to-end con fake server ───────────────────────────────


@pytest.fixture
def fake_server_config():
    return MCPServerConfig(
        server_id="fake",
        command=sys.executable,
        args=[str(FAKE_SERVER)],
        startup_timeout=10.0,
        call_timeout=10.0,
    )


@pytest.fixture
def started_server(fake_server_config):
    server = MCPServer(fake_server_config)
    server.start()
    yield server
    server.stop()


def test_mcp_server_handshake_and_tool_list(started_server):
    tool_names = {t["name"] for t in started_server.tools}
    assert tool_names == {"echo", "fail"}


def test_mcp_server_call_echo(started_server):
    result = started_server.call_tool("echo", {"message": "hola"})
    assert result == "ECHO: hola"


def test_mcp_server_call_error_raises(started_server):
    with pytest.raises(MCPServerError, match="intentional failure"):
        started_server.call_tool("fail", {})


def test_mcp_server_call_unknown_method_raises(started_server):
    with pytest.raises(MCPServerError):
        started_server.call_tool("does_not_exist", {})


def test_mcp_server_stop_kills_subprocess(fake_server_config):
    server = MCPServer(fake_server_config)
    server.start()
    proc = server._proc
    assert proc is not None
    server.stop()
    # Dale al SO un instante para procesar la terminación
    time.sleep(0.1)
    assert proc.poll() is not None, "El subprocess debería estar terminado"


def test_mcp_server_start_with_bad_command_raises():
    cfg = MCPServerConfig(
        server_id="bad",
        command="this_binary_does_not_exist_anywhere_xyz",
        startup_timeout=2.0,
    )
    server = MCPServer(cfg)
    with pytest.raises(MCPServerError):
        server.start()


# ── MCPManager + ToolRegistry integration ──────────────────────────────


@pytest.fixture
def clean_registry():
    ToolRegistry._reset()
    yield ToolRegistry()
    ToolRegistry._reset()


def _write_config(tmp_path: Path, servers: dict) -> Path:
    p = tmp_path / "mcp_servers.json"
    p.write_text(json.dumps({"servers": servers}))
    return p


def test_manager_start_all_with_empty_config(tmp_path, clean_registry):
    p = tmp_path / "empty.json"
    p.write_text(json.dumps({"servers": {}}))
    mgr = MCPManager(config_path=p)
    assert mgr.start_all() == 0
    assert mgr.servers() == {}


def test_manager_start_all_registers_namespaced_tools(tmp_path, clean_registry):
    config_path = _write_config(tmp_path, {
        "fake": {
            "command": sys.executable,
            "args": [str(FAKE_SERVER)],
            "startup_timeout": 10,
            "call_timeout": 10,
        }
    })
    mgr = MCPManager(config_path=config_path)
    try:
        n = mgr.start_all()
        assert n == 2  # echo + fail
        # Tools registradas con namespacing
        assert clean_registry.has("fake__echo")
        assert clean_registry.has("fake__fail")
        # Y son llamables vía el registry (mismo path que executor/main)
        result = clean_registry.call_sync("fake__echo", {"message": "wired"})
        assert result == "ECHO: wired"
    finally:
        mgr.stop_all()


def test_manager_skips_failed_server_and_continues(tmp_path, clean_registry):
    """Un servidor que no arranca no debe tumbar al resto."""
    config_path = _write_config(tmp_path, {
        "broken": {
            "command": "this_binary_does_not_exist_xyz",
            "startup_timeout": 2,
        },
        "fake": {
            "command": sys.executable,
            "args": [str(FAKE_SERVER)],
            "startup_timeout": 10,
            "call_timeout": 10,
        },
    })
    mgr = MCPManager(config_path=config_path)
    try:
        n = mgr.start_all()
        # Solo 'fake' registró sus 2 tools
        assert n == 2
        assert "fake" in mgr.servers()
        assert "broken" not in mgr.servers()
    finally:
        mgr.stop_all()


def test_manager_tool_appears_in_planner_text(tmp_path, clean_registry):
    """Las tools MCP llevan include_in_planner=True por default,
    así que el planner las ve."""
    from core.tools_bootstrap import register_builtin_tools
    register_builtin_tools()

    config_path = _write_config(tmp_path, {
        "fake": {
            "command": sys.executable,
            "args": [str(FAKE_SERVER)],
            "startup_timeout": 10,
            "call_timeout": 10,
        }
    })
    mgr = MCPManager(config_path=config_path)
    try:
        mgr.start_all()
        text = clean_registry.to_planner_text()
        assert "fake__echo" in text
        assert "fake__fail" in text
    finally:
        mgr.stop_all()
