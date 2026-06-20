"""
core.skills — SkillLoader: lee SKILL.md (formato OpenClaw / Anthropic)
=====================================================================
Una **skill** es una carpeta con un archivo ``SKILL.md`` que tiene:

  1. **Frontmatter YAML** entre ``---`` con al menos ``name`` y
     ``description``. Campos extra opcionales: ``user-invocable``,
     ``requires``, ``primaryEnv``, etc.
  2. **Cuerpo markdown** con instrucciones en lenguaje natural y bloques
     bash embebidos que el LLM ejecuta como pasos.

Diferencia con MCP
------------------
MCP son **subprocesses** que exponen tools nuevas (JSON-RPC). Skills son
**markdown** que el LLM lee para componer tools que ya tiene. No corren
nada por sí solas — necesitan un agente que las interprete.

Layout esperado
---------------
::

    skills/
        gh-issues/
            SKILL.md
            (otros archivos: scripts, ejemplos…)
        notion/
            SKILL.md
        …

Configuración
-------------
``config/skills.json``::

    {
      "search_paths": ["skills"],
      "enabled":      ["gh-issues", "notion"],
      "max_inject_chars": 8000
    }

* ``search_paths``: carpetas (relativas a la raíz del proyecto) donde
  buscar subcarpetas con ``SKILL.md``. Por defecto sólo ``skills/``.
* ``enabled``: ids permitidos. Si la lista está vacía, todas las que
  encuentre quedan habilitadas.
* ``max_inject_chars``: cota dura al inyectar el cuerpo de una skill en
  el system prompt — evita reventar el context window.

API pública
-----------
* :func:`load_skills`  — escanea disco y devuelve dict {id: Skill}.
* :func:`list_skills`  — versión cacheada (re-escanea si pasaron >5s).
* :func:`get_skill`    — devuelve una skill por id o None.
* :func:`reset_cache`  — fuerza re-escaneo (POST /api/skills/reload).
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import BASE_DIR

# ── Config ──────────────────────────────────────────────────────────────

_CONFIG_PATH = BASE_DIR / "config" / "skills.json"
_DEFAULT_CONFIG: dict[str, Any] = {
    "search_paths": ["skills"],
    "enabled": [],  # vacío = todas
    "max_inject_chars": 8000,
}


def _load_config() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        return dict(_DEFAULT_CONFIG)
    try:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        # Mergeo defensivo: si el usuario borra una clave, usamos el default.
        return {**_DEFAULT_CONFIG, **data}
    except (json.JSONDecodeError, OSError) as e:
        print(f"[Skills] ⚠️ skills.json inválido, usando defaults: {e}")
        return dict(_DEFAULT_CONFIG)


# ── Modelo ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Skill:
    id: str  # nombre de la carpeta
    name: str  # del frontmatter
    description: str
    path: Path  # ruta absoluta a SKILL.md
    body: str  # markdown post-frontmatter
    frontmatter: dict[str, Any]  # crudo, para metadata extra
    user_invocable: bool = True

    @property
    def char_count(self) -> int:
        return len(self.body)

    def truncated_body(self, max_chars: int) -> str:
        """Devuelve el cuerpo cortado al límite — útil al inyectar en prompt."""
        if len(self.body) <= max_chars:
            return self.body
        return self.body[:max_chars] + "\n\n…[skill truncada por límite de contexto]"


# ── Parser ──────────────────────────────────────────────────────────────


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Extrae frontmatter YAML simple (subset). Sin dep externa.

    Soporta el formato típico de SKILL.md:
      - ``key: value`` (string o bool)
      - ``key:`` seguido de bloque indentado (lo guardamos como string crudo)
      - metadata JSON multilinea inline (lo guardamos como string)

    Si hay PyYAML disponible, lo preferimos; si no, parser ingenuo que cubre
    el 90% de los casos reales.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    raw = m.group(1)
    body = text[m.end() :]

    # Intento con PyYAML primero (presente en muchos venvs como dep transitiva).
    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(raw) or {}
        if isinstance(parsed, dict):
            return parsed, body
    except ImportError:
        pass
    except Exception as e:
        print(f"[Skills] PyYAML parse falló, intento manual: {e}")

    # Fallback: parser ingenuo línea-a-línea.
    out: dict[str, Any] = {}
    current_key: str | None = None
    buf: list[str] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        if not line.startswith((" ", "\t")) and ":" in line:
            if current_key is not None and buf:
                out[current_key] = "\n".join(buf).strip()
                buf = []
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val.lower() in ("true", "false"):
                out[key] = val.lower() == "true"
            elif val:
                out[key] = val
            else:
                current_key = key
        else:
            buf.append(line)
    if current_key is not None and buf:
        out[current_key] = "\n".join(buf).strip()
    return out, body


def _load_one(skill_dir: Path) -> Skill | None:
    md_path = skill_dir / "SKILL.md"
    if not md_path.exists():
        return None
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[Skills] No pude leer {md_path}: {e}")
        return None

    fm, body = _parse_frontmatter(text)

    # Validación de frontmatter — rechaza skills con campos obligatorios faltantes.
    # Solo bloqueamos en críticos; warnings se loguean y la skill se carga igual.
    try:
        from core.skill_scanner import validate_frontmatter

        fm_findings = validate_frontmatter(fm)
        for f in fm_findings:
            if f.severity == "critical":
                print(f"[Skills] REJECTED {skill_dir.name}: {f.message}")
                return None
            else:
                print(f"[Skills] WARN {skill_dir.name} ({f.severity}): {f.message}")
    except ImportError:
        pass  # scanner opcional

    sid = (fm.get("name") or skill_dir.name).strip()
    desc = (fm.get("description") or "").strip()
    # user-invocable puede venir como bool o string "true"/"false"
    raw_ui = fm.get("user-invocable", fm.get("user_invocable", True))
    if isinstance(raw_ui, str):
        ui = raw_ui.strip().lower() not in ("false", "0", "no")
    else:
        ui = bool(raw_ui)

    # Security scan — bloquea skills con patrones críticos (prompt injection,
    # pipe-to-shell, crypto-mining, etc.). Los warnings solo se loguean.
    try:
        from core.skill_scanner import scan_skill_dir

        scan = scan_skill_dir(skill_dir)
        if scan.has_critical():
            print(f"[Skills] BLOCKED {skill_dir.name}: critical scan findings, skill not loaded.")
            for f in scan.by_severity("critical"):
                print(f"  [{f.rule_id}] {f.file}:{f.line} -- {f.message}")
            return None
        if scan.has_warnings():
            print(f"[Skills] WARN {skill_dir.name}: {scan.summary()}")
    except ImportError:
        pass

    return Skill(
        id=skill_dir.name,
        name=sid,
        description=desc,
        path=md_path.resolve(),
        body=body.strip(),
        frontmatter=fm,
        user_invocable=ui,
    )


# ── Cache + escaneo ─────────────────────────────────────────────────────


_cache: dict[str, Skill] = {}
_cache_ts: float = 0.0
_cache_lock = threading.Lock()
_CACHE_TTL = 5.0  # segundos


def load_skills(force: bool = False) -> dict[str, Skill]:
    """Escanea disco y devuelve {id: Skill}. Aplica el filtro ``enabled``
    de skills.json: si está vacío, deja pasar todas."""
    cfg = _load_config()
    enabled: list[str] = cfg.get("enabled") or []

    out: dict[str, Skill] = {}
    for rel in cfg.get("search_paths") or ["skills"]:
        root = BASE_DIR / rel
        if not root.exists() or not root.is_dir():
            continue
        for sub in sorted(root.iterdir()):
            if not sub.is_dir():
                continue
            skill = _load_one(sub)
            if skill is None:
                continue
            if enabled and skill.id not in enabled:
                continue
            out[skill.id] = skill
    return out


def list_skills(force: bool = False) -> list[Skill]:
    """Versión cacheada: re-escanea si pasaron más de _CACHE_TTL segundos."""
    global _cache, _cache_ts
    with _cache_lock:
        now = time.time()
        if force or not _cache or (now - _cache_ts) > _CACHE_TTL:
            _cache = load_skills()
            _cache_ts = now
        return list(_cache.values())


def get_skill(skill_id: str) -> Skill | None:
    for s in list_skills():
        if s.id == skill_id:
            return s
    return None


def reset_cache() -> None:
    global _cache, _cache_ts
    with _cache_lock:
        _cache = {}
        _cache_ts = 0.0


def max_inject_chars() -> int:
    return int(_load_config().get("max_inject_chars", 8000))


def build_skill_catalog_prompt() -> str:
    """Bloque listo para inyectar en el system prompt del Director. Formato
    XML inspirado en OpenClaw (packages/agent-core/src/harness/system-prompt.ts)
    — el modelo lo procesa mejor que una lista plana.

    Cada skill expone id, nombre, descripción y ruta del SKILL.md por si el
    modelo necesita razonar sobre dónde vive. Si no hay skills habilitadas
    devolvemos vacío para no meter ruido al prompt.
    """
    skills = list_skills()
    if not skills:
        return ""
    lines = [
        "The following skills are installed and provide specialized instructions for specific tasks.",
        "When a user request matches a skill description, delegate the task via agent_task — "
        "the planner will internally load the skill and chain the shell execution. "
        "Do NOT invoke use_skill yourself from this Live session.",
        "",
        "<available_skills>",
    ]
    for s in skills:
        desc = s.description.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines.append("  <skill>")
        lines.append(f"    <id>{s.id}</id>")
        lines.append(f"    <name>{s.name}</name>")
        lines.append(f"    <description>{desc}</description>")
        lines.append(f"    <location>{s.path}</location>")
        lines.append("  </skill>")
    lines.append("</available_skills>")
    return "\n".join(lines)
