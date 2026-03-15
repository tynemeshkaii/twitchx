from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import httpx

from core.storage import load_config, save_config, token_is_valid

logger = logging.getLogger(__name__)

VALID_USERNAME = re.compile(r"^[a-zA-Z0-9_]{1,25}$")

TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_API_URL = "https://api.twitch.tv/helix"


class TwitchClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=15.0)
        self._config = load_config()
        self._token_lock = asyncio.Lock()

    async def close(self) -> None:
        await self._client.aclose()

    def _reload_config(self) -> None:
        self._config = load_config()

    async def _ensure_token(self) -> str:
        async with self._token_lock:
            self._reload_config()
            if token_is_valid(self._config):
                return self._config["access_token"]
            return await self._refresh_token()

    async def _refresh_token(self) -> str:
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
        resp = await self._client.get(url, headers=headers, params=params)
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
            token = await self._refresh_token()
            headers["Authorization"] = f"Bearer {token}"
            resp = await self._client.get(url, headers=headers, params=params)
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
