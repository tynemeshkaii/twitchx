from __future__ import annotations

from core.utils import (
    format_viewers,
    normalize_channel_id,
    sanitize_kick_slug,
    sanitize_twitch_login,
    sanitize_youtube_id,
)


class TestFormatViewers:
    def test_millions(self) -> None:
        assert format_viewers(1_500_000) == "1.5M"

    def test_thousands(self) -> None:
        assert format_viewers(2_500) == "2.5k"

    def test_hundreds(self) -> None:
        assert format_viewers(500) == "500"


class TestSanitizeTwitchLogin:
    def test_plain(self) -> None:
        assert sanitize_twitch_login("xqc") == "xqc"

    def test_full_url(self) -> None:
        assert sanitize_twitch_login("https://www.twitch.tv/xqc") == "xqc"

    def test_no_scheme(self) -> None:
        assert sanitize_twitch_login("twitch.tv/xqc") == "xqc"

    def test_whitespace(self) -> None:
        assert sanitize_twitch_login("  xqc  ") == "xqc"

    def test_invalid_chars(self) -> None:
        assert sanitize_twitch_login("xq!c") == "xqc"

    def test_empty(self) -> None:
        assert sanitize_twitch_login("") == ""

    def test_lowercases(self) -> None:
        assert sanitize_twitch_login("XqC") == "xqc"

    def test_url_with_path(self) -> None:
        assert sanitize_twitch_login("https://twitch.tv/just_ns") == "just_ns"

    def test_only_special_chars(self) -> None:
        assert sanitize_twitch_login("@#$%") == ""


class TestSanitizeKickSlug:
    def test_plain(self) -> None:
        assert sanitize_kick_slug("train-wreck") == "train-wreck"

    def test_url(self) -> None:
        assert sanitize_kick_slug("https://kick.com/train-wreck") == "train-wreck"

    def test_whitespace(self) -> None:
        assert sanitize_kick_slug("  train-wreck  ") == "train-wreck"

    def test_invalid_chars(self) -> None:
        assert sanitize_kick_slug("train!wreck") == "trainwreck"


class TestSanitizeYouTubeId:
    def test_channel_id(self) -> None:
        raw = "UCxxxxxxxxxxxxxxxxxxxxxxxx"
        assert sanitize_youtube_id(raw) == raw

    def test_strips_invalid(self) -> None:
        assert sanitize_youtube_id("UCxxx!!!") == "UCxxx"

    def test_empty(self) -> None:
        assert sanitize_youtube_id("") == ""


class TestNormalizeChannelId:
    def test_preserve_case(self) -> None:
        raw = "UCxxxxxxxxxxxxxxxxxxxxxxxx"
        assert normalize_channel_id(raw) == raw

    def test_strips_special(self) -> None:
        assert normalize_channel_id("UCxxx!!!") == "UCxxx"
