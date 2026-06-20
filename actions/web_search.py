# web_search.py
from utils.cache import ttl_cache


# El cache se aplica a las funciones internas (no al wrapper público) para
# que también beneficie a las llamadas internas de _compare(). 5 minutos es
# suficiente para evitar repetir la misma búsqueda en una sesión.
@ttl_cache(ttl_seconds=300, max_entries=64, skip_if=lambda r: not r or len(str(r)) < 20)
def _gemini_search(query: str) -> str:
    from core import gemini

    client = gemini.get_client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=query,
        config={"tools": [{"google_search": {}}]},
    )

    text = ""
    for part in response.candidates[0].content.parts:
        if hasattr(part, "text") and part.text:
            text += part.text

    text = text.strip()
    if not text:
        raise ValueError("Gemini devolvió una respuesta vacía.")
    return text


@ttl_cache(ttl_seconds=300, max_entries=64, skip_if=lambda r: not r)
def _ddg_search(query: str, max_results: int = 6) -> list[dict]:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS

    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append(
                {
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", ""),
                }
            )
    return results


def _format_ddg(query: str, results: list[dict]) -> str:
    if not results:
        return f"No se encontraron resultados para: {query}"

    lines = [f"Resultados de búsqueda para: {query}\n"]
    for i, r in enumerate(results, 1):
        if r.get("title"):
            lines.append(f"{i}. {r['title']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
        if r.get("url"):
            lines.append(f"   {r['url']}")
        lines.append("")
    return "\n".join(lines).strip()


def _compare(items: list[str], aspect: str) -> str:
    query = (
        f"Compara {', '.join(items)} en términos de {aspect}. "
        "Proporciona datos y hechos específicos."
    )
    try:
        return _gemini_search(query)
    except Exception as e:
        print(f"[WebSearch] ⚠️ Falló la comparación con Gemini: {e} — usando DDG como respaldo")

    # DDG fallback: fetch results per item and merge
    all_results: dict[str, list] = {}
    for item in items:
        try:
            all_results[item] = _ddg_search(f"{item} {aspect}", max_results=3)
        except Exception:
            all_results[item] = []

    lines = [f"Comparación — {aspect.upper()}", "─" * 40]
    for item in items:
        lines.append(f"\n▸ {item}")
        for r in all_results.get(item, [])[:2]:
            if r.get("snippet"):
                lines.append(f"  • {r['snippet']}")
    return "\n".join(lines)


from core.tool_registry import tool


@tool(
    name="web_search",
    description="Searches the web for any information.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Search query"},
            "mode": {"type": "STRING", "description": "search (default) or compare"},
            "items": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "Items to compare",
            },
            "aspect": {"type": "STRING", "description": "price | specs | reviews"},
        },
        "required": ["query"],
    },
)
def web_search(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    query = params.get("query", "").strip()
    mode = params.get("mode", "search").lower().strip()
    items = params.get("items", [])
    aspect = params.get("aspect", "general").strip() or "general"

    if not query and not items:
        return "Por favor, proporcione una consulta de búsqueda, señor."

    if items and mode != "compare":
        mode = "compare"

    if player:
        player.write_log(f"[Search] {query or ', '.join(items)}")

    print(f"[WebSearch] 🔍 Consulta: {query!r}  Modo: {mode}")

    try:
        if mode == "compare" and items:
            print(f"[WebSearch] 📊 Comparando: {items}")
            result = _compare(items, aspect)
            print("[WebSearch] ✅ Comparación finalizada.")
            return result

        print("[WebSearch] 🌐 Intentando con Gemini...")
        try:
            result = _gemini_search(query)
            print("[WebSearch] ✅ Gemini OK.")
            return result
        except Exception as e:
            print(f"[WebSearch] ⚠️ Gemini falló ({e}) — intentando con DDG...")
            results = _ddg_search(query)
            result = _format_ddg(query, results)
            print(f"[WebSearch] ✅ DDG: {len(results)} resultado(s).")
            return result

    except Exception as e:
        print(f"[WebSearch] ❌ Todos los backends fallaron: {e}")
        return f"La búsqueda falló, señor: {e}"
