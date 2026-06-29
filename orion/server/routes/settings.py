"""
server.routes.settings — Configuración
========================================
Endpoints:
  GET    /api/settings/theme              → { name, theme, available: [...] }
  PATCH  /api/settings/theme              → { name } cambia el tema activo

Usa :mod:`config.theme_tokens` (fachada headless, sin Qt) — ver R-21 de
la auditoría pre-Fase 0. La UI Qt reacciona al cambio vía su propio
``theme_bus`` (se recargará al reiniciar; el evento WS notifica al
frontend para repintar en caliente).
"""

from __future__ import annotations

import contextlib
import json
import os
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from orion.config import (
    API_CONFIG_PATH,
    CONFIG_DIR,
    DATA_DIR,
    SQLITE_DB_PATH,
    VOICE_CONFIG_PATH,
)
from orion.config import (
    load_config as load_api_config,
)
from orion.config import (
    save_config as save_api_config,
)
from orion.config.theme_tokens import (
    DEFAULT_THEME,
    THEMES,
    get_theme,
    list_themes,
    load_theme_name,
    save_theme_name,
)

router = APIRouter()


# ── Voice config ────────────────────────────────────────────────────────
#
# Las voces preconstruidas que Gemini Live expone en su API. Se mantienen
# como Literal para que Pydantic rechace cualquier valor que el modelo
# subyacente no acepte.
PREBUILT_VOICES: tuple[str, ...] = ("Aoede", "Charon", "Fenrir", "Kore", "Puck")
DEFAULT_VOICE_NAME: str = "Charon"
DEFAULT_LANGUAGE_CODE: str = "es-US"
SUPPORTED_LANGUAGES: tuple[str, ...] = (
    "es-US",
    "es-ES",
    "es-MX",
    "en-US",
    "en-GB",
    "en-AU",
    "fr-FR",
    "de-DE",
    "it-IT",
    "pt-BR",
    "ja-JP",
    "ko-KR",
    "zh-CN",
)


def _load_voice_config() -> dict:
    """Carga el archivo de config de voz, devolviendo defaults si no existe."""
    if not VOICE_CONFIG_PATH.exists():
        return {
            "voice_name": DEFAULT_VOICE_NAME,
            "language_code": DEFAULT_LANGUAGE_CODE,
        }
    try:
        data = json.loads(VOICE_CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "voice_name": DEFAULT_VOICE_NAME,
            "language_code": DEFAULT_LANGUAGE_CODE,
        }
    return {
        "voice_name": data.get("voice_name") or DEFAULT_VOICE_NAME,
        "language_code": data.get("language_code") or DEFAULT_LANGUAGE_CODE,
    }


def _save_voice_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    VOICE_CONFIG_PATH.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


class VoiceConfigBody(BaseModel):
    voice_name: Literal["Aoede", "Charon", "Fenrir", "Kore", "Puck"]
    language_code: str = Field(..., min_length=2, max_length=10)


@router.get("/voice")
def get_voice_settings() -> dict:
    """Devuelve la configuración actual de voz + los catálogos de opciones
    válidas para que el frontend arme dropdowns sin hardcodear listas.

    Los cambios solo aplican al iniciar una nueva sesión Live (el motor
    recibe la SpeechConfig al abrir el canal con Gemini).
    """
    cfg = _load_voice_config()
    return {
        "voice_name": cfg["voice_name"],
        "language_code": cfg["language_code"],
        "available_voices": list(PREBUILT_VOICES),
        "available_languages": list(SUPPORTED_LANGUAGES),
    }


@router.patch("/voice")
def patch_voice_settings(body: VoiceConfigBody, request: Request) -> dict:
    if body.language_code not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Idioma '{body.language_code}' no soportado. "
                f"Opciones válidas: {', '.join(SUPPORTED_LANGUAGES)}"
            ),
        )
    cfg = {
        "voice_name": body.voice_name,
        "language_code": body.language_code,
    }
    _save_voice_config(cfg)
    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        with contextlib.suppress(Exception):
            bus.publish("settings.voice", cfg)
    return {
        "ok": True,
        **cfg,
        "available_voices": list(PREBUILT_VOICES),
        "available_languages": list(SUPPORTED_LANGUAGES),
    }


# ── Data stats ──────────────────────────────────────────────────────────


def _count_rows(conn, table: str) -> int:
    """Cuenta filas defensivamente: si la tabla todavía no existe (porque
    el subsistema correspondiente nunca se usó), devuelve 0 en lugar de
    propagar la excepción."""
    try:
        cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
        row = cur.fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


