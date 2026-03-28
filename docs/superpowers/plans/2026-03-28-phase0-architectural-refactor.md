# Phase 0: Architectural Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the codebase from a single-platform Twitch-only structure to a multi-platform architecture with abstract interfaces, without changing any user-visible behavior.

**Architecture:** Extract abstract `PlatformClient` and `ChatClient` ABCs with unified data models. Move `TwitchClient` into `core/platforms/twitch.py` as the first concrete implementation. Refactor `storage.py` to v2 multi-platform config format with automatic migration. Refactor `ui/api.py` to use a platform registry instead of direct `TwitchClient` calls.

**Tech Stack:** Python 3.11+, ABC, dataclasses, httpx, pywebview, pytest

**Spec:** `docs/superpowers/specs/2026-03-28-multiplatform-streaming-client-design.md`

---

## File Structure

**Create:**
- `core/platform.py` — ABC `PlatformClient` + all shared dataclasses (`StreamInfo`, `ChannelInfo`, `CategoryInfo`, `PlaybackInfo`, `TokenData`, `UserInfo`)
- `core/chat.py` — ABC `ChatClient` + dataclasses (`ChatMessage`, `ChatStatus`, `Badge`, `Emote`)
- `core/platforms/__init__.py` — empty init
- `core/platforms/twitch.py` — `TwitchClient(PlatformClient)` moved from `core/twitch.py`
- `core/chats/__init__.py` — empty init
- `tests/platforms/__init__.py` — empty init
- `tests/platforms/test_twitch.py` — moved from `tests/test_twitch.py`
- `tests/chats/__init__.py` — empty init

**Modify:**
- `core/storage.py` — v2 config format, migration, per-platform avatar dirs
- `ui/api.py` — platform registry, dispatch to platform clients
- `app.py` — update import path
- `pyproject.toml` — update pyright ignore path if needed

**Delete (after move):**
- `core/twitch.py` — replaced by `core/platforms/twitch.py`
- `tests/test_twitch.py` — replaced by `tests/platforms/test_twitch.py`

---

## Task 1: Create `core/platform.py` — Abstract Base Class + Data Models

**Files:**
- Create: `core/platform.py`
- Test: `tests/test_platform_models.py`

- [ ] **Step 1: Write tests for data models**

```python
# tests/test_platform_models.py
from __future__ import annotations

from core.platform import (
    CategoryInfo,
    ChannelInfo,
    PlaybackInfo,
    StreamInfo,
    TokenData,
    UserInfo,
)


class TestStreamInfo:
    def test_create(self):
        s = StreamInfo(
            platform="twitch",
            channel_id="123",
            channel_login="xqc",
            display_name="xQc",
            title="VARIETY",
            category="Just Chatting",
            viewers=15000,
            started_at="2026-03-28T16:00:00Z",
            thumbnail_url="https://example.com/thumb.jpg",
            avatar_url="https://example.com/avatar.png",
        )
        assert s.platform == "twitch"
        assert s.channel_login == "xqc"
        assert s.viewers == 15000


class TestPlaybackInfo:
    def test_hls_type(self):
        p = PlaybackInfo(url="https://example.com/stream.m3u8", playback_type="hls", quality="best")
        assert p.playback_type == "hls"

    def test_youtube_embed_type(self):
        p = PlaybackInfo(url="dQw4w9WgXcQ", playback_type="youtube_embed", quality="best")
        assert p.playback_type == "youtube_embed"


class TestChannelInfo:
    def test_can_follow_via_api(self):
        c = ChannelInfo(
            platform="kick",
            channel_id="456",
            login="ninja",
            display_name="Ninja",
            bio="Pro gamer",
            avatar_url="",
            followers=10000,
            is_live=True,
            can_follow_via_api=False,
        )
        assert c.can_follow_via_api is False


class TestTokenData:
    def test_create(self):
        t = TokenData(access_token="abc", refresh_token="def", expires_at=9999999999.0, token_type="user")
        assert t.token_type == "user"


class TestUserInfo:
    def test_create(self):
        u = UserInfo(platform="youtube", user_id="UC123", login="pewdiepie", display_name="PewDiePie", avatar_url="")
        assert u.platform == "youtube"


class TestCategoryInfo:
    def test_create(self):
        c = CategoryInfo(platform="twitch", category_id="509658", name="Just Chatting", box_art_url="", viewers=500000)
        assert c.name == "Just Chatting"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_platform_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.platform'`

- [ ] **Step 3: Create `core/platform.py`**

