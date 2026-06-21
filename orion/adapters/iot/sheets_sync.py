"""
actions.iot.sheets_sync — Sync continuo del log de sensores a Google Sheets
============================================================================
Cada N minutos lee las filas nuevas del CSV persistente (las que se
agregaron desde el último push exitoso) y las appendea a una hoja de
Google Sheets vía el CLI ``gog``.

Estado persistido en ``config/iot_sheets.json``:
  - enabled        : si está corriendo la sync
  - account        : email asociado a la hoja
  - spreadsheet_id : id único de Google Sheets
  - spreadsheet_url: link directo para abrir
  - sheet_name     : nombre de la pestaña dentro del Sheet (default "Sensores")
  - last_pushed_row: índice 0-based de la última fila del CSV ya pusheada
                     (no cuenta el header)
  - last_sync_at   : ISO 8601 del último push exitoso
  - last_error     : última excepción (se limpia en éxito)
  - sync_interval_s: cadencia del sync (default 300s = 5 min)

Resiliencia:
  * Si gog se queda sin auth, el sync falla pero el CSV local sigue
    creciendo. Al re-autenticar y volver a habilitar, el sync hace
    backfill desde donde quedó.
  * Si el Sheet fue eliminado a mano en Drive, las llamadas a append
    fallan; el módulo loguea el error y reintenta. Hay que disconnect
    + connect para regenerar.
"""

from __future__ import annotations

import csv
import json
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from orion.core.logger import get_logger

log = get_logger("iot.sheets_sync")


# ── Constantes ──────────────────────────────────────────────────────────
DEFAULT_SYNC_INTERVAL_S = 60  # 1 minuto — sentir el dato "casi en vivo"
DEFAULT_SHEET_NAME = "Sensores"
HEADER_ROW = ["timestamp", "device", "value", "unit", "samples"]

# Paleta del formato inicial. Tonos sobrios para que el Sheet sea legible
# tanto en monitor como impreso. Coinciden con la estética oscura/azul
# de los headers de las exportaciones XLSX del datalogger.
_HEADER_BG = {"red": 0.122, "green": 0.161, "blue": 0.216}  # #1F2937
_HEADER_FG = {"red": 1.0, "green": 1.0, "blue": 1.0}  # blanco
_BAND_HEADER = {"red": 0.122, "green": 0.161, "blue": 0.216}  # #1F2937
_BAND_FIRST = {"red": 1.0, "green": 1.0, "blue": 1.0}  # #FFFFFF
_BAND_SECOND = {"red": 0.961, "green": 0.969, "blue": 0.984}  # #F5F7FB


# ── Paths ──────────────────────────────────────────────────────────────
def _project_root() -> Path:
    from orion.config import IOT_CONFIG_PATH

    return IOT_CONFIG_PATH.parent.parent


def _state_path() -> Path:
    return _project_root() / "config" / "iot_sheets.json"


def _gog_exe() -> Path:
    return _project_root() / "tools" / "gog" / "gog.exe"


def _csv_path() -> Path:
    return _project_root() / "data" / "iot_sensor_log.csv"


# ── Estado en disco ────────────────────────────────────────────────────
_DEFAULT_STATE = {
    "enabled": False,
    "account": None,
    "spreadsheet_id": None,
    "spreadsheet_url": None,
    "sheet_name": DEFAULT_SHEET_NAME,
    "last_pushed_row": 0,
    "last_sync_at": None,
    "last_error": None,
    "sync_interval_s": DEFAULT_SYNC_INTERVAL_S,
}

_state_lock = threading.Lock()


def _load_state() -> dict:
    p = _state_path()
    if not p.exists():
        return dict(_DEFAULT_STATE)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        merged = dict(_DEFAULT_STATE)
        merged.update(data)
        return merged
    except Exception as e:
        log.warning("state corrupto, uso defaults: %s", e)
        return dict(_DEFAULT_STATE)


def _save_state(state: dict) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def status() -> dict:
    """Snapshot del estado actual (para la UI)."""
    with _state_lock:
        return _load_state()


