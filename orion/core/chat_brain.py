"""
core.chat_brain — Enruta el chat principal al proveedor LLM activo.

El modo voz (audio bidireccional) es Gemini Live por diseño: ningún otro
proveedor expone una API equivalente. El chat de texto (ChatPanel), en
cambio, sí puede correr en cualquier proveedor OpenAI-compat ya que el
adapter ``orion.core.llm.openai_compat.OpenAICompatProvider`` cubre
DeepSeek, Ollama (local y cloud), OpenRouter, Groq, OpenAI y Mistral.

Diseño
------
- ``get_active_brain()`` devuelve el provider + model elegidos por el
  usuario (lee ``config/brain.json``). Default: ``gemini`` → no rompe
  comportamiento existente.
- ``is_live_brain()`` indica si el chat de texto debe ir por la sesión
  Live (Gemini) o por este módulo. El bus consulta esta función en cada
  ``submit_user_text``.
- ``run_text_turn(bus, text, *, tool_registry, plugin_registry)`` ejecuta
  un turno completo via :class:`LLMProvider`: arma historial, pasa tools,
  itera tool-call → respuesta → tool-call hasta cerrar, y emite los mismos
  eventos WS que ya consume el frontend (``chat.stream``, ``tool.call``).

El módulo NO depende de ``OrionLive`` ni de la sesión Live. Eso es lo
que permite que un usuario sin key de Gemini pueda chatear con DeepSeek
u Ollama desde el primer arranque.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orion._helpers import _load_system_prompt
from orion.config import CONFIG_DIR
from orion.core.llm.base import ToolSpec, get_provider, reset_config_cache
from orion.core.logger import get_logger

log = get_logger("chat_brain")

BRAIN_CONFIG_PATH: Path = CONFIG_DIR / "brain.json"

DEFAULT_BRAIN_PROVIDER = "gemini"
DEFAULT_BRAIN_MODEL = "gemini-2.5-flash"

# Modelos sugeridos por defecto al cambiar de provider. Lo usa la UI de
# Settings como pre-selección razonable.
DEFAULT_MODEL_PER_PROVIDER: dict[str, str] = {
    "gemini": "gemini-2.5-flash",
    "deepseek": "deepseek-chat",
    "ollama": "llama3.1:8b",
    "ollama_cloud": "glm-5.2:cloud",
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5",
}

# Cuántos turnos previos se incluyen al armar el contexto. Cap por turnos
# (no por tokens) — suficiente para conversaciones cortas sin saturar el
# context window de modelos pequeños como llama3.1:8b.
MAX_HISTORY_TURNS = 20

# Tope del loop de tool-calls. Si el modelo no resuelve en este número
# de iteraciones, cerramos con un mensaje amable.
MAX_TOOL_ITERATIONS = 8

# Truncado del result de cada tool antes de devolverlo al modelo: evita
# que un resultado gigante (un archivo entero, un dump JSON) reviente el
# context window.
MAX_TOOL_RESULT_CHARS = 8000


@dataclass(frozen=True)
class BrainConfig:
    """Snapshot inmutable del cerebro activo."""

    provider: str
    model: str


# ── Persistencia + cache ────────────────────────────────────────────────

_lock = threading.Lock()
_cached: BrainConfig | None = None


def get_active_brain() -> BrainConfig:
    """Lee ``config/brain.json``, cacheado. Si falta o está corrupto,
    devuelve Gemini por defecto (back-compat para usuarios existentes)."""
    global _cached
    if _cached is not None:
        return _cached
    with _lock:
        if _cached is not None:
            return _cached
        provider = DEFAULT_BRAIN_PROVIDER
        model = DEFAULT_BRAIN_MODEL
        try:
            if BRAIN_CONFIG_PATH.exists():
                raw = json.loads(BRAIN_CONFIG_PATH.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    p = str(raw.get("provider") or "").strip().lower()
                    m = str(raw.get("model") or "").strip()
                    if p:
                        provider = p
                    if m:
                        model = m
        except (json.JSONDecodeError, OSError) as e:
            log.warning("brain.json inválido (%s); uso default Gemini", e)
        _cached = BrainConfig(provider=provider, model=model)
        return _cached


def set_active_brain(provider: str, model: str) -> BrainConfig:
    """Persiste + invalida caches. NO reinicia la app."""
    global _cached
    provider = (provider or "").strip().lower()
    model = (model or "").strip()
    if not provider or not model:
        raise ValueError("provider y model son obligatorios")
    BRAIN_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    BRAIN_CONFIG_PATH.write_text(
        json.dumps({"provider": provider, "model": model}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    with _lock:
        _cached = BrainConfig(provider=provider, model=model)
    # Invalida también el cache de credenciales por si el provider nuevo
    # tiene una key recién agregada en providers.json.
    reset_config_cache()
    log.info("Cerebro cambiado a %s / %s", provider, model)
    return _cached


def reset_cache_for_tests() -> None:
    """Invalida el snapshot cacheado. Solo para tests."""
    global _cached
    with _lock:
        _cached = None


def is_live_brain() -> bool:
    """Indica si el chat de texto debe seguir el camino Live (Gemini).

    Cualquier otro proveedor pasa por :func:`run_text_turn`.
    """
    return get_active_brain().provider == "gemini"


# ── Ejecutor del turno (path no-Gemini) ─────────────────────────────────


def run_text_turn(
    bus: Any,
    text: str,
    *,
    tool_registry: Any | None = None,
    plugin_registry: Any | None = None,
    system_prompt: str | None = None,
) -> None:
    """Procesa un turno completo de chat vía LLMProvider.

    Pensado para correr en su propio thread daemon (lo lanza
    :meth:`OrionEventBus.submit_user_text` cuando el cerebro no es Gemini).
    Maneja:

      1. Persistencia del input del usuario (sin re-publicarlo al WS — el
         frontend ya lo pintó optimistamente).
      2. Carga del historial reciente desde la conversación activa.
      3. Loop de tool-calls usando el ToolRegistry compartido (los handlers
         se ejecutan sin la sesión Live, pasándole el bus como ``player``).
      4. Emisión del texto final por ``stream_chunk`` + persistencia.
      5. Manejo de errores con mensaje accionable en el chat.

    Args:
        bus:              OrionEventBus activo.
        text:             Texto que el usuario tipeó.
        tool_registry:    ToolRegistry compartido (si None, intenta singleton).
        plugin_registry:  PluginRegistry de OrionLive (si None, no usa plugins).
        system_prompt:    Override opcional. Default: prompt cargado de disk.
    """
    brain = get_active_brain()
    log.info(
        "run_text_turn provider=%s model=%s text=%s",
        brain.provider,
        brain.model,
        text[:60],
    )

    # 1) Persistir el input del usuario. El frontend ya lo agregó via
    # pushLocal antes de mandar el mensaje al WS — si emitimos también
    # stream_chunk(role="user") se duplicaría con la pieza optimista.
    bus.persist_log_only(f"Tú: {text}")

    bus.set_state("PENSANDO")
    turn_id = uuid.uuid4().hex[:12]

    # 2) Provider
    try:
        provider = get_provider(brain.provider)
    except Exception as e:
        log.exception("Provider %s no se pudo cargar", brain.provider)
        _emit_error(bus, turn_id, f"No se pudo cargar el proveedor «{brain.provider}»: {e}")
        return

    if not provider.is_available():
        _emit_error(
            bus,
            turn_id,
            f"El cerebro actual ({brain.provider}) no tiene credenciales configuradas. "
            "Andá a Ajustes → Cerebro para agregar la API key.",
        )
        return

    # 3) Tool registry resolver (singleton si no se pasó explícito)
    if tool_registry is None:
        try:
            from orion.core.tool_registry import ToolRegistry

            tool_registry = ToolRegistry()
        except Exception:  # pragma: no cover — el singleton no debería fallar
            tool_registry = None

    # 4) Mensajes: system + historial + nuevo turno
    sys_prompt = system_prompt or _load_system_prompt()
    # Device hint per-turn: a diferencia del Live (config one-shot), acá
    # podemos consultar `get_last_client()` en cada turno y ajustar el
    # tono al dispositivo desde donde llegó este mensaje. Si el cliente
    # no declaró device, queda vacío.
    from orion.core.client_context import build_device_hint

    device_hint = build_device_hint()
    if device_hint:
        sys_prompt = f"{sys_prompt}\n\n{device_hint}"
    history = _load_history_for_provider(bus, max_turns=MAX_HISTORY_TURNS)
    turns: list[dict] = [{"role": "system", "content": sys_prompt}]
    turns.extend(history)
    turns.append({"role": "user", "content": text})

    # 5) Tools disponibles. Filtramos las que son Live-only o silenciosas:
    # mismo criterio que el planner (decl.include_in_planner / decl.silent).
    tools: list[ToolSpec] = []
    if tool_registry is not None:
        for decl in tool_registry.all():
            if decl.silent or not decl.include_in_planner:
                continue
            tools.append(
                ToolSpec(
                    name=decl.name,
                    description=decl.description,
                    parameters=decl.parameters or {"type": "object", "properties": {}},
                )
            )

    final_text = ""
    for _iteration in range(MAX_TOOL_ITERATIONS):
        try:
            resp = provider.complete_with_tools(
                turns,
                tools,
                model=brain.model,
                temperature=0.4,
            )
        except NotImplementedError:
            # Si el provider no soporta function-calling, caemos al
            # complete plano (perdiendo tools pero conservando el chat).
            log.warning("Provider %s sin function-calling, caigo a complete plano", brain.provider)
            try:
                plain = provider.complete(
                    _turns_to_plain_messages(turns),
                    model=brain.model,
                    temperature=0.4,
                )
                final_text = plain.text.strip() or "(sin respuesta)"
            except Exception as e:
                log.exception("Provider %s falló también en complete", brain.provider)
                _emit_error(bus, turn_id, f"El proveedor {brain.provider} falló: {e}")
                return
            break
        except Exception as e:
            log.exception("Provider %s falló en complete_with_tools", brain.provider)
            _emit_error(bus, turn_id, f"El proveedor {brain.provider} falló: {e}")
            return

        # Sin tool_calls → respuesta final.
        if not resp.tool_calls:
            final_text = resp.text.strip() or "(sin respuesta)"
            break

        # Con tool_calls: registramos el turno del assistant y ejecutamos
        # cada tool, agregando su resultado como turno role=tool.
        turns.append(
            {
                "role": "assistant",
                "content": resp.text or None,
                "tool_calls": resp.tool_calls,
            }
        )
        for call in resp.tool_calls:
            name = call.get("name") or ""
            args = call.get("arguments") or {}
            call_id = call.get("id") or ""
            log.info("tool_call (chat_brain): %s args=%s", name, args)
            bus.publish(
                "tool.call.start",
                {"name": name, "args": {k: str(v)[:80] for k, v in args.items()}},
            )
            try:
                result_text = _dispatch_tool(
                    name,
                    args,
                    bus=bus,
                    tool_registry=tool_registry,
                    plugin_registry=plugin_registry,
                )
            except Exception as e:
                log.exception("Tool %s falló (chat_brain)", name)
                result_text = f"La herramienta '{name}' falló: {e}"
            finally:
                bus.publish("tool.call.end", {"name": name})
            turns.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": name,
                    "content": str(result_text)[:MAX_TOOL_RESULT_CHARS],
                }
            )
    else:
        final_text = (
            "Se agotó el máximo de iteraciones de herramientas sin llegar a una respuesta. "
            "Intenta reformular la consulta."
        )

    # 6) Emitir la respuesta final + persistir
    bus.stream_chunk(role="orion", delta=final_text, turn_id=turn_id, final=False)
    bus.stream_chunk(role="orion", delta="", turn_id=turn_id, final=True)
    bus.persist_log_only(f"Orion: {final_text}")
    bus.set_state("ESCUCHANDO")


# ── Helpers internos ────────────────────────────────────────────────────


def _emit_error(bus: Any, turn_id: str, msg: str) -> None:
    bus.stream_chunk(role="orion", delta=msg, turn_id=turn_id, final=False)
    bus.stream_chunk(role="orion", delta="", turn_id=turn_id, final=True)
    bus.persist_log_only(f"ERROR: {msg}")
    bus.set_state("ESCUCHANDO")


def _load_history_for_provider(bus: Any, *, max_turns: int) -> list[dict]:
    """Convierte los mensajes de la conversación activa al formato OpenAI.

    Filtra ``sys``/``err``/``file`` — esos son meta-mensajes que no aportan
    al contexto del LLM y solo gastan tokens. Excluye también el último
    mensaje del usuario porque será re-agregado por el caller.
    """
    conv = getattr(bus, "_conversation", None)
    if conv is None:
        return []
    try:
        msgs = conv.messages()
    except Exception:
        return []
    out: list[dict] = []
    for m in msgs:
        role_raw = m.get("role")
        text = (m.get("text") or "").strip()
        if not text:
            continue
        if role_raw == "user":
            out.append({"role": "user", "content": text})
        elif role_raw in ("ai", "assistant", "orion"):
            out.append({"role": "assistant", "content": text})
        # sys / err / file no entran al contexto del provider
    if len(out) > max_turns:
        out = out[-max_turns:]
    return out


def _turns_to_plain_messages(turns: list[dict]) -> list:
    """Para providers sin function-calling: aplana ``turns`` al formato
    ``[LLMMessage]`` que espera :meth:`LLMProvider.complete`."""
    from orion.core.llm.base import LLMMessage

    out: list[LLMMessage] = []
    for t in turns:
        role = t.get("role")
        content = t.get("content")
        if role in ("system", "user", "assistant") and content:
            out.append(LLMMessage(role=role, content=str(content)))
    return out


def _dispatch_tool(
    name: str,
    args: dict,
    *,
    bus: Any,
    tool_registry: Any,
    plugin_registry: Any,
) -> str:
    """Despacha una tool por nombre: primero ToolRegistry, después plugins.

    No usamos threading aquí — el caller corre en un thread daemon de por
    sí (lanzado por ``bus.submit_user_text``), así que un call sync no
    bloquea nada crítico. Sí cortamos timeouts largos vía un signal-like
    en el futuro si hace falta — por ahora dejamos que el provider HTTP
    timeoutee según su propio cliente.
    """
    if tool_registry is not None and tool_registry.has(name):
        return tool_registry.call_sync(
            name,
            args,
            player=bus,
            speak=lambda _t: None,  # sin voz en chat texto
            current_file=getattr(bus, "current_file", None),
        )
    if plugin_registry is not None:
        plug = plugin_registry.get(name)
        if plug is not None:
            return plug.execute(args, player=bus, speak=lambda _t: None)
    return f"Herramienta desconocida: {name}"
