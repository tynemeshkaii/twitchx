"""Backwards-compatibility shim. Import from core.platforms.twitch instead."""

from core.platforms.twitch import VALID_USERNAME, TwitchClient

__all__ = ["VALID_USERNAME", "TwitchClient"]
