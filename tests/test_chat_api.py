"""ChatComponent: stale-client guards, payloads, UTF-16 offsets, echo, cleanup."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.chat import ChatMessage, ChatSendResult, ChatStatus, Emote
from core.chats.kick_chat import KickChatClient, parse_kick_emotes
from core.chats.twitch_chat import TwitchChatClient, parse_emotes
from core.platforms.base import BasePlatformClient
from core.storage import DEFAULT_CONFIG, save_config
from ui.api import TwitchXApi
from ui.api.chat import _to_utf16_offset


class _NoopThread:
    def __init__(self, target: Any = None, *args: Any, **kwargs: Any) -> None:
        self._target = target or kwargs.get("target")

    def start(self) -> None:
        return None


class _InlineThread(_NoopThread):
    def start(self) -> None:
        assert callable(self._target)
        self._target()


def _msg(text: str = "hello", emotes: list[Emote] | None = None) -> ChatMessage:
    return ChatMessage(
        platform="twitch",
        author="someone",
        author_display="Someone",
        author_color=None,
        avatar_url=None,
        text=text,
        timestamp="",
        badges=[],
        emotes=emotes or [],
        is_system=False,
        message_type="text",
        raw={},
        msg_id="m-1",
    )


async def _await(awaitable: Any) -> Any:
    return await awaitable


def _payloads(calls: list[str], fn: str) -> list[dict[str, Any]]:
    prefix = f"window.{fn}("
    return [json.loads(c[len(prefix) : -1]) for c in calls if c.startswith(prefix)]


def _save_twitch_user() -> None:
    save_config(
        {
            **DEFAULT_CONFIG,
            "platforms": {
                **DEFAULT_CONFIG["platforms"],
                "twitch": {
                    **DEFAULT_CONFIG["platforms"]["twitch"],
                    "user_login": "me",
                    "user_display_name": "Me",
                },
            },
        }
    )


# ── 1.2 stale clients ──────────────────────────────────────────


class TestStaleClientGuards:
    def test_stop_chat_cancels_client_without_loop(self, temp_config_dir: Path) -> None:
        api = TwitchXApi()
        client = TwitchChatClient()
        api._chat_client = client
        api.stop_chat()
        assert client._cancelled is True

    def test_old_client_messages_dropped_after_switch(
        self,
        temp_config_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        capture_eval_js: Any,
    ) -> None:
        monkeypatch.setattr("ui.api.chat.threading.Thread", _NoopThread)
        api = TwitchXApi()
        api._eval_js = capture_eval_js
        api.start_chat("oldchan", "twitch")
        old = api._chat_client
        assert isinstance(old, TwitchChatClient)
        api.start_chat("newchan", "twitch")
        new = api._chat_client
        assert isinstance(new, TwitchChatClient) and new is not old

        assert old._message_callback is not None
        assert old._status_callback is not None
        assert old._user_list_callback is not None
        capture_eval_js.calls.clear()
        old._message_callback(_msg("ghost"))
        old._status_callback(
            ChatStatus(
                connected=True, platform="twitch", channel_id="oldchan", error=None
            )
        )
        old._user_list_callback(["ghost"])
        assert capture_eval_js.calls == []

        assert new._message_callback is not None
        new._message_callback(_msg("live"))
        msgs = _payloads(capture_eval_js.calls, "onChatMessage")
        assert [m["text"] for m in msgs] == ["live"]

    def test_message_payload_has_channel_and_platform(
        self,
        temp_config_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        capture_eval_js: Any,
    ) -> None:
        monkeypatch.setattr("ui.api.chat.threading.Thread", _NoopThread)
        api = TwitchXApi()
        api._eval_js = capture_eval_js
        api.start_chat("somechan", "twitch")
        client = api._chat_client
        assert isinstance(client, TwitchChatClient)
        assert client._message_callback is not None
        assert client._user_list_callback is not None
        client._message_callback(_msg())
        client._user_list_callback(["a", "b"])
        msg = _payloads(capture_eval_js.calls, "onChatMessage")[-1]
        assert msg["channel_id"] == "somechan"
        assert msg["platform"] == "twitch"
        users = _payloads(capture_eval_js.calls, "onChatUserList")[-1]
        assert users["channel_id"] == "somechan"
        assert users["platform"] == "twitch"


# ── 1.3 UTF-16 offsets ─────────────────────────────────────────


class TestUtf16Offsets:
    def test_helper(self) -> None:
        assert _to_utf16_offset("😀 Kappa", 2) == 3
        assert _to_utf16_offset("abc", 2) == 2

    def test_twitch_emote_after_emoji(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = TwitchXApi()
        api._eval_js = capture_eval_js
        text = "😀 Kappa"
        api._on_chat_message(_msg(text, parse_emotes("25:2-6", text)))
        emote = _payloads(capture_eval_js.calls, "onChatMessage")[-1]["emotes"][0]
        assert (emote["start"], emote["end"]) == (3, 7)
        assert "😀 Kappa".encode("utf-16-le")[6:16].decode("utf-16-le") == "Kappa"

    def test_kick_emote_after_emoji(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = TwitchXApi()
        api._eval_js = capture_eval_js
        text, emotes = parse_kick_emotes("\U0001f600 [emote:1:abc]")
        assert (emotes[0].start, emotes[0].end) == (2, 4)
        api._on_chat_message(_msg(text, emotes))
        emote = _payloads(capture_eval_js.calls, "onChatMessage")[-1]["emotes"][0]
        assert (emote["start"], emote["end"]) == (3, 5)


# ── 1.4 token providers ────────────────────────────────────────


class TestTokenProviders:
    def test_kick_chat_client_gets_token_provider(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("ui.api.chat.threading.Thread", _NoopThread)
        api = TwitchXApi()
        api.start_chat("kickchan", "kick")
        client = api._chat_client
        assert isinstance(client, KickChatClient)
        assert client._token_provider is not None

    def test_twitch_provider_ignores_app_token(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("ui.api.chat.threading.Thread", _NoopThread)
        api = TwitchXApi()
        twitch = api._platforms["twitch"]
        monkeypatch.setattr(twitch, "_ensure_token", AsyncMock(return_value="app-tok"))
        monkeypatch.setattr(twitch, "_platform_config", lambda: {"token_type": "app"})
        api.start_chat("chan", "twitch")
        client = api._chat_client
        assert isinstance(client, TwitchChatClient)
        assert client._token_provider is not None
        assert asyncio.run(_await(client._token_provider())) is None

        monkeypatch.setattr(twitch, "_platform_config", lambda: {"token_type": "user"})
        assert asyncio.run(_await(client._token_provider())) == "app-tok"


# ── 1.5 echo after USERSTATE, NOTICE rejection ─────────────────


def _send_twitch(
    api: TwitchXApi, monkeypatch: pytest.MonkeyPatch, result: ChatSendResult
) -> MagicMock:
    client = MagicMock(spec=TwitchChatClient)
    client.platform = "twitch"
    client._channel = "chan"
    client._loop = MagicMock()
    client._loop.is_closed.return_value = False
    api._chat_client = client
    future = MagicMock()
    future.result.return_value = result
    monkeypatch.setattr(api._send_pool, "submit", lambda fn: fn())
    monkeypatch.setattr(
        "asyncio.run_coroutine_threadsafe", lambda coro, loop: (coro.close(), future)[1]
    )
    return client


class TestEchoAndNotice:
    def test_echo_waits_for_userstate(
        self,
        temp_config_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        capture_eval_js: Any,
    ) -> None:
        _save_twitch_user()
        api = TwitchXApi()
        api._eval_js = capture_eval_js
        client = _send_twitch(
            api,
            monkeypatch,
            ChatSendResult(ok=True, platform="twitch", channel_id="chan"),
        )
        api.send_chat("hello there", request_id="r1")
        assert _payloads(capture_eval_js.calls, "onChatMessage") == []
        capture_eval_js.assert_any("onChatSendResult")

        api._chat._on_userstate({"color": "#FF0000", "badges": "vip/1"}, client)
        echoes = _payloads(capture_eval_js.calls, "onChatMessage")
        assert len(echoes) == 1
        echo = echoes[0]
        assert echo["text"] == "hello there"
        assert echo["is_self"] is True
        assert echo["channel_id"] == "chan"
        assert echo["platform"] == "twitch"
        assert echo["author_color"] == "#FF0000"

        # A later USERSTATE (e.g. on re-JOIN) must not duplicate the echo.
        api._chat._on_userstate({}, client)
        assert len(_payloads(capture_eval_js.calls, "onChatMessage")) == 1

    def test_rejection_notice_drops_echo_and_reports(
        self,
        temp_config_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        capture_eval_js: Any,
    ) -> None:
        _save_twitch_user()
        api = TwitchXApi()
        api._eval_js = capture_eval_js
        client = _send_twitch(
            api,
            monkeypatch,
            ChatSendResult(ok=True, platform="twitch", channel_id="chan"),
        )
        api.send_chat("too fast")
        api._chat._on_notice("msg_slowmode", "This room is in slow mode.", client)
        notices = _payloads(capture_eval_js.calls, "onChatNotice")
        assert notices == [
            {
                "channel_id": "chan",
                "platform": "twitch",
                "msg_id": "msg_slowmode",
                "text": "This room is in slow mode.",
                "failed_text": "too fast",
            }
        ]
        api._chat._on_userstate({}, client)
        assert _payloads(capture_eval_js.calls, "onChatMessage") == []

    def test_failed_send_leaves_no_pending_echo(
        self,
        temp_config_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        capture_eval_js: Any,
    ) -> None:
        _save_twitch_user()
        api = TwitchXApi()
        api._eval_js = capture_eval_js
        client = _send_twitch(
            api,
            monkeypatch,
            ChatSendResult(ok=False, platform="twitch", channel_id="chan", error="x"),
        )
        api.send_chat("lost")
        api._chat._on_userstate({}, client)
        assert _payloads(capture_eval_js.calls, "onChatMessage") == []

    def test_notice_from_stale_client_ignored(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = TwitchXApi()
        api._eval_js = capture_eval_js
        api._chat_client = TwitchChatClient()
        api._chat._on_notice("msg_slowmode", "slow", TwitchChatClient())
        assert capture_eval_js.calls == []


# ── 1.6 loop cleanup ───────────────────────────────────────────


class TestLoopCleanup:
    def test_kick_chat_thread_closes_platform_http_clients(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("ui.api.chat.threading.Thread", _InlineThread)
        api = TwitchXApi()
        kick = api._platforms["kick"]

        async def fake_info(_channel: str) -> dict[str, Any]:
            kick._get_client()  # what the real call does on the chat loop
            return {"chatroom": {"id": 5}, "broadcaster_user_id": 9}

        monkeypatch.setattr(kick, "get_channel_info", fake_info)
        monkeypatch.setattr(KickChatClient, "connect", AsyncMock())
        before = set(BasePlatformClient._loop_clients)
        api.start_chat("kickchan", "kick")
        api.stop_chat()

        leaked = [
            key
            for key in BasePlatformClient._loop_clients
            if key not in before and key[0].is_closed()
        ]
        assert leaked == []
