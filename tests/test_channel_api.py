from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.storage import DEFAULT_CONFIG, save_config
from ui.api import TwitchXApi


def _parse_channel_profile(emitted: list[str]) -> dict:
    raw = emitted[-1]
    assert "window.onChannelProfile(" in raw
    return json.loads(raw.split("window.onChannelProfile(", 1)[1].rstrip(")"))


def _parse_channel_media(emitted: list[str]) -> dict:
    raw = emitted[-1]
    assert "window.onChannelMedia(" in raw
    return json.loads(raw.split("window.onChannelMedia(", 1)[1].rstrip(")"))


def test_get_channel_profile_twitch_emits_js_callback(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    emitted: list[str] = []

    async def fake_channel_info(login: str) -> dict:
        return {
            "platform": "twitch",
            "channel_id": "44322889",
            "login": "xqc",
            "display_name": "xQc",
            "bio": "lulw",
            "avatar_url": "https://img.jpg",
            "followers": -1,
            "is_live": True,
            "can_follow_via_api": False,
        }

    monkeypatch.setattr(api._twitch, "get_channel_info", fake_channel_info)
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.get_channel_profile("xqc", "twitch")

    payload = _parse_channel_profile(emitted)
    assert payload["login"] == "xqc"
    assert payload["display_name"] == "xQc"
    assert payload["platform"] == "twitch"
    assert payload["is_live"] is True
    assert payload["is_favorited"] is False


def test_get_channel_profile_marks_is_favorited_when_in_favorites(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    config = {
        **DEFAULT_CONFIG,
        "favorites": [{"platform": "twitch", "login": "xqc", "display_name": "xQc"}],
    }
    save_config(config)

    api = TwitchXApi()
    emitted: list[str] = []

    async def fake_channel_info(login: str) -> dict:
        return {
            "platform": "twitch",
            "channel_id": "44322889",
            "login": "xqc",
            "display_name": "xQc",
            "bio": "",
            "avatar_url": "",
            "followers": -1,
            "is_live": False,
            "can_follow_via_api": False,
        }

    monkeypatch.setattr(api._twitch, "get_channel_info", fake_channel_info)
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.get_channel_profile("xqc", "twitch")

    payload = _parse_channel_profile(emitted)
    assert payload["is_favorited"] is True


def test_get_channel_profile_kick_normalizes_raw_dict(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    emitted: list[str] = []

    async def fake_channel_info(slug: str) -> dict:
        return {
            "slug": "trainwreckstv",
            "channel_id": 99,
            "user": {"username": "Trainwreckstv", "profile_pic": "https://avatar.jpg"},
            "description": "slots and poker",
            "followers_count": 500000,
            "is_live": True,
        }

    monkeypatch.setattr(api._kick, "get_channel_info", fake_channel_info)
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.get_channel_profile("trainwreckstv", "kick")

    payload = _parse_channel_profile(emitted)
    assert payload["platform"] == "kick"
    assert payload["login"] == "trainwreckstv"
    assert payload["display_name"] == "Trainwreckstv"
    assert payload["bio"] == "slots and poker"
    assert payload["avatar_url"] == "https://avatar.jpg"
    assert payload["followers"] == 500000
    assert payload["is_live"] is True


def test_get_channel_profile_youtube_normalizes_raw_dict(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    emitted: list[str] = []

    async def fake_channel_info(channel_id: str) -> dict:
        return {
            "channel_id": "UCxxxxxx",
            "display_name": "SomeYouTuber",
            "description": "gaming videos",
            "avatar_url": "https://yt.jpg",
            "followers": 1_000_000,
        }

    monkeypatch.setattr(api._youtube, "get_channel_info", fake_channel_info)
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.get_channel_profile("UCxxxxxx", "youtube")

    payload = _parse_channel_profile(emitted)
    assert payload["platform"] == "youtube"
    assert payload["login"] == "UCxxxxxx"
    assert payload["display_name"] == "SomeYouTuber"
    assert payload["bio"] == "gaming videos"
    assert payload["followers"] == 1_000_000
    assert payload["is_live"] is False


def test_get_channel_profile_emits_null_on_empty_response(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    emitted: list[str] = []

    async def fake_channel_info(login: str) -> dict:
        return {}

    monkeypatch.setattr(api._twitch, "get_channel_info", fake_channel_info)
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.get_channel_profile("nobody", "twitch")

    assert emitted[-1] == "window.onChannelProfile(null)"


def test_get_channel_profile_ignores_unknown_platform(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    emitted: list[str] = []
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.get_channel_profile("someone", "nonexistent")

    assert not emitted


def test_get_channel_media_twitch_vods_emits_payload(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    emitted: list[str] = []

    async def fake_vods(login: str, limit: int = 12) -> list[dict]:
        assert login == "xqc"
        assert limit == 12
        return [
            {
                "id": "v1",
                "platform": "twitch",
                "kind": "vod",
                "title": "Archive",
                "url": "https://www.twitch.tv/videos/1",
                "thumbnail_url": "https://thumb.jpg",
                "published_at": "2026-04-24T10:00:00Z",
                "duration_seconds": 3600,
                "views": 100,
                "channel_login": "xqc",
                "channel_display_name": "xQc",
            }
        ]

    monkeypatch.setattr(api._twitch, "get_channel_vods", fake_vods)
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.get_channel_media("xqc", "twitch", "vods")

    payload = _parse_channel_media(emitted)
    assert payload["platform"] == "twitch"
    assert payload["tab"] == "vods"
    assert payload["supported"] is True
    assert payload["error"] is False
    assert payload["items"][0]["id"] == "v1"


def test_get_channel_media_kick_emits_unsupported(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    emitted: list[str] = []
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.get_channel_media("trainwreckstv", "kick", "clips")

    payload = _parse_channel_media(emitted)
    assert payload["platform"] == "kick"
    assert payload["tab"] == "clips"
    assert payload["supported"] is False
    assert payload["error"] is False
