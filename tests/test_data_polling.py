"""Polling payload: platform-scoped live keys, honest staleness, cache expiry."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.storage import DEFAULT_CONFIG, save_config
from ui.api import TwitchXApi


def _twitch_stream(login: str) -> dict:
    return {
        "user_login": login,
        "user_name": login.title(),
        "title": "twitch title",
        "game_name": "Twitch Game",
        "viewer_count": 1,
    }


def _payloads(calls: list[str], callback: str) -> list:
    prefix = f"window.{callback}("
    return [json.loads(c[len(prefix) : -1]) for c in calls if c.startswith(prefix)]


def _warns(calls: list[str]) -> list[dict]:
    return [p for p in _payloads(calls, "onStatusUpdate") if p.get("type") == "warn"]


@pytest.fixture
def api(temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TwitchXApi:
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
    instance = TwitchXApi()
    calls: list[str] = []
    instance._eval_js = calls.append  # type: ignore[method-assign]
    instance.calls = calls  # type: ignore[attr-defined]
    return instance


def _fetch(api: TwitchXApi, **kwargs) -> None:
    assert api._fetch_lock.acquire(blocking=False)
    kwargs.setdefault("twitch_favorites", [])
    kwargs.setdefault("kick_favorites", [])
    kwargs.setdefault("youtube_favorites", [])
    api._data._fetch_data(**kwargs)


# ── 3.3 platform:login keys ──────────────────────────────────────


class TestPlatformScopedLiveKeys:
    def test_kick_going_live_with_same_login_as_twitch_notifies_once(
        self, api: TwitchXApi, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sent: list[tuple[str, str, str]] = []
        monkeypatch.setattr(api._data, "_send_notification", lambda *a: sent.append(a))
        kick_foo = {
            "slug": "foo",
            "channel": {"slug": "foo", "username": "FooOnKick"},
            "stream_title": "kick title",
            "category": {"name": "Kick Game"},
        }

        api._data._on_data_fetched(
            ["foo"], ["foo"], [], [_twitch_stream("foo")], [], [], []
        )
        api._data._on_data_fetched(
            ["foo"], ["foo"], [], [_twitch_stream("foo")], [], [kick_foo], []
        )

        assert sent == [("FooOnKick", "kick title", "Kick Game")]
        assert api._prev_live_logins == {"twitch:foo", "kick:foo"}

    def test_youtube_key_keeps_case(
        self, api: TwitchXApi, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(api._data, "_send_notification", lambda *a: None)
        yt = {"login": "UCAbCdEf", "display_name": "Chan"}
        api._data._on_data_fetched([], [], ["UCAbCdEf"], [], [], [], [yt])
        assert api._prev_live_logins == {"youtube:UCAbCdEf"}

    def test_payload_has_no_live_set(self, api: TwitchXApi) -> None:
        api._data._on_data_fetched(["foo"], [], [], [_twitch_stream("foo")], [], [], [])
        payload = _payloads(api.calls, "onStreamsUpdate")[-1]  # type: ignore[attr-defined]
        assert "live_set" not in payload


# ── 3.4 staleness and cache expiry ───────────────────────────────


class TestKickCacheExpiry:
    def test_kick_failure_uses_recent_cache_and_warns(self, api: TwitchXApi) -> None:
        api._last_kick_streams = [{"slug": "streamer"}]
        api._platform_fetched_at["kick"] = time.time() - 10
        api._last_successful_fetch = 123.0

        with patch.object(
            api._kick, "get_live_streams", AsyncMock(side_effect=RuntimeError("down"))
        ):
            _fetch(api, kick_favorites=["streamer"])

        payload = _payloads(api.calls, "onStreamsUpdate")[-1]  # type: ignore[attr-defined]
        assert [s["login"] for s in payload["streams"]] == ["streamer"]
        warns = _warns(api.calls)  # type: ignore[attr-defined]
        assert warns and "Kick" in warns[-1]["text"]
        assert api._last_successful_fetch == 123.0

    def test_kick_cache_older_than_threshold_is_dropped(self, api: TwitchXApi) -> None:
        api._last_kick_streams = [{"slug": "streamer"}]
        api._platform_fetched_at["kick"] = time.time() - 10_000

        with patch.object(
            api._kick, "get_live_streams", AsyncMock(side_effect=RuntimeError("down"))
        ):
            _fetch(api, kick_favorites=["streamer"])

        payload = _payloads(api.calls, "onStreamsUpdate")[-1]  # type: ignore[attr-defined]
        assert payload["streams"] == []
        warns = _warns(api.calls)  # type: ignore[attr-defined]
        assert warns and "Kick" in warns[-1]["text"]

    def test_all_fresh_updates_last_successful_fetch(self, api: TwitchXApi) -> None:
        with patch.object(
            api._kick, "get_live_streams", AsyncMock(return_value=[{"slug": "s"}])
        ):
            _fetch(api, kick_favorites=["s"])

        assert api._last_successful_fetch > time.time() - 5
        assert api._platform_fetched_at["kick"] > time.time() - 5
        assert _warns(api.calls) == []  # type: ignore[attr-defined]


class TestTwitchTimeoutWarns:
    def test_timeout_reports_stale_twitch(self, api: TwitchXApi) -> None:
        async def slow_token() -> None:
            await asyncio.sleep(999)

        async def run():
            with patch.object(api._twitch, "_ensure_token", side_effect=slow_token):
                return await api._data._async_fetch(
                    twitch_favorites=["foo"], kick_favorites=[], _twitch_timeout=0.05
                )

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(run())
        finally:
            loop.close()

        assert result.twitch_error is None
        assert result.stale_platforms == ["twitch"]

    def test_twitch_cache_expires(self, api: TwitchXApi) -> None:
        api._last_twitch_streams = [_twitch_stream("old")]
        api._platform_fetched_at["twitch"] = time.time() - 10_000

        async def run():
            with patch.object(
                api._twitch, "_ensure_token", side_effect=RuntimeError("boom")
            ):
                return await api._data._async_fetch(
                    twitch_favorites=["old"], kick_favorites=[]
                )

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(run())
        finally:
            loop.close()

        assert result.twitch_streams == []
        assert result.stale_platforms == ["twitch"]