# ── Llamadas a gog ─────────────────────────────────────────────────────
def _run_gog(args: list[str], timeout: int = 30) -> dict:
    """Corre gog con --json --no-input y devuelve el dict parseado.
    Lanza RuntimeError con mensaje útil si falla."""
    gog = _gog_exe()
    if not gog.exists():
        raise RuntimeError(f"gog no encontrado en {gog}")
    cmd = [str(gog), *args, "--json", "--no-input"]
    log.debug("exec: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"gog timeout ({timeout}s)") from e
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:500]
        raise RuntimeError(f"gog exit {proc.returncode}: {err}")
    out = (proc.stdout or "").strip()
    if not out:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"raw": out}


def _gog_create_sheet(account: str, title: str) -> tuple[str, str]:
    """Crea un Sheet nuevo. Devuelve (id, url)."""
    data = _run_gog(["sheets", "create", title, "-a", account])
    sid = data.get("spreadsheetId") or data.get("id") or ""
    url = data.get("spreadsheetUrl") or data.get("url") or ""
    if not sid:
        # Algunas variantes meten el dict bajo otro nombre
        result = data.get("result") if isinstance(data, dict) else None
        if isinstance(result, dict):
            sid = result.get("spreadsheetId") or sid
            url = result.get("spreadsheetUrl") or url
    if not sid:
        raise RuntimeError(f"no se obtuvo spreadsheetId; respuesta: {data}")
    if not url:
        url = f"https://docs.google.com/spreadsheets/d/{sid}"
    return sid, url


def _gog_default_tab(account: str, sid: str) -> str:
    """Devuelve el nombre real de la primera pestaña del Sheet. En cuentas
    en español es 'Hoja 1', en inglés 'Sheet1', etc. — Google se lo asigna
    según la locale del usuario."""
    data = _run_gog(["sheets", "metadata", sid, "-a", account])
    # La estructura típica: {sheets: [{properties: {title: "...", sheetId: 0}}, ...]}
    sheets = data.get("sheets") or []
    if sheets and isinstance(sheets, list):
        first = sheets[0]
        props = first.get("properties") if isinstance(first, dict) else None
        if isinstance(props, dict):
            title = props.get("title")
            if title:
                return str(title)
    # Fallback: probemos los nombres conocidos
    return "Sheet1"


