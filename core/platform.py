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
    """Abstract interface for a streaming platform client."""

    platform_id: str
    platform_name: str

    @abstractmethod
    def get_auth_url(self) -> str: ...

    @abstractmethod
    async def exchange_code(self, code: str) -> dict[str, Any]: ...

    @abstractmethod
    async def refresh_user_token(self) -> str | None: ...

    @abstractmethod
    async def get_current_user(self) -> dict[str, Any]: ...

    @abstractmethod
    async def get_live_streams(
        self, identifiers: list[str]
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_top_streams(
        self, category: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def search_channels(self, query: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_channel_info(self, identifier: str) -> dict[str, Any]: ...

    @abstractmethod
    async def get_followed_channels(
        self, user_id: str
    ) -> list[str] | list[dict[str, str]]: ...

    @abstractmethod
    async def get_categories(
        self, query: str | None = None
    ) -> list[dict[str, Any]]: ...

    async def resolve_stream_url(self, channel_id: str, quality: str) -> dict[str, Any]:
        """Optional: return playback info for a live stream."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None: ...

    async def get_channel_vods(
        self, identifier: str, limit: int = 12
    ) -> list[dict[str, Any]]:
        """Optional: return recent VODs for a channel."""
        return []

    async def get_channel_clips(
        self, identifier: str, limit: int = 12
    ) -> list[dict[str, Any]]:
        """Optional: return recent clips for a channel."""
        return []

    # ── Polymorphic platform helpers ───────────────────────────

    @staticmethod
    @abstractmethod
    def build_stream_url(channel: str) -> str:
        """Build a platform-specific URL for streamlink."""
        ...

    @staticmethod
    @abstractmethod
    def sanitize_identifier(raw: str) -> str:
        """Extract platform-specific channel identifier from raw input
        (URL, handle, etc.) — e.g. 'https://twitch.tv/foo' → 'foo'."""
        ...

    @abstractmethod
    async def normalize_search_result(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Convert a platform-specific search result to unified format."""
        ...

    @abstractmethod
    async def normalize_stream_item(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Convert a platform-specific live stream dict to unified UI format."""
        ...
