"""
core.mcp_client — Cliente MCP (Model Context Protocol) para O.R.I.O.N
=====================================================================
Cliente mínimo sin dependencias externas para hablar JSON-RPC 2.0 sobre
stdio con servidores MCP de terceros (filesystem, github, slack, etc.).

Diseño
------

* **Transport**: stdio newline-delimited JSON (spec MCP 2024-11-05).
* **Sync**: cada llamada bloquea hasta recibir respuesta o timeout. El
  ``ToolRegistry`` ya despacha tools de forma sync; main.py las envuelve
  en ``run_in_executor`` cuando importa.
* **Sin deps nuevas**: solo ``subprocess`` + ``threading`` + ``json`` +
  ``shutil``. Esto evita arrastrar la cadena async del SDK oficial
  ``mcp`` (~30 paquetes).
* **Namespacing**: las tools MCP se registran como
  ``<server_id>__<tool_name>`` para evitar choques con builtins.

Vida del proceso
----------------

``MCPManager.start_all()`` spawnea cada subprocess, hace handshake,
lista tools y las registra en el ``ToolRegistry``. Si un servidor falla
al arrancar (binario no encontrado, handshake timeout, etc.) se loggea
el error y ORION sigue arrancando — los otros servidores y los builtins
no se ven afectados.

``MCPManager.stop_all()`` se llama al apagar ORION para terminar los
subprocesses limpiamente (SIGTERM, esperar 2s, kill si sigue vivo).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orion.core.tool_registry import ToolDeclaration, ToolRegistry

log = logging.getLogger("orion.mcp")


# ── Config ──────────────────────────────────────────────────────────────


@dataclass
class MCPServerConfig:
    """Una entrada en ``config/mcp_servers.json``."""

    server_id: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    cwd: str | None = None
    # Timeout para el handshake inicial (initialize + tools/list).
    startup_timeout: float = 15.0
    # Timeout default para cada tools/call.
    call_timeout: float = 60.0

    @classmethod
    def from_dict(cls, server_id: str, raw: dict) -> MCPServerConfig:
        return cls(
            server_id=server_id,
            command=raw["command"],
            args=list(raw.get("args", [])),
            env=dict(raw.get("env", {})),
            enabled=bool(raw.get("enabled", True)),
            cwd=raw.get("cwd"),
            startup_timeout=float(raw.get("startup_timeout", 15.0)),
            call_timeout=float(raw.get("call_timeout", 60.0)),
        )


def load_servers_config(path: Path) -> list[MCPServerConfig]:
    """Lee ``config/mcp_servers.json`` y devuelve la lista de configs.

    Si el archivo no existe o está vacío, devuelve []. Errores de parseo
    se loggean pero no abortan — preferimos que ORION arranque con
    builtins-only que no arranque nada.
    """
    if not path.exists():
        log.info("mcp_servers.json no existe en %s — MCP deshabilitado", path)
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("mcp_servers.json inválido (%s) — MCP deshabilitado", e)
        return []

    servers_raw = raw.get("servers") or {}
    configs: list[MCPServerConfig] = []
    for sid, entry in servers_raw.items():
        try:
            cfg = MCPServerConfig.from_dict(sid, entry)
            if cfg.enabled:
                configs.append(cfg)
        except (KeyError, TypeError, ValueError) as e:
            log.warning("Servidor MCP '%s' mal configurado: %s", sid, e)
    return configs


# ── Schema conversion (MCP → Gemini) ────────────────────────────────────

# JSON Schema lowercase types → Gemini OBJECT/STRING/INTEGER/...
_TYPE_MAP = {
    "object": "OBJECT",
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
}


def _convert_schema(schema: Any) -> Any:
    """Convierte un JSON Schema MCP (tipos en lowercase) al dialecto que
    Gemini Live espera (tipos en MAYÚSCULAS). Recursivo para nested.
    """
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for k, v in schema.items():
        if k == "type" and isinstance(v, str):
            out[k] = _TYPE_MAP.get(v.lower(), v.upper())
        elif k == "properties" and isinstance(v, dict):
            out[k] = {pk: _convert_schema(pv) for pk, pv in v.items()}
        elif k == "items":
            out[k] = _convert_schema(v)
        else:
            out[k] = v
    # Si no había type y hay properties, asumimos OBJECT (lo que MCP
    # implica por defecto cuando solo lista properties).
    if "type" not in out and "properties" in out:
        out["type"] = "OBJECT"
    return out


# ── MCP Server (un subprocess) ──────────────────────────────────────────


class MCPServerError(RuntimeError):
    """Cualquier fallo del transporte o del protocolo MCP."""


class MCPServer:
    """Wrapper sobre un subprocess MCP que habla JSON-RPC sobre stdio.

    Thread-safety: ``call`` puede ser invocado desde threads distintos.
    Hay un solo writer (lock interno) y un reader thread que despacha
    respuestas por id.
    """

    PROTOCOL_VERSION = "2024-11-05"

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._proc: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # JSON-RPC request id counter
        self._next_id = 1
        self._id_lock = threading.Lock()

        # Pending requests: id → (Event, container for response/error)
        self._pending: dict[int, tuple[threading.Event, dict]] = {}
        self._pending_lock = threading.Lock()

        # Writer lock — un único thread puede estar escribiendo a stdin a la vez
        self._write_lock = threading.Lock()

        # Tools descubiertas tras el handshake
        self.tools: list[dict] = []

    # ── Lifecycle ───────────────────────────────────────────────────

    def start(self) -> None:
        """Spawnea el subprocess, hace handshake y lista tools."""
        cmd_path = shutil.which(self.config.command) or self.config.command
        full_cmd = [cmd_path, *self.config.args]

        env = os.environ.copy()
        env.update(self.config.env)

        log.info("[MCP %s] spawn: %s", self.config.server_id, " ".join(full_cmd))
        # Forzamos UTF-8 también en el child (npx/uvx a veces escriben
        # mensajes en cp1252 que rompen el decode). PYTHONIOENCODING ayuda a
        # los wrappers Python; NODE_OPTIONS no aplica acá pero igual no
        # estorba. ``errors='replace'`` en el Popen + reader es la red
        # de seguridad final.
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        try:
            self._proc = subprocess.Popen(
                full_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.config.cwd,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",  # tolera bytes no-UTF8 (Windows console)
                bufsize=1,  # line-buffered
            )
        except (FileNotFoundError, OSError) as e:
            raise MCPServerError(f"No se pudo arrancar '{self.config.command}': {e}") from e

        self._reader_thread = threading.Thread(
            target=self._read_loop,
            name=f"MCPReader-{self.config.server_id}",
            daemon=True,
        )
        self._reader_thread.start()

        # Handshake
        deadline = time.monotonic() + self.config.startup_timeout
        try:
            self._initialize(deadline)
            self._send_notification("notifications/initialized", {})
            self.tools = self._list_tools(deadline)
            log.info(
                "[MCP %s] listo — %d tools descubiertas",
                self.config.server_id,
                len(self.tools),
            )
        except Exception:
            self.stop()
            raise

    def stop(self, grace_period: float = 2.0) -> None:
        """Termina el subprocess. Best-effort, no levanta excepción."""
        self._stop_event.set()
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=grace_period)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=1.0)
        except Exception as e:
            log.warning("[MCP %s] error al terminar: %s", self.config.server_id, e)
        self._proc = None

    # ── JSON-RPC framing ────────────────────────────────────────────

    def _next_request_id(self) -> int:
        with self._id_lock:
            i = self._next_id
            self._next_id += 1
            return i

    def _send_raw(self, message: dict) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise MCPServerError("Subprocess no está corriendo")
        line = json.dumps(message, ensure_ascii=False) + "\n"
        with self._write_lock:
            try:
                self._proc.stdin.write(line)
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError) as e:
                raise MCPServerError(f"stdin cerrado: {e}") from e

    def _send_request(self, method: str, params: dict, timeout: float) -> dict:
        """Envía request, bloquea hasta tener respuesta. Devuelve `result`."""
        req_id = self._next_request_id()
        event = threading.Event()
        container: dict = {}
        with self._pending_lock:
            self._pending[req_id] = (event, container)

        msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        try:
            self._send_raw(msg)
            remaining = max(0.0, timeout - 0.0)
            if not event.wait(timeout=remaining):
                raise MCPServerError(f"Timeout esperando respuesta a '{method}' ({timeout}s)")
            if "error" in container:
                err = container["error"]
                raise MCPServerError(
                    f"Servidor MCP devolvió error en '{method}': {err.get('message', err)}"
                )
            return container.get("result", {})
        finally:
            with self._pending_lock:
                self._pending.pop(req_id, None)

    def _send_notification(self, method: str, params: dict) -> None:
        """Notification = sin id, sin respuesta esperada."""
        self._send_raw({"jsonrpc": "2.0", "method": method, "params": params})

    def _read_loop(self) -> None:
        """Reader thread: lee líneas, parsea JSON, despacha por id."""
        assert self._proc is not None and self._proc.stdout is not None
        for raw_line in self._proc.stdout:
            if self._stop_event.is_set():
                break
            line = raw_line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as e:
                log.warning(
                    "[MCP %s] línea no-JSON ignorada (%s): %r", self.config.server_id, e, line[:120]
                )
                continue

            msg_id = msg.get("id")
            if msg_id is None:
                # Notification entrante del servidor (logs, progress, etc.)
                # Por ahora las ignoramos.
                continue

            with self._pending_lock:
                entry = self._pending.get(msg_id)
            if entry is None:
                # Respuesta a un id que ya no está pendiente (timeout).
                continue
            event, container = entry
            if "error" in msg:
                container["error"] = msg["error"]
            else:
                container["result"] = msg.get("result", {})
            event.set()

        # Stdout cerrado — el proceso murió. Despierta todos los pendientes
        # con un error para no dejar threads colgados.
        with self._pending_lock:
            for ev, cont in self._pending.values():
                if "result" not in cont and "error" not in cont:
                    cont["error"] = {"message": "Subprocess MCP terminó inesperadamente"}
                ev.set()

    # ── Protocol calls ──────────────────────────────────────────────

    def _initialize(self, deadline: float) -> None:
        remaining = max(1.0, deadline - time.monotonic())
        self._send_request(
            "initialize",
            {
                "protocolVersion": self.PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "orion", "version": "1.0"},
            },
            timeout=remaining,
        )

    def _list_tools(self, deadline: float) -> list[dict]:
        remaining = max(1.0, deadline - time.monotonic())
        result = self._send_request("tools/list", {}, timeout=remaining)
        return list(result.get("tools") or [])

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Llama a una tool y devuelve el texto plano del resultado.

        MCP devuelve una lista de content blocks (text, image, etc.).
        Aplanamos a string: concatenamos todos los blocks de tipo text.
        """
        result = self._send_request(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
            timeout=self.config.call_timeout,
        )
        is_error = bool(result.get("isError", False))
        content = result.get("content") or []
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        text = "\n".join(p for p in parts if p)
        if is_error:
            raise MCPServerError(f"Tool MCP '{tool_name}' falló: {text or '(sin detalle)'}")
        return text or "Listo."