def _gog_format_sheet(account: str, sid: str, sheet_name: str) -> None:
    """Aplica el formato 'bonito' al Sheet: cabecera estilizada, freeze de
    la primera fila, autoancho de columnas, formato de fecha en la columna
    de timestamp, número con decimales en la columna ``value``, entero en
    ``samples`` y bandas alternadas.

    Cada paso se intenta de forma aislada: si uno falla (p. ej. la API se
    enoja por una banda duplicada al re-formatear) no abortamos el resto.
    Eso hace que :func:`reformat` sea idempotente.
    """
    rng_header = f"{sheet_name}!A1:E1"
    rng_data_ts = f"{sheet_name}!A2:A"
    rng_data_val = f"{sheet_name}!C2:C"
    rng_data_n = f"{sheet_name}!E2:E"
    rng_table = f"{sheet_name}!A1:E1000"
    rng_cols = f"{sheet_name}!A:E"

    # 1) Cabecera: negrita, blanco sobre azul oscuro, centrada
    header_fmt = {
        "backgroundColor": _HEADER_BG,
        "horizontalAlignment": "CENTER",
        "verticalAlignment": "MIDDLE",
        "textFormat": {
            "foregroundColor": _HEADER_FG,
            "bold": True,
            "fontSize": 11,
        },
    }
    _safe_gog(
        [
            "sheets",
            "format",
            sid,
            rng_header,
            "--format-json",
            json.dumps({"userEnteredFormat": header_fmt}),
            "--format-fields",
            "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)",
            "-a",
            account,
        ]
    )

    # 2) Freeze de la primera fila — la cabecera queda visible al hacer scroll
    _safe_gog(["sheets", "freeze", sid, "--rows", "1", "--sheet", sheet_name, "-a", account])

    # 3) Auto-ancho de columnas A:E (timestamp queda holgado, samples chiquito)
    _safe_gog(["sheets", "resize-columns", sid, rng_cols, "--auto", "-a", account])

    # 4) Formato de fecha legible en la columna A (Google parsea el ISO al input)
    _safe_gog(
        [
            "sheets",
            "number-format",
            sid,
            rng_data_ts,
            "--type",
            "DATE_TIME",
            "--pattern",
            "yyyy-mm-dd hh:mm",
            "-a",
            account,
        ]
    )

    # 5) Valor con hasta 2 decimales (sin ceros sobrantes)
    _safe_gog(
        [
            "sheets",
            "number-format",
            sid,
            rng_data_val,
            "--type",
            "NUMBER",
            "--pattern",
            "0.0##",
            "-a",
            account,
        ]
    )

    # 6) Samples entero
    _safe_gog(
        [
            "sheets",
            "number-format",
            sid,
            rng_data_n,
            "--type",
            "NUMBER",
            "--pattern",
            "0",
            "-a",
            account,
        ]
    )

    # 7) Bandas alternadas. Si ya existe, la API tira error → lo ignoramos
    band = {
        "headerColor": _BAND_HEADER,
        "firstBandColor": _BAND_FIRST,
        "secondBandColor": _BAND_SECOND,
    }
    _safe_gog(
        [
            "sheets",
            "banding",
            "create",
            sid,
            rng_table,
            "--row-properties-json",
            json.dumps(band),
            "-a",
            account,
        ]
    )

    # 8) Pestaña "Gráficos" con QUERY pivotada + line charts de 24h y 1h
    try:
        _gog_ensure_charts_tab(account, sid, sheet_name)
    except Exception as e:
        log.debug("pestaña Gráficos falló (ignorado): %s", e)


CHARTS_TAB_NAME = "Gráficos"


def _quote_sheet(name: str) -> str:
    """Si el nombre de pestaña tiene espacios o acentos, hay que envolverlo
    entre comillas simples para usarlo en una fórmula (`'Hoja 1'!A:E`).
    Las comillas internas se duplican."""
    if any(c in name for c in " '\"áéíóúñ"):
        return "'" + name.replace("'", "''") + "'"
    return name


def _gog_sheet_id(account: str, sid: str, tab_name: str) -> int | None:
    """Devuelve el sheetId numérico de una pestaña por su nombre, o None."""
    try:
        data = _run_gog(["sheets", "metadata", sid, "-a", account])
    except Exception:
        return None
    for sh in data.get("sheets") or []:
        props = sh.get("properties") if isinstance(sh, dict) else None
        if isinstance(props, dict) and props.get("title") == tab_name:
            sid_num = props.get("sheetId")
            return int(sid_num) if sid_num is not None else None
    return None


