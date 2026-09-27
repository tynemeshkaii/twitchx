"""Regression tests for defects found reviewing the playback stability work.

Each test here corresponds to a concrete bug that shipped and was then fixed;
they exist so the same mistake cannot come back unnoticed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from core.storage import get_settings, load_config
from core.stream_resolver import _quality_arg, invalidate_resolve_cache, resolve_hls_url
from ui.api import TwitchXApi


def _sync_api(api: TwitchXApi, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    emitted: list[str] = []
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))
    monkeypatch.setattr(api._streams, "_start_launch_timer", lambda: None)
    monkeypatch.setattr(api._streams, "_cancel_launch_timer", lambda: None)
    monkeypatch.setattr(api, "start_chat", lambda channel, platform="twitch": None)
    monkeypatch.setattr(api, "stop_chat", lambda: None)
    return emitted


def _spy(captured: dict[str, Any], url: str | None = "https://example.com/s.m3u8"):
    def fake_resolve(
        channel: str,
        quality: str,
        streamlink_path: str = "streamlink",
        platform_client: Any = None,
        extra_args: Any = None,
        adaptive: bool = False,
        use_cache: bool = False,
    ) -> tuple[str | None, str]:
        captured["extra_args"] = list(extra_args or [])
        captured["channel"] = channel
        return (url, "" if url else "offline")

    return fake_resolve


class TestLaunchIsNotCancelledByARejectedClick:
    """A click that cannot start a stream must not kill the one that is loading."""

    def test_offline_channel_leaves_pending_launch_alone(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        api._live_streams = [{"login": "good", "title": "G", "platform": "twitch"}]
        _sync_api(api, monkeypatch)

        launch_id = api._streams._begin_launch("good")
        api.watch("offline-chan", "best")

        assert api._launch_channel == "good"
        assert api._streams._is_launch_current(launch_id) is True

    def test_already_watching_click_leaves_pending_launch_alone(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        api._live_streams = [
            {"login": "good", "title": "G", "platform": "twitch"},
            {"login": "current", "title": "C", "platform": "twitch"},
        ]
        api._watching_channel = "current"
        _sync_api(api, monkeypatch)

        launch_id = api._streams._begin_launch("good")
        api.watch("current", "best")

        assert api._streams._is_launch_current(launch_id) is True

    def test_valid_click_still_supersedes(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        api._live_streams = [
            {"login": "a", "title": "A", "platform": "twitch"},
            {"login": "b", "title": "B", "platform": "twitch"},
        ]
        captured: dict[str, Any] = {}
        monkeypatch.setattr("ui.api.streams.resolve_hls_url", _spy(captured))
        _sync_api(api, monkeypatch)

        launch_id = api._streams._begin_launch("a")
        api.watch("b", "best")

        assert api._streams._is_launch_current(launch_id) is False
        assert captured["channel"] == "b"


class TestCodecSettingRoundTrip:
    """The codec setting used to save but never load, so it silently reverted."""

    def test_saved_value_is_returned_to_the_settings_ui(
        self, temp_config_dir: Path
    ) -> None:
        api = TwitchXApi()
        api._eval_js = lambda code: None  # type: ignore[method-assign]
        api.save_settings(json.dumps({"stream_codecs": "h264"}))

        payload = api.get_full_config_for_settings()

        assert payload["stream_codecs"] == "h264"
        assert get_settings(load_config())["stream_codecs"] == "h264"

    def test_default_is_reported_as_auto(self, temp_config_dir: Path) -> None:
        api = TwitchXApi()
        assert api.get_full_config_for_settings()["stream_codecs"] == "auto"

    def test_a_save_that_omits_it_does_not_wipe_it(self, temp_config_dir: Path) -> None:
        api = TwitchXApi()
        api._eval_js = lambda code: None  # type: ignore[method-assign]
        api.save_settings(json.dumps({"stream_codecs": "h264,h265,av1"}))
        api.save_settings(json.dumps({"low_latency_mode": True}))

        assert get_settings(load_config())["stream_codecs"] == "h264,h265,av1"


class TestQualityLadderDirection:
    def test_audio_only_never_falls_back_to_video_source(self) -> None:
        assert "best" not in _quality_arg("audio_only")

    def test_lowest_video_never_falls_back_to_source(self) -> None:
        assert "best" not in _quality_arg("160p")


class TestMasterFallbackUsesTheCache:
    """A channel with no master playlist used to cost two spawns on every call."""

    def teardown_method(self) -> None:
        invalidate_resolve_cache()

    def test_second_call_after_master_failure_spawns_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str | None] = []

        def fake_run(
            resolved_sl: str,
            stream_url: str,
            quality: str | None,
            extra_args: Any = None,
        ) -> tuple[str | None, str]:
            calls.append(quality)
            if quality is None:
                return None, "no master here"
            return "https://example.com/single.m3u8", ""

        invalidate_resolve_cache()
        monkeypatch.setattr(
            "core.stream_resolver.shutil.which", lambda p: "/usr/bin/streamlink"
        )
        monkeypatch.setattr("core.stream_resolver._run_streamlink", fake_run)

        for _ in range(2):
            url, _err = resolve_hls_url(
                "https://twitch.tv/xqc", "best", adaptive=True, use_cache=True
            )
            assert url == "https://example.com/single.m3u8"

        # First call: master attempt + single rendition. Second call: master
        # attempt only, because the single-rendition result is now cached.
        assert calls.count("best") == 1


class TestRecordingArguments:
    def test_recording_gets_codecs_but_not_low_latency(
        self, temp_config_dir: Path
    ) -> None:
        """Low latency shrinks the live edge, which is wrong for a capture."""
        api = TwitchXApi()
        api._eval_js = lambda code: None  # type: ignore[method-assign]
        api.save_settings(json.dumps({"low_latency_mode": True}))
        settings = get_settings(load_config())

        playback = api._streams._streamlink_args("twitch", settings)
        recording = api._streams._streamlink_args(
            "twitch", settings, low_latency=False
        )

        assert "--twitch-low-latency" in playback
        assert "--twitch-low-latency" not in recording
        assert any("supported-codecs" in a for a in recording)


class TestRefreshEchoesRequestId:
    """The player drops replies whose id no longer matches its own state."""

    def test_request_id_is_echoed(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        captured: dict[str, Any] = {}
        monkeypatch.setattr("ui.api.streams.resolve_hls_url", _spy(captured))
        emitted = _sync_api(api, monkeypatch)

        api.refresh_stream_url("xqc", "twitch", "best", 42)

        payload = [c for c in emitted if "onStreamUrlRefreshed" in c][0]
        data = json.loads(payload.split("(", 1)[1].rsplit(")", 1)[0])
        assert data["request_id"] == 42
        assert data["quality"] == "best"

    def test_slot_request_id_and_channel_are_echoed(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        captured: dict[str, Any] = {}
        monkeypatch.setattr("ui.api.streams.resolve_hls_url", _spy(captured))
        emitted = _sync_api(api, monkeypatch)

        api.refresh_multi_slot_url(1, "xqc", "twitch", "best", 7)

        payload = [c for c in emitted if "onMultiSlotUrlRefreshed" in c][0]
        data = json.loads(payload.split("(", 1)[1].rsplit(")", 1)[0])
        assert data["request_id"] == 7
        assert data["channel"] == "xqc"
        assert data["slot_idx"] == 1

    def test_youtube_rejection_still_carries_the_id(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Otherwise the player would treat the refusal as a stale reply and hang."""
        api = TwitchXApi()
        emitted = _sync_api(api, monkeypatch)

        api.refresh_stream_url("UCabc", "youtube", "best", 5)

        payload = [c for c in emitted if "onStreamUrlRefreshed" in c][0]
        data = json.loads(payload.split("(", 1)[1].rsplit(")", 1)[0])
        assert data["request_id"] == 5
        assert data["ok"] is False


