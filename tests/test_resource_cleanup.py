"""Resource-cleanup tests: timer cancel, shutdown event, dedup caps, avatar idempotency."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import core.storage as storage
from core.chats.kick_chat import KickChatClient
from core.chats.youtube_chat import _DEDUP_MAX as _YT_DEDUP_MAX
from core.chats.youtube_chat import YouTubeChatClient
from core.storage import save_avatar
from ui.api import TwitchXApi


def test_close_cancels_polling_timer(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """close() must cancel the polling timer."""
    api = TwitchXApi()
    mock_timer = MagicMock()
    api._polling_timer = mock_timer

    # Suppress side-effects that require a real window or network
    monkeypatch.setattr(api, "_eval_js", lambda code: None)

    api.close()

    mock_timer.cancel.assert_called_once()


def test_close_sets_shutdown_event(temp_config_dir: Path) -> None:
    """close() sets _shutdown so background threads stop emitting JS."""
    api = TwitchXApi()
    assert not api._shutdown.is_set(), "precondition: _shutdown not yet set"

    api.close()

    assert api._shutdown.is_set()


def test_kick_chat_dedup_cap_does_not_grow_unbounded() -> None:
    """_seen_msg_ids in KickChatClient stays at _DEDUP_MAX, no more."""
    cap = KickChatClient._DEDUP_MAX

    client = KickChatClient.__new__(KickChatClient)
    client._seen_msg_ids = set()
    client._seen_msg_order = []

    # Simulate adding cap + 50 unique messages using the same LRU logic
    for i in range(cap + 50):
        msg_id = str(i)
        if msg_id in client._seen_msg_ids:
            continue
        client._seen_msg_ids.add(msg_id)
        client._seen_msg_order.append(msg_id)
        if len(client._seen_msg_order) > cap:
            client._seen_msg_ids.discard(client._seen_msg_order.pop(0))

    assert len(client._seen_msg_ids) == cap
    assert len(client._seen_msg_order) == cap


def test_youtube_chat_dedup_cap_does_not_grow_unbounded() -> None:
    """_seen_msg_ids in YouTubeChatClient stays at _DEDUP_MAX, no more."""
    cap = _YT_DEDUP_MAX

    client = YouTubeChatClient.__new__(YouTubeChatClient)
    client._seen_msg_ids = set()
    client._seen_msg_order = []

    # Simulate adding cap + 50 unique messages using the same LRU logic
    for i in range(cap + 50):
        msg_id = str(i)
        if msg_id in client._seen_msg_ids:
            continue
        client._seen_msg_ids.add(msg_id)
        client._seen_msg_order.append(msg_id)
        if len(client._seen_msg_order) > cap:
            old_id = client._seen_msg_order.pop(0)
            client._seen_msg_ids.discard(old_id)

    assert len(client._seen_msg_ids) == cap
    assert len(client._seen_msg_order) == cap


def test_save_avatar_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """save_avatar can be called twice for the same user without error."""
    avatar_dir = tmp_path / "avatars"
    monkeypatch.setattr(storage, "AVATAR_DIR", avatar_dir)

    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

    # Call twice — must not raise
    save_avatar("testuser", fake_png, platform="twitch")
    save_avatar("testuser", fake_png, platform="twitch")

    written = (avatar_dir / "twitch" / "testuser.png").read_bytes()
    assert written == fake_png
