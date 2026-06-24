"""
server.routes.onboarding — Wizard de primer arranque
=====================================================
Pensado para distribución a usuarios no-devs: cuando un usuario abre
Orion por primera vez (no hay ``api_keys.json`` con Gemini key), el
frontend muestra un modal bloqueante que llama estos endpoints.

Endpoints:
  GET   /api/onboarding/status   → { ready, has_api_key, paths, ... }
  POST  /api/onboarding/save     → { ok | error_kind, error? }

``status`` no requiere body — el frontend lo poll-ea cada vez que abre
la app y decide si renderizar el wizard o ir directo a la UI.

``save`` recibe la API key, opcionalmente la valida contra Gemini con un
call de bajo costo (``models.list``), y la persiste en
``%APPDATA%\\Orion\\config\\api_keys.json``.
"""

from __future__ import annotations

import os

import contextlib

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from orion.config import (
    API_CONFIG_PATH,
    BASE_DIR,
    CONFIG_DIR,
    DATA_DIR,
    has_valid_api_key,
    load_config,
    save_config,
    seed_default_configs,
)
from orion.core.logger import get_logger

log = get_logger("onboarding")

router = APIRouter()


class OnboardingBrainInfo(BaseModel):
    """Snapshot del cerebro activo + disponibilidad de su provider.

    El wizard lo usa para decidir si está "ready" por un camino no-Gemini
    (DeepSeek u Ollama con credenciales) sin obligar al usuario a darle
    key de Gemini para arrancar.
    """

    provider: str
    model: str
    is_live: bool
    available: bool


class OnboardingStatus(BaseModel):
    ready: bool = Field(
        ...,
        description=(
            "True si la app puede arrancar sin pasar por el wizard: el usuario "
            "tiene key de Gemini, O el cerebro activo no es Gemini y su provider "
            "tiene credenciales (ej: DeepSeek con key, Ollama corriendo)."
        ),
    )
    has_api_key: bool
    base_dir: str
    config_dir: str
    data_dir: str
    api_keys_path: str
    brain: OnboardingBrainInfo


class OnboardingSaveBody(BaseModel):
    gemini_api_key: str = Field(
        ...,
        min_length=10,
        description="API key de Google AI Studio. Formato típico: 'AIza…'.",
    )
    validate_remote: bool = Field(
        True,
        description=(
            "Hace un round-trip a Gemini para validar la key antes de "
            "persistir. Si está en False solo se chequea formato."
        ),
    )


class OnboardingSaveResult(BaseModel):
    ok: bool
    message: str
    api_keys_path: str | None = None


@router.get("/status", response_model=OnboardingStatus)
def get_status() -> OnboardingStatus:
    # Trigger del seed silencioso en cada status check — es idempotente,
    # solo crea archivos si NO existen aún. Garantiza que en primer
    # arranque los templates ya estén disponibles cuando el usuario
    # termina el wizard.
    seed_default_configs()
    has_key = has_valid_api_key()

    # Estado del cerebro activo. Si el usuario eligió DeepSeek u Ollama y
    # configuró su provider correctamente, también está "ready" — no
    # debería verse el wizard solo porque le falta una key de Gemini.
    from orion.core.chat_brain import get_active_brain, is_live_brain
    from orion.core.llm.base import get_provider as _get_provider

    brain_cfg = get_active_brain()
    try:
        brain_available = _get_provider(brain_cfg.provider).is_available()
    except Exception:
        brain_available = False

    brain_info = OnboardingBrainInfo(
        provider=brain_cfg.provider,
        model=brain_cfg.model,
        is_live=is_live_brain(),
        available=brain_available,
    )

    # ready = camino Gemini ya configurado, o el camino alternativo está listo.
    ready = has_key or (not brain_info.is_live and brain_available)

    return OnboardingStatus(
        ready=ready,
        has_api_key=has_key,
        base_dir=str(BASE_DIR),
        config_dir=str(CONFIG_DIR),
        data_dir=str(DATA_DIR),
        api_keys_path=str(API_CONFIG_PATH),
        brain=brain_info,
    )


@router.post("/save", response_model=OnboardingSaveResult)
def save(body: OnboardingSaveBody, request: Request) -> OnboardingSaveResult:
    key = body.gemini_api_key.strip()
    if not key:
        raise HTTPException(400, "API key vacía.")

    if body.validate_remote:
        validate_error = _validate_gemini_key(key)
        if validate_error:
            # Devolvemos 400 con un mensaje accionable. El frontend lo
            # renderiza dentro del modal sin perder lo que el usuario
            # ya tipeó.
            raise HTTPException(status_code=400, detail=validate_error)

    # Merge con el resto del config si ya había algo (ej: os_system).
    existing = load_config()
    existing["gemini_api_key"] = key
    try:
        save_config(existing)
    except OSError as e:
        log.exception("save_config falló")
        raise HTTPException(500, f"No pude escribir {API_CONFIG_PATH}: {e}") from e

    # Side-effect: refresh de la env var para que código que llame
    # ``os.environ['ORION_GEMINI_KEY']`` (raro pero existe) vea el valor
    # nuevo sin reiniciar. NO la sobrescribimos si el usuario ya la tenía
    # explícitamente seteada.
    os.environ.setdefault("ORION_GEMINI_KEY", key)

    # Desbloquear el OrionLive runner thread que está bloqueado en
    # ``bus.wait_for_api_key()`` desde el arranque. Sin esto el usuario
    # tendría que cerrar y reabrir la app para hablar con Gemini —
    # mala UX de primer arranque.
    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        with contextlib.suppress(Exception):
            bus.mark_ready()

    log.info("API key Gemini guardada (len=%d) en %s", len(key), API_CONFIG_PATH)
    return OnboardingSaveResult(
        ok=True,
        message="API key guardada. Orion ya puede conectarse a Gemini.",
        api_keys_path=str(API_CONFIG_PATH),
    )


def _validate_gemini_key(key: str) -> str | None:
    """Valida la API key contra Gemini con un call mínimo (models.list).
    Devuelve None si es válida, o un mensaje accionable si no.

    Mantenemos la dep en ``google-genai`` opcional: si no está instalada
    saltamos la validación remota — mejor persistir y dejar que el usuario
    descubra el problema con un mensaje claro que bloquear arranque por
    una dep mal instalada.
    """
    try:
        from google import genai  # type: ignore[import-not-found]
    except ImportError:
        log.warning("google-genai no está instalado — skip validación remota")
        return None

    try:
        client = genai.Client(api_key=key)
        # models.list pagina, .next() es suficiente para validar auth.
        next(iter(client.models.list()), None)
    except Exception as e:  # Google SDK levanta muchas variantes; catch wide.
        msg = str(e).lower()
        if "api key not valid" in msg or "api_key_invalid" in msg or "permission_denied" in msg:
            return (
                "Google rechazó la API key (API_KEY_INVALID). "
                "Verifica que la copiaste completa desde Google AI Studio."
            )
        if "quota" in msg or "exceeded" in msg:
            return (
                "La key es válida pero el proyecto se quedó sin cuota gratuita. "
                "Probá con otra key o esperá al reset diario."
            )
        # Errores genéricos de red, DNS, timeout: dejamos pasar para no bloquear
        # al usuario si está en una red restrictiva. Persistimos y que retry.
        log.warning("validación remota falló (acepto igual): %s", e)
        return None
    return None
