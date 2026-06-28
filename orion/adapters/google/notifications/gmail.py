"""Gmail adapter — usa google-auth + googleapiclient directamente.

Histórico: antes envolvía ``gog gmail search`` (CLI), pero en algunas
instalaciones el subprocess hereda env vars de forma inconsistente y gog
no puede leer el refresh token del keyring file-backend. Reescribimos
para usar la API de Google directamente (mismo patrón que classroom.py).

Requiere ``tools/gmail/token.json`` en formato de google-auth (refresh
token + client_id + client_secret + token_uri + scopes). Si falta, el
adapter reporta ``is_configured = False`` y el poller lo skipea.
"""

from __future__ import annotations

import contextlib
import json
import time
from datetime import datetime

from orion.config import BASE_DIR
from orion.core.logger import get_logger

from .base import NotificationAdapter, NotificationItem

log = get_logger("gmail")

_TOKEN_PATH = BASE_DIR / "tools" / "gmail" / "token.json"


def _is_revocation_error(exc: BaseException) -> bool:
    """Distingue tokens muertos vs glitches transitorios. Solo borramos en
    revocación explícita (idem patrón de classroom.py)."""
    msg = str(exc).lower()
    return any(s in msg for s in ("invalid_grant", "revoked", "deleted_client"))


def _load_creds():
    """Carga credentials del token.json; refresca si expiró. Devuelve None
    si no hay token o si el refresh falla transient."""
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
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH))
    except (ValueError, OSError, json.JSONDecodeError) as e:
        log.warning("Gmail token parse falló (NO borro): %s", e)
        return None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            if _is_revocation_error(e):
                log.warning("Gmail token revocado, lo borro: %s", e)
                with contextlib.suppress(OSError):
                    _TOKEN_PATH.unlink(missing_ok=True)
                return None
            log.warning("Gmail refresh transient falló (NO borro): %s", e)
            return None

        # Persistir el creds actualizado (incluye nuevo access_token)
        try:
            tmp = _TOKEN_PATH.with_suffix(".tmp")
            tmp.write_text(creds.to_json(), encoding="utf-8")
            tmp.replace(_TOKEN_PATH)
        except OSError as e:
            log.warning("No pude persistir token.json refrescado: %s", e)
        return creds

    return None


class GmailAdapter(NotificationAdapter):
    @property
    def source(self) -> str:
        return "gmail"

    def is_configured(self) -> bool:
        return _TOKEN_PATH.exists()

    def fetch(self, *, max_items: int = 20) -> list[NotificationItem]:
        creds = _load_creds()
        if creds is None:
            raise RuntimeError(
                "Gmail sin token. Re-autorizá la cuenta desde el panel de Notificaciones."
            )

        try:
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError
        except ImportError as e:
            raise RuntimeError("Falta googleapiclient. pip install google-api-python-client") from e

        try:
            svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
            res = (
                svc.users()
                .threads()
                .list(userId="me", q="is:unread", maxResults=max_items)
                .execute()
            )
        except HttpError as e:
            raise RuntimeError(f"Gmail API falló: {e}") from e

        threads = res.get("threads", []) or []
        items: list[NotificationItem] = []

        for t in threads[:max_items]:
            tid = str(t.get("id") or "").strip()
            if not tid:
                continue
            # Pedir metadata del primer mensaje (subject, from, internalDate)
            try:
                msg = (
                    svc.users()
                    .threads()
                    .get(
                        userId="me",
                        id=tid,
                        format="metadata",
                        metadataHeaders=["From", "Subject", "Date"],
                    )
                    .execute()
                )
            except HttpError as e:
                log.warning("Gmail thread %s falló: %s", tid, e)
                continue

            messages = msg.get("messages", []) or []
            if not messages:
                continue
            first = messages[0]
            headers = {h["name"]: h["value"] for h in first.get("payload", {}).get("headers", [])}
            sender = headers.get("From", "").strip()
            subject = (headers.get("Subject") or "(sin asunto)").strip()
            # internalDate es ms desde epoch
            internal = first.get("internalDate")
            try:
                ts = float(internal) / 1000.0 if internal else time.time()
            except (TypeError, ValueError):
                ts = time.time()
            # snippet del último mensaje del thread (más nuevo)
            snippet = (msg.get("snippet") or "").strip()

            items.append(
                NotificationItem(
                    uid=f"gmail:{tid}",
                    source="gmail",
                    title=f"✉️ {sender}: {subject}" if sender else f"✉️ {subject}",
                    summary=snippet[:200],
                    url=f"https://mail.google.com/mail/u/0/#inbox/{tid}",
                    received_ts=ts,
                    metadata={
                        "thread_id": tid,
                        "labels": list(first.get("labelIds") or []),
                        "message_count": len(messages),
                    },
                )
            )
        return items


def _parse_gog_date(s: str | None) -> float:
    """Helper legacy — sigue exportado por si algún test viejo lo importa."""
    if not s:
        return time.time()
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M").timestamp()
    except (ValueError, TypeError):
        return time.time()
