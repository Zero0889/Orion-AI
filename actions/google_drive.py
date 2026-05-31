"""
Google Drive — Action module for O.R.I.O.N
============================================
Manages files in Google Drive: upload, create, edit, move, list, search,
download, delete (trash), and share.

Uses Google Drive API v3 with OAuth2 credentials.
First-time setup requires a credentials.json from Google Cloud Console
placed in config/credentials.json.
"""

import io
import json
import os
import mimetypes
from pathlib import Path

# Google API imports
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload
    _GOOGLE_AVAILABLE = True
except ImportError:
    _GOOGLE_AVAILABLE = False

# ── Paths ──────────────────────────────────────────────────────────────────
from config import BASE_DIR as _BASE_DIR
_CREDENTIALS_PATH = _BASE_DIR / "config" / "credentials.json"
_TOKEN_PATH = _BASE_DIR / "config" / "gdrive_token.json"

# Full read/write access to Google Drive
_SCOPES = ["https://www.googleapis.com/auth/drive"]

# MIME types for Google Workspace document creation
_GDOC_MIME = "application/vnd.google-apps.document"
_GSHEET_MIME = "application/vnd.google-apps.spreadsheet"
_GSLIDES_MIME = "application/vnd.google-apps.presentation"
_GFOLDER_MIME = "application/vnd.google-apps.folder"

_EXPORT_MIMES = {
    _GDOC_MIME: ("application/pdf", ".pdf"),
    _GSHEET_MIME: ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    _GSLIDES_MIME: ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
}


def _get_downloads_dir() -> Path:
    return Path.home() / "Downloads"


# ============================================================================
#  Auth
# ============================================================================
def _authenticate():
    """Authenticate with Google Drive via OAuth2.
    Returns a Drive service object or raises an error with a user-friendly message.
    """
    if not _GOOGLE_AVAILABLE:
        raise RuntimeError(
            "Las bibliotecas de Google no están instaladas. "
            "Ejecuta: pip install google-auth google-auth-oauthlib google-api-python-client"
        )

    if not _CREDENTIALS_PATH.exists():
        raise FileNotFoundError(
            "No se encontró credentials.json en config/. "
            "Descárgalo desde Google Cloud Console (APIs > Credenciales > OAuth 2.0) "
            "y colócalo en: " + str(_CREDENTIALS_PATH)
        )

    creds = None

    if _TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), _SCOPES)
        except Exception:
            creds = None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(_CREDENTIALS_PATH), _SCOPES
        )
        creds = flow.run_local_server(port=0, open_browser=True)
        _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


# ============================================================================
#  Individual operations
# ============================================================================
def _resolve_local_upload(file_path: str) -> "Path | str":
    """Resuelve un ``file_path`` local de forma inteligente.

    Si la ruta exacta existe → devuelve Path.
    Si no, intenta buscar por nombre parcial en los lugares más comunes
    (escritorio, descargas, documentos, home) y devuelve:
      - Path si encuentra exactamente una coincidencia
      - str con el mensaje de desambiguación si hay varias
      - str con un error si no hay nada
    """
    p = Path(file_path).expanduser()
    if p.exists():
        return p

    # Si solo tenemos un nombre (no una ruta), buscar en lugares comunes
    name = p.name if p.name else file_path
    try:
        from actions.file_controller import (
            _resolve_file, _resolve_path, _format_disambiguation,
        )
    except Exception:
        return f"Archivo no encontrado: {file_path}"

    candidates: list = []
    for loc in ("desktop", "downloads", "documents", "home"):
        try:
            base = _resolve_path(loc)
            found = _resolve_file(base, name)
            if isinstance(found, Path):
                candidates.append(found)
            elif isinstance(found, list):
                for m in found:
                    candidates.append(m["path"])
        except Exception:
            continue

    # Dedup
    seen = set()
    uniq = []
    for c in candidates:
        key = str(c.resolve())
        if key not in seen:
            seen.add(key)
            uniq.append(c)

    if len(uniq) == 1:
        return uniq[0]
    if len(uniq) > 1:
        from actions.file_controller import _build_disambiguation
        return _format_disambiguation(
            _build_disambiguation(uniq),
            action_verb="subir a Drive",
        )
    return f"Archivo no encontrado: {file_path}"


