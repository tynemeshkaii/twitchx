from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "twitchx"
CONFIG_FILE = CONFIG_DIR / "config.json"

_OLD_CONFIG_DIR = Path.home() / ".config" / "streamdeck"

# ── Per-platform defaults ───────────────────────────────────

DEFAULT_PLATFORM_TWITCH: dict[str, Any] = {
    "enabled": True,
    "client_id": "",
    "client_secret": "",
    "access_token": "",
    "refresh_token": "",
    "token_expires_at": 0,
    "token_type": "app",
    "user_id": "",
    "user_login": "",
    "user_display_name": "",
}

DEFAULT_PLATFORM_KICK: dict[str, Any] = {
    "enabled": True,
    "client_id": "",
    "client_secret": "",
    "access_token": "",
    "refresh_token": "",
    "token_expires_at": 0,
    "pkce_verifier": "",
    "user_id": "",
    "user_login": "",
    "user_display_name": "",
}

DEFAULT_PLATFORM_YOUTUBE: dict[str, Any] = {
    "enabled": True,
    "client_id": "",
    "client_secret": "",
    "access_token": "",
    "refresh_token": "",
    "token_expires_at": 0,
    "user_id": "",
    "user_login": "",
    "user_display_name": "",
    "daily_quota_used": 0,
    "quota_reset_date": "",
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "quality": "best",
    "refresh_interval": 60,
    "youtube_refresh_interval": 300,
    "streamlink_path": "streamlink",
    "iina_path": "/Applications/IINA.app/Contents/MacOS/iina-cli",
    "notifications_enabled": True,
    "player_height": 360,
    "chat_visible": True,
    "chat_width": 340,
    "active_platform_filter": "all",
    "pip_enabled": False,
}

DEFAULT_CONFIG: dict[str, Any] = {
    "platforms": {
        "twitch": {**DEFAULT_PLATFORM_TWITCH},
        "kick": {**DEFAULT_PLATFORM_KICK},
        "youtube": {**DEFAULT_PLATFORM_YOUTUBE},
    },
    "favorites": [],
    "settings": {**DEFAULT_SETTINGS},
}

# Keys that belong in platforms.twitch when migrating from v1
_V1_PLATFORM_KEYS = {
    "client_id",
    "client_secret",
    "access_token",
    "refresh_token",
    "token_expires_at",
    "token_type",
    "user_id",
    "user_login",
    "user_display_name",
}

# Keys that belong in settings when migrating from v1
_V1_SETTINGS_KEYS = {
    "quality",
    "refresh_interval",
    "streamlink_path",
    "iina_path",
    "player_height",
}


def _deep_merge(defaults: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into defaults. Override values win for non-dict types."""
    result = dict(defaults)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _is_v1_config(stored: dict[str, Any]) -> bool:
    """Check if config is v1 format (flat keys at root, no 'platforms' key)."""
    return "platforms" not in stored and (
        "client_id" in stored or "quality" in stored or "favorites" in stored
    )


def _migrate_v1_to_v2(v1: dict[str, Any]) -> dict[str, Any]:
    """Migrate a v1 flat config to v2 nested format."""
    v2: dict[str, Any] = {
        "platforms": {
            "twitch": {**DEFAULT_PLATFORM_TWITCH},
            "kick": {**DEFAULT_PLATFORM_KICK},
            "youtube": {**DEFAULT_PLATFORM_YOUTUBE},
        },
        "favorites": [],
        "settings": {**DEFAULT_SETTINGS},
    }

    # Move Twitch credentials
    for key in _V1_PLATFORM_KEYS:
        if key in v1:
            v2["platforms"]["twitch"][key] = v1[key]

    # Move settings
    for key in _V1_SETTINGS_KEYS:
        if key in v1:
            v2["settings"][key] = v1[key]

    # Convert favorites from list of strings to list of objects
    old_favs = v1.get("favorites", [])
    if old_favs and isinstance(old_favs, list):
        for fav in old_favs:
            if isinstance(fav, str):
                v2["favorites"].append({
                    "platform": "twitch",
                    "login": fav,
                    "display_name": fav,
                })
            elif isinstance(fav, dict):
                # Already an object, keep it
                v2["favorites"].append(fav)

    return v2


def _migrate_old_config() -> None:
    """One-time migration from ~/.config/streamdeck/ to ~/.config/twitchx/."""
    old_config = _OLD_CONFIG_DIR / "config.json"
    if old_config.exists() and not CONFIG_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_config, CONFIG_FILE)
        old_avatars = _OLD_CONFIG_DIR / "avatars"
        new_avatars = CONFIG_DIR / "avatars"
        if old_avatars.is_dir() and not new_avatars.exists():
            shutil.copytree(old_avatars, new_avatars)


def load_config() -> dict[str, Any]:
    _migrate_old_config()
    if not CONFIG_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        save_config(DEFAULT_CONFIG)
        return _deep_merge(DEFAULT_CONFIG, {})
    with open(CONFIG_FILE) as f:
        stored = json.load(f)

    # Auto-migrate v1 → v2
    if _is_v1_config(stored):
        stored = _migrate_v1_to_v2(stored)
        save_config(stored)

    merged = _deep_merge(DEFAULT_CONFIG, stored)
    return merged


def save_config(config: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def token_is_valid(config: dict[str, Any]) -> bool:
    return (
        bool(config.get("access_token"))
        and config.get("token_expires_at", 0) > time.time() + 60
    )


# ── Convenience accessors ───────────────────────────────────


def get_platform_config(config: dict[str, Any], platform: str) -> dict[str, Any]:
    """Get the config section for a specific platform."""
    return config.get("platforms", {}).get(platform, {})


def get_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Get the settings section."""
    return config.get("settings", {**DEFAULT_SETTINGS})


def get_favorites(
    config: dict[str, Any], platform: str | None = None
) -> list[dict[str, Any]]:
    """Get favorites, optionally filtered by platform."""
    favs = config.get("favorites", [])
    if platform:
        return [f for f in favs if f.get("platform") == platform]
    return favs


def get_favorite_logins(config: dict[str, Any], platform: str) -> list[str]:
    """Get just the login names for a specific platform's favorites."""
    return [f["login"] for f in get_favorites(config, platform)]


# ── Avatar disk cache ────────────────────────────────────────

AVATAR_DIR = CONFIG_DIR / "avatars"
_AVATAR_MAX_AGE = 7 * 24 * 3600  # 7 days


def get_cached_avatar(login: str, platform: str = "twitch") -> bytes | None:
    """Return raw PNG bytes if a fresh disk-cached avatar exists."""
    path = AVATAR_DIR / platform / f"{login}.png"
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > _AVATAR_MAX_AGE:
        return None
    return path.read_bytes()


def save_avatar(login: str, data: bytes, platform: str = "twitch") -> None:
    """Persist raw image bytes to disk cache."""
    platform_dir = AVATAR_DIR / platform
    platform_dir.mkdir(parents=True, exist_ok=True)
    (platform_dir / f"{login}.png").write_bytes(data)