def _gog_ensure_charts_tab(account: str, sid: str, data_tab: str) -> int | None:
    """Crea la pestaña 'Gráficos' si no existe y la rellena con dos QUERY:
    pivot wide de la última hora y de las últimas 24 h. Encima ancla dos
    line charts (uno por rango). Devuelve el sheetId de 'Gráficos'."""
    # 1) Crear pestaña si no existe (add-tab tira error si ya estaba)
    existing_id = _gog_sheet_id(account, sid, CHARTS_TAB_NAME)
    if existing_id is None:
        try:
            _run_gog(["sheets", "add-tab", sid, CHARTS_TAB_NAME, "-a", account])
        except Exception as e:
            log.debug("add-tab '%s' falló (¿ya existía?): %s", CHARTS_TAB_NAME, e)
        existing_id = _gog_sheet_id(account, sid, CHARTS_TAB_NAME)
    if existing_id is None:
        return None

    qtab = _quote_sheet(data_tab)

    # 2) Layout de la pestaña:
    #    A1: título 24h        | A3: QUERY pivot 24h (A3..)
    #    L1: título 1h         | L3: QUERY pivot 1h  (L3..)
    #    Se anclan dos charts debajo de cada bloque.
    #
    # La QUERY:
    #   - SELECT A, AVG(C)  → timestamp + valor promedio
    #   - PIVOT B           → una columna por dispositivo
    #   - ORDER BY A DESC LIMIT N → últimos N minutos de datos
    #   - SORT(..., 1, TRUE) por fuera → orden ASC para que la línea
    #     del chart avance de izquierda a derecha en el tiempo
    title_fmt = {
        "userEnteredFormat": {
            "textFormat": {"bold": True, "fontSize": 12},
            "horizontalAlignment": "LEFT",
        }
    }
    _safe_gog(
        [
            "sheets",
            "update",
            sid,
            f"{CHARTS_TAB_NAME}!A1",
            "Últimas 24 horas",
            "-a",
            account,
            "--input",
            "USER_ENTERED",
        ]
    )
    _safe_gog(
        [
            "sheets",
            "update",
            sid,
            f"{CHARTS_TAB_NAME}!L1",
            "Última hora",
            "-a",
            account,
            "--input",
            "USER_ENTERED",
        ]
    )
    _safe_gog(
        [
            "sheets",
            "format",
            sid,
            f"{CHARTS_TAB_NAME}!A1:A1",
            "--format-json",
            json.dumps(title_fmt),
            "--format-fields",
            "userEnteredFormat(textFormat,horizontalAlignment)",
            "-a",
            account,
        ]
    )
    _safe_gog(
        [
            "sheets",
            "format",
            sid,
            f"{CHARTS_TAB_NAME}!L1:L1",
            "--format-json",
            json.dumps(title_fmt),
            "--format-fields",
            "userEnteredFormat(textFormat,horizontalAlignment)",
            "-a",
            account,
        ]
    )

    # 1440 muestras = 24h con 1 fila/min; 60 = 1 hora
    q_24h = (
        f"=IFERROR(SORT(QUERY({qtab}!A2:E,"
        f'"SELECT A, AVG(C) WHERE B IS NOT NULL '
        f"GROUP BY A PIVOT B ORDER BY A DESC LIMIT 1440 LABEL A 'timestamp'\""
        f'),1,TRUE),"Sin datos aún")'
    )
    q_1h = (
        f"=IFERROR(SORT(QUERY({qtab}!A2:E,"
        f'"SELECT A, AVG(C) WHERE B IS NOT NULL '
        f"GROUP BY A PIVOT B ORDER BY A DESC LIMIT 60 LABEL A 'timestamp'\""
        f'),1,TRUE),"Sin datos aún")'
    )
    _safe_gog(
        [
            "sheets",
            "update",
            sid,
            f"{CHARTS_TAB_NAME}!A3",
            q_24h,
            "-a",
            account,
            "--input",
            "USER_ENTERED",
        ]
    )
    _safe_gog(
        [
            "sheets",
            "update",
            sid,
            f"{CHARTS_TAB_NAME}!L3",
            q_1h,
            "-a",
            account,
            "--input",
            "USER_ENTERED",
        ]
    )

    # 3) Charts embebidos. Dos LINE charts: uno por bloque.
    _gog_ensure_chart(
        account,
        sid,
        existing_id,
        title="Sensores · últimas 24 h",
        data_start_col=0,
        data_end_col=10,
        data_row_end=1500,
        anchor_row=25,
        anchor_col=0,
    )
    _gog_ensure_chart(
        account,
        sid,
        existing_id,
        title="Sensores · última hora",
        data_start_col=11,
        data_end_col=20,
        data_row_end=100,
        anchor_row=25,
        anchor_col=11,
    )
    return existing_id


