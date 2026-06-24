"""Tests para el clasificador de errores + throttle de logging del poller
de notificaciones."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orion.adapters.google.notifications.poller import (
    NotificationPoller,
    _classify_error,
    _hash_msg,
)


# ── _classify_error ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "msg,expected_kind",
    [
        (
            'round trip: base token source: oauth2: "deleted_client" "The OAuth client was deleted."',
            "setup_required",
        ),
        ("invalid_client: The OAuth client was not found.", "setup_required"),
        ("unauthorized_client", "setup_required"),
        ("Classroom sin token. Autorizá una vez desde el panel", "auth_required"),
        ("invalid_grant: Token has been expired or revoked.", "auth_required"),
        ("Connection timeout after 30s", "transient"),
        ("HTTP 500 Internal Server Error", "transient"),
        ("", "transient"),
    ],
)
def test_classify_error_kinds(msg: str, expected_kind: str) -> None:
    out = _classify_error(msg)
    assert out["kind"] == expected_kind


def test_classify_setup_required_includes_doc_link() -> None:
    out = _classify_error("deleted_client")
    assert out["doc"] == "docs/SETUP_GOOGLE_OAUTH.md"
    assert "Google Cloud" in out["user_message"]


def test_classify_transient_passes_through_message() -> None:
    out = _classify_error("HTTP 503 Service Unavailable")
    assert out["user_message"] == "HTTP 503 Service Unavailable"
    assert out["doc"] is None


def test_hash_msg_is_stable_and_short() -> None:
    h1 = _hash_msg("deleted_client error")
    h2 = _hash_msg("deleted_client error")
    assert h1 == h2
    assert len(h1) == 12
    assert _hash_msg("other") != h1


# ── Throttle de logging ───────────────────────────────────────────────────


def test_log_error_throttled_first_call_logs(caplog: pytest.LogCaptureFixture) -> None:
    poller = NotificationPoller()
    with caplog.at_level("WARNING", logger="orion.notif_poller"):
        poller._log_error_throttled("gmail", "deleted_client", "setup_required")
    msgs = [r.getMessage() for r in caplog.records]
    assert any("falló (setup_required)" in m for m in msgs)


def test_log_error_throttled_repeat_within_interval_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    poller = NotificationPoller()
    with caplog.at_level("WARNING", logger="orion.notif_poller"):
        poller._log_error_throttled("gmail", "deleted_client", "setup_required")
        caplog.clear()
        # Llamadas inmediatas → silenciadas.
        for _ in range(5):
            poller._log_error_throttled("gmail", "deleted_client", "setup_required")
    assert caplog.records == []


def test_log_error_throttled_relog_after_interval(caplog: pytest.LogCaptureFixture) -> None:
    poller = NotificationPoller()
    with patch("orion.adapters.google.notifications.poller.time") as fake_time:
        fake_time.time.side_effect = [0.0, 1.0, 3700.0]  # 0s, 1s, 1h+
        fake_time.strftime = lambda fmt, t: "00:00:00"
        fake_time.localtime = lambda ts: ts
        with caplog.at_level("WARNING", logger="orion.notif_poller"):
            poller._log_error_throttled("gmail", "deleted_client", "setup_required")
            poller._log_error_throttled("gmail", "deleted_client", "setup_required")  # silenciada
            poller._log_error_throttled("gmail", "deleted_client", "setup_required")  # re-log
    msgs = [r.getMessage() for r in caplog.records]
    assert len(msgs) == 2
    assert "sigue fallando" in msgs[1]
    assert "3 veces" in msgs[1]


# ── poll_once + bus event ────────────────────────────────────────────────


def test_poll_once_emits_setup_required_on_transition() -> None:
    poller = NotificationPoller()
    publish = MagicMock()
    poller.set_publish(publish)

    fake_adapter = MagicMock()
    fake_adapter.is_configured.return_value = True
    fake_adapter.fetch.side_effect = RuntimeError("deleted_client error")
    poller._adapters = {"gmail": fake_adapter}

    # Primera vuelta: estado pasa a setup_required → debería publicar.
    poller.poll_once()
    publish.assert_called_once()
    event_type, payload = publish.call_args.args
    assert event_type == "notification.setup_required"
    assert payload["source"] == "gmail"
    assert "Google Cloud" in payload["user_message"]

    # Segunda vuelta con el MISMO error → no re-publica.
    publish.reset_mock()
    poller.poll_once()
    publish.assert_not_called()


def test_status_exposes_setup_required_map() -> None:
    poller = NotificationPoller()
    fake_adapter = MagicMock()
    fake_adapter.is_configured.return_value = True
    fake_adapter.fetch.side_effect = RuntimeError("deleted_client")
    poller._adapters = {"gmail": fake_adapter}

    poller.poll_once()
    st = poller.status()
    assert st["setup_required"] == {"gmail": True}
    assert st["last_status"]["gmail"]["error_kind"] == "setup_required"
    assert st["last_status"]["gmail"]["doc"] == "docs/SETUP_GOOGLE_OAUTH.md"
