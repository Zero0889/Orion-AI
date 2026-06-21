"""
actions.notebooklm_research — Investigación dinámica vía NotebookLM
==================================================================
Expone el research agent de Google NotebookLM como tool de O.R.I.O.N.

Acciones soportadas:
  - research  (default): crea un notebook, dispara el research agent
                         (fast/deep, web/drive), espera, importa fuentes
                         y devuelve la URL del notebook.
  - list     : lista los notebooks del usuario.
  - ask      : pregunta a un notebook existente (chat grounded).
  - delete   : borra un notebook por id.

El primer uso requiere `notebooklm login` (ver docs/notebooklm.md).
La sesión queda guardada en ~/.notebooklm/profiles/default/storage_state.json.

Diseño: el wrapper es sync (lo invoca el ToolRegistry síncrono), pero
adentro corre asyncio.run() porque la SDK es async.
"""

from __future__ import annotations

import asyncio
from typing import Any
import contextlib

_LOGIN_HINT = (
    "NotebookLM aún no está autenticado. Ejecuta una sola vez:\n"
    '  .venv\\Scripts\\pip.exe install "notebooklm-py[browser]"\n'
    "  .venv\\Scripts\\notebooklm.exe login\n"
    "Se abrirá Chromium para iniciar sesión con tu cuenta Google."
)


def _ensure_auth() -> str | None:
    """Devuelve None si hay sesión guardada, o un mensaje de error."""
    try:
        from notebooklm.paths import get_storage_path
    except ImportError:
        return (
            "notebooklm-py no está instalado en el venv. "
            'Ejecuta: .venv\\Scripts\\pip.exe install "notebooklm-py[browser]"'
        )
    path = get_storage_path()
    if not path.exists():
        return _LOGIN_HINT
    return None


def _notebook_url(notebook_id: str) -> str:
    return f"https://notebooklm.google.com/notebook/{notebook_id}"


def _speak(player, text: str) -> None:
    if player is None:
        return
    try:
        player.speak(text)
    except Exception:
        with contextlib.suppress(Exception):
            player(text)


# ── Acciones async ──────────────────────────────────────────────────────


async def _do_research(
    *,
    topic: str,
    n_sources: int,
    mode: str,
    source: str,
    auto_import: bool,
    notebook_name: str | None,
    timeout: float,
) -> dict[str, Any]:
    from notebooklm import NotebookLMClient

    title = notebook_name or topic[:80]
    async with NotebookLMClient.from_storage() as client:
        notebook = await client.notebooks.create(title)
        notebook_id = notebook.id

        query = topic
        if n_sources:
            query = f"{topic} (encuentra hasta {n_sources} fuentes relevantes)"

        start = await client.research.start(notebook_id, query, source=source, mode=mode)
        task = await client.research.wait_for_completion(
            notebook_id, task_id=start.task_id, timeout=timeout
        )

        imported: list[dict[str, str]] = []
        import_error: str | None = None
        sources_found = getattr(task, "sources", None) or []
        if auto_import and sources_found:
            inputs = sources_found[:n_sources] if n_sources else sources_found
            # IMPORT_RESEARCH es la RPC más frágil del flow — NotebookLM
            # frecuentemente le tira TransportServerError / timeout y la
            # lib ya hace sus propios retries. Si igual falla, NO
            # tiramos toda la investigación a la basura: el notebook ya
            # está creado con las fuentes encontradas; el usuario puede
            # abrirlo y agregarlas manualmente desde la UI de NotebookLM.
            try:
                imported = await client.research.import_sources(notebook_id, start.task_id, inputs)
            except Exception as e:
                import_error = f"{type(e).__name__}: {str(e)[:120]}"

        return {
            "notebook_id": notebook_id,
            "notebook_url": _notebook_url(notebook_id),
            "title": title,
            "mode": mode,
            "source": source,
            "task_id": start.task_id,
            "sources_found": len(sources_found),
            "sources_imported": len(imported),
            "import_error": import_error,
        }


async def _do_list(limit: int) -> dict[str, Any]:
    from notebooklm import NotebookLMClient

    async with NotebookLMClient.from_storage() as client:
        notebooks = await client.notebooks.list()
        items = []
        for nb in notebooks[:limit]:
            items.append(
                {
                    "id": nb.id,
                    "title": getattr(nb, "title", "") or "",
                    "url": _notebook_url(nb.id),
                }
            )
        return {"count": len(items), "notebooks": items}


