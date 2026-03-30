# Phase 2: Twitch Chat — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real-time Twitch IRC chat panel to the player view, supporting badges, emotes, colored nicks, message sending (authenticated), anonymous reading, auto-reconnect, and resizable layout.

**Architecture:** A `TwitchChatClient` connects via WebSocket to Twitch IRC in a dedicated thread with its own event loop. Messages are parsed from IRCv3 tags into `ChatMessage` dataclasses (defined in `core/chat.py`) and pushed to JS via `_eval_js()`. The chat panel is a flex sidebar inside `#player-view`, toggled by button/hotkey, resizable via drag handle.

**Tech Stack:** `websockets` library, Twitch IRC (IRCv3 tags), existing `ChatMessage`/`ChatStatus`/`Badge`/`Emote` dataclasses from `core/chat.py`, pywebview JS bridge.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `core/chats/twitch_chat.py` | Twitch IRC WebSocket client — connect, parse, reconnect |
| Create | `tests/chats/test_twitch_chat.py` | Unit tests for IRC parsing and client logic |
| Modify | `ui/api.py` (~lines 43-66, 916-1025, 1173-1184) | Chat bridge methods: `start_chat`, `stop_chat`, `send_chat`, `save_chat_width`, `save_chat_visibility`; integration into `watch()`, `stop_player()`, `close()` |
| Modify | `ui/index.html` (~lines 656-704, 898-908, 1377-1428, 2270-2303) | Chat panel HTML, CSS, JS handlers, keyboard shortcut `C` |
| Modify | `pyproject.toml` (line 6-11) | Add `websockets` dependency |

---

### Task 1: Add `websockets` dependency

**Files:**
- Modify: `pyproject.toml:6-11`

- [ ] **Step 1: Add websockets to dependencies**

```bash
uv add websockets
```

- [ ] **Step 2: Verify installation**

```bash
uv run python -c "import websockets; print(websockets.__version__)"
```

Expected: prints version number (e.g. `14.2`)

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add websockets dependency for Twitch IRC chat"
```

---

### Task 2: IRC message parser — pure functions + tests (TDD)

**Files:**
- Create: `core/chats/twitch_chat.py`
- Create: `tests/chats/test_twitch_chat.py`

This task creates the pure parsing functions that convert raw IRC strings into `ChatMessage` dataclasses. No WebSocket logic yet — just parsing.

- [ ] **Step 1: Write failing tests for IRC parsing**

Create `tests/chats/test_twitch_chat.py`:

```python
"""Tests for Twitch IRC chat parser and client logic."""

from __future__ import annotations

from core.chat import Badge, ChatMessage, Emote
from core.chats.twitch_chat import (
    parse_badges,
    parse_emotes,
    parse_irc_message,
)


class TestParseBadges:
    def test_single_badge(self) -> None:
        result = parse_badges("subscriber/12")
        assert len(result) == 1
        assert result[0].name == "subscriber"
        assert result[0].icon_url == ""

    def test_multiple_badges(self) -> None:
        result = parse_badges("subscriber/12,premium/1")
        assert len(result) == 2
        assert result[0].name == "subscriber"
        assert result[1].name == "premium"

    def test_empty_string(self) -> None:
        assert parse_badges("") == []

    def test_moderator_badge(self) -> None:
        result = parse_badges("moderator/1,subscriber/6")
        assert result[0].name == "moderator"
        assert result[1].name == "subscriber"


class TestParseEmotes:
    def test_single_emote(self) -> None:
        result = parse_emotes("25:0-4", "Kappa hello")
        assert len(result) == 1
        assert result[0].code == "Kappa"
        assert result[0].url == "https://static-cdn.jtvnw.net/emoticons/v2/25/default/dark/1.0"
        assert result[0].start == 0
        assert result[0].end == 4

    def test_multiple_emotes(self) -> None:
        result = parse_emotes("25:0-4,354:6-10", "Kappa HeyGuys world")
        assert len(result) == 2
        assert result[0].code == "Kappa"
        assert result[0].start == 0
        assert result[1].start == 6

    def test_same_emote_multiple_positions(self) -> None:
        result = parse_emotes("25:0-4,25:12-16", "Kappa hello Kappa")
        assert len(result) == 2
        assert result[0].start == 0
        assert result[1].start == 12

    def test_empty_string(self) -> None:
        assert parse_emotes("", "hello") == []

    def test_none_emotes(self) -> None:
        assert parse_emotes(None, "hello") == []


