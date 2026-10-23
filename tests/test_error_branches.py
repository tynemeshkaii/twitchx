"""One test per error branch that reports a failure to JS via _eval_js.

Covers branches in ui/api/data.py, favorites.py and chat.py that the
feature-focused suites never reach.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.storage import update_config
from ui.api import TwitchXApi
from ui.api.data import FetchResult


@pytest.fixture
def api(temp_config_dir: Path, run_sync: None) -> TwitchXApi:
    instance = TwitchXApi()
    calls: list[str] = []
    instance._eval_js = calls.append  # type: ignore[method-assign]
    instance.calls = calls  # type: ignore[attr-defined]
    return instance


def _calls(api: TwitchXApi) -> list[str]:
    return api.calls  # type: ignore[attr-defined]


def _status_texts(api: TwitchXApi) -> list[str]:
    """Texts of onStatusUpdate calls made with json.dumps payloads."""
    prefix = "window.onStatusUpdate("
    texts = []
    for call in _calls(api):
        if call.startswith(prefix):
            try:
                texts.append(json.loads(call[len(prefix) : -1])["text"])
            except json.JSONDecodeError:
                texts.append(call)  # JS object literal: keep raw text
    return texts


# ── data.py: _fetch_data Twitch error reporting ──────────────────


def _fetch_with_twitch_error(api: TwitchXApi, error: BaseException) -> None:
    result = FetchResult([], [], [], [], error, [])
    with (
        patch.object(api._data, "_async_fetch", AsyncMock(return_value=result)),
        patch.object(api._data, "_on_data_fetched"),
    ):
        _locked_fetch(api)


def _locked_fetch(api: TwitchXApi) -> None:
    # _fetch_data releases _fetch_lock on exit; refresh() acquires it first.
    api._fetch_lock.acquire()
    api._data._fetch_data(["someone"], [], [])


def _http_status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.twitch.tv/helix/streams")
    return httpx.HTTPStatusError(
        "boom", request=request, response=httpx.Response(code, request=request)
    )


class TestFetchDataErrors:
    def test_auth_status_points_to_credentials(self, api: TwitchXApi) -> None:
        _fetch_with_twitch_error(api, _http_status_error(401))
        assert any("Check your API credentials" in t for t in _status_texts(api))

    def test_other_status_reports_code(self, api: TwitchXApi) -> None:
        _fetch_with_twitch_error(api, _http_status_error(503))
        assert any("API error: 503" in t for t in _status_texts(api))

    def test_value_error_asks_for_credentials(self, api: TwitchXApi) -> None:
        _fetch_with_twitch_error(api, ValueError("no creds"))
        assert any("Set API credentials" in t for t in _status_texts(api))

    def test_unexpected_exception_reports_message(self, api: TwitchXApi) -> None:
        with patch.object(
            api._data, "_async_fetch", AsyncMock(side_effect=RuntimeError("kaput"))
        ):
            _locked_fetch(api)
        assert any("Error: " in t and "kaput" in t for t in _status_texts(api))


class TestChannelProfileErrors:
    def test_unnormalizable_profile_reports_not_found(self, api: TwitchXApi) -> None:
        with (
            patch.object(
                api._twitch, "get_channel_info", AsyncMock(return_value={"x": 1})
            ),
            patch.object(
                api._data, "_normalize_channel_info_to_profile", return_value={}
            ),
        ):
            api.get_channel_profile("ghost", "twitch")
        prefix = "window.onChannelProfile("
        payload = json.loads(_calls(api)[-1][len(prefix) : -1])
        assert payload == {"login": "ghost", "platform": "twitch", "found": False}


# ── favorites.py ─────────────────────────────────────────────────


class TestImportErrors:
    def test_twitch_import_without_user_id(self, api: TwitchXApi) -> None:
        api._current_user = {"login": "me"}
        api._favorites.import_follows()
        assert 'window.onImportError("No user ID")' in _calls(api)

    def test_twitch_import_failure_reports_message(self, api: TwitchXApi) -> None:
        api._current_user = {"id": "1", "login": "me"}
        api._twitch.get_followed_channels = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("helix down")
        )
        api._favorites.import_follows()
        assert 'window.onImportError("helix down")' in _calls(api)

    def test_youtube_import_failure_reports_message(self, api: TwitchXApi) -> None:
        def _login(cfg: dict) -> None:
            cfg["platforms"]["youtube"]["access_token"] = "yt-token"

        api._config = update_config(_login)
        api._youtube.get_followed_channels = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("quota")
        )
        api._favorites.youtube_import_follows()
        assert 'window.onYouTubeImportError("quota")' in _calls(api)


class TestAddChannelErrors:
    def test_youtube_disabled(self, api: TwitchXApi) -> None:
        with patch("ui.api.favorites.YOUTUBE_ENABLED", False):
            api._favorites.add_channel("@someone", "youtube")
        assert _status_texts(api) == ["YouTube is disabled in this build"]

    def test_unknown_platform(self, api: TwitchXApi) -> None:
        api._favorites.add_channel("someone", "myspace")
        assert _status_texts(api) == ["Unknown platform"]

    @pytest.mark.parametrize(
        ("info", "error", "expected"),
        [
            ({}, None, "YouTube channel not found"),
            (None, ValueError("Bad API key"), "Bad API key"),
            (None, RuntimeError("network"), "Could not resolve YouTube channel"),
        ],
    )
    def test_youtube_resolve_failures(
        self,
        api: TwitchXApi,
        info: dict[str, Any] | None,
        error: Exception | None,
        expected: str,
    ) -> None:
        resolver = AsyncMock(return_value=info, side_effect=error)
        with (
            patch("ui.api.favorites.YOUTUBE_ENABLED", True),
            patch.object(api._youtube, "get_channel_info", resolver),
        ):
            api._favorites.add_channel("@someone", "youtube")
        texts = _status_texts(api)
        assert texts and expected in texts[-1]


# ── chat.py ──────────────────────────────────────────────────────


class TestSendChatErrors:
    def test_send_without_connection_reports_unavailable(self, api: TwitchXApi) -> None:
        api._chat_client = None
        api._chat.send_chat("hi", request_id="r1")
        prefix = "window.onChatSendResult("
        payload = json.loads(_calls(api)[-1][len(prefix) : -1])
        assert payload["ok"] is False
        assert payload["error"] == "Chat is not connected."
        assert payload["request_id"] == "r1"

    def test_send_before_loop_ready_reports_unavailable(self, api: TwitchXApi) -> None:
        client = MagicMock()
        client._loop = None
        api._chat_client = client
        api._chat.send_chat("hi")
        prefix = "window.onChatSendResult("
        payload = json.loads(_calls(api)[-1][len(prefix) : -1])
        assert payload["error"] == "Chat connection is not ready yet."
