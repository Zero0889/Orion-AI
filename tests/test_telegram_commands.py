"""
Tests del sistema de slash commands de Telegram (Fase 2 supergrupo).

Cubren:
  - Parseo (incluyendo `/cmd@bot`).
  - is_command (filtro inicial).
  - Auth (sender == authorized vs no autorizado).
  - Cada comando individual con DB SQLite tmp (acceso a access_control).
  - Dispatcher de comandos desconocidos.
  - Wire en TelegramBridge: _should_dispatch_command para chats privados
    + topic Comandos + bypass al brain cuando matchea.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orion.adapters.iot import access_control as ac
from orion.adapters.messaging.telegram import TelegramConfig, TelegramGroupConfig
from orion.server import telegram_commands as tc


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_commands_registry():
    """Cada test arranca con el registry fresco."""
    tc.register_builtin_commands()
    yield
    tc.register_builtin_commands()


@pytest.fixture
def authed_chat_id() -> int:
    return 8341210361


# ── Parseo y filtros ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("/status", True),
        ("/help", True),
        ("/pausar 3", True),
        ("hola", False),
        ("", False),
        ("/", False),
        ("/123", False),  # debe empezar con letra
        ("//doble", False),  # segundo char no es alpha
    ],
)
def test_is_command(text, expected):
    assert tc.is_command(text) is expected


@pytest.mark.parametrize(
    "text,expected_cmd,expected_args",
    [
        ("/status", "status", []),
        ("/pausar 3", "pausar", ["3"]),
        ("/log hoy", "log", ["hoy"]),
        ("/status@orion_father_security_bot", "status", []),
        ("/PAUSAR 3", "pausar", ["3"]),  # case-insensitive
        ("  /status  ", "status", []),  # whitespace
    ],
)
def test_parse(text, expected_cmd, expected_args):
    cmd, args = tc.parse(text)
    assert cmd == expected_cmd
    assert args == expected_args


# ── Auth ────────────────────────────────────────────────────────────────


def test_unauthorized_sender_rejected(authed_chat_id):
    reply = tc.dispatch("/status", sender_chat_id=999999, authorized_chat_id=authed_chat_id)
    assert "No autorizado" in reply


def test_authorized_sender_can_run(authed_chat_id):
    reply = tc.dispatch("/status", sender_chat_id=authed_chat_id, authorized_chat_id=authed_chat_id)
    assert "No autorizado" not in reply
    assert "Estado del sistema" in reply


def test_help_no_auth_required(authed_chat_id):
    """`/help` debe ser ejecutable por cualquiera (requires_auth=False)."""
    reply = tc.dispatch("/help", sender_chat_id=999, authorized_chat_id=authed_chat_id)
    assert "Comandos disponibles" in reply
    assert "/status" in reply
    assert "/usuarios" in reply


def test_unknown_command(authed_chat_id):
    reply = tc.dispatch(
        "/inexistente", sender_chat_id=authed_chat_id, authorized_chat_id=authed_chat_id
    )
    assert "desconocido" in reply.lower()
    assert "/help" in reply


def test_authorized_chat_id_as_string_works():
    """Telegram default_chat_id se persiste como string en config — el
    dispatcher debe aceptarlo y comparar como int."""
    reply = tc.dispatch(
        "/status",
        sender_chat_id=8341210361,
        authorized_chat_id="8341210361",  # string
    )
    assert "No autorizado" not in reply


# ── Comandos con DB ────────────────────────────────────────────────────


def test_status_empty_db(authed_chat_id):
    reply = tc.dispatch("/status", sender_chat_id=authed_chat_id, authorized_chat_id=authed_chat_id)
    assert "Estado del sistema" in reply
    assert "0" in reply  # 0 usuarios, 0 eventos


def test_usuarios_empty(authed_chat_id):
    reply = tc.dispatch(
        "/usuarios", sender_chat_id=authed_chat_id, authorized_chat_id=authed_chat_id
    )
    assert "Ninguno" in reply


def test_usuarios_listing(authed_chat_id):
    ac.add_user(fingerprint_id=5, name="Zahir Test", phone="")
    ac.add_user(fingerprint_id=12, name="María Test", phone="")
    reply = tc.dispatch(
        "/usuarios", sender_chat_id=authed_chat_id, authorized_chat_id=authed_chat_id
    )
    assert "Zahir Test" in reply
    assert "María Test" in reply
    assert "#005" in reply
    assert "#012" in reply


def test_pausar_slot_no_existe(authed_chat_id):
    reply = tc.dispatch(
        "/pausar 99", sender_chat_id=authed_chat_id, authorized_chat_id=authed_chat_id
    )
    assert "No hay usuario" in reply


def test_pausar_slot_fuera_de_rango(authed_chat_id):
    reply = tc.dispatch(
        "/pausar 200",
        sender_chat_id=authed_chat_id,
        authorized_chat_id=authed_chat_id,
    )
    assert "fuera de rango" in reply.lower()


def test_pausar_sin_args(authed_chat_id):
    reply = tc.dispatch("/pausar", sender_chat_id=authed_chat_id, authorized_chat_id=authed_chat_id)
    assert "Falta el número" in reply


def test_pausar_args_invalidos(authed_chat_id):
    reply = tc.dispatch(
        "/pausar abc",
        sender_chat_id=authed_chat_id,
        authorized_chat_id=authed_chat_id,
    )
    assert "no es un número" in reply.lower()


def test_pausar_y_activar_round_trip(authed_chat_id):
    user = ac.add_user(fingerprint_id=7, name="Test User", phone="")
    assert user.active

    r1 = tc.dispatch("/pausar 7", sender_chat_id=authed_chat_id, authorized_chat_id=authed_chat_id)
    assert "pausado" in r1
    assert "Test User" in r1

    refreshed = [u for u in ac.list_users() if u.fingerprint_id == 7][0]
    assert refreshed.active is False

    r2 = tc.dispatch("/pausar 7", sender_chat_id=authed_chat_id, authorized_chat_id=authed_chat_id)
    assert "ya está pausado" in r2

    r3 = tc.dispatch("/activar 7", sender_chat_id=authed_chat_id, authorized_chat_id=authed_chat_id)
    assert "activado" in r3

    refreshed2 = [u for u in ac.list_users() if u.fingerprint_id == 7][0]
    assert refreshed2.active is True


def test_log_vacio(authed_chat_id):
    reply = tc.dispatch("/log", sender_chat_id=authed_chat_id, authorized_chat_id=authed_chat_id)
    assert "Sin eventos" in reply


def test_log_con_eventos(authed_chat_id):
    ac.add_user(fingerprint_id=3, name="Test", phone="")
    ac.record_event(fingerprint_id=3, event_type="GRANTED", esp_id="test", confidence=150)
    ac.record_event(fingerprint_id=-1, event_type="DENIED", esp_id="test", confidence=0)

    reply = tc.dispatch("/log", sender_chat_id=authed_chat_id, authorized_chat_id=authed_chat_id)
    assert "Test" in reply
    assert "Huella #-1" in reply or "Huella" in reply


# ── Bridge wire ────────────────────────────────────────────────────────


def _make_bridge_with_cfg(cfg: TelegramConfig):
    """Crea una instancia de bridge con cfg seteado pero sin polling."""
    from orion.server.telegram_bridge import TelegramBridge

    bus = MagicMock()
    bridge = TelegramBridge(bus)
    bridge._cfg = cfg
    return bridge


def test_should_dispatch_private_chat_command():
    cfg = TelegramConfig(
        bot_token="t",
        default_chat_id="8341210361",
        forward_notifications=True,
        enabled=True,
    )
    bridge = _make_bridge_with_cfg(cfg)
    # Chat privado: chat_id == default_chat_id, thread_id None
    assert bridge._should_dispatch_command("/status", 8341210361, None) is True


def test_should_dispatch_supergroup_commands_topic():
    cfg = TelegramConfig(
        bot_token="t",
        default_chat_id="8341210361",
        forward_notifications=True,
        enabled=True,
        group=TelegramGroupConfig(chat_id="-1004474820134", topics={"commands": 2}),
    )
    bridge = _make_bridge_with_cfg(cfg)
    # Mensaje desde el topic Comandos
    assert bridge._should_dispatch_command("/status", -1004474820134, 2) is True


def test_should_NOT_dispatch_supergroup_other_topic():
    cfg = TelegramConfig(
        bot_token="t",
        default_chat_id="8341210361",
        forward_notifications=True,
        enabled=True,
        group=TelegramGroupConfig(chat_id="-1004474820134", topics={"commands": 2, "access": 4}),
    )
    bridge = _make_bridge_with_cfg(cfg)
    # Topic Acceso: NO debe dispatchear
    assert bridge._should_dispatch_command("/status", -1004474820134, 4) is False


def test_should_NOT_dispatch_non_command_text():
    cfg = TelegramConfig(
        bot_token="t",
        default_chat_id="8341210361",
        forward_notifications=True,
        enabled=True,
    )
    bridge = _make_bridge_with_cfg(cfg)
    # Texto normal en chat privado: NO es comando
    assert bridge._should_dispatch_command("hola Orion", 8341210361, None) is False


def test_inbound_command_bypasses_brain(authed_chat_id):
    """Si llega un slash command, el bus NO recibe submit_user_text — el
    cerebro no es invocado."""
    cfg = TelegramConfig(
        bot_token="tk",
        default_chat_id=str(authed_chat_id),
        forward_notifications=True,
        enabled=True,
        group=TelegramGroupConfig(chat_id="-1004474820134", topics={"commands": 2}),
    )
    bridge = _make_bridge_with_cfg(cfg)

    fake_client = MagicMock()
    bridge._client = fake_client

    # Simulamos un mensaje del topic Comandos
    bridge._handle_inbound(
        chat_id=-1004474820134,
        text="/status",
        sender="Zahir",
        thread_id=2,
        from_user_id=authed_chat_id,
    )

    # El bus NO debió haber recibido submit_user_text
    assert not bridge.bus.submit_user_text.called

    # Verificar que se intentó mandar reply (en thread daemon — esperamos
    # un poquito a que arranque). Como _send_async usa thread, hacemos
    # un join razonable.
    import time as _t

    for _ in range(20):
        if fake_client.send_message.called:
            break
        _t.sleep(0.05)
    assert fake_client.send_message.called
    args, kwargs = fake_client.send_message.call_args
    assert args[0] == -1004474820134  # mismo chat
    assert kwargs.get("message_thread_id") == 2  # mismo topic


def test_inbound_non_command_goes_to_brain(authed_chat_id):
    """Texto normal NO debe ser dispatcheado a commands."""
    cfg = TelegramConfig(
        bot_token="tk",
        default_chat_id=str(authed_chat_id),
        forward_notifications=True,
        enabled=True,
    )
    bridge = _make_bridge_with_cfg(cfg)

    # Mock para set_last_client que se importa adentro de _handle_inbound
    with patch("orion.core.client_context.set_last_client"):
        bridge._handle_inbound(
            chat_id=authed_chat_id,
            text="hola Orion, qué hora es?",
            sender="Zahir",
            thread_id=None,
            from_user_id=authed_chat_id,
        )

    # Brain SÍ debió haber recibido el texto
    bridge.bus.submit_user_text.assert_called_once_with("hola Orion, qué hora es?")
