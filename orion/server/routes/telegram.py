"""
server.routes.telegram — Endpoints de configuración del bridge Telegram.

  GET  /api/settings/telegram         → status + config (sin exponer el token completo)
  PUT  /api/settings/telegram         → guarda config y recarga el bridge
  POST /api/settings/telegram/test    → manda un mensaje de prueba al chat configurado
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from orion.adapters.messaging.telegram import (
    TelegramClient,
    TelegramConfig,
    load_telegram_config,
    save_telegram_config,
)
from orion.core.logger import get_logger
from orion.server.telegram_bridge import get_bridge, init_bridge

log = get_logger("routes.telegram")
router = APIRouter()


def _mask_token(token: str) -> str:
    """Devuelve la cola del token (después del ``:``) para feedback visual
    sin re-exponer el secreto completo. Ej: ``123456:ABC...XYZ`` → ``ABC...XYZ``
    truncado."""
    if not token:
        return ""
    if ":" in token:
        tail = token.split(":", 1)[1]
    else:
        tail = token
    if len(tail) <= 8:
        return "***"
    return f"{tail[:4]}...{tail[-4:]}"


class TelegramConfigBody(BaseModel):
    bot_token: str | None = Field(default=None, max_length=200)
    default_chat_id: str | None = Field(default=None, max_length=64)
    forward_notifications: bool | None = None
    enabled: bool | None = None


class TelegramTestBody(BaseModel):
    message: str = Field(
        "🤖 Hola desde Orion. Telegram bridge activo.",
        max_length=500,
    )


@router.get("/telegram")
def get_telegram_state() -> dict:
    """Estado actual del bridge + config (token enmascarado)."""
    bridge = get_bridge()
    if bridge is None:
        # El bridge se inicia en el lifespan del server; si todavía no
        # arrancó (caso raro de carrera), devolvemos un status mínimo
        # basado en el config en disco.
        cfg = load_telegram_config()
        return {
            "enabled": cfg.enabled,
            "configured": cfg.is_configured,
            "has_token": bool(cfg.bot_token),
            "token_preview": _mask_token(cfg.bot_token),
            "default_chat_id": cfg.default_chat_id,
            "forward_notifications": cfg.forward_notifications,
            "running": False,
            "bot_username": None,
            "bot_ok": False,
            "bot_error": "bridge no inicializado",
        }
    status = bridge.status()
    status["token_preview"] = _mask_token(load_telegram_config().bot_token)
    return status


@router.put("/telegram")
def patch_telegram(body: TelegramConfigBody, request: Request) -> dict:
    """Patch parcial: solo se sobreescriben los campos que llegan no-None."""
    current = load_telegram_config()
    bot_token = body.bot_token if body.bot_token is not None else current.bot_token
    chat_id = body.default_chat_id if body.default_chat_id is not None else current.default_chat_id
    forward = (
        body.forward_notifications
        if body.forward_notifications is not None
        else current.forward_notifications
    )
    enabled = body.enabled if body.enabled is not None else current.enabled

    bot_token = (bot_token or "").strip()
    chat_id = (chat_id or "").strip()

    # Si el usuario quiere activarlo pero no hay token+chat, devolvemos 400
    # — mejor un error claro que un bridge encendido sin poder hablar.
    if enabled and not (bot_token and chat_id):
        raise HTTPException(
            status_code=400,
            detail="Para activar Telegram necesitás bot_token + default_chat_id.",
        )

    new_cfg = TelegramConfig(
        bot_token=bot_token,
        default_chat_id=chat_id,
        forward_notifications=bool(forward),
        enabled=bool(enabled),
    )
    save_telegram_config(new_cfg)

    # Recargar bridge para aplicar el cambio en caliente.
    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        init_bridge(bus)

    bridge = get_bridge()
    status = bridge.status() if bridge else {}
    status["token_preview"] = _mask_token(new_cfg.bot_token)
    return status


@router.post("/telegram/test")
def test_telegram(body: TelegramTestBody) -> dict:
    """Manda un mensaje al chat configurado para validar que todo conecta."""
    cfg = load_telegram_config()
    if not cfg.is_configured:
        raise HTTPException(
            status_code=400,
            detail="Falta bot_token o default_chat_id.",
        )
    try:
        client = TelegramClient(cfg.bot_token)
        resp = client.send_message(cfg.default_chat_id, body.message)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Telegram falló: {e}") from e
    if not resp.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=f"Telegram rechazó: {resp.get('description') or resp}",
        )
    return {"ok": True, "result": resp.get("result", {})}
