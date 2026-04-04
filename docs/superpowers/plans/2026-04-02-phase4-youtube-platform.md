# Phase 4: YouTube Platform — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add YouTube as a third streaming platform with OAuth login, live stream detection, iframe playback, quota tracking, and subscription import.

**Architecture:** YouTubeClient implements PlatformClient (like TwitchClient/KickClient) with per-event-loop HTTP client pooling. Live stream detection uses quota-free RSS feeds to discover video IDs, then YouTube Data API `videos.list` (1 unit/50 videos) to check live status — dramatically cheaper than `search.list` (100 units). Playback uses YouTube iframe embed (ToS requirement). QuotaTracker persists daily usage in config and auto-resets daily. No YouTube chat in this phase (deferred).

**Tech Stack:** Python (httpx, xml.etree.ElementTree), YouTube Data API v3, Google OAuth 2.0 (loopback redirect on localhost:3457)

**Quota Budget (10,000 units/day):**
- Polling (5-min intervals, 10 channels): RSS free + `videos.list` ~2 units/poll × 288 polls = ~576 units
- Search (user-initiated): `search.list` 100 units × ~20 searches = ~2,000 units
- Subscription import (one-time): `subscriptions.list` ~1 unit/page × ~10 pages = ~10 units
- Reserve: ~7,414 units

---

## File Structure

**Create:**
- `core/platforms/youtube.py` — YouTubeClient + QuotaTracker + RSS helpers
- `tests/platforms/test_youtube.py` — Unit tests

**Modify:**
- `core/storage.py` — Add `api_key` field to DEFAULT_PLATFORM_YOUTUBE
- `ui/api.py` — Register YouTube client, add auth/fetch/playback/import methods
- `ui/index.html` — YouTube settings tab, platform filter tab, iframe embed, quota indicator

---

### Task 1: Add `api_key` to YouTube config defaults

YouTube Data API requires an API key for unauthenticated (public data) requests. OAuth tokens are only for private data (subscriptions). The config already has a `DEFAULT_PLATFORM_YOUTUBE` dict — we need to add `api_key`.

**Files:**
- Modify: `core/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Add `api_key` to DEFAULT_PLATFORM_YOUTUBE**

In `core/storage.py`, add the `api_key` field:

```python
DEFAULT_PLATFORM_YOUTUBE: dict[str, Any] = {
    "enabled": True,
    "api_key": "",
    "client_id": "",
    "client_secret": "",
    "access_token": "",
    "refresh_token": "",
    "token_expires_at": 0,
    "user_id": "",
    "user_login": "",
    "user_display_name": "",
    "daily_quota_used": 0,
    "quota_reset_date": "",
}
```

- [ ] **Step 2: Run existing tests to verify no regressions**

Run: `uv run pytest tests/test_storage.py -v`
Expected: All existing storage tests PASS (deep merge ensures new field is added seamlessly).

- [ ] **Step 3: Commit**

```bash
git add core/storage.py
git commit -m "feat(youtube): add api_key to YouTube platform config defaults"
```

---

### Task 2: QuotaTracker class + tests

QuotaTracker persists daily quota usage in the YouTube config section. Auto-resets when the date changes. Thread-safe via `update_config`.

**Files:**
- Create: `core/platforms/youtube.py` (initial file with QuotaTracker only)
- Test: `tests/platforms/test_youtube.py`

- [ ] **Step 1: Write failing tests for QuotaTracker**

Create `tests/platforms/test_youtube.py`:

```python
from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


# ── QuotaTracker ──────────────────────────────────────────────


class TestQuotaTracker:
    def test_initial_remaining_is_full_budget(self, tmp_path: Path) -> None:
        _setup_config(tmp_path, {})
        from core.platforms.youtube import QuotaTracker

        qt = QuotaTracker(lambda: _yt_conf(tmp_path))
        assert qt.remaining() == 10_000

    def test_use_decrements_remaining(self, tmp_path: Path) -> None:
        _setup_config(tmp_path, {})
        from core.platforms.youtube import QuotaTracker

        qt = QuotaTracker(lambda: _yt_conf(tmp_path))
        qt.use(100)
        assert qt.remaining() == 9_900

    def test_resets_on_new_day(self, tmp_path: Path) -> None:
        _setup_config(
            tmp_path,
            {"daily_quota_used": 5000, "quota_reset_date": "2025-01-01"},
        )
        from core.platforms.youtube import QuotaTracker

        qt = QuotaTracker(lambda: _yt_conf(tmp_path))
        # Today is not 2025-01-01, so remaining should be full
        assert qt.remaining() == 10_000

    def test_same_day_preserves_usage(self, tmp_path: Path) -> None:
        today = date.today().isoformat()
        _setup_config(
            tmp_path,
            {"daily_quota_used": 3000, "quota_reset_date": today},
        )
        from core.platforms.youtube import QuotaTracker

        qt = QuotaTracker(lambda: _yt_conf(tmp_path))
        assert qt.remaining() == 7_000

    def test_can_use_returns_false_when_exhausted(self, tmp_path: Path) -> None:
        today = date.today().isoformat()
        _setup_config(
            tmp_path,
            {"daily_quota_used": 10_000, "quota_reset_date": today},
        )
        from core.platforms.youtube import QuotaTracker

        qt = QuotaTracker(lambda: _yt_conf(tmp_path))
        assert not qt.can_use(1)

    def test_can_use_returns_true_when_budget_available(
        self, tmp_path: Path
    ) -> None:
        _setup_config(tmp_path, {})
        from core.platforms.youtube import QuotaTracker

        qt = QuotaTracker(lambda: _yt_conf(tmp_path))
        assert qt.can_use(100)


# ── Helpers ───────────────────────────────────────────────────


def _setup_config(tmp_path: Path, yt_overrides: dict[str, Any]) -> None:
    """Write a minimal config.json under tmp_path for testing."""
    from core.storage import DEFAULT_PLATFORM_YOUTUBE

    yt = {**DEFAULT_PLATFORM_YOUTUBE, **yt_overrides}
    config = {"platforms": {"twitch": {}, "kick": {}, "youtube": yt}, "favorites": [], "settings": {}}
    config_dir = tmp_path / ".config" / "twitchx"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(json.dumps(config))


def _yt_conf(tmp_path: Path) -> dict[str, Any]:
    """Read youtube config section from tmp_path config."""
    config_file = tmp_path / ".config" / "twitchx" / "config.json"
    config = json.loads(config_file.read_text())
    return config.get("platforms", {}).get("youtube", {})
```

**Note:** The test helper uses a tmp_path-based config. The QuotaTracker receives a callable that returns the youtube config dict (dependency injection for testability).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/platforms/test_youtube.py -v`
Expected: FAIL — `core.platforms.youtube` module does not exist yet.

- [ ] **Step 3: Implement QuotaTracker**

Create `core/platforms/youtube.py`:

```python
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any
from urllib.parse import urlencode

import httpx

from core.storage import load_config, token_is_valid, update_config

logger = logging.getLogger(__name__)

YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3"
YOUTUBE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_REDIRECT_URI = "http://localhost:3457/callback"
YOUTUBE_RSS_URL = "https://www.youtube.com/feeds/videos.xml"
OAUTH_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"

VALID_CHANNEL_ID = re.compile(r"^UC[\w-]{22}$")

DAILY_QUOTA_LIMIT = 10_000


class QuotaTracker:
    """Track YouTube Data API daily quota usage.

    Persists usage to config. Auto-resets on date change.
    Receives a callable that returns the current youtube config dict,
    and optionally an update callable for persistence.
    """

    def __init__(
        self,
        get_yt_config: Any,
        update_fn: Any | None = None,
    ) -> None:
        self._get_yt = get_yt_config
        self._update_fn = update_fn or self._default_update
        self._lock = threading.Lock()

    @staticmethod
    def _default_update(used: int, date_str: str) -> None:
        def _apply(cfg: dict) -> None:
            yt = cfg.get("platforms", {}).get("youtube", {})
            yt["daily_quota_used"] = used
            yt["quota_reset_date"] = date_str

        update_config(_apply)

    def _today(self) -> str:
        return date.today().isoformat()

    def remaining(self) -> int:
        with self._lock:
            yt = self._get_yt()
            today = self._today()
            if yt.get("quota_reset_date") != today:
                return DAILY_QUOTA_LIMIT
            return max(0, DAILY_QUOTA_LIMIT - yt.get("daily_quota_used", 0))

    def can_use(self, units: int) -> bool:
        return self.remaining() >= units

    def use(self, units: int) -> None:
        with self._lock:
            yt = self._get_yt()
            today = self._today()
            if yt.get("quota_reset_date") != today:
                current = 0
            else:
                current = yt.get("daily_quota_used", 0)
            new_used = current + units
            self._update_fn(new_used, today)
```

