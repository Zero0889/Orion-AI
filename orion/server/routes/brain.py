"""
server.routes.brain — Configuración del "cerebro" del chat principal.

Endpoints
---------
- ``GET  /api/settings/brain``  → estado completo: cerebro activo +
  catálogo de proveedores con disponibilidad + info de Ollama.
- ``PUT  /api/settings/brain``  → cambia provider/model y emite evento
  ``settings.brain`` por el bus para que el frontend re-renderice.
- ``PUT  /api/settings/brain/providers/{name}/key`` → guarda/borra una
  key en ``config/providers.json`` e invalida los caches.
- ``POST /api/settings/brain/test``  → ping con un mensaje breve al
  provider/modelo elegido y devuelve la respuesta o el error.

El catálogo de proveedores se reusa de :mod:`orion.server.routes.agent`
(misma fuente de verdad: la que usa el editor de agentes). Para Ollama
local sumamos un endpoint extra que detecta si el daemon está corriendo
y lista los modelos descargados — necesario para que la UI explique al
usuario cómo arrancarlo.

Nota sobre Gemini: aunque sea el default "live brain", también lo
exponemos como opción aquí. Elegir gemini en el switch desactiva el
camino chat_brain — el ChatPanel vuelve a ir por la sesión Live.
"""

from __future__ import annotations

import contextlib
import json
import urllib.error
import urllib.request
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from orion.core.chat_brain import (
    DEFAULT_MODEL_PER_PROVIDER,
    get_active_brain,
    is_live_brain,
    set_active_brain,
)
from orion.config import get_api_key as get_gemini_api_key
from orion.core.llm.base import (
    LLMMessage,
    get_provider,
    set_provider_key,
)
from orion.core.logger import get_logger
from orion.server.routes.agent import _PROVIDER_CATALOG, _provider_available

log = get_logger("routes.brain")

router = APIRouter()

# Endpoint default de Ollama local — el adapter usa el mismo path en
# core/llm/openai_compat.py. Lo redeclaramos acá para el chequeo de
# detección y poder cambiarlo en tests.
OLLAMA_LOCAL_BASE = "http://localhost:11434"
OLLAMA_PROBE_TIMEOUT_S = 1.5


# ── Modelos Pydantic ────────────────────────────────────────────────────


class BrainPatch(BaseModel):
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)


class ProviderKeyBody(BaseModel):
    key: str = Field(..., max_length=400)


class BrainTestBody(BaseModel):
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    prompt: str = Field(
        "Decí 'pong' y nada más.",
        max_length=400,
        description="Prompt corto para probar el ping. Default razonable para que sea barato.",
    )


# ── Helpers ─────────────────────────────────────────────────────────────


def _ollama_detect() -> dict:
    """Hace ping a ``localhost:11434/api/tags``. Devuelve si el daemon está
    arriba + la lista de modelos descargados.

    El timeout es bajo (1.5s) para no bloquear el render del Settings.
    En Windows si Ollama no está instalado, el connect refused es inmediato.
    """
    url = f"{OLLAMA_LOCAL_BASE}/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=OLLAMA_PROBE_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            models_raw = data.get("models") or []
            models: list[dict] = []
            for m in models_raw:
                if not isinstance(m, dict):
                    continue
                models.append(
                    {
                        "name": m.get("name", ""),
                        "size": m.get("size", 0),
                        "modified_at": m.get("modified_at", ""),
                    }
                )
            return {
                "running": True,
                "base_url": OLLAMA_LOCAL_BASE,
                "models": models,
            }
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        log.debug("Ollama no detectado en %s: %s", OLLAMA_LOCAL_BASE, e)
        return {
            "running": False,
            "base_url": OLLAMA_LOCAL_BASE,
            "models": [],
        }


def _providers_payload() -> list[dict]:
    """Catálogo + status de disponibilidad de cada provider.

    Reusa el catálogo declarativo de routes/agent.py para mantener una
    única fuente de verdad de "qué modelos existen por provider".
    """
    out: list[dict] = []
    for name, info in _PROVIDER_CATALOG.items():
        out.append(
            {
                "id": name,
                "label": info["label"],
                "free": info["free"],
                "auth_hint": info["auth"],
                "models": info["models"],
                "default_model": DEFAULT_MODEL_PER_PROVIDER.get(name, ""),
                "available": _provider_available(name),
                "needs_key": name not in ("ollama",),
            }
        )
    return out


def _publish_brain_change(request: Request, provider: str, model: str) -> None:
    bus = getattr(request.app.state, "bus", None)
    if bus is None:
        return
    with contextlib.suppress(Exception):
        bus.publish("settings.brain", {"provider": provider, "model": model})


