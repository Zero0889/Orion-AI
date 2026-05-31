"""
server — Backend web (FastAPI + WebSocket) de O.R.I.O.N
========================================================
Paquete introducido en la Fase 0 de la migración a React/Tauri.

Estructura prevista
-------------------
- :mod:`server.event_bus` — OrionEventBus: reemplazo drop-in de OrionUI.
- (Fase 1) ``server.app``        — FastAPI app + montaje de /dist.
- (Fase 1) ``server.ws``         — hub de WebSockets.
- (Fase 1) ``server.routes.*``   — endpoints REST.

NO importar PyQt6 ni nada de :mod:`ui` / :mod:`ui_components` desde
este paquete. La regla está validada en :mod:`tests.test_event_bus_contract`.
"""
