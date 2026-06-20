"""
tests.fixtures.fake_mcp_server — Servidor MCP de mentira para tests
====================================================================
Implementa el subconjunto del protocolo MCP suficiente para probar
``core.mcp_client.MCPServer`` end-to-end sin instalar Node ni servidores
reales:

  - ``initialize`` / ``notifications/initialized``
  - ``tools/list`` con 2 tools: ``echo`` (devuelve texto) y ``fail``
    (devuelve isError=True).
  - ``tools/call`` para ambas.

Cualquier otro método responde con error -32601. Las requests sin ``id``
(notificaciones) se ignoran silenciosamente.
"""

from __future__ import annotations

import json
import sys


def respond(req_id, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}) + "\n")
    sys.stdout.flush()


def respond_error(req_id, code, message):
    sys.stdout.write(
        json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})
        + "\n"
    )
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method")
        req_id = msg.get("id")
        params = msg.get("params") or {}

        # Notification (no id) — ignorar
        if req_id is None:
            continue

        if method == "initialize":
            respond(
                req_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "serverInfo": {"name": "fake-mcp", "version": "0.0.1"},
                },
            )

        elif method == "tools/list":
            respond(
                req_id,
                {
                    "tools": [
                        {
                            "name": "echo",
                            "description": "Echoes a message back",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "message": {"type": "string", "description": "Texto a repetir"},
                                },
                                "required": ["message"],
                            },
                        },
                        {
                            "name": "fail",
                            "description": "Always returns an error",
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                    ]
                },
            )

        elif method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            if name == "echo":
                text = f"ECHO: {args.get('message', '')}"
                respond(req_id, {"content": [{"type": "text", "text": text}]})
            elif name == "fail":
                respond(
                    req_id,
                    {
                        "content": [{"type": "text", "text": "intentional failure"}],
                        "isError": True,
                    },
                )
            else:
                respond_error(req_id, -32601, f"unknown tool: {name}")

        else:
            respond_error(req_id, -32601, f"method not implemented: {method}")


if __name__ == "__main__":
    main()
