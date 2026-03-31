"""Kick Pusher WebSocket chat client and message parser."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
from typing import Any

import httpx
import websockets

from core.chat import Badge, ChatMessage, ChatStatus, Emote

logger = logging.getLogger(__name__)

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


# ── KickChatClient ─────────────────────────────────────────────────

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
        """Connect to Kick chat via Pusher WebSocket."""
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
