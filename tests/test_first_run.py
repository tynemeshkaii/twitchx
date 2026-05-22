from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import core.storage as storage
from core.storage import DEFAULT_CONFIG, get_favorite_logins, get_favorites, load_config
from ui.api import TwitchXApi


def test_fresh_install_no_config_file_creates_defaults(
    temp_config_dir: Path,
) -> None:
    """Simulates first launch: config file does not exist yet."""
    temp_config_dir.unlink()
    config = load_config()
    assert config["favorites"] == []
    assert config["settings"]["quality"] == "best"
    assert config["platforms"]["twitch"]["client_id"] == ""
    assert temp_config_dir.exists()  # load_config must create the file


def test_fresh_install_favorites_empty(temp_config_dir: Path) -> None:
    config = load_config()
    assert get_favorites(config) == []
    assert get_favorite_logins(config, "twitch") == []
    assert get_favorite_logins(config, "kick") == []
    assert get_favorite_logins(config, "youtube") == []


def test_add_first_channel_populates_favorites(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adding the very first channel persists correctly."""
    api = TwitchXApi()
    monkeypatch.setattr(api, "refresh", lambda: None)

    api.add_channel("xqc", platform="twitch")

    config = load_config()
    assert len(config["favorites"]) == 1
    assert config["favorites"][0]["login"] == "xqc"
    assert config["favorites"][0]["platform"] == "twitch"


def test_add_first_channel_then_second_keeps_both(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    monkeypatch.setattr(api, "refresh", lambda: None)

    api.add_channel("xqc", platform="twitch")
    api.add_channel("shroud", platform="twitch")

    config = load_config()
    logins = get_favorite_logins(config, "twitch")
    assert "xqc" in logins
    assert "shroud" in logins
    assert len(logins) == 2


def test_no_oauth_tokens_does_not_crash_load_config(temp_config_dir: Path) -> None:
    """Config with no OAuth tokens loads without error."""
    config = load_config()
    assert config["platforms"]["twitch"]["access_token"] == ""
    assert config["platforms"]["twitch"]["token_type"] == "app"
