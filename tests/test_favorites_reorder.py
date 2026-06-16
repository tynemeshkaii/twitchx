from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.storage import load_config
from ui.api import TwitchXApi


def _write_config(path: Path, cfg: dict) -> None:
    path.write_text(json.dumps(cfg))


@pytest.fixture
def api_with_favorites(temp_config_dir: Path) -> TwitchXApi:
    cfg = json.loads(temp_config_dir.read_text())
    cfg["favorites"] = [
        {"platform": "twitch", "login": "a", "display_name": "A"},
        {"platform": "twitch", "login": "b", "display_name": "B"},
        {
            "platform": "youtube",
            "login": "UCxxxxxxxxxxxxxxxxxxxxxx",
            "display_name": "Y",
        },
    ]
    _write_config(temp_config_dir, cfg)

    api = TwitchXApi()
    api._data = MagicMock()
    return api


def test_reorder_favorites_updates_group_and_order(
    temp_config_dir: Path, api_with_favorites: TwitchXApi
) -> None:
    payload = [
        {"key": "twitch:a", "group": "FPS", "order": 0},
        {"key": "twitch:b", "group": "FPS", "order": 1},
        {"key": "youtube:UCxxxxxxxxxxxxxxxxxxxxxx", "group": None, "order": 0},
    ]

    api_with_favorites.reorder_favorites(json.dumps(payload))

    cfg = load_config()
    by_key = {f"{f['platform']}:{f['login']}": f for f in cfg["favorites"]}

    assert by_key["twitch:a"]["group"] == "FPS"
    assert by_key["twitch:a"]["order"] == 0
    assert by_key["twitch:b"]["group"] == "FPS"
    assert by_key["twitch:b"]["order"] == 1
    assert by_key["youtube:UCxxxxxxxxxxxxxxxxxxxxxx"]["group"] is None
    assert by_key["youtube:UCxxxxxxxxxxxxxxxxxxxxxx"]["order"] == 0


def test_reorder_favorites_rejects_system_group_names(
    temp_config_dir: Path, api_with_favorites: TwitchXApi
) -> None:
    payload = [
        {"key": "twitch:a", "group": "Online", "order": 0},
    ]

    api_with_favorites.reorder_favorites(json.dumps(payload))

    cfg = load_config()
    fav = next(f for f in cfg["favorites"] if f["login"] == "a")
    assert fav["group"] is None


def test_reorder_favorites_ignores_invalid_payload(
    temp_config_dir: Path, api_with_favorites: TwitchXApi
) -> None:
    api_with_favorites.reorder_favorites("not-json")
    cfg = load_config()
    assert len(cfg["favorites"]) == 3


def test_load_config_adds_group_order_to_legacy_favorites(
    temp_config_dir: Path,
) -> None:
    cfg = json.loads(temp_config_dir.read_text())
    cfg["favorites"] = [
        {"platform": "twitch", "login": "legacy", "display_name": "Legacy"},
    ]
    _write_config(temp_config_dir, cfg)

    loaded = load_config()
    fav = loaded["favorites"][0]
    assert "group" in fav
    assert "order" in fav
    assert fav["group"] is None
    assert fav["order"] == 0


def test_v1_migration_adds_group_order(temp_config_dir: Path) -> None:
    v1 = {
        "client_id": "cid",
        "client_secret": "secret",
        "access_token": "tok",
        "refresh_token": "ref",
        "favorites": ["streamer1", "streamer2"],
        "quality": "best",
    }
    temp_config_dir.write_text(json.dumps(v1))

    loaded = load_config()
    assert all("group" in f and "order" in f for f in loaded["favorites"])
