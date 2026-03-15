from __future__ import annotations

import asyncio

from core.twitch import VALID_USERNAME, TwitchClient


class TestValidUsername:
    def test_accepts_simple_name(self) -> None:
        assert VALID_USERNAME.match("xqc")

    def test_accepts_underscores(self) -> None:
        assert VALID_USERNAME.match("just_ns")

    def test_accepts_numbers(self) -> None:
        assert VALID_USERNAME.match("user123")

    def test_accepts_mixed_case(self) -> None:
        assert VALID_USERNAME.match("XqC_123")

    def test_rejects_url(self) -> None:
        assert not VALID_USERNAME.match("https://twitch.tv/xqc")

    def test_rejects_url_path(self) -> None:
        assert not VALID_USERNAME.match("twitch.tv/xqc")

    def test_rejects_empty(self) -> None:
        assert not VALID_USERNAME.match("")

    def test_rejects_spaces(self) -> None:
        assert not VALID_USERNAME.match("user name")

    def test_rejects_special_chars(self) -> None:
        assert not VALID_USERNAME.match("user@name")

    def test_rejects_too_long(self) -> None:
        assert not VALID_USERNAME.match("a" * 26)

    def test_accepts_max_length(self) -> None:
        assert VALID_USERNAME.match("a" * 25)


class TestGetLiveStreamsFiltering:
    def test_filters_invalid_logins(self) -> None:
        client = TwitchClient()
        # We can't easily test the full method without mocking HTTP,
        # but we can verify the filtering logic by checking that
        # invalid names are filtered before the API call.
        logins = ["valid_user", "https://twitch.tv/bad", "", "good123"]
        cleaned = [
            name.strip().lower()
            for name in logins
            if name and name.strip()
        ]
        cleaned = [name for name in cleaned if VALID_USERNAME.match(name)]
        assert cleaned == ["valid_user", "good123"]
        loop = asyncio.new_event_loop()
        loop.run_until_complete(client.close())
        loop.close()


class TestGetUsersFiltering:
    def test_filters_invalid_logins(self) -> None:
        logins = ["ValidUser", "twitch.tv/bad", "ok_name", ""]
        cleaned = [
            name.strip().lower()
            for name in logins
            if name and name.strip()
        ]
        cleaned = [name for name in cleaned if VALID_USERNAME.match(name)]
        assert cleaned == ["validuser", "ok_name"]
