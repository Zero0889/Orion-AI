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

import importlib
import inspect
import pkgutil
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

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
_GEMINI_UNSUPPORTED_KEYS = frozenset(
    {
        "$schema",
        "$id",
        "$ref",
        "$defs",
        "definitions",
        "$comment",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "additionalProperties",
        "unevaluatedProperties",
        "patternProperties",
        "dependencies",
        "dependentRequired",
        "dependentSchemas",
        "if",
        "then",
        "else",
        "allOf",
        "oneOf",
        "not",
        "const",
        "examples",
        "default",
        "contentEncoding",
        "contentMediaType",
        "readOnly",
        "writeOnly",
    }
)


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

    _instance: ToolRegistry | None = None
    _tools: dict[str, tuple[ToolDeclaration, ToolHandler]]

    def __new__(cls) -> ToolRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    # Limpia el registry — útil en tests para aislar.
    @classmethod
    def _reset(cls) -> None:
        if cls._instance is not None:
            cls._instance._tools = {}

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

    def get(self, name: str) -> tuple[ToolDeclaration, ToolHandler] | None:
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
        if decl.needs_current_file and current_file and not params.get("file_path"):
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


# ── Decoradores @tool / @live_only_tool ─────────────────────────────────
#
# Reemplazan el patrón viejo de core/tools_bootstrap.py donde 30 bloques
# `reg.register(ToolDeclaration(...), h_xxx)` vivían en un god-file.
# Ahora cada tool declara su schema **junto a su handler** en su archivo
# de actions/, y se auto-registra al importar el módulo.
#
# Uso típico (en actions/open_app.py):
#
#     from core.tool_registry import tool
#
#     @tool(
#         name="open_app",
#         description="Opens any application on the computer...",
#         parameters={
#             "type": "OBJECT",
#             "properties": {"app_name": {"type": "STRING", "description": "..."}},
#             "required": ["app_name"],
#         },
#         fallback="Aplicación abierta.",
#     )
#     def open_app(parameters, *, player=None, response=None):
#         ...
#
# El decorador:
#   1. Inspecciona la firma de `open_app` para saber qué kwargs acepta.
#   2. Cuando el registry invoca, sólo pasa los kwargs que la función
#      declara (filtra el resto). Esto preserva la heterogeneidad de
#      firmas que tenían los wrappers viejos sin obligarnos a uniformar.
#   3. Si la función retorna None o cadena vacía, devuelve `fallback`
#      (default "Listo.").
#   4. Si `runs_in_thread=True`, ejecuta en daemon Thread y devuelve
#      `fallback` inmediatamente (caso screen_processor).
#   5. La función original queda intacta — se puede seguir llamando
#      `open_app(parameters={...}, player=...)` directamente.


# Cache de pares (decl, handler) que los decoradores vieron en esta
# corrida del intérprete. Los decoradores se evalúan UNA sola vez (al
# primer import del módulo), pero `ToolRegistry._reset()` —que usan los
# tests— vacía el dict interno y los decoradores no se re-disparan.
# Este cache permite re-poblar el registry sin re-importar módulos.
_DECORATED_TOOLS: list[tuple[ToolDeclaration, Callable]] = []


