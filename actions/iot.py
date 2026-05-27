# iot.py — Control IoT (Arduino / Focos) para O.R.I.O.N
# ═══════════════════════════════════════════════════════════════
# Controla dispositivos IoT (focos) conectados por serial a un
# Arduino. Soporta encender/apagar individual o todos, opera-
# ciones temporizadas y detección de intención por IA o reglas.
# ═══════════════════════════════════════════════════════════════

import json
import re
import sys
import time
import threading
from pathlib import Path

try:
    import serial
    _SERIAL_OK = True
except ImportError:
    _SERIAL_OK = False


# ── Rutas ────────────────────────────────────────────────────

from config import get_api_key, IOT_CONFIG_PATH as _IOT_CONFIG


# ── Configuración por defecto ────────────────────────────────

_DEFAULT_IOT_CONFIG = {
    "serial_port": "COM1",
    "baud_rate":   9600,
    "devices": {
        "foco_1": {"name": "foco 1", "cmd_on": "FOCO1_ON", "cmd_off": "FOCO1_OFF"},
        "foco_2": {"name": "foco 2", "cmd_on": "FOCO2_ON", "cmd_off": "FOCO2_OFF"},
    },
    "cmd_all_on":  "TODOS_ON",
    "cmd_all_off": "TODOS_OFF",
}


# ── Conexión serial (singleton) ──────────────────────────────

_serial_conn = None
_serial_lock = threading.Lock()


