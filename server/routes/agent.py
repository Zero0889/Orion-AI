"""
server.routes.agent — Chat directo por agente + CRUD de la orquesta
==================================================================
Endpoints:

Chat directo con agente:
  POST  /api/agent/{id}/chat              → preguntar a un agente específico

Orquesta (catálogo de agentes en config/agents.json):
  GET    /api/agent/orchestra            → lista de agentes con availability
  POST   /api/agent/orchestra            → crear agente nuevo
  PUT    /api/agent/orchestra/{id}       → actualizar (patch parcial)
  DELETE /api/agent/orchestra/{id}       → borrar agente

Catálogo de proveedores (alimenta los dropdowns de la UI):
  GET    /api/agent/providers            → proveedores + modelos sugeridos

Cualquier mutación publica ``agent.task`` u ``orchestra.update`` en el
bus para que el panel React refresque.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.logger import get_logger
from core.llm import get_provider

log = get_logger("server.routes.agent")

router = APIRouter()


# ── Chat directo con agente ────────────────────────────────────────────────

class AgentChatBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    history: list[dict] = Field(default_factory=list)
    """Cada entrada: {"role": "user"|"agent", "text": "..."}"""


@router.post("/{agent_id}/chat")
def agent_chat(agent_id: str, body: AgentChatBody) -> dict:
    """Envía un mensaje directamente a un agente y devuelve su respuesta
    como texto plano. No pasa por la cola de tareas ni por el orquestador
    — es el agente el que responde directamente.

    Incluye ``history`` para mantener el contexto de la conversación."""
    from agent.registry import ask_agent

    answer = ask_agent(agent_id, body.message, history=body.history)
    return {
        "agent_id": agent_id,
        "message":  body.message,
        "response": answer,
    }


# ── Orquesta: catálogo de agentes ──────────────────────────────────────────

class AgentSpec(BaseModel):
    """Spec que llega del frontend. Todos los campos son opcionales en
    PUT (patch parcial) y la mayoría también en POST (defaults razonables
    si no se mandan). Solo ``provider`` y ``model`` son obligatorios."""

    id:          Optional[str] = Field(default=None, min_length=1, max_length=32)
    role:        Optional[str] = None
    icon:        Optional[str] = None
    description: Optional[str] = None
    provider:    Optional[str] = None
    model:       Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    tools:       Optional[list[str]] = None
    system:      Optional[str] = None
    enabled:     Optional[bool] = None
    fallback_provider: Optional[str] = None
    fallback_model:    Optional[str] = None


def _agent_to_payload(agent_id: str, spec: dict, *, available_resolver) -> dict:
    """Normaliza una entrada de agents.json al payload del frontend."""
    provider = spec.get("provider", "")
    try:
        available = available_resolver(provider) if provider else False
    except Exception:
        available = False
    return {
        "id":                agent_id,
        "role":              spec.get("role", agent_id),
        "icon":              spec.get("icon", "circle"),
        "description":       spec.get("description", ""),
        "provider":          provider,
        "model":             spec.get("model", ""),
        "temperature":       float(spec.get("temperature", 0.7)),
        "tools":             list(spec.get("tools", [])),
        "system":            spec.get("system", ""),
        "enabled":           bool(spec.get("enabled", True)),
        "fallback_provider": spec.get("fallback_provider"),
        "fallback_model":    spec.get("fallback_model"),
        "available":         available,
    }


def _provider_available(name: str) -> bool:
    from core.llm import get_provider
    try:
        return get_provider(name).is_available()
    except Exception:
        return False


def _publish_orchestra_update(bus) -> None:
    if bus is None:
        return
    try:
        bus.publish("orchestra.update", {"ts": "now"})
    except Exception:
        pass


@router.get("/orchestra")
def list_orchestra() -> list[dict]:
    """Lista TODOS los agentes definidos (habilitados e inhabilitados).

    La UI necesita ver también los inhabilitados para poder reactivarlos
    o editarlos sin tener que tocar agents.json a mano.
    """
    from agent.orchestra_admin import load_config
    cfg = load_config()
    agents = (cfg.get("agents") or {})
    return [
        _agent_to_payload(aid, spec, available_resolver=_provider_available)
        for aid, spec in agents.items()
    ]


@router.post("/orchestra", status_code=201)
def create_agent(body: AgentSpec, request: Request) -> dict:
    if not body.id:
        raise HTTPException(status_code=422, detail="Falta el campo 'id'.")
    from agent.orchestra_admin import upsert_agent, get_agent_spec
    if get_agent_spec(body.id) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe un agente con id '{body.id}'.",
        )
    spec = body.model_dump(exclude_none=True)
    spec.pop("id", None)
    try:
        saved = upsert_agent(body.id, spec)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    _publish_orchestra_update(getattr(request.app.state, "bus", None))
    return _agent_to_payload(body.id, saved, available_resolver=_provider_available)


@router.put("/orchestra/{agent_id}")
def update_agent(agent_id: str, body: AgentSpec, request: Request) -> dict:
    from agent.orchestra_admin import upsert_agent, get_agent_spec
    if get_agent_spec(agent_id) is None:
        raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' no existe.")
    patch = body.model_dump(exclude_none=True)
    patch.pop("id", None)
    try:
        saved = upsert_agent(agent_id, patch)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    _publish_orchestra_update(getattr(request.app.state, "bus", None))
    return _agent_to_payload(agent_id, saved, available_resolver=_provider_available)


@router.delete("/orchestra/{agent_id}")
def remove_agent(agent_id: str, request: Request) -> dict:
    from agent.orchestra_admin import delete_agent
    try:
        ok = delete_agent(agent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' no existe.")
    _publish_orchestra_update(getattr(request.app.state, "bus", None))
    return {"ok": True, "id": agent_id}


# ── Catálogo de proveedores y modelos sugeridos ────────────────────────────

# Curado: lo que de verdad tiene tier gratuito y vale la pena ofrecer en
# el dropdown. El usuario puede escribir cualquier otro modelo a mano si
# quiere; esto es solo el quick-pick.
_PROVIDER_CATALOG: dict[str, dict] = {
    "gemini": {
        "label":   "Gemini",
        "free":    True,
        "auth":    "env GOOGLE_API_KEY o config/api_keys.json",
        "models":  [
            {"id": "gemini-2.5-flash",      "label": "Flash 2.5 (rápido, multimodal)"},
            {"id": "gemini-2.5-flash-lite", "label": "Flash Lite 2.5 (más barato)"},
            {"id": "gemini-2.5-pro",        "label": "Pro 2.5 (razonador)"},
        ],
    },
    "openrouter": {
        "label":   "OpenRouter",
        "free":    True,
        "auth":    "OPENROUTER_API_KEY",
        "models":  [
            {"id": "deepseek/deepseek-chat-v3.1:free", "label": "DeepSeek V3.1 (chat, gratis)"},
            {"id": "deepseek/deepseek-r1:free",        "label": "DeepSeek R1 (razonador, gratis)"},
            {"id": "meta-llama/llama-3.3-70b-instruct:free", "label": "Llama 3.3 70B (gratis)"},
            {"id": "google/gemini-2.0-flash-exp:free", "label": "Gemini 2.0 Flash (gratis)"},
            {"id": "qwen/qwen-2.5-coder-32b-instruct:free", "label": "Qwen 2.5 Coder 32B (gratis)"},
        ],
    },
    "groq": {
        "label":   "Groq",
        "free":    True,
        "auth":    "GROQ_API_KEY",
        "models":  [
            {"id": "llama-3.3-70b-versatile",          "label": "Llama 3.3 70B (rápido)"},
            {"id": "deepseek-r1-distill-llama-70b",    "label": "DeepSeek R1 Distill 70B"},
            {"id": "qwen-2.5-32b",                     "label": "Qwen 2.5 32B"},
            {"id": "mixtral-8x7b-32768",               "label": "Mixtral 8x7B"},
        ],
    },
    "openai": {
        "label":   "OpenAI",
        "free":    False,
        "auth":    "OPENAI_API_KEY",
        "models":  [
            {"id": "gpt-4o-mini", "label": "GPT-4o mini"},
            {"id": "gpt-4o",      "label": "GPT-4o"},
        ],
    },
    "anthropic": {
        "label":   "Claude (Anthropic)",
        "free":    False,
        "auth":    "ANTHROPIC_API_KEY",
        "models":  [
            {"id": "claude-sonnet-4-6", "label": "Sonnet 4.6"},
            {"id": "claude-opus-4-7",   "label": "Opus 4.7"},
            {"id": "claude-haiku-4-5",  "label": "Haiku 4.5 (rápido y barato)"},
        ],
    },
    "mistral": {
        "label":   "Mistral",
        "free":    True,
        "auth":    "MISTRAL_API_KEY",
        "models":  [
            {"id": "mistral-small-latest", "label": "Mistral Small (free tier)"},
            {"id": "codestral-latest",     "label": "Codestral (coder)"},
        ],
    },
    "ollama": {
        "label":   "Ollama (local)",
        "free":    True,
        "auth":    "sin auth — corre en localhost:11434",
        "models":  [
            {"id": "llama3.1:8b",   "label": "Llama 3.1 8B"},
            {"id": "qwen2.5:7b",    "label": "Qwen 2.5 7B"},
            {"id": "deepseek-r1:8b","label": "DeepSeek R1 8B (destilado)"},
            {"id": "mistral:7b",    "label": "Mistral 7B"},
        ],
    },
    "ollama_cloud": {
        "label":   "Ollama Cloud (Turbo)",
        "free":    False,
        "auth":    "key de ollama.com",
        "models":  [
            # GPT-OSS
            {"id": "gpt-oss:20b-cloud",         "label": "GPT-OSS 20B (cloud, ligero)"},
            {"id": "gpt-oss:120b-cloud",        "label": "GPT-OSS 120B (cloud)"},
            # DeepSeek razonador
            {"id": "deepseek-r1:cloud",         "label": "DeepSeek R1 (cloud, razonador)"},
            {"id": "deepseek-r1:671b-cloud",    "label": "DeepSeek R1 671B (cloud)"},
            # DeepSeek chat
            {"id": "deepseek-v3.2:cloud",       "label": "DeepSeek V3.2 (cloud, más reciente)"},
            {"id": "deepseek-v3.2:671b-cloud",  "label": "DeepSeek V3.2 671B (cloud)"},
            {"id": "deepseek-v3.1:cloud",       "label": "DeepSeek V3.1 (cloud)"},
            {"id": "deepseek-v3.1:671b-cloud",  "label": "DeepSeek V3.1 671B (cloud)"},
            # Qwen
            {"id": "qwen3-coder:480b-cloud",    "label": "Qwen 3 Coder 480B (cloud)"},
            {"id": "qwen3:235b-cloud",          "label": "Qwen 3 235B (cloud)"},
            # Kimi (si tu plan lo incluye)
            {"id": "kimi-k2:1t-cloud",          "label": "Kimi K2 1T (cloud)"},
        ],
    },
    "deepseek": {
        "label":   "DeepSeek",
        "free":    False,
        "auth":    "DEEPSEEK_API_KEY",
        "models":  [
            {"id": "deepseek-chat",             "label": "DeepSeek-V3 (chat, rápido)"},
            {"id": "deepseek-reasoner",         "label": "DeepSeek-R1 (razonador)"},
        ],
    },
}


@router.get("/providers")
def list_providers() -> list[dict]:
    """Catálogo de proveedores con modelos sugeridos.

    El frontend lo usa para poblar los dropdowns de "provider" y "model"
    en el editor de agentes. ``available`` indica si la API key está
    configurada para ese provider.
    """
    out: list[dict] = []
    for name, info in _PROVIDER_CATALOG.items():
        out.append({
            "id":        name,
            "label":     info["label"],
            "free":      info["free"],
            "auth_hint": info["auth"],
            "models":    info["models"],
            "available": _provider_available(name),
        })
    return out
