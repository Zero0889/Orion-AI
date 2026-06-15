"""
server.routes.circuit — Endpoints para generar netlists desde imágenes.

Pipeline simple:
  POST /api/circuit/from-image  — recibe {image_path, outputs?, output_dir?}
                                   y llama actions.circuit_from_image.
  GET  /api/circuit/list        — lista los .cir y .kicad_sch ya generados
                                   en uploads/circuits/ y uploads/.

La acción real vive en :mod:`actions.circuit_from_image`. Este router solo
hace la validación de payload, llama el handler en un executor (porque la
llamada a Gemini es bloqueante) y formatea la respuesta JSON.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import BASE_DIR
from core.logger import get_logger

log = get_logger("server.routes.circuit")
router = APIRouter()


# ── Modelos de request ─────────────────────────────────────────────────

class FromImageRequest(BaseModel):
    image_path: str = Field(..., description="Ruta absoluta a la imagen del circuito.")
    outputs:    list[str] | None = Field(default=None, description="Lista con 'spice' y/o 'kicad'. Default: ambos.")
    output_dir: str | None = Field(default=None, description="Carpeta destino. Default: la carpeta de la imagen.")


class ProteusAutodrawRequest(BaseModel):
    cir_path:        str = Field(..., description="Ruta absoluta al .cir generado previamente.")
    countdown:       int | None = Field(default=3, description="Segundos antes de empezar (para enfocar Proteus).")
    place_in_canvas: bool | None = Field(default=True, description="Si True, coloca los componentes en el canvas en una grilla.")
    cols:            int | None = Field(default=3, description="Columnas de la grilla.")


# ── Helpers ────────────────────────────────────────────────────────────

_OUTPUT_EXTS = (".cir", ".kicad_sch")


def _parse_spice_path_from_result(result: str) -> dict[str, str]:
    """Extrae las rutas SPICE/KiCad del string que devuelve la action.

    La action devuelve un mensaje como
    ``Detecté "X" con 5 componentes. SPICE: C:\\... KiCad: C:\\...``.
    Parsearlo es más simple que cambiar la firma del handler — y mantiene
    la action invocable por el agente (que solo lee el string).
    """
    out: dict[str, str] = {}
    m = re.search(r"SPICE:\s*(\S.*?\.cir)", result)
    if m:
        out["spice_path"] = m.group(1).strip()
    m = re.search(r"KiCad:\s*(\S.*?\.kicad_sch)", result)
    if m:
        out["kicad_path"] = m.group(1).strip()
    return out


# ── Endpoints ──────────────────────────────────────────────────────────

@router.post("/from-image")
async def from_image(req: FromImageRequest) -> dict[str, Any]:
    """Genera SPICE + KiCad a partir de una imagen ya subida al servidor.

    El cliente debe haber subido la imagen primero vía ``POST /api/files/upload``
    y reusar la ruta devuelta. La conversión real se ejecuta en un thread
    porque la llamada a Gemini es bloqueante (~5-10s).
    """
    image_path = Path(req.image_path)
    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(status_code=400, detail=f"Imagen no encontrada: {req.image_path}")

    params: dict[str, Any] = {"image_path": str(image_path)}
    if req.outputs:
        params["outputs"] = req.outputs
    if req.output_dir:
        params["output_dir"] = req.output_dir

    def _run() -> str:
        from actions.circuit_from_image import circuit_from_image
        return circuit_from_image(params)

    try:
        result = await asyncio.get_running_loop().run_in_executor(None, _run)
    except Exception as e:
        log.exception("circuit_from_image crashed")
        raise HTTPException(status_code=500, detail=f"Generación falló: {e}") from e

    # Si el handler devolvió error semántico (string que empieza con texto
    # de error conocido), lo devolvemos como 422 — fue válido procesarlo,
    # pero no produjo nada útil.
    lower = result.lower()
    if (
        "no detecté un circuito" in lower
        or "imagen no encontrada" in lower
        or "falta el parámetro" in lower
        or "falló:" in lower
    ):
        raise HTTPException(status_code=422, detail=result)

    paths = _parse_spice_path_from_result(result)
    return {
        "ok": True,
        "summary": result,
        **paths,
    }


@router.get("/list")
def list_circuits() -> dict[str, Any]:
    """Lista los .cir y .kicad_sch generados.

    Busca recursivamente en ``uploads/`` y en ``BASE_DIR/uploads/`` que es
    donde la action escribe por defecto si la imagen estaba ahí.
    """
    roots = [
        BASE_DIR / "uploads",
        Path(BASE_DIR) / "uploads" / "circuits",
    ]
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _OUTPUT_EXTS:
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            try:
                stat = path.stat()
            except OSError:
                continue
            items.append({
                "name":     path.name,
                "path":     str(path),
                "kind":     "spice" if path.suffix.lower() == ".cir" else "kicad",
                "size":     stat.st_size,
                "modified": stat.st_mtime,
            })

    items.sort(key=lambda x: x["modified"], reverse=True)
    return {"items": items}


@router.post("/proteus-autodraw")
async def proteus_autodraw_route(req: ProteusAutodrawRequest) -> dict[str, Any]:
    """Lanza la automatización de Proteus. El usuario debe tener Proteus
    abierto en Schematic Capture y enfocado antes del fin del countdown.
    """
    cir_path = Path(req.cir_path)
    if not cir_path.exists() or not cir_path.is_file():
        raise HTTPException(status_code=400, detail=f".cir no encontrado: {req.cir_path}")
    if cir_path.suffix.lower() != ".cir":
        raise HTTPException(status_code=400, detail="El archivo debe ser .cir")

    params: dict[str, Any] = {
        "cir_path":        str(cir_path),
        "countdown":       req.countdown or 3,
        "place_in_canvas": True if req.place_in_canvas is None else req.place_in_canvas,
        "cols":            req.cols or 3,
    }

    def _run() -> str:
        from actions.proteus_autodraw import proteus_autodraw
        return proteus_autodraw(params)

    try:
        result = await asyncio.get_running_loop().run_in_executor(None, _run)
    except Exception as e:
        log.exception("proteus_autodraw crashed")
        raise HTTPException(status_code=500, detail=f"Automatización falló: {e}") from e

    if "no está instalado" in result or "no encontrado" in result.lower() or "abortada" in result.lower():
        # Devolvemos 200 con ok=false para que la UI muestre el mensaje
        # como warning en vez de error rojo.
        return {"ok": False, "summary": result}
    return {"ok": True, "summary": result}


@router.delete("/item")
def delete_item(path: str) -> dict[str, Any]:
    """Elimina un .cir o .kicad_sch generado. Solo acepta archivos dentro de uploads/."""
    p = Path(path).resolve()
    uploads = (BASE_DIR / "uploads").resolve()
    try:
        p.relative_to(uploads)
    except ValueError:
        raise HTTPException(status_code=400, detail="Solo se pueden borrar archivos dentro de uploads/.")
    if p.suffix.lower() not in _OUTPUT_EXTS:
        raise HTTPException(status_code=400, detail="Solo se pueden borrar .cir o .kicad_sch.")
    if not p.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    try:
        p.unlink()
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"No se pudo borrar: {e}") from e
    return {"ok": True}
