"""
Classroom — Action module for O.R.I.O.N
========================================
Opens Google Classroom directly using the user's Chrome browser.

Uses subprocess to launch Chrome — no Playwright dependency.
Reads Chrome path from config/browser.json.
"""

import json
import platform
import subprocess
from pathlib import Path

_OS = platform.system()
from orion.config import BROWSER_CONFIG_PATH as _BROWSER_CONFIG_PATH

_CLASSROOM_URLS = {
    "personal": "https://classroom.google.com/u/0/",
    "normal": "https://classroom.google.com/u/0/",
    "principal": "https://classroom.google.com/u/0/",
    "institucional": "https://classroom.google.com/u/1/h",
    "universidad": "https://classroom.google.com/u/1/h",
    "uni": "https://classroom.google.com/u/1/h",
    "unmsm": "https://classroom.google.com/u/1/h",
    "secundaria": "https://classroom.google.com/u/1/h",
}


def _get_chrome_path() -> str | None:
    """Obtiene la ruta de Chrome desde browser.json o busca en el sistema."""
    import shutil

    try:
        with open(_BROWSER_CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        chrome = cfg.get("chrome_path", "")
        if chrome and Path(chrome).exists():
            return chrome
    except Exception:
        pass

    # Fallback: buscar en rutas comunes
    fallbacks = {
        "Windows": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
        "Darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
        "Linux": [],
    }
    for p in fallbacks.get(_OS, []):
        if Path(p).exists():
            return p
    return shutil.which("chrome") or shutil.which("google-chrome")


from orion.core.tool_registry import tool


@tool(
    name="classroom",
    description=(
        "Opens Google Classroom in Chrome with the correct account. "
        "Use this ALWAYS when the user mentions 'classroom', 'Google Classroom', or 'clase'. "
        "NEVER use browser_control or open_app for Classroom. "
        "Two accounts available: "
        "'personal' (default, /u/0/) for the user's main Google account, "
        "'institucional' (/u/1/) for the university/UNMSM account. "
        "If the user says 'classroom institucional', 'classroom de la uni', or 'classroom unmsm', "
        "set account to 'institucional'. Otherwise use 'personal'."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "account": {
                "type": "STRING",
                "description": "Which account: personal (default, main account /u/0/) | institucional (university account /u/1/)",
            },
            "url": {
                "type": "STRING",
                "description": "Custom Classroom URL. Leave empty to auto-resolve from account type.",
            },
        },
        "required": [],
    },
)
def classroom(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    account = params.get("account", "personal").lower().strip()
    url = params.get("url", "")

    if player:
        player.write_log(f"[classroom] {account}")

    if not url:
        url = _CLASSROOM_URLS.get(account, "https://classroom.google.com/u/0/")

    chrome = _get_chrome_path()
    if not chrome:
        return "No se encontró Google Chrome instalado."

    try:
        cmd = [chrome, url]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        label = "institucional" if "/u/1/" in url else "personal"
        return f"Google Classroom ({label}) abierto."
    except Exception as e:
        return f"Error al abrir Classroom: {e}"
