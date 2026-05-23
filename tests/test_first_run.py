from __future__ import annotations

from pathlib import Path

import pytest

from core.storage import get_favorite_logins, get_favorites, load_config
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
    monkeypatch.setattr(api._data, "refresh", lambda: None)

    api.add_channel("xqc", platform="twitch")

    config = load_config()
    assert len(config["favorites"]) == 1
    assert config["favorites"][0]["login"] == "xqc"
    assert config["favorites"][0]["platform"] == "twitch"


def test_add_first_channel_then_second_keeps_both(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    monkeypatch.setattr(api._data, "refresh", lambda: None)

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


# ── First-run credential / onboarding state ──────────────────────────────────

def test_first_run_twitch_kick_use_bundled_credentials(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On first run, Twitch and Kick report bundled credentials (no custom creds needed)."""
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda js: None)
    result = api.get_full_config_for_settings()
    assert result["twitch_using_bundled"] is True, "Twitch should use bundled on first run"
    assert result["kick_using_bundled"] is True, "Kick should use bundled on first run"


def test_first_run_youtube_has_no_bundled_credentials(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On first run, YouTube signals no valid bundled credentials — user must provide their own."""
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda js: None)
    result = api.get_full_config_for_settings()
    assert result["youtube_bundled_available"] is False
    assert result["youtube_using_bundled_api_key"] is True  # no custom key set yet
    assert result["youtube_api_key"] == ""  # field is blank on first run


def test_first_run_no_logged_in_users(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On first run, no platform has a logged-in user."""
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda js: None)
    result = api.get_full_config_for_settings()
    assert result["kick_display_name"] == ""
    assert result["youtube_display_name"] == ""
