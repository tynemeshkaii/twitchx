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


# ── YouTubeClient ─────────────────────────────────────────────


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
            "game": "",
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
                        stream = self._build_stream_from_video(item)
                        live_streams.append(stream)
                        # Cache video_id for playback
                        self._live_video_ids[stream["login"]] = stream["video_id"]
            except Exception as e:
                logger.warning("YouTube videos.list failed: %s", e)

        return live_streams

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
            "is_live": False,
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

    async def refresh_user_token(self) -> str:
        """Stub — implemented in Task 7."""
        raise NotImplementedError
