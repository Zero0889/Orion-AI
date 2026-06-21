# computer_control.py
import io
import json
import random
import re
import string
import subprocess
import time
from pathlib import Path

try:
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip

    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

from orion.config import API_CONFIG_PATH as _CONFIG_PATH
from orion.config import MEMORY_PATH as _MEMORY_PATH


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_os() -> str:
    return _load_config().get("os_system", "windows").lower()


from orion.config import get_api_key

_SAFE_SCREENSHOT_ROOTS = (Path.home(),)


def _safe_screenshot_path(requested: str | None) -> Path:
    fallback = Path.home() / "Desktop" / "orion_screenshot.png"
    if not requested:
        return fallback
    try:
        p = Path(requested).expanduser().resolve()
        for root in _SAFE_SCREENSHOT_ROOTS:
            if p.is_relative_to(root.resolve()):
                p.parent.mkdir(parents=True, exist_ok=True)
                return p
    except Exception:
        pass
    return fallback


def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI no está instalado. Ejecuta: pip install pyautogui")


_FIRST_NAMES = [
    "Alex",
    "Jordan",
    "Taylor",
    "Morgan",
    "Casey",
    "Riley",
    "Drew",
    "Quinn",
    "Avery",
    "Blake",
    "Cameron",
    "Dakota",
    "Emerson",
    "Finley",
    "Harper",
]
_LAST_NAMES = [
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Garcia",
    "Miller",
    "Davis",
    "Wilson",
    "Moore",
    "Taylor",
    "Anderson",
    "Thomas",
    "Jackson",
]
_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "proton.me", "mail.com"]


def _random_data(data_type: str) -> str:
    dt = data_type.lower().strip()

    if dt == "first_name":
        return random.choice(_FIRST_NAMES)

    if dt == "last_name":
        return random.choice(_LAST_NAMES)

    if dt == "name":
        return f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"

    if dt == "email":
        first = random.choice(_FIRST_NAMES).lower()
        last = random.choice(_LAST_NAMES).lower()
        num = random.randint(10, 999)
        return f"{first}.{last}{num}@{random.choice(_DOMAINS)}"

    if dt == "username":
        return f"{random.choice(_FIRST_NAMES).lower()}{random.randint(100, 9999)}"

    if dt == "password":
        chars = string.ascii_letters + string.digits + "!@#$%"
        raw = (
            random.choice(string.ascii_uppercase)
            + random.choice(string.digits)
            + random.choice("!@#$%")
            + "".join(random.choices(chars, k=9))
        )
        return "".join(random.sample(raw, len(raw)))

    if dt == "phone":
        return f"+1{random.randint(200, 999)}{random.randint(1_000_000, 9_999_999)}"

    if dt == "birthday":
        y = random.randint(1980, 2000)
        m = random.randint(1, 12)
        d = random.randint(1, 28)
        return f"{m:02d}/{d:02d}/{y}"

    if dt == "address":
        num = random.randint(100, 9999)
        street = random.choice(["Main St", "Oak Ave", "Park Blvd", "Elm St", "Cedar Ln"])
        return f"{num} {street}"

    if dt == "zip_code":
        return str(random.randint(10000, 99999))

    if dt == "city":
        return random.choice(["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"])

    return f"random_{data_type}_{random.randint(1000, 9999)}"


def _user_profile() -> dict:
    """Lee los campos de identidad de la memoria a largo plazo."""
    try:
        if _MEMORY_PATH.exists():
            data = json.loads(_MEMORY_PATH.read_text(encoding="utf-8"))
            identity = data.get("identity", {})
            return {k: v.get("value", "") for k, v in identity.items()}
    except Exception:
        pass
    return {}


def _type(text: str, interval: float = 0.03) -> str:
    _require_pyautogui()
    time.sleep(0.3)
    pyautogui.typewrite(text, interval=interval)
    return f"Tecleado: {text[:60]}{'…' if len(text) > 60 else ''}"


def _smart_type(text: str, clear_first: bool = True) -> str:
    _require_pyautogui()
    if clear_first:
        _clear_field()
        time.sleep(0.1)

    if len(text) > 20 and _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")
        return f"Smart-type (portapapeles): {text[:60]}{'…' if len(text) > 60 else ''}"

    pyautogui.typewrite(text, interval=0.04)
    return f"Smart-type: {text[:60]}{'…' if len(text) > 60 else ''}"


def _click(x=None, y=None, button: str = "left", clicks: int = 1) -> str:
    _require_pyautogui()
    if x is not None and y is not None:
        pyautogui.click(x, y, button=button, clicks=clicks)
        return f"{'Doble c' if clicks == 2 else 'C'}lic en ({x}, {y}) [{button}]"
    pyautogui.click(button=button, clicks=clicks)
    return f"Clic en la posición actual [{button}]"


def _hotkey(*keys) -> str:
    _require_pyautogui()
    pyautogui.hotkey(*keys)
    return f"Atajo de teclado: {'+'.join(keys)}"


def _press(key: str) -> str:
    _require_pyautogui()
    pyautogui.press(key)
    return f"Pulsada: {key}"


