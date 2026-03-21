from __future__ import annotations

import asyncio
import contextlib
import re
import time
from typing import Any

import httpx

from core.platforms import build_channel_ref, split_channel_ref
from core.storage import load_config, save_config

KICK_AUTH_URL = "https://id.kick.com/oauth/token"
KICK_API_URL = "https://api.kick.com/public/v1"
_LIVE_DIRECTORY_TTL = 60.0
_VALID_SLUG_RE = re.compile(r"^[A-Za-z0-9._-]{1,25}$")


class KickClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=15.0)
        self._config = load_config()
        self._token_lock = asyncio.Lock()
        self._live_directory_cached_at = 0.0
        self._live_directory_cache: tuple[
            list[dict[str, Any]],
            dict[int, dict[str, Any]],
        ] | None = None

    async def close(self) -> None:
        await self._client.aclose()

    async def rebind_client(self) -> None:
        old_client = self._client
        self._client = httpx.AsyncClient(timeout=15.0)
        with contextlib.suppress(Exception):
            await old_client.aclose()

    def _reload_config(self) -> None:
        self._config = load_config()

    def _token_is_valid(self) -> bool:
        return (
            bool(self._config.get("kick_access_token"))
            and self._config.get("kick_token_expires_at", 0) > time.time() + 60
        )

    async def _ensure_token(self) -> str:
        async with self._token_lock:
            self._reload_config()
            if self._token_is_valid():
                return str(self._config["kick_access_token"])
            return await self._refresh_app_token()

    async def _refresh_app_token(self) -> str:
        self._reload_config()
        client_id = str(self._config.get("kick_client_id", "")).strip()
        client_secret = str(self._config.get("kick_client_secret", "")).strip()
        if not client_id or not client_secret:
            raise ValueError(
                "Kick Client ID and Secret are required. Set them in Settings."
            )
        resp = await self._client.post(
            KICK_AUTH_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        token = str(data["access_token"])
        expires_in = int(data.get("expires_in", 3600))
        self._config["kick_access_token"] = token
        self._config["kick_token_expires_at"] = int(time.time()) + expires_in
        save_config(self._config)
        return token

    async def _get(
        self,
        path: str,
        params: list[tuple[str, str]] | None = None,
    ) -> Any:
        token = await self._ensure_token()
        headers = {"Authorization": f"Bearer {token}"}
        response = await self._client.get(
            f"{KICK_API_URL}{path}",
            params=params,
            headers=headers,
        )
        if response.status_code == 401:
            self._config["kick_access_token"] = ""
            self._config["kick_token_expires_at"] = 0
            save_config(self._config)
            token = await self._refresh_app_token()
            response = await self._client.get(
                f"{KICK_API_URL}{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return []
        return payload.get("data", [])

    async def _get_batched_data(
        self,
        endpoint: str,
        param_name: str,
        values: list[str | int],
        *,
        batch_size: int = 50,
    ) -> list[dict[str, Any]]:
        if not values:
            return []
        requests = []
        for i in range(0, len(values), batch_size):
            batch = values[i : i + batch_size]
            params = [(param_name, str(value)) for value in batch]
            requests.append(self._get(endpoint, params=params))
        responses = await asyncio.gather(*requests)
        merged: list[dict[str, Any]] = []
        for response in responses:
            if isinstance(response, list):
                merged.extend(item for item in response if isinstance(item, dict))
        return merged

    def _clean_logins(self, logins: list[str]) -> list[str]:
        cleaned: list[str] = []
        for login in logins:
            _, parsed_login = split_channel_ref(login, default_platform="kick")
            if parsed_login:
                cleaned.append(parsed_login)
        return list(dict.fromkeys(cleaned))

    async def _get_channels_by_slug(self, logins: list[str]) -> list[dict[str, Any]]:
        return await self._get_batched_data(
            "/channels",
            "slug",
            self._clean_logins(logins),
        )

    def _user_id(self, payload: dict[str, Any], key: str = "broadcaster_user_id") -> int:
        value = payload.get(key, 0)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    async def _get_users_by_id(self, user_ids: list[int]) -> list[dict[str, Any]]:
        unique_ids = [user_id for user_id in dict.fromkeys(user_ids) if user_id > 0]
        return await self._get_batched_data("/users", "id", unique_ids)

    async def _get_livestreams(
        self,
        *,
        limit: int = 25,
        sort: str = "viewer_count",
    ) -> list[dict[str, Any]]:
        data = await self._get(
            "/livestreams",
            params=[("limit", str(limit)), ("sort", sort)],
        )
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    async def _get_channels_and_users(
        self,
        logins: list[str],
    ) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
        channels = await self._get_channels_by_slug(self._clean_logins(logins))
        user_ids = [
            self._user_id(channel)
            for channel in channels
            if self._user_id(channel) > 0
        ]
        users = await self._get_users_by_id(user_ids) if user_ids else []
        users_by_id = {
            self._user_id(user, key="user_id"): user
            for user in users
            if self._user_id(user, key="user_id") > 0
        }
        return channels, users_by_id

    def _channel_ref(self, slug: str) -> str:
        return build_channel_ref("kick", slug.strip().lower())

    def _display_name(
        self,
        slug: str,
        user: dict[str, Any] | None,
    ) -> str:
        if isinstance(user, dict):
            name = str(user.get("name", "")).strip()
            if name:
                return name
        return slug.strip()

    def _profile_image_url(
        self,
        user: dict[str, Any] | None,
        fallback: dict[str, Any] | None = None,
    ) -> str:
        if isinstance(user, dict):
            value = str(user.get("profile_picture", "")).strip()
            if value:
                return value
        if isinstance(fallback, dict):
            value = str(fallback.get("profile_picture", "")).strip()
            if value:
                return value
        return ""

    def _category_name(self, payload: dict[str, Any]) -> str:
        category = payload.get("category")
        if isinstance(category, dict):
            return str(category.get("name", "")).strip()
        return ""

    def _stream_payload(self, channel: dict[str, Any]) -> dict[str, Any] | None:
        stream = channel.get("stream")
        if isinstance(stream, dict):
            return stream
        return None

    def _viewer_count(self, payload: dict[str, Any]) -> int:
        value = payload.get("viewer_count", 0)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _build_live_streams(
        self,
        channels: list[dict[str, Any]],
        users_by_id: dict[int, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        streams: list[dict[str, Any]] = []
        for channel in channels:
            stream = self._stream_payload(channel)
            if not stream or stream.get("is_live") is False:
                continue
            slug = str(channel.get("slug", "")).strip().lower()
            if not slug:
                continue
            user = users_by_id.get(self._user_id(channel))
            streams.append(
                {
                    "platform": "kick",
                    "channel_ref": self._channel_ref(slug),
                    "user_login": slug,
                    "user_name": self._display_name(slug, user),
                    "viewer_count": self._viewer_count(stream),
                    "title": str(channel.get("stream_title", "")).strip(),
                    "game_name": self._category_name(channel),
                    "game_id": "",
                    "started_at": str(stream.get("start_time", "")).strip(),
                    "thumbnail_url": str(stream.get("thumbnail", "")).strip(),
                }
            )
        return streams

    def _build_users(
        self,
        channels: list[dict[str, Any]],
        users_by_id: dict[int, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        users: list[dict[str, Any]] = []
        for channel in channels:
            slug = str(channel.get("slug", "")).strip().lower()
            if not slug:
                continue
            user = users_by_id.get(self._user_id(channel))
            users.append(
                {
                    "platform": "kick",
                    "channel_ref": self._channel_ref(slug),
                    "login": slug,
                    "display_name": self._display_name(slug, user),
                    "profile_image_url": self._profile_image_url(user),
                }
            )
        return users

    async def get_channels(self, logins: list[str]) -> list[dict[str, Any]]:
        return await self._get_channels_by_slug(logins)

    async def get_live_streams(self, logins: list[str]) -> list[dict[str, Any]]:
        channels, users_by_id = await self._get_channels_and_users(logins)
        return self._build_live_streams(channels, users_by_id)

    async def get_users(self, logins: list[str]) -> list[dict[str, Any]]:
        channels, users_by_id = await self._get_channels_and_users(logins)
        return self._build_users(channels, users_by_id)

    async def get_streams_and_users(
        self,
        logins: list[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        channels, users_by_id = await self._get_channels_and_users(logins)
        return (
            self._build_live_streams(channels, users_by_id),
            self._build_users(channels, users_by_id),
        )

    async def _get_live_directory(
        self,
        *,
        limit: int = 100,
        sort: str = "viewer_count",
    ) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
        cached = getattr(self, "_live_directory_cache", None)
        cached_at = float(getattr(self, "_live_directory_cached_at", 0.0))
        if (
            cached is not None
            and time.time() - cached_at < _LIVE_DIRECTORY_TTL
        ):
            return cached

        livestreams = await self._get_livestreams(limit=limit, sort=sort)
        user_ids = [
            self._user_id(stream)
            for stream in livestreams
            if self._user_id(stream) > 0
        ]
        users = await self._get_users_by_id(user_ids) if user_ids else []
        users_by_id = {
            self._user_id(user, key="user_id"): user
            for user in users
            if self._user_id(user, key="user_id") > 0
        }
        self._live_directory_cached_at = time.time()
        self._live_directory_cache = (livestreams, users_by_id)
        return livestreams, users_by_id

    def _search_result(
        self,
        slug: str,
        display_name: str,
        *,
        is_live: bool,
        game_name: str,
    ) -> dict[str, Any]:
        return {
            "platform": "kick",
            "broadcaster_login": self._channel_ref(slug),
            "display_name": display_name,
            "is_live": is_live,
            "game_name": game_name,
        }

    def _live_matches_query(
        self,
        query: str,
        livestream: dict[str, Any],
        user: dict[str, Any] | None,
    ) -> bool:
        query_lower = query.strip().lower()
        if not query_lower:
            return False
        haystacks = [
            str(livestream.get("slug", "")).strip().lower(),
            self._display_name(str(livestream.get("slug", "")), user).strip().lower(),
            str(livestream.get("stream_title", "")).strip().lower(),
            self._category_name(livestream).strip().lower(),
        ]
        return any(query_lower in haystack for haystack in haystacks if haystack)

    def _exact_slug_candidate(self, query: str) -> str:
        raw = query.strip()
        if not raw:
            return ""
        if raw.lower().startswith("kick:") or "kick.com/" in raw.lower():
            platform, login = split_channel_ref(raw, default_platform="kick")
            if platform == "kick":
                return login
            return ""
        if _VALID_SLUG_RE.fullmatch(raw):
            return raw.lower()
        return ""

    async def search_channels(self, query: str) -> list[dict[str, Any]]:
        raw_query = query.strip()
        if not raw_query:
            return []

        results: list[dict[str, Any]] = []
        livestreams, users_by_id = await self._get_live_directory(limit=100, sort="viewer_count")
        for livestream in livestreams:
            slug = str(livestream.get("slug", "")).strip().lower()
            if not slug:
                continue
            user = users_by_id.get(self._user_id(livestream))
            if not self._live_matches_query(raw_query, livestream, user):
                continue
            results.append(
                self._search_result(
                    slug,
                    self._display_name(slug, user),
                    is_live=True,
                    game_name=self._category_name(livestream),
                )
            )

        exact_slug = self._exact_slug_candidate(raw_query)
        if exact_slug:
            channels, users_by_id = await self._get_channels_and_users([exact_slug])
            if channels:
                channel = channels[0]
                user = users_by_id.get(self._user_id(channel))
                results.append(
                    self._search_result(
                        exact_slug,
                        self._display_name(exact_slug, user),
                        is_live=bool(
                            (self._stream_payload(channel) or {}).get("is_live", False)
                        ),
                        game_name=self._category_name(channel),
                    )
                )

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for result in results:
            broadcaster_login = str(result.get("broadcaster_login", "")).strip().lower()
            if not broadcaster_login or broadcaster_login in seen:
                continue
            seen.add(broadcaster_login)
            deduped.append(result)
        return deduped[:8]