- [ ] **Step 4: Update tests to use injected update_fn for testability**

The tests need to use tmp_path for both reading and writing. Update the test helpers:

```python
def _make_update_fn(tmp_path: Path):
    """Return an update function that writes to tmp_path config."""

    def _update(used: int, date_str: str) -> None:
        config_file = tmp_path / ".config" / "twitchx" / "config.json"
        config = json.loads(config_file.read_text())
        yt = config.get("platforms", {}).get("youtube", {})
        yt["daily_quota_used"] = used
        yt["quota_reset_date"] = date_str
        config_file.write_text(json.dumps(config))

    return _update
```

Update each test to pass the update_fn:
```python
qt = QuotaTracker(lambda: _yt_conf(tmp_path), _make_update_fn(tmp_path))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/platforms/test_youtube.py::TestQuotaTracker -v`
Expected: All 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add core/platforms/youtube.py tests/platforms/test_youtube.py
git commit -m "feat(youtube): add QuotaTracker with daily reset and persistence"
```

---

### Task 3: RSS feed parsing + tests

YouTube RSS feeds are free (no quota) and return the 15 most recent video IDs per channel. We parse them to find candidate video IDs before checking live status via the API.

**Files:**
- Modify: `core/platforms/youtube.py`
- Test: `tests/platforms/test_youtube.py`

- [ ] **Step 1: Write failing tests for RSS parsing**

Add to `tests/platforms/test_youtube.py`:

```python
class TestRSSParsing:
    def test_parses_video_ids_from_feed(self) -> None:
        from core.platforms.youtube import parse_rss_video_ids

        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <yt:videoId>abc123def45</yt:videoId>
    <title>Stream Title</title>
  </entry>
  <entry>
    <yt:videoId>xyz789ghi01</yt:videoId>
    <title>Another Video</title>
  </entry>
</feed>"""
        ids = parse_rss_video_ids(xml_data)
        assert ids == ["abc123def45", "xyz789ghi01"]

    def test_returns_empty_for_malformed_xml(self) -> None:
        from core.platforms.youtube import parse_rss_video_ids

        assert parse_rss_video_ids("not xml at all") == []

    def test_returns_empty_for_feed_with_no_entries(self) -> None:
        from core.platforms.youtube import parse_rss_video_ids

        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns="http://www.w3.org/2005/Atom">
</feed>"""
        assert parse_rss_video_ids(xml_data) == []

    def test_skips_entries_without_video_id(self) -> None:
        from core.platforms.youtube import parse_rss_video_ids

        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>No video ID here</title>
  </entry>
  <entry>
    <yt:videoId>validId12345</yt:videoId>
    <title>Has ID</title>
  </entry>
</feed>"""
        assert parse_rss_video_ids(xml_data) == ["validId12345"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/platforms/test_youtube.py::TestRSSParsing -v`
Expected: FAIL — `parse_rss_video_ids` not defined.

- [ ] **Step 3: Implement parse_rss_video_ids**

Add to `core/platforms/youtube.py`:

```python
# ── RSS feed parsing ─────────────────────────────────────────

_YT_NS = "http://www.youtube.com/xml/schemas/2015"
_ATOM_NS = "http://www.w3.org/2005/Atom"


def parse_rss_video_ids(xml_text: str) -> list[str]:
    """Extract video IDs from a YouTube channel RSS feed."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    ids: list[str] = []
    for entry in root.findall(f"{{{_ATOM_NS}}}entry"):
        vid_el = entry.find(f"{{{_YT_NS}}}videoId")
        if vid_el is not None and vid_el.text:
            ids.append(vid_el.text.strip())
    return ids
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/platforms/test_youtube.py::TestRSSParsing -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add core/platforms/youtube.py tests/platforms/test_youtube.py
git commit -m "feat(youtube): add RSS feed parser for video ID extraction"
```

---

### Task 4: YouTubeClient — constructor, HTTP helpers, token management

Set up the YouTubeClient class following the same per-event-loop HTTP client pooling pattern as TwitchClient and KickClient.

**Files:**
- Modify: `core/platforms/youtube.py`
- Test: `tests/platforms/test_youtube.py`

- [ ] **Step 1: Write tests for VALID_CHANNEL_ID and basic client setup**

Add to `tests/platforms/test_youtube.py`:

```python
from core.platforms.youtube import VALID_CHANNEL_ID, YouTubeClient


class TestValidChannelId:
    @pytest.mark.parametrize(
        "cid",
        [
            "UCX6OQ3DkcsbYNE6H8uQQuVA",
            "UC-lHJZR3Gqxm24_Vd_AJ5Yw",
            "UCVHFbqXqoYvEWM1Ddxl0QDg",
        ],
    )
    def test_accepts_valid(self, cid: str) -> None:
        assert VALID_CHANNEL_ID.match(cid)

    @pytest.mark.parametrize(
        "cid",
        [
            "",
            "not-a-channel-id",
            "UC",  # too short
            "UCtooshort",
            "@MrBeast",  # handle, not channel ID
            "https://youtube.com/channel/UCX6OQ3DkcsbYNE6H8uQQuVA",
        ],
    )
    def test_rejects_invalid(self, cid: str) -> None:
        assert not VALID_CHANNEL_ID.match(cid)


class TestYouTubeClientInit:
    def test_creates_client(self) -> None:
        client = YouTubeClient()
        assert client is not None

    def test_per_loop_client_isolation(self) -> None:
        """Different event loops get different httpx clients."""
        client = YouTubeClient()
        http_clients: list[httpx.AsyncClient] = []

        async def get_http_client() -> httpx.AsyncClient:
            return client._get_client()

        for _ in range(2):
            loop = asyncio.new_event_loop()
            try:
                hc = loop.run_until_complete(get_http_client())
                http_clients.append(hc)
                loop.run_until_complete(client.close_loop_resources())
            finally:
                loop.close()

        assert http_clients[0] is not http_clients[1]
