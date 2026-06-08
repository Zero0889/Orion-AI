"""Gmail adapter — envuelve ``gog gmail search`` para listar no-leídos.

Detalles del CLI ``gog`` (v0.22.0) que importan para no romper acá:

* La flag JSON es ``-j`` y es **global** — debe ir ANTES del subcomando
  (``gog -j gmail search ...``), no al final. Si la ponés al final, gog
  la interpreta como query arg y devuelve texto.
* La estructura del JSON tiene clave ``threads`` (no ``messages``), y
  cada item trae ``id``, ``date`` ("YYYY-MM-DD HH:MM"), ``from``,
  ``subject``, ``labels``, ``messageCount``. Sin ``snippet`` por defecto.
* En Windows el output puede incluir bytes no-cp1252 (emojis en
  subjects). Hay que forzar ``encoding="utf-8"`` con ``errors="replace"``
  o el reader thread del subprocess explota y deja ``stdout=None``.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime

from .base import NotificationAdapter, NotificationItem


class GmailAdapter(NotificationAdapter):
    @property
    def source(self) -> str:
        return "gmail"

    def is_configured(self) -> bool:
        from core.cli_installer import cli_path
        return cli_path("gog") is not None

    def fetch(self, *, max_items: int = 20) -> list[NotificationItem]:
        from core.cli_installer import cli_path, extra_path_dirs

        gog = cli_path("gog")
        if gog is None:
            raise RuntimeError("Binario `gog` no instalado. Andá a Skills → gog.")

        env = os.environ.copy()
        extras = extra_path_dirs()
        if extras:
            env["PATH"] = os.pathsep.join(extras + [env.get("PATH", "")])

        # -j VA ANTES del subcomando porque es global flag de gog.
        cmd = [gog, "-j", "gmail", "search", "is:unread", "--max", str(max_items)]
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                env=env,
                timeout=30,
                # Encoding explícito: emojis en subjects revientan cp1252.
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as e:
            raise RuntimeError(f"No pude ejecutar `gog`: {e}") from e
        except subprocess.TimeoutExpired:
            raise RuntimeError("`gog gmail search` superó el timeout (30s).")

        stdout = r.stdout or ""
        stderr = r.stderr or ""

        if r.returncode != 0:
            # Auth no hecho, sin red, scope falta — todo cae acá.
            err = (stderr or stdout).strip()
            raise RuntimeError(f"`gog gmail search` falló: {err[:300]}")

        out = stdout.strip()
        if not out:
            return []

        try:
            data = json.loads(out)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"gog devolvió output no-JSON. Primeros 200 chars: {out[:200]!r}"
            ) from e

        # gog v0.22 devuelve {nextPageToken, threads:[...]}.
        threads = data.get("threads") if isinstance(data, dict) else data
        if not isinstance(threads, list):
            return []

        items: list[NotificationItem] = []
        for t in threads[:max_items]:
            if not isinstance(t, dict):
                continue
            mid     = str(t.get("id") or "").strip()
            if not mid:
                continue
            subject = (t.get("subject") or "(sin asunto)").strip()
            sender  = (t.get("from") or "").strip()
            ts      = _parse_gog_date(t.get("date"))
            items.append(NotificationItem(
                uid         = f"gmail:{mid}",
                source      = "gmail",
                title       = f"✉️ {sender}: {subject}" if sender else f"✉️ {subject}",
                summary     = "",   # gog -j no trae snippet en search
                url         = f"https://mail.google.com/mail/u/0/#inbox/{mid}",
                received_ts = ts,
                metadata    = {
                    "thread_id":     mid,
                    "labels":        list(t.get("labels") or []),
                    "message_count": int(t.get("messageCount") or 1),
                },
            ))
        return items


def _parse_gog_date(s: str | None) -> float:
    """gog devuelve fechas tipo '2026-06-07 09:28'. Si falla, usamos ahora."""
    if not s:
        import time as _time
        return _time.time()
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M").timestamp()
    except (ValueError, TypeError):
        import time as _time
        return _time.time()
