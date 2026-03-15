from __future__ import annotations

from app import StreamDeckApp


class TestSanitizeUsername:
    def test_plain_username(self) -> None:
        assert StreamDeckApp._sanitize_username("xqc") == "xqc"

    def test_strips_whitespace(self) -> None:
        assert StreamDeckApp._sanitize_username("  xqc  ") == "xqc"

    def test_full_url(self) -> None:
        assert StreamDeckApp._sanitize_username("https://www.twitch.tv/xqc") == "xqc"

    def test_short_url(self) -> None:
        assert StreamDeckApp._sanitize_username("twitch.tv/xqc") == "xqc"

    def test_url_with_path(self) -> None:
        assert StreamDeckApp._sanitize_username("https://twitch.tv/just_ns") == "just_ns"

    def test_lowercases(self) -> None:
        assert StreamDeckApp._sanitize_username("XqC") == "xqc"

    def test_strips_invalid_chars(self) -> None:
        assert StreamDeckApp._sanitize_username("user@name!") == "username"

    def test_empty_string(self) -> None:
        assert StreamDeckApp._sanitize_username("") == ""

    def test_only_special_chars(self) -> None:
        assert StreamDeckApp._sanitize_username("@#$%") == ""
