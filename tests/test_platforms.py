from __future__ import annotations

from core.platforms import (
    build_channel_ref,
    build_channel_url,
    format_channel_ref,
    normalize_channel_ref,
    split_channel_ref,
)


class TestSplitChannelRef:
    def test_plain_username_defaults_to_twitch(self) -> None:
        assert split_channel_ref("xqc") == ("twitch", "xqc")

    def test_prefixed_kick_ref(self) -> None:
        assert split_channel_ref("kick:Trainwreckstv") == ("kick", "trainwreckstv")

    def test_twitch_url(self) -> None:
        assert split_channel_ref("https://www.twitch.tv/xqc") == ("twitch", "xqc")

    def test_kick_url(self) -> None:
        assert split_channel_ref("https://kick.com/Trainwreckstv") == (
            "kick",
            "trainwreckstv",
        )


class TestNormalizeChannelRef:
    def test_returns_prefixed_ref(self) -> None:
        assert normalize_channel_ref("xqc") == "twitch:xqc"
        assert normalize_channel_ref("kick:Trainwreckstv") == "kick:trainwreckstv"


class TestBuildChannelUrl:
    def test_builds_twitch_url(self) -> None:
        assert build_channel_url("xqc") == "https://twitch.tv/xqc"

    def test_builds_kick_url(self) -> None:
        assert build_channel_url("kick:Trainwreckstv") == "https://kick.com/trainwreckstv"


class TestBuildChannelRef:
    def test_omits_prefix_for_default_platform(self) -> None:
        assert build_channel_ref("twitch", "xqc") == "xqc"

    def test_keeps_prefix_for_non_default_platform(self) -> None:
        assert build_channel_ref("kick", "Trainwreckstv") == "kick:trainwreckstv"


class TestFormatChannelRef:
    def test_formats_default_platform_without_prefix(self) -> None:
        assert format_channel_ref("twitch:xqc") == "xqc"

    def test_formats_non_default_platform_with_prefix(self) -> None:
        assert format_channel_ref("kick:trainwreckstv") == "kick:trainwreckstv"
