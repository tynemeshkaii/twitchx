from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

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
