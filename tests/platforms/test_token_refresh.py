"""Phase 2 audit: token refresh, bounded retries and auth revocation."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs

import httpx
import pytest
from pytest_httpx import HTTPXMock

from core.platforms.base import BasePlatformClient, _retry_delay
from core.platforms.kick import KICK_AUTH_URL, KickClient
from core.platforms.twitch import TWITCH_API_URL, TWITCH_AUTH_URL, TwitchClient
from core.platforms.youtube import YOUTUBE_API_URL, YouTubeClient
from core.storage import load_config, update_config

KICK_TOKEN_URL = f"{KICK_AUTH_URL}/oauth/token"
FAR_FUTURE = 9_999_999_999


def _set_platform(platform: str, **values: object) -> None:
    def _apply(cfg: dict) -> None:
        cfg["platforms"][platform].update(values)

    update_config(_apply)


def _form(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


def _add_racing_401s(httpx_mock: HTTPXMock, urls: list[str]) -> None:
    """Reply 401 to "old" token only after every URL got one, then 200 to "new"."""
    arrived = 0
    both_arrived = asyncio.Event()

    async def _stale(request: httpx.Request) -> httpx.Response:
        nonlocal arrived
        arrived += 1
        if arrived == len(urls):
            both_arrived.set()
        await both_arrived.wait()
        return httpx.Response(401)

    for url in urls:
        httpx_mock.add_callback(
            _stale, url=url, match_headers={"Authorization": "Bearer old"}
        )
        httpx_mock.add_response(
            url=url, json={"data": []}, match_headers={"Authorization": "Bearer new"}
        )


@pytest.fixture
def no_sleep():
    with patch("asyncio.sleep", new=AsyncMock()) as sleep:
        yield sleep


# ── _retry_delay ─────────────────────────────────────────────


class TestRetryDelay:
    def _resp(self, **headers: str) -> httpx.Response:
        return httpx.Response(429, headers=headers)

    def test_integer_retry_after(self) -> None:
        assert _retry_delay(self._resp(**{"Retry-After": "7"}), 2) == 7

    def test_http_date_retry_after(self) -> None:
        when = datetime.now(UTC) + timedelta(seconds=10)
        delay = _retry_delay(
            self._resp(**{"Retry-After": format_datetime(when, usegmt=True)}), 2
        )
        assert 8 <= delay <= 10

    def test_past_http_date_clamped_to_min(self) -> None:
        resp = self._resp(**{"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"})
        assert _retry_delay(resp, 2) == 1

    def test_garbage_uses_default(self) -> None:
        assert _retry_delay(self._resp(**{"Retry-After": "soon"}), 3) == 3

    def test_ratelimit_reset(self) -> None:
        reset = str(int(time.time()) + 5)
        assert 3 <= _retry_delay(self._resp(**{"Ratelimit-Reset": reset}), 2) <= 5

    def test_clamped_to_max(self) -> None:
        assert _retry_delay(self._resp(**{"Retry-After": "3600"}), 2) == 30

    def test_missing_headers_uses_default(self) -> None:
        assert _retry_delay(self._resp(), 2) == 2


# ── 2.1 refresh body + error classification ──────────────────


class TestKickRefresh:
    async def test_refresh_sends_client_secret(
        self, temp_config_dir, httpx_mock: HTTPXMock
    ) -> None:
        _set_platform("kick", client_id="cid", client_secret="csec", refresh_token="r1")
        httpx_mock.add_response(
            url=KICK_TOKEN_URL,
            json={"access_token": "new", "refresh_token": "r2", "expires_in": 3600},
        )
        client = KickClient()
        assert await client.refresh_user_token() == "new"
        await client.close()
        body = _form(httpx_mock.get_requests()[0])
        assert body["client_secret"] == "csec"
        assert body["client_id"] == "cid"
        assert body["grant_type"] == "refresh_token"

    async def test_500_keeps_auth(self, temp_config_dir, httpx_mock: HTTPXMock) -> None:
        _set_platform("kick", access_token="a", refresh_token="r1", user_login="me")
        httpx_mock.add_response(url=KICK_TOKEN_URL, status_code=500)
        client = KickClient()
        with pytest.raises(httpx.HTTPStatusError):
            await client.refresh_user_token()
        await client.close()
        kc = load_config()["platforms"]["kick"]
        assert kc["refresh_token"] == "r1"
        assert kc["user_login"] == "me"

    async def test_timeout_keeps_auth(
        self, temp_config_dir, httpx_mock: HTTPXMock
    ) -> None:
        _set_platform("kick", refresh_token="r1", user_login="me")
        httpx_mock.add_exception(httpx.ReadTimeout("slow"), url=KICK_TOKEN_URL)
        client = KickClient()
        with pytest.raises(httpx.ReadTimeout):
            await client.refresh_user_token()
        await client.close()
        assert load_config()["platforms"]["kick"]["refresh_token"] == "r1"

    async def test_invalid_grant_clears_auth_and_notifies(
        self, temp_config_dir, httpx_mock: HTTPXMock
    ) -> None:
        _set_platform("kick", refresh_token="r1", user_login="me")
        httpx_mock.add_response(
            url=KICK_TOKEN_URL, status_code=400, json={"error": "invalid_grant"}
        )
        client = KickClient()
        revoked = MagicMock()
        client.on_auth_revoked = revoked
        with pytest.raises(ValueError):
            await client.refresh_user_token()
        await client.close()
        kc = load_config()["platforms"]["kick"]
        assert kc["refresh_token"] == ""
        assert kc["user_login"] == ""
        revoked.assert_called_once_with()


class TestTwitchRefresh:
    async def test_500_keeps_auth(self, temp_config_dir, httpx_mock: HTTPXMock) -> None:
        _set_platform("twitch", token_type="user", refresh_token="r1", user_login="me")
        httpx_mock.add_response(url=TWITCH_AUTH_URL, status_code=503)
        client = TwitchClient()
        with pytest.raises(httpx.HTTPStatusError):
            await client.refresh_user_token()
        await client.close()
        tc = load_config()["platforms"]["twitch"]
        assert tc["refresh_token"] == "r1"
        assert tc["token_type"] == "user"

    async def test_invalid_grant_clears_and_notifies(
        self, temp_config_dir, httpx_mock: HTTPXMock
    ) -> None:
        _set_platform("twitch", token_type="user", refresh_token="r1", user_login="me")
        httpx_mock.add_response(
            url=TWITCH_AUTH_URL,
            status_code=400,
            json={"status": 400, "message": "Invalid refresh token"},
        )
        client = TwitchClient()
        revoked = MagicMock()
        client.on_auth_revoked = revoked
        with pytest.raises(ValueError):
            await client.refresh_user_token()
        await client.close()
        tc = load_config()["platforms"]["twitch"]
        assert tc["token_type"] == "app"
        assert tc["user_login"] == ""
        revoked.assert_called_once_with()


# ── 2.2 bounded retries ──────────────────────────────────────


class TestTwitchRetries:
    async def test_429_gives_up_after_three_waits(
        self, temp_config_dir, httpx_mock: HTTPXMock, no_sleep
    ) -> None:
        _set_platform("twitch", access_token="tok", token_expires_at=FAR_FUTURE)
        for _ in range(4):
            httpx_mock.add_response(
                url=f"{TWITCH_API_URL}/users",
                status_code=429,
                headers={"Ratelimit-Reset": "garbage"},
            )
        client = TwitchClient()
        with pytest.raises(httpx.HTTPStatusError):
            await client._get("/users")
        await client.close()
        assert no_sleep.await_count == 3

    async def test_401_refresh_401_raises_after_single_refresh(
        self, temp_config_dir, httpx_mock: HTTPXMock
    ) -> None:
        _set_platform("twitch", access_token="tok", token_expires_at=FAR_FUTURE)
        httpx_mock.add_response(url=f"{TWITCH_API_URL}/users", status_code=401)
        httpx_mock.add_response(url=f"{TWITCH_API_URL}/users", status_code=401)
        client = TwitchClient()
        refresh = AsyncMock(return_value="tok2")
        client._refresh_after_401 = refresh  # type: ignore[method-assign]
        with pytest.raises(httpx.HTTPStatusError):
            await client._get("/users")
        await client.close()
        assert refresh.await_count == 1


class TestKickRetries:
    async def test_429_http_date_retry_after_bounded(
        self, temp_config_dir, httpx_mock: HTTPXMock, no_sleep
    ) -> None:
        url = "https://api.kick.com/public/v1/channels"
        for _ in range(4):
            httpx_mock.add_response(
                url=url,
                status_code=429,
                headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"},
            )
        client = KickClient()
        with pytest.raises(httpx.HTTPStatusError):
            await client._get(url)
        await client.close()
        assert no_sleep.await_count == 3

    async def test_401_refresh_401_raises(
        self, temp_config_dir, httpx_mock: HTTPXMock
    ) -> None:
        _set_platform("kick", access_token="tok", token_expires_at=FAR_FUTURE)
        url = "https://api.kick.com/public/v1/users"
        httpx_mock.add_response(url=url, status_code=401)
        httpx_mock.add_response(url=url, status_code=401)
        client = KickClient()
        refresh = AsyncMock(return_value="tok2")
        client._refresh_after_401 = refresh  # type: ignore[method-assign]
        with pytest.raises(httpx.HTTPStatusError):
            await client._get(url, auth_required=True)
        await client.close()
        assert refresh.await_count == 1


class TestBaseRequestRetries:
    async def test_429_bounded(
        self, temp_config_dir, httpx_mock: HTTPXMock, no_sleep
    ) -> None:
        url = f"{YOUTUBE_API_URL}/videos"
        for _ in range(4):
            httpx_mock.add_response(
                url=url, status_code=429, headers={"Retry-After": "nonsense"}
            )
        client = YouTubeClient()
        with pytest.raises(httpx.HTTPStatusError):
            await client._request("GET", url)
        await client.close()
        assert no_sleep.await_count == 3

    async def test_401_refreshes_once(
        self, temp_config_dir, httpx_mock: HTTPXMock
    ) -> None:
        url = f"{YOUTUBE_API_URL}/channels"
        httpx_mock.add_response(url=url, status_code=401)
        httpx_mock.add_response(url=url, status_code=401)
        client: BasePlatformClient = YouTubeClient()
        refresh = AsyncMock(return_value="tok2")
        client._refresh_after_401 = refresh  # type: ignore[method-assign]
        with pytest.raises(httpx.HTTPStatusError):
            await client._request("GET", url, headers={"Authorization": "Bearer tok"})
        await client.close()
        assert refresh.await_count == 1


# ── 2.3 races and fallback ───────────────────────────────────


class TestTwitchRefreshRace:
    async def test_parallel_401_refreshes_once(
        self, temp_config_dir, httpx_mock: HTTPXMock
    ) -> None:
        _set_platform(
            "twitch",
            token_type="user",
            access_token="old",
            refresh_token="r1",
            token_expires_at=FAR_FUTURE,
        )
        _add_racing_401s(
            httpx_mock, [f"{TWITCH_API_URL}/users", f"{TWITCH_API_URL}/channels"]
        )
        httpx_mock.add_response(
            url=TWITCH_AUTH_URL,
            json={"access_token": "new", "refresh_token": "r2", "expires_in": 3600},
        )
        client = TwitchClient()
        await asyncio.gather(client._get("/users"), client._get("/channels"))
        await client.close()
        token_calls = [
            r for r in httpx_mock.get_requests() if str(r.url) == TWITCH_AUTH_URL
        ]
        assert len(token_calls) == 1

    async def test_user_refresh_revoked_falls_back_to_app_token(
        self, temp_config_dir, httpx_mock: HTTPXMock
    ) -> None:
        _set_platform(
            "twitch",
            token_type="user",
            access_token="expired",
            refresh_token="r1",
            token_expires_at=1,
            user_login="me",
            # App-token fallback needs client creds; don't rely on the
            # gitignored bundled core/credentials.py (absent in CI).
            client_id="cid",
            client_secret="csec",
        )
        httpx_mock.add_response(
            url=TWITCH_AUTH_URL,
            status_code=400,
            json={"status": 400, "message": "Invalid refresh token"},
        )
        httpx_mock.add_response(
            url=TWITCH_AUTH_URL,
            json={"access_token": "app-tok", "expires_in": 3600},
        )
        client = TwitchClient()
        revoked = MagicMock()
        client.on_auth_revoked = revoked
        token = await client._ensure_token()
        await client.close()
        assert token == "app-tok"
        revoked.assert_called_once_with()
        tc = load_config()["platforms"]["twitch"]
        assert tc["token_type"] == "app"
        assert tc["access_token"] == "app-tok"


class TestKickRefreshRace:
    async def test_parallel_401_refreshes_once(
        self, temp_config_dir, httpx_mock: HTTPXMock
    ) -> None:
        _set_platform(
            "kick", access_token="old", refresh_token="r1", token_expires_at=FAR_FUTURE
        )
        base = "https://api.kick.com/public/v1"
        _add_racing_401s(httpx_mock, [f"{base}/users", f"{base}/channels"])
        httpx_mock.add_response(
            url=KICK_TOKEN_URL,
            json={"access_token": "new", "refresh_token": "r2", "expires_in": 3600},
        )
        client = KickClient()
        await asyncio.gather(
            client._get(f"{base}/users", auth_required=True),
            client._get(f"{base}/channels", auth_required=True),
        )
        await client.close()
        token_calls = [
            r for r in httpx_mock.get_requests() if str(r.url) == KICK_TOKEN_URL
        ]
        assert len(token_calls) == 1
