# Phase 3: Kick Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Kick chat support via Pusher WebSocket protocol for reading and REST API for sending, reusing the existing chat panel UI.

**Architecture:** `KickChatClient` in `core/chats/kick_chat.py` connects to Pusher WebSocket (protocol 7) for reading chat messages and uses HTTP POST for sending. Pure parsing functions extract emotes (`[emote:id:name]` format), badges, and message types from double-encoded Pusher JSON. Integration in `ui/api.py` adds a `platform == "kick"` branch in `start_chat()` that fetches `chatroom_id` via `KickClient.get_channel_info()` before connecting.

**Tech Stack:** Python 3.12, websockets, httpx, pytest

---

### Task 1: Pure parsing functions — emotes

**Files:**
- Create: `core/chats/kick_chat.py`
- Test: `tests/chats/test_kick_chat.py`

- [ ] **Step 1: Write failing tests for Kick emote parsing**

Create the test file with emote parser tests:

```python
"""Tests for Kick Pusher chat client."""

from __future__ import annotations

from core.chat import Emote
from core.chats.kick_chat import parse_kick_emotes


class TestParseKickEmotes:
    def test_single_emote(self) -> None:
        text = "hello [emote:12345:KickHype] world"
        clean, emotes = parse_kick_emotes(text)
        assert clean == "hello KickHype world"
        assert emotes == [
            Emote(
                code="KickHype",
                url="https://files.kick.com/emotes/12345/fullsize",
                start=6,
                end=13,
            )
        ]

    def test_multiple_emotes(self) -> None:
        text = "[emote:111:A] and [emote:222:B]"
        clean, emotes = parse_kick_emotes(text)
        assert clean == "A and B"
        assert len(emotes) == 2
        assert emotes[0] == Emote(code="A", url="https://files.kick.com/emotes/111/fullsize", start=0, end=0)
        assert emotes[1] == Emote(code="B", url="https://files.kick.com/emotes/222/fullsize", start=6, end=6)

    def test_no_emotes(self) -> None:
        text = "hello world"
        clean, emotes = parse_kick_emotes(text)
        assert clean == "hello world"
        assert emotes == []

    def test_empty_text(self) -> None:
        clean, emotes = parse_kick_emotes("")
        assert clean == ""
        assert emotes == []

    def test_adjacent_emotes(self) -> None:
        text = "[emote:1:A][emote:2:B]"
        clean, emotes = parse_kick_emotes(text)
        assert clean == "AB"
        assert emotes[0].start == 0
        assert emotes[0].end == 0
        assert emotes[1].start == 1
        assert emotes[1].end == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/chats/test_kick_chat.py::TestParseKickEmotes -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.chats.kick_chat'`

- [ ] **Step 3: Implement parse_kick_emotes**

Create `core/chats/kick_chat.py` with the emote parser:

```python
"""Kick Pusher WebSocket chat client and message parser."""

from __future__ import annotations

import re

from core.chat import Emote

KICK_EMOTE_URL = "https://files.kick.com/emotes/{id}/fullsize"
_EMOTE_RE = re.compile(r"\[emote:(\d+):(\w+)\]")


def parse_kick_emotes(text: str) -> tuple[str, list[Emote]]:
    """Parse [emote:id:name] markers from Kick chat text.

    Returns (cleaned_text, emotes) where cleaned_text has markers replaced
    with the emote code, and emotes have start/end positions in the cleaned text.
    """
    if not text:
        return "", []

    emotes: list[Emote] = []
    clean_parts: list[str] = []
    last_end = 0
    offset = 0

    for m in _EMOTE_RE.finditer(text):
        emote_id, code = m.group(1), m.group(2)
        # Append text before this emote
        before = text[last_end : m.start()]
        clean_parts.append(before)
        offset += len(before)

        start = offset
        end = offset + len(code) - 1
        emotes.append(
            Emote(
                code=code,
                url=KICK_EMOTE_URL.replace("{id}", emote_id),
                start=start,
                end=end,
            )
        )
        clean_parts.append(code)
        offset += len(code)
        last_end = m.end()

    clean_parts.append(text[last_end:])
    return "".join(clean_parts), emotes
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/chats/test_kick_chat.py::TestParseKickEmotes -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add core/chats/kick_chat.py tests/chats/test_kick_chat.py
git commit -m "feat(kick-chat): add emote parser for [emote:id:name] format"
```

