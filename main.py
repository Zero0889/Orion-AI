"""
O.R.I.O.N — Operador de Redes Inteligentes y Optimización Neural
================================================================
Núcleo principal del asistente. Se conecta a Gemini Live, maneja el
audio bidireccional, ejecuta herramientas y se sincroniza con la UI.
"""

from __future__ import annotations

import asyncio
import re
import sys
import threading
import traceback
from pathlib import Path

import sounddevice as sd
from google import genai
from google.genai import types

from config import get_api_key, PROMPT_PATH
from core.logger import get_logger
from plugins.base import PluginRegistry
from ui import OrionUI
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)

# ── Acciones ────────────────────────────────────────────────────────────────
from actions.file_processor   import file_processor
from actions.flight_finder    import flight_finder
from actions.open_app         import open_app
from actions.weather_report   import weather_action
from actions.send_message     import send_message
from actions.reminder         import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor import screen_process
from actions.youtube_video    import youtube_video
from actions.desktop          import desktop_control
from actions.browser_control  import browser_control
from actions.file_controller  import file_controller
from actions.code_helper      import code_helper
from actions.dev_agent        import dev_agent
from actions.web_search       import web_search as web_search_action
from actions.computer_control import computer_control
from actions.game_updater     import game_updater
from actions.iot              import iot_control
from actions.google_drive     import google_drive
from actions.classroom        import classroom

log = get_logger("main")

LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024


def _load_system_prompt() -> str:
    """Carga el prompt del sistema. Si no existe, usa uno por defecto en español."""
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        log.warning("Prompt no encontrado en %s, usando default", PROMPT_PATH)
        return (
            "You are ORION (Operador de Redes Inteligentes y Optimización Neural), "
            "a personal voice assistant. Be concise, direct, and always use "
            "the available tools to complete tasks. "
            "Never simulate or fabricate results — always call the "
            "appropriate tool. Always respond in Spanish."
        )


# Limpieza de transcripciones (caracteres de control que a veces emite el modelo)
_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)
# Tokens espurios que el modelo a veces transcribe a partir de ruido ambiental
# (chasquidos, micro-ruido, etc.). Si la transcripción entera es uno de éstos,
# se descarta.
_TRANSCRIPT_NOISE = {
    "noice", "noise", "[noise]", "[ruido]", "(noise)", "(ruido)",
    "uh", "um", "uhm", "hmm", "mmh", "mm", "ah", "eh",
    "...", "…", ".", "-",
}
# Limpieza de marcadores estilo [BLANK_AUDIO], (background noise), [música], etc.
_BRACKET_RE = re.compile(r"[\[\(\<](?:blank[_ ]?audio|background|music|música|silencio|ruido|noise|inaudible|aplausos|applause)[^\]\)\>]*[\]\)\>]", re.IGNORECASE)

def _clean_transcript(text: str) -> str:
    text = _CTRL_RE.sub("", text)
    text = _BRACKET_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    text = text.strip()
    if text.lower() in _TRANSCRIPT_NOISE:
        return ""
    # Una sola palabra muy corta sin letras alfabéticas → ruido
    if text and len(text) <= 2 and not any(c.isalpha() for c in text):
        return ""
    return text