def _upload_file(service, file_path: str, folder_id: str = None) -> str:
    """Upload a local file to Google Drive."""
    resolved = _resolve_local_upload(file_path)
    if isinstance(resolved, str):
        return resolved
    p = resolved

    mime_type = mimetypes.guess_type(str(p))[0] or "application/octet-stream"

    metadata = {"name": p.name}
    if folder_id:
        metadata["parents"] = [folder_id]

    media = MediaFileUpload(str(p), mimetype=mime_type, resumable=True)
    result = service.files().create(
        body=metadata, media_body=media, fields="id, name, webViewLink"
    ).execute()

    return (
        f"Archivo subido exitosamente.\n"
        f"  Nombre: {result.get('name')}\n"
        f"  ID: {result.get('id')}\n"
        f"  Link: {result.get('webViewLink', 'N/A')}"
    )


def _create_document(service, name: str, doc_type: str = "document",
                     folder_id: str = None, content: str = None) -> str:
    """Create a new Google Workspace document (Doc, Sheet, or Slides)."""
    type_map = {
        "document": _GDOC_MIME,
        "doc": _GDOC_MIME,
        "documento": _GDOC_MIME,
        "spreadsheet": _GSHEET_MIME,
        "sheet": _GSHEET_MIME,
        "hoja": _GSHEET_MIME,
        "excel": _GSHEET_MIME,
        "presentation": _GSLIDES_MIME,
        "slides": _GSLIDES_MIME,
        "presentacion": _GSLIDES_MIME,
    }

    mime = type_map.get(doc_type.lower().strip(), _GDOC_MIME)

    metadata = {"name": name, "mimeType": mime}
    if folder_id:
        metadata["parents"] = [folder_id]

    result = service.files().create(
        body=metadata, fields="id, name, webViewLink, mimeType"
    ).execute()

    doc_id = result.get("id")

    if content and mime == _GDOC_MIME:
        try:
            from googleapiclient.discovery import build as build_svc
            docs_service = build_svc("docs", "v1", credentials=service._http.credentials)
            requests_body = [
                {"insertText": {"location": {"index": 1}, "text": content}}
            ]
            docs_service.documents().batchUpdate(
                documentId=doc_id, body={"requests": requests_body}
            ).execute()
        except Exception:
            pass

    type_label = {
        _GDOC_MIME: "Documento",
        _GSHEET_MIME: "Hoja de cálculo",
        _GSLIDES_MIME: "Presentación",
    }.get(mime, "Documento")

    return (
        f"{type_label} creado exitosamente.\n"
        f"  Nombre: {result.get('name')}\n"
        f"  ID: {doc_id}\n"
        f"  Link: {result.get('webViewLink', 'N/A')}"
    )


def _create_folder(service, name: str, parent_id: str = None) -> str:
    """Create a folder in Google Drive."""
    metadata = {"name": name, "mimeType": _GFOLDER_MIME}
    if parent_id:
        metadata["parents"] = [parent_id]

    result = service.files().create(
        body=metadata, fields="id, name, webViewLink"
    ).execute()

    return (
        f"Carpeta creada exitosamente.\n"
        f"  Nombre: {result.get('name')}\n"
        f"  ID: {result.get('id')}\n"
        f"  Link: {result.get('webViewLink', 'N/A')}"
    )


