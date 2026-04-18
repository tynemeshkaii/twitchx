# Phase 5: Browse — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a browse view where users see categories aggregated from Twitch, Kick, and YouTube, filter by platform, and drill into live streams per category.

**Architecture:** `get_categories()` and `get_top_streams()` added to each platform client; a module-level `_aggregate_categories()` in `ui/api.py` merges results by normalized name; a 10-minute per-platform cache in `~/.config/twitchx/cache/browse_cache.json` protects expensive YouTube `search.list` calls; browse UI is a hidden `#browse-view` div toggled over the stream grid, with its own platform tabs and two-level navigation (categories grid → streams grid → back); a new `watch_direct(channel, platform, quality)` api method bypasses the `watch()` live-check gate for channels opened from browse.

**YouTube limitation:** `search.list` returns `channelId` but not `video_id`, so YouTube stream cards in browse are display-only in this phase. Twitch and Kick stream cards are fully watchable.

**Tech Stack:** Python + httpx (existing); pywebview JS bridge (existing); vanilla JS + CSS custom properties (existing); pytest + unittest.mock (existing test suite).

---

## File Map

**Create:**
- `tests/test_browse_cache.py` — browse cache helper tests
- `tests/platforms/test_twitch_browse.py` — `get_categories` + `get_top_streams` tests
- `tests/platforms/test_kick_browse.py` — normalized `get_categories` + `get_top_streams` tests
- `tests/platforms/test_youtube_browse.py` — `get_categories` + `get_top_streams` tests
- `tests/test_browse_api.py` — `_aggregate_categories` tests

**Modify:**
- `core/storage.py` — add `BROWSE_CACHE_TTL`, `load_browse_cache()`, `save_browse_cache()`, `is_browse_slot_fresh()`
- `core/platforms/twitch.py` — add `get_categories()`, `get_top_streams()`
- `core/platforms/kick.py` — normalize `get_categories()` return format, add `get_top_streams()`
- `core/platforms/youtube.py` — add `get_categories()`, `get_top_streams()`
- `ui/api.py` — add imports, module-level `_aggregate_categories()`, `get_browse_categories()`, `_fetch_browse_categories()`, `get_browse_top_streams()`, `_fetch_browse_top_streams()`, `watch_direct()`
- `ui/index.html` — add `#browse-view` HTML, CSS, sidebar Browse button, JS navigation functions, `window.onBrowseCategories`, `window.onBrowseTopStreams`

---

## Task 1: Browse cache helpers in `core/storage.py`

**Files:**
- Modify: `core/storage.py`
- Test: `tests/test_browse_cache.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_browse_cache.py`:

```python
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

from core.storage import is_browse_slot_fresh, load_browse_cache, save_browse_cache


def test_load_browse_cache_returns_empty_when_file_missing(tmp_path: Path) -> None:
    with patch("core.storage.CONFIG_DIR", tmp_path):
        result = load_browse_cache()
    assert result == {}


def test_load_browse_cache_returns_data_when_file_exists(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    data = {"categories_twitch": {"data": [{"name": "Fortnite"}], "fetched_at": 1000.0}}
    (cache_dir / "browse_cache.json").write_text(json.dumps(data))
    with patch("core.storage.CONFIG_DIR", tmp_path):
        result = load_browse_cache()
    assert result == data


def test_load_browse_cache_returns_empty_on_corrupt_json(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "browse_cache.json").write_text("NOT_JSON{{{")
    with patch("core.storage.CONFIG_DIR", tmp_path):
        result = load_browse_cache()
    assert result == {}


def test_save_browse_cache_creates_dirs_and_writes(tmp_path: Path) -> None:
    data = {"categories_kick": {"data": [], "fetched_at": 9999.0}}
    with patch("core.storage.CONFIG_DIR", tmp_path):
        save_browse_cache(data)
    written = json.loads((tmp_path / "cache" / "browse_cache.json").read_text())
    assert written == data


def test_is_browse_slot_fresh_true_within_ttl() -> None:
    cache = {"categories_twitch": {"data": [], "fetched_at": time.time() - 100}}
    assert is_browse_slot_fresh(cache, "categories_twitch", ttl=600) is True


def test_is_browse_slot_fresh_false_when_expired() -> None:
    cache = {"categories_twitch": {"data": [], "fetched_at": time.time() - 700}}
    assert is_browse_slot_fresh(cache, "categories_twitch", ttl=600) is False


def test_is_browse_slot_fresh_false_when_slot_missing() -> None:
    assert is_browse_slot_fresh({}, "categories_twitch") is False
```

- [ ] **Step 2: Run tests — expect failures**

```bash
uv run pytest tests/test_browse_cache.py -v
```
Expected: `ImportError` — functions not yet defined.

- [ ] **Step 3: Implement browse cache helpers**

Append to `core/storage.py` (after the avatar cache block at the end of the file):

```python
# ── Browse cache ──────────────────────────────────────────────

BROWSE_CACHE_TTL = 600  # 10 minutes


def load_browse_cache() -> dict[str, Any]:
    """Load browse cache from disk. Returns {} on cache miss or parse error."""
    try:
        path = CONFIG_DIR / "cache" / "browse_cache.json"
        return json.loads(path.read_text()) if path.exists() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_browse_cache(data: dict[str, Any]) -> None:
    """Persist browse cache to disk, creating directories as needed."""
    path = CONFIG_DIR / "cache" / "browse_cache.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def is_browse_slot_fresh(
    cache: dict[str, Any], slot_key: str, ttl: int = BROWSE_CACHE_TTL
) -> bool:
    """Return True if the named cache slot exists and is within ttl seconds old."""
    return time.time() - cache.get(slot_key, {}).get("fetched_at", 0) < ttl
```