class TestParseIrcMessage:
    def test_privmsg_with_tags(self) -> None:
        raw = (
            "@badge-info=subscriber/12;badges=subscriber/12,premium/1;"
            "color=#FF4500;display-name=TestUser;emotes=25:0-4;"
            "id=abc123;tmi-sent-ts=1234567890 "
            ":testuser!testuser@testuser.tmi.twitch.tv "
            "PRIVMSG #channel :Kappa hello world"
        )
        msg = parse_irc_message(raw, "channel")
        assert isinstance(msg, ChatMessage)
        assert msg.platform == "twitch"
        assert msg.author == "testuser"
        assert msg.author_display == "TestUser"
        assert msg.author_color == "#FF4500"
        assert msg.text == "Kappa hello world"
        assert msg.is_system is False
        assert msg.message_type == "text"
        assert len(msg.badges) == 2
        assert len(msg.emotes) == 1

    def test_privmsg_no_color(self) -> None:
        raw = (
            "@display-name=NoColor;badges=;emotes= "
            ":nocolor!nocolor@nocolor.tmi.twitch.tv "
            "PRIVMSG #channel :just text"
        )
        msg = parse_irc_message(raw, "channel")
        assert msg is not None
        assert msg.author_color is None
        assert msg.text == "just text"

    def test_usernotice_sub(self) -> None:
        raw = (
            "@badge-info=subscriber/1;badges=subscriber/0;"
            "color=#00FF00;display-name=SubUser;"
            "emotes=;msg-id=sub;system-msg=SubUser\\ssubscribed;"
            "tmi-sent-ts=1234567890 "
            ":tmi.twitch.tv USERNOTICE #channel :hype message"
        )
        msg = parse_irc_message(raw, "channel")
        assert msg is not None
        assert msg.is_system is True
        assert msg.message_type == "sub"
        assert "SubUser" in msg.text or "hype message" in msg.text

    def test_usernotice_raid(self) -> None:
        raw = (
            "@badge-info=;badges=;color=;display-name=Raider;"
            "msg-id=raid;msg-param-viewerCount=150;"
            "system-msg=150\\sraiders\\sfrom\\sRaider;"
            "tmi-sent-ts=1234567890 "
            ":tmi.twitch.tv USERNOTICE #channel"
        )
        msg = parse_irc_message(raw, "channel")
        assert msg is not None
        assert msg.is_system is True
        assert msg.message_type == "raid"

    def test_usernotice_subgift(self) -> None:
        raw = (
            "@badge-info=subscriber/6;badges=subscriber/6;"
            "color=#8A2BE2;display-name=Gifter;"
            "emotes=;msg-id=subgift;"
            "system-msg=Gifter\\sgifted\\sa\\ssub;"
            "tmi-sent-ts=1234567890 "
            ":tmi.twitch.tv USERNOTICE #channel"
        )
        msg = parse_irc_message(raw, "channel")
        assert msg is not None
        assert msg.is_system is True
        assert msg.message_type == "sub"

    def test_ping_returns_none(self) -> None:
        assert parse_irc_message("PING :tmi.twitch.tv", "ch") is None

    def test_non_privmsg_returns_none(self) -> None:
        raw = ":tmi.twitch.tv 001 justinfan12345 :Welcome"
        assert parse_irc_message(raw, "ch") is None

    def test_join_returns_none(self) -> None:
        raw = ":justinfan12345!justinfan12345@justinfan12345.tmi.twitch.tv JOIN #channel"
        assert parse_irc_message(raw, "channel") is None
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/chats/test_twitch_chat.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.chats.twitch_chat'` or `ImportError`

- [ ] **Step 3: Implement parsing functions**

Create `core/chats/twitch_chat.py`:

