from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.constants import (
    AVATAR_CACHE_TTL_SECONDS,
    BROWSE_CACHE_TTL_SECONDS,
    CONFIG_DIR_NAME,
    CONFIG_FILE_NAME,
    DEFAULT_IINA_PATH,
    DEFAULT_MPV_PATH,
    DEFAULT_RECORDING_DIR,
)
from core.utils import sanitize_kick_slug, sanitize_twitch_login, sanitize_youtube_login

CONFIG_DIR = Path.home() / ".config" / CONFIG_DIR_NAME
CONFIG_FILE = CONFIG_DIR / CONFIG_FILE_NAME

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
    "oauth_scopes": "",
    "pkce_verifier": "",
    "oauth_state": "",
    "user_id": "",
    "user_login": "",
    "user_display_name": "",
}

DEFAULT_PLATFORM_YOUTUBE: dict[str, Any] = {
    "enabled": True,
    "api_key": "",
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
    "iina_path": DEFAULT_IINA_PATH,
    "external_player": "iina",
    "mpv_path": DEFAULT_MPV_PATH,
    "recording_path": DEFAULT_RECORDING_DIR,
    "notifications_enabled": True,
    "player_height": 360,
    "chat_visible": True,
    "chat_width": 340,
    "active_platform_filter": "all",
    "pip_enabled": False,
    "low_latency_mode": False,
    "chat_filter_sub_only": False,
    "chat_filter_mod_only": False,
    "chat_block_list": [],
    "chat_anti_spam": True,
    "keyboard_shortcuts": {
        "refresh": "r",
        "watch": " ",
        "fullscreen": "f",
        "toggle_chat": "c",
        "mute": "m",
        "pip": "p",
        "volume_up": "ArrowUp",
        "volume_down": "ArrowDown",
        "next_stream": "ArrowRight",
        "prev_stream": "ArrowLeft",
    },
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
                v2["favorites"].append(
                    {
                        "platform": "twitch",
                        "login": fav,
                        "display_name": fav,
                    }
                )
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


def _migrate_favorites_v2(cfg: dict[str, Any]) -> bool:
    """Normalize and deduplicate favorites. Idempotent.

    - Restores mangled YouTube logins from display_name
    - Deduplicates YouTube channels preferring human-readable display_name
    - Converts v1 string favorites to v2 dict objects

    Mutates cfg in-place and returns whether any changes were made.
    """
    raw = cfg.get("favorites", [])
    changed = False

    # Regex for a valid YouTube channel ID (UC + 22 word/hyphen chars)
    _yt_id_re = re.compile(r"^UC[\w-]{22}$", re.IGNORECASE)

    # ── Phase 1: restore YouTube logins that were mangled on entry ────────
    pre: list[Any] = []
    for entry in raw:
        if isinstance(entry, dict) and entry.get("platform") == "youtube":
            login: str = entry.get("login", "")
            disp: str = entry.get("display_name", "")
            if (
                login
                and disp
                and login != disp
                and (
                    login.lower() == disp.lower()
                    or (_yt_id_re.match(disp) and not _yt_id_re.match(login))
                )
            ):
                entry = {**entry, "login": disp}
                changed = True
        pre.append(entry)

    # ── Phase 2: for each YouTube channel, pick the entry with the best
    # display_name (a real human name beats a raw channel ID).
    yt_best: dict[str, dict[str, Any]] = {}
    for entry in pre:
        if not isinstance(entry, dict) or entry.get("platform") != "youtube":
            continue
        login = entry.get("login", "")
        if not login:
            continue
        k = login.lower()
        existing = yt_best.get(k)
        if existing is None:
            yt_best[k] = entry
        elif _yt_id_re.match(existing.get("display_name", "")) and not _yt_id_re.match(
            entry.get("display_name", "")
        ):
            yt_best[k] = entry
            changed = True

    # ── Phase 3: standard dedup + legacy string → dict conversion ────────
    cleaned: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for entry in pre:
        if isinstance(entry, str):
            name = sanitize_twitch_login(entry)
            if not name:
                changed = True
                continue
            key: tuple[str, str] = ("twitch", name)
            if key in seen:
                changed = True
                continue
            seen.add(key)
            cleaned.append({"platform": "twitch", "login": name, "display_name": name})
            changed = True

        elif isinstance(entry, dict):
            login = entry.get("login", "")
            platform: str = entry.get("platform", "twitch")
            if platform == "youtube":
                name = sanitize_youtube_login(login) if login else ""
            elif platform == "kick":
                name = sanitize_kick_slug(login) if login else ""
            else:
                name = sanitize_twitch_login(login) if login else ""
            if not name:
                changed = True
                continue
            dedup_login = name.lower() if platform == "youtube" else name
            key = (platform, dedup_login)
            if key in seen:
                changed = True
                continue
            seen.add(key)

            if platform == "youtube":
                if name != login:
                    entry = {**entry, "login": name}
                    changed = True
                best = yt_best.get(name.lower(), entry)
                if best is not entry:
                    best_display = best.get("display_name", "")
                    entry_display = entry.get("display_name", "")
                    if best_display != entry_display:
                        entry = {**entry, "display_name": best_display}
                        changed = True
                cleaned.append(entry)
            else:
                if name != login:
                    entry = {**entry, "login": name}
                    changed = True
                cleaned.append(entry)

        else:
            changed = True

    if changed:
        cfg["favorites"] = cleaned
    return changed


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

    favorites_changed = _migrate_favorites_v2(stored)
    merged = _deep_merge(DEFAULT_CONFIG, stored)
    if favorites_changed:
        save_config(merged)
    return merged


def save_config(config: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(config, f, indent=2)
    os.replace(tmp, CONFIG_FILE)


_config_lock = threading.Lock()


def update_config(update_fn: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Atomically load config, apply update_fn, save, and return the result.

    This prevents race conditions where multiple threads load stale config
    copies and overwrite each other's changes.
    """
    with _config_lock:
        config = load_config()
        update_fn(config)
        save_config(config)
        return config


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


def get_cached_avatar(login: str, platform: str = "twitch") -> bytes | None:
    """Return raw PNG bytes if a fresh disk-cached avatar exists."""
    path = AVATAR_DIR / platform / f"{login}.png"
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > AVATAR_CACHE_TTL_SECONDS:
        return None
    return path.read_bytes()


def save_avatar(login: str, data: bytes, platform: str = "twitch") -> None:
    """Persist raw image bytes to disk cache."""
    platform_dir = AVATAR_DIR / platform
    platform_dir.mkdir(parents=True, exist_ok=True)
    (platform_dir / f"{login}.png").write_bytes(data)


# ── Browse cache ──────────────────────────────────────────────


def load_browse_cache() -> dict[str, Any]:
    """Load browse cache from disk. Returns {} on cache miss or parse error."""
    try:
        path = CONFIG_DIR / "cache" / "browse_cache.json"
        return json.loads(path.read_text()) if path.exists() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_browse_cache(data: dict[str, Any]) -> None:
    """Persist browse cache to disk atomically, creating directories as needed."""
    path = CONFIG_DIR / "cache" / "browse_cache.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)


def is_browse_slot_fresh(
    cache: dict[str, Any], slot_key: str, ttl: int = BROWSE_CACHE_TTL_SECONDS
) -> bool:
    """Return True if the named cache slot exists and is within ttl seconds old."""
    return time.time() - cache.get(slot_key, {}).get("fetched_at", 0) < ttl
