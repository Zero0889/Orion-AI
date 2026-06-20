"""
actions.circuit_from_image — Imagen de circuito → netlist SPICE + esquemático KiCad
====================================================================================
Analiza una imagen de un circuito electrónico (foto, screenshot, esquema dibujado)
con Gemini Vision y genera dos artefactos:

  - ``<name>.cir``       — netlist Berkeley SPICE (importable a Proteus vía
                            *File → Import Section* o LTspice/ngspice).
  - ``<name>.kicad_sch`` — esquemático KiCad v6/v7 en formato S-expression,
                            abrible directamente con KiCad eeschema.

Salida del handler ``circuit_from_image(parameters, ...)``: string legible con
el resumen del circuito detectado + las rutas de los archivos generados, listo
para ser hablado por TTS o mostrado en el chat.

Reusa el patrón de :mod:`actions.file_processor` para la llamada a Gemini con
``PIL.Image`` (ver ``_process_image`` ahí). No introduce dependencias nuevas:
solo Pillow + google-genai, ambos ya en ``requirements.txt``.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
import contextlib

# ── Tipos detectables y prefijo SPICE ──────────────────────────────────
# El prefijo es el primer carácter del refdes SPICE (R1, C1, L1, D1, Q1, M1,
# V1, I1, U1). Mantenemos la convención estándar para que Proteus / ngspice
# lo entiendan sin traducción.
_SPICE_PREFIX = {
    "resistor": "R",
    "capacitor": "C",
    "inductor": "L",
    "diode": "D",
    "led": "D",
    "bjt_npn": "Q",
    "bjt_pnp": "Q",
    "nmos": "M",
    "pmos": "M",
    "opamp": "X",
    "vsource": "V",
    "isource": "I",
    "switch": "S",
    "ground": None,  # GND no se emite como componente, es una net
}

# Modelos SPICE por defecto cuando el componente requiere uno (BJT/MOSFET/diodo).
# Usamos modelos estándar de la biblioteca SPICE3 que Proteus reconoce.
_DEFAULT_MODELS = {
    "diode": "1N4148",
    "led": "LED",
    "bjt_npn": "2N3904",
    "bjt_pnp": "2N3906",
    "nmos": "IRF540",
    "pmos": "IRF9540",
}

# Símbolos KiCad por defecto (librería:símbolo). Se mapean al `lib_id` de los
# símbolos genéricos de KiCad 7 — el usuario puede reemplazarlos sin romper
# la net del esquemático.
_KICAD_SYMBOL = {
    "resistor": ("Device:R", ["~", "~"]),
    "capacitor": ("Device:C", ["~", "~"]),
    "inductor": ("Device:L", ["~", "~"]),
    "diode": ("Device:D", ["K", "A"]),
    "led": ("Device:LED", ["K", "A"]),
    "bjt_npn": ("Device:Q_NPN_BCE", ["B", "C", "E"]),
    "bjt_pnp": ("Device:Q_PNP_BCE", ["B", "C", "E"]),
    "nmos": ("Device:Q_NMOS_GSD", ["G", "S", "D"]),
    "pmos": ("Device:Q_PMOS_GSD", ["G", "S", "D"]),
    "opamp": ("Amplifier_Operational:LM358", ["+", "-", "V+", "V-", "~"]),
    "vsource": ("Simulation_SPICE:VDC", ["+", "-"]),
    "isource": ("Simulation_SPICE:IDC", ["+", "-"]),
    "switch": ("Switch:SW_Push", ["1", "2"]),
}


# ── Cliente Gemini ──────────────────────────────────────────────────────


def _gemini_client():
    """Reusa el mismo cliente que ``actions.file_processor``.

    Mantenerlo lazy evita importar el SDK cuando la action no se invoca.
    """
    from core import gemini

    return gemini.model("gemini-2.5-flash")


# ── Análisis con visión ────────────────────────────────────────────────

_VISION_PROMPT = """You are an expert electronics engineer analyzing a circuit image.

Your task: identify every component, terminal, instrument, and electrical
connection (net) in the image, then return STRICT JSON (no markdown, no
prose) in this exact shape:

