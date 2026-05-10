from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
from typing import Any

from core.chat import ChatMessage, ChatSendResult, ChatStatus
from core.chats.kick_chat import KickChatClient
from core.chats.twitch_chat import TwitchChatClient
from core.chats.youtube_chat import YouTubeChatClient
from core.storage import CONFIG_DIR, get_platform_config, update_config
from core.third_party_emotes import fetch_channel_emotes

from ._base import BaseApiComponent

logger = logging.getLogger(__name__)


class ChatComponent(BaseApiComponent):
    """Chat connection, message sending, and callbacks."""

    # ── Start / Stop ────────────────────────────────────────────

    def start_chat(self, channel: str, platform: str = "twitch", live_chat_id: str | None = None) -> None:
        self.stop_chat()

        if platform == "twitch":
            twitch_conf = get_platform_config(self._config, "twitch")
            token = twitch_conf.get("access_token") or None
            login = twitch_conf.get("user_login") or None

            twitch_client = TwitchChatClient()
            twitch_client.on_message(self._on_chat_message)
            twitch_client.on_status(self._on_chat_status)

            def _on_user_list(users: list[str]) -> None:
                payload = json.dumps({"count": len(users), "users": users[:500]})
                self._eval_js(f"window.onChatUserList({payload})")

            if hasattr(twitch_client, "on_user_list"):
                twitch_client.on_user_list(_on_user_list)  # type: ignore[arg-type]

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
                        )
                    )
                finally:
                    twitch_client._loop = None
                    loop.close()

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
                            users = emote_loop.run_until_complete(twitch_client_ref.get_users([channel]))
                            if users:
                                twitch_user_id = str(users[0].get("id", ""))
                        except Exception:
                            pass
                        finally:
                            emote_loop.close()
                    cache_dir = str(CONFIG_DIR / "emotes")
                    emote_map = fetch_channel_emotes(channel, twitch_user_id, cache_dir)
                    if emote_map and not self._shutdown.is_set():
                        payload = json.dumps({"channel": channel, "emotes": emote_map})
                        self._eval_js(f"window.onThirdPartyEmotes({payload})")
                except Exception:
                    pass

            threading.Thread(target=_fetch_emotes, daemon=True).start()

        elif platform == "kick":
            kick_conf = get_platform_config(self._config, "kick")
            token = kick_conf.get("access_token") or None
            scopes = self._api._parse_scopes(kick_conf.get("oauth_scopes", ""))

            kick_chat_client = KickChatClient()
            kick_chat_client.on_message(self._on_chat_message)
            kick_chat_client.on_status(self._on_chat_status)
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
                            )
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
                    self._on_chat_status(
                        ChatStatus(
                            connected=False,
                            platform="kick",
                            channel_id=channel,
                            error=str(exc)[:120] or "Kick chat failed",
                        )
                    )
                finally:
                    kick_chat_client._loop = None
                    loop.close()

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
            yt_chat_client.on_message(self._on_chat_message)
            yt_chat_client.on_status(self._on_chat_status)
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
                        )
                    )
                finally:
                    yt_chat_client._loop = None
                    loop.close()

            self._api._chat_thread = threading.Thread(target=run_youtube_chat, daemon=True)
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

    def stop_chat(self) -> None:
        client = self._api._chat_client
        self._api._chat_client = None
        self._api._chat_thread = None
        if client is None:
            return
        client._running = False
        loop = client._loop
        if loop is not None:
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
        if not self._api._chat_client or not text:
            return
        client = self._api._chat_client
        loop = client._loop
        if not loop or loop.is_closed():
            return

        platform = client.platform
        conf = get_platform_config(self._config, platform)
        login = conf.get("user_login", "")
        display = conf.get("user_display_name", "") or login
        channel_id = getattr(client, "_channel", "") or ""

        def _do_send() -> None:
            future = asyncio.run_coroutine_threadsafe(
                client.send_message(text, reply_to=reply_to), loop
            )
            try:
                result = future.result(timeout=5)
            except Exception:
                result = ChatSendResult(
                    ok=False,
                    platform=platform,
                    channel_id=channel_id,
                    error="Timed out while sending the chat message.",
                )

            if result.ok and platform == "twitch":
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
                        "msg_id": result.message_id,
                        "reply_to_id": reply_to,
                        "reply_to_display": reply_display,
                        "reply_to_body": reply_body,
                        "is_self": True,
                    }
                )
                self._eval_js(f"window.onChatMessage({echo})")
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

        with contextlib.suppress(RuntimeError):
            self._api._send_pool.submit(_do_send)

    # ── Persistence ──────────────────────────────────────────────

    def set_chat_mode(self, mode: str, value: bool, slow_wait: int = 30) -> None:
        """Set a Twitch chat mode (slow_mode, emote_mode, subscriber_mode, follower_mode).

        Only works if the logged-in user is the broadcaster of the watched channel.
        """
        twitch_conf = get_platform_config(self._config, "twitch")
        user_id = twitch_conf.get("user_id", "")
        if not user_id:
            self._eval_js("window.onChatModeChanged({ok: false, error: 'Not logged in to Twitch'})")
            return

        channel = self._api._watching_channel
        if not channel:
            self._eval_js("window.onChatModeChanged({ok: false, error: 'Not watching any channel'})")
            return

        def _do() -> None:
            loop = asyncio.new_event_loop()
            try:
                twitch = self._get_platform("twitch")
                kwargs: dict[str, Any] = {mode: value}
                if mode == "slow_mode" and value:
                    kwargs["slow_mode_wait_time"] = slow_wait
                ok = loop.run_until_complete(
                    twitch.set_chat_settings(
                        broadcaster_id=user_id,
                        moderator_id=user_id,
                        **kwargs,
                    )
                )
                payload = json.dumps({"ok": ok, "mode": mode, "value": value})
            except Exception as exc:
                payload = json.dumps({"ok": False, "error": str(exc)[:100]})
            finally:
                loop.close()
            self._eval_js(f"window.onChatModeChanged({payload})")

        threading.Thread(target=_do, daemon=True).start()

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

    def _on_chat_message(self, msg: ChatMessage) -> None:
        config = self._config
        platform_conf = get_platform_config(config, msg.platform)
        self_login = str(platform_conf.get("user_login", "")).strip().lower()
        is_self = bool(self_login and self_login == str(msg.author).strip().lower())
        data = json.dumps(
            {
                "platform": msg.platform,
                "author": msg.author,
                "author_display": msg.author_display,
                "author_color": msg.author_color,
                "text": msg.text,
                "timestamp": msg.timestamp,
                "badges": [
                    {"name": b.name, "icon_url": b.icon_url} for b in msg.badges
                ],
                "emotes": [
                    {"code": e.code, "url": e.url, "start": e.start, "end": e.end}
                    for e in msg.emotes
                ],
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

    def _on_chat_status(self, status: ChatStatus) -> None:
        platform_conf = get_platform_config(self._config, status.platform)
        self_login = platform_conf.get("user_login", "")
        data = json.dumps(
            {
                "connected": status.connected,
                "platform": status.platform,
                "channel_id": status.channel_id,
                "error": status.error,
                "authenticated": status.authenticated,
                "self_login": self_login,
            }
        )
        self._eval_js(f"window.onChatStatus({data})")
