"""
actions.proteus_autodraw — Automatización de Proteus 8 vía pyautogui.

Toma un archivo SPICE (.cir) generado por :mod:`actions.circuit_from_image`
(y opcionalmente su JSON sidecar) y, en Proteus 8 Schematic Capture:

  1. **Pick Devices** → agrega componentes únicos al panel DEVICES.
  2. **Component Mode** → coloca cada componente en una grilla del canvas.
  3. **Terminals Mode** → coloca terminales (GROUND, POWER, IN, OUT…).
  4. **Virtual Instruments Mode** → coloca osciloscopios, voltímetros, etc.
  5. **Selection Mode** → deja el cursor en modo selección al terminar.

Optimizaciones clave
--------------------
- Los componentes con la misma librería (ej. 5 resistencias RES) se
  buscan UNA sola vez en Pick Devices, no una por instancia.
- Cambio de modo (Component / Terminals / Virtual Instruments) por click
  en el icono correspondiente de la sidebar izquierda, en coordenadas
  relativas a la ventana de Proteus detectada.

Datos de entrada
----------------
Si existe un archivo ``<base>.circuit.json`` al lado del ``.cir`` con la
estructura completa que devolvió Gemini (incluyendo ``terminals`` e
``instruments``), lo usamos. Si no, parseamos el ``.cir`` y solo
colocamos componentes (no terminals ni instruments).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any
import contextlib

# ── Mapeo SPICE → librería Proteus ─────────────────────────────────────
#
# Notas de selección:
#   - V → VSOURCE (no BATTERY): VSOURCE es la fuente DC genérica que
#     Proteus simula. BATTERY tiene parámetros internos y es más
#     restrictiva.
#   - I → CSOURCE (no CCS): CSOURCE es la fuente de corriente DC.
#   - D / Q / M: si Gemini detectó un modelo específico en el .cir lo
#     usamos textual (1N4148, 2N3904, IRF540). Si no, default.
_PROTEUS_LIBNAME = {
    "R": "RES",
    "C": "CAP",
    "L": "INDUCTOR",
    "D": "1N4148",
    "Q": "2N3904",
    "M": "IRF540",
    "U": "LM358",
    "X": "LM358",
    "V": "VSOURCE",
    "I": "CSOURCE",
    "S": "SW-SPST",
}

# Márgenes default del canvas (px) restados al rect de la ventana
_CANVAS_MARGINS_DEFAULT = {"top": 180, "left": 175, "right": 30, "bottom": 50}

# Posición del panel lateral (DEVICES / INSTRUMENTS / TERMINALS).
# Coordenadas relativas al rect de la ventana de Proteus 8 Pro.
_PANEL = {
    "x_offset_left": 80,  # centro horizontal de la lista
    "y_start": 270,  # centro vertical de la PRIMERA fila
    "row_height": 19,  # alto típico de cada fila
}

# Sidebar izquierda (columna de modos). El icono de "selection" está
# arriba del todo; "component" debajo; "terminals" en el medio;
# "virtual_instruments" más abajo. Coordenadas validadas con
# screenshots del usuario en Proteus 8 Pro maximizado.
_SIDEBAR = {
    "x": 18,  # x absoluto desde el borde izquierdo de la ventana
    "y_first": 156,  # y del primer icono (selection)
    "icon_height": 30,  # alto típico de cada icono
    "modes": {
        "selection": 0,
        "component": 1,
        "junction_dot": 2,
        "wire_label": 3,
        "text_script": 4,
        "buses": 5,
        "subcircuits": 6,
        "terminals": 7,
        "device_pins": 8,
        "graph": 9,
        "tape_recorder": 10,
        "generator": 11,
        "probe": 12,
        "virtual_instruments": 13,
    },
}

# Mapeo: tipo lógico (del JSON de Gemini) → idx en el panel TERMINALS.
# El idx es la fila 0-based dentro del panel cuando estás en Terminals Mode.
_TERMINAL_PANEL_IDX = {
    "default": 0,
    "input": 1,
    "in": 1,
    "output": 2,
    "out": 2,
    "bidir": 3,
    "power": 4,
    "vcc": 4,
    "vdd": 4,
    "ground": 5,
    "gnd": 5,
    "chassis": 6,
    "dynamic": 7,
    "bus": 8,
    "nc": 9,
}

# Mapeo: tipo lógico → idx en el panel INSTRUMENTS.
_INSTRUMENT_PANEL_IDX = {
    "oscilloscope": 0,
    "logic_analyser": 1,
    "logic_analyzer": 1,
    "counter_timer": 2,
    "virtual_terminal": 3,
    "spi_debugger": 4,
    "i2c_debugger": 5,
    "signal_generator": 6,
    "pattern_generator": 7,
    "dc_voltmeter": 8,
    "dc_ammeter": 9,
    "ac_voltmeter": 10,
    "ac_ammeter": 11,
    "wattmeter": 12,
}


# ── Parser SPICE (fallback si no hay JSON sidecar) ─────────────────────


def _parse_cir(cir_path: Path) -> list[dict[str, Any]]:
    """Extrae refdes + nombre de librería Proteus por línea SPICE."""
    components: list[dict[str, Any]] = []
    for raw in cir_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("*") or line.startswith("."):
            continue
        tokens = line.split()
        if not tokens:
            continue
        refdes = tokens[0]
        kind = refdes[0].upper()
        if kind not in _PROTEUS_LIBNAME:
            continue

        last = tokens[-1] if len(tokens) > 1 else ""
        looks_like_model = bool(re.match(r"^[A-Za-z][\w-]*$", last)) and last.upper() not in (
            "DC",
            "AC",
        )
        proteus_name = (
            last if looks_like_model and kind in ("D", "Q", "M", "X") else _PROTEUS_LIBNAME[kind]
        )

        components.append(
            {
                "refdes": refdes,
                "kind": kind,
                "lib_name": proteus_name,
            }
        )
    return components


def _read_circuit_sidecar(cir_path: Path) -> dict[str, Any] | None:
    """Devuelve el dict del JSON sidecar (<base>.circuit.json) si existe."""
    sidecar = cir_path.with_suffix(".circuit.json")
    if not sidecar.exists():
        return None
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[proteus_autodraw] JSON sidecar inválido ({sidecar.name}): {e}")
        return None


# Catálogo: tipo del JSON de Gemini → (prefijo refdes, librería Proteus,
# usar `value` como librería si está presente).
#
# Cuando ``use_value=True`` y Gemini detectó un modelo concreto (ej.
# "2N2222", "1N4007", "BC547"), pisamos el default. Útil para diodos
# y transistores donde el modelo importa.
_GEMINI_TO_PROTEUS: dict[str, tuple[str, str, bool]] = {
    # ── Pasivos ─────────────────────────────────────────────
    "resistor": ("R", "RES", False),
    "potentiometer": ("RV", "POT-LIN", False),
    "ldr": ("LDR", "LDR", False),
    "thermistor": ("TH", "NTC", False),
    "capacitor": ("C", "CAP", False),
    "capacitor_polarized": ("C", "CAP-ELEC", False),
    "capacitor_electrolytic": ("C", "CAP-ELEC", False),
    "inductor": ("L", "INDUCTOR", False),
    "transformer": ("TR", "TRAN-2P3S", False),
    "crystal": ("X", "CRYSTAL", False),
    # ── Diodos ──────────────────────────────────────────────
    "diode": ("D", "1N4148", True),
    "diode_zener": ("D", "1N4733A", True),
    "diode_rectifier": ("D", "1N4007", True),
    "diode_schottky": ("D", "1N5817", True),
    "led": ("D", "LED-RED", False),
    "bridge_rectifier": ("BR", "BRIDGE", False),
    # ── Transistores ────────────────────────────────────────
    "bjt_npn": ("Q", "2N3904", True),
    "bjt_pnp": ("Q", "2N3906", True),
    "nmos": ("M", "IRF540", True),
    "pmos": ("M", "IRF9540", True),
    # ── ICs ─────────────────────────────────────────────────
    "opamp": ("U", "LM358", False),
    "timer_555": ("U", "NE555", False),
    "regulator_7805": ("U", "7805", False),
    "regulator_7812": ("U", "7812", False),
    "regulator_7905": ("U", "7905", False),
    "regulator_lm317": ("U", "LM317", False),
    # ── Fuentes ─────────────────────────────────────────────
    "vsource": ("V", "VSOURCE", False),
    "vsource_dc": ("V", "VSOURCE", False),
    "vsource_ac": ("V", "VSINE", False),
    "vsine": ("V", "VSINE", False),
    "isource": ("I", "CSOURCE", False),
    "isource_dc": ("I", "CSOURCE", False),
    # ── Switches y entrada ──────────────────────────────────
    "switch": ("S", "SW-SPST", False),
    "switch_spdt": ("S", "SW-SPDT", False),
    "button": ("SW", "BUTTON", False),
    "relay": ("RL", "G2RL-1", False),
    # ── Salida / actuadores ─────────────────────────────────
    "buzzer": ("BUZ", "BUZZER", False),
    "speaker": ("LS", "SPEAKER", False),
    "motor_dc": ("M", "MOTOR-DC", False),
    "microphone": ("MIC", "MIC", False),
    "seven_segment": ("DSP", "7SEG-COM-CAT", False),
}


def _components_from_circuit(circuit: dict[str, Any]) -> list[dict[str, Any]]:
    """Convierte la lista de components del JSON de Gemini al formato
    que usa este módulo (refdes + lib_name de Proteus).

    Tipos no reconocidos se ignoran silenciosamente (mejor que fallar:
    el resto del circuito sí se coloca).
    """
    out: list[dict[str, Any]] = []
    counters: dict[str, int] = {}
    for c in circuit.get("components") or []:
        ctype = (c.get("type") or "").lower().strip()
        value = (c.get("value") or "").strip()

        entry = _GEMINI_TO_PROTEUS.get(ctype)
        if entry is None:
            continue
        kind, default_lib, use_value = entry

        lib = (
            value
            if (use_value and value and re.match(r"^[A-Za-z0-9][\w-]*$", value))
            else default_lib
        )

        counters[kind] = counters.get(kind, 0) + 1
        refdes = c.get("id") or f"{kind}{counters[kind]}"
        out.append({"refdes": refdes, "kind": kind, "lib_name": lib})
    return out


# ── pyautogui + window detection ───────────────────────────────────────


def _require_pyautogui():
    try:
        import pyautogui

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05
        return pyautogui
    except ImportError as e:
        raise RuntimeError("pyautogui no está instalado. Ejecuta: pip install pyautogui") from e


def _proteus_window(pyautogui_) -> tuple[int, int, int, int] | None:
    try:
        get = pyautogui_.getWindowsWithTitle
    except AttributeError:
        return None
    for hint in ("Proteus 8", "Proteus", "Schematic Capture"):
        try:
            wins = get(hint)
        except Exception:
            continue
        for w in wins:
            try:
                if w.width > 200 and w.height > 200:
                    return (w.left, w.top, w.left + w.width, w.top + w.height)
            except Exception:
                continue
    return None


def _canvas_bounds(
    pyautogui_,
    margins: dict[str, int] | None = None,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int] | None, bool]:
    """Devuelve ``(canvas_rect, window_rect, located)``."""
    m = {**_CANVAS_MARGINS_DEFAULT, **(margins or {})}
    win = _proteus_window(pyautogui_)
    if win is not None:
        l, t, r, b = win
        canvas = (l + m["left"], t + m["top"], r - m["right"], b - m["bottom"])
        return canvas, win, True
    sw, sh = pyautogui_.size()
    return (m["left"], m["top"], sw - m["right"], sh - m["bottom"]), None, False


def _panel_position(
    window_rect: tuple[int, int, int, int],
    index: int,
    *,
    custom: dict[str, int] | None = None,
) -> tuple[int, int]:
    cfg = {**_PANEL, **(custom or {})}
    l, t, _, _ = window_rect
    return (l + cfg["x_offset_left"], t + cfg["y_start"] + index * cfg["row_height"])


def _sidebar_position(window_rect: tuple[int, int, int, int], mode: str) -> tuple[int, int] | None:
    idx = _SIDEBAR["modes"].get(mode)
    if idx is None:
        return None
    l, t, _, _ = window_rect
    return (l + _SIDEBAR["x"], t + _SIDEBAR["y_first"] + idx * _SIDEBAR["icon_height"])


def _grid_positions(
    bounds: tuple[int, int, int, int],
    n: int,
    *,
    cols: int = 3,
    pad_ratio: float = 0.12,
) -> list[tuple[int, int]]:
    """Reparte ``n`` posiciones en grilla dentro del rect."""
    l, t, r, b = bounds
    w, h = r - l, b - t
    pad_x = int(w * pad_ratio)
    pad_y = int(h * pad_ratio)
    usable_l, usable_t = l + pad_x, t + pad_y
    usable_w, usable_h = w - 2 * pad_x, h - 2 * pad_y

    cols = max(1, min(cols, n))
    rows = max(1, (n + cols - 1) // cols)
    cell_w = usable_w / cols
    cell_h = usable_h / rows if rows > 1 else usable_h
    positions: list[tuple[int, int]] = []
    for i in range(n):
        r_idx, c_idx = divmod(i, cols)
        x = int(usable_l + cell_w * (c_idx + 0.5))
        y = int(usable_t + cell_h * (r_idx + 0.5))
        positions.append((x, y))
    return positions


# ── Sub-rutinas atómicas ───────────────────────────────────────────────


def _add_one_via_pick(pyautogui_, lib_name: str, *, settle: float = 0.9) -> None:
    """Añade un componente al panel DEVICES vía el dialog Pick Devices.

    Cadencia calibrada (defaults para ``settle=0.9``):
      - Abrir Pick Devices (P):           1.0 s mínimo
      - Después de escribir keywords:     1.0 s mínimo (Proteus filtra)
      - Entre los dos Enter:              0.9 s
      - Después del segundo Enter:        0.9 s
      - Después de Esc (cierra dialog):   0.9 s
    """
    # 1. Abrir Pick Devices — el dialog tarda en abrir la primera vez
    pyautogui_.press("p")
    time.sleep(max(settle, 1.0))

    # 2. Limpiar Keywords y escribir el nombre
    pyautogui_.hotkey("ctrl", "a")
    pyautogui_.press("delete")
    pyautogui_.typewrite(lib_name, interval=0.05)
    # CRÍTICO: la grilla de resultados se repuebla con debounce
    time.sleep(max(settle, 1.0))

    # 3. Confirmar búsqueda y añadir al panel
    pyautogui_.press("enter")
    time.sleep(settle)
    pyautogui_.press("enter")
    time.sleep(settle)

    # 4. Cerrar el dialog Pick Devices
    pyautogui_.press("escape")
    time.sleep(settle)


def _place_one(
    pyautogui_,
    panel_xy: tuple[int, int],
    canvas_xy: tuple[int, int],
    *,
    settle: float = 0.9,
) -> None:
    """Selecciona un item del panel lateral y lo coloca en el canvas.

    Sirve para los tres modos: Component, Terminals, Virtual Instruments.
    El flujo es idéntico — solo cambia qué panel está activo.
    """
    dx, dy = panel_xy
    cx, cy = canvas_xy

    # 1. Limpiar estado de placement previo
    pyautogui_.press("escape")
    time.sleep(settle * 0.4)

    # 2. Click simple en la fila del panel
    pyautogui_.moveTo(dx, dy, duration=0.2)
    time.sleep(0.3)
    pyautogui_.click(dx, dy)
    time.sleep(settle)

    # 3. Click preparatorio en canvas (Proteus 8 lo necesita)
    pyautogui_.moveTo(cx, cy, duration=0.3)
    time.sleep(0.3)
    pyautogui_.click(cx, cy)
    time.sleep(max(settle * 0.6, 0.6))

    # 4. Click que deposita la instancia
    pyautogui_.click(cx, cy)
    time.sleep(settle)

    # 5. Salir del modo placement
    pyautogui_.press("escape")
    time.sleep(settle * 0.6)


def _switch_mode(
    pyautogui_,
    window_rect: tuple[int, int, int, int],
    mode: str,
    *,
    settle: float = 1.0,
) -> bool:
    """Cambia el modo de Proteus clickeando el icono de la sidebar.

    Devuelve True si encontró las coordenadas y clickeó, False si el
    modo no está mapeado.
    """
    xy = _sidebar_position(window_rect, mode)
    if xy is None:
        return False
    pyautogui_.moveTo(xy[0], xy[1], duration=0.2)
    time.sleep(0.3)
    pyautogui_.click(xy[0], xy[1])
    time.sleep(settle)
    return True


# ── Helpers de planificación ───────────────────────────────────────────


def _dedupe_libs(components: list[dict[str, Any]]) -> tuple[list[str], list[int]]:
    """Devuelve ``(unique_libs, comp_to_panel_idx)``.

    ``unique_libs`` está en orden de primera aparición (= orden en el panel
    DEVICES tras la fase de añadido). ``comp_to_panel_idx[i]`` es la fila
    del panel donde está la librería del componente ``i``.
    """
    seen: dict[str, int] = {}
    unique: list[str] = []
    mapping: list[int] = []
    for c in components:
        lib = c["lib_name"]
        if lib not in seen:
            seen[lib] = len(unique)
            unique.append(lib)
        mapping.append(seen[lib])
    return unique, mapping


# ── Handler público ────────────────────────────────────────────────────


from orion.core.tool_registry import tool


@tool(
    name="proteus_autodraw",
    description=(
        "Automates Proteus 8 Schematic Capture to add the components "
        "of a previously generated SPICE netlist (.cir) into Proteus' "
        "DEVICES panel. The user must have Proteus open in Schematic "
        "Capture mode and bring it to foreground when prompted. "
        "Components are added to the panel only — the user still needs "
        "to drag them onto the canvas and wire them manually."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "cir_path": {
                "type": "STRING",
                "description": "Absolute path to the .cir file.",
            },
            "countdown": {
                "type": "INTEGER",
                "description": "Seconds before automation starts (default 3) — gives the user time to focus Proteus.",
            },
        },
        "required": ["cir_path"],
    },
    timeout=180,
)
def proteus_autodraw(parameters: dict, player=None, **_kwargs) -> str:
    """Handler invocable como tool y por el endpoint REST.

    Parámetros principales: ``cir_path``, ``countdown``, ``settle``,
    ``place_in_canvas``, ``cols``, ``canvas_margins``.
    """
    cir_path_str = (parameters.get("cir_path") or "").strip()
    if not cir_path_str:
        return "Falta el parámetro 'cir_path'."

    cir_path = Path(cir_path_str)
    if not cir_path.exists() or not cir_path.is_file():
        return f"Archivo .cir no encontrado: {cir_path_str}"
    if cir_path.suffix.lower() != ".cir":
        return f"El archivo debe ser .cir (recibido: {cir_path.suffix})."

    # Preferimos JSON sidecar (más info: terminals + instruments). Caemos
    # al parser del .cir si no existe (modo "solo componentes").
    circuit_json = _read_circuit_sidecar(cir_path)
    if circuit_json:
        components = _components_from_circuit(circuit_json)
        terminals = list(circuit_json.get("terminals") or [])
        instruments = list(circuit_json.get("instruments") or [])
        source = f"JSON sidecar ({len(terminals)} terminales, {len(instruments)} instrumentos)"
    else:
        components = _parse_cir(cir_path)
        terminals = []
        instruments = []
        source = ".cir SPICE (solo componentes)"

    if not components and not terminals and not instruments:
        return "El circuito no contiene elementos reconocibles."

    try:
        pyautogui_ = _require_pyautogui()
    except RuntimeError as e:
        return str(e)

    countdown = int(parameters.get("countdown") or 3)
    settle = float(parameters.get("settle") or 0.9)
    place_in_canvas = bool(parameters.get("place_in_canvas", True))
    cols = int(parameters.get("cols") or 3)
    margins = (
        parameters.get("canvas_margins")
        if isinstance(parameters.get("canvas_margins"), dict)
        else None
    )

    log = (
        f"[proteus_autodraw] {len(components)} comp + {len(terminals)} term + "
        f"{len(instruments)} instr desde {cir_path.name} ({source})"
    )
    print(log)
    if player and hasattr(player, "write_log"):
        with contextlib.suppress(Exception):
            player.write_log(log)

    # Countdown
    for i in range(countdown, 0, -1):
        print(f"[proteus_autodraw] empezando en {i}s — pon Proteus en foreground")
        time.sleep(1)

    # ── Setup posiciones ──────────────────────────────────────────────
    window_rect: tuple[int, int, int, int] | None = None
    window_located = True
    canvas_rect: tuple[int, int, int, int] | None = None
    if place_in_canvas:
        canvas_rect, window_rect, window_located = _canvas_bounds(pyautogui_, margins=margins)
        if window_rect is None:
            place_in_canvas = False
            print("[proteus_autodraw] ventana no localizada → solo añadir")

    # Total de items que van al canvas, para calcular grilla unificada
    total_to_place = (
        (len(components) if place_in_canvas else 0)
        + (len(terminals) if place_in_canvas and window_rect else 0)
        + (len(instruments) if place_in_canvas and window_rect else 0)
    )
    positions: list[tuple[int, int]] = (
        _grid_positions(canvas_rect, total_to_place, cols=cols)
        if (place_in_canvas and canvas_rect and total_to_place > 0)
        else []
    )

    # ── Fase 1: añadir libs únicas al panel DEVICES ───────────────────
    unique_libs, comp_to_panel_idx = _dedupe_libs(components)
    added_libs: list[str] = []
    failed: list[str] = []
    try:
        for lib in unique_libs:
            try:
                _add_one_via_pick(pyautogui_, lib, settle=settle)
                added_libs.append(lib)
            except Exception as e:
                if e.__class__.__name__ == "FailSafeException":
                    raise
                failed.append(f"Pick Devices '{lib}': {e}")
    except Exception as e:
        return (
            f"Automatización abortada en fase Pick Devices tras {len(added_libs)}/{len(unique_libs)} libs. "
            f"Razón: {e.__class__.__name__}."
        )

    pos_cursor = 0
    placed_components = 0
    placed_terminals = 0
    placed_instruments = 0

    # ── Fase 2: colocar componentes (Component Mode) ─────────────────
    if place_in_canvas and window_rect is not None and components:
        try:
            for idx, comp in enumerate(components):
                panel_idx = comp_to_panel_idx[idx]
                # Si esa librería falló en fase 1, saltamos su placement
                if panel_idx >= len(added_libs):
                    failed.append(f"{comp['refdes']}: librería no disponible")
                    pos_cursor += 1
                    continue
                panel_xy = _panel_position(window_rect, panel_idx)
                canvas_xy = positions[pos_cursor]
                pos_cursor += 1
                try:
                    _place_one(pyautogui_, panel_xy, canvas_xy, settle=settle)
                    placed_components += 1
                except Exception as e:
                    if e.__class__.__name__ == "FailSafeException":
                        raise
                    failed.append(f"placement comp {comp['refdes']}: {e}")
        except Exception as e:
            return (
                f"Automatización abortada en fase Componentes tras {placed_components}/{len(components)}. "
                f"Razón: {e.__class__.__name__}."
            )

    # ── Fase 3: colocar terminales (Terminals Mode) ──────────────────
    if place_in_canvas and window_rect is not None and terminals:
        if _switch_mode(pyautogui_, window_rect, "terminals", settle=settle):
            try:
                for term in terminals:
                    ttype = (term.get("type") or "").lower()
                    panel_idx = _TERMINAL_PANEL_IDX.get(ttype)
                    if panel_idx is None:
                        failed.append(f"terminal '{ttype}' no mapeado")
                        pos_cursor += 1
                        continue
                    panel_xy = _panel_position(window_rect, panel_idx)
                    canvas_xy = (
                        positions[pos_cursor] if pos_cursor < len(positions) else positions[-1]
                    )
                    pos_cursor += 1
                    try:
                        _place_one(pyautogui_, panel_xy, canvas_xy, settle=settle)
                        placed_terminals += 1
                    except Exception as e:
                        if e.__class__.__name__ == "FailSafeException":
                            raise
                        failed.append(f"placement terminal '{ttype}': {e}")
            except Exception as e:
                return (
                    f"Automatización abortada en fase Terminals tras {placed_terminals}/{len(terminals)}. "
                    f"Razón: {e.__class__.__name__}."
                )
        else:
            failed.append("no se pudo cambiar a Terminals Mode (icono sidebar no mapeado)")

    # ── Fase 4: colocar instrumentos (Virtual Instruments Mode) ──────
    if place_in_canvas and window_rect is not None and instruments:
        if _switch_mode(pyautogui_, window_rect, "virtual_instruments", settle=settle):
            try:
                for instr in instruments:
                    itype = (instr.get("type") or "").lower()
                    panel_idx = _INSTRUMENT_PANEL_IDX.get(itype)
                    if panel_idx is None:
                        failed.append(f"instrumento '{itype}' no mapeado")
                        pos_cursor += 1
                        continue
                    panel_xy = _panel_position(window_rect, panel_idx)
                    canvas_xy = (
                        positions[pos_cursor] if pos_cursor < len(positions) else positions[-1]
                    )
                    pos_cursor += 1
                    try:
                        _place_one(pyautogui_, panel_xy, canvas_xy, settle=settle)
                        placed_instruments += 1
                    except Exception as e:
                        if e.__class__.__name__ == "FailSafeException":
                            raise
                        failed.append(f"placement instrumento '{itype}': {e}")
            except Exception as e:
                return (
                    f"Automatización abortada en fase Instruments tras {placed_instruments}/{len(instruments)}. "
                    f"Razón: {e.__class__.__name__}."
                )
        else:
            failed.append("no se pudo cambiar a Virtual Instruments Mode")

    # ── Final: volver a selection mode ────────────────────────────────
    if place_in_canvas and window_rect is not None:
        _switch_mode(pyautogui_, window_rect, "selection", settle=settle * 0.5)

    # ── Reporte ───────────────────────────────────────────────────────
    parts: list[str] = []
    parts.append(
        f"Añadí {len(added_libs)} librerías únicas en Pick Devices "
        f"(de {len(components)} componentes)."
    )
    if place_in_canvas:
        parts.append(
            f"Coloqué {placed_components} componentes, {placed_terminals} terminales, "
            f"{placed_instruments} instrumentos."
        )
        if not window_located:
            parts.append(
                "Aviso: no detecté la ventana de Proteus por título; usé el centro de la pantalla."
            )
    if failed:
        parts.append("Avisos: " + "; ".join(failed[:5]) + (" …" if len(failed) > 5 else "") + ".")
    parts.append("Conecta las wires a mano (Fase 5 pendiente).")
    return " ".join(parts)
