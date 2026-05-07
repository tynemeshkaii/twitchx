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
    # _get is called with (url, params=...) as keyword arg
    params = mock_get.call_args.kwargs.get("params")
    param_dict: dict[str, str] = (
        dict(params) if isinstance(params, list) else params or {}
    )
    assert param_dict.get("category_id") == "15"
