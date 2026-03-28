from __future__ import annotations

import json
import os
import time
from pathlib import Path

from core.storage import (
    DEFAULT_CONFIG,
    DEFAULT_SETTINGS,
    get_cached_avatar,
    get_favorite_logins,
    get_favorites,
    get_platform_config,
    get_settings,
    load_config,
    save_avatar,
    save_config,
    token_is_valid,
)


# ── Helper to patch storage paths ───────────────────────────


def _patch_storage(monkeypatch: object, tmp_path: Path) -> Path:
    import core.storage as mod

    config_file = tmp_path / "config.json"
    monkeypatch.setattr(mod, "CONFIG_DIR", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "CONFIG_FILE", config_file)  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "_OLD_CONFIG_DIR", tmp_path / "nonexistent")  # type: ignore[attr-defined]
    return config_file


# ── Config defaults / load / save ────────────────────────────


def test_load_config_defaults(tmp_path: Path, monkeypatch: object) -> None:
    _patch_storage(monkeypatch, tmp_path)

    config = load_config()
    for key in DEFAULT_CONFIG:
        assert key in config, f"Missing key: {key}"
    assert "platforms" in config
    assert "settings" in config
    assert "favorites" in config
    assert config["platforms"]["twitch"]["client_id"] == ""
    assert config["settings"]["refresh_interval"] == 60
    assert (tmp_path / "config.json").exists()


def test_load_config_deep_merge(tmp_path: Path, monkeypatch: object) -> None:
    """A v2 config on disk with partial platform data gets missing keys from defaults."""
    config_file = _patch_storage(monkeypatch, tmp_path)

    # Write a v2 config missing some twitch keys and missing kick/youtube entirely
    config_file.write_text(
        json.dumps(
            {
                "platforms": {
                    "twitch": {"client_id": "test123", "enabled": True},
                },
                "favorites": [],
                "settings": {"quality": "720p"},
            }
        )
    )

    config = load_config()
    # Stored value preserved
    assert config["platforms"]["twitch"]["client_id"] == "test123"
    assert config["settings"]["quality"] == "720p"
    # Missing twitch keys filled from defaults
    assert config["platforms"]["twitch"]["access_token"] == ""
    assert config["platforms"]["twitch"]["token_type"] == "app"
    # Missing platforms filled from defaults
    assert "kick" in config["platforms"]
    assert "youtube" in config["platforms"]
    # Missing settings filled from defaults
    assert config["settings"]["refresh_interval"] == 60


def test_save_and_reload(tmp_path: Path, monkeypatch: object) -> None:
    _patch_storage(monkeypatch, tmp_path)

    data = {
        "platforms": {
            "twitch": {**DEFAULT_CONFIG["platforms"]["twitch"], "client_id": "abc"},
            "kick": {**DEFAULT_CONFIG["platforms"]["kick"]},
            "youtube": {**DEFAULT_CONFIG["platforms"]["youtube"]},
        },
        "favorites": [{"platform": "twitch", "login": "streamer1", "display_name": "streamer1"}],
        "settings": {**DEFAULT_CONFIG["settings"]},
    }
    save_config(data)

    loaded = load_config()
    assert loaded["platforms"]["twitch"]["client_id"] == "abc"
    assert loaded["favorites"] == [
        {"platform": "twitch", "login": "streamer1", "display_name": "streamer1"}
    ]


# ── v1 → v2 migration ───────────────────────────────────────


