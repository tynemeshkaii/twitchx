from __future__ import annotations

import asyncio
import time
import types

import pytest

import core.kick as kick_mod
from core.kick import KickClient


def _channel_payload(*, is_live: bool = True) -> dict[str, object]:
    return {
        "slug": "trainwreckstv",
        "broadcaster_user_id": 123,
        "category": {
            "id": 1,
            "name": "Slots",
            "thumbnail": "https://img.example/category.jpg",
        },
        "stream_title": "Late night slots",
        "stream": {
            "is_live": is_live,
            "viewer_count": 12345,
            "start_time": "2026-03-16T10:00:00Z",
            "thumbnail": "https://img.example/thumb.jpg",
        }
        if is_live
        else None,
    }


def _user_payload() -> dict[str, object]:
    return {
        "user_id": 123,
        "name": "Trainwreckstv",
        "profile_picture": "https://img.example/avatar.png",
    }


def _livestream_payload(
    *,
    slug: str = "trainwreckstv",
    user_id: int = 123,
    title: str = "Late night slots",
    category_name: str = "Slots",
) -> dict[str, object]:
    return {
        "slug": slug,
        "broadcaster_user_id": user_id,
        "stream_title": title,
        "viewer_count": 12345,
        "started_at": "2026-03-16T10:00:00Z",
        "thumbnail": "https://img.example/thumb.jpg",
        "profile_picture": "https://img.example/avatar.png",
        "category": {
            "id": 1,
            "name": category_name,
            "thumbnail": "https://img.example/category.jpg",
        },
    }


