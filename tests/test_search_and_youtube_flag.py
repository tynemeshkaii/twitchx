"""Channel search resilience and the YOUTUBE_ENABLED backend gate."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.storage import DEFAULT_CONFIG, save_config
from ui.api import TwitchXApi


def _payloads(calls: list[str], callback: str) -> list:
    """First argument of each ``window.<callback>(...)`` call."""
    return [args[0] for args in _call_args(calls, callback)]


def _call_args(calls: list[str], callback: str) -> list[list]:
    prefix = f"window.{callback}("
    return [
        json.loads("[" + c[len(prefix) : -1] + "]")
        for c in calls
        if c.startswith(prefix)
    ]


@pytest.fixture
def api(temp_config_dir: Path, run_sync) -> TwitchXApi:
    platforms = {
        name: {**conf, "enabled": True}
        for name, conf in DEFAULT_CONFIG["platforms"].items()
    }
    platforms["twitch"].update(client_id="fakeid", client_secret="fakesecret")
    platforms["youtube"].update(api_key="yt-key", access_token="yt-token")
    save_config({**DEFAULT_CONFIG, "platforms": platforms})
    instance = TwitchXApi()
    calls: list[str] = []
    instance._eval_js = calls.append  # type: ignore[method-assign]
    instance.calls = calls  # type: ignore[attr-defined]
    return instance


TWITCH_HIT = {
    "broadcaster_login": "foo",
    "display_name": "Foo",
    "is_live": False,
    "game_name": "",
}


class TestSearchResilience:
    def test_kick_failure_keeps_twitch_results(self, api: TwitchXApi) -> None:
        with (
            patch.object(
                api._kick,
                "search_channels",
                AsyncMock(side_effect=RuntimeError("kick down")),
            ),
            patch.object(
                api._twitch, "search_channels", AsyncMock(return_value=[TWITCH_HIT])
            ),
            patch("ui.api.favorites.YOUTUBE_ENABLED", False),
        ):
            api.search_channels("foo", "all")

        results = _payloads(api.calls, "onSearchResults")[-1]  # type: ignore[attr-defined]
        assert [(r["platform"], r["login"]) for r in results] == [("twitch", "foo")]


class TestSearchMeta:
    def test_results_carry_query_and_platform(self, api: TwitchXApi) -> None:
        with (
            patch.object(api._kick, "search_channels", AsyncMock(return_value=[])),
            patch.object(
                api._twitch, "search_channels", AsyncMock(return_value=[TWITCH_HIT])
            ),
            patch("ui.api.favorites.YOUTUBE_ENABLED", False),
        ):
            api.search_channels("foo", "all")

        args = _call_args(api.calls, "onSearchResults")[-1]  # type: ignore[attr-defined]
        assert args[1] == {"query": "foo", "platform": "all"}

    def test_failure_still_carries_query(self, api: TwitchXApi) -> None:
        with patch("ui.api.favorites.asyncio.gather", side_effect=RuntimeError("x")):
            api.search_channels("bar", "kick")

        args = _call_args(api.calls, "onSearchResults")[-1]  # type: ignore[attr-defined]
        assert args == [[], {"query": "bar", "platform": "kick"}]


class TestYouTubeDisabled:
    def test_search_skips_youtube(self, api: TwitchXApi) -> None:
        yt_search = AsyncMock(return_value=[])
        with (
            patch.object(api._kick, "search_channels", AsyncMock(return_value=[])),
            patch.object(api._twitch, "search_channels", AsyncMock(return_value=[])),
            patch.object(api._youtube, "search_channels", yt_search),
            patch("ui.api.favorites.YOUTUBE_ENABLED", False),
        ):
            api.search_channels("foo", "all")
        yt_search.assert_not_called()

    def test_polling_skips_youtube(self, api: TwitchXApi) -> None:
        import asyncio

        yt_live = AsyncMock(return_value=[{"login": "UCx"}])
        with (
            patch.object(api._youtube, "get_live_streams", yt_live),
            patch("ui.api.data.YOUTUBE_ENABLED", False),
        ):
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    api._data._async_fetch([], [], ["UCx"])
                )
            finally:
                loop.close()
        yt_live.assert_not_called()
        assert result.youtube_streams == []

    def test_browse_all_excludes_youtube(self, api: TwitchXApi) -> None:
        yt_cats = AsyncMock(return_value=[])
        with (
            patch.object(api._twitch, "get_categories", AsyncMock(return_value=[])),
            patch.object(api._kick, "get_categories", AsyncMock(return_value=[])),
            patch.object(api._youtube, "get_categories", yt_cats),
            patch("ui.api.data.YOUTUBE_ENABLED", False),
        ):
            api._data._fetch_browse_categories("all")
        yt_cats.assert_not_called()
        payload = _payloads(api.calls, "onBrowseCategories")[-1]  # type: ignore[attr-defined]
        assert "youtube" not in payload["errors"]
        assert "youtube" not in payload["enabled_platforms"]

    def test_add_youtube_channel_is_rejected(self, api: TwitchXApi) -> None:
        with patch("ui.api.favorites.YOUTUBE_ENABLED", False):
            api.add_channel("UCabcdefghijklmnopqrstuv", "youtube")
        statuses = _payloads(api.calls, "onStatusUpdate")  # type: ignore[attr-defined]
        assert statuses[-1] == {
            "text": "YouTube is disabled in this build",
            "type": "error",
        }
