import os
import shutil
import platform
from pathlib import Path
from datetime import datetime

try:
    import send2trash
    _SEND2TRASH = True
except ImportError:
    _SEND2TRASH = False

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


def _windows_known_folder(name: str) -> Path | None:
    """Devuelve la ruta real de una carpeta conocida de Windows (Desktop,
    Documents, Downloads, etc.). En equipos con OneDrive sincronizado, la
    carpeta real vive dentro de ``%USERPROFILE%\\OneDrive\\``, no en
    ``%USERPROFILE%\\``. Lee el registro y, si falla, cae en el fallback
    OneDrive/local.
    """
    if _OS != "Windows":
        return None
    # Mapeo a las claves del registro Shell Folders
    reg_key_map = {
        "Desktop":   "Desktop",
        "Personal":  "Personal",     # Documents
        "Documents": "Personal",
        "Downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
        "My Pictures": "My Pictures",
        "Pictures": "My Pictures",
        "My Music": "My Music",
        "Music": "My Music",
        "My Video": "My Video",
        "Videos": "My Video",
    }
    sub = reg_key_map.get(name)
    if not sub:
        return None
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        ) as k:
            val, _ = winreg.QueryValueEx(k, sub)
            # Expandir %USERPROFILE% u %OneDrive% si aparecen
            val = os.path.expandvars(val)
            p = Path(val)
            if p.exists():
                return p
    except Exception:
        pass
    # Fallback: OneDrive\Folder o ~\Folder
    one = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
    folder_name = {
        "Personal": "Documents",
        "My Pictures": "Pictures",
        "My Music": "Music",
        "My Video": "Videos",
    }.get(name, name)
    if one:
        cand = Path(one) / folder_name
        if cand.exists():
            return cand
    cand = Path.home() / folder_name
    return cand if cand.exists() else None


def _safe_roots() -> list[Path]:
    """Conjunto de carpetas raíz consideradas 'seguras' para operaciones
    de archivos. Incluye ``~`` y la raíz de OneDrive si está activo."""
    roots: list[Path] = [Path.home()]
    one = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
    if one:
        p = Path(one)
        if p.exists():
            roots.append(p)
    return roots


_SAFE_ROOTS: list[Path] = _safe_roots()

def _is_safe_path(target: Path) -> bool:
    """¿La ruta proporcionada está dentro de _SAFE_ROOTS? Si no, rechazar la operación."""
    try:
        resolved = target.resolve()
        return any(
            resolved == root.resolve() or resolved.is_relative_to(root.resolve())
            for root in _SAFE_ROOTS
        )
    except Exception:
        return False

def _get_desktop() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DESKTOP_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    if _OS == "Windows":
        p = _windows_known_folder("Desktop")
        if p:
            return p
    return Path.home() / "Desktop"

def _get_downloads() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DOWNLOAD_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    if _OS == "Windows":
        p = _windows_known_folder("Downloads")
        if p:
            return p
    return Path.home() / "Downloads"

def _get_documents() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DOCUMENTS_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    if _OS == "Windows":
        p = _windows_known_folder("Documents")
        if p:
            return p
    return Path.home() / "Documents"

def _get_pictures() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_PICTURES_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    if _OS == "Windows":
        p = _windows_known_folder("Pictures")
        if p:
            return p
    return Path.home() / "Pictures"

def _get_music() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_MUSIC_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    if _OS == "Windows":
        p = _windows_known_folder("Music")
        if p:
            return p
    return Path.home() / "Music"

def _get_videos() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_VIDEOS_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    if _OS == "Windows":
        p = _windows_known_folder("Videos")
        if p:
            return p
    return Path.home() / "Videos"


def _resolve_path(raw: str) -> Path:
    shortcuts: dict[str, Path] = {
        "desktop":   _get_desktop(),
        "downloads": _get_downloads(),
        "documents": _get_documents(),
        "pictures":  _get_pictures(),
        "music":     _get_music(),
        "videos":    _get_videos(),
        "home":      Path.home(),
    }
    lower = raw.strip().lower()
    if lower in shortcuts:
        return shortcuts[lower]
    return Path(raw).expanduser()


