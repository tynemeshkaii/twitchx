from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from core.storage import load_config, save_config, token_is_valid

logger = logging.getLogger(__name__)

VALID_USERNAME = re.compile(r"^[a-zA-Z0-9_]{1,25}$")

TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_API_URL = "https://api.twitch.tv/helix"
TWITCH_REDIRECT_URI = "http://localhost:3457/callback"
OAUTH_SCOPE = "user:read:follows"


class TwitchClient:
    def __init__(self) -> None:
        self._config = load_config()
        self._loop_clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}
        self._token_locks: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}
        self._loop_state_lock = threading.Lock()

    async def close(self) -> None:
        await self.close_loop_resources()

    def reset_client(self) -> None:
        """Compatibility no-op.

        HTTP clients are now scoped per event loop, so a new temporary loop
        automatically gets a fresh client and never reuses sockets from a
        previously closed loop.
        """

    def _get_client(self) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        with self._loop_state_lock:
            client = self._loop_clients.get(loop)
            if client is None:
                client = httpx.AsyncClient(timeout=15.0)
                self._loop_clients[loop] = client
            return client

    def _get_token_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        with self._loop_state_lock:
            lock = self._token_locks.get(loop)
            if lock is None:
                lock = asyncio.Lock()
                self._token_locks[loop] = lock
            return lock

    async def close_loop_resources(self) -> None:
        loop = asyncio.get_running_loop()
        with self._loop_state_lock:
            client = self._loop_clients.pop(loop, None)
            self._token_locks.pop(loop, None)
        if client is not None:
            await client.aclose()

    def _reload_config(self) -> None:
        self._config = load_config()

    async def _ensure_token(self) -> str:
        async with self._get_token_lock():
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
        resp = await self._get_client().post(
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
        params = urlencode(
            {
                "client_id": self._config["client_id"],
                "redirect_uri": TWITCH_REDIRECT_URI,
                "response_type": "code",
                "scope": OAUTH_SCOPE,
                "force_verify": "false",
            }
        )
        return f"https://id.twitch.tv/oauth2/authorize?{params}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        self._reload_config()
        resp = await self._get_client().post(
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
        return resp.json()

    async def refresh_user_token(self) -> str:
        resp = await self._get_client().post(
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

    async def get_followed_channels(self, user_id: str) -> list[str]:
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
            cursor = data.get("pagination", {}).get("cursor")
            if not cursor:
                break
        return all_logins

    async def _get(
        self,
        endpoint: str,
        params: Any = None,
    ) -> Any:
        token = await self._ensure_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Client-Id": self._config["client_id"],
        }
        url = f"{TWITCH_API_URL}{endpoint}"
        logger.debug("GET %s params=%s", url, params)
        client = self._get_client()
        resp = await client.get(url, headers=headers, params=params)
        logger.debug("Response: %d", resp.status_code)
        if resp.status_code != 200:
            logger.debug("Body: %s", resp.text[:300])
        if resp.status_code == 429:
            retry_after = (
                float(resp.headers.get("Ratelimit-Reset", time.time() + 2))
                - time.time()
            )
            await asyncio.sleep(max(retry_after, 1))
            return await self._get(endpoint, params)
        if resp.status_code == 401:
            self._config["access_token"] = ""
            save_config(self._config)
            if self._config.get("token_type") == "user" and self._config.get(
                "refresh_token"
            ):
                token = await self.refresh_user_token()
            else:
                token = await self._refresh_app_token()
            headers["Authorization"] = f"Bearer {token}"
            resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_live_streams(self, logins: list[str]) -> list[dict[str, Any]]:
        logins = [name.strip().lower() for name in logins if name and name.strip()]
        logins = [name for name in logins if VALID_USERNAME.match(name)]
        if not logins:
            return []
        all_streams: list[dict[str, Any]] = []
        for i in range(0, len(logins), 100):
            batch = logins[i : i + 100]
            params = [("user_login", login) for login in batch]
            data = await self._get("/streams", params=params)
            all_streams.extend(data.get("data", []))
        return all_streams

    async def get_users(self, logins: list[str]) -> list[dict[str, Any]]:
        logins = [name.strip().lower() for name in logins if name and name.strip()]
        logins = [name for name in logins if VALID_USERNAME.match(name)]
        if not logins:
            return []
        all_users: list[dict[str, Any]] = []
        for i in range(0, len(logins), 100):
            batch = logins[i : i + 100]
            params = [("login", login) for login in batch]
            data = await self._get("/users", params=params)
            all_users.extend(data.get("data", []))
        return all_users

    async def get_games(self, game_ids: list[str]) -> dict[str, str]:
        game_ids = [g.strip() for g in game_ids if g and g.strip()]
        if not game_ids:
            return {}
        unique_ids = list(set(game_ids))
        all_games: list[dict[str, Any]] = []
        for i in range(0, len(unique_ids), 100):
            batch = unique_ids[i : i + 100]
            params = [("id", gid) for gid in batch]
            data = await self._get("/games", params=params)
            all_games.extend(data.get("data", []))
        return {g["id"]: g["name"] for g in all_games}

    async def search_channels(self, query: str) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            return []
        params = [("query", query), ("live_only", "false"), ("first", "8")]
        data = await self._get("/search/channels", params=params)
        return data.get("data", [])
