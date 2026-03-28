# Phase 1: Kick Platform — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add full Kick.com support as a second streaming platform — live streams, OAuth PKCE login, search, favorites, platform filtering, and settings.

**Architecture:** KickClient mirrors TwitchClient's structure (per-loop httpx clients, token locks, auto-refresh on 401) but uses OAuth 2.1 + PKCE instead of client_credentials. The existing oauth_server.py on port 3457 handles Kick callbacks too (no parallel logins allowed). UI adds platform filter tabs, platform badges on cards, and a Kick settings tab. `stream_resolver.py` gains a `platform` parameter to build `kick.com/{slug}` URLs for streamlink.

**Tech Stack:** Python 3.14, httpx, asyncio, pywebview, streamlink, vanilla JS/CSS

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `core/platforms/kick.py` | KickClient — Kick API + OAuth PKCE |
| Create | `tests/platforms/test_kick.py` | Unit tests for KickClient |
| Modify | `core/stream_resolver.py` | Add `platform` param for Kick URL construction |
| Modify | `tests/test_stream_resolver.py` | Tests for Kick stream resolution |
| Modify | `ui/api.py` | Integrate KickClient into bridge, add kick_login/logout/test, extend refresh/search/add/remove/watch |
| Modify | `ui/index.html` | Platform filter tabs, platform badges, Kick settings tab, platform-aware search/add |

---

### Task 1: KickClient — PKCE helpers and constructor

**Files:**
- Create: `core/platforms/kick.py`
- Create: `tests/platforms/test_kick.py`

- [ ] **Step 1: Write PKCE and slug validation tests**

```python
# tests/platforms/test_kick.py
from __future__ import annotations

import asyncio
import base64
import hashlib

import pytest

from core.platforms.kick import VALID_SLUG, KickClient, generate_pkce_pair


class TestValidSlug:
    @pytest.mark.parametrize(
        "slug",
        ["xqc", "trainwreck", "a_b_c", "user123", "some-slug", "a" * 25],
    )
    def test_accepts_valid(self, slug: str) -> None:
        assert VALID_SLUG.match(slug)

    @pytest.mark.parametrize(
        "slug",
        [
            "kick.com/xqc",
            "https://kick.com/xqc",
            "",
            "user name",
            "user@name",
        ],
    )
    def test_rejects_invalid(self, slug: str) -> None:
        assert not VALID_SLUG.match(slug)


class TestPKCE:
    def test_verifier_length(self) -> None:
        verifier, challenge = generate_pkce_pair()
        assert 43 <= len(verifier) <= 128

    def test_challenge_matches_verifier(self) -> None:
        verifier, challenge = generate_pkce_pair()
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        assert challenge == expected

    def test_pair_is_unique(self) -> None:
        v1, _ = generate_pkce_pair()
        v2, _ = generate_pkce_pair()
        assert v1 != v2
```

- [ ] **Step 2: Run tests — expect FAIL (module not found)**

Run: `cd /Users/pesnya/Documents/streamdeck && uv run pytest tests/platforms/test_kick.py -v`
Expected: `ModuleNotFoundError: No module named 'core.platforms.kick'`

- [ ] **Step 3: Create kick.py with PKCE helpers, VALID_SLUG, and KickClient constructor**

```python
# core/platforms/kick.py
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
KICK_OAUTH_SCOPE = "user:read"


def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge (S256)."""
    verifier = base64.urlsafe_b64encode(os.urandom(96)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


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
        """Compatibility no-op — clients are per event loop."""

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
```

- [ ] **Step 4: Run tests — expect PASS for PKCE and slug tests**

Run: `cd /Users/pesnya/Documents/streamdeck && uv run pytest tests/platforms/test_kick.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/pesnya/Documents/streamdeck
git add core/platforms/kick.py tests/platforms/test_kick.py
git commit -m "feat(kick): add KickClient skeleton with PKCE helpers and slug validation"
```

---

### Task 2: KickClient — OAuth flow (auth URL, exchange, refresh, get_current_user)

**Files:**
- Modify: `core/platforms/kick.py`
- Modify: `tests/platforms/test_kick.py`

- [ ] **Step 1: Write tests for auth URL generation and PKCE verifier storage**