```python
# core/platform.py
"""Abstract base class for streaming platform clients and shared data models."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class StreamInfo:
    """Normalized live stream data from any platform."""

    platform: str
    channel_id: str
    channel_login: str
    display_name: str
    title: str
    category: str
    viewers: int
    started_at: str
    thumbnail_url: str
    avatar_url: str


@dataclass
class PlaybackInfo:
    """Stream playback URL and type."""

    url: str
    playback_type: str  # "hls" | "youtube_embed"
    quality: str


@dataclass
class ChannelInfo:
    """Normalized channel/streamer profile."""

    platform: str
    channel_id: str
    login: str
    display_name: str
    bio: str
    avatar_url: str
    followers: int
    is_live: bool
    can_follow_via_api: bool


@dataclass
class CategoryInfo:
    """Stream category / game."""

    platform: str
    category_id: str
    name: str
    box_art_url: str
    viewers: int


@dataclass
class TokenData:
    """OAuth token pair."""

    access_token: str
    refresh_token: str
    expires_at: float
    token_type: str


@dataclass
class UserInfo:
    """Authenticated user profile."""

    platform: str
    user_id: str
    login: str
    display_name: str
    avatar_url: str


class PlatformClient(ABC):
    """Abstract interface for a streaming platform client.

    Each platform (Twitch, Kick, YouTube) implements this interface.
    All methods that do I/O are async.
    """

    platform_id: str
    platform_name: str

    # --- Auth ---

    @abstractmethod
    def get_auth_url(self) -> str: ...

    @abstractmethod
    async def exchange_code(self, code: str) -> TokenData: ...

    @abstractmethod
    async def refresh_token(self) -> TokenData: ...

    @abstractmethod
    async def get_current_user(self) -> UserInfo: ...

    # --- Streams ---

    @abstractmethod
    async def get_live_streams(self, channel_ids: list[str]) -> list[StreamInfo]: ...

    @abstractmethod
    async def get_top_streams(self, category: str | None = None, limit: int = 20) -> list[StreamInfo]: ...

    @abstractmethod
    async def search_channels(self, query: str) -> list[ChannelInfo]: ...

    # --- Channel ---

    @abstractmethod
    async def get_channel_info(self, channel_id: str) -> ChannelInfo: ...

    @abstractmethod
    async def get_followed_channels(self, user_id: str) -> list[str]: ...

    # --- Social ---

    @abstractmethod
    async def follow(self, channel_id: str) -> bool: ...

    @abstractmethod
    async def unfollow(self, channel_id: str) -> bool: ...

    # --- Browse ---

    @abstractmethod
    async def get_categories(self, query: str | None = None) -> list[CategoryInfo]: ...

    # --- Playback ---

    @abstractmethod
    async def resolve_stream_url(self, channel_id: str, quality: str) -> PlaybackInfo: ...

    # --- Lifecycle ---

    @abstractmethod
    async def close(self) -> None: ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_platform_models.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/platform.py tests/test_platform_models.py
git commit -m "feat: add PlatformClient ABC and shared data models"
```

---

## Task 2: Create `core/chat.py` — Chat Abstract Base Class + Data Models

**Files:**
- Create: `core/chat.py`
- Test: `tests/test_chat_models.py`

- [ ] **Step 1: Write tests for chat data models**

```python
# tests/test_chat_models.py
from __future__ import annotations

from core.chat import Badge, ChatClient, ChatMessage, ChatStatus, Emote


class TestChatMessage:
    def test_create_text_message(self):
        msg = ChatMessage(
            platform="twitch",
            author="viewer123",
            author_display="Viewer123",
            author_color="#FF0000",
            avatar_url=None,
            text="Hello stream!",
            timestamp="2026-03-28T16:00:00Z",
            badges=[Badge(name="subscriber", icon_url="https://example.com/sub.png")],
            emotes=[Emote(code="Kappa", url="https://example.com/kappa.png", start=0, end=4)],
            is_system=False,
            message_type="text",
            raw={},
        )
        assert msg.platform == "twitch"
        assert msg.message_type == "text"
        assert len(msg.badges) == 1
        assert msg.badges[0].name == "subscriber"
        assert len(msg.emotes) == 1
        assert msg.emotes[0].code == "Kappa"


class TestChatStatus:
    def test_connected(self):
        s = ChatStatus(connected=True, platform="kick", channel_id="123", error=None)
        assert s.connected is True
        assert s.error is None

    def test_error(self):
        s = ChatStatus(connected=False, platform="youtube", channel_id="abc", error="Auth failed")
        assert s.connected is False
        assert s.error == "Auth failed"


class TestChatClientIsAbstract:
    def test_cannot_instantiate(self):
        import pytest

        with pytest.raises(TypeError):
            ChatClient()  # type: ignore[abstract]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_chat_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.chat'`

- [ ] **Step 3: Create `core/chat.py`**