def _list_files(service, folder_id: str = None, query: str = None,
                max_results: int = 20) -> str:
    """List files in Google Drive, optionally filtered by folder or query."""
    q_parts = ["trashed = false"]

    if folder_id:
        q_parts.append(f"'{folder_id}' in parents")

    if query:
        q_parts.append(f"name contains '{query}'")

    q = " and ".join(q_parts)

    results = service.files().list(
        q=q,
        pageSize=min(max_results, 100),
        fields="files(id, name, mimeType, modifiedTime, size, webViewLink)",
        orderBy="modifiedTime desc",
    ).execute()

    files = results.get("files", [])

    if not files:
        return "No se encontraron archivos en Google Drive."

    lines = [f"Archivos en Google Drive ({len(files)} resultado(s)):"]
    for f in files:
        mime = f.get("mimeType", "")
        if mime == _GFOLDER_MIME:
            icon = "\U0001F4C1"
        elif "document" in mime:
            icon = "\U0001F4DD"
        elif "spreadsheet" in mime:
            icon = "\U0001F4CA"
        elif "presentation" in mime:
            icon = "\U0001F4CA"
        elif "image" in mime:
            icon = "\U0001F5BC"
        elif "video" in mime:
            icon = "\U0001F3AC"
        elif "audio" in mime:
            icon = "\U0001F3B5"
        else:
            icon = "\U0001F4C4"

        size_str = ""
        if f.get("size"):
            size_bytes = int(f["size"])
            for unit in ["B", "KB", "MB", "GB"]:
                if size_bytes < 1024:
                    size_str = f" ({size_bytes:.1f} {unit})"
                    break
                size_bytes /= 1024

        lines.append(f"  {icon} {f['name']}{size_str} — ID: {f['id']}")

    return "\n".join(lines)


def _search_files(service, query: str, max_results: int = 20) -> str:
    """Search files by name or full-text content in Google Drive."""
    q = f"(name contains '{query}' or fullText contains '{query}') and trashed = false"

    results = service.files().list(
        q=q,
        pageSize=min(max_results, 100),
        fields="files(id, name, mimeType, modifiedTime, webViewLink)",
        orderBy="relevance",
    ).execute()

    files = results.get("files", [])

    if not files:
        return f"No se encontraron archivos con '{query}' en Google Drive."

    lines = [f"Resultados de búsqueda para '{query}' ({len(files)} archivo(s)):"]
    for f in files:
        lines.append(f"  \U0001F4C4 {f['name']} — ID: {f['id']}")

    return "\n".join(lines)


def _move_file(service, file_id: str, destination_folder_id: str) -> str:
    """Move a file to a different folder in Google Drive."""
    file_info = service.files().get(
        fileId=file_id, fields="name, parents"
    ).execute()

    previous_parents = ",".join(file_info.get("parents", []))

    result = service.files().update(
        fileId=file_id,
        addParents=destination_folder_id,
        removeParents=previous_parents,
        fields="id, name, webViewLink",
    ).execute()

    return (
        f"Archivo movido exitosamente.\n"
        f"  Nombre: {result.get('name')}\n"
        f"  Nuevo Link: {result.get('webViewLink', 'N/A')}"
    )


def _rename_file(service, file_id: str, new_name: str) -> str:
    """Rename a file in Google Drive."""
    result = service.files().update(
        fileId=file_id,
        body={"name": new_name},
        fields="id, name, webViewLink",
    ).execute()

    return (
        f"Archivo renombrado exitosamente.\n"
        f"  Nuevo nombre: {result.get('name')}\n"
        f"  Link: {result.get('webViewLink', 'N/A')}"
    )


def _delete_file(service, file_id: str) -> str:
    """Move a file to trash in Google Drive (not permanent delete)."""
    file_info = service.files().get(
        fileId=file_id, fields="name"
    ).execute()

    service.files().update(
        fileId=file_id, body={"trashed": True}
    ).execute()

    return f"Archivo enviado a la papelera: {file_info.get('name')}"