def _scroll(direction: str = "down", amount: int = 3) -> str:
    _require_pyautogui()
    vertical = direction in ("up", "down")
    clicks = amount if direction in ("up", "right") else -amount
    pyautogui.scroll(clicks) if vertical else pyautogui.hscroll(clicks)
    return f"Scroll {direction} ×{amount}"


def _move(x: int, y: int, duration: float = 0.3) -> str:
    _require_pyautogui()
    pyautogui.moveTo(x, y, duration=duration)
    return f"Ratón → ({x}, {y})"


def _drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> str:
    _require_pyautogui()
    pyautogui.moveTo(x1, y1, duration=0.2)
    pyautogui.dragTo(x2, y2, duration=duration, button="left")
    return f"Arrastrado ({x1},{y1}) → ({x2},{y2})"


def _clipboard_get() -> str:
    if _PYPERCLIP:
        return pyperclip.paste()
    _hotkey("ctrl", "c")
    time.sleep(0.2)
    return "(copiado — pyperclip no disponible para lectura)"


def _clipboard_paste(text: str) -> str:
    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.1)
        _require_pyautogui()
        pyautogui.hotkey("ctrl", "v")
        return f"Pegado: {text[:60]}{'…' if len(text) > 60 else ''}"
    return "pyperclip no disponible"


def _screenshot(save_path: str | None = None) -> str:
    _require_pyautogui()
    path = _safe_screenshot_path(save_path)
    img = pyautogui.screenshot()
    img.save(str(path))
    return f"Captura de pantalla guardada: {path}"


def _clear_field() -> str:
    _require_pyautogui()
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.press("delete")
    return "Campo limpiado"


