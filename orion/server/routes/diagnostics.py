"""
server.routes.diagnostics — Panel diagnostico para usuarios finales
====================================================================
Endpoints que el frontend usa para que un usuario no-dev pueda ver:
  - donde estan los archivos de config / data / logs en su PC
  - el tail del log actual con highlight de WARN/ERROR
  - info basica del runtime (Python, OS, versiones)

GET /api/diagnostics/info     -> paths + versiones
GET /api/diagnostics/log/tail -> ultimos N lineas del log activo

Pensados para que reemplacen al "tengo que abrir el CMD" — el usuario
abre el panel Diagnostico y ve todo lo que necesita para reportar un
problema o entender un fallo.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from orion.config import (
    API_CONFIG_PATH,
    BASE_DIR,
    CONFIG_DIR,
    DATA_DIR,
    RESOURCES_DIR,
)

router = APIRouter()


# El logger guarda en BASE_DIR/logs/orion.log con rotacion. La ruta no
# esta exportada en orion.config porque hoy solo el logger la conoce —
# la replicamos aca con el mismo calculo para evitar acoplar el modulo
# de logging a un endpoint.
def _log_dir() -> Path:
    return BASE_DIR / "logs"


def _active_log_file() -> Path:
    return _log_dir() / "orion.log"


class DiagnosticsInfo(BaseModel):
    base_dir: str = Field(..., description="Raiz user-writable (APPDATA en prod).")
    resources_dir: str = Field(..., description="Raiz read-only (assets bundled en prod).")
    config_dir: str
    data_dir: str
    api_keys_path: str
    log_path: str
    log_dir: str
    python_version: str
    platform: str
    frozen: bool
    sys_executable: str


class LogTailResult(BaseModel):
    path: str
    exists: bool
    size_bytes: int
    lines: list[str]
    truncated: bool = Field(
        ..., description="True si pedimos mas lineas de las que el archivo tiene."
    )


@router.get("/info", response_model=DiagnosticsInfo)
def get_info() -> DiagnosticsInfo:
    log_path = _active_log_file()
    return DiagnosticsInfo(
        base_dir=str(BASE_DIR),
        resources_dir=str(RESOURCES_DIR),
        config_dir=str(CONFIG_DIR),
        data_dir=str(DATA_DIR),
        api_keys_path=str(API_CONFIG_PATH),
        log_path=str(log_path),
        log_dir=str(_log_dir()),
        python_version=platform.python_version(),
        platform=f"{platform.system()} {platform.release()} ({platform.machine()})",
        frozen=bool(getattr(sys, "frozen", False)),
        sys_executable=sys.executable,
    )


@router.get("/log/tail", response_model=LogTailResult)
def log_tail(lines: int = 200) -> LogTailResult:
    """Devuelve las ultimas ``lines`` lineas del log activo.

    Cap a 5000 lineas para evitar abusos accidentales (un panel que se
    abre y cierra cada segundo no debe poder DoS-ar al backend leyendo
    millones de bytes).
    """
    if lines < 1 or lines > 5000:
        raise HTTPException(400, "El parametro `lines` debe estar entre 1 y 5000.")

    path = _active_log_file()
    if not path.exists():
        return LogTailResult(path=str(path), exists=False, size_bytes=0, lines=[], truncated=False)

    size = path.stat().st_size

    # Para archivos chicos, leer todo es mas simple que reverse-buffer.
    # 5 MB con rotacion suele ser manejable.
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise HTTPException(500, f"No pude leer {path}: {e}") from e

    all_lines = content.splitlines()
    truncated = len(all_lines) > lines
    tail = all_lines[-lines:]

    return LogTailResult(
        path=str(path),
        exists=True,
        size_bytes=size,
        lines=tail,
        truncated=truncated,
    )


@router.post("/log/open-folder")
def open_log_folder() -> dict:
    """Abre la carpeta de logs en el explorador del sistema.

    Solo tiene efecto en el host local — si el usuario abrio Orion via
    Tailscale desde otra PC, esto correra en la maquina del servidor
    (donde uvicorn corre), no en la del cliente. Pero el 99% de los
    usuarios usan localhost, asi que el trade-off vale la pena.
    """
    folder = _log_dir()
    folder.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform == "win32":
            os.startfile(str(folder))
        elif sys.platform == "darwin":
            import subprocess

            subprocess.Popen(["open", str(folder)])
        else:
            import subprocess

            subprocess.Popen(["xdg-open", str(folder)])
    except Exception as e:
        raise HTTPException(500, f"No pude abrir {folder}: {e}") from e
    return {"ok": True, "path": str(folder)}