async def _do_ask(notebook_id: str, question: str) -> dict[str, Any]:
    from notebooklm import NotebookLMClient

    async with NotebookLMClient.from_storage() as client:
        result = await client.chat.ask(notebook_id, question)
        answer = getattr(result, "answer", None) or getattr(result, "text", "") or str(result)
        refs = getattr(result, "references", None) or []
        return {
            "notebook_id": notebook_id,
            "answer": answer,
            "references": [
                {
                    "title": getattr(r, "title", "") or "",
                    "url": getattr(r, "url", "") or "",
                }
                for r in refs
            ][:20],
        }


async def _do_delete(notebook_id: str) -> dict[str, Any]:
    from notebooklm import NotebookLMClient

    async with NotebookLMClient.from_storage() as client:
        await client.notebooks.delete(notebook_id)
        return {"notebook_id": notebook_id, "deleted": True}


# ── Entry point sync (lo llama el ToolRegistry) ─────────────────────────


def _format_research_result(r: dict[str, Any]) -> str:
    lines = [
        f"Notebook creado: {r['title']}",
        f"URL: {r['notebook_url']}",
        f"Modo: {r['mode']} | Fuente: {r['source']}",
        f"Fuentes encontradas: {r['sources_found']} | Importadas: {r['sources_imported']}",
    ]
    # Caso típico: la búsqueda funcionó pero el auto-import falló por
    # un timeout/transporte de NotebookLM. Comunicamos AMBAS cosas
    # claro: la investigación NO se perdió, solo hay que importar a mano.
    if r.get("import_error") and r["sources_found"] > 0:
        lines.append("")
        lines.append(
            f"Aviso: el auto-import fallo ({r['import_error']}). "
            f"Abri el notebook en {r['notebook_url']} y usa 'Agregar fuente' "
            f"para importarlas manualmente - las fuentes ya fueron encontradas."
        )
    return "\n".join(lines)


def _format_list_result(r: dict[str, Any]) -> str:
    if not r["notebooks"]:
        return "No tienes notebooks en NotebookLM."
    lines = [f"Notebooks ({r['count']}):"]
    for nb in r["notebooks"]:
        title = nb["title"] or "(sin título)"
        lines.append(f"  • {title} — {nb['url']}")
    return "\n".join(lines)


def _format_ask_result(r: dict[str, Any]) -> str:
    out = [r["answer"]]
    if r["references"]:
        out.append("\nFuentes citadas:")
        for ref in r["references"]:
            label = ref["title"] or ref["url"] or "(sin título)"
            out.append(f"  • {label}")
    return "\n".join(out)


from orion.core.tool_registry import tool


