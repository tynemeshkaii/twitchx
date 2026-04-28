from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any
from urllib.parse import urlencode

from core.platforms.base import BasePlatformClient
from core.storage import token_is_valid, update_config

logger = logging.getLogger(__name__)

VALID_USERNAME = re.compile(r"^[a-zA-Z0-9_]{1,25}$")

TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_API_URL = "https://api.twitch.tv/helix"
TWITCH_REDIRECT_URI = "http://localhost:3457/callback"
OAUTH_SCOPE = "user:read:follows chat:read chat:edit"


class TwitchClient(BasePlatformClient):
    PLATFORM_ID = "twitch"
    PLATFORM_NAME = "Twitch"

    def __init__(self) -> None:
        super().__init__()

    async def _ensure_token(self) -> str:
        async with self._get_token_lock():
            self._reload_config()
            tc = self._platform_config()
            # Prefer user token if available
            if tc.get("token_type") == "user":
                if token_is_valid(tc):
                    return tc["access_token"]
                if tc.get("refresh_token"):
                    return await self.refresh_user_token()
            # Fall back to app-level client_credentials
            if token_is_valid(tc):
                return tc["access_token"]
            return await self._refresh_app_token()

    async def _refresh_app_token(self) -> str:
        tc = self._platform_config()
        client_id = tc.get("client_id", "")
        client_secret = tc.get("client_secret", "")
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
        expires_at = int(time.time()) + expires_in

        def _apply(cfg: dict) -> None:
            tc = cfg.get("platforms", {}).get("twitch", {})
            tc["access_token"] = token
            tc["token_expires_at"] = expires_at

        self._config = update_config(_apply)
        return token

    # ── OAuth (user-level) ───────────────────────────────────────

    def get_auth_url(self) -> str:
        self._reload_config()
        tc = self._platform_config()
        params = urlencode(
            {
                "client_id": tc["client_id"],
                "redirect_uri": TWITCH_REDIRECT_URI,
                "response_type": "code",
                "scope": OAUTH_SCOPE,
                "force_verify": "false",
            }
        )
        return f"https://id.twitch.tv/oauth2/authorize?{params}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        self._reload_config()
        tc = self._platform_config()
        resp = await self._get_client().post(
            TWITCH_AUTH_URL,
            data={
                "client_id": tc["client_id"],
                "client_secret": tc["client_secret"],
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": TWITCH_REDIRECT_URI,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def refresh_user_token(self) -> str:
        tc = self._platform_config()
        resp = await self._get_client().post(
            TWITCH_AUTH_URL,
            data={
                "client_id": tc["client_id"],
                "client_secret": tc["client_secret"],
                "refresh_token": tc["refresh_token"],
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code in (400, 401):
            # Token revoked — clear user auth
            def _clear(cfg: dict) -> None:
                tc = cfg.get("platforms", {}).get("twitch", {})
                tc["access_token"] = ""
                tc["refresh_token"] = ""
                tc["token_expires_at"] = 0
                tc["token_type"] = "app"
                tc["user_id"] = ""
                tc["user_login"] = ""
                tc["user_display_name"] = ""

            self._config = update_config(_clear)
            raise ValueError("User token expired. Please log in again.")
        resp.raise_for_status()
        data = resp.json()
        new_token = data["access_token"]
        new_refresh = data.get("refresh_token", tc["refresh_token"])
        new_expires = int(time.time()) + data.get("expires_in", 3600)

        def _update(cfg: dict) -> None:
            tc = cfg.get("platforms", {}).get("twitch", {})
            tc["access_token"] = new_token
            tc["refresh_token"] = new_refresh
            tc["token_expires_at"] = new_expires

        self._config = update_config(_update)
        return new_token

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
        tc = self._platform_config()
        headers = {
            "Authorization": f"Bearer {token}",
            "Client-Id": tc["client_id"],
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

            def _clear_token(cfg: dict) -> None:
                cfg.get("platforms", {}).get("twitch", {})["access_token"] = ""

            self._config = update_config(_clear_token)
            if tc.get("token_type") == "user" and tc.get("refresh_token"):
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

    async def get_categories(self, query: str | None = None) -> list[dict[str, Any]]:
        """Return top games from Helix, normalized to cross-platform format.

        With query: searches /games by name. Without: fetches /games/top?first=50.
        """
        if query:
            params: Any = {"name": query.strip()}
            data = await self._get("/games", params)
        else:
            params = {"first": "50"}
            data = await self._get("/games/top", params)
        return [
            {
                "platform": "twitch",
                "category_id": g["id"],
                "name": g["name"],
                "box_art_url": g["box_art_url"]
                .replace("{width}", "285")
                .replace("{height}", "380"),
                "viewers": 0,
            }
            for g in data.get("data", [])
        ]

    async def get_top_streams(
        self,
        category_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return top live Twitch streams, optionally filtered by game_id.

        Normalized to the cross-platform stream dict format.
        avatar_url is always empty — Helix /streams omits profile images.
        """
        params: Any = [("first", str(min(limit, 100)))]
        if category_id:
            params.append(("game_id", category_id))
        data = await self._get("/streams", params)
        return [
            {
                "platform": "twitch",
                "channel_id": s["user_id"],
                "channel_login": s["user_login"],
                "display_name": s["user_name"],
                "title": s["title"],
                "category": s["game_name"],
                "category_id": s["game_id"],
                "viewers": s["viewer_count"],
                "started_at": s["started_at"],
                "thumbnail_url": s["thumbnail_url"]
                .replace("{width}", "440")
                .replace("{height}", "248"),
                "avatar_url": "",
            }
            for s in data.get("data", [])
        ]

    async def get_channel_info(self, login: str) -> dict[str, Any]:
        """Return normalized channel profile dict. Costs 2 API calls (/users + /streams).

        followers is always -1 — /channels/followers requires broadcaster-level auth.
        """
        login = login.strip().lower()
        if not login:
            return {}
        users_data, streams_data = await asyncio.gather(
            self._get("/users", [("login", login)]),
            self._get("/streams", [("user_login", login)]),
        )
        users = users_data.get("data", [])
        if not users:
            return {}
        u = users[0]
        is_live = bool(streams_data.get("data", []))
        return {
            "platform": "twitch",
            "channel_id": u.get("id", ""),
            "login": u.get("login", login),
            "display_name": u.get("display_name", ""),
            "bio": u.get("description", ""),
            "avatar_url": u.get("profile_image_url", ""),
            "followers": -1,
            "is_live": is_live,
            "can_follow_via_api": False,
        }

    @staticmethod
    def _parse_duration_seconds(raw: str) -> int:
        """Convert Twitch duration strings like '3h5m12s' to seconds."""
        if not raw:
            return 0
        total = 0
        for match in re.finditer(r"(\d+)([hms])", raw.lower()):
            value = int(match.group(1))
            unit = match.group(2)
            if unit == "h":
                total += value * 3600
            elif unit == "m":
                total += value * 60
            else:
                total += value
        return total

    async def _get_user_by_login(self, login: str) -> dict[str, Any]:
        login = login.strip().lower()
        if not login:
            return {}
        users_data = await self._get("/users", [("login", login)])
        users = users_data.get("data", [])
        return users[0] if users else {}

    async def get_channel_vods(
        self, login: str, limit: int = 12
    ) -> list[dict[str, Any]]:
        """Return recent archived broadcasts for a broadcaster."""
        user = await self._get_user_by_login(login)
        user_id = user.get("id", "")
        if not user_id:
            return []
        data = await self._get(
            "/videos",
            [
                ("user_id", user_id),
                ("type", "archive"),
                ("first", str(min(limit, 20))),
            ],
        )
        items = data.get("data", [])
        return [
            {
                "id": item.get("id", ""),
                "platform": "twitch",
                "kind": "vod",
                "channel_login": user.get("login", login),
                "channel_display_name": user.get("display_name", login),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "thumbnail_url": item.get("thumbnail_url", "")
                .replace("%{width}", "440")
                .replace("%{height}", "248"),
                "published_at": item.get("created_at", ""),
                "duration_seconds": self._parse_duration_seconds(
                    item.get("duration", "")
                ),
                "views": int(item.get("view_count", 0) or 0),
            }
            for item in items
            if item.get("id") and item.get("url")
        ]

    async def get_channel_clips(
        self, login: str, limit: int = 12
    ) -> list[dict[str, Any]]:
        """Return top clips for a broadcaster, sorted by Twitch."""
        user = await self._get_user_by_login(login)
        user_id = user.get("id", "")
        if not user_id:
            return []
        data = await self._get(
            "/clips",
            [
                ("broadcaster_id", user_id),
                ("first", str(min(limit, 20))),
            ],
        )
        items = data.get("data", [])
        return [
            {
                "id": item.get("id", ""),
                "platform": "twitch",
                "kind": "clip",
                "channel_login": user.get("login", login),
                "channel_display_name": user.get("display_name", login),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "thumbnail_url": item.get("thumbnail_url", ""),
                "published_at": item.get("created_at", ""),
                "duration_seconds": int(item.get("duration", 0) or 0),
                "views": int(item.get("view_count", 0) or 0),
            }
            for item in items
            if item.get("id") and item.get("url")
        ]
