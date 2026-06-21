"""
server.routes.files — Drop-zone web (Fase 4)
=============================================
Endpoints:
  POST   /api/files/upload    multipart → guarda en uploads/ y setea
                               bus.current_file
  GET    /api/files/current   → { path, name, size, exists } | { current: None }
  DELETE /api/files/current   → limpia bus.current_file

Diseño
------
- Los archivos se guardan en :data:`UPLOADS_DIR` (por defecto
  ``<BASE_DIR>/uploads/``) con nombre ``<timestamp>_<original>``
  saneado para evitar colisiones y path-traversal.
- Al subir, ``bus.current_file = abs_path`` dispara el evento
  ``file.attached`` en el WS (definido en el setter del bus).
- ``main.OrionLive`` ya lee ``ui.current_file`` antes de invocar
  ``file_processor`` y ``google_drive``, así que los archivos subidos
  desde web son tratados igual que los arrastrados a la UI Qt.
- Cap de tamaño defensivo (50 MB) — el ``file_processor`` ya valida
  el tipo cuando ejecuta la acción.

Seguridad
---------
- Nombre saneado: solo ``[A-Za-z0-9._-]``, longitud máxima 120.
- Path-traversal imposible (descartamos ``/`` y ``\\`` del nombre
  original).
- ``DELETE /current`` solo limpia el puntero, no borra el archivo del
  disco (decisión: el usuario puede querer reutilizarlo desde la
  UI Qt).
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from orion.config import UPLOADS_DIR
from orion.core.logger import get_logger

log = get_logger("server.routes.files")
router = APIRouter()


MAX_BYTES = 50 * 1024 * 1024  # 50 MB
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _ensure_uploads_dir() -> Path:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOADS_DIR


def _safe_name(original: str | None) -> str:
    """Devuelve un nombre seguro para guardar en uploads/."""
    name = (original or "file").split("/")[-1].split("\\")[-1]
    name = _SAFE_NAME.sub("_", name) or "file"
    return name[-120:]


@router.post("/upload", status_code=201)
async def upload_file(request: Request, file: UploadFile = File(...)) -> dict:
    """Sube un archivo y lo deja como ``current_file`` del bus."""
    uploads = _ensure_uploads_dir()
    safe = _safe_name(file.filename)
    final = uploads / f"{int(time.time() * 1000)}_{safe}"

    # Stream a disco con cap de tamaño defensivo.
    written = 0
    try:
        with final.open("wb") as fout:
            while True:
                chunk = await file.read(1024 * 1024)  # 1 MB
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_BYTES:
                    fout.close()
                    final.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"Archivo demasiado grande (> {MAX_BYTES // (1024 * 1024)} MB)",
                    )
                fout.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        # Limpia si quedó algo a medias.
        final.unlink(missing_ok=True)
        log.error("Upload falló: %s", e)
        raise HTTPException(status_code=500, detail=f"No se pudo guardar: {e}") from e
    finally:
        await file.close()

    abs_path = str(final.resolve())
    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        # El setter del bus emite file.attached automáticamente.
        try:
            bus.current_file = abs_path
        except Exception as e:
            log.warning("bus.current_file falló: %s", e)

    log.info("Archivo subido: %s (%d bytes)", final.name, written)
    return {
        "ok": True,
        "path": abs_path,
        "name": final.name,
        "original": file.filename or "",
        "size": written,
    }


@router.get("/current")
async def get_current_file(request: Request) -> dict:
    bus = getattr(request.app.state, "bus", None)
    path = getattr(bus, "current_file", None) if bus else None
    if not path:
        return {"current": None}
    p = Path(path)
    return {
        "current": {
            "path": str(p),
            "name": p.name,
            "size": p.stat().st_size if p.exists() else None,
            "exists": p.exists(),
        }
    }


@router.delete("/current", status_code=204)
async def clear_current_file(request: Request) -> None:
    bus = getattr(request.app.state, "bus", None)
    if bus is None:
        return
    # Limpiar; el setter del bus emitirá file.attached con path null
    # (ver server.event_bus.OrionEventBus.current_file setter).
    try:
        bus.current_file = None
    except Exception as e:
        log.warning("clear current_file falló: %s", e)