---

### Task 2: Pure parsing functions — message parsing

**Files:**
- Modify: `core/chats/kick_chat.py`
- Test: `tests/chats/test_kick_chat.py`

- [ ] **Step 1: Write failing tests for Kick message parsing**

Append to `tests/chats/test_kick_chat.py`:

```python
import json

from core.chat import Badge, ChatMessage
from core.chats.kick_chat import parse_kick_event


class TestParseKickEvent:
    def _make_event(self, msg_data: dict) -> dict:
        """Create a Pusher event with double-encoded data."""
        return {
            "event": "App\\Events\\ChatMessageSentEvent",
            "data": json.dumps(msg_data),
            "channel": "chatrooms.123.v2",
        }

    def test_basic_message(self) -> None:
        data = {
            "id": "uuid-1",
            "chatroom_id": 123,
            "content": "hello world",
            "type": "message",
            "created_at": "2024-01-01T00:00:00.000000Z",
            "sender": {
                "id": 67890,
                "username": "TestUser",
                "slug": "testuser",
                "identity": {"color": "#FF4500", "badges": []},
            },
        }
        msg = parse_kick_event(self._make_event(data))
        assert msg is not None
        assert msg.platform == "kick"
        assert msg.author == "testuser"
        assert msg.author_display == "TestUser"
        assert msg.author_color == "#FF4500"
        assert msg.text == "hello world"
        assert msg.message_type == "text"
        assert msg.is_system is False
        assert msg.msg_id == "uuid-1"

    def test_message_with_emotes(self) -> None:
        data = {
            "id": "uuid-2",
            "chatroom_id": 123,
            "content": "hi [emote:999:PogChamp] gg",
            "type": "message",
            "created_at": "2024-01-01T00:00:00.000000Z",
            "sender": {
                "id": 1,
                "username": "User",
                "slug": "user",
                "identity": {"color": "#00FF00", "badges": []},
            },
        }
        msg = parse_kick_event(self._make_event(data))
        assert msg is not None
        assert msg.text == "hi PogChamp gg"
        assert len(msg.emotes) == 1
        assert msg.emotes[0].code == "PogChamp"
        assert msg.emotes[0].url == "https://files.kick.com/emotes/999/fullsize"

    def test_badges(self) -> None:
        data = {
            "id": "uuid-3",
            "chatroom_id": 123,
            "content": "hello",
            "type": "message",
            "created_at": "2024-01-01T00:00:00.000000Z",
            "sender": {
                "id": 1,
                "username": "Mod",
                "slug": "mod",
                "identity": {
                    "color": "#0000FF",
                    "badges": [
                        {"type": "subscriber", "text": "Subscriber", "count": 6},
                        {"type": "moderator", "text": "Moderator"},
                    ],
                },
            },
        }
        msg = parse_kick_event(self._make_event(data))
        assert msg is not None
        assert len(msg.badges) == 2
        assert msg.badges[0] == Badge(name="subscriber", icon_url="")
        assert msg.badges[1] == Badge(name="moderator", icon_url="")

    def test_subscription_system_message(self) -> None:
        data = {
            "id": "uuid-4",
            "chatroom_id": 123,
            "content": "UserX subscribed",
            "type": "subscription",
            "created_at": "2024-01-01T00:00:00.000000Z",
            "sender": {
                "id": 1,
                "username": "UserX",
                "slug": "userx",
                "identity": {"color": "", "badges": []},
            },
        }
        msg = parse_kick_event(self._make_event(data))
        assert msg is not None
        assert msg.is_system is True
        assert msg.message_type == "sub"

    def test_gifted_sub_system_message(self) -> None:
        data = {
            "id": "uuid-5",
            "chatroom_id": 123,
            "content": "UserY gifted a sub",
            "type": "gifted_subscription",
            "created_at": "2024-01-01T00:00:00.000000Z",
            "sender": {
                "id": 1,
                "username": "UserY",
                "slug": "usery",
                "identity": {"color": "", "badges": []},
            },
        }
        msg = parse_kick_event(self._make_event(data))
        assert msg is not None
        assert msg.is_system is True
        assert msg.message_type == "sub"

    def test_raid_system_message(self) -> None:
        data = {
            "id": "uuid-6",
            "chatroom_id": 123,
            "content": "Raid from UserZ",
            "type": "raid",
            "created_at": "2024-01-01T00:00:00.000000Z",
            "sender": {
                "id": 1,
                "username": "UserZ",
                "slug": "userz",
                "identity": {"color": "", "badges": []},
            },
        }
        msg = parse_kick_event(self._make_event(data))
        assert msg is not None
        assert msg.is_system is True
        assert msg.message_type == "raid"

    def test_non_chat_event_returns_none(self) -> None:
        event = {"event": "pusher:connection_established", "data": "{}"}
        assert parse_kick_event(event) is None

    def test_subscription_succeeded_returns_none(self) -> None:
        event = {
            "event": "pusher_internal:subscription_succeeded",
            "channel": "chatrooms.123.v2",
            "data": "{}",
        }
        assert parse_kick_event(event) is None

    def test_missing_sender_returns_none(self) -> None:
        data = {
            "id": "uuid-7",
            "chatroom_id": 123,
            "content": "orphan",
            "type": "message",
            "created_at": "2024-01-01T00:00:00.000000Z",
        }
        msg = parse_kick_event(self._make_event(data))
        assert msg is None

    def test_no_color_gives_none(self) -> None:
        data = {
            "id": "uuid-8",
            "chatroom_id": 123,
            "content": "hi",
            "type": "message",
            "created_at": "2024-01-01T00:00:00.000000Z",
            "sender": {
                "id": 1,
                "username": "NoColor",
                "slug": "nocolor",
                "identity": {"color": "", "badges": []},
            },
        }
        msg = parse_kick_event(self._make_event(data))
        assert msg is not None
        assert msg.author_color is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/chats/test_kick_chat.py::TestParseKickEvent -v`