```

- [ ] **Step 2: Implement YouTubeClient class**

Add to `core/platforms/youtube.py`:

```python
class YouTubeClient:
    """YouTube Data API v3 client with per-event-loop HTTP pooling."""

    def __init__(self) -> None:
        self._config = load_config()
        self._loop_clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}
        self._token_locks: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}
        self._loop_state_lock = threading.Lock()
        self._quota = QuotaTracker(
            self._yconf,
        )
        self._live_video_ids: dict[str, str] = {}

    def _yconf(self) -> dict[str, Any]:
        """Shortcut to the YouTube platform config section."""
        return self._config.get("platforms", {}).get("youtube", {})

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
        """Compatibility no-op — clients are per-event-loop."""

    def _reload_config(self) -> None:
        self._config = load_config()

    # ── Token management ─────────────────────────────────────

    async def _ensure_token(self) -> str | None:
        """Return a valid OAuth token, refreshing if needed. None if unavailable."""
        async with self._get_token_lock():
            self._reload_config()
            yc = self._yconf()
            if token_is_valid(yc):
                return yc["access_token"]
            if yc.get("refresh_token"):
                try:
                    return await self.refresh_user_token()
                except ValueError:
                    return None
            return None

    def _get_auth_params(self) -> dict[str, str]:
        """Return auth params — OAuth token header or api_key query param."""
        yc = self._yconf()
        # Prefer OAuth token if available (checked by caller via _ensure_token)
        # Otherwise use API key
        api_key = yc.get("api_key", "")
        if api_key:
            return {"key": api_key}
        return {}

    # ── Generic GET ──────────────────────────────────────────

    async def _yt_get(
        self,
        endpoint: str,
        params: dict[str, str] | None = None,
        auth_required: bool = False,
    ) -> dict[str, Any]:
        """Make a GET request to the YouTube Data API."""
        token = await self._ensure_token()
        headers: dict[str, str] = {}
        query: dict[str, str] = dict(params or {})

        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif auth_required:
            raise ValueError("YouTube authentication required but no valid token.")
        else:
            # Use API key for unauthenticated requests
            api_key = self._yconf().get("api_key", "")
            if not api_key:
                raise ValueError("YouTube API key required. Set it in Settings.")
            query["key"] = api_key

        url = f"{YOUTUBE_API_URL}/{endpoint}"
        logger.debug("YT GET %s params=%s", url, query)
        client = self._get_client()
        resp = await client.get(url, headers=headers, params=query)
        logger.debug("YT Response: %d", resp.status_code)

        if resp.status_code == 403:
            body = resp.json()
            errors = body.get("error", {}).get("errors", [])
            for err in errors:
                if err.get("reason") == "quotaExceeded":
                    raise ValueError("YouTube API daily quota exceeded.")
            resp.raise_for_status()
        if resp.status_code == 401 and token:
            new_token = await self._ensure_token()
            if new_token:
                headers["Authorization"] = f"Bearer {new_token}"
                resp = await client.get(url, headers=headers, params=query)
            else:
                resp.raise_for_status()
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/platforms/test_youtube.py::TestValidChannelId tests/platforms/test_youtube.py::TestYouTubeClientInit -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add core/platforms/youtube.py tests/platforms/test_youtube.py
git commit -m "feat(youtube): add YouTubeClient with HTTP pooling and token management"
```

---

### Task 5: YouTubeClient — get_live_streams

The core feature: detect which favorited YouTube channels are currently live.

**Strategy:** Fetch RSS feeds (0 quota) to collect recent video IDs → batch-check via `videos.list` with `liveStreamingDetails` (1 unit per 50 videos) → return only live streams.

**Files:**
- Modify: `core/platforms/youtube.py`
- Test: `tests/platforms/test_youtube.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/platforms/test_youtube.py`:

```python
class TestGetLiveStreams:
    def test_empty_channel_list_returns_empty(self) -> None:
        client = YouTubeClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(client.get_live_streams([]))
        assert result == []
        loop.run_until_complete(client.close())
        loop.close()

    def test_invalid_channel_ids_filtered(self) -> None:
        client = YouTubeClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            client.get_live_streams(["not-valid", "", "@handle"])
        )
        assert result == []
        loop.run_until_complete(client.close())
        loop.close()

    def test_builds_stream_info_from_api_response(self) -> None:
        """Verify _build_stream_from_video extracts correct fields."""
        from core.platforms.youtube import YouTubeClient

        video_item = {
            "id": "dQw4w9WgXcQ",
            "snippet": {
                "channelId": "UCuAXFkgsw1L7xaCfnd5JJOw",
                "channelTitle": "Rick Astley",
                "title": "Live Concert Stream",
                "categoryId": "10",
                "thumbnails": {
                    "high": {"url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"}
                },
            },
            "liveStreamingDetails": {
                "actualStartTime": "2026-04-02T10:00:00Z",
                "concurrentViewers": "12345",
            },
        }
        stream = YouTubeClient._build_stream_from_video(video_item)
        assert stream["login"] == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert stream["display_name"] == "Rick Astley"
        assert stream["title"] == "Live Concert Stream"
        assert stream["viewers"] == 12345
        assert stream["platform"] == "youtube"
        assert stream["video_id"] == "dQw4w9WgXcQ"

    def test_is_live_check(self) -> None:
        """Verify _is_video_live correctly identifies active live streams."""
        from core.platforms.youtube import YouTubeClient

        # Active live stream
        assert YouTubeClient._is_video_live(
            {
                "liveStreamingDetails": {
                    "actualStartTime": "2026-04-02T10:00:00Z",
                    "concurrentViewers": "100",
                }
            }
        )
        # Ended stream
        assert not YouTubeClient._is_video_live(
            {
                "liveStreamingDetails": {
                    "actualStartTime": "2026-04-02T10:00:00Z",
                    "actualEndTime": "2026-04-02T12:00:00Z",
                }
            }
        )
        # Not a live stream
        assert not YouTubeClient._is_video_live({"snippet": {"title": "normal video"}})
```

- [ ] **Step 2: Implement get_live_streams and helpers**

Add to `YouTubeClient` in `core/platforms/youtube.py`:

```python
    # ── Live streams ─────────────────────────────────────────

    @staticmethod
    def _is_video_live(item: dict[str, Any]) -> bool:
        """Check if a video item from videos.list is currently live."""
        details = item.get("liveStreamingDetails", {})
        return bool(
            details.get("actualStartTime")
            and not details.get("actualEndTime")
            and details.get("concurrentViewers")
        )

    @staticmethod
    def _build_stream_from_video(item: dict[str, Any]) -> dict[str, Any]:
        """Build a normalized stream dict from a videos.list item."""
        snippet = item.get("snippet", {})
        details = item.get("liveStreamingDetails", {})
        thumbs = snippet.get("thumbnails", {})
        thumb_url = (
            thumbs.get("maxres", {}).get("url")
            or thumbs.get("high", {}).get("url")
            or thumbs.get("medium", {}).get("url", "")
        )
        return {
            "login": snippet.get("channelId", ""),
            "display_name": snippet.get("channelTitle", ""),
            "title": snippet.get("title", ""),
            "game": "",  # YouTube doesn't have game categories like Twitch
            "viewers": int(details.get("concurrentViewers", 0)),
            "started_at": details.get("actualStartTime", ""),
            "thumbnail_url": thumb_url,
            "viewer_trend": None,
            "platform": "youtube",
            "video_id": item.get("id", ""),
            "channel_id": snippet.get("channelId", ""),
            "category_id": snippet.get("categoryId", ""),
        }

    async def _fetch_rss_video_ids(self, channel_id: str) -> list[str]:
        """Fetch recent video IDs from a channel's RSS feed (no quota cost)."""
        url = f"{YOUTUBE_RSS_URL}?channel_id={channel_id}"
        try:
            client = self._get_client()
            resp = await client.get(url, timeout=10.0)
            if resp.status_code != 200:
                logger.debug("RSS feed returned %d for %s", resp.status_code, channel_id)
                return []
            return parse_rss_video_ids(resp.text)
        except Exception as e:
            logger.debug("RSS fetch failed for %s: %s", channel_id, e)
            return []

    async def get_live_streams(self, channel_ids: list[str]) -> list[dict[str, Any]]:
        """Get live streams for a list of YouTube channel IDs.

        Uses RSS feeds (free) to discover video IDs, then videos.list (1 unit/50)
        to check which are currently live.
        """
        valid_ids = [cid for cid in channel_ids if cid and VALID_CHANNEL_ID.match(cid)]
        if not valid_ids:
            return []

        # 1. Fetch RSS feeds in parallel (no quota cost)
        rss_tasks = [self._fetch_rss_video_ids(cid) for cid in valid_ids]
        rss_results = await asyncio.gather(*rss_tasks, return_exceptions=True)

        all_video_ids: list[str] = []
        for result in rss_results:
            if isinstance(result, list):
                all_video_ids.extend(result)

        if not all_video_ids:
            return []

        # Deduplicate
        seen: set[str] = set()
        unique_ids: list[str] = []
        for vid in all_video_ids:
            if vid not in seen:
                seen.add(vid)
                unique_ids.append(vid)

        # 2. Batch check via videos.list (1 unit per 50 videos)
        live_streams: list[dict[str, Any]] = []
        for i in range(0, len(unique_ids), 50):
            batch = unique_ids[i : i + 50]
            if not self._quota.can_use(1):
                logger.warning("YouTube quota exhausted, skipping live check")
                break
            try:
                data = await self._yt_get(
                    "videos",
                    params={
                        "part": "snippet,liveStreamingDetails",
                        "id": ",".join(batch),
                    },
                )
                self._quota.use(1)
                for item in data.get("items", []):
                    if self._is_video_live(item):
                        live_streams.append(self._build_stream_from_video(item))
            except Exception as e:
                logger.warning("YouTube videos.list failed: %s", e)

        return live_streams
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/platforms/test_youtube.py::TestGetLiveStreams -v`
Expected: All 4 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add core/platforms/youtube.py tests/platforms/test_youtube.py
git commit -m "feat(youtube): add get_live_streams with RSS + videos.list"
```

---

### Task 6: YouTubeClient — search_channels + get_channel_info

Channel search uses `search.list` (100 units). Channel info uses `channels.list` (1 unit).

**Files:**
- Modify: `core/platforms/youtube.py`
- Test: `tests/platforms/test_youtube.py`

- [ ] **Step 1: Write failing tests**

