from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.storage import DEFAULT_CONFIG, DEFAULT_SETTINGS, load_config, save_config
from ui.api import TwitchXApi


def test_default_settings_has_accent_color():
    assert DEFAULT_SETTINGS["accent_color"] == "#FF9F0A"


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


def test_get_full_config_returns_accent_color(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda js: None)
    result = api.get_full_config_for_settings()
    assert result["accent_color"] == "#FF9F0A"


def test_save_settings_persists_accent_color(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TwitchXApi()
    monkeypatch.setattr(api, "_eval_js", lambda js: None)
    api.save_settings(json.dumps({"accent_color": "#BF5AF2"}))
    config = load_config()
    assert config["settings"]["accent_color"] == "#BF5AF2"


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
