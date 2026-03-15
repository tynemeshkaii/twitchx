from __future__ import annotations

from app import StreamDeckApp


class TestSanitizeUsername:
    def test_plain(self) -> None:
        assert StreamDeckApp._sanitize_username("xqc") == "xqc"

    def test_full_url(self) -> None:
        assert StreamDeckApp._sanitize_username("https://www.twitch.tv/xqc") == "xqc"

    def test_no_scheme(self) -> None:
        assert StreamDeckApp._sanitize_username("twitch.tv/xqc") == "xqc"

    def test_whitespace(self) -> None:
        assert StreamDeckApp._sanitize_username("  xqc  ") == "xqc"

    def test_invalid_chars(self) -> None:
        assert StreamDeckApp._sanitize_username("xq!c") == "xqc"

    def test_empty(self) -> None:
        assert StreamDeckApp._sanitize_username("") == ""

    def test_lowercases(self) -> None:
        assert StreamDeckApp._sanitize_username("XqC") == "xqc"

    def test_url_with_path(self) -> None:
        assert StreamDeckApp._sanitize_username("https://twitch.tv/just_ns") == "just_ns"

    def test_only_special_chars(self) -> None:
        assert StreamDeckApp._sanitize_username("@#$%") == ""


class TestMigrateFavorites:
    def test_cleans_urls(self) -> None:
        raw = ["https://twitch.tv/xqc", "just_ns", "twitch.tv/xqc", "good123"]
        sanitize = StreamDeckApp._sanitize_username
        cleaned = []
        seen: set[str] = set()
        for entry in raw:
            name = sanitize(entry)
            if name and name not in seen:
                cleaned.append(name)
                seen.add(name)
        assert cleaned == ["xqc", "just_ns", "good123"]

    def test_noop_clean(self) -> None:
        raw = ["xqc", "just_ns", "good123"]
        sanitize = StreamDeckApp._sanitize_username
        cleaned = []
        seen: set[str] = set()
        for entry in raw:
            name = sanitize(entry)
            if name and name not in seen:
                cleaned.append(name)
                seen.add(name)
        assert cleaned == raw