Expected: FAIL — `ImportError: cannot import name 'parse_kick_event'`

- [ ] **Step 3: Implement parse_kick_event**

Add to `core/chats/kick_chat.py` (after the emote parser):

```python
import json
import logging
from typing import Any

from core.chat import Badge, ChatMessage

logger = logging.getLogger(__name__)

_CHAT_EVENT = "App\\Events\\ChatMessageSentEvent"

_MSG_TYPE_MAP = {
    "message": "text",
    "subscription": "sub",
    "gifted_subscription": "sub",
    "raid": "raid",
}


def parse_kick_event(event: dict[str, Any]) -> ChatMessage | None:
    """Parse a Pusher event into ChatMessage. Returns None for non-chat events."""
    if event.get("event") != _CHAT_EVENT:
        return None

    try:
        data = json.loads(event["data"]) if isinstance(event["data"], str) else event["data"]
    except (json.JSONDecodeError, KeyError):
        return None

    sender = data.get("sender")
    if not sender:
        return None

    identity = sender.get("identity", {})
    raw_color = identity.get("color", "") or ""
    color = raw_color if raw_color else None

    badges = [
        Badge(name=b["type"], icon_url="")
        for b in identity.get("badges", [])
        if "type" in b
    ]

    raw_content = data.get("content", "")
    text, emotes = parse_kick_emotes(raw_content)

    msg_type_raw = data.get("type", "message")
    message_type = _MSG_TYPE_MAP.get(msg_type_raw, "text")
    is_system = msg_type_raw != "message"

    return ChatMessage(
        platform="kick",
        author=sender.get("slug", ""),
        author_display=sender.get("username", ""),
        author_color=color,
        avatar_url=None,
        text=text,
        timestamp=data.get("created_at", ""),
        badges=badges,
        emotes=emotes,
        is_system=is_system,
        message_type=message_type,
        raw=data,
        msg_id=data.get("id"),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/chats/test_kick_chat.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add core/chats/kick_chat.py tests/chats/test_kick_chat.py
git commit -m "feat(kick-chat): add Pusher event parser with badge/emote/system-msg support"
```

