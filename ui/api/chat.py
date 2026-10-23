from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx

from core import storage as _storage
from core.chat import ChatMessage, ChatSendResult, ChatStatus, Emote
from core.chats.kick_chat import KickChatClient
from core.chats.twitch_chat import TwitchChatClient, parse_badges
from core.chats.youtube_chat import YouTubeChatClient
from core.storage import get_platform_config, update_config
from core.third_party_emotes import fetch_channel_emotes

from ._base import BaseApiComponent

if TYPE_CHECKING:
    from . import TwitchXApi

logger = logging.getLogger(__name__)

# A Twitch echo waits for USERSTATE (accepted) or NOTICE (rejected); entries
# older than this are considered lost and never rendered.
_ECHO_TTL = 10.0

# set_chat_mode: Helix chat-settings fields the UI may toggle, and the slow
# mode wait range offered by the UI (Helix itself allows 3..120 seconds).
_CHAT_MODES = frozenset({"slow_mode", "emote_mode", "subscriber_mode", "follower_mode"})
_SLOW_WAIT_MIN = 3
_SLOW_WAIT_MAX = 120


def _to_utf16_offset(text: str, cp_index: int) -> int:
    """Convert a code-point index into ``text`` to a UTF-16 code-unit index (JS)."""
    return len(text[:cp_index].encode("utf-16-le")) // 2


def _emotes_payload(text: str, emotes: list[Emote]) -> list[dict[str, Any]]:
    """Serialize emotes with start/end converted from code points to UTF-16 units."""
    result: list[dict[str, Any]] = []
    for e in emotes:
        length = len(e.code) if e.code else e.end - e.start + 1
        result.append(
            {
                "code": e.code,
                "url": e.url,
                "start": _to_utf16_offset(text, e.start),
                "end": _to_utf16_offset(text, e.start + length) - 1,
            }
        )
    return result


@dataclass
class _PendingEcho:
    client: Any
    payload: dict[str, Any]
    created: float = field(default_factory=time.monotonic)


