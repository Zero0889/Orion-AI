# desktop.py
import os
import platform
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
import contextlib

_OS = platform.system()


def _get_desktop() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DESKTOP_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Desktop"


# ── Eliminado: ejecución de código LLM-generado ─────────────────────────────
# Antes esta tool aceptaba `action="task"` con texto libre, le pedía a Gemini
# que generara código Python y lo ejecutaba con exec() sobre un dict de
# "safe_builtins". Ese sandbox NO ofrecía garantías reales: el modelo
# `().__class__.__mro__[1].__subclasses__()` clásico permite escapar de
# cualquier filtro de builtins en CPython, y el flujo end-to-end era una
# ruta de RCE accesible por voz / prompt injection.
#
# Reemplazo: las 7 acciones explícitas (wallpaper, organize, clean, list,
# stats, current_wallpaper, wallpaper_url) cubren los casos legítimos sin
# codegen. Si el modelo intenta `action="task"`, devolvemos un mensaje
# explicando cómo formular la petición con las acciones disponibles.
# Para automatización ad-hoc real existen tools dedicadas: file_controller,
# computer_control, open_app, screen_processor.


def set_wallpaper(image_path: str) -> str:
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        return f"Imagen no encontrada: {image_path}"
    if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        return f"Formato no compatible: {path.suffix}. Use jpg, png, bmp o webp."

    try:
        if _OS == "Windows":
            import ctypes

            if path.suffix.lower() in {".webp", ".png"}:
                try:
                    from PIL import Image

                    bmp_path = Path(tempfile.mktemp(suffix=".bmp"))
                    Image.open(path).convert("RGB").save(bmp_path, "BMP")
                    path = bmp_path
                except ImportError:
                    pass
            ctypes.windll.user32.SystemParametersInfoW(20, 0, str(path), 3)
            return f"Fondo de pantalla establecido: {path.name}"

        elif _OS == "Darwin":
            script = (
                f'tell application "System Events" to tell every desktop to '
                f'set picture to POSIX file "{path}"'
            )
            subprocess.run(["osascript", "-e", script], capture_output=True)
            return f"Fondo de pantalla establecido: {path.name}"

        else:
            desktop_env = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
            uri = f"file://{path}"

            if "gnome" in desktop_env or "unity" in desktop_env:
                subprocess.run(
                    ["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri],
                    capture_output=True,
                )
                subprocess.run(
                    ["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri],
                    capture_output=True,
                )

            elif "kde" in desktop_env:
                # KDE Plasma
                script = f"""
var allDesktops = desktops();
for (var i = 0; i < allDesktops.length; i++) {{
    d = allDesktops[i];
    d.wallpaperPlugin = "org.kde.image";
    d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    d.writeConfig("Image", "file://{path}");
}}
"""
                subprocess.run(
                    [
                        "qdbus",
                        "org.kde.plasmashell",
                        "/PlasmaShell",
                        "org.kde.PlasmaShell.evaluateScript",
                        script,
                    ],
                    capture_output=True,
                )

            elif "xfce" in desktop_env:
                subprocess.run(
                    [
                        "xfconf-query",
                        "-c",
                        "xfce4-desktop",
                        "-p",
                        "/backdrop/screen0/monitor0/workspace0/last-image",
                        "-s",
                        str(path),
                    ],
                    capture_output=True,
                )

            else:
                result = subprocess.run(["feh", "--bg-scale", str(path)], capture_output=True)
                if result.returncode != 0:
                    return (
                        f"No se pudo establecer el fondo de pantalla automáticamente en {desktop_env}. "
                        f"Intente manualmente o instale 'feh'."
                    )

            return f"Fondo de pantalla establecido: {path.name}"

    except Exception as e:
        return f"No se pudo establecer el fondo de pantalla: {e}"


def set_wallpaper_from_url(url: str) -> str:
    try:
        import urllib.request

        suffix = Path(url.split("?")[0]).suffix or ".jpg"
        tmp = Path(tempfile.mktemp(suffix=suffix))
        urllib.request.urlretrieve(url, str(tmp))
        result = set_wallpaper(str(tmp))
        with contextlib.suppress(Exception):
            tmp.unlink()
        return result
    except Exception as e:
        return f"No se pudo descargar el fondo de pantalla: {e}"


def get_current_wallpaper() -> str:
    try:
        if _OS == "Windows":
            import winreg

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop")
            val, _ = winreg.QueryValueEx(key, "Wallpaper")
            winreg.CloseKey(key)
            return f"Fondo de pantalla actual: {val}"

        elif _OS == "Darwin":
            script = 'tell application "System Events" to get picture of desktop 1'
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            return f"Fondo de pantalla actual: {result.stdout.strip()}"

        else:
            desktop_env = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
            if "gnome" in desktop_env or "unity" in desktop_env:
                result = subprocess.run(
                    ["gsettings", "get", "org.gnome.desktop.background", "picture-uri"],
                    capture_output=True,
                    text=True,
                )
                return f"Fondo de pantalla actual: {result.stdout.strip()}"
            return "La obtención de la ruta del fondo de pantalla no es compatible con este entorno de escritorio."

    except Exception as e:
        return f"No se pudo obtener el fondo de pantalla: {e}"


FILE_TYPE_MAP = {
    "Imagenes": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".heic"},
    "Documentos": {
        ".pdf",
        ".doc",
        ".docx",
        ".txt",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".csv",
        ".odt",
        ".ods",
        ".odp",
    },
    "Videos": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
    "Musica": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
    "Archivos": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "Codigo": {
        ".py",
        ".js",
        ".ts",
        ".html",
        ".css",
        ".json",
        ".xml",
        ".cpp",
        ".java",
        ".cs",
        ".go",
        ".rs",
        ".sh",
        ".php",
    },
    "Ejecutables": {".exe", ".msi", ".bat", ".cmd", ".sh", ".appimage", ".deb", ".rpm"},
}

_SKIP_EXTENSIONS = {
    "Windows": {".lnk", ".url"},
    "Darwin": {".webloc"},
    "Linux": {".desktop"},
}


def organize_desktop(mode: str = "by_type") -> str:
    desktop = _get_desktop()
    skip_exts = _SKIP_EXTENSIONS.get(_OS, set())
    moved, skipped = [], []

    for item in desktop.iterdir():
        if item.is_dir() or item.name.startswith("."):
            continue
        if item.suffix.lower() in skip_exts:
            continue

        if mode == "by_date":
            mtime = datetime.fromtimestamp(item.stat().st_mtime)
            folder_name = mtime.strftime("%Y-%m")
        else:
            ext = item.suffix.lower()
            folder_name = "Otros"
            for folder, exts in FILE_TYPE_MAP.items():
                if ext in exts:
                    folder_name = folder
                    break

        target_dir = desktop / folder_name
        target_dir.mkdir(exist_ok=True)
        new_path = target_dir / item.name

        if new_path.exists():
            skipped.append(item.name)
            continue

        shutil.move(str(item), str(new_path))
        moved.append(f"{item.name} → {folder_name}/")

    result = f"Escritorio organizado ({mode}): {len(moved)} archivo(s) movido(s)."
    if moved:
        result += "\n" + "\n".join(moved[:8])
        if len(moved) > 8:
            result += f"\n... y {len(moved) - 8} más."
    if skipped:
        result += f"\n{len(skipped)} archivo(s) omitido(s) (conflicto de nombre)."
    return result


def list_desktop() -> str:
    desktop = _get_desktop()
    items = []
    for item in sorted(desktop.iterdir()):
        if item.name.startswith("."):
            continue
        if item.is_dir():
            try:
                count = len(list(item.iterdir()))
            except PermissionError:
                count = "?"
            items.append(f"📁 {item.name}/ ({count} elementos)")
        else:
            size = item.stat().st_size
            size_str = (
                f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"
            )
            items.append(f"📄 {item.name} ({size_str})")

    if not items:
        return "El escritorio está vacío."
    return f"Escritorio ({len(items)} elementos):\n" + "\n".join(items)


def clean_desktop() -> str:
    desktop = _get_desktop()
    skip_exts = _SKIP_EXTENSIONS.get(_OS, set())
    today = datetime.now().strftime("%Y-%m-%d")
    archive_dir = desktop / f"Archivo Escritorio {today}"
    archive_dir.mkdir(exist_ok=True)

    moved = 0
    for item in desktop.iterdir():
        if item.is_dir() or item.name.startswith("."):
            continue
        if item.suffix.lower() in skip_exts:
            continue
        new_path = archive_dir / item.name
        if not new_path.exists():
            shutil.move(str(item), str(new_path))
            moved += 1

    return f"Escritorio limpio: {moved} archivo(s) archivado(s) en '{archive_dir.name}'."


def get_desktop_stats() -> str:
    desktop = _get_desktop()
    files = [i for i in desktop.iterdir() if i.is_file()]
    folders = [i for i in desktop.iterdir() if i.is_dir()]
    total_size = sum(f.stat().st_size for f in files if f.exists())
    size_str = (
        f"{total_size / 1024:.1f} KB"
        if total_size < 1024 * 1024
        else f"{total_size / 1024 / 1024:.1f} MB"
    )
    return (
        f"Estadísticas del escritorio ({_OS}):\n"
        f"  Archivos : {len(files)}\n"
        f"  Carpetas : {len(folders)}\n"
        f"  Tamaño   : {size_str}\n"
        f"  Ruta     : {desktop}"
    )


from core.tool_registry import tool


@tool(
    name="desktop_control",
    description=(
        "Controls the desktop with EXPLICIT actions only. "
        "For file operations use file_controller; for opening apps "
        "use open_app; for general system control use computer_control."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "wallpaper | wallpaper_url | current_wallpaper | organize | clean | list | stats",
            },
            "path": {"type": "STRING", "description": "Image path for wallpaper"},
            "url": {"type": "STRING", "description": "Image URL for wallpaper_url"},
            "mode": {"type": "STRING", "description": "by_type or by_date for organize"},
        },
        "required": ["action"],
    },
)
def desktop_control(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    parameters:
        action : wallpaper | wallpaper_url | current_wallpaper |
                 organize  | clean | list | stats |
                 task (impulsado por IA)
        path   : ruta de imagen para 'wallpaper'
        url    : URL de imagen para 'wallpaper_url'
        mode   : 'by_type' o 'by_date' para 'organize'
        task   : descripción en lenguaje natural para acciones impulsadas por IA
    """
    params = parameters or {}
    action = params.get("action", "").lower().strip()
    task = params.get("task", "").strip()

    if player:
        player.write_log(f"[desktop] {action or task[:40]}")

    try:
        if action == "wallpaper":
            path = params.get("path", "")
            return set_wallpaper(path) if path else "No se proporcionó ruta de imagen."

        elif action == "wallpaper_url":
            url = params.get("url", "")
            return set_wallpaper_from_url(url) if url else "No se proporcionó URL."

        elif action == "current_wallpaper":
            return get_current_wallpaper()

        elif action == "organize":
            return organize_desktop(params.get("mode", "by_type"))

        elif action == "clean":
            return clean_desktop()

        elif action == "list":
            return list_desktop()

        elif action == "stats":
            return get_desktop_stats()

        elif action == "task" or task:
            # Esta rama ejecutaba código LLM-generado vía exec(). Removida
            # por seguridad — ver comentario al inicio del módulo.
            return (
                "Las tareas ad-hoc de escritorio ya no se ejecutan con "
                "código generado. Use una acción explícita:\n"
                "  • wallpaper / wallpaper_url / current_wallpaper\n"
                "  • organize (mode=by_type|by_date) / clean\n"
                "  • list / stats\n"
                "Para operaciones de archivos, abrir apps o automatización "
                "general, use las tools file_controller, open_app o "
                "computer_control."
            )

        else:
            return (
                "Acción de escritorio desconocida. Acciones soportadas: "
                "wallpaper, wallpaper_url, current_wallpaper, organize, "
                "clean, list, stats."
            )

    except Exception as e:
        print(f"[Desktop] Error: {e}")
        return f"Error de control de escritorio: {e}"