# ── Extensiones legibles para el usuario ──────────────────────────────────
_EXT_LABELS: dict[str, str] = {
    ".pdf": "PDF", ".doc": "Word", ".docx": "Word",
    ".xls": "Excel", ".xlsx": "Excel", ".csv": "CSV",
    ".ppt": "PowerPoint", ".pptx": "PowerPoint",
    ".txt": "Texto", ".rtf": "RTF", ".odt": "OpenDocument",
    ".py": "Python", ".js": "JavaScript", ".html": "HTML", ".css": "CSS",
    ".java": "Java", ".cpp": "C++", ".cs": "C#", ".go": "Go",
    ".zip": "ZIP", ".rar": "RAR", ".7z": "7-Zip",
    ".jpg": "Imagen JPEG", ".jpeg": "Imagen JPEG", ".png": "Imagen PNG",
    ".gif": "GIF", ".bmp": "Bitmap", ".svg": "SVG", ".webp": "WebP",
    ".mp3": "Audio MP3", ".wav": "Audio WAV", ".flac": "Audio FLAC",
    ".mp4": "Video MP4", ".avi": "Video AVI", ".mkv": "Video MKV",
    ".exe": "Ejecutable", ".msi": "Instalador",
    ".pdsprj": "Proteus Project", ".workspace": "Workspace",
    ".json": "JSON", ".xml": "XML", ".yaml": "YAML",
    ".md": "Markdown", ".log": "Log",
    ".iso": "Imagen ISO", ".torrent": "Torrent",
    ".apk": "Android APK", ".deb": "Paquete Debian", ".rpm": "Paquete RPM",
    ".sql": "SQL", ".db": "Base de datos", ".sqlite": "SQLite",
    ".psd": "Photoshop", ".ai": "Illustrator", ".fig": "Figma",
    ".blend": "Blender", ".dwg": "AutoCAD", ".stl": "Modelo 3D",
}


def _friendly_ext(ext: str) -> str:
    """Devuelve un nombre amigable para la extensión del archivo."""
    return _EXT_LABELS.get(ext.lower(), ext.upper().lstrip(".") if ext else "Sin extensión")


