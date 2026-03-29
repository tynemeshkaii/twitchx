"""Twitch IRC message parser and WebSocket chat client."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from typing import Any

import websockets

from core.chat import Badge, ChatMessage, ChatStatus, Emote

logger = logging.getLogger(__name__)

TWITCH_IRC_URL = "wss://irc-ws.chat.twitch.tv:443"
EMOTE_URL_TEMPLATE = "https://static-cdn.jtvnw.net/emoticons/v2/{id}/default/dark/1.0"

# IRC tag escape sequences
_TAG_ESCAPES = {
    r"\s": " ",
    r"\n": "\n",
    r"\\": "\\",
    r"\r": "\r",
    r"\:": ";",
}

# USERNOTICE msg-id values that map to "sub"
_SUB_MSG_IDS = {"sub", "resub", "subgift", "submysterygift", "giftpaidupgrade"}

RECONNECT_DELAYS = [3, 6, 12, 24, 48]


# ── Pure parsing functions ──────────────────────────────────────────


def _unescape_tag(value: str) -> str:
    """Unescape IRCv3 tag value.

    Order matters: ``\\\\`` must be replaced first so that ``\\s`` in the
    raw string is not misinterpreted as an escaped space.
    """
    # Replace \\ first to avoid double-unescaping
    result = value.replace("\\\\", "\x00")
    result = result.replace("\\s", " ")
    result = result.replace("\\n", "\n")
    result = result.replace("\\r", "\r")
    result = result.replace("\\:", ";")
    result = result.replace("\x00", "\\")
    return result


def parse_tags(raw_tags: str) -> dict[str, str]:
    """Parse IRCv3 tags like ``color=#FF4500;display-name=User``."""
    if not raw_tags:
        return {}
    tags: dict[str, str] = {}
    for pair in raw_tags.split(";"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            tags[key] = _unescape_tag(value)
        elif pair:
            tags[pair] = ""
    return tags


def parse_badges(raw: str) -> list[Badge]:
    """Parse ``subscriber/12,premium/1`` into Badge list."""
    if not raw:
        return []
    return [Badge(name=b, icon_url="") for b in raw.split(",") if b]


def parse_emotes(raw: str | None, text: str) -> list[Emote]:
    """Parse ``25:0-4,354:6-10`` into Emote list with CDN URLs."""
    if not raw:
        return []
    emotes: list[Emote] = []
    for group in raw.split("/"):
        if ":" not in group:
            continue
        emote_id, positions = group.split(":", 1)
        url = EMOTE_URL_TEMPLATE.replace("{id}", emote_id)
        for pos in positions.split(","):
            if "-" not in pos:
                continue
            start_s, end_s = pos.split("-", 1)
            start, end = int(start_s), int(end_s)
            code = text[start : end + 1] if end + 1 <= len(text) else ""
            emotes.append(Emote(code=code, url=url, start=start, end=end))
    return emotes


# Regex to parse an IRC message:
# Optional @tags, :prefix, command, params, and optional trailing
_IRC_RE = re.compile(
    r"^(?:@(?P<tags>\S+) )?"  # optional tags
    r"(?::(?P<prefix>\S+) )?"  # optional prefix
    r"(?P<command>\S+)"  # command
    r"(?P<params>.*)"  # rest
)


def parse_irc_message(line: str, channel: str) -> ChatMessage | None:
    """Parse a raw IRC line. Returns ChatMessage for PRIVMSG/USERNOTICE, else None."""
    if not line:
        return None

    m = _IRC_RE.match(line)
    if not m:
        return None

    tags_raw = m.group("tags") or ""
    prefix = m.group("prefix") or ""
    command = m.group("command")
    params = m.group("params").strip()

    if command not in ("PRIVMSG", "USERNOTICE"):
        return None

    tags = parse_tags(tags_raw)

    # Extract trailing message (after " :")
    # params looks like "#channel :message text"
    trailing = ""
    if " :" in params:
        _, trailing = params.split(" :", 1)

    # Author from prefix (nick!user@host)
    author = prefix.split("!", 1)[0] if "!" in prefix else ""

    display_name = tags.get("display-name", author)
    color = tags.get("color") or None
    badges = parse_badges(tags.get("badges", ""))
    emotes = parse_emotes(tags.get("emotes") or None, trailing)
    timestamp = tags.get("tmi-sent-ts", "")

    if command == "PRIVMSG":
        return ChatMessage(
            platform="twitch",
            author=author,
            author_display=display_name,
            author_color=color,
            avatar_url=None,
            text=trailing,
            timestamp=timestamp,
            badges=badges,
            emotes=emotes,
            is_system=False,
            message_type="text",
            raw=tags,
        )

    # USERNOTICE
    msg_id = tags.get("msg-id", "")
    if msg_id in _SUB_MSG_IDS:
        message_type = "sub"
    elif msg_id == "raid":
        message_type = "raid"
    else:
        message_type = "text"

    # User message in trailing takes priority; fall back to system-msg tag
    text = trailing if trailing else tags.get("system-msg", "")

    return ChatMessage(
        platform="twitch",
        author="",
        author_display=display_name,
        author_color=color,
        avatar_url=None,
        text=text,
        timestamp=timestamp,
        badges=badges,
        emotes=emotes,
        is_system=True,
        message_type=message_type,
        raw=tags,
    )


# ── TwitchChatClient ───────────────────────────────────────────────


class TwitchChatClient:
    """WebSocket client for Twitch IRC chat."""

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
        self._channel = channel_id
        self._running = True

        if token and login:
            self._authenticated = True
            self._login = login
            nick = login
            password = f"oauth:{token}"
        else:
            self._authenticated = False
            self._login = None
            nick = "justinfan12345"
            password = "SCHMOOPIIE"

        attempt = 0
        while self._running:
            try:
                async with websockets.connect(TWITCH_IRC_URL) as ws:
                    self._ws = ws
                    await ws.send(f"PASS {password}")
                    await ws.send(f"NICK {nick}")
                    await ws.send("CAP REQ :twitch.tv/tags twitch.tv/commands")
                    await ws.send(f"JOIN #{channel_id}")

                    # Reset reconnect counter on successful connect
                    attempt = 0
                    self._emit_status(connected=True)

                    while self._running:
                        data = await ws.recv()
                        if isinstance(data, bytes):
                            data = data.decode("utf-8", errors="replace")
                        for raw_line in data.split("\r\n"):
                            line = raw_line.strip()
                            if not line:
                                continue
                            if line.startswith("PING ") or line == "PING":
                                await ws.send(line.replace("PING", "PONG", 1))
                                continue
                            msg = parse_irc_message(line, channel_id)
                            if msg and self._message_callback:
                                self._message_callback(msg)

            except websockets.exceptions.ConnectionClosedOK:
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
                    "Twitch chat disconnected, reconnecting in %ds (attempt %d)",
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

    async def send_message(self, text: str) -> bool:
        """Send a chat message. Returns False if not authenticated."""
        if not self._authenticated:
            return False
        if not self._ws or not self._channel:
            return False
        await self._ws.send(f"PRIVMSG #{self._channel} :{text}")
        return True

    def on_message(self, callback: Callable[[ChatMessage], None]) -> None:
        """Register message callback."""
        self._message_callback = callback

    def on_status(self, callback: Callable[[ChatStatus], None]) -> None:
        """Register status callback."""
        self._status_callback = callback

    def _emit_status(self, connected: bool, error: str | None = None) -> None:
        """Emit a status update."""
        if self._status_callback and self._channel:
            self._status_callback(
                ChatStatus(
                    connected=connected,
                    platform="twitch",
                    channel_id=self._channel,
                    error=error,
                )
            )
