from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.chat import ChatMessage, ChatSendResult
from core.storage import DEFAULT_CONFIG, load_config, save_config
from ui.api import TwitchXApi


def test_add_channel_accepts_kick_url_with_hyphen(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    api = TwitchXApi()
    monkeypatch.setattr(api, "refresh", lambda: None)

    api.add_channel("https://kick.com/train-wreck", platform="kick")

    config = load_config()
    assert config["favorites"] == [
        {
            "platform": "kick",
            "login": "train-wreck",
            "display_name": "train-wreck",
        }
    ]


def test_get_config_exposes_existing_kick_profile_without_login(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    config = {
        **DEFAULT_CONFIG,
        "platforms": {
            **DEFAULT_CONFIG["platforms"],
            "kick": {
                **DEFAULT_CONFIG["platforms"]["kick"],
                "user_login": "",
                "user_display_name": "Kick User",
            },
        },
    }
    save_config(config)

    api = TwitchXApi()
    masked = api.get_config()

    assert masked["kick_user"] == {
        "login": "",
        "display_name": "Kick User",
    }


def test_get_config_exposes_kick_scopes(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    config = {
        **DEFAULT_CONFIG,
        "platforms": {
            **DEFAULT_CONFIG["platforms"],
            "kick": {
                **DEFAULT_CONFIG["platforms"]["kick"],
                "oauth_scopes": "user:read channel:read",
            },
        },
    }
    save_config(config)

    api = TwitchXApi()
    masked = api.get_config()

    assert masked["kick_scopes"] == "user:read channel:read"


def test_kick_search_does_not_require_saved_credentials(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    api = TwitchXApi()
    emitted: list[str] = []

    async def fake_search(query: str) -> list[dict[str, object]]:
        assert query == "train"
        return [
            {
                "slug": "train-wreck",
                "username": "Train Wreck",
                "is_live": True,
                "category": {"name": "Slots"},
            }
        ]

    monkeypatch.setattr(api._kick, "search_channels", fake_search)
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.search_channels("train", platform="kick")

    assert emitted
    assert "train-wreck" in emitted[-1]


def test_search_channels_all_combines_kick_and_twitch_results(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    config = {
        **DEFAULT_CONFIG,
        "platforms": {
            **DEFAULT_CONFIG["platforms"],
            "twitch": {
                **DEFAULT_CONFIG["platforms"]["twitch"],
                "client_id": "tw_id",
                "client_secret": "tw_secret",
            },
        },
    }
    save_config(config)

    api = TwitchXApi()
    emitted: list[str] = []

    async def fake_kick_search(query: str) -> list[dict[str, object]]:
        assert query == "train"
        return [{"slug": "trainwreckstv", "username": "Trainwreckstv", "is_live": True}]

    async def fake_twitch_search(query: str) -> list[dict[str, object]]:
        assert query == "train"
        return [
            {"broadcaster_login": "train", "display_name": "Train", "is_live": False}
        ]

    monkeypatch.setattr(api._kick, "search_channels", fake_kick_search)
    monkeypatch.setattr(api._twitch, "search_channels", fake_twitch_search)
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.search_channels("train", platform="all")

    assert emitted
    payload = emitted[-1].split("window.onSearchResults(", 1)[1].rsplit(")", 1)[0]
    results = json.loads(payload)
    assert {(item["platform"], item["login"]) for item in results} == {
        ("kick", "trainwreckstv"),
        ("twitch", "train"),
    }


@pytest.mark.asyncio
async def test_build_kick_stream_item_maps_current_public_payload() -> None:
    from core.platforms.kick import KickClient

    client = KickClient()
    item = await client.normalize_stream_item(
        {
            "slug": "vitaly",
            "stream_title": "CATCHING CHILD PREDATORS!",
            "thumbnail": "https://images.kick.com/video_thumbnails/test/480.webp",
            "started_at": "2026-04-02T02:02:36Z",
            "viewer_count": 18275,
            "broadcaster_user_id": 21725177,
            "channel_id": 20736988,
            "category": {"name": "IRL"},
        }
    )

    assert item["login"] == "vitaly"
    assert item["title"] == "CATCHING CHILD PREDATORS!"
    assert item["thumbnail_url"].endswith("/480.webp")
    assert item["game"] == "IRL"
    assert item["broadcaster_user_id"] == 21725177


def test_save_settings_clears_credentials_when_empty(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    config = {
        **DEFAULT_CONFIG,
        "platforms": {
            **DEFAULT_CONFIG["platforms"],
            "twitch": {
                **DEFAULT_CONFIG["platforms"]["twitch"],
                "client_id": "tw_id",
                "client_secret": "tw_secret",
            },
            "kick": {
                **DEFAULT_CONFIG["platforms"]["kick"],
                "client_id": "kick_id",
                "client_secret": "kick_secret",
            },
            "youtube": {
                **DEFAULT_CONFIG["platforms"]["youtube"],
                "api_key": "yt_key",
                "client_id": "yt_cid",
                "client_secret": "yt_cs",
            },
        },
    }
    save_config(config)

    api = TwitchXApi()
    monkeypatch.setattr(api, "start_polling", lambda interval: None)
    monkeypatch.setattr(api, "_eval_js", lambda code: None)

    api.save_settings(
        json.dumps(
            {
                "client_id": "",
                "client_secret": "",
                "kick_client_id": "",
                "kick_client_secret": "",
                "youtube_api_key": "",
                "youtube_client_id": "",
                "youtube_client_secret": "",
                "refresh_interval": 60,
                "streamlink_path": "streamlink",
                "iina_path": "/Applications/IINA.app/Contents/MacOS/iina-cli",
            }
        )
    )

    stored = load_config()
    assert stored["platforms"]["twitch"]["client_id"] == ""
    assert stored["platforms"]["twitch"]["client_secret"] == ""
    assert stored["platforms"]["kick"]["client_id"] == ""
    assert stored["platforms"]["kick"]["client_secret"] == ""
    assert stored["platforms"]["youtube"]["api_key"] == ""
    assert stored["platforms"]["youtube"]["client_id"] == ""
    assert stored["platforms"]["youtube"]["client_secret"] == ""


def test_save_settings_partial_credential_clear(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    config = {
        **DEFAULT_CONFIG,
        "platforms": {
            **DEFAULT_CONFIG["platforms"],
            "twitch": {
                **DEFAULT_CONFIG["platforms"]["twitch"],
                "client_id": "old_id",
                "client_secret": "old_secret",
            },
        },
    }
    save_config(config)

    api = TwitchXApi()
    monkeypatch.setattr(api, "start_polling", lambda interval: None)
    monkeypatch.setattr(api, "_eval_js", lambda code: None)

    api.save_settings(
        json.dumps(
            {
                "client_id": "",
                "client_secret": "new_secret",
                "refresh_interval": 60,
                "streamlink_path": "streamlink",
            }
        )
    )

    stored = load_config()
    assert stored["platforms"]["twitch"]["client_id"] == ""
    assert stored["platforms"]["twitch"]["client_secret"] == "new_secret"


def test_add_channel_emits_duplicate_warning_without_refresh(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    save_config(
        {
            **DEFAULT_CONFIG,
            "favorites": [
                {
                    "platform": "kick",
                    "login": "chessbrah",
                    "display_name": "chessbrah",
                }
            ],
        }
    )

    api = TwitchXApi()
    emitted: list[str] = []
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))
    monkeypatch.setattr(api, "refresh", lambda: emitted.append("refresh"))

    api.add_channel("https://kick.com/chessbrah", platform="kick")

    assert "refresh" not in emitted
    assert any("already in Kick favorites" in code for code in emitted)


def test_watch_uses_kick_platform_for_kick_stream(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    api = TwitchXApi()
    api._live_streams = [
        {
            "login": "train-wreck",
            "title": "Kick stream",
            "platform": "kick",
        }
    ]

    captured: dict[str, str] = {}
    emitted: list[str] = []

    def fake_resolve(
        channel: str,
        quality: str,
        streamlink_path: str = "streamlink",
        platform_client=None,
        extra_args=None,
    ) -> tuple[str | None, str]:
        captured["channel"] = channel
        captured["quality"] = quality
        captured["platform"] = platform_client.PLATFORM_ID if platform_client else ""
        return ("https://example.com/kick.m3u8", "")

    monkeypatch.setattr("ui.api.streams.resolve_hls_url", fake_resolve)
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))
    monkeypatch.setattr(api._streams, "_start_launch_timer", lambda: None)
    monkeypatch.setattr(api._streams, "_cancel_launch_timer", lambda: None)
    monkeypatch.setattr(api, "start_chat", lambda channel, platform: None)

    api.watch("train-wreck", "best")

    assert captured["platform"] == "kick"
    assert any("onStreamReady" in code for code in emitted)


def test_watch_is_noop_when_already_watching_same_channel(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    api._watching_channel = "shroud"
    api._live_streams = [
        {
            "login": "shroud",
            "title": "Test stream",
            "platform": "twitch",
        }
    ]

    emitted: list[str] = []
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.watch("shroud", "best")

    assert not any("onStreamReady" in code for code in emitted)
    assert any("Already watching" in code for code in emitted)
    assert api._watching_channel == "shroud"


def test_watch_is_noop_case_insensitive(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    api._watching_channel = "Shroud"
    api._live_streams = [
        {
            "login": "shroud",
            "title": "Test stream",
            "platform": "twitch",
        }
    ]

    emitted: list[str] = []
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.watch("shroud", "best")

    assert not any("onStreamReady" in code for code in emitted)
    assert any("Already watching" in code for code in emitted)
    assert api._watching_channel == "Shroud"


def test_watch_starts_new_session_after_ending_previous(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    api._live_streams = [
        {"login": "one", "title": "First", "platform": "twitch"},
        {"login": "two", "title": "Second", "platform": "twitch"},
    ]
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: None)
    monkeypatch.setattr(api._streams, "_start_launch_timer", lambda: None)
    monkeypatch.setattr(api._streams, "_cancel_launch_timer", lambda: None)
    monkeypatch.setattr(api, "start_chat", lambda channel, platform: None)
    monkeypatch.setattr(
        "ui.api.streams.resolve_hls_url",
        lambda channel, quality, streamlink_path, platform_client=None, extra_args=None: (
            f"https://example.com/{channel}.m3u8",
            "",
        ),
    )

    api.watch("one", "best")
    first_session = api._active_watch_session
    api._watching_channel = None
    api.watch("two", "best")

    recent = api._watch_stats.get_recent_sessions(10)
    first = next(row for row in recent if row["id"] == first_session)
    assert first["ended_at"] is not None
    assert api._active_watch_session != first_session


def test_watch_ignores_late_resolver_after_launch_invalidated(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    api._live_streams = [{"login": "shroud", "title": "Live", "platform": "twitch"}]
    emitted: list[str] = []

    def fake_resolve(
        channel: str,
        quality: str,
        streamlink_path: str = "streamlink",
        platform_client=None,
        extra_args=None,
    ) -> tuple[str, str]:
        api._launch_id += 1
        return "https://example.com/late.m3u8", ""

    monkeypatch.setattr("ui.api.streams.resolve_hls_url", fake_resolve)
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))
    monkeypatch.setattr(api._streams, "_start_launch_timer", lambda: None)
    monkeypatch.setattr(api._streams, "_cancel_launch_timer", lambda: None)

    api.watch("shroud", "best")

    assert not any("onStreamReady" in code for code in emitted)
    assert api._watching_channel is None


def test_watch_media_resolves_original_media_url(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    captured: dict[str, str] = {}
    emitted: list[str] = []

    def fake_resolve(
        channel: str,
        quality: str,
        streamlink_path: str = "streamlink",
        platform_client=None,
        extra_args=None,
    ) -> tuple[str, str]:
        captured["channel"] = channel
        return "https://example.com/vod.m3u8", ""

    monkeypatch.setattr("ui.api.streams.resolve_hls_url", fake_resolve)
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))
    monkeypatch.setattr(api._streams, "_start_launch_timer", lambda: None)
    monkeypatch.setattr(api._streams, "_cancel_launch_timer", lambda: None)

    api.watch_media(
        "https://www.twitch.tv/videos/123",
        "best",
        platform="twitch",
        channel="xqc",
        title="VOD",
    )

    assert captured["channel"] == "https://www.twitch.tv/videos/123"
    assert any("onStreamReady" in code for code in emitted)


def test_watch_external_uses_kick_platform_for_kick_stream(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    api = TwitchXApi()
    api._live_streams = [
        {
            "login": "train-wreck",
            "title": "Kick stream",
            "platform": "kick",
        }
    ]

    captured: dict[str, str] = {}
    emitted: list[str] = []

    class Result:
        success = True
        message = "ok"

    def fake_launch(
        channel: str,
        quality: str,
        streamlink_path: str = "streamlink",
        iina_path: str = "",
        platform_client=None,
        extra_args=None,
    ) -> Result:
        captured["channel"] = channel
        captured["quality"] = quality
        captured["platform"] = platform_client.PLATFORM_ID if platform_client else ""
        return Result()

    monkeypatch.setattr("ui.api.streams.launch_stream", fake_launch)
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.watch_external("train-wreck", "best")

    assert captured["platform"] == "kick"
    assert any("onLaunchResult" in code for code in emitted)


def test_start_chat_kick_uses_chatroom_and_scope_for_send_auth(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    config = {
        **DEFAULT_CONFIG,
        "platforms": {
            **DEFAULT_CONFIG["platforms"],
            "kick": {
                **DEFAULT_CONFIG["platforms"]["kick"],
                "access_token": "kick-token",
                "oauth_scopes": "user:read channel:read chat:write",
                "user_login": "kick-user",
                "user_display_name": "Kick User",
            },
        },
    }
    save_config(config)

    api = TwitchXApi()
    captured: dict[str, object] = {}

    async def fake_channel_info(_channel: str) -> dict[str, object]:
        return {
            "chatroom": {"id": 20466645},
            "broadcaster_user_id": 21725177,
        }

    async def fake_connect(
        channel_id: str,
        token: str | None = None,
        chatroom_id: int | None = None,
        broadcaster_user_id: int | None = None,
        can_send: bool | None = None,
    ) -> None:
        captured["channel_id"] = channel_id
        captured["token"] = token
        captured["chatroom_id"] = chatroom_id
        captured["broadcaster_user_id"] = broadcaster_user_id
        captured["can_send"] = can_send

    monkeypatch.setattr(api._kick, "get_channel_info", fake_channel_info)
    monkeypatch.setattr(api._chat, "_on_chat_status", lambda status: None)

    class FakeKickChatClient:
        platform = "kick"

        def on_message(self, _callback: object) -> None:
            return None

        def on_status(self, _callback: object) -> None:
            return None

        async def connect(
            self,
            channel_id: str,
            token: str | None = None,
            chatroom_id: int | None = None,
            broadcaster_user_id: int | None = None,
            can_send: bool | None = None,
        ) -> None:
            await fake_connect(
                channel_id,
                token=token,
                chatroom_id=chatroom_id,
                broadcaster_user_id=broadcaster_user_id,
                can_send=can_send,
            )

    class InlineThread:
        def __init__(
            self, target: object | None = None, *args: object, **kwargs: object
        ) -> None:
            self._target = target or kwargs.get("target")

        def start(self) -> None:
            assert callable(self._target)
            self._target()

    monkeypatch.setattr("ui.api.chat.KickChatClient", FakeKickChatClient)
    monkeypatch.setattr("threading.Thread", InlineThread)

    api.start_chat("vitaly", platform="kick")

    assert captured["channel_id"] == "vitaly"
    assert captured["chatroom_id"] == 20466645
    assert captured["broadcaster_user_id"] == 21725177
    assert captured["can_send"] is True


def test_send_chat_kick_emits_send_result_without_local_echo(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    config = {
        **DEFAULT_CONFIG,
        "platforms": {
            **DEFAULT_CONFIG["platforms"],
            "kick": {
                **DEFAULT_CONFIG["platforms"]["kick"],
                "user_login": "kick-user",
                "user_display_name": "Kick User",
            },
        },
    }
    save_config(config)

    api = TwitchXApi()
    emitted: list[str] = []
    api._eval_js = lambda code: emitted.append(code)

    class FakeKickChatClient:
        platform = "kick"
        _channel = "trainwreckstv"
        _loop = type("Loop", (), {"is_closed": lambda self: False})()

        async def send_message(
            self, text: str, reply_to: str | None = None
        ) -> ChatSendResult:
            assert text == "hello kick"
            assert reply_to == "parent-1"
            return ChatSendResult(
                ok=True,
                platform="kick",
                channel_id="trainwreckstv",
                message_id="kick-msg-1",
            )

    def fake_run_coroutine_threadsafe(coro: object, _loop: object) -> object:
        class FakeFuture:
            def result(self, timeout: float | None = None) -> ChatSendResult:
                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(coro)  # type: ignore[arg-type]
                finally:
                    loop.close()

        return FakeFuture()

    api._chat_client = FakeKickChatClient()  # type: ignore[assignment]
    monkeypatch.setattr(api._send_pool, "submit", lambda fn: fn())
    monkeypatch.setattr(
        "asyncio.run_coroutine_threadsafe", fake_run_coroutine_threadsafe
    )

    api.send_chat(
        "hello kick",
        reply_to="parent-1",
        reply_display="Streamer",
        reply_body="parent body",
        request_id="req-1",
    )

    assert any("window.onChatSendResult" in code for code in emitted)
    assert any('"message_id": "kick-msg-1"' in code for code in emitted)
    assert not any("window.onChatMessage" in code for code in emitted)


def test_send_chat_kick_failure_emits_error_result(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    api = TwitchXApi()
    emitted: list[str] = []
    api._eval_js = lambda code: emitted.append(code)

    class FakeKickChatClient:
        platform = "kick"
        _channel = "trainwreckstv"
        _loop = type("Loop", (), {"is_closed": lambda self: False})()

        async def send_message(
            self, text: str, reply_to: str | None = None
        ) -> ChatSendResult:
            return ChatSendResult(
                ok=False,
                platform="kick",
                channel_id="trainwreckstv",
                error="Kick blocked this message.",
            )

    def fake_run_coroutine_threadsafe(coro: object, _loop: object) -> object:
        class FakeFuture:
            def result(self, timeout: float | None = None) -> ChatSendResult:
                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(coro)  # type: ignore[arg-type]
                finally:
                    loop.close()

        return FakeFuture()

    api._chat_client = FakeKickChatClient()  # type: ignore[assignment]
    monkeypatch.setattr(api._send_pool, "submit", lambda fn: fn())
    monkeypatch.setattr(
        "asyncio.run_coroutine_threadsafe", fake_run_coroutine_threadsafe
    )

    api.send_chat("hello kick", request_id="req-2")

    assert any("window.onChatSendResult" in code for code in emitted)
    assert any("Kick blocked this message." in code for code in emitted)
    assert not any("window.onChatMessage" in code for code in emitted)


def test_on_chat_message_marks_own_kick_messages_as_self(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    config = {
        **DEFAULT_CONFIG,
        "platforms": {
            **DEFAULT_CONFIG["platforms"],
            "kick": {
                **DEFAULT_CONFIG["platforms"]["kick"],
                "user_login": "kick-user",
                "user_display_name": "Kick User",
            },
        },
    }
    save_config(config)

    api = TwitchXApi()
    emitted: list[str] = []
    api._eval_js = lambda code: emitted.append(code)

    api._on_chat_message(
        ChatMessage(
            platform="kick",
            author="kick-user",
            author_display="Kick User",
            author_color="#fff",
            avatar_url=None,
            text="hello",
            timestamp="2026-04-02T08:00:00Z",
            badges=[],
            emotes=[],
            is_system=False,
            message_type="text",
            raw={},
            msg_id="msg-1",
        )
    )

    assert emitted
    assert '"is_self": true' in emitted[-1]


class TestFetchLock:
    def test_concurrent_refresh_is_no_op(self, temp_config_dir, monkeypatch) -> None:
        """A second refresh() while one is in progress must be a no-op."""

        from core.storage import DEFAULT_CONFIG, save_config

        cfg = {
            **DEFAULT_CONFIG,
            "favorites": [
                {"platform": "twitch", "login": "somestreamer", "display_name": "some"}
            ],
            "platforms": {
                **DEFAULT_CONFIG["platforms"],
                "twitch": {
                    **DEFAULT_CONFIG["platforms"]["twitch"],
                    "client_id": "x",
                    "client_secret": "y",
                },
            },
        }
        save_config(cfg)

        from ui.api import TwitchXApi

        api = TwitchXApi()
        api._window = None  # suppress eval_js

        call_count = 0
        fetch_started = threading.Event()
        fetch_proceed = threading.Event()

        original_fetch = api._data._fetch_data

        def slow_fetch(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            fetch_started.set()
            fetch_proceed.wait(timeout=2)
            original_fetch(*args, **kwargs)

        monkeypatch.setattr(api._data, "_fetch_data", slow_fetch)

        t = threading.Thread(target=api.refresh)
        t.start()
        assert fetch_started.wait(timeout=2), "slow_fetch did not start in time"

        # Second refresh while first is in progress — must be a no-op
        api.refresh()

        fetch_proceed.set()
        t.join(timeout=5)

        assert call_count == 1, f"Expected 1 fetch, got {call_count}"


class TestPollLock:
    def test_concurrent_start_polling_creates_one_timer(
        self, temp_config_dir, monkeypatch
    ) -> None:
        """Concurrent start_polling calls must result in exactly one active timer chain."""

        from ui.api import TwitchXApi

        api = TwitchXApi()
        api._window = None
        monkeypatch.setattr(api, "refresh", lambda: None)

        timer_starts: list[threading.Timer] = []
        original_timer = threading.Timer

        def tracking_timer(interval, fn, *args, **kwargs):
            t = original_timer(interval, fn, *args, **kwargs)
            timer_starts.append(t)
            return t

        monkeypatch.setattr(threading, "Timer", tracking_timer)

        barrier = threading.Barrier(3)

        def call_start():
            barrier.wait()
            api.start_polling(interval_seconds=9999)

        threads = [threading.Thread(target=call_start) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # Only one Timer must have been created and started
        started = [t for t in timer_starts if t.is_alive()]
        assert len(started) == 1, (
            f"Expected 1 active timer, got {len(started)}: {started}"
        )
        api.stop_polling()


class TestAsyncFetchIsolation:
    def test_twitch_error_does_not_discard_kick_streams(
        self, temp_config_dir, monkeypatch
    ) -> None:
        """If Twitch raises, Kick results must still be returned."""

        from core.storage import DEFAULT_CONFIG, save_config

        cfg = {
            **DEFAULT_CONFIG,
            "platforms": {
                **DEFAULT_CONFIG["platforms"],
                "twitch": {
                    **DEFAULT_CONFIG["platforms"]["twitch"],
                    "client_id": "fakeid",
                    "client_secret": "fakesecret",
                },
            },
        }
        save_config(cfg)

        from ui.api import TwitchXApi

        api = TwitchXApi()

        fake_kick_stream = {"slug": "streamer", "viewer_count": 100}

        async def run():
            with (
                patch.object(
                    api._twitch, "_ensure_token", side_effect=Exception("Twitch down")
                ),
                patch.object(
                    api._kick,
                    "get_live_streams",
                    return_value=[fake_kick_stream],
                ),
            ):
                _, _, kick, _, _ = await api._data._async_fetch(
                    twitch_favorites=["somestreamer"],
                    kick_favorites=["streamer"],
                )
            return kick

        loop = asyncio.new_event_loop()
        kick_results = loop.run_until_complete(run())
        loop.close()

        assert kick_results == [fake_kick_stream]

    def test_twitch_timeout_does_not_discard_kick_streams(
        self, temp_config_dir, monkeypatch
    ) -> None:
        """If Twitch times out, Kick results must still be returned."""

        from core.storage import DEFAULT_CONFIG, save_config

        cfg = {
            **DEFAULT_CONFIG,
            "platforms": {
                **DEFAULT_CONFIG["platforms"],
                "twitch": {
                    **DEFAULT_CONFIG["platforms"]["twitch"],
                    "client_id": "fakeid",
                    "client_secret": "fakesecret",
                },
            },
        }
        save_config(cfg)

        from ui.api import TwitchXApi

        api = TwitchXApi()

        fake_kick_stream = {"slug": "streamer", "viewer_count": 50}

        async def slow_token():
            await asyncio.sleep(999)

        async def run():
            # side_effect on an async method: mock calls slow_token() and awaits the coroutine.
            # asyncio.wait_for with _twitch_timeout=0.05 cancels it, raising asyncio.TimeoutError.
            with (
                patch.object(api._twitch, "_ensure_token", side_effect=slow_token),
                patch.object(
                    api._kick,
                    "get_live_streams",
                    return_value=[fake_kick_stream],
                ),
            ):
                _, _, kick, _, _ = await api._data._async_fetch(
                    twitch_favorites=["somestreamer"],
                    kick_favorites=["streamer"],
                    _twitch_timeout=0.05,
                )
            return kick

        loop = asyncio.new_event_loop()
        kick_results = loop.run_until_complete(run())
        loop.close()

        assert kick_results == [fake_kick_stream]


class TestParallelFetch:
    """Verify asyncio.gather parallel fetch: independent errors per platform."""

    def _setup(self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:

        from core.storage import DEFAULT_CONFIG, save_config

        cfg = {
            **DEFAULT_CONFIG,
            "platforms": {
                **DEFAULT_CONFIG["platforms"],
                "twitch": {
                    **DEFAULT_CONFIG["platforms"]["twitch"],
                    "client_id": "fakeid",
                    "client_secret": "fakesecret",
                },
            },
        }
        save_config(cfg)

    def test_twitch_cache_used_on_connect_error(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ConnectError → _last_twitch_streams returned, twitch_error set."""
        self._setup(temp_config_dir, monkeypatch)
        import httpx

        from ui.api import TwitchXApi

        api = TwitchXApi()
        cached = [{"user_login": "cached_streamer", "platform": "twitch"}]
        api._last_twitch_streams = list(cached)

        async def run():
            with patch.object(
                api._twitch, "_ensure_token", side_effect=httpx.ConnectError("down")
            ):
                return await api._data._async_fetch(
                    twitch_favorites=["cached_streamer"],
                    kick_favorites=[],
                )

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(run())
        loop.close()

        twitch_streams, _, _, _, twitch_error = result
        assert twitch_streams == cached
        assert isinstance(twitch_error, httpx.ConnectError)

    def test_twitch_cache_updated_on_success(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Successful Twitch fetch updates _last_twitch_streams; twitch_error is None."""
        self._setup(temp_config_dir, monkeypatch)
        from ui.api import TwitchXApi

        api = TwitchXApi()
        fresh = [{"user_login": "live_streamer", "platform": "twitch"}]

        async def run():
            with (
                patch.object(api._twitch, "_ensure_token", return_value=None),
                patch.object(api._twitch, "get_live_streams", return_value=fresh),
                patch.object(api._twitch, "get_users", return_value=[]),
            ):
                return await api._data._async_fetch(
                    twitch_favorites=["live_streamer"],
                    kick_favorites=[],
                )

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(run())
        loop.close()

        twitch_streams, _, _, _, twitch_error = result
        assert twitch_streams == fresh
        assert twitch_error is None
        assert api._last_twitch_streams == fresh

    def test_twitch_timeout_sets_error_to_none(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Twitch TimeoutError → twitch_error=None (timeout is non-retriable)."""
        self._setup(temp_config_dir, monkeypatch)
        from ui.api import TwitchXApi

        api = TwitchXApi()

        async def slow_token():
            await asyncio.sleep(999)

        async def run():
            with patch.object(api._twitch, "_ensure_token", side_effect=slow_token):
                return await api._data._async_fetch(
                    twitch_favorites=["somestreamer"],
                    kick_favorites=[],
                    _twitch_timeout=0.05,
                )

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(run())
        loop.close()

        _, _, _, _, twitch_error = result
        assert twitch_error is None

    def test_youtube_cache_served_when_twitch_fails(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """YouTube _last_youtube_streams served even when Twitch raises ConnectError."""
        self._setup(temp_config_dir, monkeypatch)
        import time

        import httpx

        from ui.api import TwitchXApi

        api = TwitchXApi()
        fake_yt = [{"login": "UCfakechannel1234567890", "platform": "youtube"}]
        api._last_youtube_streams = list(fake_yt)
        api._last_youtube_fetch = time.time()  # just fetched → cache hit, no API call

        async def run():
            with patch.object(
                api._twitch, "_ensure_token", side_effect=httpx.ConnectError("down")
            ):
                return await api._data._async_fetch(
                    twitch_favorites=["somestreamer"],
                    kick_favorites=[],
                    youtube_favorites=["UCfakechannel1234567890"],
                )

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(run())
        loop.close()

        _, _, _, youtube_streams, twitch_error = result
        assert youtube_streams == fake_yt
        assert isinstance(twitch_error, httpx.ConnectError)


class TestAddMultiSlot:
    def test_success_emits_onMultiSlotReady(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        emitted: list[str] = []
        monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
        monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))
        monkeypatch.setattr(
            "ui.api.streams.resolve_hls_url",
            lambda ch, q, sl, platform_client=None, extra_args=None: ("https://hls.example.com/s.m3u8", ""),
        )

        api.add_multi_slot(0, "xqc", "twitch", "best")

        assert len(emitted) == 1
        assert "onMultiSlotReady" in emitted[0]
        payload = json.loads(emitted[0].split("(", 1)[1].rstrip(")"))
        assert payload["slot_idx"] == 0
        assert payload["url"] == "https://hls.example.com/s.m3u8"
        assert payload["channel"] == "xqc"
        assert payload["platform"] == "twitch"
        assert "error" not in payload

    def test_resolve_error_emits_error_payload(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        emitted: list[str] = []
        monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
        monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))
        monkeypatch.setattr(
            "ui.api.streams.resolve_hls_url",
            lambda ch, q, sl, platform_client=None, extra_args=None: (None, "streamlink not found"),
        )

        api.add_multi_slot(2, "ninja", "twitch", "720p")

        assert len(emitted) == 1
        payload = json.loads(emitted[0].split("(", 1)[1].rstrip(")"))
        assert payload["slot_idx"] == 2
        assert "error" in payload
        assert "url" not in payload

    def test_out_of_range_slot_idx_is_noop(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        emitted: list[str] = []
        monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
        monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

        api.add_multi_slot(4, "xqc", "twitch", "best")

        assert emitted == []

    def test_negative_slot_idx_is_noop(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        emitted: list[str] = []
        monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
        monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

        api.add_multi_slot(-1, "xqc", "twitch", "best")

        assert emitted == []

    def test_title_populated_from_live_streams_cache(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        api._live_streams = [
            {"login": "xqc", "platform": "twitch", "title": "Gaming Session"}
        ]
        emitted: list[str] = []
        monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
        monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))
        monkeypatch.setattr(
            "ui.api.streams.resolve_hls_url",
            lambda ch, q, sl, platform_client=None, extra_args=None: ("https://hls.example.com/s.m3u8", ""),
        )

        api.add_multi_slot(0, "xqc", "twitch", "best")

        payload = json.loads(emitted[0].split("(", 1)[1].rstrip(")"))
        assert payload["title"] == "Gaming Session"

    def test_kick_slot_passes_kick_platform_to_resolver(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        emitted: list[str] = []
        captured: dict[str, str] = {}
        monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
        monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

        def fake_resolve(
            ch: str, q: str, sl: str, platform_client=None, extra_args=None
        ) -> tuple[str, str]:
            captured["platform"] = (
                platform_client.PLATFORM_ID if platform_client else ""
            )
            return "https://hls.example.com/s.m3u8", ""

        monkeypatch.setattr("ui.api.streams.resolve_hls_url", fake_resolve)

        api.add_multi_slot(1, "xqcow", "kick", "best")

        assert captured["platform"] == "kick"
        payload = json.loads(emitted[0].split("(", 1)[1].rstrip(")"))
        assert payload["platform"] == "kick"

    def test_youtube_slot_preserves_channel_id_case_for_lookup(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        api._live_streams = [
            {
                "login": "UCAbCdEfGhIjKlMnOpQrStU",
                "platform": "youtube",
                "title": "Live",
                "video_id": "abc123def45",
            }
        ]
        emitted: list[str] = []
        captured: dict[str, str] = {}
        monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
        monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

        def fake_resolve(
            ch: str, q: str, sl: str, platform_client=None, extra_args=None
        ) -> tuple[str, str]:
            captured["channel"] = ch
            return "https://hls.example.com/yt.m3u8", ""

        monkeypatch.setattr("ui.api.streams.resolve_hls_url", fake_resolve)

        api.add_multi_slot(0, "UCAbCdEfGhIjKlMnOpQrStU", "youtube", "best")

        assert captured["channel"] == "abc123def45"
        payload = json.loads(emitted[0].split("(", 1)[1].rstrip(")"))
        assert "error" not in payload


def test_refresh_no_favorites_reports_kick_credentials(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = {
        **DEFAULT_CONFIG,
        "platforms": {
            **DEFAULT_CONFIG["platforms"],
            "kick": {
                **DEFAULT_CONFIG["platforms"]["kick"],
                "client_id": "kick_id",
                "client_secret": "kick_secret",
            },
        },
    }
    save_config(config)

    api = TwitchXApi()
    emitted: list[str] = []
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.refresh()

    payload = json.loads(emitted[-1].split("window.onStreamsUpdate(", 1)[1].rstrip(")"))
    assert payload["has_credentials"] is True


def test_get_config_includes_pip_and_shortcuts(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    cfg = api.get_config()
    assert "pip_enabled" in cfg
    assert cfg["pip_enabled"] is False
    assert "keyboard_shortcuts" in cfg
    assert cfg["keyboard_shortcuts"]["refresh"] == "r"
    assert cfg["keyboard_shortcuts"]["pip"] == "p"


def test_get_full_config_for_settings_includes_pip_and_shortcuts(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    cfg = api.get_full_config_for_settings()
    assert "pip_enabled" in cfg
    assert cfg["pip_enabled"] is False
    assert "keyboard_shortcuts" in cfg
    assert cfg["keyboard_shortcuts"]["refresh"] == "r"
    assert cfg["keyboard_shortcuts"]["mute"] == "m"


def test_save_settings_persists_pip_enabled_and_shortcuts(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    monkeypatch.setattr(api, "start_polling", lambda interval: None)
    monkeypatch.setattr(api, "_eval_js", lambda code: None)

    api.save_settings(
        json.dumps(
            {
                "pip_enabled": True,
                "keyboard_shortcuts": {"refresh": "g", "mute": "n"},
            }
        )
    )

    stored = load_config()
    settings = stored["settings"]
    assert settings["pip_enabled"] is True
    sc = settings["keyboard_shortcuts"]
    assert sc["refresh"] == "g"
    assert sc["mute"] == "n"


def test_save_settings_filters_unknown_shortcut_keys(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    monkeypatch.setattr(api, "start_polling", lambda interval: None)
    monkeypatch.setattr(api, "_eval_js", lambda code: None)

    api.save_settings(
        json.dumps(
            {
                "keyboard_shortcuts": {
                    "refresh": "g",
                    "unknown_action": "z",
                }
            }
        )
    )

    stored = load_config()
    sc = stored["settings"]["keyboard_shortcuts"]
    assert "refresh" in sc
    assert "unknown_action" not in sc


def test_save_settings_filters_invalid_shortcut_values_and_falls_back_to_defaults(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    monkeypatch.setattr(api, "start_polling", lambda interval: None)
    monkeypatch.setattr(api, "_eval_js", lambda code: None)

    api.save_settings(
        json.dumps(
            {
                "keyboard_shortcuts": {
                    "refresh": "g",
                    "mute": "",
                    "pip": "a" * 51,
                    "fullscreen": 123,
                }
            }
        )
    )

    stored = load_config()
    sc = stored["settings"]["keyboard_shortcuts"]
    assert sc.get("refresh") == "g"
    # Invalid values are filtered out; deep_merge restores defaults for missing keys
    assert sc.get("mute") == "m"
    assert sc.get("pip") == "p"
    assert sc.get("fullscreen") == "f"


class TestWatchMediaStreamType:
    def test_watch_media_emits_vod_stream_type(
        self, run_sync, capture_eval_js, temp_config_dir
    ) -> None:
        from unittest.mock import patch

        with patch("ui.api.streams.resolve_hls_url") as mock_resolve:
            mock_resolve.return_value = ("https://example.com/vod.m3u8", "")
            api = TwitchXApi()
            api._eval_js = capture_eval_js
            api._live_streams = []
            api.watch_media(
                url="https://www.twitch.tv/videos/123456",
                quality="best",
                platform="twitch",
                channel="xqc",
                title="My VOD",
            )
        capture_eval_js.assert_any('"stream_type": "vod"')

    def test_watch_emits_live_stream_type(
        self, run_sync, capture_eval_js, temp_config_dir
    ) -> None:
        from unittest.mock import patch

        with patch("ui.api.streams.resolve_hls_url") as mock_resolve:
            mock_resolve.return_value = ("https://example.com/live.m3u8", "")
            api = TwitchXApi()
            api._eval_js = capture_eval_js
            api._live_streams = [{"login": "xqc", "platform": "twitch", "user_login": "xqc"}]
            api.watch("xqc", "best")
        capture_eval_js.assert_any('"stream_type": "live"')


def test_start_watch_session_is_atomic_under_lock(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Concurrent _start_watch_session must not create orphaned DB sessions."""
    import threading
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda code: None)

    call_count: list[int] = [0]
    created_ids: list[int] = []
    created_lock = threading.Lock()

    def mock_start(*args: object, **kwargs: object) -> int:
        with created_lock:
            call_count[0] += 1
            sid = call_count[0]
            created_ids.append(sid)
            return sid

    monkeypatch.setattr(api._watch_stats, "start_session", mock_start)
    monkeypatch.setattr(api._watch_stats, "end_session", lambda sid: None)

    def worker(n: int) -> None:
        api._streams._start_watch_session(f"ch{n}", "twitch")

    t1 = threading.Thread(target=worker, args=(1,))
    t2 = threading.Thread(target=worker, args=(2,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert api._active_watch_session == call_count[0]


def test_finish_launch_invalidates_launch_id(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_finish_launch must increment _launch_id to prevent concurrent tick()."""
    api = TwitchXApi()
    monkeypatch.setattr(api._streams, "_start_launch_timer", lambda: None)
    monkeypatch.setattr(api._streams, "_cancel_launch_timer", lambda: None)

    lid = api._streams._begin_launch("test")
    result = api._streams._finish_launch(lid)

    assert result is True
    assert api._launch_id != lid
    assert api._launch_channel is None


def test_finish_launch_returns_false_when_stale(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stale _finish_launch must return False and NOT increment _launch_id."""
    api = TwitchXApi()
    monkeypatch.setattr(api._streams, "_start_launch_timer", lambda: None)
    monkeypatch.setattr(api._streams, "_cancel_launch_timer", lambda: None)

    lid = api._streams._begin_launch("test")
    api._launch_id += 1

    result = api._streams._finish_launch(lid)

    assert result is False


def test_async_run_closes_thread_loop(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_async_run must call _close_thread_loop instead of bare loop.close()."""
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda code: None)
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())

    close_calls: list[object] = []
    monkeypatch.setattr(api, "_close_thread_loop", lambda loop: close_calls.append(loop))

    async def dummy() -> None:
        pass

    api._auth._async_run(dummy())

    assert len(close_calls) == 1


def test_send_chat_forwards_reply_params(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """send_chat must forward reply context to the chat client."""
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda code: None)

    mock_client = MagicMock()
    mock_client._loop = MagicMock()
    mock_client._loop.is_closed.return_value = False
    mock_client.platform = "twitch"
    mock_client._channel = "test_channel"
    api._chat_client = mock_client

    submitted_fn: list[Any] = []
    monkeypatch.setattr(api._send_pool, "submit", lambda fn: submitted_fn.append(fn))

    api.send_chat(
        "hello",
        reply_to="r-123",
        reply_display="User",
        reply_body="original",
        request_id="req-test",
    )

    assert len(submitted_fn) == 1

    mock_future = MagicMock()
    mock_future.result.return_value = ChatSendResult(
        ok=True, platform="twitch", channel_id="test"
    )

    with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future):
        submitted_fn[0]()

    mock_client.send_message.assert_called_once_with("hello", reply_to="r-123")