def _normalize(s: str) -> str:
    """Normaliza un texto para comparación: minúsculas, sin acentos, sin separadores."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().replace("_", " ").replace("-", " ").replace(".", " ").strip()


def _primary_stem(item: Path) -> str:
    """Devuelve el primer 'tramo' del nombre, antes del primer punto.
    Útil para archivos con sufijos extra tipo
    ``Informe.pdsprj.DESKTOP-XX.zahir.workspace``."""
    return item.name.split(".")[0]


def _resolve_file(
    base: Path,
    name: str,
    *,
    recursive: bool = False,
) -> "Path | list[dict] | str":
    """Busca un archivo/carpeta de forma inteligente en ``base``.

    Estrategia de resolución (en orden de prioridad):
      1. Coincidencia exacta  (base / name)
      2. Coincidencia por stem normalizado (sin acentos, sin separadores)
      3. Coincidencia parcial  (substring tras normalización)
      4. Fuzzy matching con difflib (tolerancia a errores de dictado)

    Si ``recursive=True``, explora subcarpetas hasta una profundidad razonable.

    Returns
    -------
    Path         — si hay exactamente 1 coincidencia
    list[dict]   — si hay múltiples coincidencias (para desambiguación)
    str          — mensaje de error si no se encontró nada
    """
    if not name:
        return "No se especificó el nombre del archivo."

    target = _normalize(name)
    # Quita extensiones del nombre buscado para comparar contra el stem
    target_no_ext = target
    for ext in _EXT_LABELS:
        if target_no_ext.endswith(_normalize(ext)):
            target_no_ext = target_no_ext[: -len(_normalize(ext))].strip()
            break

    # 1) Coincidencia exacta
    exact = base / name
    if exact.exists():
        return exact

    # Escanear el directorio
    try:
        if recursive:
            items = [p for p in base.rglob("*") if not any(
                part.startswith(".") for part in p.relative_to(base).parts
            )]
        else:
            items = list(base.iterdir())
    except PermissionError:
        return f"Permiso denegado: {base}"
    except FileNotFoundError:
        return f"Directorio no encontrado: {base}"

    # 2) Coincidencia por stem normalizado (nombre o primer tramo antes del primer punto)
    stem_matches = []
    for item in items:
        primary = _normalize(_primary_stem(item))
        stem_norm = _normalize(item.stem)
        if primary == target_no_ext or stem_norm == target_no_ext:
            stem_matches.append(item)
    # Eliminar duplicados manteniendo el orden
    stem_matches = list(dict.fromkeys(stem_matches))
    if len(stem_matches) == 1:
        return stem_matches[0]
    if len(stem_matches) > 1:
        return _build_disambiguation(stem_matches)

    # 3) Coincidencia parcial (substring tras normalización)
    partial_matches = []
    for item in items:
        primary = _normalize(_primary_stem(item))
        stem_norm = _normalize(item.stem)
        # El nombre buscado está contenido en el stem o primary
        if target_no_ext and (target_no_ext in primary or target_no_ext in stem_norm):
            partial_matches.append(item)
            continue
        # O el primary del archivo está contenido en el nombre buscado
        if primary and len(primary) > 2 and primary in target_no_ext:
            partial_matches.append(item)
    partial_matches = list(dict.fromkeys(partial_matches))
    if len(partial_matches) == 1:
        return partial_matches[0]
    if len(partial_matches) > 1:
        return _build_disambiguation(partial_matches)

    # 4) Fuzzy matching (tolerancia a errores de voz/escritura)
    from difflib import SequenceMatcher
    scored = []
    for item in items:
        primary = _normalize(_primary_stem(item))
        stem_norm = _normalize(item.stem)
        ratio = max(
            SequenceMatcher(None, target_no_ext, primary).ratio(),
            SequenceMatcher(None, target_no_ext, stem_norm).ratio(),
        )
        if ratio >= 0.6:
            scored.append((ratio, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    fuzzy_matches = [item for _, item in scored[:10]]

    if len(fuzzy_matches) == 1:
        return fuzzy_matches[0]
    if len(fuzzy_matches) > 1:
        return _build_disambiguation(fuzzy_matches)

    return f"No se encontró ningún archivo o carpeta con nombre similar a '{name}' en {base.name}/"


def _build_disambiguation(matches: list[Path]) -> list[dict]:
    """Construye una lista de coincidencias para desambiguación."""
    results = []
    for item in matches:
        kind = "📁 Carpeta" if item.is_dir() else "📄 Archivo"
        ext = _friendly_ext(item.suffix) if not item.is_dir() else "Carpeta"
        try:
            size = _format_size(item.stat().st_size) if item.is_file() else ""
        except Exception:
            size = ""
        results.append({
            "path": item,
            "name": item.name,
            "stem": item.stem,
            "ext": ext,
            "kind": kind,
            "size": size,
        })
    return results


def _format_disambiguation(matches: list[dict], action_verb: str = "procesar") -> str:
    """Formatea la lista de coincidencias para que Gemini pregunte al usuario.

    Agrupa carpetas y archivos por tipo legible (Word, PDF, Proteus, Workspace…)
    para que ORION pueda preguntar de forma natural:
    ``He encontrado un PDF, una carpeta y un proyecto de Proteus, ¿cuál
    quieres eliminar o quieres todos?``.
    """
    folders = [m for m in matches if m["kind"].startswith("📁")]
    files = [m for m in matches if not m["kind"].startswith("📁")]

    # Resumen amigable agrupado por tipo (lo que ORION debe leer al usuario)
    summary_parts: list[str] = []
    if folders:
        summary_parts.append(
            "una carpeta" if len(folders) == 1
            else f"{len(folders)} carpetas"
        )
    # Agrupar archivos por extensión legible
    by_ext: dict[str, int] = {}
    for f in files:
        by_ext[f["ext"]] = by_ext.get(f["ext"], 0) + 1
    for ext, count in by_ext.items():
        if count == 1:
            summary_parts.append(f"un archivo {ext}")
        else:
            summary_parts.append(f"{count} archivos {ext}")

    if len(summary_parts) > 1:
        natural = ", ".join(summary_parts[:-1]) + " y " + summary_parts[-1]
    elif summary_parts:
        natural = summary_parts[0]
    else:
        natural = f"{len(matches)} coincidencias"

    lines = [
        f"He encontrado {natural} con nombre similar. "
        f"Pregúntale al usuario CUÁL quiere {action_verb} (o si quiere TODOS).",
        "",
        "Coincidencias detalladas:",
    ]
    for i, m in enumerate(matches, 1):
        size_part = f" ({m['size']})" if m['size'] else ""
        lines.append(f"  {i}. {m['kind']} — {m['name']} [{m['ext']}]{size_part}")
    lines.append("")
    lines.append(
        f"IMPORTANTE: di al usuario las opciones en lenguaje natural "
        f"(ej. 'tengo un PDF y una carpeta') y pregunta cuál {action_verb} "
        f"o si quiere todos. NO leas la ruta completa."
    )
    return "\n".join(lines)


def _format_size(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"

def _safe_trash(target: Path) -> str:

    if not _SEND2TRASH:
        return (
            "send2trash no está instalado. "
            "Ejecuta: pip install send2trash — "
            "La eliminación permanente está deshabilitada por seguridad."
        )
    send2trash.send2trash(str(target))
    return f"Enviado a la papelera: {target.name}"


def list_files(path: str = "desktop", show_hidden: bool = False) -> str:
    try:
        target = _resolve_path(path)
        if not _is_safe_path(target):
            return f"Acceso denegado: {target}"
        if not target.exists():
            return f"Ruta no encontrada: {target}"
        if not target.is_dir():
            return f"No es un directorio: {target}"

        items = []
        for item in sorted(target.iterdir()):
            if not show_hidden and item.name.startswith("."):
                continue
            if item.is_dir():
                items.append(f"📁 {item.name}/")
            else:
                size = _format_size(item.stat().st_size)
                items.append(f"📄 {item.name} ({size})")

        if not items:
            return f"El directorio está vacío: {target.name}/"

        return f"Contenido de {target.name}/ ({len(items)} elementos):\n" + "\n".join(items)

    except PermissionError:
        return f"Permiso denegado: {path}"
    except Exception as e:
        return f"Error al listar archivos: {e}"


def create_file(path: str, name: str = "", content: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Acceso denegado: {target}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Archivo creado: {target.name}"
    except Exception as e:
        return f"No se pudo crear el archivo: {e}"


def create_folder(path: str, name: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Acceso denegado: {target}"
        target.mkdir(parents=True, exist_ok=True)
        return f"Carpeta creada: {target.name}"
    except Exception as e:
        return f"No se pudo crear la carpeta: {e}"


_PROTECTED_DIRS = lambda: {
    _get_desktop(), _get_downloads(), _get_documents(),
    _get_pictures(), _get_music(), _get_videos(), Path.home()
}


def delete_file(path: str, name: str = "", confirm_all: bool = False) -> str:
    try:
        base = _resolve_path(path)
        if not name:
            return "No se especificó qué eliminar."
        if not _is_safe_path(base):
            return f"Acceso denegado: {base}"

        # Resolución inteligente del nombre
        resolved = _resolve_file(base, name)

        # Múltiples coincidencias → preguntar al usuario (o eliminar todas si confirm_all)
        if isinstance(resolved, list):
            if confirm_all:
                deleted, errors = [], []
                protected = {p.resolve() for p in _PROTECTED_DIRS()}
                for m in resolved:
                    t = m["path"]
                    if t.resolve() in protected:
                        errors.append(f"{t.name} (protegido)")
                        continue
                    try:
                        _safe_trash(t)
                        deleted.append(t.name)
                    except Exception as e:
                        errors.append(f"{t.name} ({e})")
                msg = f"Eliminados {len(deleted)} elemento(s) a la papelera."
                if errors:
                    msg += f" No eliminados: {', '.join(errors)}."
                return msg
            return _format_disambiguation(resolved, action_verb="eliminar")

        if isinstance(resolved, str):
            return resolved

        target = resolved
        if target.resolve() in {p.resolve() for p in _PROTECTED_DIRS()}:
            return f"Directorio protegido, no se puede eliminar: {target.name}"

        return _safe_trash(target)

    except PermissionError:
        return f"Permiso denegado: {path}"
    except Exception as e:
        return f"No se pudo eliminar: {e}"


def move_file(path: str, name: str = "", destination: str = "") -> str:
    try:
        base = _resolve_path(path)
        dst = _resolve_path(destination) if destination else None
        if not name:
            return "No se especificó el archivo a mover."
        resolved = _resolve_file(base, name)
        if isinstance(resolved, list):
            return _format_disambiguation(resolved, action_verb="mover")
        if isinstance(resolved, str):
            return resolved
        src = resolved

        if dst is None:
            return "No se especificó destino."
        if not _is_safe_path(src):
            return f"Acceso denegado (origen): {src}"
        if not _is_safe_path(dst):
            return f"Acceso denegado (destino): {dst}"

        if dst.is_dir():
            dst = dst / src.name

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Movido: {src.name} → {dst.parent.name}/"

    except Exception as e:
        return f"No se pudo mover: {e}"


def copy_file(path: str, name: str = "", destination: str = "") -> str:
    try:
        base = _resolve_path(path)
        dst = _resolve_path(destination) if destination else None
        if not name:
            return "No se especificó el archivo a copiar."
        resolved = _resolve_file(base, name)
        if isinstance(resolved, list):
            return _format_disambiguation(resolved, action_verb="copiar")
        if isinstance(resolved, str):
            return resolved
        src = resolved

        if dst is None:
            return "No se especificó destino."
        if not _is_safe_path(src):
            return f"Acceso denegado (origen): {src}"
        if not _is_safe_path(dst):
            return f"Acceso denegado (destino): {dst}"

        if dst.is_dir():
            dst = dst / src.name

        dst.parent.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            shutil.copytree(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))

        return f"Copiado: {src.name} → {dst.parent.name}/"

    except Exception as e:
        return f"No se pudo copiar: {e}"


def rename_file(path: str, name: str = "", new_name: str = "") -> str:
    try:
        base = _resolve_path(path)
        if not name:
            return "No se especificó qué renombrar."
        resolved = _resolve_file(base, name)
        if isinstance(resolved, list):
            return _format_disambiguation(resolved, action_verb="renombrar")
        if isinstance(resolved, str):
            return resolved
        target = resolved

        if not _is_safe_path(target):
            return f"Acceso denegado: {target}"
        if not new_name:
            return "No se proporcionó nombre nuevo."

        new_path = target.parent / new_name
        if new_path.exists():
            return f"Ya existe un archivo llamado '{new_name}' aquí."

        target.rename(new_path)
        return f"Renombrado: {target.name} → {new_name}"

    except Exception as e:
        return f"No se pudo renombrar: {e}"


def read_file(path: str, name: str = "", max_chars: int = 4000) -> str:
    try:
        base = _resolve_path(path)
        if name:
            resolved = _resolve_file(base, name)
            if isinstance(resolved, list):
                return _format_disambiguation(resolved, action_verb="leer")
            if isinstance(resolved, str):
                return resolved
            target = resolved
        else:
            target = base

        if not _is_safe_path(target):
            return f"Acceso denegado: {target}"
        if not target.is_file():
            return f"No es un archivo: {target.name}"

        content = target.read_text(encoding="utf-8", errors="ignore")
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n[Truncado — {len(content)} caracteres en total]"
        return content

    except Exception as e:
        return f"No se pudo leer el archivo: {e}"


def write_file(path: str, name: str = "", content: str = "",
               append: bool = False) -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Acceso denegado: {target}"
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(target, mode, encoding="utf-8") as f:
            f.write(content)
        action = "Añadido a" if append else "Escrito en"
        return f"{action}: {target.name}"
    except Exception as e:
        return f"No se pudo escribir el archivo: {e}"


def find_files(name: str = "", extension: str = "",
               path: str = "home", max_results: int = 20) -> str:
    try:
        search_path = _resolve_path(path)
        if not _is_safe_path(search_path):
            return f"Acceso denegado: {search_path}"
        if not search_path.exists():
            return f"Ruta de búsqueda no encontrada: {path}"

        results    = []
        dir_count  = 0
        max_dirs   = 500  # límite de rendimiento + seguridad

        for item in search_path.rglob("*"):
            if item.is_dir():
                dir_count += 1
                if dir_count > max_dirs:
                    break
                continue
            if not item.is_file():
                continue
            if extension and item.suffix.lower() != extension.lower():
                continue
            if name and name.lower() not in item.name.lower():
                continue
            size = _format_size(item.stat().st_size)
            results.append(f"📄 {item.name} ({size}) — {item.parent}")
            if len(results) >= max_results:
                break

        if not results:
            query = name or extension or "archivos"
            return f"No se encontraron {query} en {search_path.name}/"

        return f"Se encontraron {len(results)} archivo(s):\n" + "\n".join(results)

    except Exception as e:
        return f"Error de búsqueda: {e}"


def get_largest_files(path: str = "downloads", count: int = 10) -> str:
    count = min(count, 50)  # máximo 50
    try:
        search_path = _resolve_path(path)
        if not _is_safe_path(search_path):
            return f"Acceso denegado: {search_path}"
        if not search_path.exists():
            return f"Ruta no encontrada: {path}"

        files = []
        for item in search_path.rglob("*"):
            if item.is_file():
                try:
                    files.append((item.stat().st_size, item))
                except Exception:
                    continue

        files.sort(reverse=True)
        top = files[:count]

        if not top:
            return "No se encontraron archivos."

        lines = [f"Los {len(top)} archivos más grandes en {search_path.name}/:"]
        for size, f in top:
            lines.append(f"  {_format_size(size):>10}  {f.name}  ({f.parent})")

        return "\n".join(lines)

    except Exception as e:
        return f"Error: {e}"


def get_disk_usage(path: str = "home") -> str:
    try:
        target = _resolve_path(path)
        usage  = shutil.disk_usage(target)
        pct    = usage.used / usage.total * 100
        return (
            f"Uso del disco ({target}):\n"
            f"  Total : {_format_size(usage.total)}\n"
            f"  Usado : {_format_size(usage.used)} ({pct:.1f}%)\n"
            f"  Libre : {_format_size(usage.free)}"
        )
    except Exception as e:
        return f"No se pudo obtener el uso del disco: {e}"


def organize_desktop() -> str:
    type_map = {
        "Imagenes":   {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".heic"},
        "Documentos": {".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx",
                       ".ppt", ".pptx", ".csv", ".odt", ".ods", ".odp"},
        "Videos":     {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
        "Musica":     {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
        "Archivos":   {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
        "Codigo":     {".py", ".js", ".ts", ".html", ".css", ".json", ".xml",
                       ".cpp", ".java", ".cs", ".go", ".rs", ".sh"},
    }

    desktop = _get_desktop()
    moved, skipped = [], []

    try:
        for item in desktop.iterdir():
            # No tocar carpetas, archivos ocultos ni carpetas ya organizadas
            if item.is_dir() or item.name.startswith("."):
                continue
            if item.name in {k for k in type_map}:
                continue

            ext        = item.suffix.lower()
            target_dir = desktop / "Otros"
            for folder, exts in type_map.items():
                if ext in exts:
                    target_dir = desktop / folder
                    break

            target_dir.mkdir(exist_ok=True)
            new_path = target_dir / item.name

            if new_path.exists():
                skipped.append(item.name)
                continue

            shutil.move(str(item), str(new_path))
            moved.append(f"{item.name} → {target_dir.name}/")

        result = f"Escritorio organizado: {len(moved)} archivo(s) movido(s)."
        if moved:
            preview = moved[:8]
            result += "\n" + "\n".join(preview)
            if len(moved) > 8:
                result += f"\n... y {len(moved) - 8} más."
        if skipped:
            result += f"\n{len(skipped)} archivo(s) omitido(s) (conflicto de nombre)."
        return result

    except Exception as e:
        return f"No se pudo organizar el escritorio: {e}"


def get_file_info(path: str, name: str = "") -> str:
    try:
        base = _resolve_path(path)
        if name:
            resolved = _resolve_file(base, name)
            if isinstance(resolved, list):
                return _format_disambiguation(resolved, action_verb="consultar")
            if isinstance(resolved, str):
                return resolved
            target = resolved
        else:
            target = base
        if not _is_safe_path(target):
            return f"Acceso denegado: {target}"
        if not target.exists():
            return f"No encontrado: {target.name}"

        stat = target.stat()
        info = {
            "Nombre":     target.name,
            "Tipo":       "Carpeta" if target.is_dir() else "Archivo",
            "Tamaño":     _format_size(stat.st_size),
            "Ubicación":  str(target.parent),
            "Creado":     datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
            "Modificado": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "Extensión":  target.suffix or "—",
        }
        return "\n".join(f"  {k}: {v}" for k, v in info.items())

    except Exception as e:
        return f"No se pudo obtener la información del archivo: {e}"

def file_controller(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "").lower().strip()
    path   = params.get("path", "desktop")
    name   = params.get("name", "")

    if player:
        player.write_log(f"[file] {action} {name or path}")

    try:
        if action == "list":
            return list_files(path)

        elif action == "create_file":
            return create_file(path, name=name, content=params.get("content", ""))

        elif action == "create_folder":
            return create_folder(path, name=name)

        elif action in ("delete", "delete_all"):
            confirm_all = action == "delete_all" or bool(params.get("confirm_all", False))
            return delete_file(path, name=name, confirm_all=confirm_all)

        elif action == "move":
            return move_file(path, name=name, destination=params.get("destination", ""))

        elif action == "copy":
            return copy_file(path, name=name, destination=params.get("destination", ""))

        elif action == "rename":
            return rename_file(path, name=name, new_name=params.get("new_name", ""))

        elif action == "read":
            return read_file(path, name=name)

        elif action == "write":
            return write_file(
                path, name=name,
                content=params.get("content", ""),
                append=params.get("append", False)
            )

        elif action == "find":
            return find_files(
                name=name or params.get("name", ""),
                extension=params.get("extension", ""),
                path=path,
                max_results=min(int(params.get("max_results", 20)), 50),
            )

        elif action == "largest":
            return get_largest_files(
                path=path,
                count=int(params.get("count", 10)),
            )

        elif action == "disk_usage":
            return get_disk_usage(path)

        elif action == "organize_desktop":
            return organize_desktop()

        elif action == "info":
            return get_file_info(path, name=name)

        else:
            return f"Acción desconocida: '{action}'"

    except Exception as e:
        return f"Error del controlador de archivos ({action}): {e}"
