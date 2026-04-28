"""Shared infrastructure for platform chat clients."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import Any

from core.chat import ChatClient, ChatMessage, ChatStatus

logger = logging.getLogger(__name__)

RECONNECT_DELAYS = [3, 6, 12, 24, 48]


class StopReconnect(Exception):
    """Raised by a connect_fn to signal that the reconnection loop should stop."""


class BaseChatClient(ChatClient):
    """Shared infrastructure for chat clients.

    Subclasses must set:
        platform: str  — "twitch" or "kick"
    """

    platform: str = ""

    def __init__(self) -> None:
        self._ws: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._message_callback: Callable[[ChatMessage], None] | None = None
        self._status_callback: Callable[[ChatStatus], None] | None = None
        self._channel: str | None = None
        self._running = False
        self._authenticated = False

    def on_message(self, callback: Callable[[ChatMessage], None]) -> None:
        self._message_callback = callback

    def on_status(self, callback: Callable[[ChatStatus], None]) -> None:
        self._status_callback = callback

    def _emit_status(self, connected: bool, error: str | None = None) -> None:
        """Push status update to registered callback."""
        if self._status_callback and self._channel:
            self._status_callback(
                ChatStatus(
                    connected=connected,
                    platform=self.platform,
                    channel_id=self._channel,
                    error=error,
                    authenticated=self._authenticated,
                )
            )

    async def disconnect(self) -> None:
        """Disconnect WebSocket and emit offline status."""
        self._running = False
        if self._ws:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
        self._emit_status(connected=False)

    async def _reconnect_loop(self, connect_fn: Callable[[], Any]) -> None:
        """Outer reconnection loop with exponential backoff.

        Args:
            connect_fn: Async callable that establishes a new WebSocket connection
                        and sets self._ws. Should raise on failure.
                        Raise StopReconnect to exit the loop cleanly.
        """
        attempt = 0
        while self._running:
            try:
                await connect_fn()
                attempt = 0  # reset on successful connection
            except StopReconnect:
                break
            except Exception as e:
                if not self._running:
                    break
                attempt += 1
                if attempt >= len(RECONNECT_DELAYS):
                    self._emit_status(
                        connected=False, error=f"Max reconnect attempts: {e}"
                    )
                    return
                delay = RECONNECT_DELAYS[
                    min(attempt - 1, len(RECONNECT_DELAYS) - 1)
                ]
                self._emit_status(
                    connected=False, error=f"Reconnecting in {delay}s: {e}"
                )
                await asyncio.sleep(delay)
