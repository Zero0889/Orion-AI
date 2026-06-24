"""
actions.gog_auth — Gestión del CLI ``gog`` desde ORION
========================================================
Wrapper de alto nivel para que la UI pueda:

  * Listar cuentas autorizadas y qué servicios tienen cada una.
  * Listar el catálogo de servicios disponibles (gmail, calendar, …)
    con sus scopes y APIs.
  * Disparar un flow de autorización (``gog auth add``) en background:
    spawnea subprocess, monitorea stdout/stderr, deja un estado
    consultable y un endpoint para cancelar.

El gran win: el usuario nunca más tiene que abrir una terminal para
autorizar Google. La card en Ajustes (y los banners contextuales en
cada feature) le sirven todo en GUI.

Diseño del flow async
---------------------
gog auth add abre el browser, escucha en localhost para el callback,
recibe el code, lo intercambia, y termina. Si el usuario consiente,
el proceso retorna 0; si cancela o se vence el timeout, retorna != 0.

Nosotros lo lanzamos con ``subprocess.Popen`` (sin esperar) y un thread
monitor que:
  - lee stdout/stderr para extraer la URL OAuth (la imprime al inicio)
  - espera al proceso
  - actualiza el estado ``running → success | error | cancelled``

Mientras está running, GET ``/flow_status`` devuelve la URL al frontend
para mostrarla por si el browser no se abrió solo (raro pero pasa).
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from orion.core.logger import get_logger
import contextlib

log = get_logger("gog_auth")


# Servicios que precargamos por default cuando la UI no especifica nada.
# Match con la elección del usuario en la sesión de diseño.
DEFAULT_SERVICES = ["gmail", "classroom", "sheets", "drive", "docs", "slides", "contacts"]


def _gog_exe() -> Path:
    """Resuelve la ruta del binario gog priorizando tools/ user-writable
    y cayendo a la copia bundled del .exe. Mantenemos el alias por
    compat con tests existentes."""
    from orion.core.cli_installer import cli_path

    found = cli_path("gog")
    if found:
        return Path(found)
    # Si no se encontró, devolvemos el path "esperado" en BASE_DIR/tools
    # para que el error de _run_gog_json sea autoexplicativo.
    from orion.config import BASE_DIR

    return BASE_DIR / "tools" / "gog" / "gog.exe"


# ── Lectura sincrónica (rápida) ────────────────────────────────────────
def _run_gog_json(args: list[str], timeout: int = 15) -> dict:
    """Corre gog con --json --no-input. Devuelve dict parseado."""
    gog = _gog_exe()
    if not gog.exists():
        raise RuntimeError(f"gog no encontrado en {gog}")
    cmd = [str(gog), *args, "--json", "--no-input"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"gog timeout ({timeout}s)") from e
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:500]
        raise RuntimeError(f"gog exit {proc.returncode}: {err}")
    out = (proc.stdout or "").strip()
    if not out:
        return {}
    return json.loads(out)


def list_accounts() -> list[dict]:
    """Devuelve la lista de cuentas con sus servicios y scopes activos."""
    data = _run_gog_json(["auth", "list"])
    accs = data.get("accounts") or []
    if not isinstance(accs, list):
        return []
    # Normalizamos los campos que la UI necesita.
    out = []
    for a in accs:
        if not isinstance(a, dict):
            continue
        out.append(
            {
                "email": a.get("email") or "",
                "services": list(a.get("services") or []),
                "scopes": list(a.get("scopes") or []),
                "client": a.get("client") or "default",
                "created_at": a.get("created_at") or "",
            }
        )
    return out


def list_services() -> list[dict]:
    """Devuelve el catálogo de servicios disponibles en gog. Cada uno con
    scopes y APIs requeridas."""
    data = _run_gog_json(["auth", "services"])
    svcs = data.get("services") or []
    if not isinstance(svcs, list):
        return []
    out = []
    for s in svcs:
        if not isinstance(s, dict):
            continue
        out.append(
            {
                "service": s.get("service") or "",
                "scopes": list(s.get("scopes") or []),
                "apis": list(s.get("apis") or []),
                "user": bool(s.get("user", True)),
            }
        )
    return out


def account_has_services(email: str, required: list[str]) -> dict:
    """Helper para los GUARDS contextuales: dice si una cuenta concreta
    tiene autorizados los servicios pedidos. Devuelve:
      { "satisfied": bool, "missing": [...] }
    Si la cuenta no existe → satisfied=False, missing=todos."""
    target = email.strip().lower()
    if not target:
        return {"satisfied": False, "missing": list(required), "account_exists": False}
    try:
        accs = list_accounts()
    except Exception as e:
        log.warning("list_accounts falló: %s", e)
        return {
            "satisfied": False,
            "missing": list(required),
            "account_exists": False,
            "error": str(e),
        }
    account = next((a for a in accs if (a.get("email") or "").lower() == target), None)
    if not account:
        return {"satisfied": False, "missing": list(required), "account_exists": False}
    have = {s.lower() for s in account.get("services", [])}
    missing = [s for s in required if s.lower() not in have]
    return {
        "satisfied": len(missing) == 0,
        "missing": missing,
        "account_exists": True,
    }


# ── Flow asíncrono de gog auth add ─────────────────────────────────────
@dataclass
class AuthFlow:
    account: str
    services: list[str]
    status: str  # "running" | "success" | "error" | "cancelled"
    started_at: float
    finished_at: float | None = None
    auth_url: str | None = None
    message: str | None = None
    process: subprocess.Popen | None = field(default=None, repr=False)


_flow_lock = threading.Lock()
_current_flow: AuthFlow | None = None


# Regex para extraer la URL OAuth de la salida de gog. gog escribe algo
# como "Open this URL in your browser: https://accounts.google.com/..."
_URL_RX = re.compile(r"https://accounts\.google\.com\S+")


def get_flow_status() -> dict:
    """Snapshot del flow actual (idle si no hay nada en curso)."""
    with _flow_lock:
        f = _current_flow
        if f is None:
            return {"status": "idle"}
        return {
            "status": f.status,
            "account": f.account,
            "services": list(f.services),
            "started_at": f.started_at,
            "finished_at": f.finished_at,
            "auth_url": f.auth_url,
            "message": f.message,
        }


def start_auth(account: str, services: list[str] | None = None, force_consent: bool = True) -> dict:
    """Arranca el flow de autorización. Spawnea ``gog auth add``,
    devuelve el snapshot inicial. El thread monitor se encarga de
    actualizar el estado cuando termine."""
    global _current_flow
    account = (account or "").strip()
    if not account:
        raise ValueError("Falta el email de la cuenta")
    services = services or DEFAULT_SERVICES
    if not services:
        raise ValueError("Hay que pedir al menos un servicio")

    with _flow_lock:
        if _current_flow is not None and _current_flow.status == "running":
            raise RuntimeError("Ya hay una autorización en curso. Cancelala primero.")

        gog = _gog_exe()
        if not gog.exists():
            raise RuntimeError(f"gog no encontrado en {gog}")

        cmd = [
            str(gog),
            "auth",
            "add",
            account,
            "--services",
            ",".join(services),
            "--no-input",
        ]
        if force_consent:
            cmd.append("--force-consent")
        log.info("spawning: %s", " ".join(cmd))
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,  # line-buffered
            )
        except Exception as e:
            raise RuntimeError(f"no se pudo arrancar gog: {e}") from e

        _current_flow = AuthFlow(
            account=account,
            services=list(services),
            status="running",
            started_at=time.time(),
            process=proc,
        )

    threading.Thread(
        target=_monitor_flow,
        args=(_current_flow,),
        daemon=True,
        name="gog-auth-monitor",
    ).start()

    return get_flow_status()


def _monitor_flow(flow: AuthFlow) -> None:
    """Lee stdout línea por línea para sacar la URL, después espera
    al proceso y actualiza estado."""
    proc = flow.process
    if proc is None:
        return
    try:
        if proc.stdout:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                log.debug("gog: %s", line)
                if not flow.auth_url:
                    m = _URL_RX.search(line)
                    if m:
                        with _flow_lock:
                            flow.auth_url = m.group(0)
        rc = proc.wait(timeout=600)
    except subprocess.TimeoutExpired:
        with _flow_lock:
            flow.status = "error"
            flow.message = "timeout (10 min)"
            flow.finished_at = time.time()
        with contextlib.suppress(Exception):
            proc.kill()
        return
    except Exception as e:
        log.exception("monitor crasheó")
        with _flow_lock:
            flow.status = "error"
            flow.message = str(e)
            flow.finished_at = time.time()
        return

    with _flow_lock:
        flow.finished_at = time.time()
        if flow.status == "cancelled":
            return  # ya lo marcamos desde cancel_flow
        if rc == 0:
            flow.status = "success"
            flow.message = "Autorización completada"
        else:
            flow.status = "error"
            flow.message = f"gog exit {rc}"


def cancel_flow() -> dict:
    """Mata el subprocess en curso. Idempotente."""
    global _current_flow
    with _flow_lock:
        f = _current_flow
        if f is None or f.status != "running" or f.process is None:
            return get_flow_status()
        with contextlib.suppress(Exception):
            f.process.kill()
        f.status = "cancelled"
        f.message = "Cancelado por el usuario"
        f.finished_at = time.time()
        return {
            "status": f.status,
            "account": f.account,
            "services": list(f.services),
            "started_at": f.started_at,
            "finished_at": f.finished_at,
            "message": f.message,
        }


def reset_flow() -> dict:
    """Limpia el flow actual (después de un success/error confirmado por
    la UI). Sirve para volver al estado idle sin tener que reiniciar."""
    global _current_flow
    with _flow_lock:
        f = _current_flow
        if f and f.status in ("success", "error", "cancelled"):
            _current_flow = None
    return get_flow_status()
