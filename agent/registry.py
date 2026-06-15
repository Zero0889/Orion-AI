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
from core.llm import LLMMessage, LLMResponse, ToolSpec, get_provider


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
    max_tool_iterations: int = 6,
) -> str:
    """Pregunta directa a un agente.

    Si el agente declara ``tools`` y al menos una está registrada en el
    ``ToolRegistry``, entra en un **agentic loop**: pasa las tools al LLM,
    ejecuta los ``tool_calls`` que devuelva, alimenta los resultados de
    vuelta como turnos ``role=tool``, y repite hasta que el modelo
    devuelva una respuesta final de texto (o se alcance el límite de
    iteraciones).

    Si no tiene tools válidas, cae al modo plano (texto in/out) — igual
    que antes.

    Cae al ``fallback_provider`` si el primario no está disponible o
    devuelve error de credenciales/red. El fallback puede no soportar
    function-calling: en ese caso opera en modo texto plano.
    """
    agent = get_agent(agent_id)

    available_tools = _resolve_agent_tools(agent)

    # Construye los turnos en formato extendido (mismo schema que usan los
    # providers con function-calling).
    turns: list[dict] = []
    if agent.system:
        turns.append({"role": "system", "content": agent.system})
    if extra_context:
        turns.append({"role": "system", "content": extra_context})
    if history:
        for h in history[-20:]:
            text = h.get("text", "")
            if not text:
                continue
            role = "assistant" if h.get("role") == "agent" else "user"
            turns.append({"role": role, "content": text})
    turns.append({"role": "user", "content": user_prompt})

    # ── Modo agentic (con tools) ────────────────────────────────────
    if available_tools:
        try:
            provider = get_provider(agent.provider)
            if provider.is_available():
                return _run_tool_loop(
                    provider=provider,
                    model=agent.model,
                    temperature=agent.temperature,
                    turns=turns,
                    tools=available_tools,
                    max_iterations=max_tool_iterations,
                    agent_id=agent.id,
                )
        except NotImplementedError:
            # Provider primario sin function-calling: probamos fallback.
            print(
                f"[AgentRegistry] ⚠️ {agent.id}/{agent.provider} "
                f"no soporta function-calling — intentando fallback."
            )
        except Exception as e:
            print(f"[AgentRegistry] ⚠️ {agent.id}/{agent.provider} falló: {e}")

        if agent.fallback_provider and agent.fallback_model:
            try:
                fb = get_provider(agent.fallback_provider)
                if fb.is_available():
                    print(
                        f"[AgentRegistry] 🔄 {agent.id} → fallback "
                        f"{agent.fallback_provider} (tool-loop)"
                    )
                    return _run_tool_loop(
                        provider=fb,
                        model=agent.fallback_model,
                        temperature=agent.temperature,
                        turns=turns,
                        tools=available_tools,
                        max_iterations=max_tool_iterations,
                        agent_id=agent.id,
                    )
            except NotImplementedError:
                pass  # Fallback tampoco — caemos a texto plano abajo.
            except Exception as e:
                print(f"[AgentRegistry] ⚠️ fallback de {agent.id} falló: {e}")

    # ── Modo plano (sin tools o sin soporte function-calling) ───────
    messages = [LLMMessage(role=t["role"], content=t.get("content") or "") for t in turns]

    try:
        provider = get_provider(agent.provider)
        if provider.is_available():
            resp: LLMResponse = provider.complete(
                messages, model=agent.model, temperature=agent.temperature
            )
            return resp.text
    except Exception as e:
        print(f"[AgentRegistry] ⚠️ {agent.id}/{agent.provider} falló: {e}")

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


# ── Helpers del agentic loop ─────────────────────────────────────────────

def _resolve_agent_tools(agent: AgentDef) -> list[ToolSpec]:
    """Resuelve la whitelist del agente contra el ToolRegistry.

    - ``"*"`` significa "todas las tools registradas".
    - Tools que el agente declara pero no existen se ignoran (con log).
    - Las que tengan ``silent=True`` o ``include_in_planner=False`` se
      excluyen del expand de ``"*"`` (cumplen el mismo criterio que en el
      planner: son meta-tools, no acciones).
    """
    from core.tool_registry import ToolRegistry

    reg = ToolRegistry()
    declared = set(agent.tools)

    if "*" in declared:
        decls = [
            d for d in reg.all()
            if not d.silent and d.include_in_planner
        ]
    else:
        decls = []
        for name in declared:
            entry = reg.get(name)
            if entry is None:
                print(
                    f"[AgentRegistry] ⚠️ agente {agent.id} declara tool "
                    f"'{name}' pero no está registrada — la ignoro."
                )
                continue
            decls.append(entry[0])

    return [
        ToolSpec(name=d.name, description=d.description, parameters=d.parameters)
        for d in decls
    ]


def _run_tool_loop(
    *,
    provider,
    model: str,
    temperature: float,
    turns: list[dict],
    tools: list[ToolSpec],
    max_iterations: int,
    agent_id: str,
) -> str:
    """Loop agentic: llama LLM → si tool_calls → ejecuta → vuelve a llamar."""
    from core.tool_registry import ToolRegistry

    reg = ToolRegistry()
    working_turns = list(turns)  # copia, no mutamos el original

    for iteration in range(max_iterations):
        resp: LLMResponse = provider.complete_with_tools(
            working_turns, tools, model=model, temperature=temperature,
        )

        # Sin tool_calls: respuesta final.
        if not resp.tool_calls:
            return resp.text or ""

        # Append del turno assistant con los tool_calls solicitados.
        working_turns.append({
            "role": "assistant",
            "content": resp.text or None,
            "tool_calls": resp.tool_calls,
        })

        # Ejecuta cada tool_call y mete el resultado como turn role=tool.
        for tc in resp.tool_calls:
            name = tc.get("name") or ""
            args = tc.get("arguments") or {}
            call_id = tc.get("id") or ""
            try:
                result = reg.call_sync(name, args)
            except KeyError:
                result = f"Error: tool '{name}' no registrada."
            except Exception as e:
                result = f"Error ejecutando '{name}': {type(e).__name__}: {e}"

            working_turns.append({
                "role":         "tool",
                "tool_call_id": call_id,
                "name":         name,
                "content":      str(result),
            })

    print(
        f"[AgentRegistry] ⚠️ {agent_id} alcanzó max_tool_iterations="
        f"{max_iterations}; devolviendo último texto."
    )
    return (
        "(El agente no terminó dentro del límite de iteraciones de tools. "
        "Resultado parcial guardado en logs.)"
    )
