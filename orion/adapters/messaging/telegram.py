"""
adapters.messaging.telegram — Cliente HTTP + tool para Telegram Bot API.

API oficial: https://core.telegram.org/bots/api

Métodos usados:
  - sendMessage   → mandar texto a un chat.
  - getUpdates    → long-polling de mensajes entrantes (lo usa el bridge).
  - getMe         → ping para validar token + obtener el username del bot.

Sin deps externas: solo ``urllib`` stdlib, igual que los providers LLM.
El cliente es **stateless** (no guarda offsets) para que el bridge pueda
elegir su propia estrategia de persistencia.
"""

from __future__ import annotations

import contextlib
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from orion.config import CONFIG_DIR
from orion.core.logger import get_logger
from orion.core.tool_registry import tool

log = get_logger("telegram")

API_BASE = "https://api.telegram.org"
DEFAULT_TIMEOUT_S = 30
LONG_POLL_TIMEOUT_S = 25  # el server tiene que aguantar al menos esto + 5

TELEGRAM_CONFIG_PATH = CONFIG_DIR / "telegram.json"


# ── Tipos ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TelegramUpdate:
    """Un update recibido por getUpdates. Sólo modelamos los campos que
    nos interesan — el rest del payload de Telegram se ignora."""

    update_id: int
    chat_id: int | None
    """ID del chat donde llegó el mensaje. En un chat privado coincide con
    ``from_user_id``; en grupos/supergrupos es el ID del grupo (negativo)."""

    text: str | None
    from_username: str | None
    from_first_name: str | None
    from_user_id: int | None = None
    """ID personal del usuario que mandó el mensaje. SIEMPRE distinto al
    chat_id en grupos. Usar este para auth de comandos (el del user real)."""

    message_thread_id: int | None = None
    """Presente cuando el mensaje vino de un topic de un supergrupo con
    forum-topics. None para chats privados o el general del grupo."""


# ── Cliente HTTP ────────────────────────────────────────────────────────