---

### Task 3: KickChatClient — WebSocket connect and disconnect

**Files:**
- Modify: `core/chats/kick_chat.py`
- Test: `tests/chats/test_kick_chat.py`

- [ ] **Step 1: Write failing tests for connect/disconnect**

Append to `tests/chats/test_kick_chat.py`:

```python
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import websockets.exceptions

from core.chats.kick_chat import KickChatClient, PUSHER_URL


class TestKickChatClientInit:
    def test_initial_state(self) -> None:
        client = KickChatClient()
        assert client.platform == "kick"
        assert client._ws is None
        assert client._channel is None
        assert client._running is False
        assert client._authenticated is False


def _make_kick_ws_mock(recv_side_effect: list) -> AsyncMock:
    """Create a mock websocket that yields messages then closes."""
    mock_ws = AsyncMock()

    async def _recv() -> str:
        if not recv_side_effect:
            raise websockets.exceptions.ConnectionClosedOK(None, None)
        val = recv_side_effect.pop(0)
        if isinstance(val, Exception):
            raise val
        return val

    mock_ws.recv = _recv
    mock_ws.close = AsyncMock()
    mock_ws.send = AsyncMock()
    return mock_ws


@asynccontextmanager
async def _patch_kick_ws(mock_ws: AsyncMock):
    """Patch websockets.connect for Kick chat, one connection only."""
    call_count = 0

    @asynccontextmanager
    async def _fake_connect(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise websockets.exceptions.ConnectionClosedOK(None, None)
        yield mock_ws

    with patch("core.chats.kick_chat.websockets.connect", _fake_connect):
        yield


class TestKickChatClientConnect:
    async def test_connects_and_subscribes(self) -> None:
        """After connection_established, client subscribes to chatroom channel."""
        client = KickChatClient()
        conn_msg = json.dumps({
            "event": "pusher:connection_established",
            "data": json.dumps({"socket_id": "123.456", "activity_timeout": 120}),
        })
        sub_ok = json.dumps({
            "event": "pusher_internal:subscription_succeeded",
            "channel": "chatrooms.99.v2",
            "data": "{}",
        })
        mock_ws = _make_kick_ws_mock([conn_msg, sub_ok])

        async with _patch_kick_ws(mock_ws):
            await client.connect(channel_id="testslug", chatroom_id=99)

        send_calls = [c.args[0] for c in mock_ws.send.call_args_list]
        expected_sub = json.dumps({
            "event": "pusher:subscribe",
            "data": {"channel": "chatrooms.99.v2"},
        })
        assert expected_sub in send_calls

    async def test_status_callback_on_connect(self) -> None:
        client = KickChatClient()
        statuses = []
        client.on_status(lambda s: statuses.append(s.connected))

        conn_msg = json.dumps({
            "event": "pusher:connection_established",
            "data": json.dumps({"socket_id": "1.2", "activity_timeout": 120}),
        })
        sub_ok = json.dumps({
            "event": "pusher_internal:subscription_succeeded",
            "channel": "chatrooms.1.v2",
            "data": "{}",
        })
        mock_ws = _make_kick_ws_mock([conn_msg, sub_ok])

        async with _patch_kick_ws(mock_ws):
            await client.connect(channel_id="ch", chatroom_id=1)

        assert True in statuses


class TestKickChatClientDisconnect:
    async def test_disconnect_sets_running_false(self) -> None:
        client = KickChatClient()
        client._running = True
        client._ws = AsyncMock()
        await client.disconnect()
        assert client._running is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/chats/test_kick_chat.py::TestKickChatClientInit -v`
