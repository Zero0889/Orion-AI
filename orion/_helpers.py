"""orion._helpers — Helpers internos del runtime (privados al paquete).

Funciones puras + regexes que comparten ``orion.runtime``, ``orion.audio``
y ``orion.live_session``. Viven aparte para evitar circular imports
entre los mixins.

NO importar desde fuera de orion/ — la API pública es ``orion.main()``.
"""

from __future__ import annotations

import re

from orion.config import PROMPT_PATH
from orion.core.logger import get_logger

log = get_logger("orion.helpers")


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
            "appropriate tool.\n\n"
            "LANGUAGE: ALWAYS respond ONLY in Spanish. Never English, never mixed. "
            "If a tool returns English content, translate the summary to Spanish "
            "before speaking. Every reply — including time, date, math, errors — "
            "must be 100% Spanish."
        )


def _first_real_exception(exc: BaseException) -> BaseException:
    """Desempaqueta ``ExceptionGroup`` para devolver la primera excepción
    "real" (no-grupo). Si el argumento ya es una excepción normal, la
    devuelve tal cual. Si está anidado (group dentro de group), busca en
    profundidad hasta encontrar la raíz."""
    while isinstance(exc, BaseExceptionGroup):
        inner = exc.exceptions
        if not inner:
            return exc
        exc = inner[0]
    return exc


# Limpieza de transcripciones (caracteres de control que a veces emite el modelo)
_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)
# Tokens espurios que el modelo a veces transcribe a partir de ruido ambiental
# (chasquidos, micro-ruido, etc.). Si la transcripción entera es uno de éstos,
# se descarta.
_TRANSCRIPT_NOISE = {
    "noice",
    "noise",
    "[noise]",
    "[ruido]",
    "(noise)",
    "(ruido)",
    "uh",
    "um",
    "uhm",
    "hmm",
    "mmh",
    "mm",
    "ah",
    "eh",
    "...",
    "…",
    ".",
    "-",
}
# Limpieza de marcadores estilo [BLANK_AUDIO], (background noise), [música], etc.
_BRACKET_RE = re.compile(
    r"[\[\(\<](?:blank[_ ]?audio|background|music|música|silencio|ruido|noise|inaudible|aplausos|applause)[^\]\)\>]*[\]\)\>]",
    re.IGNORECASE,
)


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