# ── Manager (multi-server) ──────────────────────────────────────────────


def _make_tool_name(server_id: str, tool_name: str) -> str:
    """Namespaceado para evitar choques con builtins.

    Gemini exige nombres ``[a-zA-Z_][a-zA-Z0-9_]*``, así que normalizamos
    cualquier caracter raro a underscore.
    """
    raw = f"{server_id}__{tool_name}"
    return "".join(c if (c.isalnum() or c == "_") else "_" for c in raw)


class MCPManager:
    """Orquesta múltiples ``MCPServer`` y los registra en el ToolRegistry."""

    def __init__(self, config_path: Path | None = None):
        from orion.config import CONFIG_DIR

        self._config_path = config_path or (CONFIG_DIR / "mcp_servers.json")
        self._servers: dict[str, MCPServer] = {}

    def start_all(self) -> int:
        """Arranca todos los servidores configurados y registra sus tools.
        Devuelve el número de tools registradas (suma de todos los servers).
        """
        configs = load_servers_config(self._config_path)
        if not configs:
            return 0

        registry = ToolRegistry()
        total_tools = 0
        for cfg in configs:
            try:
                server = MCPServer(cfg)
                server.start()
                self._servers[cfg.server_id] = server
                for tool in server.tools:
                    self._register_tool(registry, cfg.server_id, server, tool)
                    total_tools += 1
            except (MCPServerError, OSError) as e:
                log.warning("[MCP %s] no arrancó: %s", cfg.server_id, e)
        return total_tools

    def stop_all(self) -> None:
        for server in list(self._servers.values()):
            server.stop()
        self._servers.clear()

    def servers(self) -> dict[str, MCPServer]:
        return dict(self._servers)

    # ── Reload + restart de servers individuales ───────────────────

    def restart_server(self, server_id: str) -> int:
        """Para y vuelve a arrancar un server específico. Devuelve el
        número de tools re-registradas. Útil tras editar su config.
        """
        registry = ToolRegistry()
        # Para el server vivo si existía
        existing = self._servers.pop(server_id, None)
        if existing is not None:
            # Desregistrar sus tools del registry
            prefix = f"{server_id}__"
            for name in list(registry.names()):
                # Tools MCP llevan el namespace; las desregistramos para
                # evitar handlers colgando contra un subprocess muerto.
                if name.startswith(prefix) or name.startswith(
                    "".join(c if (c.isalnum() or c == "_") else "_" for c in prefix)
                ):
                    registry.unregister(name)
            existing.stop()

        # Vuelve a leer la config y arranca solo este server
        configs = load_servers_config(self._config_path)
        for cfg in configs:
            if cfg.server_id != server_id:
                continue
            try:
                server = MCPServer(cfg)
                server.start()
                self._servers[server_id] = server
                count = 0
                for tool in server.tools:
                    self._register_tool(registry, cfg.server_id, server, tool)
                    count += 1
                return count
            except (MCPServerError, OSError) as e:
                log.warning("[MCP %s] no arrancó: %s", server_id, e)
                raise
        raise KeyError(f"No hay config para servidor MCP '{server_id}'")

    def reload_all(self) -> int:
        """Para todos los servidores activos y vuelve a leer la config.
        Útil tras editar ``mcp_servers.json`` manualmente."""
        self.stop_all()
        # Limpia tools MCP del registry (cualquier nombre con '__' que
        # provenga de algún server). Conservador: solo borramos las que
        # tenían un server_id que estaba antes activo.
        return self.start_all()

    # ── Registro de cada tool en el ToolRegistry ───────────────────

    def _register_tool(
        self,
        registry: ToolRegistry,
        server_id: str,
        server: MCPServer,
        tool: dict,
    ) -> None:
        mcp_name = tool.get("name") or "unnamed"
        public_name = _make_tool_name(server_id, mcp_name)
        description = tool.get("description") or f"MCP tool from server '{server_id}'"
        # Algunos servers exponen ``inputSchema`` (spec MCP). Otros
        # ``parameters`` (forma adyacente). Aceptamos ambos.
        schema = tool.get("inputSchema") or tool.get("parameters") or {}
        gemini_schema = _convert_schema(schema)
        if not isinstance(gemini_schema, dict) or "type" not in gemini_schema:
            gemini_schema = {"type": "OBJECT", "properties": {}}

        decl = ToolDeclaration(
            name=public_name,
            description=description,
            parameters=gemini_schema,
            timeout=int(server.config.call_timeout),
            needs_player=False,
            needs_speak=False,
            include_in_planner=True,
        )

        # Captura server + mcp_name por closure
        def _handler(parameters: dict, **_kwargs) -> str:
            return server.call_tool(mcp_name, parameters)

        registry.register(decl, _handler)
        log.info("[MCP %s] tool registrada: %s", server_id, public_name)


# ── Singleton accessor (para las routes HTTP) ──────────────────────────
#
# ``OrionLive.__init__`` instancia el manager y se lo pasa a
# ``set_mcp_manager``. Las routes lo recuperan con ``get_mcp_manager``
# vía dependency injection. Si nadie lo seteó (ej. tests del frontend
# sin Live activo), devuelve una instancia "vacía" para no romper.

_GLOBAL_MANAGER: MCPManager | None = None


def set_mcp_manager(mgr: MCPManager) -> None:
    """Registra la instancia global. La llama ``OrionLive.__init__``."""
    global _GLOBAL_MANAGER
    _GLOBAL_MANAGER = mgr


def get_mcp_manager() -> MCPManager:
    """Devuelve la instancia global o una vacía si no hay Live activo.

    Las routes siempre obtienen un MCPManager utilizable. Si no hay
    Live arrancado (ej. tests que solo levantan el FastAPI), la
    instancia vacía permite GET sin error y POST escribe al config sin
    spawn (los servers arrancarán cuando Live tome el control).
    """
    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER is None:
        _GLOBAL_MANAGER = MCPManager()
    return _GLOBAL_MANAGER
