"""Follow-ups to the audit fixes: cross-thread token lock, Kick app token,
Kick avatar negative cache."""

from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import patch

import httpx
import pytest
from pytest_httpx import HTTPXMock

from core.platforms import base as base_mod
from core.platforms.kick import KICK_API_URL, KICK_AUTH_URL, KickClient
from core.storage import update_config

KICK_TOKEN_URL = f"{KICK_AUTH_URL}/oauth/token"
CHANNELS_URL = f"{KICK_API_URL}/public/v1/channels?slug=foo"


def _set_kick(**values: object) -> None:
    def _apply(cfg: dict) -> None:
        cfg["platforms"]["kick"].update(values)

    update_config(_apply)


# ── Cross-thread token lock ──────────────────────────────────────


def test_refresh_after_401_runs_once_across_threads(temp_config_dir) -> None:
    """Each worker thread has its own loop; only one may refresh a stale token."""
    client = KickClient()
    state = {"token": "old", "refreshes": 0}

    async def fake_refresh() -> str:
        state["refreshes"] += 1
        await asyncio.sleep(0.1)
        state["token"] = f"new{state['refreshes']}"
        return state["token"]

    client.refresh_user_token = fake_refresh  # type: ignore[method-assign]
    client._reload_config = lambda: None  # type: ignore[method-assign]
    client._platform_config = lambda: {  # type: ignore[method-assign]
        "access_token": state["token"],
        "refresh_token": "r",
    }
    results: list[str | None] = []

    def worker() -> None:
        results.append(asyncio.run(client._refresh_after_401("old")))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert state["refreshes"] == 1
    assert results == ["new1"] * 4


def test_token_lock_released_when_waiter_is_cancelled(temp_config_dir) -> None:
    """A wait_for timeout while queued for the thread lock must not leak it."""
    client = KickClient()

    async def hold_then_cancel_waiter() -> None:
        async with client._get_token_lock():
            # A second loop/thread queues for the same platform lock and is
            # cancelled before it gets it.
            def other_thread() -> None:
                async def waiter() -> None:
                    with pytest.raises(TimeoutError):
                        async with asyncio.timeout(0.05):
                            async with client._get_token_lock():
                                pass

                asyncio.run(waiter())

            t = threading.Thread(target=other_thread)
            t.start()
            await asyncio.to_thread(t.join, 5)

    asyncio.run(hold_then_cancel_waiter())

    async def acquire_again() -> bool:
        async with asyncio.timeout(5):
            async with client._get_token_lock():
                return True

    # The cancelled waiter got the lock late and must have released it.
    assert asyncio.run(acquire_again()) is True
    lock = base_mod.BasePlatformClient._thread_token_locks["kick"]
    deadline = time.time() + 2
    while lock.locked() and time.time() < deadline:
        time.sleep(0.01)
    assert not lock.locked()


# ── Kick app token ───────────────────────────────────────────────


@pytest.mark.kick_app_token
async def test_kick_get_uses_app_token_without_login(
    temp_config_dir, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url=KICK_TOKEN_URL, json={"access_token": "app1", "expires_in": 3600}
    )
    httpx_mock.add_response(
        url=CHANNELS_URL,
        json={"data": []},
        match_headers={"Authorization": "Bearer app1"},
        is_reusable=True,
    )
    client = KickClient()
    with patch.object(client, "_effective_creds", return_value=("cid", "csec")):
        try:
            await client._get(CHANNELS_URL)
            await client._get(CHANNELS_URL)
        finally:
            await client.close()

    posts = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(posts) == 1  # cached for the second GET
    assert b"grant_type=client_credentials" in posts[0].content
    # Never persisted: config access_token means "logged-in user".
    from core.storage import load_config

    assert load_config()["platforms"]["kick"]["access_token"] == ""


@pytest.mark.kick_app_token
async def test_kick_app_token_renewed_after_401(
    temp_config_dir, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url=KICK_TOKEN_URL, json={"access_token": "app1", "expires_in": 3600}
    )
    httpx_mock.add_response(
        url=KICK_TOKEN_URL, json={"access_token": "app2", "expires_in": 3600}
    )
    httpx_mock.add_response(
        url=CHANNELS_URL,
        status_code=401,
        match_headers={"Authorization": "Bearer app1"},
    )
    httpx_mock.add_response(
        url=CHANNELS_URL,
        json={"data": [{"slug": "foo"}]},
        match_headers={"Authorization": "Bearer app2"},
    )
    client = KickClient()
    with patch.object(client, "_effective_creds", return_value=("cid", "csec")):
        try:
            data = await client._get(CHANNELS_URL)
        finally:
            await client.close()
    assert data == {"data": [{"slug": "foo"}]}


@pytest.mark.kick_app_token
async def test_kick_user_token_preferred_over_app_token(
    temp_config_dir, httpx_mock: HTTPXMock
) -> None:
    _set_kick(access_token="user", token_expires_at=9_999_999_999)
    httpx_mock.add_response(
        url=CHANNELS_URL,
        json={"data": []},
        match_headers={"Authorization": "Bearer user"},
    )
    client = KickClient()
    try:
        await client._get(CHANNELS_URL)
    finally:
        await client.close()
    assert all(r.method == "GET" for r in httpx_mock.get_requests())


@pytest.mark.kick_app_token
async def test_kick_auth_required_never_uses_app_token(
    temp_config_dir, httpx_mock: HTTPXMock
) -> None:
    client = KickClient()
    with (
        patch.object(client, "_effective_creds", return_value=("cid", "csec")),
        pytest.raises(ValueError),
    ):
        await client._get(f"{KICK_API_URL}/public/v1/users", auth_required=True)
    await client.close()
    assert httpx_mock.get_requests() == []


@pytest.mark.kick_app_token
async def test_kick_app_token_failure_backs_off(
    temp_config_dir, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(url=KICK_TOKEN_URL, status_code=401)
    httpx_mock.add_response(url=CHANNELS_URL, status_code=401, is_reusable=True)
    client = KickClient()
    with patch.object(client, "_effective_creds", return_value=("cid", "csec")):
        try:
            for _ in range(3):
                with pytest.raises(httpx.HTTPStatusError):
                    await client._get(CHANNELS_URL)
        finally:
            await client.close()
    posts = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(posts) == 1


@pytest.mark.kick_app_token
async def test_kick_app_token_needs_credentials(
    temp_config_dir, httpx_mock: HTTPXMock
) -> None:
    client = KickClient()
    with patch.object(client, "_effective_creds", return_value=("", "")):
        assert await client._ensure_app_token() is None
    await client.close()
    assert httpx_mock.get_requests() == []


# ── Kick avatar negative cache ───────────────────────────────────


def test_kick_avatar_miss_is_cached(temp_config_dir) -> None:
    from ui.api import TwitchXApi

    with patch("httpx.Client"):
        api = TwitchXApi()
    images = api._images
    with patch.object(images, "_lookup_kick_avatar", return_value="") as lookup:
        assert images._resolve_kick_avatar("foo") == ""
        assert images._resolve_kick_avatar("foo") == ""
    assert lookup.call_count == 1

    # After the TTL the channel is looked up again.
    images._kick_avatar_misses["foo"] -= 10 * 60 * 60
    with patch.object(
        images, "_lookup_kick_avatar", return_value="https://x/p.png"
    ) as lookup:
        assert images._resolve_kick_avatar("foo") == "https://x/p.png"
    assert lookup.call_count == 1
    assert api._user_avatars["kick:foo"] == "https://x/p.png"
    assert "foo" not in images._kick_avatar_misses