def _gog_ensure_chart(
    account: str,
    sid: str,
    sheet_id: int,
    *,
    title: str,
    data_start_col: int,
    data_end_col: int,
    data_row_end: int,
    anchor_row: int,
    anchor_col: int,
) -> None:
    """Crea un line chart ya configurado para los datos pivotados. Si ya
    existe un chart con el mismo título, lo reemplaza."""
    # Detectar charts existentes con el mismo título y borrarlos para no
    # acumular duplicados en cada reformat.
    try:
        listing = _run_gog(["sheets", "chart", "list", sid, "-a", account])
        charts = listing.get("charts") if isinstance(listing, dict) else None
        if isinstance(charts, list):
            for ch in charts:
                spec = ch.get("spec") if isinstance(ch, dict) else None
                if isinstance(spec, dict) and spec.get("title") == title:
                    cid = ch.get("chartId")
                    if cid is not None:
                        _safe_gog(["sheets", "chart", "delete", sid, str(cid), "-a", account, "-y"])
    except Exception as e:
        log.debug("chart list/delete previo falló (ignorado): %s", e)

    spec = {
        "title": title,
        "basicChart": {
            "chartType": "LINE",
            "legendPosition": "BOTTOM_LEGEND",
            "headerCount": 1,
            "axis": [
                {"position": "BOTTOM_AXIS", "title": "Tiempo"},
                {"position": "LEFT_AXIS", "title": "Valor"},
            ],
            "domains": [
                {
                    "domain": {
                        "sourceRange": {
                            "sources": [
                                {
                                    "sheetId": sheet_id,
                                    "startRowIndex": 2,
                                    "endRowIndex": data_row_end,
                                    "startColumnIndex": data_start_col,
                                    "endColumnIndex": data_start_col + 1,
                                }
                            ]
                        }
                    }
                }
            ],
            "series": [
                {
                    "series": {
                        "sourceRange": {
                            "sources": [
                                {
                                    "sheetId": sheet_id,
                                    "startRowIndex": 2,
                                    "endRowIndex": data_row_end,
                                    "startColumnIndex": data_start_col + 1,
                                    "endColumnIndex": data_end_col,
                                }
                            ]
                        }
                    },
                    "targetAxis": "LEFT_AXIS",
                }
            ],
        },
    }
    _safe_gog(
        [
            "sheets",
            "chart",
            "create",
            sid,
            "--spec-json",
            json.dumps(spec),
            "--sheet",
            CHARTS_TAB_NAME,
            "--anchor",
            f"{chr(ord('A') + anchor_col)}{anchor_row + 1}",
            "--width",
            "720",
            "--height",
            "400",
            "-a",
            account,
        ]
    )


def _safe_gog(args: list[str]) -> None:
    """Versión 'best-effort' de :func:`_run_gog`: loguea y sigue de largo si
    falla. Usado solo para los pasos cosméticos del formateo."""
    try:
        _run_gog(args, timeout=30)
    except Exception as e:
        log.debug("formato (paso ignorado): %s ← %s", e, args[:4])


def _gog_append(account: str, sid: str, sheet_name: str, rows: list[list[str]]) -> int:
    """Appendea filas. rows = list[list[str]]. Devuelve cantidad de filas."""
    if not rows:
        return 0
    values_json = json.dumps(rows, ensure_ascii=False)
    # range "Sheet1!A1" → la API de Sheets append busca la primera fila
    # vacía después de ese rango. Usamos solo el nombre de la pestaña.
    range_ = f"{sheet_name}!A1"
    _run_gog(
        [
            "sheets",
            "append",
            sid,
            range_,
            "--values-json",
            values_json,
            "-a",
            account,
            "--input",
            "USER_ENTERED",
        ],
        timeout=60,
    )
    return len(rows)


# ── Lectura del CSV ────────────────────────────────────────────────────
def _read_csv_rows(skip_first_n: int) -> list[list[str]]:
    """Lee el CSV, descarta el header, y devuelve las filas a partir del
    índice ``skip_first_n`` (0-based). Tolera ausencia del archivo."""
    p = _csv_path()
    if not p.exists() or p.stat().st_size == 0:
        return []
    rows: list[list[str]] = []
    with p.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        # Skip header
        try:
            next(reader)
        except StopIteration:
            return []
        for i, r in enumerate(reader):
            if i < skip_first_n:
                continue
            if r:
                rows.append(r)
    return rows


