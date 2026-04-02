from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest

from core.platforms.kick import (
    VALID_SLUG,
    KickClient,
    _generate_code_challenge,
    _generate_code_verifier,
)

# ── Helpers ───────────────────────────────────────────────────


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


# ── VALID_SLUG ─────────────────────────────────────────────────


class TestValidSlug:
    @pytest.mark.parametrize(
        "slug",
        [
            "xqc",
            "just-a-slug",
            "user_123",
            "user-name",
            "XqC_123",
            "a-b-c",
            "a" * 25,
            "hello-world",
        ],
    )
    def test_accepts_valid(self, slug: str) -> None:
        assert VALID_SLUG.match(slug)

    @pytest.mark.parametrize(
        "slug",
        [
            "kick.com/xqc",
            "https://kick.com/xqc",
            "",
            "a" * 26,
            "user name",
            "user@name",
            "user.name",
        ],
    )
    def test_rejects_invalid(self, slug: str) -> None:
        assert not VALID_SLUG.match(slug)

    def test_allows_hyphen(self) -> None:
        assert VALID_SLUG.match("my-channel")

    def test_rejects_dot(self) -> None:
        assert not VALID_SLUG.match("my.channel")


# ── PKCE helpers ───────────────────────────────────────────────


class TestPKCEHelpers:
    def test_verifier_is_url_safe_base64(self) -> None:
        verifier = _generate_code_verifier()
        # Must only contain URL-safe base64 chars (no padding =)
        assert all(
            c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
            for c in verifier
        )
        assert "=" not in verifier

    def test_verifier_length_in_range(self) -> None:
        verifier = _generate_code_verifier()
        # RFC 7636: 43–128 chars
        assert 43 <= len(verifier) <= 128

    def test_verifier_different_each_call(self) -> None:
        v1 = _generate_code_verifier()
        v2 = _generate_code_verifier()
        assert v1 != v2

    def test_challenge_is_url_safe_base64(self) -> None:
        verifier = _generate_code_verifier()
        challenge = _generate_code_challenge(verifier)
        assert all(
            c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
            for c in challenge
        )
        assert "=" not in challenge

    def test_challenge_is_43_chars_for_sha256(self) -> None:
        # SHA-256 produces 32 bytes → base64url without padding = 43 chars
        verifier = _generate_code_verifier()
        challenge = _generate_code_challenge(verifier)
        assert len(challenge) == 43

    def test_challenge_is_deterministic(self) -> None:
        verifier = _generate_code_verifier()
        c1 = _generate_code_challenge(verifier)
        c2 = _generate_code_challenge(verifier)
        assert c1 == c2

    def test_challenge_differs_for_different_verifiers(self) -> None:
        v1 = _generate_code_verifier()
        v2 = _generate_code_verifier()
        assert _generate_code_challenge(v1) != _generate_code_challenge(v2)

    def test_challenge_s256_correctness(self) -> None:
        """Verify S256 with known input."""
        import base64
        import hashlib

        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        expected_digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected = (
            base64.urlsafe_b64encode(expected_digest).rstrip(b"=").decode("ascii")
        )
        assert _generate_code_challenge(verifier) == expected


# ── Slug filtering ──────────────────────────────────────────────


class TestGetLiveStreamsFiltering:
    def test_filters_invalid_slugs(self) -> None:
        slugs = ["valid-slug", "https://kick.com/bad", "", "good_channel", "a" * 26]
        cleaned = [s.strip().lower() for s in slugs if s and s.strip()]
        cleaned = [s for s in cleaned if VALID_SLUG.match(s)]
        assert cleaned == ["valid-slug", "good_channel"]

    def test_empty_list_returns_empty(self) -> None:
        client = KickClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(client.get_live_streams([]))
        assert result == []
        loop.run_until_complete(client.close())
        loop.close()

    def test_all_invalid_slugs_returns_empty(self) -> None:
        client = KickClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            client.get_live_streams(["https://kick.com/bad", "", "a" * 26])
        )
        assert result == []
        loop.run_until_complete(client.close())
        loop.close()

    def test_whitespace_only_returns_empty(self) -> None:
        client = KickClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(client.get_live_streams(["   ", "\t"]))
        assert result == []
        loop.run_until_complete(client.close())
        loop.close()


