"""
server.routes.notebooklm — Endpoints para gestionar el login de NotebookLM.

NotebookLM (Google) invalida la sesión local de notebooklm-py cada
ciertas semanas/meses. Cuando expira, la única forma de renovar es
correr `notebooklm.exe login`, que abre Chromium para que el usuario
inicie sesión con Google. Estos endpoints exponen ese flujo desde la UI:

  GET  /api/notebooklm/status — estado actual (installed, session, in_progress)
  POST /api/notebooklm/login  — spawnea `notebooklm login` en background

El subprocess se ejecuta LOCALMENTE en la máquina donde corre Orion
(necesita abrir un browser). No funciona vía Tailscale desde otra PC.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from orion.core.logger import get_logger
import contextlib

log = get_logger("server.routes.notebooklm")
router = APIRouter()


# ── Estado in-memory del subprocess de login ────────────────────────────
# Solo permitimos UN login a la vez. El monitor thread actualiza el
# estado cuando el proceso termina.

_state_lock = threading.Lock()
_state: dict[str, Any] = {
    "status": "idle",  # idle | running | success | failed
    "message": "",
    "started_at": 0.0,
    "finished_at": 0.0,
    "_proc": None,  # subprocess.Popen | None — no se serializa
}


def _public_state() -> dict[str, Any]:
    """Snapshot sin el handler del proc (no se serializa por JSON)."""
    with _state_lock:
        return {
            "status": _state["status"],
            "message": _state["message"],
            "started_at": _state["started_at"],
            "finished_at": _state["finished_at"],
            "elapsed": (
                (_state["finished_at"] or time.time()) - _state["started_at"]
                if _state["started_at"]
                else 0.0
            ),
        }


def _has_session() -> bool:
    """True si existe el storage_state.json de notebooklm-py."""
    try:
        from notebooklm.paths import get_storage_path

        return get_storage_path().exists()
    except Exception:
        return False


def _notebooklm_cli_path() -> Path | None:
    """Resuelve la ruta a notebooklm.exe (Windows) o notebooklm (Linux).
    Prioriza el venv del proyecto."""
    # Venv del proyecto primero
    project_root = Path(__file__).resolve().parents[2]
    candidates = [
        project_root / ".venv" / "Scripts" / "notebooklm.exe",
        project_root / ".venv" / "bin" / "notebooklm",
    ]
    for c in candidates:
        if c.exists():
            return c
    # Fallback al PATH
    found = shutil.which("notebooklm")
    return Path(found) if found else None


def _monitor_login(proc: subprocess.Popen) -> None:
    """Espera al subprocess y actualiza el state al terminar.
    Corre en thread daemon."""
    try:
        proc.wait(timeout=600)  # 10 min máximo de paciencia
        rc = proc.returncode
        with _state_lock:
            _state["_proc"] = None
            _state["finished_at"] = time.time()
            if rc == 0 and _has_session():
                _state["status"] = "success"
                _state["message"] = "Sesión guardada correctamente."
            elif rc == 0:
                _state["status"] = "failed"
                _state["message"] = "El CLI terminó OK pero no encontré la sesión guardada."
            else:
                # Lee stderr para mensaje útil
                err = ""
                with contextlib.suppress(Exception):
                    err = (proc.stderr.read() or "")[:200] if proc.stderr else ""
                _state["status"] = "failed"
                _state["message"] = f"Login falló (exit {rc}). {err}".strip()
    except subprocess.TimeoutExpired:
        with contextlib.suppress(Exception):
            proc.kill()
        with _state_lock:
            _state["_proc"] = None
            _state["status"] = "failed"
            _state["message"] = "Timeout: el login tardó más de 10 minutos."
            _state["finished_at"] = time.time()
    except Exception as e:
        with _state_lock:
            _state["_proc"] = None
            _state["status"] = "failed"
            _state["message"] = f"Error inesperado: {e}"
            _state["finished_at"] = time.time()


# ── Endpoints ───────────────────────────────────────────────────────────


@router.get("/status")
def get_status() -> dict[str, Any]:
    """Estado completo: instalación, sesión, y último intento de login."""
    cli = _notebooklm_cli_path()
    return {
        "installed": cli is not None,
        "cli_path": str(cli) if cli else None,
        "has_session": _has_session(),
        "login": _public_state(),
    }


@router.post("/login", status_code=202)
def start_login() -> dict[str, Any]:
    """Spawnea `notebooklm login` en background. Devuelve 409 si ya hay
    un login en progreso. La UI debe pollear /status hasta que
    ``login.status`` pase de 'running' a 'success' o 'failed'."""

    cli = _notebooklm_cli_path()
    if cli is None:
        raise HTTPException(
            status_code=500,
            detail=(
                "notebooklm CLI no encontrado. Instalá con: "
                '.venv\\Scripts\\pip.exe install "notebooklm-py[browser]"'
            ),
        )

    with _state_lock:
        if _state["status"] == "running":
            raise HTTPException(
                status_code=409,
                detail="Ya hay un login en progreso. Esperá a que termine.",
            )

        try:
            # CREATE_NEW_PROCESS_GROUP en Windows para que el subprocess
            # tenga su propia ventana de consola y Chromium pueda
            # abrirse sin que el cierre del padre lo arrastre.
            creationflags = 0
            with contextlib.suppress(AttributeError):  # Linux/Mac no tienen este flag
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

            proc = subprocess.Popen(
                [str(cli), "login"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
            )
        except OSError as e:
            raise HTTPException(500, f"No pude lanzar el CLI: {e}") from e

        _state["status"] = "running"
        _state["message"] = "Esperando que termines de iniciar sesión en Chromium…"
        _state["started_at"] = time.time()
        _state["finished_at"] = 0.0
        _state["_proc"] = proc

    log.info("NotebookLM login iniciado (PID %s)", proc.pid)
    threading.Thread(
        target=_monitor_login,
        args=(proc,),
        daemon=True,
        name="NotebookLMLoginMonitor",
    ).start()

    return {"ok": True, "pid": proc.pid, "message": "Login iniciado."}


@router.post("/cancel")
def cancel_login() -> dict[str, Any]:
    """Mata el subprocess de login si está corriendo."""
    with _state_lock:
        proc = _state.get("_proc")
        if proc is None or _state["status"] != "running":
            return {"ok": False, "message": "No hay login en progreso."}
        try:
            proc.kill()
        except Exception as e:
            log.warning("Kill del login falló: %s", e)
        _state["status"] = "failed"
        _state["message"] = "Cancelado por el usuario."
        _state["finished_at"] = time.time()
        _state["_proc"] = None
    return {"ok": True, "message": "Login cancelado."}
