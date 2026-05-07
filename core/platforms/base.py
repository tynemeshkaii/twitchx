"""Shared infrastructure for all platform API clients."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

import httpx

from core.platform import PlatformClient
from core.storage import get_platform_config, load_config

logger = logging.getLogger(__name__)


class BasePlatformClient(PlatformClient):
    """Shared infrastructure for all platform API clients.

    Subclasses must set:
        PLATFORM_ID: str      — e.g. "twitch", "kick", "youtube"
        PLATFORM_NAME: str    — e.g. "Twitch", "Kick", "YouTube"
    """

    PLATFORM_ID: str = ""
    PLATFORM_NAME: str = ""

    # --- Per-event-loop httpx client pooling ---
    _loop_clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}
    _token_locks: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}
    _loop_state_lock = threading.Lock()

    def __init__(self) -> None:
        self._config = load_config()
        self.platform_id = self.PLATFORM_ID
        self.platform_name = self.PLATFORM_NAME

    # --- Config accessors ---
    def _reload_config(self) -> None:
        self._config = load_config()

    def _platform_config(self) -> dict[str, Any]:
        """Return platform-specific config section (e.g. config.platforms.twitch)."""
        return get_platform_config(self._config, self.PLATFORM_ID)

    # --- Per-loop httpx client ---
    def _client_headers(self) -> dict[str, str]:
        """Override in subclass to customise User-Agent / Accept headers."""
        return {
            "User-Agent": f"TwitchX/2.0 ({self.PLATFORM_NAME})",
            "Accept": "application/json",
        }

    def _client_timeout(self) -> float:
        """Override in subclass to customise HTTP timeout."""
        return 30.0

    def _get_client(self) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        with self._loop_state_lock:
            client = self._loop_clients.get(loop)
            if client is None:
                client = httpx.AsyncClient(
                    timeout=httpx.Timeout(self._client_timeout()),
                    headers=self._client_headers(),
                )
                self._loop_clients[loop] = client
            return client

    # --- Per-loop token lock ---
    def _get_token_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        with self._loop_state_lock:
            lock = self._token_locks.get(loop)
            if lock is None:
                lock = asyncio.Lock()
                self._token_locks[loop] = lock
            return lock

    # --- Cleanup ---
    async def close(self) -> None:
        await self.close_loop_resources()

    async def close_loop_resources(self) -> None:
        loop = asyncio.get_running_loop()
        with self._loop_state_lock:
            client = self._loop_clients.pop(loop, None)
            self._token_locks.pop(loop, None)
        if client is not None:
            await client.aclose()

    def reset_client(self) -> None:
        """Compatibility no-op.

        HTTP clients are now scoped per event loop, so a new temporary loop
        automatically gets a fresh client and never reuses sockets from a
        previously closed loop.
        """

    # --- Token management (basic user-token only; Twitch overrides for app tokens) ---
    async def _ensure_token(self) -> str | None:
        """Check and refresh user token if needed. Returns token or None."""
        async with self._get_token_lock():
            self._reload_config()
            platform_cfg = self._platform_config()
            if (
                platform_cfg.get("access_token")
                and platform_cfg.get("token_expires_at", 0)
                > asyncio.get_running_loop().time() + 60
            ):
                return platform_cfg["access_token"]
            if platform_cfg.get("refresh_token"):
                try:
                    return await self.refresh_user_token()
                except ValueError:
                    return None
            return None

    # --- Shared request wrapper with retry/refresh pattern ---
    async def _request(
        self,
        method: str,
        url: str,
        params: Any = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """HTTP request wrapper with rate-limit retry and 401 token refresh."""
        client = self._get_client()
        merged_headers = {**client.headers, **(headers or {})}

        while True:
            logger.debug("%s %s params=%s", method, url, params)
            resp = await client.request(
                method, url, params=params, headers=merged_headers
            )

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("retry-after", "5"))
                logger.debug("429 rate-limited, waiting %ds", retry_after)
                await asyncio.sleep(retry_after)
                continue

            if resp.status_code == 401:
                logger.debug("401 unauthorized, refreshing token")
                new_token = await self.refresh_user_token()
                if new_token:
                    merged_headers["Authorization"] = f"Bearer {new_token}"
                    continue
                resp.raise_for_status()
                return resp

            self._check_response_errors(resp)
            resp.raise_for_status()
            return resp

    def _check_response_errors(self, resp: httpx.Response) -> None:
        """Override to handle platform-specific HTTP errors (e.g. YouTube 403 quota)."""
        pass
