"""Shared infrastructure for all platform API clients."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
import time
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from core import bundled_credentials as _bundled_creds
from core.platform import PlatformClient
from core.storage import get_platform_config, load_config

_BUNDLED_CLIENT_IDS: dict[str, str] = {
    "twitch": _bundled_creds.TWITCH_CLIENT_ID,
    "kick": _bundled_creds.KICK_CLIENT_ID,
    "youtube": _bundled_creds.YOUTUBE_CLIENT_ID,
}
_BUNDLED_CLIENT_SECRETS: dict[str, str] = {
    "twitch": _bundled_creds.TWITCH_CLIENT_SECRET,
    "kick": _bundled_creds.KICK_CLIENT_SECRET,
    "youtube": _bundled_creds.YOUTUBE_CLIENT_SECRET,
}

logger = logging.getLogger(__name__)

MAX_RATE_LIMIT_RETRIES = 3
_MIN_RETRY_DELAY = 1.0
_MAX_RETRY_DELAY = 30.0


class AuthRevokedError(ValueError):
    """The platform rejected the refresh token; stored user auth was cleared."""


def _retry_delay(resp: httpx.Response, default: float) -> float:
    """Seconds to wait before retrying a 429, clamped to [1, 30].

    Reads ``Retry-After`` (delta-seconds or HTTP-date), then Twitch's
    ``Ratelimit-Reset`` (unix timestamp). Unparseable values use ``default``.
    """
    delay = default
    retry_after = resp.headers.get("Retry-After", "").strip()
    reset = resp.headers.get("Ratelimit-Reset", "").strip()
    if retry_after:
        try:
            delay = float(retry_after)
        except ValueError:
            try:
                delay = parsedate_to_datetime(retry_after).timestamp() - time.time()
            except (TypeError, ValueError, IndexError):
                delay = default
    elif reset:
        try:
            delay = float(reset) - time.time()
        except ValueError:
            delay = default
    return min(max(delay, _MIN_RETRY_DELAY), _MAX_RETRY_DELAY)


def _refresh_rejected(resp: httpx.Response) -> bool:
    """True when the token endpoint refused the refresh token itself.

    Neither Twitch (``{"message": "Invalid refresh token"}``) nor Kick
    (``{"error": "Invalid request"}``) sends a standard ``invalid_grant`` code,
    so 400/401 is the revocation signal; 5xx, 429 and transport errors are not.
    """
    return resp.status_code in (400, 401)


# A refresh is a single HTTP round trip; past this, assume a wedged holder
# and proceed rather than hang the caller's thread forever.
_TOKEN_THREAD_LOCK_TIMEOUT = 60.0
_TOKEN_LOCK_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="twitchx-token-lock"
)


class _TokenGuard:
    """``async with``: per-loop asyncio.Lock, then a process-wide threading.Lock."""

    def __init__(self, loop_lock: asyncio.Lock, thread_lock: threading.Lock) -> None:
        self._loop_lock = loop_lock
        self._thread_lock = thread_lock
        self._thread_held = False

    async def __aenter__(self) -> None:
        await self._loop_lock.acquire()
        thread_lock = self._thread_lock
        # A concurrent.futures future, not a loop one: its done-callback runs
        # in the worker thread, so it still fires after the caller's loop closed.
        cfut = _TOKEN_LOCK_EXECUTOR.submit(
            thread_lock.acquire, True, _TOKEN_THREAD_LOCK_TIMEOUT
        )
        try:
            self._thread_held = await asyncio.shield(asyncio.wrap_future(cfut))
        except BaseException:
            # Cancelled (e.g. wait_for timeout) while the worker still waits:
            # release the lock as soon as that worker gets it, or it leaks.
            def _release_late(f: concurrent.futures.Future[bool]) -> None:
                if not f.cancelled() and f.exception() is None and f.result():
                    thread_lock.release()

            cfut.add_done_callback(_release_late)
            self._loop_lock.release()
            raise
        if not self._thread_held:
            logger.warning("Token lock wait timed out; continuing without it")

    async def __aexit__(self, *exc: object) -> None:
        if self._thread_held:
            self._thread_held = False
            self._thread_lock.release()
        self._loop_lock.release()


class BasePlatformClient(PlatformClient):
    """Shared infrastructure for all platform API clients.

    Subclasses must set:
        PLATFORM_ID: str      — e.g. "twitch", "kick", "youtube"
        PLATFORM_NAME: str    — e.g. "Twitch", "Kick", "YouTube"
    """

    PLATFORM_ID: str = ""
    PLATFORM_NAME: str = ""

    # Called (from the HTTP worker thread) after refresh_user_token() wiped the
    # stored user auth. The UI layer sets it; core never imports UI code.
    on_auth_revoked: Callable[[], None] | None = None

    # --- Per-event-loop httpx client pooling (keyed by (loop, PLATFORM_ID)) ---
    _loop_clients: dict[tuple[asyncio.AbstractEventLoop, str], httpx.AsyncClient] = {}
    _token_locks: dict[tuple[asyncio.AbstractEventLoop, str], asyncio.Lock] = {}
    _thread_token_locks: dict[str, threading.Lock] = {}
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

    def _effective_creds(self) -> tuple[str, str]:
        """Return (client_id, client_secret): config override or bundled fallback."""
        cfg = self._platform_config()
        cid = cfg.get("client_id", "") or _BUNDLED_CLIENT_IDS.get(self.PLATFORM_ID, "")
        csec = cfg.get("client_secret", "") or _BUNDLED_CLIENT_SECRETS.get(
            self.PLATFORM_ID, ""
        )
        return cid, csec

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
        key = (loop, self.PLATFORM_ID)
        with self._loop_state_lock:
            client = self._loop_clients.get(key)
            if client is None:
                client = httpx.AsyncClient(
                    timeout=httpx.Timeout(self._client_timeout()),
                    headers=self._client_headers(),
                )
                self._loop_clients[key] = client
            return client

    # --- Token lock (per loop + process-wide per platform) ---
    def _get_token_lock(self) -> _TokenGuard:
        """Serialize token checks/refreshes across coroutines *and* threads.

        Every worker thread runs its own event loop, so an asyncio.Lock alone
        lets polling, chat and image threads refresh at the same time with the
        same refresh token — Kick rotates it, so the losers get 400 and wipe
        the login. The asyncio lock is taken first (one contender per loop),
        then the platform's threading lock off-loop, so no loop ever blocks.
        """
        loop = asyncio.get_running_loop()
        key = (loop, self.PLATFORM_ID)
        with self._loop_state_lock:
            lock = self._token_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._token_locks[key] = lock
            thread_lock = self._thread_token_locks.get(self.PLATFORM_ID)
            if thread_lock is None:
                thread_lock = threading.Lock()
                self._thread_token_locks[self.PLATFORM_ID] = thread_lock
        return _TokenGuard(lock, thread_lock)

    # --- Cleanup ---
    async def close(self) -> None:
        await self.close_loop_resources()

    async def close_loop_resources(self) -> None:
        loop = asyncio.get_running_loop()
        key = (loop, self.PLATFORM_ID)
        with self._loop_state_lock:
            client = self._loop_clients.pop(key, None)
            self._token_locks.pop(key, None)
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
                and platform_cfg.get("token_expires_at", 0) > time.time() + 60
            ):
                return platform_cfg["access_token"]
            if platform_cfg.get("refresh_token"):
                try:
                    return await self.refresh_user_token()
                except ValueError:
                    return None
            return None

    def _notify_auth_revoked(self) -> None:
        callback = self.on_auth_revoked
        if callback is None:
            return
        try:
            callback()
        except Exception:
            logger.exception("%s on_auth_revoked callback failed", self.PLATFORM_NAME)

    async def _refresh_after_401(self, stale_token: str) -> str | None:
        """Refresh after a 401, once per stale token across concurrent callers.

        Under the token lock: if another coroutine already replaced
        ``stale_token``, reuse its result instead of refreshing again.
        """
        async with self._get_token_lock():
            self._reload_config()
            platform_cfg = self._platform_config()
            current = platform_cfg.get("access_token", "")
            if current and current != stale_token:
                return current
            if not platform_cfg.get("refresh_token"):
                return None
            try:
                return await self.refresh_user_token()
            except ValueError:
                return None

    # --- Shared request wrapper with retry/refresh pattern ---
    async def _request(
        self,
        method: str,
        url: str,
        params: Any = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """HTTP request wrapper with bounded 429 retries and one 401 refresh."""
        client = self._get_client()
        merged_headers = {**client.headers, **(headers or {})}
        rate_limit_retries = 0
        refreshed = False

        while True:
            logger.debug("%s %s params=%s", method, url, params)
            resp = await client.request(
                method, url, params=params, headers=merged_headers
            )

            if resp.status_code == 429 and rate_limit_retries < MAX_RATE_LIMIT_RETRIES:
                rate_limit_retries += 1
                delay = _retry_delay(resp, 5)
                logger.debug("429 rate-limited, waiting %.1fs", delay)
                await asyncio.sleep(delay)
                continue

            if resp.status_code == 401 and not refreshed:
                refreshed = True
                logger.debug("401 unauthorized, refreshing token")
                stale = merged_headers.get("Authorization", "").removeprefix("Bearer ")
                new_token = await self._refresh_after_401(stale)
                if new_token:
                    merged_headers["Authorization"] = f"Bearer {new_token}"
                    continue

            self._check_response_errors(resp)
            resp.raise_for_status()
            return resp

    def _check_response_errors(self, resp: httpx.Response) -> None:
        """Override to handle platform-specific HTTP errors (e.g. YouTube 403 quota)."""
        pass
