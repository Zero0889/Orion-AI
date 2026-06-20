import time
import webbrowser
from urllib.parse import quote_plus
import contextlib

# Cache simple: evita reabrir el navegador si el usuario pregunta la misma
# ciudad varias veces seguidas (ventana de 2 minutos).
_WEATHER_CACHE: dict[tuple[str, str], float] = {}
_WEATHER_TTL = 120  # segundos


def weather_action(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    city = parameters.get("city")
    when = parameters.get("time", "today")

    if not city or not isinstance(city, str) or not city.strip():
        msg = "Señor, falta la ciudad para el reporte del clima."
        _log(msg, player)
        return msg

    city = city.strip()
    when = (when or "today").strip()

    search_query = f"weather in {city} {when}"
    url = f"https://www.google.com/search?q={quote_plus(search_query)}"

    # ── Cache: no reabrir si ya se consultó hace poco ──
    now = time.time()
    cache_key = (city.lower(), when.lower())
    last = _WEATHER_CACHE.get(cache_key)
    if last is not None and (now - last) < _WEATHER_TTL:
        msg = f"Ya tienes el clima de {city} abierto, señor (actualizado hace menos de 2 minutos)."
        _log(msg, player)
        return msg

    try:
        opened = webbrowser.open(url)
        if not opened:
            raise RuntimeError("webbrowser.open returned False")
    except Exception as e:
        msg = f"Señor, no pude abrir el navegador para el reporte del clima: {e}"
        _log(msg, player)
        return msg

    _WEATHER_CACHE[cache_key] = now
    # Limpieza ocasional para que el dict no crezca sin límite
    if len(_WEATHER_CACHE) > 50:
        cutoff = now - _WEATHER_TTL
        for k in [k for k, t in _WEATHER_CACHE.items() if t < cutoff]:
            _WEATHER_CACHE.pop(k, None)

    msg = f"Mostrando el clima de {city}, {when}, señor."
    _log(msg, player)

    if session_memory:
        with contextlib.suppress(Exception):
            session_memory.set_last_search(query=search_query, response=msg)

    return msg


def _log(message: str, player=None) -> None:
    print(f"[Weather] {message}")
    if player:
        with contextlib.suppress(Exception):
            player.write_log(f"O.R.I.O.N: {message}")