```python
# Add to tests/platforms/test_kick.py

class TestKickAuthUrl:
    def test_auth_url_contains_pkce_challenge(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("core.platforms.kick.load_config", lambda: {
            "platforms": {
                "kick": {
                    "client_id": "test_id",
                    "client_secret": "test_secret",
                    "access_token": "",
                    "refresh_token": "",
                    "token_expires_at": 0,
                    "pkce_verifier": "",
                    "user_id": "",
                    "user_login": "",
                    "user_display_name": "",
                }
            },
            "favorites": [],
            "settings": {},
        })
        saved = {}
        monkeypatch.setattr("core.platforms.kick.save_config", lambda c: saved.update(c))

        client = KickClient()
        url = client.get_auth_url()
        assert "id.kick.com/oauth/authorize" in url
        assert "code_challenge=" in url
        assert "code_challenge_method=S256" in url
        assert "response_type=code" in url
        # Verifier should be stored in config
        kc = saved.get("platforms", {}).get("kick", {})
        assert len(kc.get("pkce_verifier", "")) > 40

        loop = asyncio.new_event_loop()
        loop.run_until_complete(client.close())
        loop.close()
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `cd /Users/pesnya/Documents/streamdeck && uv run pytest tests/platforms/test_kick.py::TestKickAuthUrl -v`
Expected: FAIL — `get_auth_url` not defined

- [ ] **Step 3: Implement OAuth methods in KickClient**

Add these methods to `KickClient` in `core/platforms/kick.py`:

```python
    # ── OAuth (PKCE) ───────────────────────────────────────────

    def get_auth_url(self) -> str:
        self._reload_config()
        kc = self._kconf()
        verifier, challenge = generate_pkce_pair()
        kc["pkce_verifier"] = verifier
        save_config(self._config)

        params = urlencode(
            {
                "client_id": kc["client_id"],
                "redirect_uri": KICK_REDIRECT_URI,
                "response_type": "code",
                "scope": KICK_OAUTH_SCOPE,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{KICK_AUTH_URL}/oauth/authorize?{params}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        self._reload_config()
        kc = self._kconf()
        resp = await self._get_client().post(
            f"{KICK_AUTH_URL}/oauth/token",
            data={
                "client_id": kc["client_id"],
                "client_secret": kc["client_secret"],
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": KICK_REDIRECT_URI,
                "code_verifier": kc.get("pkce_verifier", ""),
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def refresh_user_token(self) -> str:
        kc = self._kconf()
        resp = await self._get_client().post(
            f"{KICK_AUTH_URL}/oauth/token",
            data={
                "client_id": kc["client_id"],
                "client_secret": kc["client_secret"],
                "refresh_token": kc["refresh_token"],
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code in (400, 401):
            kc["access_token"] = ""
            kc["refresh_token"] = ""
            kc["token_expires_at"] = 0
            kc["pkce_verifier"] = ""
            kc["user_id"] = ""
            kc["user_login"] = ""
            kc["user_display_name"] = ""
            save_config(self._config)
            raise ValueError("Kick token expired. Please log in again.")
        resp.raise_for_status()
        data = resp.json()
        kc["access_token"] = data["access_token"]
        kc["refresh_token"] = data.get("refresh_token", kc["refresh_token"])
        kc["token_expires_at"] = int(time.time()) + data.get("expires_in", 3600)
        save_config(self._config)
        return data["access_token"]

    async def get_current_user(self) -> dict[str, Any]:
        kc = self._kconf()
        headers = {"Authorization": f"Bearer {kc['access_token']}"}
        resp = await self._get_client().get(
            f"{KICK_API_URL}/api/v1/user", headers=headers
        )
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd /Users/pesnya/Documents/streamdeck && uv run pytest tests/platforms/test_kick.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/pesnya/Documents/streamdeck
git add core/platforms/kick.py tests/platforms/test_kick.py
git commit -m "feat(kick): add OAuth PKCE flow (auth URL, exchange, refresh, get_current_user)"
```

---

### Task 3: KickClient — API methods (get_live_streams, search_channels, get_channel_info)

**Files:**
- Modify: `core/platforms/kick.py`
- Modify: `tests/platforms/test_kick.py`

- [ ] **Step 1: Write tests for stream/channel filtering**

```python
# Add to tests/platforms/test_kick.py

class TestGetLiveStreamsFiltering:
    def test_filters_invalid_slugs(self) -> None:
        client = KickClient()
        slugs = ["valid-user", "https://kick.com/bad", "", "good_123"]
        cleaned = [s.strip().lower() for s in slugs if s and s.strip()]
        cleaned = [s for s in cleaned if VALID_SLUG.match(s)]
        assert cleaned == ["valid-user", "good_123"]
        loop = asyncio.new_event_loop()
        loop.run_until_complete(client.close())
        loop.close()

    def test_empty_list(self) -> None:
        client = KickClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(client.get_live_streams([]))
        assert result == []
        loop.run_until_complete(client.close())
        loop.close()


class TestSearchChannels:
    def test_empty_query_returns_empty(self) -> None:
        client = KickClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(client.search_channels(""))
        assert result == []
        loop.run_until_complete(client.close())
        loop.close()

    def test_whitespace_query_returns_empty(self) -> None:
        client = KickClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(client.search_channels("   "))
        assert result == []
        loop.run_until_complete(client.close())
        loop.close()


class TestGetFollowedChannels:
    def test_returns_empty_list(self) -> None:
        """Kick API does not support follows — always returns empty."""
        client = KickClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(client.get_followed_channels("any_id"))
        assert result == []
        loop.run_until_complete(client.close())
        loop.close()
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `cd /Users/pesnya/Documents/streamdeck && uv run pytest tests/platforms/test_kick.py::TestGetLiveStreamsFiltering -v`
Expected: FAIL — `get_live_streams` not defined

- [ ] **Step 3: Implement API methods in KickClient**

Add `_ensure_token`, `_get`, and API methods to `KickClient`:

```python
    # ── Token management ───────────────────────────────────────

    async def _ensure_token(self) -> str | None:
        """Return a valid access token if we have one, or None for public endpoints."""
        async with self._get_token_lock():
            self._reload_config()
            kc = self._kconf()
            if token_is_valid(kc):
                return kc["access_token"]
            if kc.get("refresh_token"):
                return await self.refresh_user_token()
            return None

    async def _get(
        self,
        url: str,
        params: Any = None,
        auth_required: bool = False,
    ) -> Any:
        headers: dict[str, str] = {}
        token = await self._ensure_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif auth_required:
            raise ValueError("Kick login required for this action.")

        logger.debug("GET %s params=%s", url, params)
        client = self._get_client()
        resp = await client.get(url, headers=headers, params=params)
        logger.debug("Response: %d", resp.status_code)

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "2"))
            await asyncio.sleep(max(retry_after, 1))
            return await self._get(url, params, auth_required)

        if resp.status_code == 401 and token:
            kc = self._kconf()
            kc["access_token"] = ""
            save_config(self._config)
            if kc.get("refresh_token"):
                new_token = await self.refresh_user_token()
                headers["Authorization"] = f"Bearer {new_token}"
                resp = await client.get(url, headers=headers, params=params)
            else:
                resp.raise_for_status()

        resp.raise_for_status()
        return resp.json()

    # ── Public API ─────────────────────────────────────────────

    async def get_live_streams(self, slugs: list[str]) -> list[dict[str, Any]]:
        slugs = [s.strip().lower() for s in slugs if s and s.strip()]
        slugs = [s for s in slugs if VALID_SLUG.match(s)]
        if not slugs:
            return []
        # Kick livestreams endpoint — fetch all and filter by our slugs
        data = await self._get(f"{KICK_API_URL}/public/v1/livestreams")
        all_streams: list[dict[str, Any]] = data if isinstance(data, list) else data.get("data", [])
        slug_set = set(slugs)
        return [
            s for s in all_streams
            if s.get("slug", "").lower() in slug_set
            or s.get("channel", {}).get("slug", "").lower() in slug_set
        ]

    async def search_channels(self, query: str) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            return []
        data = await self._get(
            f"{KICK_API_URL}/public/v1/channels",
            params={"search": query},
        )
        return data if isinstance(data, list) else data.get("data", [])

    async def get_channel_info(self, slug: str) -> dict[str, Any]:
        data = await self._get(f"{KICK_API_URL}/public/v1/channels/{slug}")
        return data if isinstance(data, dict) else {}

    async def get_followed_channels(self, user_id: str) -> list[str]:
        """Kick API does not support follows — return empty list."""
        return []

    async def get_categories(self, query: str | None = None) -> list[dict[str, Any]]:
        params = {"search": query} if query else None
        data = await self._get(f"{KICK_API_URL}/public/v2/categories", params=params)
        return data if isinstance(data, list) else data.get("data", [])
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd /Users/pesnya/Documents/streamdeck && uv run pytest tests/platforms/test_kick.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/pesnya/Documents/streamdeck
git add core/platforms/kick.py tests/platforms/test_kick.py
git commit -m "feat(kick): add API methods (get_live_streams, search, channel info, categories)"
```

---

### Task 4: KickClient — per-event-loop client isolation test

**Files:**
- Modify: `tests/platforms/test_kick.py`

- [ ] **Step 1: Write test for separate httpx clients per event loop**

```python
# Add to tests/platforms/test_kick.py
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class _KeepAliveHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


class TestLoopLocalHttpClient:
    def test_uses_separate_clients_for_separate_event_loops(self) -> None:
        server = HTTPServer(("127.0.0.1", 0), _KeepAliveHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        client = KickClient()
        client_ids: list[int] = []
        responses: list[str] = []

        async def fetch_once() -> tuple[int, str]:
            http_client = client._get_client()
            response = await http_client.get(f"http://127.0.0.1:{port}/")
            return id(http_client), response.text

        try:
            for _ in range(2):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    client_id, body = loop.run_until_complete(fetch_once())
                    client_ids.append(client_id)
                    responses.append(body)
                    loop.run_until_complete(client.close_loop_resources())
                finally:
                    asyncio.set_event_loop(None)
                    loop.close()
        finally:
            server.shutdown()
            server.server_close()

        assert responses == ["ok", "ok"]
        assert client_ids[0] != client_ids[1]
```

- [ ] **Step 2: Run test — expect PASS**

Run: `cd /Users/pesnya/Documents/streamdeck && uv run pytest tests/platforms/test_kick.py::TestLoopLocalHttpClient -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd /Users/pesnya/Documents/streamdeck
git add tests/platforms/test_kick.py
git commit -m "test(kick): add per-event-loop client isolation test"
```

---

### Task 5: stream_resolver.py — platform support for Kick

**Files:**
- Modify: `core/stream_resolver.py`
- Modify: `tests/test_stream_resolver.py`

- [ ] **Step 1: Write test for Kick stream URL resolution**

Read current `tests/test_stream_resolver.py` first to understand existing patterns, then add:

```python
# Add to tests/test_stream_resolver.py

class TestResolveKickHlsUrl:
    def test_builds_kick_url(self, monkeypatch):
        """resolve_hls_url with platform='kick' should pass kick.com URL to streamlink."""
        calls = []

        def mock_which(path):
            return "/usr/bin/streamlink"

        def mock_run(cmd, capture_output=False, timeout=None):
            calls.append(cmd)
            result = type("R", (), {"returncode": 0, "stdout": b"https://hls.kick.com/test.m3u8\n", "stderr": b""})
            return result

        monkeypatch.setattr("core.stream_resolver.shutil.which", mock_which)
        monkeypatch.setattr("core.stream_resolver.subprocess.run", mock_run)

        url, err = resolve_hls_url("xqc", "best", platform="kick")
        assert url == "https://hls.kick.com/test.m3u8"
        assert err == ""
        assert "https://kick.com/xqc" in calls[0]
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `cd /Users/pesnya/Documents/streamdeck && uv run pytest tests/test_stream_resolver.py::TestResolveKickHlsUrl -v`
Expected: FAIL — `resolve_hls_url() got an unexpected keyword argument 'platform'`

- [ ] **Step 3: Add platform parameter to resolve_hls_url**

Modify `core/stream_resolver.py`:

Change the `resolve_hls_url` function signature and URL construction:

```python
def resolve_hls_url(
    channel: str,
    quality: str,
    streamlink_path: str = "streamlink",
    platform: str = "twitch",
) -> tuple[str | None, str]:
    """Resolve HLS URL for a channel on a given platform.

    Returns (hls_url, error_message). Falls back to 'best' quality
    if the requested quality is unavailable.
    """
    resolved_sl = shutil.which(streamlink_path)
    if resolved_sl is None:
        return (
            None,
            "streamlink not found.\n\nInstall it with:\n  brew install streamlink",
        )

    if platform == "kick":
        stream_url = f"https://kick.com/{channel}"
    else:
        stream_url = f"https://twitch.tv/{channel}"

    hls_url, err = _run_streamlink(resolved_sl, stream_url, quality)

    if not hls_url and quality != "best":
        hls_url, err = _run_streamlink(resolved_sl, stream_url, "best")

    return hls_url, err
```

- [ ] **Step 4: Run ALL stream_resolver tests — expect PASS**

Run: `cd /Users/pesnya/Documents/streamdeck && uv run pytest tests/test_stream_resolver.py -v`
Expected: All tests PASS (existing Twitch tests use default `platform="twitch"`)

- [ ] **Step 5: Commit**

```bash
cd /Users/pesnya/Documents/streamdeck
git add core/stream_resolver.py tests/test_stream_resolver.py
git commit -m "feat(resolver): add platform param for Kick stream URL resolution"
```

---

### Task 6: ui/api.py — KickClient integration (constructor, close, config)

**Files:**
- Modify: `ui/api.py`

- [ ] **Step 1: Add KickClient to imports and constructor**

In `ui/api.py`, add the import:

```python
from core.platforms.kick import KickClient
```

In `__init__`, after `self._twitch = TwitchClient()`:

```python
        self._kick = KickClient()
        self._platforms: dict[str, Any] = {"twitch": self._twitch, "kick": self._kick}
```

- [ ] **Step 2: Add _get_kick_config helper**

After `_get_twitch_config`:

```python
    def _get_kick_config(self) -> dict[str, Any]:
        """Get Kick platform config section."""
        return get_platform_config(self._config, "kick")
```

- [ ] **Step 3: Update _close_thread_loop to close both clients**

Replace the existing `_close_thread_loop`:

```python
    def _close_thread_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        try:
            asyncio.set_event_loop(loop)
            for client in self._platforms.values():
                loop.run_until_complete(client.close_loop_resources())
        finally:
            asyncio.set_event_loop(None)
            loop.close()
```

- [ ] **Step 4: Update close() to close Kick client too**

Replace the `close()` method:

```python
    def close(self) -> None:
        self._shutdown.set()
        self.stop_polling()
        self._cancel_launch_timer()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            for client in self._platforms.values():
                loop.run_until_complete(client.close())
        finally:
            asyncio.set_event_loop(None)
            loop.close()
```

- [ ] **Step 5: Update get_config to include Kick status**

In `get_config`, after the existing `masked` dict construction, add Kick info:

```python
        kick_conf = get_platform_config(self._config, "kick")
        masked["kick_has_credentials"] = bool(
            kick_conf.get("client_id") and kick_conf.get("client_secret")
        )
        if kick_conf.get("user_login"):
            masked["kick_user"] = {
                "login": kick_conf["user_login"],
                "display_name": kick_conf.get("user_display_name", ""),
            }
```

- [ ] **Step 6: Update get_full_config_for_settings to include Kick fields**

In `get_full_config_for_settings`, add Kick fields to the return dict:

```python
        kick_conf = get_platform_config(self._config, "kick")
        # ... existing return dict becomes:
        return {
            "client_id": twitch_conf.get("client_id", ""),
            "client_secret": twitch_conf.get("client_secret", ""),
            "quality": settings.get("quality", "best"),
            "refresh_interval": settings.get("refresh_interval", 60),
            "streamlink_path": settings.get("streamlink_path", "streamlink"),
            "iina_path": settings.get("iina_path", ""),
            "kick_client_id": kick_conf.get("client_id", ""),
            "kick_client_secret": kick_conf.get("client_secret", ""),
        }
```

- [ ] **Step 7: Update save_settings to handle Kick fields**

In `save_settings`, after the existing Twitch field handling, add:

```python
        kick_conf = get_platform_config(self._config, "kick")
        if "kick_client_id" in parsed:
            kick_conf["client_id"] = parsed["kick_client_id"].strip()
        if "kick_client_secret" in parsed:
            kick_conf["client_secret"] = parsed["kick_client_secret"].strip()
        self._config["platforms"]["kick"] = kick_conf
```

- [ ] **Step 8: Run existing tests to ensure nothing broke**

Run: `cd /Users/pesnya/Documents/streamdeck && uv run pytest tests/ -v`
Expected: All existing tests PASS

- [ ] **Step 9: Commit**

```bash
cd /Users/pesnya/Documents/streamdeck
git add ui/api.py
git commit -m "feat(api): integrate KickClient into bridge (constructor, config, close)"
```

---

### Task 7: ui/api.py — Kick OAuth login/logout and test_connection

**Files:**
- Modify: `ui/api.py`

- [ ] **Step 1: Add kick_login method**

After the existing `import_follows` method, add:

```python
    # ── Kick Auth ──────────────────────────────────────────────

    def kick_login(self) -> None:
        kick_conf = self._get_kick_config()
        if not kick_conf.get("client_id") or not kick_conf.get("client_secret"):
            self._eval_js(
                'window.onKickLoginError("Set Kick API credentials in Settings first")'
            )
            return
        auth_url = self._kick.get_auth_url()
        self._eval_js(
            "window.onStatusUpdate({text: 'Waiting for Kick login...', type: 'warn'})"
        )

        def do_login() -> None:
            webbrowser.open(auth_url)
            code = wait_for_oauth_code()
            if self._shutdown.is_set():
                return
            if code is None:
                self._eval_js('window.onKickLoginError("Login timed out")')
                return
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                token_data = loop.run_until_complete(self._kick.exchange_code(code))
                kick_conf = self._config["platforms"]["kick"]
                kick_conf["access_token"] = token_data["access_token"]
                kick_conf["refresh_token"] = token_data.get("refresh_token", "")
                kick_conf["token_expires_at"] = int(time.time()) + token_data.get(
                    "expires_in", 3600
                )
                save_config(self._config)

                user = loop.run_until_complete(self._kick.get_current_user())
                kick_conf["user_id"] = str(user.get("id", ""))
                kick_conf["user_login"] = user.get("username", user.get("slug", ""))
                kick_conf["user_display_name"] = user.get(
                    "username", user.get("slug", "")
                )
                save_config(self._config)

                result = json.dumps(
                    {
                        "platform": "kick",
                        "display_name": kick_conf["user_display_name"],
                        "login": kick_conf["user_login"],
                    }
                )
                self._eval_js(f"window.onKickLoginComplete({result})")
                self.refresh()
            except Exception as e:
                msg = str(e)[:80] if str(e) else "Kick login failed"
                safe_msg = json.dumps(msg)
                self._eval_js(f"window.onKickLoginError({safe_msg})")
            finally:
                self._close_thread_loop(loop)

        self._run_in_thread(do_login)

    def kick_logout(self) -> None:
        kick_conf = self._config["platforms"]["kick"]
        kick_conf["access_token"] = ""
        kick_conf["refresh_token"] = ""
        kick_conf["token_expires_at"] = 0
        kick_conf["pkce_verifier"] = ""
        kick_conf["user_id"] = ""
        kick_conf["user_login"] = ""
        kick_conf["user_display_name"] = ""
        save_config(self._config)
        self._eval_js("window.onKickLogout()")

    def kick_test_connection(self, client_id: str, client_secret: str) -> None:
        def do_test() -> None:
            try:
                resp = httpx.post(
                    "https://id.kick.com/oauth/token",
                    data={
                        "client_id": client_id.strip(),
                        "client_secret": client_secret.strip(),
                        "grant_type": "client_credentials",
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    result = json.dumps({"success": True, "message": "Kick connected"})
                else:
                    result = json.dumps(
                        {"success": False, "message": "Invalid Kick credentials"}
                    )
            except httpx.ConnectError:
                result = json.dumps(
                    {"success": False, "message": "No internet connection"}
                )
            except Exception as exc:
                msg = str(exc)[:60]
                result = json.dumps({"success": False, "message": msg})
            self._eval_js(f"window.onKickTestResult({result})")

        self._run_in_thread(do_test)
```

- [ ] **Step 2: Run existing tests**

Run: `cd /Users/pesnya/Documents/streamdeck && uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
cd /Users/pesnya/Documents/streamdeck
git add ui/api.py
git commit -m "feat(api): add Kick OAuth login/logout and test_connection"
```

---

### Task 8: ui/api.py — platform-aware channels (add, remove, search)

**Files:**
- Modify: `ui/api.py`

- [ ] **Step 1: Update add_channel with platform parameter**

Replace `add_channel`:

```python
    def add_channel(self, username: str, platform: str = "twitch") -> None:
        clean = self._sanitize_username(username)
        if not clean:
            return
        favorites = self._config.get("favorites", [])
        if any(f.get("login") == clean and f.get("platform") == platform for f in favorites):
            return
        favorites.append({"platform": platform, "login": clean, "display_name": clean})
        self._config["favorites"] = favorites
        save_config(self._config)
        self.refresh()
```

- [ ] **Step 2: Update remove_channel with platform parameter**

Replace `remove_channel`:

```python
    def remove_channel(self, channel: str, platform: str = "twitch") -> None:
        favorites = self._config.get("favorites", [])
        self._config["favorites"] = [
            f for f in favorites
            if not (f.get("login") == channel.lower() and f.get("platform") == platform)
        ]
        save_config(self._config)
        self.refresh()
```

- [ ] **Step 3: Update search_channels with platform parameter**

Replace `search_channels`:

```python
    def search_channels(self, query: str, platform: str = "twitch") -> None:
        if platform == "kick":
            kick_conf = self._get_kick_config()
            if not kick_conf.get("client_id") or not kick_conf.get("client_secret"):
                self._eval_js("window.onSearchResults([])")
                return

            def do_search() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    results = loop.run_until_complete(self._kick.search_channels(query))
                    items = []
                    for r in results:
                        slug = r.get("slug", r.get("username", "")).lower()
                        items.append(
                            {
                                "login": slug,
                                "display_name": r.get("username", slug),
                                "is_live": r.get("is_live", False),
                                "game_name": r.get("category", {}).get("name", "") if isinstance(r.get("category"), dict) else "",
                                "platform": "kick",
                            }
                        )
                    self._eval_js(f"window.onSearchResults({json.dumps(items)})")
                except Exception:
                    self._eval_js("window.onSearchResults([])")
                finally:
                    self._close_thread_loop(loop)

            self._run_in_thread(do_search)
            return

        # Twitch search (existing logic)
        twitch_conf = self._get_twitch_config()
        if not twitch_conf.get("client_id") or not twitch_conf.get("client_secret"):
            self._eval_js("window.onSearchResults([])")
            return

        def do_search() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(self._twitch.search_channels(query))
                items = []
                for r in results:
                    items.append(
                        {
                            "login": r.get(
                                "broadcaster_login", r.get("display_name", "")
                            ).lower(),
                            "display_name": r.get("display_name", ""),
                            "is_live": r.get("is_live", False),
                            "game_name": r.get("game_name", ""),
                            "platform": "twitch",
                        }
                    )
                self._eval_js(f"window.onSearchResults({json.dumps(items)})")
            except Exception:
                self._eval_js("window.onSearchResults([])")
            finally:
                self._close_thread_loop(loop)

        self._run_in_thread(do_search)
```

- [ ] **Step 4: Update reorder_channels for platform awareness**

Replace `reorder_channels`:

```python
    def reorder_channels(self, new_order_json: str, platform: str = "twitch") -> None:
        new_order = json.loads(new_order_json) if isinstance(new_order_json, str) else new_order_json
        old_favs = {
            f["login"]: f for f in self._config.get("favorites", [])
            if f.get("platform") == platform
        }
        reordered = []
        for login in new_order:
            if login in old_favs:
                reordered.append(old_favs[login])
            else:
                reordered.append({"platform": platform, "login": login, "display_name": login})
        other = [f for f in self._config.get("favorites", []) if f.get("platform") != platform]
        self._config["favorites"] = reordered + other
        save_config(self._config)
```

- [ ] **Step 5: Run existing tests**

Run: `cd /Users/pesnya/Documents/streamdeck && uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/pesnya/Documents/streamdeck
git add ui/api.py
git commit -m "feat(api): platform-aware add/remove/search/reorder channels"
```

---

### Task 9: ui/api.py — Kick data fetch in refresh cycle

**Files:**
- Modify: `ui/api.py`

- [ ] **Step 1: Update refresh() to fetch Kick favorites too**

Replace the `refresh()` method:

```python
    def refresh(self) -> None:
        self._config = load_config()
        twitch_favorites = get_favorite_logins(self._config, "twitch")
        kick_favorites = get_favorite_logins(self._config, "kick")
        twitch_conf = get_platform_config(self._config, "twitch")
        kick_conf = get_platform_config(self._config, "kick")

        has_any_favorites = bool(twitch_favorites or kick_favorites)
        has_twitch_creds = bool(
            twitch_conf.get("client_id") and twitch_conf.get("client_secret")
        )
        has_kick_creds = bool(
            kick_conf.get("client_id") and kick_conf.get("client_secret")
        )

        if not has_any_favorites:
            data = json.dumps(
                {
                    "streams": [],
                    "favorites": [],
                    "live_set": [],
                    "updated_time": "",
                    "total_viewers": 0,
                    "has_credentials": has_twitch_creds or has_kick_creds,
                }
            )
            self._eval_js(f"window.onStreamsUpdate({data})")
            return

        if not has_twitch_creds and not has_kick_creds:
            all_favs = twitch_favorites + kick_favorites
            data = json.dumps(
                {
                    "streams": [],
                    "favorites": all_favs,
                    "live_set": [],
                    "updated_time": "",
                    "total_viewers": 0,
                    "has_credentials": False,
                }
            )
            self._eval_js(f"window.onStreamsUpdate({data})")
            return

        if self._fetching:
            return
        self._fetching = True
        self._eval_js("window.onStatusUpdate({text: 'Refreshing...', type: 'info'})")
        self._run_in_thread(
            lambda tf=list(twitch_favorites), kf=list(kick_favorites): self._fetch_data(tf, kf)
        )
```

- [ ] **Step 2: Update _fetch_data to accept kick_favorites**

Replace `_fetch_data`:

```python
    def _fetch_data(self, twitch_favorites: list[str], kick_favorites: list[str] | None = None) -> None:
        if kick_favorites is None:
            kick_favorites = []
        retry_delays = [5, 15, 30]
        max_attempts = len(retry_delays) + 1

        try:
            for attempt in range(1, max_attempts + 1):
                if self._shutdown.is_set():
                    return
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    twitch_streams, twitch_users, kick_streams = loop.run_until_complete(
                        self._async_fetch(twitch_favorites, kick_favorites)
                    )
                    self._on_data_fetched(
                        twitch_favorites, kick_favorites,
                        twitch_streams, twitch_users, kick_streams,
                    )
                    return
                except httpx.ConnectError:
                    if attempt < max_attempts:
                        delay = retry_delays[attempt - 1]
                        att = attempt + 1
                        self._eval_js(
                            f"window.onStatusUpdate({{text: 'Reconnecting... (attempt {att}/{max_attempts})', type: 'warn'}})"
                        )
                        time.sleep(delay)
                    else:
                        self._eval_js(
                            "window.onStatusUpdate({text: 'No internet connection', type: 'error'})"
                        )
                except httpx.HTTPStatusError as e:
                    status_code = e.response.status_code
                    if status_code in (401, 403):
                        self._eval_js(
                            "window.onStatusUpdate({text: 'Check your API credentials in Settings', type: 'error'})"
                        )
                    else:
                        self._eval_js(
                            f"window.onStatusUpdate({{text: 'API error: {status_code}', type: 'error'}})"
                        )
                    return
                except ValueError:
                    self._eval_js(
                        "window.onStatusUpdate({text: 'Set API credentials in Settings', type: 'error'})"
                    )
                    return
                except Exception as e:
                    traceback.print_exc()
                    msg = str(e)[:80] if str(e) else "Unknown error"
                    safe_msg = json.dumps(msg)
                    self._eval_js(
                        f"window.onStatusUpdate({{text: 'Error: ' + String({safe_msg}), type: 'error'}})"
                    )
                    return
                finally:
                    self._close_thread_loop(loop)
        finally:
            self._fetching = False
```

- [ ] **Step 3: Update _async_fetch to fetch from both platforms**

Replace `_async_fetch`:

```python
    async def _async_fetch(
        self,
        twitch_favorites: list[str],
        kick_favorites: list[str],
    ) -> tuple[list[dict], list[dict], list[dict]]:
        twitch_conf = get_platform_config(self._config, "twitch")
        kick_conf = get_platform_config(self._config, "kick")
        has_twitch = bool(twitch_conf.get("client_id") and twitch_conf.get("client_secret") and twitch_favorites)
        has_kick = bool(kick_conf.get("client_id") and kick_conf.get("client_secret") and kick_favorites)

        twitch_streams: list[dict] = []
        twitch_users: list[dict] = []
        kick_streams: list[dict] = []

        if has_twitch:
            await self._twitch._ensure_token()
            streams, users = await asyncio.gather(
                self._twitch.get_live_streams(twitch_favorites),
                self._twitch.get_users(twitch_favorites),
            )
            twitch_streams = streams
            twitch_users = users
            game_ids = [s.get("game_id", "") for s in streams if s.get("game_id")]
            if game_ids:
                games = await self._twitch.get_games(game_ids)
                self._games.update(games)

        if has_kick:
            try:
                kick_streams = await self._kick.get_live_streams(kick_favorites)
            except Exception:
                logger.warning("Kick fetch failed", exc_info=True)

        return twitch_streams, twitch_users, kick_streams
```

- [ ] **Step 4: Update _on_data_fetched to merge both platforms' streams**

Replace `_on_data_fetched`:

```python
    def _on_data_fetched(
        self,
        twitch_favorites: list[str],
        kick_favorites: list[str],
        twitch_streams: list[dict],
        twitch_users: list[dict],
        kick_streams: list[dict],
    ) -> None:
        self._live_streams = twitch_streams + kick_streams
        self._last_successful_fetch = time.time()

        # Twitch live logins
        twitch_live = {s["user_login"].lower() for s in twitch_streams}
        # Kick live slugs
        kick_live = set()
        for s in kick_streams:
            slug = s.get("slug", s.get("channel", {}).get("slug", "")).lower()
            if slug:
                kick_live.add(slug)
        all_live = twitch_live | kick_live

        # Notifications
        if self._first_fetch_done:
            newly_live = all_live - self._prev_live_logins
            if newly_live:
                tw_map = {s["user_login"].lower(): s for s in twitch_streams}
                k_map = {}
                for s in kick_streams:
                    slug = s.get("slug", s.get("channel", {}).get("slug", "")).lower()
                    if slug:
                        k_map[slug] = s
                for login in newly_live:
                    s = tw_map.get(login) or k_map.get(login)
                    if s:
                        name = s.get("user_name", s.get("slug", login))
                        title = s.get("title", s.get("session_title", ""))
                        game = s.get("game_name", "")
                        if not game and isinstance(s.get("category"), dict):
                            game = s["category"].get("name", "")
                        self._send_notification(name, title, game)
        self._prev_live_logins = set(all_live)
        self._first_fetch_done = True

        # Store user avatar URLs for lazy loading (Twitch)
        for u in twitch_users:
            login = u["login"].lower()
            url = u.get("profile_image_url", "")
            if url:
                self._user_avatars[login] = url

        # Build stream items for JS
        stream_items = []

        # Twitch streams
        for s in twitch_streams:
            login = s["user_login"].lower()
            game_id = s.get("game_id", "")
            game_name = s.get("game_name", "") or self._games.get(game_id, "")
            thumb_url = (
                s.get("thumbnail_url", "")
                .replace("{width}", "880")
                .replace("{height}", "496")
            )
            stream_items.append(
                {
                    "login": login,
                    "display_name": s.get("user_name", login),
                    "title": s.get("title", ""),
                    "game": game_name,
                    "viewers": s.get("viewer_count", 0),
                    "started_at": s.get("started_at", ""),
                    "thumbnail_url": thumb_url,
                    "viewer_trend": None,
                    "platform": "twitch",
                }
            )

        # Kick streams
        for s in kick_streams:
            slug = s.get("slug", s.get("channel", {}).get("slug", "")).lower()
            channel_data = s.get("channel", {}) if isinstance(s.get("channel"), dict) else {}
            category = s.get("category", {}) if isinstance(s.get("category"), dict) else {}
            thumb = s.get("thumbnail", channel_data.get("thumbnail", ""))
            stream_items.append(
                {
                    "login": slug,
                    "display_name": s.get("slug", slug),
                    "title": s.get("session_title", s.get("title", "")),
                    "game": category.get("name", ""),
                    "viewers": s.get("viewer_count", s.get("viewers", 0)),
                    "started_at": s.get("created_at", s.get("started_at", "")),
                    "thumbnail_url": thumb,
                    "viewer_trend": None,
                    "platform": "kick",
                }
            )

        all_favorites = twitch_favorites + kick_favorites
        now = datetime.now().strftime("%H:%M:%S")
        total = sum(item["viewers"] for item in stream_items)

        data = json.dumps(
            {
                "streams": stream_items,
                "favorites": all_favorites,
                "live_set": list(all_live),
                "updated_time": now,
                "total_viewers": total,
                "total_viewers_formatted": format_viewers(total) if total else "0",
                "has_credentials": True,
                "user_avatars": self._user_avatars,
            }
        )
        self._eval_js(f"window.onStreamsUpdate({data})")
```

- [ ] **Step 5: Update watch() to handle Kick streams**

In `watch()`, update the stream URL to handle Kick channels. Change the `do_resolve` inner function to detect platform:

```python
    def watch(self, channel: str, quality: str) -> None:
        if not channel:
            self._eval_js(
                "window.onLaunchResult({success: false, message: 'Select a channel first', channel: ''})"
            )
            return

        # Determine platform from live streams
        platform = "twitch"
        live_logins = set()
        for s in self._live_streams:
            login = s.get("user_login", s.get("slug", s.get("channel", {}).get("slug", "") if isinstance(s.get("channel"), dict) else "")).lower()
            live_logins.add(login)
            if login == channel.lower():
                # Kick streams don't have "user_login"
                if "user_login" not in s:
                    platform = "kick"

        if channel.lower() not in live_logins:
            safe_ch = json.dumps(channel)
            self._eval_js(
                f"window.onLaunchResult({{success: false, message: {safe_ch} + ' is offline', channel: {safe_ch}}})"
            )
            return

        self._config["settings"]["quality"] = quality
        save_config(self._config)
        safe_ch = json.dumps(channel)
        self._eval_js(
            f"window.onStatusUpdate({{text: 'Loading ' + {safe_ch} + '...', type: 'warn'}})"
        )

        self._launch_channel = channel
        self._launch_elapsed = 0
        self._start_launch_timer()

        title = ""
        for s in self._live_streams:
            login = s.get("user_login", s.get("slug", s.get("channel", {}).get("slug", "") if isinstance(s.get("channel"), dict) else "")).lower()
            if login == channel.lower():
                title = s.get("title", s.get("session_title", ""))
                break

        stream_platform = platform

        def do_resolve() -> None:
            settings = get_settings(self._config)
            hls_url, err = resolve_hls_url(
                channel,
                quality,
                settings.get("streamlink_path", "streamlink"),
                platform=stream_platform,
            )
            self._cancel_launch_timer()
            self._launch_channel = None

            if not hls_url:
                r = json.dumps(
                    {
                        "success": False,
                        "message": f"streamlink error: {err}"
                        if err
                        else "Could not resolve stream URL",
                        "channel": channel,
                    }
                )
                self._eval_js(f"window.onLaunchResult({r})")
                return

            self._watching_channel = channel
            stream_data = json.dumps(
                {
                    "url": hls_url,
                    "channel": channel,
                    "title": title,
                    "platform": stream_platform,
                }
            )
            self._eval_js(f"window.onStreamReady({stream_data})")
            r = json.dumps(
                {
                    "success": True,
                    "message": f"Playing {channel}",
                    "channel": channel,
                }
            )
            self._eval_js(f"window.onLaunchResult({r})")

        self._run_in_thread(do_resolve)
```

- [ ] **Step 6: Update watch_external() similarly**

In `watch_external()`, detect platform the same way and pass to `launch_stream`:

After the `live_logins` check, detect platform:

```python
    def watch_external(self, channel: str, quality: str) -> None:
        if not channel:
            return
        platform = "twitch"
        live_logins = set()
        for s in self._live_streams:
            login = s.get("user_login", s.get("slug", s.get("channel", {}).get("slug", "") if isinstance(s.get("channel"), dict) else "")).lower()
            live_logins.add(login)
            if login == channel.lower() and "user_login" not in s:
                platform = "kick"
        if channel.lower() not in live_logins:
            return

        stream_platform = platform

        def do_launch() -> None:
            settings = get_settings(self._config)
            if stream_platform == "kick":
                # For Kick, resolve HLS URL and pass to IINA
                hls_url, err = resolve_hls_url(
                    channel,
                    quality,
                    settings.get("streamlink_path", "streamlink"),
                    platform="kick",
                )
                if not hls_url:
                    r = json.dumps({"success": False, "message": err or "Could not resolve", "channel": channel})
                    self._eval_js(f"window.onLaunchResult({r})")
                    return
                result = launch_stream(
                    channel, quality,
                    settings.get("streamlink_path", "streamlink"),
                    settings.get("iina_path", "/Applications/IINA.app/Contents/MacOS/iina-cli"),
                )
            else:
                result = launch_stream(
                    channel, quality,
                    settings.get("streamlink_path", "streamlink"),
                    settings.get("iina_path", "/Applications/IINA.app/Contents/MacOS/iina-cli"),
                )
            r = json.dumps(
                {"success": result.success, "message": result.message, "channel": channel}
            )
            self._eval_js(f"window.onLaunchResult({r})")

        self._run_in_thread(do_launch)
```

- [ ] **Step 7: Update open_browser to handle Kick**

Replace `open_browser`:

```python
    def open_browser(self, channel: str, platform: str = "twitch") -> None:
        if channel:
            if platform == "kick":
                webbrowser.open(f"https://kick.com/{channel}")
            else:
                webbrowser.open(f"https://twitch.tv/{channel}")
```

- [ ] **Step 8: Run all tests**

Run: `cd /Users/pesnya/Documents/streamdeck && uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
cd /Users/pesnya/Documents/streamdeck
git add ui/api.py
git commit -m "feat(api): Kick data fetch in refresh cycle, platform-aware watch/search/browser"
```

---

### Task 10: ui/index.html — Platform filter tabs in sidebar

**Files:**
- Modify: `ui/index.html`

- [ ] **Step 1: Add CSS for platform tabs**

After the `#profile-area` CSS block (around line 63), add:

```css
/* ── Platform filter tabs ──────────────────────────────── */
#platform-tabs {
  display: flex; gap: 0;
  padding: 0 12px;
  border-bottom: 1px solid var(--bg-border);
}
.platform-tab {
  flex: 1; padding: 8px 0;
  background: transparent; border: none;
  color: var(--text-muted); font-size: 11px; font-weight: 700;
  letter-spacing: 0.5px; text-transform: uppercase;
  cursor: pointer; font-family: inherit;
  border-bottom: 2px solid transparent;
  transition: all 0.15s ease;
}
.platform-tab:hover { color: var(--text-secondary); }
.platform-tab.active {
  color: var(--accent); border-bottom-color: var(--accent);
}
```

- [ ] **Step 2: Add platform tabs HTML**

After `#profile-area` div (around line 850 in the HTML body), add:

```html
<div id="platform-tabs">
  <button class="platform-tab active" data-platform="all">All</button>
  <button class="platform-tab" data-platform="twitch">Twitch</button>
  <button class="platform-tab" data-platform="kick">Kick</button>
</div>
```

- [ ] **Step 3: Add JS state and event handlers for platform filter**

In the `state` object, add:

```javascript
  activePlatformFilter: 'all',
```

In the `DOMContentLoaded` event handler, add:

```javascript
  // Platform filter tabs
  document.querySelectorAll('.platform-tab').forEach(function(tab) {
    tab.addEventListener('click', function() {
      document.querySelectorAll('.platform-tab').forEach(function(t) { t.classList.remove('active'); });
      tab.classList.add('active');
      state.activePlatformFilter = tab.dataset.platform;
      renderGrid();
      renderSidebar();
    });
  });
```

- [ ] **Step 4: Update getFilteredSortedStreams to filter by platform**

Add platform filter at the start of `getFilteredSortedStreams`:

```javascript
function getFilteredSortedStreams() {
  var streams = state.streams.slice();
  // Platform filter
  if (state.activePlatformFilter !== 'all') {
    streams = streams.filter(function(s) {
      return s.platform === state.activePlatformFilter;
    });
  }
  if (state.filterText) {
    // ... rest unchanged
```

- [ ] **Step 5: Update search_channels call to pass platform**

In the search input handler, update the API call to pass the active platform:

```javascript
  state.searchDebounce = setTimeout(function() {
    if (api) {
      var searchPlatform = state.activePlatformFilter === 'all' ? 'twitch' : state.activePlatformFilter;
      api.search_channels(query, searchPlatform);
    }
  }, 400);
```

- [ ] **Step 6: Update addChannel to pass platform**

Update `addChannel`:

```javascript
function addChannel() {
  var input = document.getElementById('search-input');
  var val = input.value.trim();
  if (val && api) {
    var platform = state.activePlatformFilter === 'all' ? 'twitch' : state.activePlatformFilter;
    api.add_channel(val, platform);
    input.value = '';
    document.getElementById('search-dropdown').style.display = 'none';
  }
}
```

Update `addChannelDirect` to accept platform:

```javascript
function addChannelDirect(login, platform) {
  if (api) api.add_channel(login, platform || 'twitch');
}
```

Update search result click handlers (in `onSearchResults`) to pass platform:

```javascript
    addBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      addChannelDirect(r.login, r.platform || 'twitch');
    });
    // ...
    row.addEventListener('click', function() {
      addChannelDirect(r.login, r.platform || 'twitch');
      dd.style.display = 'none';
      document.getElementById('search-input').value = '';
    });
```

- [ ] **Step 7: Commit**

```bash
cd /Users/pesnya/Documents/streamdeck
git add ui/index.html
git commit -m "feat(ui): add platform filter tabs (All/Twitch/Kick) with filtering"
```

---

### Task 11: ui/index.html — Platform badge on stream cards

**Files:**
- Modify: `ui/index.html`

- [ ] **Step 1: Add CSS for platform badge**

```css
/* ── Platform badge ────────────────────────────────────── */
.platform-badge {
  position: absolute; top: 8px; right: 8px;
  width: 22px; height: 22px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 800;
  color: white; text-transform: uppercase;
  backdrop-filter: blur(4px);
}
.platform-badge.twitch { background: rgba(145, 70, 255, 0.85); }
.platform-badge.kick { background: rgba(83, 252, 24, 0.85); color: #000; }
```

- [ ] **Step 2: Add platform badge to createStreamCard**

In `createStreamCard`, after the `liveBadge` element creation and before `watchBadge`, add:

```javascript
  var platformBadge = document.createElement('span');
  platformBadge.className = 'platform-badge ' + (s.platform || 'twitch');
  platformBadge.textContent = s.platform === 'kick' ? 'K' : 'T';
  thumb.appendChild(platformBadge);
```

- [ ] **Step 3: Store platform on card dataset**

In `createStreamCard`, add after `card.dataset.started = s.started_at;`:

```javascript
  card.dataset.platform = s.platform || 'twitch';
```

- [ ] **Step 4: Commit**

```bash
cd /Users/pesnya/Documents/streamdeck
git add ui/index.html
git commit -m "feat(ui): add platform badge (T/K) on stream cards"
```

---

### Task 12: ui/index.html — Kick settings tab

**Files:**
- Modify: `ui/index.html`

- [ ] **Step 1: Add CSS for settings tabs**

```css
/* ── Settings tabs ─────────────────────────────────────── */
.settings-tabs {
  display: flex; gap: 0; margin-bottom: 16px;
  border-bottom: 1px solid var(--bg-border);
}
.settings-tab {
  flex: 1; padding: 8px 0;
  background: transparent; border: none;
  color: var(--text-muted); font-size: 12px; font-weight: 600;
  cursor: pointer; font-family: inherit;
  border-bottom: 2px solid transparent;
  transition: all 0.15s ease;
}
.settings-tab:hover { color: var(--text-secondary); }
.settings-tab.active {
  color: var(--accent); border-bottom-color: var(--accent);
}
.settings-panel { display: none; }
.settings-panel.active { display: block; }
```

- [ ] **Step 2: Restructure settings modal HTML with tabs**

Replace the settings modal inner content (between `<h2>` and `<div id="settings-feedback">`) with:

```html
    <h2>&#9881; Settings</h2>

    <div class="settings-tabs">
      <button class="settings-tab active" data-panel="general">General</button>
      <button class="settings-tab" data-panel="twitch">Twitch</button>
      <button class="settings-tab" data-panel="kick">Kick</button>
    </div>

    <!-- General panel -->
    <div class="settings-panel active" id="panel-general">
      <div class="setting-group">
        <label>Streamlink Path</label>
        <input id="s-streamlink" type="text" autocomplete="off">
      </div>
      <div class="setting-group">
        <label>IINA Path</label>
        <input id="s-iina" type="text" autocomplete="off">
      </div>
      <div class="setting-group">
        <label>Refresh Interval</label>
        <select id="s-interval">
          <option value="30">30 seconds</option>
          <option value="60">60 seconds</option>
          <option value="120">120 seconds</option>
        </select>
      </div>
    </div>

    <!-- Twitch panel -->
    <div class="settings-panel" id="panel-twitch">
      <div class="setting-group">
        <label>Client ID</label>
        <input id="s-client-id" type="text" autocomplete="off">
      </div>
      <div class="setting-group">
        <label>Client Secret</label>
        <div class="secret-row">
          <input id="s-client-secret" type="password" autocomplete="off">
          <button class="eye-btn" id="eye-toggle-btn">&#128065;</button>
        </div>
      </div>
      <div class="oauth-note">
        Redirect URL: http://localhost:3457/callback
      </div>
      <div class="settings-btns" style="margin-top:10px;">
        <button id="test-btn">Test Connection</button>
      </div>
    </div>

    <!-- Kick panel -->
    <div class="settings-panel" id="panel-kick">
      <div class="setting-group">
        <label>Client ID</label>
        <input id="s-kick-client-id" type="text" autocomplete="off">
      </div>
      <div class="setting-group">
        <label>Client Secret</label>
        <div class="secret-row">
          <input id="s-kick-client-secret" type="password" autocomplete="off">
          <button class="eye-btn" id="kick-eye-toggle-btn">&#128065;</button>
        </div>
      </div>
      <div id="kick-login-area">
        <button id="kick-login-btn" class="onboarding-btn" style="width:100%;margin-top:8px;">Login with Kick</button>
      </div>
      <div id="kick-user-area" style="display:none;margin-top:8px;">
        <span id="kick-user-display" style="font-size:13px;color:var(--text-primary);font-weight:600;"></span>
        <a id="kick-logout-link" style="font-size:11px;color:var(--text-muted);cursor:pointer;margin-left:8px;">Logout</a>
      </div>
      <div class="oauth-note" style="margin-top:8px;">
        Redirect URL: http://localhost:3457/callback<br>
        Register at <a href="#" style="color:var(--accent);">developers.kick.com</a>
      </div>
      <div class="settings-btns" style="margin-top:10px;">
        <button id="kick-test-btn">Test Connection</button>
      </div>
    </div>

    <div id="settings-feedback"></div>

    <div class="settings-btns">
      <button id="save-btn">Save</button>
    </div>
```

- [ ] **Step 3: Add JS for settings tab switching**

In the `DOMContentLoaded` handler, add:

```javascript
  // Settings tabs
  document.querySelectorAll('.settings-tab').forEach(function(tab) {
    tab.addEventListener('click', function() {
      document.querySelectorAll('.settings-tab').forEach(function(t) { t.classList.remove('active'); });
      document.querySelectorAll('.settings-panel').forEach(function(p) { p.classList.remove('active'); });
      tab.classList.add('active');
      document.getElementById('panel-' + tab.dataset.panel).classList.add('active');
    });
  });

  // Kick settings handlers
  document.getElementById('kick-eye-toggle-btn').addEventListener('click', function() {
    var input = document.getElementById('s-kick-client-secret');
    input.type = input.type === 'password' ? 'text' : 'password';
  });
  document.getElementById('kick-login-btn').addEventListener('click', function() {
    if (api) api.kick_login();
  });
  document.getElementById('kick-logout-link').addEventListener('click', function() {
    if (api) api.kick_logout();
  });
  document.getElementById('kick-test-btn').addEventListener('click', function() {
    var cid = document.getElementById('s-kick-client-id').value.trim();
    var cs = document.getElementById('s-kick-client-secret').value.trim();
    if (!cid || !cs) {
      var fb = document.getElementById('settings-feedback');
      fb.textContent = 'Kick Client ID and Secret are required';
      fb.style.color = 'var(--error-red)';
      return;
    }
    document.getElementById('kick-test-btn').disabled = true;
    document.getElementById('settings-feedback').textContent = 'Testing Kick...';
    document.getElementById('settings-feedback').style.color = 'var(--text-muted)';
    api.kick_test_connection(cid, cs);
  });
```

- [ ] **Step 4: Update openSettings to populate Kick fields**

Update `openSettings`:

```javascript
function openSettings() {
  if (!api) return;
  var config = api.get_full_config_for_settings();
  document.getElementById('s-client-id').value = config.client_id || '';
  document.getElementById('s-client-secret').value = config.client_secret || '';
  document.getElementById('s-streamlink').value = config.streamlink_path || 'streamlink';
  document.getElementById('s-iina').value = config.iina_path || '/Applications/IINA.app/Contents/MacOS/iina-cli';
  document.getElementById('s-interval').value = String(config.refresh_interval || 60);
  document.getElementById('s-kick-client-id').value = config.kick_client_id || '';
  document.getElementById('s-kick-client-secret').value = config.kick_client_secret || '';
  document.getElementById('settings-feedback').textContent = '';
  // Reset to General tab
  document.querySelectorAll('.settings-tab').forEach(function(t) { t.classList.remove('active'); });
  document.querySelectorAll('.settings-panel').forEach(function(p) { p.classList.remove('active'); });
  document.querySelector('.settings-tab[data-panel="general"]').classList.add('active');
  document.getElementById('panel-general').classList.add('active');
  document.getElementById('settings-overlay').classList.add('visible');
}
```

- [ ] **Step 5: Update saveSettings to include Kick fields**

Update `saveSettings`:

```javascript
function saveSettings() {
  var data = {
    client_id: document.getElementById('s-client-id').value.trim(),
    client_secret: document.getElementById('s-client-secret').value.trim(),
    streamlink_path: document.getElementById('s-streamlink').value.trim(),
    iina_path: document.getElementById('s-iina').value.trim(),
    refresh_interval: parseInt(document.getElementById('s-interval').value, 10),
    kick_client_id: document.getElementById('s-kick-client-id').value.trim(),
    kick_client_secret: document.getElementById('s-kick-client-secret').value.trim(),
  };
  if (api) api.save_settings(JSON.stringify(data));
}
```

- [ ] **Step 6: Add Kick OAuth callback handlers**

Add global JS callback handlers:

```javascript
window.onKickLoginComplete = function(data) {
  document.getElementById('kick-login-area').style.display = 'none';
  document.getElementById('kick-user-area').style.display = 'block';
  document.getElementById('kick-user-display').textContent = data.display_name;
  setStatus('Kick: logged in as ' + data.display_name, 'success');
};

window.onKickLoginError = function(msg) {
  setStatus('Kick login error: ' + msg, 'error');
};

window.onKickLogout = function() {
  document.getElementById('kick-login-area').style.display = 'block';
  document.getElementById('kick-user-area').style.display = 'none';
  document.getElementById('kick-user-display').textContent = '';
  setStatus('Kick: logged out', 'info');
};

window.onKickTestResult = function(data) {
  var fb = document.getElementById('settings-feedback');
  if (data.success) {
    fb.textContent = '\u2713 ' + data.message;
    fb.style.color = 'var(--live-green)';
  } else {
    fb.textContent = '\u2717 ' + data.message;
    fb.style.color = 'var(--error-red)';
  }
  document.getElementById('kick-test-btn').disabled = false;
};
```

- [ ] **Step 7: Commit**

```bash
cd /Users/pesnya/Documents/streamdeck
git add ui/index.html
git commit -m "feat(ui): add Kick settings tab with OAuth login, test connection"
```

---

### Task 13: ui/index.html — Platform-aware sidebar and context menu

**Files:**
- Modify: `ui/index.html`

- [ ] **Step 1: Update renderSidebar to filter by platform**

At the top of `renderSidebar`, filter favorites by active platform:

```javascript
function renderSidebar() {
  var list = document.getElementById('channel-list');
  var filteredFavorites = state.favorites;
  // Note: state.favorites from Python is now a flat list of logins.
  // We need to work with the stream items which have platform info.
  var groups = getSidebarGroups();
  var selectedExpanded = expandSidebarSectionForLogin(state.selectedChannel);
  // ... rest unchanged
```

Note: The sidebar filtering happens naturally because `state.favorites` comes from the merged list, and `state.streams` already has platform info. The grid filter handles most of the work. The sidebar shows all favorites but the live/offline status already works cross-platform.

- [ ] **Step 2: Update context menu open_browser to detect platform**

In the context menu handler, update the browser action:

```javascript
    else if (action === 'browser') {
      // Detect platform from streams
      var plat = 'twitch';
      for (var i = 0; i < state.streams.length; i++) {
        if (state.streams[i].login === ctxChannel) {
          plat = state.streams[i].platform || 'twitch';
          break;
        }
      }
      if (api) api.open_browser(ctxChannel, plat);
    }
```

- [ ] **Step 3: Update copy URL in context menu**

```javascript
    else if (action === 'copy') {
      var copyPlat = 'twitch';
      for (var i = 0; i < state.streams.length; i++) {
        if (state.streams[i].login === ctxChannel) {
          copyPlat = state.streams[i].platform || 'twitch';
          break;
        }
      }
      var copyUrl = copyPlat === 'kick'
        ? 'https://kick.com/' + ctxChannel
        : 'https://twitch.tv/' + ctxChannel;
      navigator.clipboard.writeText(copyUrl);
      setStatus('Copied URL', 'info');
    }
```

- [ ] **Step 4: Update remove context menu to pass platform**

```javascript
    else if (action === 'remove') {
      var removePlat = 'twitch';
      // Check favorites for platform
      // state.favorites is currently just logins - we need to check streams
      for (var i = 0; i < state.streams.length; i++) {
        if (state.streams[i].login === ctxChannel) {
          removePlat = state.streams[i].platform || 'twitch';
          break;
        }
      }
      if (api) api.remove_channel(ctxChannel, removePlat);
    }
```

- [ ] **Step 5: Commit**

```bash
cd /Users/pesnya/Documents/streamdeck
git add ui/index.html
git commit -m "feat(ui): platform-aware context menu (browser, copy, remove)"
```

---

### Task 14: Lint, format, and full test pass

**Files:**
- All modified files

- [ ] **Step 1: Run formatter**

Run: `cd /Users/pesnya/Documents/streamdeck && make fmt`

- [ ] **Step 2: Run linter**

Run: `cd /Users/pesnya/Documents/streamdeck && make lint`
Fix any issues that arise.

- [ ] **Step 3: Run all tests**

Run: `cd /Users/pesnya/Documents/streamdeck && make test`
Expected: All tests PASS (existing + new Kick tests)

- [ ] **Step 4: Run full check**

Run: `cd /Users/pesnya/Documents/streamdeck && make check`
Expected: PASS

- [ ] **Step 5: Commit any lint/format fixes**

```bash
cd /Users/pesnya/Documents/streamdeck
git add -A
git commit -m "chore: lint and format fixes for Phase 1"
```

---

### Task 15: Manual smoke test

**Files:** None (verification only)

- [ ] **Step 1: Launch the app**

Run: `cd /Users/pesnya/Documents/streamdeck && ./run.sh`

- [ ] **Step 2: Verify platform tabs appear**

Check that the sidebar shows All / Twitch / Kick tabs below the profile area.

- [ ] **Step 3: Verify settings tabs**

Open Settings (Cmd+,). Verify General / Twitch / Kick tabs. Check that switching tabs shows correct panels.

- [ ] **Step 4: Verify Kick credentials can be saved**

Enter Kick Client ID/Secret in the Kick settings tab. Click Save. Reopen settings and verify values persisted.

- [ ] **Step 5: Verify existing Twitch functionality works**

Confirm that Twitch streams still load, search works, avatars appear, and Watch/IINA buttons function.
