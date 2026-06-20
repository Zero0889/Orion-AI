import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from config import is_linux, is_mac, is_windows

_KNOWN_APPIDS: dict[str, tuple[str, str]] = {
    "pubg": ("578080", "PUBG: Battlegrounds"),
    "pubg battlegrounds": ("578080", "PUBG: Battlegrounds"),
    "pubg: battlegrounds": ("578080", "PUBG: Battlegrounds"),
    "battlegrounds": ("578080", "PUBG: Battlegrounds"),
    "gta5": ("271590", "Grand Theft Auto V"),
    "gta v": ("271590", "Grand Theft Auto V"),
    "grand theft auto v": ("271590", "Grand Theft Auto V"),
    "cs2": ("730", "Counter-Strike 2"),
    "csgo": ("730", "Counter-Strike 2"),
    "counter-strike 2": ("730", "Counter-Strike 2"),
    "counter strike 2": ("730", "Counter-Strike 2"),
    "dota2": ("570", "Dota 2"),
    "dota 2": ("570", "Dota 2"),
    "rust": ("252490", "Rust"),
    "valheim": ("892970", "Valheim"),
    "cyberpunk": ("1091500", "Cyberpunk 2077"),
    "cyberpunk 2077": ("1091500", "Cyberpunk 2077"),
    "elden ring": ("1245620", "ELDEN RING"),
    "minecraft": ("1672970", "Minecraft Launcher"),
    "apex legends": ("1172470", "Apex Legends"),
    "apex": ("1172470", "Apex Legends"),
    "fortnite": ("1517990", "Fortnite"),
    "goose goose duck": ("1568590", "Goose Goose Duck"),
    "among us": ("945360", "Among Us"),
    "fall guys": ("1097150", "Fall Guys"),
    "rocket league": ("252950", "Rocket League"),
    "warframe": ("230410", "Warframe"),
    "destiny 2": ("1085660", "Destiny 2"),
    "team fortress 2": ("440", "Team Fortress 2"),
    "tf2": ("440", "Team Fortress 2"),
    "left 4 dead 2": ("550", "Left 4 Dead 2"),
    "l4d2": ("550", "Left 4 Dead 2"),
    "paladins": ("444090", "Paladins"),
    "smite": ("386360", "SMITE"),
    "war thunder": ("236390", "War Thunder"),
    "world of warships": ("552990", "World of Warships"),
    "path of exile": ("238960", "Path of Exile"),
    "poe": ("238960", "Path of Exile"),
    "lost ark": ("1599340", "Lost Ark"),
    "new world": ("1063730", "New World: Aeternum"),
}


def _find_steam_path() -> Path | None:
    if is_windows():
        return _find_steam_windows()
    if is_mac():
        return _find_steam_mac()
    return _find_steam_linux()


def _find_steam_windows() -> Path | None:
    try:
        import winreg

        for hive, key_path in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam"),
        ]:
            try:
                key = winreg.OpenKey(hive, key_path)
                val, _ = winreg.QueryValueEx(key, "InstallPath")
                winreg.CloseKey(key)
                p = Path(val)
                if p.exists() and (p / "steam.exe").exists():
                    return p
            except Exception:
                continue
    except ImportError:
        pass
    for p in [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Steam",
        Path(os.environ.get("ProgramFiles", "")) / "Steam",
        Path("C:/Steam"),
        Path("D:/Steam"),
        Path("E:/Steam"),
        Path("F:/Steam"),
    ]:
        if p.exists() and (p / "steam.exe").exists():
            return p
    return None


def _find_steam_mac() -> Path | None:
    for p in [
        Path.home() / "Library" / "Application Support" / "Steam",
        Path("/Applications/Steam.app/Contents/MacOS"),
    ]:
        if p.exists():
            return p
    return None


def _find_steam_linux() -> Path | None:
    for p in [
        Path.home() / ".steam" / "steam",
        Path.home() / ".steam" / "root",
        Path.home() / ".local" / "share" / "Steam",
        Path("/usr/share/steam"),
        Path("/opt/steam"),
    ]:
        if p.exists():
            return p
    return None


def _steam_exe(steam_path: Path) -> Path:
    if is_windows():
        return steam_path / "steam.exe"
    if is_mac():
        return Path("/Applications/Steam.app/Contents/MacOS/steam_osx")
    return steam_path / "steam.sh"


def _launch_steam_url(exe: Path, url: str) -> None:
    if is_mac():
        subprocess.Popen(["open", url])
    elif is_linux():
        subprocess.Popen(["xdg-open", url])
    else:
        subprocess.Popen([str(exe), url])


