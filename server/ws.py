"""
server.ws — Hub WebSocket de O.R.I.O.N
========================================
Un único endpoint ``/ws`` que:

  1. Acepta conexiones de clientes (React, Tauri WebView, etc.).
  2. Suscribe cada conexión al ``OrionEventBus``.
  3. Drena la ``_outbound_queue`` del bus desde **un solo task** que vive
     en el loop de uvicorn (Loop A) y hace fan-out a todos los clientes.
  4. Acepta comandos del cliente (text, interrupt, mute, …).

Patrón de concurrencia (informe pre-Fase 0, R-15/R-17):

  - **Productores** del bus (acciones, OrionLive, sensores IoT) llaman
    ``bus.publish(...)`` desde cualquier hilo/loop. Internamente eso
    usa ``loop_A.call_soon_threadsafe`` y deposita en la queue.
  - **Un único consumer** (``_drain_loop``) corre en Loop A y reparte a
    los WS suscritos. Si un cliente está lento, los demás no se ven
    afectados (el send es por cliente, con timeout y manejo de error).
  - **Comandos** del cliente se procesan **una sola vez** por mensaje
    (no se duplican entre clientes). El bus.submit_user_text() ya
    encapsula el salto al loop B (OrionLive).
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from core.logger import get_logger

log = get_logger("server.ws")

# Si un send tarda más que esto, asumimos que el cliente murió.
SEND_TIMEOUT_S = 2.0


# ============================================================================
#  Registro del endpoint en la app
# ============================================================================
def register_ws(app: FastAPI, bus: Any) -> None:
    """Registra el endpoint ``/ws`` en la app FastAPI y arranca el drain task."""

    # Set de clientes conectados (vive en el cierre del registro).
    clients: set[WebSocket] = set()
    clients_lock = asyncio.Lock()

    # ── Drain loop ────────────────────────────────────────────────────────
    # Una sola coroutine que consume bus._outbound_queue y reparte a todos.
    async def _drain_loop() -> None:
        log.info("WS drain loop iniciado")
        while True:
            q = bus._outbound_queue
            if q is None:
                # El bus aún no está conectado al loop (no debería pasar
                # con lifespan, pero por si acaso esperamos un poco).
                await asyncio.sleep(0.1)
                continue
            try:
                msg = await q.get()
            except RuntimeError:
                # Loop cerrándose
                break

            # Snapshot de clientes — si la lista cambia durante el broadcast,
            # los nuevos esperan al siguiente evento.
            async with clients_lock:
                snapshot = list(clients)

            if not snapshot:
                continue

            # Broadcast en paralelo con timeout y manejo de fallos individual.
            results = await asyncio.gather(
                *[_safe_send(ws, msg) for ws in snapshot],
                return_exceptions=True,
            )

            # Limpieza de clientes muertos
            dead = [ws for ws, ok in zip(snapshot, results) if ok is not True]
            if dead:
                async with clients_lock:
                    for ws in dead:
                        clients.discard(ws)

    async def _safe_send(ws: WebSocket, msg: dict) -> bool:
        try:
            if ws.client_state != WebSocketState.CONNECTED:
                return False
            await asyncio.wait_for(ws.send_json(msg), timeout=SEND_TIMEOUT_S)
            return True
        except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError):
            return False
        except Exception as e:
            log.debug("WS send error: %s", e)
            return False

    # El drain task se inicia/para desde el lifespan de server.app
    # (ver build_app). Exponemos las coroutines necesarias:
    async def _start_drain() -> None:
        app.state.ws_drain_task = asyncio.create_task(_drain_loop())

    async def _stop_drain() -> None:
        t = getattr(app.state, "ws_drain_task", None)
        if t is not None:
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass

    # Guardamos referencias para que app.py las pueda invocar.
    app.state.ws_start_drain = _start_drain
    app.state.ws_stop_drain  = _stop_drain

    # ── Endpoint /ws ──────────────────────────────────────────────────────
    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        async with clients_lock:
            clients.add(ws)
        log.info("WS cliente conectado (total=%d)", len(clients))

        # Saludo inicial con el estado actual para que el cliente pinte sin
        # esperar al siguiente evento.
        await _safe_send(ws, {
            "type": "state",
            "payload": {"value": getattr(bus, "_state", "ESCUCHANDO")},
        })
        await _safe_send(ws, {
            "type": "mute",
            "payload": {"value": bool(bus.muted)},
        })

        try:
            while True:
                msg = await ws.receive_json()
                await _handle_client_message(bus, msg)
        except WebSocketDisconnect:
            pass
        except Exception as e:
            log.debug("WS recv error: %s", e)
        finally:
            async with clients_lock:
                clients.discard(ws)
            log.info("WS cliente desconectado (total=%d)", len(clients))


# ============================================================================
#  Manejo de mensajes entrantes (cliente → bus)
# ============================================================================
async def _handle_client_message(bus: Any, msg: dict) -> None:
    """Procesa un mensaje recibido por el WS. Los comandos se aplican una
    sola vez (no se duplican por número de clientes)."""
    if not isinstance(msg, dict):
        return
    msg_type = msg.get("type")
    payload = msg.get("payload") or {}

    if msg_type == "text":
        text = (payload.get("text") or "").strip()
        if text:
            bus.submit_user_text(text)

    elif msg_type == "interrupt":
        bus.trigger_interrupt()

    elif msg_type == "mute":
        bus.muted = bool(payload.get("value", False))

    elif msg_type == "file.attach":
        path = payload.get("path")
        if path:
            bus.current_file = path

    else:
        log.debug("WS mensaje ignorado: %s", msg_type)