def _load_iot_config() -> dict:
    """Carga la configuración IoT. Si no existe, crea una por defecto."""
    if _IOT_CONFIG.exists():
        try:
            return json.loads(_IOT_CONFIG.read_text(encoding="utf-8"))
        except Exception:
            pass
    _IOT_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    _IOT_CONFIG.write_text(
        json.dumps(_DEFAULT_IOT_CONFIG, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("[IoT] Archivo de configuración creado: config/iot_config.json")
    return _DEFAULT_IOT_CONFIG.copy()


def _get_serial() -> "serial.Serial | None":
    """Obtiene o crea la conexión serial al Arduino."""
    global _serial_conn

    if not _SERIAL_OK:
        return None

    with _serial_lock:
        if _serial_conn is not None and _serial_conn.is_open:
            return _serial_conn

        cfg  = _load_iot_config()
        port = cfg.get("serial_port", "COM1")
        baud = cfg.get("baud_rate", 9600)

        try:
            _serial_conn = serial.Serial(port, baud, timeout=2)
            time.sleep(2)  # Esperar a que Arduino se reinicie
            print(f"[IoT] Conectado a {port} @ {baud}")
            return _serial_conn
        except Exception as e:
            print(f"[IoT] Error de conexión serial ({port}): {e}")
            _serial_conn = None
            return None


def _close_serial():
    """Cierra la conexión serial."""
    global _serial_conn
    with _serial_lock:
        if _serial_conn and _serial_conn.is_open:
            _serial_conn.close()
            print("[IoT] Conexión serial cerrada.")
        _serial_conn = None


# ── Comandos válidos ─────────────────────────────────────────

def _get_valid_commands(cfg: dict) -> set:
    """Retorna el set de comandos válidos según la configuración."""
    cmds = {cfg.get("cmd_all_on", "TODOS_ON"), cfg.get("cmd_all_off", "TODOS_OFF")}
    for dev in cfg.get("devices", {}).values():
        cmds.add(dev["cmd_on"])
        cmds.add(dev["cmd_off"])
    return cmds


def _device_name_map(cfg: dict) -> dict:
    """Mapa de comando → nombre legible del dispositivo."""
    names = {}
    for dev in cfg.get("devices", {}).values():
        names[dev["cmd_on"]]  = dev["name"]
        names[dev["cmd_off"]] = dev["name"]
    return names


# ── Normalización de texto ───────────────────────────────────

def _normalize_text(text: str) -> str:
    """Normaliza el texto del usuario: corrige fonética, números, referencias."""
    text = text.lower().strip()

    # Correcciones fonéticas comunes del reconocimiento de voz
    text = text.replace("segun2",    "segundos")
    text = text.replace("segun dos", "segundos")
    text = text.replace("segun2s",   "segundos")
    text = text.replace("*",         "y")

    # Números escritos en español → dígitos
    num_words = {
        r"\bun\b": "1",    r"\buno\b": "1",      r"\buna\b": "1",
        r"\bdos\b": "2",   r"\btres\b": "3",     r"\bcuatro\b": "4",
        r"\bcinco\b": "5", r"\bseis\b": "6",     r"\bsiete\b": "7",
        r"\bocho\b": "8",  r"\bnueve\b": "9",    r"\bdiez\b": "10",
        r"\bonce\b": "11", r"\bdoce\b": "12",    r"\bquince\b": "15",
        r"\bveinte\b": "20", r"\btreinta\b": "30",
        r"\bcuarenta\b": "40", r"\bcincuenta\b": "50",
    }
    for pattern, digit in num_words.items():
        text = re.sub(pattern, digit, text)

    # Normalizar referencias a focos
    text = text.replace("foco uno",  "foco 1")
    text = text.replace("foco dos",  "foco 2")
    text = text.replace("foco tres", "foco 3")
    text = text.replace("foco foco", "foco")
    text = text.replace("1 y 2",     "foco 1 y foco 2")
    text = text.replace("1 y 3",     "foco 1 y foco 3")
    text = text.replace("2 y 3",     "foco 2 y foco 3")

    # Espacios múltiples
    text = re.sub(r"\s+", " ", text).strip()

    return text


# ── Reglas manuales (evita llamar a Gemini si es obvio) ──────

_RULES_OFF_ALL = [
    "mucha luz", "demasiada luz", "mucho brillo",
    "ya hay luz", "no necesito luz", "suficiente luz",
    "apaga todo", "apaga todos", "apaga los focos",
    "apagame todo", "apagame los focos",
    "apaga la luz", "apaga las luces",
]

_RULES_ON_ALL = [
    "esta oscuro", "está oscuro", "falta luz", "necesito luz",
    "hay poca luz", "poca luz", "muy oscuro",
    "no veo nada", "no se ve", "no se ve nada",
    "prende todo", "prende todos", "prende los focos",
    "enciende todo", "enciende todos", "enciende los focos",
    "prendeme todo", "prendeme todos", "prendeme los focos",
    "enciendeme todo", "enciendeme todos",
    "prende la luz", "prende las luces",
    "enciende la luz", "enciende las luces",
]


def _manual_rules(text: str, cfg: dict) -> list[str] | None:
    """
    Intenta resolver el comando con reglas directas antes de usar IA.
    Retorna la lista de comandos si hay match, None si necesita IA.
    """
    all_on  = cfg.get("cmd_all_on",  "TODOS_ON")
    all_off = cfg.get("cmd_all_off", "TODOS_OFF")

    for phrase in _RULES_OFF_ALL:
        if phrase in text:
            return [all_off]

    for phrase in _RULES_ON_ALL:
        if phrase in text:
            return [all_on]

    # Reglas para focos individuales
    devices = cfg.get("devices", {})
    commands = []

    for key, dev in devices.items():
        name = dev["name"]  # e.g. "foco 1"
        num  = name.split()[-1] if " " in name else key

        on_patterns  = [f"prende el {name}", f"enciende el {name}",
                        f"prende {name}", f"enciende {name}",
                        f"prendeme el {name}", f"enciendeme el {name}"]
        off_patterns = [f"apaga el {name}", f"apaga {name}",
                        f"apagame el {name}"]

        for p in on_patterns:
            if p in text:
                commands.append(dev["cmd_on"])
                break

        for p in off_patterns:
            if p in text:
                commands.append(dev["cmd_off"])
                break

    return commands if commands else None


# ── Enviar comandos al Arduino ───────────────────────────────

def _send_commands(commands: list[str], cfg: dict) -> tuple[list[str], list[str]]:
    """
    Envía una lista de comandos al Arduino.
    Retorna (ejecutados_ok, errores).
    """
    conn = _get_serial()
    if conn is None:
        return [], ["No se pudo conectar al Arduino."]

    valid    = _get_valid_commands(cfg)
    executed = []
    errs     = []

    for cmd in commands:
        cmd = cmd.strip().upper()
        if cmd not in valid:
            errs.append(f"Comando no válido: {cmd}")
            continue
        try:
            conn.write((cmd + "\n").encode())
            time.sleep(0.1)
            executed.append(cmd)
            print(f"[IoT] >>> {cmd}")
        except Exception as e:
            errs.append(f"Error al enviar {cmd}: {e}")
            print(f"[IoT] Error enviando {cmd}: {e}")

    return executed, errs


def _auto_off(commands_on: list[str], cfg: dict):
    """Apaga automáticamente los dispositivos que se encendieron."""
    off_cmds = []
    all_on  = cfg.get("cmd_all_on", "TODOS_ON")
    all_off = cfg.get("cmd_all_off", "TODOS_OFF")

    for cmd in commands_on:
        if cmd == all_on:
            off_cmds.append(all_off)
        elif cmd.endswith("_ON"):
            off_cmds.append(cmd.replace("_ON", "_OFF"))

    if off_cmds:
        _send_commands(off_cmds, cfg)


# ── Generar respuesta en español ─────────────────────────────

def _build_response(executed: list[str], cfg: dict) -> str:
    """Genera una frase en español describiendo qué se hizo."""
    if not executed:
        return "No se ejecutó ningún comando."

    names   = _device_name_map(cfg)
    all_on  = cfg.get("cmd_all_on",  "TODOS_ON")
    all_off = cfg.get("cmd_all_off", "TODOS_OFF")

    encendidos = []
    apagados   = []

    for cmd in executed:
        if cmd == all_on:
            encendidos = ["todos los focos"]
            break
        elif cmd == all_off:
            apagados = ["todos los focos"]
            break
        elif cmd.endswith("_ON"):
            encendidos.append(names.get(cmd, cmd))
        elif cmd.endswith("_OFF"):
            apagados.append(names.get(cmd, cmd))

    frases = []

    if encendidos:
        if encendidos == ["todos los focos"]:
            sujeto, verbo = "todos los focos", "han sido encendidos"
        elif len(encendidos) == 1:
            sujeto, verbo = encendidos[0], "ha sido encendido"
        else:
            sujeto = ", ".join(encendidos[:-1]) + " y " + encendidos[-1]
            verbo  = "han sido encendidos"
        frases.append(f"{sujeto.capitalize()} {verbo} correctamente.")

    if apagados:
        if apagados == ["todos los focos"]:
            sujeto, verbo = "todos los focos", "han sido apagados"
        elif len(apagados) == 1:
            sujeto, verbo = apagados[0], "ha sido apagado"
        else:
            sujeto = ", ".join(apagados[:-1]) + " y " + apagados[-1]
            verbo  = "han sido apagados"
        frases.append(f"{sujeto.capitalize()} {verbo} correctamente.")

    return " ".join(frases) if frases else "Comando ejecutado correctamente."


# ── Parseo de tiempo ─────────────────────────────────────────

def _parse_duration(text: str) -> tuple[int | None, str]:
    """
    Extrae duración en segundos del texto y retorna (segundos, texto_limpio).
    El texto limpio es el texto sin la expresión de tiempo.
    """
    pattern = re.compile(
        r"(?:durante|por|en)?\s*(\d+)\s*(segundo|segundos|seg|minuto|minutos|min)\b",
        re.IGNORECASE,
    )

    match = pattern.search(text)
    if match:
        value = int(match.group(1))
        unit  = match.group(2).lower()
        if "minuto" in unit or unit == "min":
            value *= 60

        # Eliminar la expresión de tiempo del texto
        clean = pattern.sub("", text).strip()
        clean = re.sub(r"\s+", " ", clean).strip()

        print(f"[IoT] Tiempo detectado: {value} segundos")
        return value, clean

    # Buscar "por X" sin unidad (asume segundos)
    match2 = re.search(r"por\s+(\d+)\b", text)
    if match2:
        val = int(match2.group(1))
        clean = re.sub(r"por\s+\d+", "", text).strip()
        return val, clean

    return None, text


# ── Detección de intención con Gemini ────────────────────────

def _detect_iot_intent(description: str, cfg: dict) -> list[str]:
    """
    Usa Gemini para interpretar un comando de lenguaje natural
    y devolver la lista de comandos Arduino a ejecutar.
    """
    import google.generativeai as genai

    genai.configure(api_key=get_api_key())
    model = genai.GenerativeModel("gemini-2.5-flash-lite")

    # Build device list for prompt
    device_lines = []
    for dev in cfg.get("devices", {}).values():
        device_lines.append(
            f"  {dev['cmd_on']}  -> turn on {dev['name']}\n"
            f"  {dev['cmd_off']} -> turn off {dev['name']}"
        )
    device_str = "\n".join(device_lines)

    all_on  = cfg.get("cmd_all_on",  "TODOS_ON")
    all_off = cfg.get("cmd_all_off", "TODOS_OFF")

    prompt = f"""You are an IoT command interpreter for a home automation system.
The user controls electrical lights (focos) connected to an Arduino.

Available commands:
{device_str}
  {all_on}   -> turn on all lights
  {all_off}  -> turn off all lights

The user said (in Spanish): "{description}"

Rules:
- Return ONLY the Arduino commands to execute, separated by commas.
- If the user wants to turn on a light, use the _ON command.
- If the user wants to turn off a light, use the _OFF command.
- If the user says "all", "todos", or refers to all lights, use {all_on} or {all_off}.
- If the context implies needing light (e.g. "it's dark", "I can't see"), use {all_on}.
- If the context implies too much light (e.g. "too bright"), use {all_off}.
- Return ONLY the commands. No explanation, no markdown, no extra text.
- If you cannot determine the intent, return: UNKNOWN

Examples:
  "enciende el foco 1"          -> FOCO1_ON
  "apaga todo"                  -> {all_off}
  "prende el foco 1 y el foco 2" -> FOCO1_ON, FOCO2_ON
  "está muy oscuro"             -> {all_on}
  "apaga el foco 2"             -> FOCO2_OFF
"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip().upper()
        text = re.sub(r"```(?:\w+)?", "", text).strip().rstrip("`").strip()

        if "UNKNOWN" in text or "DESCONOCIDO" in text:
            return []

        commands = [c.strip() for c in text.replace("\n", ",").split(",") if c.strip()]
        valid    = _get_valid_commands(cfg)
        return [c for c in commands if c in valid]

    except Exception as e:
        print(f"[IoT] Error en detección de intención: {e}")
        return []


# ── Operación temporizada (hilo separado) ────────────────────

def _timed_operation(commands_on: list[str], duration: int, cfg: dict,
                     speak=None):
    """Ejecuta apagado automático después de `duration` segundos."""
    def _worker():
        if speak:
            if duration >= 60:
                mins = duration // 60
                speak(f"Se apagarán automáticamente en {mins} minuto{'s' if mins > 1 else ''}.")
            else:
                unit = "segundo" if duration == 1 else "segundos"
                speak(f"Se apagarán automáticamente en {duration} {unit}.")

        time.sleep(duration)
        _auto_off(commands_on, cfg)
        print(f"[IoT] Apagado automático completado ({duration}s)")

        if speak:
            speak("Focos apagados automáticamente, señor.")

    thread = threading.Thread(target=_worker, daemon=True, name="IoT-AutoOff")
    thread.start()


# ══════════════════════════════════════════════════════════════
#  FUNCIÓN PRINCIPAL — punto de entrada para O.R.I.O.N
# ══════════════════════════════════════════════════════════════

def iot_control(parameters: dict, player=None, speak=None) -> str:
    """
    Controla dispositivos IoT conectados al Arduino.

    Parámetros:
        action      : "on" | "off" | "all_on" | "all_off"
                      | "timed" | "status" | "auto" (default: "auto")
        device      : "foco_1" | "foco_2" | "all"
        duration    : int (segundos, para operación temporizada)
        description : str (comando en lenguaje natural para modo "auto")
    """
    if not _SERIAL_OK:
        return ("El módulo 'pyserial' no está instalado. "
                "Ejecuta: pip install pyserial")

    action      = (parameters.get("action") or "auto").lower().strip()
    device      = (parameters.get("device") or "").lower().strip()
    duration    = parameters.get("duration")
    description = parameters.get("description", "").strip()

    cfg = _load_iot_config()

    log = f"[IoT] action={action} device={device} duration={duration}"
    print(log)
    if player:
        player.write_log(log)

    # ── Acción: status ────────────────────────────────────────
    if action == "status":
        conn = _get_serial()
        if conn and conn.is_open:
            port      = cfg.get("serial_port", "?")
            n_devices = len(cfg.get("devices", {}))
            return (f"Arduino conectado en {port}. "
                    f"{n_devices} dispositivo(s) configurados.")
        return "Arduino no conectado. Verifica el puerto y la conexión."

    # ── Acción: auto (reglas manuales → IA) ───────────────────
    if action == "auto":
        if not description:
            return "No se proporcionó descripción del comando IoT."

        # Normalizar texto
        normalized = _normalize_text(description)

        # Detectar duración y limpiar texto
        parsed_duration, clean_text = _parse_duration(normalized)

        # Intentar con reglas manuales primero (más rápido, sin API)
        commands = _manual_rules(clean_text, cfg)

        # Si no hubo match, usar Gemini
        if commands is None:
            print("[IoT] Sin regla manual, consultando Gemini...")
            commands = _detect_iot_intent(clean_text, cfg)

        if not commands:
            return ("No pude interpretar la orden IoT. "
                    "Intente especificar qué foco encender o apagar.")

        executed, errs = _send_commands(commands, cfg)

        if errs and not executed:
            return f"Error al ejecutar: {'; '.join(errs)}"

        response = _build_response(executed, cfg)

        # Operación temporizada si se detectó duración
        use_duration = parsed_duration or (int(duration) if duration else None)
        if use_duration and any(
            c.endswith("_ON") or c == cfg.get("cmd_all_on") for c in executed
        ):
            _timed_operation(executed, use_duration, cfg, speak=speak)
            unit = "segundo" if use_duration == 1 else "segundos"
            response += f" Se apagarán automáticamente en {use_duration} {unit}."

        return response

    # ── Acción: on / off ──────────────────────────────────────
    commands_to_send = []

    if action in ("on", "off"):
        if not device:
            return "Debes especificar qué dispositivo controlar."

        if device == "all":
            cmd = cfg.get("cmd_all_on") if action == "on" else cfg.get("cmd_all_off")
            commands_to_send.append(cmd)
        else:
            dev_cfg = cfg.get("devices", {}).get(device)
            if not dev_cfg:
                available = ", ".join(cfg.get("devices", {}).keys())
                return f"Dispositivo '{device}' no encontrado. Disponibles: {available}"
            cmd = dev_cfg["cmd_on"] if action == "on" else dev_cfg["cmd_off"]
            commands_to_send.append(cmd)

    elif action == "all_on":
        commands_to_send.append(cfg.get("cmd_all_on", "TODOS_ON"))

    elif action == "all_off":
        commands_to_send.append(cfg.get("cmd_all_off", "TODOS_OFF"))

    elif action == "timed":
        if not device:
            device = "all"
        if not duration:
            duration = 30  # Default 30 segundos

        if device == "all":
            commands_to_send.append(cfg.get("cmd_all_on", "TODOS_ON"))
        else:
            dev_cfg = cfg.get("devices", {}).get(device)
            if not dev_cfg:
                return f"Dispositivo '{device}' no encontrado."
            commands_to_send.append(dev_cfg["cmd_on"])

    else:
        return (f"Acción IoT desconocida: '{action}'. "
                "Use: on, off, all_on, all_off, timed, auto, status")

    # ── Ejecutar ──────────────────────────────────────────────
    executed, errs = _send_commands(commands_to_send, cfg)

    if errs and not executed:
        return f"Error: {'; '.join(errs)}"

    response = _build_response(executed, cfg)

    # Temporizado
    if action == "timed" and executed:
        dur = int(duration) if duration else 30
        _timed_operation(executed, dur, cfg, speak=speak)
        unit = "segundo" if dur == 1 else "segundos"
        response += f" Se apagarán automáticamente en {dur} {unit}."

    elif duration and executed:
        dur = int(duration)
        _timed_operation(executed, dur, cfg, speak=speak)
        unit = "segundo" if dur == 1 else "segundos"
        response += f" Se apagarán automáticamente en {dur} {unit}."

    return response