def _focus_window(title: str) -> str:
    os_name = _get_os()

    if os_name == "windows":
        try:
            script = f'(New-Object -ComObject WScript.Shell).AppActivate("{title}")'
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                timeout=5,
            )
            time.sleep(0.3)
            return f"Ventana enfocada: {title}"
        except Exception as e:
            return f"focus_window (Windows) falló: {e}"

    if os_name == "mac":
        script = (
            f'tell application "System Events" to '
            f'set frontmost of (first process whose name contains "{title}") to true'
        )
        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5,
            )
            time.sleep(0.3)
            return f"Ventana enfocada: {title}"
        except Exception as e:
            return f"focus_window (macOS) falló: {e}"

    if os_name == "linux":
        try:
            result = subprocess.run(
                ["wmctrl", "-a", title],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                time.sleep(0.3)
                return f"Ventana enfocada: {title}"
        except FileNotFoundError:
            pass
        try:
            result = subprocess.run(
                ["xdotool", "search", "--name", title, "windowactivate"],
                capture_output=True,
                timeout=5,
            )
            time.sleep(0.3)
            return f"Ventana enfocada: {title}"
        except FileNotFoundError:
            return "focus_window (Linux) requiere wmctrl o xdotool"
        except Exception as e:
            return f"focus_window (Linux) falló: {e}"

    return f"focus_window: SO desconocido '{os_name}'"


def _screen_find(description: str) -> tuple[int, int] | None:
    api_key = get_api_key()
    if not api_key:
        print("[ComputerControl] ⚠️ No hay clave API para screen_find")
        return None

    try:
        from google.genai import types as gtypes

        from orion.core import gemini

        _require_pyautogui()
        w, h = pyautogui.size()
        img = pyautogui.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        client = gemini.get_client()
        prompt = (
            f"This is a screenshot of a {w}×{h} pixel screen. "
            f"Locate the UI element described as: '{description}'. "
            f"Reply ONLY with the center coordinates in the format: x,y "
            f"If the element is not visible, reply: NOT_FOUND"
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=[
                gtypes.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt,
            ],
        )

        text = (response.text or "").strip()
        if "NOT_FOUND" in text.upper():
            return None

        match = re.search(r"(\d+)\s*,\s*(\d+)", text)
        if match:
            return int(match.group(1)), int(match.group(2))

    except Exception as e:
        print(f"[ComputerControl] ⚠️ screen_find falló: {e}")

    return None


from orion.core.tool_registry import tool


@tool(
    name="computer_control",
    description="Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data",
            },
            "text": {"type": "STRING", "description": "Text to type or paste"},
            "x": {"type": "INTEGER", "description": "X coordinate"},
            "y": {"type": "INTEGER", "description": "Y coordinate"},
            "keys": {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
            "key": {"type": "STRING", "description": "Single key e.g. 'enter'"},
            "direction": {"type": "STRING", "description": "up | down | left | right"},
            "amount": {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
            "seconds": {"type": "NUMBER", "description": "Seconds to wait"},
            "title": {"type": "STRING", "description": "Window title for focus_window"},
            "description": {
                "type": "STRING",
                "description": "Element description for screen_find/screen_click",
            },
            "type": {"type": "STRING", "description": "Data type for random_data"},
            "field": {
                "type": "STRING",
                "description": "Field for user_data: name|email|city",
            },
            "clear_first": {
                "type": "BOOLEAN",
                "description": "Clear field before typing (default: true)",
            },
            "path": {"type": "STRING", "description": "Save path for screenshot"},
        },
        "required": ["action"],
    },
)
def computer_control(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Tabla de despacho para todas las acciones de control del ordenador.

    Claves de parameters (todas opcionales salvo indicación):
      action        : (requerido) una de las acciones listadas abajo
      text          : texto a teclear o pegar
      x, y          : coordenadas de pantalla
      button        : 'left' | 'right' (por defecto: left)
      keys          : cadena de atajo, p.ej. 'ctrl+c'
      key           : nombre de una sola tecla, p.ej. 'enter'
      direction     : 'up' | 'down' | 'left' | 'right'
      amount        : cantidad de scroll (por defecto: 3)
      seconds       : duración de espera
      title         : fragmento de título de ventana para focus_window
      description   : descripción en lenguaje natural para screen_find/click
      type          : tipo de dato para random_data
      field         : nombre de campo de memoria para user_data
      clear_first   : bool, limpiar el campo antes de teclear (por defecto: true)
      path          : ruta de guardado para screenshot (debe estar dentro del home)

    Acciones:
      type          — teclear texto en el cursor
      smart_type    — limpiar campo + teclear (vía portapapeles)
      click         — clic izquierdo
      double_click  — doble clic izquierdo
      right_click   — clic derecho
      move          — mover el ratón
      drag          — arrastrar entre dos puntos
      hotkey        — combinación de teclas
      press         — una sola tecla
      scroll        — desplazamiento de la rueda
      copy          — leer el portapapeles
      paste         — escribir + pegar del portapapeles
      screenshot    — capturar la pantalla (sólo ruta segura)
      wait          — esperar N segundos
      clear_field   — seleccionar todo + suprimir
      focus_window  — traer la ventana al frente
      screen_find   — localizador de elementos por IA (devuelve x,y)
      screen_click  — localizador de elementos por IA + clic
      random_data   — generar datos falsos de formulario
      user_data     — obtener datos reales desde la memoria
    """
    params = parameters or {}
    action = params.get("action", "").lower().strip()

    if not action:
        return "No se especificó ninguna acción para computer_control."

    if player:
        player.write_log(f"[Computer] {action}")

    print(f"[ComputerControl] ▶ {action}  {params}")

    try:
        if action == "type":
            return _type(params.get("text", ""))

        if action == "smart_type":
            return _smart_type(
                params.get("text", ""),
                clear_first=params.get("clear_first", True),
            )

        if action in ("click", "left_click"):
            return _click(params.get("x"), params.get("y"), "left", 1)

        if action == "double_click":
            return _click(params.get("x"), params.get("y"), "left", 2)

        if action == "right_click":
            return _click(params.get("x"), params.get("y"), "right", 1)

        if action == "move":
            return _move(int(params.get("x", 0)), int(params.get("y", 0)))

        if action == "drag":
            return _drag(
                int(params.get("x1", 0)),
                int(params.get("y1", 0)),
                int(params.get("x2", 0)),
                int(params.get("y2", 0)),
            )

        if action == "hotkey":
            raw = params.get("keys", "")
            keys = [k.strip() for k in raw.split("+")] if isinstance(raw, str) else raw
            return _hotkey(*keys)

        if action == "press":
            return _press(params.get("key", "enter"))

        if action == "scroll":
            return _scroll(
                direction=params.get("direction", "down"),
                amount=int(params.get("amount", 3)),
            )

        if action == "copy":
            return _clipboard_get()

        if action == "paste":
            return _clipboard_paste(params.get("text", ""))

        if action == "screenshot":
            return _screenshot(params.get("path"))

        if action == "screen_find":
            coords = _screen_find(params.get("description", ""))
            return f"{coords[0]},{coords[1]}" if coords else "NOT_FOUND"

        if action == "screen_click":
            desc = params.get("description", "")
            coords = _screen_find(desc)
            if coords:
                time.sleep(0.2)
                _click(x=coords[0], y=coords[1])
                return f"Clic en '{desc}' en {coords}"
            return f"Elemento no encontrado en la pantalla: '{desc}'"

        if action == "wait":
            secs = float(params.get("seconds", 1.0))
            secs = min(secs, 30.0)
            time.sleep(secs)
            return f"Esperado {secs}s"

        if action == "clear_field":
            return _clear_field()

        if action == "focus_window":
            return _focus_window(params.get("title", ""))

        if action == "random_data":
            dt = params.get("type", "name")
            result = _random_data(dt)
            print(f"[ComputerControl] 🎲 aleatorio {dt} → {result}")
            return result

        if action == "user_data":
            field = params.get("field", "name")
            profile = _user_profile()
            value = profile.get(field, "")
            if not value:
                value = _random_data(field)
                print(f"[ComputerControl] ⚠️ No hay '{field}' en memoria, usando aleatorio: {value}")
            return value

        return f"Acción desconocida: '{action}'"

    except Exception as e:
        print(f"[ComputerControl] ❌ {action}: {e}")
        return f"computer_control '{action}' falló: {e}"
