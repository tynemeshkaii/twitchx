"""Playback stability: adaptive resolves, URL refresh and launch supersession."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ui.api import TwitchXApi


def _resolver_spy(
    captured: dict[str, Any], url: str | None = "https://example.com/s.m3u8", err: str = ""
):
    def fake_resolve(
        channel: str,
        quality: str,
        streamlink_path: str = "streamlink",
        platform_client: Any = None,
        extra_args: Any = None,
        adaptive: bool = False,
        use_cache: bool = False,
    ) -> tuple[str | None, str]:
        captured["channel"] = channel
        captured["quality"] = quality
        captured["adaptive"] = adaptive
        captured["use_cache"] = use_cache
        captured["platform"] = platform_client.PLATFORM_ID if platform_client else ""
        captured["calls"] = captured.get("calls", 0) + 1
        return (url, err)

    return fake_resolve


def _sync_api(api: TwitchXApi, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    emitted: list[str] = []
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))
    monkeypatch.setattr(api._streams, "_start_launch_timer", lambda: None)
    monkeypatch.setattr(api._streams, "_cancel_launch_timer", lambda: None)
    monkeypatch.setattr(api, "start_chat", lambda channel, platform="twitch": None)
    monkeypatch.setattr(api, "stop_chat", lambda: None)
    return emitted


class TestAdaptiveResolve:
    def test_twitch_live_requests_adaptive_master(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AVPlayer must be handed the master playlist so it can switch bitrate."""
        api = TwitchXApi()
        api._live_streams = [{"login": "xqc", "title": "t", "platform": "twitch"}]
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            "ui.api.streams.resolve_hls_url", _resolver_spy(captured)
        )
        _sync_api(api, monkeypatch)

        api.watch("xqc", "best")

        assert captured["adaptive"] is True
        assert captured["platform"] == "twitch"

    def test_youtube_is_not_adaptive(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        api._live_streams = [
            {
                "login": "UCabc",
                "title": "t",
                "platform": "youtube",
                "video_id": "vid123",
            }
        ]
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            "ui.api.streams.resolve_hls_url", _resolver_spy(captured)
        )
        _sync_api(api, monkeypatch)

        api.watch("UCabc", "best")

        assert captured["adaptive"] is False

    def test_vod_playback_stays_single_rendition(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            "ui.api.streams.resolve_hls_url", _resolver_spy(captured)
        )
        _sync_api(api, monkeypatch)

        api.watch_media("https://twitch.tv/videos/1", "best", "twitch", "xqc")

        assert captured["adaptive"] is False


class TestRefreshStreamUrl:
    def test_emits_fresh_url(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            "ui.api.streams.resolve_hls_url",
            _resolver_spy(captured, "https://example.com/fresh.m3u8"),
        )
        emitted = _sync_api(api, monkeypatch)

        api.refresh_stream_url("xqc", "twitch", "best")

        payloads = [c for c in emitted if "onStreamUrlRefreshed" in c]
        assert len(payloads) == 1
        data = json.loads(payloads[0].split("(", 1)[1].rsplit(")", 1)[0])
        assert data["ok"] is True
        assert data["url"] == "https://example.com/fresh.m3u8"
        assert data["channel"] == "xqc"

    def test_bypasses_the_resolve_cache(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A refresh exists because the cached URL went stale."""
        api = TwitchXApi()
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            "ui.api.streams.resolve_hls_url", _resolver_spy(captured)
        )
        _sync_api(api, monkeypatch)

        api.refresh_stream_url("xqc", "twitch", "best")

        assert captured["use_cache"] is False

    def test_failure_reports_error(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            "ui.api.streams.resolve_hls_url",
            _resolver_spy(captured, None, "channel offline"),
        )
        emitted = _sync_api(api, monkeypatch)

        api.refresh_stream_url("xqc", "twitch", "best")

        payload = [c for c in emitted if "onStreamUrlRefreshed" in c][0]
        data = json.loads(payload.split("(", 1)[1].rsplit(")", 1)[0])
        assert data["ok"] is False
        assert "offline" in data["error"]

    def test_youtube_is_rejected_without_resolving(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            "ui.api.streams.resolve_hls_url", _resolver_spy(captured)
        )
        emitted = _sync_api(api, monkeypatch)

        api.refresh_stream_url("UCabc", "youtube", "best")

        assert captured.get("calls") is None
        assert any("onStreamUrlRefreshed" in c for c in emitted)

    def test_empty_channel_is_ignored(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        emitted = _sync_api(api, monkeypatch)

        api.refresh_stream_url("", "twitch", "best")

        assert emitted == []


class TestRefreshMultiSlotUrl:
    def test_emits_slot_payload(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            "ui.api.streams.resolve_hls_url",
            _resolver_spy(captured, "https://example.com/slot.m3u8"),
        )
        emitted = _sync_api(api, monkeypatch)

        api.refresh_multi_slot_url(2, "xqc", "twitch", "720p60")

        payload = [c for c in emitted if "onMultiSlotUrlRefreshed" in c][0]
        data = json.loads(payload.split("(", 1)[1].rsplit(")", 1)[0])
        assert data["slot_idx"] == 2
        assert data["ok"] is True
        assert data["url"] == "https://example.com/slot.m3u8"
        assert captured["quality"] == "720p60"

    def test_out_of_range_slot_is_ignored(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        emitted = _sync_api(api, monkeypatch)

        api.refresh_multi_slot_url(9, "xqc", "twitch", "best")

        assert emitted == []


class TestLaunchSupersession:
    def test_second_watch_supersedes_the_first(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Picking another channel mid-launch must not be silently dropped."""
        api = TwitchXApi()
        api._live_streams = [
            {"login": "a", "title": "A", "platform": "twitch"},
            {"login": "b", "title": "B", "platform": "twitch"},
        ]
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            "ui.api.streams.resolve_hls_url", _resolver_spy(captured)
        )
        emitted = _sync_api(api, monkeypatch)

        # Leave the first launch in flight by not letting its resolver run.
        api._streams._begin_launch("a")
        assert api._launch_channel == "a"

        api.watch("b", "best")

        assert captured["channel"] == "b"
        assert any("onStreamReady" in c for c in emitted)

    def test_superseded_resolver_result_is_discarded(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        stale_id = api._streams._begin_launch("a")
        api._streams._cancel_pending_launch()

        assert api._streams._is_launch_current(stale_id) is False
        assert api._streams._finish_launch(stale_id) is False
