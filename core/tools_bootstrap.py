"""
core.tools_bootstrap — Registro de todas las tools builtin
==========================================================
Este módulo da de alta en :class:`core.tool_registry.ToolRegistry` todas
las herramientas builtin de ORION. Antes de este refactor las
declaraciones vivían en ``main.py`` (lista TOOL_DECLARATIONS) y los
handlers en ``main.py::_build_tool_handlers`` + un if/elif paralelo en
``agent/executor.py::_call_tool``. Ahora hay un solo lugar.

Llamar a :func:`register_builtin_tools` es idempotente: si los nombres
ya están registrados, los reemplaza.

Casos especiales
----------------
Cuatro tools tienen lógica que está acoplada a ``OrionLive`` (Gemini Live
session, task queue, ``self.ui.notes_changed()``, ``os._exit``):

  - ``quick_note``      — guarda en notas rápidas + refresca panel
  - ``save_memory``     — actualiza memoria long-term
  - ``agent_task``      — encola una tarea en el agent worker
  - ``shutdown_orion``  — apaga el proceso

Sus declaraciones se registran aquí (para que Gemini Live y los tests las
vean) pero el handler real lo inyecta ``main.py`` con
``ToolRegistry().register(decl, handler)`` durante ``OrionLive.__init__``.
Los stubs que dejamos aquí devuelven un mensaje claro si alguien intenta
invocarlos fuera de modo Live.
"""

from __future__ import annotations

import threading
from typing import Any

from core.tool_registry import ToolDeclaration, ToolRegistry


# ── Helpers de wrapping ─────────────────────────────────────────────────

def _stub_live_only(name: str):
    """Handler de relleno para tools que requieren contexto Live.

    Si el executor o un test los invoca sin que main.py los haya
    sobreescrito, devuelve un mensaje explicativo en vez de explotar.
    """
    def _h(parameters: dict, **_kwargs) -> str:
        return f"La herramienta '{name}' solo está disponible en modo voz (Gemini Live)."
    return _h


# ── Schemas y handlers ──────────────────────────────────────────────────

