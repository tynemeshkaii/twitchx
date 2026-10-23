from __future__ import annotations

import pytest

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
        assert format_viewers(2_500) == "2.5K"

    def test_hundreds(self) -> None:
        assert format_viewers(500) == "500"

    # Same table is checked against formatViewers (ui/js/utils.js) by hand
    # with node; the two formatters must agree.
    @pytest.mark.parametrize(
        ("count", "expected"),
        [
            (0, "0"),
            (950, "950"),
            (999, "999"),
            (1_000, "1K"),
            (1_050, "1.1K"),
            (9_700, "9.7K"),
            (12_000, "12K"),
            (88_300, "88.3K"),
            (99_949, "99.9K"),
            (99_950, "100K"),
            (100_000, "100K"),
            (210_000, "210K"),
            (999_499, "999K"),
            (999_500, "1M"),
            (999_950, "1M"),
            (1_000_000, "1M"),
            (1_200_000, "1.2M"),
            (12_000_000, "12M"),
        ],
    )
    def test_boundaries(self, count: int, expected: str) -> None:
        assert format_viewers(count) == expected


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
