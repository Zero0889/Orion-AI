"""
core.tool_registry — Registro unificado de herramientas de O.R.I.O.N
====================================================================
Single source of truth para todas las tools que ORION expone:

- A Gemini Live (``main.py`` lo lee como ``TOOL_DECLARATIONS``).
- Al executor autónomo (``agent/executor.py`` lo despacha por nombre).
- Al planner (``agent/planner.py`` lo serializa al PLANNER_PROMPT).

Antes había 3 lugares donde había que dar de alta una tool — uno por
consumidor. Esta clase los unifica. Para añadir una tool nueva basta con
registrarla aquí (vía ``core/tools_bootstrap.py``) y aparece en los tres
sitios automáticamente.

Diseño
------

* ``ToolDeclaration`` — dataclass con la metadata (name, description,
  parameters schema en formato Gemini, timeout, flags de contexto).
* ``ToolRegistry`` — singleton con un dict ``{name: (decl, handler)}``.
  Los handlers son funciones SYNC con firma
  ``(parameters: dict, *, player=None, speak=None, current_file=None) -> str``.
  El registry NO se encarga de threading ni de asyncio — el caller
  (main.py o executor.py) decide cómo invocar (run_in_executor o directo).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


# ── Tipos públicos ──────────────────────────────────────────────────────

# Firma normalizada que TODOS los handlers deben cumplir.
# Se reciben **siempre** los kwargs ``player``, ``speak``, ``current_file``
# aunque la tool no los use (el registry los pasa por contexto).
ToolHandler = Callable[..., str]


@dataclass
class ToolDeclaration:
    """Metadata de una tool. Equivale a una entrada del antiguo
    ``TOOL_DECLARATIONS`` en main.py más algunos flags de contexto.
    """

    name: str
    description: str
    parameters: dict = field(default_factory=dict)
    timeout: int = 60

    # Contexto que el handler necesita recibir al llamarse.
    # Si ``True``, el registry pasa ese kwarg; si ``False``, lo omite.
    needs_player: bool = True
    needs_speak: bool = False
    needs_current_file: bool = False

    # ``runs_in_thread`` — el handler arranca su propio thread y devuelve
    # rápido (caso de screen_process: la vision habla por sí misma).
    runs_in_thread: bool = False

    # ``silent`` — el resultado se considera de uso interno (save_memory).
    silent: bool = False

    # ``include_in_planner`` — si False, la tool no aparece en el prompt
    # del planner autónomo. Útil para tools que solo tienen sentido en
    # modo Live (agent_task, shutdown_orion, quick_note).
    include_in_planner: bool = True

    def to_gemini_dict(self) -> dict:
        """Serializa a la forma que espera Gemini Live en
        ``LiveConnectConfig(tools=[{"function_declarations": [...]}])``.

        Los parameters pasan por :func:`_sanitize_gemini_schema` porque
        Gemini Live acepta solo un subset de JSON Schema. Tools MCP que
        usan ``$schema``, ``exclusiveMaximum``, ``additionalProperties``,
        etc. rompen el pydantic validator del SDK si no se limpian antes.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": _sanitize_gemini_schema(self.parameters),
        }


# Campos de JSON Schema que Gemini Live NO acepta y hay que filtrar al
# serializar. Lista basada en errores reales del pydantic validator del
# google.genai SDK y en la spec de OpenAPI subset que Gemini soporta.
_GEMINI_UNSUPPORTED_KEYS = frozenset({
    "$schema", "$id", "$ref", "$defs", "definitions", "$comment",
    "exclusiveMaximum", "exclusiveMinimum",
    "additionalProperties", "unevaluatedProperties",
    "patternProperties", "dependencies", "dependentRequired", "dependentSchemas",
    "if", "then", "else", "allOf", "oneOf", "not",
    "const", "examples", "default",
    "contentEncoding", "contentMediaType",
    "readOnly", "writeOnly",
})


def _sanitize_gemini_schema(schema):
    """Recursivamente elimina campos de JSON Schema que Gemini Live rechaza.

    Trabaja sobre dicts/lists puros. Devuelve una copia limpia — no muta
    el input (los handlers nativos siguen viendo el schema original).
    """
    if isinstance(schema, dict):
        clean = {}
        for k, v in schema.items():
            if k in _GEMINI_UNSUPPORTED_KEYS:
                continue
            # ``type`` array (["string","null"]) → primer no-null
            if k == "type" and isinstance(v, list):
                non_null = [t for t in v if t != "null"]
                clean[k] = non_null[0] if non_null else "string"
            else:
                clean[k] = _sanitize_gemini_schema(v)
        return clean
    if isinstance(schema, list):
        return [_sanitize_gemini_schema(item) for item in schema]
    return schema


