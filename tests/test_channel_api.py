from __future__ import annotations

import json
from pathlib import Path

import pytest

import core.storage as storage
from core.storage import DEFAULT_CONFIG, save_config
from ui.api import TwitchXApi


def _patch_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(storage, "CONFIG_DIR", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(storage, "CONFIG_FILE", tmp_path / "config.json")  # type: ignore[attr-defined]
    monkeypatch.setattr(storage, "_OLD_CONFIG_DIR", tmp_path / "old")  # type: ignore[attr-defined]


def _parse_channel_profile(emitted: list[str]) -> dict:
    raw = emitted[-1]
    assert "window.onChannelProfile(" in raw
    return json.loads(raw.split("window.onChannelProfile(", 1)[1].rstrip(")"))


def test_get_channel_profile_twitch_emits_js_callback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_storage(monkeypatch, tmp_path)
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_storage(monkeypatch, tmp_path)

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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_storage(monkeypatch, tmp_path)
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_storage(monkeypatch, tmp_path)
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_storage(monkeypatch, tmp_path)
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_storage(monkeypatch, tmp_path)
    api = TwitchXApi()
    emitted: list[str] = []
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.get_channel_profile("someone", "nonexistent")

    assert not emitted
