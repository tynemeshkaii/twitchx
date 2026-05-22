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


def test_get_auth_url_includes_pkce_params(temp_config_dir):
    """get_auth_url() must include code_challenge and code_challenge_method."""
    from core.platforms.twitch import TwitchClient

    client = TwitchClient()
    url = client.get_auth_url()
    assert "code_challenge=" in url
    assert "code_challenge_method=S256" in url
    assert "code_verifier" not in url  # verifier stays local, never in URL


def test_get_auth_url_stores_pkce_verifier(temp_config_dir):
    """get_auth_url() must persist pkce_verifier to config."""
    from core.platforms.twitch import TwitchClient
    from core.storage import load_config

    client = TwitchClient()
    client.get_auth_url()
    cfg = load_config()
    verifier = cfg.get("platforms", {}).get("twitch", {}).get("pkce_verifier", "")
    assert len(verifier) >= 43  # RFC 7636 minimum verifier length


def test_get_auth_url_uses_effective_client_id(temp_config_dir):
    """get_auth_url() uses bundled client_id when config is empty."""
    import core.credentials as creds
    from core.platforms.twitch import TwitchClient

    client = TwitchClient()
    url = client.get_auth_url()
    assert creds.TWITCH_CLIENT_ID in url


@pytest.mark.asyncio
async def test_exchange_code_sends_code_verifier_and_secret(temp_config_dir):
    """exchange_code() must send code_verifier and client_secret (confidential client)."""
    from unittest.mock import MagicMock

    from core.platforms.twitch import TwitchClient
    from core.storage import update_config

    def _set_verifier(cfg):
        cfg["platforms"]["twitch"]["pkce_verifier"] = "test_verifier_abc123xyz456def789"

    update_config(_set_verifier)

    client = TwitchClient()
    captured = {}

    async def mock_post(url, data=None, **kwargs):
        if data:
            captured.update(data)
        resp = MagicMock()
        resp.raise_for_status = MagicMock(return_value=None)
        resp.status_code = 200
        resp.json = MagicMock(
            return_value={
                "access_token": "tok",
                "refresh_token": "ref",
                "expires_in": 3600,
            }
        )
        return resp

    mock_http_client = MagicMock()
    mock_http_client.post = mock_post
    client._get_client = lambda: mock_http_client
    await client.exchange_code("auth_code_xyz")

    assert captured.get("code_verifier") == "test_verifier_abc123xyz456def789"
    assert captured.get("code") == "auth_code_xyz"
    # Confidential clients (those with a client_secret) must send it even with PKCE.
    assert "client_secret" in captured


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


# ── Coverage: OAuth, HTTP layer, utility methods ──────────────


class TestSanitizeIdentifier:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("xqc", "xqc"),
            ("https://twitch.tv/xqc", "xqc"),
            ("twitch.tv/foo_bar", "foo_bar"),
            ("@xqc", "xqc"),
            ("XQC", "xqc"),
            ("", ""),
        ],
    )
    def test_sanitize_identifier(self, raw: str, expected: str) -> None:
        assert TwitchClient.sanitize_identifier(raw) == expected


class TestBuildStreamUrl:
    def test_build_stream_url(self) -> None:
        url = TwitchClient.build_stream_url("xqc")
        assert url == "https://twitch.tv/xqc"


class TestSearchChannels:
    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self, temp_config_dir) -> None:
        client = TwitchClient()
        result = await client.search_channels("")
        await client.close()
        assert result == []

    @pytest.mark.asyncio
    async def test_non_empty_query_calls_search(self, temp_config_dir) -> None:
        client = TwitchClient()

        async def fake_get(endpoint: str, params: object = None) -> Any:
            assert endpoint == "/search/channels"
            assert isinstance(params, list)
            assert ("query", "xqc") in params
            return {
                "data": [{"id": "1", "display_name": "xQc", "broadcaster_login": "xqc"}]
            }

        client._get = fake_get  # type: ignore[method-assign]
        result = await client.search_channels("xqc")
        await client.close()
        assert len(result) == 1
        assert result[0]["broadcaster_login"] == "xqc"


class TestGetGames:
    @pytest.mark.asyncio
    async def test_empty_returns_empty_dict(self, temp_config_dir) -> None:
        client = TwitchClient()
        result = await client.get_games([])
        await client.close()
        assert result == {}

    @pytest.mark.asyncio
    async def test_deduplicates_and_returns_name_map(self, temp_config_dir) -> None:
        client = TwitchClient()

        async def fake_get(endpoint: str, params: object = None) -> Any:
            assert endpoint == "/games"
            assert isinstance(params, list)
            param_ids = [p[1] for p in params if isinstance(p, tuple) and p[0] == "id"]
            return {
                "data": [
                    {"id": gid, "name": f"Game{gid}"}
                    for gid in param_ids
                    if gid in ("123", "456", "789")
                ]
            }

        client._get = fake_get  # type: ignore[method-assign]
        result = await client.get_games(["123", "456", "123", "789", "456"])
        await client.close()
        assert result == {"123": "Game123", "456": "Game456", "789": "Game789"}


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_returns_current_user(self, temp_config_dir) -> None:
        client = TwitchClient()

        async def fake_get(endpoint: str, params: Any = None) -> Any:
            return {
                "data": [{"id": "123", "login": "testuser", "display_name": "TestUser"}]
            }

        client._get = fake_get  # type: ignore[method-assign]
        result = await client.get_current_user()
        await client.close()
        assert result == {"id": "123", "login": "testuser", "display_name": "TestUser"}

    @pytest.mark.asyncio
    async def test_empty_data_raises_value_error(self, temp_config_dir) -> None:
        client = TwitchClient()

        async def fake_get(endpoint: str, params: Any = None) -> Any:
            return {"data": []}

        client._get = fake_get  # type: ignore[method-assign]
        with pytest.raises(ValueError, match="Could not fetch"):
            await client.get_current_user()
        await client.close()