```python
# core/chat.py
"""Abstract base class for platform chat clients and shared chat data models."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Badge:
    """Chat badge (moderator, subscriber, etc.)."""

    name: str
    icon_url: str


@dataclass
class Emote:
    """Chat emote with position in message text."""

    code: str
    url: str
    start: int
    end: int


@dataclass
class ChatMessage:
    """Normalized chat message from any platform."""

    platform: str
    author: str
    author_display: str
    author_color: str | None
    avatar_url: str | None
    text: str
    timestamp: str
    badges: list[Badge]
    emotes: list[Emote]
    is_system: bool
    message_type: str  # "text" | "super_chat" | "sub" | "raid" | "donation"
    raw: dict[str, Any]


@dataclass
class ChatStatus:
    """Chat connection status."""

    connected: bool
    platform: str
    channel_id: str
    error: str | None


class ChatClient(ABC):
    """Abstract interface for a platform chat client.

    Each platform (Twitch IRC, Kick Pusher, YouTube polling)
    implements this interface.
    """

    platform: str

    @abstractmethod
    async def connect(self, channel_id: str, token: str | None = None) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def send_message(self, text: str) -> bool: ...

    @abstractmethod
    def on_message(self, callback: Callable[[ChatMessage], None]) -> None: ...

    @abstractmethod
    def on_status(self, callback: Callable[[ChatStatus], None]) -> None: ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_chat_models.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/chat.py tests/test_chat_models.py
git commit -m "feat: add ChatClient ABC and shared chat data models"
```

---

## Task 3: Create directory structure for platforms and chats

**Files:**
- Create: `core/platforms/__init__.py`, `core/chats/__init__.py`, `tests/platforms/__init__.py`, `tests/chats/__init__.py`

- [ ] **Step 1: Create directories and empty init files**

```bash
mkdir -p core/platforms core/chats tests/platforms tests/chats
touch core/platforms/__init__.py core/chats/__init__.py tests/platforms/__init__.py tests/chats/__init__.py
```

- [ ] **Step 2: Commit**

```bash
git add core/platforms/__init__.py core/chats/__init__.py tests/platforms/__init__.py tests/chats/__init__.py
git commit -m "chore: create directory structure for platforms and chats"
```

---

## Task 4: Refactor `core/storage.py` — Multi-platform config v2

**Files:**
- Modify: `core/storage.py`
- Test: `tests/test_storage.py`

This is the trickiest part of Phase 0. The config format changes internally, but the app must still work identically. The migration runs automatically on load.

- [ ] **Step 1: Read current test file to understand existing test coverage**

Run: `cat tests/test_storage.py`

Understand what tests exist before modifying.

- [ ] **Step 2: Write migration tests**

Add these tests to `tests/test_storage.py`:

