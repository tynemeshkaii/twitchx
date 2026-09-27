"""Codec negotiation: what we advertise to Twitch, and what unlocks 1440p60."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from core.codecs import resolve_supported_codecs, twitch_codec_args
from core.stream_resolver import _quality_arg
from ui.api import TwitchXApi


class TestResolveSupportedCodecs:
    def test_auto_always_requests_hevc(self) -> None:
        """HEVC is where Twitch keeps its high renditions and is safe everywhere."""
        assert resolve_supported_codecs("auto", None) == "h264,h265"

    def test_auto_adds_av1_only_on_hardware_decode(self) -> None:
        assert resolve_supported_codecs("auto", True) == "h264,h265,av1"

    def test_auto_omits_av1_without_hardware_decode(self) -> None:
        assert resolve_supported_codecs("auto", False) == "h264,h265"

    def test_auto_omits_av1_while_probe_is_unanswered(self) -> None:
        """A resolve before the probe replies must not gamble on AV1."""
        assert resolve_supported_codecs("auto", None) == "h264,h265"

    def test_explicit_mode_overrides_capability(self) -> None:
        assert resolve_supported_codecs("h264", True) == "h264"
        assert resolve_supported_codecs("h264,h265,av1", False) == "h264,h265,av1"

    def test_unknown_mode_falls_back_to_auto(self) -> None:
        assert resolve_supported_codecs("nonsense", True) == "h264,h265,av1"


class TestTwitchCodecArgs:
    def test_auto_emits_the_flag(self) -> None:
        assert twitch_codec_args("auto", False) == [
            "--twitch-supported-codecs=h264,h265"
        ]

    def test_av1_capable_host_gets_av1(self) -> None:
        assert twitch_codec_args("auto", True) == [
            "--twitch-supported-codecs=h264,h265,av1"
        ]

    def test_h264_only_emits_nothing(self) -> None:
        """h264 is streamlink's own default; omitting the flag keeps commands stable."""
        assert twitch_codec_args("h264", True) == []


class TestQualityLadder1440:
    def test_1440p60_steps_down_through_1080(self) -> None:
        ladder = _quality_arg("1440p60").split(",")
        assert ladder[0] == "1440p60"
        assert ladder.index("1080p60") < ladder.index("best")
        assert ladder[-1] == "best"

    def test_1080p60_ladder_never_climbs_to_1440(self) -> None:
        """Picking 1080p60 must not be upgraded into a heavier rendition."""
        assert "1440p" not in _quality_arg("1080p60")


def _resolver_spy(captured: dict[str, Any]):
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
        captured["quality"] = quality
        return ("https://example.com/s.m3u8", "")

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


class TestCodecArgsReachTheResolver:
    def test_twitch_watch_sends_codec_flag(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        api._live_streams = [{"login": "xqc", "title": "t", "platform": "twitch"}]
        captured: dict[str, Any] = {}
        monkeypatch.setattr("ui.api.streams.resolve_hls_url", _resolver_spy(captured))
        _sync_api(api, monkeypatch)

        api.watch("xqc", "1440p60")

        assert "--twitch-supported-codecs=h264,h265" in captured["extra_args"]
        assert captured["quality"] == "1440p60"

    def test_av1_report_reaches_the_resolver(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        api._live_streams = [{"login": "xqc", "title": "t", "platform": "twitch"}]
        captured: dict[str, Any] = {}
        monkeypatch.setattr("ui.api.streams.resolve_hls_url", _resolver_spy(captured))
        _sync_api(api, monkeypatch)

        api.set_codec_support({"av1": True, "hevc": True})
        api.watch("xqc", "best")

        assert "--twitch-supported-codecs=h264,h265,av1" in captured["extra_args"]

    def test_kick_gets_no_twitch_codec_flag(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        api._live_streams = [{"login": "trainwreck", "title": "t", "platform": "kick"}]
        captured: dict[str, Any] = {}
        monkeypatch.setattr("ui.api.streams.resolve_hls_url", _resolver_spy(captured))
        _sync_api(api, monkeypatch)

        api.watch("trainwreck", "best")

        assert not any("supported-codecs" in a for a in captured["extra_args"])

    def test_low_latency_and_codecs_combine(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        api._live_streams = [{"login": "xqc", "title": "t", "platform": "twitch"}]
        api.save_settings(json.dumps({"low_latency_mode": True}))
        captured: dict[str, Any] = {}
        monkeypatch.setattr("ui.api.streams.resolve_hls_url", _resolver_spy(captured))
        _sync_api(api, monkeypatch)

        api.watch("xqc", "best")

        assert "--twitch-low-latency" in captured["extra_args"]
        assert "--twitch-supported-codecs=h264,h265" in captured["extra_args"]

    def test_h264_setting_removes_the_flag(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = TwitchXApi()
        api._live_streams = [{"login": "xqc", "title": "t", "platform": "twitch"}]
        api.save_settings(json.dumps({"stream_codecs": "h264"}))
        captured: dict[str, Any] = {}
        monkeypatch.setattr("ui.api.streams.resolve_hls_url", _resolver_spy(captured))
        _sync_api(api, monkeypatch)

        api.watch("xqc", "best")

        assert captured["extra_args"] == []


class TestSetCodecSupport:
    def test_records_hardware_av1(self, temp_config_dir: Path) -> None:
        api = TwitchXApi()
        api.set_codec_support({"av1": True, "hevc": True})
        assert api._av1_capable is True

    def test_records_missing_av1(self, temp_config_dir: Path) -> None:
        api = TwitchXApi()
        api.set_codec_support({"av1": False, "hevc": True})
        assert api._av1_capable is False

    def test_absent_av1_key_stays_unknown(self, temp_config_dir: Path) -> None:
        api = TwitchXApi()
        api.set_codec_support({"hevc": True})
        assert api._av1_capable is None

    def test_garbage_payload_is_ignored(self, temp_config_dir: Path) -> None:
        api = TwitchXApi()
        api.set_codec_support("not a dict")  # type: ignore[arg-type]
        api.set_codec_support(None)
        assert api._av1_capable is None


class TestCodecSettingValidation:
    def test_valid_mode_is_persisted(self, temp_config_dir: Path) -> None:
        api = TwitchXApi()
        api.save_settings(json.dumps({"stream_codecs": "h264,h265,av1"}))
        from core.storage import get_settings, load_config

        assert get_settings(load_config())["stream_codecs"] == "h264,h265,av1"

    def test_invalid_mode_is_rejected(self, temp_config_dir: Path) -> None:
        api = TwitchXApi()
        api.save_settings(json.dumps({"stream_codecs": "vp9"}))
        from core.storage import get_settings, load_config

        assert get_settings(load_config())["stream_codecs"] == "auto"
