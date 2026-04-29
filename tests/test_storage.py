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

# ── Config defaults / load / save ────────────────────────────


def test_load_config_defaults(temp_config_dir: Path) -> None:
    config = load_config()
    for key in DEFAULT_CONFIG:
        assert key in config, f"Missing key: {key}"
    assert "platforms" in config
    assert "settings" in config
    assert "favorites" in config
    assert config["platforms"]["twitch"]["client_id"] == ""
    assert config["settings"]["refresh_interval"] == 60
    assert temp_config_dir.exists()


def test_load_config_deep_merge(temp_config_dir: Path) -> None:
    """A v2 config on disk with partial platform data gets missing keys from defaults."""

    # Write a v2 config missing some twitch keys and missing kick/youtube entirely
    temp_config_dir.write_text(
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


def test_save_and_reload(temp_config_dir: Path) -> None:

    data = {
        "platforms": {
            "twitch": {**DEFAULT_CONFIG["platforms"]["twitch"], "client_id": "abc"},
            "kick": {**DEFAULT_CONFIG["platforms"]["kick"]},
            "youtube": {**DEFAULT_CONFIG["platforms"]["youtube"]},
        },
        "favorites": [
            {"platform": "twitch", "login": "streamer1", "display_name": "streamer1"}
        ],
        "settings": {**DEFAULT_CONFIG["settings"]},
    }
    save_config(data)

    loaded = load_config()
    assert loaded["platforms"]["twitch"]["client_id"] == "abc"
    assert loaded["favorites"] == [
        {"platform": "twitch", "login": "streamer1", "display_name": "streamer1"}
    ]


# ── v1 → v2 migration ───────────────────────────────────────


def test_v1_migration_credentials(temp_config_dir: Path) -> None:
    """v1 flat config migrates Twitch credentials into platforms.twitch."""

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
    temp_config_dir.write_text(json.dumps(v1))

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


def test_v1_migration_minimal(temp_config_dir: Path) -> None:
    """v1 config with only a few keys still migrates correctly."""

    temp_config_dir.write_text(json.dumps({"client_id": "x", "favorites": ["a"]}))

    config = load_config()
    assert config["platforms"]["twitch"]["client_id"] == "x"
    assert config["favorites"] == [
        {"platform": "twitch", "login": "a", "display_name": "a"}
    ]
    # Defaults filled in
    assert config["settings"]["quality"] == "best"


def test_v2_config_no_remigration(temp_config_dir: Path) -> None:
    """A config with 'platforms' key is already v2 and should not be re-migrated."""

    v2 = {
        "platforms": {
            "twitch": {"client_id": "already_v2", "enabled": True},
        },
        "favorites": [{"platform": "twitch", "login": "test", "display_name": "test"}],
        "settings": {"quality": "1080p"},
    }
    temp_config_dir.write_text(json.dumps(v2))

    config = load_config()
    assert config["platforms"]["twitch"]["client_id"] == "already_v2"
    assert config["favorites"] == [
        {"platform": "twitch", "login": "test", "display_name": "test"}
    ]
    assert config["settings"]["quality"] == "1080p"


def test_fresh_install_gets_v2(temp_config_dir: Path) -> None:
    """Fresh install (no config file) produces v2 defaults."""

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
    monkeypatch.setattr(mod, "AVATAR_CACHE_TTL_SECONDS", 0)  # type: ignore[attr-defined]

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


def test_keyboard_shortcuts_in_default_settings() -> None:
    sc = DEFAULT_SETTINGS["keyboard_shortcuts"]
    assert sc["refresh"] == "r"
    assert sc["watch"] == " "
    assert sc["fullscreen"] == "f"
    assert sc["toggle_chat"] == "c"
    assert sc["mute"] == "m"
    assert sc["pip"] == "p"
    assert sc["volume_up"] == "ArrowUp"
    assert sc["volume_down"] == "ArrowDown"
    assert sc["next_stream"] == "ArrowRight"
    assert sc["prev_stream"] == "ArrowLeft"


def test_keyboard_shortcuts_deep_merged_from_stored(
    temp_config_dir: Path,
) -> None:
    temp_config_dir.write_text(
        json.dumps(
            {
                "platforms": {},
                "favorites": [],
                "settings": {
                    "keyboard_shortcuts": {"refresh": "G", "mute": "N"},
                },
            }
        )
    )
    config = load_config()
    sc = config["settings"]["keyboard_shortcuts"]
    assert sc["refresh"] == "G"  # stored value wins
    assert sc["mute"] == "N"  # stored value wins
    assert sc["watch"] == " "  # default kept
    assert sc["fullscreen"] == "f"  # default kept
    assert sc["pip"] == "p"  # default kept


# ── _migrate_favorites_v2 ────────────────────────────────────


def test_migrate_favorites_v2_cleans_v1_urls(temp_config_dir: Path) -> None:
    """v1 string favorites are converted to v2 dict objects."""
    temp_config_dir.write_text(
        json.dumps(
            {
                "platforms": {"twitch": {}, "kick": {}, "youtube": {}},
                "favorites": [
                    "https://twitch.tv/xqc",
                    "just_ns",
                    "twitch.tv/xqc",
                    "good123",
                ],
                "settings": {},
            }
        )
    )

    config = load_config()
    assert config["favorites"] == [
        {"platform": "twitch", "login": "xqc", "display_name": "xqc"},
        {"platform": "twitch", "login": "just_ns", "display_name": "just_ns"},
        {"platform": "twitch", "login": "good123", "display_name": "good123"},
    ]


def test_migrate_favorites_v2_noop_clean_v2(temp_config_dir: Path) -> None:
    """Clean v2 favorites are not re-saved."""
    temp_config_dir.write_text(
        json.dumps(
            {
                "platforms": {"twitch": {}, "kick": {}, "youtube": {}},
                "favorites": [
                    {"platform": "twitch", "login": "xqc", "display_name": "xQc"},
                    {
                        "platform": "kick",
                        "login": "trainwreck",
                        "display_name": "Trainwreck",
                    },
                ],
                "settings": {},
            }
        )
    )

    mtime_before = temp_config_dir.stat().st_mtime
    config = load_config()
    mtime_after = temp_config_dir.stat().st_mtime
    # No save needed — already clean
    assert mtime_after == mtime_before
    assert config["favorites"] == [
        {"platform": "twitch", "login": "xqc", "display_name": "xQc"},
        {
            "platform": "kick",
            "login": "trainwreck",
            "display_name": "Trainwreck",
        },
    ]


def test_migrate_favorites_v2_deduplicates_v2(temp_config_dir: Path) -> None:
    """Duplicate v2 favorites are removed."""
    temp_config_dir.write_text(
        json.dumps(
            {
                "platforms": {"twitch": {}, "kick": {}, "youtube": {}},
                "favorites": [
                    {"platform": "twitch", "login": "xqc", "display_name": "xQc"},
                    {"platform": "twitch", "login": "xqc", "display_name": "xQc"},
                ],
                "settings": {},
            }
        )
    )

    config = load_config()
    assert len(config["favorites"]) == 1


def test_migrate_favorites_v2_same_login_different_platforms_kept(
    temp_config_dir: Path,
) -> None:
    """Same login on different platforms are NOT deduplicated."""
    temp_config_dir.write_text(
        json.dumps(
            {
                "platforms": {"twitch": {}, "kick": {}, "youtube": {}},
                "favorites": [
                    {"platform": "twitch", "login": "xqc", "display_name": "xQc"},
                    {"platform": "kick", "login": "xqc", "display_name": "xQc"},
                ],
                "settings": {},
            }
        )
    )

    mtime_before = temp_config_dir.stat().st_mtime
    config = load_config()
    mtime_after = temp_config_dir.stat().st_mtime
    assert len(config["favorites"]) == 2
    assert mtime_after == mtime_before  # No change needed


def test_migrate_favorites_v2_keeps_kick_slug_hyphen(temp_config_dir: Path) -> None:
    temp_config_dir.write_text(
        json.dumps(
            {
                "platforms": {"twitch": {}, "kick": {}, "youtube": {}},
                "favorites": [
                    {
                        "platform": "kick",
                        "login": "train-wreck",
                        "display_name": "Train Wreck",
                    },
                ],
                "settings": {},
            }
        )
    )

    mtime_before = temp_config_dir.stat().st_mtime
    config = load_config()
    mtime_after = temp_config_dir.stat().st_mtime
    assert config["favorites"][0]["login"] == "train-wreck"
    assert mtime_after == mtime_before


def test_migrate_favorites_v2_normalizes_kick_url(temp_config_dir: Path) -> None:
    temp_config_dir.write_text(
        json.dumps(
            {
                "platforms": {"twitch": {}, "kick": {}, "youtube": {}},
                "favorites": [
                    {
                        "platform": "kick",
                        "login": "https://kick.com/train-wreck",
                        "display_name": "Train Wreck",
                    },
                ],
                "settings": {},
            }
        )
    )

    config = load_config()
    assert config["favorites"][0]["login"] == "train-wreck"


def test_migrate_favorites_v2_idempotent(temp_config_dir: Path) -> None:
    """Repeated load_config calls do not corrupt favorites."""
    temp_config_dir.write_text(
        json.dumps(
            {
                "platforms": {"twitch": {}, "kick": {}, "youtube": {}},
                "favorites": [
                    {"platform": "twitch", "login": "xqc", "display_name": "xQc"},
                ],
                "settings": {},
            }
        )
    )

    config1 = load_config()
    config2 = load_config()
    assert config1["favorites"] == config2["favorites"]


def test_migrate_favorites_v2_preserves_youtube_handle(temp_config_dir: Path) -> None:
    """YouTube @handle login must keep the @ prefix during migration."""
    temp_config_dir.write_text(
        json.dumps(
            {
                "platforms": {"twitch": {}, "kick": {}, "youtube": {}},
                "favorites": [
                    {
                        "platform": "youtube",
                        "login": "@MrBeast",
                        "display_name": "MrBeast",
                    },
                ],
                "settings": {},
            }
        )
    )

    config = load_config()
    assert config["favorites"][0]["login"] == "@mrbeast"


def test_migrate_favorites_v2_preserves_youtube_video_prefix(
    temp_config_dir: Path,
) -> None:
    """YouTube v: prefix must be preserved during migration."""
    temp_config_dir.write_text(
        json.dumps(
            {
                "platforms": {"twitch": {}, "kick": {}, "youtube": {}},
                "favorites": [
                    {
                        "platform": "youtube",
                        "login": "v:dQw4w9WgXcQ",
                        "display_name": "Rick Astley",
                    },
                ],
                "settings": {},
            }
        )
    )

    config = load_config()
    assert config["favorites"][0]["login"] == "v:dQw4w9WgXcQ"


def test_migrate_favorites_v2_preserves_youtube_channel_id(
    temp_config_dir: Path,
) -> None:
    """Bare UC channel ID must stay intact (case-sensitive)."""
    temp_config_dir.write_text(
        json.dumps(
            {
                "platforms": {"twitch": {}, "kick": {}, "youtube": {}},
                "favorites": [
                    {
                        "platform": "youtube",
                        "login": "UCX6OQ3DkcsbYNE6H8uQQuVA",
                        "display_name": "Test Channel",
                    },
                ],
                "settings": {},
            }
        )
    )

    config = load_config()
    assert config["favorites"][0]["login"] == "UCX6OQ3DkcsbYNE6H8uQQuVA"