class TelegramClient:
    """Cliente HTTP para la Bot API. Una instancia por bot token."""

    def __init__(self, token: str):
        self.token = (token or "").strip()
        if not self.token:
            raise ValueError("Telegram token vacío")

    def _url(self, method: str) -> str:
        return f"{API_BASE}/bot{self.token}/{method}"

    def get_me(self) -> dict:
        """Devuelve info del bot (username, id, name). Sirve como ping
        para validar el token al guardarlo."""
        return self._get("getMe")

    def send_message(
        self,
        chat_id: int | str,
        text: str,
        *,
        parse_mode: str | None = "Markdown",
        message_thread_id: int | None = None,
    ) -> dict:
        """Manda un mensaje. ``parse_mode`` por default Markdown para que
        los **negrita** y ``code`` que generan los LLMs se rendericen bien.

        ``message_thread_id`` enruta el mensaje a un *topic* específico
        dentro de un supergrupo con forum-topics habilitado. Si es ``None``,
        el mensaje cae en el general del grupo o el chat privado.

        Si el texto es muy largo (>4096 chars, límite de Telegram) lo
        partimos en bloques.
        """
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "texto vacío"}

        def _build_payload(body: str) -> dict:
            p: dict = {"chat_id": chat_id, "text": body}
            if parse_mode:
                p["parse_mode"] = parse_mode
            if message_thread_id is not None:
                p["message_thread_id"] = message_thread_id
            return p

        # Telegram aborta con 400 si supera 4096 chars.
        MAX = 4000
        if len(text) <= MAX:
            return self._post("sendMessage", _build_payload(text))

        # Multi-parte. Mandamos cada bloque por separado.
        last_resp: dict = {}
        for i in range(0, len(text), MAX):
            block = text[i : i + MAX]
            try:
                last_resp = self._post("sendMessage", _build_payload(block))
            except Exception as e:
                log.warning("send_message bloque falló: %s", e)
                return {"ok": False, "error": str(e)}
        return last_resp

    def get_updates(
        self,
        offset: int = 0,
        *,
        timeout_s: int = LONG_POLL_TIMEOUT_S,
        allowed_updates: list[str] | None = None,
    ) -> list[TelegramUpdate]:
        """Long-polling de mensajes nuevos. Devuelve lista vacía si timeout.

        ``offset = last_update_id + 1`` — todo update con id < offset queda
        confirmado y Telegram lo borra de su cola. Por eso es importante
        avanzar el offset SOLO cuando ya procesamos el mensaje.
        """
        params: dict = {"timeout": timeout_s}
        if offset > 0:
            params["offset"] = offset
        if allowed_updates:
            params["allowed_updates"] = json.dumps(allowed_updates)
        # http timeout debe ser > timeout_s para que el long-poll cierre
        # solo cuando el server lo decide, no cuando urllib se aburre.
        data = self._get("getUpdates", params=params, timeout_s=timeout_s + 5)
        if not data.get("ok"):
            log.warning("getUpdates devolvió ok=false: %s", str(data)[:200])
            return []
        updates: list[TelegramUpdate] = []
        for raw in data.get("result", []) or []:
            if not isinstance(raw, dict):
                continue
            msg = raw.get("message") or raw.get("edited_message") or {}
            chat = msg.get("chat") or {}
            sender = msg.get("from") or {}
            updates.append(
                TelegramUpdate(
                    update_id=int(raw.get("update_id", 0)),
                    chat_id=chat.get("id"),
                    text=msg.get("text"),
                    from_username=sender.get("username"),
                    from_first_name=sender.get("first_name"),
                    from_user_id=sender.get("id"),
                    message_thread_id=msg.get("message_thread_id"),
                )
            )
        return updates

    # ── HTTP plumbing ────────────────────────────────────────────────────

    def _get(
        self,
        method: str,
        *,
        params: dict | None = None,
        timeout_s: int = DEFAULT_TIMEOUT_S,
    ) -> dict:
        url = self._url(method)
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = ""
            with contextlib.suppress(Exception):
                detail = e.read().decode("utf-8")[:300]
            raise RuntimeError(f"Telegram GET {method} HTTP {e.code}: {detail or e.reason}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Telegram GET {method} red: {e.reason}") from e

    def _post(self, method: str, payload: dict, *, timeout_s: int = DEFAULT_TIMEOUT_S) -> dict:
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(self._url(method), data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = ""
            with contextlib.suppress(Exception):
                detail = e.read().decode("utf-8")[:300]
            raise RuntimeError(f"Telegram POST {method} HTTP {e.code}: {detail or e.reason}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Telegram POST {method} red: {e.reason}") from e


# ── Config persistido ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TelegramGroupConfig:
    """Subconfig para un supergrupo con forum-topics habilitado.

    ``chat_id`` es el ID del supergrupo (negativo, ``-100…``). ``topics``
    mapea nombres lógicos → ``message_thread_id`` del tema. Nombres usados
    por el resto del backend:

      * ``access``   → notifs del ESP32 de huella
      * ``status``   → resúmenes diarios + alertas IoT (futuro)
      * ``commands`` → input del usuario para slash commands (futuro)
      * ``chat``     → bridge LLM ↔ Telegram (futuro)

    Si un nombre no está en ``topics``, el caller debe decidir el fallback
    (típicamente: mandar al ``default_chat_id``).
    """

    chat_id: str
    topics: dict[str, int]


@dataclass(frozen=True, slots=True)
class TelegramConfig:
    bot_token: str
    default_chat_id: str
    forward_notifications: bool
    enabled: bool
    group: TelegramGroupConfig | None = None
    daily_summary_hour: int = 21
    """Hora (0-23, local timezone) a la que el scheduler postea el resumen
    diario al topic ``status``. Solo se evalúa si el group tiene topic
    ``status`` mapeado."""

    @property
    def is_configured(self) -> bool:
        # "Configurado" = token + algún destino. El supergrupo solo
        # cuenta como destino si tiene chat_id no vacío.
        has_dest = bool(self.default_chat_id) or bool(self.group and self.group.chat_id)
        return bool(self.bot_token and has_dest)

    def resolve_topic(self, name: str) -> tuple[str, int | None] | None:
        """Devuelve (chat_id, message_thread_id) si hay un topic configurado
        bajo ese ``name`` dentro del supergrupo. ``None`` si no hay grupo
        o si el topic no está mapeado — el caller decide si hace fallback
        a ``default_chat_id``."""
        g = self.group
        if g and g.chat_id and name in g.topics:
            return g.chat_id, int(g.topics[name])
        return None


_EMPTY_CONFIG = TelegramConfig(
    bot_token="",
    default_chat_id="",
    forward_notifications=True,
    enabled=False,
    group=None,
)


def _parse_group(raw: dict | None) -> TelegramGroupConfig | None:
    """Acepta tanto el formato moderno ``{"chat_id": "...", "topics": {...}}``
    como ``None`` / ``{}`` (= sin grupo). Si el chat_id falta, devolvemos
    None — el grupo no es usable sin él."""
    if not isinstance(raw, dict):
        return None
    chat_id = str(raw.get("chat_id", "")).strip()
    if not chat_id:
        return None
    topics_raw = raw.get("topics") or {}
    topics: dict[str, int] = {}
    if isinstance(topics_raw, dict):
        for k, v in topics_raw.items():
            try:
                topics[str(k)] = int(v)
            except (TypeError, ValueError):
                log.warning("Topic %r tiene message_thread_id inválido: %r", k, v)
    return TelegramGroupConfig(chat_id=chat_id, topics=topics)


def load_telegram_config() -> TelegramConfig:
    """Lee config/telegram.json. Devuelve config vacía si no existe."""
    try:
        raw = json.loads(TELEGRAM_CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return _EMPTY_CONFIG
    summary_hour_raw = raw.get("daily_summary_hour", 21)
    try:
        summary_hour = max(0, min(23, int(summary_hour_raw)))
    except (TypeError, ValueError):
        summary_hour = 21
    return TelegramConfig(
        bot_token=str(raw.get("bot_token", "")).strip(),
        default_chat_id=str(raw.get("default_chat_id", "")).strip(),
        forward_notifications=bool(raw.get("forward_notifications", True)),
        enabled=bool(raw.get("enabled", False)),
        group=_parse_group(raw.get("group")),
        daily_summary_hour=summary_hour,
    )


def save_telegram_config(cfg: TelegramConfig) -> None:
    TELEGRAM_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {
        "bot_token": cfg.bot_token,
        "default_chat_id": cfg.default_chat_id,
        "forward_notifications": cfg.forward_notifications,
        "enabled": cfg.enabled,
        "daily_summary_hour": cfg.daily_summary_hour,
    }
    if cfg.group is not None:
        payload["group"] = {
            "chat_id": cfg.group.chat_id,
            "topics": dict(cfg.group.topics),
        }
    TELEGRAM_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    TELEGRAM_CONFIG_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ── Tool: send_telegram ──────────────────────────────────────────────────


@tool(
    name="send_telegram",
    description=(
        "Manda un mensaje a Telegram al chat por defecto configurado por el "
        "usuario. Útil para notificar al usuario cuando no está delante de la "
        "PC. Si Telegram no está configurado, devuelve un error claro y NO "
        "intenta otros canales."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "message": {
                "type": "STRING",
                "description": "Texto a enviar. Soporta Markdown básico de Telegram.",
            },
        },
        "required": ["message"],
    },
    fallback="No pude mandar el mensaje por Telegram.",
)
def send_telegram(message: str) -> str:
    """Tool que Orion puede invocar para mandarle un mensaje al usuario por
    Telegram. Lee la config en cada llamada — así si el usuario la actualizó
    en caliente vía Settings, el siguiente call usa los valores nuevos.
    """
    cfg = load_telegram_config()
    if not cfg.is_configured:
        return (
            "Telegram no está configurado. Pedile al usuario que pegue su bot "
            "token y chat_id en Ajustes → Mensajería → Telegram."
        )
    try:
        client = TelegramClient(cfg.bot_token)
        resp = client.send_message(cfg.default_chat_id, message)
    except Exception as e:
        log.warning("send_telegram falló: %s", e)
        return f"No pude mandar el mensaje por Telegram: {e}"
    if not resp.get("ok"):
        return f"Telegram rechazó el mensaje: {resp.get('description') or resp}"
    return "Mensaje enviado por Telegram."