Expected: FAIL — `ImportError: cannot import name 'KickChatClient'`

- [ ] **Step 3: Implement KickChatClient connect/disconnect**

Add to `core/chats/kick_chat.py`:

```python
import asyncio
from collections.abc import Callable

import websockets

from core.chat import ChatStatus

PUSHER_URL = (
    "wss://ws-us2.pusher.com/app/eb1d5f283081a78b932c"
    "?protocol=7&client=js&version=8.4.0-rc2&flash=false"
)
RECONNECT_DELAYS = [3, 6, 12, 24, 48]


class KickChatClient:
    """Pusher WebSocket client for Kick chat."""

    platform = "kick"

    def __init__(self) -> None:
        self._ws: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._message_callback: Callable[[ChatMessage], None] | None = None
        self._status_callback: Callable[[ChatStatus], None] | None = None
        self._channel: str | None = None
        self._chatroom_id: int | None = None
        self._running = False
        self._authenticated = False
        self._token: str | None = None

    async def connect(
        self,
        channel_id: str,
        token: str | None = None,
        chatroom_id: int | None = None,
    ) -> None:
        """Connect to Kick chat via Pusher WebSocket.

        Args:
            channel_id: Channel slug (used for status callbacks).
            token: OAuth access token for sending messages (None = read-only).
            chatroom_id: Kick chatroom ID for Pusher channel subscription.
        """
        self._channel = channel_id
        self._chatroom_id = chatroom_id
        self._running = True
        self._loop = asyncio.get_event_loop()
        self._authenticated = token is not None
        self._token = token

        pusher_channel = f"chatrooms.{chatroom_id}.v2"
        attempt = 0

        while self._running:
            try:
                async with websockets.connect(PUSHER_URL) as ws:
                    self._ws = ws

                    # Wait for connection_established
                    raw = await ws.recv()
                    event = json.loads(raw)
                    if event.get("event") != "pusher:connection_established":
                        continue

                    # Subscribe to chatroom
                    await ws.send(json.dumps({
                        "event": "pusher:subscribe",
                        "data": {"channel": pusher_channel},
                    }))

                    attempt = 0
                    self._emit_status(connected=True)

                    while self._running:
                        raw = await ws.recv()
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8", errors="replace")
                        event = json.loads(raw)
                        ev_name = event.get("event", "")

                        if ev_name == "pusher:ping":
                            await ws.send(json.dumps({"event": "pusher:pong"}))
                            continue

                        if ev_name in (
                            "pusher_internal:subscription_succeeded",
                            "pusher:connection_established",
                        ):
                            continue

                        msg = parse_kick_event(event)
                        if msg and self._message_callback:
                            self._message_callback(msg)

            except websockets.exceptions.ConnectionClosedOK:
                self._emit_status(connected=False)
                break
            except Exception:
                if not self._running:
                    break
                delay = (
                    RECONNECT_DELAYS[attempt]
                    if attempt < len(RECONNECT_DELAYS)
                    else RECONNECT_DELAYS[-1]
                )
                attempt += 1
                if attempt >= len(RECONNECT_DELAYS):
                    self._emit_status(
                        connected=False, error="Max reconnect attempts reached"
                    )
                    break
                logger.warning(
                    "Kick chat disconnected, reconnecting in %ds (attempt %d)",
                    delay,
                    attempt,
                )
                self._emit_status(
                    connected=False,
                    error=f"Reconnecting in {delay}s (attempt {attempt})",
                )
                await asyncio.sleep(delay)

        self._ws = None

    async def disconnect(self) -> None:
        """Disconnect from chat."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._emit_status(connected=False)

    def on_message(self, callback: Callable[[ChatMessage], None]) -> None:
        """Register message callback."""
        self._message_callback = callback

    def on_status(self, callback: Callable[[ChatStatus], None]) -> None:
        """Register status callback."""
        self._status_callback = callback

    def _emit_status(self, connected: bool, error: str | None = None) -> None:
        if self._status_callback and self._channel:
            self._status_callback(
                ChatStatus(
                    connected=connected,
                    platform="kick",
                    channel_id=self._channel,
                    error=error,
                    authenticated=self._authenticated,
                )
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/chats/test_kick_chat.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add core/chats/kick_chat.py tests/chats/test_kick_chat.py
git commit -m "feat(kick-chat): add KickChatClient with Pusher WebSocket connect/disconnect"
```

