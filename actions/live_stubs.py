"""
actions.live_stubs — Stubs de las 4 tools que sólo funcionan en modo voz
========================================================================
Estas 4 tools tienen lógica acoplada a ``OrionLive`` (Gemini Live session,
task queue, ``self.ui.notes_changed()``, ``os._exit``):

  - ``agent_task``      — encola una tarea en el agent worker
  - ``shutdown_orion``  — apaga el proceso
  - ``quick_note``      — guarda en notas rápidas + refresca panel
  - ``save_memory``     — actualiza memoria long-term

Las declaraciones se registran acá vía ``@live_only_tool`` (para que
Gemini Live y los tests las vean) pero el handler real lo inyecta
``OrionLive.__init__`` con ``ToolRegistry().register(decl, handler)``
durante el startup del modo voz. Los stubs que dejamos devuelven un
mensaje explicativo si alguien los invoca fuera de modo Live.

Las funciones acá son **placeholders** — no tienen lógica útil; sólo
sirven para que el decorador tenga algo a lo cual atarse y la
declaración aparezca en el registry.
"""

from __future__ import annotations

from core.tool_registry import live_only_tool


@live_only_tool(
    name="agent_task",
    description=(
        "Executes complex multi-step tasks requiring multiple different tools. "
        "Examples: 'research X and save to file', 'find and organize files'. "
        "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "goal": {
                "type": "STRING",
                "description": "Complete description of what to accomplish",
            },
            "priority": {
                "type": "STRING",
                "description": "low | normal | high (default: normal)",
            },
        },
        "required": ["goal"],
    },
    # Semi-síncrono: el handler en main.py espera hasta 110s por el
    # resultado para devolverlo como tool_response. Damos margen de
    # 10s extra para que el handler complete el fallback async.
    timeout=120,
    include_in_planner=False,
)
def agent_task() -> None:
    """Live-only stub."""


@live_only_tool(
    name="shutdown_orion",
    description=(
        "Shuts down the assistant completely. "
        "Call this when the user expresses intent to end the conversation, "
        "close the assistant, say goodbye, or stop ORION. "
        "The user can say this in ANY language."
    ),
    parameters={"type": "OBJECT", "properties": {}},
    include_in_planner=False,
)
def shutdown_orion() -> None:
    """Live-only stub."""


@live_only_tool(
    name="quick_note",
    description=(
        "Saves a quick note to the user's notes panel (notas rápidas). "
        "USE THIS — not save_memory — when the user says any of: "
        "'toma nota', 'tomar nota', 'apunta', 'anota', 'guarda esta nota', "
        "'tomame una nota', 'añade una nota', or asks to write something down. "
        "Notes are for ad-hoc reminders/ideas, NOT for personal facts about the user "
        "(those use save_memory). After saving, briefly confirm verbally."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "text": {
                "type": "STRING",
                "description": "Full text of the note to save in Spanish. Required.",
            },
            "pinned": {
                "type": "BOOLEAN",
                "description": "Pin the note at the top of the list (default: false)",
            },
        },
        "required": ["text"],
    },
    include_in_planner=False,
)
def quick_note() -> None:
    """Live-only stub."""


@live_only_tool(
    name="save_memory",
    description=(
        "Save an important personal fact about the user to long-term memory. "
        "Call this silently whenever the user reveals something worth remembering: "
        "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
        "Do NOT call for: weather, reminders, searches, or one-time commands. "
        "Do NOT announce that you are saving — just call it silently. "
        "Values must be in Spanish regardless of the conversation language."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "category": {
                "type": "STRING",
                "description": (
                    "identity — name, age, birthday, city, job, language, nationality | "
                    "preferences — favorite food/color/music/film/game/sport, hobbies | "
                    "projects — active projects, goals, things being built | "
                    "relationships — friends, family, partner, colleagues | "
                    "wishes — future plans, things to buy, travel dreams | "
                    "notes — habits, schedule, anything else worth remembering"
                ),
            },
            "key": {
                "type": "STRING",
                "description": "Short snake_case key (e.g. nombre, comida_favorita, hermana_nombre)",
            },
            "value": {
                "type": "STRING",
                "description": "Concise value in Spanish (e.g. Fatih, pizza, hermana mayor)",
            },
        },
        "required": ["category", "key", "value"],
    },
    silent=True,
)
def save_memory() -> None:
    """Live-only stub."""
