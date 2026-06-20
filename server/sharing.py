"""
server.sharing — toggle "Compartir vía Tailscale" + middleware de IP filter
==========================================================================
El backend siempre escucha en ``0.0.0.0`` para que la red privada Tailscale
pueda llegar. Quién entra de verdad lo controla este módulo:

  • Si ``sharing_enabled = False``  → SOLO ``127.0.0.1`` pasa.
    Comportamiento idéntico al bind antiguo a localhost.
  • Si ``sharing_enabled = True``   → ``127.0.0.1`` + rango Tailscale
    (``100.64.0.0/10``, CGNAT reservado a Tailscale por el RFC 6598).
    Cualquier otra IP (LAN local, internet directo) recibe **403**.

El flag se persiste en ``config/sharing.json`` y se puede leer/escribir
desde la API (ver ``server.routes.settings``). También se expone el último
``tailscale_ip`` detectado para mostrarlo en la UI.
"""

from __future__ import annotations

import ipaddress
import json
import threading

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config import CONFIG_DIR

# ── Persistencia ────────────────────────────────────────────────────────────

SHARING_CONFIG_PATH = CONFIG_DIR / "sharing.json"

# Rango de IPs que Tailscale asigna a sus dispositivos (CGNAT).
_TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")
# Loopback siempre permitido (consola local, scripts en el mismo PC).
_LOOPBACK_NET = ipaddress.ip_network("127.0.0.0/8")

# Estado en memoria; thread-safe porque uvicorn puede atender varias
# corutinas concurrentes y, por seguridad, queremos lecturas consistentes.
_state_lock = threading.Lock()
_enabled = False


def _load_from_disk() -> bool:
    """Devuelve el flag persistido (default: False)."""
    try:
        raw = json.loads(SHARING_CONFIG_PATH.read_text(encoding="utf-8"))
        return bool(raw.get("enabled", False))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False


def _save_to_disk(enabled: bool) -> None:
    SHARING_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SHARING_CONFIG_PATH.write_text(
        json.dumps({"enabled": enabled}, indent=2),
        encoding="utf-8",
    )


def init_state() -> None:
    """Llamar al arrancar el backend. Carga el último estado guardado."""
    global _enabled
    with _state_lock:
        _enabled = _load_from_disk()


def get_sharing() -> bool:
    with _state_lock:
        return _enabled


def set_sharing(enabled: bool) -> bool:
    """Actualiza el flag y lo persiste. Devuelve el nuevo valor."""
    global _enabled
    with _state_lock:
        _enabled = bool(enabled)
        _save_to_disk(_enabled)
        return _enabled


# ── Detección de IP Tailscale para mostrar en la UI ─────────────────────────


def detect_tailscale_ip() -> str | None:
    """Recorre las interfaces de red y devuelve la primera IP del rango
    Tailscale, o None si no hay (no instalado, no conectado, etc.).
    """
    try:
        import psutil
    except ImportError:
        return None

    try:
        addrs = psutil.net_if_addrs()
    except Exception:
        return None

    for _iface, snic_list in addrs.items():
        for snic in snic_list:
            addr = getattr(snic, "address", "") or ""
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if ip in _TAILSCALE_NET:
                return str(ip)
    return None


# ── Middleware ──────────────────────────────────────────────────────────────


def _client_ip(request: Request) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Obtiene el IP de quien hace la petición. Starlette lo guarda en
    ``request.client`` (host, port)."""
    client = request.client
    if client is None or not client.host:
        return None
    try:
        return ipaddress.ip_address(client.host)
    except ValueError:
        return None


def _allowed(ip, sharing: bool) -> bool:
    if ip is None:
        # Si no podemos identificar la IP, denegamos por seguridad.
        return False
    if ip in _LOOPBACK_NET:
        return True
    if sharing and ip in _TAILSCALE_NET:
        return True
    return False


class SharingMiddleware:
    """ASGI middleware. Más simple que BaseHTTPMiddleware y evita
    overhead innecesario en cada request."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Construye un Request mínimo para reutilizar _client_ip
        # (en ASGI scope, el cliente está en scope["client"] = (host, port))
        client = scope.get("client")
        ip = None
        if client and client[0]:
            try:
                ip = ipaddress.ip_address(client[0])
            except ValueError:
                ip = None

        sharing = get_sharing()
        if _allowed(ip, sharing):
            await self.app(scope, receive, send)
            return

        # Bloqueamos: 403 para HTTP, close-code 4403 para websocket.
        if scope["type"] == "http":
            response = JSONResponse(
                {
                    "detail": "Acceso denegado. Tu IP no está en la lista permitida. "
                    "Activa el toggle 'Compartir vía Tailscale' en Ajustes para "
                    "permitir conexiones desde tu red privada Tailscale.",
                    "your_ip": str(ip) if ip else "desconocido",
                    "sharing": sharing,
                },
                status_code=403,
            )
            await response(scope, receive, send)
        else:  # websocket
            await send({"type": "websocket.close", "code": 4403})


def install(app: FastAPI) -> None:
    """Registra el middleware en la app FastAPI."""
    app.add_middleware(SharingMiddleware)