```python
class TestSearchChannels:
    def test_empty_query_returns_empty(self) -> None:
        client = YouTubeClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(client.search_channels(""))
        assert result == []
        loop.run_until_complete(client.close())
        loop.close()

    def test_normalizes_search_result(self) -> None:
        """Verify _normalize_channel_search_result extracts correct fields."""
        item = {
            "id": {"channelId": "UCX6OQ3DkcsbYNE6H8uQQuVA"},
            "snippet": {
                "channelTitle": "MrBeast",
                "description": "YouTube creator",
                "thumbnails": {
                    "default": {"url": "https://yt3.ggpht.com/thumb.jpg"}
                },
            },
        }
        result = YouTubeClient._normalize_channel_search_result(item)
        assert result["login"] == "UCX6OQ3DkcsbYNE6H8uQQuVA"
        assert result["display_name"] == "MrBeast"
        assert result["platform"] == "youtube"


class TestGetChannelInfo:
    def test_builds_channel_info_from_response(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = YouTubeClient()

        async def fake_yt_get(
            endpoint: str, params: dict | None = None, auth_required: bool = False
        ) -> dict[str, Any]:
            return {
                "items": [
                    {
                        "id": "UCX6OQ3DkcsbYNE6H8uQQuVA",
                        "snippet": {
                            "title": "MrBeast",
                            "description": "YouTube creator",
                            "thumbnails": {
                                "default": {"url": "https://yt3.ggpht.com/thumb.jpg"}
                            },
                        },
                        "statistics": {
                            "subscriberCount": "100000000",
                        },
                    }
                ]
            }

        monkeypatch.setattr(client, "_yt_get", fake_yt_get)
        monkeypatch.setattr(client._quota, "use", lambda n: None)

        loop = asyncio.new_event_loop()
        try:
            info = loop.run_until_complete(
                client.get_channel_info("UCX6OQ3DkcsbYNE6H8uQQuVA")
            )
        finally:
            loop.run_until_complete(client.close())
            loop.close()

        assert info["channel_id"] == "UCX6OQ3DkcsbYNE6H8uQQuVA"
        assert info["display_name"] == "MrBeast"
        assert info["followers"] == 100_000_000
```

- [ ] **Step 2: Implement search_channels and get_channel_info**

Add to `YouTubeClient`:

```python
    # ── Search ───────────────────────────────────────────────

    @staticmethod
    def _normalize_channel_search_result(item: dict[str, Any]) -> dict[str, Any]:
        """Normalize a search.list channel result for the UI."""
        snippet = item.get("snippet", {})
        channel_id = item.get("id", {}).get("channelId", "")
        thumbs = snippet.get("thumbnails", {})
        return {
            "login": channel_id,
            "display_name": snippet.get("channelTitle", ""),
            "is_live": False,  # search.list doesn't indicate live status
            "game_name": "",
            "platform": "youtube",
            "avatar_url": thumbs.get("default", {}).get("url", ""),
        }

    async def search_channels(self, query: str) -> list[dict[str, Any]]:
        """Search for YouTube channels. Costs 100 quota units."""
        query = query.strip()
        if not query:
            return []
        if not self._quota.can_use(100):
            logger.warning("YouTube quota too low for search (need 100 units)")
            return []
        try:
            data = await self._yt_get(
                "search",
                params={
                    "part": "snippet",
                    "type": "channel",
                    "q": query,
                    "maxResults": "10",
                },
            )
            self._quota.use(100)
            return [
                self._normalize_channel_search_result(item)
                for item in data.get("items", [])
                if item.get("id", {}).get("channelId")
            ]
        except Exception as e:
            logger.warning("YouTube search failed: %s", e)
            return []

    # ── Channel info ─────────────────────────────────────────

    async def get_channel_info(self, channel_id: str) -> dict[str, Any]:
        """Get channel details. Costs 1 quota unit."""
        channel_id = channel_id.strip()
        if not channel_id:
            return {}
        data = await self._yt_get(
            "channels",
            params={
                "part": "snippet,statistics",
                "id": channel_id,
            },
        )
        self._quota.use(1)
        items = data.get("items", [])
        if not items:
            return {}
        item = items[0]
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        thumbs = snippet.get("thumbnails", {})
        return {
            "channel_id": item.get("id", channel_id),
            "display_name": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "avatar_url": thumbs.get("default", {}).get("url", ""),
            "followers": int(stats.get("subscriberCount", 0)),
        }
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/platforms/test_youtube.py::TestSearchChannels tests/platforms/test_youtube.py::TestGetChannelInfo -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add core/platforms/youtube.py tests/platforms/test_youtube.py
git commit -m "feat(youtube): add search_channels and get_channel_info"
```

---

### Task 7: YouTubeClient — OAuth, get_current_user, get_followed_channels, resolve_stream_url

Complete the remaining YouTubeClient methods: Google OAuth 2.0 flow, user profile, subscription import, and iframe playback info.

**Files:**
- Modify: `core/platforms/youtube.py`
- Test: `tests/platforms/test_youtube.py`

- [ ] **Step 1: Write failing tests**

```python
class TestOAuth:
    def test_get_auth_url_contains_required_params(self) -> None:
        client = YouTubeClient()
        # Inject a client_id for the test
        client._config = {
            "platforms": {
                "youtube": {"client_id": "test-client-id", "client_secret": "secret"}
            }
        }
        url = client.get_auth_url()
        assert "accounts.google.com" in url
        assert "test-client-id" in url
        assert "localhost%3A3457" in url or "localhost:3457" in url
        assert "youtube.readonly" in url


class TestGetFollowedChannels:
    def test_returns_channel_ids_from_subscriptions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = YouTubeClient()
        call_count = 0

        async def fake_yt_get(
            endpoint: str, params: dict | None = None, auth_required: bool = False
        ) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "items": [
                        {
                            "snippet": {
                                "resourceId": {"channelId": "UC111"},
                                "title": "Channel One",
                            }
                        },
                        {
                            "snippet": {
                                "resourceId": {"channelId": "UC222"},
                                "title": "Channel Two",
                            }
                        },
                    ],
                    "nextPageToken": "page2",
                }
            return {
                "items": [
                    {
                        "snippet": {
                            "resourceId": {"channelId": "UC333"},
                            "title": "Channel Three",
                        }
                    }
                ],
            }

        monkeypatch.setattr(client, "_yt_get", fake_yt_get)
        monkeypatch.setattr(client._quota, "use", lambda n: None)
        monkeypatch.setattr(client._quota, "can_use", lambda n: True)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(client.get_followed_channels("me"))
        finally:
            loop.run_until_complete(client.close())
            loop.close()

        assert result == [
            {"channel_id": "UC111", "display_name": "Channel One"},
            {"channel_id": "UC222", "display_name": "Channel Two"},
            {"channel_id": "UC333", "display_name": "Channel Three"},
        ]


class TestResolveStreamUrl:
    def test_returns_youtube_embed_playback_info(self) -> None:
        client = YouTubeClient()
        # Inject a known video_id into cached streams
        client._live_video_ids = {"UCtest123456789012345": "dQw4w9WgXcQ"}

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                client.resolve_stream_url("UCtest123456789012345", "best")
            )
        finally:
            loop.run_until_complete(client.close())
            loop.close()

        assert result["url"] == "dQw4w9WgXcQ"
        assert result["playback_type"] == "youtube_embed"
```

- [ ] **Step 2: Implement OAuth and remaining methods**

Add to `YouTubeClient`:

```python
    # ── OAuth ────────────────────────────────────────────────

    def get_auth_url(self) -> str:
        """Generate Google OAuth authorization URL."""
        yc = self._yconf()
        params = {
            "client_id": yc.get("client_id", ""),
            "redirect_uri": YOUTUBE_REDIRECT_URI,
            "response_type": "code",
            "scope": OAUTH_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{YOUTUBE_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for tokens."""
        self._reload_config()
        yc = self._yconf()
        client = self._get_client()
        resp = await client.post(
            YOUTUBE_TOKEN_URL,
            data={
                "client_id": yc.get("client_id", ""),
                "client_secret": yc.get("client_secret", ""),
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": YOUTUBE_REDIRECT_URI,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def refresh_user_token(self) -> str:
        """Refresh the OAuth token. Clears auth state on failure."""
        yc = self._yconf()
        client = self._get_client()
        resp = await client.post(
            YOUTUBE_TOKEN_URL,
            data={
                "client_id": yc.get("client_id", ""),
                "client_secret": yc.get("client_secret", ""),
                "refresh_token": yc.get("refresh_token", ""),
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code in (400, 401):

            def _clear(cfg: dict) -> None:
                yc = cfg.get("platforms", {}).get("youtube", {})
                yc["access_token"] = ""
                yc["refresh_token"] = ""
                yc["token_expires_at"] = 0
                yc["user_id"] = ""
                yc["user_login"] = ""
                yc["user_display_name"] = ""

            self._config = update_config(_clear)
            raise ValueError("YouTube token expired. Please log in again.")
        resp.raise_for_status()
        data = resp.json()
        new_token = data["access_token"]
        new_expires = int(time.time()) + data.get("expires_in", 3600)

        def _update(cfg: dict) -> None:
            yc = cfg.get("platforms", {}).get("youtube", {})
            yc["access_token"] = new_token
            yc["token_expires_at"] = new_expires

        self._config = update_config(_update)
        return new_token

    async def get_current_user(self) -> dict[str, Any]:
        """Get the authenticated user's YouTube channel info."""
        data = await self._yt_get(
            "channels",
            params={"part": "snippet", "mine": "true"},
            auth_required=True,
        )
        self._quota.use(1)
        items = data.get("items", [])
        if not items:
            raise ValueError("No YouTube channel found for this account.")
        item = items[0]
        snippet = item.get("snippet", {})
        thumbs = snippet.get("thumbnails", {})
        return {
            "id": item.get("id", ""),
            "login": snippet.get("customUrl", item.get("id", "")),
            "display_name": snippet.get("title", ""),
            "profile_image_url": thumbs.get("default", {}).get("url", ""),
        }

    # ── Subscriptions ────────────────────────────────────────

    async def get_followed_channels(self, user_id: str) -> list[dict[str, str]]:
        """Get user's YouTube subscriptions. Returns list of {channel_id, display_name}.

        Costs 1 unit per page (50 subscriptions/page).
        """
        channels: list[dict[str, str]] = []
        page_token: str | None = None

        while True:
            if not self._quota.can_use(1):
                logger.warning("YouTube quota too low for subscriptions fetch")
                break
            params: dict[str, str] = {
                "part": "snippet",
                "mine": "true",
                "maxResults": "50",
            }
            if page_token:
                params["pageToken"] = page_token
            data = await self._yt_get("subscriptions", params=params, auth_required=True)
            self._quota.use(1)

            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                resource = snippet.get("resourceId", {})
                cid = resource.get("channelId", "")
                name = snippet.get("title", cid)
                if cid:
                    channels.append({"channel_id": cid, "display_name": name})

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return channels

    # ── Playback ─────────────────────────────────────────────

    async def resolve_stream_url(
        self, channel_id: str, quality: str
    ) -> dict[str, Any]:
        """Return PlaybackInfo for YouTube iframe embed.

        YouTube ToS prohibits custom playback — must use iframe embed.
        """
        video_id = self._live_video_ids.get(channel_id, "")
        if not video_id:
            raise ValueError(f"No live video found for channel {channel_id}")
        return {
            "url": video_id,
            "playback_type": "youtube_embed",
            "quality": quality,
        }
```

Update `get_live_streams` to populate `_live_video_ids` cache. Add this line inside the live stream detection loop, right after `live_streams.append(...)`:

```python
                        stream = self._build_stream_from_video(item)
                        live_streams.append(stream)
                        # Cache video_id for playback
                        self._live_video_ids[stream["login"]] = stream["video_id"]
```

- [ ] **Step 3: Run all YouTube tests**

Run: `uv run pytest tests/platforms/test_youtube.py -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add core/platforms/youtube.py tests/platforms/test_youtube.py
git commit -m "feat(youtube): add OAuth, subscriptions, and iframe playback"
```

---

### Task 8: api.py — Register YouTube client, config, auth

Wire YouTubeClient into the API bridge: register in `_platforms`, add config/login/logout/test methods.

**Files:**
- Modify: `ui/api.py`

- [ ] **Step 1: Add YouTube imports and registration**

At the top of `ui/api.py`, add the import:

```python
from core.platforms.youtube import YouTubeClient
```

In `__init__`, register YouTube:

```python
        self._youtube = YouTubeClient()
        self._platforms: dict[str, Any] = {
            "twitch": self._twitch,
            "kick": self._kick,
            "youtube": self._youtube,
        }
```

Add config helper:

```python
    def _get_youtube_config(self) -> dict[str, Any]:
        """Get YouTube platform config section."""
        return get_platform_config(self._config, "youtube")
```

- [ ] **Step 2: Add YouTube to get_config and get_full_config_for_settings**

In `get_config()`, after the Kick section, add:

```python
        yt_conf = get_platform_config(self._config, "youtube")
        masked["youtube_has_credentials"] = bool(yt_conf.get("api_key"))
        masked["youtube_has_oauth"] = bool(
            yt_conf.get("client_id") and yt_conf.get("client_secret")
        )
        if yt_conf.get("user_login") or yt_conf.get("user_display_name"):
            masked["youtube_user"] = {
                "login": yt_conf.get("user_login", ""),
                "display_name": yt_conf.get(
                    "user_display_name", yt_conf.get("user_login", "")
                ),
            }
        masked["youtube_quota_remaining"] = self._youtube._quota.remaining()
```

In `get_full_config_for_settings()`, add YouTube fields to the returned dict:

```python
            "youtube_api_key": yt_conf.get("api_key", ""),
            "youtube_client_id": yt_conf.get("client_id", ""),
            "youtube_client_secret": yt_conf.get("client_secret", ""),
            "youtube_display_name": yt_conf.get("user_display_name", ""),
            "youtube_user_login": yt_conf.get("user_login", ""),
            "youtube_quota_remaining": self._youtube._quota.remaining(),
```

(Also read `yt_conf` at the top of the method: `yt_conf = get_platform_config(self._config, "youtube")`)

- [ ] **Step 3: Add YouTube to save_settings**

In `save_settings`, after the Kick credential handling, add:

```python
            yc = cfg.get("platforms", {}).get("youtube", {})
            if "youtube_api_key" in parsed:
                new_yt_key = parsed["youtube_api_key"].strip()
                if new_yt_key:
                    yc["api_key"] = new_yt_key
            if "youtube_client_id" in parsed:
                new_yt_cid = parsed["youtube_client_id"].strip()
                if new_yt_cid:
                    yc["client_id"] = new_yt_cid
            if "youtube_client_secret" in parsed:
                new_yt_cs = parsed["youtube_client_secret"].strip()
                if new_yt_cs:
                    yc["client_secret"] = new_yt_cs
```

- [ ] **Step 4: Add youtube_login, youtube_logout, youtube_test_connection**

```python
    def youtube_login(self) -> None:
        yt_conf = self._get_youtube_config()
        if not yt_conf.get("client_id") or not yt_conf.get("client_secret"):
            self._eval_js("window.onYouTubeNeedsCredentials()")
            return
        auth_url = self._youtube.get_auth_url()
        if self._polling_timer:
            self._polling_timer.cancel()
            self._polling_timer = None
        self._eval_js(
            "window.onStatusUpdate({text: 'Waiting for YouTube login...', type: 'warn'})"
        )

        def do_login() -> None:
            webbrowser.open(auth_url)
            code = wait_for_oauth_code()
            if self._shutdown.is_set():
                return
            if code is None:
                self._eval_js('window.onYouTubeLoginError("Login timed out")')
                self._restart_polling()
                return
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                token_data = loop.run_until_complete(
                    self._youtube.exchange_code(code)
                )
                access_token = token_data["access_token"]
                refresh_token = token_data.get("refresh_token", "")
                expires_at = int(time.time()) + token_data.get("expires_in", 3600)

                def _save_tokens(cfg: dict) -> None:
                    yc = cfg.get("platforms", {}).get("youtube", {})
                    yc["access_token"] = access_token
                    yc["refresh_token"] = refresh_token
                    yc["token_expires_at"] = expires_at

                self._config = update_config(_save_tokens)

                user = loop.run_until_complete(self._youtube.get_current_user())
                uid = user.get("id", "")
                ulogin = user.get("login", "")
                udisplay = user.get("display_name", ulogin)

                def _save_user(cfg: dict) -> None:
                    yc = cfg.get("platforms", {}).get("youtube", {})
                    yc["user_id"] = uid
                    yc["user_login"] = ulogin
                    yc["user_display_name"] = udisplay

                self._config = update_config(_save_user)

                result = json.dumps(
                    {
                        "platform": "youtube",
                        "display_name": udisplay,
                        "login": ulogin,
                    }
                )
                self._eval_js(f"window.onYouTubeLoginComplete({result})")
                self.refresh()
            except Exception as e:
                msg = str(e)[:80] if str(e) else "YouTube login failed"
                safe_msg = json.dumps(msg)
                self._eval_js(f"window.onYouTubeLoginError({safe_msg})")
                self._restart_polling()
            finally:
                self._close_thread_loop(loop)

        self._run_in_thread(do_login)

    def youtube_logout(self) -> None:

        def _clear(cfg: dict) -> None:
            yc = cfg.get("platforms", {}).get("youtube", {})
            yc["access_token"] = ""
            yc["refresh_token"] = ""
            yc["token_expires_at"] = 0
            yc["user_id"] = ""
            yc["user_login"] = ""
            yc["user_display_name"] = ""

        self._config = update_config(_clear)
        self._eval_js("window.onYouTubeLogout()")

    def youtube_test_connection(self, api_key: str) -> None:
        """Test YouTube API key by fetching a known video."""

        def do_test() -> None:
            try:
                resp = httpx.get(
                    f"{YOUTUBE_API_URL}/videos",
                    params={
                        "part": "snippet",
                        "id": "dQw4w9WgXcQ",
                        "key": api_key.strip(),
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    result = json.dumps({"success": True, "message": "Connected"})
                elif resp.status_code == 403:
                    result = json.dumps(
                        {"success": False, "message": "API key invalid or quota exceeded"}
                    )
                else:
                    result = json.dumps(
                        {"success": False, "message": f"HTTP {resp.status_code}"}
                    )
            except httpx.ConnectError:
                result = json.dumps(
                    {"success": False, "message": "No internet connection"}
                )
            except Exception as exc:
                msg = str(exc)[:60]
                result = json.dumps({"success": False, "message": msg})
            self._eval_js(f"window.onYouTubeTestResult({result})")

        self._run_in_thread(do_test)
```

