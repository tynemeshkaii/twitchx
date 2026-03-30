"""Tests for Twitch IRC parser and TwitchChatClient."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import websockets.exceptions

from core.chat import Badge, ChatMessage, Emote
from core.chats.twitch_chat import (
    TwitchChatClient,
    parse_badges,
    parse_emotes,
    parse_irc_message,
    parse_tags,
)

# ── parse_tags ──────────────────────────────────────────────────────


class TestParseTags:
    def test_basic(self) -> None:
        result = parse_tags("color=#FF4500;display-name=User")
        assert result == {"color": "#FF4500", "display-name": "User"}

    def test_empty_value(self) -> None:
        result = parse_tags("color=;display-name=User")
        assert result == {"color": "", "display-name": "User"}

    def test_empty_string(self) -> None:
        assert parse_tags("") == {}

    def test_escaped_space(self) -> None:
        result = parse_tags(r"system-msg=User\ssubscribed")
        assert result["system-msg"] == "User subscribed"

    def test_escaped_newline(self) -> None:
        result = parse_tags(r"msg=hello\nworld")
        assert result["msg"] == "hello\nworld"

    def test_escaped_backslash(self) -> None:
        result = parse_tags(r"msg=back\\slash")
        assert result["msg"] == "back\\slash"

    def test_single_tag(self) -> None:
        result = parse_tags("turbo=1")
        assert result == {"turbo": "1"}


# ── parse_badges ────────────────────────────────────────────────────


class TestParseBadges:
    def test_multiple(self) -> None:
        result = parse_badges("subscriber/12,premium/1")
        assert result == [
            Badge(name="subscriber/12", icon_url=""),
            Badge(name="premium/1", icon_url=""),
        ]

    def test_single(self) -> None:
        result = parse_badges("broadcaster/1")
        assert result == [Badge(name="broadcaster/1", icon_url="")]

    def test_empty(self) -> None:
        assert parse_badges("") == []


# ── parse_emotes ────────────────────────────────────────────────────


class TestParseEmotes:
    def test_single_emote(self) -> None:
        result = parse_emotes("25:0-4", "Kappa hello")
        assert len(result) == 1
        assert result[0] == Emote(
            code="Kappa",
            url="https://static-cdn.jtvnw.net/emoticons/v2/25/default/dark/1.0",
            start=0,
            end=4,
        )

    def test_multiple_emotes(self) -> None:
        result = parse_emotes("25:0-4/354:6-10", "Kappa LULxx world")
        assert len(result) == 2
        assert result[0].code == "Kappa"
        assert result[1].code == "LULxx"
        assert result[1].start == 6
        assert result[1].end == 10

    def test_same_emote_multiple_positions(self) -> None:
        result = parse_emotes("25:0-4,12-16", "Kappa hello Kappa")
        assert len(result) == 2
        assert result[0].code == "Kappa"
        assert result[1].code == "Kappa"
        assert result[1].start == 12

    def test_none_raw(self) -> None:
        assert parse_emotes(None, "hello world") == []

    def test_empty_string(self) -> None:
        assert parse_emotes("", "hello world") == []


# ── parse_irc_message ──────────────────────────────────────────────


class TestParseIrcMessage:
    def test_privmsg(self) -> None:
        line = (
            "@badge-info=subscriber/12;badges=subscriber/12,premium/1;"
            "color=#FF4500;display-name=UserName;emotes=25:0-4;"
            "id=abc123;tmi-sent-ts=1234567890123 "
            ":username!username@username.tmi.twitch.tv PRIVMSG #channel "
            ":Kappa hello world"
        )
        msg = parse_irc_message(line, "channel")
        assert msg is not None
        assert msg.platform == "twitch"
        assert msg.author == "username"
        assert msg.author_display == "UserName"
        assert msg.author_color == "#FF4500"
        assert msg.text == "Kappa hello world"
        assert msg.message_type == "text"
        assert msg.is_system is False
        assert len(msg.badges) == 2
        assert len(msg.emotes) == 1
        assert msg.timestamp == "1234567890123"

    def test_privmsg_no_tags(self) -> None:
        line = ":username!username@username.tmi.twitch.tv PRIVMSG #channel :hello"
        msg = parse_irc_message(line, "channel")
        assert msg is not None
        assert msg.author == "username"
        assert msg.text == "hello"
        assert msg.badges == []
        assert msg.emotes == []

    def test_usernotice_sub(self) -> None:
        line = (
            "@badge-info=subscriber/1;badges=subscriber/0;"
            "color=#00FF00;display-name=SubUser;"
            r"system-msg=SubUser\ssubscribed\sat\sTier\s1.;"
            "msg-id=sub;id=xyz789;tmi-sent-ts=9999999999999 "
            ":tmi.twitch.tv USERNOTICE #channel"
        )
        msg = parse_irc_message(line, "channel")
        assert msg is not None
        assert msg.is_system is True
        assert msg.message_type == "sub"
        assert msg.text == "SubUser subscribed at Tier 1."
        assert msg.author == ""
        assert msg.author_display == "SubUser"

    def test_usernotice_resub_with_message(self) -> None:
        line = (
            "@badge-info=subscriber/24;badges=subscriber/24;"
            "color=#0000FF;display-name=ResubUser;"
            r"system-msg=ResubUser\ssubscribed\sfor\s24\smonths.;"
            "msg-id=resub;id=def456;tmi-sent-ts=8888888888888 "
            ":tmi.twitch.tv USERNOTICE #channel :Thanks for the stream!"
        )
        msg = parse_irc_message(line, "channel")
        assert msg is not None
        assert msg.is_system is True
        assert msg.message_type == "sub"
        # User message takes priority over system-msg when present
        assert msg.text == "Thanks for the stream!"

    def test_usernotice_raid(self) -> None:
        line = (
            "@badge-info=;badges=;"
            "color=;display-name=RaidUser;"
            r"system-msg=5\sraiders\sfrom\sRaidUser;"
            "msg-id=raid;id=raid123;tmi-sent-ts=7777777777777 "
            ":tmi.twitch.tv USERNOTICE #channel"
        )
        msg = parse_irc_message(line, "channel")
        assert msg is not None
        assert msg.is_system is True
        assert msg.message_type == "raid"
        assert msg.text == "5 raiders from RaidUser"

    def test_usernotice_subgift(self) -> None:
        line = (
            "@badge-info=subscriber/6;badges=subscriber/6;"
            "color=#FF0000;display-name=GiftUser;"
            r"system-msg=GiftUser\sgifted\sa\ssub;"
            "msg-id=subgift;id=gift123;tmi-sent-ts=6666666666666 "
            ":tmi.twitch.tv USERNOTICE #channel"
        )
        msg = parse_irc_message(line, "channel")
        assert msg is not None
        assert msg.message_type == "sub"

    def test_ping_returns_none(self) -> None:
        assert parse_irc_message("PING :tmi.twitch.tv", "channel") is None

    def test_join_returns_none(self) -> None:
        line = ":username!username@username.tmi.twitch.tv JOIN #channel"
        assert parse_irc_message(line, "channel") is None

    def test_numeric_reply_returns_none(self) -> None:
        line = ":tmi.twitch.tv 001 justinfan12345 :Welcome, GLHF!"
        assert parse_irc_message(line, "channel") is None

    def test_empty_line_returns_none(self) -> None:
        assert parse_irc_message("", "channel") is None

    def test_privmsg_no_color(self) -> None:
        line = (
            "@badge-info=;badges=;color=;display-name=NoColor;"
            "emotes=;id=nc123;tmi-sent-ts=5555555555555 "
            ":nocolor!nocolor@nocolor.tmi.twitch.tv PRIVMSG #channel :hi"
        )
        msg = parse_irc_message(line, "channel")
        assert msg is not None
        assert msg.author_color is None


# ── TwitchChatClient ────────────────────────────────────────────────


class TestTwitchChatClientInit:
    def test_initial_state(self) -> None:
        client = TwitchChatClient()
        assert client.platform == "twitch"
        assert client._ws is None
        assert client._channel is None
        assert client._running is False
        assert client._authenticated is False


def _make_ws_mock(recv_side_effect: list[Any]) -> AsyncMock:
    """Create a mock websocket that stops the client after recv exhaustion."""
    mock_ws = AsyncMock()

    async def _recv() -> str:
        if not recv_side_effect:
            raise websockets.exceptions.ConnectionClosedOK(None, None)
        val = recv_side_effect.pop(0)
        if isinstance(val, Exception):
            raise val
        return val

    mock_ws.recv = _recv
    mock_ws.close = AsyncMock()
    mock_ws.send = AsyncMock()
    return mock_ws


@asynccontextmanager
async def _patch_ws(mock_ws: AsyncMock):  # type: ignore[type-arg]
    """Patch websockets.connect to yield a mock websocket, once only."""
    call_count = 0

    @asynccontextmanager
    async def _fake_connect(*_args: Any, **_kwargs: Any):  # type: ignore[type-arg]
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise websockets.exceptions.ConnectionClosedOK(None, None)
        yield mock_ws

    with patch("core.chats.twitch_chat.websockets.connect", _fake_connect):
        yield


class TestTwitchChatClientConnect:
    async def test_anonymous_connect(self) -> None:
        client = TwitchChatClient()
        mock_ws = _make_ws_mock([])

        async with _patch_ws(mock_ws):
            await client.connect("testchannel")

        calls = [c.args[0] for c in mock_ws.send.call_args_list]
        assert "PASS SCHMOOPIIE" in calls
        assert "NICK justinfan12345" in calls
        assert "CAP REQ :twitch.tv/tags twitch.tv/commands" in calls
        assert "JOIN #testchannel" in calls

    async def test_authenticated_connect(self) -> None:
        client = TwitchChatClient()
        mock_ws = _make_ws_mock([])

        async with _patch_ws(mock_ws):
            await client.connect("testchannel", token="mytoken", login="mylogin")

        calls = [c.args[0] for c in mock_ws.send.call_args_list]
        assert "PASS oauth:mytoken" in calls
        assert "NICK mylogin" in calls
        assert client._authenticated is True


class TestTwitchChatClientDisconnect:
    async def test_disconnect_sets_running_false(self) -> None:
        client = TwitchChatClient()
        client._running = True
        client._ws = AsyncMock()
        await client.disconnect()
        assert client._running is False


class TestTwitchChatClientSend:
    async def test_send_anonymous_returns_false(self) -> None:
        client = TwitchChatClient()
        client._authenticated = False
        client._ws = AsyncMock()
        client._channel = "test"
        result = await client.send_message("hello")
        assert result is False

    async def test_send_authenticated_returns_true(self) -> None:
        client = TwitchChatClient()
        client._authenticated = True
        client._running = True
        client._ws = AsyncMock()
        client._channel = "test"
        result = await client.send_message("hello")
        assert result is True
        client._ws.send.assert_called_once_with("PRIVMSG #test :hello")


class TestTwitchChatClientPing:
    async def test_ping_triggers_pong(self) -> None:
        client = TwitchChatClient()
        callback = MagicMock()
        client.on_message(callback)

        mock_ws = _make_ws_mock(["PING :tmi.twitch.tv"])

        async with _patch_ws(mock_ws):
            await client.connect("testchannel")

        # Check PONG was sent (after PASS, NICK, CAP, JOIN)
        send_calls = [c.args[0] for c in mock_ws.send.call_args_list]
        assert "PONG :tmi.twitch.tv" in send_calls


class TestTwitchChatClientMessageCallback:
    async def test_privmsg_triggers_callback(self) -> None:
        client = TwitchChatClient()
        received: list[ChatMessage] = []
        client.on_message(lambda msg: received.append(msg))

        irc_line = (
            "@badge-info=;badges=;color=#FF4500;display-name=TestUser;"
            "emotes=;id=msg1;tmi-sent-ts=1111111111111 "
            ":testuser!testuser@testuser.tmi.twitch.tv PRIVMSG #mychannel "
            ":hello chat"
        )

        mock_ws = _make_ws_mock([irc_line])

        async with _patch_ws(mock_ws):
            await client.connect("mychannel")

        assert len(received) == 1
        assert received[0].text == "hello chat"
        assert received[0].author == "testuser"


class TestTwitchChatClientLoginFailure:
    async def test_login_failure_falls_back_to_anonymous(self) -> None:
        """When Twitch rejects auth, client should reconnect as anonymous."""
        statuses: list[dict[str, Any]] = []

        def on_status(s: Any) -> None:
            statuses.append({"connected": s.connected, "error": s.error})

        # First connection: authenticated, gets login failure
        ws1 = AsyncMock()
        ws1.close = AsyncMock()
        ws1.send = AsyncMock()
        ws1_msgs = [":tmi.twitch.tv NOTICE * :Login unsuccessful"]

        async def ws1_recv() -> str:
            if not ws1_msgs:
                raise websockets.exceptions.ConnectionClosedOK(None, None)
            return ws1_msgs.pop(0)

        ws1.recv = ws1_recv

        # Second connection: anonymous, succeeds then closes
        ws2 = AsyncMock()
        ws2.close = AsyncMock()
        ws2.send = AsyncMock()

        async def ws2_recv() -> str:
            raise websockets.exceptions.ConnectionClosedOK(None, None)

        ws2.recv = ws2_recv

        call_count = 0

        @asynccontextmanager
        async def fake_connect(*_a: Any, **_k: Any):  # type: ignore[type-arg]
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield ws1
            elif call_count == 2:
                yield ws2
            else:
                raise websockets.exceptions.ConnectionClosedOK(None, None)

        client = TwitchChatClient()
        client.on_status(on_status)

        with patch("core.chats.twitch_chat.websockets.connect", fake_connect):
            await client.connect("testchannel", token="badtoken", login="badlogin")

        # Should have fallen back to anonymous
        assert client._authenticated is False
        assert client._login is None

        # Second connection should use anonymous creds
        ws2_calls = [c.args[0] for c in ws2.send.call_args_list]
        assert "PASS SCHMOOPIIE" in ws2_calls
        assert "NICK justinfan12345" in ws2_calls

        # Status should include the "anonymous" error
        anon_statuses = [s for s in statuses if s["error"] == "anonymous"]
        assert len(anon_statuses) >= 1
