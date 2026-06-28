"""
Tests del routing de notificaciones por topic
=============================================
Verifican:

  1. ``TelegramConfig.resolve_topic`` devuelve ``(chat_id, thread_id)`` si
     el topic está mapeado, ``None`` si no hay grupo o el topic falta.
  2. ``TelegramClient.send_message`` propaga ``message_thread_id`` al payload.
  3. ``_parse_group`` rechaza inputs basura sin romperse.
  4. El loader de config acepta el formato nuevo y el viejo (sin ``group``).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orion.adapters.messaging import telegram as tg


@pytest.fixture
def cfg_path(tmp_path: Path, monkeypatch) -> Path:
    p = tmp_path / "telegram.json"
    monkeypatch.setattr(tg, "TELEGRAM_CONFIG_PATH", p)
    return p


# ── load_telegram_config ────────────────────────────────────────────────


def test_load_without_group_block(cfg_path: Path):
    cfg_path.write_text(
        json.dumps(
            {
                "bot_token": "tk",
                "default_chat_id": "123",
                "forward_notifications": True,
                "enabled": True,
            }
        ),
        encoding="utf-8",
    )
    cfg = tg.load_telegram_config()
    assert cfg.bot_token == "tk"
    assert cfg.default_chat_id == "123"
    assert cfg.group is None
    assert cfg.is_configured


def test_load_with_group_and_topics(cfg_path: Path):
    cfg_path.write_text(
        json.dumps(
            {
                "bot_token": "tk",
                "default_chat_id": "123",
                "forward_notifications": True,
                "enabled": True,
                "group": {
                    "chat_id": "-1001234567890",
                    "topics": {"access": 2, "status": 5},
                },
            }
        ),
        encoding="utf-8",
    )
    cfg = tg.load_telegram_config()
    assert cfg.group is not None
    assert cfg.group.chat_id == "-1001234567890"
    assert cfg.group.topics == {"access": 2, "status": 5}


def test_load_with_group_missing_chat_id_is_none(cfg_path: Path):
    cfg_path.write_text(
        json.dumps(
            {
                "bot_token": "tk",
                "default_chat_id": "123",
                "group": {"topics": {"access": 2}},  # falta chat_id
            }
        ),
        encoding="utf-8",
    )
    cfg = tg.load_telegram_config()
    assert cfg.group is None


def test_load_with_invalid_thread_id_skips_topic(cfg_path: Path):
    cfg_path.write_text(
        json.dumps(
            {
                "bot_token": "tk",
                "default_chat_id": "123",
                "group": {
                    "chat_id": "-100",
                    "topics": {"access": "not-an-int", "status": 5},
                },
            }
        ),
        encoding="utf-8",
    )
    cfg = tg.load_telegram_config()
    assert cfg.group is not None
    assert cfg.group.topics == {"status": 5}


# ── resolve_topic ───────────────────────────────────────────────────────


def test_resolve_topic_returns_pair():
    cfg = tg.TelegramConfig(
        bot_token="tk",
        default_chat_id="123",
        forward_notifications=True,
        enabled=True,
        group=tg.TelegramGroupConfig(chat_id="-100", topics={"access": 42}),
    )
    assert cfg.resolve_topic("access") == ("-100", 42)


def test_resolve_topic_returns_none_if_not_mapped():
    cfg = tg.TelegramConfig(
        bot_token="tk",
        default_chat_id="123",
        forward_notifications=True,
        enabled=True,
        group=tg.TelegramGroupConfig(chat_id="-100", topics={"access": 42}),
    )
    assert cfg.resolve_topic("status") is None


def test_resolve_topic_returns_none_if_no_group():
    cfg = tg.TelegramConfig(
        bot_token="tk",
        default_chat_id="123",
        forward_notifications=True,
        enabled=True,
        group=None,
    )
    assert cfg.resolve_topic("access") is None


# ── is_configured con grupo ─────────────────────────────────────────────


def test_is_configured_with_only_group():
    cfg = tg.TelegramConfig(
        bot_token="tk",
        default_chat_id="",
        forward_notifications=True,
        enabled=True,
        group=tg.TelegramGroupConfig(chat_id="-100", topics={"access": 1}),
    )
    assert cfg.is_configured


def test_is_configured_without_destination():
    cfg = tg.TelegramConfig(
        bot_token="tk",
        default_chat_id="",
        forward_notifications=True,
        enabled=True,
        group=None,
    )
    assert not cfg.is_configured


# ── send_message propaga message_thread_id ──────────────────────────────


def test_send_message_includes_thread_id():
    client = tg.TelegramClient("tk")
    with patch.object(client, "_post", return_value={"ok": True}) as mock_post:
        client.send_message("-100", "hola topic", message_thread_id=42)
        args, _kwargs = mock_post.call_args
        assert args[0] == "sendMessage"
        payload = args[1]
        assert payload["chat_id"] == "-100"
        assert payload["text"] == "hola topic"
        assert payload["message_thread_id"] == 42


def test_send_message_omits_thread_id_when_none():
    client = tg.TelegramClient("tk")
    with patch.object(client, "_post", return_value={"ok": True}) as mock_post:
        client.send_message("123", "hola directo")
        args, _ = mock_post.call_args
        assert "message_thread_id" not in args[1]


def test_send_message_long_text_each_block_carries_thread_id():
    """Si el texto supera 4000 chars y se parte, cada bloque tiene que
    seguir llegando al mismo topic."""
    client = tg.TelegramClient("tk")
    big = "x" * 9000
    with patch.object(client, "_post", return_value={"ok": True}) as mock_post:
        client.send_message("-100", big, message_thread_id=7)
        # 9000 / 4000 = 3 bloques
        assert mock_post.call_count == 3
        for call in mock_post.call_args_list:
            payload = call.args[1]
            assert payload["message_thread_id"] == 7


# ── save_telegram_config round-trip con group ───────────────────────────


def test_save_then_load_round_trip(cfg_path: Path):
    cfg = tg.TelegramConfig(
        bot_token="tk-real",
        default_chat_id="111",
        forward_notifications=False,
        enabled=True,
        group=tg.TelegramGroupConfig(chat_id="-222", topics={"access": 3}),
    )
    tg.save_telegram_config(cfg)
    loaded = tg.load_telegram_config()
    assert loaded == cfg


# ── routes/access._maybe_notify_telegram usa topic ──────────────────────


def test_access_notify_uses_topic_when_configured(cfg_path: Path):
    """Integración: si hay topic ``access`` configurado, el route le pega
    al topic en vez de al default_chat_id."""
    from orion.adapters.iot.access_control import AccessEvent

    cfg_path.write_text(
        json.dumps(
            {
                "bot_token": "tk",
                "default_chat_id": "111",
                "enabled": True,
                "group": {
                    "chat_id": "-222",
                    "topics": {"access": 99},
                },
            }
        ),
        encoding="utf-8",
    )

    from orion.server.routes import access as access_route

    ev = AccessEvent(
        id="x",
        fingerprint_id=1,
        event_type="GRANTED",
        esp_id="puerta",
        confidence=150,
        timestamp="2026-06-27T08:01:00",
        user_name="Zahir",
    )

    fake_client = MagicMock()
    with patch.object(access_route, "TelegramClient", return_value=fake_client):
        access_route._maybe_notify_telegram(ev)

    fake_client.send_message.assert_called_once()
    args, kwargs = fake_client.send_message.call_args
    assert args[0] == "-222"  # chat_id del grupo, no el privado
    assert kwargs.get("message_thread_id") == 99


def test_access_notify_falls_back_to_default_chat(cfg_path: Path):
    """Sin grupo configurado, sigue mandando al default_chat_id (legacy)."""
    from orion.adapters.iot.access_control import AccessEvent

    cfg_path.write_text(
        json.dumps(
            {
                "bot_token": "tk",
                "default_chat_id": "111",
                "enabled": True,
            }
        ),
        encoding="utf-8",
    )

    from orion.server.routes import access as access_route

    ev = AccessEvent(
        id="x",
        fingerprint_id=1,
        event_type="GRANTED",
        esp_id="puerta",
        confidence=150,
        timestamp="2026-06-27T08:01:00",
        user_name="Zahir",
    )

    fake_client = MagicMock()
    with patch.object(access_route, "TelegramClient", return_value=fake_client):
        access_route._maybe_notify_telegram(ev)

    fake_client.send_message.assert_called_once()
    args, kwargs = fake_client.send_message.call_args
    assert args[0] == "111"  # default_chat_id privado
    assert kwargs.get("message_thread_id") is None
