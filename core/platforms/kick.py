from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import re
import secrets
import threading
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from curl_cffi import requests as curl_requests

from core.storage import load_config, token_is_valid, update_config

logger = logging.getLogger(__name__)

VALID_SLUG = re.compile(r"^[a-zA-Z0-9_-]{1,25}$")

KICK_API_URL = "https://api.kick.com"
KICK_AUTH_URL = "https://id.kick.com"
KICK_LEGACY_URL = "https://kick.com"
KICK_SEARCH_URL = "https://search.kick.com"
KICK_REDIRECT_URI = "http://localhost:3457/callback"
OAUTH_SCOPE = "user:read channel:read chat:write"
KICK_BROWSER_IMPERSONATION = "chrome124"
KICK_TYPESENSE_API_KEY = "nXIMW0iEN6sMujFYjFuhdrSwVow3pDQu"


# ── PKCE helpers ─────────────────────────────────────────────


def _generate_code_verifier(length: int = 64) -> str:
    """Generate a cryptographically random PKCE code verifier (43–128 chars, URL-safe)."""
    raw = os.urandom(length)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _generate_code_challenge(verifier: str) -> str:
    """Derive the S256 code challenge from a verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class KickClient:
    def __init__(self) -> None:
        self._config = load_config()
        self._loop_clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}
        self._token_locks: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}
        self._loop_state_lock = threading.Lock()
        self._livestreams_cache: tuple[float, list[dict[str, Any]]] = (0, [])

    def _kconf(self) -> dict[str, Any]:
        """Shortcut to the Kick platform config section."""
        return self._config.get("platforms", {}).get("kick", {})

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

    # ── OAuth (user-level PKCE) ──────────────────────────────

    def get_auth_url(self) -> str:
        """Generate PKCE challenge, store verifier in config, return auth URL."""
        self._reload_config()
        verifier = _generate_code_verifier()
        challenge = _generate_code_challenge(verifier)
        state = secrets.token_urlsafe(32)

        def _apply(cfg: dict) -> None:
            kc = cfg.get("platforms", {}).get("kick", {})
            kc["pkce_verifier"] = verifier
            kc["oauth_state"] = state

        self._config = update_config(_apply)
        kc = self._kconf()
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": kc.get("client_id", ""),
            "redirect_uri": KICK_REDIRECT_URI,
            "scope": OAUTH_SCOPE,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        encoded_params = urlencode(params)
        return f"{KICK_AUTH_URL}/oauth/authorize?{encoded_params}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange authorization code + PKCE verifier for tokens."""
        self._reload_config()
        kc = self._kconf()
        resp = await self._get_client().post(
            f"{KICK_AUTH_URL}/oauth/token",
            data={
                "client_id": kc.get("client_id", ""),
                "client_secret": kc.get("client_secret", ""),
                "code": code,
                "code_verifier": kc.get("pkce_verifier", ""),
                "grant_type": "authorization_code",
                "redirect_uri": KICK_REDIRECT_URI,
            },
        )
        resp.raise_for_status()

        def _clear_verifier(cfg: dict) -> None:
            cfg.get("platforms", {}).get("kick", {})["pkce_verifier"] = ""

        self._config = update_config(_clear_verifier)
        return resp.json()

    async def refresh_user_token(self) -> str:
        """Refresh the user token; clear auth state on 400/401."""
        kc = self._kconf()
        resp = await self._get_client().post(
            f"{KICK_AUTH_URL}/oauth/token",
            data={
                "client_id": kc.get("client_id", ""),
                "refresh_token": kc.get("refresh_token", ""),
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code in (400, 401):

            def _clear(cfg: dict) -> None:
                kc = cfg.get("platforms", {}).get("kick", {})
                kc["access_token"] = ""
                kc["refresh_token"] = ""
                kc["token_expires_at"] = 0
                kc["oauth_scopes"] = ""
                kc["pkce_verifier"] = ""
                kc["user_id"] = ""
                kc["user_login"] = ""
                kc["user_display_name"] = ""

            self._config = update_config(_clear)
            raise ValueError("User token expired. Please log in again.")
        resp.raise_for_status()
        data = resp.json()
        new_token = data["access_token"]
        new_refresh = data.get("refresh_token", kc.get("refresh_token", ""))
        new_expires = int(time.time()) + data.get("expires_in", 3600)
        new_scopes = data.get("scope", kc.get("oauth_scopes", ""))

        def _update(cfg: dict) -> None:
            kc = cfg.get("platforms", {}).get("kick", {})
            kc["access_token"] = new_token
            kc["refresh_token"] = new_refresh
            kc["token_expires_at"] = new_expires
            kc["oauth_scopes"] = new_scopes

        self._config = update_config(_update)
        return new_token

    async def get_current_user(self) -> dict[str, Any]:
        """Return the current authorized user merged with their channel slug."""
        user_data, channel_data = await asyncio.gather(
            self._get(f"{KICK_API_URL}/public/v1/users", auth_required=True),
            self._get(f"{KICK_API_URL}/public/v1/channels", auth_required=True),
        )

        users = (
            user_data.get("data", user_data)
            if isinstance(user_data, dict)
            else user_data
        )
        channels = (
            channel_data.get("data", channel_data)
            if isinstance(channel_data, dict)
            else channel_data
        )

        if isinstance(users, list) and users:
            user = dict(users[0])
        elif isinstance(users, dict):
            user = dict(users)
        else:
            user = {}

        channel: dict[str, Any] = {}
        if isinstance(channels, list) and channels:
            channel = dict(channels[0])
        elif isinstance(channels, dict):
            channel = dict(channels)

        if channel:
            user["channel"] = channel
            if channel.get("slug"):
                user["slug"] = channel["slug"]
            if channel.get("broadcaster_user_id") and not user.get("user_id"):
                user["user_id"] = channel["broadcaster_user_id"]

        if user:
            return user
        raise ValueError("No user data returned from Kick API.")

    # ── Token management ─────────────────────────────────────

    async def _ensure_token(self) -> str | None:
        """Return a valid access token, refreshing if needed. Returns None if unavailable."""
        async with self._get_token_lock():
            self._reload_config()
            kc = self._kconf()
            if token_is_valid(kc):
                return kc["access_token"]
            if kc.get("refresh_token"):
                try:
                    return await self.refresh_user_token()
                except ValueError:
                    return None
            return None

    # ── Generic GET ──────────────────────────────────────────

    async def _get(
        self,
        url: str,
        params: Any = None,
        auth_required: bool = False,
    ) -> Any:
        token = await self._ensure_token()
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif auth_required:
            raise ValueError("Authentication required but no valid token available.")
        logger.debug("GET %s params=%s", url, params)
        client = self._get_client()
        resp = await client.get(url, headers=headers, params=params)
        logger.debug("Response: %d", resp.status_code)
        if resp.status_code != 200:
            logger.debug("Body: %s", resp.text[:300])
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "2"))
            await asyncio.sleep(max(retry_after, 1))
            return await self._get(url, params, auth_required)
        if resp.status_code == 401 and token:
            async with self._get_token_lock():

                def _clear_token(cfg: dict) -> None:
                    cfg.get("platforms", {}).get("kick", {})["access_token"] = ""

                self._config = update_config(_clear_token)
            new_token = await self._ensure_token()
            if new_token:
                headers["Authorization"] = f"Bearer {new_token}"
                resp = await client.get(url, headers=headers, params=params)
            else:
                resp.raise_for_status()
        resp.raise_for_status()
        return resp.json()

    async def _legacy_get_json(self, path: str) -> dict[str, Any]:
        """Fetch browser-protected Kick endpoints through a browser-like client."""

        def _fetch() -> dict[str, Any]:
            resp = curl_requests.get(
                f"{KICK_LEGACY_URL}{path}",
                impersonate=KICK_BROWSER_IMPERSONATION,
                timeout=20,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"{resp.status_code} while fetching {path}")
            data = resp.json()
            return data if isinstance(data, dict) else {}

        return await asyncio.to_thread(_fetch)

    async def _search_typesense_channels(self, query: str) -> list[dict[str, Any]]:
        """Use the same Typesense index as the Kick web app for channel search."""

        def _fetch() -> list[dict[str, Any]]:
            resp = curl_requests.get(
                f"{KICK_SEARCH_URL}/collections/channel/documents/search",
                headers={"X-TYPESENSE-API-KEY": KICK_TYPESENSE_API_KEY},
                params={"q": query, "query_by": "username"},
                impersonate=KICK_BROWSER_IMPERSONATION,
                timeout=20,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"{resp.status_code} while searching channels")
            data = resp.json()
            hits = data.get("hits", []) if isinstance(data, dict) else []
            results: list[dict[str, Any]] = []
            for hit in hits:
                doc = hit.get("document", {}) if isinstance(hit, dict) else {}
                if not isinstance(doc, dict):
                    continue
                slug = doc.get("slug") or doc.get("channel_slug") or ""
                username = doc.get("username") or doc.get("user_username") or slug
                if not slug and username:
                    slug = str(username).strip().lower()
                if not slug:
                    continue
                results.append(
                    {
                        "slug": str(slug).strip().lower(),
                        "username": username,
                        "is_live": bool(doc.get("is_live", False)),
                        "verified": bool(doc.get("verified", False)),
                    }
                )
            return results

        return await asyncio.to_thread(_fetch)

    @staticmethod
    def _merge_channel_payloads(
        public_channel: dict[str, Any],
        legacy_channel: dict[str, Any],
        legacy_chatroom: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(public_channel)

        if legacy_channel:
            for key, value in legacy_channel.items():
                if key not in merged or merged.get(key) in ("", None, [], {}):
                    merged[key] = value
            if legacy_channel.get("user_id") and not merged.get("broadcaster_user_id"):
                merged["broadcaster_user_id"] = legacy_channel["user_id"]
            if legacy_channel.get("livestream") and not merged.get("stream"):
                merged["stream"] = legacy_channel["livestream"]
            if legacy_channel.get("id") and not merged.get("channel_id"):
                merged["channel_id"] = legacy_channel["id"]

        if legacy_chatroom:
            merged["chatroom"] = legacy_chatroom
            merged["chatroom_id"] = legacy_chatroom.get("id")
        elif isinstance(merged.get("chatroom"), dict):
            merged["chatroom_id"] = merged["chatroom"].get("id")

        return merged

    # ── API methods ──────────────────────────────────────────

    async def get_live_streams(self, slugs: list[str]) -> list[dict[str, Any]]:
        """GET /public/v1/livestreams and filter by slugs."""
        slugs = [s.strip().lower() for s in slugs if s and s.strip()]
        slugs = [s for s in slugs if VALID_SLUG.match(s)]
        if not slugs:
            return []
        # Kick's public livestreams endpoint does not support filtering by slug.
        # We fetch all live streams and filter client-side.
        # Short-lived cache (5s) avoids re-fetching within a single poll cycle.
        cache_time, cache_data = self._livestreams_cache
        if time.time() - cache_time < 5:
            streams = cache_data
        else:
            data = await self._get(f"{KICK_API_URL}/public/v1/livestreams")
            streams = data.get("data", data) if isinstance(data, dict) else data
            self._livestreams_cache = (time.time(), streams)
        slug_set = set(slugs)
        return [
            s
            for s in streams
            if s.get("channel", {}).get("slug", "").lower() in slug_set
            or s.get("slug", "").lower() in slug_set
        ]

    async def search_channels(self, query: str) -> list[dict[str, Any]]:
        """Search Kick channels via the same index used by the website."""
        query = query.strip()
        if not query:
            return []
        return await self._search_typesense_channels(query)

    async def get_channel_info(self, slug: str) -> dict[str, Any]:
        """Return public channel data merged with chat metadata from browser endpoints."""
        slug = slug.strip().lower()
        if not slug:
            return {}
        public_task = self._get(
            f"{KICK_API_URL}/public/v1/channels",
            params=[("slug", slug)],
        )
        legacy_channel_task = self._legacy_get_json(f"/api/v1/channels/{slug}")
        legacy_chatroom_task = self._legacy_get_json(
            f"/api/v2/channels/{slug}/chatroom"
        )

        public_data, legacy_channel, legacy_chatroom = await asyncio.gather(
            public_task,
            legacy_channel_task,
            legacy_chatroom_task,
            return_exceptions=True,
        )

        public_channel: dict[str, Any] = {}
        if isinstance(public_data, dict):
            channels = public_data.get("data", public_data)
            if isinstance(channels, list):
                public_channel = channels[0] if channels else {}
            elif isinstance(channels, dict):
                public_channel = channels

        return self._merge_channel_payloads(
            public_channel,
            legacy_channel if isinstance(legacy_channel, dict) else {},
            legacy_chatroom if isinstance(legacy_chatroom, dict) else {},
        )

    async def get_followed_channels(self, user_id: str) -> list[str]:
        """Kick doesn't support fetching followed channels via API — returns []."""
        return []

    async def get_categories(self, query: str = "") -> list[dict[str, Any]]:
        """GET /public/v2/categories, normalized to cross-platform format."""
        query = query.strip()
        params = [("search", query)] if query else None
        data = await self._get(f"{KICK_API_URL}/public/v2/categories", params=params)
        items: list[Any] = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []
        return [
            {
                "platform": "kick",
                "category_id": str(item.get("id", "")),
                "name": item.get("name", ""),
                "box_art_url": item.get("banner", ""),
                "viewers": item.get("viewers_count", 0),
            }
            for item in items
            if item.get("name")
        ]

    async def get_top_streams(
        self,
        category_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """GET /public/v1/livestreams sorted by viewers (desc).

        Normalized to the cross-platform stream dict format.
        """
        params: list[tuple[str, str]] = [
            ("limit", str(min(limit, 100))),
            ("sort", "desc"),
        ]
        if category_id:
            params.append(("category_id", category_id))
        data = await self._get(f"{KICK_API_URL}/public/v1/livestreams", params=params)
        items: list[Any] = data.get("data", []) if isinstance(data, dict) else []
        results: list[dict[str, Any]] = []
        for s in items:
            channel = s.get("channel", {})
            user = channel.get("user", {})
            categories = s.get("categories", [])
            cat = categories[0] if categories else {}
            results.append(
                {
                    "platform": "kick",
                    "channel_id": str(channel.get("id", "")),
                    "channel_login": channel.get("slug", ""),
                    "display_name": user.get("username", channel.get("slug", "")),
                    "title": s.get("session_title", ""),
                    "category": cat.get("name", ""),
                    "category_id": str(cat.get("id", "")),
                    "viewers": s.get("viewer_count", 0),
                    "started_at": s.get("created_at", ""),
                    "thumbnail_url": (s.get("thumbnail") or {}).get("src", ""),
                    "avatar_url": user.get("profile_pic", ""),
                }
            )
        return results
