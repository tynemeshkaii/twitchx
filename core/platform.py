"""Abstract base class for streaming platform clients and shared data models."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


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
    async def exchange_code(self, code: str) -> TokenData: ...

    @abstractmethod
    async def refresh_token(self) -> TokenData: ...

    @abstractmethod
    async def get_current_user(self) -> UserInfo: ...

    @abstractmethod
    async def get_live_streams(self, channel_ids: list[str]) -> list[StreamInfo]: ...

    @abstractmethod
    async def get_top_streams(self, category: str | None = None, limit: int = 20) -> list[StreamInfo]: ...

    @abstractmethod
    async def search_channels(self, query: str) -> list[ChannelInfo]: ...

    @abstractmethod
    async def get_channel_info(self, channel_id: str) -> ChannelInfo: ...

    @abstractmethod
    async def get_followed_channels(self, user_id: str) -> list[str]: ...

    @abstractmethod
    async def follow(self, channel_id: str) -> bool: ...

    @abstractmethod
    async def unfollow(self, channel_id: str) -> bool: ...

    @abstractmethod
    async def get_categories(self, query: str | None = None) -> list[CategoryInfo]: ...

    @abstractmethod
    async def resolve_stream_url(self, channel_id: str, quality: str) -> PlaybackInfo: ...

    @abstractmethod
    async def close(self) -> None: ...
