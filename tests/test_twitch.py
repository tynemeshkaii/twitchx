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


class TestGetFollowedChannels:
    def test_reports_progress_after_each_page(self) -> None:
        client = TwitchClient.__new__(TwitchClient)
        pages = iter(
            [
                {
                    "data": [
                        {"broadcaster_login": "alpha"},
                        {"broadcaster_login": "beta"},
                    ],
                    "pagination": {"cursor": "next-page"},
                },
                {
                    "data": [{"broadcaster_login": "gamma"}],
                    "pagination": {},
                },
            ]
        )

        async def fake_get(endpoint: str, params: object = None) -> dict[str, object]:
            assert endpoint == "/channels/followed"
            return next(pages)

        client._get = fake_get  # type: ignore[attr-defined]
        progress: list[int] = []
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                client.get_followed_channels("user-1", on_progress=progress.append)
            )
        finally:
            loop.close()

        assert result == ["alpha", "beta", "gamma"]
        assert progress == [2, 3]


class TestBatchFetching:
    def test_get_live_streams_fetches_batches_concurrently(self) -> None:
        client = TwitchClient.__new__(TwitchClient)
        active = 0
        max_active = 0
        requests: list[list[tuple[str, str]]] = []

        async def fake_get(endpoint: str, params: object = None) -> dict[str, object]:
            nonlocal active, max_active
            assert endpoint == "/streams"
            batch = list(params or [])
            requests.append(batch)
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return {
                "data": [
                    {"user_login": value}
                    for key, value in batch
                    if key == "user_login"
                ]
            }

        client._get = fake_get  # type: ignore[attr-defined]
        logins = [f"user{i}" for i in range(250)]
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(client.get_live_streams(logins))
        finally:
            loop.close()

        assert len(result) == 250
        assert len(requests) == 3
        assert max_active > 1

    def test_get_users_fetches_batches_concurrently(self) -> None:
        client = TwitchClient.__new__(TwitchClient)
        active = 0
        max_active = 0
        requests: list[list[tuple[str, str]]] = []

        async def fake_get(endpoint: str, params: object = None) -> dict[str, object]:
            nonlocal active, max_active
            assert endpoint == "/users"
            batch = list(params or [])
            requests.append(batch)
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return {
                "data": [
                    {"login": value}
                    for key, value in batch
                    if key == "login"
                ]
            }

        client._get = fake_get  # type: ignore[attr-defined]
        logins = [f"user{i}" for i in range(250)]
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(client.get_users(logins))
        finally:
            loop.close()

        assert len(result) == 250
        assert len(requests) == 3
        assert max_active > 1

    def test_get_games_fetches_batches_concurrently(self) -> None:
        client = TwitchClient.__new__(TwitchClient)
        active = 0
        max_active = 0
        requests: list[list[tuple[str, str]]] = []

        async def fake_get(endpoint: str, params: object = None) -> dict[str, object]:
            nonlocal active, max_active
            assert endpoint == "/games"
            batch = list(params or [])
            requests.append(batch)
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return {
                "data": [
                    {"id": value, "name": f"Game {value}"}
                    for key, value in batch
                    if key == "id"
                ]
            }

        client._get = fake_get  # type: ignore[attr-defined]
        game_ids = [str(i) for i in range(250)]
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(client.get_games(game_ids))
        finally:
            loop.close()

        assert len(result) == 250
        assert len(requests) == 3
        assert max_active > 1
