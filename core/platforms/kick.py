from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import re
import threading
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from core.storage import load_config, save_config, token_is_valid

logger = logging.getLogger(__name__)

VALID_SLUG = re.compile(r"^[a-zA-Z0-9_-]{1,25}$")

KICK_API_URL = "https://api.kick.com"
KICK_AUTH_URL = "https://id.kick.com"
KICK_REDIRECT_URI = "http://localhost:3457/callback"
OAUTH_SCOPE = "user:read channel:read"


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
        kc = self._kconf()
        verifier = _generate_code_verifier()
        challenge = _generate_code_challenge(verifier)
        kc["pkce_verifier"] = verifier
        save_config(self._config)
        params = urlencode(
            {
                "client_id": kc.get("client_id", ""),
                "redirect_uri": KICK_REDIRECT_URI,
                "response_type": "code",
                "scope": OAUTH_SCOPE,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{KICK_AUTH_URL}/oauth/authorize?{params}"

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
        kc["pkce_verifier"] = ""
        save_config(self._config)
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
            # Token revoked — clear user auth
            kc["access_token"] = ""
            kc["refresh_token"] = ""
            kc["token_expires_at"] = 0
            kc["pkce_verifier"] = ""
            kc["user_id"] = ""
            kc["user_login"] = ""
            kc["user_display_name"] = ""
            save_config(self._config)
            raise ValueError("User token expired. Please log in again.")
        resp.raise_for_status()
        data = resp.json()
        kc["access_token"] = data["access_token"]
        kc["refresh_token"] = data.get("refresh_token", kc.get("refresh_token", ""))
        kc["token_expires_at"] = int(time.time()) + data.get("expires_in", 3600)
        save_config(self._config)
        return data["access_token"]

    async def get_current_user(self) -> dict[str, Any]:
        """GET /api/v1/user — requires valid user token."""
        token = await self._ensure_token()
        if not token:
            raise ValueError("No valid token. Please log in to Kick.")
        resp = await self._get_client().get(
            f"{KICK_API_URL}/api/v1/user",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()

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
                kc = self._kconf()
                kc["access_token"] = ""
                save_config(self._config)
            new_token = await self._ensure_token()
            if new_token:
                headers["Authorization"] = f"Bearer {new_token}"
                resp = await client.get(url, headers=headers, params=params)
            else:
                resp.raise_for_status()
        resp.raise_for_status()
        return resp.json()

    # ── API methods ──────────────────────────────────────────

    async def get_live_streams(self, slugs: list[str]) -> list[dict[str, Any]]:
        """GET /public/v1/livestreams and filter by slugs."""
        slugs = [s.strip().lower() for s in slugs if s and s.strip()]
        slugs = [s for s in slugs if VALID_SLUG.match(s)]
        if not slugs:
            return []
        # Kick's public livestreams endpoint does not support filtering by slug.
        # We fetch all live streams and filter client-side.
        data = await self._get(f"{KICK_API_URL}/public/v1/livestreams")
        streams: list[dict[str, Any]] = (
            data.get("data", data) if isinstance(data, dict) else data
        )
        slug_set = set(slugs)
        return [
            s
            for s in streams
            if s.get("channel", {}).get("slug", "").lower() in slug_set
            or s.get("slug", "").lower() in slug_set
        ]

    async def search_channels(self, query: str) -> list[dict[str, Any]]:
        """GET /public/v1/channels?search=query."""
        query = query.strip()
        if not query:
            return []
        data = await self._get(
            f"{KICK_API_URL}/public/v1/channels",
            params=[("search", query)],
        )
        return data.get("data", data) if isinstance(data, dict) else data

    async def get_channel_info(self, slug: str) -> dict[str, Any]:
        """GET /public/v1/channels/{slug}."""
        slug = slug.strip().lower()
        data = await self._get(f"{KICK_API_URL}/public/v1/channels/{slug}")
        return data.get("data", data) if isinstance(data, dict) else data

    async def get_followed_channels(self, user_id: str) -> list[str]:
        """Kick doesn't support fetching followed channels via API — returns []."""
        return []

    async def get_categories(self, query: str) -> list[dict[str, Any]]:
        """GET /public/v2/categories."""
        query = query.strip()
        params = [("search", query)] if query else None
        data = await self._get(f"{KICK_API_URL}/public/v2/categories", params=params)
        return data.get("data", data) if isinstance(data, dict) else data