def test_v1_migration_credentials(tmp_path: Path, monkeypatch: object) -> None:
    """v1 flat config migrates Twitch credentials into platforms.twitch."""
    config_file = _patch_storage(monkeypatch, tmp_path)

    v1 = {
        "client_id": "my_id",
        "client_secret": "my_secret",
        "access_token": "tok123",
        "token_expires_at": 9999999999,
        "favorites": ["xqc", "shroud"],
        "quality": "720p",
        "refresh_interval": 120,
        "streamlink_path": "/usr/bin/streamlink",
        "iina_path": "/usr/bin/iina",
        "user_id": "12345",
        "user_login": "myuser",
        "user_display_name": "MyUser",
        "refresh_token": "ref_tok",
        "token_type": "user",
        "player_height": 480,
    }
    config_file.write_text(json.dumps(v1))

    config = load_config()

    # Credentials moved to platforms.twitch
    assert config["platforms"]["twitch"]["client_id"] == "my_id"
    assert config["platforms"]["twitch"]["client_secret"] == "my_secret"
    assert config["platforms"]["twitch"]["access_token"] == "tok123"
    assert config["platforms"]["twitch"]["token_type"] == "user"
    assert config["platforms"]["twitch"]["user_login"] == "myuser"

    # Settings moved to settings
    assert config["settings"]["quality"] == "720p"
    assert config["settings"]["refresh_interval"] == 120
    assert config["settings"]["player_height"] == 480
    assert config["settings"]["streamlink_path"] == "/usr/bin/streamlink"

    # Favorites converted to objects
    assert config["favorites"] == [
        {"platform": "twitch", "login": "xqc", "display_name": "xqc"},
        {"platform": "twitch", "login": "shroud", "display_name": "shroud"},
    ]

    # Kick/YouTube defaults present
    assert config["platforms"]["kick"]["enabled"] is True
    assert config["platforms"]["youtube"]["enabled"] is True


def test_v1_migration_minimal(tmp_path: Path, monkeypatch: object) -> None:
    """v1 config with only a few keys still migrates correctly."""
    config_file = _patch_storage(monkeypatch, tmp_path)

    config_file.write_text(json.dumps({"client_id": "x", "favorites": ["a"]}))

    config = load_config()
    assert config["platforms"]["twitch"]["client_id"] == "x"
    assert config["favorites"] == [
        {"platform": "twitch", "login": "a", "display_name": "a"}
    ]
    # Defaults filled in
    assert config["settings"]["quality"] == "best"


def test_v2_config_no_remigration(tmp_path: Path, monkeypatch: object) -> None:
    """A config with 'platforms' key is already v2 and should not be re-migrated."""
    config_file = _patch_storage(monkeypatch, tmp_path)

    v2 = {
        "platforms": {
            "twitch": {"client_id": "already_v2", "enabled": True},
        },
        "favorites": [{"platform": "twitch", "login": "test", "display_name": "test"}],
        "settings": {"quality": "1080p"},
    }
    config_file.write_text(json.dumps(v2))

    config = load_config()
    assert config["platforms"]["twitch"]["client_id"] == "already_v2"
    assert config["favorites"] == [
        {"platform": "twitch", "login": "test", "display_name": "test"}
    ]
    assert config["settings"]["quality"] == "1080p"


def test_fresh_install_gets_v2(tmp_path: Path, monkeypatch: object) -> None:
    """Fresh install (no config file) produces v2 defaults."""
    _patch_storage(monkeypatch, tmp_path)

    config = load_config()
    assert "platforms" in config
    assert "twitch" in config["platforms"]
    assert "kick" in config["platforms"]
    assert "youtube" in config["platforms"]
    assert config["settings"]["quality"] == "best"
    assert config["favorites"] == []


# ── token_is_valid ───────────────────────────────────────────


def test_token_is_valid_with_platform_dict() -> None:
    """token_is_valid works with a platform section dict (not full config)."""
    platform = {
        "access_token": "tok",
        "token_expires_at": time.time() + 3600,
    }
    assert token_is_valid(platform) is True


def test_token_is_valid_expired() -> None:
    platform = {
        "access_token": "tok",
        "token_expires_at": time.time() - 100,
    }
    assert token_is_valid(platform) is False


def test_token_is_valid_missing_token() -> None:
    assert token_is_valid({"access_token": "", "token_expires_at": 0}) is False


# ── Convenience accessors ────────────────────────────────────