```python
class TestConfigMigrationV1ToV2:
    """Test automatic migration from flat Twitch-only config to multi-platform v2."""

    def test_migrates_twitch_credentials(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.storage.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("core.storage.CONFIG_FILE", tmp_path / "config.json")
        monkeypatch.setattr("core.storage.AVATAR_DIR", tmp_path / "avatars")
        monkeypatch.setattr("core.storage._OLD_CONFIG_DIR", tmp_path / "old_streamdeck")

        v1_config = {
            "client_id": "my_cid",
            "client_secret": "my_secret",
            "access_token": "my_token",
            "token_expires_at": 9999999999,
            "refresh_token": "my_refresh",
            "token_type": "user",
            "user_id": "12345",
            "user_login": "testuser",
            "user_display_name": "TestUser",
            "favorites": ["xqc", "shroud"],
            "quality": "720p60",
            "refresh_interval": 120,
        }
        tmp_path.mkdir(exist_ok=True)
        (tmp_path / "config.json").write_text(json.dumps(v1_config))

        config = load_config()

        # Credentials moved to platforms.twitch
        assert config["platforms"]["twitch"]["client_id"] == "my_cid"
        assert config["platforms"]["twitch"]["client_secret"] == "my_secret"
        assert config["platforms"]["twitch"]["access_token"] == "my_token"
        assert config["platforms"]["twitch"]["refresh_token"] == "my_refresh"
        assert config["platforms"]["twitch"]["token_type"] == "user"
        assert config["platforms"]["twitch"]["user_id"] == "12345"
        assert config["platforms"]["twitch"]["user_login"] == "testuser"

        # Favorites converted to objects
        assert config["favorites"] == [
            {"platform": "twitch", "login": "xqc", "display_name": "xqc"},
            {"platform": "twitch", "login": "shroud", "display_name": "shroud"},
        ]

        # Settings preserved
        assert config["settings"]["quality"] == "720p60"
        assert config["settings"]["refresh_interval"] == 120

        # Kick and YouTube defaults present
        assert "kick" in config["platforms"]
        assert "youtube" in config["platforms"]

    def test_v2_config_not_migrated(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.storage.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("core.storage.CONFIG_FILE", tmp_path / "config.json")
        monkeypatch.setattr("core.storage.AVATAR_DIR", tmp_path / "avatars")
        monkeypatch.setattr("core.storage._OLD_CONFIG_DIR", tmp_path / "old_streamdeck")

        v2_config = {
            "platforms": {
                "twitch": {"client_id": "already_v2", "enabled": True},
                "kick": {"enabled": False},
                "youtube": {"enabled": False},
            },
            "favorites": [{"platform": "twitch", "login": "xqc", "display_name": "xQc"}],
            "settings": {"quality": "best"},
        }
        tmp_path.mkdir(exist_ok=True)
        (tmp_path / "config.json").write_text(json.dumps(v2_config))

        config = load_config()
        assert config["platforms"]["twitch"]["client_id"] == "already_v2"

    def test_fresh_install_gets_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.storage.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("core.storage.CONFIG_FILE", tmp_path / "config.json")
        monkeypatch.setattr("core.storage.AVATAR_DIR", tmp_path / "avatars")
        monkeypatch.setattr("core.storage._OLD_CONFIG_DIR", tmp_path / "old_streamdeck")

        config = load_config()
        assert "platforms" in config
        assert config["platforms"]["twitch"]["client_id"] == ""
        assert config["favorites"] == []
        assert config["settings"]["quality"] == "best"


class TestAvatarPlatformDirs:
    """Avatar cache now uses per-platform subdirectories."""

    def test_get_cached_avatar_with_platform(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.storage.AVATAR_DIR", tmp_path / "avatars")
        avatar_dir = tmp_path / "avatars" / "twitch"
        avatar_dir.mkdir(parents=True)
        (avatar_dir / "xqc.png").write_bytes(b"fake_png_data")

        result = get_cached_avatar("xqc", platform="twitch")
        assert result == b"fake_png_data"

    def test_save_avatar_with_platform(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.storage.AVATAR_DIR", tmp_path / "avatars")

        save_avatar("ninja", b"kick_avatar_data", platform="kick")

        saved = tmp_path / "avatars" / "kick" / "ninja.png"
        assert saved.exists()
        assert saved.read_bytes() == b"kick_avatar_data"

    def test_backwards_compat_default_twitch(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.storage.AVATAR_DIR", tmp_path / "avatars")
        avatar_dir = tmp_path / "avatars" / "twitch"
        avatar_dir.mkdir(parents=True)
        (avatar_dir / "test.png").write_bytes(b"data")

        result = get_cached_avatar("test")
        assert result == b"data"
```

- [ ] **Step 3: Run new tests to verify they fail**

Run: `uv run pytest tests/test_storage.py::TestConfigMigrationV1ToV2 -v`
Expected: FAIL

- [ ] **Step 4: Rewrite `core/storage.py` with v2 config format**

Replace the entire `core/storage.py` with:

