"""
server.routes.integrations — Integraciones externas (Google vía gog)
=====================================================================
Endpoints para que la UI gestione la autorización de cuentas Google
sin tocar la terminal:

  GET    /api/integrations/gog/accounts      → lista de cuentas activas
  GET    /api/integrations/gog/services      → catálogo gog
  GET    /api/integrations/gog/flow_status   → estado del flow en curso
  POST   /api/integrations/gog/start_auth    → arrancar gog auth add
  POST   /api/integrations/gog/cancel        → matar flow en curso
  POST   /api/integrations/gog/reset         → limpiar estado terminal
  POST   /api/integrations/gog/check         → ¿esta cuenta tiene estos servicios?

Diseño consciente: gog hace todo el trabajo pesado (browser OAuth,
callback localhost, intercambio de code → token). Acá solo wrapeamos
para tener una API REST que el frontend pueda consumir con poll.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from orion.actions import gog_auth
from orion.core.logger import get_logger
from orion.server import safe_error_detail

log = get_logger("server.routes.integrations")

router = APIRouter()


class StartAuthBody(BaseModel):
    account: str
    services: list[str] | None = None
    force_consent: bool = True


class CheckBody(BaseModel):
    account: str
    services: list[str] = Field(..., description="Servicios requeridos")


@router.get("/gog/accounts")
def gog_accounts() -> list[dict]:
    try:
        return gog_auth.list_accounts()
    except Exception as e:
        log.warning("list_accounts falló: %s", e)
        raise HTTPException(status_code=500, detail=safe_error_detail(e)) from e


@router.get("/gog/services")
def gog_services() -> list[dict]:
    try:
        return gog_auth.list_services()
    except Exception as e:
        log.warning("list_services falló: %s", e)
        raise HTTPException(status_code=500, detail=safe_error_detail(e)) from e


@router.get("/gog/flow_status")
def gog_flow_status() -> dict:
    return gog_auth.get_flow_status()


@router.post("/gog/start_auth")
def gog_start_auth(body: StartAuthBody) -> dict:
    try:
        return gog_auth.start_auth(
            account=body.account,
            services=body.services,
            force_consent=body.force_consent,
        )
    except Exception as e:
        log.exception("start_auth falló")
        raise HTTPException(status_code=400, detail=safe_error_detail(e)) from e


@router.post("/gog/cancel")
def gog_cancel() -> dict:
    return gog_auth.cancel_flow()


@router.post("/gog/reset")
def gog_reset() -> dict:
    return gog_auth.reset_flow()


@router.post("/gog/check")
def gog_check(body: CheckBody) -> dict:
    """¿La cuenta tiene los servicios? Usado por los guards contextuales."""
    return gog_auth.account_has_services(body.account, body.services)
