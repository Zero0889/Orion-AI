"""Classroom adapter — Google Classroom API nativo.

Por qué no `gog`
----------------
gog NO soporta Classroom. Necesitamos hablar la API directamente con
``google-api-python-client``. Reusamos el ``client_secret.json`` que el
usuario ya tiene del setup de gog, pero **el token OAuth es separado** —
gog y nosotros pedimos scopes distintos y Google los entrega aparte.

Localización de credenciales
----------------------------
Se busca el client_secret en este orden:
1. ``$ORION_GOOGLE_CLIENT_SECRET`` (env var, si la setearon)
2. ``tools/classroom/client_secret.json``
3. ``tools/gog/client_secret.json``  (el del setup de gog, si lo dejaron ahí)
4. ``%USERPROFILE%\\Documents\\gog\\client_secret.json``

El token de Classroom siempre se persiste en
``tools/classroom/token.json``. La primera vez que se usa
:meth:`ClassroomAdapter.fetch` abre el navegador para que el usuario
autorice los scopes de Classroom (separados de los de gog).

Scopes
------
* ``classroom.courses.readonly``           — listar cursos.
* ``classroom.coursework.me.readonly``     — tareas asignadas a mí (alumno).
* ``classroom.announcements.readonly``     — avisos en el feed del curso.

Estado del adapter
------------------
* ``is_configured`` = hay client_secret en disco. Si no lo hay, devolvemos
  ``False`` y el panel le pide al usuario que lo ponga; NO crasheamos.
* ``fetch`` lista las últimas N coursework + announcement de TODOS los
  cursos activos en orden cronológico desc.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from orion.config import BASE_DIR, CONFIG_DIR
from orion.core.logger import get_logger

from .base import NotificationAdapter, NotificationItem
import contextlib

log = get_logger("classroom")


# Google a veces devuelve scopes ligeramente distintos a los pedidos
# (student-submissions vs coursework). Si esto se setea solo dentro de
# authorize_interactive(), el refresh automático del poller que corre en
# segundo plano puede crashear al chocar con el mismatch. Lo dejamos a
# nivel de módulo con setdefault para no pisar config explícita del user.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


_TOKEN_PATH = BASE_DIR / "tools" / "classroom" / "token.json"
_CLIENT_SECRET_NAME = "client_secret.json"

_SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly",
    "https://www.googleapis.com/auth/classroom.announcements.readonly",
]


# ── Localización de credenciales ─────────────────────────────────────────


def _find_client_secret() -> Path | None:
    candidates = []
    env = os.environ.get("ORION_GOOGLE_CLIENT_SECRET")
    if env:
        candidates.append(Path(env))
    candidates.append(BASE_DIR / "tools" / "classroom" / _CLIENT_SECRET_NAME)
    candidates.append(BASE_DIR / "tools" / "gog" / _CLIENT_SECRET_NAME)
    home = Path.home()
    candidates.append(home / "Documents" / "gog" / _CLIENT_SECRET_NAME)
    for c in candidates:
        if c.exists():
            return c
    return None


# ── Auth ─────────────────────────────────────────────────────────────────


# Patrones de error de Google que indican REVOCACIÓN REAL del token. Solo en
# estos casos el token está muerto irrecuperablemente y conviene borrarlo
# para que el usuario re-autorice. Cualquier otro error (red, 5xx, scopes,
# parse glitch) es transient → NO borrar.
_REVOKED_PATTERNS = (
    "invalid_grant",
    "token has been expired or revoked",
    "token has been revoked",
    "token was revoked",
    "consent_required",
    "user_required",
    "account_deleted",
    "account_disabled",
)


def _is_revocation_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(p in msg for p in _REVOKED_PATTERNS)


def _atomic_write_token(creds) -> None:
    """Escritura atómica del token a disco. Si algo falla a mitad, el
    archivo original queda intacto en lugar de quedar corrupto."""
    payload = creds.to_json()
    tmp = _TOKEN_PATH.with_suffix(".tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(str(tmp), str(_TOKEN_PATH))
    except OSError as e:
        log.warning("No pude persistir token refrescado: %s", e)
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)


def _load_creds():
    """Devuelve credentials válidas o None si hay que pedir auth interactiva.

    Política de persistencia del token (revisada — antes era demasiado
    agresiva, borraba el token al menor blip y el usuario tenía que
    re-autorizar en cada arranque):

      • Si el archivo está corrupto al parsear → NO borrar. Logueamos y
        devolvemos None. Si realmente está muerto, el próximo intento
        fallará igual y el usuario re-autorizará una vez.
      • Si el refresh falla por error de **red** o 5xx → NO borrar.
        Un blip de internet no debe forzar re-auth.
      • Si Google devuelve EXPLÍCITAMENTE 'invalid_grant' / 'revoked' →
        el token está muerto de verdad. Lo borramos.
      • Si Google no devuelve un nuevo refresh_token en el response,
        preservamos el original (Google solo lo devuelve la primera vez).
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as e:
        raise RuntimeError(
            "Falta google-auth. Reinstalá deps: pip install -r requirements.txt"
        ) from e

    if not _TOKEN_PATH.exists():
        return None
    try:
        # Don't enforce scopes here — Google may return slightly different
        # scopes than requested (e.g. student-submissions vs coursework).
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH))
    except (ValueError, OSError, json.JSONDecodeError) as e:
        # NO borrar: el parse puede fallar por una escritura concurrente o
        # un glitch del FS. Si pasa N veces, ya se verá; mientras tanto
        # preferimos preservar el token y devolver None esta vez.
        log.warning("token parse falló (NO borro): %s", e)
        return None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        original_refresh = creds.refresh_token
        try:
            creds.refresh(Request())
        except Exception as e:
            if _is_revocation_error(e):
                log.warning("token revocado por Google, lo borro: %s", e)
                with contextlib.suppress(OSError):
                    _TOKEN_PATH.unlink(missing_ok=True)
                return None
            # Cualquier otro error: red, 5xx, scope mismatch transient, etc.
            # Conservamos el token y devolvemos None — el próximo poll lo
            # reintenta sin obligar al usuario a re-autorizar.
            log.warning("refresh transient falló (NO borro token): %s", e)
            return None

        # Google a veces NO devuelve refresh_token en el response del
        # refresh — solo en la primera autorización. Si pasa, preservamos
        # el original explícitamente para que la próxima vez podamos
        # refrescar de nuevo.
        if not creds.refresh_token and original_refresh:
            with contextlib.suppress(Exception):
                creds._refresh_token = original_refresh
        _atomic_write_token(creds)
        return creds

    # Token expirado y sin refresh_token → muerto irrecuperablemente. Esto
    # solo pasa si el OAuth inicial NO pidió access_type=offline + prompt=consent
    # (lo arreglamos en authorize_interactive más abajo). Borramos el token
    # para que el banner aparezca y el usuario re-autorice UNA vez bien.
    if creds and creds.expired and not creds.refresh_token:
        log.warning("token sin refresh_token — re-auth requerida (era OAuth viejo)")
        with contextlib.suppress(OSError):
            _TOKEN_PATH.unlink(missing_ok=True)
    return None