```python
"""Twitch IRC chat client via WebSocket.

Connects to wss://irc-ws.chat.twitch.tv:443, parses IRCv3 tagged messages
into ChatMessage dataclasses, and supports anonymous (justinfan) or
authenticated reading/sending.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from typing import Any

from core.chat import Badge, ChatMessage, ChatStatus, Emote

logger = logging.getLogger(__name__)

IRC_URL = "wss://irc-ws.chat.twitch.tv:443"
ANON_PASS = "SCHMOOPIIE"
ANON_NICK = "justinfan12345"

_EMOTE_URL = "https://static-cdn.jtvnw.net/emoticons/v2/{id}/default/dark/1.0"

# ── Pure parsing functions ──────────────────────────────────


def parse_tags(raw_tags: str) -> dict[str, str]:
    """Parse IRCv3 tags string into a dict.

    Example: 'color=#FF4500;display-name=User' -> {'color': '#FF4500', 'display-name': 'User'}
    """
    tags: dict[str, str] = {}
    for pair in raw_tags.split(";"):
        if "=" in pair:
            key, _, val = pair.partition("=")
            # IRC tag escaping: \\s -> space, \\n -> newline, \\\\ -> backslash
            val = val.replace("\\s", " ").replace("\\n", "\n").replace("\\\\", "\\")
            tags[key] = val
        elif pair:
            tags[pair] = ""
    return tags


def parse_badges(raw: str) -> list[Badge]:
    """Parse badges tag value into Badge list.

    Example: 'subscriber/12,premium/1' -> [Badge('subscriber', ''), Badge('premium', '')]
    """
    if not raw:
        return []
    badges: list[Badge] = []
    for entry in raw.split(","):
        name = entry.split("/")[0]
        if name:
            badges.append(Badge(name=name, icon_url=""))
    return badges


def parse_emotes(raw: str | None, text: str) -> list[Emote]:
    """Parse emotes tag value into Emote list.

    Example: '25:0-4,354:6-10' with text 'Kappa HeyGuys world'
    -> [Emote('Kappa', url, 0, 4), Emote('HeyGuys', url, 6, 10)]
    """
    if not raw:
        return []
    emotes: list[Emote] = []
    for group in raw.split("/"):
        if ":" not in group:
            continue
        emote_id, _, positions = group.partition(":")
        for pos in positions.split(","):
            if "-" not in pos:
                continue
            start_s, _, end_s = pos.partition("-")
            start, end = int(start_s), int(end_s)
            code = text[start : end + 1] if end < len(text) else ""
            emotes.append(
                Emote(
                    code=code,
                    url=_EMOTE_URL.format(id=emote_id),
                    start=start,
                    end=end,
                )
            )
    emotes.sort(key=lambda e: e.start)
    return emotes


# Regex to split an IRC line: optional @tags, optional :prefix, command, params
_IRC_RE = re.compile(
    r"^(?:@(?P<tags>\S+) )?"  # optional tags
    r"(?::(?P<prefix>\S+) )?"  # optional prefix
    r"(?P<command>[A-Z0-9]+)"  # command
    r"(?P<params>.*)"  # rest
)


def _extract_login_from_prefix(prefix: str) -> str:
    """Extract login from IRC prefix like 'user!user@user.tmi.twitch.tv'."""
    return prefix.split("!")[0] if "!" in prefix else prefix


def parse_irc_message(line: str, channel: str) -> ChatMessage | None:
    """Parse a raw IRC line into a ChatMessage, or None if not a chat message.

    Returns None for PING, numeric replies, JOIN/PART, and other non-message lines.
    Handles PRIVMSG (normal messages) and USERNOTICE (subs, raids, gifts).
    """
    m = _IRC_RE.match(line)
    if not m:
        return None

    command = m.group("command")
    if command not in ("PRIVMSG", "USERNOTICE"):
        return None

    tags = parse_tags(m.group("tags") or "")
    prefix = m.group("prefix") or ""
    params = m.group("params").strip()

    # Extract message text (everything after ' :' in params)
    text = ""
    if " :" in params:
        text = params.split(" :", 1)[1]

    author = _extract_login_from_prefix(prefix)
    display = tags.get("display-name", author)
    color = tags.get("color") or None
    timestamp = tags.get("tmi-sent-ts", "")

    badges = parse_badges(tags.get("badges", ""))
    emotes = parse_emotes(tags.get("emotes"), text)

    is_system = command == "USERNOTICE"
    message_type = "text"

    if is_system:
        msg_id = tags.get("msg-id", "")
        if msg_id in ("sub", "resub", "subgift", "submysterygift", "giftpaidupgrade"):
            message_type = "sub"
        elif msg_id == "raid":
            message_type = "raid"
        else:
            message_type = msg_id or "text"

        # For USERNOTICE, use system-msg as text if no user message
        system_msg = tags.get("system-msg", "")
        if system_msg and not text:
            text = system_msg
        elif system_msg and text:
            text = f"{system_msg} — {text}"
        author = tags.get("login", author)

    return ChatMessage(
        platform="twitch",
        author=author,
        author_display=display,
        author_color=color,
        avatar_url=None,
        text=text,
        timestamp=timestamp,
        badges=badges,
        emotes=emotes,
        is_system=is_system,
        message_type=message_type,
        raw=tags,
    )
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/chats/test_twitch_chat.py -v
```

Expected: all 17 tests PASS

- [ ] **Step 5: Run full test suite + lint**

```bash
make check
```

Expected: 134+ tests pass, 0 lint errors

- [ ] **Step 6: Commit**

```bash
git add core/chats/twitch_chat.py tests/chats/test_twitch_chat.py
git commit -m "feat(chat): IRC message parser with badges, emotes, USERNOTICE support"
```

---

### Task 3: TwitchChatClient — WebSocket connect, disconnect, send + tests (TDD)

**Files:**
- Modify: `core/chats/twitch_chat.py`
- Modify: `tests/chats/test_twitch_chat.py`

This task adds the `TwitchChatClient` class with connect/disconnect/send and reconnect logic.

- [ ] **Step 1: Write failing tests for TwitchChatClient**

