"""
server.app — App FastAPI de O.R.I.O.N
======================================
Punto de entrada del backend web (Fase 1). En esta fase:

  - REST de **solo lectura** sobre los JSON existentes.
  - WebSocket ``/ws`` que retransmite eventos del :class:`OrionEventBus`.
  - La UI Qt sigue corriendo en paralelo (Loop A vs. Loop B en el
    informe de auditoría).

Patrón de uso desde ``main.py``::

    from server.app import build_app
    from server.event_bus import OrionEventBus

    bus = OrionEventBus()
    app = build_app(bus)
    # uvicorn.run(app, host="127.0.0.1", port=8765)

La función :func:`build_app` recibe el bus como dependencia para que las
rutas que necesiten publicar eventos puedan usarlo. No hay variables
globales — la app es siempre creada con el bus inyectado.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import BASE_DIR
from core.logger import get_logger

log = get_logger("server.app")

DEFAULT_HOST = "127.0.0.1"
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
        from server.telemetry import run as run_telemetry
        app.state.telemetry_task = asyncio.create_task(run_telemetry(bus))

        try:
            yield
        finally:
            t = getattr(app.state, "telemetry_task", None)
            if t is not None:
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass

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

    # CORS: el frontend React (Vite dev en :5173 por defecto) debe poder
    # llamar al backend en :8765. Sin esto, fetch desde otro origen falla.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            # Cuando empaquetemos con Tauri, el WebView carga desde
            # tauri://localhost — la añadiremos en su momento.
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Endpoint de salud (Fase 1, sin auth) ─────────────────────────────
    @app.get("/api/health")
    async def health() -> JSONResponse:
        return JSONResponse({
            "ok": True,
            "service": "orion-backend",
            "version": app.version,
            "state": getattr(bus, "_state", "ESCUCHANDO"),
            "muted": bool(bus.muted),
        })

    # ── Routers ───────────────────────────────────────────────────────────
    from server.routes import (
        agent, conversations, iot, memory, notes,
        settings as settings_route,
    )
    app.include_router(memory.router,            prefix="/api/memory",        tags=["memory"])
    app.include_router(notes.router,             prefix="/api/notes",         tags=["notes"])
    app.include_router(conversations.router,     prefix="/api/conversations", tags=["conversations"])
    app.include_router(settings_route.router,    prefix="/api/settings",      tags=["settings"])
    app.include_router(agent.router,             prefix="/api/agent",         tags=["agent"])
    app.include_router(iot.router,               prefix="/api/iot",           tags=["iot"])

    # ── WebSocket hub ────────────────────────────────────────────────────
    from server.ws import register_ws
    register_ws(app, bus)

    # ── Frontend estático (Fase 2: si web/dist existe, se sirve aquí) ────
    # En modo dev (Vite en :5173) este bloque no aplica — el usuario abre
    # http://localhost:5173 directamente. En modo prod (Tauri / portable)
    # FastAPI sirve los archivos generados por ``npm run build``.
    dist_dir = (Path(BASE_DIR) / "web" / "dist").resolve()
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
        log.info("web/dist no presente: ejecuta `npm run build` en web/ para empaquetar el frontend")

    return app
