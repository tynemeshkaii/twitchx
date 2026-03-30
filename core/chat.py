"""Abstract base class for platform chat clients and shared chat data models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


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
    msg_id: str | None = None
    reply_to_id: str | None = None
    reply_to_display: str | None = None
    reply_to_body: str | None = None


@dataclass
class ChatStatus:
    """Chat connection status."""

    connected: bool
    platform: str
    channel_id: str
    error: str | None
    authenticated: bool = False


class ChatClient(ABC):
    """Abstract interface for a platform chat client."""

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
