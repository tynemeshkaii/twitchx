from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from . import TwitchXApi

logger = logging.getLogger(__name__)


class BaseApiComponent:
    """Shared infrastructure for all API sub-components.

    Provides:
        - _eval_js(code) — safe JS evaluation, guarded by _shutdown
        - _run_in_thread(fn) — dispatch to daemon thread
        - _async_run(coro) — run async coroutine in a new event loop
        - Access to shared state: _config, _live_streams, platform clients
    """

    def __init__(self, parent: TwitchXApi) -> None:
        self._api = parent

    @property
    def _shutdown(self) -> threading.Event:
        return self._api._shutdown

    @property
    def _config(self) -> dict[str, Any]:
        return self._api._config

    @_config.setter
    def _config(self, value: dict[str, Any]) -> None:
        self._api._config = value

    @property
    def _live_streams(self) -> list[dict[str, Any]]:
        return self._api._live_streams

    @_live_streams.setter
    def _live_streams(self, value: list[dict[str, Any]]) -> None:
        self._api._live_streams = value

    @property
    def _twitch(self) -> Any:
        return self._api._twitch

    @property
    def _kick(self) -> Any:
        return self._api._kick

    @property
    def _youtube(self) -> Any:
        return self._api._youtube

    @property
    def _platforms(self) -> dict[str, Any]:
        return self._api._platforms

    def _get_platform(self, platform_id: str) -> Any:
        return self._api._get_platform(platform_id)

    def _get_twitch_config(self) -> dict[str, Any]:
        return self._api._get_twitch_config()

    def _get_kick_config(self) -> dict[str, Any]:
        return self._api._get_kick_config()

    def _get_youtube_config(self) -> dict[str, Any]:
        return self._api._get_youtube_config()

    def _eval_js(self, code: str) -> None:
        self._api._eval_js(code)

    def _run_in_thread(self, fn: Callable[[], None]) -> None:
        self._api._run_in_thread(fn)

    def _async_run(self, coro: Any) -> None:
        """Run async coroutine in a new event loop, in a daemon thread."""

        def _runner() -> None:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(coro)
            except Exception as e:
                self._handle_async_error(e)
            finally:
                loop.close()

        self._run_in_thread(_runner)

    def _close_thread_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._api._close_thread_loop(loop)

    def _handle_async_error(self, error: Exception) -> None:
        """Override in subclass for domain-specific error handling."""
        pass
