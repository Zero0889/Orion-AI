"""
config.theme — Sistema de temas configurables para O.R.I.O.N
==============================================================
Define presets de colores y permite cambiar el tema en runtime.
El tema activo se guarda en config/theme.json.

Para cambiar de tema: edita ese archivo o usa el selector en la UI.
"""

import json
from pathlib import Path

from config import CONFIG_DIR

_THEME_CONFIG_PATH = CONFIG_DIR / "theme.json"


# ============================================================================
#  Definición de temas
# ============================================================================
# Cada tema define los mismos colores. Para añadir uno nuevo, copia uno
# existente y modifica los valores.

THEMES: dict[str, dict] = {
    # ── Rojo ORION (default) ─────────────────────────────────────────────
    "red": {
        "name": "Rojo ORION",
        "BG":       "#0a0205",
        "PANEL":    "#140307",
        "PANEL2":   "#1a040a",
        "DARK":     "#0d0204",
        "BORDER":   "#3d0d18",
        "BORDER_B": "#7a1a2c",
        "BORDER_A": "#5c1422",
        "PRI":      "#ff2a4d",
        "PRI_DIM":  "#a01828",
        "PRI_GHO":  "#2e0810",
        "ACC":      "#ff6b1a",
        "ACC2":     "#ffb84d",
        "GREEN":    "#33ff99",
        "GREEN_D":  "#15994d",
        "RED":      "#ff1f3a",
        "MUTED_C":  "#ff5577",
        "TEXT":     "#ffc4cc",
        "TEXT_DIM": "#8a3a48",
        "TEXT_MED": "#cc6678",
        "WHITE":    "#fff0f2",
        "BAR_BG":   "#1f0510",
        "ORB_ACTIVE": [
            (255, 60,  60),
            (255, 110, 70),
            (220, 30,  55),
            (170, 15,  40),
        ],
        "ORB_MUTED": [
            (140, 60, 80),
            (110, 40, 60),
            (90,  30, 50),
            (70,  20, 35),
        ],
    },

    # ── Negro y rojo (alto contraste) ────────────────────────────────────
    "black_red": {
        "name": "Negro & Rojo",
        "BG":       "#000000",
        "PANEL":    "#0a0a0a",
        "PANEL2":   "#111111",
        "DARK":     "#050505",
        "BORDER":   "#330000",
        "BORDER_B": "#990000",
        "BORDER_A": "#660000",
        "PRI":      "#ff0033",
        "PRI_DIM":  "#990022",
        "PRI_GHO":  "#1a0008",
        "ACC":      "#ff5500",
        "ACC2":     "#ffaa00",
        "GREEN":    "#00ff66",
        "GREEN_D":  "#008833",
        "RED":      "#ff0022",
        "MUTED_C":  "#aa3344",
        "TEXT":     "#ffffff",
        "TEXT_DIM": "#666666",
        "TEXT_MED": "#aaaaaa",
        "WHITE":    "#ffffff",
        "BAR_BG":   "#1a0008",
        "ORB_ACTIVE": [
            (255, 0,   40),
            (255, 60,  20),
            (200, 0,   30),
            (130, 0,   20),
        ],
        "ORB_MUTED": [
            (120, 40, 60),
            (90,  30, 45),
            (70,  20, 35),
            (50,  15, 25),
        ],
    },

    # ── Cian sci-fi (HUD clásico) ────────────────────────────────────────
    "cyan": {
        "name": "Cyan HUD",
        "BG":       "#02080a",
        "PANEL":    "#031318",
        "PANEL2":   "#04181f",
        "DARK":     "#020c10",
        "BORDER":   "#0d3d4a",
        "BORDER_B": "#1a7a92",
        "BORDER_A": "#145c70",
        "PRI":      "#2affd6",
        "PRI_DIM":  "#18a08c",
        "PRI_GHO":  "#082e2a",
        "ACC":      "#1ab8ff",
        "ACC2":     "#4dd9ff",
        "GREEN":    "#33ff99",
        "GREEN_D":  "#15994d",
        "RED":      "#ff3a55",
        "MUTED_C":  "#557799",
        "TEXT":     "#c4ffea",
        "TEXT_DIM": "#3a7a8a",
        "TEXT_MED": "#66ccd8",
        "WHITE":    "#f0fffa",
        "BAR_BG":   "#05181f",
        "ORB_ACTIVE": [
            (60,  255, 220),
            (70,  200, 255),
            (30,  220, 200),
            (15,  140, 170),
        ],
        "ORB_MUTED": [
            (60, 100, 120),
            (40, 80,  100),
            (30, 60,  80),
            (20, 45,  60),
        ],
    },

    # ── Verde matrix ─────────────────────────────────────────────────────
    "green": {
        "name": "Matrix Green",
        "BG":       "#020a04",
        "PANEL":    "#03150a",
        "PANEL2":   "#041a0d",
        "DARK":     "#020d05",
        "BORDER":   "#0d3d1a",
        "BORDER_B": "#1a7a3a",
        "BORDER_A": "#145c2a",
        "PRI":      "#2aff66",
        "PRI_DIM":  "#18a040",
        "PRI_GHO":  "#082e15",
        "ACC":      "#1aff99",
        "ACC2":     "#4dffbb",
        "GREEN":    "#33ff99",
        "GREEN_D":  "#15994d",
        "RED":      "#ff3a3a",
        "MUTED_C":  "#557755",
        "TEXT":     "#c4ffcc",
        "TEXT_DIM": "#3a7a48",
        "TEXT_MED": "#66cc78",
        "WHITE":    "#f0fff2",
        "BAR_BG":   "#051f10",
        "ORB_ACTIVE": [
            (60,  255, 100),
            (110, 255, 70),
            (30,  220, 80),
            (15,  140, 40),
        ],
        "ORB_MUTED": [
            (60,  100, 70),
            (40,  80,  50),
            (30,  60,  40),
            (20,  45,  30),
        ],
    },

    # ── Ámbar CRT retro ──────────────────────────────────────────────────
    "amber": {
        "name": "Amber CRT",
        "BG":       "#0a0602",
        "PANEL":    "#180e03",
        "PANEL2":   "#1f1304",
        "DARK":     "#0d0702",
        "BORDER":   "#3d2a0d",
        "BORDER_B": "#7a5a1a",
        "BORDER_A": "#5c4214",
        "PRI":      "#ffaa2a",
        "PRI_DIM":  "#a06818",
        "PRI_GHO":  "#2e1f08",
        "ACC":      "#ff7a1a",
        "ACC2":     "#ffd84d",
        "GREEN":    "#aaff33",
        "GREEN_D":  "#669915",
        "RED":      "#ff5a1a",
        "MUTED_C":  "#998855",
        "TEXT":     "#ffe8c4",
        "TEXT_DIM": "#8a7a3a",
        "TEXT_MED": "#ccaa66",
        "WHITE":    "#fff8f0",
        "BAR_BG":   "#1f1505",
        "ORB_ACTIVE": [
            (255, 170, 60),
            (255, 220, 90),
            (220, 130, 30),
            (170, 90,  15),
        ],
        "ORB_MUTED": [
            (140, 110, 60),
            (110, 85,  40),
            (90,  70,  30),
            (70,  55,  20),
        ],
    },

    # ── Púrpura cyberpunk ────────────────────────────────────────────────
    "purple": {
        "name": "Cyberpunk Purple",
        "BG":       "#08020a",
        "PANEL":    "#120318",
        "PANEL2":   "#180420",
        "DARK":     "#0a020e",
        "BORDER":   "#380d4a",
        "BORDER_B": "#7a1ab0",
        "BORDER_A": "#5c1480",
        "PRI":      "#c855ff",
        "PRI_DIM":  "#7a18a0",
        "PRI_GHO":  "#1f0833",
        "ACC":      "#ff1aaa",
        "ACC2":     "#ff66dd",
        "GREEN":    "#33ffcc",
        "GREEN_D":  "#159988",
        "RED":      "#ff3a77",
        "MUTED_C":  "#776699",
        "TEXT":     "#e8c4ff",
        "TEXT_DIM": "#6a3a8a",
        "TEXT_MED": "#aa66cc",
        "WHITE":    "#fff0ff",
        "BAR_BG":   "#1a0524",
        "ORB_ACTIVE": [
            (200, 80,  255),
            (255, 60,  200),
            (160, 30,  220),
            (110, 15,  150),
        ],
        "ORB_MUTED": [
            (90,  60,  110),
            (75,  45,  90),
            (60,  35,  75),
            (45,  25,  55),
        ],
    },

    # ── Monocromo (blanco y negro puro) ──────────────────────────────────
    "mono": {
        "name": "Mono",
        "BG":       "#000000",
        "PANEL":    "#0a0a0a",
        "PANEL2":   "#141414",
        "DARK":     "#050505",
        "BORDER":   "#2a2a2a",
        "BORDER_B": "#666666",
        "BORDER_A": "#4a4a4a",
        "PRI":      "#ffffff",
        "PRI_DIM":  "#888888",
        "PRI_GHO":  "#1a1a1a",
        "ACC":      "#cccccc",
        "ACC2":     "#aaaaaa",
        "GREEN":    "#ffffff",
        "GREEN_D":  "#888888",
        "RED":      "#ffffff",
        "MUTED_C":  "#666666",
        "TEXT":     "#ffffff",
        "TEXT_DIM": "#555555",
        "TEXT_MED": "#999999",
        "WHITE":    "#ffffff",
        "BAR_BG":   "#1a1a1a",
        "ORB_ACTIVE": [
            (255, 255, 255),
            (220, 220, 220),
            (180, 180, 180),
            (140, 140, 140),
        ],
        "ORB_MUTED": [
            (100, 100, 100),
            (80,  80,  80),
            (60,  60,  60),
            (40,  40,  40),
        ],
    },

    # ── Hielo ártico (azul + blanco) ─────────────────────────────────────
    "arctic": {
        "name": "Arctic Ice",
        "BG":       "#020812",
        "PANEL":    "#03121f",
        "PANEL2":   "#04182a",
        "DARK":     "#020a16",
        "BORDER":   "#0d2a4a",
        "BORDER_B": "#1a5a92",
        "BORDER_A": "#144270",
        "PRI":      "#7ad5ff",
        "PRI_DIM":  "#4080a0",
        "PRI_GHO":  "#08182e",
        "ACC":      "#aaeeff",
        "ACC2":     "#dff5ff",
        "GREEN":    "#88ffcc",
        "GREEN_D":  "#558899",
        "RED":      "#ff7a8a",
        "MUTED_C":  "#557799",
        "TEXT":     "#e0f0ff",
        "TEXT_DIM": "#557788",
        "TEXT_MED": "#88aacc",
        "WHITE":    "#ffffff",
        "BAR_BG":   "#05182a",
        "ORB_ACTIVE": [
            (180, 230, 255),
            (220, 245, 255),
            (130, 200, 240),
            (90,  160, 210),
        ],
        "ORB_MUTED": [
            (80,  120, 150),
            (60,  100, 130),
            (50,  85,  110),
            (40,  70,  95),
        ],
    },
}