class TestTargetedCacheInvalidation:
    """Refreshing one channel must not evict the other multistream slots."""

    def teardown_method(self) -> None:
        invalidate_resolve_cache()

    def test_only_the_refreshed_channel_is_evicted(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        invalidate_resolve_cache()
        spawns: list[str] = []

        def fake_run(
            resolved_sl: str,
            stream_url: str,
            quality: str | None,
            extra_args: Any = None,
        ) -> tuple[str | None, str]:
            spawns.append(stream_url)
            return f"https://example.com/{stream_url[-4:]}.m3u8", ""

        monkeypatch.setattr(
            "core.stream_resolver.shutil.which", lambda p: "/usr/bin/streamlink"
        )
        monkeypatch.setattr("core.stream_resolver._run_streamlink", fake_run)

        api = TwitchXApi()
        _sync_api(api, monkeypatch)
        settings = get_settings(load_config())

        api._streams._resolve_for_player("aaaa", "best", "twitch", settings)
        api._streams._resolve_for_player("bbbb", "best", "twitch", settings)
        assert len(spawns) == 2

        api._streams._invalidate_resolve_for("aaaa", "twitch")

        # bbbb is still cached; only aaaa has to be resolved again.
        api._streams._resolve_for_player("bbbb", "best", "twitch", settings)
        assert len(spawns) == 2
        api._streams._resolve_for_player("aaaa", "best", "twitch", settings)
        assert len(spawns) == 3


class TestSaveQuality:
    def test_live_switch_persists_quality(self, temp_config_dir: Path) -> None:
        api = TwitchXApi()
        api.save_quality("720p60")
        assert get_settings(load_config())["quality"] == "720p60"

    def test_empty_quality_is_ignored(self, temp_config_dir: Path) -> None:
        api = TwitchXApi()
        api.save_quality("1080p60")
        api.save_quality("")
        assert get_settings(load_config())["quality"] == "1080p60"
