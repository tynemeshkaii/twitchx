"""Tests for BaseChatClient reconnect loop and cancellation."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from core.chats.base import BaseChatClient, ReconnectNow, StopReconnect


class _Client(BaseChatClient):
    platform = "twitch"

    async def connect(self, channel_id: str, token: str | None = None) -> None:
        return None

    async def send_message(self, text: str, reply_to: str | None = None) -> Any:
        return None


def _make_client() -> tuple[_Client, list[Any]]:
    client = _Client()
    client._channel = "chan"
    client._running = True
    statuses: list[Any] = []
    client.on_status(statuses.append)
    return client, statuses


class TestReconnectCounter:
    async def test_counter_resets_after_each_successful_connection(self) -> None:
        client, statuses = _make_client()
        calls = 0

        async def connect_fn() -> None:
            nonlocal calls
            calls += 1
            if calls > 6:
                raise StopReconnect()
            client._mark_connected()
            raise OSError("network down")

        with patch("core.chats.base.asyncio.sleep", AsyncMock()):
            await client._reconnect_loop(connect_fn)

        assert calls == 7
        errors = [s.error or "" for s in statuses]
        assert not any("Max reconnect attempts" in e for e in errors)

    async def test_consecutive_failures_without_connection_stop_loop(self) -> None:
        client, statuses = _make_client()
        calls = 0

        async def connect_fn() -> None:
            nonlocal calls
            calls += 1
            raise OSError("refused")

        with patch("core.chats.base.asyncio.sleep", AsyncMock()):
            await client._reconnect_loop(connect_fn)

        assert calls == 5
        assert "Max reconnect attempts" in (statuses[-1].error or "")

    async def test_reconnect_now_skips_delay_and_counter(self) -> None:
        client, statuses = _make_client()
        calls = 0

        async def connect_fn() -> None:
            nonlocal calls
            calls += 1
            if calls > 10:
                raise StopReconnect()
            raise ReconnectNow()

        sleep = AsyncMock()
        with patch("core.chats.base.asyncio.sleep", sleep):
            await client._reconnect_loop(connect_fn)

        assert calls == 11
        sleep.assert_not_called()
        assert not any("Max reconnect" in (s.error or "") for s in statuses)


class TestCancel:
    def test_cancel_sets_flags(self) -> None:
        client, _ = _make_client()
        client.cancel()
        assert client._cancelled is True
        assert client._running is False

    async def test_disconnect_marks_cancelled(self) -> None:
        client, _ = _make_client()
        client._ws = AsyncMock()
        await client.disconnect()
        assert client._cancelled is True

    async def test_reconnect_loop_does_not_run_when_cancelled(self) -> None:
        client, _ = _make_client()
        client.cancel()
        client._running = True  # even if a stale connect() flips it back
        connect_fn = AsyncMock()
        await client._reconnect_loop(connect_fn)
        connect_fn.assert_not_called()
