"""Kick Pusher WebSocket chat client and message parser."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from core.chat import Badge, ChatMessage, Emote

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
