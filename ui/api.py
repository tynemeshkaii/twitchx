from __future__ import annotations

import asyncio
import base64
import contextlib
import io
import json
import logging
import re
import subprocess
import threading
import time
import traceback
import webbrowser
from datetime import datetime
from typing import Any

import httpx
from PIL import Image

from core.launcher import launch_stream
from core.oauth_server import wait_for_oauth_code
from core.platforms.twitch import TwitchClient
from core.storage import (
    get_cached_avatar,
    get_favorite_logins,
    get_platform_config,
    get_settings,
    load_config,
    save_avatar,
    save_config,
)
from core.stream_resolver import resolve_hls_url
from core.utils import format_viewers

logger = logging.getLogger(__name__)


class TwitchXApi:
    """Python↔JS bridge exposed to pywebview as the js_api object."""

    def __init__(self) -> None:
        self._window: Any = None
        self._config = load_config()
        self._twitch = TwitchClient()
        self._platforms: dict[str, Any] = {"twitch": self._twitch}
        self._active_platform: str = "twitch"
        self._shutdown = threading.Event()
        self._fetching = False
        self._polling_timer: threading.Timer | None = None
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
        self._last_successful_fetch: float = 0
        # User avatar URLs for lazy loading
        self._user_avatars: dict[str, str] = {}

        # Restore user profile if logged in
        twitch_conf = get_platform_config(self._config, "twitch")
        if twitch_conf.get("user_id") and twitch_conf.get("user_login"):
            self._current_user = {
                "id": twitch_conf["user_id"],
                "login": twitch_conf["user_login"],
                "display_name": twitch_conf.get("user_display_name", ""),
            }

    def set_window(self, window: Any) -> None:
        self._window = window

    def _eval_js(self, code: str) -> None:
        """Safely evaluate JS in the webview window."""
        if self._shutdown.is_set() or self._window is None:
            return
        with contextlib.suppress(Exception):
            self._window.evaluate_js(code)

    def _run_in_thread(self, fn: Any) -> None:
        threading.Thread(target=fn, daemon=True).start()

    def _get_platform(self, platform_id: str) -> Any:
        """Get a platform client by ID."""
        return self._platforms.get(platform_id)

    def _get_twitch_config(self) -> dict[str, Any]:
        """Get Twitch platform config section."""
        return get_platform_config(self._config, "twitch")

    def _close_thread_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._twitch.close_loop_resources())
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    @staticmethod
    def _sanitize_username(raw: str) -> str:
        raw = raw.strip()
        match = re.search(r"(?:twitch\.tv/)([A-Za-z0-9_]+)", raw)
        if match:
            return match.group(1).lower()
        return re.sub(r"[^A-Za-z0-9_]", "", raw).lower()

    # ── Config ──────────────────────────────────────────────────

    def get_config(self) -> dict[str, Any]:
        self._config = load_config()
        twitch_conf = get_platform_config(self._config, "twitch")
        settings = get_settings(self._config)
        masked = {
            "client_id": twitch_conf.get("client_id", "")[:8] + "..." if twitch_conf.get("client_id") else "",
            "has_credentials": bool(twitch_conf.get("client_id") and twitch_conf.get("client_secret")),
            "quality": settings.get("quality", "best"),
            "refresh_interval": settings.get("refresh_interval", 60),
            "favorites": get_favorite_logins(self._config, "twitch"),
        }
        if self._current_user:
            masked["current_user"] = self._current_user
        return masked

    def get_full_config_for_settings(self) -> dict[str, Any]:
        """Return config including secret for the settings dialog."""
        self._config = load_config()
        twitch_conf = get_platform_config(self._config, "twitch")
        settings = get_settings(self._config)
        return {
            "client_id": twitch_conf.get("client_id", ""),
            "client_secret": twitch_conf.get("client_secret", ""),
            "quality": settings.get("quality", "best"),
            "refresh_interval": settings.get("refresh_interval", 60),
            "streamlink_path": settings.get("streamlink_path", "streamlink"),
            "iina_path": settings.get("iina_path", ""),
        }

    def save_settings(self, data: str) -> None:
        """Save settings from JS. data is JSON string."""
        parsed = json.loads(data) if isinstance(data, str) else data
        twitch_conf = get_platform_config(self._config, "twitch")
        settings = get_settings(self._config)

        if "client_id" in parsed:
            twitch_conf["client_id"] = parsed["client_id"].strip()
        if "client_secret" in parsed:
            twitch_conf["client_secret"] = parsed["client_secret"].strip()
        if "quality" in parsed:
            settings["quality"] = parsed["quality"]
        if "refresh_interval" in parsed:
            settings["refresh_interval"] = int(parsed["refresh_interval"])
        if "streamlink_path" in parsed:
            settings["streamlink_path"] = parsed["streamlink_path"].strip()
        if "iina_path" in parsed:
            settings["iina_path"] = parsed["iina_path"].strip()

        self._config["platforms"]["twitch"] = twitch_conf
        self._config["settings"] = settings
        save_config(self._config)

        interval = settings.get("refresh_interval", 60)
        self.start_polling(interval)
        self._eval_js("window.onSettingsSaved()")

    def test_connection(self, client_id: str, client_secret: str) -> None:
        def do_test() -> None:
            try:
                resp = httpx.post(
                    "https://id.twitch.tv/oauth2/token",
                    data={
                        "client_id": client_id.strip(),
                        "client_secret": client_secret.strip(),
                        "grant_type": "client_credentials",
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    result = json.dumps({"success": True, "message": "Connected"})
                else:
                    result = json.dumps(
                        {"success": False, "message": "Invalid credentials"}
                    )
            except httpx.ConnectError:
                result = json.dumps(
                    {"success": False, "message": "No internet connection"}
                )
            except Exception as exc:
                msg = str(exc)[:60]
                result = json.dumps({"success": False, "message": msg})
            self._eval_js(f"window.onTestResult({result})")

        self._run_in_thread(do_test)

    # ── Auth ────────────────────────────────────────────────────

    def login(self) -> None:
        twitch_conf = self._get_twitch_config()
        if not twitch_conf.get("client_id") or not twitch_conf.get("client_secret"):
            self._eval_js(
                'window.onLoginError("Set API credentials in Settings first")'
            )
            return
        auth_url = self._twitch.get_auth_url()
        self._eval_js(
            "window.onStatusUpdate({text: 'Waiting for Twitch login...', type: 'warn'})"
        )

        def do_login() -> None:
            webbrowser.open(auth_url)
            code = wait_for_oauth_code()
            if self._shutdown.is_set():
                return
            if code is None:
                self._eval_js('window.onLoginError("Login timed out")')
                return
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                token_data = loop.run_until_complete(self._twitch.exchange_code(code))
                twitch_conf = self._config["platforms"]["twitch"]
                twitch_conf["access_token"] = token_data["access_token"]
                twitch_conf["refresh_token"] = token_data.get("refresh_token", "")
                twitch_conf["token_expires_at"] = int(time.time()) + token_data.get(
                    "expires_in", 3600
                )
                twitch_conf["token_type"] = "user"
                save_config(self._config)

                user = loop.run_until_complete(self._twitch.get_current_user())
                twitch_conf["user_id"] = user["id"]
                twitch_conf["user_login"] = user["login"]
                twitch_conf["user_display_name"] = user.get(
                    "display_name", user["login"]
                )
                save_config(self._config)

                self._current_user = user
                avatar_url = user.get("profile_image_url", "")
                result = json.dumps(
                    {
                        "display_name": user.get("display_name", user["login"]),
                        "login": user["login"],
                        "avatar_url": avatar_url,
                    }
                )
                self._eval_js(f"window.onLoginComplete({result})")
                # Load avatar
                if avatar_url:
                    self.get_avatar(user["login"].lower())
                # Trigger refresh
                self.refresh()
            except Exception as e:
                msg = str(e)[:80] if str(e) else "Login failed"
                safe_msg = json.dumps(msg)
                self._eval_js(f"window.onLoginError({safe_msg})")
            finally:
                self._close_thread_loop(loop)

        self._run_in_thread(do_login)

    def logout(self) -> None:
        twitch_conf = self._config["platforms"]["twitch"]
        twitch_conf["access_token"] = ""
        twitch_conf["refresh_token"] = ""
        twitch_conf["token_expires_at"] = 0
        twitch_conf["token_type"] = "app"
        twitch_conf["user_id"] = ""
        twitch_conf["user_login"] = ""
        twitch_conf["user_display_name"] = ""
        save_config(self._config)
        self._current_user = None
        self._eval_js("window.onLogout()")

    def import_follows(self) -> None:
        if not self._current_user:
            self._eval_js('window.onImportError("Not logged in")')
            return
        twitch_conf = self._get_twitch_config()
        user_id = self._current_user.get("id", twitch_conf.get("user_id", ""))
        if not user_id:
            self._eval_js('window.onImportError("No user ID")')
            return
        self._eval_js(
            "window.onStatusUpdate({text: 'Importing followed channels...', type: 'warn'})"
        )

        def do_import() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                logins = loop.run_until_complete(
                    self._twitch.get_followed_channels(user_id)
                )
                existing_logins = {
                    f["login"]
                    for f in self._config.get("favorites", [])
                    if f.get("platform") == "twitch"
                }
                added = 0
                for login in logins:
                    if login.lower() not in existing_logins:
                        self._config["favorites"].append(
                            {"platform": "twitch", "login": login.lower(), "display_name": login}
                        )
                        existing_logins.add(login.lower())
                        added += 1
                save_config(self._config)
                result = json.dumps({"added": added})
                self._eval_js(f"window.onImportComplete({result})")
                self.refresh()
            except Exception as e:
                msg = str(e)[:80] if str(e) else "Import failed"
                safe_msg = json.dumps(msg)
                self._eval_js(f"window.onImportError({safe_msg})")
            finally:
                self._close_thread_loop(loop)

        self._run_in_thread(do_import)

    # ── Channels ────────────────────────────────────────────────

    def add_channel(self, username: str) -> None:
        clean = self._sanitize_username(username)
        if not clean:
            return
        favorites = self._config.get("favorites", [])
        if any(f.get("login") == clean and f.get("platform") == "twitch" for f in favorites):
            return
        favorites.append({"platform": "twitch", "login": clean, "display_name": clean})
        self._config["favorites"] = favorites
        save_config(self._config)
        self.refresh()

    def remove_channel(self, channel: str) -> None:
        favorites = self._config.get("favorites", [])
        self._config["favorites"] = [
            f for f in favorites
            if not (f.get("login") == channel.lower() and f.get("platform") == "twitch")
        ]
        save_config(self._config)
        self.refresh()

    def reorder_channels(self, new_order_json: str) -> None:
        new_order = json.loads(new_order_json) if isinstance(new_order_json, str) else new_order_json
        old_favs = {f["login"]: f for f in self._config.get("favorites", []) if f.get("platform") == "twitch"}
        reordered = []
        for login in new_order:
            if login in old_favs:
                reordered.append(old_favs[login])
            else:
                reordered.append({"platform": "twitch", "login": login, "display_name": login})
        non_twitch = [f for f in self._config.get("favorites", []) if f.get("platform") != "twitch"]
        self._config["favorites"] = reordered + non_twitch
        save_config(self._config)

    def search_channels(self, query: str) -> None:
        twitch_conf = self._get_twitch_config()
        if not twitch_conf.get("client_id") or not twitch_conf.get("client_secret"):
            self._eval_js("window.onSearchResults([])")
            return

        def do_search() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(self._twitch.search_channels(query))
                items = []
                for r in results:
                    items.append(
                        {
                            "login": r.get(
                                "broadcaster_login", r.get("display_name", "")
                            ).lower(),
                            "display_name": r.get("display_name", ""),
                            "is_live": r.get("is_live", False),
                            "game_name": r.get("game_name", ""),
                        }
                    )
                self._eval_js(f"window.onSearchResults({json.dumps(items)})")
            except Exception:
                self._eval_js("window.onSearchResults([])")
            finally:
                self._close_thread_loop(loop)

        self._run_in_thread(do_search)

    # ── Data fetch ──────────────────────────────────────────────

    def refresh(self) -> None:
        self._config = load_config()
        favorites = get_favorite_logins(self._config, "twitch")
        twitch_conf = get_platform_config(self._config, "twitch")

        if not favorites:
            has_creds = bool(
                twitch_conf.get("client_id") and twitch_conf.get("client_secret")
            )
            data = json.dumps(
                {
                    "streams": [],
                    "favorites": [],
                    "live_set": [],
                    "updated_time": "",
                    "total_viewers": 0,
                    "has_credentials": has_creds,
                }
            )
            self._eval_js(f"window.onStreamsUpdate({data})")
            return

        if not twitch_conf.get("client_id") or not twitch_conf.get("client_secret"):
            data = json.dumps(
                {
                    "streams": [],
                    "favorites": favorites,
                    "live_set": [],
                    "updated_time": "",
                    "total_viewers": 0,
                    "has_credentials": False,
                }
            )
            self._eval_js(f"window.onStreamsUpdate({data})")
            return

        if self._fetching:
            return
        self._fetching = True
        self._eval_js("window.onStatusUpdate({text: 'Refreshing...', type: 'info'})")
        self._run_in_thread(lambda fav=list(favorites): self._fetch_data(fav))

    def _fetch_data(self, favorites: list[str]) -> None:
        retry_delays = [5, 15, 30]
        max_attempts = len(retry_delays) + 1

        try:
            for attempt in range(1, max_attempts + 1):
                if self._shutdown.is_set():
                    return
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    streams, users = loop.run_until_complete(
                        self._async_fetch(favorites)
                    )
                    self._on_data_fetched(favorites, streams, users)
                    return
                except httpx.ConnectError:
                    if attempt < max_attempts:
                        delay = retry_delays[attempt - 1]
                        att = attempt + 1
                        self._eval_js(
                            f"window.onStatusUpdate({{text: 'Reconnecting... (attempt {att}/{max_attempts})', type: 'warn'}})"
                        )
                        time.sleep(delay)
                    else:
                        self._eval_js(
                            "window.onStatusUpdate({text: 'No internet connection', type: 'error'})"
                        )
                except httpx.HTTPStatusError as e:
                    status_code = e.response.status_code
                    if status_code in (401, 403):
                        self._eval_js(
                            "window.onStatusUpdate({text: 'Check your Twitch API credentials in Settings', type: 'error'})"
                        )
                    else:
                        self._eval_js(
                            f"window.onStatusUpdate({{text: 'API error: {status_code}', type: 'error'}})"
                        )
                    return
                except ValueError:
                    self._eval_js(
                        "window.onStatusUpdate({text: 'Set Twitch API credentials in Settings', type: 'error'})"
                    )
                    return
                except Exception as e:
                    traceback.print_exc()
                    msg = str(e)[:80] if str(e) else "Unknown error"
                    safe_msg = json.dumps(msg)
                    self._eval_js(
                        f"window.onStatusUpdate({{text: 'Error: ' + String({safe_msg}), type: 'error'}})"
                    )
                    return
                finally:
                    self._close_thread_loop(loop)
        finally:
            self._fetching = False

    async def _async_fetch(self, favorites: list[str]) -> tuple[list[dict], list[dict]]:
        await self._twitch._ensure_token()
        streams, users = await asyncio.gather(
            self._twitch.get_live_streams(favorites),
            self._twitch.get_users(favorites),
        )
        game_ids = [s.get("game_id", "") for s in streams if s.get("game_id")]
        if game_ids:
            games = await self._twitch.get_games(game_ids)
            self._games.update(games)
        return streams, users

    def _on_data_fetched(
        self, favorites: list[str], streams: list[dict], users: list[dict]
    ) -> None:
        self._live_streams = streams
        self._last_successful_fetch = time.time()
        live_logins = {s["user_login"].lower() for s in streams}

        # Notifications
        if self._first_fetch_done:
            newly_live = live_logins - self._prev_live_logins
            if newly_live:
                stream_map = {s["user_login"].lower(): s for s in streams}
                for login in newly_live:
                    s = stream_map.get(login)
                    if s:
                        self._send_notification(
                            s.get("user_name", login),
                            s.get("title", ""),
                            s.get("game_name", ""),
                        )
        self._prev_live_logins = set(live_logins)
        self._first_fetch_done = True

        # Store user avatar URLs for lazy loading
        for u in users:
            login = u["login"].lower()
            url = u.get("profile_image_url", "")
            if url:
                self._user_avatars[login] = url

        # Build stream items for JS
        stream_items = []
        for s in streams:
            login = s["user_login"].lower()
            game_id = s.get("game_id", "")
            game_name = s.get("game_name", "") or self._games.get(game_id, "")
            thumb_url = (
                s.get("thumbnail_url", "")
                .replace("{width}", "880")
                .replace("{height}", "496")
            )
            stream_items.append(
                {
                    "login": login,
                    "display_name": s.get("user_name", login),
                    "title": s.get("title", ""),
                    "game": game_name,
                    "viewers": s.get("viewer_count", 0),
                    "started_at": s.get("started_at", ""),
                    "thumbnail_url": thumb_url,
                    "viewer_trend": None,
                    "platform": "twitch",
                }
            )

        now = datetime.now().strftime("%H:%M:%S")
        total = sum(s.get("viewer_count", 0) for s in streams)

        data = json.dumps(
            {
                "streams": stream_items,
                "favorites": favorites,
                "live_set": list(live_logins),
                "updated_time": now,
                "total_viewers": total,
                "total_viewers_formatted": format_viewers(total) if total else "0",
                "has_credentials": True,
                "user_avatars": self._user_avatars,
            }
        )
        self._eval_js(f"window.onStreamsUpdate({data})")

    # ── Notifications ────────────────────────────────────────────

    def _send_notification(self, name: str, title: str, game: str) -> None:
        safe_name = name.replace('"', '\\"')
        safe_title = title.replace('"', '\\"')[:80]
        safe_game = game.replace('"', '\\"')

        script = (
            f'display notification "{safe_name} is now live: {safe_title}" '
            f'with title "TwitchX" subtitle "{safe_game}"'
        )

        def do_notify() -> None:
            with contextlib.suppress(Exception):
                subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    timeout=5,
                )

        self._run_in_thread(do_notify)

    # ── Polling ──────────────────────────────────────────────────

    def start_polling(self, interval_seconds: int = 60) -> None:
        self.stop_polling()
        self.refresh()

        def tick() -> None:
            if not self._shutdown.is_set():
                self.refresh()
                # Check for stale data
                if self._last_successful_fetch > 0:
                    stale = (
                        time.time() - self._last_successful_fetch > 2 * interval_seconds
                    )
                    if stale:
                        self._eval_js(
                            "window.onStatusUpdate({text: 'Data may be stale', type: 'warn', stale: true})"
                        )
                self._polling_timer = threading.Timer(interval_seconds, tick)
                self._polling_timer.daemon = True
                self._polling_timer.start()

        self._polling_timer = threading.Timer(interval_seconds, tick)
        self._polling_timer.daemon = True
        self._polling_timer.start()

    def stop_polling(self) -> None:
        if self._polling_timer:
            self._polling_timer.cancel()
            self._polling_timer = None

    # ── Watch ────────────────────────────────────────────────────

    def watch(self, channel: str, quality: str) -> None:
        """Resolve HLS URL in background, then play natively via AVPlayer."""
        if not channel:
            self._eval_js(
                "window.onLaunchResult({success: false, message: 'Select a channel first', channel: ''})"
            )
            return
        live_logins = {s["user_login"].lower() for s in self._live_streams}
        if channel.lower() not in live_logins:
            safe_ch = json.dumps(channel)
            self._eval_js(
                f"window.onLaunchResult({{success: false, message: {safe_ch} + ' is offline', channel: {safe_ch}}})"
            )
            return

        self._config["settings"]["quality"] = quality
        save_config(self._config)
        safe_ch = json.dumps(channel)
        self._eval_js(
            f"window.onStatusUpdate({{text: 'Loading ' + {safe_ch} + '...', type: 'warn'}})"
        )

        # Start launch progress timer
        self._launch_channel = channel
        self._launch_elapsed = 0
        self._start_launch_timer()

        # Find stream title for player
        title = ""
        for s in self._live_streams:
            if s["user_login"].lower() == channel.lower():
                title = s.get("title", "")
                break

        def do_resolve() -> None:
            settings = get_settings(self._config)
            hls_url, err = resolve_hls_url(
                channel,
                quality,
                settings.get("streamlink_path", "streamlink"),
            )
            self._cancel_launch_timer()
            self._launch_channel = None

            if not hls_url:
                r = json.dumps(
                    {
                        "success": False,
                        "message": f"streamlink error: {err}"
                        if err
                        else "Could not resolve stream URL",
                        "channel": channel,
                    }
                )
                self._eval_js(f"window.onLaunchResult({r})")
                return

            # Send HLS URL to JS for <video> playback
            self._watching_channel = channel
            stream_data = json.dumps(
                {
                    "url": hls_url,
                    "channel": channel,
                    "title": title,
                }
            )
            self._eval_js(f"window.onStreamReady({stream_data})")
            r = json.dumps(
                {
                    "success": True,
                    "message": f"Playing {channel}",
                    "channel": channel,
                }
            )
            self._eval_js(f"window.onLaunchResult({r})")

        self._run_in_thread(do_resolve)

    def stop_player(self) -> None:
        """Stop playback — tells JS to tear down the <video> player."""
        self._watching_channel = None
        self._eval_js("window.onPlayerStop()")

    def watch_external(self, channel: str, quality: str) -> None:
        """Launch stream in IINA (fallback)."""
        if not channel:
            return
        live_logins = {s["user_login"].lower() for s in self._live_streams}
        if channel.lower() not in live_logins:
            return

        def do_launch() -> None:
            settings = get_settings(self._config)
            result = launch_stream(
                channel,
                quality,
                settings.get("streamlink_path", "streamlink"),
                settings.get(
                    "iina_path", "/Applications/IINA.app/Contents/MacOS/iina-cli"
                ),
            )
            r = json.dumps(
                {
                    "success": result.success,
                    "message": result.message,
                    "channel": channel,
                }
            )
            self._eval_js(f"window.onLaunchResult({r})")

        self._run_in_thread(do_launch)

    def _start_launch_timer(self) -> None:
        self._cancel_launch_timer()
        self._launch_elapsed += 3

        def tick() -> None:
            if not self._shutdown.is_set() and self._launch_channel:
                ch = self._launch_channel
                elapsed = self._launch_elapsed
                safe_ch = json.dumps(ch)
                self._eval_js(
                    f"window.onLaunchProgress({{channel: {safe_ch}, elapsed: {elapsed}}})"
                )
                self._start_launch_timer()

        self._launch_timer = threading.Timer(3.0, tick)
        self._launch_timer.daemon = True
        self._launch_timer.start()

    def _cancel_launch_timer(self) -> None:
        if self._launch_timer:
            self._launch_timer.cancel()
            self._launch_timer = None

    def open_browser(self, channel: str) -> None:
        if channel:
            webbrowser.open(f"https://twitch.tv/{channel}")

    # ── Avatars + Thumbnails ────────────────────────────────────

    def get_avatar(self, login: str) -> None:
        def do_fetch() -> None:
            login_lower = login.lower()
            # Try disk cache first
            cached_bytes = get_cached_avatar(login_lower)
            if cached_bytes:
                try:
                    img = Image.open(io.BytesIO(cached_bytes)).resize(
                        (56, 56), Image.Resampling.LANCZOS
                    )
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    b64 = base64.b64encode(buf.getvalue()).decode()
                    data_url = f"data:image/png;base64,{b64}"
                    result = json.dumps({"login": login_lower, "data": data_url})
                    self._eval_js(f"window.onAvatar({result})")
                    return
                except Exception:
                    pass

            # Need URL — check stored URLs
            url = self._user_avatars.get(login_lower, "")
            if not url:
                return

            try:
                resp = httpx.get(url, timeout=10)
                raw_bytes = resp.content
                img = Image.open(io.BytesIO(raw_bytes)).resize(
                    (56, 56), Image.Resampling.LANCZOS
                )
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode()
                data_url = f"data:image/png;base64,{b64}"
                result = json.dumps({"login": login_lower, "data": data_url})
                self._eval_js(f"window.onAvatar({result})")
                save_avatar(login_lower, raw_bytes)
            except Exception:
                pass

        self._run_in_thread(do_fetch)

    def get_thumbnail(self, login: str, url: str) -> None:
        def do_fetch() -> None:
            try:
                resp = httpx.get(url, timeout=10)
                raw_bytes = resp.content
                img = Image.open(io.BytesIO(raw_bytes)).resize(
                    (440, 248), Image.Resampling.LANCZOS
                )
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                b64 = base64.b64encode(buf.getvalue()).decode()
                data_url = f"data:image/jpeg;base64,{b64}"
                result = json.dumps({"login": login.lower(), "data": data_url})
                self._eval_js(f"window.onThumbnail({result})")
            except Exception:
                pass

        self._run_in_thread(do_fetch)

    # ── Cleanup ──────────────────────────────────────────────────

    def close(self) -> None:
        self._shutdown.set()
        self.stop_polling()
        self._cancel_launch_timer()
        # Close twitch client
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._twitch.close())
        finally:
            asyncio.set_event_loop(None)
            loop.close()
