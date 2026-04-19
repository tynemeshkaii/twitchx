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
    assert s["title"] == "Live stream title"
    assert s["thumbnail_url"] == "https://img.youtube.com/vi/abc/mqdefault.jpg"
    assert s["channel_login"] == "UCxyz"


def test_get_top_streams_skips_items_without_snippet() -> None:
    client = YouTubeClient()
    mock_items = [
        {"id": "vid1"},  # no snippet key
        {
            "snippet": {
                "channelId": "UCabc",
                "channelTitle": "Chan",
                "title": "Live",
                "thumbnails": {},
            }
        },
    ]
    with (
        patch.object(client, "_ensure_token", return_value="tok"),
        patch.object(client._quota, "check_and_use", return_value=True),
        patch.object(client, "_yt_get", return_value={"items": mock_items}),
    ):
        result = _run(client.get_top_streams())
    assert len(result) == 1
    assert result[0]["channel_id"] == "UCabc"
