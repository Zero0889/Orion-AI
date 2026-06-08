"""
server.routes.notifications — Bandeja de notificaciones
========================================================
Endpoints:

  GET  /api/notifications             → lista (?source=, ?unread=)
  GET  /api/notifications/status      → status del poller + último ok por source
  POST /api/notifications/poll        → forzar refresco (?source=)
  POST /api/notifications/mark-read   → body {"uids": [...]}
  POST /api/notifications/mark-all-read?source=...
  POST /api/notifications/classroom/authorize → abre el OAuth dance (devuelve path token)
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from actions.notifications import get_poller, get_store
from core.logger import get_logger

log = get_logger("server.routes.notifications")

# Cap del OAuth dance (Google InstalledAppFlow + interacción del usuario).
_OAUTH_TIMEOUT_S = 180.0

router = APIRouter()


# NOTA arquitectura (I-04): los endpoints que hacen I/O sincrónico (disco,
# locks que un thread puede tener tomado, llamadas HTTP a Gmail/Classroom)
# se declaran como `def` (no `async def`). FastAPI los despacha al
# threadpool de starlette automáticamente, liberando el event loop para
# que el WS y otros REST sigan respondiendo.

@router.get("")
def list_notifications(source: str | None = None, unread: bool = False) -> list[dict]:
    return get_store().list_all(source=source, unread_only=unread)


@router.get("/status")
def poller_status() -> dict:
    return get_poller().status()


@router.post("/poll")
def poll_now(request: Request, source: str | None = None) -> dict:
    poller = get_poller()
    # Si no estaba seteado el publish (arranque temprano), lo cableamos ahora.
    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        poller.set_publish(bus.publish)
    return poller.poll_once(only_source=source)


class MarkReadBody(BaseModel):
    uids: list[str] = Field(default_factory=list)


@router.post("/mark-read")
def mark_read(body: MarkReadBody, request: Request) -> dict:
    n = get_store().mark_read(body.uids)
    bus = getattr(request.app.state, "bus", None)
    if bus is not None and n:
        try:
            bus.publish("notification.read", {"count": n})
        except Exception as e:
            log.debug("publish notification.read falló: %s", e)
    return {"ok": True, "marked": n}


@router.post("/mark-all-read")
def mark_all_read(request: Request, source: str | None = None) -> dict:
    n = get_store().mark_all_read(source=source)
    bus = getattr(request.app.state, "bus", None)
    if bus is not None and n:
        try:
            bus.publish("notification.read", {"count": n, "source": source})
        except Exception as e:
            log.debug("publish notification.read falló: %s", e)
    return {"ok": True, "marked": n}


@router.post("/classroom/authorize")
async def classroom_authorize() -> dict:
    """Abre el navegador para el OAuth dance de Classroom.

    El ``InstalledAppFlow`` de google-auth-oauthlib es **estrictamente
    bloqueante** (levanta un webserver efímero en localhost:<random> y
    espera al callback). Para no congelar el event loop de uvicorn durante
    hasta 3 minutos, despachamos la operación al threadpool default de
    asyncio con ``run_in_executor`` y la envolvemos con ``wait_for`` para
    el timeout. Mientras el OAuth corre, otros endpoints REST y el WS
    siguen respondiendo normalmente.
    """
    from actions.notifications.classroom import authorize_interactive

    loop = asyncio.get_running_loop()
    try:
        token_path = await asyncio.wait_for(
            loop.run_in_executor(None, authorize_interactive),
            timeout=_OAUTH_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        # El thread del OAuth queda huérfano en background — no podemos
        # cancelarlo (Google no expone API de abort). El usuario simplemente
        # cerró/abandonó el navegador. Próxima llamada limpia.
        raise HTTPException(status_code=504, detail="OAuth timeout (3min)")
    except Exception as e:
        from server import safe_error_detail
        log.exception("OAuth Classroom falló")
        raise HTTPException(status_code=500, detail=safe_error_detail(e))
    return {"ok": True, "token_path": token_path}