# ── Singleton ───────────────────────────────────────────────────────────

class ToolRegistry:
    """Singleton: una sola instancia por proceso.

    Patrón idéntico a ``plugins.base.PluginRegistry`` para mantener
    coherencia.
    """

    _instance: "ToolRegistry | None" = None

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}  # type: ignore[attr-defined]
        return cls._instance

    # Limpia el registry — útil en tests para aislar.
    @classmethod
    def _reset(cls) -> None:
        if cls._instance is not None:
            cls._instance._tools = {}  # type: ignore[attr-defined]

    # ── Registro ────────────────────────────────────────────────────

    def register(self, decl: ToolDeclaration, handler: ToolHandler) -> None:
        """Registra una tool. Si ya existe una con el mismo nombre, la
        reemplaza (último gana — útil para tests y para plugins que
        sobrescriben builtins)."""
        if not decl.name:
            raise ValueError("ToolDeclaration sin name")
        self._tools[decl.name] = (decl, handler)

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[tuple[ToolDeclaration, ToolHandler]]:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def all(self) -> list[ToolDeclaration]:
        return [decl for decl, _ in self._tools.values()]

    # ── Despacho ────────────────────────────────────────────────────

    def call_sync(
        self,
        name: str,
        parameters: dict | None = None,
        *,
        player=None,
        speak: Callable | None = None,
        current_file: str | None = None,
    ) -> str:
        """Despacha una tool de forma SINCRÓNICA. Devuelve el string que
        se enviará de vuelta al modelo (o al executor).

        El registry no maneja timeouts ni threading — eso es responsabilidad
        del caller. Aquí solo se inyecta el contexto declarado en la
        ``ToolDeclaration`` y se llama al handler.
        """
        entry = self._tools.get(name)
        if entry is None:
            raise KeyError(f"Tool desconocida: {name}")
        decl, handler = entry

        params = dict(parameters or {})

        # Inyección de file_path si la tool lo declara y no se proveyó
        if (
            decl.needs_current_file
            and current_file
            and not params.get("file_path")
        ):
            params["file_path"] = current_file

        kwargs: dict = {}
        if decl.needs_player:
            kwargs["player"] = player
        if decl.needs_speak:
            kwargs["speak"] = speak

        result = handler(params, **kwargs)
        return result if result is not None else "Listo."

    # ── Serialización ──────────────────────────────────────────────

    def to_gemini_declarations(self) -> list[dict]:
        """Devuelve la lista de declaraciones para ``LiveConnectConfig``."""
        return [decl.to_gemini_dict() for decl in self.all()]

    def timeouts(self) -> dict[str, int]:
        """Devuelve el dict ``{tool_name: seconds}`` para overrides — los
        valores != 60 son los que main.py tenía hardcoded en
        ``_TOOL_TIMEOUTS``.
        """
        return {decl.name: decl.timeout for decl in self.all() if decl.timeout != 60}

    def to_planner_text(self) -> str:
        """Renderiza la sección "AVAILABLE TOOLS AND THEIR PARAMETERS"
        del PLANNER_PROMPT.

        Formato compatible con el prompt original:

            tool_name
              param_name: type (required|optional) — description
              ...
        """
        lines: list[str] = []
        for decl in self.all():
            # Tools silent (save_memory) o explícitamente fuera del planner
            # (agent_task / shutdown_orion / quick_note) no aparecen — el
            # planner se encarga de tareas multi-paso, no de side-effects
            # internos ni meta-orquestación.
            if decl.silent or not decl.include_in_planner:
                continue
            lines.append(decl.name)
            props = (decl.parameters or {}).get("properties", {}) or {}
            required = set((decl.parameters or {}).get("required", []) or [])
            for pname, pdef in props.items():
                ptype = (pdef.get("type") or "string").lower()
                req = "required" if pname in required else "optional"
                pdesc = pdef.get("description", "")
                lines.append(f"  {pname}: {ptype} ({req}) — {pdesc}")
            lines.append("")  # blank line entre tools
        return "\n".join(lines).rstrip() + "\n"
