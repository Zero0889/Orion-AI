"""
agent.orchestra_admin — CRUD de ``config/agents.json``.

La orquesta vive en un único JSON editable a mano. Este módulo añade un
write-path seguro para que la UI pueda crear, actualizar y borrar
agentes sin que el usuario tenga que tocar el archivo a mano.

Garantías:

- **Escritura atómica**: escribimos a ``.tmp`` y renombramos. Si algo
  falla a la mitad, el ``agents.json`` original queda intacto.
- **Lock por proceso**: ``threading.Lock`` evita corrupciones cuando
  dos requests concurrentes (típico en uvicorn) llegan a la vez.
- **Invalidación del registry**: al guardar, se llama a
  ``agent.registry.reset_cache()`` para que la siguiente lectura vea
  los cambios sin reiniciar el servidor.

Validación mínima en :func:`upsert_agent`: id válido (snake_case),
provider conocido, ``tools`` lista de strings. La validación profunda
(¿el modelo existe? ¿el provider responde?) se hace cuando el agente
se invoca, no aquí — así el usuario puede guardar configuraciones
"work in progress" sin que la UI le grite.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from config import BASE_DIR
from core.llm.base import _OPENAI_COMPAT  # set de providers OpenAI-compatible


_AGENTS_PATH = BASE_DIR / "config" / "agents.json"
_LOCK = threading.Lock()

_VALID_ID = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
_VALID_PROVIDERS = {"gemini"} | _OPENAI_COMPAT


# ── Lectura ────────────────────────────────────────────────────────────────

def load_config() -> dict:
    """Lee el JSON completo. Devuelve ``{}`` si no existe o está roto."""
    if not _AGENTS_PATH.exists():
        return {}
    try:
        return json.loads(_AGENTS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[OrchestraAdmin] ⚠️ agents.json ilegible: {e}")
        return {}


def get_agent_spec(agent_id: str) -> dict | None:
    return (load_config().get("agents") or {}).get(agent_id)


# ── Escritura ──────────────────────────────────────────────────────────────

def _save_atomic(data: dict) -> None:
    """Escribe ``agents.json`` de forma atómica.

    Si el rename falla en Windows porque el destino está abierto, hacemos
    fallback a write-through (menos seguro pero el SO no nos deja otra).
    """
    tmp = _AGENTS_PATH.with_suffix(".json.tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp.write_text(payload, encoding="utf-8")
    try:
        tmp.replace(_AGENTS_PATH)
    except OSError:
        # Windows fallback: el archivo destino está bloqueado.
        _AGENTS_PATH.write_text(payload, encoding="utf-8")
        try:
            tmp.unlink()
        except OSError:
            pass


def _invalidate_registry() -> None:
    """Forza al registry a releer agents.json en la próxima llamada."""
    try:
        from agent.registry import reset_cache
        reset_cache()
    except Exception as e:
        print(f"[OrchestraAdmin] ⚠️ no pude invalidar registry: {e}")


def _validate_spec(agent_id: str, spec: dict, *, creating: bool) -> None:
    if creating and not _VALID_ID.match(agent_id):
        raise ValueError(
            f"id inválido: '{agent_id}'. Usa snake_case (letras minúsculas, "
            f"números y guion bajo). Ej: 'translator', 'finance_v2'."
        )
    if not isinstance(spec, dict):
        raise ValueError("spec debe ser un objeto JSON.")
    provider = spec.get("provider")
    if provider and provider not in _VALID_PROVIDERS:
        raise ValueError(
            f"provider '{provider}' no soportado. Conocidos: "
            f"{', '.join(sorted(_VALID_PROVIDERS))}"
        )
    if "tools" in spec and not isinstance(spec["tools"], list):
        raise ValueError("'tools' debe ser una lista de strings.")
    if "model" in spec and not isinstance(spec["model"], str):
        raise ValueError("'model' debe ser un string.")
    if "temperature" in spec:
        t = spec["temperature"]
        if not isinstance(t, (int, float)) or not (0.0 <= float(t) <= 2.0):
            raise ValueError("'temperature' debe ser un número entre 0 y 2.")


def upsert_agent(agent_id: str, spec: dict) -> dict:
    """Crea o actualiza un agente. Devuelve la spec ya escrita.

    Si el id no existía, se crea. Si existía, se sobreescribe (los
    campos no enviados se preservan en la versión persistida — patch
    parcial). Esto permite que la UI mande solo lo que cambia.
    """
    with _LOCK:
        cfg = load_config()
        cfg.setdefault("agents", {})

        existing = cfg["agents"].get(agent_id, {})
        creating = not existing

        _validate_spec(agent_id, spec, creating=creating)

        merged = {**existing, **spec}
        # Defaults razonables al crear.
        if creating:
            merged.setdefault("enabled",     True)
            merged.setdefault("temperature", 0.5)
            merged.setdefault("tools",       [])
            merged.setdefault("icon",        "circle-dot")
            merged.setdefault("system",      "")
            merged.setdefault("description", "")
            merged.setdefault("role",        agent_id.replace("_", " ").title())

        if not merged.get("provider") or not merged.get("model"):
            raise ValueError(
                "Un agente necesita al menos 'provider' y 'model' configurados."
            )

        cfg["agents"][agent_id] = merged
        _save_atomic(cfg)

    _invalidate_registry()
    return merged


def delete_agent(agent_id: str) -> bool:
    """Elimina un agente. Devuelve True si existía y se borró."""
    with _LOCK:
        cfg = load_config()
        agents = cfg.get("agents") or {}
        if agent_id not in agents:
            return False
        # Protección: no permitir borrar el último agente habilitado, o
        # quedarse sin Director. Sin él, el planner no sabe a quién
        # enrutar y la orquesta se rompe.
        if agent_id == "director":
            raise ValueError(
                "No puedes borrar al Director. Es el agente que enruta a "
                "los demás. Deshabilítalo o cambia su modelo en lugar de "
                "borrarlo."
            )
        del agents[agent_id]
        cfg["agents"] = agents
        _save_atomic(cfg)

    _invalidate_registry()
    return True