Also add the import at the top of api.py:

```python
from core.platforms.youtube import YOUTUBE_API_URL
```

- [ ] **Step 5: Commit**

```bash
git add ui/api.py
git commit -m "feat(youtube): register YouTubeClient in API bridge with auth methods"
```

---

### Task 9: api.py — Fetch integration, stream building, search, import

Extend `_async_fetch` to include YouTube streams. Add `_build_youtube_stream_item`, extend `search_channels`, add `youtube_import_follows`.

**Files:**
- Modify: `ui/api.py`

- [ ] **Step 1: Add `_build_youtube_stream_item` and `_normalize_youtube_search_result`**

```python
    @staticmethod
    def _normalize_youtube_search_result(result: dict[str, Any]) -> dict[str, Any]:
        return {
            "login": result.get("login", ""),
            "display_name": result.get("display_name", ""),
            "is_live": result.get("is_live", False),
            "game_name": "",
            "platform": "youtube",
        }

    @staticmethod
    def _build_youtube_stream_item(stream: dict[str, Any]) -> dict[str, Any]:
        return {
            "login": stream.get("login", ""),
            "display_name": stream.get("display_name", ""),
            "title": stream.get("title", ""),
            "game": stream.get("game", ""),
            "viewers": stream.get("viewers", 0),
            "started_at": stream.get("started_at", ""),
            "thumbnail_url": stream.get("thumbnail_url", ""),
            "viewer_trend": None,
            "platform": "youtube",
            "video_id": stream.get("video_id", ""),
            "channel_id": stream.get("channel_id", ""),
        }
```

- [ ] **Step 2: Extend `refresh()` to include YouTube favorites**

In `refresh()`, after `kick_favorites = ...`, add:

```python
        youtube_favorites = get_favorite_logins(self._config, "youtube")
```

Update `all_favorites`:

```python
        all_favorites = twitch_favorites + kick_favorites + youtube_favorites
```

Update the `_fetch_data` call signature and lambda:

```python
        self._run_in_thread(
            lambda tf=list(twitch_favorites), kf=list(kick_favorites), yf=list(youtube_favorites): self._fetch_data(
                tf, kf, yf
            )
        )
```

Also add `_last_youtube_fetch: float = 0` to `TwitchXApi.__init__` alongside the other state fields.
```

- [ ] **Step 3: Extend `_fetch_data` and `_async_fetch` for YouTube**

Update `_fetch_data` signature:

```python
    def _fetch_data(
        self, twitch_favorites: list[str], kick_favorites: list[str], youtube_favorites: list[str]
    ) -> None:
```

Update the async fetch call and data handler inside the try block:

```python
                    twitch_streams, twitch_users, kick_streams, youtube_streams = (
                        loop.run_until_complete(
                            self._async_fetch(twitch_favorites, kick_favorites, youtube_favorites)
                        )
                    )
                    self._on_data_fetched(
                        twitch_favorites,
                        kick_favorites,
                        youtube_favorites,
                        twitch_streams,
                        twitch_users,
                        kick_streams,
                        youtube_streams,
                    )
```

Update `_async_fetch`:

```python
    async def _async_fetch(
        self, twitch_favorites: list[str], kick_favorites: list[str], youtube_favorites: list[str]
    ) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
        twitch_streams: list[dict] = []
        twitch_users: list[dict] = []
        kick_streams: list[dict] = []
        youtube_streams: list[dict] = []

        # ... existing Twitch and Kick fetch logic ...

        # Fetch YouTube data respecting the 5-minute minimum polling interval
        if youtube_favorites:
            yt_conf = get_platform_config(self._config, "youtube")
            settings = get_settings(self._config)
            yt_interval = settings.get("youtube_refresh_interval", 300)
            yt_due = time.time() - self._last_youtube_fetch >= yt_interval
            if yt_due and (yt_conf.get("api_key") or yt_conf.get("access_token")):
                try:
                    youtube_streams = await self._youtube.get_live_streams(youtube_favorites)
                    self._last_youtube_fetch = time.time()
                except Exception as e:
                    logger.warning("YouTube fetch failed: %s", e)

        return twitch_streams, twitch_users, kick_streams, youtube_streams
```

- [ ] **Step 4: Update `_on_data_fetched` to include YouTube streams**

Update the method signature and add YouTube stream building:

```python
    def _on_data_fetched(
        self,
        twitch_favorites: list[str],
        kick_favorites: list[str],
        youtube_favorites: list[str],
        twitch_streams: list[dict],
        twitch_users: list[dict],
        kick_streams: list[dict],
        youtube_streams: list[dict],
    ) -> None:
```

After the Kick stream items section, add:

```python
        # Build YouTube stream items
        youtube_live_ids = set()
        for s in youtube_streams:
            item = self._build_youtube_stream_item(s)
            stream_items.append(item)
            youtube_live_ids.add(item["login"])
```

Update `live_logins` to include YouTube:

```python
        live_logins = twitch_live_logins | kick_live_slugs | youtube_live_ids
```

Update `all_favorites`:

```python
        all_favorites = twitch_favorites + kick_favorites + youtube_favorites
```

- [ ] **Step 5: Extend `search_channels` for YouTube**

In the `do_search` inner function, add YouTube search:

```python
                if platform in {"youtube", "all"}:
                    yt_conf = get_platform_config(self._config, "youtube")
                    if yt_conf.get("api_key") or yt_conf.get("access_token"):
                        yt_results = loop.run_until_complete(
                            self._youtube.search_channels(query)
                        )
                        items.extend(
                            self._normalize_youtube_search_result(result)
                            for result in yt_results
                        )
```

- [ ] **Step 6: Add `youtube_import_follows`**

```python
    def youtube_import_follows(self) -> None:
        """Import user's YouTube subscriptions into favorites."""
        yt_conf = self._get_youtube_config()
        if not yt_conf.get("access_token"):
            self._eval_js('window.onYouTubeImportError("Not logged in to YouTube")')
            return
        self._eval_js(
            "window.onStatusUpdate({text: 'Importing YouTube subscriptions...', type: 'warn'})"
        )

        def do_import() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                subs = loop.run_until_complete(
                    self._youtube.get_followed_channels("me")
                )
                added = 0

                def _apply(cfg: dict) -> None:
                    nonlocal added
                    existing = {
                        f["login"]
                        for f in cfg.get("favorites", [])
                        if f.get("platform") == "youtube"
                    }
                    for sub in subs:
                        cid = sub["channel_id"]
                        if cid not in existing:
                            cfg["favorites"].append(
                                {
                                    "platform": "youtube",
                                    "login": cid,
                                    "display_name": sub["display_name"],
                                }
                            )
                            existing.add(cid)
                            added += 1

                self._config = update_config(_apply)
                result = json.dumps({"added": added})
                self._eval_js(f"window.onYouTubeImportComplete({result})")
                self.refresh()
            except Exception as e:
                msg = str(e)[:80] if str(e) else "YouTube import failed"
                safe_msg = json.dumps(msg)
                self._eval_js(f"window.onYouTubeImportError({safe_msg})")
            finally:
                self._close_thread_loop(loop)

        self._run_in_thread(do_import)
