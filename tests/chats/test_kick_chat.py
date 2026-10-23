"""Tests for Kick Pusher chat client."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import websockets.exceptions

from core.chat import Badge, ChatMessage, Emote
from core.chats.kick_chat import KickChatClient, parse_kick_emotes, parse_kick_event


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
        assert emotes[0] == Emote(
            code="A", url="https://files.kick.com/emotes/111/fullsize", start=0, end=0
        )
        assert emotes[1] == Emote(
            code="B", url="https://files.kick.com/emotes/222/fullsize", start=6, end=6
        )

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

    def test_current_chat_message_event_shape(self) -> None:
        event = {
            "event": "App\\Events\\ChatMessageEvent",
            "data": json.dumps(
                {
                    "id": "uuid-9",
                    "chatroom_id": 123,
                    "content": "hello from 2026",
                    "type": "message",
                    "created_at": "2026-04-02T07:02:06+00:00",
                    "sender": {
                        "id": 42,
                        "username": "CurrentUser",
                        "slug": "current-user",
                        "profile_thumb": "https://files.kick.com/avatar.webp",
                        "identity": {"color": "#BC66FF", "badges": []},
                    },
                }
            ),
            "channel": "chatrooms.123.v2",
        }

        msg = parse_kick_event(event)

        assert msg is not None
        assert msg.author == "current-user"
        assert msg.author_display == "CurrentUser"
        assert msg.avatar_url == "https://files.kick.com/avatar.webp"
        assert msg.text == "hello from 2026"

    def test_reply_event_populates_reply_metadata(self) -> None:
        event = {
            "event": "App\\Events\\ChatMessageEvent",
            "data": json.dumps(
                {
                    "id": "uuid-10",
                    "chatroom_id": 123,
                    "content": "reply text",
                    "type": "reply",
                    "created_at": "2026-04-02T07:02:06+00:00",
                    "sender": {
                        "id": 42,
                        "username": "CurrentUser",
                        "slug": "current-user",
                        "identity": {"color": "#BC66FF", "badges": []},
                    },
                    "metadata": {
                        "original_sender": {"username": "Streamer"},
                        "original_message": {
                            "id": "parent-1",
                            "content": "parent text",
                        },
                    },
                }
            ),
            "channel": "chatrooms.123.v2",
        }

        msg = parse_kick_event(event)

        assert msg is not None
        assert msg.reply_to_id == "parent-1"
        assert msg.reply_to_display == "Streamer"
        assert msg.reply_to_body == "parent text"

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


def _make_kick_ws_mock(recv_side_effect: list) -> AsyncMock:
    """Create a mock websocket that yields messages then closes."""
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
async def _patch_kick_ws(mock_ws: AsyncMock):
    """Patch websockets.connect for Kick chat, one connection only."""
    call_count = 0

    @asynccontextmanager
    async def _fake_connect(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise websockets.exceptions.ConnectionClosedOK(None, None)
        yield mock_ws

    with patch("core.chats.kick_chat.websockets.connect", _fake_connect):
        yield


class TestKickChatClientInit:
    def test_initial_state(self) -> None:
        client = KickChatClient()
        assert client.platform == "kick"
        assert client._ws is None
        assert client._channel is None
        assert client._running is False
        assert client._authenticated is False


class TestKickChatClientConnect:
    async def test_connects_and_subscribes(self) -> None:
        client = KickChatClient()
        conn_msg = json.dumps(
            {
                "event": "pusher:connection_established",
                "data": json.dumps({"socket_id": "123.456", "activity_timeout": 120}),
            }
        )
        sub_ok = json.dumps(
            {
                "event": "pusher_internal:subscription_succeeded",
                "channel": "chatrooms.99.v2",
                "data": "{}",
            }
        )
        mock_ws = _make_kick_ws_mock([conn_msg, sub_ok])

        async with _patch_kick_ws(mock_ws):
            await client.connect(channel_id="testslug", chatroom_id=99)

        send_calls = [c.args[0] for c in mock_ws.send.call_args_list]
        expected_subs = {
            json.dumps(
                {
                    "event": "pusher:subscribe",
                    "data": {"channel": "chatrooms.99.v2"},
                }
            ),
            json.dumps(
                {
                    "event": "pusher:subscribe",
                    "data": {"channel": "chatrooms.99"},
                }
            ),
            json.dumps(
                {
                    "event": "pusher:subscribe",
                    "data": {"channel": "chatroom_99"},
                }
            ),
        }
        assert expected_subs.issubset(set(send_calls))

    async def test_status_callback_on_connect(self) -> None:
        client = KickChatClient()
        statuses = []
        client.on_status(lambda s: statuses.append(s.connected))

        conn_msg = json.dumps(
            {
                "event": "pusher:connection_established",
                "data": json.dumps({"socket_id": "1.2", "activity_timeout": 120}),
            }
        )
        sub_ok = json.dumps(
            {
                "event": "pusher_internal:subscription_succeeded",
                "channel": "chatrooms.1.v2",
                "data": "{}",
            }
        )
        mock_ws = _make_kick_ws_mock([conn_msg, sub_ok])

        async with _patch_kick_ws(mock_ws):
            await client.connect(channel_id="ch", chatroom_id=1)

        assert True in statuses


class TestKickChatClientDisconnect:
    async def test_disconnect_sets_running_false(self) -> None:
        client = KickChatClient()
        client._running = True
        client._ws = AsyncMock()
        await client.disconnect()
        assert client._running is False


class TestKickChatClientPing:
    async def test_pusher_ping_triggers_pong(self) -> None:
        client = KickChatClient()
        conn_msg = json.dumps(
            {
                "event": "pusher:connection_established",
                "data": json.dumps({"socket_id": "1.2", "activity_timeout": 120}),
            }
        )
        sub_ok = json.dumps(
            {
                "event": "pusher_internal:subscription_succeeded",
                "channel": "chatrooms.1.v2",
                "data": "{}",
            }
        )
        ping = json.dumps({"event": "pusher:ping"})
        mock_ws = _make_kick_ws_mock([conn_msg, sub_ok, ping])

        async with _patch_kick_ws(mock_ws):
            await client.connect(channel_id="ch", chatroom_id=1)

        send_calls = [c.args[0] for c in mock_ws.send.call_args_list]
        pong = json.dumps({"event": "pusher:pong"})
        assert pong in send_calls


class TestKickChatClientMessageCallback:
    async def test_chat_message_triggers_callback(self) -> None:
        client = KickChatClient()
        received: list[ChatMessage] = []
        client.on_message(lambda m: received.append(m))

        conn_msg = json.dumps(
            {
                "event": "pusher:connection_established",
                "data": json.dumps({"socket_id": "1.2", "activity_timeout": 120}),
            }
        )
        sub_ok = json.dumps(
            {
                "event": "pusher_internal:subscription_succeeded",
                "channel": "chatrooms.1.v2",
                "data": "{}",
            }
        )
        chat_data = {
            "id": "msg-1",
            "chatroom_id": 1,
            "content": "hello kick chat",
            "type": "message",
            "created_at": "2024-01-01T00:00:00Z",
            "sender": {
                "id": 1,
                "username": "Tester",
                "slug": "tester",
                "identity": {"color": "#FF0000", "badges": []},
            },
        }
        chat_event = json.dumps(
            {
                "event": "App\\Events\\ChatMessageSentEvent",
                "data": json.dumps(chat_data),
                "channel": "chatrooms.1.v2",
            }
        )
        mock_ws = _make_kick_ws_mock([conn_msg, sub_ok, chat_event])

        async with _patch_kick_ws(mock_ws):
            await client.connect(channel_id="ch", chatroom_id=1)

        assert len(received) == 1
        assert received[0].text == "hello kick chat"
        assert received[0].author == "tester"


class TestKickChatClientReconnect:
    async def test_reconnects_on_error(self) -> None:
        client = KickChatClient()
        statuses: list[dict] = []
        client.on_status(
            lambda s: statuses.append({"connected": s.connected, "error": s.error})
        )

        call_count = 0

        @asynccontextmanager
        async def _fake_connect(*_a: Any, **_k: Any):  # type: ignore[type-arg]
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("boom")
            if call_count == 2:
                raise ConnectionError("boom again")
            raise ConnectionError("boom 3")
            yield  # unreachable, but makes this a valid async generator

        with (
            patch("core.chats.kick_chat.websockets.connect", _fake_connect),
            patch("core.chats.base.asyncio.sleep", new_callable=AsyncMock),
        ):
            await client.connect(channel_id="ch", chatroom_id=1)

        reconnect_errors = [
            s for s in statuses if s["error"] and "Reconnecting" in s["error"]
        ]
        assert len(reconnect_errors) >= 1


class TestKickChatClientSend:
    async def test_send_without_token_returns_false(self) -> None:
        client = KickChatClient()
        client._authenticated = False
        client._running = True
        client._chatroom_id = 1
        result = await client.send_message("hello")
        assert result.ok is False
        assert result.error == "Kick chat is read-only. Re-login to send."

    async def test_send_with_token_posts_rest(self) -> None:
        client = KickChatClient()
        client._authenticated = True
        client._running = True
        client._token = "test-token"
        client._chatroom_id = 99
        client._broadcaster_user_id = 777
        client._channel = "testch"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {"message_id": "msg-1", "is_sent": True},
            "message": "OK",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("core.chats.kick_chat.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client.send_message("hello kick")

        assert result.ok is True
        assert result.message_id == "msg-1"
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs[1]["json"]["content"] == "hello kick"
        assert call_kwargs[1]["json"]["broadcaster_user_id"] == 777
        assert call_kwargs[1]["json"]["type"] == "user"
        assert "Bearer test-token" in call_kwargs[1]["headers"]["Authorization"]
        assert call_kwargs[1]["headers"]["Accept"] == "application/json"

    async def test_send_reply_includes_reply_to_message_id(self) -> None:
        client = KickChatClient()
        client._authenticated = True
        client._running = True
        client._token = "test-token"
        client._chatroom_id = 99
        client._broadcaster_user_id = 777
        client._channel = "testch"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {"message_id": "reply-1", "is_sent": True},
            "message": "OK",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("core.chats.kick_chat.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client.send_message("hello kick", reply_to="parent-1")

        assert result.ok is True
        assert (
            mock_client.post.call_args[1]["json"]["reply_to_message_id"] == "parent-1"
        )

    async def test_send_forbidden_returns_descriptive_error(self) -> None:
        client = KickChatClient()
        client._authenticated = True
        client._running = True
        client._token = "test-token"
        client._chatroom_id = 99
        client._broadcaster_user_id = 777
        client._channel = "testch"

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.json.return_value = {"data": {}, "message": "Forbidden"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("core.chats.kick_chat.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client.send_message("hello kick")

        assert result.ok is False
        assert result.error is not None
        assert "follower-only" in result.error

    async def test_send_no_chatroom_returns_false(self) -> None:
        client = KickChatClient()
        client._authenticated = True
        client._running = True
        client._token = "tok"
        client._broadcaster_user_id = None
        result = await client.send_message("hello")
        assert result.ok is False
        assert result.error is not None
        assert "metadata is incomplete" in result.error


# ── Phase 1 audit: cancel, robust frames, pusher errors, token provider ──

_CONN_OK = json.dumps(
    {
        "event": "pusher:connection_established",
        "data": json.dumps({"socket_id": "1.2", "activity_timeout": 120}),
    }
)


def _chat_frame(msg_id: str, content: str) -> str:
    return json.dumps(
        {
            "event": "App\\Events\\ChatMessageEvent",
            "channel": "chatrooms.1.v2",
            "data": json.dumps(
                {
                    "id": msg_id,
                    "content": content,
                    "type": "message",
                    "created_at": "2024-01-01T00:00:00Z",
                    "sender": {
                        "id": 1,
                        "username": "U",
                        "slug": "u",
                        "identity": {"color": "", "badges": []},
                    },
                }
            ),
        }
    )


class TestKickCancelAndGuards:
    async def test_cancel_before_connect_never_opens_socket(self) -> None:
        client = KickChatClient()
        client.cancel()
        connect = MagicMock()
        with patch("core.chats.kick_chat.websockets.connect", connect):
            await client.connect(channel_id="ch", chatroom_id=1)
        connect.assert_not_called()
        assert client._running is False

    async def test_missing_chatroom_id_does_not_subscribe(self) -> None:
        client = KickChatClient()
        statuses: list[Any] = []
        client.on_status(statuses.append)
        connect = MagicMock()
        with patch("core.chats.kick_chat.websockets.connect", connect):
            await client.connect(channel_id="ch", chatroom_id=None)
        connect.assert_not_called()
        assert statuses and statuses[-1].error == "No chatroom found"


class TestKickRobustFrames:
    async def test_garbage_frames_are_skipped(self) -> None:
        client = KickChatClient()
        received: list[ChatMessage] = []
        client.on_message(received.append)
        mock_ws = _make_kick_ws_mock(
            [
                _CONN_OK,
                "not json at all",
                json.dumps(["a", "list"]),
                json.dumps({"event": "App\\Events\\ChatMessageEvent", "data": "[1]"}),
                json.dumps(
                    {
                        "event": "App\\Events\\ChatMessageEvent",
                        "data": json.dumps({"content": "x", "sender": "oops"}),
                    }
                ),
                _chat_frame("m1", "survived"),
            ]
        )
        async with _patch_kick_ws(mock_ws):
            await client.connect(channel_id="ch", chatroom_id=1)
        assert [m.text for m in received] == ["survived"]

    def test_parse_kick_event_rejects_non_dict_data(self) -> None:
        event = {"event": "App\\Events\\ChatMessageEvent", "data": "[1, 2]"}
        assert parse_kick_event(event) is None

    def test_parse_kick_event_rejects_non_dict_sender(self) -> None:
        event = {
            "event": "App\\Events\\ChatMessageEvent",
            "data": {"content": "hi", "sender": ["nope"]},
        }
        assert parse_kick_event(event) is None

    async def test_connection_established_resets_attempt_counter(self) -> None:
        client = KickChatClient()
        mock_ws = _make_kick_ws_mock([_CONN_OK])
        with patch.object(client, "_mark_connected") as mark:
            async with _patch_kick_ws(mock_ws):
                await client.connect(channel_id="ch", chatroom_id=1)
        mark.assert_called_once()

    async def test_pusher_error_42xx_reconnects_immediately(self) -> None:
        err = json.dumps(
            {"event": "pusher:error", "data": {"code": 4200, "message": "reconnect"}}
        )
        ws1 = _make_kick_ws_mock([_CONN_OK, err])
        ws2 = _make_kick_ws_mock([_CONN_OK])
        sockets = [ws1, ws2]
        opened: list[int] = []

        @asynccontextmanager
        async def fake_connect(*_a: Any, **_k: Any):  # type: ignore[type-arg]
            opened.append(1)
            if not sockets:
                raise websockets.exceptions.ConnectionClosedOK(None, None)
            yield sockets.pop(0)

        sleep = AsyncMock()
        client = KickChatClient()
        with (
            patch("core.chats.kick_chat.websockets.connect", fake_connect),
            patch("core.chats.base.asyncio.sleep", sleep),
        ):
            await client.connect(channel_id="ch", chatroom_id=1)
        assert len(opened) == 2
        sleep.assert_not_called()


def _ok_send_mocks() -> tuple[MagicMock, AsyncMock]:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"message_id": "m", "is_sent": True}}
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    return mock_resp, mock_client


class TestKickTokenProvider:
    def _client(self, provider: Any) -> KickChatClient:
        client = KickChatClient(token_provider=provider)
        client._authenticated = True
        client._running = True
        client._token = "stale-token"
        client._broadcaster_user_id = 777
        client._channel = "testch"
        return client

    async def test_provider_token_used_for_send(self) -> None:
        provider = AsyncMock(return_value="fresh-token")
        client = self._client(provider)
        _, mock_client = _ok_send_mocks()
        with patch("core.chats.kick_chat.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client.send_message("hi")
        assert result.ok is True
        provider.assert_awaited_once()
        headers = mock_client.post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer fresh-token"

    async def test_provider_none_returns_relogin_error(self) -> None:
        provider = AsyncMock(return_value=None)
        client = self._client(provider)
        with patch("core.chats.kick_chat.httpx.AsyncClient") as mock_cls:
            result = await client.send_message("hi")
        assert result.ok is False
        assert result.error is not None
        assert "Re-login to Kick" in result.error
        mock_cls.assert_not_called()