def register_builtin_tools() -> None:
    """Registra las 22 tools builtin + los 4 stubs Live-only.

    Idempotente: re-llamarlo sobreescribe las entradas anteriores.
    """
    reg = ToolRegistry()

    # ── open_app ────────────────────────────────────────────────────
    def h_open_app(parameters: dict, *, player=None, **_):
        from actions.open_app import open_app
        r = open_app(parameters=parameters, response=None, player=player)
        return r or f"Aplicación abierta: {parameters.get('app_name')}."

    reg.register(
        ToolDeclaration(
            name="open_app",
            description=(
                "Opens any application on the computer. "
                "Use this whenever the user asks to open, launch, or start any app, "
                "website, or program. Always call this tool — never just say you opened it."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "app_name": {
                        "type": "STRING",
                        "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                    }
                },
                "required": ["app_name"]
            },
        ),
        h_open_app,
    )

    # ── web_search ──────────────────────────────────────────────────
    def h_web_search(parameters: dict, *, player=None, **_):
        from actions.web_search import web_search
        return web_search(parameters=parameters, player=player) or "Listo."

    reg.register(
        ToolDeclaration(
            name="web_search",
            description="Searches the web for any information.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "query":  {"type": "STRING", "description": "Search query"},
                    "mode":   {"type": "STRING", "description": "search (default) or compare"},
                    "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                    "aspect": {"type": "STRING", "description": "price | specs | reviews"}
                },
                "required": ["query"]
            },
        ),
        h_web_search,
    )

    # ── weather_report ──────────────────────────────────────────────
    def h_weather(parameters: dict, *, player=None, **_):
        from actions.weather_report import weather_action
        return weather_action(parameters=parameters, player=player) or "Reporte del clima entregado."

    reg.register(
        ToolDeclaration(
            name="weather_report",
            description="Gives the weather report to user",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "city": {"type": "STRING", "description": "City name"}
                },
                "required": ["city"]
            },
        ),
        h_weather,
    )

    # ── send_message ────────────────────────────────────────────────
    def h_send_msg(parameters: dict, *, player=None, **_):
        from actions.send_message import send_message
        r = send_message(parameters=parameters, response=None, player=player, session_memory=None)
        return r or f"Mensaje enviado a {parameters.get('receiver')}."

    reg.register(
        ToolDeclaration(
            name="send_message",
            description="Sends a text message via WhatsApp, Telegram, or other messaging platform.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                    "message_text": {"type": "STRING", "description": "The message to send"},
                    "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
                },
                "required": ["receiver", "message_text", "platform"]
            },
        ),
        h_send_msg,
    )

    # ── reminder ────────────────────────────────────────────────────
    def h_reminder(parameters: dict, *, player=None, **_):
        from actions.reminder import reminder
        return reminder(parameters=parameters, response=None, player=player) or "Recordatorio creado."

    reg.register(
        ToolDeclaration(
            name="reminder",
            description="Sets a timed reminder using Task Scheduler.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                    "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                    "message": {"type": "STRING", "description": "Reminder message text"}
                },
                "required": ["date", "time", "message"]
            },
        ),
        h_reminder,
    )

    # ── youtube_video ───────────────────────────────────────────────
    def h_youtube(parameters: dict, *, player=None, **_):
        from actions.youtube_video import youtube_video
        return youtube_video(parameters=parameters, response=None, player=player) or "Listo."

    reg.register(
        ToolDeclaration(
            name="youtube_video",
            description=(
                "Controls YouTube. Use for: playing videos, summarizing a video's content, "
                "getting video info, or showing trending videos."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                    "query":  {"type": "STRING", "description": "Search query for play action"},
                    "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                    "region": {"type": "STRING", "description": "Country code for trending e.g. ES, MX, AR"},
                    "url":    {"type": "STRING", "description": "Video URL for get_info action"},
                },
                "required": []
            },
        ),
        h_youtube,
    )

    # ── screen_process ──────────────────────────────────────────────
    # La vision module corre en su propio thread y habla por sí misma.
    # El handler devuelve un mensaje de aviso al modelo para que se calle.
    def h_screen(parameters: dict, *, player=None, **_):
        from actions.screen_processor import screen_process
        threading.Thread(
            target=screen_process,
            kwargs={
                "parameters": parameters, "response": None,
                "player": player, "session_memory": None,
            },
            daemon=True,
        ).start()
        return (
            "Vision module activated. Stay silent — "
            "the vision module will speak directly to the user."
        )

    reg.register(
        ToolDeclaration(
            name="screen_process",
            description=(
                "Captures and analyzes the screen or webcam image. "
                "MUST be called when user asks what is on screen, what you see, "
                "analyze my screen, look at camera, etc. "
                "You have NO visual ability without this tool. "
                "After calling this tool, stay SILENT — the vision module speaks directly."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                    "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
                },
                "required": ["text"]
            },
            runs_in_thread=True,
        ),
        h_screen,
    )

    # ── computer_settings ───────────────────────────────────────────
    def h_settings(parameters: dict, *, player=None, **_):
        from actions.computer_settings import computer_settings
        return computer_settings(parameters=parameters, response=None, player=player) or "Listo."

    reg.register(
        ToolDeclaration(
            name="computer_settings",
            description=(
                "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
                "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
                "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
                "Use for ANY single computer control command. NEVER route to agent_task."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "action":      {"type": "STRING", "description": "The action to perform"},
                    "description": {"type": "STRING", "description": "Natural language description of what to do"},
                    "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
                },
                "required": []
            },
        ),
        h_settings,
    )

    # ── browser_control ─────────────────────────────────────────────
    def h_browser(parameters: dict, *, player=None, **_):
        from actions.browser_control import browser_control
        return browser_control(parameters=parameters, player=player) or "Listo."

    reg.register(
        ToolDeclaration(
            name="browser_control",
            description=(
                "Controls any web browser. Use for: opening websites, searching the web, "
                "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
                "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
                "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                    "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                    "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                    "query":       {"type": "STRING", "description": "Search query for search action"},
                    "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                    "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                    "text":        {"type": "STRING", "description": "Text to click or type"},
                    "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                    "direction":   {"type": "STRING", "description": "up | down for scroll"},
                    "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                    "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                    "path":        {"type": "STRING", "description": "Save path for screenshot"},
                    "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                    "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                },
                "required": ["action"]
            },
        ),
        h_browser,
    )

    # ── file_controller ─────────────────────────────────────────────
    def h_file_ctrl(parameters: dict, *, player=None, **_):
        from actions.file_controller import file_controller
        return file_controller(parameters=parameters, player=player) or "Listo."

    reg.register(
        ToolDeclaration(
            name="file_controller",
            description=(
                "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage, "
                "find duplicates, recursive size analysis, BULK DELETE BY CRITERIA. "
                "Recognizes files by partial/short names (e.g. 'informe teórico' matches both "
                "'Informe-teorico.pdf' and a folder of the same name). "
                "If multiple matches are found, the tool returns a disambiguation result — "
                "ASK the user in natural language which one (or 'all') and call again with "
                "confirm_all=true if they pick all. "
                "For 'find duplicate files' use action=duplicates. For 'which folder takes "
                "the most space' use action=tree_size. "
                "BULK DELETE SAFETY: actions 'delete_bulk', 'delete_duplicates' and 'delete_empty_folders' "
                "ALWAYS default to dry_run=true (preview only). You MUST: "
                "(1) first call with dry_run=true to get the preview, "
                "(2) tell the user the count/total/sample, "
                "(3) wait for EXPLICIT verbal confirmation ('sí borrá', 'confirmo'), "
                "(4) only then call again with dry_run=false AND confirm=true. "
                "Files go to the recycle bin (send2trash), not permanent. "
                "These bulk actions are fast in-process scans — DO NOT chain list+delete manually."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | delete_all | delete_bulk | delete_duplicates | delete_empty_folders | move | copy | rename | read | write | find | largest | duplicates | tree_size | disk_usage | organize_desktop | info"},
                    "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                    "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                    "new_name":    {"type": "STRING", "description": "New name for rename"},
                    "content":     {"type": "STRING", "description": "Content for create_file/write"},
                    "name":        {"type": "STRING", "description": "File name (partial OK — the tool resolves stems, normalizes accents and matches both files and folders)"},
                    "extension":   {"type": "STRING", "description": "Filter by extension for find/largest/duplicates/delete_bulk/delete_duplicates (e.g. .pdf or just pdf)"},
                    "pattern":     {"type": "STRING", "description": "Glob pattern for delete_bulk (e.g. '*.tmp', 'Thumbs.db', '*~')"},
                    "older_than_days": {"type": "INTEGER", "description": "delete_bulk: only files older than N days (by mtime)"},
                    "larger_than_mb":  {"type": "NUMBER",  "description": "delete_bulk: only files > N MB"},
                    "smaller_than_mb": {"type": "NUMBER",  "description": "delete_bulk: only files < N MB"},
                    "keep":        {"type": "STRING", "description": "delete_duplicates: which copy to keep — shortest_path (default) | oldest | newest | first"},
                    "dry_run":     {"type": "BOOLEAN", "description": "Bulk-delete actions: when true (default) returns only a PREVIEW. Set false ONLY after the user explicitly confirmed."},
                    "confirm":     {"type": "BOOLEAN", "description": "Bulk-delete actions: required true when dry_run=false. Extra safety to avoid accidental deletion."},
                    "count":       {"type": "INTEGER", "description": "Number of results for largest (default 10, max 50)"},
                    "min_size_mb": {"type": "NUMBER",  "description": "Minimum file size in MB for largest (default 0 = no minimum)"},
                    "min_size_kb": {"type": "NUMBER",  "description": "Minimum file size in KB for duplicates/delete_duplicates (default 1 = ignore tiny files)"},
                    "max_groups":  {"type": "INTEGER", "description": "Max duplicate groups to return (default 20, max 100)"},
                    "depth":       {"type": "INTEGER", "description": "Recursion depth for tree_size (1-4, default 1)"},
                    "top":         {"type": "INTEGER", "description": "How many subfolders to list in tree_size (default 20, max 50)"},
                    "confirm_all": {"type": "BOOLEAN", "description": "When true on a delete with multiple matches, delete ALL of them. Use only after the user confirmed 'todos/all'."},
                },
                "required": ["action"]
            },
        ),
        h_file_ctrl,
    )

    # ── desktop_control ─────────────────────────────────────────────
    def h_desktop(parameters: dict, *, player=None, **_):
        from actions.desktop import desktop_control
        return desktop_control(parameters=parameters, player=player) or "Listo."

    reg.register(
        ToolDeclaration(
            name="desktop_control",
            description="Controls the desktop: wallpaper, organize, clean, list, stats.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                    "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                    "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                    "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                    "task":   {"type": "STRING", "description": "Natural language desktop task"},
                },
                "required": ["action"]
            },
        ),
        h_desktop,
    )

    # ── code_helper ─────────────────────────────────────────────────
    def h_code(parameters: dict, *, player=None, speak=None, **_):
        from actions.code_helper import code_helper
        return code_helper(parameters=parameters, player=player, speak=speak) or "Listo."

    reg.register(
        ToolDeclaration(
            name="code_helper",
            description=(
                "Writes, edits, explains, runs, or builds SOURCE CODE FILES "
                "(Python, JavaScript, C++, etc). "
                "NEVER use this for math questions, integrals, derivatives, "
                "equations or formulas — answer math DIRECTLY with LaTeX in chat."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                    "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                    "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                    "output_path": {"type": "STRING", "description": "Where to save the file"},
                    "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                    "code":        {"type": "STRING", "description": "Raw code string for explain"},
                    "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                    "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
                },
                "required": ["action"]
            },
            timeout=180,
            needs_speak=True,
        ),
        h_code,
    )

    # ── dev_agent ───────────────────────────────────────────────────
    def h_dev(parameters: dict, *, player=None, speak=None, **_):
        from actions.dev_agent import dev_agent
        return dev_agent(parameters=parameters, player=player, speak=speak) or "Listo."

    reg.register(
        ToolDeclaration(
            name="dev_agent",
            description="Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "description":  {"type": "STRING", "description": "What the project should do"},
                    "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                    "project_name": {"type": "STRING", "description": "Optional project folder name"},
                    "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
                },
                "required": ["description"]
            },
            timeout=300,
            needs_speak=True,
        ),
        h_dev,
    )

    # ── agent_task ──────────────────────────────────────────────────
    # Stub Live-only: main.py reemplaza el handler con la versión que
    # encola en task_queue.
    reg.register(
        ToolDeclaration(
            name="agent_task",
            description=(
                "Executes complex multi-step tasks requiring multiple different tools. "
                "Examples: 'research X and save to file', 'find and organize files'. "
                "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                    "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
                },
                "required": ["goal"]
            },
            # Semi-síncrono: el handler en main.py espera hasta 110s por el
            # resultado para devolverlo como tool_response. Damos margen de
            # 10s extra para que el handler complete el fallback async.
            timeout=120,
            include_in_planner=False,
        ),
        _stub_live_only("agent_task"),
    )

    # ── computer_control ────────────────────────────────────────────
    def h_comp_ctrl(parameters: dict, *, player=None, **_):
        from actions.computer_control import computer_control
        return computer_control(parameters=parameters, player=player) or "Listo."

    reg.register(
        ToolDeclaration(
            name="computer_control",
            description="Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                    "text":        {"type": "STRING", "description": "Text to type or paste"},
                    "x":           {"type": "INTEGER", "description": "X coordinate"},
                    "y":           {"type": "INTEGER", "description": "Y coordinate"},
                    "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                    "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                    "direction":   {"type": "STRING", "description": "up | down | left | right"},
                    "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                    "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                    "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                    "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                    "type":        {"type": "STRING",  "description": "Data type for random_data"},
                    "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                    "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                    "path":        {"type": "STRING",  "description": "Save path for screenshot"},
                },
                "required": ["action"]
            },
        ),
        h_comp_ctrl,
    )

    # ── game_updater ────────────────────────────────────────────────
    def h_game(parameters: dict, *, player=None, speak=None, **_):
        from actions.game_updater import game_updater
        return game_updater(parameters=parameters, player=player, speak=speak) or "Listo."

    reg.register(
        ToolDeclaration(
            name="game_updater",
            description=(
                "THE ONLY tool for ANY Steam or Epic Games request. "
                "Use for: installing, downloading, updating games, listing installed games, "
                "checking download status, scheduling updates. "
                "ALWAYS call directly for any Steam/Epic/game request. "
                "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                    "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                    "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                    "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                    "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                    "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                    "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
                },
                "required": []
            },
            timeout=300,
            needs_speak=True,
        ),
        h_game,
    )

    # ── flight_finder ───────────────────────────────────────────────
    def h_flight(parameters: dict, *, player=None, **_):
        from actions.flight_finder import flight_finder
        return flight_finder(parameters=parameters, player=player) or "Listo."

    reg.register(
        ToolDeclaration(
            name="flight_finder",
            description="Searches Google Flights and speaks the best options.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                    "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                    "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                    "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                    "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                    "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                    "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
                },
                "required": ["origin", "destination", "date"]
            },
            timeout=90,
        ),
        h_flight,
    )

    # ── shutdown_orion ──────────────────────────────────────────────
    reg.register(
        ToolDeclaration(
            name="shutdown_orion",
            description=(
                "Shuts down the assistant completely. "
                "Call this when the user expresses intent to end the conversation, "
                "close the assistant, say goodbye, or stop ORION. "
                "The user can say this in ANY language."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {},
            },
            include_in_planner=False,
        ),
        _stub_live_only("shutdown_orion"),
    )

    # ── file_processor ──────────────────────────────────────────────
    def h_file_proc(parameters: dict, *, player=None, speak=None, **_):
        from actions.file_processor import file_processor
        return file_processor(parameters=parameters, player=player, speak=speak) or "Listo."

    reg.register(
        ToolDeclaration(
            name="file_processor",
            description=(
                "Processes any file that the user has uploaded or dropped onto the interface. "
                "Use this when the user refers to an uploaded file and wants an action on it. "
                "Supports: images (describe/ocr/resize/compress/convert), "
                "PDFs (summarize/extract_text/to_word), "
                "Word docs & text files (summarize/fix/reformat/translate), "
                "CSV/Excel (analyze/stats/filter/sort/convert), "
                "JSON/XML (validate/format/analyze), "
                "code files (explain/review/fix/optimize/run/document/test), "
                "audio (transcribe/trim/convert/info), "
                "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
                "archives (list/extract), "
                "presentations (summarize/extract_text). "
                "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
                "If the user's command is ambiguous, pick the most logical action for that file type."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "file_path": {
                        "type": "STRING",
                        "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
                    },
                    "action": {
                        "type": "STRING",
                        "description": (
                            "What to do with the file. Examples by type:\n"
                            "image: describe | ocr | resize | compress | convert | info\n"
                            "pdf: summarize | extract_text | to_word | info\n"
                            "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                            "csv/excel: analyze | stats | filter | sort | convert | info\n"
                            "json: validate | format | analyze | to_csv\n"
                            "code: explain | review | fix | optimize | run | document | test\n"
                            "audio: transcribe | trim | convert | info\n"
                            "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                            "archive: list | extract\n"
                            "pptx: summarize | extract_text | analyze"
                        )
                    },
                    "instruction": {
                        "type": "STRING",
                        "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Spanish', 'find all email addresses'"
                    },
                    "format": {
                        "type": "STRING",
                        "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
                    },
                    "width":       {"type": "INTEGER", "description": "Target width for image resize"},
                    "height":      {"type": "INTEGER", "description": "Target height for image resize"},
                    "scale":       {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
                    "quality":     {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
                    "start":       {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
                    "end":         {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
                    "timestamp":   {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
                    "column":      {"type": "STRING",  "description": "Column name for CSV filter/sort"},
                    "value":       {"type": "STRING",  "description": "Filter value for CSV filter"},
                    "condition":   {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
                    "ascending":   {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
                    "save":        {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
                    "destination": {"type": "STRING",  "description": "Output folder for archive extract"},
                },
                "required": []
            },
            timeout=180,
            needs_speak=True,
            needs_current_file=True,
        ),
        h_file_proc,
    )

    # ── quick_note (Live-only stub; main.py inyecta el real) ────────
    reg.register(
        ToolDeclaration(
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
                        "description": "Full text of the note to save in Spanish. Required."
                    },
                    "pinned": {
                        "type": "BOOLEAN",
                        "description": "Pin the note at the top of the list (default: false)"
                    },
                },
                "required": ["text"]
            },
            include_in_planner=False,
        ),
        _stub_live_only("quick_note"),
    )

    # ── save_memory (Live-only stub; main.py inyecta el real) ───────
    reg.register(
        ToolDeclaration(
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
                        )
                    },
                    "key":   {"type": "STRING", "description": "Short snake_case key (e.g. nombre, comida_favorita, hermana_nombre)"},
                    "value": {"type": "STRING", "description": "Concise value in Spanish (e.g. Fatih, pizza, hermana mayor)"},
                },
                "required": ["category", "key", "value"]
            },
            silent=True,
        ),
        _stub_live_only("save_memory"),
    )

    # ── iot_control ─────────────────────────────────────────────────
    def h_iot(parameters: dict, *, player=None, speak=None, **_):
        from actions.iot import iot_control
        return iot_control(parameters=parameters, player=player, speak=speak) or "Listo."

    reg.register(
        ToolDeclaration(
            name="iot_control",
            description=(
                "Controls IoT/home-automation devices: lights, dimmers, RGB strips, "
                "smart plugs, sensors, etc. Devices may be connected via Arduino (serial) "
                "OR WiFi/MQTT — the tool handles both transparently. "
                "Use this for ANY home automation request. NEVER use agent_task for IoT. "
                "When the user says something natural like 'enciende la luz', 'pon la "
                "tira al 30%', 'luz azul', 'modo película' or 'qué temperatura hay', "
                "use action=auto and pass the original text as 'description'. "
                "If you already know the exact device id and action, prefer the explicit "
                "form (action=on/off/dim/rgb/scene/read_sensor) for lower latency. "
                "Capabilities are PER DEVICE: dim only works on dimmable devices, rgb "
                "only on RGB-capable. The tool will tell you if a device doesn't support "
                "a capability — relay that message to the user."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "action": {
                        "type": "STRING",
                        "description": (
                            "auto — (default) interpret 'description' in natural language | "
                            "on / off — turn a specific device on/off | "
                            "all_on / all_off — global on/off across every device | "
                            "timed — turn a device on for 'duration' seconds then auto-off | "
                            "dim — set brightness 0-100 (requires the device to be dimmable) | "
                            "rgb — set RGB color (requires rgb capability) | "
                            "scene — run a named scene (use 'scene' parameter) | "
                            "read_sensor — get the latest cached sensor reading for a device | "
                            "list_devices — return all devices with their capabilities | "
                            "status — connection status of every configured transport"
                        )
                    },
                    "device":      {"type": "STRING",  "description": "Device id (use list_devices to discover). 'all' is a shortcut for all_on/all_off."},
                    "duration":    {"type": "INTEGER", "description": "Seconds for 'timed' (or for 'on' to auto-off later)."},
                    "value":       {"type": "INTEGER", "description": "Brightness 0-100 for 'dim'."},
                    "color":       {"type": "STRING",  "description": "Color for 'rgb' — accepts a name (rojo/azul/...), hex (#ff00aa) or 'r,g,b'."},
                    "scene":       {"type": "STRING",  "description": "Scene id or name for action=scene."},
                    "description": {"type": "STRING",  "description": "Natural-language command for action=auto."},
                },
                "required": []
            },
            needs_speak=True,
        ),
        h_iot,
    )

    # ── google_drive ────────────────────────────────────────────────
    def h_drive(parameters: dict, *, player=None, **_):
        from actions.google_drive import google_drive
        return google_drive(parameters=parameters, player=player) or "Listo."

    reg.register(
        ToolDeclaration(
            name="google_drive",
            description=(
                "Manages files in Google Drive. Use this for ANY request involving Google Drive: "
                "uploading files, creating documents/sheets/presentations/folders, listing files, "
                "searching, moving, renaming, editing document content, downloading, or deleting. "
                "The user can provide a local file path to upload, or refer to files already in Drive by name or ID. "
                "When the user says 'upload this file to Drive' or 'save this to my Drive', use action=upload. "
                "When creating documents, the user can specify type: document (Google Docs), "
                "sheet/spreadsheet (Google Sheets), presentation/slides (Google Slides). "
                "For files already uploaded to the assistant, use the current_file path with action=upload. "
                "ALWAYS use this tool for any Google Drive request. NEVER use browser_control or agent_task for Drive."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "action": {
                        "type": "STRING",
                        "description": (
                            "upload — upload a local file to Drive | "
                            "create — create a new Google Doc/Sheet/Slides | "
                            "create_folder — create a new folder | "
                            "list — list files (optionally in a folder) | "
                            "search — search files by name or content | "
                            "move — move a file to a different folder | "
                            "rename — rename a file | "
                            "edit — update/replace the content of an existing file | "
                            "delete — send a file to trash | "
                            "download — download a file to local storage | "
                            "info — get detailed file information"
                        )
                    },
                    "file_path": {
                        "type": "STRING",
                        "description": "Local file path for upload or edit actions. Leave empty to use the currently uploaded file in the UI."
                    },
                    "file_id": {
                        "type": "STRING",
                        "description": "Google Drive file ID for move/rename/delete/download/info/edit actions."
                    },
                    "name": {
                        "type": "STRING",
                        "description": "Name for new documents, folders, or search query."
                    },
                    "doc_type": {
                        "type": "STRING",
                        "description": "Type of document to create: document | spreadsheet | presentation (default: document)"
                    },
                    "folder_id": {
                        "type": "STRING",
                        "description": "Target folder ID for upload/create/create_folder/list actions."
                    },
                    "destination_folder_id": {
                        "type": "STRING",
                        "description": "Destination folder ID for move action."
                    },
                    "new_name": {
                        "type": "STRING",
                        "description": "New name for rename action."
                    },
                    "content": {
                        "type": "STRING",
                        "description": "Text content for creating or editing documents."
                    },
                    "query": {
                        "type": "STRING",
                        "description": "Search query for search/list actions."
                    },
                    "destination": {
                        "type": "STRING",
                        "description": "Local destination path for download action."
                    },
                    "max_results": {
                        "type": "INTEGER",
                        "description": "Maximum number of results for list/search (default: 20)."
                    },
                },
                "required": ["action"]
            },
            timeout=120,
            needs_current_file=True,
        ),
        h_drive,
    )

    # ── classroom ───────────────────────────────────────────────────
    def h_classroom(parameters: dict, *, player=None, **_):
        from actions.classroom import classroom
        return classroom(parameters=parameters, player=player) or "Listo."

    reg.register(
        ToolDeclaration(
            name="classroom",
            description=(
                "Opens Google Classroom in Chrome with the correct account. "
                "Use this ALWAYS when the user mentions 'classroom', 'Google Classroom', or 'clase'. "
                "NEVER use browser_control or open_app for Classroom. "
                "Two accounts available: "
                "'personal' (default, /u/0/) for the user's main Google account, "
                "'institucional' (/u/1/) for the university/UNMSM account. "
                "If the user says 'classroom institucional', 'classroom de la uni', or 'classroom unmsm', "
                "set account to 'institucional'. Otherwise use 'personal'."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "account": {
                        "type": "STRING",
                        "description": "Which account: personal (default, main account /u/0/) | institucional (university account /u/1/)"
                    },
                    "url": {
                        "type": "STRING",
                        "description": "Custom Classroom URL. Leave empty to auto-resolve from account type."
                    },
                },
                "required": []
            },
        ),
        h_classroom,
    )

    # ── use_skill ───────────────────────────────────────────────────
    # Devuelve el cuerpo markdown de una skill como contexto extra. El
    # Director / planner la invoca cuando la tarea encaja con la skill;
    # el especialista que ejecute el siguiente paso ve el contenido en
    # step_results y lo aplica. Lee desde core.skills (que parsea
    # skills/<id>/SKILL.md y aplica max_inject_chars).
    def h_use_skill(parameters: dict, *, player=None, **_):
        from core.skills import get_skill, max_inject_chars
        sid = (parameters.get("skill_id") or "").strip()
        if not sid:
            return "use_skill: falta 'skill_id'."
        skill = get_skill(sid)
        if skill is None:
            from core.skills import list_skills
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