```

- [ ] **Step 7: Update `watch()` to handle YouTube iframe playback**

In `watch()`, after the existing HLS resolution code, add a YouTube branch. The key difference: YouTube doesn't use streamlink — it returns a video_id for iframe embed.

Before the `do_resolve` function definition, add:

```python
        # YouTube uses iframe embed, not streamlink
        if platform == "youtube":
            video_id = stream.get("video_id", "") if stream else ""
            if not video_id:
                r = json.dumps(
                    {
                        "success": False,
                        "message": "No live video found for this channel",
                        "channel": channel,
                    }
                )
                self._eval_js(f"window.onLaunchResult({r})")
                self._cancel_launch_timer()
                return
            self._cancel_launch_timer()
            self._watching_channel = channel
            stream_data = json.dumps(
                {
                    "url": video_id,
                    "channel": channel,
                    "title": title,
                    "platform": "youtube",
                    "playback_type": "youtube_embed",
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
            return
```

- [ ] **Step 8: Update `open_browser` for YouTube**

```python
    def open_browser(self, channel: str, platform: str = "twitch") -> None:
        if channel:
            if platform == "kick":
                webbrowser.open(f"https://kick.com/{channel}")
            elif platform == "youtube":
                webbrowser.open(f"https://youtube.com/channel/{channel}")
            else:
                webbrowser.open(f"https://twitch.tv/{channel}")
```

- [ ] **Step 9: Update `_sanitize_channel_name` for YouTube**

```python
    @staticmethod
    def _sanitize_channel_name(raw: str, platform: str = "twitch") -> str:
        raw = raw.strip()
        if platform == "youtube":
            # youtube.com/channel/UCxxxx
            match = re.search(
                r"youtube\.com/channel/(UC[\w-]{22})", raw, re.IGNORECASE
            )
            if match:
                return match.group(1)
            # Raw channel ID
            clean = re.sub(r"[^A-Za-z0-9_-]", "", raw)
            if re.match(r"^UC[\w-]{22}$", clean):
                return clean
            return ""  # Invalid — use search to add YouTube channels
        if platform == "kick":
            match = re.search(r"(?:kick\.com/)([A-Za-z0-9_-]+)", raw, re.IGNORECASE)
            if match:
                return match.group(1).lower()
            return re.sub(r"[^A-Za-z0-9_-]", "", raw).lower()
        return TwitchXApi._sanitize_username(raw)
```

- [ ] **Step 10: Commit**

```bash
git add ui/api.py
git commit -m "feat(youtube): integrate YouTube into fetch, search, playback, and import"
```

---

### Task 10: index.html — YouTube settings tab

Add a "YouTube" tab to the settings modal with fields for API Key, Client ID, Client Secret, login button, import subscriptions, and quota display.

**Files:**
- Modify: `ui/index.html`

- [ ] **Step 1: Add YouTube settings tab button**

After the Kick settings tab button (`<button class="settings-tab" data-tab="kick">Kick</button>`), add:

```html
      <button class="settings-tab" data-tab="youtube">YouTube</button>
```

- [ ] **Step 2: Add YouTube settings panel HTML**

After the `settings-panel-kick` div closing tag (`</div>`) and before the `settings-feedback` div, add:

```html
    <!-- YouTube panel -->
    <div class="settings-panel" id="settings-panel-youtube">
      <div class="setting-group">
        <label>YouTube API Key</label>
        <div class="secret-row">
          <input id="s-youtube-api-key" type="password" autocomplete="off">
          <button class="eye-btn" id="youtube-key-eye-toggle-btn">&#128065;</button>
        </div>
      </div>
      <div class="setting-group">
        <label>YouTube Client ID (for login)</label>
        <input id="s-youtube-client-id" type="text" autocomplete="off">
      </div>
      <div class="setting-group">
        <label>YouTube Client Secret (for login)</label>
        <div class="secret-row">
          <input id="s-youtube-client-secret" type="password" autocomplete="off">
          <button class="eye-btn" id="youtube-secret-eye-toggle-btn">&#128065;</button>
        </div>
      </div>
      <div class="oauth-note">
        Requires a Google Cloud project with YouTube Data API v3 enabled.<br>
        API Key: needed for stream checking and search.<br>
        Client ID + Secret: needed for login and subscription import.<br>
        Redirect URI: http://localhost:3457/callback
      </div>
      <div id="youtube-login-area" class="setting-group">
        <button id="youtube-login-btn" style="width:100%;height:36px;background:#FF0000;color:white;border:none;border-radius:var(--radius-sm);font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;">Login with YouTube</button>
      </div>
      <div id="youtube-user-area" class="setting-group" style="display:none;">
        <div id="youtube-user-display" style="font-size:13px;color:var(--text-primary);margin-bottom:4px;"></div>
        <div id="youtube-quota-display" style="font-size:12px;color:var(--text-muted);margin-bottom:8px;"></div>
        <button id="youtube-import-subs-btn" style="width:100%;height:30px;background:var(--bg-elevated);color:var(--text-primary);border:1px solid var(--border);border-radius:var(--radius-sm);font-size:12px;cursor:pointer;font-family:inherit;margin-bottom:8px;">Import Subscriptions</button>
        <a id="youtube-logout-settings-link" style="font-size:12px;color:var(--text-muted);cursor:pointer;text-decoration:none;">Logout from YouTube</a>
      </div>
      <div class="settings-btns">
        <button id="youtube-test-btn">Test YouTube Connection</button>
      </div>
    </div>
```

- [ ] **Step 3: Add YouTube JS event handlers**

In the `DOMContentLoaded` event listener, add after the Kick event handlers:

```javascript
  // YouTube eye toggles
  document.getElementById('youtube-key-eye-toggle-btn').addEventListener('click', function() {
    var input = document.getElementById('s-youtube-api-key');
    input.type = input.type === 'password' ? 'text' : 'password';
  });
  document.getElementById('youtube-secret-eye-toggle-btn').addEventListener('click', function() {
    var input = document.getElementById('s-youtube-client-secret');
    input.type = input.type === 'password' ? 'text' : 'password';
  });

  // YouTube login
  document.getElementById('youtube-login-btn').addEventListener('click', function() {
    var cid = document.getElementById('s-youtube-client-id').value.trim();
    var cs = document.getElementById('s-youtube-client-secret').value.trim();
    if (!cid || !cs) {
      var fb = document.getElementById('settings-feedback');
      fb.textContent = 'YouTube Client ID and Secret are required for login';
      fb.style.color = 'var(--error-red)';
      return;
    }
    if (api) api.youtube_login();
  });

  // YouTube logout
  document.getElementById('youtube-logout-settings-link').addEventListener('click', function() {
    if (api) api.youtube_logout();
  });

  // YouTube import subscriptions
  document.getElementById('youtube-import-subs-btn').addEventListener('click', function() {
    if (api) api.youtube_import_follows();
  });

  // YouTube test connection
  document.getElementById('youtube-test-btn').addEventListener('click', function() {
    var key = document.getElementById('s-youtube-api-key').value.trim();
    if (!key) {
      var fb = document.getElementById('settings-feedback');
      fb.textContent = 'YouTube API Key is required';
      fb.style.color = 'var(--error-red)';
      return;
    }
    document.getElementById('youtube-test-btn').disabled = true;
    document.getElementById('settings-feedback').textContent = 'Testing YouTube...';
    document.getElementById('settings-feedback').style.color = 'var(--text-muted)';
    api.youtube_test_connection(key);
  });
```

- [ ] **Step 4: Add YouTube JS callbacks**

Add these window callbacks alongside the existing Kick callbacks:

```javascript
window.onYouTubeLoginComplete = function(data) {
  document.getElementById('youtube-login-area').style.display = 'none';
  document.getElementById('youtube-user-area').style.display = 'block';
  document.getElementById('youtube-user-display').textContent = 'Logged in as ' + data.display_name;
  var fb = document.getElementById('settings-feedback');
  fb.textContent = 'YouTube login successful';
  fb.style.color = 'var(--live-green)';
};

window.onYouTubeLoginError = function(msg) {
  var fb = document.getElementById('settings-feedback');
  fb.textContent = 'YouTube: ' + msg;
  fb.style.color = 'var(--error-red)';
};

window.onYouTubeNeedsCredentials = function() {
  var fb = document.getElementById('settings-feedback');
  fb.textContent = 'YouTube Client ID and Secret are required for login';
  fb.style.color = 'var(--error-red)';
  showSettingsTab('youtube');
};

window.onYouTubeLogout = function() {
  document.getElementById('youtube-login-area').style.display = 'block';
  document.getElementById('youtube-user-area').style.display = 'none';
  document.getElementById('youtube-user-display').textContent = '';
};

window.onYouTubeTestResult = function(data) {
  document.getElementById('youtube-test-btn').disabled = false;
  var fb = document.getElementById('settings-feedback');
  fb.textContent = data.success ? 'YouTube: ' + data.message : 'YouTube: ' + data.message;
  fb.style.color = data.success ? 'var(--live-green)' : 'var(--error-red)';
};

window.onYouTubeImportComplete = function(data) {
  var fb = document.getElementById('settings-feedback');
  fb.textContent = 'Imported ' + data.added + ' YouTube subscriptions';
  fb.style.color = 'var(--live-green)';
};

window.onYouTubeImportError = function(msg) {
  var fb = document.getElementById('settings-feedback');
  fb.textContent = 'YouTube import: ' + msg;
  fb.style.color = 'var(--error-red)';
};
```

- [ ] **Step 5: Update settings population to include YouTube fields**

In the function that populates settings fields on modal open (look for where `s-kick-client-id` is populated), add:

```javascript
    document.getElementById('s-youtube-api-key').value = config.youtube_api_key || '';
    document.getElementById('s-youtube-client-id').value = config.youtube_client_id || '';
    document.getElementById('s-youtube-client-secret').value = config.youtube_client_secret || '';
    // YouTube user state
    if (config.youtube_display_name) {
      document.getElementById('youtube-login-area').style.display = 'none';
      document.getElementById('youtube-user-area').style.display = 'block';
      document.getElementById('youtube-user-display').textContent = 'Logged in as ' + config.youtube_display_name;
      document.getElementById('youtube-quota-display').textContent = 'Quota remaining: ' + (config.youtube_quota_remaining || 0) + ' / 10,000';
    } else {
      document.getElementById('youtube-login-area').style.display = 'block';
      document.getElementById('youtube-user-area').style.display = 'none';
    }
```

Update the save settings function to include YouTube fields:

```javascript
      youtube_api_key: document.getElementById('s-youtube-api-key').value.trim(),
      youtube_client_id: document.getElementById('s-youtube-client-id').value.trim(),
      youtube_client_secret: document.getElementById('s-youtube-client-secret').value.trim(),
```

- [ ] **Step 6: Commit**

```bash
git add ui/index.html
git commit -m "feat(youtube): add YouTube settings tab with API key, OAuth, and quota display"
```

---

### Task 11: index.html — YouTube platform tab + YouTube badge on cards

Add YouTube to the platform filter tabs in the sidebar and show a YouTube badge on stream cards.

**Files:**
- Modify: `ui/index.html`

- [ ] **Step 1: Add YouTube platform tab button**

After the Kick platform tab button, add:

```html
        <button class="platform-tab" data-platform="youtube">YouTube</button>
```

- [ ] **Step 2: Add YouTube badge styling**

In the CSS section where `.platform-badge` or Kick badge styles are defined, ensure YouTube streams show a red YouTube badge. Find where the platform badge logic is in the `renderGrid` or card creation JS, and add a YouTube case:

```javascript
    // In the card creation function, where platform badge is set:
    if (stream.platform === 'youtube') {
      badge.textContent = 'YT';
      badge.style.background = '#FF0000';
    }
```

- [ ] **Step 3: Update platform filter logic for YouTube**

The existing platform filter JS compares `stream.platform`. Since YouTube streams have `platform: "youtube"`, the filter should work automatically with the existing `data-platform="youtube"` attribute. Verify the `getFilteredSortedStreams` function filters correctly — it should already work since it compares `stream.platform === activePlatformFilter`.

- [ ] **Step 4: Commit**

```bash
git add ui/index.html
git commit -m "feat(youtube): add YouTube platform tab and stream card badge"
```

---

### Task 12: index.html — YouTube iframe embed in player-view

When a YouTube stream is selected, show an iframe instead of the `<video>` element. Hide the native video and show the YouTube iframe. Reverse on stop.

**Files:**
- Modify: `ui/index.html`

- [ ] **Step 1: Add YouTube iframe container to player-content**

In the `#player-content` div, after the `<video>` element, add:

```html
          <iframe id="youtube-embed" style="display:none; flex:1; min-width:0; border:none; background:#000;" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>
```

- [ ] **Step 2: Update `onStreamReady` to handle YouTube embed**

Replace the existing `window.onStreamReady` with:

```javascript
window.onStreamReady = function(data) {
  var video = document.getElementById('stream-video');
  var ytEmbed = document.getElementById('youtube-embed');

  if (data.playback_type === 'youtube_embed') {
    // Hide native video, show YouTube iframe
    video.style.display = 'none';
    video.pause();
    video.removeAttribute('src');
    ytEmbed.src = 'https://www.youtube.com/embed/' + data.url + '?autoplay=1&playsinline=1';
    ytEmbed.style.display = 'block';
  } else {
    // HLS playback (Twitch/Kick)
    ytEmbed.style.display = 'none';
    ytEmbed.removeAttribute('src');
    video.style.display = 'block';
    video.src = data.url;
    video.play();
  }
  state.playerPlatform = data.platform || 'twitch';
  document.getElementById('player-channel-name').textContent = data.channel;
  document.getElementById('player-stream-title').textContent = data.title || '';
  showPlayerView();
};
```

- [ ] **Step 3: Update `onPlayerStop` and `hidePlayerView` to clean up iframe**

```javascript
window.onPlayerStop = function() {
  hidePlayerView();
};
```

In the `hidePlayerView` function, add iframe cleanup:

```javascript
function hidePlayerView() {
  var video = document.getElementById('stream-video');
  var ytEmbed = document.getElementById('youtube-embed');
  video.pause();
  video.removeAttribute('src');
  video.style.display = 'block';
  ytEmbed.removeAttribute('src');
  ytEmbed.style.display = 'none';
  // ... rest of existing hidePlayerView logic
```

- [ ] **Step 4: Update fullscreen toggle to handle iframe**

In the `toggleVideoFullscreen` function, check which element is active:

```javascript
function toggleVideoFullscreen() {
  var ytEmbed = document.getElementById('youtube-embed');
  var target = ytEmbed.style.display !== 'none' ? ytEmbed : document.getElementById('stream-video');
  if (document.fullscreenElement) {
    document.exitFullscreen();
  } else {
    target.requestFullscreen();
  }
}
```

- [ ] **Step 5: Disable IINA button for YouTube streams**

In the watch-external button handler, check platform:

```javascript
  document.getElementById('watch-external-btn').addEventListener('click', function() {
    if (!state.selectedChannel || !api) return;
    if (state.playerPlatform === 'youtube') {
      // IINA doesn't work with YouTube (ToS prohibits custom playback)
      return;
    }
    var quality = document.getElementById('quality-select').value;
    api.watch_external(state.selectedChannel, quality);
  });
```

- [ ] **Step 6: Commit**

```bash
git add ui/index.html
git commit -m "feat(youtube): add iframe embed playback for YouTube streams"
```

---

### Task 13: Lint, test, and final verification

Run the full test suite and linter to ensure everything works together.

**Files:** All modified files

- [ ] **Step 1: Run linter**

Run: `make lint`
Expected: No errors. Fix any issues found.

- [ ] **Step 2: Run full test suite**

Run: `make test`
Expected: All tests pass (existing 57 + new YouTube tests).

- [ ] **Step 3: Run format check**

Run: `make fmt`

- [ ] **Step 4: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix(youtube): resolve lint and test issues from Phase 4"
```

---

## Google Cloud Setup Guide (for the user)

To use YouTube features, you need a Google Cloud project:

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Enable **YouTube Data API v3** in APIs & Services → Library
4. Create an **API Key** in APIs & Services → Credentials → Create Credentials → API Key
5. (Optional, for login) Create **OAuth 2.0 Client ID**:
   - Application type: **Web application**
   - Authorized redirect URI: `http://localhost:3457/callback`
6. Enter the API Key in TwitchX Settings → YouTube tab
7. (Optional) Enter Client ID + Secret for login/subscription import
