"""
server.app — App FastAPI de O.R.I.O.N
======================================
Punto de entrada del backend web (Fase 1). En esta fase:

  - REST de **solo lectura** sobre los JSON existentes.
  - WebSocket ``/ws`` que retransmite eventos del :class:`OrionEventBus`.
  - La UI Qt sigue corriendo en paralelo (Loop A vs. Loop B en el
    informe de auditoría).

Patrón de uso desde ``main.py``::

    from orion.server.app import build_app
    from orion.server.event_bus import OrionEventBus

    bus = OrionEventBus()
    app = build_app(bus)
    # uvicorn.run(app, host="127.0.0.1", port=8765)

La función :func:`build_app` recibe el bus como dependencia para que las
rutas que necesiten publicar eventos puedan usarlo. No hay variables
globales — la app es siempre creada con el bus inyectado.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from orion.config import RESOURCES_DIR
from orion.core.logger import get_logger

log = get_logger("server.app")

# Bindeamos a todas las interfaces para que dispositivos en la red privada
# Tailscale (rango 100.64.0.0/10) puedan llegar al backend. El acceso real
# se filtra por IP en server.sharing.SharingMiddleware — con "sharing OFF"
# solo localhost pasa, así que bindear a 0.0.0.0 es seguro.
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8765


# ============================================================================
#  Builder
# ============================================================================
def build_app(bus: Any) -> FastAPI:
    """Construye la app FastAPI con el bus inyectado.

    El bus se guarda en ``app.state.bus`` para que las rutas y el hub WS
    accedan a él via ``request.app.state.bus`` o ``ws.app.state.bus``.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Loop A (uvicorn) — el bus lo necesita para hacer fan-out seguro.
        loop = asyncio.get_running_loop()
        bus.attach_server_loop(loop)
        log.info("OrionEventBus conectado al loop uvicorn")

        # Arrancar el drain task del hub WebSocket (definido en ws.py).
        start = getattr(app.state, "ws_start_drain", None)
        if start is not None:
            await start()

        # Telemetría periódica (CPU/RAM/disco) — Fase 3b
        from orion.server.telemetry import run as run_telemetry

        app.state.telemetry_task = asyncio.create_task(run_telemetry(bus))

        try:
            yield
        finally:
            t = getattr(app.state, "telemetry_task", None)
            if t is not None:
                t.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await t

            stop = getattr(app.state, "ws_stop_drain", None)
            if stop is not None:
                await stop()
            log.info("Cerrando app FastAPI")

    app = FastAPI(
        title="O.R.I.O.N Backend",
        version="0.1.0",
        description=(
            "Backend FastAPI + WebSocket de Orion. Convive con la UI Qt "
            "durante la migración a frontend React (rama migration/web-ui)."
        ),
        lifespan=lifespan,
    )
    app.state.bus = bus

    # CORS: el frontend React (Vite dev en :5173) y el host servido por el
    # propio backend (DEFAULT_PORT) son los orígenes confiables. Si la IP
    # Tailscale del equipo está detectable, la añadimos como origen
    # explícito en lugar de aceptar TODO el rango 100/10 — el CGNAT
    # también lo usan otros ISP, y `credentials=true` con regex amplia
    # amplificaba el riesgo (ver auditoría I-08).
    from orion.server.sharing import detect_tailscale_ip

    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        f"http://127.0.0.1:{DEFAULT_PORT}",
        f"http://localhost:{DEFAULT_PORT}",
        # Tauri WebView (modo empaquetado) servirá assets desde el propio
        # backend, así que comparte origen — no necesita entrada aparte.
    ]
    ts_ip = detect_tailscale_ip()
    if ts_ip:
        allowed_origins.append(f"http://{ts_ip}:{DEFAULT_PORT}")
        allowed_origins.append(f"http://{ts_ip}:5173")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Correlation-ID middleware ─────────────────────────────────────────
    # Setea ``orion.core.correlation`` por request. El logger structlog
    # lo lee y lo inyecta como `corr_id=...` en cada log line — permite
    # `grep corr_id=abc12345 logs/orion.log` para reconstruir un request.
    #
    # Si el cliente manda `X-Request-Id`, lo respetamos (útil cuando hay
    # un reverse proxy/CDN que ya genera trace ids). Si no, generamos uno.
    @app.middleware("http")
    async def _correlation_middleware(request, call_next):
        from orion.core.correlation import new_correlation_id, set_correlation_id

        inbound = request.headers.get("X-Request-Id", "").strip()
        cid = inbound if inbound else new_correlation_id()
        if inbound:
            set_correlation_id(inbound)
        response = await call_next(request)
        # Devolvemos el header para que el cliente pueda correlacionar.
        response.headers["X-Request-Id"] = cid
        return response

    # ── Sharing (filtra por IP en cada request) ──────────────────────────
    # Cargado desde config/sharing.json al arrancar; toggleable via API.
    from orion.server.sharing import init_state as init_sharing
    from orion.server.sharing import install as install_sharing

    init_sharing()
    install_sharing(app)

    # ── Endpoint de salud (Fase 1, sin auth) ─────────────────────────────
    @app.get("/api/health")
    async def health() -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "service": "orion-backend",
                "version": app.version,
                "state": getattr(bus, "_state", "ESCUCHANDO"),
                "muted": bool(bus.muted),
            }
        )

    # ── Routers ───────────────────────────────────────────────────────────
    from orion.server.routes import (
        access,
        agent,
        circuit,
        conversations,
        files,
        integrations,
        iot,
        mcp,
        memory,
        notes,
        notifications,
        skills,
    )
    from orion.server.routes import (
        diagnostics as diagnostics_route,
    )
    from orion.server.routes import (
        notebooklm as notebooklm_route,
    )
    from orion.server.routes import (
        onboarding as onboarding_route,
    )
    from orion.server.routes import (
        settings as settings_route,
    )
    from orion.server.routes import (
        brain as brain_route,
    )
    from orion.server.routes import (
        telegram as telegram_route,
    )

    app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
    app.include_router(notes.router, prefix="/api/notes", tags=["notes"])
    app.include_router(conversations.router, prefix="/api/conversations", tags=["conversations"])
    app.include_router(settings_route.router, prefix="/api/settings", tags=["settings"])
    # brain_route monta endpoints bajo /api/settings/brain — los registros
    # son distintos al settings_route (theme/api_key/sharing) así que no chocan.
    app.include_router(brain_route.router, prefix="/api/settings", tags=["settings"])
    app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
    app.include_router(iot.router, prefix="/api/iot", tags=["iot"])
    app.include_router(mcp.router, prefix="/api/mcp", tags=["mcp"])
    app.include_router(skills.router, prefix="/api/skills", tags=["skills"])
    app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
    app.include_router(files.router, prefix="/api/files", tags=["files"])
    app.include_router(notebooklm_route.router, prefix="/api/notebooklm", tags=["notebooklm"])
    app.include_router(integrations.router, prefix="/api/integrations", tags=["integrations"])
    app.include_router(circuit.router, prefix="/api/circuit", tags=["circuit"])
    app.include_router(access.router, prefix="/api/access", tags=["access"])
    app.include_router(onboarding_route.router, prefix="/api/onboarding", tags=["onboarding"])
    app.include_router(diagnostics_route.router, prefix="/api/diagnostics", tags=["diagnostics"])
    app.include_router(telegram_route.router, prefix="/api/settings", tags=["telegram"])

    # ── WebSocket hub ────────────────────────────────────────────────────
    from orion.server.ws import register_ws

    register_ws(app, bus)

    # ── Notification poller (Gmail + Classroom en background) ─────────────
    try:
        from orion.adapters.google.notifications import get_poller, start_poller

        get_poller().set_publish(bus.publish)
        start_poller()
    except Exception as e:
        log.warning("Notification poller no arrancó: %s", e)

    # ── Telegram bridge (long-poll + hook bus) ──────────────────────────
    # Arranca solo si config/telegram.json tiene token + chat_id + enabled.
    # Reloadable en caliente desde PUT /api/settings/telegram sin reiniciar.
    try:
        from orion.server.telegram_bridge import init_bridge as init_tg_bridge

        init_tg_bridge(bus)
    except Exception as e:
        log.warning("Telegram bridge no arrancó: %s", e)

    # ── Frontend estático (Fase 2: si web/dist existe, se sirve aquí) ────
    # En modo dev (Vite en :5173) este bloque no aplica — el usuario abre
    # http://localhost:5173 directamente. En modo prod (Tauri / portable)
    # FastAPI sirve los archivos generados por ``npm run build``.
    dist_dir = (Path(RESOURCES_DIR) / "web" / "dist").resolve()
    if dist_dir.is_dir() and (dist_dir / "index.html").is_file():
        assets_dir = dist_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/")
        async def root_spa() -> FileResponse:
            return FileResponse(str(dist_dir / "index.html"))

        # SPA fallback: cualquier ruta no /api/* ni /ws devuelve index.html
        # para que el router del frontend tome el control.
        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str) -> FileResponse:
            # Si es un archivo real bajo dist, lo servimos directo.
            candidate = (dist_dir / full_path).resolve()
            try:
                candidate.relative_to(dist_dir)
            except ValueError:
                return FileResponse(str(dist_dir / "index.html"))
            if candidate.is_file():
                return FileResponse(str(candidate))
            return FileResponse(str(dist_dir / "index.html"))

        log.info("Frontend estatico servido desde %s", dist_dir)
    else:
        log.info(
            "web/dist no presente: ejecuta `npm run build` en web/ para empaquetar el frontend"
        )

    return app