def tool(
    *,
    name: str,
    description: str,
    parameters: dict | None = None,
    timeout: int = 60,
    needs_player: bool = True,
    needs_speak: bool = False,
    needs_current_file: bool = False,
    runs_in_thread: bool = False,
    silent: bool = False,
    include_in_planner: bool = True,
    fallback: str = "Listo.",
) -> Callable[[Callable], Callable]:
    """Decorador que registra la función como tool en el singleton
    ``ToolRegistry`` al momento del import del módulo.
    """

    def decorator(func: Callable) -> Callable:
        # Para tests que usan `patch("module.func", mock)`: resolvemos
        # la función real en cada invocación (no cacheamos la closure),
        # y reinspeccionamos su firma para que el filtrado de kwargs
        # respete el mock — el mock puede tener menos params que la
        # función original y revienta si le pasamos kwargs que no acepta.
        module_name = func.__module__
        func_name = func.__name__

        def _invoke(parameters: dict, *, player=None, speak=None, **_extra: Any) -> str:
            real_func = getattr(importlib.import_module(module_name), func_name, func)
            try:
                sig = inspect.signature(real_func)
                accepted = set(sig.parameters.keys())
                accepts_var_kw = any(
                    p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
                )
            except (ValueError, TypeError):
                # Built-ins o C-funcs sin signature inspectable: pasar todo.
                accepted, accepts_var_kw = set(), True

            call_kwargs: dict[str, Any] = {"parameters": parameters}
            # `available` se arma respetando los flags de la declaración
            # (needs_player / needs_speak) — son parte del contrato del
            # registry. Después filtramos por la firma real para no
            # pasar kwargs que la función no acepta.
            available: dict[str, Any] = {}
            if needs_player:
                available["player"] = player
            if needs_speak:
                available["speak"] = speak
            # Sentinel kwargs legacy que algunos handlers viejos esperan.
            # No los exponemos si no están explícitamente en la firma.
            legacy_sentinels = {"response": None, "session_memory": None}

            if accepts_var_kw:
                call_kwargs.update(available)
            else:
                for k, v in available.items():
                    if k in accepted:
                        call_kwargs[k] = v
                for k, v in legacy_sentinels.items():
                    if k in accepted:
                        call_kwargs[k] = v

            result = real_func(**call_kwargs)
            return result if result not in (None, "") else fallback

        if runs_in_thread:
            # La función real corre en background; el wrapper devuelve
            # `fallback` (o el `description` apropiado) inmediatamente.
            sync_invoke = _invoke

            def _threaded(parameters: dict, **kw: Any) -> str:
                threading.Thread(
                    target=sync_invoke,
                    args=(parameters,),
                    kwargs=kw,
                    daemon=True,
                ).start()
                return fallback

            handler: Callable = _threaded
        else:
            handler = _invoke

        decl = ToolDeclaration(
            name=name,
            description=description,
            parameters=parameters or {},
            timeout=timeout,
            needs_player=needs_player,
            needs_speak=needs_speak,
            needs_current_file=needs_current_file,
            runs_in_thread=runs_in_thread,
            silent=silent,
            include_in_planner=include_in_planner,
        )
        _DECORATED_TOOLS.append((decl, handler))
        ToolRegistry().register(decl, handler)

        # Atributo público por si algún test/caller necesita la decl.
        func.__orion_tool__ = decl  # type: ignore[attr-defined]
        return func

    return decorator


def live_only_tool(
    *,
    name: str,
    description: str,
    parameters: dict | None = None,
    timeout: int = 60,
    needs_player: bool = True,
    silent: bool = False,
    include_in_planner: bool = True,
) -> Callable[[Callable], Callable]:
    """Variante de :func:`tool` para las 4 tools que sólo funcionan en
    modo voz (Gemini Live). El handler registrado es un stub explicativo
    — ``main.OrionLive.__init__`` lo reemplaza con el handler real que
    necesita la sesión Live (task queue, ``os._exit``, etc.).
    """

    def decorator(func: Callable) -> Callable:
        def _stub(parameters: dict, **_kw: Any) -> str:
            return f"La herramienta '{name}' solo está disponible en modo voz (Gemini Live)."

        decl = ToolDeclaration(
            name=name,
            description=description,
            parameters=parameters or {},
            timeout=timeout,
            needs_player=needs_player,
            silent=silent,
            include_in_planner=include_in_planner,
        )
        _DECORATED_TOOLS.append((decl, _stub))
        ToolRegistry().register(decl, _stub)
        func.__orion_tool__ = decl  # type: ignore[attr-defined]
        return func

    return decorator


# ── Auto-discovery ──────────────────────────────────────────────────────


def _replay_decorated() -> None:
    """Re-registra en el registry todas las tools que algún decorator ya
    procesó en esta corrida del intérprete.

    Por qué existe: ``ToolRegistry._reset()`` (que los tests usan para
    aislar) vacía el dict interno. Pero los decoradores Python sólo se
    evalúan UNA vez por proceso, así que sin esta función las tools
    decoradas se perderían tras cualquier reset.
    """
    reg = ToolRegistry()
    for decl, handler in _DECORATED_TOOLS:
        reg.register(decl, handler)


def auto_discover_tools(package: str = "orion.actions") -> int:
    """Importa todos los submódulos de ``package`` para que los
    decoradores ``@tool`` / ``@live_only_tool`` se disparen y registren
    sus tools.

    Es idempotente: si los módulos ya están importados, Python reusa el
    cache y los decoradores no se re-ejecutan (cada decorator corre 1
    vez por proceso).

    Devuelve la cantidad de submódulos visitados (útil para tests).
    """
    pkg = importlib.import_module(package)
    if not hasattr(pkg, "__path__"):
        return 0

    count = 0
    for module_info in pkgutil.walk_packages(pkg.__path__, prefix=f"{package}."):
        # Saltear los `_pycache_` y módulos privados convencionales.
        if module_info.name.rsplit(".", 1)[-1].startswith("_"):
            continue
        try:
            importlib.import_module(module_info.name)
            count += 1
        except Exception as e:
            # Un módulo roto no debería tumbar el resto. Log y seguir.
            import logging

            logging.getLogger("orion.tool_registry").warning(
                "auto_discover: import de %s falló — %s", module_info.name, e
            )

    # Re-registrar las tools decoradas que ya estaban en cache (caso típico
    # tras un ToolRegistry._reset() de tests, donde el import es no-op y
    # los decoradores no se vuelven a disparar).
    _replay_decorated()
    return count
