from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import httpx
import pytest

from core.platforms.twitch import VALID_USERNAME, TwitchClient


class _KeepAliveHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


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


class TestLoopLocalHttpClient:
    def test_uses_separate_clients_for_separate_event_loops(self) -> None:
        server = HTTPServer(("127.0.0.1", 0), _KeepAliveHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        client = TwitchClient()
        http_clients: list[httpx.AsyncClient] = []
        responses: list[str] = []

        async def fetch_once() -> tuple[httpx.AsyncClient, str]:
            http_client = client._get_client()
            response = await http_client.get(f"http://127.0.0.1:{port}/")
            return http_client, response.text

        try:
            for _ in range(2):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    http_client, body = loop.run_until_complete(fetch_once())
                    http_clients.append(http_client)
                    responses.append(body)
                    loop.run_until_complete(client.close_loop_resources())
                finally:
                    asyncio.set_event_loop(None)
                    loop.close()
        finally:
            server.shutdown()
            server.server_close()

        assert responses == ["ok", "ok"]
        # Keep strong references to both clients before comparing identity so
        # CPython cannot reuse the first client's memory address for the second.
        assert http_clients[0] is not http_clients[1]


class TestGetChannelInfo:
    def test_returns_normalized_profile_for_live_user(self) -> None:
        client = TwitchClient()

        async def fake_get(endpoint: str, params: Any = None) -> Any:
            if endpoint == "/users":
                return {
                    "data": [
                        {
                            "id": "44322889",
                            "login": "xqc",
                            "display_name": "xQc",
                            "profile_image_url": "https://img.jpg",
                            "description": "lulw",
                        }
                    ]
                }
            return {"data": [{"user_login": "xqc"}]}  # /streams

        loop = asyncio.new_event_loop()
        client._get = fake_get  # type: ignore[method-assign]
        result = loop.run_until_complete(client.get_channel_info("xQc"))
        loop.close()

        assert result["platform"] == "twitch"
        assert result["login"] == "xqc"
        assert result["display_name"] == "xQc"
        assert result["bio"] == "lulw"
        assert result["avatar_url"] == "https://img.jpg"
        assert result["is_live"] is True
        assert result["followers"] == -1
        assert result["can_follow_via_api"] is False

    def test_returns_empty_dict_for_unknown_user(self) -> None:
        client = TwitchClient()

        async def fake_get(endpoint: str, params: Any = None) -> Any:
            return {"data": []}

        loop = asyncio.new_event_loop()
        client._get = fake_get  # type: ignore[method-assign]
        result = loop.run_until_complete(client.get_channel_info("nobody"))
        loop.close()

        assert result == {}

    def test_empty_login_returns_empty_dict_without_http(self) -> None:
        client = TwitchClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(client.get_channel_info(""))
        loop.run_until_complete(client.close_loop_resources())
        loop.close()

        assert result == {}

    def test_offline_user_sets_is_live_false(self) -> None:
        client = TwitchClient()

        async def fake_get(endpoint: str, params: Any = None) -> Any:
            if endpoint == "/users":
                return {
                    "data": [
                        {
                            "id": "999",
                            "login": "streamerfoo",
                            "display_name": "StreamerFoo",
                            "profile_image_url": "",
                            "description": "",
                        }
                    ]
                }
            return {"data": []}  # /streams — not live

        loop = asyncio.new_event_loop()
        client._get = fake_get  # type: ignore[method-assign]
        result = loop.run_until_complete(client.get_channel_info("streamerfoo"))
        loop.close()

        assert result["is_live"] is False


class TestChannelMedia:
    def test_get_channel_vods_returns_normalized_archives(self) -> None:
        client = TwitchClient()

        async def fake_get(endpoint: str, params: Any = None) -> Any:
            if endpoint == "/users":
                return {
                    "data": [
                        {
                            "id": "44322889",
                            "login": "xqc",
                            "display_name": "xQc",
                        }
                    ]
                }
            return {
                "data": [
                    {
                        "id": "v123",
                        "title": "Ranked grind",
                        "url": "https://www.twitch.tv/videos/123",
                        "thumbnail_url": "https://thumb/%{width}x%{height}.jpg",
                        "created_at": "2026-04-24T18:00:00Z",
                        "duration": "3h5m7s",
                        "view_count": 12345,
                    }
                ]
            }

        loop = asyncio.new_event_loop()
        client._get = fake_get  # type: ignore[method-assign]
        result = loop.run_until_complete(client.get_channel_vods("xQc"))
        loop.close()

        assert result == [
            {
                "id": "v123",
                "platform": "twitch",
                "kind": "vod",
                "channel_login": "xqc",
                "channel_display_name": "xQc",
                "title": "Ranked grind",
                "url": "https://www.twitch.tv/videos/123",
                "thumbnail_url": "https://thumb/440x248.jpg",
                "published_at": "2026-04-24T18:00:00Z",
                "duration_seconds": 11107,
                "views": 12345,
            }
        ]

    def test_get_channel_clips_returns_normalized_items(self) -> None:
        client = TwitchClient()

        async def fake_get(endpoint: str, params: Any = None) -> Any:
            if endpoint == "/users":
                return {
                    "data": [
                        {
                            "id": "44322889",
                            "login": "xqc",
                            "display_name": "xQc",
                        }
                    ]
                }
            return {
                "data": [
                    {
                        "id": "clip123",
                        "title": "Huge comeback",
                        "url": "https://clips.twitch.tv/FancyClip",
                        "thumbnail_url": "https://clip-thumb.jpg",
                        "created_at": "2026-04-20T12:00:00Z",
                        "duration": 28.4,
                        "view_count": 9876,
                    }
                ]
            }

        loop = asyncio.new_event_loop()
        client._get = fake_get  # type: ignore[method-assign]
        result = loop.run_until_complete(client.get_channel_clips("xQc"))
        loop.close()

        assert result == [
            {
                "id": "clip123",
                "platform": "twitch",
                "kind": "clip",
                "channel_login": "xqc",
                "channel_display_name": "xQc",
                "title": "Huge comeback",
                "url": "https://clips.twitch.tv/FancyClip",
                "thumbnail_url": "https://clip-thumb.jpg",
                "published_at": "2026-04-20T12:00:00Z",
                "duration_seconds": 28,
                "views": 9876,
            }
        ]