{
  "title": "<short circuit name, e.g. 'RC Low-Pass Filter'>",
  "components": [
    {
      "id": "<refdes like R1, C1, U1>",
      "type": "<one of the COMPONENT TYPES listed below>",
      "value": "<value with SPICE suffix: '1k', '10nF', '4.7uH', '1N4148' for diode model, '5V DC', '5V AC 1kHz', '1mA DC'>",
      "pins": ["<net name pin1>", "<net name pin2>", ...]
    }
  ],
  "terminals": [
    {
      "id": "<label like GND1, VCC1>",
      "type": "<ground | power | input | output | bidir | bus | nc>",
      "pin": "<net name this terminal connects to>"
    }
  ],
  "instruments": [
    {
      "id": "<label like OS1, V1, A1>",
      "type": "<oscilloscope | dc_voltmeter | dc_ammeter | ac_voltmeter | ac_ammeter | wattmeter | logic_analyser | signal_generator | pattern_generator | counter_timer | virtual_terminal>",
      "pins": ["<net pin A>", "<net pin B>", ...]
    }
  ],
  "nets": ["<list of all unique net names used above>"],
  "notes": "<one short sentence about the circuit's purpose or what you noticed>"
}

COMPONENT TYPES (use these exact strings in the `type` field):
  Pasivos:
    resistor, potentiometer, ldr, thermistor,
    capacitor (ceramic/film), capacitor_polarized (electrolytic),
    inductor, transformer, crystal
  Diodos:
    diode (general purpose), diode_zener, diode_rectifier,
    diode_schottky, led, bridge_rectifier
  Transistores:
    bjt_npn, bjt_pnp, nmos, pmos
  Circuitos integrados:
    opamp, timer_555, regulator_7805, regulator_7812,
    regulator_7905, regulator_lm317
  Fuentes:
    vsource (DC), vsource_ac (AC sine), isource (DC current)
  Switches y entrada:
    switch (SPST), switch_spdt, button (momentary push), relay
  Salida / actuadores:
    buzzer, speaker, motor_dc, microphone, seven_segment

CRITICAL RULES:
1. Pin order by component type:
   - resistor/capacitor/inductor/ldr/thermistor/crystal/buzzer/speaker/motor_dc: [pin1, pin2]
   - potentiometer: [terminal1, wiper, terminal2]
   - diode (any kind)/led: [anode, cathode]
   - bridge_rectifier: [ac1, ac2, vplus, vminus]
   - vsource/vsource_ac/isource: [positive, negative]
   - bjt_npn/bjt_pnp: [base, collector, emitter]
   - nmos/pmos: [gate, drain, source]
   - opamp: [in+, in-, vcc, vee, out]
   - timer_555: [gnd, trig, out, reset, ctrl, thresh, disch, vcc]
   - regulator_7805/7812/7905: [in, gnd, out]
   - regulator_lm317: [adj, in, out]
   - switch/button/relay: [pin1, pin2] (relay: include coil pins if visible)
   - transformer: [pri1, pri2, sec1, sec2] (+ sec_center if center-tap)
   - seven_segment: [a, b, c, d, e, f, g, dp, common]
2. Use lowercase net names: 'vcc', 'vee', 'gnd', 'vin', 'vout', 'n1', 'n2'.
3. GROUND symbols (the triangle/lines pointing down) go in the `terminals`
   list with `type: "ground"`, NOT in `components`. Their `pin` is the net
   they connect to (usually 'gnd'). Same for VCC/POWER symbols → `terminals`
   with `type: "power"`.
4. If you see an oscilloscope, voltmeter, ammeter, or signal generator,
   put it in `instruments`. Do NOT put them in `components`.
5. Refdes prefixes: R, C, L, D, Q, M, U, V, I, SW. Sequential numbering.
6. Values:
   - Resistors: ohms ('1k', '4.7k', '100', '1M').
   - Capacitors: farads ('10nF', '100uF', '1pF').
   - Inductors: henries ('10uH', '1mH').
   - DC sources: '5V DC', '9V DC', '1mA DC'.
   - AC sources: '5V AC 1kHz' (amplitude + frequency).
