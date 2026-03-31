"""Tests for Kick Pusher chat client."""

from __future__ import annotations

from core.chat import Emote
from core.chats.kick_chat import parse_kick_emotes


class TestParseKickEmotes:
    def test_single_emote(self) -> None:
        text = "hello [emote:12345:KickHype] world"
        clean, emotes = parse_kick_emotes(text)
        assert clean == "hello KickHype world"
        assert emotes == [
            Emote(
                code="KickHype",
                url="https://files.kick.com/emotes/12345/fullsize",
                start=6,
                end=13,
            )
        ]

    def test_multiple_emotes(self) -> None:
        text = "[emote:111:A] and [emote:222:B]"
        clean, emotes = parse_kick_emotes(text)
        assert clean == "A and B"
        assert len(emotes) == 2
        assert emotes[0] == Emote(code="A", url="https://files.kick.com/emotes/111/fullsize", start=0, end=0)
        assert emotes[1] == Emote(code="B", url="https://files.kick.com/emotes/222/fullsize", start=6, end=6)

    def test_no_emotes(self) -> None:
        text = "hello world"
        clean, emotes = parse_kick_emotes(text)
        assert clean == "hello world"
        assert emotes == []

    def test_empty_text(self) -> None:
        clean, emotes = parse_kick_emotes("")
        assert clean == ""
        assert emotes == []

    def test_adjacent_emotes(self) -> None:
        text = "[emote:1:A][emote:2:B]"
        clean, emotes = parse_kick_emotes(text)
        assert clean == "AB"
        assert emotes[0].start == 0
        assert emotes[0].end == 0
        assert emotes[1].start == 1
        assert emotes[1].end == 1


import json

from core.chat import Badge, ChatMessage
from core.chats.kick_chat import parse_kick_event


class TestParseKickEvent:
    def _make_event(self, msg_data: dict) -> dict:
        """Create a Pusher event with double-encoded data."""
        return {
            "event": "App\\Events\\ChatMessageSentEvent",
            "data": json.dumps(msg_data),
            "channel": "chatrooms.123.v2",
        }

    def test_basic_message(self) -> None:
        data = {
            "id": "uuid-1",
            "chatroom_id": 123,
            "content": "hello world",
            "type": "message",
            "created_at": "2024-01-01T00:00:00.000000Z",
            "sender": {
                "id": 67890,
                "username": "TestUser",
                "slug": "testuser",
                "identity": {"color": "#FF4500", "badges": []},
            },
        }
        msg = parse_kick_event(self._make_event(data))
        assert msg is not None
        assert msg.platform == "kick"
        assert msg.author == "testuser"
        assert msg.author_display == "TestUser"
        assert msg.author_color == "#FF4500"
        assert msg.text == "hello world"
        assert msg.message_type == "text"
        assert msg.is_system is False
        assert msg.msg_id == "uuid-1"

    def test_message_with_emotes(self) -> None:
        data = {
            "id": "uuid-2",
            "chatroom_id": 123,
            "content": "hi [emote:999:PogChamp] gg",
            "type": "message",
            "created_at": "2024-01-01T00:00:00.000000Z",
            "sender": {
                "id": 1,
                "username": "User",
                "slug": "user",
                "identity": {"color": "#00FF00", "badges": []},
            },
        }
        msg = parse_kick_event(self._make_event(data))
        assert msg is not None
        assert msg.text == "hi PogChamp gg"
        assert len(msg.emotes) == 1
        assert msg.emotes[0].code == "PogChamp"
        assert msg.emotes[0].url == "https://files.kick.com/emotes/999/fullsize"

    def test_badges(self) -> None:
        data = {
            "id": "uuid-3",
            "chatroom_id": 123,
            "content": "hello",
            "type": "message",
            "created_at": "2024-01-01T00:00:00.000000Z",
            "sender": {
                "id": 1,
                "username": "Mod",
                "slug": "mod",
                "identity": {
                    "color": "#0000FF",
                    "badges": [
                        {"type": "subscriber", "text": "Subscriber", "count": 6},
                        {"type": "moderator", "text": "Moderator"},
                    ],
                },
            },
        }
        msg = parse_kick_event(self._make_event(data))
        assert msg is not None
        assert len(msg.badges) == 2
        assert msg.badges[0] == Badge(name="subscriber", icon_url="")
        assert msg.badges[1] == Badge(name="moderator", icon_url="")

    def test_subscription_system_message(self) -> None:
        data = {
            "id": "uuid-4",
            "chatroom_id": 123,
            "content": "UserX subscribed",
            "type": "subscription",
            "created_at": "2024-01-01T00:00:00.000000Z",
            "sender": {
                "id": 1,
                "username": "UserX",
                "slug": "userx",
                "identity": {"color": "", "badges": []},
            },
        }
        msg = parse_kick_event(self._make_event(data))
        assert msg is not None
        assert msg.is_system is True
        assert msg.message_type == "sub"

    def test_gifted_sub_system_message(self) -> None:
        data = {
            "id": "uuid-5",
            "chatroom_id": 123,
            "content": "UserY gifted a sub",
            "type": "gifted_subscription",
            "created_at": "2024-01-01T00:00:00.000000Z",
            "sender": {
                "id": 1,
                "username": "UserY",
                "slug": "usery",
                "identity": {"color": "", "badges": []},
            },
        }
        msg = parse_kick_event(self._make_event(data))
        assert msg is not None
        assert msg.is_system is True
        assert msg.message_type == "sub"

    def test_raid_system_message(self) -> None:
        data = {
            "id": "uuid-6",
            "chatroom_id": 123,
            "content": "Raid from UserZ",
            "type": "raid",
            "created_at": "2024-01-01T00:00:00.000000Z",
            "sender": {
                "id": 1,
                "username": "UserZ",
                "slug": "userz",
                "identity": {"color": "", "badges": []},
            },
        }
        msg = parse_kick_event(self._make_event(data))
        assert msg is not None
        assert msg.is_system is True
        assert msg.message_type == "raid"

    def test_non_chat_event_returns_none(self) -> None:
        event = {"event": "pusher:connection_established", "data": "{}"}
        assert parse_kick_event(event) is None

    def test_subscription_succeeded_returns_none(self) -> None:
        event = {
            "event": "pusher_internal:subscription_succeeded",
            "channel": "chatrooms.123.v2",
            "data": "{}",
        }
        assert parse_kick_event(event) is None

    def test_missing_sender_returns_none(self) -> None:
        data = {
            "id": "uuid-7",
            "chatroom_id": 123,
            "content": "orphan",
            "type": "message",
            "created_at": "2024-01-01T00:00:00.000000Z",
        }
        msg = parse_kick_event(self._make_event(data))
        assert msg is None

    def test_no_color_gives_none(self) -> None:
        data = {
            "id": "uuid-8",
            "chatroom_id": 123,
            "content": "hi",
            "type": "message",
            "created_at": "2024-01-01T00:00:00.000000Z",
            "sender": {
                "id": 1,
                "username": "NoColor",
                "slug": "nocolor",
                "identity": {"color": "", "badges": []},
            },
        }
        msg = parse_kick_event(self._make_event(data))
        assert msg is not None
        assert msg.author_color is None