def authorize_interactive() -> str:
    """Abre el navegador para el OAuth dance. Llamada explícita desde el
    endpoint REST; NO se invoca en ``fetch`` para no abrir Chrome en medio
    de un poll automático. Devuelve el path al token guardado.

    CRÍTICO: pasamos ``access_type='offline'`` y ``prompt='consent'`` al
    authorization URL. Sin esto, Google puede devolver SOLO un access_token
    válido 1h (caso típico: usuario ya había autorizado la app antes y
    Google omite el refresh_token). Con prompt=consent forzamos pantalla
    de consentimiento → Google siempre incluye refresh_token. Esta era
    la causa raíz del "Classroom me pide autorizar en cada arranque".
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    # OAUTHLIB_RELAX_TOKEN_SCOPE ya se setea a nivel de módulo (arriba).

    cs = _find_client_secret()
    if cs is None:
        raise RuntimeError(
            "No encontré client_secret.json. Copialo a "
            "tools/classroom/client_secret.json o usá el del setup de gog."
        )
    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(cs), _SCOPES)
    creds = flow.run_local_server(
        port=0,
        open_browser=True,
        # kwargs que se inyectan en el authorization URL de Google.
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    if not creds.refresh_token:
        # Defensa en profundidad: si por alguna razón Google sigue sin
        # darnos refresh_token, avisamos en el log. El token aún se guarda
        # (será válido 1h), pero el usuario notará si esto pasa repetido.
        log.warning(
            "OAuth completó sin refresh_token — el token caducará en 1h. "
            "Verifica que tu app esté publicada (no 'Testing') en Google Cloud."
        )
    _atomic_write_token(creds)
    return str(_TOKEN_PATH)


# ── URL rewrite (inyectar /u/N/) ─────────────────────────────────────────


def _get_user_index() -> int | None:
    """Lee user_index del config de notificaciones (classroom.user_index)."""
    cfg_path = CONFIG_DIR / "notifications.json"
    if not cfg_path.exists():
        return None
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        return data.get("sources", {}).get("classroom", {}).get("user_index")
    except Exception:
        return None


def _rewrite_url(url: str | None, user_index: int | None) -> str | None:
    """Reescribe classroom.google.com/c/… → classroom.google.com/u/N/c/…"""
    if not url or user_index is None:
        return url
    # Already has /u/N/ → replace it
    import re

    if re.search(r"/u/\d+/", url):
        return re.sub(r"/u/\d+/", f"/u/{user_index}/", url)
    # Insert /u/N/ after the domain
    return url.replace(
        "classroom.google.com/",
        f"classroom.google.com/u/{user_index}/",
        1,
    )


# ── Adapter ──────────────────────────────────────────────────────────────


class ClassroomAdapter(NotificationAdapter):
    @property
    def source(self) -> str:
        return "classroom"

    def is_configured(self) -> bool:
        # Configurado = hay client_secret Y hay token guardado.
        return _find_client_secret() is not None and _TOKEN_PATH.exists()

    def fetch(self, *, max_items: int = 20) -> list[NotificationItem]:
        creds = _load_creds()
        if creds is None:
            raise RuntimeError(
                "Classroom sin token. Autorizá una vez desde el panel de "
                "Notificaciones → 'Autorizar Classroom'."
            )

        try:
            from googleapiclient.discovery import build
        except ImportError as e:
            raise RuntimeError("Falta google-api-python-client. Reinstalá deps.") from e

        service = build("classroom", "v1", credentials=creds, cache_discovery=False)
        user_idx = _get_user_index()

        # 1) Cursos activos.
        try:
            courses_resp = (
                service.courses()
                .list(
                    courseStates=["ACTIVE"],
                    pageSize=30,
                )
                .execute()
            )
        except Exception as e:
            raise RuntimeError(f"Classroom API courses.list: {e}") from e

        courses = courses_resp.get("courses", []) or []
        if not courses:
            return []

        # 2) Por cada curso: últimas N coursework + announcement.
        items: list[NotificationItem] = []
        per_course = max(2, max_items // max(len(courses), 1))
        for course in courses:
            cid = course["id"]
            cname = course.get("name") or f"Curso {cid}"
            alt = course.get("alternateLink")

            # Coursework (tareas).
            try:
                cw_resp = (
                    service.courses()
                    .courseWork()
                    .list(
                        courseId=cid,
                        pageSize=per_course,
                        orderBy="updateTime desc",
                    )
                    .execute()
                )
            except Exception as e:
                log.warning("%s: courseWork falló: %s", cname, e)
                cw_resp = {}
            for cw in cw_resp.get("courseWork") or []:
                title = cw.get("title", "Tarea")
                due = cw.get("dueDate")
                due_str = _format_due(due, cw.get("dueTime"))
                summary = f"{cname}" + (f" · entrega {due_str}" if due_str else "")
                items.append(
                    NotificationItem(
                        uid=f"classroom:{cid}:cw:{cw['id']}",
                        source="classroom",
                        title=f"📚 {title}",
                        summary=summary,
                        url=_rewrite_url(cw.get("alternateLink") or alt, user_idx),
                        received_ts=_ts_from_iso(cw.get("updateTime")) or time.time(),
                        metadata={
                            "course_id": cid,
                            "kind": "coursework",
                            "work_type": cw.get("workType"),
                        },
                    )
                )

            # Announcements (avisos).
            try:
                an_resp = (
                    service.courses()
                    .announcements()
                    .list(
                        courseId=cid,
                        pageSize=per_course,
                        orderBy="updateTime desc",
                    )
                    .execute()
                )
            except Exception as e:
                log.warning("%s: announcements falló: %s", cname, e)
                an_resp = {}
            for an in an_resp.get("announcements") or []:
                text = (an.get("text") or "").strip().replace("\n", " ")
                if len(text) > 120:
                    text = text[:117] + "…"
                items.append(
                    NotificationItem(
                        uid=f"classroom:{cid}:an:{an['id']}",
                        source="classroom",
                        title=f"📢 {cname}",
                        summary=text or "(sin texto)",
                        url=_rewrite_url(an.get("alternateLink") or alt, user_idx),
                        received_ts=_ts_from_iso(an.get("updateTime")) or time.time(),
                        metadata={"course_id": cid, "kind": "announcement"},
                    )
                )

        items.sort(key=lambda x: x.received_ts, reverse=True)
        return items[:max_items]


# ── Helpers ──────────────────────────────────────────────────────────────


def _format_due(date: dict | None, time_obj: dict | None) -> str:
    if not date:
        return ""
    try:
        y = int(date.get("year", 0))
        m = int(date.get("month", 0))
        d = int(date.get("day", 0))
        if not (y and m and d):
            return ""
        s = f"{d:02}/{m:02}/{y}"
        if time_obj:
            h = int(time_obj.get("hours", 0))
            mn = int(time_obj.get("minutes", 0))
            s += f" {h:02}:{mn:02}"
        return s
    except (TypeError, ValueError):
        return ""


def _ts_from_iso(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        # Google devuelve ISO 8601 con sufijo "Z".
        from datetime import datetime

        if iso.endswith("Z"):
            iso = iso[:-1] + "+00:00"
        return datetime.fromisoformat(iso).timestamp()
    except (TypeError, ValueError):
        return None