class TestSearchChannels:
    def test_empty_query_returns_empty(self) -> None:
        client = KickClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(client.search_channels(""))
        assert result == []
        loop.run_until_complete(client.close())
        loop.close()

    def test_whitespace_query_returns_empty(self) -> None:
        client = KickClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(client.search_channels("   "))
        assert result == []
        loop.run_until_complete(client.close())
        loop.close()

    def test_uses_typesense_channel_search(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = KickClient()

        async def fake_typesense(query: str) -> list[dict[str, object]]:
            assert query == "chessbrah"
            return [
                {
                    "slug": "chessbrah",
                    "username": "chessbrah",
                    "is_live": True,
                    "verified": True,
                }
            ]

        monkeypatch.setattr(client, "_search_typesense_channels", fake_typesense)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(client.search_channels("chessbrah"))
        finally:
            loop.run_until_complete(client.close())
            loop.close()

        assert result == [
            {
                "slug": "chessbrah",
                "username": "chessbrah",
                "is_live": True,
                "verified": True,
            }
        ]


class TestGetFollowedChannels:
    def test_always_returns_empty_list(self) -> None:
        client = KickClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(client.get_followed_channels("any_user_id"))
        assert result == []
        loop.run_until_complete(client.close())
        loop.close()


class TestGetCurrentUser:
    def test_merges_user_profile_with_channel_slug(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = KickClient()

        async def fake_get(
            url: str, params: object = None, auth_required: bool = False
        ) -> dict[str, object]:
            if url.endswith("/public/v1/users"):
                return {
                    "data": [
                        {
                            "user_id": 123,
                            "name": "John Doe",
                            "profile_picture": "https://kick.com/avatar.webp",
                        }
                    ]
                }
            if url.endswith("/public/v1/channels"):
                return {
                    "data": [
                        {
                            "slug": "john-doe",
                            "broadcaster_user_id": 123,
                        }
                    ]
                }
            raise AssertionError(f"Unexpected URL: {url}")

        monkeypatch.setattr(client, "_get", fake_get)

        loop = asyncio.new_event_loop()
        try:
            user = loop.run_until_complete(client.get_current_user())
        finally:
            loop.run_until_complete(client.close())
            loop.close()

        assert user["user_id"] == 123
        assert user["name"] == "John Doe"
        assert user["slug"] == "john-doe"
        assert user["channel"]["slug"] == "john-doe"


class TestGetChannelInfo:
    def test_merges_public_channel_with_legacy_chat_metadata(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = KickClient()

        async def fake_get(
            url: str, params: object = None, auth_required: bool = False
        ) -> dict[str, object]:
            assert url.endswith("/public/v1/channels")
            assert params == [("slug", "vitaly")]
            return {
                "data": [
                    {
                        "broadcaster_user_id": 21725177,
                        "slug": "vitaly",
                        "stream_title": "Public title",
                    }
                ]
            }

        async def fake_legacy(path: str) -> dict[str, object]:
            if path == "/api/v1/channels/vitaly":
                return {
                    "id": 20736988,
                    "user_id": 21725177,
                    "slug": "vitaly",
                }
            if path == "/api/v2/channels/vitaly/chatroom":
                return {"id": 20466645, "followers_mode": {"enabled": True}}
            raise AssertionError(f"Unexpected path: {path}")

        monkeypatch.setattr(client, "_get", fake_get)
        monkeypatch.setattr(client, "_legacy_get_json", fake_legacy)

        loop = asyncio.new_event_loop()
        try:
            info = loop.run_until_complete(client.get_channel_info("vitaly"))
        finally:
            loop.run_until_complete(client.close())
            loop.close()

        assert info["slug"] == "vitaly"
        assert info["broadcaster_user_id"] == 21725177
        assert info["channel_id"] == 20736988
        assert info["chatroom_id"] == 20466645
        assert info["chatroom"]["followers_mode"]["enabled"] is True


# ── Per-event-loop client isolation ─────────────────────────────


class TestLoopLocalHttpClient:
    def test_uses_separate_clients_for_separate_event_loops(self) -> None:
        server = HTTPServer(("127.0.0.1", 0), _KeepAliveHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        client = KickClient()
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

    def test_same_loop_reuses_client(self) -> None:
        client = KickClient()

        async def get_two_client_ids() -> tuple[int, int]:
            c1 = client._get_client()
            c2 = client._get_client()
            return id(c1), id(c2)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            id1, id2 = loop.run_until_complete(get_two_client_ids())
            assert id1 == id2
            loop.run_until_complete(client.close_loop_resources())
        finally:
            asyncio.set_event_loop(None)
            loop.close()
