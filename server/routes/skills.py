"""
server.routes.skills — Skills (formato SKILL.md, estilo OpenClaw/Anthropic)
==========================================================================
Endpoints:

  GET    /api/skills              → lista de skills locales cargadas
  GET    /api/skills/{id}         → detalle (incluye cuerpo markdown)
  POST   /api/skills/reload       → fuerza re-escaneo del disco
  GET    /api/skills/registry/search?q=… → busca en el repo OpenClaw
  POST   /api/skills/install      → descarga una skill desde OpenClaw

Las skills NO son MCP. Son markdown que el LLM lee como contexto para
componer tools que ya tiene. Ver :mod:`core.skills` para el modelo.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import BASE_DIR
from core.skills import get_skill, list_skills, max_inject_chars, reset_cache
import contextlib

router = APIRouter()

# Repo de OpenClaw como registry por defecto. El usuario podría apuntar a
# un fork desde config/skills.json si quisiera; por ahora hardcodeo el
# oficial — es lo que llaman "ClawHub" indirectamente.
_OPENCLAW_REPO = "openclaw/openclaw"
_OPENCLAW_BRANCH = "main"
_OPENCLAW_PATH = "skills"


def _summary(s) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "user_invocable": s.user_invocable,
        "char_count": s.char_count,
        "path": str(s.path),
    }


@router.get("/")
async def get_skills() -> list[dict]:
    return [_summary(s) for s in list_skills()]


@router.post("/reload")
async def reload_skills() -> dict:
    reset_cache()
    skills = list_skills(force=True)
    return {"ok": True, "count": len(skills)}


# ── Registry (OpenClaw / ClawHub) ────────────────────────────────────────


def _gh_api(path: str) -> list | dict:
    """Llamada a la GitHub API sin auth. Suficiente para listar contenido
    público; sujeto al rate limit de 60 req/h sin token, pero como sólo
    listamos al buscar y al instalar, sobra. Si el usuario topa el límite
    le aparece un 403 explícito y le explicamos que necesita ``gh auth``.
    """
    url = f"https://api.github.com/repos/{_OPENCLAW_REPO}/contents/{path}?ref={_OPENCLAW_BRANCH}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ORION-Skills-Installer/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise HTTPException(
                status_code=503,
                detail="GitHub API rate-limit. Esperá ~1h o autenticá `gh auth login`.",
            ) from e
        if e.code == 404:
            raise HTTPException(status_code=404, detail="No existe en el repo OpenClaw.") from e
        raise HTTPException(status_code=502, detail=f"GitHub API: {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise HTTPException(status_code=502, detail=f"Sin red: {e.reason}") from e


@router.get("/registry/search")
async def search_registry(q: str = "") -> list[dict]:
    """Lista las skills disponibles en el repo OpenClaw. ``q`` filtra por
    substring sobre el id (case-insensitive). Devuelve metadata mínima —
    descripción detallada llega al instalar (lee el SKILL.md)."""
    items = _gh_api(_OPENCLAW_PATH)
    if not isinstance(items, list):
        return []
    needle = q.strip().lower()
    out: list[dict] = []
    for it in items:
        if it.get("type") != "dir":
            continue
        sid = it.get("name", "")
        if needle and needle not in sid.lower():
            continue
        out.append(
            {
                "id": sid,
                "html_url": it.get("html_url"),
                "source": "openclaw",
            }
        )
    return out


class InstallBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    source: str = Field(default="openclaw", description="Por ahora sólo 'openclaw'")


def _download_file(raw_url: str) -> bytes:
    req = urllib.request.Request(raw_url, headers={"User-Agent": "ORION-Skills-Installer/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _install_dir(remote_path: str, local_dir, depth: int = 0) -> list[str]:
    """Descarga recursiva. Devuelve lista de archivos escritos (relativos a
    local_dir). Limita la profundidad a 5 — las skills reales no anidan más."""
    if depth > 5:
        return []
    items = _gh_api(remote_path)
    if not isinstance(items, list):
        return []
    written: list[str] = []
    local_dir.mkdir(parents=True, exist_ok=True)
    for it in items:
        name = it.get("name", "")
        if not name:
            continue
        if it.get("type") == "file":
            url = it.get("download_url")
            if not url:
                continue
            try:
                data = _download_file(url)
            except Exception as e:
                print(f"[Skills] ⚠️ No pude bajar {url}: {e}")
                continue
            (local_dir / name).write_bytes(data)
            written.append(name)
        elif it.get("type") == "dir":
            sub_remote = f"{remote_path}/{name}"
            sub_local = local_dir / name
            for w in _install_dir(sub_remote, sub_local, depth + 1):
                written.append(f"{name}/{w}")
    return written


@router.post("/install", status_code=201)
async def install_skill(body: InstallBody) -> dict:
    """Descarga ``skills/<name>/`` del repo OpenClaw a ``skills/<name>/``
    en el filesystem de ORION. Tras descargar:

    1. Escanea con :mod:`core.skill_scanner` — si hay críticos (prompt
       injection, pipe-to-shell, crypto-mining), borra y rechaza.
    2. Escribe ``.openclaw-origin.json`` dentro de la carpeta para tracking.
    3. Actualiza ``config/skills.lock.json`` con la nueva instalación.
    4. Fuerza re-escaneo del cache.

    Idempotente: si la skill ya existe, sobreescribe archivos (no borra
    archivos extra para no pisar ediciones manuales)."""
    import json
    import shutil
    import time

    if body.source != "openclaw":
        raise HTTPException(status_code=400, detail="Por ahora sólo source='openclaw'.")

    sid = body.name.strip()
    if not all(c.isalnum() or c in "-_." for c in sid) or sid.startswith(".") or "/" in sid:
        raise HTTPException(status_code=400, detail="Nombre de skill inválido.")

    local_dir = BASE_DIR / "skills" / sid
    remote = f"{_OPENCLAW_PATH}/{sid}"

    files = _install_dir(remote, local_dir)
    if not files:
        raise HTTPException(
            status_code=404,
            detail=f"No bajé ningún archivo de '{sid}'. Revisá el nombre exacto en el repo.",
        )

    if "SKILL.md" not in files:
        print(f"[Skills] ⚠️ '{sid}' instalada pero sin SKILL.md en raíz.")

    # ── Security scan ──
    scan_summary: dict = {}
    try:
        from core.skill_scanner import scan_skill_dir

        scan = scan_skill_dir(local_dir)
        scan_summary = scan.to_dict()
        if scan.has_critical():
            # Borrar lo descargado y rechazar
            with contextlib.suppress(Exception):
                shutil.rmtree(local_dir)
            criticals = [
                f"[{f.rule_id}] {f.file}:{f.line} — {f.message}"
                for f in scan.by_severity("critical")
            ]
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Skill rechazada por security scanner",
                    "criticals": criticals,
                    "summary": scan.summary(),
                },
            )
    except ImportError:
        pass  # scanner no disponible

    # ── Origin tracking ──
    origin = {
        "version": 1,
        "registry": body.source,
        "slug": sid,
        "installed_at": int(time.time()),
        "installed_files": files,
    }
    try:
        (local_dir / ".openclaw-origin.json").write_text(
            json.dumps(origin, indent=2), encoding="utf-8"
        )
    except OSError as e:
        print(f"[Skills] ⚠️ No pude escribir .openclaw-origin.json: {e}")

    # ── Lockfile global ──
    lock_path = BASE_DIR / "config" / "skills.lock.json"
    lock: dict = {"version": 1, "skills": {}}
    if lock_path.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock.setdefault("skills", {})
    lock["skills"][sid] = {
        "registry": body.source,
        "installed_at": origin["installed_at"],
    }
    try:
        lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"[Skills] ⚠️ No pude escribir skills.lock.json: {e}")

    reset_cache()
    return {
        "ok": True,
        "id": sid,
        "files": files,
        "path": str(local_dir),
        "loaded": any(s.id == sid for s in list_skills(force=True)),
        "scan": scan_summary,
    }


# ── CLI auxiliares (binarios que llaman las skills) ─────────────────────


@router.get("/cli")
async def list_cli() -> list[dict]:
    """Catálogo completo de CLIs conocidos por el installer con su status."""
    from core.cli_installer import registry_info

    return registry_info()


@router.get("/cli/{name}/status")
async def cli_status(name: str) -> dict:
    """Reporta si un binario está disponible y dónde (tools/ o PATH del sistema)."""
    from core.cli_installer import REGISTRY, cli_path

    if name not in REGISTRY:
        raise HTTPException(status_code=404, detail=f"CLI '{name}' no registrado.")
    p = cli_path(name)
    return {
        "name": name,
        "installed": p is not None,
        "path": p,
        "managed": bool(p and "/tools/" in p.replace("\\", "/")),
        "version": REGISTRY[name].version,
    }


@router.post("/cli/{name}/install", status_code=201)
async def cli_install(name: str, force: bool = False) -> dict:
    """Descarga la release oficial del CLI a tools/<name>/. Tras instalar,
    el executor lo encuentra automáticamente (se mete tools/<name>/ en el
    PATH del subprocess de generated_code)."""
    from core.cli_installer import REGISTRY, install_cli

    if name not in REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"CLI '{name}' no registrado. Conocidos: {', '.join(REGISTRY)}",
        )
    try:
        path = install_cli(name, force=force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Instalación falló: {e}") from e
    return {"ok": True, "name": name, "path": path}


# ── Detalle por id (DEBE quedar al final del archivo) ──────────────────
# FastAPI matchea por orden de declaración: si esta ruta estuviera antes,
# /api/skills/cli, /api/skills/install y /api/skills/reload caerían acá
# como skill_id="cli|install|reload" y devolverían 404.


@router.get("/{skill_id}")
async def get_skill_detail(skill_id: str) -> dict:
    skill = get_skill(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' no encontrada")
    return {
        **_summary(skill),
        "body": skill.body,
        "frontmatter": skill.frontmatter,
        "max_inject": max_inject_chars(),
    }
