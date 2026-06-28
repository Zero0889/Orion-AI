"""
server.telegram_commands — Slash commands para el topic Comandos.

Cuando el `telegram_bridge` recibe un mensaje en el topic mapeado a
"commands", primero intenta dispatchearlo como slash command. Si no
matchea, cae al flow normal (cerebro LLM).

Comandos disponibles (read-only en esta versión):

  /status          — Resumen del sistema (usuarios, eventos hoy, último acceso)
  /usuarios        — Lista de huellas enroladas
  /pausar <slot>   — Marca un usuario como inactivo
  /activar <slot>  — Reactiva un usuario pausado
  /log [hoy]       — Últimos 10 eventos de acceso
  /help            — Lista de comandos

Auth: solo el ``chat_id`` privado configurado en ``telegram.json``
(`default_chat_id`) puede ejecutar comandos. Los demás miembros del
supergrupo reciben "no autorizado" si intentan.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from orion.adapters.iot import access_control as ac
from orion.core.logger import get_logger

log = get_logger("telegram.commands")


# ── Tipos ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CommandContext:
    """Contexto que se pasa a cada handler — todo lo que necesita para
    responder y razonar sobre la invocación."""

    sender_chat_id: int
    """El chat ID de quien mandó el mensaje (no el group chat ID)."""

    args: list[str]
    """Argumentos del comando, ya tokenizados. Para `/pausar 3` → `["3"]`."""

    raw_text: str
    """El texto completo del comando, útil para logging y replies de error."""


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """Definición de un comando registrado."""

    name: str
    """Sin la barra. Ej: `"status"` para `/status`."""

    handler: Callable[[CommandContext], str]
    """Recibe el contexto, devuelve el texto a responder (Markdown OK)."""

    description: str
    """Descripción corta usada por `/help`."""

    requires_auth: bool = True
    """Si True (default), solo el `authorized_chat_id` puede ejecutarlo."""


# ── Registry ─────────────────────────────────────────────────────────────


_REGISTRY: dict[str, CommandSpec] = {}


def register(spec: CommandSpec) -> None:
    """Registra un comando. Idempotente — re-registrar pisa el handler
    (útil en tests)."""
    _REGISTRY[spec.name.lower()] = spec


def list_commands() -> list[CommandSpec]:
    """Devuelve los comandos en orden de registro (Python 3.7+ dict
    preserva insertion order)."""
    return list(_REGISTRY.values())


def get_command(name: str) -> CommandSpec | None:
    return _REGISTRY.get(name.lower())


# ── Dispatcher ───────────────────────────────────────────────────────────


def is_command(text: str) -> bool:
    """True si el texto empieza con `/` seguido de letra. Filtra cosas
    como `/` solo o `/123`."""
    if not text or len(text) < 2:
        return False
    if text[0] != "/":
        return False
    return text[1].isalpha() or text[1] == "_"


def parse(text: str) -> tuple[str, list[str]]:
    """Parsea `"/comando arg1 arg2"` → `("comando", ["arg1", "arg2"])`.

    Limpia sufijos `@botname` que Telegram agrega cuando hay varios bots
    en el chat (ej: `/status@orion_bot` → `"status"`).
    """
    parts = text.strip().split()
    cmd = parts[0].lstrip("/").lower()
    # Telegram a veces agrega "@bot_username" después del comando.
    if "@" in cmd:
        cmd = cmd.split("@", 1)[0]
    args = parts[1:]
    return cmd, args


def dispatch(text: str, *, sender_chat_id: int, authorized_chat_id: int | str | None) -> str:
    """Punto de entrada. Devuelve el texto a responder al usuario.

    - Si el comando no existe → mensaje "comando desconocido + /help".
    - Si requiere auth y `sender_chat_id != authorized_chat_id` → "no autorizado".
    - Sino, ejecuta el handler y devuelve su respuesta.

    Nunca lanza — los errores del handler se capturan y se devuelven como
    texto para que Telegram los muestre al usuario.
    """
    cmd_name, args = parse(text)
    spec = _REGISTRY.get(cmd_name)
    if spec is None:
        return f"❓ Comando desconocido: `/{cmd_name}`\n\nUsá /help para ver los disponibles."

    if spec.requires_auth:
        try:
            auth_id = int(authorized_chat_id) if authorized_chat_id is not None else None
        except (TypeError, ValueError):
            auth_id = None
        if auth_id is None or sender_chat_id != auth_id:
            log.warning("Comando %r rechazado: sender=%s no autorizado", cmd_name, sender_chat_id)
            return "⛔ No autorizado para ejecutar comandos."

    ctx = CommandContext(sender_chat_id=sender_chat_id, args=args, raw_text=text)
    try:
        return spec.handler(ctx)
    except Exception as e:  # pragma: no cover
        log.exception("Handler de /%s crasheó", cmd_name)
        return f"💥 El comando `/{cmd_name}` falló: `{e}`"


# ── Handlers ─────────────────────────────────────────────────────────────


def _cmd_status(_ctx: CommandContext) -> str:
    users = ac.list_users()
    enrolled = len(users)
    active = sum(1 for u in users if u.active)

    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    events_today = ac.count_events(since=f"{today}T00:00:00")
    granted_today = ac.count_events(since=f"{today}T00:00:00", event_type="GRANTED")
    denied_today = ac.count_events(since=f"{today}T00:00:00", event_type="DENIED")

    last_events = ac.list_events(limit=1)
    last_str = "ninguno"
    if last_events:
        e = last_events[0]
        nombre = e.user_name or f"Huella #{e.fingerprint_id}"
        hora = e.timestamp[11:16] if len(e.timestamp) >= 16 else e.timestamp
        last_str = f"{nombre} a las {hora} ({e.event_type})"

    return (
        "🛡️ *Estado del sistema*\n"
        f"\n👥 Usuarios enrolados: *{enrolled}* ({active} activos)"
        f"\n📅 Eventos hoy: *{events_today}* "
        f"(✅ {granted_today} · ⛔ {denied_today})"
        f"\n🕒 Último: {last_str}"
    )


def _cmd_usuarios(_ctx: CommandContext) -> str:
    users = sorted(ac.list_users(), key=lambda u: u.fingerprint_id)
    if not users:
        return "👥 *Usuarios enrolados*\n\n_Ninguno todavía._"
    lines = ["👥 *Usuarios enrolados*\n"]
    for u in users:
        marker = "🟢" if u.active else "⚪"
        slot = str(u.fingerprint_id).rjust(3, "0")
        lines.append(f"{marker} `#{slot}` — {u.name}")
    return "\n".join(lines)


def _slot_from_args(ctx: CommandContext) -> int | str:
    """Valida `args[0]` como slot 0-127. Devuelve int OK o string de error."""
    if not ctx.args:
        return "⚠️ Falta el número de slot. Ej: `/pausar 3`"
    try:
        slot = int(ctx.args[0])
    except ValueError:
        return f"⚠️ `{ctx.args[0]}` no es un número de slot válido."
    if not 0 <= slot <= 127:
        return f"⚠️ Slot {slot} fuera de rango (0-127)."
    return slot


def _cmd_pausar(ctx: CommandContext) -> str:
    slot = _slot_from_args(ctx)
    if isinstance(slot, str):
        return slot
    users = [u for u in ac.list_users() if u.fingerprint_id == slot]
    if not users:
        return f"⚠️ No hay usuario enrolado en slot #{slot}."
    user = users[0]
    if not user.active:
        return f"ℹ️ {user.name} ya está pausado."
    updated = ac.update_user(user.id, active=False)
    return f"⏸️ *{updated.name}* pausado (slot #{slot}). Sus lecturas se logean como DENIED."


def _cmd_activar(ctx: CommandContext) -> str:
    slot = _slot_from_args(ctx)
    if isinstance(slot, str):
        return slot
    users = [u for u in ac.list_users() if u.fingerprint_id == slot]
    if not users:
        return f"⚠️ No hay usuario enrolado en slot #{slot}."
    user = users[0]
    if user.active:
        return f"ℹ️ {user.name} ya está activo."
    updated = ac.update_user(user.id, active=True)
    return f"▶️ *{updated.name}* activado (slot #{slot})."


def _cmd_log(ctx: CommandContext) -> str:
    # "/log" → últimos 10. "/log hoy" → solo los de hoy.
    since: str | None = None
    if ctx.args and ctx.args[0].lower() in ("hoy", "today"):
        today = datetime.now().astimezone().strftime("%Y-%m-%d")
        since = f"{today}T00:00:00"
    events = ac.list_events(limit=10, since=since)
    if not events:
        return "📋 *Registros recientes*\n\n_Sin eventos._"

    header = "📋 *Registros de hoy*" if since else "📋 *Últimos 10 eventos*"
    lines = [header, ""]
    for e in events:
        hora = e.timestamp[11:16] if len(e.timestamp) >= 16 else e.timestamp
        icon = "✅" if e.event_type == "GRANTED" else "⛔"
        nombre = e.user_name or f"Huella #{e.fingerprint_id}"
        lines.append(f"{icon} `{hora}` — {nombre}")
    return "\n".join(lines)


def _cmd_help(_ctx: CommandContext) -> str:
    lines = ["🤖 *Comandos disponibles*\n"]
    for spec in list_commands():
        lines.append(f"`/{spec.name}` — {spec.description}")
    return "\n".join(lines)


# ── Registración (orden importa para `/help`) ────────────────────────────


def register_builtin_commands() -> None:
    """Idempotente — se llama desde el bridge al primer arranque. Re-llamar
    pisa el registry (útil en tests)."""
    _REGISTRY.clear()
    register(
        CommandSpec(
            name="status",
            handler=_cmd_status,
            description="Resumen del sistema (usuarios, eventos hoy, último acceso).",
        )
    )
    register(
        CommandSpec(
            name="usuarios",
            handler=_cmd_usuarios,
            description="Lista de huellas enroladas.",
        )
    )
    register(
        CommandSpec(
            name="pausar",
            handler=_cmd_pausar,
            description="Pausa un slot. Ej: `/pausar 3`",
        )
    )
    register(
        CommandSpec(
            name="activar",
            handler=_cmd_activar,
            description="Reactiva un slot pausado. Ej: `/activar 3`",
        )
    )
    register(
        CommandSpec(
            name="log",
            handler=_cmd_log,
            description="Últimos 10 eventos. `/log hoy` filtra al día actual.",
        )
    )
    register(
        CommandSpec(
            name="help",
            handler=_cmd_help,
            description="Esta ayuda.",
            requires_auth=False,
        )
    )


# Auto-registración al import — para que el bridge no tenga que llamarla.
register_builtin_commands()
