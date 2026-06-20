"""
core.tools_bootstrap — Bootstrap del registry de tools builtin
==============================================================
Esta función registra todas las tools que ORION expone a:
  - Gemini Live (``main.py`` lo lee como ``TOOL_DECLARATIONS``).
  - El executor autónomo (``agent/executor.py`` lo despacha por nombre).
  - El planner (``agent/planner.py`` lo serializa al PLANNER_PROMPT).

Tras la migración a decoradores ``@tool`` (Fase 3 item A), la mayoría de
las tools se auto-registran al importarse su módulo en ``actions/``.
Este bootstrap hace dos cosas:

  1. ``auto_discover_tools("actions")`` — importa todos los submódulos de
     ``actions/`` para que sus ``@tool`` / ``@live_only_tool`` se disparen.
  2. Registra a mano las 2 tools cuyo handler vive fuera de ``actions/``
     (``ask_user`` en ``core/ask_user.py`` y ``use_skill`` en
     ``core/skills.py``) — su lógica no es "abrir un archivo y delegar",
     es interactiva/declarativa y se mantiene como handler explícito.

Las 4 tools "Live-only" (``agent_task``, ``shutdown_orion``,
``quick_note``, ``save_memory``) están decoradas con ``@live_only_tool``
en ``actions/live_stubs.py``; el stub se reemplaza con el handler real
en ``OrionLive.__init__``.
"""

from __future__ import annotations

from core.tool_registry import ToolDeclaration, ToolRegistry


def register_builtin_tools() -> None:
    """Registra las tools builtin en el ToolRegistry singleton.

    **Idempotente**: si las tools ya están registradas (chequea por
    ``agent_task`` + ``ask_user`` que son la última builtin Live-only
    + la última explícita) no hace nada. Antes la función reescribía
    siempre y eso pisaba los handlers Live-only que
    ``OrionLive._inject_live_only_handlers`` inyectaba en startup.
    """
    reg = ToolRegistry()
    if reg.has("agent_task") and reg.has("ask_user"):
        return

    # ── Auto-discover de las tools migradas a @tool ─────────────────
    # Cada módulo de actions/ que use `@tool` o `@live_only_tool` se
    # auto-registra al importarse.
    from core.tool_registry import auto_discover_tools as _auto_discover_tools

    _auto_discover_tools("actions")

    # ── ask_user (handler explícito en core/, no en actions/) ───────
    # La validación de options es parte del contrato del tool y vive
    # acá; el handler usa el AskUser server (HTTP block hasta respuesta).
    def h_ask_user(parameters: dict, **_kwargs) -> str:
        from core.ask_user import get_ask_user

        question = (parameters.get("question") or "").strip()
        options = parameters.get("options") or []
        allow_other = bool(parameters.get("allow_other", True))
        if not question:
            return "ask_user: falta el campo 'question'."
        if not options or not isinstance(options, list):
            return "ask_user: 'options' debe ser una lista con al menos 2 opciones."
        clean: list[dict] = []
        for o in options:
            if isinstance(o, dict) and o.get("label"):
                clean.append(
                    {
                        "label": str(o["label"]),
                        "description": str(o.get("description", "")),
                    }
                )
            elif isinstance(o, str):
                clean.append({"label": o, "description": ""})
        if len(clean) < 2:
            return "ask_user: se requieren al menos 2 opciones válidas."
        return get_ask_user().ask(question, clean, allow_other=allow_other)

    reg.register(
        ToolDeclaration(
            name="ask_user",
            description=(
                "Asks the user a clarification question with multiple-choice options. "
                "Use BEFORE executing a task when the request is ambiguous and you "
                "need a specific detail: time period, language, depth (fast/deep), "
                "source type, output format, scope, target audience, etc. "
                "The user picks an option (or types their own if allow_other is true) "
                "and the choice comes back as the tool result so you can continue. "
                "Best practice: keep it to 2-4 mutually exclusive options. "
                "Examples: '¿Qué período histórico te interesa?' with ['Colonial 1532-1821', "
                "'Independencia 1821-1824', 'Toda la conquista']. "
                "'¿Búsqueda rápida o profunda?' with ['Rápida (5 fuentes)', "
                "'Profunda (20+ fuentes vía NotebookLM)']."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "question": {
                        "type": "STRING",
                        "description": "Clarification question in Spanish, e.g. '¿Qué período te interesa?'",
                    },
                    "options": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "label": {
                                    "type": "STRING",
                                    "description": "Short button text (max 40 chars)",
                                },
                                "description": {
                                    "type": "STRING",
                                    "description": "Optional one-line subtitle for clarity",
                                },
                            },
                            "required": ["label"],
                        },
                        "description": "2-4 mutually exclusive options",
                    },
                    "allow_other": {
                        "type": "BOOLEAN",
                        "description": "If true (default), user gets a free-text 'Otro' option to type a custom answer.",
                    },
                },
                "required": ["question", "options"],
            },
            # La tool bloquea hasta 300s esperando respuesta + 20s margen.
            timeout=320,
        ),
        h_ask_user,
    )

    # ── use_skill (handler explícito; el cuerpo de la skill se inyecta
    #    como contexto extra al siguiente paso del planner) ──────────
    def h_use_skill(parameters: dict, *, player=None, **_):
        from core.skills import get_skill, list_skills, max_inject_chars

        sid = (parameters.get("skill_id") or "").strip()
        if not sid:
            return "use_skill: falta 'skill_id'."
        skill = get_skill(sid)
        if skill is None:
            available = ", ".join(s.id for s in list_skills()) or "(ninguna instalada)"
            return f"use_skill: '{sid}' no instalada. Disponibles: {available}"
        body = skill.truncated_body(max_inject_chars())
        return (
            f"# Skill cargada: {skill.id}\n"
            f"# Descripción: {skill.description}\n\n"
            f"Sigue las instrucciones de esta skill al ejecutar los pasos siguientes.\n"
            f"Ejecuta los bloques bash con generated_code cuando aplique.\n\n"
            f"---\n{body}"
        )

    reg.register(
        ToolDeclaration(
            name="use_skill",
            description=(
                "Loads a SKILL.md recipe as context for the next step. Use when the user "
                "request matches one of the installed skills (see catalog in your system prompt). "
                "The returned markdown teaches the next agent how to combine existing tools "
                "(shell, files, web) to fulfill the task. Skills are NOT executable on their own — "
                "after calling use_skill, the next step must be generated_code or another tool "
                "that actually runs the instructions."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "skill_id": {
                        "type": "STRING",
                        "description": "Id de la skill (nombre de carpeta en skills/). Ej: 'gh-issues', 'github'.",
                    },
                },
                "required": ["skill_id"],
            },
        ),
        h_use_skill,
    )
