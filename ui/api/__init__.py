from __future__ import annotations

import asyncio
import json
import logging
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from core.chats.kick_chat import KickChatClient
from core.chats.twitch_chat import TwitchChatClient
from core.chats.youtube_chat import YouTubeChatClient
from core.constants import WATCH_STATS_DB_NAME
from core.platforms.kick import KickClient
from core.platforms.twitch import TwitchClient
from core.platforms.youtube import YouTubeClient
from core.recorder import Recorder
from core.storage import (
    CONFIG_DIR,
    DEFAULT_SETTINGS,
    get_favorite_logins,
    get_platform_config,
    get_settings,
    load_config,
    update_config,
)
from core.watch_stats import WatchStatsDB

from .auth import AuthComponent
from .chat import ChatComponent
from .data import DataComponent, _aggregate_categories  # noqa: F401
from .favorites import FavoritesComponent
from .images import ImagesComponent
from .streams import StreamsComponent

logger = logging.getLogger(__name__)

_ACCENT_PALETTE = {
    "#FF9F0A",
    "#BF5AF2",
    "#0A84FF",
    "#30D158",
    "#FF453A",
    "#FF2D55",
}


class TwitchXApi:
    """Python↔JS bridge. Orchestrates sub-components, owns shared state.

    Each sub-component handles one domain:
        AuthComponent       — OAuth login/logout for all platforms
        FavoritesComponent  — channel management, search, import
        DataComponent       — polling, refresh, browse, channel profiles
        StreamsComponent    — video playback (native, external, multistream)
        ChatComponent       — chat connection and message sending
        ImagesComponent     — avatar and thumbnail fetching
    """

    def __init__(self) -> None:
        # ─── Shared state owned by the orchestrator ───
        self._window: Any = None
        self._config = load_config()
        self._twitch = TwitchClient()
        self._kick = KickClient()
        self._youtube = YouTubeClient()
        self._platforms: dict[str, Any] = {
            "twitch": self._twitch,
            "kick": self._kick,
            "youtube": self._youtube,
        }
        self._active_platform: str = "twitch"
        self._shutdown = threading.Event()
        self._fetch_lock = threading.Lock()
        self._poll_lock = threading.Lock()
        self._polling_timer: threading.Timer | None = None
        self._poll_generation = 0
        self._live_streams: list[dict[str, Any]] = []
        self._games: dict[str, str] = {}
        self._prev_live_logins: set[str] = set()
        self._first_fetch_done = False
        self._watching_channel: str | None = None
        self._selected_channel: str | None = None
        self._current_user: dict[str, Any] | None = None
        self._launch_timer: threading.Timer | None = None
        self._launch_elapsed = 0
        self._launch_channel: str | None = None
        self._launch_id = 0
        self._last_successful_fetch: float = 0
        self._last_youtube_fetch: float = 0
        self._last_youtube_streams: list[dict[str, Any]] = []
        self._last_twitch_streams: list[dict[str, Any]] = []
        self._last_twitch_users: list[dict[str, Any]] = []
        self._last_kick_streams: list[dict[str, Any]] = []
        self._user_avatars: dict[str, str] = {}
        self._fetching_avatars: set[str] = set()
        self._fetching_thumbnails: set[str] = set()
        self._http = httpx.Client(timeout=10, limits=httpx.Limits(max_connections=20))
        self._image_pool = ThreadPoolExecutor(
            max_workers=8, thread_name_prefix="twitchx-img"
        )
        self._send_pool = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="twitchx-send"
        )
        self._chat_client: TwitchChatClient | KickChatClient | YouTubeChatClient | None = None
        self._chat_thread: threading.Thread | None = None
        self._watch_stats = WatchStatsDB(str(CONFIG_DIR / WATCH_STATS_DB_NAME))
        self._recorder = Recorder()
        self._active_watch_session: int | None = None
        self._active_watch_lock = threading.Lock()
        threading.Thread(
            target=self._watch_stats.cleanup_old_sessions,
            daemon=True,
        ).start()

        # Restore user profile if logged in
        twitch_conf = get_platform_config(self._config, "twitch")
        if twitch_conf.get("user_id") and twitch_conf.get("user_login"):
            self._current_user = {
                "id": twitch_conf["user_id"],
                "login": twitch_conf["user_login"],
                "display_name": twitch_conf.get("user_display_name", ""),
            }

        # ─── Sub-components ───
        self._auth = AuthComponent(self)
        self._favorites = FavoritesComponent(self)
        self._data = DataComponent(self)
        self._streams = StreamsComponent(self)
        self._chat = ChatComponent(self)
        self._images = ImagesComponent(self)

    # ─── Backward-compatible method delegation (accessed by tests) ───

    def _fetch_data(self, *args: Any, **kwargs: Any) -> None:
        self._data._fetch_data(*args, **kwargs)

    def _on_chat_message(self, msg: Any) -> None:
        self._chat._on_chat_message(msg)

    # ─── Delegate to sub-components ──────────────────────────

    # Auth
    def login(self) -> None:
        self._auth.login()

    def logout(self) -> None:
        self._auth.logout()

    def kick_login(self, client_id: str = "", client_secret: str = "") -> None:
        self._auth.kick_login(client_id, client_secret)

    def kick_logout(self) -> None:
        self._auth.kick_logout()

    def youtube_login(self, client_id: str = "", client_secret: str = "") -> None:
        self._auth.youtube_login(client_id, client_secret)

    def youtube_logout(self) -> None:
        self._auth.youtube_logout()

    def test_connection(self, client_id: str, client_secret: str) -> None:
        self._auth.test_connection(client_id, client_secret)

    def kick_test_connection(self, client_id: str, client_secret: str) -> None:
        self._auth.kick_test_connection(client_id, client_secret)

    def youtube_test_connection(self, api_key: str = "") -> None:
        self._auth.youtube_test_connection(api_key)

    # Favorites
    def add_channel(
        self, username: str, platform: str = "twitch", display_name: str = ""
    ) -> None:
        self._favorites.add_channel(username, platform, display_name)

    def remove_channel(self, channel: str, platform: str = "twitch") -> None:
        self._favorites.remove_channel(channel, platform)

    def reorder_channels(self, new_order_json: str, platform: str = "twitch") -> None:
        self._favorites.reorder_channels(new_order_json, platform)

    def import_follows(self) -> None:
        self._favorites.import_follows()

    def youtube_import_follows(self) -> None:
        self._favorites.youtube_import_follows()

    def search_channels(self, query: str, platform: str = "twitch") -> None:
        self._favorites.search_channels(query, platform)

    # Data
    def refresh(self) -> None:
        self._data.refresh()

    def start_polling(self, interval_seconds: int = 60) -> None:
        self._data.start_polling(interval_seconds)

    def stop_polling(self) -> None:
        self._data.stop_polling()

    def get_browse_categories(self, platform_filter: str = "all") -> None:
        self._data.get_browse_categories(platform_filter)

    def get_browse_top_streams(
        self,
        category_name: str,
        platform_ids: dict[str, str],
        platform_filter: str = "all",
    ) -> None:
        self._data.get_browse_top_streams(category_name, platform_ids, platform_filter)

    def get_channel_profile(self, login: str, platform: str = "twitch") -> None:
        self._data.get_channel_profile(login, platform)

    def get_channel_media(
        self,
        login: str,
        platform: str = "twitch",
        tab: str = "vods",
    ) -> None:
        self._data.get_channel_media(login, platform, tab)

    # Streams
    def watch(self, channel: str, quality: str) -> None:
        self._streams.watch(channel, quality)

    def watch_direct(self, channel: str, platform: str, quality: str) -> None:
        self._streams.watch_direct(channel, platform, quality)

    def watch_external(self, channel: str, quality: str) -> None:
        self._streams.watch_external(channel, quality)

    def watch_media(
        self,
        url: str,
        quality: str,
        platform: str = "twitch",
        channel: str = "",
        title: str = "",
        with_chat: bool = False,
    ) -> None:
        self._streams.watch_media(url, quality, platform, channel, title, with_chat)

    def stop_player(self) -> None:
        self._streams.stop_player()

    def add_multi_slot(
        self, slot_idx: int, channel: str, platform: str, quality: str
    ) -> None:
        self._streams.add_multi_slot(slot_idx, channel, platform, quality)

    def stop_multi(self) -> None:
        self._streams.stop_multi()

    def start_recording(self) -> None:
        self._streams.start_recording()

    def stop_recording(self) -> None:
        self._streams.stop_recording()

    # Chat
    def start_chat(self, channel: str, platform: str = "twitch") -> None:
        self._chat.start_chat(channel, platform)

    def stop_chat(self) -> None:
        self._chat.stop_chat()

    def send_chat(
        self,
        text: str,
        reply_to: str | None = None,
        reply_display: str | None = None,
        reply_body: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self._chat.send_chat(text, reply_to, reply_display, reply_body, request_id)

    def save_chat_width(self, width: int) -> None:
        self._chat.save_chat_width(width)

    def save_chat_visibility(self, visible: bool) -> None:
        self._chat.save_chat_visibility(visible)

    def save_chat_block_list(self, words_json: str) -> None:
        self._chat.save_chat_block_list(words_json)

    def set_chat_mode(self, mode: str, value: bool, slow_wait: int = 30) -> None:
        self._chat.set_chat_mode(mode, value, slow_wait)

    # Images
    def get_avatar(self, login: str, platform: str = "twitch") -> None:
        self._images.get_avatar(login, platform)

    def get_thumbnail(self, login: str, url: str) -> None:
        self._images.get_thumbnail(login, url)

    # Watch Statistics
    def get_watch_statistics(self, period: str = "today") -> str:
        return json.dumps(self._watch_stats.get_stats_for_period(period))

    def get_watch_history(self, limit: int = 20) -> str:
        return json.dumps(self._watch_stats.get_recent_sessions(limit))

    # ─── Config methods (stay in orchestrator) ─────────────────

    def get_config(self) -> dict[str, Any]:
        self._config = load_config()
        twitch_conf = get_platform_config(self._config, "twitch")
        kick_conf = get_platform_config(self._config, "kick")
        yt_conf = get_platform_config(self._config, "youtube")
        settings = get_settings(self._config)
        all_favs = (
            get_favorite_logins(self._config, "twitch")
            + get_favorite_logins(self._config, "kick")
            + get_favorite_logins(self._config, "youtube")
        )
        masked = {
            "client_id": twitch_conf.get("client_id", "")[:8] + "..."
            if twitch_conf.get("client_id")
            else "",
            "has_credentials": bool(
                (twitch_conf.get("client_id") and twitch_conf.get("client_secret"))
                or (kick_conf.get("client_id") and kick_conf.get("client_secret"))
                or (yt_conf.get("api_key"))
            ),
            "quality": settings.get("quality", "best"),
            "refresh_interval": settings.get("refresh_interval", 60),
            "favorites": all_favs,
        }
        if self._current_user:
            masked["current_user"] = self._current_user
        masked["kick_has_credentials"] = bool(
            kick_conf.get("client_id") and kick_conf.get("client_secret")
        )
        if kick_conf.get("user_login") or kick_conf.get("user_display_name"):
            masked["kick_user"] = {
                "login": kick_conf.get("user_login", ""),
                "display_name": kick_conf.get(
                    "user_display_name", kick_conf.get("user_login", "")
                ),
            }
        masked["kick_scopes"] = kick_conf.get("oauth_scopes", "")
        masked["youtube_has_credentials"] = bool(yt_conf.get("api_key"))
        masked["youtube_has_oauth"] = bool(
            yt_conf.get("client_id") and yt_conf.get("client_secret")
        )
        if yt_conf.get("user_login") or yt_conf.get("user_display_name"):
            masked["youtube_user"] = {
                "login": yt_conf.get("user_login", ""),
                "display_name": yt_conf.get(
                    "user_display_name", yt_conf.get("user_login", "")
                ),
            }
        masked["youtube_quota_remaining"] = self._youtube.quota_remaining()
        _st = get_settings(self._config)
        masked["pip_enabled"] = _st.get("pip_enabled", False)
        masked["keyboard_shortcuts"] = _st.get("keyboard_shortcuts", {})
        return masked

    def get_full_config_for_settings(self) -> dict[str, Any]:
        self._config = load_config()
        twitch_conf = get_platform_config(self._config, "twitch")
        kick_conf = get_platform_config(self._config, "kick")
        yt_conf = get_platform_config(self._config, "youtube")
        settings = get_settings(self._config)
        return {
            "client_id": twitch_conf.get("client_id", ""),
            "client_secret": twitch_conf.get("client_secret", ""),
            "quality": settings.get("quality", "best"),
            "refresh_interval": settings.get("refresh_interval", 60),
            "streamlink_path": settings.get("streamlink_path", "streamlink"),
            "iina_path": settings.get("iina_path", ""),
            "external_player": settings.get("external_player", "iina"),
            "mpv_path": settings.get("mpv_path", ""),
            "recording_path": settings.get("recording_path", ""),
            "kick_client_id": kick_conf.get("client_id", ""),
            "kick_client_secret": kick_conf.get("client_secret", ""),
            "chat_visible": settings.get("chat_visible", True),
            "chat_width": settings.get("chat_width", 340),
            "kick_display_name": kick_conf.get("user_display_name", ""),
            "kick_user_login": kick_conf.get("user_login", ""),
            "kick_scopes": kick_conf.get("oauth_scopes", ""),
            "youtube_api_key": yt_conf.get("api_key", ""),
            "youtube_client_id": yt_conf.get("client_id", ""),
            "youtube_client_secret": yt_conf.get("client_secret", ""),
            "youtube_display_name": yt_conf.get("user_display_name", ""),
            "youtube_user_login": yt_conf.get("user_login", ""),
            "youtube_quota_remaining": self._youtube.quota_remaining(),
            "pip_enabled": settings.get("pip_enabled", False),
            "low_latency_mode": settings.get("low_latency_mode", False),
            "chat_filter_sub_only": settings.get("chat_filter_sub_only", False),
            "chat_filter_mod_only": settings.get("chat_filter_mod_only", False),
            "chat_block_list": settings.get("chat_block_list", []),
            "chat_anti_spam": settings.get("chat_anti_spam", True),
            "keyboard_shortcuts": settings.get("keyboard_shortcuts", {}),
            "accent_color": settings.get("accent_color", "#FF9F0A"),
        }

    def save_settings(self, data: str) -> None:
        parsed = json.loads(data) if isinstance(data, str) else data

        def _apply(cfg: dict) -> None:
            tc = cfg.get("platforms", {}).get("twitch", {})
            st = cfg.get("settings", {})
            if "client_id" in parsed:
                tc["client_id"] = parsed["client_id"].strip()
            if "client_secret" in parsed:
                tc["client_secret"] = parsed["client_secret"].strip()
            if "quality" in parsed:
                st["quality"] = parsed["quality"]
            if "refresh_interval" in parsed:
                st["refresh_interval"] = int(parsed["refresh_interval"])
            if "streamlink_path" in parsed:
                st["streamlink_path"] = parsed["streamlink_path"].strip()
            if "iina_path" in parsed:
                st["iina_path"] = parsed["iina_path"].strip()
            if "external_player" in parsed and parsed["external_player"] in ("iina", "mpv"):
                st["external_player"] = parsed["external_player"]
            if "mpv_path" in parsed:
                st["mpv_path"] = parsed["mpv_path"].strip()
            if "recording_path" in parsed:
                st["recording_path"] = parsed["recording_path"].strip()
            kc = cfg.get("platforms", {}).get("kick", {})
            if "kick_client_id" in parsed:
                kc["client_id"] = parsed["kick_client_id"].strip()
            if "kick_client_secret" in parsed:
                kc["client_secret"] = parsed["kick_client_secret"].strip()
            yc = cfg.get("platforms", {}).get("youtube", {})
            if "youtube_api_key" in parsed:
                yc["api_key"] = parsed["youtube_api_key"].strip()
            if "youtube_client_id" in parsed:
                yc["client_id"] = parsed["youtube_client_id"].strip()
            if "youtube_client_secret" in parsed:
                yc["client_secret"] = parsed["youtube_client_secret"].strip()
            if "pip_enabled" in parsed:
                st["pip_enabled"] = bool(parsed["pip_enabled"])
            if "low_latency_mode" in parsed:
                st["low_latency_mode"] = bool(parsed["low_latency_mode"])
            if "chat_filter_sub_only" in parsed:
                st["chat_filter_sub_only"] = bool(parsed["chat_filter_sub_only"])
            if "chat_filter_mod_only" in parsed:
                st["chat_filter_mod_only"] = bool(parsed["chat_filter_mod_only"])
            if "chat_block_list" in parsed and isinstance(parsed["chat_block_list"], list):
                st["chat_block_list"] = [str(w)[:50] for w in parsed["chat_block_list"][:100]]
            if "chat_anti_spam" in parsed:
                st["chat_anti_spam"] = bool(parsed["chat_anti_spam"])
            if "keyboard_shortcuts" in parsed and isinstance(
                parsed["keyboard_shortcuts"], dict
            ):
                known = set(DEFAULT_SETTINGS.get("keyboard_shortcuts", {}).keys())
                validated = {
                    k: v
                    for k, v in parsed["keyboard_shortcuts"].items()
                    if k in known and isinstance(v, str) and 0 < len(v) <= 50
                }
                st["keyboard_shortcuts"] = validated
            if "accent_color" in parsed and parsed["accent_color"] in _ACCENT_PALETTE:
                st["accent_color"] = parsed["accent_color"]

        self._config = update_config(_apply)

        interval = get_settings(self._config).get("refresh_interval", 60)
        self.start_polling(interval)
        self._eval_js("window.onSettingsSaved()")

    # ─── Browser / URL ───────────────────────────────────────

    def open_browser(self, channel: str, platform: str = "twitch") -> None:
        if channel:
            if platform == "kick":
                webbrowser.open(f"https://kick.com/{channel}")
            elif platform == "youtube":
                webbrowser.open(f"https://youtube.com/channel/{channel}")
            else:
                webbrowser.open(f"https://twitch.tv/{channel}")

    def open_url(self, url: str) -> None:
        if url:
            webbrowser.open(url)

    # ─── Shared infrastructure (used by components) ────────────

    def _eval_js(self, code: str) -> None:
        if self._shutdown.is_set() or self._window is None:
            return
        try:
            self._window.evaluate_js(code)
        except Exception as e:
            logger.debug("_eval_js failed: %s", e, exc_info=True)

    def _run_in_thread(self, fn: Any) -> None:
        threading.Thread(target=fn, daemon=True).start()

    def _get_platform(self, platform_id: str) -> Any:
        return self._platforms.get(platform_id)

    def _get_twitch_config(self) -> dict[str, Any]:
        return get_platform_config(self._config, "twitch")

    def _get_kick_config(self) -> dict[str, Any]:
        return get_platform_config(self._config, "kick")

    def _get_youtube_config(self) -> dict[str, Any]:
        return get_platform_config(self._config, "youtube")

    def _close_thread_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        try:
            asyncio.set_event_loop(loop)
            for client in self._platforms.values():
                loop.run_until_complete(client.close_loop_resources())
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    # ─── Static helpers shared across components ──────────────

    @staticmethod
    def _parse_scopes(raw: str) -> set[str]:
        return {part.strip() for part in raw.split() if part.strip()}

    # ─── Lifecycle ───────────────────────────────────────────

    def set_window(self, window: Any) -> None:
        self._window = window

    def close(self) -> None:
        self._recorder.stop()
        self._streams._end_watch_session()
        self.stop_chat()
        self._shutdown.set()
        self.stop_polling()
        self._streams._cancel_launch_timer()
        self._image_pool.shutdown(wait=False)
        self._send_pool.shutdown(wait=False)
        self._http.close()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            for client in self._platforms.values():
                loop.run_until_complete(client.close())
        finally:
            asyncio.set_event_loop(None)
            loop.close()