Note: `json`, `time`, `Any`, and `CONFIG_DIR` are already imported/defined in `storage.py`. The inline `path` variable (rather than a module-level constant) avoids breaking the `patch("core.storage.CONFIG_DIR", ...)` test pattern.

- [ ] **Step 4: Run tests — expect all pass**

```bash
uv run pytest tests/test_browse_cache.py -v
```
Expected: 7 PASSED.

- [ ] **Step 5: Run full suite — expect no regressions**

```bash
make test
```

- [ ] **Step 6: Commit**

```bash
git add core/storage.py tests/test_browse_cache.py
git commit -m "feat(browse): add browse cache helpers to storage"
```

---

## Task 2: Twitch `get_categories()` and `get_top_streams()`

**Files:**
- Modify: `core/platforms/twitch.py`
- Test: `tests/platforms/test_twitch_browse.py`

- [ ] **Step 1: Write failing tests**

Create `tests/platforms/test_twitch_browse.py`:

```python
from __future__ import annotations

import asyncio
from unittest.mock import patch

from core.platforms.twitch import TwitchClient


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def test_get_categories_normalizes_format() -> None:
    client = TwitchClient()
    mock_data = {
        "data": [
            {
                "id": "33214",
                "name": "Fortnite",
                "box_art_url": "https://img/{width}x{height}.jpg",
                "igdb_id": "1905",
            }
        ]
    }
    with patch.object(client, "_get", return_value=mock_data):
        result = _run(client.get_categories())
    assert len(result) == 1
    cat = result[0]
    assert cat["platform"] == "twitch"
    assert cat["category_id"] == "33214"
    assert cat["name"] == "Fortnite"
    assert "{width}" not in cat["box_art_url"]
    assert "{height}" not in cat["box_art_url"]
    assert cat["viewers"] == 0


def test_get_categories_no_query_uses_games_top() -> None:
    client = TwitchClient()
    with patch.object(client, "_get", return_value={"data": []}) as mock_get:
        _run(client.get_categories())
    endpoint = mock_get.call_args[0][0]
    assert endpoint == "/games/top"


def test_get_top_streams_normalizes_format() -> None:
    client = TwitchClient()
    mock_data = {
        "data": [
            {
                "user_id": "12345",
                "user_login": "xqc",
                "user_name": "xQc",
                "title": "Playing games",
                "game_name": "Fortnite",
                "game_id": "33214",
                "viewer_count": 50000,
                "started_at": "2026-04-15T10:00:00Z",
                "thumbnail_url": "https://img/{width}x{height}.jpg",
            }
        ]
    }
    with patch.object(client, "_get", return_value=mock_data):
        result = _run(client.get_top_streams())
    assert len(result) == 1
    s = result[0]
    assert s["platform"] == "twitch"
    assert s["channel_login"] == "xqc"
    assert s["display_name"] == "xQc"
    assert s["viewers"] == 50000
    assert "{width}" not in s["thumbnail_url"]


def test_get_top_streams_with_category_passes_game_id() -> None:
    client = TwitchClient()
    with patch.object(client, "_get", return_value={"data": []}) as mock_get:
        _run(client.get_top_streams(category_id="33214"))
    params = mock_get.call_args[0][1]  # list of tuples
    assert ("game_id", "33214") in params
```

- [ ] **Step 2: Run tests — expect failures**

```bash
uv run pytest tests/platforms/test_twitch_browse.py -v
```
Expected: `AttributeError: 'TwitchClient' object has no attribute 'get_categories'`

- [ ] **Step 3: Implement methods**

Append to `core/platforms/twitch.py` (inside the `TwitchClient` class, after `search_channels`):

```python
    async def get_categories(
        self, query: str | None = None
    ) -> list[dict[str, Any]]:
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
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
uv run pytest tests/platforms/test_twitch_browse.py -v
```
Expected: 4 PASSED.

- [ ] **Step 5: Run full suite**

```bash
make test
```

- [ ] **Step 6: Commit**

```bash
git add core/platforms/twitch.py tests/platforms/test_twitch_browse.py
git commit -m "feat(browse): add get_categories and get_top_streams to TwitchClient"
```

---

## Task 3: Kick normalized `get_categories()` and `get_top_streams()`

**Files:**
- Modify: `core/platforms/kick.py`
- Test: `tests/platforms/test_kick_browse.py`

- [ ] **Step 1: Write failing tests**

Create `tests/platforms/test_kick_browse.py`:

