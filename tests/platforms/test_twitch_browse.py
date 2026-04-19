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
