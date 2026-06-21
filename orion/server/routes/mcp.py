"""
server.routes.mcp — Gestión de servidores MCP desde la UI
==========================================================

Endpoints de **lectura**:
  GET    /api/mcp/servers              → servers configurados + status live
  GET    /api/mcp/tools                → todas las tools MCP registradas

Endpoints de **mutación** (modifican ``config/mcp_servers.json``):
  POST   /api/mcp/servers              → crear server nuevo (escribe + spawn)
  PUT    /api/mcp/servers/{id}         → actualizar server (escribe + restart)
  DELETE /api/mcp/servers/{id}         → borrar server (stop + escribe)

Endpoints de **control**:
  POST   /api/mcp/servers/{id}/restart → restart sin tocar config
  POST   /api/mcp/reload               → relee config desde disco y reaplica

Seguridad
---------
El middleware ``server.sharing`` ya restringe acceso a loopback/Tailscale.
**Cuidado**: estos endpoints permiten ejecutar binarios arbitrarios como
subprocess (los servers MCP). En modo sharing=True (Tailscale abierto),
quien tenga acceso a tu tailnet puede registrar comandos. Si querés
restringir mutación solo a localhost, agregalo en este módulo
(``_require_loopback`` helper).
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from orion.config import CONFIG_DIR
from orion.core.mcp_client import (
    MCPServerError,
    get_mcp_manager,
)
from orion.core.mcp_recipes import list_recipes
from orion.core.tool_registry import ToolRegistry

log = logging.getLogger("orion.server.mcp")

router = APIRouter()

MCP_CONFIG_PATH = CONFIG_DIR / "mcp_servers.json"


# ── Registry proxy ──────────────────────────────────────────────────────
# El catálogo oficial vive en registry.modelcontextprotocol.io. Le hacemos
# de intermediarios para:
#   1. Evitar CORS (el browser no puede llamarlo directo)
#   2. Cachear (mismo search repetido → 1 hit al upstream, no N)
#   3. Normalizar el shape: el frontend NO debería conocer el formato
#      crudo del registry, que puede cambiar.

REGISTRY_BASE = "https://registry.modelcontextprotocol.io/v0"
REGISTRY_TIMEOUT = 8.0
_REGISTRY_CACHE: dict[str, tuple[float, dict]] = {}
_REGISTRY_CACHE_TTL = 300.0  # 5 min


def _fetch_registry(url: str) -> dict:
    """Hace GET al registry con cache TTL. Levanta HTTPException en fallo."""
    now = time.monotonic()
    cached = _REGISTRY_CACHE.get(url)
    if cached and (now - cached[0]) < _REGISTRY_CACHE_TTL:
        return cached[1]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "orion/1.0"})
        with urllib.request.urlopen(req, timeout=REGISTRY_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise HTTPException(502, f"Registry MCP no disponible: {e.reason}") from e
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(502, f"Registry devolvió payload inválido: {e}") from e
    _REGISTRY_CACHE[url] = (now, payload)
    return payload


def _normalize_package(pkg: dict) -> dict | None:
    """Convierte un ``package`` del registry a algo que el MCPPanel
    pueda usar directamente para pre-rellenar el form (command + args +
    env vars). Devuelve None si el package no es stdio o no sabemos
    cómo arrancarlo."""
    if (pkg.get("transport") or {}).get("type") != "stdio":
        return None

    runtime_hint = pkg.get("runtimeHint") or ""
    registry_type = pkg.get("registryType") or ""
    identifier = pkg.get("identifier") or ""

    # Heurística: si runtimeHint viene seteado lo usamos, sino caemos a
    # convenciones por tipo de registry.
    command = runtime_hint
    if not command:
        if registry_type == "npm":
            command = "npx"
        elif registry_type == "pypi":
            command = "uvx"
        elif registry_type == "oci":
            command = "docker"
        else:
            return None  # tipo desconocido — el usuario tendría que armarlo a mano

    # runtimeArguments son flags ANTES del identifier (ej. "-y").
    runtime_args: list[str] = []
    for a in pkg.get("runtimeArguments") or []:
        v = a.get("value")
        if isinstance(v, str):
            runtime_args.append(v)

    # packageArguments son flags DESPUÉS del identifier (ej. una ruta o token).
    package_args: list[str] = []
    for a in pkg.get("packageArguments") or []:
        v = a.get("value")
        if isinstance(v, str):
            package_args.append(v)

    args = (
        [*runtime_args, identifier, *package_args] if identifier else [*runtime_args, *package_args]
    )

    env_required: list[dict] = []
    for e in pkg.get("environmentVariables") or []:
        env_required.append(
            {
                "name": e.get("name", ""),
                "description": (e.get("description") or "")[:200],
                "required": bool(e.get("isRequired", False)),
            }
        )

    return {
        "command": command,
        "args": args,
        "env_required": env_required,
        "registry_type": registry_type,
        "identifier": identifier,
        "version": pkg.get("version", ""),
    }


def _normalize_server(entry: dict) -> dict:
    """Aplana un entry del registry al shape que consume el MCPPanel.

    El upstream envuelve cada server en ``{"server": {...}, "_meta": {...}}``
    desde la spec de septiembre 2025. Antes era flat — soportamos ambos
    para ser robustos a cambios futuros.

    Devuelve además ``remote=True`` cuando el server expone solo transports
    HTTP/SSE (que ORION todavía no consume — el cliente actual es stdio).
    Así el UI puede mostrarlos diferenciados en vez de un genérico
    "no instalable".
    """
    server = entry.get("server") if isinstance(entry.get("server"), dict) else entry

    raw_pkgs = server.get("packages") or []
    normalized_pkgs: list[dict] = []
    for pkg in raw_pkgs:
        n = _normalize_package(pkg)
        if n is not None:
            normalized_pkgs.append(n)

    raw_remotes = server.get("remotes") or []
    remote_kinds = sorted(
        {(r.get("type") or "").lower() for r in raw_remotes if isinstance(r, dict)}
    )

    return {
        "name": server.get("name", ""),
        "title": server.get("title") or server.get("name", ""),
        "description": (server.get("description") or "")[:400],
        "version": server.get("version", ""),
        "repository": (server.get("repository") or {}).get("url"),
        "packages": normalized_pkgs,
        "installable": bool(normalized_pkgs),
        "remote": bool(raw_remotes) and not normalized_pkgs,
        "remote_kinds": remote_kinds,
    }


# ── Schemas ─────────────────────────────────────────────────────────────


class MCPServerBody(BaseModel):
    """Payload para crear/actualizar un servidor MCP."""

    command: str = Field(..., description="Binario a ejecutar (ej. 'npx', 'python')")
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    cwd: str | None = None
    startup_timeout: float = 15.0
    call_timeout: float = 60.0


# ── Persistencia ────────────────────────────────────────────────────────


def _load_raw_config() -> dict[str, Any]:
    """Lee el JSON crudo (preserva los `_comment`/`_example` que viven
    al lado de los servers)."""
    if not MCP_CONFIG_PATH.exists():
        return {"servers": {}}
    try:
        raw = json.loads(MCP_CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(500, f"mcp_servers.json corrupto: {e}") from e
    if "servers" not in raw or not isinstance(raw["servers"], dict):
        raw["servers"] = {}
    return raw


def _save_raw_config(raw: dict[str, Any]) -> None:
    """Escribe el JSON atómicamente (tmp + rename) para no corromper si
    el proceso muere a mitad de write."""
    MCP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(raw, indent=2, ensure_ascii=False)
    # tempfile en el mismo dir para asegurar rename atómico cross-fs
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".mcp_servers.", suffix=".tmp", dir=str(MCP_CONFIG_PATH.parent)
    )
    try:
        with open(tmp_fd, "w", encoding="utf-8") as f:
            f.write(payload)
        Path(tmp_path).replace(MCP_CONFIG_PATH)
    except OSError as e:
        log.warning("escritura atómica de mcp_servers.json falló: %s", e)
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError as cleanup_err:
            log.debug("cleanup del tmp file falló: %s", cleanup_err)
        raise


# ── Helpers de presentación ─────────────────────────────────────────────


def _server_to_dict(server_id: str, cfg_dict: dict, live_status: dict) -> dict:
    """Combina la config persistida con el estado live (running / tools)."""
    return {
        "id": server_id,
        "command": cfg_dict.get("command", ""),
        "args": cfg_dict.get("args", []),
        "env": cfg_dict.get("env", {}),
        "enabled": bool(cfg_dict.get("enabled", True)),
        "cwd": cfg_dict.get("cwd"),
        "startup_timeout": cfg_dict.get("startup_timeout", 15.0),
        "call_timeout": cfg_dict.get("call_timeout", 60.0),
        # Estado live
        "running": live_status.get("running", False),
        "tool_count": live_status.get("tool_count", 0),
        "tools": live_status.get("tools", []),
        "error": live_status.get("error"),
    }


def _live_status_for(server_id: str) -> dict:
    mgr = get_mcp_manager()
    server = mgr.servers().get(server_id)
    if server is None:
        return {"running": False, "tool_count": 0, "tools": []}
    tools = [
        {
            "name": t.get("name", ""),
            "description": (t.get("description") or "")[:200],
        }
        for t in server.tools
    ]
    return {
        "running": True,
        "tool_count": len(tools),
        "tools": tools,
    }


# ── Read endpoints ──────────────────────────────────────────────────────


@router.get("/servers")
async def list_servers() -> list[dict]:
    raw = _load_raw_config()
    out = []
    for sid, entry in (raw.get("servers") or {}).items():
        if not isinstance(entry, dict):
            continue
        out.append(_server_to_dict(sid, entry, _live_status_for(sid)))
    return out


@router.get("/tools")
async def list_mcp_tools() -> list[dict]:
    """Todas las tools MCP actualmente en el ToolRegistry. Útil para
    debugging: confirmar que un server registró lo que se espera."""
    registry = ToolRegistry()
    mgr = get_mcp_manager()
    server_ids = set(mgr.servers().keys())
    out = []
    for decl in registry.all():
        # Las tools MCP llevan namespacing `<server_id>__<tool>`
        if "__" not in decl.name:
            continue
        prefix = decl.name.split("__", 1)[0]
        if prefix in server_ids or _looks_like_mcp_name(prefix, server_ids):
            out.append(
                {
                    "name": decl.name,
                    "server_id": prefix,
                    "description": decl.description,
                    "timeout": decl.timeout,
                }
            )
    return out


def _looks_like_mcp_name(prefix: str, server_ids: set[str]) -> bool:
    """El namespacing puede sanitizar caracteres (`my-svr` → `my_svr`).
    Reconciliamos por similitud simple."""
    sanitized = "".join(c if (c.isalnum() or c == "_") else "_" for c in prefix)
    return sanitized in {
        "".join(c if (c.isalnum() or c == "_") else "_" for c in s) for s in server_ids
    }


# ── Mutation endpoints ──────────────────────────────────────────────────


@router.post("/servers", status_code=201)
async def create_server(body: dict) -> dict:
    """Crea un server nuevo. Body: ``{id, ...MCPServerBody}``.

    El ``id`` lo elige el usuario (no autogenerado) para que coincida
    con el namespacing de las tools.
    """
    server_id = (body.get("id") or "").strip()
    if not server_id:
        raise HTTPException(400, "El campo 'id' es obligatorio")
    if not server_id.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(400, "El id solo admite letras, dígitos, '-' y '_'")

    payload = MCPServerBody(**{k: v for k, v in body.items() if k != "id"})

    raw = _load_raw_config()
    if server_id in raw["servers"]:
        raise HTTPException(409, f"Ya existe un server con id '{server_id}'")
    raw["servers"][server_id] = payload.model_dump(exclude_none=True)
    _save_raw_config(raw)

    # Intentar spawnear si está enabled
    error = None
    if payload.enabled:
        try:
            get_mcp_manager().restart_server(server_id)
        except (MCPServerError, KeyError, OSError) as e:
            log.warning("[MCP] server '%s' guardado pero no arrancó: %s", server_id, e)
            error = str(e)

    return _server_to_dict(server_id, raw["servers"][server_id], _live_status_for(server_id)) | {
        "error": error,
    }


@router.put("/servers/{server_id}")
async def update_server(server_id: str, body: dict) -> dict:
    """Actualiza un server existente. Para y vuelve a arrancar si está
    enabled. NO permite cambiar el id."""
    payload = MCPServerBody(**body)

    raw = _load_raw_config()
    if server_id not in raw["servers"]:
        raise HTTPException(404, f"Server '{server_id}' no existe")
    raw["servers"][server_id] = payload.model_dump(exclude_none=True)
    _save_raw_config(raw)

    error = None
    try:
        if payload.enabled:
            get_mcp_manager().restart_server(server_id)
        else:
            # Si lo deshabilitaron, basta con pararlo
            mgr = get_mcp_manager()
            srv = mgr.servers().get(server_id)
            if srv is not None:
                srv.stop()
                mgr._servers.pop(server_id, None)
    except (MCPServerError, KeyError, OSError) as e:
        log.warning("[MCP] update '%s': %s", server_id, e)
        error = str(e)

    return _server_to_dict(server_id, raw["servers"][server_id], _live_status_for(server_id)) | {
        "error": error,
    }


@router.delete("/servers/{server_id}", status_code=204)
async def delete_server(server_id: str) -> None:
    raw = _load_raw_config()
    if server_id not in raw["servers"]:
        raise HTTPException(404, f"Server '{server_id}' no existe")

    # Stop live antes de borrar la config
    mgr = get_mcp_manager()
    srv = mgr.servers().get(server_id)
    if srv is not None:
        try:
            srv.stop()
        except Exception as e:
            log.warning("stop MCP '%s' falló: %s", server_id, e)
        mgr._servers.pop(server_id, None)

    # Limpiar tools del registry
    registry = ToolRegistry()
    sanitized = "".join(c if (c.isalnum() or c == "_") else "_" for c in server_id)
    for name in list(registry.names()):
        if name.startswith(f"{server_id}__") or name.startswith(f"{sanitized}__"):
            registry.unregister(name)

    raw["servers"].pop(server_id, None)
    _save_raw_config(raw)


@router.post("/servers/{server_id}/restart")
async def restart_server(server_id: str) -> dict:
    raw = _load_raw_config()
    if server_id not in raw["servers"]:
        raise HTTPException(404, f"Server '{server_id}' no existe")
    try:
        count = get_mcp_manager().restart_server(server_id)
    except (MCPServerError, KeyError, OSError) as e:
        raise HTTPException(500, f"Restart falló: {e}") from e
    return {"ok": True, "server_id": server_id, "tool_count": count}


@router.get("/recipes")
async def list_curated_recipes() -> list[dict]:
    """Lista de recetas curadas (servers populares pre-armados).

    El registry público no incluye los reference servers de Anthropic
    (Filesystem, Git, Memory, etc.) — solo están en su monorepo. Acá los
    devolvemos hardcoded para que la UI pueda mostrarlos en un tab
    'Curados' con instalación de un click.
    """
    return list_recipes()


# ── GitHub stars (best-effort, cacheado) ───────────────────────────────

GITHUB_API = "https://api.github.com"
GITHUB_TIMEOUT = 4.0
_GH_STAR_CACHE: dict[str, tuple[float, int | None]] = {}
_GH_STAR_TTL = 24 * 3600.0  # 24h


def _parse_github_repo(url: str) -> tuple[str, str] | None:
    """De ``https://github.com/owner/repo[/tree/...]`` extrae (owner, repo).
    Devuelve None si no es un URL de GitHub reconocible."""
    if not url:
        return None
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return None
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def _fetch_github_stars(repo_url: str) -> int | None:
    """Best-effort. Devuelve el conteo de estrellas o None si:
       - URL no parseable
       - Rate limit / 404 / error de red
       - Timeout
    Cachea positivos Y negativos por 24h para no martillar la API."""
    parsed = _parse_github_repo(repo_url)
    if parsed is None:
        return None
    owner, repo = parsed
    cache_key = f"{owner}/{repo}"
    now = time.monotonic()
    cached = _GH_STAR_CACHE.get(cache_key)
    if cached and (now - cached[0]) < _GH_STAR_TTL:
        return cached[1]

    url = f"{GITHUB_API}/repos/{owner}/{repo}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "orion/1.0",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=GITHUB_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        stars = int(data.get("stargazers_count", 0))
    except Exception as e:
        log.debug("GitHub stars fetch falló para %s: %s", cache_key, e)
        stars = None
    _GH_STAR_CACHE[cache_key] = (now, stars)
    return stars


@router.get("/registry/stars")
async def registry_stars(repo_url: str = Query(...)) -> dict:
    """Devuelve estrellas de GitHub para un repo. Best-effort, cacheado
    24h. Si falla devuelve ``stars: null`` (no error 502 — la UI debe
    seguir andando sin esta info)."""
    stars = _fetch_github_stars(repo_url)
    return {"repo_url": repo_url, "stars": stars}


@router.get("/registry/search")
async def registry_search(
    q: str = Query("", description="Texto a buscar en nombre/descripción"),
    limit: int = Query(20, ge=1, le=50),
    cursor: str | None = Query(None, description="nextCursor de la página previa"),
) -> dict:
    """Proxy al registry oficial. Devuelve servers normalizados +
    nextCursor para paginar."""
    params: dict[str, Any] = {"limit": limit}
    if q.strip():
        params["search"] = q.strip()
    if cursor:
        params["cursor"] = cursor
    url = f"{REGISTRY_BASE}/servers?{urllib.parse.urlencode(params)}"
    payload = _fetch_registry(url)

    servers = [_normalize_server(s) for s in (payload.get("servers") or [])]
    metadata = payload.get("metadata") or {}
    return {
        "servers": servers,
        "next_cursor": metadata.get("nextCursor"),
        "count": metadata.get("count", len(servers)),
    }


@router.post("/reload")
async def reload_all() -> dict:
    """Relee config/mcp_servers.json y reaplica. Útil tras editar el
    JSON a mano."""
    try:
        count = get_mcp_manager().reload_all()
    except Exception as e:
        raise HTTPException(500, f"Reload falló: {e}") from e
    return {"ok": True, "tool_count": count}