```python
from __future__ import annotations

import asyncio
from unittest.mock import patch

from core.platforms.kick import KickClient


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def test_get_categories_returns_normalized_format() -> None:
    client = KickClient()
    mock_data = {
        "data": [
            {
                "id": 15,
                "name": "Just Chatting",
                "slug": "just-chatting",
                "banner": "https://kick.com/banner.jpg",
                "viewers_count": 80000,
            }
        ]
    }
    with patch.object(client, "_get", return_value=mock_data):
        result = _run(client.get_categories())
    assert len(result) == 1
    cat = result[0]
    assert cat["platform"] == "kick"
    assert cat["category_id"] == "15"
    assert cat["name"] == "Just Chatting"
    assert cat["box_art_url"] == "https://kick.com/banner.jpg"
    assert cat["viewers"] == 80000


def test_get_top_streams_returns_normalized_format() -> None:
    client = KickClient()
    mock_data = {
        "data": [
            {
                "channel": {
                    "id": 99,
                    "slug": "trainwreckstv",
                    "user": {
                        "username": "Trainwreckstv",
                        "profile_pic": "https://kick.com/pic.jpg",
                    },
                },
                "session_title": "SLOTS!",
                "categories": [{"id": 15, "name": "Slots & Casino"}],
                "viewer_count": 20000,
                "created_at": "2026-04-15T10:00:00Z",
                "thumbnail": {"src": "https://kick.com/thumb.jpg"},
            }
        ]
    }
    with patch.object(client, "_get", return_value=mock_data):
        result = _run(client.get_top_streams())
    assert len(result) == 1
    s = result[0]
    assert s["platform"] == "kick"
    assert s["channel_login"] == "trainwreckstv"
    assert s["display_name"] == "Trainwreckstv"
    assert s["viewers"] == 20000
    assert s["avatar_url"] == "https://kick.com/pic.jpg"


def test_get_top_streams_with_category_id_passes_param() -> None:
    client = KickClient()
    with patch.object(client, "_get", return_value={"data": []}) as mock_get:
        _run(client.get_top_streams(category_id="15"))
    params = mock_get.call_args[0][1]  # second positional arg
    param_dict = dict(params) if isinstance(params, list) else params
    assert param_dict.get("category_id") == "15"
```

- [ ] **Step 2: Run tests — expect failures**

```bash
uv run pytest tests/platforms/test_kick_browse.py -v
```
Expected: `AssertionError` — `platform` key absent in current raw return.

- [ ] **Step 3: Normalize `get_categories()` and add `get_top_streams()`**

In `core/platforms/kick.py`, replace the existing `get_categories` method (currently around line 444):

```python
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
```

Then append `get_top_streams` directly after `get_categories`:

```python
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
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
uv run pytest tests/platforms/test_kick_browse.py -v
```
Expected: 3 PASSED.

- [ ] **Step 5: Run full suite — confirm existing Kick tests still pass**

```bash
make test
```

- [ ] **Step 6: Commit**

```bash
git add core/platforms/kick.py tests/platforms/test_kick_browse.py
git commit -m "feat(browse): normalize get_categories and add get_top_streams to KickClient"
```

---

## Task 4: YouTube `get_categories()` and `get_top_streams()`

**Files:**
- Modify: `core/platforms/youtube.py`
- Test: `tests/platforms/test_youtube_browse.py`

- [ ] **Step 1: Write failing tests**

Create `tests/platforms/test_youtube_browse.py`:

```python
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from core.platforms.youtube import YouTubeClient


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def test_get_categories_filters_unassignable() -> None:
    client = YouTubeClient()
    mock_items = [
        {"id": "20", "snippet": {"title": "Gaming", "assignable": True}},
        {"id": "0", "snippet": {"title": "Film & Animation", "assignable": False}},
        {"id": "24", "snippet": {"title": "Entertainment", "assignable": True}},
    ]
    with (
        patch.object(client, "_ensure_token", return_value="tok"),
        patch.object(client._quota, "check_and_use", return_value=True),
        patch.object(client, "_yt_get", return_value={"items": mock_items}),
    ):
        result = _run(client.get_categories())
    assert len(result) == 2
    ids = {c["category_id"] for c in result}
    assert ids == {"20", "24"}
    assert result[0]["platform"] == "youtube"
    assert result[0]["box_art_url"] == ""
    assert result[0]["viewers"] == 0


def test_get_categories_returns_empty_when_no_token() -> None:
    client = YouTubeClient()
    with patch.object(client, "_ensure_token", return_value=None):
        result = _run(client.get_categories())
    assert result == []


def test_get_categories_returns_empty_when_quota_exhausted() -> None:
    client = YouTubeClient()
    with (
        patch.object(client, "_ensure_token", return_value="tok"),
        patch.object(client._quota, "check_and_use", return_value=False),
    ):
        result = _run(client.get_categories())
    assert result == []


def test_get_top_streams_costs_100_quota_units() -> None:
    client = YouTubeClient()
    quota_spy = MagicMock(return_value=True)
    with (
        patch.object(client, "_ensure_token", return_value="tok"),
        patch.object(client._quota, "check_and_use", quota_spy),
        patch.object(client, "_yt_get", return_value={"items": []}),
    ):
        _run(client.get_top_streams())
    quota_spy.assert_called_once_with(100)


def test_get_top_streams_returns_empty_when_quota_exhausted() -> None:
    client = YouTubeClient()
    with (
        patch.object(client, "_ensure_token", return_value="tok"),
        patch.object(client._quota, "check_and_use", return_value=False),
    ):
        result = _run(client.get_top_streams())
    assert result == []


def test_get_top_streams_normalizes_format() -> None:
    client = YouTubeClient()
    mock_items = [
        {
            "snippet": {
                "channelId": "UCxyz",
                "channelTitle": "SomeChannel",
                "title": "Live stream title",
                "publishedAt": "2026-04-15T10:00:00Z",
                "thumbnails": {
                    "medium": {"url": "https://img.youtube.com/vi/abc/mqdefault.jpg"}
                },
            }
        }
    ]
    with (
        patch.object(client, "_ensure_token", return_value="tok"),
        patch.object(client._quota, "check_and_use", return_value=True),
        patch.object(client, "_yt_get", return_value={"items": mock_items}),
    ):
        result = _run(client.get_top_streams(category_id="20"))
    assert len(result) == 1
    s = result[0]
    assert s["platform"] == "youtube"
    assert s["channel_id"] == "UCxyz"
    assert s["display_name"] == "SomeChannel"
    assert s["viewers"] == 0
    assert s["category_id"] == "20"
```