Append to `tests/chats/test_twitch_chat.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from core.chat import ChatMessage, ChatStatus
from core.chats.twitch_chat import TwitchChatClient


class TestTwitchChatClientConnect:
    """Test connect/disconnect lifecycle."""

    @patch("core.chats.twitch_chat.websockets")
    async def test_anonymous_connect_sends_caps_and_join(self, mock_ws: MagicMock) -> None:
        """Anonymous connection sends PASS, NICK, CAP REQ, and JOIN."""
        mock_conn = AsyncMock()
        mock_conn.recv = AsyncMock(side_effect=Exception("closed"))
        mock_ws.connect = AsyncMock(return_value=mock_conn)

        client = TwitchChatClient()
        status_cb = MagicMock()
        client.on_status(status_cb)

        try:
            await asyncio.wait_for(client.connect("testchannel"), timeout=0.5)
        except (TimeoutError, Exception):
            pass

        sent = [call.args[0] for call in mock_conn.send.call_args_list]
        assert any("SCHMOOPIIE" in s for s in sent), f"Expected PASS in {sent}"
        assert any("justinfan12345" in s for s in sent), f"Expected NICK in {sent}"
        assert any("CAP REQ" in s for s in sent), f"Expected CAP REQ in {sent}"
        assert any("JOIN #testchannel" in s for s in sent), f"Expected JOIN in {sent}"

    @patch("core.chats.twitch_chat.websockets")
    async def test_authenticated_connect_uses_token(self, mock_ws: MagicMock) -> None:
        mock_conn = AsyncMock()
        mock_conn.recv = AsyncMock(side_effect=Exception("closed"))
        mock_ws.connect = AsyncMock(return_value=mock_conn)

        client = TwitchChatClient()

        try:
            await asyncio.wait_for(
                client.connect("ch", token="abc123", login="myuser"), timeout=0.5
            )
        except (TimeoutError, Exception):
            pass

        sent = [call.args[0] for call in mock_conn.send.call_args_list]
        assert any("oauth:abc123" in s for s in sent)
        assert any("myuser" in s for s in sent)


class TestTwitchChatClientDisconnect:
    async def test_disconnect_sets_running_false(self) -> None:
        client = TwitchChatClient()
        client._running = True
        client._ws = AsyncMock()
        await client.disconnect()
        assert client._running is False


class TestTwitchChatClientSend:
    async def test_send_anonymous_returns_false(self) -> None:
        client = TwitchChatClient()
        client._channel = "test"
        client._authenticated = False
        result = await client.send_message("hi")
        assert result is False

    async def test_send_authenticated_returns_true(self) -> None:
        client = TwitchChatClient()
        client._channel = "test"
        client._authenticated = True
        client._ws = AsyncMock()
        result = await client.send_message("hi")
        assert result is True
        client._ws.send.assert_called_once_with("PRIVMSG #test :hi")


class TestTwitchChatClientPingPong:
    @patch("core.chats.twitch_chat.websockets")
    async def test_ping_triggers_pong(self, mock_ws: MagicMock) -> None:
        """PING from Twitch should produce a PONG response."""
        messages = ["PING :tmi.twitch.tv"]
        mock_conn = AsyncMock()
        call_count = 0

        async def fake_recv() -> str:
            nonlocal call_count
            if call_count < len(messages):
                msg = messages[call_count]
                call_count += 1
                return msg
            raise Exception("done")

        mock_conn.recv = AsyncMock(side_effect=fake_recv)
        mock_ws.connect = AsyncMock(return_value=mock_conn)

        client = TwitchChatClient()

        try:
            await asyncio.wait_for(client.connect("ch"), timeout=0.5)
        except (TimeoutError, Exception):
            pass

        sent = [call.args[0] for call in mock_conn.send.call_args_list]
        assert any("PONG :tmi.twitch.tv" in s for s in sent), f"Expected PONG in {sent}"


class TestTwitchChatClientMessageCallback:
    @patch("core.chats.twitch_chat.websockets")
    async def test_privmsg_triggers_callback(self, mock_ws: MagicMock) -> None:
        raw_line = (
            "@display-name=Tester;badges=;emotes=;color=#AABBCC;"
            "tmi-sent-ts=1234567890 "
            ":tester!tester@tester.tmi.twitch.tv "
            "PRIVMSG #channel :hello world"
        )
        messages = [raw_line]
        mock_conn = AsyncMock()
        call_count = 0

        async def fake_recv() -> str:
            nonlocal call_count
            if call_count < len(messages):
                msg = messages[call_count]
                call_count += 1
                return msg
            raise Exception("done")

        mock_conn.recv = AsyncMock(side_effect=fake_recv)
        mock_ws.connect = AsyncMock(return_value=mock_conn)

        client = TwitchChatClient()
        received: list[ChatMessage] = []
        client.on_message(lambda m: received.append(m))

        try:
            await asyncio.wait_for(client.connect("channel"), timeout=0.5)
        except (TimeoutError, Exception):
            pass

        assert len(received) == 1
        assert received[0].author == "tester"
        assert received[0].text == "hello world"
```

- [ ] **Step 2: Run tests — verify new tests fail**

```bash
uv run pytest tests/chats/test_twitch_chat.py -v -k "Client"
```

Expected: ImportError or AttributeError for `TwitchChatClient`

- [ ] **Step 3: Implement TwitchChatClient**

Add to the end of `core/chats/twitch_chat.py`:

```python
# ── Reconnection config ─────────────────────────────────────

_MAX_RECONNECTS = 5
_BACKOFF_BASE = 3  # seconds: 3, 6, 12, 24, 48

try:
    import websockets
except ImportError:
    websockets = None  # type: ignore[assignment]


class TwitchChatClient:
    """Twitch IRC chat client via WebSocket."""

    platform = "twitch"

    def __init__(self) -> None:
        self._ws: Any = None
        self._message_callback: Callable[[ChatMessage], None] | None = None
        self._status_callback: Callable[[ChatStatus], None] | None = None
        self._channel: str | None = None
        self._running = False
        self._authenticated = False
        self._login: str | None = None

    async def connect(
        self,
        channel_id: str,
        token: str | None = None,
        login: str | None = None,
    ) -> None:
        """Connect to Twitch IRC and join channel. token=None for anonymous."""
        self._channel = channel_id.lower()
        self._authenticated = token is not None
        self._login = login
        self._running = True
        reconnect_count = 0

        while self._running and reconnect_count <= _MAX_RECONNECTS:
            try:
                self._ws = await websockets.connect(IRC_URL)

                # Authenticate
                if token and login:
                    await self._ws.send(f"PASS oauth:{token}")
                    await self._ws.send(f"NICK {login}")
                else:
                    await self._ws.send(f"PASS {ANON_PASS}")
                    await self._ws.send(f"NICK {ANON_NICK}")

                # Request IRCv3 capabilities
                await self._ws.send("CAP REQ :twitch.tv/tags twitch.tv/commands")
                await self._ws.send(f"JOIN #{self._channel}")

                # Notify connected
                self._emit_status(connected=True)
                reconnect_count = 0  # Reset on successful connect

                # Message loop
                while self._running:
                    data = await self._ws.recv()
                    for line in data.split("\r\n"):
                        if not line:
                            continue
                        if line.startswith("PING"):
                            await self._ws.send("PONG :tmi.twitch.tv")
                            continue
                        msg = parse_irc_message(line, self._channel)
                        if msg and self._message_callback:
                            self._message_callback(msg)

            except Exception as e:
                if not self._running:
                    break
                reconnect_count += 1
                self._emit_status(connected=False, error=str(e))
                if reconnect_count > _MAX_RECONNECTS:
                    logger.error("Chat: max reconnects reached for #%s", self._channel)
                    break
                delay = _BACKOFF_BASE * (2 ** (reconnect_count - 1))
                logger.info(
                    "Chat: reconnecting to #%s in %ds (attempt %d/%d)",
                    self._channel,
                    delay,
                    reconnect_count,
                    _MAX_RECONNECTS,
                )
                await asyncio.sleep(delay)

        self._emit_status(connected=False)

    async def disconnect(self) -> None:
        """Disconnect from IRC."""
        self._running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def send_message(self, text: str) -> bool:
        """Send a chat message. Returns False if not authenticated."""
        if not self._authenticated or not self._ws or not self._channel:
            return False
        await self._ws.send(f"PRIVMSG #{self._channel} :{text}")
        return True

    def on_message(self, callback: Callable[[ChatMessage], None]) -> None:
        self._message_callback = callback

    def on_status(self, callback: Callable[[ChatStatus], None]) -> None:
        self._status_callback = callback

    def _emit_status(self, connected: bool, error: str | None = None) -> None:
        if self._status_callback:
            self._status_callback(
                ChatStatus(
                    connected=connected,
                    platform="twitch",
                    channel_id=self._channel or "",
                    error=error,
                )
            )
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/chats/test_twitch_chat.py -v
```

