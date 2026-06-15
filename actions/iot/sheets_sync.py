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
from typing import Optional

from core.logger import get_logger

log = get_logger("iot.sheets_sync")


# ── Constantes ──────────────────────────────────────────────────────────
DEFAULT_SYNC_INTERVAL_S = 300   # 5 minutos
DEFAULT_SHEET_NAME      = "Sensores"
HEADER_ROW              = ["timestamp", "device", "value", "unit", "samples"]


# ── Paths ──────────────────────────────────────────────────────────────
def _project_root() -> Path:
    from config import IOT_CONFIG_PATH
    return IOT_CONFIG_PATH.parent.parent


def _state_path() -> Path:
    return _project_root() / "config" / "iot_sheets.json"


def _gog_exe() -> Path:
    return _project_root() / "tools" / "gog" / "gog.exe"


def _csv_path() -> Path:
    return _project_root() / "memory" / "iot_sensor_log.csv"


# ── Estado en disco ────────────────────────────────────────────────────
_DEFAULT_STATE = {
    "enabled":          False,
    "account":          None,
    "spreadsheet_id":   None,
    "spreadsheet_url":  None,
    "sheet_name":       DEFAULT_SHEET_NAME,
    "last_pushed_row":  0,
    "last_sync_at":     None,
    "last_error":       None,
    "sync_interval_s":  DEFAULT_SYNC_INTERVAL_S,
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
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
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


def _gog_append(account: str, sid: str, sheet_name: str, rows: list[list[str]]) -> int:
    """Appendea filas. rows = list[list[str]]. Devuelve cantidad de filas."""
    if not rows:
        return 0
    values_json = json.dumps(rows, ensure_ascii=False)
    # range "Sheet1!A1" → la API de Sheets append busca la primera fila
    # vacía después de ese rango. Usamos solo el nombre de la pestaña.
    range_ = f"{sheet_name}!A1"
    _run_gog([
        "sheets", "append", sid, range_,
        "--values-json", values_json,
        "-a", account,
        "--input", "USER_ENTERED",
    ], timeout=60)
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
def connect(account: str, title: Optional[str] = None) -> dict:
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

        state.update({
            "enabled":         True,
            "account":         account,
            "spreadsheet_id":  sid,
            "spreadsheet_url": url,
            "sheet_name":      tab_name,
            "last_pushed_row": 0,
            "last_error":      None,
            "last_sync_at":    datetime.now().isoformat(),
        })
        _save_state(state)

    # Disparar un primer sync inmediato (puede haber datos acumulados)
    start()
    request_sync_now()
    return status()


def disconnect() -> dict:
    """Desactiva el sync. NO borra el Sheet en Drive — el usuario decide qué
    hacer con él."""
    with _state_lock:
        state = _load_state()
        state.update({
            "enabled":      False,
            "last_error":   None,
        })
        _save_state(state)
    return status()


def sync_once() -> dict:
    """Lee nuevas filas y las pushea. Devuelve estadísticas."""
    with _state_lock:
        state = _load_state()
        if not state.get("enabled"):
            return {"ok": False, "reason": "disabled"}
        sid     = state.get("spreadsheet_id")
        account = state.get("account")
        sheet   = state.get("sheet_name") or DEFAULT_SHEET_NAME
        offset  = int(state.get("last_pushed_row") or 0)

    if not sid or not account:
        return {"ok": False, "reason": "not_configured"}

    rows = _read_csv_rows(offset)
    if not rows:
        with _state_lock:
            state = _load_state()
            state["last_sync_at"] = datetime.now().isoformat()
            state["last_error"]   = None
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
            state["last_sync_at"]    = datetime.now().isoformat()
            state["last_error"]      = None
            _save_state(state)
        log.info("sync OK: %d filas pusheadas (offset=%d → %d)",
                 pushed_total, offset, offset + pushed_total)
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
_sync_thread: Optional[threading.Thread] = None
_sync_stop = threading.Event()
_sync_wake = threading.Event()   # señal para forzar un sync inmediato


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
        target=_sync_loop, daemon=True, name="iot-sheets-sync",
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
        log.info("estado previo encontrado, retomando sync (Sheet %s)",
                 state.get("spreadsheet_id"))
        start()
