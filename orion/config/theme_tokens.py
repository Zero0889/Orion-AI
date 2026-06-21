"""
config.theme_tokens — Tokens de tema puros (sin Qt)
====================================================
Re-export del subconjunto **headless** de :mod:`config.theme`, pensado
para que el backend web (FastAPI + WebSocket) y un futuro frontend React
puedan consumir los temas sin arrastrar PyQt6.

Auditoría pre-Fase 0 — R-21
---------------------------
``config/theme.py`` ya es código Python puro (sólo diccionarios de hex y
tuplas RGB + helpers que leen/escriben JSON). Este módulo formaliza la
**superficie pública estable** que el backend usa: si en el futuro alguien
añade un helper Qt al archivo original, el backend no lo verá por aquí.

Reglas
------
- Este módulo **no** debe importar PyQt6 ni nada de ``ui*``.
- ``server.*`` y futuros endpoints REST/WS deben importar desde aquí, no
  desde ``config.theme``.
- ``ui*`` puede seguir importando de ``config.theme`` para acceder a los
  mismos datos + cualquier helper Qt que se añada en el futuro.
"""

from __future__ import annotations

# Re-export explícito de la API pública sin Qt.
from orion.config.theme import (
    DEFAULT_THEME,
    THEMES,
    get_theme,
    list_themes,
    load_theme_name,
    save_theme_name,
)

__all__ = [
    "DEFAULT_THEME",
    "THEMES",
    "get_theme",
    "list_themes",
    "load_theme_name",
    "save_theme_name",
]
