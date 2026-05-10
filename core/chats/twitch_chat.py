"""Twitch IRC message parser and WebSocket chat client."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

import websockets

from core.chat import Badge, ChatMessage, ChatSendResult, Emote
from core.chats.base import BaseChatClient, StopReconnect

logger = logging.getLogger(__name__)

TWITCH_IRC_URL = "wss://irc-ws.chat.twitch.tv:443"
EMOTE_URL_TEMPLATE = "https://static-cdn.jtvnw.net/emoticons/v2/{id}/default/dark/1.0"

_SUB_MSG_IDS = {"sub", "resub", "subgift", "submysterygift", "giftpaidupgrade"}


def parse_names_reply(line: str) -> list[str]:
    """Parse IRC 353 (NAMES reply) into a list of usernames."""
    if " 353 " not in line:
        return []
    if " :" not in line:
        return []
    _, trailing = line.rsplit(" :", 1)
    users = [u.lstrip("@+") for u in trailing.strip().split() if u.strip()]
    return users


def parse_join_part(line: str) -> tuple[str | None, str | None]:
    """Parse JOIN or PART line. Returns (action, username) or (None, None)."""
    for command in ("JOIN", "PART"):
        if f" {command} " in line or line.endswith(f" {command}"):
            prefix_end = line.find(" ")
            if prefix_end < 0:
                return None, None
            prefix = line[1:prefix_end] if line.startswith(":") else ""
            nick = prefix.split("!")[0] if "!" in prefix else ""
            if nick:
                return command.lower(), nick
    return None, None


# ── Pure parsing functions ──────────────────────────────────────────


def _unescape_tag(value: str) -> str:
    """Unescape IRCv3 tag value.

    Split on ``\\\\`` first so that single-backslash sequences inside each
    segment are unambiguous, then rejoin with a literal ``\\``.  This avoids
    the NUL-byte placeholder trick which breaks on rare inputs containing \\x00.
    """
    parts = value.split("\\\\")
    for i, part in enumerate(parts):
        part = part.replace("\\s", " ")
        part = part.replace("\\n", "\n")
        part = part.replace("\\r", "\r")
        part = part.replace("\\:", ";")
        parts[i] = part
    return "\\".join(parts)


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
    msg_id = tags.get("id") or None

    # Reply threading
    reply_to_id = tags.get("reply-parent-msg-id") or None
    reply_to_display = tags.get("reply-parent-display-name") or None
    reply_to_body = tags.get("reply-parent-msg-body") or None

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
            msg_id=msg_id,
            reply_to_id=reply_to_id,
            reply_to_display=reply_to_display,
            reply_to_body=reply_to_body,
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


class TwitchChatClient(BaseChatClient):
    """WebSocket client for Twitch IRC chat."""

    platform = "twitch"

    def __init__(self) -> None:
        super().__init__()
        self._login: str | None = None
        self._users: set[str] = set()
        self._user_list_callback: Callable[[list[str]], None] | None = None

    def on_user_list(self, callback: Callable[[list[str]], None]) -> None:
        self._user_list_callback = callback

    async def connect(
        self,
        channel_id: str,
        token: str | None = None,
        login: str | None = None,
    ) -> None:
        """Connect to Twitch IRC and join channel. token=None for anonymous."""
        self._channel = channel_id
        self._running = True
        self._loop = __import__("asyncio").get_running_loop()

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

        async def _connect_ws() -> None:
            nonlocal nick, password
            try:
                async with websockets.connect(TWITCH_IRC_URL) as ws:
                    self._ws = ws
                    await ws.send(f"PASS {password}")
                    await ws.send(f"NICK {nick}")
                    await ws.send("CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership")
                    await ws.send(f"JOIN #{channel_id}")

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
                            names = parse_names_reply(line)
                            if names:
                                self._users.update(names)
                                if self._user_list_callback:
                                    self._user_list_callback(sorted(self._users))
                                continue
                            action, nick = parse_join_part(line)
                            if action == "join" and nick:
                                self._users.add(nick)
                                if self._user_list_callback:
                                    self._user_list_callback(sorted(self._users))
                                continue
                            elif action == "part" and nick:
                                self._users.discard(nick)
                                if self._user_list_callback:
                                    self._user_list_callback(sorted(self._users))
                                continue
                            # Detect login failure and fall back to anonymous
                            if (
                                "Login unsuccessful" in line
                                or "Login authentication failed" in line
                            ):
                                logger.warning(
                                    "Twitch IRC login failed, falling back to anonymous"
                                )
                                self._authenticated = False
                                self._login = None
                                nick = "justinfan12345"
                                password = "SCHMOOPIIE"
                                self._emit_status(connected=False, error="anonymous")
                                return
                            msg = parse_irc_message(line, channel_id)
                            if msg and self._message_callback:
                                self._message_callback(msg)
            except websockets.exceptions.ConnectionClosedOK:
                self._emit_status(connected=False)
                raise StopReconnect() from None

        await self._reconnect_loop(_connect_ws)
        self._ws = None

    async def send_message(
        self, text: str, reply_to: str | None = None
    ) -> ChatSendResult:
        """Send a chat message.

        Args:
            text: Message text to send.
            reply_to: Optional message ID to reply to (threaded reply).
        """
        channel_id = self._channel or ""
        if not self._authenticated or not self._running:
            return ChatSendResult(
                ok=False,
                platform="twitch",
                channel_id=channel_id,
                error="Twitch chat is read-only. Re-login to send.",
            )
        if not self._ws or not self._channel:
            return ChatSendResult(
                ok=False,
                platform="twitch",
                channel_id=channel_id,
                error="Twitch chat is not connected yet.",
            )
        try:
            if reply_to:
                await self._ws.send(
                    f"@reply-parent-msg-id={reply_to} PRIVMSG #{self._channel} :{text}"
                )
            else:
                await self._ws.send(f"PRIVMSG #{self._channel} :{text}")
        except Exception:
            return ChatSendResult(
                ok=False,
                platform="twitch",
                channel_id=channel_id,
                error="Failed to send Twitch chat message.",
            )
        return ChatSendResult(ok=True, platform="twitch", channel_id=channel_id)
