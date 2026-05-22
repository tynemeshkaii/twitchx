"""Network resilience tests for _fetch_data: retry, exhaustion, and timeout handling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from core.storage import DEFAULT_CONFIG, save_config
from ui.api import TwitchXApi


def _make_api_with_twitch_creds(temp_config_dir: Path) -> TwitchXApi:
    """Set up a TwitchXApi instance with Twitch credentials configured."""
    cfg = {
        **DEFAULT_CONFIG,
        "favorites": [
            {"platform": "twitch", "login": "streamer1", "display_name": "Streamer1"}
        ],
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
    api = TwitchXApi()
    return api


def _call_fetch_data(api: TwitchXApi, **kwargs) -> None:
    """Acquire the fetch lock (as refresh() would) then call _fetch_data directly."""
    acquired = api._fetch_lock.acquire(blocking=False)
    if not acquired:
        raise RuntimeError("fetch_lock already held — test setup error")
    try:
        api._data._fetch_data(**kwargs)
    except Exception:
        # _fetch_data releases the lock in its own finally block
        raise


class TestNetworkResilience:
    def test_connect_error_triggers_retry_then_success(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """First Twitch call raises ConnectError, second succeeds.

        Verifies that:
        - _ensure_token is called twice (retry happened)
        - onStreamsUpdate is emitted to JS after the successful retry
        """
        api = _make_api_with_twitch_creds(temp_config_dir)

        js_calls: list[str] = []
        monkeypatch.setattr(api, "_eval_js", lambda code: js_calls.append(code))

        # _ensure_token: fail first, succeed second
        call_count = 0

        async def flaky_ensure_token() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("connection refused")

        fresh_stream = {
            "user_login": "streamer1",
            "user_name": "Streamer1",
            "viewer_count": 100,
            "title": "Playing games",
            "game_id": "",
            "game_name": "",
            "thumbnail_url": "",
            "started_at": "",
        }

        with (
            patch.object(api._twitch, "_ensure_token", side_effect=flaky_ensure_token),
            patch.object(
                api._twitch, "get_live_streams", AsyncMock(return_value=[fresh_stream])
            ),
            patch.object(api._twitch, "get_users", AsyncMock(return_value=[])),
            patch("ui.api.data.time.sleep"),  # skip retry delay
        ):
            _call_fetch_data(
                api,
                twitch_favorites=["streamer1"],
                kick_favorites=[],
                youtube_favorites=[],
            )

        assert call_count == 2, f"Expected 2 _ensure_token calls, got {call_count}"
        streams_update_calls = [c for c in js_calls if "onStreamsUpdate" in c]
        assert len(streams_update_calls) >= 2, (
            f"Expected onStreamsUpdate emitted at least twice (once per attempt), got {len(streams_update_calls)}: {streams_update_calls}"
        )
        assert "streamer1" in streams_update_calls[-1], (
            "Last onStreamsUpdate should contain real stream data from the successful retry"
        )

    def test_all_retries_exhausted_emits_error_status(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All 4 Twitch attempts raise ConnectError.

        After exhaustion, an error status JS call must appear containing
        a reconnect/error/failed indicator (e.g., 'No internet connection').
        """
        api = _make_api_with_twitch_creds(temp_config_dir)

        js_calls: list[str] = []
        monkeypatch.setattr(api, "_eval_js", lambda code: js_calls.append(code))

        with (
            patch.object(
                api._twitch,
                "_ensure_token",
                side_effect=httpx.ConnectError("always fails"),
            ),
            patch("ui.api.data.time.sleep"),  # skip all retry delays
        ):
            _call_fetch_data(
                api,
                twitch_favorites=["streamer1"],
                kick_favorites=[],
                youtube_favorites=[],
            )

        # At exhaustion, must emit a "No internet connection" error status
        error_calls = [
            c
            for c in js_calls
            if "onStatusUpdate" in c
            and any(
                keyword in c
                for keyword in (
                    "Reconnect",
                    "reconnect",
                    "No internet",
                    "error",
                    "failed",
                )
            )
        ]
        assert error_calls, (
            f"Expected error/reconnect status after exhausted retries, got JS calls: {js_calls}"
        )

        # The fetch lock must be released after exhaustion
        acquired = api._fetch_lock.acquire(blocking=False)
        assert acquired, "fetch_lock was not released after retry exhaustion"
        if acquired:
            api._fetch_lock.release()

    def test_read_timeout_does_not_crash(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Twitch raises ReadTimeout — _fetch_data must not raise and must release the lock.

        ReadTimeout is not a ConnectError so it is not retried; the fetch ends
        after the first attempt with no uncaught exception.
        """
        api = _make_api_with_twitch_creds(temp_config_dir)

        js_calls: list[str] = []
        monkeypatch.setattr(api, "_eval_js", lambda code: js_calls.append(code))

        with (
            patch.object(
                api._twitch,
                "_ensure_token",
                side_effect=httpx.ReadTimeout("read timed out"),
            ),
            patch("ui.api.data.time.sleep"),  # in case any delay path is hit
        ):
            # Must not raise
            _call_fetch_data(
                api,
                twitch_favorites=["streamer1"],
                kick_favorites=[],
                youtube_favorites=[],
            )

        # The fetch lock must be released after the timeout
        acquired = api._fetch_lock.acquire(blocking=False)
        assert acquired, "fetch_lock was not released after ReadTimeout"
        if acquired:
            api._fetch_lock.release()