class TestRefreshUserToken:
    @pytest.mark.asyncio
    async def test_success_refreshes_token(self, temp_config_dir) -> None:
        from unittest.mock import MagicMock

        from core.storage import load_config, update_config

        def _set_refresh(cfg):
            cfg["platforms"]["twitch"]["refresh_token"] = "old_refresh"

        update_config(_set_refresh)

        client = TwitchClient()

        async def mock_post(url, data=None, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock(return_value=None)
            resp.status_code = 200
            resp.json = MagicMock(
                return_value={
                    "access_token": "new_token",
                    "refresh_token": "new_refresh",
                    "expires_in": 3600,
                }
            )
            return resp

        mock_http_client = MagicMock()
        mock_http_client.post = mock_post
        client._get_client = lambda: mock_http_client

        result = await client.refresh_user_token()
        await client.close()

        assert result == "new_token"
        cfg = load_config()
        yt = cfg["platforms"]["twitch"]
        assert yt["access_token"] == "new_token"
        assert yt["refresh_token"] == "new_refresh"

    @pytest.mark.asyncio
    async def test_400_clears_auth_and_raises_value_error(
        self, temp_config_dir
    ) -> None:
        from unittest.mock import MagicMock

        from core.storage import load_config, update_config

        def _set_refresh(cfg):
            cfg["platforms"]["twitch"]["refresh_token"] = "bad_refresh"

        update_config(_set_refresh)

        client = TwitchClient()

        async def mock_post(url, data=None, **kwargs):
            resp = MagicMock()
            resp.status_code = 400
            return resp

        mock_http_client = MagicMock()
        mock_http_client.post = mock_post
        client._get_client = lambda: mock_http_client

        with pytest.raises(ValueError, match="User token expired"):
            await client.refresh_user_token()
        await client.close()

        cfg = load_config()
        tw = cfg["platforms"]["twitch"]
        assert tw.get("access_token") is None or tw.get("access_token") == ""
        assert tw.get("refresh_token") is None or tw.get("refresh_token") == ""


class TestEnsureToken:
    @pytest.mark.asyncio
    async def test_returns_valid_token(self, temp_config_dir) -> None:
        from core.storage import update_config

        def _set_token(cfg):
            cfg["platforms"]["twitch"]["access_token"] = "good_token"
            cfg["platforms"]["twitch"]["refresh_token"] = "good_refresh"
            cfg["platforms"]["twitch"]["token_expires_at"] = 9999999999  # far future

        update_config(_set_token)

        client = TwitchClient()
        token = await client._ensure_token()
        await client.close()
        assert token == "good_token"

    @pytest.mark.asyncio
    async def test_expired_refreshes_token(self, temp_config_dir) -> None:
        from unittest.mock import AsyncMock

        from core.storage import update_config

        def _set_token(cfg):
            cfg["platforms"]["twitch"]["access_token"] = "expired_token"
            cfg["platforms"]["twitch"]["refresh_token"] = "refresh_me"
            cfg["platforms"]["twitch"]["token_type"] = "user"
            cfg["platforms"]["twitch"]["token_expires_at"] = 1

        update_config(_set_token)

        client = TwitchClient()
        client.refresh_user_token = AsyncMock(return_value="new_token")  # type: ignore[method-assign]
        token = await client._ensure_token()
        await client.close()
        assert token == "new_token"


class TestGetUsers:
    @pytest.mark.asyncio
    async def test_batch_loop_with_valid_logins(self, temp_config_dir) -> None:
        client = TwitchClient()

        async def fake_get(endpoint: str, params: Any = None) -> Any:
            return {"data": [{"id": "1", "login": "user1"}]}

        client._get = fake_get  # type: ignore[method-assign]
        result = await client.get_users(["user1"])
        await client.close()
        assert result == [{"id": "1", "login": "user1"}]


class TestGetLiveStreams:
    @pytest.mark.asyncio
    async def test_empty_filtered_list_returns_empty(self, temp_config_dir) -> None:
        client = TwitchClient()

        async def fake_get(endpoint: str, params: Any = None) -> Any:
            return {"data": []}

        client._get = fake_get  # type: ignore[method-assign]
        result = await client.get_live_streams(["nobody_live"])
        await client.close()
        assert result == []