class TestKickClient:
    def test_refresh_app_token_saves_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = KickClient.__new__(KickClient)
        client._config = {
            "kick_client_id": "kick-id",
            "kick_client_secret": "kick-secret",
            "kick_access_token": "",
            "kick_token_expires_at": 0,
        }
        client._reload_config = lambda: None  # type: ignore[method-assign]

        class FakeResponse:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict[str, object]:
                return {"access_token": "kick-token", "expires_in": 3600}

        async def fake_post(url: str, data: dict[str, str]) -> FakeResponse:
            assert url == kick_mod.KICK_AUTH_URL
            assert data == {
                "client_id": "kick-id",
                "client_secret": "kick-secret",
                "grant_type": "client_credentials",
            }
            return FakeResponse()

        saved: dict[str, object] = {}
        client._client = types.SimpleNamespace(post=fake_post)
        monkeypatch.setattr(kick_mod, "save_config", lambda config: saved.update(config))

        loop = asyncio.new_event_loop()
        try:
            token = loop.run_until_complete(KickClient._refresh_app_token(client))
        finally:
            loop.close()

        assert token == "kick-token"
        assert saved["kick_access_token"] == "kick-token"
        assert saved["kick_token_expires_at"] >= int(time.time()) + 3590

    def test_get_streams_and_users_maps_public_api_payloads(self) -> None:
        client = KickClient.__new__(KickClient)

        async def fake_get_channels_by_slug(
            logins: list[str],
        ) -> list[dict[str, object]]:
            assert logins == ["trainwreckstv"]
            return [_channel_payload()]

        async def fake_get_users_by_id(
            user_ids: list[int],
        ) -> list[dict[str, object]]:
            assert user_ids == [123]
            return [_user_payload()]

        client._get_channels_by_slug = fake_get_channels_by_slug  # type: ignore[method-assign]
        client._get_users_by_id = fake_get_users_by_id  # type: ignore[method-assign]

        loop = asyncio.new_event_loop()
        try:
            streams, users = loop.run_until_complete(
                KickClient.get_streams_and_users(client, ["Trainwreckstv"])
            )
        finally:
            loop.close()

        assert streams == [
            {
                "platform": "kick",
                "channel_ref": "kick:trainwreckstv",
                "user_login": "trainwreckstv",
                "user_name": "Trainwreckstv",
                "viewer_count": 12345,
                "title": "Late night slots",
                "game_name": "Slots",
                "game_id": "",
                "started_at": "2026-03-16T10:00:00Z",
                "thumbnail_url": "https://img.example/thumb.jpg",
            }
        ]
        assert users == [
            {
                "platform": "kick",
                "channel_ref": "kick:trainwreckstv",
                "login": "trainwreckstv",
                "display_name": "Trainwreckstv",
                "profile_image_url": "https://img.example/avatar.png",
            }
        ]

    def test_get_live_streams_skips_offline_channels(self) -> None:
        client = KickClient.__new__(KickClient)
        offline_payload = _channel_payload(is_live=False)

        async def fake_get_channels_by_slug(
            logins: list[str],
        ) -> list[dict[str, object]]:
            return [offline_payload]

        async def fake_get_users_by_id(
            user_ids: list[int],
        ) -> list[dict[str, object]]:
            return [_user_payload()]

        client._get_channels_by_slug = fake_get_channels_by_slug  # type: ignore[method-assign]
        client._get_users_by_id = fake_get_users_by_id  # type: ignore[method-assign]

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                KickClient.get_live_streams(client, ["Trainwreckstv"])
            )
        finally:
            loop.close()

        assert result == []

    def test_search_channels_returns_live_match_for_fuzzy_query(self) -> None:
        client = KickClient.__new__(KickClient)

        async def fake_get_livestreams(**kwargs: object) -> list[dict[str, object]]:
            assert kwargs == {"limit": 100, "sort": "viewer_count"}
            return [_livestream_payload()]

        async def fake_get_users_by_id(
            user_ids: list[int],
        ) -> list[dict[str, object]]:
            assert user_ids == [123]
            return [_user_payload()]

        async def fake_get_channels_by_slug(
            logins: list[str],
        ) -> list[dict[str, object]]:
            assert logins == ["train"]
            return []

        client._get_livestreams = fake_get_livestreams  # type: ignore[method-assign]
        client._get_users_by_id = fake_get_users_by_id  # type: ignore[method-assign]
        client._get_channels_by_slug = fake_get_channels_by_slug  # type: ignore[method-assign]

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(KickClient.search_channels(client, "train"))
        finally:
            loop.close()

        assert result == [
            {
                "platform": "kick",
                "broadcaster_login": "kick:trainwreckstv",
                "display_name": "Trainwreckstv",
                "is_live": True,
                "game_name": "Slots",
            }
        ]

    def test_search_channels_returns_exact_offline_channel_match(self) -> None:
        client = KickClient.__new__(KickClient)

        async def fake_get_livestreams(**kwargs: object) -> list[dict[str, object]]:
            return []

        async def fake_get_users_by_id(
            user_ids: list[int],
        ) -> list[dict[str, object]]:
            assert user_ids == [123]
            return [_user_payload()]

        async def fake_get_channels_by_slug(
            logins: list[str],
        ) -> list[dict[str, object]]:
            assert logins == ["trainwreckstv"]
            return [_channel_payload(is_live=False)]

        client._get_livestreams = fake_get_livestreams  # type: ignore[method-assign]
        client._get_users_by_id = fake_get_users_by_id  # type: ignore[method-assign]
        client._get_channels_by_slug = fake_get_channels_by_slug  # type: ignore[method-assign]

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                KickClient.search_channels(client, "Trainwreckstv")
            )
        finally:
            loop.close()

        assert result == [
            {
                "platform": "kick",
                "broadcaster_login": "kick:trainwreckstv",
                "display_name": "Trainwreckstv",
                "is_live": False,
                "game_name": "Slots",
            }
        ]

    def test_search_channels_returns_empty_for_unknown_channel(self) -> None:
        client = KickClient.__new__(KickClient)

        async def fake_get_livestreams(**kwargs: object) -> list[dict[str, object]]:
            return []

        async def fake_get_users_by_id(
            user_ids: list[int],
        ) -> list[dict[str, object]]:
            return []

        async def fake_get_channels_by_slug(
            logins: list[str],
        ) -> list[dict[str, object]]:
            assert logins == ["missing"]
            return []

        client._get_livestreams = fake_get_livestreams  # type: ignore[method-assign]
        client._get_users_by_id = fake_get_users_by_id  # type: ignore[method-assign]
        client._get_channels_by_slug = fake_get_channels_by_slug  # type: ignore[method-assign]

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                KickClient.search_channels(client, "missing")
            )
        finally:
            loop.close()

        assert result == []