def _download_file(service, file_id: str, destination: str = None) -> str:
    """Download a file from Google Drive to local storage."""
    file_info = service.files().get(
        fileId=file_id, fields="name, mimeType, size"
    ).execute()

    name = file_info.get("name", "archivo")
    mime = file_info.get("mimeType", "")

    dest_dir = Path(destination) if destination else _get_downloads_dir()
    if dest_dir.is_dir():
        pass
    else:
        dest_dir = dest_dir.parent
    dest_dir.mkdir(parents=True, exist_ok=True)

    if mime in _EXPORT_MIMES:
        export_mime, ext = _EXPORT_MIMES[mime]
        if not name.endswith(ext):
            name = name + ext
        request = service.files().export_media(fileId=file_id, mimeType=export_mime)
    else:
        request = service.files().get_media(fileId=file_id)

    out_path = dest_dir / name
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    with open(out_path, "wb") as f:
        f.write(fh.getvalue())

    return (
        f"Archivo descargado exitosamente.\n"
        f"  Nombre: {name}\n"
        f"  Guardado en: {out_path}"
    )


def _get_file_info(service, file_id: str) -> str:
    """Get detailed info about a file in Google Drive."""
    result = service.files().get(
        fileId=file_id,
        fields="id, name, mimeType, size, modifiedTime, createdTime, owners, webViewLink, parents",
    ).execute()

    size_str = "N/A"
    if result.get("size"):
        size_bytes = int(result["size"])
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                size_str = f"{size_bytes:.1f} {unit}"
                break
            size_bytes /= 1024

    owners = ", ".join(
        o.get("displayName", o.get("emailAddress", "?"))
        for o in result.get("owners", [])
    )

    return (
        f"Información del archivo:\n"
        f"  Nombre: {result.get('name')}\n"
        f"  ID: {result.get('id')}\n"
        f"  Tipo: {result.get('mimeType')}\n"
        f"  Tamaño: {size_str}\n"
        f"  Creado: {result.get('createdTime', 'N/A')}\n"
        f"  Modificado: {result.get('modifiedTime', 'N/A')}\n"
        f"  Propietario: {owners}\n"
        f"  Link: {result.get('webViewLink', 'N/A')}"
    )


def _update_content(service, file_id: str, content: str = None,
                    file_path: str = None) -> str:
    """Update the content of an existing file in Google Drive.
    Either replaces with text content or uploads a new version from a local file.
    """
    file_info = service.files().get(
        fileId=file_id, fields="name, mimeType"
    ).execute()

    name = file_info.get("name", "archivo")
    mime = file_info.get("mimeType", "")

    if content and mime == _GDOC_MIME:
        try:
            from googleapiclient.discovery import build as build_svc
            docs_service = build_svc("docs", "v1", credentials=service._http.credentials)

            doc = docs_service.documents().get(documentId=file_id).execute()
            body_content = doc.get("body", {}).get("content", [])
            end_index = 1
            for element in body_content:
                if "endIndex" in element:
                    end_index = element["endIndex"]

            requests_body = []
            if end_index > 2:
                requests_body.append({
                    "deleteContentRange": {
                        "range": {"startIndex": 1, "endIndex": end_index - 1}
                    }
                })
            requests_body.append({
                "insertText": {"location": {"index": 1}, "text": content}
            })

            docs_service.documents().batchUpdate(
                documentId=file_id, body={"requests": requests_body}
            ).execute()

            return (
                f"Contenido del documento actualizado.\n"
                f"  Nombre: {name}\n"
                f"  ID: {file_id}"
            )
        except Exception as e:
            return f"Error al actualizar el documento: {e}"

    if file_path:
        p = Path(file_path)
        if not p.exists():
            return f"Archivo local no encontrado: {file_path}"
        upload_mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        media = MediaFileUpload(str(p), mimetype=upload_mime, resumable=True)
        result = service.files().update(
            fileId=file_id, media_body=media, fields="id, name, webViewLink"
        ).execute()
        return (
            f"Archivo actualizado con nueva versión.\n"
            f"  Nombre: {result.get('name')}\n"
            f"  Link: {result.get('webViewLink', 'N/A')}"
        )

    if content:
        buf = io.BytesIO(content.encode("utf-8"))
        media = MediaIoBaseUpload(buf, mimetype="text/plain", resumable=True)
        result = service.files().update(
            fileId=file_id, media_body=media, fields="id, name, webViewLink"
        ).execute()
        return (
            f"Contenido del archivo actualizado.\n"
            f"  Nombre: {result.get('name')}\n"
            f"  Link: {result.get('webViewLink', 'N/A')}"
        )

    return "No se proporcionó contenido ni archivo para actualizar."


