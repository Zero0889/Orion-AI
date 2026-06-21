"""
actions.iot.rules — Interpretación de comandos en lenguaje natural
===================================================================
Primero intenta resolver con reglas locales (rápido, sin llamar a Gemini)
y si no hay coincidencia clara, delega al modelo. Es la evolución del
``_manual_rules`` / ``_detect_iot_intent`` del antiguo ``iot.py``,
extendido para entender dimming, color y escenas.

Cada función pura aquí es testeable sin Arduino ni red.
"""

from __future__ import annotations

import json
import re

from .config import IoTConfig
from .devices import Device

# ── Normalización de texto (números en palabras, ruido del STT) ─────────────

_NUM_WORDS = {
    r"\buno\b": "1",
    r"\buna\b": "1",
    r"\bun\b": "1",
    r"\bdos\b": "2",
    r"\btres\b": "3",
    r"\bcuatro\b": "4",
    r"\bcinco\b": "5",
    r"\bseis\b": "6",
    r"\bsiete\b": "7",
    r"\bocho\b": "8",
    r"\bnueve\b": "9",
    r"\bdiez\b": "10",
    r"\bonce\b": "11",
    r"\bdoce\b": "12",
    r"\bquince\b": "15",
    r"\bveinte\b": "20",
    r"\btreinta\b": "30",
    r"\bcuarenta\b": "40",
    r"\bcincuenta\b": "50",
    r"\bsesenta\b": "60",
    r"\bsetenta\b": "70",
    r"\bochenta\b": "80",
    r"\bnoventa\b": "90",
    r"\bcien\b": "100",
}


