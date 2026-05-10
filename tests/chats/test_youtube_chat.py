"""Tests for YouTube Live Chat client and message parser."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.chat import ChatMessage
from core.chats.base import StopReconnect
from core.chats.youtube_chat import (
    YouTubeChatClient,
    parse_youtube_chat_message,
)

# ── parse_youtube_chat_message ────────────────────────────────────────


class TestParseYoutubeChatMessage:
    def _make_text_message(self, **overrides: Any) -> dict[str, Any]:
        base = {
            "id": "msg-1",
            "snippet": {
                "type": "textMessageEvent",
                "liveChatId": "QWERTY",
                "authorChannelId": "UCx12345",
                "publishedAt": "2026-05-01T12:00:00.000Z",
                "textMessageDetails": {"messageText": "Hello YouTube chat!"},
                "displayMessage": "Hello YouTube chat!",
            },
            "authorDetails": {
                "channelId": "UCx12345",
                "displayName": "TestUser",
                "profileImageUrl": "https://yt3.ggpht.com/avatar.jpg",
                "isVerified": False,
                "isChatOwner": False,
                "isChatModerator": False,
                "isChatSponsor": False,
            },
        }
        base.update(overrides)
        return base

    def test_text_message(self) -> None:
        item = self._make_text_message()
        msg = parse_youtube_chat_message(item)
        assert msg is not None
        assert msg.platform == "youtube"
        assert msg.author == "UCx12345"
        assert msg.author_display == "TestUser"
        assert msg.text == "Hello YouTube chat!"
        assert msg.message_type == "text"
        assert msg.is_system is False
        assert msg.msg_id == "msg-1"
        assert msg.avatar_url == "https://yt3.ggpht.com/avatar.jpg"
        assert msg.author_color is None
        assert msg.emotes == []

    def test_text_message_no_avatar(self) -> None:
        item = self._make_text_message()
        item["authorDetails"]["profileImageUrl"] = ""
        msg = parse_youtube_chat_message(item)
        assert msg is not None
        assert msg.avatar_url is None

    def test_super_chat(self) -> None:
        item = self._make_text_message(
            id="msg-sc1",
            snippet={
                "type": "superChatEvent",
                "liveChatId": "QWERTY",
                "authorChannelId": "UCx999",
                "publishedAt": "2026-05-01T12:01:00.000Z",
                "superChatDetails": {
                    "amountDisplayString": "$5.00",
                    "currency": "USD",
                    "userComment": "Great stream!",
                },
                "displayMessage": "$5.00 Great stream!",
            },
            authorDetails={
                "channelId": "UCx999",
                "displayName": "SuperFan",
                "profileImageUrl": "https://yt3.ggpht.com/super.jpg",
                "isVerified": False,
                "isChatOwner": False,
                "isChatModerator": False,
                "isChatSponsor": False,
            },
        )
        msg = parse_youtube_chat_message(item)
        assert msg is not None
        assert msg.message_type == "super_chat"
        assert msg.is_system is True
        assert "$5.00" in msg.text
        assert "Great stream!" in msg.text

    def test_super_chat_no_comment(self) -> None:
        item = self._make_text_message(
            id="msg-sc2",
            snippet={
                "type": "superChatEvent",
                "liveChatId": "QWERTY",
                "authorChannelId": "UCx999",
                "publishedAt": "2026-05-01T12:01:00.000Z",
                "superChatDetails": {
                    "amountDisplayString": "$2.00",
                    "currency": "USD",
                    "userComment": "",
                },
                "displayMessage": "$2.00",
            },
            authorDetails={
                "channelId": "UCx999",
                "displayName": "Fan",
                "profileImageUrl": "",
                "isVerified": False,
                "isChatOwner": False,
                "isChatModerator": False,
                "isChatSponsor": False,
            },
        )
        msg = parse_youtube_chat_message(item)
        assert msg is not None
        assert msg.text == "$2.00"

    def test_new_sponsor_event(self) -> None:
        item = self._make_text_message(
            id="msg-sub1",
            snippet={
                "type": "newSponsorEvent",
                "liveChatId": "QWERTY",
                "authorChannelId": "UCx555",
                "publishedAt": "2026-05-01T12:02:00.000Z",
                "displayMessage": "NewMember just became a member!",
            },
            authorDetails={
                "channelId": "UCx555",
                "displayName": "NewMember",
                "profileImageUrl": "",
                "isVerified": False,
                "isChatOwner": False,
                "isChatModerator": False,
                "isChatSponsor": True,
            },
        )
        msg = parse_youtube_chat_message(item)
        assert msg is not None
        assert msg.message_type == "sub"
        assert msg.is_system is True
        assert "NewMember" in msg.text

    def test_member_milestone_chat_event(self) -> None:
        item = self._make_text_message(
            id="msg-ms1",
            snippet={
                "type": "memberMilestoneChatEvent",
                "liveChatId": "QWERTY",
                "authorChannelId": "UCx666",
                "publishedAt": "2026-05-01T12:03:00.000Z",
                "displayMessage": "LongTimer 12 month milestone!",
            },
            authorDetails={
                "channelId": "UCx666",
                "displayName": "LongTimer",
                "profileImageUrl": "",
                "isVerified": False,
                "isChatOwner": False,
                "isChatModerator": False,
                "isChatSponsor": True,
            },
        )
        msg = parse_youtube_chat_message(item)
        assert msg is not None
        assert msg.message_type == "sub"
        assert msg.is_system is True

    def test_owner_badge(self) -> None:
        item = self._make_text_message()
        item["authorDetails"]["isChatOwner"] = True
        msg = parse_youtube_chat_message(item)
        assert msg is not None
        assert any(b.name == "owner" for b in msg.badges)

    def test_moderator_badge(self) -> None:
        item = self._make_text_message()
        item["authorDetails"]["isChatModerator"] = True
        msg = parse_youtube_chat_message(item)
        assert msg is not None
        assert any(b.name == "moderator" for b in msg.badges)

    def test_sponsor_badge(self) -> None:
        item = self._make_text_message()
        item["authorDetails"]["isChatSponsor"] = True
        msg = parse_youtube_chat_message(item)
        assert msg is not None
        assert any(b.name == "sponsor" for b in msg.badges)

    def test_verified_badge(self) -> None:
        item = self._make_text_message()
        item["authorDetails"]["isVerified"] = True
        msg = parse_youtube_chat_message(item)
        assert msg is not None
        assert any(b.name == "verified" for b in msg.badges)

    def test_multiple_badges(self) -> None:
        item = self._make_text_message()
        item["authorDetails"]["isChatOwner"] = True
        item["authorDetails"]["isVerified"] = True
        msg = parse_youtube_chat_message(item)
        assert msg is not None
        assert len(msg.badges) == 2

    def test_no_badges(self) -> None:
        item = self._make_text_message()
        msg = parse_youtube_chat_message(item)
        assert msg is not None
        assert msg.badges == []

    def test_message_deleted_returns_none(self) -> None:
        item = {
            "id": "del-1",
            "snippet": {"type": "messageDeletedEvent"},
            "authorDetails": {},
        }
        assert parse_youtube_chat_message(item) is None

    def test_user_banned_returns_none(self) -> None:
        item = {
            "id": "ban-1",
            "snippet": {"type": "userBannedEvent"},
            "authorDetails": {},
        }
        assert parse_youtube_chat_message(item) is None

    def test_unknown_type_defaults_to_text(self) -> None:
        item = self._make_text_message(
            snippet={
                "type": "someNewEventType",
                "liveChatId": "QWERTY",
                "authorChannelId": "UCx12345",
                "publishedAt": "2026-05-01T12:00:00.000Z",
                "displayMessage": "something happened",
            }
        )
        msg = parse_youtube_chat_message(item)
        assert msg is not None
        assert msg.message_type == "text"
        assert msg.text == "something happened"

    def test_empty_fields(self) -> None:
        item = {
            "id": "",
            "snippet": {
                "type": "textMessageEvent",
                "publishedAt": "",
                "textMessageDetails": {"messageText": "hi"},
            },
            "authorDetails": {
                "channelId": "",
                "displayName": "",
                "profileImageUrl": "",
                "isVerified": False,
                "isChatOwner": False,
                "isChatModerator": False,
                "isChatSponsor": False,
            },
        }
        msg = parse_youtube_chat_message(item)
        assert msg is not None
        assert msg.author == ""
        assert msg.author_display == ""
        assert msg.text == "hi"


# ── YouTubeChatClient ────────────────────────────────────────────────


class TestYouTubeChatClientInit:
    def test_initial_state(self) -> None:
        yt = MagicMock()
        client = YouTubeChatClient(yt)
        assert client.platform == "youtube"
        assert client._ws is None
        assert client._channel is None
        assert client._running is False
        assert client._authenticated is False
        assert client._live_chat_id is None


class TestYouTubeChatClientSend:
    async def test_send_always_returns_false(self) -> None:
        yt = MagicMock()
        client = YouTubeChatClient(yt)
        client._channel = "test_channel"
        result = await client.send_message("hello")
        assert result.ok is False
        assert result.platform == "youtube"
        assert result.channel_id == "test_channel"
        assert "read-only" in result.error or "YouTube" in result.error


class TestYouTubeChatClientConnect:
    async def test_connect_with_live_chat_id(self) -> None:
        yt = MagicMock()
        yt._quota = MagicMock()
        yt._quota.check_and_use.return_value = True
        yt._yt_get = AsyncMock(side_effect=StopReconnect)

        client = YouTubeChatClient(yt)
        statuses: list[Any] = []
        client.on_status(lambda s: statuses.append(s))

        # Providing live_chat_id skips resolution
        with (
            patch("core.chats.youtube_chat.asyncio.sleep", new_callable=AsyncMock),
            contextlib.suppress(StopReconnect),
        ):
            await client.connect(
                "UCtest123", token="fake", live_chat_id="abc123"
            )

        # Should have emitted connected=True at least once
        connected_statuses = [s for s in statuses if s.connected]
        assert len(connected_statuses) >= 1

    async def test_connect_without_live_chat_id_resolves_from_video(self) -> None:
        yt = MagicMock()
        yt._live_video_ids = {"UCtest123": "vid_abc"}
        yt._quota = MagicMock()
        yt._quota.check_and_use.return_value = True
        yt._yt_get = AsyncMock(
            side_effect=StopReconnect
        )

        client = YouTubeChatClient(yt)
        statuses: list[Any] = []
        client.on_status(lambda s: statuses.append(s))

        # _resolve_live_chat_id should be called
        with (
            patch.object(
                client,
                "_resolve_live_chat_id",
                new_callable=AsyncMock,
                return_value="chat_abc",
            ),
            patch("core.chats.youtube_chat.asyncio.sleep", new_callable=AsyncMock),
            contextlib.suppress(StopReconnect),
        ):
            await client.connect("UCtest123", token="fake")

        assert client._live_chat_id == "chat_abc"

    async def test_connect_no_chat_id_emits_error(self) -> None:
        yt = MagicMock()
        yt._live_video_ids = {}

        client = YouTubeChatClient(yt)
        statuses: list[Any] = []
        client.on_status(lambda s: statuses.append(s))

        await client.connect("UC_no_stream", token="fake")

        assert len(statuses) == 1
        assert statuses[0].connected is False
        assert "No active live chat" in statuses[0].error


class TestYouTubeChatClientDisconnect:
    async def test_disconnect_clears_state(self) -> None:
        yt = MagicMock()
        client = YouTubeChatClient(yt)
        client._running = True
        client._live_chat_id = "chat_123"
        client._next_page_token = "token_abc"
        client._channel = "UCtest"
        await client.disconnect()
        assert client._running is False
        assert client._live_chat_id is None
        assert client._next_page_token is None


class TestYoutubeChatDedup:
    async def test_duplicate_messages_are_skipped(self) -> None:
        yt = MagicMock()
        yt._quota = MagicMock()
        yt._quota.check_and_use.return_value = True

        msg_item = {
            "id": "msg-dup1",
            "snippet": {
                "type": "textMessageEvent",
                "publishedAt": "2026-05-01T12:00:00.000Z",
                "textMessageDetails": {"messageText": "hello"},
                "displayMessage": "hello",
            },
            "authorDetails": {
                "channelId": "UCx1",
                "displayName": "User1",
                "profileImageUrl": "",
                "isVerified": False,
                "isChatOwner": False,
                "isChatModerator": False,
                "isChatSponsor": False,
            },
        }

        received: list[ChatMessage] = []

        client = YouTubeChatClient(yt)
        client.on_message(lambda m: received.append(m))
        client._running = True
        client._live_chat_id = "chat_1"
        client._loop = asyncio.new_event_loop()

        # First poll: returns message
        yt._yt_get = AsyncMock(
            return_value={
                "items": [msg_item],
                "pollingIntervalMillis": 5000,
                "nextPageToken": "tok1",
            }
        )

        call_count = 0

        async def fake_sleep(seconds: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                client._running = False

        with patch("core.chats.youtube_chat.asyncio.sleep", new_callable=AsyncMock, side_effect=fake_sleep):
            await client._poll_messages()
            assert len(received) == 1

        # Reset for second poll with same message
        client._running = True
        yt._yt_get = AsyncMock(
            return_value={
                "items": [msg_item],
                "pollingIntervalMillis": 5000,
                "nextPageToken": "tok2",
            }
        )

        call_count2 = 0

        async def fake_sleep2(seconds: float) -> None:
            nonlocal call_count2
            call_count2 += 1
            if call_count2 >= 1:
                client._running = False

        with patch("core.chats.youtube_chat.asyncio.sleep", new_callable=AsyncMock, side_effect=fake_sleep2):
            await client._poll_messages()
            assert len(received) == 1  # Duplicate was skipped

        client._loop.close()


class TestYoutubeChatQuota:
    async def test_quota_exhausted_stops_polling(self) -> None:
        yt = MagicMock()
        yt._quota = MagicMock()
        yt._quota.check_and_use.return_value = False

        client = YouTubeChatClient(yt)
        client._running = True
        client._live_chat_id = "chat_1"
        client._channel = "UCtest"

        statuses: list[Any] = []
        client.on_status(lambda s: statuses.append(s))

        with pytest.raises(StopReconnect):
            await client._poll_messages()

        assert any("quota" in (s.error or "").lower() for s in statuses)