from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path
from typing import Any

import pytest


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


# ── QuotaTracker ──────────────────────────────────────────────


class TestQuotaTracker:
    def test_initial_remaining_is_full_budget(self, tmp_path: Path) -> None:
        _setup_config(tmp_path, {})
        from core.platforms.youtube import QuotaTracker

        qt = QuotaTracker(lambda: _yt_conf(tmp_path), _make_update_fn(tmp_path))
        assert qt.remaining() == 10_000

    def test_use_decrements_remaining(self, tmp_path: Path) -> None:
        _setup_config(tmp_path, {})
        from core.platforms.youtube import QuotaTracker

        qt = QuotaTracker(lambda: _yt_conf(tmp_path), _make_update_fn(tmp_path))
        qt.use(100)
        assert qt.remaining() == 9_900

    def test_resets_on_new_day(self, tmp_path: Path) -> None:
        _setup_config(
            tmp_path,
            {"daily_quota_used": 5000, "quota_reset_date": "2025-01-01"},
        )
        from core.platforms.youtube import QuotaTracker

        qt = QuotaTracker(lambda: _yt_conf(tmp_path), _make_update_fn(tmp_path))
        # Today is not 2025-01-01, so remaining should be full
        assert qt.remaining() == 10_000

    def test_same_day_preserves_usage(self, tmp_path: Path) -> None:
        today = date.today().isoformat()
        _setup_config(
            tmp_path,
            {"daily_quota_used": 3000, "quota_reset_date": today},
        )
        from core.platforms.youtube import QuotaTracker

        qt = QuotaTracker(lambda: _yt_conf(tmp_path), _make_update_fn(tmp_path))
        assert qt.remaining() == 7_000

    def test_can_use_returns_false_when_exhausted(self, tmp_path: Path) -> None:
        today = date.today().isoformat()
        _setup_config(
            tmp_path,
            {"daily_quota_used": 10_000, "quota_reset_date": today},
        )
        from core.platforms.youtube import QuotaTracker

        qt = QuotaTracker(lambda: _yt_conf(tmp_path), _make_update_fn(tmp_path))
        assert not qt.can_use(1)

    def test_can_use_returns_true_when_budget_available(self, tmp_path: Path) -> None:
        _setup_config(tmp_path, {})
        from core.platforms.youtube import QuotaTracker

        qt = QuotaTracker(lambda: _yt_conf(tmp_path), _make_update_fn(tmp_path))
        assert qt.can_use(100)


# ── RSS Parsing ───────────────────────────────────────────────


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


# ── YouTubeClient ─────────────────────────────────────────────


import asyncio
import httpx


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
        from core.platforms.youtube import VALID_CHANNEL_ID

        assert VALID_CHANNEL_ID.match(cid)

    @pytest.mark.parametrize(
        "cid",
        [
            "",
            "not-a-channel-id",
            "UC",
            "UCtooshort",
            "@MrBeast",
            "https://youtube.com/channel/UCX6OQ3DkcsbYNE6H8uQQuVA",
        ],
    )
    def test_rejects_invalid(self, cid: str) -> None:
        from core.platforms.youtube import VALID_CHANNEL_ID

        assert not VALID_CHANNEL_ID.match(cid)


class TestYouTubeClientInit:
    def test_creates_client(self) -> None:
        from core.platforms.youtube import YouTubeClient

        client = YouTubeClient()
        assert client is not None

    def test_per_loop_client_isolation(self) -> None:
        """Different event loops get different httpx clients."""
        from core.platforms.youtube import YouTubeClient

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


# ── get_live_streams ──────────────────────────────────────────


class TestGetLiveStreams:
    def test_empty_channel_list_returns_empty(self) -> None:
        from core.platforms.youtube import YouTubeClient

        client = YouTubeClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(client.get_live_streams([]))
        assert result == []
        loop.run_until_complete(client.close())
        loop.close()

    def test_invalid_channel_ids_filtered(self) -> None:
        from core.platforms.youtube import YouTubeClient

        client = YouTubeClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            client.get_live_streams(["not-valid", "", "@handle"])
        )
        assert result == []
        loop.run_until_complete(client.close())
        loop.close()

    def test_builds_stream_info_from_api_response(self) -> None:
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
        from core.platforms.youtube import YouTubeClient

        assert YouTubeClient._is_video_live(
            {
                "liveStreamingDetails": {
                    "actualStartTime": "2026-04-02T10:00:00Z",
                    "concurrentViewers": "100",
                }
            }
        )
        assert not YouTubeClient._is_video_live(
            {
                "liveStreamingDetails": {
                    "actualStartTime": "2026-04-02T10:00:00Z",
                    "actualEndTime": "2026-04-02T12:00:00Z",
                }
            }
        )
        assert not YouTubeClient._is_video_live({"snippet": {"title": "normal video"}})


# ── search + channel info ─────────────────────────────────────


class TestSearchChannels:
    def test_empty_query_returns_empty(self) -> None:
        from core.platforms.youtube import YouTubeClient

        client = YouTubeClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(client.search_channels(""))
        assert result == []
        loop.run_until_complete(client.close())
        loop.close()

    def test_normalizes_search_result(self) -> None:
        from core.platforms.youtube import YouTubeClient

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
        from core.platforms.youtube import YouTubeClient

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


# ── OAuth + user + subscriptions ──────────────────────────────


class TestOAuth:
    def test_get_auth_url_contains_required_params(self) -> None:
        from core.platforms.youtube import YouTubeClient

        client = YouTubeClient()
        client._config = {
            "platforms": {
                "youtube": {"client_id": "test-client-id", "client_secret": "secret", "api_key": ""}
            }
        }
        url = client.get_auth_url()
        assert "accounts.google.com" in url
        assert "test-client-id" in url
        assert "localhost" in url
        assert "youtube.readonly" in url


class TestGetFollowedChannels:
    def test_returns_channel_ids_from_subscriptions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from core.platforms.youtube import YouTubeClient

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
        from core.platforms.youtube import YouTubeClient

        client = YouTubeClient()
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
