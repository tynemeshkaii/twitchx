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

from core.platforms.base import BasePlatformClient
from core.storage import update_config

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

    Maintains authoritative in-memory counters seeded from config at init.
    Writes to disk for persistence across restarts, but never reads from disk
    after construction — eliminating stale-config reads on every remaining() call.
    """

    def __init__(
        self,
        get_yt_config: Any,
        update_fn: Any | None = None,
    ) -> None:
        self._update_fn = update_fn or self._default_update
        self._lock = threading.Lock()
        # Seed in-memory state from persisted config once at construction.
        yc = get_yt_config()
        today = date.today().isoformat()
        if yc.get("quota_reset_date") == today:
            self._used: int = yc.get("daily_quota_used", 0)
        else:
            self._used = 0
        self._date: str = today

    @staticmethod
    def _default_update(used: int, date_str: str) -> None:
        def _apply(cfg: dict) -> None:
            yt = cfg.get("platforms", {}).get("youtube", {})
            yt["daily_quota_used"] = used
            yt["quota_reset_date"] = date_str

        update_config(_apply)

    def _maybe_reset(self) -> None:
        """Reset counter if the calendar day has changed. Must be called under lock."""
        today = date.today().isoformat()
        if self._date != today:
            self._used = 0
            self._date = today

    def remaining(self) -> int:
        with self._lock:
            self._maybe_reset()
            return max(0, DAILY_QUOTA_LIMIT - self._used)

    def can_use(self, units: int) -> bool:
        return self.remaining() >= units

    def use(self, units: int) -> None:
        with self._lock:
            self._maybe_reset()
            self._used += units
            self._update_fn(self._used, self._date)

    def check_and_use(self, units: int) -> bool:
        """Atomically check quota and consume it if available.

        Returns True and decrements the counter if units are available,
        False without side effects otherwise. Prefer this over calling
        can_use() + use() separately to avoid a TOCTOU race.
        """
        with self._lock:
            self._maybe_reset()
            if DAILY_QUOTA_LIMIT - self._used < units:
                return False
            self._used += units
            self._update_fn(self._used, self._date)
            return True


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


class YouTubeClient(BasePlatformClient):
    """YouTube Data API v3 client with per-event-loop HTTP pooling."""

    PLATFORM_ID = "youtube"
    PLATFORM_NAME = "YouTube"

    def __init__(self) -> None:
        super().__init__()
        self._quota = QuotaTracker(self._platform_config)
        self._live_video_ids: dict[str, str] = {}

    def _client_headers(self) -> dict[str, str]:
        return {"User-Agent": "TwitchX/2.0 (YouTube)"}

    def _check_response_errors(self, resp: httpx.Response) -> None:
        """Handle YouTube-specific 403 quota exceeded."""
        if resp.status_code == 403:
            try:
                body = resp.json()
            except Exception:
                raise ValueError("YouTube API quota exceeded") from None
            errors = body.get("error", {}).get("errors", [])
            for err in errors:
                if err.get("reason") == "quotaExceeded":
                    raise ValueError("YouTube API daily quota exceeded.")

    def quota_remaining(self) -> int:
        """Return the number of remaining YouTube Data API quota units for today."""
        return self._quota.remaining()

    # ── Token management ─────────────────────────────────────

    async def _ensure_token(self) -> str | None:
        """Return a valid OAuth token, refreshing if needed. None if unavailable."""
        async with self._get_token_lock():
            self._reload_config()
            yc = self._platform_config()
            if yc.get("access_token") and yc.get("token_expires_at", 0) > asyncio.get_running_loop().time() + 60:
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
            api_key = self._platform_config().get("api_key", "")
            if not api_key:
                raise ValueError("YouTube API key required. Set it in Settings.")
            query["key"] = api_key

        url = f"{YOUTUBE_API_URL}/{endpoint}"
        resp = await self._request("GET", url, params=query, headers=headers)
        return resp.json()

    async def _get(
        self,
        endpoint: str,
        params: dict[str, str] | None = None,
        auth_required: bool = False,
    ) -> dict[str, Any]:
        """Compatibility alias for _yt_get (used by tests)."""
        return await self._yt_get(endpoint, params, auth_required)

    # ── Live streams ─────────────────────────────────────────

    @staticmethod
    def _is_video_live(item: dict[str, Any]) -> bool:
        """Check if a video item from videos.list is currently live.

        A stream is live when actualStartTime is set and actualEndTime is absent.
        concurrentViewers is intentionally not required — YouTube omits it for
        some streams (new streams, hidden counts, API propagation lag).
        """
        details = item.get("liveStreamingDetails", {})
        return bool(details.get("actualStartTime") and not details.get("actualEndTime"))

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
                logger.debug(
                    "RSS feed returned %d for %s", resp.status_code, channel_id
                )
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

        # Evict stale video IDs for channels we are about to recheck.
        # Ensures resolve_stream_url never returns an ended stream's ID.
        for cid in valid_ids:
            self._live_video_ids.pop(cid, None)

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
            if not self._quota.check_and_use(1):
                logger.warning("YouTube quota exhausted, skipping live check")
                break
            try:
                data = await self._get(
                    "videos",
                    params={
                        "part": "snippet,liveStreamingDetails",
                        "id": ",".join(batch),
                    },
                )
                for item in data.get("items", []):
                    if self._is_video_live(item):
                        stream = self._build_stream_from_video(item)
                        live_streams.append(stream)
                        # Cache video_id for playback — guard against empty channelId
                        channel_id = stream["login"]
                        if channel_id and VALID_CHANNEL_ID.match(channel_id):
                            self._live_video_ids[channel_id] = stream["video_id"]
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

    @staticmethod
    def _parse_iso8601_duration_seconds(raw: str) -> int:
        """Convert ISO8601 video durations like PT1H2M3S to seconds."""
        if not raw:
            return 0
        match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", raw)
        if not match:
            return 0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds

    async def _get_channel_resource(
        self, channel_id_or_handle: str, part: str
    ) -> dict[str, Any]:
        raw = channel_id_or_handle.strip()
        if not raw:
            return {}
        params: dict[str, str]
        if raw.startswith("@"):
            params = {"part": part, "forHandle": raw}
        else:
            params = {"part": part, "id": raw}
        data = await self._get("channels", params=params)
        items = data.get("items", []) if isinstance(data, dict) else []
        return items[0] if items else {}

    async def _get_uploaded_video_items(
        self,
        channel_id_or_handle: str,
        max_results: int = 12,
    ) -> list[dict[str, Any]]:
        if not self._quota.check_and_use(1):
            logger.warning("YouTube quota too low for channel media lookup")
            return []
        channel = await self._get_channel_resource(
            channel_id_or_handle, "contentDetails,snippet"
        )
        uploads_id = (
            channel.get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("uploads", "")
        )
        if not uploads_id:
            return []

        if not self._quota.check_and_use(1):
            logger.warning("YouTube quota too low for uploads playlist lookup")
            return []
        playlist_data = await self._get(
            "playlistItems",
            params={
                "part": "snippet,contentDetails",
                "playlistId": uploads_id,
                "maxResults": str(min(max_results, 50)),
            },
        )
        playlist_items = (
            playlist_data.get("items", []) if isinstance(playlist_data, dict) else []
        )
        video_ids = [
            item.get("contentDetails", {}).get("videoId", "")
            for item in playlist_items
            if item.get("contentDetails", {}).get("videoId")
        ]
        if not video_ids:
            return []

        if not self._quota.check_and_use(1):
            logger.warning("YouTube quota too low for video metadata lookup")
            return []
        videos_data = await self._get(
            "videos",
            params={
                "part": "snippet,contentDetails,status,liveStreamingDetails",
                "id": ",".join(video_ids),
            },
        )
        items = videos_data.get("items", []) if isinstance(videos_data, dict) else []
        by_id = {
            item.get("id", ""): item
            for item in items
            if isinstance(item, dict) and item.get("id")
        }
        return [by_id[video_id] for video_id in video_ids if video_id in by_id]

    def _normalize_uploaded_video(
        self,
        item: dict[str, Any],
        kind: str,
    ) -> dict[str, Any] | None:
        video_id = item.get("id", "")
        if not video_id:
            return None
        snippet = item.get("snippet", {})
        status = item.get("status", {})
        live_state = snippet.get("liveBroadcastContent", "none")
        if status.get("privacyStatus") == "private":
            return None
        if live_state in ("live", "upcoming") or self._is_video_live(item):
            return None
        content = item.get("contentDetails", {})
        duration_seconds = self._parse_iso8601_duration_seconds(
            content.get("duration", "")
        )
        thumbs = snippet.get("thumbnails", {})
        thumb_url = (
            thumbs.get("maxres", {}).get("url")
            or thumbs.get("high", {}).get("url")
            or thumbs.get("medium", {}).get("url")
            or thumbs.get("default", {}).get("url", "")
        )
        channel_id = snippet.get("channelId", "")
        return {
            "id": video_id,
            "platform": "youtube",
            "kind": kind,
            "channel_login": channel_id,
            "channel_display_name": snippet.get("channelTitle", channel_id),
            "title": snippet.get("title", ""),
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "thumbnail_url": thumb_url,
            "published_at": snippet.get("publishedAt", ""),
            "duration_seconds": duration_seconds,
            "views": 0,
        }

    async def search_channels(self, query: str) -> list[dict[str, Any]]:
        """Search for YouTube channels. Costs 100 quota units."""
        query = query.strip()
        if not query:
            return []
        if not self._quota.check_and_use(100):
            logger.warning("YouTube quota too low for search (need 100 units)")
            return []
        try:
            data = await self._get(
                "search",
                params={
                    "part": "snippet",
                    "type": "channel",
                    "q": query,
                    "maxResults": "10",
                },
            )
            return [
                self._normalize_channel_search_result(item)
                for item in data.get("items", [])
                if item.get("id", {}).get("channelId")
            ]
        except Exception as e:
            logger.warning("YouTube search failed: %s", e)
            return []

    # ── Channel info ─────────────────────────────────────────

    async def get_channel_info(self, channel_id_or_handle: str) -> dict[str, Any]:
        """Get channel details. Costs 1–2 quota units.

        Accepts:
        - UC channel ID (UCxxxxxxxxxxxxxxxxxxxxxxxx)
        - @handle  (@windpress)
        - YouTube video ID (11 chars) — resolves to the channel that owns it
        """
        raw = channel_id_or_handle.strip()
        if not raw:
            return {}

        # If given a video ID (11 printable chars, not a UC ID), resolve to channel first
        _VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
        if _VIDEO_ID_RE.match(raw) and not raw.startswith("UC"):
            if not self._quota.check_and_use(1):
                raise ValueError("YouTube API daily quota exceeded.")
            video_data = await self._get(
                "videos",
                params={"part": "snippet", "id": raw},
            )
            vitems = video_data.get("items", []) if isinstance(video_data, dict) else []
            if not vitems:
                return {}
            raw = vitems[0].get("snippet", {}).get("channelId", "")
            if not raw:
                return {}

        if not self._quota.check_and_use(1):
            raise ValueError("YouTube API daily quota exceeded.")
        data = await self._get_channel_resource(raw, "snippet,statistics")
        if not data:
            return {}
        item = data
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        thumbs = snippet.get("thumbnails", {})
        return {
            "channel_id": item.get("id", raw),
            "display_name": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "avatar_url": thumbs.get("default", {}).get("url", ""),
            "followers": int(stats.get("subscriberCount", 0)),
        }

    async def get_channel_vods(
        self, channel_id_or_handle: str, limit: int = 12
    ) -> list[dict[str, Any]]:
        items = await self._get_uploaded_video_items(
            channel_id_or_handle, max_results=limit
        )
        results: list[dict[str, Any]] = []
        for item in items:
            normalized = self._normalize_uploaded_video(item, "vod")
            if normalized is not None:
                results.append(normalized)
            if len(results) >= limit:
                break
        return results

    async def get_channel_clips(
        self, channel_id_or_handle: str, limit: int = 12
    ) -> list[dict[str, Any]]:
        items = await self._get_uploaded_video_items(
            channel_id_or_handle, max_results=max(limit * 3, 24)
        )
        results: list[dict[str, Any]] = []
        for item in items:
            normalized = self._normalize_uploaded_video(item, "clip")
            if normalized is None:
                continue
            if (
                normalized["duration_seconds"] <= 0
                or normalized["duration_seconds"] > 90
            ):
                continue
            results.append(normalized)
            if len(results) >= limit:
                break
        return results

    # ── OAuth ────────────────────────────────────────────────

    def get_auth_url(self) -> str:
        """Generate Google OAuth authorization URL."""
        self._reload_config()
        yc = self._platform_config()
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
        yc = self._platform_config()
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
        yc = self._platform_config()
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
        data = await self._get(
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
            if not self._quota.check_and_use(1):
                logger.warning("YouTube quota too low for subscriptions fetch")
                break
            params: dict[str, str] = {
                "part": "snippet",
                "mine": "true",
                "maxResults": "50",
            }
            if page_token:
                params["pageToken"] = page_token
            data = await self._get(
                "subscriptions", params=params, auth_required=True
            )

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

    # ── Browse ───────────────────────────────────────────────

    async def get_categories(self, query: str | None = None) -> list[dict[str, Any]]:
        """Return assignable YouTube video categories for US region.

        query is ignored — YouTube categories are a fixed regional list.
        Costs 1 quota unit. Returns [] if unauthenticated or quota exhausted.
        """
        token = await self._ensure_token()
        if not token:
            return []
        if not self._quota.check_and_use(1):
            return []
        data = await self._get(
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
        data = await self._get("search", params)
        results: list[dict[str, Any]] = []
        for item in data.get("items", []):
            snippet = item.get("snippet")
            if not snippet:
                continue
            results.append(
                {
                    "platform": "youtube",
                    "channel_id": snippet.get("channelId", ""),
                    "channel_login": snippet.get("channelId", ""),
                    "display_name": snippet.get("channelTitle", ""),
                    "title": snippet.get("title", ""),
                    "category": "",
                    "category_id": category_id or "",
                    "viewers": 0,
                    "started_at": snippet.get("publishedAt", ""),
                    "thumbnail_url": snippet.get("thumbnails", {})
                    .get("medium", {})
                    .get("url", ""),
                    "avatar_url": "",
                }
            )
        return results

    # ── Playback ─────────────────────────────────────────────

    async def resolve_stream_url(self, channel_id: str, quality: str) -> dict[str, Any]:
        """Return playback info for YouTube iframe embed.

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

    # ── Polymorphic helpers ────────────────────────────────────

    @staticmethod
    def build_stream_url(channel: str) -> str:
        return f"https://www.youtube.com/watch?v={channel}"

    @staticmethod
    def sanitize_identifier(raw: str) -> str:
        """Extract YouTube channel identifier from raw string.

        Handles URLs (channel ID, @handle, video ID) and bare identifiers.
        """
        from core.utils import normalize_channel_id

        raw = raw.strip()
        # Direct channel URL
        match = re.search(r"youtube\.com/channel/(UC[\w-]{22})", raw, re.IGNORECASE)
        if match:
            return match.group(1)
        # Video URL — we can resolve this later via get_channel_info
        match = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", raw)
        if match:
            return "v:" + match.group(1)
        # @handle
        match = re.search(
            r"(?:youtube\.com/)?(@[A-Za-z0-9][A-Za-z0-9_.-]{2,29})", raw, re.IGNORECASE
        )
        if match:
            return match.group(1).lower()
        clean = normalize_channel_id(raw)
        if VALID_CHANNEL_ID.match(clean):
            return clean
        if re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,29}$", clean):
            return "@" + clean.lower()
        return ""

    async def normalize_search_result(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "login": raw.get("login", ""),
            "display_name": raw.get("display_name", ""),
            "is_live": raw.get("is_live", False),
            "game_name": "",
            "platform": "youtube",
        }

    async def normalize_stream_item(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "login": raw.get("login", ""),
            "display_name": raw.get("display_name", ""),
            "title": raw.get("title", ""),
            "game": raw.get("game", ""),
            "viewers": raw.get("viewers", 0),
            "started_at": raw.get("started_at", ""),
            "thumbnail_url": raw.get("thumbnail_url", ""),
            "viewer_trend": None,
            "platform": "youtube",
            "video_id": raw.get("video_id", ""),
            "channel_id": raw.get("channel_id", ""),
        }