# ============================================================================
#  Main entry point (follows O.R.I.O.N action pattern)
# ============================================================================
def google_drive(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """Unified entry point for all Google Drive operations."""
    params = parameters or {}
    action = params.get("action", "").lower().strip()

    if player:
        player.write_log(f"[gdrive] {action}")

    try:
        service = _authenticate()
    except FileNotFoundError as e:
        return str(e)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Error de autenticación con Google Drive: {e}"

    try:
        if action == "upload":
            file_path = params.get("file_path", "")
            if not file_path:
                return "No se proporcionó la ruta del archivo a subir."
            return _upload_file(
                service,
                file_path=file_path,
                folder_id=params.get("folder_id"),
            )

        elif action in ("create", "crear"):
            name = params.get("name", "")
            if not name:
                return "No se proporcionó el nombre del documento."
            return _create_document(
                service,
                name=name,
                doc_type=params.get("doc_type", "document"),
                folder_id=params.get("folder_id"),
                content=params.get("content"),
            )

        elif action in ("create_folder", "crear_carpeta"):
            name = params.get("name", "")
            if not name:
                return "No se proporcionó el nombre de la carpeta."
            return _create_folder(
                service,
                name=name,
                parent_id=params.get("folder_id"),
            )

        elif action in ("list", "listar"):
            return _list_files(
                service,
                folder_id=params.get("folder_id"),
                query=params.get("query"),
                max_results=int(params.get("max_results", 20)),
            )

        elif action in ("search", "buscar"):
            query = params.get("query", "")
            if not query:
                return "No se proporcionó un término de búsqueda."
            return _search_files(
                service, query=query,
                max_results=int(params.get("max_results", 20)),
            )

        elif action in ("move", "mover"):
            file_id = params.get("file_id", "")
            dest = params.get("destination_folder_id", "")
            if not file_id:
                return "No se proporcionó el ID del archivo a mover."
            if not dest:
                return "No se proporcionó el ID de la carpeta destino."
            return _move_file(service, file_id=file_id, destination_folder_id=dest)

        elif action in ("rename", "renombrar"):
            file_id = params.get("file_id", "")
            new_name = params.get("new_name", "")
            if not file_id:
                return "No se proporcionó el ID del archivo."
            if not new_name:
                return "No se proporcionó el nuevo nombre."
            return _rename_file(service, file_id=file_id, new_name=new_name)

        elif action in ("delete", "eliminar", "trash"):
            file_id = params.get("file_id", "")
            if not file_id:
                return "No se proporcionó el ID del archivo a eliminar."
            return _delete_file(service, file_id=file_id)

        elif action in ("download", "descargar"):
            file_id = params.get("file_id", "")
            if not file_id:
                return "No se proporcionó el ID del archivo a descargar."
            return _download_file(
                service, file_id=file_id,
                destination=params.get("destination"),
            )

        elif action in ("info", "detalles"):
            file_id = params.get("file_id", "")
            if not file_id:
                return "No se proporcionó el ID del archivo."
            return _get_file_info(service, file_id=file_id)

        elif action in ("edit", "editar", "update", "actualizar"):
            file_id = params.get("file_id", "")
            if not file_id:
                return "No se proporcionó el ID del archivo a editar."
            return _update_content(
                service, file_id=file_id,
                content=params.get("content"),
                file_path=params.get("file_path"),
            )

        else:
            return (
                f"Acción desconocida: '{action}'. "
                "Acciones disponibles: upload, create, create_folder, list, search, "
                "move, rename, delete, download, info, edit."
            )

    except Exception as e:
        return f"Error en Google Drive ({action}): {e}"