Expected: all tests PASS (parsing + client tests)

- [ ] **Step 5: Run full suite + lint**

```bash
make check
```

Expected: 140+ tests pass, 0 lint errors

- [ ] **Step 6: Commit**

```bash
git add core/chats/twitch_chat.py tests/chats/test_twitch_chat.py
git commit -m "feat(chat): TwitchChatClient with WebSocket connect, reconnect, send"
```

---

### Task 4: Chat bridge methods in `ui/api.py`

**Files:**
- Modify: `ui/api.py:1-66` (imports + `__init__`)
- Modify: `ui/api.py:916-1025` (`watch()`, `stop_player()`)
- Modify: `ui/api.py:1173-1184` (`close()`)

This task wires the TwitchChatClient into the pywebview bridge.

- [ ] **Step 1: Add import and init fields**

At the top of `ui/api.py`, add to imports:

```python
from core.chat import ChatMessage, ChatStatus
from core.chats.twitch_chat import TwitchChatClient
```

In `TwitchXApi.__init__`, after `self._user_avatars: dict[str, str] = {}` (line ~65), add:

```python
        # Chat
        self._chat_client: TwitchChatClient | None = None
        self._chat_thread: threading.Thread | None = None
```

- [ ] **Step 2: Add chat bridge methods**

Add before the `# ── Cleanup` section (~line 1171):

```python
    # ── Chat ──────────────────────────────────────────────────

    def start_chat(self, channel: str, platform: str = "twitch") -> None:
        """Start chat for a channel. Called when entering player-view."""
        self.stop_chat()

        if platform != "twitch":
            return  # Only Twitch chat for now

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

    def stop_chat(self) -> None:
        """Stop current chat connection."""
        if self._chat_client:
            client = self._chat_client
            client._running = False
            if client._ws:
                def do_close() -> None:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(client.disconnect())
                    except Exception:
                        pass
                    finally:
                        loop.close()

                threading.Thread(target=do_close, daemon=True).start()
        self._chat_client = None
        self._chat_thread = None

    def send_chat(self, text: str) -> None:
        """Send a chat message."""
        if not self._chat_client or not text:
            return
        client = self._chat_client

        def do_send() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(client.send_message(text))
            except Exception:
                pass
            finally:
                loop.close()

        threading.Thread(target=do_send, daemon=True).start()

    def save_chat_width(self, width: int) -> None:
        """Persist chat panel width."""
        self._config["settings"]["chat_width"] = max(250, min(500, width))
        save_config(self._config)

    def save_chat_visibility(self, visible: bool) -> None:
        """Persist chat panel visibility."""
        self._config["settings"]["chat_visible"] = visible
        save_config(self._config)

    def _on_chat_message(self, msg: ChatMessage) -> None:
        """Callback from chat client — push to JS."""
        data = json.dumps({
            "platform": msg.platform,
            "author": msg.author,
            "author_display": msg.author_display,
            "author_color": msg.author_color,
            "text": msg.text,
            "timestamp": msg.timestamp,
            "badges": [{"name": b.name, "icon_url": b.icon_url} for b in msg.badges],
            "emotes": [{"code": e.code, "url": e.url, "start": e.start, "end": e.end} for e in msg.emotes],
            "is_system": msg.is_system,
            "message_type": msg.message_type,
        })
        self._eval_js(f"window.onChatMessage({data})")

    def _on_chat_status(self, status: ChatStatus) -> None:
        """Callback from chat client — push connection status to JS."""
        data = json.dumps({
            "connected": status.connected,
            "platform": status.platform,
            "channel_id": status.channel_id,
            "error": status.error,
        })
        self._eval_js(f"window.onChatStatus({data})")
```

- [ ] **Step 3: Integrate with player lifecycle**