# ── Operaciones públicas ───────────────────────────────────────────────
def connect(account: str, title: str | None = None) -> dict:
    """Crea el Sheet, escribe header, marca enabled=True, arranca el sync.
    Si ya estaba conectado, levanta error — primero hay que disconnect."""
    with _state_lock:
        state = _load_state()
        if state.get("enabled"):
            raise RuntimeError("Ya hay un Sheet conectado. Desconectá primero.")

        title = title or f"Orion IoT — Live ({datetime.now().strftime('%Y-%m-%d')})"
        log.info("creando Sheet '%s' para %s", title, account)
        sid, url = _gog_create_sheet(account, title)

        # El nombre real de la primera pestaña depende de la locale del
        # usuario en Google ("Hoja 1" en español, "Sheet1" en inglés, etc).
        # Hay que pedir la metadata para usar el nombre correcto en el
        # range del append.
        try:
            tab_name = _gog_default_tab(account, sid)
        except Exception as e:
            log.warning("no se pudo leer metadata, uso 'Sheet1': %s", e)
            tab_name = "Sheet1"
        log.info("pestaña real: '%s'", tab_name)

        # Primera escritura: el header
        _gog_append(account, sid, tab_name, [HEADER_ROW])

        # Estilo "bonito" de la hoja. Si algo falla acá no abortamos: el
        # sync de datos es lo crítico, el cosmético se reintenta con
        # /sheets/reformat o en el próximo connect.
        try:
            _gog_format_sheet(account, sid, tab_name)
        except Exception as e:
            log.warning("formato inicial falló: %s", e)

        state.update(
            {
                "enabled": True,
                "account": account,
                "spreadsheet_id": sid,
                "spreadsheet_url": url,
                "sheet_name": tab_name,
                "last_pushed_row": 0,
                "last_error": None,
                "last_sync_at": datetime.now().isoformat(),
            }
        )
        _save_state(state)

    # Disparar un primer sync inmediato (puede haber datos acumulados)
    start()
    request_sync_now()
    return status()


MIN_SYNC_INTERVAL_S = 10
MAX_SYNC_INTERVAL_S = 3600


def update_sync_interval(seconds: int) -> dict:
    """Cambia el periodo de sync. Lo persiste en :file:`iot_sheets.json` y
    despierta el loop para que el cambio tome efecto en el próximo tick
    (no en hasta el viejo intervalo).

    Rechaza valores fuera de [10s, 1h] — abajo de 10s el broker público
    de HiveMQ se queja y arriba de 1h ya no tiene sentido llamarlo
    'live'."""
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "invalid"}
    if s < MIN_SYNC_INTERVAL_S or s > MAX_SYNC_INTERVAL_S:
        return {
            "ok": False,
            "reason": "out_of_range",
            "min": MIN_SYNC_INTERVAL_S,
            "max": MAX_SYNC_INTERVAL_S,
        }
    with _state_lock:
        state = _load_state()
        state["sync_interval_s"] = s
        _save_state(state)
    # Despierta el loop: si estaba durmiendo en wait(interval_viejo)
    # se va a despertar ya y la próxima espera será con el nuevo valor.
    _sync_wake.set()
    return {"ok": True, "sync_interval_s": s}


def reformat() -> dict:
    """Re-aplica el formato 'bonito' al Sheet ya conectado. Útil cuando el
    usuario tocó algo a mano o cuando subió a una versión nueva con
    cambios cosméticos."""
    with _state_lock:
        state = _load_state()
        if not state.get("enabled"):
            return {"ok": False, "reason": "disabled"}
        sid = state.get("spreadsheet_id")
        account = state.get("account")
        sheet = state.get("sheet_name") or DEFAULT_SHEET_NAME

    if not sid or not account:
        return {"ok": False, "reason": "not_configured"}

    try:
        _gog_format_sheet(account, sid, sheet)
    except Exception as e:
        return {"ok": False, "reason": "format_failed", "error": str(e)[:300]}
    return {"ok": True}