```python
# core/storage.py
"""Multi-platform config storage with automatic v1→v2 migration.

Config lives at ~/.config/twitchx/config.json.
v1 format: flat Twitch-only keys at root level.
v2 format: platforms.<id>.*, favorites as objects, settings section.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "twitchx"
CONFIG_FILE = CONFIG_DIR / "config.json"
_OLD_CONFIG_DIR = Path.home() / ".config" / "streamdeck"
AVATAR_DIR = CONFIG_DIR / "avatars"
_AVATAR_MAX_AGE = 7 * 24 * 3600  # 7 days

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

# Legacy v1 keys that indicate a v1 config (flat Twitch fields at root)
_V1_KEYS = {"client_id", "client_secret", "access_token", "token_expires_at"}


def _migrate_old_config() -> None:
    """One-time migration from ~/.config/streamdeck/ to ~/.config/twitchx/."""
    if CONFIG_DIR.exists() or not _OLD_CONFIG_DIR.exists():
        return
    shutil.copytree(_OLD_CONFIG_DIR, CONFIG_DIR)


def _migrate_v1_to_v2(config: dict[str, Any]) -> dict[str, Any]:
    """Migrate flat Twitch-only config (v1) to multi-platform format (v2)."""
    if "platforms" in config:
        return config  # Already v2

    if not _V1_KEYS.intersection(config.keys()):
        return config  # Empty or unknown format, will get defaults

    # Extract Twitch credentials
    twitch = {**DEFAULT_PLATFORM_TWITCH}
    for key in DEFAULT_PLATFORM_TWITCH:
        if key in config:
            twitch[key] = config[key]

    # Convert favorites from strings to objects
    old_favs = config.get("favorites", [])
    new_favs = []
    for f in old_favs:
        if isinstance(f, str):
            new_favs.append({"platform": "twitch", "login": f, "display_name": f})
        elif isinstance(f, dict):
            new_favs.append(f)  # Already an object

    # Extract settings
    settings = {**DEFAULT_SETTINGS}
    for key in DEFAULT_SETTINGS:
        if key in config:
            settings[key] = config[key]

    return {
        "platforms": {
            "twitch": twitch,
            "kick": {**DEFAULT_PLATFORM_KICK},
            "youtube": {**DEFAULT_PLATFORM_YOUTUBE},
        },
        "favorites": new_favs,
        "settings": settings,
    }


def _deep_merge(defaults: dict[str, Any], stored: dict[str, Any]) -> dict[str, Any]:
    """Merge stored config with defaults so missing keys get default values."""
    result = {**defaults}
    for key, value in stored.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict[str, Any]:
    """Load config from disk, migrating and merging with defaults."""
    _migrate_old_config()
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            stored = json.load(f)
        stored = _migrate_v1_to_v2(stored)
        return _deep_merge(DEFAULT_CONFIG, stored)
    return {**DEFAULT_CONFIG, "platforms": {k: {**v} for k, v in DEFAULT_CONFIG["platforms"].items()}, "settings": {**DEFAULT_CONFIG["settings"]}, "favorites": []}


def save_config(config: dict[str, Any]) -> None:
    """Write config to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def token_is_valid(config: dict[str, Any]) -> bool:
    """Check if a platform config section has a valid (non-expired) token.

    Works with both v2 platform sections and legacy flat configs.
    """
    token = config.get("access_token", "")
    expires = config.get("token_expires_at", 0)
    return bool(token) and expires > time.time() + 60


# --- Convenience accessors for v2 config ---


def get_platform_config(config: dict[str, Any], platform: str) -> dict[str, Any]:
    """Get the config section for a specific platform."""
    return config.get("platforms", {}).get(platform, {})


def get_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Get the settings section."""
    return config.get("settings", {**DEFAULT_SETTINGS})


def get_favorites(config: dict[str, Any], platform: str | None = None) -> list[dict[str, Any]]:
    """Get favorites, optionally filtered by platform."""
    favs = config.get("favorites", [])
    if platform:
        return [f for f in favs if f.get("platform") == platform]
    return favs


def get_favorite_logins(config: dict[str, Any], platform: str) -> list[str]:
    """Get just the login names for a specific platform's favorites."""
    return [f["login"] for f in get_favorites(config, platform)]


# --- Avatar disk cache ---


def get_cached_avatar(login: str, platform: str = "twitch") -> bytes | None:
    """Return cached avatar bytes if fresh, else None."""
    path = AVATAR_DIR / platform / f"{login}.png"
    if not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    if age > _AVATAR_MAX_AGE:
        return None
    return path.read_bytes()


def save_avatar(login: str, data: bytes, platform: str = "twitch") -> None:
    """Save avatar image to disk cache under platform subdirectory."""
    platform_dir = AVATAR_DIR / platform
    platform_dir.mkdir(parents=True, exist_ok=True)
    (platform_dir / f"{login}.png").write_bytes(data)
```

- [ ] **Step 5: Run all storage tests**

Run: `uv run pytest tests/test_storage.py -v`
Expected: All tests PASS (both old and new). If any old tests use the previous function signatures (e.g., `get_cached_avatar` without `platform` param), they should still work due to the `platform="twitch"` default.

- [ ] **Step 6: Commit**

```bash
git add core/storage.py tests/test_storage.py
git commit -m "refactor: storage v2 format with multi-platform config and migration"
```

---

## Task 5: Move `core/twitch.py` → `core/platforms/twitch.py`

**Files:**
- Create: `core/platforms/twitch.py` (moved and adapted)
- Modify: `core/twitch.py` → re-export shim for backwards compat during transition

The strategy: copy twitch.py to its new location, update imports to use new storage helpers, and leave a thin re-export shim at the old location so nothing breaks during the transition.

- [ ] **Step 1: Copy twitch.py to new location**

```bash
cp core/twitch.py core/platforms/twitch.py
```

- [ ] **Step 2: Update imports in `core/platforms/twitch.py`**

In `core/platforms/twitch.py`, change the import line:

Old:
```python
from core.storage import load_config, save_config, token_is_valid
```

New:
```python
from core.storage import get_platform_config, load_config, save_config, token_is_valid
```

No other changes needed yet — the TwitchClient class stays exactly as-is internally. It will be adapted to implement PlatformClient ABC in a later phase when we actually need the abstract interface. For Phase 0, we just move the file.

- [ ] **Step 3: Replace `core/twitch.py` with a re-export shim**

```python
# core/twitch.py
"""Backwards-compatibility shim. Import from core.platforms.twitch instead."""
from core.platforms.twitch import VALID_USERNAME, TwitchClient

__all__ = ["VALID_USERNAME", "TwitchClient"]
```