def _gemini_key_status() -> dict:
    """Devuelve el estado de la key de Gemini. La UI lo muestra como
    "Voz: habilitada / deshabilitada" porque la voz exige Gemini."""
    try:
        get_gemini_api_key()
        configured = True
    except RuntimeError:
        configured = False
    return {"configured": configured}


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get("/brain")
def get_brain_state() -> dict:
    """Estado completo del cerebro: activo + catálogo + ollama + gemini."""
    active = get_active_brain()
    return {
        "active": {
            "provider": active.provider,
            "model": active.model,
            "is_live": is_live_brain(),
        },
        "providers": _providers_payload(),
        "ollama": _ollama_detect(),
        "gemini": _gemini_key_status(),
    }


@router.put("/brain")
def patch_brain(body: BrainPatch, request: Request) -> dict:
    provider = body.provider.strip().lower()
    model = body.model.strip()

    if provider not in _PROVIDER_CATALOG:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Provider '{provider}' no soportado. Conocidos: {sorted(_PROVIDER_CATALOG.keys())}"
            ),
        )

    try:
        cfg = set_active_brain(provider, model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    _publish_brain_change(request, cfg.provider, cfg.model)

    # Si el cerebro nuevo NO es Gemini, desbloqueamos el wait_for_api_key del
    # bus. Sin esto el OrionLive runner que arrancó sin key sigue bloqueado
    # esperando una key Gemini que el usuario no va a poner — y el chat de
    # texto vía chat_brain ya está listo para responder.
    if not is_live_brain():
        bus = getattr(request.app.state, "bus", None)
        if bus is not None:
            with contextlib.suppress(Exception):
                bus.mark_ready()

    return {
        "ok": True,
        "active": {
            "provider": cfg.provider,
            "model": cfg.model,
            "is_live": is_live_brain(),
        },
    }


@router.put("/brain/providers/{name}/key")
def set_brain_provider_key(name: str, body: ProviderKeyBody, request: Request) -> dict:
    """Guarda/borra la key del provider en ``config/providers.json``.

    El path param se usa como provider id. Si es un id desconocido
    devolvemos 400 para evitar guardar basura.
    """
    name = name.strip().lower()
    if name not in _PROVIDER_CATALOG:
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{name}' desconocido.",
        )
    # Ollama local no necesita key. Si alguien manda una, la guardamos
    # igual (puede ser para ollama_cloud — la UI debería elegir bien),
    # pero documentamos el caso.
    try:
        set_provider_key(name, body.key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Notificar al frontend para que actualice el badge "available".
    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        with contextlib.suppress(Exception):
            bus.publish(
                "settings.brain.provider_key",
                {"provider": name, "configured": bool(body.key.strip())},
            )

    return {
        "ok": True,
        "provider": name,
        "configured": bool(body.key.strip()),
        "available": _provider_available(name),
    }


@router.get("/brain/ollama")
def get_ollama_status() -> dict:
    """Endpoint dedicado para que el wizard de onboarding pueda hacer
    polling rápido mientras el usuario instala Ollama."""
    return _ollama_detect()


@router.post("/brain/test")
def test_brain(body: BrainTestBody) -> dict:
    """Manda un mensaje breve al provider+model para validar
    credenciales/conectividad. Devuelve la respuesta truncada o el error."""
    provider_name = body.provider.strip().lower()
    if provider_name not in _PROVIDER_CATALOG:
        raise HTTPException(status_code=400, detail=f"Provider '{provider_name}' desconocido.")

    try:
        provider = get_provider(provider_name)
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"No se pudo cargar {provider_name}: {e}"
        ) from e

    if not provider.is_available():
        return {
            "ok": False,
            "error": f"Sin credenciales para {provider_name}.",
            "actionable": True,
        }

    # Mensaje único + temperature baja: queremos respuesta corta y barata.
    messages: list[LLMMessage] = [
        LLMMessage(role="system", content="Responde en una sola palabra."),
        LLMMessage(role="user", content=body.prompt),
    ]
    try:
        resp = provider.complete(messages, model=body.model, temperature=0.0, max_tokens=20)
    except Exception as e:
        return {
            "ok": False,
            "error": str(e)[:300],
            "actionable": False,
        }
    return {
        "ok": True,
        "model": resp.model,
        "provider": resp.provider,
        "text": (resp.text or "").strip()[:300],
    }


# Re-export para tests que quieran mockear el probe de Ollama.
__all__: list[str] = ["_ollama_detect", "router"]


def _set_ollama_probe(fn: Any) -> None:  # pragma: no cover — solo tests
    """Hook para tests: cambia la función de detección sin tener que
    levantar un Ollama de mentira en HTTP."""
    global _ollama_detect
    _ollama_detect = fn  # type: ignore[assignment]