def _get_steam_libraries(steam_path: Path) -> list[Path]:
    libraries = [steam_path / "steamapps"]
    vdf_path = steam_path / "steamapps" / "libraryfolders.vdf"
    if not vdf_path.exists():
        return libraries
    try:
        content = vdf_path.read_text(encoding="utf-8", errors="ignore")
        for raw_path in re.findall(r'"path"\s+"([^"]+)"', content):
            lib = Path(raw_path.replace("\\\\", "/")) / "steamapps"
            if lib.exists() and lib not in libraries:
                libraries.append(lib)
    except Exception:
        pass
    return libraries


def _get_steam_games(steam_path: Path) -> list[dict]:
    games = []
    for lib in _get_steam_libraries(steam_path):
        for acf in lib.glob("appmanifest_*.acf"):
            try:
                content = acf.read_text(encoding="utf-8", errors="ignore")
                app_id = re.search(r'"appid"\s+"(\d+)"', content)
                name = re.search(r'"name"\s+"([^"]+)"', content)
                state = re.search(r'"StateFlags"\s+"(\d+)"', content)
                size = re.search(r'"SizeOnDisk"\s+"(\d+)"', content)
                if app_id and name:
                    games.append(
                        {
                            "id": app_id.group(1),
                            "name": name.group(1),
                            "state": int(state.group(1)) if state else 0,
                            "size": int(size.group(1)) if size else 0,
                            "lib": str(lib),
                            "acf": str(acf),
                        }
                    )
            except Exception:
                continue
    return games


def _is_steam_running() -> bool:
    try:
        if is_windows():
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq steam.exe"], capture_output=True, text=True
            ).stdout
            return "steam.exe" in out.lower()
        proc = "steam_osx" if is_mac() else "steam"
        return bool(
            subprocess.run(["pgrep", "-x", proc], capture_output=True, text=True).stdout.strip()
        )
    except Exception:
        return False


def _get_steam_window_rect() -> tuple[int, int, int, int] | None:
    try:
        import pygetwindow as gw

        for w in gw.getAllWindows():
            if "steam" in w.title.lower() and w.width > 200 and w.visible:
                return w.left, w.top, w.width, w.height
    except Exception:
        pass
    return None