@router.get("/data")
def get_data_stats() -> dict:
    """Devuelve estadísticas reales de la persistencia local: ruta del DB,
    tamaño en disco y conteos por tabla. Pensado para que el panel
    "Datos" del usuario muestre qué tiene almacenado sin necesidad de
    abrir herramientas externas.
    """
    from orion.storage import get_connection

    db_size_bytes = 0
    if SQLITE_DB_PATH.exists():
        try:
            db_size_bytes = SQLITE_DB_PATH.stat().st_size
        except OSError:
            db_size_bytes = 0

    conn = get_connection()
    tables = {
        "quick_notes": "Notas rápidas",
        "memory_entries": "Memoria semántica",
        "conversations": "Conversaciones",
        "conversation_messages": "Mensajes de chat",
        "notifications": "Notificaciones",
        "access_users": "Usuarios biométricos",
        "access_events": "Eventos de acceso",
    }
    counts = [
        {"table": tname, "label": label, "count": _count_rows(conn, tname)}
        for tname, label in tables.items()
    ]

    return {
        "db_path": str(SQLITE_DB_PATH),
        "db_size_bytes": db_size_bytes,
        "data_dir": str(DATA_DIR),
        "tables": counts,
    }


class ThemePatch(BaseModel):
    name: str = Field(..., min_length=1)


# Handlers con I/O sincrónico (load_theme_name, load_api_config) van como
# `def` para que FastAPI los despache al threadpool y no bloqueen el loop.


@router.get("/theme")
def get_theme_endpoint() -> dict:
    name = load_theme_name() or DEFAULT_THEME
    return {
        "name": name,
        "theme": get_theme(name),
        "available": [{"id": tid, "name": tname} for tid, tname in list_themes()],
    }


class ApiKeyBody(BaseModel):
    key: str = Field(..., min_length=10, max_length=400)


@router.get("/api_key")
def get_api_key_status() -> dict:
    """No expone la key, sólo si está configurada (en env var o archivo).

    Esto es lo que el wizard del frontend usa para decidir si mostrarse
    o no.
    """
    env_key = (os.environ.get("ORION_GEMINI_KEY") or "").strip()
    cfg = load_api_config()
    file_key = (cfg.get("gemini_api_key") or "").strip()
    configured = bool(env_key or file_key)
    return {
        "configured": configured,
        "source": "env" if env_key else ("file" if file_key else None),
        "path": str(API_CONFIG_PATH) if not env_key else None,
    }


@router.post("/api_key")
def set_api_key(body: ApiKeyBody, request: Request) -> dict:
    """Guarda la API key de Gemini en ``config/api_keys.json``.

    Si la key entra por env var ``ORION_GEMINI_KEY`` siempre toma
    prioridad sobre el archivo (ver :func:`config.get_api_key`).
    Después de guardar emite ``system.ready`` por el bus para
    desbloquear ``wait_for_api_key`` y notificar a la UI.
    """
    key = body.key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="API key vacía")

    cfg = load_api_config()
    cfg["gemini_api_key"] = key
    cfg.setdefault("os_system", "windows")
    save_api_config(cfg)

    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        with contextlib.suppress(Exception):
            bus.mark_ready()

    return {"ok": True, "configured": True}


class SharingBody(BaseModel):
    enabled: bool


@router.get("/sharing")
def get_sharing_endpoint() -> dict:
    """Devuelve el estado del toggle 'Compartir vía Tailscale' + la IP
    Tailscale detectada (si está) para mostrarla en la UI."""
    from orion.server.sharing import detect_tailscale_ip, get_sharing

    return {
        "enabled": get_sharing(),
        "tailscale_ip": detect_tailscale_ip(),
        "port": 8765,
    }


@router.post("/sharing")
def post_sharing_endpoint(body: SharingBody, request: Request) -> dict:
    """Activa/desactiva el filtro de IP. Persiste en config/sharing.json
    y notifica via bus (settings.sharing) para que el frontend re-renderice."""
    from orion.server.sharing import detect_tailscale_ip, set_sharing

    enabled = set_sharing(body.enabled)
    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        with contextlib.suppress(Exception):
            bus.publish("settings.sharing", {"enabled": enabled})
    return {
        "ok": True,
        "enabled": enabled,
        "tailscale_ip": detect_tailscale_ip(),
        "port": 8765,
    }


@router.patch("/theme")
def patch_theme(body: ThemePatch, request: Request) -> dict:
    if body.name not in THEMES:
        raise HTTPException(
            status_code=400,
            detail=f"Tema '{body.name}' no existe. Disponibles: {sorted(THEMES.keys())}",
        )
    save_theme_name(body.name)
    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        with contextlib.suppress(Exception):
            bus.publish(
                "settings.theme",
                {
                    "name": body.name,
                    "theme": get_theme(body.name),
                },
            )
    return {"ok": True, "name": body.name, "theme": get_theme(body.name)}