@tool(
    name="notebooklm_research",
    description=(
        "Investigación dinámica con Google NotebookLM. SUSTITUYE a web_search "
        "cuando el usuario pide investigar un tema con MÚLTIPLES fuentes, generar "
        "un notebook de referencias, o quiere abrir el resultado en notebooklm.google.com. "
        "Acciones: "
        "research (default) — crea un notebook nuevo y dispara el research agent "
        "de Google para buscar fuentes web o Drive y auto-importarlas; "
        "list — lista los notebooks existentes del usuario; "
        "ask — hace una pregunta a un notebook ya creado (respuesta grounded con citas); "
        "delete — elimina un notebook por id. "
        "Para 'research' devuelve la URL del notebook listo para abrir en el navegador. "
        "Modo 'fast' (~minutos) vs 'deep' (~10-30 min, fuentes más exhaustivas). "
        "Source 'web' (default) busca en internet, 'drive' busca en tu Google Drive."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "research (default) | list | ask | delete",
            },
            "topic": {
                "type": "STRING",
                "description": "Tema a investigar (para action=research). Sé específico: incluye fechas, ámbito, idioma si aplica.",
            },
            "n_sources": {
                "type": "INTEGER",
                "description": "Número objetivo de fuentes a importar (default 20).",
            },
            "mode": {
                "type": "STRING",
                "description": "fast (default, ~minutos) | deep (búsqueda exhaustiva, ~10-30 min).",
            },
            "source": {
                "type": "STRING",
                "description": "web (default, busca en internet) | drive (busca en Google Drive del usuario).",
            },
            "auto_import": {
                "type": "BOOLEAN",
                "description": "Importa automáticamente las fuentes encontradas al notebook (default true).",
            },
            "notebook_name": {
                "type": "STRING",
                "description": "Título personalizado del notebook. Si se omite, se usa el topic.",
            },
            "notebook_id": {
                "type": "STRING",
                "description": "ID del notebook (para action=ask o action=delete).",
            },
            "question": {"type": "STRING", "description": "Pregunta para action=ask."},
            "limit": {
                "type": "INTEGER",
                "description": "Máximo de notebooks a devolver en action=list (default 30).",
            },
            "timeout": {
                "type": "NUMBER",
                "description": "Timeout en segundos para esperar el research (default 1800 = 30 min).",
            },
        },
        "required": [],
    },
    timeout=1900,
)
def notebooklm_research(parameters: dict, *, player=None, **_) -> str:
    action = (parameters.get("action") or "research").strip().lower()

    auth_error = _ensure_auth()
    if auth_error:
        return auth_error

    try:
        if action == "research":
            topic = (parameters.get("topic") or "").strip()
            if not topic:
                return "Falta 'topic': describe qué quieres investigar."
            n_sources = int(parameters.get("n_sources") or 20)
            mode = (parameters.get("mode") or "fast").strip().lower()
            if mode not in ("fast", "deep"):
                mode = "fast"
            source = (parameters.get("source") or "web").strip().lower()
            if source not in ("web", "drive"):
                source = "web"
            auto_import = bool(parameters.get("auto_import", True))
            notebook_name = parameters.get("notebook_name")
            timeout = float(parameters.get("timeout") or 1800)

            _speak(player, f"Iniciando investigación en NotebookLM sobre {topic}.")
            result = asyncio.run(
                _do_research(
                    topic=topic,
                    n_sources=n_sources,
                    mode=mode,
                    source=source,
                    auto_import=auto_import,
                    notebook_name=notebook_name,
                    timeout=timeout,
                )
            )
            return _format_research_result(result)

        if action == "list":
            limit = int(parameters.get("limit") or 30)
            return _format_list_result(asyncio.run(_do_list(limit)))

        if action == "ask":
            notebook_id = (parameters.get("notebook_id") or "").strip()
            question = (parameters.get("question") or "").strip()
            if not notebook_id or not question:
                return "Para 'ask' necesito 'notebook_id' y 'question'."
            return _format_ask_result(asyncio.run(_do_ask(notebook_id, question)))

        if action == "delete":
            notebook_id = (parameters.get("notebook_id") or "").strip()
            if not notebook_id:
                return "Para 'delete' necesito 'notebook_id'."
            asyncio.run(_do_delete(notebook_id))
            return f"Notebook {notebook_id} eliminado."

        return f"Acción desconocida: {action!r}. Usa: research | list | ask | delete"

    except Exception as e:
        # Si el error parece de auth (401, redirect a accounts.google.com,
        # storage_state inválido) damos instrucciones claras: hay que
        # re-loguear vía CLI, NO basta con clickear el link OAuth que
        # devuelve la lib — porque el OAuth web no escribe en el storage
        # local de notebooklm-py.
        msg = str(e).lower()
        looks_like_auth = (
            "401" in msg
            or "unauthorized" in msg
            or "accounts.google.com" in msg
            or "login" in msg
            or "authentic" in msg
            or "storage_state" in msg
            or "sign in" in msg
        )
        if looks_like_auth:
            return (
                "La sesión de NotebookLM expiró. Para reconectarte:\n"
                "  1) Abrí una terminal nueva.\n"
                "  2) Corré: .venv\\Scripts\\notebooklm.exe login\n"
                "  3) Se va a abrir Chromium — iniciá sesión con tu cuenta Google.\n"
                "  4) Volvé a pedirme la investigación.\n"
                "(El link que Google muestra en el mensaje de error NO sirve por sí solo "
                "— necesita el CLI para guardar la sesión en disco.)"
            )
        return f"NotebookLM falló: {type(e).__name__}: {e}"