---

### Task 4: KickChatClient — ping/pong, message callback, reconnect

**Files:**
- Test: `tests/chats/test_kick_chat.py`

- [ ] **Step 1: Write failing tests for ping/pong and message callback**

Append to `tests/chats/test_kick_chat.py`:

```python
class TestKickChatClientPing:
    async def test_pusher_ping_triggers_pong(self) -> None:
        client = KickChatClient()
        conn_msg = json.dumps({
            "event": "pusher:connection_established",
            "data": json.dumps({"socket_id": "1.2", "activity_timeout": 120}),
        })
        sub_ok = json.dumps({
            "event": "pusher_internal:subscription_succeeded",
            "channel": "chatrooms.1.v2",
            "data": "{}",
        })
        ping = json.dumps({"event": "pusher:ping"})
        mock_ws = _make_kick_ws_mock([conn_msg, sub_ok, ping])

        async with _patch_kick_ws(mock_ws):
            await client.connect(channel_id="ch", chatroom_id=1)

        send_calls = [c.args[0] for c in mock_ws.send.call_args_list]
        pong = json.dumps({"event": "pusher:pong"})
        assert pong in send_calls


class TestKickChatClientMessageCallback:
    async def test_chat_message_triggers_callback(self) -> None:
        client = KickChatClient()
        received: list[ChatMessage] = []
        client.on_message(lambda m: received.append(m))

        conn_msg = json.dumps({
            "event": "pusher:connection_established",
            "data": json.dumps({"socket_id": "1.2", "activity_timeout": 120}),
        })
        sub_ok = json.dumps({
            "event": "pusher_internal:subscription_succeeded",
            "channel": "chatrooms.1.v2",
            "data": "{}",
        })
        chat_data = {
            "id": "msg-1",
            "chatroom_id": 1,
            "content": "hello kick chat",
            "type": "message",
            "created_at": "2024-01-01T00:00:00Z",
            "sender": {
                "id": 1,
                "username": "Tester",
                "slug": "tester",
                "identity": {"color": "#FF0000", "badges": []},
            },
        }
        chat_event = json.dumps({
            "event": "App\\Events\\ChatMessageSentEvent",
            "data": json.dumps(chat_data),
            "channel": "chatrooms.1.v2",
        })
        mock_ws = _make_kick_ws_mock([conn_msg, sub_ok, chat_event])

        async with _patch_kick_ws(mock_ws):
            await client.connect(channel_id="ch", chatroom_id=1)

        assert len(received) == 1
        assert received[0].text == "hello kick chat"
        assert received[0].author == "tester"


class TestKickChatClientReconnect:
    async def test_reconnects_on_error(self) -> None:
        """On unexpected error, client reconnects with backoff."""
        client = KickChatClient()
        statuses: list[dict] = []
        client.on_status(lambda s: statuses.append({"connected": s.connected, "error": s.error}))

        call_count = 0

        @asynccontextmanager
        async def _fake_connect(*_a, **_k):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("boom")
            if call_count == 2:
                raise ConnectionError("boom again")
            # Third attempt: give up after max attempts
            raise ConnectionError("boom 3")

        with patch("core.chats.kick_chat.websockets.connect", _fake_connect):
            with patch("core.chats.kick_chat.asyncio.sleep", new_callable=AsyncMock):
                await client.connect(channel_id="ch", chatroom_id=1)

        # Should have reconnect error statuses
        reconnect_errors = [s for s in statuses if s["error"] and "Reconnecting" in s["error"]]
        assert len(reconnect_errors) >= 1
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/chats/test_kick_chat.py -v`
Expected: all PASS (these test existing connect logic from Task 3)

- [ ] **Step 3: Commit**