- [ ] **Step 2: Run tests — expect failures**

```bash
uv run pytest tests/platforms/test_youtube_browse.py -v
```
Expected: `AttributeError: 'YouTubeClient' object has no attribute 'get_categories'`

- [ ] **Step 3: Implement methods**

Append to `core/platforms/youtube.py` inside `YouTubeClient`, before the `close()` method:

```python
    async def get_categories(
        self, query: str | None = None
    ) -> list[dict[str, Any]]:
        """Return assignable YouTube video categories for US region.

        query is ignored — YouTube categories are a fixed regional list.
        Costs 1 quota unit. Returns [] if unauthenticated or quota exhausted.
        """
        token = await self._ensure_token()
        if not token:
            return []
        if not self._quota.check_and_use(1):
            return []
        data = await self._yt_get(
            "videoCategories",
            {"part": "snippet", "regionCode": "US"},
        )
        return [
            {
                "platform": "youtube",
                "category_id": item["id"],
                "name": item["snippet"]["title"],
                "box_art_url": "",
                "viewers": 0,
            }
            for item in data.get("items", [])
            if item.get("snippet", {}).get("assignable", False)
        ]

    async def get_top_streams(
        self,
        category_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for live YouTube streams using search.list.

        Costs 100 quota units per call. Returns [] if unauthenticated or quota
        exhausted. viewer counts are 0 (search.list does not return them).
        avatar_url is empty (requires a separate channels.list call).
        """
        token = await self._ensure_token()
        if not token:
            return []
        if not self._quota.check_and_use(100):
            return []
        params: dict[str, str] = {
            "part": "snippet",
            "type": "video",
            "eventType": "live",
            "maxResults": str(min(limit, 50)),
            "order": "viewCount",
        }
        if category_id:
            params["videoCategoryId"] = category_id
        data = await self._yt_get("search", params)
        return [
            {
                "platform": "youtube",
                "channel_id": item["snippet"]["channelId"],
                "channel_login": item["snippet"]["channelId"],
                "display_name": item["snippet"]["channelTitle"],
                "title": item["snippet"]["title"],
                "category": "",
                "category_id": category_id or "",
                "viewers": 0,
                "started_at": item["snippet"].get("publishedAt", ""),
                "thumbnail_url": item["snippet"]
                    .get("thumbnails", {})
                    .get("medium", {})
                    .get("url", ""),
                "avatar_url": "",
            }
            for item in data.get("items", [])
        ]
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
uv run pytest tests/platforms/test_youtube_browse.py -v
```
Expected: 6 PASSED.

- [ ] **Step 5: Run full suite**

```bash
make test
```

- [ ] **Step 6: Commit**

```bash
git add core/platforms/youtube.py tests/platforms/test_youtube_browse.py
git commit -m "feat(browse): add get_categories and get_top_streams to YouTubeClient"
```

---

## Task 5: Browse API in `ui/api.py`

**Files:**
- Modify: `ui/api.py`
- Test: `tests/test_browse_api.py`

- [ ] **Step 1: Write failing tests for `_aggregate_categories`**

Create `tests/test_browse_api.py`:

```python
from __future__ import annotations

from ui.api import _aggregate_categories


def test_merges_categories_with_same_name() -> None:
    by_platform = {
        "twitch": [
            {"platform": "twitch", "category_id": "33214", "name": "Fortnite",
             "box_art_url": "https://img.jpg", "viewers": 0}
        ],
        "kick": [
            {"platform": "kick", "category_id": "42", "name": "Fortnite",
             "box_art_url": "", "viewers": 0}
        ],
    }
    result = _aggregate_categories(by_platform)
    assert len(result) == 1
    assert result[0]["name"] == "Fortnite"
    assert set(result[0]["platforms"]) == {"twitch", "kick"}
    assert result[0]["platform_ids"]["twitch"] == "33214"
    assert result[0]["platform_ids"]["kick"] == "42"


def test_keeps_distinct_names_separate() -> None:
    by_platform = {
        "twitch": [
            {"platform": "twitch", "category_id": "1", "name": "Fortnite",
             "box_art_url": "", "viewers": 0},
            {"platform": "twitch", "category_id": "2", "name": "Minecraft",
             "box_art_url": "", "viewers": 0},
        ],
    }
    result = _aggregate_categories(by_platform)
    assert {r["name"] for r in result} == {"Fortnite", "Minecraft"}


def test_merges_case_insensitively() -> None:
    by_platform = {
        "twitch": [
            {"platform": "twitch", "category_id": "1", "name": "Just Chatting",
             "box_art_url": "", "viewers": 0}
        ],
        "kick": [
            {"platform": "kick", "category_id": "9", "name": "just chatting",
             "box_art_url": "", "viewers": 0}
        ],
    }
    result = _aggregate_categories(by_platform)
    assert len(result) == 1


def test_prefers_first_nonempty_box_art_url() -> None:
    by_platform = {
        "twitch": [
            {"platform": "twitch", "category_id": "1", "name": "Fortnite",
             "box_art_url": "https://twitch.jpg", "viewers": 0}
        ],
        "youtube": [
            {"platform": "youtube", "category_id": "20", "name": "Fortnite",
             "box_art_url": "", "viewers": 0}
        ],
    }
    result = _aggregate_categories(by_platform)
    assert result[0]["box_art_url"] == "https://twitch.jpg"


def test_sorts_by_viewers_descending() -> None:
    by_platform = {
        "kick": [
            {"platform": "kick", "category_id": "1", "name": "Fortnite",
             "box_art_url": "", "viewers": 100},
            {"platform": "kick", "category_id": "2", "name": "Minecraft",
             "box_art_url": "", "viewers": 500},
        ]
    }
    result = _aggregate_categories(by_platform)
    assert result[0]["name"] == "Minecraft"
    assert result[1]["name"] == "Fortnite"
```

