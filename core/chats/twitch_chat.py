"""Twitch IRC message parser and WebSocket chat client."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple

import websockets

from core.chat import Badge, ChatMessage, ChatSendResult, Emote
from core.chats.base import BaseChatClient, ReconnectNow, StopReconnect

logger = logging.getLogger(__name__)

_REPLY_ID_RE = re.compile(r"[A-Za-z0-9-]+")

TWITCH_IRC_URL = "wss://irc-ws.chat.twitch.tv:443"
EMOTE_URL_TEMPLATE = "https://static-cdn.jtvnw.net/emoticons/v2/{id}/default/dark/1.0"

_SUB_MSG_IDS = {"sub", "resub", "subgift", "submysterygift", "giftpaidupgrade"}

# NOTICE msg-ids Twitch uses to reject a PRIVMSG the user just sent.
NOTICE_REJECT_IDS = frozenset(
    {
        "msg_banned",
        "msg_bad_characters",
        "msg_channel_blocked",
        "msg_channel_suspended",
        "msg_duplicate",
        "msg_emoteonly",
        "msg_followersonly",
        "msg_followersonly_followed",
        "msg_followersonly_zero",
        "msg_r9k",
        "msg_ratelimit",
        "msg_rejected",
        "msg_rejected_mandatory",
        "msg_requires_verified_phone_number",
        "msg_slowmode",
        "msg_subsonly",
        "msg_suspended",
        "msg_timedout",
        "msg_verified_email",
    }
)

_LOGIN_FAILED_MARKERS = ("Login unsuccessful", "Login authentication failed")

ANON_NICK = "justinfan12345"
ANON_PASSWORD = "SCHMOOPIIE"


# ── Pure parsing functions ──────────────────────────────────────────


# Regex to parse an IRC message:
# Optional @tags, :prefix, command, params, and optional trailing
_IRC_RE = re.compile(
    r"^(?:@(?P<tags>\S+) )?"  # optional tags
    r"(?::(?P<prefix>\S+) )?"  # optional prefix
    r"(?P<command>\S+)"  # command
    r"(?P<params>.*)"  # rest
)


class IrcLine(NamedTuple):
    tags: dict[str, str]
    prefix: str
    command: str
    args: list[str]
    trailing: str | None

    @property
    def nick(self) -> str:
        return self.prefix.split("!", 1)[0] if "!" in self.prefix else ""


def parse_irc_line(line: str) -> IrcLine | None:
    """Split a raw IRC line into tags, prefix, command, middle args and trailing."""
    if not line:
        return None
    m = _IRC_RE.match(line)
    if not m:
        return None
    params = m.group("params").lstrip(" ")
    trailing: str | None = None
    if params.startswith(":"):
        middle, trailing = "", params[1:]
    elif " :" in params:
        middle, trailing = params.split(" :", 1)
    else:
        middle = params
    return IrcLine(
        tags=parse_tags(m.group("tags") or ""),
        prefix=m.group("prefix") or "",
        command=m.group("command"),
        args=middle.split(),
        trailing=trailing,
    )


def parse_names_reply(line: str) -> list[str]:
    """Parse IRC 353 (NAMES reply) into a list of usernames."""
    parsed = parse_irc_line(line)
    if parsed is None or parsed.command != "353" or not parsed.trailing:
        return []
    return [u.lstrip("@+") for u in parsed.trailing.split() if u.strip()]


def parse_join_part(line: str) -> tuple[str | None, str | None]:
    """Parse JOIN or PART line. Returns (action, username) or (None, None)."""
    parsed = parse_irc_line(line)
    if parsed is None or parsed.command not in ("JOIN", "PART") or not parsed.nick:
        return None, None
    return parsed.command.lower(), parsed.nick


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


def parse_irc_message(line: str, channel: str) -> ChatMessage | None:
    """Parse a raw IRC line. Returns ChatMessage for PRIVMSG/USERNOTICE, else None."""
    parsed = parse_irc_line(line)
    if parsed is None:
        return None
    return _irc_to_message(parsed)


def _irc_to_message(parsed: IrcLine) -> ChatMessage | None:
    command = parsed.command
    if command not in ("PRIVMSG", "USERNOTICE"):
        return None

    tags = parsed.tags
    # params look like "#channel :message text"
    trailing = parsed.trailing or ""
    author = parsed.nick

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

    def __init__(
        self, token_provider: Callable[[], Awaitable[str | None]] | None = None
    ) -> None:
        super().__init__()
        self._login: str | None = None
        self._token: str | None = None
        self._users: set[str] = set()
        self._user_list_callback: Callable[[list[str]], None] | None = None
        self._notice_callback: Callable[[str, str], None] | None = None
        self._userstate_callback: Callable[[dict[str, str]], None] | None = None
        # Returns a fresh user token (or None); called before every connect attempt.
        self._token_provider = token_provider
        self._login_retry_used = False

    def on_user_list(self, callback: Callable[[list[str]], None]) -> None:
        self._user_list_callback = callback

    def on_notice(self, callback: Callable[[str, str], None]) -> None:
        """Register callback(msg_id, text) for NOTICEs rejecting our own message."""
        self._notice_callback = callback

    def on_userstate(self, callback: Callable[[dict[str, str]], None]) -> None:
        """Register callback(tags) for USERSTATE (sent after an accepted PRIVMSG)."""
        self._userstate_callback = callback

    def _emit_user_list(self) -> None:
        if self._user_list_callback:
            self._user_list_callback(sorted(self._users))

    def _fall_back_to_anonymous(self) -> None:
        self._authenticated = False
        self._login = None
        self._token = None

    async def _credentials(self) -> tuple[str, str]:
        """Return (nick, password) for the next connect attempt."""
        if not (self._authenticated and self._login):
            return ANON_NICK, ANON_PASSWORD
        if self._token_provider is not None:
            try:
                fresh = await self._token_provider()
            except Exception as exc:
                logger.warning("Twitch chat token refresh failed: %s", exc)
                fresh = None
            if fresh:
                self._token = fresh
        return self._login, f"oauth:{self._token}"

    async def connect(
        self,
        channel_id: str,
        token: str | None = None,
        login: str | None = None,
    ) -> None:
        """Connect to Twitch IRC and join channel. token=None for anonymous."""
        if self._cancelled:
            return
        self._channel = channel_id
        self._running = True
        self._loop = asyncio.get_running_loop()

        if token and login:
            self._authenticated = True
            self._login = login
            self._token = token
        else:
            self._fall_back_to_anonymous()

        async def _connect_ws() -> None:
            nick, password = await self._credentials()
            if not self._should_run():
                raise StopReconnect()
            try:
                async with websockets.connect(TWITCH_IRC_URL) as ws:
                    self._ws = ws
                    await ws.send(f"PASS {password}")
                    await ws.send(f"NICK {nick}")
                    await ws.send(
                        "CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership"
                    )
                    await ws.send(f"JOIN #{channel_id}")

                    self._emit_status(connected=True)

                    while self._should_run():
                        data = await ws.recv()
                        if isinstance(data, bytes):
                            data = data.decode("utf-8", errors="replace")
                        for raw_line in data.split("\r\n"):
                            line = raw_line.strip()
                            if line and not await self._handle_line(ws, line):
                                return
            except websockets.exceptions.ConnectionClosedOK:
                self._emit_status(connected=False)
                raise StopReconnect() from None

        await self._reconnect_loop(_connect_ws)
        self._ws = None

    async def _handle_line(self, ws: Any, line: str) -> bool:
        """Dispatch one IRC line by command. Returns False to end this connection."""
        parsed = parse_irc_line(line)
        if parsed is None:
            return True
        command = parsed.command

        if command == "PING":
            await ws.send(line.replace("PING", "PONG", 1))
        elif command == "RECONNECT":
            # Server maintenance: reconnect at once, without backoff.
            raise ReconnectNow()
        elif command == "001":
            self._mark_connected()
            self._login_retry_used = False
        elif command == "353":
            self._users.update(parse_names_reply(line))
            self._emit_user_list()
        elif command in ("JOIN", "PART"):
            nick = parsed.nick
            if nick:
                if command == "JOIN":
                    self._users.add(nick)
                else:
                    self._users.discard(nick)
                self._emit_user_list()
        elif command == "NOTICE":
            return self._handle_notice(parsed)
        elif command == "USERSTATE":
            if self._userstate_callback:
                self._userstate_callback(parsed.tags)
        elif command in ("PRIVMSG", "USERNOTICE"):
            msg = _irc_to_message(parsed)
            if msg and self._message_callback:
                self._message_callback(msg)
        return True

    def _handle_notice(self, parsed: IrcLine) -> bool:
        text = parsed.trailing or ""
        if any(marker in text for marker in _LOGIN_FAILED_MARKERS):
            if (
                self._authenticated
                and self._token_provider is not None
                and not self._login_retry_used
            ):
                # The token may have expired since connect(): retry once with a
                # freshly provided one before giving up on authentication.
                self._login_retry_used = True
                logger.warning("Twitch IRC login failed, retrying with fresh token")
                raise ReconnectNow()
            logger.warning("Twitch IRC login failed, falling back to anonymous")
            self._fall_back_to_anonymous()
            self._emit_status(connected=False, error="anonymous")
            return False
        msg_id = parsed.tags.get("msg-id", "")
        if msg_id in NOTICE_REJECT_IDS:
            if self._notice_callback:
                self._notice_callback(msg_id, text)
        else:
            logger.debug("Twitch NOTICE %s: %s", msg_id or "-", text)
        return True

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
        # CR/LF would split the payload into multiple IRC commands.
        text = text.replace("\r", " ").replace("\n", " ").strip()
        if not text:
            return ChatSendResult(
                ok=False,
                platform="twitch",
                channel_id=channel_id,
                error="Message is empty.",
            )
        if reply_to and not _REPLY_ID_RE.fullmatch(reply_to):
            reply_to = None
        try:
            if reply_to:
                await self._ws.send(
                    f"@reply-parent-msg-id={reply_to} PRIVMSG #{self._channel} :{text}"
                )
            else:
                await self._ws.send(f"PRIVMSG #{self._channel} :{text}")
        except (websockets.exceptions.WebSocketException, OSError, RuntimeError) as exc:
            logger.warning("Twitch chat send failed: %s", exc)
            return ChatSendResult(
                ok=False,
                platform="twitch",
                channel_id=channel_id,
                error="Failed to send Twitch chat message.",
            )
        return ChatSendResult(ok=True, platform="twitch", channel_id=channel_id)
