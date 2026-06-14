from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.storage import (
    DEFAULT_CONFIG,
    DEFAULT_SETTINGS,
    load_config,
    save_config,
)
from ui.api import TwitchXApi


def test_default_settings_has_accent_color():
    assert DEFAULT_SETTINGS["accent_color"] == "#FF9F0A"


def test_default_settings_has_theme():
    assert DEFAULT_SETTINGS["theme"] == "dark"


def test_load_config_fills_accent_color_when_missing(temp_config_dir: Path) -> None:
    """Deep merge adds accent_color even if stored config lacks it."""
    stored = {
        "platforms": DEFAULT_CONFIG["platforms"],
        "favorites": [],
        "settings": {"quality": "best"},  # no accent_color
    }
    save_config(stored)
    config = load_config()
    assert config["settings"]["accent_color"] == "#FF9F0A"


def test_load_config_fills_theme_when_missing(temp_config_dir: Path) -> None:
    """Deep merge adds theme even if stored config lacks it."""
    stored = {
        "platforms": DEFAULT_CONFIG["platforms"],
        "favorites": [],
        "settings": {"quality": "best"},  # no theme
    }
    save_config(stored)
    config = load_config()
    assert config["settings"]["theme"] == "dark"


def test_get_full_config_returns_accent_color(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda js: None)
    result = api.get_full_config_for_settings()
    assert result["accent_color"] == "#FF9F0A"


def test_get_full_config_returns_theme(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda js: None)
    result = api.get_full_config_for_settings()
    assert result["theme"] == "dark"


def test_save_settings_persists_accent_color(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda js: None)
    api.save_settings(json.dumps({"accent_color": "#BF5AF2"}))
    config = load_config()
    assert config["settings"]["accent_color"] == "#BF5AF2"


@pytest.mark.parametrize("theme", ["auto", "dark", "light"])
def test_save_settings_persists_theme(
    theme: str, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda js: None)
    api.save_settings(json.dumps({"theme": theme}))
    config = load_config()
    assert config["settings"]["theme"] == theme


def test_save_settings_rejects_invalid_theme(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only auto/dark/light are accepted; unknown values are ignored."""
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda js: None)
    api.save_settings(json.dumps({"theme": "hacker"}))
    config = load_config()
    assert config["settings"]["theme"] == "dark"


def test_save_settings_rejects_invalid_accent_color(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only palette values are accepted; unknown strings are ignored."""
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda js: None)
    api.save_settings(json.dumps({"accent_color": "javascript:alert(1)"}))
    config = load_config()
    # Falls back to default because the value is not in the allowed palette
    assert config["settings"]["accent_color"] == "#FF9F0A"


# ── Credential state fields ──────────────────────────────────────────────────


def test_twitch_using_bundled_is_true_by_default(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fresh install: no custom Twitch credentials → twitch_using_bundled=True."""
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda js: None)
    result = api.get_full_config_for_settings()
    assert result["twitch_using_bundled"] is True


def test_twitch_using_bundled_is_false_when_custom_creds_saved(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After saving custom Twitch credentials → twitch_using_bundled=False."""
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda js: None)
    api.save_settings(json.dumps({"client_id": "myid", "client_secret": "mysecret"}))
    result = api.get_full_config_for_settings()
    assert result["twitch_using_bundled"] is False


def test_kick_using_bundled_is_true_by_default(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fresh install: no custom Kick credentials → kick_using_bundled=True."""
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda js: None)
    result = api.get_full_config_for_settings()
    assert result["kick_using_bundled"] is True


def test_youtube_bundled_available_is_always_false(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """YouTube has no real bundled credentials; youtube_bundled_available must be False."""
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda js: None)
    result = api.get_full_config_for_settings()
    assert result["youtube_bundled_available"] is False


def test_youtube_using_bundled_api_key_true_when_no_custom_key(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No custom API key configured → youtube_using_bundled_api_key=True (no custom key)."""
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda js: None)
    result = api.get_full_config_for_settings()
    assert result["youtube_using_bundled_api_key"] is True


def test_youtube_using_bundled_api_key_false_when_custom_key_saved(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After saving a custom YouTube API key → youtube_using_bundled_api_key=False."""
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda js: None)
    api.save_settings(json.dumps({"youtube_api_key": "AIzaSy_my_key"}))
    result = api.get_full_config_for_settings()
    assert result["youtube_using_bundled_api_key"] is False
    assert result["youtube_bundled_available"] is False  # still False regardless


def test_credential_state_fields_all_present(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All credential state fields are present in get_full_config_for_settings."""
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda js: None)
    result = api.get_full_config_for_settings()
    for key in (
        "twitch_using_bundled",
        "kick_using_bundled",
        "youtube_using_bundled_oauth",
        "youtube_using_bundled_api_key",
        "youtube_bundled_available",
    ):
        assert key in result, f"Missing credential state field: {key}"