# ============================================================================
#  Declaración de herramientas para Gemini
#  (las descripciones se quedan en inglés porque así el modelo las entiende
#   mejor, pero el comportamiento del asistente es en español)
# ============================================================================
TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. ES, MX, AR"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command. NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
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
        }
    },
    {
        "name": "file_controller",
        "description": (
            "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage. "
            "Recognizes files by partial/short names (e.g. 'informe teórico' matches both "
            "'Informe-teorico.pdf' and a folder of the same name). "
            "If multiple matches are found, the tool returns a disambiguation result — "
            "ASK the user in natural language which one (or 'all') and call again with "
            "confirm_all=true if they pick all."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | delete_all | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name (partial OK — the tool resolves stems, normalizes accents and matches both files and folders)"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
                "confirm_all": {"type": "BOOLEAN", "description": "When true on a delete with multiple matches, delete ALL of them. Use only after the user confirmed 'todos/all'."},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": (
            "Writes, edits, explains, runs, or builds SOURCE CODE FILES "
            "(Python, JavaScript, C++, etc). "
            "NEVER use this for math questions, integrals, derivatives, "
            "equations or formulas — answer math DIRECTLY with LaTeX in chat."
        ),
        "parameters": {
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
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
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
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
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
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
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
        }
    },
    {
        "name": "shutdown_orion",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop ORION. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
        "name": "file_processor",
        "description": (
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
        "parameters": {
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
        }
    },
    {
        "name": "quick_note",
        "description": (
            "Saves a quick note to the user's notes panel (notas rápidas). "
            "USE THIS — not save_memory — when the user says any of: "
            "'toma nota', 'tomar nota', 'apunta', 'anota', 'guarda esta nota', "
            "'tomame una nota', 'añade una nota', or asks to write something down. "
            "Notes are for ad-hoc reminders/ideas, NOT for personal facts about the user "
            "(those use save_memory). After saving, briefly confirm verbally."
        ),
        "parameters": {
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
        }
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in Spanish regardless of the conversation language."
        ),
        "parameters": {
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
        }
    },
    {
        "name": "iot_control",
        "description": (
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
        "parameters": {
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
        }
    },
    {
        "name": "google_drive",
        "description": (
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
        "parameters": {
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
        }
    },
    {
        "name": "classroom",
        "description": (
            "Opens Google Classroom in Chrome with the correct account. "
            "Use this ALWAYS when the user mentions 'classroom', 'Google Classroom', or 'clase'. "
            "NEVER use browser_control or open_app for Classroom. "
            "Two accounts available: "
            "'personal' (default, /u/0/) for the user's main Google account, "
            "'institucional' (/u/1/) for the university/UNMSM account. "
            "If the user says 'classroom institucional', 'classroom de la uni', or 'classroom unmsm', "
            "set account to 'institucional'. Otherwise use 'personal'."
        ),
        "parameters": {
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
        }
    },
]


# ============================================================================
#  Núcleo Live de ORION
# ============================================================================
class OrionLive:
    """Maneja la sesión Live con Gemini: audio bidireccional, ejecución de
    herramientas y sincronización con la interfaz."""

    def __init__(self, ui: OrionUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command
        self.ui.on_interrupt    = self.interrupt
        self._turn_done_event: asyncio.Event | None = None
        # Tabla de despacho de herramientas (lazy init en _execute_tool)
        self._tool_handlers: dict | None = None
        # Watchdog: marcas de tiempo para detectar cuelgues en PENSANDO
        import time
        self._pensando_since: float | None = None
        self._last_activity_ts: float = time.time()

        # ── Plugins ──
        self._plugin_registry = PluginRegistry()
        n = self._plugin_registry.discover_and_load()
        if n:
            log.info("Plugins disponibles: %s", list(self._plugin_registry.plugins.keys()))

    # ── Callbacks de UI ──────────────────────────────────────────────────
    def _on_text_command(self, text: str):
        """Recibe texto desde la UI (input manual o eventos como archivo cargado).
        Captura locales para evitar race conditions con la reconexión.
        """
        loop = self._loop
        session = self.session
        if not loop or not session:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                session.send_client_content(
                    turns={"parts": [{"text": text}]},
                    turn_complete=True
                ),
                loop
            )
        except Exception as e:
            log.warning("on_text_command falló: %s", e)

    def _ui_state(self, state: str):
        """Cambia el estado UI y mantiene el contador del watchdog."""
        import time
        if state == "PENSANDO":
            self._pensando_since = time.time()
        else:
            self._pensando_since = None
        self._last_activity_ts = time.time()
        self.ui.set_state(state)

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self._ui_state("HABLANDO")
        elif not self.ui.muted:
            self._ui_state("ESCUCHANDO")

    def speak(self, text: str):
        """Hace que ORION diga algo (enviando el texto al modelo Live)."""
        loop = self._loop
        session = self.session
        if not loop or not session:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                session.send_client_content(
                    turns={"parts": [{"text": text}]},
                    turn_complete=True
                ),
                loop
            )
        except Exception as e:
            log.warning("speak falló: %s", e)

    def speak_error(self, tool_name: str, error: str):
        """Informa al usuario de un error en una herramienta."""
        short = str(error)[:120]
        self.ui.write_log(f"ERROR: {tool_name} — {short}")
        self.speak(f"Hubo un problema al ejecutar {tool_name}. {short}")

    def interrupt(self):
        """Interrumpe inmediatamente la voz de ORION.

        - Vacía la cola de audio que está pendiente de reproducción.
        - Marca el turno como terminado y vuelve al estado ESCUCHANDO.
        """
        log.info("Interrupción del usuario solicitada")
        # Vaciar la cola de audio pendiente — la reproducción se detiene
        q = self.audio_in_queue
        if q is not None:
            try:
                while not q.empty():
                    q.get_nowait()
            except Exception:
                pass

        # Forzar el turno como terminado
        if self._turn_done_event is not None:
            try:
                self._loop.call_soon_threadsafe(self._turn_done_event.set)
            except Exception:
                pass

        self.set_speaking(False)

        # Avisar al modelo que pare (le enviamos un mensaje vacío de turno)
        loop = self._loop
        session = self.session
        if loop and session:
            try:
                asyncio.run_coroutine_threadsafe(
                    session.send_client_content(
                        turns={"parts": [{"text": "[INTERRUPCIÓN_USUARIO] El usuario te ha pedido detenerte. No continúes."}]},
                        turn_complete=True
                    ),
                    loop,
                )
            except Exception as e:
                log.warning("Interrupción remota falló: %s", e)

    # ── Configuración de la sesión ───────────────────────────────────────
    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        # Nombres de días/meses en español para el contexto temporal
        dias  = ["Lunes", "Martes", "Miércoles", "Jueves",
                 "Viernes", "Sábado", "Domingo"]
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                 "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

        now      = datetime.now()
        time_str = (
            f"{dias[now.weekday()]}, {now.day} de {meses[now.month - 1]} de {now.year} "
            f"— {now.strftime('%H:%M')}"
        )
        time_ctx = (
            f"[CURRENT DATE AND TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this information to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS + self._plugin_registry.get_tool_declarations()}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    # ── Ejecución de herramientas ────────────────────────────────────────
    # Timeout por defecto (segundos) para evitar que ORION quede congelado
    # esperando una herramienta que no responde.
    _DEFAULT_TOOL_TIMEOUT = 60
    # Timeouts especiales por herramienta (operaciones que pueden tardar más)
    _TOOL_TIMEOUTS: dict[str, int] = {
        "dev_agent":      300,
        "game_updater":   300,
        "agent_task":     30,
        "code_helper":    180,
        "file_processor": 180,
        "google_drive":   120,
        "flight_finder":  90,
    }

    def _build_tool_handlers(self) -> dict:
        """Construye el diccionario de handlers. Cada handler recibe args y
        devuelve un coroutine que produce el string resultado.

        Usar un diccionario es O(1) en vez del antiguo if/elif que era O(n).
        Mantiene comportamiento idéntico al original.
        """
        loop = asyncio.get_event_loop()

        def _run(func, **extra):
            return loop.run_in_executor(None, lambda: func(parameters=extra.pop("parameters"), **extra))

        async def h_open_app(args):
            r = await loop.run_in_executor(
                None,
                lambda: open_app(parameters=args, response=None, player=self.ui)
            )
            return r or f"Aplicación abierta: {args.get('app_name')}."

        async def h_weather(args):
            r = await loop.run_in_executor(
                None,
                lambda: weather_action(parameters=args, player=self.ui)
            )
            return r or "Reporte del clima entregado."

        async def h_browser(args):
            r = await loop.run_in_executor(
                None,
                lambda: browser_control(parameters=args, player=self.ui)
            )
            return r or "Listo."

        async def h_file_ctrl(args):
            r = await loop.run_in_executor(
                None,
                lambda: file_controller(parameters=args, player=self.ui)
            )
            return r or "Listo."

        async def h_send_msg(args):
            r = await loop.run_in_executor(
                None,
                lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None)
            )
            return r or f"Mensaje enviado a {args.get('receiver')}."

        async def h_reminder(args):
            r = await loop.run_in_executor(
                None,
                lambda: reminder(parameters=args, response=None, player=self.ui)
            )
            return r or "Recordatorio creado."

        async def h_youtube(args):
            r = await loop.run_in_executor(
                None,
                lambda: youtube_video(parameters=args, response=None, player=self.ui)
            )
            return r or "Listo."

        async def h_screen(args):
            # Vision corre en su propio hilo y habla por sí mismo
            threading.Thread(
                target=screen_process,
                kwargs={
                    "parameters": args, "response": None,
                    "player": self.ui, "session_memory": None
                },
                daemon=True
            ).start()
            return (
                "Vision module activated. Stay silent — "
                "the vision module will speak directly to the user."
            )

        async def h_settings(args):
            r = await loop.run_in_executor(
                None,
                lambda: computer_settings(parameters=args, response=None, player=self.ui)
            )
            return r or "Listo."

        async def h_desktop(args):
            r = await loop.run_in_executor(
                None,
                lambda: desktop_control(parameters=args, player=self.ui)
            )
            return r or "Listo."

        async def h_code(args):
            r = await loop.run_in_executor(
                None,
                lambda: code_helper(parameters=args, player=self.ui, speak=self.speak)
            )
            return r or "Listo."

        async def h_dev(args):
            r = await loop.run_in_executor(
                None,
                lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak)
            )
            return r or "Listo."

        async def h_agent_task(args):
            from agent.task_queue import get_queue, TaskPriority
            priority_map = {
                "low":    TaskPriority.LOW,
                "normal": TaskPriority.NORMAL,
                "high":   TaskPriority.HIGH,
            }
            priority = priority_map.get(
                args.get("priority", "normal").lower(),
                TaskPriority.NORMAL
            )
            task_id = get_queue().submit(
                goal=args.get("goal", ""),
                priority=priority,
                speak=self.speak
            )
            return f"Tarea iniciada (ID: {task_id})."

        async def h_web_search(args):
            r = await loop.run_in_executor(
                None,
                lambda: web_search_action(parameters=args, player=self.ui)
            )
            return r or "Listo."

        async def h_file_proc(args):
            if not args.get("file_path") and self.ui.current_file:
                args["file_path"] = self.ui.current_file
            r = await loop.run_in_executor(
                None,
                lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
            )
            return r or "Listo."

        async def h_comp_ctrl(args):
            r = await loop.run_in_executor(
                None,
                lambda: computer_control(parameters=args, player=self.ui)
            )
            return r or "Listo."

        async def h_game(args):
            r = await loop.run_in_executor(
                None,
                lambda: game_updater(parameters=args, player=self.ui, speak=self.speak)
            )
            return r or "Listo."

        async def h_flight(args):
            r = await loop.run_in_executor(
                None,
                lambda: flight_finder(parameters=args, player=self.ui)
            )
            return r or "Listo."

        async def h_iot(args):
            r = await loop.run_in_executor(
                None,
                lambda: iot_control(parameters=args, player=self.ui, speak=self.speak)
            )
            return r or "Listo."

        async def h_drive(args):
            if not args.get("file_path") and self.ui.current_file:
                if args.get("action") in ("upload", "edit", "update"):
                    args["file_path"] = self.ui.current_file
            r = await loop.run_in_executor(
                None,
                lambda: google_drive(parameters=args, player=self.ui)
            )
            return r or "Listo."

        async def h_classroom(args):
            r = await loop.run_in_executor(
                None,
                lambda: classroom(parameters=args, player=self.ui)
            )
            return r or "Listo."

        async def h_shutdown(args):
            self.ui.write_log("SISTEMA: Apagado solicitado.")
            self.speak("Hasta luego.")
            def _shutdown():
                import os, time
                time.sleep(1.5)
                os._exit(0)
            threading.Thread(target=_shutdown, daemon=True).start()
            return "Apagando ORION."

        return {
            "open_app":          h_open_app,
            "weather_report":    h_weather,
            "browser_control":   h_browser,
            "file_controller":   h_file_ctrl,
            "send_message":      h_send_msg,
            "reminder":          h_reminder,
            "youtube_video":     h_youtube,
            "screen_process":    h_screen,
            "computer_settings": h_settings,
            "desktop_control":   h_desktop,
            "code_helper":       h_code,
            "dev_agent":         h_dev,
            "agent_task":        h_agent_task,
            "web_search":        h_web_search,
            "file_processor":    h_file_proc,
            "computer_control":  h_comp_ctrl,
            "game_updater":      h_game,
            "flight_finder":     h_flight,
            "iot_control":       h_iot,
            "google_drive":      h_drive,
            "classroom":         h_classroom,
            "shutdown_orion":    h_shutdown,
        }

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        log.info("Tool call: %s  %s", name, args)
        self._ui_state("PENSANDO")

        # quick_note: guarda una nota en el panel de notas rápidas
        if name == "quick_note":
            text = (args.get("text") or "").strip()
            pinned = bool(args.get("pinned", False))
            if not text:
                if not self.ui.muted:
                    self.ui.set_state("ESCUCHANDO")
                return types.FunctionResponse(
                    id=fc.id, name=name,
                    response={"result": "No se proporcionó texto para la nota."}
                )
            try:
                from memory.quick_notes import add_note, update_note
                n = add_note(text)
                if pinned and n.get("id"):
                    update_note(n["id"], pinned=True)
                # Refresca el panel de notas si está abierto
                try:
                    win = getattr(self.ui, "_win", None)
                    panel = getattr(win, "_notes_panel", None) if win else None
                    if panel is not None and panel.isVisible():
                        panel.reload()
                except Exception:
                    pass
                self.ui.write_log(f"NOTA guardada: {text[:80]}")
                result_msg = "Nota guardada en el panel de notas rápidas."
            except Exception as e:
                log.warning("quick_note falló: %s", e)
                result_msg = f"No se pudo guardar la nota: {e}"
            if not self.ui.muted:
                self._ui_state("ESCUCHANDO")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": result_msg}
            )

        # save_memory se ejecuta de forma silenciosa (caso especial)
        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                log.info("Memoria guardada: %s/%s = %s", category, key, value)
            if not self.ui.muted:
                self._ui_state("ESCUCHANDO")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        # Lazy init de los handlers (solo una vez por sesión)
        if self._tool_handlers is None:
            self._tool_handlers = self._build_tool_handlers()

        result  = "Listo."
        handler = self._tool_handlers.get(name)

        # Si no hay handler nativo, buscar en plugins
        plugin = None
        if handler is None:
            plugin = self._plugin_registry.get(name)

        try:
            if handler is None and plugin is None:
                result = f"Herramienta desconocida: {name}"
            elif plugin is not None:
                loop = asyncio.get_event_loop()
                timeout = plugin.timeout
                try:
                    result = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda: plugin.execute(args, player=self.ui, speak=self.speak)
                        ),
                        timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    result = f"Plugin '{name}' tardó más de {timeout}s y fue cancelado."
                    log.warning("Timeout en plugin %s (%ds)", name, timeout)
                if not result:
                    result = "Listo."
            else:
                timeout = self._TOOL_TIMEOUTS.get(name, self._DEFAULT_TOOL_TIMEOUT)
                try:
                    result = await asyncio.wait_for(handler(args), timeout=timeout)
                except asyncio.TimeoutError:
                    result = (
                        f"La herramienta '{name}' tardó más de {timeout}s y fue cancelada."
                    )
                    log.warning("Timeout en %s (%ds)", name, timeout)
                if not result:
                    result = "Listo."

        except Exception as e:
            result = f"La herramienta '{name}' falló: {e}"
            log.error("Tool %s falló", name, exc_info=True)
            self.speak_error(name, e)

        if not self.ui.muted:
            self._ui_state("ESCUCHANDO")

        log.info("Tool result: %s → %s", name, str(result)[:80])
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    # ── Loops de audio ───────────────────────────────────────────────────
    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        log.info("Micrófono iniciado")
        loop = asyncio.get_event_loop()

        def _enqueue(payload):
            """Encola el chunk. Si la cola está llena, descarta el más antiguo
            (evita el bug en el que ``put_nowait`` lanzaba QueueFull y la
            sesión quedaba ‘pensando’ sin recibir audio)."""
            try:
                self.out_queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    self.out_queue.get_nowait()
                except Exception:
                    pass
                try:
                    self.out_queue.put_nowait(payload)
                except Exception:
                    pass

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                orion_speaking = self._is_speaking
            # No enviar audio mientras ORION habla (evita feedback)
            if not orion_speaking and not self.ui.muted:
                data = indata.tobytes()
                loop.call_soon_threadsafe(_enqueue,
                    {"data": data, "mime_type": "audio/pcm"}
                )

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                log.info("Stream de micrófono abierto")
                while True:
                    await asyncio.sleep(0.1)
        except sd.PortAudioError as e:
            log.error("Error de audio en micrófono: %s", e)
            raise
        except OSError as e:
            log.error("Error de sistema en micrófono: %s", e)
            raise

    async def _receive_audio(self):
        log.info("Recepción de audio iniciada")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        import time
                        self._last_activity_ts = time.time()
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"Tú: {full_in}")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"ORION: {full_out}")
                            out_buf = []

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            log.debug("Function call: %s", fc.name)
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except Exception as e:
            log.error("Error en recepción de audio: %s", e, exc_info=True)
            raise

    async def _watchdog(self):
        """Detecta cuelgues: si ORION queda en PENSANDO sin actividad de
        audio durante demasiado tiempo, fuerza ESCUCHANDO para que el usuario
        pueda volver a hablar.

        También resetea ``_is_speaking`` si no llega audio nuevo durante un
        rato y el turno está marcado como terminado.
        """
        import time
        STUCK_LIMIT_S = 12.0  # PENSANDO sin audio durante 12s → desbloquear
        SPEAKING_TIMEOUT_S = 6.0  # _is_speaking sin audio en 6s → resetear
        while True:
            try:
                await asyncio.sleep(2.0)
                now = time.time()
                # 1) Si _is_speaking sigue True pero la cola está vacía y el
                #    turno terminó, resetea.
                with self._speaking_lock:
                    speaking = self._is_speaking
                if speaking and self.audio_in_queue and self.audio_in_queue.empty():
                    if (now - self._last_activity_ts) > SPEAKING_TIMEOUT_S:
                        log.warning("Watchdog: _is_speaking stuck, reset.")
                        self.set_speaking(False)
                        if self._turn_done_event:
                            try:
                                self._turn_done_event.set()
                            except Exception:
                                pass
                # 2) Si PENSANDO se prolonga sin actividad, vuelve a ESCUCHANDO
                if self._pensando_since is not None:
                    elapsed = now - self._pensando_since
                    no_audio = (
                        self.audio_in_queue is None
                        or self.audio_in_queue.empty()
                    )
                    if elapsed > STUCK_LIMIT_S and no_audio:
                        log.warning(
                            "Watchdog: PENSANDO bloqueado %.1fs → ESCUCHANDO",
                            elapsed,
                        )
                        self._pensando_since = None
                        if not self.ui.muted:
                            self.ui.set_state("ESCUCHANDO")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.debug("watchdog tick error: %s", e)

    async def _play_audio(self):
        log.info("Reproducción de audio iniciada")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    # Sin chunks y el turno terminó → ORION dejó de hablar
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
        except sd.PortAudioError as e:
            log.error("Error de audio en reproducción: %s", e)
            raise
        except OSError as e:
            log.error("Error de sistema en reproducción: %s", e)
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    # ── Loop principal ───────────────────────────────────────────────────
    async def run(self):
        try:
            client = genai.Client(
                api_key=get_api_key(),
                http_options={"api_version": "v1beta"}
            )
        except RuntimeError as e:
            log.error("Error de configuración: %s", e)
            self.ui.write_log(f"ERROR DE CONFIGURACIÓN: {e}")
            return

        # Backoff exponencial: 3s → 5s → 10s → 20s → 30s (máx)
        # Evita bombardear la API si Gemini está caído.
        backoff_s = 3
        max_backoff_s = 30

        while True:
            try:
                log.info("Conectando a Gemini Live...")
                self._ui_state("PENSANDO")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self._loop            = asyncio.get_event_loop()
                    self.audio_in_queue   = asyncio.Queue()
                    self.out_queue        = asyncio.Queue(maxsize=10)
                    self._turn_done_event = asyncio.Event()

                    log.info("Conectado a Gemini Live.")
                    self._ui_state("ESCUCHANDO")
                    self.ui.write_log("SISTEMA: ORION en línea.")

                    # Conexión exitosa → reset del backoff
                    backoff_s = 3

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._watchdog())

            except Exception as e:
                log.warning("Sesión desconectada: %s", e, exc_info=True)

            self.set_speaking(False)
            self._ui_state("PENSANDO")
            log.info("Reconectando en %ds...", backoff_s)
            await asyncio.sleep(backoff_s)
            # Crece el backoff para el siguiente intento si vuelve a fallar
            backoff_s = min(int(backoff_s * 1.8), max_backoff_s)


# ============================================================================
#  Punto de entrada
# ============================================================================
def main():
    ui = OrionUI("face.png")

    def runner():
        ui.wait_for_api_key()
        orion = OrionLive(ui)
        try:
            asyncio.run(orion.run())
        except KeyboardInterrupt:
            log.info("Cerrando ORION...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()


if __name__ == "__main__":
    main()