In `watch()` method, after line `self._eval_js(f"window.onStreamReady({stream_data})")` (~line 1010), add:

```python
            # Start chat for this channel
            self.start_chat(channel, platform)
```

In `stop_player()` method (~line 1022), add `self.stop_chat()` before the existing line:

```python
    def stop_player(self) -> None:
        """Stop playback — tells JS to tear down the <video> player."""
        self.stop_chat()
        self._watching_channel = None
        self._eval_js("window.onPlayerStop()")
```

In `close()` method (~line 1173), add `self.stop_chat()` at the beginning:

```python
    def close(self) -> None:
        self.stop_chat()
        self._shutdown.set()
        self.stop_polling()
        ...
```

- [ ] **Step 4: Add chat settings to config response**

In `get_full_config_for_settings()`, add to the returned dict:

```python
            "chat_visible": settings.get("chat_visible", True),
            "chat_width": settings.get("chat_width", 340),
```

- [ ] **Step 5: Run lint + tests**

```bash
make check
```

Expected: all tests pass, 0 lint errors

- [ ] **Step 6: Commit**

```bash
git add ui/api.py
git commit -m "feat(chat): bridge methods — start_chat, stop_chat, send_chat in TwitchXApi"
```

---

### Task 5: Chat panel HTML + CSS in `ui/index.html`

**Files:**
- Modify: `ui/index.html:656-704` (CSS)
- Modify: `ui/index.html:898-908` (HTML)

- [ ] **Step 1: Add chat panel CSS**

After the `#stream-video` CSS block (~line 704), before the `@keyframes pulse` block, add:

```css
/* ── Chat panel ───────────────────────────────────────── */
#player-content {
  display: flex; flex: 1; overflow: hidden;
}
#chat-panel {
  width: var(--chat-width, 340px);
  min-width: 250px; max-width: 500px;
  display: flex; flex-direction: column;
  background: var(--bg-surface);
  border-left: 1px solid var(--bg-border);
}
#chat-panel.hidden { display: none; }
#chat-header {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--bg-border);
  flex-shrink: 0;
}
#chat-title {
  font-size: 13px; font-weight: 600;
  color: var(--text-secondary);
}
#chat-status-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--text-muted);
  flex-shrink: 0;
}
#chat-status-dot.connected { background: var(--live-green); }
#chat-messages {
  flex: 1; overflow-y: auto;
  padding: 8px; font-size: 13px; line-height: 1.4;
}
.chat-msg { padding: 2px 0; word-wrap: break-word; }
.chat-msg .badge {
  width: 18px; height: 18px;
  vertical-align: middle; margin-right: 2px;
}
.chat-msg .nick { font-weight: 600; cursor: pointer; }
.chat-msg .emote { height: 28px; vertical-align: middle; }
.chat-msg.system { color: var(--text-muted); font-style: italic; }
#chat-new-messages {
  display: none; position: sticky; bottom: 0;
  text-align: center; padding: 4px;
  background: var(--bg-elevated);
  color: var(--accent); cursor: pointer;
  font-size: 12px; font-weight: 600;
  border-top: 1px solid var(--bg-border);
}
#chat-new-messages.visible { display: block; }
#chat-input-area {
  display: flex; padding: 8px; gap: 6px;
  border-top: 1px solid var(--bg-border);
}
#chat-input {
  flex: 1; background: var(--bg-elevated);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-sm);
  color: var(--text-primary); padding: 6px 10px;
  font-size: 13px; font-family: inherit;
  outline: none;
}
#chat-input:focus { border-color: var(--accent); }
#chat-input:disabled { opacity: 0.5; cursor: not-allowed; }
#chat-send-btn {
  padding: 6px 12px; background: var(--accent);
  color: white; border: none;
  border-radius: var(--radius-sm);
  font-size: 12px; font-weight: 600; cursor: pointer;
  font-family: inherit;
}
#chat-send-btn:hover { background: var(--accent-hover); }
#chat-send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
#chat-resize-handle {
  width: 4px; cursor: col-resize;
  background: var(--bg-border); flex-shrink: 0;
}
#chat-resize-handle:hover { background: var(--accent); }
#toggle-chat-btn {
  height: 28px; padding: 0 10px;
  background: var(--bg-elevated); color: var(--text-secondary);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-sm);
  font-size: 13px; cursor: pointer; font-family: inherit;
  transition: all 0.15s ease;
}
#toggle-chat-btn:hover { border-color: var(--accent); color: var(--accent); }
```

- [ ] **Step 2: Modify player-view HTML structure**

Replace the player-view section (~lines 898-908):

**Old:**
```html
      <div id="player-view">
        <div id="player-header">
          <span id="player-channel-name"></span>
          <span id="player-stream-title"></span>
          <div id="player-header-actions">
            <button id="fullscreen-player-btn" title="Fullscreen (F)">&#9974;</button>
            <button id="close-player-btn">&#10005; Close</button>
          </div>
        </div>
        <video id="stream-video" autoplay controls playsinline></video>
      </div>
```

