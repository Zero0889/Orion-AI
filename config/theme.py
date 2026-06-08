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
    # ── Orion Black (Perplexity-style deep black, default) ──────────────
    "orion_black": {
        "name": "Orion Black",
        "BG":       "#000000",
        "PANEL":    "#0d0d0d",
        "PANEL2":   "#161616",
        "DARK":     "#000000",
        "BORDER":   "#1f1f1f",
        "BORDER_B": "#2e2e2e",
        "BORDER_A": "#262626",
        "PRI":      "#6063ec",
        "PRI_DIM":  "#484bb2",
        "PRI_GHO":  "#12123a",
        "ACC":      "#6366f1",
        "ACC2":     "#818cf8",
        "GREEN":    "#22c55e",
        "GREEN_D":  "#16a34a",
        "RED":      "#ef4444",
        "MUTED_C":  "#71717a",
        "TEXT":     "#ededed",
        "TEXT_DIM": "#a1a1aa",
        "TEXT_MED": "#d4d4d8",
        "WHITE":    "#ffffff",
        "BAR_BG":   "#0d0d0d",
        "ORB_ACTIVE": [
            (96,  99,  236),
            (129, 140, 248),
            (67,  56,  202),
            (49,  46,  129),
        ],
        "ORB_MUTED": [
            (82,  82,  91),
            (63,  63,  70),
            (39,  39,  42),
            (24,  24,  27),
        ],
    },

    # ── Rojo ORION ─────────────────────────────────────────────────────
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

    # ── Blanco & Negro (alto contraste, sustituye todos los rojos) ───────
    "blanco": {
        "name": "Blanco & Negro",
        "BG":       "#000000",
        "PANEL":    "#0c0c0c",
        "PANEL2":   "#181818",
        "DARK":     "#000000",
        "BORDER":   "#2e2e2e",
        "BORDER_B": "#d4d4d4",
        "BORDER_A": "#8a8a8a",
        "PRI":      "#ffffff",
        "PRI_DIM":  "#b0b0b0",
        "PRI_GHO":  "#1f1f1f",
        "ACC":      "#ffffff",
        "ACC2":     "#dcdcdc",
        "GREEN":    "#ffffff",
        "GREEN_D":  "#9e9e9e",
        "RED":      "#ffffff",
        "MUTED_C":  "#7a7a7a",
        "TEXT":     "#ffffff",
        "TEXT_DIM": "#8a8a8a",
        "TEXT_MED": "#c8c8c8",
        "WHITE":    "#ffffff",
        "BAR_BG":   "#1c1c1c",
        # Overrides para eliminar todo rastro de color en pintura libre
        "BG_GLOW":  "#1a1a1a",
        "BG_DARK":  "#000000",
        "DROP_HOVER": "#161616",
        "DROP_OVER":  "#222222",
        "TEMP_C":   "#cccccc",
        "MUTE_BTN_BG":  "#202020",
        "MUTE_BTN_HOV": "#2a2a2a",
        "BTN_BG_ERR":   "#181818",
        "BTN_BG_ERR_H": "#222222",
        "BTN_BG_OK":    "#181818",
        "BTN_BG_OK_H":  "#222222",
        "ORB_ACTIVE": [
            (255, 255, 255),
            (240, 240, 240),
            (210, 210, 210),
            (170, 170, 170),
        ],
        "ORB_MUTED": [
            (130, 130, 130),
            (100, 100, 100),
            (75,  75,  75),
            (55,  55,  55),
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

    # ── Orion Blue (tactical mission control) ────────────────────────────
    "orion_blue": {
        "name": "Orion Blue",
        "BG":       "#0a0b0e",
        "PANEL":    "#0f1115",
        "PANEL2":   "#13161c",
        "DARK":     "#070809",
        "BORDER":   "#1a1f2a",
        "BORDER_B": "#2a3a55",
        "BORDER_A": "#1f2a40",
        "PRI":      "#0066ff",
        "PRI_DIM":  "#1a4a8a",
        "PRI_GHO":  "#08172e",
        "ACC":      "#00f0ff",
        "ACC2":     "#7ad5ff",
        "GREEN":    "#0df272",
        "GREEN_D":  "#0a9c4d",
        "RED":      "#ff3a55",
        "MUTED_C":  "#5a6680",
        "TEXT":     "#e1dde8",
        "TEXT_DIM": "#5b6480",
        "TEXT_MED": "#9aa3bc",
        "WHITE":    "#ffffff",
        "BAR_BG":   "#0a1424",
        "BG_GLOW":  "#0a1a35",
        "BG_DARK":  "#040608",
        "ORB_ACTIVE": [
            (0,   102, 255),
            (0,   240, 255),
            (90,  170, 255),
            (255, 255, 255),
        ],
        "ORB_MUTED": [
            (60,  80,  120),
            (45,  65,  95),
            (35,  50,  75),
            (25,  35,  55),
        ],
    },

    # ── Cyber Cyan (electric grid) ────────────────────────────────────────
    "cyber_cyan": {
        "name": "Cyber Cyan",
        "BG":       "#02080c",
        "PANEL":    "#031319",
        "PANEL2":   "#051c25",
        "DARK":     "#010608",
        "BORDER":   "#0f3a4a",
        "BORDER_B": "#1faabf",
        "BORDER_A": "#157286",
        "PRI":      "#00f5ff",
        "PRI_DIM":  "#0d8a9c",
        "PRI_GHO":  "#072830",
        "ACC":      "#5dffff",
        "ACC2":     "#a0ffff",
        "GREEN":    "#33ff99",
        "GREEN_D":  "#1a995a",
        "RED":      "#ff3355",
        "MUTED_C":  "#557788",
        "TEXT":     "#d4f7ff",
        "TEXT_DIM": "#3a7a8a",
        "TEXT_MED": "#77c4d4",
        "WHITE":    "#f0ffff",
        "BAR_BG":   "#04181f",
        "ORB_ACTIVE": [
            (0,   245, 255),
            (110, 255, 255),
            (0,   190, 220),
            (60,  140, 170),
        ],
        "ORB_MUTED": [
            (40,  100, 120),
            (30,  80,  100),
            (25,  60,  80),
            (20,  45,  60),
        ],
    },

    # ── Deep Purple (royal neural) ───────────────────────────────────────
    "deep_purple": {
        "name": "Deep Purple",
        "BG":       "#08040f",
        "PANEL":    "#10081f",
        "PANEL2":   "#170b2c",
        "DARK":     "#05030a",
        "BORDER":   "#2a1550",
        "BORDER_B": "#5a2a9c",
        "BORDER_A": "#42206e",
        "PRI":      "#8b5cf6",
        "PRI_DIM":  "#5a3aa0",
        "PRI_GHO":  "#1a0d35",
        "ACC":      "#c084fc",
        "ACC2":     "#ddb4ff",
        "GREEN":    "#34d399",
        "GREEN_D":  "#0e7d5a",
        "RED":      "#f43f5e",
        "MUTED_C":  "#7a6699",
        "TEXT":     "#ede9fe",
        "TEXT_DIM": "#6a548a",
        "TEXT_MED": "#a89bcc",
        "WHITE":    "#ffffff",
        "BAR_BG":   "#1a0d2e",
        "ORB_ACTIVE": [
            (139, 92,  246),
            (192, 132, 252),
            (110, 70,  220),
            (75,  45,  170),
        ],
        "ORB_MUTED": [
            (75,  60,  100),
            (60,  45,  85),
            (45,  35,  70),
            (35,  25,  55),
        ],
    },

    # ── Red Alert (emergency tactical) ────────────────────────────────────
    "red_alert": {
        "name": "Red Alert",
        "BG":       "#0a0204",
        "PANEL":    "#150307",
        "PANEL2":   "#1f050b",
        "DARK":     "#070101",
        "BORDER":   "#4a0a18",
        "BORDER_B": "#b21833",
        "BORDER_A": "#7a1424",
        "PRI":      "#ff0033",
        "PRI_DIM":  "#a00824",
        "PRI_GHO":  "#2e0510",
        "ACC":      "#ff5544",
        "ACC2":     "#ffaa55",
        "GREEN":    "#33ff99",
        "GREEN_D":  "#15994d",
        "RED":      "#ff0022",
        "MUTED_C":  "#aa3344",
        "TEXT":     "#ffe0e6",
        "TEXT_DIM": "#8a3848",
        "TEXT_MED": "#cc6678",
        "WHITE":    "#ffffff",
        "BAR_BG":   "#1f0508",
        "ORB_ACTIVE": [
            (255, 0,   51),
            (255, 85,  68),
            (220, 10,  40),
            (160, 5,   25),
        ],
        "ORB_MUTED": [
            (120, 40, 50),
            (95,  30, 40),
            (75,  22, 32),
            (55,  16, 25),
        ],
    },

    # ── Pure Black (OLED minimal) ─────────────────────────────────────────
    "pure_black": {
        "name": "Pure Black",
        "BG":       "#000000",
        "PANEL":    "#050505",
        "PANEL2":   "#0a0a0a",
        "DARK":     "#000000",
        "BORDER":   "#1a1a1a",
        "BORDER_B": "#3a3a3a",
        "BORDER_A": "#252525",
        "PRI":      "#ffffff",
        "PRI_DIM":  "#888888",
        "PRI_GHO":  "#141414",
        "ACC":      "#e0e0e0",
        "ACC2":     "#c0c0c0",
        "GREEN":    "#ffffff",
        "GREEN_D":  "#7a7a7a",
        "RED":      "#ffffff",
        "MUTED_C":  "#555555",
        "TEXT":     "#ffffff",
        "TEXT_DIM": "#4a4a4a",
        "TEXT_MED": "#8a8a8a",
        "WHITE":    "#ffffff",
        "BAR_BG":   "#0d0d0d",
        "BG_GLOW":  "#0a0a0a",
        "BG_DARK":  "#000000",
        "DROP_HOVER": "#101010",
        "DROP_OVER":  "#1a1a1a",
        "TEMP_C":   "#ffffff",
        "MUTE_BTN_BG":  "#151515",
        "MUTE_BTN_HOV": "#1f1f1f",
        "BTN_BG_ERR":   "#0f0f0f",
        "BTN_BG_ERR_H": "#1a1a1a",
        "BTN_BG_OK":    "#0f0f0f",
        "BTN_BG_OK_H":  "#1a1a1a",
        "ORB_ACTIVE": [
            (255, 255, 255),
            (230, 230, 230),
            (200, 200, 200),
            (160, 160, 160),
        ],
        "ORB_MUTED": [
            (100, 100, 100),
            (75,  75,  75),
            (55,  55,  55),
            (35,  35,  35),
        ],
    },

    # ── Orion Light (clean glass-morphism day mode) ──────────────────────
    "orion_light": {
        "name": "Orion Light",
        "BG":       "#f5f7fa",
        "PANEL":    "#ffffff",
        "PANEL2":   "#f8fafe",
        "DARK":     "#eef1f6",
        "BORDER":   "#dfe3eb",
        "BORDER_B": "#bcc3d0",
        "BORDER_A": "#cfd5e0",
        "PRI":      "#4361ee",
        "PRI_DIM":  "#3a50b9",
        "PRI_GHO":  "#e3edff",
        "ACC":      "#00b0d8",
        "ACC2":     "#3ac8e8",
        "GREEN":    "#16a34a",
        "GREEN_D":  "#0e7d3b",
        "RED":      "#dc2626",
        "MUTED_C":  "#949bac",
        "TEXT":     "#181b22",
        "TEXT_DIM": "#646e87",
        "TEXT_MED": "#454c5e",
        "WHITE":    "#ffffff",
        "BAR_BG":   "#eef1f6",
        "BG_GLOW":  "#ebf3ff",
        "BG_DARK":  "#dde2ec",
        "DROP_HOVER": "#eaf1ff",
        "DROP_OVER":  "#d6e4ff",
        "TEMP_C":   "#dc2626",
        "MUTE_BTN_BG":  "#ffe5ea",
        "MUTE_BTN_HOV": "#ffd5dc",
        "BTN_BG_ERR":   "#fff0f2",
        "BTN_BG_ERR_H": "#ffe2e7",
        "BTN_BG_OK":    "#e8f7ef",
        "BTN_BG_OK_H":  "#d4f0e0",
        "ORB_ACTIVE": [
            (67,  97,  238),
            (60,  200, 232),
            (90,  140, 230),
            (140, 180, 240),
        ],
        "ORB_MUTED": [
            (170, 180, 200),
            (140, 150, 175),
            (120, 130, 155),
            (100, 110, 135),
        ],
    },

    # ── Glass White (light mode glassmorphism) ────────────────────────────
    "glass_white": {
        "name": "Glass White",
        "BG":       "#f4f5f8",
        "PANEL":    "#ffffff",
        "PANEL2":   "#f0f2f6",
        "DARK":     "#e7eaf0",
        "BORDER":   "#dfe3eb",
        "BORDER_B": "#bcc3d0",
        "BORDER_A": "#cfd5e0",
        "PRI":      "#0066ff",
        "PRI_DIM":  "#3a85ff",
        "PRI_GHO":  "#e3edff",
        "ACC":      "#00b0d8",
        "ACC2":     "#3ac8e8",
        "GREEN":    "#0ea05a",
        "GREEN_D":  "#0a7d47",
        "RED":      "#e63950",
        "MUTED_C":  "#8a93a8",
        "TEXT":     "#181b22",
        "TEXT_DIM": "#7b849b",
        "TEXT_MED": "#454c5e",
        "WHITE":    "#ffffff",
        "BAR_BG":   "#e7eaf0",
        "BG_GLOW":  "#ebf3ff",
        "BG_DARK":  "#dde2ec",
        "DROP_HOVER": "#eaf1ff",
        "DROP_OVER":  "#d6e4ff",
        "TEMP_C":   "#e63950",
        "MUTE_BTN_BG":  "#ffe5ea",
        "MUTE_BTN_HOV": "#ffd5dc",
        "BTN_BG_ERR":   "#fff0f2",
        "BTN_BG_ERR_H": "#ffe2e7",
        "BTN_BG_OK":    "#e8f7ef",
        "BTN_BG_OK_H":  "#d4f0e0",
        "ORB_ACTIVE": [
            (0,   102, 255),
            (60,  200, 232),
            (90,  140, 230),
            (140, 180, 240),
        ],
        "ORB_MUTED": [
            (170, 180, 200),
            (140, 150, 175),
            (120, 130, 155),
            (100, 110, 135),
        ],
    },
}


DEFAULT_THEME = "orion_black"


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