This ensures all existing imports (`from core.twitch import TwitchClient`) continue to work.

- [ ] **Step 4: Run all tests to verify nothing broke**

Run: `uv run pytest tests/ -v`
Expected: All existing tests PASS. The shim makes the move transparent.

- [ ] **Step 5: Commit**

```bash
git add core/platforms/twitch.py core/twitch.py
git commit -m "refactor: move TwitchClient to core/platforms/twitch.py with backwards-compat shim"
```

---

## Task 6: Move `tests/test_twitch.py` → `tests/platforms/test_twitch.py`

**Files:**
- Create: `tests/platforms/test_twitch.py` (moved)
- Delete: `tests/test_twitch.py`

- [ ] **Step 1: Copy test file to new location**

```bash
cp tests/test_twitch.py tests/platforms/test_twitch.py
```

- [ ] **Step 2: Update import in `tests/platforms/test_twitch.py`**

Change line 9:

Old:
```python
from core.twitch import VALID_USERNAME, TwitchClient
```

New:
```python
from core.platforms.twitch import VALID_USERNAME, TwitchClient
```

- [ ] **Step 3: Remove old test file**

```bash
rm tests/test_twitch.py
```

- [ ] **Step 4: Run tests from new location**

Run: `uv run pytest tests/platforms/test_twitch.py -v`
Expected: All tests PASS

Run: `uv run pytest tests/ -v`
Expected: All tests PASS (old file gone, new file found)

- [ ] **Step 5: Commit**

```bash
git add tests/platforms/test_twitch.py
git rm tests/test_twitch.py
git commit -m "refactor: move twitch tests to tests/platforms/test_twitch.py"
```

---

## Task 7: Refactor `ui/api.py` — Platform registry

**Files:**
- Modify: `ui/api.py`

This is the largest change. The goal: replace the hardcoded `self._twitch` with a platform registry `self._platforms`, while keeping all behavior identical. The only platform in the registry for now is Twitch.

- [ ] **Step 1: Update imports in `ui/api.py`**

Change:
```python
from core.twitch import TwitchClient
```
To:
```python
from core.platforms.twitch import TwitchClient
from core.storage import get_favorite_logins, get_platform_config, get_settings
```

- [ ] **Step 2: Add platform registry to `__init__`**

In `TwitchXApi.__init__`, after `self._twitch = TwitchClient()`, add:

```python
        self._platforms: dict[str, Any] = {"twitch": self._twitch}
        self._active_platform: str = "twitch"
```

This is additive — `self._twitch` stays for now, the registry is a parallel structure. No existing code breaks.

- [ ] **Step 3: Add helper methods for platform access**

Add these methods to `TwitchXApi` class (after `_run_in_thread`):

```python
    def _get_platform(self, platform_id: str) -> Any:
        """Get a platform client by ID."""
        return self._platforms.get(platform_id)

    def _get_twitch_config(self) -> dict[str, Any]:
        """Get Twitch platform config section. Convenience for transition period."""
        return get_platform_config(self._config, "twitch")
```

- [ ] **Step 4: Update `_on_data_fetched` to include platform field**

In `_on_data_fetched`, where stream items are built (the list comprehension that creates dicts), add `"platform": "twitch"` to each stream dict. This is additive — JS ignores unknown fields.

Find the stream item dict construction (around line 500-520) and add the field:

```python
            item = {
                "platform": "twitch",  # NEW: platform identifier
                "login": login,
                # ... rest stays the same
            }
```

- [ ] **Step 5: Update `close()` to iterate platforms**

In the `close()` method, after the existing `self._twitch.close()` call pattern, this already works because `self._twitch` is the same object as `self._platforms["twitch"]`. No change needed yet.

- [ ] **Step 6: Update `get_config` to use v2 structure**

The `get_config()` method currently reads `self._config["client_id"]` etc. directly. Update it to read from the Twitch platform section while still returning the same shape to JS:

```python
    def get_config(self) -> dict[str, Any]:
        twitch_conf = get_platform_config(self._config, "twitch")
        settings = get_settings(self._config)
        masked = {
            "client_id": twitch_conf.get("client_id", "")[:8] + "..." if twitch_conf.get("client_id") else "",
            "has_credentials": bool(twitch_conf.get("client_id") and twitch_conf.get("client_secret")),
            "quality": settings.get("quality", "best"),
            "refresh_interval": settings.get("refresh_interval", 60),
            "favorites": get_favorite_logins(self._config, "twitch"),
        }
        if self._current_user:
            masked["current_user"] = self._current_user
        return masked
```

- [ ] **Step 7: Update `get_full_config_for_settings`**

Update to read from v2 structure but return the same flat shape JS expects:

```python
    def get_full_config_for_settings(self) -> dict[str, Any]:
        twitch_conf = get_platform_config(self._config, "twitch")
        settings = get_settings(self._config)
        return {
            "client_id": twitch_conf.get("client_id", ""),
            "client_secret": twitch_conf.get("client_secret", ""),
            "quality": settings.get("quality", "best"),
            "refresh_interval": settings.get("refresh_interval", 60),
            "streamlink_path": settings.get("streamlink_path", "streamlink"),
            "iina_path": settings.get("iina_path", ""),
        }
```

- [ ] **Step 8: Update `save_settings` to write to v2 structure**

In `save_settings`, instead of writing flat keys to `self._config`, write to the appropriate sections:

```python
    def save_settings(self, data: str) -> None:
        parsed = json.loads(data)
        twitch_conf = get_platform_config(self._config, "twitch")
        settings = get_settings(self._config)

        if "client_id" in parsed:
            twitch_conf["client_id"] = parsed["client_id"].strip()
        if "client_secret" in parsed:
            twitch_conf["client_secret"] = parsed["client_secret"].strip()
        if "quality" in parsed:
            settings["quality"] = parsed["quality"]
        if "refresh_interval" in parsed:
            settings["refresh_interval"] = int(parsed["refresh_interval"])
        if "streamlink_path" in parsed:
            settings["streamlink_path"] = parsed["streamlink_path"].strip()
        if "iina_path" in parsed:
            settings["iina_path"] = parsed["iina_path"].strip()

        self._config["platforms"]["twitch"] = twitch_conf
        self._config["settings"] = settings
        save_config(self._config)
        self._twitch._reload_config()

        interval = settings.get("refresh_interval", 60)
        self.start_polling(interval)
        self._eval_js("window.onSettingsSaved()")
```

- [ ] **Step 9: Update `login` method to read/write v2 config**

In the `login()` method, everywhere it reads/writes `self._config["access_token"]`, `self._config["user_id"]`, etc., change to read/write through `self._config["platforms"]["twitch"]`. The key changes:

After `exchange_code` succeeds (around line 210-225):
```python
            twitch_conf = self._config["platforms"]["twitch"]
            twitch_conf["access_token"] = tokens["access_token"]
            twitch_conf["refresh_token"] = tokens.get("refresh_token", "")
            twitch_conf["token_expires_at"] = time.time() + tokens.get("expires_in", 3600)
            twitch_conf["token_type"] = "user"
```

After `get_current_user` succeeds (around line 230-240):
```python
            twitch_conf["user_id"] = user_data["id"]
            twitch_conf["user_login"] = user_data["login"]
            twitch_conf["user_display_name"] = user_data["display_name"]
            save_config(self._config)
```

- [ ] **Step 10: Update `logout` method to clear v2 config**

```python
    def logout(self) -> None:
        twitch_conf = self._config["platforms"]["twitch"]
        twitch_conf["access_token"] = ""
        twitch_conf["refresh_token"] = ""
        twitch_conf["token_expires_at"] = 0
        twitch_conf["token_type"] = "app"
        twitch_conf["user_id"] = ""
        twitch_conf["user_login"] = ""
        twitch_conf["user_display_name"] = ""
        save_config(self._config)
        self._current_user = None
        self._eval_js("window.onLogout()")
```

- [ ] **Step 11: Update `add_channel` and `remove_channel` for v2 favorites**

```python
    def add_channel(self, username: str) -> None:
        clean = self._sanitize_username(username)
        if not clean:
            return
        favorites = self._config.get("favorites", [])
        # Check if already exists for twitch
        if any(f.get("login") == clean and f.get("platform") == "twitch" for f in favorites):
            return
        favorites.append({"platform": "twitch", "login": clean, "display_name": clean})
        self._config["favorites"] = favorites
        save_config(self._config)
        self.refresh()

    def remove_channel(self, channel: str) -> None:
        favorites = self._config.get("favorites", [])
        self._config["favorites"] = [
            f for f in favorites
            if not (f.get("login") == channel and f.get("platform") == "twitch")
        ]
        save_config(self._config)
        self.refresh()
```

- [ ] **Step 12: Update `reorder_channels` for v2 favorites**

```python
    def reorder_channels(self, new_order_json: str) -> None:
        new_order = json.loads(new_order_json)
        # Rebuild favorites preserving platform info
        old_favs = {f["login"]: f for f in self._config.get("favorites", []) if f.get("platform") == "twitch"}
        reordered = []
        for login in new_order:
            if login in old_favs:
                reordered.append(old_favs[login])
            else:
                reordered.append({"platform": "twitch", "login": login, "display_name": login})
        # Keep non-twitch favorites at the end (for future platforms)
        non_twitch = [f for f in self._config.get("favorites", []) if f.get("platform") != "twitch"]
        self._config["favorites"] = reordered + non_twitch
        save_config(self._config)
```