**New:**
```html
      <div id="player-view">
        <div id="player-header">
          <span id="player-channel-name"></span>
          <span id="player-stream-title"></span>
          <div id="player-header-actions">
            <button id="toggle-chat-btn" title="Toggle Chat (C)">&#128172;</button>
            <button id="fullscreen-player-btn" title="Fullscreen (F)">&#9974;</button>
            <button id="close-player-btn">&#10005; Close</button>
          </div>
        </div>
        <div id="player-content">
          <video id="stream-video" autoplay controls playsinline></video>
          <div id="chat-resize-handle"></div>
          <div id="chat-panel">
            <div id="chat-header">
              <span id="chat-title">Chat</span>
              <span id="chat-status-dot"></span>
            </div>
            <div id="chat-messages"></div>
            <div id="chat-new-messages">&#8595; New messages</div>
            <div id="chat-input-area">
              <input id="chat-input" type="text" placeholder="Send a message..." maxlength="500" disabled />
              <button id="chat-send-btn" disabled>Send</button>
            </div>
          </div>
        </div>
      </div>
```

- [ ] **Step 3: Update `#stream-video` CSS**

The existing `#stream-video` rule is:
```css
#stream-video {
  flex: 1; width: 100%; background: #000;
  outline: none;
}
```

Change to:
```css
#stream-video {
  flex: 1; min-width: 0; background: #000;
  outline: none;
}
```

(Replace `width: 100%` with `min-width: 0` so flex works correctly with the chat panel.)

- [ ] **Step 4: Run lint**

```bash
make lint
```

Expected: 0 errors

- [ ] **Step 5: Commit**

```bash
git add ui/index.html
git commit -m "feat(chat): chat panel HTML/CSS layout in player-view"
```

---

### Task 6: Chat JS handlers in `ui/index.html`

**Files:**
- Modify: `ui/index.html` (JS section)

- [ ] **Step 1: Add chat JS callbacks and handlers**

In the JS section, after the `onPlayerState` handler (~line 1395), add:

```javascript
/* ── Chat ───────────────────────────────────────────────── */

var chatAutoScroll = true;

window.onChatMessage = function(msg) {
  var container = document.getElementById('chat-messages');
  if (!container) return;

  var el = document.createElement('div');
  el.className = 'chat-msg' + (msg.is_system ? ' system' : '');

  // Badges
  for (var i = 0; i < msg.badges.length; i++) {
    var badge = msg.badges[i];
    if (badge.icon_url) {
      var img = document.createElement('img');
      img.className = 'badge';
      img.src = badge.icon_url;
      img.alt = badge.name;
      el.appendChild(img);
    }
  }

  // Nick
  if (!msg.is_system) {
    var nick = document.createElement('span');
    nick.className = 'nick';
    nick.textContent = msg.author_display;
    if (msg.author_color) nick.style.color = msg.author_color;
    el.appendChild(nick);

    var sep = document.createElement('span');
    sep.textContent = ': ';
    el.appendChild(sep);
  }

  // Message text with emotes
  renderChatEmotes(el, msg.text, msg.emotes);

  container.appendChild(el);

  // Buffer limit: 500 messages
  while (container.children.length > 500) {
    container.removeChild(container.firstChild);
  }

  // Auto-scroll
  if (chatAutoScroll) {
    container.scrollTop = container.scrollHeight;
  } else {
    var btn = document.getElementById('chat-new-messages');
    if (btn) btn.classList.add('visible');
  }
};

function renderChatEmotes(parent, text, emotes) {
  if (!emotes || emotes.length === 0) {
    parent.appendChild(document.createTextNode(text));
    return;
  }
  var sorted = emotes.slice().sort(function(a, b) { return a.start - b.start; });
  var lastIdx = 0;
  for (var i = 0; i < sorted.length; i++) {
    var emote = sorted[i];
    if (emote.start > lastIdx) {
      parent.appendChild(document.createTextNode(text.slice(lastIdx, emote.start)));
    }
    var img = document.createElement('img');
    img.className = 'emote';
    img.src = emote.url;
    img.alt = emote.code;
    img.title = emote.code;
    parent.appendChild(img);
    lastIdx = emote.end + 1;
  }
  if (lastIdx < text.length) {
    parent.appendChild(document.createTextNode(text.slice(lastIdx)));
  }
}

function clearChatMessages() {
  var container = document.getElementById('chat-messages');
  if (!container) return;
  while (container.firstChild) {
    container.removeChild(container.firstChild);
  }
}

window.onChatStatus = function(status) {
  var dot = document.getElementById('chat-status-dot');
  if (dot) {
    if (status.connected) {
      dot.classList.add('connected');
      dot.title = 'Connected';
      // Clear messages on new connection (channel switch)
      clearChatMessages();
      chatAutoScroll = true;
      var newBtn = document.getElementById('chat-new-messages');
      if (newBtn) newBtn.classList.remove('visible');
    } else {
      dot.classList.remove('connected');
      dot.title = status.error || 'Disconnected';
    }
  }
  updateChatInput();
};

function updateChatInput() {
  var input = document.getElementById('chat-input');
  var btn = document.getElementById('chat-send-btn');
  if (!input || !btn) return;
  var hasAuth = !!(state.currentUser);
  input.disabled = !hasAuth;
  btn.disabled = !hasAuth;
  input.placeholder = hasAuth ? 'Send a message...' : 'Log in to chat';
}
```

- [ ] **Step 2: Add chat scroll detection + "new messages" button**