def test_get_platform_config() -> None:
    config = {
        "platforms": {"twitch": {"client_id": "abc"}},
    }
    assert get_platform_config(config, "twitch") == {"client_id": "abc"}
    assert get_platform_config(config, "kick") == {}


def test_get_settings() -> None:
    config = {"settings": {"quality": "720p"}}
    assert get_settings(config)["quality"] == "720p"

    # Missing settings returns defaults
    assert get_settings({})["quality"] == "best"


def test_get_favorites_filtered() -> None:
    config = {
        "favorites": [
            {"platform": "twitch", "login": "xqc", "display_name": "xQc"},
            {"platform": "kick", "login": "adin", "display_name": "Adin"},
            {"platform": "twitch", "login": "shroud", "display_name": "shroud"},
        ]
    }
    assert len(get_favorites(config)) == 3
    assert len(get_favorites(config, "twitch")) == 2
    assert len(get_favorites(config, "kick")) == 1
    assert len(get_favorites(config, "youtube")) == 0


def test_get_favorite_logins() -> None:
    config = {
        "favorites": [
            {"platform": "twitch", "login": "xqc", "display_name": "xQc"},
            {"platform": "kick", "login": "adin", "display_name": "Adin"},
        ]
    }
    assert get_favorite_logins(config, "twitch") == ["xqc"]
    assert get_favorite_logins(config, "kick") == ["adin"]
    assert get_favorite_logins(config, "youtube") == []


# ── Avatar disk cache ────────────────────────────────────────


def test_get_cached_avatar_missing(tmp_path: Path, monkeypatch: object) -> None:
    import core.storage as mod

    monkeypatch.setattr(mod, "AVATAR_DIR", tmp_path)  # type: ignore[attr-defined]

    result = get_cached_avatar("nonexistent_user")
    assert result is None


def test_get_cached_avatar_expired(tmp_path: Path, monkeypatch: object) -> None:
    import core.storage as mod

    monkeypatch.setattr(mod, "AVATAR_DIR", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "_AVATAR_MAX_AGE", 0)  # type: ignore[attr-defined]

    platform_dir = tmp_path / "twitch"
    platform_dir.mkdir()
    avatar_file = platform_dir / "olduser.png"
    avatar_file.write_bytes(b"fake_png_data")
    os.utime(avatar_file, (time.time() - 100, time.time() - 100))

    result = get_cached_avatar("olduser")
    assert result is None


def test_get_cached_avatar_fresh(tmp_path: Path, monkeypatch: object) -> None:
    import core.storage as mod

    monkeypatch.setattr(mod, "AVATAR_DIR", tmp_path)  # type: ignore[attr-defined]

    platform_dir = tmp_path / "twitch"
    platform_dir.mkdir()
    avatar_file = platform_dir / "freshuser.png"
    avatar_file.write_bytes(b"fresh_avatar_data")

    result = get_cached_avatar("freshuser")
    assert result == b"fresh_avatar_data"


def test_save_avatar_creates_dir(tmp_path: Path, monkeypatch: object) -> None:
    import core.storage as mod

    avatar_dir = tmp_path / "avatars_new"
    monkeypatch.setattr(mod, "AVATAR_DIR", avatar_dir)  # type: ignore[attr-defined]

    assert not avatar_dir.exists()
    save_avatar("testuser", b"\x89PNG_fake_data")
    assert (avatar_dir / "twitch").exists()
    assert (avatar_dir / "twitch" / "testuser.png").read_bytes() == b"\x89PNG_fake_data"


def test_save_avatar_custom_platform(tmp_path: Path, monkeypatch: object) -> None:
    import core.storage as mod

    monkeypatch.setattr(mod, "AVATAR_DIR", tmp_path)  # type: ignore[attr-defined]

    save_avatar("streamer", b"kick_data", platform="kick")
    assert (tmp_path / "kick" / "streamer.png").read_bytes() == b"kick_data"

    result = get_cached_avatar("streamer", platform="kick")
    assert result == b"kick_data"