DEFAULT_THEME = "red"


# ============================================================================
#  API
# ============================================================================

def load_theme_name() -> str:
    if not _THEME_CONFIG_PATH.exists():
        return DEFAULT_THEME
    try:
        data = json.loads(_THEME_CONFIG_PATH.read_text(encoding="utf-8"))
        name = data.get("active", DEFAULT_THEME)
        return name if name in THEMES else DEFAULT_THEME
    except (json.JSONDecodeError, OSError):
        return DEFAULT_THEME


def save_theme_name(name: str) -> None:
    if name not in THEMES:
        return
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _THEME_CONFIG_PATH.write_text(
        json.dumps({"active": name}, indent=2),
        encoding="utf-8",
    )


def get_theme(name: str | None = None) -> dict:
    if name is None:
        name = load_theme_name()
    return THEMES.get(name, THEMES[DEFAULT_THEME])


def list_themes() -> list[tuple[str, str]]:
    """Retorna [(id, display_name), ...] de todos los temas disponibles."""
    return [(k, v["name"]) for k, v in THEMES.items()]


def apply_theme_to_class(theme: dict, target_class) -> None:
    """Aplica los valores del tema a los atributos de una clase."""
    for key, value in theme.items():
        if key in ("name", "ORB_ACTIVE", "ORB_MUTED"):
            continue
        setattr(target_class, key, value)