def normalize(text: str) -> str:
    """Limpieza ligera para que las reglas locales tengan más chance."""
    text = (text or "").lower().strip()
    # Errores típicos del STT con "segundos"
    text = text.replace("segun2", "segundos")
    text = text.replace("segun dos", "segundos")
    for pat, num in _NUM_WORDS.items():
        text = re.sub(pat, num, text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── Parseo de duración (existía en v1, se conserva) ─────────────────────────

_DUR_RE = re.compile(
    r"(?:durante|por|en)?\s*(\d+)\s*(segundo|segundos|seg|minuto|minutos|min|hora|horas|h)\b",
    re.IGNORECASE,
)


def parse_duration(text: str) -> tuple[int | None, str]:
    """Extrae duración en SEGUNDOS y devuelve (segundos, texto_sin_duración)."""
    m = _DUR_RE.search(text)
    if not m:
        return None, text
    n = int(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("min"):
        n *= 60
    elif unit.startswith("h"):
        n *= 3600
    clean = _DUR_RE.sub("", text).strip()
    clean = re.sub(r"\s+", " ", clean).strip()
    return n, clean


# ── Parseo de porcentaje (para dimming) ─────────────────────────────────────

_PCT_RE = re.compile(r"\b(\d{1,3})\s*%")
_AT_LEVEL_RE = re.compile(r"\bal\s+(\d{1,3})\b")  # "pon el foco al 30"


def parse_percent(text: str) -> int | None:
    """Devuelve el primer porcentaje 0-100 que encuentre, o None."""
    for pattern in (_PCT_RE, _AT_LEVEL_RE):
        m = pattern.search(text)
        if m:
            v = int(m.group(1))
            if 0 <= v <= 100:
                return v
    return None


# ── Parseo de color (palabras + hex) ────────────────────────────────────────

_COLOR_WORDS: dict[str, tuple[int, int, int]] = {
    "blanco": (255, 255, 255),
    "negro": (0, 0, 0),
    "rojo": (255, 0, 0),
    "verde": (0, 255, 0),
    "azul": (0, 0, 255),
    "amarillo": (255, 255, 0),
    "cian": (0, 255, 255),
    "magenta": (255, 0, 255),
    "rosa": (255, 105, 180),
    "naranja": (255, 140, 0),
    "morado": (128, 0, 128),
    "violeta": (148, 0, 211),
    "turquesa": (64, 224, 208),
    "lima": (50, 205, 50),
    "celeste": (135, 206, 235),
    "ambar": (255, 191, 0),
    "ámbar": (255, 191, 0),
    "calido": (255, 197, 143),
    "cálido": (255, 197, 143),
    "frio": (180, 220, 255),
    "frío": (180, 220, 255),
}

_HEX_RE = re.compile(r"#?([0-9a-f]{6})\b", re.IGNORECASE)


def parse_color(text: str) -> tuple[int, int, int] | None:
    """Devuelve (r,g,b) si encuentra un color claro en el texto."""
    t = text.lower()
    for word, rgb in _COLOR_WORDS.items():
        if word in t:
            return rgb
    m = _HEX_RE.search(t)
    if m:
        hex_s = m.group(1)
        return (
            int(hex_s[0:2], 16),
            int(hex_s[2:4], 16),
            int(hex_s[4:6], 16),
        )
    return None


# ── Reglas globales (todo on/off) ───────────────────────────────────────────

_ALL_OFF_PHRASES = [
    "mucha luz",
    "demasiada luz",
    "mucho brillo",
    "ya hay luz",
    "no necesito luz",
    "suficiente luz",
    "apaga todo",
    "apaga todos",
    "apaga los focos",
    "apagame todo",
    "apagame los focos",
    "apaga la luz",
    "apaga las luces",
]

_ALL_ON_PHRASES = [
    "esta oscuro",
    "está oscuro",
    "falta luz",
    "necesito luz",
    "hay poca luz",
    "poca luz",
    "muy oscuro",
    "no veo nada",
    "no se ve",
    "no se ve nada",
    "prende todo",
    "prende todos",
    "prende los focos",
    "enciende todo",
    "enciende todos",
    "enciende los focos",
    "prendeme todo",
    "prendeme todos",
    "prendeme los focos",
    "enciendeme todo",
    "enciendeme todos",
    "prende la luz",
    "prende las luces",
    "enciende la luz",
    "enciende las luces",
]


# ── Resolución de dispositivo individual ────────────────────────────────────


def find_device(text: str, cfg: IoTConfig) -> Device | None:
    """Busca el dispositivo más probable mencionado en el texto.

    Estrategia en 2 pasadas:

    1. Match por ``name`` completo o ``id`` (substring, case-insensitive).
       Si hay varias coincidencias, gana la más larga (más específica).
       Esto cubre "foco 1", "tira led", "temp_sala", etc.

    2. Si nada matcheó, intentar la **primera palabra** del nombre como
       alias — pero SOLO si esa palabra es única entre todos los
       dispositivos. Esto deja que el usuario diga "tira" en lugar de
       "tira led" sin que "foco" matche por accidente (porque hay varios
       dispositivos cuyo nombre empieza por "foco").
    """
    t = (text or "").lower()

    # ── Pasada 1: nombre/id completo ──
    best: Device | None = None
    best_len = 0
    for dev in cfg.devices.values():
        for needle in (dev.name.lower(), dev.id.lower()):
            if needle and needle in t and len(needle) > best_len:
                best = dev
                best_len = len(needle)
    if best is not None:
        return best

    # ── Pasada 2: primera palabra como alias (si es única) ──
    first_word_to_dev: dict[str, Device | None] = {}
    for dev in cfg.devices.values():
        parts = dev.name.lower().split()
        if not parts:
            continue
        fw = parts[0]
        # Si ya hay otro dispositivo con la misma primera palabra → ambiguo
        if fw in first_word_to_dev:
            first_word_to_dev[fw] = None
        else:
            first_word_to_dev[fw] = dev

    for fw, dev in first_word_to_dev.items():
        if dev is None or not fw:
            continue
        if re.search(rf"\b{re.escape(fw)}\b", t):
            return dev

    return None


# ── Resultado estructurado de la interpretación ─────────────────────────────


def detect_intent_local(text: str, cfg: IoTConfig) -> dict | None:
    """Intenta resolver SIN llamar a Gemini. Devuelve un dict con la
    intención si hay match claro, o None si necesita IA.

    Formato del dict::

        {"action": "on|off|all_on|all_off|dim|rgb|scene",
         "device": "foco_1",          # opcional
         "value":  30,                 # opcional (dim)
         "color":  [255, 0, 0],        # opcional (rgb)
         "scene":  "modo_pelicula",    # opcional
         "duration": 30}               # opcional (segundos)
    """
    t = normalize(text)

    # Escenas — match exacto o por nombre
    for sid, sdata in cfg.scenes.items():
        names = [sid.lower(), sdata.get("name", "").lower()]
        if any(n and n in t for n in names if len(n) >= 3):
            return {"action": "scene", "scene": sid}

    # Apagar/encender TODO
    for phrase in _ALL_OFF_PHRASES:
        if phrase in t:
            return {"action": "all_off"}
    for phrase in _ALL_ON_PHRASES:
        if phrase in t:
            duration, _ = parse_duration(t)
            return {"action": "all_on", "duration": duration}

    dev = find_device(t, cfg)
    if not dev:
        return None

    # Color → rgb (necesita capability)
    color = parse_color(t)
    if color and dev.capabilities.rgb:
        return {"action": "rgb", "device": dev.id, "color": list(color)}

    # Porcentaje → dim (necesita capability dimmable)
    pct = parse_percent(t)
    if pct is not None and dev.capabilities.dimmable:
        return {"action": "dim", "device": dev.id, "value": pct}

    # Encender/apagar simple
    if any(w in t for w in ("apaga", "apagar", "apagame")):
        return {"action": "off", "device": dev.id}
    if any(w in t for w in ("prende", "enciende", "encender", "prendeme")):
        duration, _ = parse_duration(t)
        return {"action": "on", "device": dev.id, "duration": duration}

    return None


# ── Fallback con Gemini ─────────────────────────────────────────────────────


def detect_intent_with_gemini(text: str, cfg: IoTConfig) -> dict | None:
    """Pregunta a Gemini cuando las reglas locales no decidieron. Devuelve
    el mismo formato de dict que :func:`detect_intent_local`, o None.
    """
    from orion.core import gemini  # import lazy: tests sin red no lo necesitan

    devices_desc = []
    for dev in cfg.devices.values():
        caps = []
        if dev.capabilities.on_off:
            caps.append("on/off")
        if dev.capabilities.dimmable:
            caps.append("dim")
        if dev.capabilities.rgb:
            caps.append("rgb")
        if dev.capabilities.sensor:
            caps.append(f"sensor:{dev.capabilities.sensor}")
        devices_desc.append(f'  - id="{dev.id}" name="{dev.name}" caps=[{", ".join(caps)}]')

    scenes_desc = [f'  - id="{sid}" name="{s.get("name", sid)}"' for sid, s in cfg.scenes.items()]

    prompt = f"""You interpret natural-language IoT commands (Spanish or English)
into a JSON action plan for a home automation system.

Available devices:
{chr(10).join(devices_desc) or "  (none)"}

Available scenes:
{chr(10).join(scenes_desc) or "  (none)"}

User said: "{text}"

Return EXACTLY one JSON object with these possible shapes (no markdown, no extra text):
  {{"action":"on",      "device":"<id>"[,"duration": <seconds>]}}
  {{"action":"off",     "device":"<id>"}}
  {{"action":"all_on" [,"duration": <seconds>]}}
  {{"action":"all_off"}}
  {{"action":"dim",     "device":"<id>", "value": <0-100>}}
  {{"action":"rgb",     "device":"<id>", "color":[<r>,<g>,<b>]}}
  {{"action":"scene",   "scene":"<scene_id>"}}
  {{"action":"unknown"}}

Rules:
- "dim" is ONLY valid if the device's caps include "dim". If not, fall back to "on" or "unknown".
- "rgb" is ONLY valid if the device's caps include "rgb".
- "device" and "scene" must be exact ids from the lists above.
- If the user implies needing light without naming a device, return all_on.
"""

    try:
        raw = gemini.generate_text(prompt, model=gemini.FLASH_LITE)
    except Exception as e:
        print(f"[IoT-Rules] Gemini falló: {e}")
        return None

    # Limpiamos posibles fences ```json
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[IoT-Rules] Respuesta no-JSON de Gemini: {raw[:120]!r}")
        return None

    if result.get("action") in (None, "unknown"):
        return None
    return result
