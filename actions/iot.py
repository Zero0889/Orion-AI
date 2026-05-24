# iot.py — Control IoT (Arduino / LEDs) para O.R.I.O.N
# ═══════════════════════════════════════════════════════════════
# Controla dispositivos IoT (LEDs/focos) conectados por serial
# a un Arduino. Soporta encender/apagar individual o todos,
# operaciones temporizadas y detección de intención por IA.
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

def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

_BASE_DIR       = _get_base_dir()
_API_CONFIG     = _BASE_DIR / "config" / "api_keys.json"
_IOT_CONFIG     = _BASE_DIR / "config" / "iot_config.json"

# ── Configuración por defecto ────────────────────────────────

_DEFAULT_IOT_CONFIG = {
    "serial_port":  "COM2",
    "baud_rate":    9600,
    "devices": {
        "led_1": {"name": "LED 1", "cmd_on": "LED1_ON", "cmd_off": "LED1_OFF"},
        "led_2": {"name": "LED 2", "cmd_on": "LED2_ON", "cmd_off": "LED2_OFF"},
        "led_3": {"name": "LED 3", "cmd_on": "LED3_ON", "cmd_off": "LED3_OFF"},
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
    # Crear config por defecto
    _IOT_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    _IOT_CONFIG.write_text(
        json.dumps(_DEFAULT_IOT_CONFIG, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("[IoT] Archivo de configuración creado: config/iot_config.json")
    return _DEFAULT_IOT_CONFIG.copy()


def _get_api_key() -> str:
    with open(_API_CONFIG, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _get_serial() -> "serial.Serial | None":
    """Obtiene o crea la conexión serial al Arduino."""
    global _serial_conn

    if not _SERIAL_OK:
        return None

    with _serial_lock:
        if _serial_conn is not None and _serial_conn.is_open:
            return _serial_conn

        cfg = _load_iot_config()
        port = cfg.get("serial_port", "COM2")
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


# ── Enviar comandos al Arduino ───────────────────────────────

def _send_commands(commands: list[str], cfg: dict) -> tuple[list[str], list[str]]:
    """
    Envía una lista de comandos al Arduino.
    Retorna (ejecutados_ok, errores).
    """
    conn = _get_serial()
    if conn is None:
        return [], ["No se pudo conectar al Arduino."]

    valid = _get_valid_commands(cfg)
    executed = []
    errs = []

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
    all_on = cfg.get("cmd_all_on", "TODOS_ON")
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

    names = _device_name_map(cfg)
    all_on  = cfg.get("cmd_all_on",  "TODOS_ON")
    all_off = cfg.get("cmd_all_off", "TODOS_OFF")

    encendidos = []
    apagados   = []

    for cmd in executed:
        if cmd == all_on:
            encendidos = ["todos los dispositivos"]
            break
        elif cmd == all_off:
            apagados = ["todos los dispositivos"]
            break
        elif cmd.endswith("_ON"):
            encendidos.append(names.get(cmd, cmd))
        elif cmd.endswith("_OFF"):
            apagados.append(names.get(cmd, cmd))

    frases = []

    if encendidos:
        if len(encendidos) == 1:
            sujeto = encendidos[0]
            verbo  = "ha sido encendido" if sujeto != "todos los dispositivos" else "han sido encendidos"
        else:
            sujeto = ", ".join(encendidos[:-1]) + " y " + encendidos[-1]
            verbo  = "han sido encendidos"
        frases.append(f"{sujeto.capitalize()} {verbo} correctamente.")

    if apagados:
        if len(apagados) == 1:
            sujeto = apagados[0]
            verbo  = "ha sido apagado" if sujeto != "todos los dispositivos" else "han sido apagados"
        else:
            sujeto = ", ".join(apagados[:-1]) + " y " + apagados[-1]
            verbo  = "han sido apagados"
        frases.append(f"{sujeto.capitalize()} {verbo} correctamente.")

    return " ".join(frases) if frases else "Comando ejecutado correctamente."


# ── Detección de intención con Gemini ────────────────────────

def _detect_iot_intent(description: str, cfg: dict) -> list[str]:
    """
    Usa Gemini para interpretar un comando de lenguaje natural
    y devolver la lista de comandos Arduino a ejecutar.
    """
    import google.generativeai as genai

    genai.configure(api_key=_get_api_key())
    model = genai.GenerativeModel("gemini-2.5-flash-lite")

    # Build device list for prompt
    device_list = []
    for key, dev in cfg.get("devices", {}).items():
        device_list.append(f"  {dev['cmd_on']} / {dev['cmd_off']} — controls {dev['name']}")
    device_str = "\n".join(device_list)

    all_on  = cfg.get("cmd_all_on",  "TODOS_ON")
    all_off = cfg.get("cmd_all_off", "TODOS_OFF")

    prompt = f"""You are an IoT command interpreter for a home automation system.
The user controls LED lights / devices connected to an Arduino.

Available commands:
{device_str}
  {all_on} / {all_off} — controls all devices at once

The user said (possibly in Spanish or any language): "{description}"

Rules:
- Return ONLY the Arduino commands to execute, separated by commas.
- If the user wants to turn on a device, use the _ON command.
- If the user wants to turn off a device, use the _OFF command.
- If the user says "all", "todos", or refers to all devices, use {all_on} or {all_off}.
- If the context implies needing light (e.g. "it's dark", "I can't see"), use {all_on}.
- If the context implies too much light (e.g. "too bright", "turn off"), use {all_off}.
- Return ONLY the commands, no explanation, no markdown.
- If you cannot determine the intent, return: UNKNOWN

Examples:
  "enciende el led 1" -> LED1_ON
  "apaga todo" -> {all_off}
  "prende el 1 y el 3" -> LED1_ON, LED3_ON
  "está muy oscuro" -> {all_on}
"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip().upper()
        text = re.sub(r"```(?:\w+)?", "", text).strip().rstrip("`").strip()

        if "UNKNOWN" in text:
            return []

        commands = [c.strip() for c in text.replace("\n", ",").split(",") if c.strip()]
        valid = _get_valid_commands(cfg)
        return [c for c in commands if c in valid]

    except Exception as e:
        print(f"[IoT] Error en detección de intención: {e}")
        return []


# ── Parseo de tiempo ─────────────────────────────────────────

def _parse_duration(text: str) -> int | None:
    """Extrae duración en segundos del texto del usuario."""
    # Normalizar números escritos en español
    num_words = {
        "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
        "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
        "diez": 10, "quince": 15, "veinte": 20, "treinta": 30,
    }
    normalized = text.lower()
    for word, num in num_words.items():
        normalized = re.sub(rf"\b{word}\b", str(num), normalized)

    match = re.search(r"(\d+)\s*(segundo|segundos|seg|s|minuto|minutos|min|m)\b", normalized)
    if match:
        value = int(match.group(1))
        unit  = match.group(2)
        if unit.startswith("min") or unit == "m":
            value *= 60
        return value

    # Buscar pattern "por X" sin unidad (asume segundos)
    match2 = re.search(r"por\s+(\d+)\b", normalized)
    if match2:
        return int(match2.group(1))

    return None


# ── Operación temporizada (hilo separado) ────────────────────

def _timed_operation(commands_on: list[str], duration: int, cfg: dict,
                     speak=None):
    """Ejecuta apagado automático después de `duration` segundos."""
    def _worker():
        if speak:
            if duration >= 60:
            	mins = duration // 60
            	speak(f"Los dispositivos se apagarán en {mins} minuto{'s' if mins > 1 else ''}.")
            else:
            	speak(f"Los dispositivos se apagarán en {duration} segundos.")

        time.sleep(duration)
        _auto_off(commands_on, cfg)
        print(f"[IoT] Apagado automático completado ({duration}s)")

        if speak:
            speak("Los dispositivos fueron apagados automáticamente, señor.")

    thread = threading.Thread(target=_worker, daemon=True, name="IoT-AutoOff")
    thread.start()


# ══════════════════════════════════════════════════════════════
#  FUNCIÓN PRINCIPAL — punto de entrada para O.R.I.O.N
# ══════════════════════════════════════════════════════════════

def iot_control(parameters: dict, player=None, speak=None) -> str:
    """
    Controla dispositivos IoT conectados al Arduino.

    Parámetros:
        action      : "on" | "off" | "all_on" | "all_off" | "toggle"
                      | "status" | "timed" | "auto" (default: "auto")
        device      : "led_1" | "led_2" | "led_3" | "all"
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
            port = cfg.get("serial_port", "?")
            n_devices = len(cfg.get("devices", {}))
            return (f"Arduino conectado en {port}. "
                    f"{n_devices} dispositivo(s) configurados.")
        return "Arduino no conectado. Verifica el puerto y la conexión."

    # ── Acción: auto (IA interpreta) ──────────────────────────
    if action == "auto":
        if not description:
            return "No se proporcionó descripción del comando IoT."

        # Detectar duración en el texto
        parsed_duration = _parse_duration(description)

        # Detectar comandos con IA
        commands = _detect_iot_intent(description, cfg)

        if not commands:
            return ("No pude interpretar la orden IoT. "
                    "Intente especificar qué dispositivo encender o apagar.")

        executed, errs = _send_commands(commands, cfg)

        if errs and not executed:
            return f"Error al ejecutar: {'; '.join(errs)}"

        response = _build_response(executed, cfg)

        # Operación temporizada si se detectó duración
        if parsed_duration and any(c.endswith("_ON") or c in (cfg["cmd_all_on"],) for c in executed):
            _timed_operation(executed, parsed_duration, cfg, speak=speak)
            response += f" Se apagarán automáticamente en {parsed_duration} segundos."

        return response

    # ── Acción: on / off / all_on / all_off ───────────────────
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
        return f"Acción IoT desconocida: '{action}'. Use: on, off, all_on, all_off, timed, auto, status"

    # ── Ejecutar ──────────────────────────────────────────────
    executed, errs = _send_commands(commands_to_send, cfg)

    if errs and not executed:
        return f"Error: {'; '.join(errs)}"

    response = _build_response(executed, cfg)

    # Temporizado
    if action == "timed" and executed:
        dur = int(duration) if duration else 30
        _timed_operation(executed, dur, cfg, speak=speak)
        response += f" Se apagarán automáticamente en {dur} segundos."

    elif duration and executed:
        dur = int(duration)
        _timed_operation(executed, dur, cfg, speak=speak)
        response += f" Se apagarán automáticamente en {dur} segundos."

    return response