class ChatComponent(BaseApiComponent):
    """Chat connection, message sending, and callbacks."""

    def __init__(self, parent: TwitchXApi) -> None:
        super().__init__(parent)
        self._pending_echoes: deque[_PendingEcho] = deque()
        self._echo_lock = threading.Lock()

    def _is_current(self, client: Any) -> bool:
        return self._api._chat_client is client

    def _bind_callbacks(self, client: Any, channel: str) -> None:
        """Route client callbacks through a check that the client is still active.

        A replaced client may keep delivering for a while (its loop is still
        draining); those events must never reach the UI of the new channel.
        """
        # Known before connect() runs, so every payload can name its channel.
        client._channel = channel
        client.on_message(lambda msg: self._on_chat_message(msg, client))
        client.on_status(lambda status: self._on_chat_status(status, client))

    # ── Start / Stop ────────────────────────────────────────────

    def start_chat(
        self, channel: str, platform: str = "twitch", live_chat_id: str | None = None
    ) -> None:
        self.stop_chat()
        connecting = json.dumps(
            {
                "connected": False,
                "connecting": True,
                "platform": platform,
                "channel_id": channel,
                "error": None,
                "authenticated": False,
                "self_login": "",
            }
        )
        self._eval_js(f"window.onChatStatus({connecting})")

        if platform == "twitch":
            twitch_conf = get_platform_config(self._config, "twitch")
            token = twitch_conf.get("access_token") or None
            login = twitch_conf.get("user_login") or None

            twitch_client = TwitchChatClient(token_provider=self._twitch_user_token)
            self._bind_callbacks(twitch_client, channel)

            def _on_user_list(users: list[str]) -> None:
                if not self._is_current(twitch_client):
                    return
                payload = json.dumps(
                    {
                        "channel_id": channel,
                        "platform": "twitch",
                        "count": len(users),
                        "users": users[:500],
                    }
                )
                self._eval_js(f"window.onChatUserList({payload})")

            twitch_client.on_user_list(_on_user_list)
            twitch_client.on_notice(
                lambda msg_id, text: self._on_notice(msg_id, text, twitch_client)
            )
            twitch_client.on_userstate(
                lambda tags: self._on_userstate(tags, twitch_client)
            )

            self._api._chat_client = twitch_client

            def run_chat() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                twitch_client._loop = loop
                try:
                    loop.run_until_complete(
                        twitch_client.connect(channel, token=token, login=login)
                    )
                except Exception as exc:
                    logger.warning("Twitch chat connect failed: %s", exc)
                    self._on_chat_status(
                        ChatStatus(
                            connected=False,
                            platform="twitch",
                            channel_id=channel,
                            error=str(exc)[:120],
                            authenticated=bool(token and login),
                        ),
                        twitch_client,
                    )
                finally:
                    twitch_client._loop = None
                    self._close_thread_loop(loop)

            self._api._chat_thread = threading.Thread(target=run_chat, daemon=True)
            self._api._chat_thread.start()

            # Fetch third-party emotes for this Twitch channel in a background thread
            def _fetch_emotes() -> None:
                try:
                    twitch_client_ref = self._platforms.get("twitch")
                    twitch_user_id = ""
                    if twitch_client_ref:
                        emote_loop = asyncio.new_event_loop()
                        try:
                            asyncio.set_event_loop(emote_loop)
                            users = emote_loop.run_until_complete(
                                twitch_client_ref.get_users([channel])
                            )
                            if users:
                                twitch_user_id = str(users[0].get("id", ""))
                        except (httpx.HTTPError, OSError, ValueError) as exc:
                            logger.debug(
                                "Failed to resolve Twitch user ID for emotes: %s", exc
                            )
                        finally:
                            self._close_thread_loop(emote_loop)
                    cache_dir = str(_storage.CONFIG_DIR / "emotes")
                    emote_map = fetch_channel_emotes(channel, twitch_user_id, cache_dir)
                    if (
                        emote_map
                        and not self._shutdown.is_set()
                        and self._is_current(twitch_client)
                    ):
                        payload = json.dumps({"channel": channel, "emotes": emote_map})
                        self._eval_js(f"window.onThirdPartyEmotes({payload})")
                except Exception as exc:
                    logger.debug(
                        "Third-party emote fetch failed for %s: %s", channel, exc
                    )

            threading.Thread(target=_fetch_emotes, daemon=True).start()

        elif platform == "kick":
            kick_conf = get_platform_config(self._config, "kick")
            token = kick_conf.get("access_token") or None
            scopes = self._api._parse_scopes(kick_conf.get("oauth_scopes", ""))

            kick_platform = self._platforms.get("kick")
            kick_chat_client = KickChatClient(
                token_provider=kick_platform._ensure_token if kick_platform else None
            )
            self._bind_callbacks(kick_chat_client, channel)
            self._api._chat_client = kick_chat_client

            def run_kick_chat() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                kick_chat_client._loop = loop
                try:
                    kick_client = self._platforms.get("kick")
                    if not kick_client:
                        return
                    info = loop.run_until_complete(
                        kick_client.get_channel_info(channel)
                    )
                    chatroom_id = None
                    broadcaster_user_id = None
                    if isinstance(info, dict):
                        chatroom = info.get("chatroom", {})
                        chatroom_id = (
                            chatroom.get("id")
                            if isinstance(chatroom, dict)
                            else info.get("chatroom_id")
                        )
                        broadcaster_user_id = (
                            info.get("broadcaster_user_id")
                            or info.get("user_id")
                            or info.get("user", {}).get("id")
                        )
                    if chatroom_id is None:
                        self._on_chat_status(
                            ChatStatus(
                                connected=False,
                                platform="kick",
                                channel_id=channel,
                                error="No chatroom found",
                            ),
                            kick_chat_client,
                        )
                        return
                    can_send = bool(
                        token and broadcaster_user_id and "chat:write" in scopes
                    )
                    try:
                        bid = int(broadcaster_user_id) if broadcaster_user_id else None
                    except (ValueError, TypeError):
                        bid = None
                    loop.run_until_complete(
                        kick_chat_client.connect(
                            channel,
                            token=token,
                            chatroom_id=chatroom_id,
                            broadcaster_user_id=bid,
                            can_send=can_send,
                        )
                    )
                except Exception as exc:
                    logger.warning("Kick chat connect failed: %s", exc)
                    self._on_chat_status(
                        ChatStatus(
                            connected=False,
                            platform="kick",
                            channel_id=channel,
                            error=str(exc)[:120] or "Kick chat failed",
                        ),
                        kick_chat_client,
                    )
                finally:
                    kick_chat_client._loop = None
                    self._close_thread_loop(loop)

            self._api._chat_thread = threading.Thread(target=run_kick_chat, daemon=True)
            self._api._chat_thread.start()

        elif platform == "youtube":
            yt_client = self._youtube
            if not yt_client:
                self._on_chat_status(
                    ChatStatus(
                        connected=False,
                        platform="youtube",
                        channel_id=channel,
                        error="YouTube client not available",
                    )
                )
                return

            yt_chat_client = YouTubeChatClient(yt_client)
            self._bind_callbacks(yt_chat_client, channel)
            self._api._chat_client = yt_chat_client

            yt_conf = get_platform_config(self._config, "youtube")
            token = yt_conf.get("access_token") or None

            def run_youtube_chat() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                yt_chat_client._loop = loop
                try:
                    loop.run_until_complete(
                        yt_chat_client.connect(
                            channel,
                            token=token,
                            live_chat_id=live_chat_id,
                        )
                    )
                except Exception as exc:
                    logger.warning("YouTube chat connect failed: %s", exc)
                    self._on_chat_status(
                        ChatStatus(
                            connected=False,
                            platform="youtube",
                            channel_id=channel,
                            error=str(exc)[:120],
                            authenticated=bool(token),
                        ),
                        yt_chat_client,
                    )
                finally:
                    yt_chat_client._loop = None
                    self._close_thread_loop(loop)

            self._api._chat_thread = threading.Thread(
                target=run_youtube_chat, daemon=True
            )
            self._api._chat_thread.start()

        else:
            self._on_chat_status(
                ChatStatus(
                    connected=False,
                    platform=platform,
                    channel_id=channel,
                    error=f"Chat not supported for {platform}",
                )
            )

    async def _twitch_user_token(self) -> str | None:
        """Fresh Twitch *user* token for IRC; app tokens can't log into chat."""
        twitch = self._platforms.get("twitch")
        if twitch is None:
            return None
        token = await twitch._ensure_token()
        if twitch._platform_config().get("token_type") != "user":
            return None
        return token or None

    def stop_chat(self) -> None:
        client = self._api._chat_client
        self._api._chat_client = None
        self._api._chat_thread = None
        with self._echo_lock:
            self._pending_echoes.clear()
        if client is None:
            return
        # Before looking at client._loop: the chat thread may not have set it yet,
        # and a cancelled client refuses to start connect() later.
        client.cancel()
        loop = client._loop
        if loop is not None and not loop.is_closed():
            with contextlib.suppress(Exception):
                fut = asyncio.run_coroutine_threadsafe(client.disconnect(), loop)
                fut.result(timeout=3)

    # ── Send ────────────────────────────────────────────────────

    def send_chat(
        self,
        text: str,
        reply_to: str | None = None,
        reply_display: str | None = None,
        reply_body: str | None = None,
        request_id: str | None = None,
    ) -> None:
        def _send_unavailable(error: str) -> None:
            payload = json.dumps(
                {
                    "ok": False,
                    "platform": "",
                    "channel_id": "",
                    "message_id": None,
                    "error": error,
                    "request_id": request_id,
                    "text": text,
                    "reply_to_id": reply_to,
                    "reply_to_display": reply_display,
                    "reply_to_body": reply_body,
                }
            )
            self._eval_js(f"window.onChatSendResult({payload})")

        if not text:
            return
        if not self._api._chat_client:
            _send_unavailable("Chat is not connected.")
            return
        client = self._api._chat_client
        loop = client._loop
        if not loop or loop.is_closed():
            _send_unavailable("Chat connection is not ready yet.")
            return

        platform = client.platform
        conf = get_platform_config(self._config, platform)
        login = conf.get("user_login", "")
        display = conf.get("user_display_name", "") or login
        channel_id = getattr(client, "_channel", "") or ""

        def _do_send() -> None:
            # Twitch IRC never echoes our own PRIVMSG. Queue a local echo *before*
            # sending (USERSTATE can arrive before future.result() returns); it is
            # rendered on USERSTATE (accepted) and dropped on a rejection NOTICE.
            pending: _PendingEcho | None = None
            if platform == "twitch":
                pending = _PendingEcho(
                    client=client,
                    payload={
                        "channel_id": channel_id,
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
                    },
                )
                with self._echo_lock:
                    self._pending_echoes.append(pending)

            future = asyncio.run_coroutine_threadsafe(
                client.send_message(text, reply_to=reply_to), loop
            )
            try:
                result = future.result(timeout=5)
            except Exception as exc:
                logger.warning("Chat send failed for %s: %s", platform, exc)
                result = ChatSendResult(
                    ok=False,
                    platform=platform,
                    channel_id=channel_id,
                    error="Timed out while sending the chat message.",
                )

            if pending is not None and not result.ok:
                with self._echo_lock, contextlib.suppress(ValueError):
                    self._pending_echoes.remove(pending)
            send_result = json.dumps(
                {
                    "ok": result.ok,
                    "platform": result.platform,
                    "channel_id": result.channel_id,
                    "message_id": result.message_id,
                    "error": result.error,
                    "request_id": request_id,
                    "text": text,
                    "reply_to_id": reply_to,
                    "reply_to_display": reply_display,
                    "reply_to_body": reply_body,
                }
            )
            self._eval_js(f"window.onChatSendResult({send_result})")

        try:
            self._api._send_pool.submit(_do_send)
        except RuntimeError:
            _send_unavailable("Chat sender is shutting down.")

    # ── Persistence ──────────────────────────────────────────────

    def _emit_chat_mode_error(self, error: str) -> None:
        payload = json.dumps({"ok": False, "error": error})
        self._eval_js(f"window.onChatModeChanged({payload})")

    def set_chat_mode(self, mode: str, value: bool, slow_wait: int = 30) -> None:
        """Set a Twitch chat mode (slow_mode, emote_mode, subscriber_mode, follower_mode).

        Only works if the logged-in user is the broadcaster of the watched channel.
        """
        if mode not in _CHAT_MODES:
            logger.warning("set_chat_mode: unknown mode %r", mode)
            self._emit_chat_mode_error("Unknown chat mode")
            return
        twitch_conf = get_platform_config(self._config, "twitch")
        user_id = twitch_conf.get("user_id", "")
        if not user_id:
            self._emit_chat_mode_error("Not logged in to Twitch")
            return

        target = self._api._watching
        if target is None:
            self._emit_chat_mode_error("Not watching any channel")
            return
        if target.platform != "twitch":
            self._emit_chat_mode_error("Chat modes are Twitch-only")
            return

        def _do() -> None:
            loop = asyncio.new_event_loop()
            try:
                twitch = self._get_platform("twitch")
                kwargs: dict[str, Any] = {mode: bool(value)}
                if mode == "slow_mode" and value:
                    kwargs["slow_mode_wait_time"] = max(
                        _SLOW_WAIT_MIN, min(_SLOW_WAIT_MAX, int(slow_wait))
                    )
                settings = loop.run_until_complete(
                    twitch.set_chat_settings(
                        broadcaster_id=user_id,
                        moderator_id=user_id,
                        **kwargs,
                    )
                )
                payload = json.dumps(
                    {"ok": bool(settings), "mode": mode, "value": bool(value)}
                )
            except Exception as exc:
                logger.warning("set_chat_mode failed: %s", exc)
                payload = json.dumps({"ok": False, "error": str(exc)[:100]})
            finally:
                self._close_thread_loop(loop)
            self._eval_js(f"window.onChatModeChanged({payload})")

        self._run_in_thread(_do)

    def save_chat_width(self, width: int) -> None:
        clamped = max(250, min(500, width))

        def _apply(cfg: dict) -> None:
            cfg.get("settings", {})["chat_width"] = clamped

        self._config = update_config(_apply)

    def save_chat_visibility(self, visible: bool) -> None:
        def _apply(cfg: dict) -> None:
            cfg.get("settings", {})["chat_visible"] = visible

        self._config = update_config(_apply)

    def save_chat_block_list(self, words_json: str) -> None:
        try:
            words = json.loads(words_json)
            if not isinstance(words, list):
                return
        except (ValueError, TypeError):
            return

        def _apply(cfg: dict) -> None:
            cfg.get("settings", {})["chat_block_list"] = [
                str(w).strip().lower()[:50] for w in words[:100] if str(w).strip()
            ]

        self._config = update_config(_apply)

    # ── Callbacks ────────────────────────────────────────────────

    def _on_chat_message(self, msg: ChatMessage, source: Any = None) -> None:
        if source is not None and not self._is_current(source):
            return
        client = source if source is not None else self._api._chat_client
        channel_id = getattr(client, "_channel", None) or ""
        config = self._config
        platform_conf = get_platform_config(config, msg.platform)
        self_login = str(platform_conf.get("user_login", "")).strip().lower()
        is_self = bool(self_login and self_login == str(msg.author).strip().lower())
        data = json.dumps(
            {
                "channel_id": channel_id,
                "platform": msg.platform,
                "author": msg.author,
                "author_display": msg.author_display,
                "author_color": msg.author_color,
                "text": msg.text,
                "timestamp": msg.timestamp,
                "badges": [
                    {"name": b.name, "icon_url": b.icon_url} for b in msg.badges
                ],
                "emotes": _emotes_payload(msg.text, msg.emotes),
                "is_system": msg.is_system,
                "message_type": msg.message_type,
                "msg_id": msg.msg_id,
                "reply_to_id": msg.reply_to_id,
                "reply_to_display": msg.reply_to_display,
                "reply_to_body": msg.reply_to_body,
                "is_self": is_self,
            }
        )
        self._eval_js(f"window.onChatMessage({data})")

    def _on_chat_status(self, status: ChatStatus, source: Any = None) -> None:
        if source is not None and not self._is_current(source):
            return
        platform_conf = get_platform_config(self._config, status.platform)
        self_login = platform_conf.get("user_login", "")
        data = json.dumps(
            {
                "connected": status.connected,
                "connecting": False,
                "platform": status.platform,
                "channel_id": status.channel_id,
                "error": status.error,
                "authenticated": status.authenticated,
                "self_login": self_login,
            }
        )
        self._eval_js(f"window.onChatStatus({data})")

    def _pop_pending_echo(self, client: Any) -> _PendingEcho | None:
        """Oldest live pending echo of ``client``; stale entries are discarded."""
        now = time.monotonic()
        with self._echo_lock:
            while self._pending_echoes:
                entry = self._pending_echoes.popleft()
                if entry.client is client and now - entry.created <= _ECHO_TTL:
                    return entry
        return None

    def _on_userstate(self, tags: dict[str, str], source: Any) -> None:
        """Twitch accepted our PRIVMSG: render the queued local echo."""
        if not self._is_current(source):
            return
        entry = self._pop_pending_echo(source)
        if entry is None:
            return  # USERSTATE on JOIN, not a reply to our message
        payload = entry.payload
        if tags.get("color"):
            payload["author_color"] = tags["color"]
        if tags.get("display-name"):
            payload["author_display"] = tags["display-name"]
        payload["badges"] = [
            {"name": b.name, "icon_url": b.icon_url}
            for b in parse_badges(tags.get("badges", ""))
        ]
        self._eval_js(f"window.onChatMessage({json.dumps(payload)})")

    def _on_notice(self, msg_id: str, text: str, source: Any) -> None:
        """Twitch rejected our PRIVMSG (slow mode, followers-only, ...)."""
        if not self._is_current(source):
            return
        entry = self._pop_pending_echo(source)
        data = json.dumps(
            {
                "channel_id": getattr(source, "_channel", None) or "",
                "platform": getattr(source, "platform", "twitch"),
                "msg_id": msg_id,
                "text": text,
                "failed_text": entry.payload["text"] if entry else None,
            }
        )
        self._eval_js(f"window.onChatNotice({data})")