```javascript
// Scroll detection for chat
document.getElementById('chat-messages').addEventListener('scroll', function() {
  var el = this;
  chatAutoScroll = (el.scrollHeight - el.scrollTop - el.clientHeight) < 60;
  if (chatAutoScroll) {
    var btn = document.getElementById('chat-new-messages');
    if (btn) btn.classList.remove('visible');
  }
});

document.getElementById('chat-new-messages').addEventListener('click', function() {
  var container = document.getElementById('chat-messages');
  container.scrollTop = container.scrollHeight;
  chatAutoScroll = true;
  this.classList.remove('visible');
});
```

- [ ] **Step 3: Add chat input handlers**

```javascript
// Send chat message
document.getElementById('chat-input').addEventListener('keydown', function(e) {
  if (e.key === 'Enter' && this.value.trim()) {
    pywebview.api.send_chat(this.value.trim());
    this.value = '';
  }
});

document.getElementById('chat-send-btn').addEventListener('click', function() {
  var input = document.getElementById('chat-input');
  if (input.value.trim()) {
    pywebview.api.send_chat(input.value.trim());
    input.value = '';
  }
});
```

- [ ] **Step 4: Add toggle chat button handler**

```javascript
// Toggle chat
document.getElementById('toggle-chat-btn').addEventListener('click', function() {
  toggleChatPanel();
});

function toggleChatPanel() {
  var panel = document.getElementById('chat-panel');
  var handle = document.getElementById('chat-resize-handle');
  panel.classList.toggle('hidden');
  if (handle) handle.style.display = panel.classList.contains('hidden') ? 'none' : '';
  pywebview.api.save_chat_visibility(!panel.classList.contains('hidden'));
}
```

- [ ] **Step 5: Add chat resize handler**

```javascript
// Chat resize
(function() {
  var handle = document.getElementById('chat-resize-handle');
  var panel = document.getElementById('chat-panel');
  var dragging = false;

  handle.addEventListener('mousedown', function(e) {
    e.preventDefault();
    dragging = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  });

  document.addEventListener('mousemove', function(e) {
    if (!dragging) return;
    var container = document.getElementById('player-content');
    var rect = container.getBoundingClientRect();
    var newWidth = rect.right - e.clientX;
    newWidth = Math.max(250, Math.min(500, newWidth));
    panel.style.width = newWidth + 'px';
  });

  document.addEventListener('mouseup', function() {
    if (!dragging) return;
    dragging = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    var w = parseInt(panel.style.width) || 340;
    pywebview.api.save_chat_width(w);
  });
})();
```

- [ ] **Step 6: Add keyboard shortcut `C` for chat toggle**

In the `handleKeydown` function, after the `'f'` fullscreen check (~line 2298), add:

```javascript
  } else if (e.key === 'c' && document.getElementById('player-view').classList.contains('active')) {
    e.preventDefault(); toggleChatPanel();
```

- [ ] **Step 7: Initialize chat panel state from config**

In the `showPlayerView()` function, add at the end (before `renderSidebar()`):

```javascript
  // Restore chat panel visibility and width from config
  var chatPanel = document.getElementById('chat-panel');
  var chatHandle = document.getElementById('chat-resize-handle');
  var cfg = pywebview.api.get_full_config_for_settings();
  if (cfg && cfg.chat_width) chatPanel.style.width = cfg.chat_width + 'px';
  if (cfg && cfg.chat_visible === false) {
    chatPanel.classList.add('hidden');
    if (chatHandle) chatHandle.style.display = 'none';
  } else {
    chatPanel.classList.remove('hidden');
    if (chatHandle) chatHandle.style.display = '';
  }
  updateChatInput();
```

In the `hidePlayerView()` function, add after `video.load()`:

```javascript
  // Clear chat
  clearChatMessages();
```

- [ ] **Step 8: Run lint**

```bash
make lint
```

Expected: 0 errors

- [ ] **Step 9: Commit**

```bash
git add ui/index.html
git commit -m "feat(chat): JS handlers — message rendering, emotes, resize, toggle, scroll"
```

---

### Task 7: Final integration test + cleanup

**Files:**
- All modified files

- [ ] **Step 1: Run full test suite**

```bash
make check
```

Expected: 140+ tests pass (117 existing + ~25 new chat tests), 0 lint errors

- [ ] **Step 2: Format code**

```bash
make fmt
```

- [ ] **Step 3: Run lint again after formatting**

```bash
make lint
```

Expected: 0 errors

- [ ] **Step 4: Manual smoke test (optional)**

```bash
./run.sh
```

Verify:
- Start watching a Twitch stream — chat panel appears on the right
- Chat messages appear with colored nicks
- Badge/emote images load from Twitch CDN
- `C` key toggles chat panel visibility
- Drag the resize handle between video and chat
- Close player — chat disconnects, messages cleared
- Anonymous mode: chat input shows "Log in to chat" (disabled)

- [ ] **Step 5: Final commit (only if formatting/lint changes needed)**

```bash
git add -A
git commit -m "chore: Phase 2 lint and format fixes"
```

---

## Summary

| Task | Description | New Tests |
|------|-------------|-----------|
| 1 | Add `websockets` dependency | 0 |
| 2 | IRC parser (badges, emotes, PRIVMSG, USERNOTICE) | ~17 |
| 3 | TwitchChatClient (connect, disconnect, send, reconnect) | ~8 |
| 4 | Chat bridge in `ui/api.py` | 0 |
| 5 | Chat panel HTML + CSS | 0 |
| 6 | Chat JS handlers (render, scroll, resize, toggle) | 0 |
| 7 | Integration test + cleanup | 0 |

**Total: ~25 new tests, 7 tasks**