- [ ] **Step 2: Run tests — expect import failure**

```bash
uv run pytest tests/test_browse_api.py -v
```
Expected: `ImportError: cannot import name '_aggregate_categories' from 'ui.api'`

- [ ] **Step 3: Add imports and `_aggregate_categories` to `ui/api.py`**

In `ui/api.py`, extend the existing `from core.storage import ...` line to also import:

```python
from core.storage import (
    # ... existing imports ...,
    is_browse_slot_fresh,
    load_browse_cache,
    save_browse_cache,
)
```

Add the module-level function immediately **before** the `TwitchXApi` class definition:

```python
def _aggregate_categories(
    by_platform: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Merge category lists from multiple platforms by normalized name.

    Categories with the same lowercased name are merged. Viewer counts are
    summed. The first non-empty box_art_url encountered is kept.
    Result is sorted by total viewers descending.
    """
    merged: dict[str, dict[str, Any]] = {}
    for platform, categories in by_platform.items():
        for cat in categories:
            key = cat["name"].lower().strip()
            if not key:
                continue
            if key not in merged:
                merged[key] = {
                    "name": cat["name"],
                    "platforms": [],
                    "platform_ids": {},
                    "box_art_url": "",
                    "viewers": 0,
                }
            entry = merged[key]
            entry["platforms"].append(platform)
            entry["platform_ids"][platform] = cat["category_id"]
            entry["viewers"] += cat.get("viewers", 0)
            if not entry["box_art_url"] and cat.get("box_art_url"):
                entry["box_art_url"] = cat["box_art_url"]
    return sorted(merged.values(), key=lambda x: x["viewers"], reverse=True)
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
uv run pytest tests/test_browse_api.py -v
```
Expected: 5 PASSED.

- [ ] **Step 5: Add browse API methods and `watch_direct` to `TwitchXApi`**

Append to the `TwitchXApi` class in `ui/api.py` (after `watch_external`, before `close`):

```python
    # ── Browse ─────────────────────────────────────────────────

    def get_browse_categories(self, platform_filter: str = "all") -> None:
        """Fetch and aggregate browse categories from enabled platforms.

        Called from JS. Fires window.onBrowseCategories(categories) when done.
        platform_filter: "all" | "twitch" | "kick" | "youtube"
        """
        self._run_in_thread(lambda: self._fetch_browse_categories(platform_filter))

    def _fetch_browse_categories(self, platform_filter: str) -> None:
        platforms = (
            ["twitch", "kick", "youtube"]
            if platform_filter == "all"
            else [platform_filter]
        )
        self._config = load_config()
        enabled = [
            p for p in platforms
            if self._config.get("platforms", {}).get(p, {}).get("enabled", False)
        ]
        cache = load_browse_cache()
        now = time.time()
        results: dict[str, list[dict[str, Any]]] = {}
        to_fetch: list[str] = []
        for platform in enabled:
            slot = f"categories_{platform}"
            if is_browse_slot_fresh(cache, slot):
                results[platform] = cache[slot]["data"]
            else:
                to_fetch.append(platform)
        if to_fetch:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                for platform in to_fetch:
                    client = self._get_platform(platform)
                    try:
                        categories = loop.run_until_complete(client.get_categories())
                        results[platform] = categories
                        cache[f"categories_{platform}"] = {
                            "data": categories,
                            "fetched_at": now,
                        }
                    except Exception as e:
                        logger.warning("browse categories failed for %s: %s", platform, e)
                        results[platform] = []
                save_browse_cache(cache)
            finally:
                self._close_thread_loop(loop)
        merged = _aggregate_categories(results)
        self._eval_js(f"window.onBrowseCategories({json.dumps(merged)})")

    def get_browse_top_streams(
        self,
        category_name: str,
        platform_ids: dict[str, str],
        platform_filter: str = "all",
    ) -> None:
        """Fetch top streams for a category from relevant platforms.

        Called from JS. Fires window.onBrowseTopStreams({"category": name,
        "streams": [...]}) when done.
        platform_ids: {"twitch": "33214", "kick": "42", "youtube": "20"}
        """
        self._run_in_thread(
            lambda: self._fetch_browse_top_streams(
                category_name, platform_ids, platform_filter
            )
        )

    def _fetch_browse_top_streams(
        self,
        category_name: str,
        platform_ids: dict[str, str],
        platform_filter: str,
    ) -> None:
        in_filter = (
            list(platform_ids.keys())
            if platform_filter == "all"
            else [platform_filter]
        )
        platforms_to_query = [p for p in in_filter if p in platform_ids]
        cache = load_browse_cache()
        now = time.time()
        all_streams: list[dict[str, Any]] = []
        to_fetch: list[str] = []
        for platform in platforms_to_query:
            cat_id = platform_ids[platform]
            slot = f"top_streams_youtube_{cat_id}"
            if platform == "youtube" and is_browse_slot_fresh(cache, slot):
                all_streams.extend(cache[slot]["data"])
            else:
                to_fetch.append(platform)
        if to_fetch:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                for platform in to_fetch:
                    cat_id = platform_ids[platform]
                    client = self._get_platform(platform)
                    try:
                        streams = loop.run_until_complete(
                            client.get_top_streams(category_id=cat_id, limit=20)
                        )
                        all_streams.extend(streams)
                        if platform == "youtube":
                            slot = f"top_streams_youtube_{cat_id}"
                            cache[slot] = {"data": streams, "fetched_at": now}
                    except Exception as e:
                        logger.warning("browse top streams failed for %s: %s", platform, e)
            finally:
                self._close_thread_loop(loop)
            save_browse_cache(cache)
        all_streams.sort(key=lambda s: s.get("viewers", 0), reverse=True)
        payload = {"category": category_name, "streams": all_streams[:40]}
        self._eval_js(f"window.onBrowseTopStreams({json.dumps(payload)})")

    def watch_direct(self, channel: str, platform: str, quality: str) -> None:
        """Watch a Twitch or Kick stream opened from browse.

        Unlike watch(), does not require the channel to be in the live cache.
        YouTube is not supported — video_id is unavailable from browse search
        results; YouTube stream cards in browse are display-only.
        """
        if not channel or platform not in ("twitch", "kick"):
            return

        def _save_quality(cfg: dict[str, Any]) -> None:
            cfg.get("settings", {})["quality"] = quality

        self._config = update_config(_save_quality)
        safe_ch = json.dumps(channel)
        self._eval_js(
            f"window.onStatusUpdate({{text: 'Loading ' + {safe_ch} + '...', type: 'warn'}})"
        )
        self._launch_channel = channel
        self._launch_elapsed = 0
        self._start_launch_timer()

        def do_resolve() -> None:
            settings = get_settings(self._config)
            hls_url, err = resolve_hls_url(
                channel,
                quality,
                settings.get("streamlink_path", "streamlink"),
                platform=platform,
            )
            self._cancel_launch_timer()
            self._launch_channel = None
            if not hls_url:
                r = json.dumps(
                    {
                        "success": False,
                        "message": err or "Could not resolve stream URL",
                        "channel": channel,
                    }
                )
                self._eval_js(f"window.onLaunchResult({r})")
                return
            self._watching_channel = channel
            stream_data = json.dumps(
                {"url": hls_url, "channel": channel, "title": "", "platform": platform}
            )
            self._eval_js(f"window.onStreamReady({stream_data})")
            r = json.dumps(
                {"success": True, "message": f"Playing {channel}", "channel": channel}
            )
            self._eval_js(f"window.onLaunchResult({r})")

        self._run_in_thread(do_resolve)
```

