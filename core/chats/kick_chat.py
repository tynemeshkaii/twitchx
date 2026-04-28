"""Kick Pusher WebSocket chat client and message parser."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
import websockets

from core.chat import Badge, ChatMessage, ChatSendResult, Emote
from core.chats.base import BaseChatClient, StopReconnect

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


_CHAT_EVENTS = {
    "App\\Events\\ChatMessageEvent",
    "App\\Events\\ChatMessageSentEvent",
}

_MSG_TYPE_MAP = {
    "message": "text",
    "reply": "text",
    "subscription": "sub",
    "gifted_subscription": "sub",
    "raid": "raid",
}


def parse_kick_event(event: dict[str, Any]) -> ChatMessage | None:
    """Parse a Pusher event into ChatMessage. Returns None for non-chat events."""
    if event.get("event") not in _CHAT_EVENTS:
        return None

    try:
        data = (
            json.loads(event["data"])
            if isinstance(event["data"], str)
            else event["data"]
        )
    except (json.JSONDecodeError, KeyError):
        return None

    payload = data.get("message") if isinstance(data.get("message"), dict) else data
    sender = data.get("user") or payload.get("sender")
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

    raw_content = payload.get("content", payload.get("message", ""))
    text, emotes = parse_kick_emotes(raw_content)

    msg_type_raw = payload.get("type", "message")
    message_type = _MSG_TYPE_MAP.get(msg_type_raw, "text")
    is_system = msg_type_raw not in {"message", "reply"}

    metadata = payload.get("metadata", {})
    reply_to_id = None
    reply_to_display = None
    reply_to_body = None
    if isinstance(metadata, dict):
        original_sender = metadata.get("original_sender", {})
        original_message = metadata.get("original_message", {})
        if isinstance(original_sender, dict):
            reply_to_display = original_sender.get("username")
        if isinstance(original_message, dict):
            reply_to_id = original_message.get("id")
            reply_to_body = original_message.get("content")

    author = sender.get("slug", "")
    if not author and sender.get("username"):
        author = str(sender["username"]).strip().lower()

    return ChatMessage(
        platform="kick",
        author=author,
        author_display=sender.get("username", ""),
        author_color=color,
        avatar_url=sender.get("profile_thumb"),
        text=text,
        timestamp=payload.get("created_at", data.get("created_at", "")),
        badges=badges,
        emotes=emotes,
        is_system=is_system,
        message_type=message_type,
        raw=data,
        msg_id=payload.get("id"),
        reply_to_id=reply_to_id,
        reply_to_display=reply_to_display,
        reply_to_body=reply_to_body,
    )


# ── KickChatClient ─────────────────────────────────────────────────

PUSHER_URL = (
    "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679"
    "?protocol=7&client=js&version=8.4.0&flash=false"
)


class KickChatClient(BaseChatClient):
    """Pusher WebSocket client for Kick chat."""

    platform = "kick"

    # Pusher delivers on multiple channel variants; deduplicate by msg_id.
    _DEDUP_MAX = 200

    def __init__(self) -> None:
        super().__init__()
        self._chatroom_id: int | None = None
        self._broadcaster_user_id: int | None = None
        self._token: str | None = None
        self._seen_msg_ids: set[str] = set()
        self._seen_msg_order: list[str] = []

    async def connect(
        self,
        channel_id: str,
        token: str | None = None,
        chatroom_id: int | None = None,
        broadcaster_user_id: int | None = None,
        can_send: bool | None = None,
    ) -> None:
        """Connect to Kick chat via Pusher WebSocket."""
        self._channel = channel_id
        self._chatroom_id = chatroom_id
        self._broadcaster_user_id = broadcaster_user_id
        self._running = True
        self._loop = __import__("asyncio").get_running_loop()
        self._authenticated = (
            bool(token) if can_send is None else bool(token) and can_send
        )
        self._token = token

        pusher_channels = [
            f"chatrooms.{chatroom_id}.v2",
            f"chatrooms.{chatroom_id}",
            f"chatroom_{chatroom_id}",
        ]

        async def _connect_ws() -> None:
            try:
                async with websockets.connect(PUSHER_URL) as ws:
                    self._ws = ws

                    # Wait for connection_established
                    raw = await ws.recv()
                    event = json.loads(raw)
                    if event.get("event") != "pusher:connection_established":
                        raise ValueError("Pusher connection not established")

                    # Kick currently acknowledges multiple channel aliases; subscribe
                    # to all known variants so chat survives backend naming changes.
                    for pusher_channel in pusher_channels:
                        await ws.send(
                            json.dumps(
                                {
                                    "event": "pusher:subscribe",
                                    "data": {"channel": pusher_channel},
                                }
                            )
                        )

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
                            if msg.msg_id:
                                if msg.msg_id in self._seen_msg_ids:
                                    continue
                                self._seen_msg_ids.add(msg.msg_id)
                                self._seen_msg_order.append(msg.msg_id)
                                if len(self._seen_msg_order) > self._DEDUP_MAX:
                                    self._seen_msg_ids.discard(
                                        self._seen_msg_order.pop(0)
                                    )
                            self._message_callback(msg)
            except websockets.exceptions.ConnectionClosedOK:
                self._emit_status(connected=False)
                raise StopReconnect() from None

        await self._reconnect_loop(_connect_ws)
        self._ws = None

    @staticmethod
    def _extract_send_error(
        status_code: int, payload: dict[str, Any], reply_to: str | None
    ) -> str:
        message = str(payload.get("message", "")).strip()

        if status_code == 400:
            return "Kick rejected this message. Check the length and reply target."
        if status_code == 401:
            return "Kick chat token expired. Re-login to Kick."
        if status_code == 403:
            return (
                "Kick blocked this message. The channel may be follower-only, "
                "subscriber-only, or your account may not meet chat requirements."
            )
        if status_code == 404 and reply_to:
            return "Kick could not find the message you're replying to."
        if status_code == 404:
            return "Kick could not find this chat channel."
        if status_code == 429:
            return "Kick chat rate limit hit. Wait a moment and try again."
        if message and message.upper() != "OK":
            return f"Kick chat error: {message}"
        return "Kick did not accept the message."

    async def send_message(
        self, text: str, reply_to: str | None = None
    ) -> ChatSendResult:
        """Send a chat message via REST API."""
        channel_id = self._channel or ""
        if not self._authenticated or not self._running:
            return ChatSendResult(
                ok=False,
                platform="kick",
                channel_id=channel_id,
                error="Kick chat is read-only. Re-login to send.",
            )
        if not self._token or not self._broadcaster_user_id:
            return ChatSendResult(
                ok=False,
                platform="kick",
                channel_id=channel_id,
                error="Kick chat metadata is incomplete. Reload the stream and try again.",
            )

        body: dict[str, Any] = {
            "content": text,
            "broadcaster_user_id": self._broadcaster_user_id,
            "type": "user",
        }
        if reply_to:
            body["reply_to_message_id"] = reply_to

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.kick.com/public/v1/chat",
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=body,
                )
        except Exception:
            logger.warning("Failed to send Kick chat message", exc_info=True)
            return ChatSendResult(
                ok=False,
                platform="kick",
                channel_id=channel_id,
                error="Could not reach the Kick chat API.",
            )

        try:
            payload = resp.json()
        except ValueError:
            payload = {"message": resp.text[:200].strip()}

        if not (200 <= resp.status_code < 300):
            return ChatSendResult(
                ok=False,
                platform="kick",
                channel_id=channel_id,
                error=self._extract_send_error(resp.status_code, payload, reply_to),
            )

        data: dict[str, Any] = {}
        if isinstance(payload, dict):
            raw_data = payload.get("data", {})
            if isinstance(raw_data, dict):
                data = raw_data
        is_sent = bool(data.get("is_sent"))
        message_id = data.get("message_id")
        if not is_sent:
            return ChatSendResult(
                ok=False,
                platform="kick",
                channel_id=channel_id,
                error="Kick did not confirm that the message was sent.",
            )
        return ChatSendResult(
            ok=True,
            platform="kick",
            channel_id=channel_id,
            message_id=str(message_id) if message_id else None,
        )