- [ ] **Step 13: Update `refresh` and `_fetch_data` to use v2 favorites**

In `refresh()`, change the line that reads favorites:

Old:
```python
        favorites = list(self._config.get("favorites", []))
```

New:
```python
        favorites = get_favorite_logins(self._config, "twitch")
```

The rest of `_fetch_data` and `_async_fetch` receive `favorites` as `list[str]` (just logins), so they work unchanged.

- [ ] **Step 14: Update `import_follows` for v2 favorites**

In `import_follows`, where new channels are added to favorites:

Old:
```python
            existing = set(self._config.get("favorites", []))
            ...
            self._config["favorites"] = list(existing | new_follows)
```

New:
```python
            existing_logins = {f["login"] for f in self._config.get("favorites", []) if f.get("platform") == "twitch"}
            new_logins = set(followed) - existing_logins
            for login in new_logins:
                self._config["favorites"].append({"platform": "twitch", "login": login, "display_name": login})
```

- [ ] **Step 15: Update `test_connection` to read from v2 config**

The `test_connection` method receives `client_id` and `client_secret` directly from JS — no config reading needed. No change required.

- [ ] **Step 16: Update `__init__` to restore user profile from v2 config**

In `__init__`, where it restores `self._current_user` from config (around lines 55-65):

Old:
```python
        if self._config.get("user_id"):
            self._current_user = {
                "id": self._config["user_id"],
                "login": self._config["user_login"],
                "display_name": self._config["user_display_name"],
            }
```

New:
```python
        twitch_conf = get_platform_config(self._config, "twitch")
        if twitch_conf.get("user_id"):
            self._current_user = {
                "id": twitch_conf["user_id"],
                "login": twitch_conf["user_login"],
                "display_name": twitch_conf["user_display_name"],
            }
```

- [ ] **Step 17: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 18: Commit**

```bash
git add ui/api.py
git commit -m "refactor: api.py uses platform registry and v2 config structure"
```

---

## Task 8: Update `app.py` import and verify

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Check if app.py imports from core.twitch**

Read `app.py` and check imports. If it imports `TwitchClient` or anything from `core.twitch`, update to use `core.platforms.twitch`. The shim handles this, but updating the import is cleaner.

- [ ] **Step 2: Update import if needed**

If `app.py` has:
```python
from core.twitch import ...
```
Change to:
```python
from core.platforms.twitch import ...
```

If `app.py` only imports from `ui/api.py` (which is likely), no change needed.

- [ ] **Step 3: Update `pyproject.toml` if needed**

Check if `pyproject.toml` has any paths referencing `core/twitch.py` (e.g., in pyright config). Update to `core/platforms/twitch.py`.

- [ ] **Step 4: Commit if changes were made**

```bash
git add app.py pyproject.toml
git commit -m "chore: update import paths in app.py and pyproject.toml"
```

---

## Task 9: Lint, test, and verify full app

**Files:** All modified files

- [ ] **Step 1: Run linter**

Run: `make lint`
Expected: No errors. Fix any import or type issues.

- [ ] **Step 2: Run formatter**

Run: `make fmt`

- [ ] **Step 3: Run full test suite**

Run: `make test`
Expected: All 57+ tests PASS (original tests + new migration/model tests)

- [ ] **Step 4: Run the app manually**

Run: `make run`
Expected: App launches, loads config (migrating if needed), shows streams if credentials exist, sidebar works, watching works. No visible changes.

- [ ] **Step 5: Verify config migration**

Check `~/.config/twitchx/config.json` — it should now have the v2 structure with `platforms`, `favorites` as objects, and `settings`. All credentials and favorites should be preserved.

- [ ] **Step 6: Commit any lint/format fixes**

```bash
git add -A
git commit -m "chore: lint and format fixes after Phase 0 refactor"
```

---

## Task 10: Remove backwards-compat shim (cleanup)

**Files:**
- Modify: `core/twitch.py` → delete or keep as shim

- [ ] **Step 1: Search for remaining imports of `core.twitch`**

```bash
grep -r "from core.twitch" --include="*.py" .
grep -r "import core.twitch" --include="*.py" .
```

- [ ] **Step 2: Update any remaining imports**

Change all `from core.twitch import ...` to `from core.platforms.twitch import ...`.

- [ ] **Step 3: Decide on shim**

If all imports are updated, delete `core/twitch.py`. If external tools or scripts might reference it, keep the shim.

- [ ] **Step 4: Run tests one final time**

Run: `make check`
Expected: All lint checks pass, all tests pass.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "refactor: Phase 0 complete — multi-platform architecture foundation"
```