- [ ] **Step 6: Run full suite**

```bash
make test
```

- [ ] **Step 7: Commit**

```bash
git add ui/api.py tests/test_browse_api.py
git commit -m "feat(browse): add browse API methods and watch_direct to TwitchXApi"
```

---

## Task 6: Browse view HTML and CSS in `ui/index.html`

**Files:**
- Modify: `ui/index.html`

No unit tests for HTML/CSS. Verified in Task 7 via manual app run.

- [ ] **Step 1: Add `#browse-view` HTML**

In `ui/index.html`, find `<div id="player-view"` inside the main content area. Insert the following div immediately before it:

```html
<div id="browse-view" class="hidden">
  <div id="browse-header">
    <button id="browse-back-btn" class="browse-back-btn hidden" onclick="browseGoBack()">&#8592; Back</button>
    <span id="browse-title">Browse</span>
    <div id="browse-platform-tabs">
      <button class="browse-platform-tab active" data-platform="all" onclick="setBrowsePlatform(this,'all')">All</button>
      <button class="browse-platform-tab" data-platform="twitch" onclick="setBrowsePlatform(this,'twitch')">Twitch</button>
      <button class="browse-platform-tab" data-platform="kick" onclick="setBrowsePlatform(this,'kick')">Kick</button>
      <button class="browse-platform-tab" data-platform="youtube" onclick="setBrowsePlatform(this,'youtube')">YouTube</button>
    </div>
  </div>
  <div id="browse-body">
    <div id="browse-categories-grid" class="browse-grid"></div>
    <div id="browse-streams-grid" class="browse-grid browse-streams-grid hidden"></div>
    <div id="browse-loading" class="browse-loading hidden">Loading...</div>
    <div id="browse-empty" class="browse-empty hidden">No results found.</div>
  </div>
</div>
```

- [ ] **Step 2: Add Browse button to sidebar**

Find the search input wrapper in the sidebar (contains `id="search-input"` or similar). Insert this wrapper immediately after it, before the channel list section:

```html
<div id="browse-nav-wrapper">
  <button id="browse-nav-btn" onclick="showBrowseView()">Browse</button>
</div>
```

- [ ] **Step 3: Add CSS**

In the `<style>` block, insert the following rules after the existing player/toolbar styles:

