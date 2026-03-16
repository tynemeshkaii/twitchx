from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import secrets
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

import httpx

from core.oauth_server import validate_state
from core.storage import load_config, save_config, token_is_valid

logger = logging.getLogger(__name__)

VALID_USERNAME = re.compile(r"^[a-zA-Z0-9_]{1,25}$")

TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_API_URL = "https://api.twitch.tv/helix"
TWITCH_REDIRECT_URI = "http://localhost:3457/callback"
OAUTH_SCOPE = "user:read:follows"


class TwitchClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=15.0)
        self._config = load_config()
        self._token_lock = asyncio.Lock()
        self._rate_limit_lock = asyncio.Lock()
        self._rate_limit_reset_at = 0.0
        self._rate_limit_waiter: asyncio.Task[None] | None = None

    async def close(self) -> None:
        await self._cancel_rate_limit_waiter()
        await self._client.aclose()

    async def rebind_client(self) -> None:
        await self._cancel_rate_limit_waiter()
        old_client = self._client
        self._client = httpx.AsyncClient(timeout=15.0)
        with contextlib.suppress(Exception):
            await old_client.aclose()

    def reset_client(self) -> None:
        """Replace the httpx client to discard stale connections.

        Call this after running async operations on a temporary event loop
        that has since been closed — the old connections are bound to that
        loop and will raise RuntimeError('Event loop is closed') if reused.
        """
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is not None:
            running_loop.create_task(self.rebind_client())
            return

        with contextlib.suppress(Exception):
            asyncio.run(self.rebind_client())

    def _reload_config(self) -> None:
        self._config = load_config()

    async def _ensure_token(self) -> str:
        async with self._token_lock:
            self._reload_config()
            # Prefer user token if available
            if self._config.get("token_type") == "user":
                if token_is_valid(self._config):
                    return self._config["access_token"]
                if self._config.get("refresh_token"):
                    return await self.refresh_user_token()
            # Fall back to app-level client_credentials
            if token_is_valid(self._config):
                return self._config["access_token"]
            return await self._refresh_app_token()

    async def _refresh_app_token(self) -> str:
        client_id = self._config.get("client_id", "")
        client_secret = self._config.get("client_secret", "")
        if not client_id or not client_secret:
            raise ValueError(
                "Twitch Client ID and Secret are required. Set them in Settings."
            )
        resp = await self._client.post(
            TWITCH_AUTH_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        self._config["access_token"] = token
        self._config["token_expires_at"] = int(time.time()) + expires_in
        save_config(self._config)
        return token

    # ── OAuth (user-level) ───────────────────────────────────────

    def get_auth_url(self) -> str:
        self._reload_config()
        state = secrets.token_urlsafe(24)
        self._config["oauth_state"] = state
        save_config(self._config)
        params = urlencode({
            "client_id": self._config["client_id"],
            "redirect_uri": TWITCH_REDIRECT_URI,
            "response_type": "code",
            "scope": OAUTH_SCOPE,
            "force_verify": "false",
            "state": state,
        })
        return f"https://id.twitch.tv/oauth2/authorize?{params}"

    def consume_oauth_state(self, received_state: str | None) -> bool:
        self._reload_config()
        expected_state = self._config.get("oauth_state")
        self._config["oauth_state"] = ""
        save_config(self._config)
        return validate_state(expected_state, received_state)

    async def exchange_code(self, code: str) -> dict[str, Any]:
        self._reload_config()
        resp = await self._client.post(
            TWITCH_AUTH_URL,
            data={
                "client_id": self._config["client_id"],
                "client_secret": self._config["client_secret"],
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": TWITCH_REDIRECT_URI,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._config["access_token"] = data["access_token"]
        self._config["refresh_token"] = data.get("refresh_token", "")
        self._config["token_expires_at"] = int(time.time()) + data.get(
            "expires_in", 3600
        )
        self._config["token_type"] = "user"
        save_config(self._config)
        return data

    async def refresh_user_token(self) -> str:
        resp = await self._client.post(
            TWITCH_AUTH_URL,
            data={
                "client_id": self._config["client_id"],
                "client_secret": self._config["client_secret"],
                "refresh_token": self._config["refresh_token"],
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code in (400, 401):
            # Token revoked — clear user auth
            self._config["access_token"] = ""
            self._config["refresh_token"] = ""
            self._config["token_expires_at"] = 0
            self._config["token_type"] = "app"
            self._config["user_id"] = ""
            self._config["user_login"] = ""
            self._config["user_display_name"] = ""
            save_config(self._config)
            raise ValueError("User token expired. Please log in again.")
        resp.raise_for_status()
        data = resp.json()
        self._config["access_token"] = data["access_token"]
        self._config["refresh_token"] = data.get(
            "refresh_token", self._config["refresh_token"]
        )
        self._config["token_expires_at"] = int(time.time()) + data.get(
            "expires_in", 3600
        )
        save_config(self._config)
        return data["access_token"]

    async def get_current_user(self) -> dict[str, Any]:
        data = await self._get("/users")
        users = data.get("data", [])
        if not users:
            raise ValueError("Could not fetch current user")
        return users[0]

    async def get_followed_channels(
        self,
        user_id: str,
        on_progress: Callable[[int], None] | None = None,
    ) -> list[str]:
        all_logins: list[str] = []
        cursor: str | None = None
        while True:
            params: list[tuple[str, str]] = [
                ("user_id", user_id),
                ("first", "100"),
            ]
            if cursor:
                params.append(("after", cursor))
            data = await self._get("/channels/followed", params=params)
            for ch in data.get("data", []):
                login = ch.get("broadcaster_login", "").lower()
                if login:
                    all_logins.append(login)
            if on_progress is not None:
                with contextlib.suppress(Exception):
                    on_progress(len(all_logins))
            cursor = data.get("pagination", {}).get("cursor")
            if not cursor:
                break
        return all_logins

    async def _get_batched_data(
        self,
        endpoint: str,
        param_name: str,
        values: list[str],
    ) -> list[dict[str, Any]]:
        requests = []
        for i in range(0, len(values), 100):
            batch = values[i : i + 100]
            params = [(param_name, value) for value in batch]
            requests.append(self._get(endpoint, params=params))
        responses = await asyncio.gather(*requests)
        merged: list[dict[str, Any]] = []
        for response in responses:
            merged.extend(response.get("data", []))
        return merged

    async def _cancel_rate_limit_waiter(self) -> None:
        waiter = self._rate_limit_waiter
        self._rate_limit_waiter = None
        self._rate_limit_reset_at = 0.0
        if waiter is None or waiter.done():
            return
        waiter.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await waiter

    def _parse_rate_limit_reset_at(self, resp: Any) -> float:
        raw_value = resp.headers.get("Ratelimit-Reset")
        try:
            reset_at = float(raw_value)
        except (TypeError, ValueError):
            reset_at = time.time() + 2
        return max(reset_at, time.time() + 1)

    async def _set_rate_limit_window(self, reset_at: float) -> None:
        waiter_to_cancel: asyncio.Task[None] | None = None
        async with self._rate_limit_lock:
            if reset_at <= self._rate_limit_reset_at:
                return
            self._rate_limit_reset_at = reset_at
            waiter = self._rate_limit_waiter
            if waiter is not None and not waiter.done():
                waiter.cancel()
                waiter_to_cancel = waiter
            delay = max(self._rate_limit_reset_at - time.time(), 0)
            self._rate_limit_waiter = (
                asyncio.create_task(asyncio.sleep(delay)) if delay > 0 else None
            )
        if waiter_to_cancel is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await waiter_to_cancel

    async def _wait_for_rate_limit_window(self) -> None:
        while True:
            async with self._rate_limit_lock:
                waiter = self._rate_limit_waiter
                if self._rate_limit_reset_at <= time.time():
                    self._rate_limit_reset_at = 0.0
                    self._rate_limit_waiter = None
                    return
                if waiter is None or waiter.done():
                    delay = max(self._rate_limit_reset_at - time.time(), 0)
                    if delay <= 0:
                        self._rate_limit_reset_at = 0.0
                        self._rate_limit_waiter = None
                        return
                    self._rate_limit_waiter = asyncio.create_task(
                        asyncio.sleep(delay)
                    )
                    waiter = self._rate_limit_waiter
            if waiter is None:
                return
            try:
                await waiter
            except asyncio.CancelledError:
                continue

    async def _recover_token_after_401(
        self,
        rejected_token: str,
        *,
        user_token: bool,
    ) -> str:
        async with self._token_lock:
            self._reload_config()
            current_token = self._config.get("access_token", "")
            if current_token and current_token != rejected_token and token_is_valid(
                self._config
            ):
                if not user_token or self._config.get("token_type") == "user":
                    return current_token
            if user_token and self._config.get("token_type") != "user":
                raise ValueError("User token expired. Please log in again.")
            self._config["access_token"] = ""
            save_config(self._config)
            if user_token:
                if not self._config.get("refresh_token"):
                    raise ValueError("User token expired. Please log in again.")
                return await self.refresh_user_token()
            return await self._refresh_app_token()

    async def _get(
        self,
        endpoint: str,
        params: Any = None,
    ) -> Any:
        token = await self._ensure_token()
        user_token = self._config.get("token_type") == "user"
        await self._wait_for_rate_limit_window()
        headers = {
            "Authorization": f"Bearer {token}",
            "Client-Id": self._config["client_id"],
        }
        url = f"{TWITCH_API_URL}{endpoint}"
        logger.debug("GET %s params=%s", url, params)
        resp = await self._client.get(url, headers=headers, params=params)
        logger.debug("Response: %d", resp.status_code)
        if resp.status_code != 200:
            logger.debug("Body: %s", resp.text[:300])
        if resp.status_code == 429:
            await self._set_rate_limit_window(
                self._parse_rate_limit_reset_at(resp)
            )
            return await self._get(endpoint, params)
        if resp.status_code == 401:
            token = await self._recover_token_after_401(
                token,
                user_token=user_token,
            )
            headers["Authorization"] = f"Bearer {token}"
            resp = await self._client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_live_streams(self, logins: list[str]) -> list[dict[str, Any]]:
        logins = [name.strip().lower() for name in logins if name and name.strip()]
        logins = [name for name in logins if VALID_USERNAME.match(name)]
        logins = list(dict.fromkeys(logins))
        if not logins:
            return []
        return await self._get_batched_data("/streams", "user_login", logins)

    async def get_users(self, logins: list[str]) -> list[dict[str, Any]]:
        logins = [name.strip().lower() for name in logins if name and name.strip()]
        logins = [name for name in logins if VALID_USERNAME.match(name)]
        logins = list(dict.fromkeys(logins))
        if not logins:
            return []
        return await self._get_batched_data("/users", "login", logins)

    async def get_games(self, game_ids: list[str]) -> dict[str, str]:
        game_ids = [g.strip() for g in game_ids if g and g.strip()]
        if not game_ids:
            return {}
        unique_ids = list(dict.fromkeys(game_ids))
        all_games = await self._get_batched_data("/games", "id", unique_ids)
        return {g["id"]: g["name"] for g in all_games}

    async def search_channels(self, query: str) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            return []
        params = [("query", query), ("live_only", "false"), ("first", "8")]
        data = await self._get("/search/channels", params=params)
        return data.get("data", [])
