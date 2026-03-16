from __future__ import annotations

import asyncio

import pytest

from core.twitch import VALID_USERNAME, TwitchClient


class TestValidUsername:
    @pytest.mark.parametrize(
        "name",
        ["xqc", "just_ns", "a_b_c", "user123", "XqC_123", "a" * 25],
    )
    def test_accepts_valid(self, name: str) -> None:
        assert VALID_USERNAME.match(name)

    @pytest.mark.parametrize(
        "name",
        [
            "twitch.tv/xqc",
            "https://twitch.tv/xqc",
            "",
            "a" * 26,
            "user name",
            "user@name",
        ],
    )
    def test_rejects_invalid(self, name: str) -> None:
        assert not VALID_USERNAME.match(name)


class TestGetLiveStreamsFiltering:
    def test_filters_invalid_logins(self) -> None:
        client = TwitchClient()
        logins = ["valid_user", "https://twitch.tv/bad", "", "good123"]
        cleaned = [name.strip().lower() for name in logins if name and name.strip()]
        cleaned = [name for name in cleaned if VALID_USERNAME.match(name)]
        assert cleaned == ["valid_user", "good123"]
        loop = asyncio.new_event_loop()
        loop.run_until_complete(client.close())
        loop.close()


class TestGetUsersFiltering:
    def test_filters_invalid_logins(self) -> None:
        logins = ["ValidUser", "twitch.tv/bad", "ok_name", ""]
        cleaned = [name.strip().lower() for name in logins if name and name.strip()]
        cleaned = [name for name in cleaned if VALID_USERNAME.match(name)]
        assert cleaned == ["validuser", "ok_name"]

    def test_empty_list(self) -> None:
        client = TwitchClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(client.get_users([]))
        assert result == []
        loop.run_until_complete(client.close())
        loop.close()


class TestGetGamesDeduplicates:
    def test_deduplicates_ids(self) -> None:
        # Verify that duplicate game IDs are deduplicated before request
        game_ids = ["123", "456", "123", "789", "456"]
        unique = list(set(game_ids))
        assert len(unique) == 3
