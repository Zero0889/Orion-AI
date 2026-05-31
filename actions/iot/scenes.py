"""
actions.iot.scenes — Escenas: agrupar varias acciones IoT
==========================================================
Una escena es una lista de acciones (cada una sobre un dispositivo) que
se ejecutan en orden. Ejemplos típicos:

```json
"scenes": {
  "modo_pelicula": {
    "name": "Modo Película",
    "actions": [
      {"device": "foco_1",   "command": "off"},
      {"device": "foco_rgb", "command": "rgb", "color": [50, 0, 100]},
      {"device": "foco_rgb", "command": "dim", "value": 20}
    ]
  },
  "buenos_dias": {
    "name": "Buenos días",
    "actions": [
      {"device": "foco_1", "command": "on"},
      {"device": "foco_2", "command": "on"}
    ]
  }
}
```

La ejecución se delega al orquestador (``control.py``) que ya sabe cómo
validar capabilities y enrutar al transport adecuado.
"""

from __future__ import annotations

from typing import Callable, Optional

from .config import IoTConfig


# Tipo del callback que dispara una acción individual.
# Recibe (device_id, command, **kwargs) y devuelve un mensaje str.
ActionRunner = Callable[..., str]


def list_scenes(cfg: IoTConfig) -> list[dict]:
    """Devuelve lista resumida ``[{"id": ..., "name": ..., "steps": N}, ...]``."""
    out = []
    for scene_id, scene in cfg.scenes.items():
        out.append({
            "id":    scene_id,
            "name":  scene.get("name", scene_id),
            "steps": len(scene.get("actions") or []),
        })
    return out


def find_scene(cfg: IoTConfig, query: str) -> Optional[tuple[str, dict]]:
    """Busca una escena por id exacto o por nombre (case-insensitive,
    aceptando coincidencia parcial).
    """
    if not query:
        return None
    q = query.lower().strip()

    # 1) id exacto
    if q in cfg.scenes:
        return q, cfg.scenes[q]

    # 2) nombre exacto
    for sid, sdata in cfg.scenes.items():
        if sdata.get("name", "").lower() == q:
            return sid, sdata

    # 3) coincidencia parcial por nombre o id
    for sid, sdata in cfg.scenes.items():
        if q in sid.lower() or q in sdata.get("name", "").lower():
            return sid, sdata

    return None


def execute_scene(scene: dict, runner: ActionRunner) -> str:
    """Ejecuta los pasos de la escena en orden.

    ``runner(device, command, **kwargs)`` es proporcionado por el
    orquestador y ya valida capabilities + transporte. Si un paso falla,
    se registra y se continúa con el siguiente (las escenas son
    best-effort por diseño: "modo dormir" no debe abortar si una bombilla
    está desenchufada).
    """
    name    = scene.get("name", "escena")
    actions = scene.get("actions") or []

    if not actions:
        return f"La escena '{name}' está vacía."

    results: list[str] = []
    ok, fail = 0, 0
    for step in actions:
        device  = step.get("device")
        command = step.get("command")
        if not device or not command:
            continue
        # Resto del paso son kwargs (value, color, duration, ...)
        kwargs = {k: v for k, v in step.items() if k not in ("device", "command")}
        try:
            msg = runner(device, command, **kwargs)
            results.append(msg)
            ok += 1
        except Exception as e:
            results.append(f"{device}: {e}")
            fail += 1

    if fail == 0:
        return f"Escena '{name}' aplicada ({ok} pasos)."
    return f"Escena '{name}': {ok} pasos OK, {fail} con error."
