"""Shared infrastructure for platform chat clients."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import Any

from core.chat import ChatClient, ChatMessage, ChatStatus
from core.constants import CHAT_RECONNECT_DELAYS

logger = logging.getLogger(__name__)

RECONNECT_DELAYS = CHAT_RECONNECT_DELAYS


class StopReconnect(Exception):
    """Raised by a connect_fn to signal that the reconnection loop should stop."""


class ReconnectNow(Exception):
    """Raised by a connect_fn to reconnect immediately (no backoff, no attempt count).

    Used for server-initiated reconnects (Twitch ``RECONNECT``, Pusher 4200-4299).
    """


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
        # Set once by cancel()/disconnect(); a cancelled client never (re)connects.
        self._cancelled = False
        self._reconnect_attempt = 0

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

    def cancel(self) -> None:
        """Synchronously mark the client as stopped (safe from any thread).

        Unlike disconnect() it needs no event loop, so it also covers the window
        before connect() started: a cancelled client returns from connect() at once.
        """
        self._cancelled = True
        self._running = False

    def _mark_connected(self) -> None:
        """Called by connect_fn once the server accepted the connection."""
        self._reconnect_attempt = 0

    def _should_run(self) -> bool:
        return self._running and not self._cancelled

    async def disconnect(self) -> None:
        """Disconnect WebSocket and emit offline status."""
        self._cancelled = True
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
                        and sets self._ws. Should raise on failure and call
                        self._mark_connected() once the server accepted it — that
                        resets the backoff counter, so only consecutive failed
                        attempts count towards the limit.
                        Raise StopReconnect to exit the loop cleanly, ReconnectNow
                        to reconnect without delay.
        """
        self._reconnect_attempt = 0
        while self._should_run():
            try:
                await connect_fn()
            except StopReconnect:
                break
            except ReconnectNow:
                logger.info("Chat server requested reconnect")
                continue
            except Exception as e:
                attempt = self._reconnect_attempt + 1
                logger.warning("Chat reconnect error (attempt %d): %s", attempt, e)
                if not self._should_run():
                    break
                self._reconnect_attempt = attempt
                if attempt >= len(RECONNECT_DELAYS):
                    self._emit_status(
                        connected=False, error=f"Max reconnect attempts: {e}"
                    )
                    return
                delay = RECONNECT_DELAYS[min(attempt - 1, len(RECONNECT_DELAYS) - 1)]
                self._emit_status(
                    connected=False, error=f"Reconnecting in {delay}s: {e}"
                )
                await asyncio.sleep(delay)
