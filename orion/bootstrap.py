"""orion.bootstrap — Setup del proceso + entry point ``main()``.

Responsable de:
  - Configurar stdout/stderr en UTF-8 (Windows fix para emojis).
  - Extender PATH con tools/ para subprocesses (gog, etc.).
  - Registrar las builtin tools en el ``ToolRegistry``.
  - Construir el servidor uvicorn (backend FastAPI).
  - Spawnear ``OrionLive`` en un thread daemon.
  - Bloquear el main thread con uvicorn hasta Ctrl+C.

``python -m orion`` arranca acá (vía ``orion/__main__.py`` thin wrapper).
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading

# ── UTF-8 stdout/stderr (Windows fix) ────────────────────────────────────
# La consola por defecto en Windows decodifica con cp1252, que NO sabe
# leer la mayoría de emojis ni caracteres unicode (⏸, —, ✅, etc). Hay
# decenas de print() con emojis dispersos por el codebase (browser,
# code_helper, iot, etc); cuando alguno se ejecuta bajo un request HTTP,
# UnicodeEncodeError revienta el handler entero y el cliente recibe 500.
# Reconfigurar acá una sola vez resuelve TODOS de un saque, sin tocar
# cada print individual. `errors="replace"` evita que un caracter raro
# de un futuro print rompa nada (lo cambia por "?").
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    # En entornos donde stdout no soporta reconfigure (pythonw, sidecar
    # sin consola), no es bloqueante — los print() simplemente no salen.
    pass

from orion.config import get_api_key
from orion.core.logger import get_logger
from orion.core.tools_bootstrap import register_builtin_tools

# Registramos las builtin tools al importar bootstrap. Esto debe pasar
# ANTES de cualquier construcción de OrionLive (que lee el ToolRegistry
# en su __init__).
register_builtin_tools()

log = get_logger("orion.bootstrap")

# ── PATH para subprocesses (Windows fix) ────────────────────────────────
# En Windows, subprocess.run([bin, ...], env={...PATH...}) NO usa el PATH del
# env kwarg — CreateProcessW resuelve binarios consultando el PATH del proceso
# padre. Por eso inyectamos tools/<x>/ a os.environ una sola vez al arrancar,
# así los subprocesses (gog, etc.) heredan el PATH correctamente sin tocar
# nada más.
try:
    from orion.core.cli_installer import extra_path_dirs as _extra_path_dirs

    _extras = _extra_path_dirs()
    if _extras:
        _cur = os.environ.get("PATH", "")
        _missing = [d for d in _extras if d not in _cur.split(os.pathsep)]
        if _missing:
            os.environ["PATH"] = os.pathsep.join(_missing + [_cur])
            log.info("PATH extendido con tools/: %s", _missing)
except Exception as _e:
    log.warning("No pude extender PATH con tools/: %s", _e)


def _build_uvicorn_server(bus):
    """Devuelve un ``uvicorn.Server`` listo para servir el backend Orion."""
    import uvicorn

    from orion.server.app import DEFAULT_HOST, DEFAULT_PORT, build_app

    app = build_app(bus)
    config = uvicorn.Config(
        app,
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        log_level="warning",
        access_log=False,
        loop="asyncio",
        lifespan="on",
    )
    return uvicorn.Server(config), DEFAULT_HOST, DEFAULT_PORT


def _spawn_orion_live(bus) -> None:
    """Arranca ``OrionLive`` en un thread daemon usando el bus como player."""
    # Import lazy: OrionLive arrastra sounddevice/google-genai; importarlo
    # acá adentro permite que tests que sólo tocan bootstrap (sin runtime)
    # se ejecuten sin esas deps cargadas al import del módulo.
    from orion.runtime import OrionLive

    def runner():
        bus.wait_for_api_key()
        orion = OrionLive(bus)

        def _attach_live_loop():
            import time

            for _ in range(100):
                if getattr(orion, "_loop", None) is not None:
                    bus.set_live_loop(orion._loop)
                    return
                time.sleep(0.05)

        threading.Thread(target=_attach_live_loop, daemon=True).start()

        try:
            asyncio.run(orion.run())
        except KeyboardInterrupt:
            log.info("Cerrando ORION...")

    threading.Thread(target=runner, daemon=True, name="OrionLiveRunner").start()


def main() -> None:
    """Arranca el backend FastAPI + frontend React.

    El main thread lo bloquea uvicorn; ``OrionLive`` corre en un thread
    daemon. El wizard de API key se atiende desde el frontend vía
    ``POST /api/settings/api_key``.
    """
    from orion.server.event_bus import OrionEventBus

    log.info("Iniciando Orion (modo web)")
    bus = OrionEventBus()

    # Si la API key ya está configurada (env o archivo), desbloquea el
    # wait_for_api_key() del bus de inmediato. Si no, el frontend mostrará
    # el wizard y POST /api/settings/api_key llamará a bus.mark_ready().
    try:
        get_api_key()
        bus.mark_ready()
    except RuntimeError:
        log.info("API key no configurada — esperando wizard web")
    except Exception:
        pass

    _spawn_orion_live(bus)

    server, host, port = _build_uvicorn_server(bus)
    # `host` puede ser "0.0.0.0" (bindea todas las interfaces para que
    # Tailscale alcance), pero los navegadores no pueden navegar a esa
    # dirección. Para el log y el auto-open usamos siempre 127.0.0.1.
    browse_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{browse_host}:{port}"
    log.info("Frontend disponible en %s", url)
    if host in ("0.0.0.0", "::"):
        log.info("Backend escucha en %s:%d (Tailscale + localhost)", host, port)

    # Abrir el navegador automáticamente (mejor primera experiencia).
    # En entornos sin GUI (Tauri / sidecar / servidor) esto es no-op.
    if not os.environ.get("ORION_NO_BROWSER"):
        try:
            import webbrowser

            webbrowser.open(url, new=2)
        except Exception:
            pass

    # uvicorn bloquea el main thread hasta Ctrl+C
    try:
        asyncio.run(server.serve())
    except KeyboardInterrupt:
        log.info("Cerrando ORION...")


__all__ = ["_build_uvicorn_server", "_spawn_orion_live", "main"]
