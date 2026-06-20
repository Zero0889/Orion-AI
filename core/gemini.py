"""
core.gemini — Cliente Gemini centralizado para O.R.I.O.N
========================================================
Envoltura única sobre el SDK nuevo ``google.genai``. Reemplaza el patrón
repetido (y deprecado) que estaba esparcido por ``actions/`` y ``agent/``::

    import google.generativeai as genai
    genai.configure(api_key=get_api_key())
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)

Ventajas de centralizarlo aquí:

- **Un solo ``genai.Client`` cacheado** — antes cada llamada reconfiguraba el
  SDK y reconstruía el modelo, añadiendo latencia en cada turno.
- **API estable** — el paquete legacy ``google.generativeai`` está deprecado y
  emitía un ``FutureWarning`` que ``main.py`` tenía que silenciar a mano.
- **Punto único** para modelos por defecto, ``system_instruction``,
  temperatura y manejo de errores.

El núcleo Live (``main.py``) ya usaba ``google.genai`` directamente; este
módulo extiende ese mismo SDK al resto del proyecto.
"""

from __future__ import annotations

from functools import lru_cache

from google import genai
from google.genai import types

from config import get_api_key

# ── Alias de modelos (nombre legible → ID real) ─────────────────────────────
FLASH = "gemini-2.5-flash"
FLASH_LITE = "gemini-2.5-flash-lite"


@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    """Devuelve el cliente Gemini único y cacheado.

    Se crea una sola vez por proceso. Si la API key cambia en caliente, llama
    a ``reset_client()`` para forzar su recreación.
    """
    return genai.Client(api_key=get_api_key())


def reset_client() -> None:
    """Invalida el cliente cacheado (p. ej. tras cambiar la API key)."""
    get_client.cache_clear()


def _build_config(
    system_instruction: str | None = None,
    temperature: float | None = None,
    response_mime_type: str | None = None,
) -> types.GenerateContentConfig | None:
    kwargs: dict = {}
    if system_instruction:
        kwargs["system_instruction"] = system_instruction
    if temperature is not None:
        kwargs["temperature"] = temperature
    if response_mime_type:
        kwargs["response_mime_type"] = response_mime_type
    return types.GenerateContentConfig(**kwargs) if kwargs else None


def generate(
    contents,
    *,
    model: str = FLASH,
    system_instruction: str | None = None,
    temperature: float | None = None,
    response_mime_type: str | None = None,
):
    """Genera contenido y devuelve el objeto respuesta completo.

    ``contents`` acepta lo mismo que el viejo ``generate_content``: un string,
    o una lista de partes (texto + imágenes PIL, etc.). El objeto devuelto
    expone ``.text`` igual que antes.
    """
    config = _build_config(system_instruction, temperature, response_mime_type)
    return get_client().models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )


def generate_text(
    contents,
    *,
    model: str = FLASH,
    system_instruction: str | None = None,
    temperature: float | None = None,
    response_mime_type: str | None = None,
) -> str:
    """Como :func:`generate` pero devuelve directamente el texto ya recortado."""
    resp = generate(
        contents,
        model=model,
        system_instruction=system_instruction,
        temperature=temperature,
        response_mime_type=response_mime_type,
    )
    return (resp.text or "").strip()


# ── Compatibilidad con el patrón antiguo ────────────────────────────────────
# Algunos módulos (``code_helper``, ``dev_agent``, ``file_processor``) tenían un
# helper local que devolvía un ``genai.GenerativeModel`` y luego llamaban a
# ``model.generate_content(...)`` en muchos sitios. Para migrarlos sin tocar
# cada call site, :func:`model` devuelve un objeto con la misma interfaz
# ``.generate_content`` pero apoyado en el cliente nuevo y cacheado.


class _ModelHandle:
    """Adaptador mínimo: imita ``GenerativeModel.generate_content`` del SDK
    legacy delegando en el cliente ``google.genai`` cacheado."""

    __slots__ = ("_model", "_system_instruction")

    def __init__(self, model_name: str, system_instruction: str | None = None):
        self._model = model_name
        self._system_instruction = system_instruction

    def generate_content(self, contents):
        return generate(
            contents,
            model=self._model,
            system_instruction=self._system_instruction,
        )


def model(model_name: str = FLASH, system_instruction: str | None = None) -> _ModelHandle:
    """Devuelve un handle compatible con el viejo ``GenerativeModel``.

    Reemplazo directo de::

        genai.configure(api_key=...)
        model = genai.GenerativeModel(name, system_instruction=...)

    por::

        from core import gemini
        model = gemini.model(name, system_instruction=...)
    """
    return _ModelHandle(model_name, system_instruction)
