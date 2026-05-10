"""YouTube Live Chat polling client and message parser."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.chat import Badge, ChatMessage, ChatSendResult
from core.chats.base import RECONNECT_DELAYS, BaseChatClient, StopReconnect

logger = logging.getLogger(__name__)

_CHAT_MESSAGES_QUOTA = 5
_DEFAULT_POLL_INTERVAL = 5.0
_MIN_POLL_INTERVAL = 2.0
_DEDUP_MAX = 500

_MSG_TYPE_MAP = {
    "textMessageEvent": "text",
    "superChatEvent": "super_chat",
    "newSponsorEvent": "sub",
    "memberMilestoneChatEvent": "sub",
}


def parse_youtube_chat_message(item: dict[str, Any]) -> ChatMessage | None:
    """Parse a YouTube liveChatMessages.list item into a ChatMessage.

    Returns None for non-displayable message types (deletions, bans).
    """
    snippet = item.get("snippet", {})
    author_details = item.get("authorDetails", {})

    msg_type_raw = snippet.get("type", "")

    if msg_type_raw in ("messageDeletedEvent", "userBannedEvent"):
        return None

    message_type = _MSG_TYPE_MAP.get(msg_type_raw, "text")

    text = ""
    if msg_type_raw == "textMessageEvent":
        text = snippet.get("textMessageDetails", {}).get("messageText", "")
    elif msg_type_raw == "superChatEvent":
        details = snippet.get("superChatDetails", {})
        amount = details.get("amountDisplayString", "")
        comment = details.get("userComment", "")
        text = f"{amount} {comment}".strip() if amount else comment
    elif msg_type_raw in ("newSponsorEvent", "memberMilestoneChatEvent"):
        text = snippet.get("displayMessage", "")
    else:
        text = snippet.get("displayMessage", "")

    author_id = author_details.get("channelId", "")
    author_display = author_details.get("displayName", author_id)
    avatar_url = author_details.get("profileImageUrl", "") or None

    badges: list[Badge] = []
    if author_details.get("isChatOwner"):
        badges.append(Badge(name="owner", icon_url=""))
    if author_details.get("isChatModerator"):
        badges.append(Badge(name="moderator", icon_url=""))
    if author_details.get("isChatSponsor"):
        badges.append(Badge(name="sponsor", icon_url=""))
    if author_details.get("isVerified"):
        badges.append(Badge(name="verified", icon_url=""))

    is_system = msg_type_raw != "textMessageEvent"
    if msg_type_raw == "superChatEvent":
        is_system = True

    timestamp = snippet.get("publishedAt", "")
    msg_id = item.get("id") or snippet.get("id", "")

    return ChatMessage(
        platform="youtube",
        author=author_id,
        author_display=author_display,
        author_color=None,
        avatar_url=avatar_url,
        text=text,
        timestamp=timestamp,
        badges=badges,
        emotes=[],
        is_system=is_system,
        message_type=message_type,
        raw=item,
        msg_id=msg_id,
    )


class YouTubeChatClient(BaseChatClient):
    """Polling client for YouTube Live Chat via Data API v3.

    Unlike Twitch/Kick which use WebSocket connections, YouTube Live Chat
    is accessed via periodic HTTP polling of the liveChatMessages.list endpoint.
    Each poll costs 5 quota units.
    """

    platform = "youtube"

    def __init__(self, youtube_client: Any) -> None:
        super().__init__()
        self._yt = youtube_client
        self._live_chat_id: str | None = None
        self._next_page_token: str | None = None
        self._polling_interval: float = _DEFAULT_POLL_INTERVAL
        self._seen_msg_ids: set[str] = set()
        self._seen_msg_order: list[str] = []

    async def connect(
        self,
        channel_id: str,
        token: str | None = None,
        live_chat_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Connect to YouTube Live Chat by polling liveChatMessages.list.

        If live_chat_id is not provided, attempts to resolve it from the
        channel's current live stream via the YouTube Data API.
        """
        self._channel = channel_id
        self._running = True
        self._loop = __import__("asyncio").get_running_loop()
        self._authenticated = bool(token)

        if live_chat_id:
            self._live_chat_id = live_chat_id
        else:
            try:
                chat_id = await self._resolve_live_chat_id(channel_id)
            except Exception as e:
                logger.warning("Failed to resolve YouTube live chat ID: %s", e)
                self._emit_status(
                    connected=False,
                    error=f"Could not find live chat: {e}"[:120],
                )
                return
            if not chat_id:
                self._emit_status(
                    connected=False,
                    error="No active live chat found for this channel.",
                )
                return
            self._live_chat_id = chat_id

        self._emit_status(connected=True)

        attempt = 0
        while self._running:
            try:
                await self._poll_messages()
                attempt = 0
            except StopReconnect:
                break
            except Exception as e:
                if not self._running:
                    break
                attempt += 1
                if attempt >= len(RECONNECT_DELAYS):
                    self._emit_status(
                        connected=False, error=f"Max reconnect attempts: {e}"[:120]
                    )
                    break
                delay = RECONNECT_DELAYS[min(attempt - 1, len(RECONNECT_DELAYS) - 1)]
                self._emit_status(
                    connected=False, error=f"Retrying in {delay}s: {e}"[:120]
                )
                await asyncio.sleep(delay)

        self._ws = None

    async def _resolve_live_chat_id(self, channel_id: str) -> str | None:
        """Resolve liveChatId from a channel's current live stream."""
        video_id = self._yt._live_video_ids.get(channel_id, "")
        if not video_id:
            return None

        data = await self._yt._yt_get(
            "videos",
            params={"part": "liveStreamingDetails", "id": video_id},
        )
        items = data.get("items", [])
        if not items:
            return None

        live_details = items[0].get("liveStreamingDetails", {})
        return live_details.get("activeLiveChatId") or None

    async def _poll_messages(self) -> None:
        """Fetch one batch of chat messages and sleep until next poll."""
        if not self._live_chat_id or not self._running:
            return

        if not self._yt._quota.check_and_use(_CHAT_MESSAGES_QUOTA):
            logger.warning("YouTube quota exhausted, stopping chat poll")
            self._emit_status(
                connected=False,
                error="YouTube API daily quota exceeded. Chat polling stopped.",
            )
            raise StopReconnect()

        params: dict[str, str] = {
            "part": "snippet,authorDetails",
            "liveChatId": self._live_chat_id,
            "maxResults": "200",
        }
        if self._next_page_token:
            params["pageToken"] = self._next_page_token

        data = await self._yt._yt_get(
            "liveChat/messages", params=params, auth_required=False
        )

        if not self._running:
            return

        if isinstance(data, dict) and "error" in data:
            error = data["error"]
            for err in error.get("errors", []):
                reason = err.get("reason", "")
                if reason == "liveChatEnded":
                    self._emit_status(
                        connected=False, error="Live stream has ended."
                    )
                    raise StopReconnect()
                if reason == "quotaExceeded":
                    self._emit_status(
                        connected=False,
                        error="YouTube API daily quota exceeded.",
                    )
                    raise StopReconnect()
            raise ValueError(
                f"YouTube chat API error: {error.get('message', 'Unknown')}"
            )

        polling_ms = data.get("pollingIntervalMillis", 5000)
        self._polling_interval = max(_MIN_POLL_INTERVAL, polling_ms / 1000.0)
        self._next_page_token = data.get("nextPageToken")

        for item in data.get("items", []):
            msg = parse_youtube_chat_message(item)
            if msg is None:
                continue
            if msg.msg_id:
                if msg.msg_id in self._seen_msg_ids:
                    continue
                self._seen_msg_ids.add(msg.msg_id)
                self._seen_msg_order.append(msg.msg_id)
                if len(self._seen_msg_order) > _DEDUP_MAX:
                    old_id = self._seen_msg_order.pop(0)
                    self._seen_msg_ids.discard(old_id)
            if self._message_callback:
                self._message_callback(msg)

        await asyncio.sleep(self._polling_interval)

    async def disconnect(self) -> None:
        """Stop polling and disconnect."""
        self._running = False
        self._live_chat_id = None
        self._next_page_token = None
        self._seen_msg_ids.clear()
        self._seen_msg_order.clear()
        self._emit_status(connected=False)

    async def send_message(
        self, text: str, reply_to: str | None = None
    ) -> ChatSendResult:
        """YouTube Live Chat does not support sending from third-party apps."""
        channel_id = self._channel or ""
        return ChatSendResult(
            ok=False,
            platform="youtube",
            channel_id=channel_id,
            error="YouTube chat is read-only in TwitchX.",
        )