def disconnect() -> dict:
    """Desactiva el sync. NO borra el Sheet en Drive — el usuario decide qué
    hacer con él."""
    with _state_lock:
        state = _load_state()
        state.update(
            {
                "enabled": False,
                "last_error": None,
            }
        )
        _save_state(state)
    return status()


def sync_once() -> dict:
    """Lee nuevas filas y las pushea. Devuelve estadísticas."""
    with _state_lock:
        state = _load_state()
        if not state.get("enabled"):
            return {"ok": False, "reason": "disabled"}
        sid = state.get("spreadsheet_id")
        account = state.get("account")
        sheet = state.get("sheet_name") or DEFAULT_SHEET_NAME
        offset = int(state.get("last_pushed_row") or 0)

    if not sid or not account:
        return {"ok": False, "reason": "not_configured"}

    rows = _read_csv_rows(offset)
    if not rows:
        with _state_lock:
            state = _load_state()
            state["last_sync_at"] = datetime.now().isoformat()
            state["last_error"] = None
            _save_state(state)
        return {"ok": True, "pushed": 0, "offset": offset}

    try:
        # Chunkeamos en lotes de 200 filas para no romper línea de comando
        # ni hacer payloads gigantes contra la API de Sheets.
        pushed_total = 0
        for i in range(0, len(rows), 200):
            chunk = rows[i : i + 200]
            _gog_append(account, sid, sheet, chunk)
            pushed_total += len(chunk)

        with _state_lock:
            state = _load_state()
            state["last_pushed_row"] = offset + pushed_total
            state["last_sync_at"] = datetime.now().isoformat()
            state["last_error"] = None
            _save_state(state)
        log.info(
            "sync OK: %d filas pusheadas (offset=%d → %d)",
            pushed_total,
            offset,
            offset + pushed_total,
        )
        return {"ok": True, "pushed": pushed_total, "offset": offset + pushed_total}

    except Exception as e:
        msg = str(e)[:500]
        log.warning("sync falló: %s", msg)
        with _state_lock:
            state = _load_state()
            state["last_error"] = msg
            _save_state(state)
        return {"ok": False, "reason": "push_failed", "error": msg}


# ── Sync loop en background ────────────────────────────────────────────
_sync_thread: threading.Thread | None = None
_sync_stop = threading.Event()
_sync_wake = threading.Event()  # señal para forzar un sync inmediato


def _sync_loop() -> None:
    log.info("sync loop iniciado")
    while not _sync_stop.is_set():
        state = _load_state()
        interval = int(state.get("sync_interval_s") or DEFAULT_SYNC_INTERVAL_S)

        if state.get("enabled"):
            try:
                sync_once()
            except Exception as e:
                log.exception("sync_once crasheó: %s", e)

        # Espera hasta el próximo tick o hasta que alguien llame request_sync_now
        _sync_wake.wait(timeout=interval)
        _sync_wake.clear()
    log.info("sync loop detenido")


def start() -> None:
    """Arranca el thread de sync. Idempotente."""
    global _sync_thread
    if _sync_thread and _sync_thread.is_alive():
        return
    _sync_stop.clear()
    _sync_wake.clear()
    _sync_thread = threading.Thread(
        target=_sync_loop,
        daemon=True,
        name="iot-sheets-sync",
    )
    _sync_thread.start()


def stop() -> None:
    _sync_stop.set()
    _sync_wake.set()


def request_sync_now() -> None:
    """Despierta el loop para que haga un sync ya, sin esperar al próximo
    tick. Usado por el endpoint POST /sheets/sync_now y al conectar."""
    _sync_wake.set()


# ── Auto-arranque ──────────────────────────────────────────────────────
def auto_start() -> None:
    """Llamado desde IoTSystem.__init__. Solo arranca el loop si hay un
    Sheet ya conectado de una sesión anterior."""
    state = _load_state()
    if state.get("enabled"):
        log.info("estado previo encontrado, retomando sync (Sheet %s)", state.get("spreadsheet_id"))
        start()
