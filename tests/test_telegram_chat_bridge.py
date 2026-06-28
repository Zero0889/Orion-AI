"""
Tests del bridge brain ↔ Telegram (Fase 3 supergrupo: chat libre).

Cubren:
  - Filtro: solo chat privado o topic Chat reciben/disparan el brain.
  - Topics access/status/comandos con texto libre quedan ignorados.
  - Auth: solo el `default_chat_id` puede chatear con el brain.
  - Routing de la respuesta: la respuesta de Orion vuelve al MISMO topic
    de donde vino (preserva thread_id), no al chat privado por default.
  - Back-compat: chat privado sigue funcionando (thread_id None).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orion.adapters.messaging.telegram import TelegramConfig, TelegramGroupConfig
from orion.server.telegram_bridge import TelegramBridge


AUTHED_USER = 8341210361
GROUP_CHAT = -1004474820134
CHAT_THREAD = 11
ACCESS_THREAD = 4
COMMANDS_THREAD = 2


@pytest.fixture
def cfg_with_topics() -> TelegramConfig:
    return TelegramConfig(
        bot_token="t",
        default_chat_id=str(AUTHED_USER),
        forward_notifications=True,
        enabled=True,
        group=TelegramGroupConfig(
            chat_id=str(GROUP_CHAT),
            topics={
                "access": ACCESS_THREAD,
                "commands": COMMANDS_THREAD,
                "chat": CHAT_THREAD,
            },
        ),
    )


@pytest.fixture
def cfg_no_group() -> TelegramConfig:
    """Config legacy sin supergrupo — solo chat privado."""
    return TelegramConfig(
        bot_token="t",
        default_chat_id=str(AUTHED_USER),
        forward_notifications=True,
        enabled=True,
    )


def _make_bridge(cfg: TelegramConfig) -> TelegramBridge:
    bridge = TelegramBridge(MagicMock())
    bridge._cfg = cfg
    bridge._client = MagicMock()
    return bridge


# ── _should_forward_to_brain ────────────────────────────────────────────


def test_private_chat_forwards_to_brain(cfg_with_topics):
    bridge = _make_bridge(cfg_with_topics)
    assert bridge._should_forward_to_brain(AUTHED_USER, None) is True


def test_chat_topic_forwards_to_brain(cfg_with_topics):
    bridge = _make_bridge(cfg_with_topics)
    assert bridge._should_forward_to_brain(GROUP_CHAT, CHAT_THREAD) is True


def test_access_topic_does_NOT_forward(cfg_with_topics):
    bridge = _make_bridge(cfg_with_topics)
    assert bridge._should_forward_to_brain(GROUP_CHAT, ACCESS_THREAD) is False


def test_commands_topic_does_NOT_forward(cfg_with_topics):
    """Comandos tiene su propio dispatcher; texto libre desde ahí queda
    ignorado para evitar mensajes accidentales al brain."""
    bridge = _make_bridge(cfg_with_topics)
    assert bridge._should_forward_to_brain(GROUP_CHAT, COMMANDS_THREAD) is False


def test_unknown_chat_does_NOT_forward(cfg_with_topics):
    bridge = _make_bridge(cfg_with_topics)
    assert bridge._should_forward_to_brain(99999, None) is False


def test_general_topic_of_supergroup_does_NOT_forward(cfg_with_topics):
    """El topic General de cualquier supergrupo tiene thread_id=None
    cuando se mandó al general. Pero el chat_id es el del grupo, no
    coincide con default_chat_id, así que NO debe forwardear."""
    bridge = _make_bridge(cfg_with_topics)
    assert bridge._should_forward_to_brain(GROUP_CHAT, None) is False


def test_legacy_no_group_still_forwards_private(cfg_no_group):
    """Config sin bloque group: chat privado sigue funcionando."""
    bridge = _make_bridge(cfg_no_group)
    assert bridge._should_forward_to_brain(AUTHED_USER, None) is True


def test_chat_topic_missing_from_config_does_NOT_forward():
    """Si el user no configuró el topic chat, ese chat_id/thread_id no
    triggea el brain (solo el privado lo hace)."""
    cfg = TelegramConfig(
        bot_token="t",
        default_chat_id=str(AUTHED_USER),
        forward_notifications=True,
        enabled=True,
        group=TelegramGroupConfig(chat_id=str(GROUP_CHAT), topics={"access": 4}),
    )
    bridge = _make_bridge(cfg)
    # Algún topic random del grupo
    assert bridge._should_forward_to_brain(GROUP_CHAT, 99) is False


# ── _is_authorized_user ────────────────────────────────────────────────


def test_auth_user_ok(cfg_with_topics):
    bridge = _make_bridge(cfg_with_topics)
    assert bridge._is_authorized_user(AUTHED_USER) is True


def test_auth_user_no(cfg_with_topics):
    bridge = _make_bridge(cfg_with_topics)
    assert bridge._is_authorized_user(99999) is False


def test_auth_user_none(cfg_with_topics):
    bridge = _make_bridge(cfg_with_topics)
    assert bridge._is_authorized_user(None) is False


# ── _handle_inbound + reply flow ───────────────────────────────────────


def test_inbound_from_chat_topic_forwarded_to_brain(cfg_with_topics):
    """Mensaje libre desde topic Chat → brain + entry en _pending con
    el thread_id correcto."""
    bridge = _make_bridge(cfg_with_topics)
    with patch("orion.core.client_context.set_last_client"):
        bridge._handle_inbound(
            chat_id=GROUP_CHAT,
            text="qué hora es?",
            sender="Zahir",
            thread_id=CHAT_THREAD,
            from_user_id=AUTHED_USER,
        )
    bridge.bus.submit_user_text.assert_called_once_with("qué hora es?")
    assert list(bridge._pending) == [(GROUP_CHAT, CHAT_THREAD)]


def test_inbound_from_private_chat_forwarded_to_brain(cfg_with_topics):
    """Chat privado sigue funcionando como antes — thread_id None."""
    bridge = _make_bridge(cfg_with_topics)
    with patch("orion.core.client_context.set_last_client"):
        bridge._handle_inbound(
            chat_id=AUTHED_USER,
            text="hola",
            sender="Zahir",
            thread_id=None,
            from_user_id=AUTHED_USER,
        )
    bridge.bus.submit_user_text.assert_called_once_with("hola")
    assert list(bridge._pending) == [(AUTHED_USER, None)]


def test_inbound_from_access_topic_ignored(cfg_with_topics):
    """Texto libre en topic Acceso → NO se manda al brain, no se mete
    en _pending."""
    bridge = _make_bridge(cfg_with_topics)
    bridge._handle_inbound(
        chat_id=GROUP_CHAT,
        text="alguien acaba de entrar?",
        sender="Zahir",
        thread_id=ACCESS_THREAD,
        from_user_id=AUTHED_USER,
    )
    assert not bridge.bus.submit_user_text.called
    assert len(bridge._pending) == 0


def test_inbound_from_unauthorized_user_ignored(cfg_with_topics):
    """Otro miembro del supergrupo escribe en el topic Chat → NO triggea
    brain (no consume tokens, no responde)."""
    bridge = _make_bridge(cfg_with_topics)
    bridge._handle_inbound(
        chat_id=GROUP_CHAT,
        text="hola Orion, escuchame",
        sender="Intruder",
        thread_id=CHAT_THREAD,
        from_user_id=99999,  # OTRO user, no el autorizado
    )
    assert not bridge.bus.submit_user_text.called
    assert len(bridge._pending) == 0


# ── _maybe_forward_orion_reply ─────────────────────────────────────────


def test_orion_reply_routed_to_same_topic(cfg_with_topics):
    """Cuando llega un log 'Orion: ...' del bus, lo mandamos al chat/topic
    que está al frente de _pending — con su thread_id."""
    bridge = _make_bridge(cfg_with_topics)
    # Simulamos que vino una pregunta del topic Chat
    with bridge._pending_lock:
        bridge._pending.append((GROUP_CHAT, CHAT_THREAD))

    bridge._maybe_forward_orion_reply({"text": "Orion: son las 6 PM."})

    # Esperamos al thread de send_async (es async)
    import time as _t

    for _ in range(20):
        if bridge._client.send_message.called:
            break
        _t.sleep(0.05)
    assert bridge._client.send_message.called
    args, kwargs = bridge._client.send_message.call_args
    assert args[0] == GROUP_CHAT
    assert kwargs.get("message_thread_id") == CHAT_THREAD


def test_orion_reply_to_private_chat_no_thread_id(cfg_with_topics):
    """Pregunta del privado → reply al privado con thread_id None."""
    bridge = _make_bridge(cfg_with_topics)
    with bridge._pending_lock:
        bridge._pending.append((AUTHED_USER, None))

    bridge._maybe_forward_orion_reply({"text": "Orion: hola Zahir!"})

    import time as _t

    for _ in range(20):
        if bridge._client.send_message.called:
            break
        _t.sleep(0.05)
    assert bridge._client.send_message.called
    args, kwargs = bridge._client.send_message.call_args
    assert args[0] == AUTHED_USER
    assert kwargs.get("message_thread_id") is None


def test_orion_reply_with_empty_pending_does_nothing(cfg_with_topics):
    """Si llega una reply de Orion pero nadie preguntó (deque vacía),
    NO debe mandar nada — evita pisar respuestas a comandos slash que
    no usan _pending."""
    bridge = _make_bridge(cfg_with_topics)
    bridge._maybe_forward_orion_reply({"text": "Orion: respuesta huerfana"})
    # No esperamos thread; tampoco debería arrancarse uno
    assert not bridge._client.send_message.called


def test_orion_reply_non_orion_prefix_ignored(cfg_with_topics):
    """Logs que no empiezan con 'Orion:' no son respuestas para forward."""
    bridge = _make_bridge(cfg_with_topics)
    with bridge._pending_lock:
        bridge._pending.append((AUTHED_USER, None))

    bridge._maybe_forward_orion_reply({"text": "user: hola"})

    # _pending sigue intacta porque no era una reply de Orion
    assert len(bridge._pending) == 1
    assert not bridge._client.send_message.called


# ── _handle_chat_stream (path moderno de chat_brain) ───────────────────


def _wait_for_send(bridge, timeout_s: float = 1.0) -> bool:
    """Espera a que el thread daemon de _send_async dispare send_message."""
    import time as _t

    deadline = _t.time() + timeout_s
    while _t.time() < deadline:
        if bridge._client.send_message.called:
            return True
        _t.sleep(0.02)
    return False


def test_chat_stream_chat_brain_pattern_routed_to_topic(cfg_with_topics):
    """chat_brain emite UN chunk con todo el texto + un chunk vacío con
    final=True. El bridge debe acumular y mandar al cerrar."""
    bridge = _make_bridge(cfg_with_topics)
    with bridge._pending_lock:
        bridge._pending.append((GROUP_CHAT, CHAT_THREAD))

    bridge._handle_chat_stream(
        {"role": "orion", "turn_id": "t1", "delta": "Son las 6 PM.", "final": False}
    )
    # Aún no se envía nada porque final=False
    assert not bridge._client.send_message.called

    bridge._handle_chat_stream({"role": "orion", "turn_id": "t1", "delta": "", "final": True})
    assert _wait_for_send(bridge)
    args, kwargs = bridge._client.send_message.call_args
    assert args[0] == GROUP_CHAT
    assert args[1] == "Son las 6 PM."
    assert kwargs.get("message_thread_id") == CHAT_THREAD


def test_chat_stream_live_pattern_accumulates_many_deltas(cfg_with_topics):
    """Gemini Live emite muchos chunks pequeños sin espacios (ver
    `_clean_transcript` que les hace .strip()). El bridge debe restituir
    los espacios entre palabras."""
    bridge = _make_bridge(cfg_with_topics)
    with bridge._pending_lock:
        bridge._pending.append((AUTHED_USER, None))

    for chunk in ["Hola", "Zahir", "qué", "tal?"]:
        bridge._handle_chat_stream(
            {"role": "orion", "turn_id": "t2", "delta": chunk, "final": False}
        )
    bridge._handle_chat_stream({"role": "orion", "turn_id": "t2", "delta": "", "final": True})
    assert _wait_for_send(bridge)
    args, _ = bridge._client.send_message.call_args
    # _smart_join restituye los espacios entre palabras pegadas
    assert args[1] == "Hola Zahir qué tal?"


def test_chat_stream_smart_join_preserves_existing_spaces(cfg_with_topics):
    """Si los chunks YA traen espacios (chat_brain), no agregamos extras."""
    bridge = _make_bridge(cfg_with_topics)
    with bridge._pending_lock:
        bridge._pending.append((AUTHED_USER, None))

    # Mezcla: algunos chunks con space al final, otros sin
    for chunk in ["Hola ", "Zahir", ", ", "qué", " tal?"]:
        bridge._handle_chat_stream(
            {"role": "orion", "turn_id": "t-mix", "delta": chunk, "final": False}
        )
    bridge._handle_chat_stream({"role": "orion", "turn_id": "t-mix", "delta": "", "final": True})
    assert _wait_for_send(bridge)
    args, _ = bridge._client.send_message.call_args
    assert args[1] == "Hola Zahir, qué tal?"


def test_chat_stream_real_bug_scenario(cfg_with_topics):
    """El bug reportado: 'Son las 11:31 del domingo' llegaba a Telegram
    como 'Sonlas11:31deldomingo'. Verifica que _smart_join lo arregla."""
    bridge = _make_bridge(cfg_with_topics)
    with bridge._pending_lock:
        bridge._pending.append((AUTHED_USER, None))

    for chunk in ["Hola.", "Son", "las", "11:31", "del", "domingo"]:
        bridge._handle_chat_stream(
            {"role": "orion", "turn_id": "tbug", "delta": chunk, "final": False}
        )
    bridge._handle_chat_stream({"role": "orion", "turn_id": "tbug", "delta": "", "final": True})
    assert _wait_for_send(bridge)
    args, _ = bridge._client.send_message.call_args
    assert args[1] == "Hola. Son las 11:31 del domingo"


def test_chat_stream_role_user_ignored(cfg_with_topics):
    """Chunks con role='user' son el eco del mensaje del usuario — no
    debemos reenviarlos a Telegram."""
    bridge = _make_bridge(cfg_with_topics)
    with bridge._pending_lock:
        bridge._pending.append((AUTHED_USER, None))

    bridge._handle_chat_stream(
        {"role": "user", "turn_id": "t3", "delta": "qué hora es?", "final": True}
    )
    assert not bridge._client.send_message.called
    # El pending sigue intacto esperando la respuesta de Orion
    assert len(bridge._pending) == 1


def test_chat_stream_empty_buffer_does_nothing(cfg_with_topics):
    """Si llega un final=True sin deltas previas con contenido, no
    enviamos un mensaje vacío."""
    bridge = _make_bridge(cfg_with_topics)
    with bridge._pending_lock:
        bridge._pending.append((AUTHED_USER, None))

    bridge._handle_chat_stream({"role": "orion", "turn_id": "t4", "delta": "", "final": True})
    assert not bridge._client.send_message.called


def test_chat_stream_interleaved_turns(cfg_with_topics):
    """Dos turnos overlapping (en paralelo): cada uno mantiene su buffer
    propio por turn_id."""
    bridge = _make_bridge(cfg_with_topics)
    with bridge._pending_lock:
        bridge._pending.append((AUTHED_USER, None))
        bridge._pending.append((GROUP_CHAT, CHAT_THREAD))

    bridge._handle_chat_stream(
        {"role": "orion", "turn_id": "tA", "delta": "Respuesta A", "final": False}
    )
    bridge._handle_chat_stream(
        {"role": "orion", "turn_id": "tB", "delta": "Respuesta B", "final": False}
    )
    bridge._handle_chat_stream({"role": "orion", "turn_id": "tA", "delta": "", "final": True})
    # Primer final → primer pending. Verificar.
    assert _wait_for_send(bridge)
    args1, _ = bridge._client.send_message.call_args_list[0]
    assert args1[1] == "Respuesta A"

    bridge._handle_chat_stream({"role": "orion", "turn_id": "tB", "delta": "", "final": True})
    # El segundo final → segundo pending.
    import time as _t

    deadline = _t.time() + 1.0
    while _t.time() < deadline and bridge._client.send_message.call_count < 2:
        _t.sleep(0.02)
    assert bridge._client.send_message.call_count == 2
    args2, _ = bridge._client.send_message.call_args_list[1]
    assert args2[1] == "Respuesta B"