```css
/* ── Browse view ────────────────────────────────────────── */
#browse-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg-base);
}
#browse-view.hidden { display: none; }

#browse-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
}
#browse-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}
.browse-back-btn {
  background: none;
  border: 1px solid rgba(255,255,255,0.12);
  color: var(--text-secondary);
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 12px;
}
.browse-back-btn:hover { background: var(--bg-elevated); color: var(--text-primary); }
.browse-back-btn.hidden { display: none; }

#browse-platform-tabs { display: flex; gap: 4px; }
.browse-platform-tab {
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
}
.browse-platform-tab.active { background: var(--accent); color: #fff; }
.browse-platform-tab:hover:not(.active) {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

#browse-body { flex: 1; overflow-y: auto; padding: 14px; }

.browse-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 10px;
}
.browse-grid.hidden { display: none; }
.browse-streams-grid {
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
}

.browse-category-card {
  background: var(--bg-elevated);
  border-radius: var(--radius-md);
  overflow: hidden;
  cursor: pointer;
  border: 1px solid rgba(255,255,255,0.04);
  transition: transform 0.12s ease, box-shadow 0.12s ease;
}
.browse-category-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0,0,0,0.35);
}
.browse-category-art {
  width: 100%;
  aspect-ratio: 3 / 4;
  object-fit: cover;
  display: block;
  background: var(--bg-surface);
}
.browse-category-info { padding: 7px 8px 8px; }
.browse-category-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.browse-category-platforms { display: flex; gap: 3px; margin-top: 4px; }

.browse-stream-card {
  background: var(--bg-elevated);
  border-radius: var(--radius-md);
  overflow: hidden;
  cursor: pointer;
  border: 1px solid rgba(255,255,255,0.04);
  transition: transform 0.12s ease;
}
.browse-stream-card:hover { transform: translateY(-2px); }
.browse-stream-thumb {
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  display: block;
  background: var(--bg-surface);
}
.browse-stream-info { padding: 7px 8px 8px; }
.browse-stream-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.browse-stream-title {
  font-size: 11px;
  color: var(--text-secondary);
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}
.browse-stream-viewers {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
  display: block;
}

.browse-loading, .browse-empty {
  text-align: center;
  color: var(--text-muted);
  padding: 40px;
  font-size: 13px;
}
.browse-loading.hidden, .browse-empty.hidden { display: none; }

#browse-nav-btn {
  display: block;
  width: 100%;
  padding: 7px 12px;
  background: var(--bg-elevated);
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  text-align: left;
}
#browse-nav-btn:hover { background: var(--bg-overlay); color: var(--text-primary); }
#browse-nav-wrapper { padding: 0 8px 6px; }
```

- [ ] **Step 4: Commit**

```bash
git add ui/index.html
git commit -m "feat(browse): add browse-view HTML and CSS"
```

---

## Task 7: Browse JS — navigation, callbacks, and stream cards

**Files:**
- Modify: `ui/index.html` (JS section only)

- [ ] **Step 1: Add browse state variables**

Find `var state = {` in the JS block and add these fields:

```javascript
browseMode: 'categories',    // 'categories' | 'streams'
browseCategory: null,        // currently selected category object
browsePlatformFilter: 'all', // current filter in browse view
```

- [ ] **Step 2: Add browse navigation functions**

Add the following functions in the JS section (near other view-toggle helpers):

```javascript
function showBrowseView() {
  document.getElementById('toolbar').classList.add('hidden');
  document.getElementById('stream-grid').classList.add('hidden');
  document.getElementById('browse-view').classList.remove('hidden');
  state.browseMode = 'categories';
  state.browseCategory = null;
  state.browsePlatformFilter = 'all';
  document.querySelectorAll('.browse-platform-tab').forEach(function(t) {
    t.classList.toggle('active', t.dataset.platform === 'all');
  });
  document.getElementById('browse-back-btn').classList.add('hidden');
  document.getElementById('browse-title').textContent = 'Browse';
  document.getElementById('browse-categories-grid').classList.remove('hidden');
  document.getElementById('browse-streams-grid').classList.add('hidden');
  loadBrowseCategories();
}

function hideBrowseView() {
  document.getElementById('browse-view').classList.add('hidden');
  document.getElementById('toolbar').classList.remove('hidden');
  document.getElementById('stream-grid').classList.remove('hidden');
}

function browseGoBack() {
  if (state.browseMode === 'streams') {
    state.browseMode = 'categories';
    state.browseCategory = null;
    document.getElementById('browse-back-btn').classList.add('hidden');
    document.getElementById('browse-title').textContent = 'Browse';
    document.getElementById('browse-categories-grid').classList.remove('hidden');
    document.getElementById('browse-streams-grid').classList.add('hidden');
    document.getElementById('browse-empty').classList.add('hidden');
  } else {
    hideBrowseView();
  }
}

function setBrowsePlatform(btn, platform) {
  document.querySelectorAll('.browse-platform-tab').forEach(function(t) {
    t.classList.remove('active');
  });
  btn.classList.add('active');
  state.browsePlatformFilter = platform;
  if (state.browseMode === 'categories') {
    loadBrowseCategories();
  } else if (state.browseCategory) {
    _triggerBrowseTopStreams(state.browseCategory);
  }
}

function loadBrowseCategories() {
  document.getElementById('browse-categories-grid').replaceChildren();
  document.getElementById('browse-loading').classList.remove('hidden');
  document.getElementById('browse-empty').classList.add('hidden');
  if (api) api.get_browse_categories(state.browsePlatformFilter);
}

function _triggerBrowseTopStreams(category) {
  state.browseMode = 'streams';
  state.browseCategory = category;
  document.getElementById('browse-title').textContent = category.name;
  document.getElementById('browse-back-btn').classList.remove('hidden');
  document.getElementById('browse-categories-grid').classList.add('hidden');
  document.getElementById('browse-streams-grid').replaceChildren();
  document.getElementById('browse-streams-grid').classList.remove('hidden');
  document.getElementById('browse-loading').classList.remove('hidden');
  document.getElementById('browse-empty').classList.add('hidden');
  if (api) {
    api.get_browse_top_streams(
      category.name,
      category.platform_ids,
      state.browsePlatformFilter
    );
  }
}
```

- [ ] **Step 3: Add `window.onBrowseCategories` callback**

