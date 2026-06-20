"""
scripts/dump_openapi.py — Volcado del schema OpenAPI a JSON.

Para qué: el frontend usa ``openapi-typescript`` para generar tipos TS
desde este JSON. Ejecutar ``npm run gen:api`` en ``web/`` corre este
script y después convierte el JSON a ``web/src/api/generated.ts``.

Output: ``web/src/api/openapi.json`` (commiteado al repo para que un dev
de frontend no necesite Python instalado para regenerar tipos).

Importante: no arranca uvicorn ni el WS hub. Sólo construye la app
FastAPI in-memory para que ``app.openapi()`` resuelva el schema.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Permite ejecutar `python scripts/dump_openapi.py` desde cualquier cwd.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from server.app import build_app
from server.event_bus import OrionEventBus

OUTPUT_PATH = _REPO_ROOT / "web" / "src" / "api" / "openapi.json"


def main() -> int:
    app = build_app(OrionEventBus())
    schema = app.openapi()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # `sort_keys=True` para que el output sea determinista entre runs.
    # Sin esto, la primera regeneración tras un cambio menor mete diff
    # de orden por todo el archivo y CI no puede detectar drift real.
    # `newline="\n"` fuerza LF — sin esto, en Windows el `write_text`
    # convierte `\n` → `\r\n` y CI Linux ve drift artificial.
    payload = json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="\n") as f:
        f.write(payload)

    paths = len(schema.get("paths", {}))
    schemas = len(schema.get("components", {}).get("schemas", {}))
    print(
        f"OpenAPI dumped: {OUTPUT_PATH.relative_to(_REPO_ROOT)} ({paths} paths, {schemas} schemas)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