def _click_first_profile_by_screenshot() -> bool:

    try:
        import numpy as np
        import pyautogui

        time.sleep(1.5)
        win = _get_steam_window_rect()
        if not win:
            print("[GameUpdater] ⚠️ No se encontró la ventana de Steam")
            return False

        wx, wy, ww, wh = win
        screenshot = pyautogui.screenshot(region=(wx, wy, ww, wh))
        img = np.array(screenshot)
        h, w = img.shape[:2]

        search_y1, search_y2 = h // 3, h * 3 // 4
        search_x1, search_x2 = w // 5, w * 4 // 5
        region = img[search_y1:search_y2, search_x1:search_x2]

        r, g, b = (
            region[:, :, 0].astype(int),
            region[:, :, 1].astype(int),
            region[:, :, 2].astype(int),
        )
        max_c = np.maximum(np.maximum(r, g), b)
        min_c = np.minimum(np.minimum(r, g), b)
        colorful = (max_c > 60) & ((max_c - min_c) > 40)

        if not colorful.any():
            print("[GameUpdater] ⚠️ No se encontró color de avatar — haciendo clic estimado")
            pyautogui.click(wx + ww // 2 - ww // 6, wy + wh // 2)
            return True

        cols = np.where(colorful.any(axis=0))[0]
        rows = np.where(colorful.any(axis=1))[0]
        if not len(cols) or not len(rows):
            return False

        avatar_w = min(90, region.shape[1] // 4)
        first_col = int(cols[0])
        block_cols = cols[cols < first_col + avatar_w]

        abs_x = wx + search_x1 + int(block_cols.mean())
        abs_y = wy + search_y1 + int(rows.mean())
        print(f"[GameUpdater] 🎯 Avatar de perfil ({abs_x}, {abs_y}) — haciendo clic")
        pyautogui.click(abs_x, abs_y)
        return True

    except ImportError as e:
        print(f"[GameUpdater] ⚠️ Biblioteca faltante: {e}")
        return False
    except Exception as e:
        print(f"[GameUpdater] ⚠️ La detección de perfil falló: {e}")
        return False


def _handle_steam_profile_selection() -> bool:
    print("[GameUpdater] 🔍 Verificando diálogo de selección de perfil...")
    win = _get_steam_window_rect()
    if not win:
        return False

    wx, wy, ww, wh = win
    try:
        import numpy as np
        import pyautogui

        screenshot = pyautogui.screenshot(region=(wx, wy, ww, wh))
        img = np.array(screenshot)
        is_small = ww < 900 and wh < 700
        top_region = img[: wh // 3, :, :]
        white_pixels = int(
            np.sum(
                (top_region[:, :, 0] > 200)
                & (top_region[:, :, 1] > 200)
                & (top_region[:, :, 2] > 200)
            )
        )
        if not is_small and white_pixels <= 100:
            print("[GameUpdater] ℹ️ No hay diálogo de perfil — Steam ya ha iniciado sesión")
            return False
    except ImportError:
        pass
    except Exception:
        pass

    print("[GameUpdater] 👤 Selección de perfil detectada — haciendo clic en el primer perfil")
    return _click_first_profile_by_screenshot()


def _find_best_drive() -> dict | None:
    import shutil
    import string

    drives = []
    for letter in string.ascii_uppercase:
        drive_path = f"{letter}:\\"
        if os.path.exists(drive_path):
            try:
                free_gb = shutil.disk_usage(drive_path).free / (1024**3)
                if free_gb > 0:
                    drives.append({"letter": letter, "path": drive_path, "free_gb": free_gb})
            except Exception:
                continue
    return max(drives, key=lambda d: d["free_gb"]) if drives else None


def _select_drive_in_dialog(dialog, drive_letter: str) -> bool:
    target = drive_letter.upper()
    for control_type in ("ListItem", "RadioButton"):
        try:
            for ctrl in dialog.descendants(control_type=control_type):
                if target in ctrl.window_text().upper():
                    ctrl.click_input()
                    print(
                        f"[GameUpdater] ✅ Unidad seleccionada ({control_type}): {ctrl.window_text()}"
                    )
                    return True
        except Exception:
            continue
    try:
        for combo in dialog.descendants(control_type="ComboBox"):
            try:
                combo.expand()
                time.sleep(0.15)
                for idx, txt in enumerate(combo.texts()):
                    if target in txt.upper():
                        combo.select(idx)
                        return True
                combo.collapse()
            except Exception:
                continue
    except Exception:
        pass
    try:
        for ctrl in dialog.descendants():
            txt = ctrl.window_text().upper()
            if f"{target}:" in txt and len(txt) < 80:
                ctrl.click_input()
                return True
    except Exception:
        pass
    return False


def _click_button(window, keywords: list[str]) -> bool:
    try:
        for btn in window.descendants(control_type="Button"):
            try:
                txt = btn.window_text().lower().strip()
                if txt in keywords or any(kw in txt for kw in keywords):
                    btn.click_input()
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _handle_install_dialog_pyautogui(game_name: str, best_drive: dict) -> str:
    try:
        import pyautogui
        import pygetwindow as gw
    except ImportError:
        return (
            f"Se abrió el diálogo de instalación para '{game_name}'. "
            f"Por favor, seleccione '{best_drive['letter']}:' y haga clic en Instalar manualmente."
        )

    pyautogui.FAILSAFE = False
    drive_label = f"{best_drive['letter']}:"
    install_win = None

    for _ in range(30):
        time.sleep(0.5)
        for w in gw.getAllWindows():
            if (
                ("install" in w.title.lower() or "steam" in w.title.lower())
                and w.width > 300
                and w.visible
            ):
                install_win = w
                break
        if install_win:
            break

    if not install_win:
        return f"Por favor, seleccione '{drive_label}' y haga clic en Instalar en Steam para '{game_name}'."

    try:
        install_win.activate()
        time.sleep(0.4)
    except Exception:
        pass

    wx, wy = install_win.left, install_win.top
    ww, wh = install_win.width, install_win.height
    pyautogui.click(wx + int(ww * 0.35), wy + int(wh * 0.45))
    time.sleep(0.2)
    pyautogui.typewrite(best_drive["letter"], interval=0.05)
    time.sleep(0.2)
    pyautogui.click(wx + int(ww * 0.72), wy + int(wh * 0.88))
    return f"Se intentó la selección de unidad {drive_label} y clic en Instalar para '{game_name}'."


def _handle_install_dialog(game_name: str) -> str:
    best_drive = _find_best_drive()
    if not best_drive:
        return f"Se abrió el diálogo de instalación para '{game_name}'. No se pudieron detectar las unidades."

    drive_letter = best_drive["letter"]
    drive_label = f"{drive_letter}:"
    print(
        f"[GameUpdater] 🏆 Unidad objetivo: {drive_label} ({best_drive['free_gb']:.1f} GB libres)"
    )

    try:
        from pywinauto import Application, findwindows

        dialog = None

        for _ in range(40):
            time.sleep(0.5)
            try:
                for hwnd in findwindows.find_windows(
                    title_re=r"(?i)(install|yükle|steam)", visible_only=True
                ):
                    try:
                        app = Application(backend="uia").connect(handle=hwnd)
                        win = app.window(handle=hwnd)
                        rect = win.rectangle()
                        if win.is_visible() and rect.width() > 300 and rect.height() > 200:
                            all_text = " ".join(
                                c.window_text() for c in win.descendants() if c.window_text()
                            ).upper()
                            if any(
                                x in all_text for x in ("C:", "D:", "E:", "F:", "INSTALL", "YÜKLE")
                            ):
                                dialog = win
                                break
                    except Exception:
                        continue
            except Exception:
                pass
            if dialog:
                break

        if not dialog:
            raise RuntimeError("No se encontró el diálogo")

        dialog.set_focus()
        time.sleep(0.4)
        drive_selected = _select_drive_in_dialog(dialog, drive_letter)
        install_clicked = _click_button(
            dialog, ["install", "yükle", "next", "ileri", "ok", "tamam"]
        )

        if install_clicked:
            suffix = (
                f"Se seleccionó {drive_label} y"
                if drive_selected
                else "Se usó la unidad predeterminada, pero"
            )
            return f"{suffix} se hizo clic en Instalar para '{game_name}'."
        return f"Por favor, haga clic en Instalar manualmente en Steam para '{game_name}'."

    except ImportError:
        return _handle_install_dialog_pyautogui(game_name, best_drive)
    except Exception as e:
        print(f"[GameUpdater] ⚠️ pywinauto falló: {e}")
        return _handle_install_dialog_pyautogui(game_name, best_drive)


def _ensure_steam_running(steam_path: Path) -> bool:
    if _is_steam_running():
        return True

    exe = _steam_exe(steam_path)
    if not exe.exists():
        print(f"[GameUpdater] ❌ Steam no encontrado: {exe}")
        return False

    print("[GameUpdater] 🚀 Iniciando Steam...")
    if is_mac():
        subprocess.Popen(["open", "-a", "Steam"])
    else:
        subprocess.Popen([str(exe)])

    for _ in range(20):
        time.sleep(1)
        if _is_steam_running():
            print("[GameUpdater] ✅ Steam en ejecución")
            time.sleep(4)
            if is_windows():
                _handle_steam_profile_selection()
                time.sleep(2)
            return True

    print("[GameUpdater] ⚠️ No se pudo iniciar Steam")
    return False


def _search_steam_appid(game_name: str) -> tuple[str | None, str | None]:
    name_lower = game_name.lower().strip()

    steam_path = _find_steam_path()
    if steam_path:
        for g in _get_steam_games(steam_path):
            if name_lower in g["name"].lower():
                return g["id"], g["name"]

    if name_lower in _KNOWN_APPIDS:
        app_id, canonical = _KNOWN_APPIDS[name_lower]
        print(f"[GameUpdater] 📖 Conocido: {canonical} ({app_id})")
        return app_id, canonical

    for key, (app_id, canonical) in _KNOWN_APPIDS.items():
        if name_lower in key or key in name_lower:
            print(f"[GameUpdater] 📖 Coincidencia parcial: {canonical} ({app_id})")
            return app_id, canonical

    try:
        import urllib.parse
        import urllib.request

        query = urllib.parse.quote(game_name)
        url = f"https://store.steampowered.com/api/storesearch/?term={query}&l=english&cc=US"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            items = json.loads(resp.read().decode()).get("items", [])
        if items:
            best = items[0]
            print(f"[GameUpdater] 🌐 Store API: {best['name']} ({best['id']})")
            return str(best["id"]), best["name"]
    except Exception as e:
        print(f"[GameUpdater] ⚠️ La búsqueda de AppID falló: {e}")

    return None, None


def _update_steam_games(steam_path: Path, game_name: str = None) -> str:
    if not _ensure_steam_running(steam_path):
        return "No se pudo iniciar Steam."

    exe = _steam_exe(steam_path)
    games = _get_steam_games(steam_path)
    if not games:
        return "No se encontraron juegos de Steam."

    if game_name:
        name_lower = game_name.lower()
        targets = [g for g in games if name_lower in g["name"].lower()]
        if not targets:
            available = ", ".join(g["name"] for g in games[:5])
            return f"El juego '{game_name}' no se encontró. Instalados: {available}..."
    else:
        targets = games

    already_updated, already_running, update_started, errors = [], [], [], []

    for game in targets:
        state = game["state"]
        name = game["name"]
        if state == 4:
            already_updated.append(name)
        elif state == 1026:
            already_running.append(name)
        else:
            try:
                _launch_steam_url(exe, f"steam://update/{game['id']}")
                update_started.append(name)
                time.sleep(0.3)
            except Exception as e:
                errors.append(f"{name}: {e}")

    parts = []
    if update_started:
        names = ", ".join(update_started[:3])
        suffix = f" y {len(update_started) - 3} más" if len(update_started) > 3 else ""
        parts.append(f"Actualización iniciada para: {names}{suffix}.")
    if already_running:
        parts.append(f"Ya actualizándose: {', '.join(already_running)}.")
    if already_updated:
        parts.append(
            f"{already_updated[0]} ya está actualizado."
            if game_name
            else f"{len(already_updated)} juego(s) ya actualizado(s)."
        )
    if errors:
        parts.append(f"Errores: {'; '.join(errors)}.")
    return " ".join(parts) if parts else "No hay juegos para actualizar."


def _install_steam_game(steam_path: Path, game_name: str = None, app_id: str = None) -> str:
    if not _ensure_steam_running(steam_path):
        return "No se pudo iniciar Steam."

    exe = _steam_exe(steam_path)
    installed_games = _get_steam_games(steam_path)

    already = None
    if app_id:
        already = next((g for g in installed_games if g["id"] == str(app_id)), None)
    elif game_name:
        name_lower = game_name.lower()
        already = next((g for g in installed_games if name_lower in g["name"].lower()), None)
    else:
        return "Por favor, especifique un nombre de juego o AppID."

    if already:
        state = already["state"]
        name = already["name"]
        if state == 4:
            return f"'{name}' ya está instalado y actualizado."
        if state == 1026:
            return f"'{name}' se está descargando o actualizando actualmente."
        if state in (6, 516):
            _launch_steam_url(exe, f"steam://update/{already['id']}")
            return f"'{name}' tiene una actualización pendiente. Actualización iniciada."
        return f"'{name}' ya está instalado."

    if not app_id and game_name:
        found_id, found_name = _search_steam_appid(game_name)
        if not found_id:
            return (
                f"No se encontró '{game_name}' en Steam. "
                f"Intente proporcionando el AppID directamente."
            )
        app_id = found_id
        game_name = found_name or game_name
        print(f"[GameUpdater] 🔍 Instalando: {game_name} (AppID: {app_id})")

    try:
        _launch_steam_url(exe, f"steam://install/{app_id}")

        if is_windows():
            threading.Thread(
                target=_handle_install_dialog, args=(game_name or str(app_id),), daemon=True
            ).start()
        return f"Instalación iniciada para '{game_name}'. Steam abrirá el diálogo de descarga."
    except Exception as e:
        return f"La instalación falló: {e}"


def _get_download_status(steam_path: Path) -> str:
    games = _get_steam_games(steam_path)
    active = [g for g in games if g["state"] == 1026]
    pending = [g for g in games if g["state"] in (6, 516)]
    lines = []
    if active:
        lines.append(f"Descargando: {', '.join(g['name'] for g in active)}.")
    if pending:
        names = ", ".join(g["name"] for g in pending[:5])
        suffix = f" y {len(pending) - 5} más" if len(pending) > 5 else ""
        lines.append(f"Actualizaciones pendientes: {names}{suffix}.")
    return " ".join(lines) if lines else "No hay descargas activas ni actualizaciones pendientes."


def _system_shutdown() -> None:
    if is_windows():
        subprocess.run(["shutdown", "/s", "/t", "10"])
    elif is_mac():
        subprocess.run(["osascript", "-e", 'tell app "System Events" to shut down'])
    else:
        subprocess.run(["systemctl", "poweroff"])


def _watch_and_shutdown(
    steam_path: Path, speak=None, check_interval: int = 30, timeout_hours: int = 12
):
    print("[GameUpdater]...")
    deadline = time.time() + timeout_hours * 3600

    for _ in range(24):
        time.sleep(5)
        active = [g for g in _get_steam_games(steam_path) if g["state"] == 1026]
        if active:
            names = ", ".join(g["name"] for g in active)
            if speak:
                speak(f"Descarga iniciada para {names}. Apagaré el equipo cuando termine.")
            break
    else:
        return

    while time.time() < deadline:
        time.sleep(check_interval)
        if not any(g["state"] == 1026 for g in _get_steam_games(steam_path)):
            if speak:
                speak("Descarga completada. Apagando ahora.")
            time.sleep(5)
            _system_shutdown()
            return

    if speak:
        speak("La descarga está tardando demasiado. Cancelando el apagado automático.")


def _find_epic_exe() -> Path | None:
    if is_windows():
        return _find_epic_exe_windows()
    if is_mac():
        return _find_epic_exe_mac()
    return _find_epic_exe_linux()


def _find_epic_exe_windows() -> Path | None:
    try:
        import winreg

        for hive, key_path in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\EpicGames\EpicGamesLauncher"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EpicGames\EpicGamesLauncher"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\EpicGames\EpicGamesLauncher"),
        ]:
            try:
                key = winreg.OpenKey(hive, key_path)
                val, _ = winreg.QueryValueEx(key, "AppDataPath")
                winreg.CloseKey(key)
                exe = Path(val) / "Binaries" / "Win64" / "EpicGamesLauncher.exe"
                if exe.exists():
                    return exe
            except Exception:
                continue
    except ImportError:
        pass
    for candidate in [
        Path(os.environ.get("ProgramFiles(x86)", ""))
        / "Epic Games"
        / "Launcher"
        / "Portal"
        / "Binaries"
        / "Win64"
        / "EpicGamesLauncher.exe",
        Path(os.environ.get("ProgramFiles", ""))
        / "Epic Games"
        / "Launcher"
        / "Portal"
        / "Binaries"
        / "Win64"
        / "EpicGamesLauncher.exe",
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "EpicGamesLauncher"
        / "Portal"
        / "Binaries"
        / "Win64"
        / "EpicGamesLauncher.exe",
    ]:
        if candidate.exists():
            return candidate
    return None


def _find_epic_exe_mac() -> Path | None:
    p = Path("/Applications/Epic Games Launcher.app/Contents/MacOS/EpicGamesLauncher")
    return p if p.exists() else None


def _find_epic_exe_linux() -> Path | None:
    for c in [Path.home() / ".local" / "bin" / "heroic", Path("/usr/bin/heroic")]:
        if c.exists():
            return c
    return None


def _epic_manifests_path() -> Path | None:
    if is_windows():
        p = (
            Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
            / "Epic"
            / "EpicGamesLauncher"
            / "Data"
            / "Manifests"
        )
        return p if p.exists() else None
    if is_mac():
        p = (
            Path.home()
            / "Library"
            / "Application Support"
            / "Epic"
            / "EpicGamesLauncher"
            / "Data"
            / "Manifests"
        )
        return p if p.exists() else None
    return None


def _get_epic_games() -> list[dict]:
    manifests = _epic_manifests_path()
    if not manifests:
        return []
    games = []
    for item_file in manifests.glob("*.item"):
        try:
            data = json.loads(item_file.read_text(encoding="utf-8"))
            name = data.get("DisplayName") or data.get("AppName", "")
            if name:
                games.append({"id": data.get("AppName", ""), "name": name})
        except Exception:
            continue
    return games


def _is_epic_running() -> bool:
    try:
        if is_windows():
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq EpicGamesLauncher.exe"],
                capture_output=True,
                text=True,
            ).stdout
            return "epicgameslauncher.exe" in out.lower()
        proc = "EpicGamesLauncher" if is_mac() else "heroic"
        return bool(
            subprocess.run(["pgrep", "-x", proc], capture_output=True, text=True).stdout.strip()
        )
    except Exception:
        return False


def _update_epic_games(epic_exe: Path, game_name: str = None) -> str:
    games = _get_epic_games()

    if game_name:
        name_lower = game_name.lower()
        matched = [g for g in games if name_lower in g["name"].lower()]
        if not matched:
            return f"'{game_name}' no se encontró en Epic."
        try:
            url = f"com.epicgames.launcher://apps/{matched[0]['id']}?action=launch&silent=true"
            if is_mac():
                subprocess.Popen(["open", url])
            elif is_linux():
                subprocess.Popen([str(epic_exe), url] if epic_exe else ["xdg-open", url])
            else:
                subprocess.Popen([str(epic_exe), url])
            return f"Epic abierto para '{matched[0]['name']}'."
        except Exception as e:
            return f"La actualización de Epic falló: {e}"
    else:
        try:
            if is_mac():
                subprocess.Popen(["open", "-a", "Epic Games Launcher"])
            elif is_linux():
                if epic_exe:
                    subprocess.Popen([str(epic_exe)])
                else:
                    return (
                        "Epic Games no tiene soporte nativo en Linux. "
                        "Considere usar Heroic Launcher."
                    )
            else:
                if _is_epic_running():
                    for g in games[:10]:
                        subprocess.Popen(
                            [
                                str(epic_exe),
                                f"com.epicgames.launcher://apps/{g['id']}?action=launch&silent=true",
                            ]
                        )
                        time.sleep(0.5)
                    return f"Se verificó la actualización de {len(games)} juego(s) de Epic."
                else:
                    subprocess.Popen([str(epic_exe)])
            count = len(games)
            return (
                f"Epic Games Launcher abierto. Se verificarán {count} juego(s)."
                if count
                else "Epic Games Launcher abierto."
            )
        except Exception as e:
            return f"No se pudo iniciar Epic: {e}"


def _schedule_daily_update(hour: int = 3, minute: int = 0) -> str:
    if is_windows():
        return _schedule_windows(hour, minute)
    if is_mac():
        return _schedule_mac(hour, minute)
    return _schedule_linux(hour, minute)


def _schedule_windows(hour: int, minute: int) -> str:
    task_name = "ORION_GameUpdater"
    script_path = Path(__file__).resolve()
    subprocess.run(["schtasks", "/Delete", "/TN", task_name, "/F"], capture_output=True)
    for extra in (["/RL", "HIGHEST", "/RU", "SYSTEM"], []):
        cmd = [
            "schtasks",
            "/Create",
            "/TN",
            task_name,
            "/TR",
            f'"{sys.executable}" "{script_path}" --scheduled',
            "/SC",
            "DAILY",
            "/ST",
            f"{hour:02d}:{minute:02d}",
            "/F",
            *extra,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return f"Actualización diaria de juegos programada a las {hour:02d}:{minute:02d}."
    return f"La programación falló: {result.stderr.strip()}"


def _schedule_mac(hour: int, minute: int) -> str:
    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / "com.orion.gameupdater.plist"
    script_path = Path(__file__).resolve()
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>Label</key><string>com.orion.gameupdater</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{script_path}</string>
        <string>--scheduled</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>{hour}</integer>
        <key>Minute</key><integer>{minute}</integer>
    </dict>
    <key>RunAtLoad</key><false/>
</dict></plist>"""
    try:
        plist_path.write_text(plist_content, encoding="utf-8")
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
        result = subprocess.run(
            ["launchctl", "load", str(plist_path)], capture_output=True, text=True
        )
        if result.returncode == 0:
            return f"Actualización diaria de juegos programada a las {hour:02d}:{minute:02d} vía launchd."
        return f"La programación falló: {result.stderr.strip()}"
    except Exception as e:
        return f"La programación falló: {e}"


def _schedule_linux(hour: int, minute: int) -> str:
    script_path = Path(__file__).resolve()
    marker = "# ORION_GameUpdater"
    cron_entry = f"{minute} {hour} * * * {sys.executable} {script_path} --scheduled  {marker}"
    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        lines = [
            l for l in existing.stdout.splitlines() if marker not in l and str(script_path) not in l
        ]
        lines.append(cron_entry)
        proc = subprocess.run(
            ["crontab", "-"], input="\n".join(lines) + "\n", text=True, capture_output=True
        )
        if proc.returncode == 0:
            return (
                f"Actualización diaria de juegos programada a las {hour:02d}:{minute:02d} vía cron."
            )
        return f"La programación falló: {proc.stderr.strip()}"
    except Exception as e:
        return f"La programación falló: {e}"


def _cancel_scheduled_update() -> str:
    if is_windows():
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", "ORION_GameUpdater", "/F"],
            capture_output=True,
            text=True,
        )
        return (
            "Actualización programada cancelada."
            if result.returncode == 0
            else "No se encontró ninguna actualización programada."
        )
    if is_mac():
        plist_path = Path.home() / "Library" / "LaunchAgents" / "com.orion.gameupdater.plist"
        if plist_path.exists():
            subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
            plist_path.unlink()
            return "Actualización programada cancelada."
        return "No se encontró ninguna actualización programada."

    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        lines = [l for l in existing.stdout.splitlines() if "ORION_GameUpdater" not in l]
        subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True)
        return "Actualización programada cancelada."
    except Exception as e:
        return f"La cancelación falló: {e}"


def _get_schedule_status() -> str:
    if is_windows():
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", "ORION_GameUpdater", "/FO", "LIST"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return "No se encontró ninguna actualización de juegos programada."
        for line in result.stdout.strip().splitlines():
            if any(k in line for k in ("Next Run", "Sonraki", "Prochaine", "Próxima", "Nächste")):
                return f"Actualización de juegos programada. {line.strip()}"
        return "La actualización de juegos está programada."
    if is_mac():
        plist_path = Path.home() / "Library" / "LaunchAgents" / "com.orion.gameupdater.plist"
        return (
            "La actualización de juegos está programada vía launchd."
            if plist_path.exists()
            else "No se encontró ninguna actualización de juegos programada."
        )

    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if "ORION_GameUpdater" in result.stdout:
            for line in result.stdout.splitlines():
                if "ORION_GameUpdater" in line:
                    return (
                        f"La actualización de juegos está programada: {line.split('#')[0].strip()}"
                    )
        return "No se encontró ninguna actualización de juegos programada."
    except Exception:
        return "No se encontró ninguna actualización de juegos programada."


from core.tool_registry import tool


@tool(
    name="game_updater",
    description=(
        "THE ONLY tool for ANY Steam or Epic Games request. "
        "Use for: installing, downloading, updating games, listing installed games, "
        "checking download status, scheduling updates. "
        "ALWAYS call directly for any Steam/Epic/game request. "
        "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)",
            },
            "platform": {
                "type": "STRING",
                "description": "steam | epic | both (default: both)",
            },
            "game_name": {
                "type": "STRING",
                "description": "Game name (partial match supported)",
            },
            "app_id": {
                "type": "STRING",
                "description": "Steam AppID for install (optional)",
            },
            "hour": {
                "type": "INTEGER",
                "description": "Hour for scheduled update 0-23 (default: 3)",
            },
            "minute": {
                "type": "INTEGER",
                "description": "Minute for scheduled update 0-59 (default: 0)",
            },
            "shutdown_when_done": {
                "type": "BOOLEAN",
                "description": "Shut down PC when download finishes",
            },
        },
        "required": [],
    },
    timeout=300,
    needs_speak=True,
)
def game_updater(parameters: dict, player=None, speak=None) -> str:
    p = parameters or {}
    action = p.get("action", "update").lower().strip()
    platform = p.get("platform", "both").lower().strip()
    game_name = (p.get("game_name") or "").strip() or None
    app_id = (p.get("app_id") or "").strip() or None
    hour = int(p.get("hour", 3))
    minute = int(p.get("minute", 0))
    shutdown = str(p.get("shutdown_when_done", "false")).lower() == "true"

    results = []

    if action == "schedule":
        return _schedule_daily_update(hour=hour, minute=minute)
    if action == "cancel_schedule":
        return _cancel_scheduled_update()
    if action == "schedule_status":
        return _get_schedule_status()

    if action == "list":
        if platform in ("steam", "both"):
            steam_path = _find_steam_path()
            if steam_path:
                games = _get_steam_games(steam_path)
                if games:
                    names = ", ".join(g["name"] for g in games[:8])
                    suffix = f" y {len(games) - 8} más" if len(games) > 8 else ""
                    results.append(f"Steam ({len(games)} juegos): {names}{suffix}.")
                else:
                    results.append("Steam: No se encontraron juegos.")
            else:
                results.append("Steam: No instalado.")
        if platform in ("epic", "both"):
            if is_linux():
                results.append("Epic: No tiene soporte nativo en Linux.")
            else:
                games = _get_epic_games()
                if games:
                    names = ", ".join(g["name"] for g in games[:8])
                    suffix = f" y {len(games) - 8} más" if len(games) > 8 else ""
                    results.append(f"Epic ({len(games)} juegos): {names}{suffix}.")
                else:
                    results.append("Epic: No se encontraron juegos.")
        return " | ".join(results) or "No se encontraron plataformas."

    if action == "download_status":
        if platform in ("steam", "both"):
            steam_path = _find_steam_path()
            results.append(
                _get_download_status(steam_path) if steam_path else "Steam: No instalado."
            )
        if platform in ("epic", "both"):
            results.append("El estado de descarga de Epic no está disponible directamente.")
        return " ".join(results)

    if action in ("install", "update"):
        if platform in ("steam", "both"):
            steam_path = _find_steam_path()
            if not steam_path:
                results.append("Steam: No instalado.")
            else:
                if game_name:
                    installed = _get_steam_games(steam_path)
                    name_lower = game_name.lower()
                    is_installed = any(name_lower in g["name"].lower() for g in installed)
                    if not is_installed:
                        msg = _install_steam_game(steam_path, game_name=game_name, app_id=app_id)
                        if shutdown:
                            threading.Thread(
                                target=_watch_and_shutdown,
                                kwargs={"steam_path": steam_path, "speak": speak},
                                daemon=True,
                            ).start()
                            msg += " Apagado automático activado."
                        if player:
                            player.write_log(f"[GameUpdater] {msg[:100]}")
                        if speak:
                            speak(msg)
                        return msg
                    else:
                        results.append(
                            f"Steam: {_update_steam_games(steam_path, game_name=game_name)}"
                        )
                else:
                    if action == "install":
                        results.append(
                            "Steam: Por favor, especifique un nombre de juego para instalar."
                        )
                    else:
                        results.append(f"Steam: {_update_steam_games(steam_path)}")

                if shutdown:
                    threading.Thread(
                        target=_watch_and_shutdown,
                        kwargs={"steam_path": steam_path, "speak": speak},
                        daemon=True,
                    ).start()
                    results.append("Apagado automático activado.")

        if platform in ("epic", "both"):
            if is_linux():
                results.append("Epic: No tiene soporte nativo en Linux. Use Heroic Launcher.")
            else:
                epic_exe = _find_epic_exe()
                if epic_exe:
                    results.append(f"Epic: {_update_epic_games(epic_exe, game_name=game_name)}")
                else:
                    results.append("Epic: No instalado.")

        output = " | ".join(results) or "Nada que hacer."
        if player:
            player.write_log(f"[GameUpdater] {output[:100]}")
        if speak:
            speak(output)
        return output

    return f"Acción desconocida: '{action}'."


if __name__ == "__main__":
    if "--scheduled" in sys.argv:
        print(f"[GameUpdater] 🕐 Ejecución programada a las {datetime.now().strftime('%H:%M')}")
        result = game_updater({"action": "update", "platform": "both"})
        print(f"[GameUpdater] ✅ {result}")