```bash
git add tests/chats/test_kick_chat.py
git commit -m "test(kick-chat): add ping/pong, message callback, and reconnect tests"
```

---

### Task 5: KickChatClient — send_message via REST

**Files:**
- Modify: `core/chats/kick_chat.py`
- Test: `tests/chats/test_kick_chat.py`

- [ ] **Step 1: Write failing tests for send_message**

Append to `tests/chats/test_kick_chat.py`:

```python
from unittest.mock import patch as sync_patch


class TestKickChatClientSend:
    async def test_send_without_token_returns_false(self) -> None:
        client = KickChatClient()
        client._authenticated = False
        client._running = True
        client._chatroom_id = 1
        result = await client.send_message("hello")
        assert result is False

    async def test_send_with_token_posts_rest(self) -> None:
        client = KickChatClient()
        client._authenticated = True
        client._running = True
        client._token = "test-token"
        client._chatroom_id = 99
        client._channel = "testch"

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("core.chats.kick_chat.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client.send_message("hello kick")

        assert result is True
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs[1]["json"]["content"] == "hello kick"
        assert call_kwargs[1]["json"]["chatroom_id"] == 99
        assert "Bearer test-token" in call_kwargs[1]["headers"]["Authorization"]

    async def test_send_no_chatroom_returns_false(self) -> None:
        client = KickChatClient()
        client._authenticated = True
        client._running = True
        client._token = "tok"
        client._chatroom_id = None
        result = await client.send_message("hello")
        assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/chats/test_kick_chat.py::TestKickChatClientSend -v`
Expected: FAIL — `AttributeError: 'KickChatClient' object has no attribute 'send_message'`

- [ ] **Step 3: Implement send_message**

Add `send_message` method to `KickChatClient` in `core/chats/kick_chat.py`, and add `import httpx` at the top:

```python
    async def send_message(self, text: str, reply_to: str | None = None) -> bool:
        """Send a chat message via REST API. Returns False if not authenticated."""
        if not self._authenticated or not self._running:
            return False
        if not self._token or not self._chatroom_id:
            return False

        body: dict[str, Any] = {
            "content": text,
            "chatroom_id": self._chatroom_id,
            "type": "message",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.kick.com/public/v1/chat",
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                return resp.status_code == 200
        except Exception:
            logger.warning("Failed to send Kick chat message")
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/chats/test_kick_chat.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add core/chats/kick_chat.py tests/chats/test_kick_chat.py
git commit -m "feat(kick-chat): add REST-based send_message for Kick chat"
```

---

### Task 6: Integrate KickChatClient into ui/api.py

**Files:**
- Modify: `ui/api.py:22` (import)
- Modify: `ui/api.py:69` (type annotation)
- Modify: `ui/api.py:1183-1211` (start_chat)
- Modify: `ui/api.py:1226-1279` (send_chat)

- [ ] **Step 1: Add KickChatClient import**

At `ui/api.py:22`, change:

```python
from core.chats.twitch_chat import TwitchChatClient
```

to:

```python
from core.chats.kick_chat import KickChatClient
from core.chats.twitch_chat import TwitchChatClient
```

- [ ] **Step 2: Update _chat_client type annotation**

At `ui/api.py:69`, change:

```python
self._chat_client: TwitchChatClient | None = None
```

to:

```python
self._chat_client: TwitchChatClient | KickChatClient | None = None
```

- [ ] **Step 3: Update start_chat to handle Kick**

Replace `start_chat` method (`ui/api.py:1183-1211`) with:

```python
    def start_chat(self, channel: str, platform: str = "twitch") -> None:
        """Start chat for a channel. Called when entering player-view."""
        self.stop_chat()

        if platform == "twitch":
            twitch_conf = get_platform_config(self._config, "twitch")
            token = twitch_conf.get("access_token") or None
            login = twitch_conf.get("user_login") or None

            self._chat_client = TwitchChatClient()
            self._chat_client.on_message(self._on_chat_message)
            self._chat_client.on_status(self._on_chat_status)

            def run_chat() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        self._chat_client.connect(channel, token=token, login=login)  # type: ignore[union-attr]
                    )
                except Exception:
                    pass
                finally:
                    loop.close()

            self._chat_thread = threading.Thread(target=run_chat, daemon=True)
            self._chat_thread.start()

        elif platform == "kick":
            kick_conf = get_platform_config(self._config, "kick")
            token = kick_conf.get("access_token") or None

            self._chat_client = KickChatClient()
            self._chat_client.on_message(self._on_chat_message)
            self._chat_client.on_status(self._on_chat_status)

            def run_kick_chat() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # Fetch chatroom_id from channel info
                    kick_client = self._platforms.get("kick")
                    if not kick_client:
                        return
                    info = loop.run_until_complete(kick_client.get_channel_info(channel))
                    chatroom_id = None
                    if isinstance(info, dict):
                        chatroom = info.get("chatroom", {})
                        chatroom_id = chatroom.get("id") if isinstance(chatroom, dict) else info.get("chatroom_id")
                    if chatroom_id is None:
                        self._on_chat_status(
                            ChatStatus(connected=False, platform="kick", channel_id=channel, error="No chatroom found")
                        )
                        return
                    loop.run_until_complete(
                        self._chat_client.connect(channel, token=token, chatroom_id=chatroom_id)  # type: ignore[union-attr]
                    )
                except Exception:
                    pass
                finally:
                    loop.close()

            self._chat_thread = threading.Thread(target=run_kick_chat, daemon=True)
            self._chat_thread.start()
```

- [ ] **Step 4: Update send_chat for Kick (local echo with platform-aware config)**

Replace `send_chat` method (`ui/api.py:1226-1279`) with:

```python
    def send_chat(
        self,
        text: str,
        reply_to: str | None = None,
        reply_display: str | None = None,
        reply_body: str | None = None,
    ) -> None:
        """Send a chat message, optionally as a reply.

        After sending, pushes a local echo to JS because Twitch IRC
        does not echo your own messages back. Kick Pusher may echo back,
        but we add local echo for consistency — JS deduplicates by msg_id.
        """
        if not self._chat_client or not text:
            return
        client = self._chat_client
        loop = client._loop
        if not loop or loop.is_closed():
            return

        platform = client.platform
        conf = get_platform_config(self._config, platform)
        login = conf.get("user_login", "")
        display = conf.get("user_display_name", "") or login

        def _do_send() -> None:
            future = asyncio.run_coroutine_threadsafe(
                client.send_message(text, reply_to=reply_to), loop
            )
            try:
                ok = future.result(timeout=5)
            except Exception:
                ok = False
            if ok:
                echo = json.dumps(
                    {
                        "platform": platform,
                        "author": login,
                        "author_display": display,
                        "author_color": None,
                        "text": text,
                        "timestamp": "",
                        "badges": [],
                        "emotes": [],
                        "is_system": False,
                        "message_type": "text",
                        "msg_id": None,
                        "reply_to_id": reply_to,
                        "reply_to_display": reply_display,
                        "reply_to_body": reply_body,
                        "is_self": True,
                    }
                )
                self._eval_js(f"window.onChatMessage({echo})")

        threading.Thread(target=_do_send, daemon=True).start()
```

- [ ] **Step 5: Run lint and all tests**

Run: `make check`
Expected: lint clean, all tests pass

- [ ] **Step 6: Commit**

```bash
git add ui/api.py
git commit -m "feat(kick-chat): integrate KickChatClient into api.py bridge"
```

---

### Task 7: Final verification — full test suite and lint

**Files:** (none to modify — verification only)

- [ ] **Step 1: Run full test suite**

Run: `make test`
Expected: all tests pass (152+ existing + new Kick chat tests)

- [ ] **Step 2: Run lint and type checking**

Run: `make lint`
Expected: no errors

- [ ] **Step 3: Final commit if any fixups needed**

If any fixups were required:
```bash
git add -u
git commit -m "fix(kick-chat): address lint/test issues from integration"
```
