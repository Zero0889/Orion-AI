"""
agent.registry — Catálogo de agentes de la orquesta multi-agente.

Lee ``config/agents.json``, instancia los proveedores LLM que toquen y
expone helpers para que el planner y el executor consulten:

- :func:`list_agents`     — agentes habilitados
- :func:`get_agent`       — definición de un agente por id
- :func:`agent_can_use`   — ¿este agente tiene permiso para usar esta tool?
- :func:`ask_agent`       — pregunta directa a un agente (sin tool-use)

Fallback automático: si el proveedor primario no está disponible (key
vacía) y el agente declara ``fallback_provider`` + ``fallback_model``,
:func:`ask_agent` cae al fallback en lugar de fallar.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache

from config import BASE_DIR
from core.llm import LLMMessage, LLMResponse, get_provider


@dataclass(frozen=True)
class AgentDef:
    id: str
    role: str
    icon: str
    description: str
    provider: str
    model: str
    temperature: float
    tools: tuple[str, ...]
    system: str
    enabled: bool = True
    fallback_provider: str | None = None
    fallback_model: str | None = None


def _load_agents_config() -> dict:
    path = BASE_DIR / "config" / "agents.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[AgentRegistry] ⚠️ No pude leer agents.json: {e}")
        return {}


@lru_cache(maxsize=1)
def _agents() -> dict[str, AgentDef]:
    cfg = _load_agents_config()
    out: dict[str, AgentDef] = {}
    for agent_id, spec in (cfg.get("agents") or {}).items():
        if not isinstance(spec, dict):
            continue
        out[agent_id] = AgentDef(
            id=agent_id,
            role=spec.get("role", agent_id),
            icon=spec.get("icon", "circle"),
            description=spec.get("description", ""),
            provider=spec.get("provider", "gemini"),
            model=spec.get("model", "gemini-2.5-flash"),
            temperature=float(spec.get("temperature", 0.7)),
            tools=tuple(spec.get("tools", [])),
            system=spec.get("system", ""),
            enabled=bool(spec.get("enabled", True)),
            fallback_provider=spec.get("fallback_provider"),
            fallback_model=spec.get("fallback_model"),
        )
    return out


def reset_cache() -> None:
    """Forzar relectura de agents.json (p. ej. al editarlo en caliente)."""
    _agents.cache_clear()


# ── API pública ────────────────────────────────────────────────────────────

def list_agents(*, only_enabled: bool = True) -> list[AgentDef]:
    agents = _agents().values()
    if only_enabled:
        agents = [a for a in agents if a.enabled]
    return list(agents)


def get_agent(agent_id: str) -> AgentDef:
    agents = _agents()
    if agent_id not in agents:
        raise KeyError(
            f"Agente '{agent_id}' no definido en config/agents.json. "
            f"Disponibles: {', '.join(agents) or '(ninguno)'}"
        )
    return agents[agent_id]


def has_agent(agent_id: str) -> bool:
    return agent_id in _agents()


def agent_can_use(agent_id: str, tool: str) -> bool:
    """Comprueba la whitelist de tools del agente. '*' = todas."""
    agent = get_agent(agent_id)
    return "*" in agent.tools or tool in agent.tools


def agent_for_tool(tool: str) -> str | None:
    """Devuelve el id del primer agente habilitado que puede usar esa tool.
    Útil para retro-compatibilidad cuando el planner emite pasos sin
    campo ``agent``."""
    for agent in list_agents():
        if "*" in agent.tools or tool in agent.tools:
            return agent.id
    return None


def ask_agent(
    agent_id: str,
    user_prompt: str,
    *,
    history: list[dict] | None = None,
    extra_context: str = "",
) -> str:
    """Pregunta directa a un agente. Sin tool-use, solo texto in/out.

    Si se proporciona ``history`` (lista de ``{role, text}``), se incluye
    como contexto de conversación antes del mensaje actual.

    Cae al ``fallback_provider`` si el primario no está disponible o
    devuelve error de credenciales/red.
    """
    agent = get_agent(agent_id)

    messages: list[LLMMessage] = []
    if agent.system:
        messages.append(LLMMessage(role="system", content=agent.system))
    if extra_context:
        messages.append(LLMMessage(role="system", content=extra_context))

    # Conversation history — últimos 20 mensajes para no exceder contexto
    if history:
        for h in history[-20:]:
            role = h.get("role", "user")
            text = h.get("text", "")
            if not text:
                continue
            llm_role = "assistant" if role == "agent" else "user"
            messages.append(LLMMessage(role=llm_role, content=text))

    messages.append(LLMMessage(role="user", content=user_prompt))

    try:
        provider = get_provider(agent.provider)
        if provider.is_available():
            resp: LLMResponse = provider.complete(
                messages, model=agent.model, temperature=agent.temperature
            )
            return resp.text
    except Exception as e:
        print(f"[AgentRegistry] ⚠️ {agent.id}/{agent.provider} falló: {e}")

    # Fallback declarado en agents.json.
    if agent.fallback_provider and agent.fallback_model:
        print(f"[AgentRegistry] 🔄 {agent.id} → fallback {agent.fallback_provider}")
        provider = get_provider(agent.fallback_provider)
        resp = provider.complete(
            messages, model=agent.fallback_model, temperature=agent.temperature
        )
        return resp.text

    raise RuntimeError(
        f"Agente '{agent.id}' no pudo responder: provider '{agent.provider}' "
        f"no disponible y sin fallback definido."
    )
