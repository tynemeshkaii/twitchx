from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "twitchx"
CONFIG_FILE = CONFIG_DIR / "config.json"

_OLD_CONFIG_DIR = Path.home() / ".config" / "streamdeck"

DEFAULT_CONFIG: dict[str, Any] = {
    "client_id": "",
    "client_secret": "",
    "kick_client_id": "",
    "kick_client_secret": "",
    "access_token": "",
    "token_expires_at": 0,
    "kick_access_token": "",
    "kick_token_expires_at": 0,
    "favorites": [],
    "quality": "best",
    "refresh_interval": 60,
    "streamlink_path": "streamlink",
    "iina_path": "/Applications/IINA.app/Contents/MacOS/iina-cli",
    "user_id": "",
    "user_login": "",
    "user_display_name": "",
    "refresh_token": "",
    "token_type": "app",
    "oauth_state": "",
}


def _migrate_old_config() -> None:
    """One-time migration from ~/.config/streamdeck/ to ~/.config/twitchx/."""
    old_config = _OLD_CONFIG_DIR / "config.json"
    if old_config.exists() and not CONFIG_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_config, CONFIG_FILE)
        CONFIG_FILE.chmod(0o600)
        old_avatars = _OLD_CONFIG_DIR / "avatars"
        new_avatars = CONFIG_DIR / "avatars"
        if old_avatars.is_dir() and not new_avatars.exists():
            shutil.copytree(old_avatars, new_avatars)


def load_config() -> dict[str, Any]:
    _migrate_old_config()
    if not CONFIG_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE) as f:
            stored = json.load(f)
        if not isinstance(stored, dict):
            raise TypeError("Config root must be a JSON object")
    except (json.JSONDecodeError, OSError, TypeError):
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    merged = {**DEFAULT_CONFIG, **stored}
    return merged


def save_config(config: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        dir=CONFIG_DIR,
        prefix="config.",
        suffix=".tmp",
    )
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(config, f, indent=2)
        os.replace(temp_path, CONFIG_FILE)
        CONFIG_FILE.chmod(0o600)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def token_is_valid(config: dict[str, Any]) -> bool:
    return (
        bool(config.get("access_token"))
        and config.get("token_expires_at", 0) > time.time() + 60
    )


# ── Avatar disk cache ────────────────────────────────────────

AVATAR_DIR = CONFIG_DIR / "avatars"  # ~/.config/twitchx/avatars/
_AVATAR_MAX_AGE = 7 * 24 * 3600  # 7 days


def get_cached_avatar(login: str) -> bytes | None:
    """Return raw PNG bytes if a fresh disk-cached avatar exists."""
    path = AVATAR_DIR / f"{login}.png"
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > _AVATAR_MAX_AGE:
        return None
    return path.read_bytes()


def save_avatar(login: str, data: bytes) -> None:
    """Persist raw image bytes to disk cache."""
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    (AVATAR_DIR / f"{login}.png").write_bytes(data)