7. If the image is NOT a circuit, return exactly: {"error": "no_circuit_detected"}

If a field has no items, return it as an empty array, e.g. `"terminals": []`.

Output ONLY the JSON object. No backticks, no prose, no leading whitespace.
"""


def _analyze_with_vision(image_path: Path) -> dict:
    """Llama a Gemini con la imagen y devuelve el dict del circuito.

    Levanta ``RuntimeError`` con mensaje claro si el SDK falla. Si Gemini
    responde con error semántico ('no_circuit_detected'), devuelve ese dict
    tal cual — quien llama decide qué decir al usuario.
    """
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("Pillow no está instalado. Ejecuta: pip install Pillow") from e

    try:
        img = Image.open(image_path)
    except Exception as e:
        raise RuntimeError(f"No se pudo abrir la imagen: {e}") from e

    model = _gemini_client()
    try:
        response = model.generate_content([_VISION_PROMPT, img])
    except Exception as e:
        raise RuntimeError(f"Gemini Vision falló: {e}") from e

    raw = (response.text or "").strip()
    # Defensivo: si el modelo igual rodea con ```json … ``` lo despegamos.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```\s*$", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Gemini devolvió JSON inválido: {e}. Respuesta cruda (primeros 300 chars): {raw[:300]}"
        ) from e

    if not isinstance(data, dict):
        raise RuntimeError("La respuesta de Gemini no es un objeto JSON.")

    return data


# ── Generadores de output ──────────────────────────────────────────────


def _to_spice(circuit: dict) -> str:
    """Emite netlist Berkeley SPICE a partir del dict de circuito.

    Las líneas siguen el formato clásico::

        R1 n1 n2 1k
        C1 n2 gnd 10nF
        V1 vcc gnd DC 5
        D1 a k 1N4148
        Q1 b c e 2N3904
        .end

    Proteus importa esto sin problema vía *File → Import Section* — el parser
    SPICE3 de su simulador es estándar.
    """
    title = circuit.get("title", "Untitled circuit")
    notes = circuit.get("notes", "")
    components = circuit.get("components", [])

    lines: list[str] = []
    lines.append(f"* {title}")
    if notes:
        lines.append(f"* {notes}")
    lines.append(
        f"* Generated by O.R.I.O.N circuit_from_image at {datetime.now().isoformat(timespec='seconds')}"
    )
    lines.append("")

    # Modelos referenciados por componentes que los necesitan. Los acumulamos
    # para emitirlos al final como .model statements.
    models_used: dict[str, str] = {}  # model_name → device_type ('D','NPN','PMOS')

    for comp in components:
        ctype = (comp.get("type") or "").lower()
        cid = comp.get("id") or "?"
        value = (comp.get("value") or "").strip()
        pins = comp.get("pins") or []

        prefix = _SPICE_PREFIX.get(ctype)
        if prefix is None:
            # ground u otro no-componente: ignoramos.
            continue

        # Asegurar que el refdes empiece con el prefijo correcto.
        if not cid.upper().startswith(prefix):
            cid = f"{prefix}{cid}"

        if ctype in ("resistor", "capacitor", "inductor"):
            if len(pins) < 2:
                lines.append(f"* SKIPPED {cid}: pins insuficientes ({pins})")
                continue
            lines.append(f"{cid} {pins[0]} {pins[1]} {value or '1k'}")

        elif ctype in ("diode", "led"):
            if len(pins) < 2:
                lines.append(f"* SKIPPED {cid}: pins insuficientes ({pins})")
                continue
            model = value if value and not value.endswith("V") else _DEFAULT_MODELS[ctype]
            lines.append(f"{cid} {pins[0]} {pins[1]} {model}")
            models_used[model] = "D"

        elif ctype in ("bjt_npn", "bjt_pnp"):
            if len(pins) < 3:
                lines.append(f"* SKIPPED {cid}: pins insuficientes ({pins})")
                continue
            model = value or _DEFAULT_MODELS[ctype]
            # Orden SPICE: C B E
            lines.append(f"{cid} {pins[1]} {pins[0]} {pins[2]} {model}")
            models_used[model] = "NPN" if ctype == "bjt_npn" else "PNP"

        elif ctype in ("nmos", "pmos"):
            if len(pins) < 3:
                lines.append(f"* SKIPPED {cid}: pins insuficientes ({pins})")
                continue
            model = value or _DEFAULT_MODELS[ctype]
            # Orden SPICE: D G S B (body = source si no hay 4to pin)
            body = pins[3] if len(pins) >= 4 else pins[2]
            lines.append(f"{cid} {pins[1]} {pins[0]} {pins[2]} {body} {model}")
            models_used[model] = "NMOS" if ctype == "nmos" else "PMOS"

        elif ctype == "vsource":
            if len(pins) < 2:
                continue
            val = value or "5V DC"
            # Normalizar "5V DC" → "DC 5"
            m = re.match(r"\s*([\d.]+)\s*V?\s*(DC|AC)?", val, re.IGNORECASE)
            if m:
                num, kind = m.group(1), (m.group(2) or "DC").upper()
                lines.append(f"{cid} {pins[0]} {pins[1]} {kind} {num}")
            else:
                lines.append(f"{cid} {pins[0]} {pins[1]} DC {val}")

        elif ctype == "isource":
            if len(pins) < 2:
                continue
            val = value or "1mA DC"
            m = re.match(r"\s*([\d.]+)\s*(m|u|n)?A?\s*(DC|AC)?", val, re.IGNORECASE)
            if m:
                num, suf, kind = m.group(1), (m.group(2) or ""), (m.group(3) or "DC").upper()
                lines.append(f"{cid} {pins[0]} {pins[1]} {kind} {num}{suf.lower()}")
            else:
                lines.append(f"{cid} {pins[0]} {pins[1]} DC {val}")

        elif ctype == "opamp":
            # Modelo subcircuit. Pin order KiCad: +, -, vcc, vee, out
            if len(pins) < 5:
                lines.append(f"* SKIPPED {cid}: opamp requiere 5 pines (+,-,V+,V-,out)")
                continue
            lines.append(
                f"X{cid.lstrip('X')} {pins[0]} {pins[1]} {pins[2]} {pins[3]} {pins[4]} LM358"
            )

        elif ctype == "switch":
            if len(pins) < 2:
                continue
            lines.append(f"* {cid}: switch (asume abierto). Conexión {pins[0]}-{pins[1]}")

    lines.append("")
    # Models al final
    for model, kind in models_used.items():
        if kind == "D":
            lines.append(f".model {model} D")
        elif kind in ("NPN", "PNP"):
            lines.append(f".model {model} {kind} (Is=1e-14 Bf=100)")
        elif kind in ("NMOS", "PMOS"):
            lines.append(f".model {model} {kind} (Vto=2 Kp=20u)")

    lines.append(".end")
    return "\n".join(lines) + "\n"


# ── KiCad schematic writer ─────────────────────────────────────────────

_KICAD_HEADER = """(kicad_sch (version 20230121) (generator orion_circuit_from_image)

  (uuid {uuid})

  (paper "A4")

  (title_block
    (title "{title}")
    (date "{date}")
    (company "O.R.I.O.N")
    (comment 1 "{notes}")
  )

  (lib_symbols
{lib_symbols}
  )

"""

# Símbolo mínimo en lib_symbols. KiCad necesita ver el símbolo definido
# para resolver el lib_id. Para simplificar usamos referencias a la lib
# estándar; los usuarios pueden re-linkear desde KiCad si hace falta.
_LIB_SYMBOL_STUB = """    (symbol "{lib_id}"
      (pin_numbers hide) (pin_names (offset 0))
      (in_bom yes) (on_board yes)
      (property "Reference" "{ref_prefix}" (at 0 0 0))
      (property "Value" "{lib_id}" (at 0 0 0))
    )"""


def _uuid() -> str:
    """UUID v4 sin importar uuid completo del stdlib para reducir overhead."""
    import uuid as _u

    return str(_u.uuid4())


def _to_kicad_sch(circuit: dict) -> str:
    """Emite un .kicad_sch v6/v7 mínimo pero válido.

    Layout: cuadrícula 50.8 mm horizontal, 25.4 mm vertical (grilla estándar
    de KiCad). Cada componente ocupa una celda y se conecta a los demás vía
    labels globales (más simple y robusto que trazar wires explícitos para
    todas las nets posibles).
    """
    title = circuit.get("title", "Untitled circuit")
    notes = circuit.get("notes", "")
    components = circuit.get("components", [])

    # Símbolos únicos referenciados
    seen_lib_ids: dict[str, str] = {}  # lib_id → ref_prefix
    for comp in components:
        ctype = (comp.get("type") or "").lower()
        if ctype not in _KICAD_SYMBOL:
            continue
        lib_id, _ = _KICAD_SYMBOL[ctype]
        ref_prefix = (comp.get("id", "?")[0] if comp.get("id") else "?").upper()
        seen_lib_ids.setdefault(lib_id, ref_prefix)

    lib_symbols_block = "\n".join(
        _LIB_SYMBOL_STUB.format(lib_id=lib_id, ref_prefix=ref_prefix)
        for lib_id, ref_prefix in seen_lib_ids.items()
    )

    out = [
        _KICAD_HEADER.format(
            uuid=_uuid(),
            title=title.replace('"', "'"),
            date=datetime.now().strftime("%Y-%m-%d"),
            notes=notes.replace('"', "'")[:80],
            lib_symbols=lib_symbols_block,
        )
    ]

    # Layout en grilla
    col_w, row_h = 50.8, 25.4
    cols = 5
    x0, y0 = 50.8, 50.8

    for idx, comp in enumerate(components):
        ctype = (comp.get("type") or "").lower()
        if ctype not in _KICAD_SYMBOL:
            continue
        lib_id, pin_names = _KICAD_SYMBOL[ctype]
        cid = comp.get("id", f"X{idx + 1}")
        value = comp.get("value", "")
        pins = comp.get("pins") or []

        row, col = divmod(idx, cols)
        x = x0 + col * col_w
        y = y0 + row * row_h

        sym_uuid = _uuid()
        out.append(f"""  (symbol (lib_id "{lib_id}") (at {x:.2f} {y:.2f} 0) (unit 1)
    (in_bom yes) (on_board yes) (dnp no)
    (uuid {sym_uuid})
    (property "Reference" "{cid}" (at {x:.2f} {y - 7.62:.2f} 0))
    (property "Value" "{value}" (at {x:.2f} {y + 7.62:.2f} 0))
""")

        # Pines como labels globales — esto crea la net automáticamente.
        # KiCad enlaza pines y labels que coinciden en posición + texto.
        for pin_idx, net in enumerate(pins):
            if not net:
                continue
            label_y = y + 2.54 * (pin_idx - len(pins) / 2)
            out.append(f"""    (label "{net}" (at {x + 7.62:.2f} {label_y:.2f} 0)
      (effects (font (size 1.27 1.27)) (justify left))
      (uuid {_uuid()})
    )
""")
        out.append("  )\n")

    out.append('\n  (sheet_instances\n    (path "/" (page "1"))\n  )\n')
    out.append(")\n")
    return "".join(out)


# ── Handler público ────────────────────────────────────────────────────

_VALID_OUTPUTS = {"spice", "kicad"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"}


def _sanitize_filename(name: str) -> str:
    """Reduce el title a un filename seguro multiplataforma."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return (safe or "circuit")[:60]


from core.tool_registry import tool


@tool(
    name="circuit_from_image",
    description=(
        "Analyzes an electronic circuit image (photo, screenshot, hand-drawn "
        "schematic) and generates a SPICE netlist (.cir importable to Proteus "
        "via File > Import Section) and a KiCad schematic (.kicad_sch). "
        "Use this WHENEVER the user uploads a circuit image and asks for a "
        "netlist, SPICE, Proteus, KiCad, .cir or schematic file. "
        "Do NOT use file_processor for this — file_processor only describes "
        "images, it does not generate circuit files."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "image_path": {
                "type": "STRING",
                "description": "Absolute path to the circuit image. If empty, uses the currently uploaded file.",
            },
            "outputs": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "Targets to generate: 'spice', 'kicad'. Default: both.",
            },
            "output_dir": {
                "type": "STRING",
                "description": "Folder where the .cir and .kicad_sch are written. Default: the image's folder.",
            },
        },
        "required": ["image_path"],
    },
    timeout=120,
    needs_current_file=True,
)
def circuit_from_image(parameters: dict, player=None, **_kwargs) -> str:
    """Handler invocable como tool por el agente y por el endpoint REST.

    Parameters
    ----------
    parameters
        ``image_path`` (requerido) — ruta absoluta a la imagen.
        ``outputs`` (opcional) — lista con ``"spice"`` y/o ``"kicad"``.
        ``output_dir`` (opcional) — carpeta destino. Default: la de la imagen.

    Returns
    -------
    str
        Mensaje legible para el usuario con el resumen del circuito y las
        rutas de los archivos generados, o un mensaje de error claro.
    """
    image_path_str = (parameters.get("image_path") or "").strip()
    if not image_path_str:
        return "Falta el parámetro 'image_path'."

    image_path = Path(image_path_str)
    if not image_path.exists() or not image_path.is_file():
        return f"Imagen no encontrada: {image_path_str}"
    if image_path.suffix.lower() not in _IMAGE_EXTS:
        return f"Formato de imagen no soportado: {image_path.suffix}. Usa jpg, png, webp o bmp."

    outputs = parameters.get("outputs") or ["spice", "kicad"]
    if isinstance(outputs, str):
        outputs = [outputs]
    outputs = [o.lower().strip() for o in outputs if o.lower().strip() in _VALID_OUTPUTS]
    if not outputs:
        outputs = ["spice", "kicad"]

    output_dir = Path(parameters.get("output_dir") or image_path.parent)
    output_dir.mkdir(parents=True, exist_ok=True)

    log = f"[circuit_from_image] {image_path.name} → {outputs}"
    print(log)
    if player and hasattr(player, "write_log"):
        with contextlib.suppress(Exception):
            player.write_log(log)

    # Visión
    try:
        circuit = _analyze_with_vision(image_path)
    except RuntimeError as e:
        return f"Análisis del circuito falló: {e}"

    if "error" in circuit:
        if circuit["error"] == "no_circuit_detected":
            return "No detecté un circuito electrónico en la imagen. ¿Es la imagen correcta?"
        return f"El análisis devolvió un error: {circuit['error']}"

    components = circuit.get("components") or []
    if not components:
        return "El análisis no identificó componentes en el circuito."

    base = _sanitize_filename(circuit.get("title") or image_path.stem)
    written: dict[str, Path] = {}

    # JSON sidecar: guarda la respuesta cruda de Gemini (incluye terminals
    # e instruments) junto al .cir. proteus_autodraw lo lee si existe para
    # colocar también terminales y osciloscopios; si no existe, cae al
    # parser SPICE puro.
    if "spice" in outputs:
        try:
            sidecar_path = output_dir / f"{base}.circuit.json"
            sidecar_path.write_text(
                json.dumps(circuit, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            written["sidecar"] = sidecar_path
        except Exception:
            pass  # el sidecar es bonus — no debe romper el flujo principal

    if "spice" in outputs:
        try:
            content = _to_spice(circuit)
            spice_path = output_dir / f"{base}.cir"
            spice_path.write_text(content, encoding="utf-8")
            written["spice"] = spice_path
        except Exception as e:
            return f"Generación de SPICE falló: {e}"

    if "kicad" in outputs:
        try:
            content = _to_kicad_sch(circuit)
            kicad_path = output_dir / f"{base}.kicad_sch"
            kicad_path.write_text(content, encoding="utf-8")
            written["kicad"] = kicad_path
        except Exception as e:
            return f"Generación de KiCad falló: {e}"

    # Resumen para el usuario
    title = circuit.get("title", "Circuito")
    notes = circuit.get("notes", "")
    n = len(components)
    parts = [f'Detecté "{title}" con {n} componentes.']
    if notes:
        parts.append(notes)
    if "spice" in written:
        parts.append(f"SPICE: {written['spice']}")
    if "kicad" in written:
        parts.append(f"KiCad: {written['kicad']}")
    return " ".join(parts)
