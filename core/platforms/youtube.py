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