```javascript
window.onBrowseCategories = function(categories) {
  document.getElementById('browse-loading').classList.add('hidden');
  var grid = document.getElementById('browse-categories-grid');
  grid.replaceChildren();
  if (!categories || !categories.length) {
    document.getElementById('browse-empty').classList.remove('hidden');
    return;
  }
  categories.forEach(function(cat) {
    var card = document.createElement('div');
    card.className = 'browse-category-card';
    card.onclick = function() { _triggerBrowseTopStreams(cat); };

    var img = document.createElement('img');
    img.className = 'browse-category-art';
    img.alt = '';
    if (cat.box_art_url) img.src = cat.box_art_url;
    img.onerror = function() { img.style.display = 'none'; };

    var info = document.createElement('div');
    info.className = 'browse-category-info';

    var nameEl = document.createElement('span');
    nameEl.className = 'browse-category-name';
    nameEl.textContent = cat.name;

    var badges = document.createElement('div');
    badges.className = 'browse-category-platforms';
    (cat.platforms || []).forEach(function(p) {
      var badge = document.createElement('span');
      badge.className = 'platform-badge platform-badge-' + p;
      badge.textContent = p.charAt(0).toUpperCase();
      badges.appendChild(badge);
    });

    info.appendChild(nameEl);
    info.appendChild(badges);
    card.appendChild(img);
    card.appendChild(info);
    grid.appendChild(card);
  });
};
```

- [ ] **Step 4: Add `window.onBrowseTopStreams` callback**

```javascript
window.onBrowseTopStreams = function(payload) {
  document.getElementById('browse-loading').classList.add('hidden');
  var grid = document.getElementById('browse-streams-grid');
  grid.replaceChildren();
  if (!payload || !payload.streams || !payload.streams.length) {
    document.getElementById('browse-empty').classList.remove('hidden');
    return;
  }
  payload.streams.forEach(function(stream) {
    var card = document.createElement('div');
    card.className = 'browse-stream-card';

    // YouTube streams are display-only (video_id not available from search.list)
    if (stream.platform !== 'youtube') {
      card.onclick = function() {
        hideBrowseView();
        var quality = document.getElementById('quality-select')
          ? document.getElementById('quality-select').value
          : 'best';
        if (api) api.watch_direct(stream.channel_login, stream.platform, quality);
      };
    }

    var thumb = document.createElement('img');
    thumb.className = 'browse-stream-thumb';
    thumb.alt = '';
    if (stream.thumbnail_url) thumb.src = stream.thumbnail_url;
    thumb.onerror = function() { thumb.style.display = 'none'; };

    var info = document.createElement('div');
    info.className = 'browse-stream-info';

    var badge = document.createElement('span');
    badge.className = 'platform-badge platform-badge-' + stream.platform;
    badge.textContent = stream.platform.charAt(0).toUpperCase();

    var nameEl = document.createElement('span');
    nameEl.className = 'browse-stream-name';
    nameEl.textContent = stream.display_name;

    var titleEl = document.createElement('span');
    titleEl.className = 'browse-stream-title';
    titleEl.textContent = stream.title;

    var viewersEl = document.createElement('span');
    viewersEl.className = 'browse-stream-viewers';
    if (stream.viewers) viewersEl.textContent = formatViewers(stream.viewers);

    info.appendChild(badge);
    info.appendChild(nameEl);
    info.appendChild(titleEl);
    info.appendChild(viewersEl);
    card.appendChild(thumb);
    card.appendChild(info);
    grid.appendChild(card);
  });
};
```

- [ ] **Step 5: Run full test suite**

```bash
make test
```

- [ ] **Step 6: Launch the app and manually verify**

```bash
make run
```

Verification checklist:
- [ ] Sidebar shows "Browse" button
- [ ] Clicking "Browse" hides the stream grid and toolbar, shows browse-view
- [ ] Category cards load with box art images and platform badges
- [ ] Platform filter tabs filter category results correctly
- [ ] Clicking a category shows top streams with the category name as title and back button
- [ ] Stream cards render: thumbnail, platform badge, display name, title, viewer count
- [ ] Clicking a Twitch or Kick stream card hides browse and starts playback
- [ ] YouTube stream cards are visible but not clickable (no onclick)
- [ ] Back button returns to category grid
- [ ] Returning to the same category within 10 min uses cached data (check logs)
- [ ] No JS errors in the console after navigating around

- [ ] **Step 7: Commit**

```bash
git add ui/index.html
git commit -m "feat(browse): add browse view JS navigation and rendering callbacks"
```

---

## Self-Review

**Spec coverage:**
- ✅ browse-view with platform filter tabs (Tasks 6–7)
- ✅ Category cards grid aggregated across platforms (Task 5, `_aggregate_categories`)
- ✅ Click category → top streams grid with platform badges (Task 7, `_triggerBrowseTopStreams`)
- ✅ YouTube results cached 10 minutes (Task 5, `top_streams_youtube_*` slots)
- ✅ Category caching 10 minutes per platform (Task 5, `categories_*` slots)
- ⚠️ YouTube stream playback from browse not supported — `search.list` returns `channelId` but not `video_id`; YouTube stream cards are display-only and clearly documented as a known limitation

**Placeholder scan:** No TBD, TODO, "implement later", or "add appropriate" patterns present. Every step has working code.

**Type consistency:**
- `_aggregate_categories` defined as module-level in `ui/api.py`, imported in tests as `from ui.api import _aggregate_categories` — consistent
- `is_browse_slot_fresh(cache, slot_key, ttl)` signature matches all call sites in `_fetch_browse_categories` and `_fetch_browse_top_streams` — consistent
- `get_top_streams(category_id=..., limit=...)` keyword arguments used identically at all three client call sites — consistent
- JS `api.get_browse_top_streams(name, platform_ids, filter)` maps to Python `(self, category_name, platform_ids: dict, platform_filter)` — pywebview converts JS object → Python dict automatically
