from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from typing import Any

import httpx

from core.storage import (
    get_favorite_logins,
    get_favorites,
    get_platform_config,
    get_settings,
    is_browse_slot_fresh,
    load_browse_cache,
    load_config,
    save_browse_cache,
)
from core.utils import format_viewers

from ._base import BaseApiComponent

logger = logging.getLogger(__name__)


def _aggregate_categories(
    by_platform: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for platform, categories in by_platform.items():
        for cat in categories:
            key = cat["name"].lower().strip()
            if not key:
                continue
            if key not in merged:
                merged[key] = {
                    "name": cat["name"],
                    "platforms": [],
                    "platform_ids": {},
                    "box_art_url": "",
                    "viewers": 0,
                }
            entry = merged[key]
            entry["platforms"].append(platform)
            entry["platform_ids"][platform] = cat["category_id"]
            entry["viewers"] += cat.get("viewers", 0)
            if not entry["box_art_url"] and cat.get("box_art_url"):
                entry["box_art_url"] = cat["box_art_url"]
    return sorted(merged.values(), key=lambda x: x["viewers"], reverse=True)


class DataComponent(BaseApiComponent):
    """Polling, refresh, browse, channel profiles."""

    # ── Polling infrastructure ──────────────────────────────────

    def restart_polling(self) -> None:
        """Restart polling with the configured interval."""
        interval = get_settings(self._config).get("refresh_interval", 60)
        self.start_polling(interval)

    def start_polling(self, interval_seconds: int = 60) -> None:
        with self._api._poll_lock:
            self._api._poll_generation += 1
            my_gen = self._api._poll_generation
            if self._api._polling_timer:
                self._api._polling_timer.cancel()
                self._api._polling_timer = None

        def tick() -> None:
            if self._shutdown.is_set():
                return
            self.refresh()
            if self._api._last_successful_fetch > 0:
                stale = time.time() - self._api._last_successful_fetch > 2 * interval_seconds
                if stale:
                    self._eval_js(
                        "window.onStatusUpdate({text: 'Data may be stale', type: 'warn', stale: true})"
                    )
            with self._api._poll_lock:
                if not self._shutdown.is_set() and self._api._poll_generation == my_gen:
                    self._api._polling_timer = threading.Timer(interval_seconds, tick)
                    self._api._polling_timer.daemon = True
                    self._api._polling_timer.start()

        with self._api._poll_lock:
            if self._api._poll_generation == my_gen:
                self._api._polling_timer = threading.Timer(interval_seconds, tick)
                self._api._polling_timer.daemon = True
                self._api._polling_timer.start()

        self.refresh()

    def stop_polling(self) -> None:
        with self._api._poll_lock:
            if self._api._polling_timer:
                self._api._polling_timer.cancel()
                self._api._polling_timer = None

    # ── Refresh ─────────────────────────────────────────────────

    def refresh(self) -> None:
        self._config = load_config()
        twitch_favorites = get_favorite_logins(self._config, "twitch")
        kick_favorites = get_favorite_logins(self._config, "kick")
        youtube_favorites = get_favorite_logins(self._config, "youtube")
        twitch_conf = get_platform_config(self._config, "twitch")

        all_favorites = twitch_favorites + kick_favorites + youtube_favorites

        if not all_favorites:
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

        twitch_has_creds = bool(
            twitch_conf.get("client_id") and twitch_conf.get("client_secret")
        )

        if not twitch_has_creds and not kick_favorites and not youtube_favorites:
            data = json.dumps(
                {
                    "streams": [],
                    "favorites": all_favorites,
                    "live_set": [],
                    "updated_time": "",
                    "total_viewers": 0,
                    "has_credentials": False,
                }
            )
            self._eval_js(f"window.onStreamsUpdate({data})")
            return

        if not self._api._fetch_lock.acquire(blocking=False):
            return
        try:
            self._eval_js(
                "window.onStatusUpdate({text: 'Refreshing...', type: 'info'})"
            )
            self._run_in_thread(
                lambda tf=list(twitch_favorites), kf=list(kick_favorites), yf=list(youtube_favorites): (
                    self._fetch_data(tf, kf, yf)
                )
            )
        except BaseException:
            self._api._fetch_lock.release()
            raise

    def _fetch_data(
        self,
        twitch_favorites: list[str],
        kick_favorites: list[str],
        youtube_favorites: list[str] | None = None,
    ) -> None:
        if youtube_favorites is None:
            youtube_favorites = []
        retry_delays = [5, 15, 30]
        max_attempts = len(retry_delays) + 1

        try:
            for attempt in range(1, max_attempts + 1):
                if self._shutdown.is_set():
                    return
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    (
                        twitch_streams,
                        twitch_users,
                        kick_streams,
                        youtube_streams,
                        twitch_error,
                    ) = loop.run_until_complete(
                        self._async_fetch(
                            twitch_favorites, kick_favorites, youtube_favorites
                        )
                    )
                    self._on_data_fetched(
                        twitch_favorites,
                        kick_favorites,
                        youtube_favorites,
                        twitch_streams,
                        twitch_users,
                        kick_streams,
                        youtube_streams,
                    )
                    if twitch_error is None:
                        return
                    if isinstance(twitch_error, httpx.ConnectError):
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
                    elif isinstance(twitch_error, httpx.HTTPStatusError):
                        status_code = twitch_error.response.status_code
                        if status_code in (401, 403):
                            self._eval_js(
                                "window.onStatusUpdate({text: 'Check your API credentials in Settings', type: 'error'})"
                            )
                        else:
                            self._eval_js(
                                f"window.onStatusUpdate({{text: 'API error: {status_code}', type: 'error'}})"
                            )
                        return
                    elif isinstance(twitch_error, ValueError):
                        self._eval_js(
                            "window.onStatusUpdate({text: 'Set API credentials in Settings', type: 'error'})"
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
            self._api._fetch_lock.release()

    async def _async_fetch(
        self,
        twitch_favorites: list[str],
        kick_favorites: list[str],
        youtube_favorites: list[str] | None = None,
        _twitch_timeout: float = 12.0,
        _kick_timeout: float = 12.0,
        _youtube_timeout: float = 20.0,
    ) -> tuple[list[dict], list[dict], list[dict], list[dict], BaseException | None]:
        youtube_favorites = youtube_favorites or []

        async def _do_twitch() -> tuple[list[dict], list[dict]]:
            twitch_conf = get_platform_config(self._config, "twitch")
            if not (
                twitch_favorites
                and twitch_conf.get("client_id")
                and twitch_conf.get("client_secret")
            ):
                return [], []
            await self._twitch._ensure_token()
            streams, users = await asyncio.gather(
                self._twitch.get_live_streams(twitch_favorites),
                self._twitch.get_users(twitch_favorites),
            )
            game_ids = [s.get("game_id", "") for s in streams if s.get("game_id")]
            if game_ids:
                games = await self._twitch.get_games(game_ids)
                self._api._games.update(games)
            return streams, users

        async def _do_kick() -> list[dict]:
            if not kick_favorites:
                return []
            try:
                streams = await asyncio.wait_for(
                    self._kick.get_live_streams(kick_favorites),
                    timeout=_kick_timeout,
                )
                self._api._last_kick_streams = streams
                return streams
            except Exception as e:
                logger.warning("Kick fetch failed: %s", e)
                return list(self._api._last_kick_streams)

        async def _do_youtube() -> list[dict]:
            if not youtube_favorites:
                return []
            yt_conf = get_platform_config(self._config, "youtube")
            settings = get_settings(self._config)
            yt_interval = settings.get("youtube_refresh_interval", 300)
            yt_due = time.time() - self._api._last_youtube_fetch >= yt_interval
            if not yt_due or not (
                yt_conf.get("api_key") or yt_conf.get("access_token")
            ):
                return list(self._api._last_youtube_streams)
            try:
                youtube_streams = await asyncio.wait_for(
                    self._youtube.get_live_streams(youtube_favorites),
                    timeout=_youtube_timeout,
                )
                self._api._last_youtube_fetch = time.time()
                self._api._last_youtube_streams = youtube_streams
                return youtube_streams
            except ValueError as e:
                msg = str(e)[:120]
                logger.warning("YouTube config error: %s", msg)
                self._eval_js(
                    "window.onStatusUpdate("
                    + json.dumps({"text": f"YouTube: {msg}", "type": "error"})
                    + ")"
                )
                return list(self._api._last_youtube_streams)
            except Exception as e:
                logger.warning("YouTube fetch failed: %s", e)
                return list(self._api._last_youtube_streams)

        twitch_result, kick_result, yt_result = await asyncio.gather(
            asyncio.wait_for(_do_twitch(), timeout=_twitch_timeout),
            _do_kick(),
            _do_youtube(),
            return_exceptions=True,
        )

        twitch_error: BaseException | None = None
        if isinstance(twitch_result, BaseException):
            if isinstance(twitch_result, TimeoutError):
                logger.warning("Twitch fetch timed out after %.1fs", _twitch_timeout)
            elif isinstance(
                twitch_result, (httpx.ConnectError, httpx.HTTPStatusError, ValueError)
            ):
                twitch_error = twitch_result
            else:
                logger.warning("Twitch fetch failed: %s", twitch_result)
            twitch_streams: list[dict] = list(self._api._last_twitch_streams)
            twitch_users: list[dict] = list(self._api._last_twitch_users)
        else:
            twitch_streams, twitch_users = twitch_result
            self._api._last_twitch_streams = twitch_streams
            self._api._last_twitch_users = twitch_users

        kick_streams: list[dict] = kick_result if isinstance(kick_result, list) else []
        youtube_streams: list[dict] = yt_result if isinstance(yt_result, list) else []

        return twitch_streams, twitch_users, kick_streams, youtube_streams, twitch_error

    def _on_data_fetched(
        self,
        twitch_favorites: list[str],
        kick_favorites: list[str],
        youtube_favorites: list[str],
        twitch_streams: list[dict],
        twitch_users: list[dict],
        kick_streams: list[dict],
        youtube_streams: list[dict],
    ) -> None:
        self._api._last_successful_fetch = time.time()

        twitch_live_logins = {s["user_login"].lower() for s in twitch_streams}
        kick_live_slugs = {
            (s.get("slug", "") or s.get("channel", {}).get("slug", "")).lower()
            for s in kick_streams
        }
        youtube_live_ids = {
            s.get("login", "") for s in youtube_streams if s.get("login")
        }
        live_logins = twitch_live_logins | kick_live_slugs | youtube_live_ids

        if self._api._first_fetch_done:
            newly_live = live_logins - self._api._prev_live_logins
            if newly_live:
                unified_map: dict[str, dict] = {}
                for s in twitch_streams:
                    unified_map[s["user_login"].lower()] = {
                        "name": s.get("user_name", s["user_login"]),
                        "title": s.get("title", ""),
                        "game": s.get("game_name", ""),
                    }
                for s in kick_streams:
                    slug = (
                        s.get("slug", "") or s.get("channel", {}).get("slug", "")
                    ).lower()
                    if slug:
                        unified_map[slug] = {
                            "name": s.get("channel", {}).get("username") or slug,
                            "title": s.get("stream_title")
                            or s.get("session_title")
                            or s.get("title", ""),
                            "game": s.get("category", {}).get("name", "")
                            if isinstance(s.get("category"), dict)
                            else "",
                        }
                for s in youtube_streams:
                    cid = s.get("login", "")
                    if cid:
                        unified_map[cid] = {
                            "name": s.get("display_name", cid),
                            "title": s.get("title", ""),
                            "game": s.get("game", ""),
                        }
                for login in newly_live:
                    info = unified_map.get(login)
                    if info:
                        self._send_notification(
                            info["name"],
                            info["title"],
                            info["game"],
                        )
        self._api._prev_live_logins = set(live_logins)
        self._api._first_fetch_done = True

        for u in twitch_users:
            login = u["login"].lower()
            url = u.get("profile_image_url", "")
            if url:
                self._api._user_avatars[login] = url

        stream_items: list[dict[str, Any]] = []
        for s in twitch_streams:
            login = s["user_login"].lower()
            game_id = s.get("game_id", "")
            game_name = s.get("game_name", "") or self._api._games.get(game_id, "")
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

        for s in kick_streams:
            stream_items.append(self._api._build_kick_stream_item(s))

        for s in youtube_streams:
            stream_items.append(self._api._build_youtube_stream_item(s))

        self._live_streams = stream_items

        all_favorites = twitch_favorites + kick_favorites + youtube_favorites
        now = datetime.now().strftime("%H:%M:%S")
        total = sum(item.get("viewers", 0) for item in stream_items)

        favorites_meta = {
            f"{f.get('platform', 'twitch')}:{f['login']}": {
                "display_name": f.get("display_name", f["login"]),
                "platform": f.get("platform", "twitch"),
                "login": f["login"],
            }
            for f in get_favorites(self._config)
        }

        data = json.dumps(
            {
                "streams": stream_items,
                "favorites": all_favorites,
                "favorites_meta": favorites_meta,
                "live_set": list(live_logins),
                "updated_time": now,
                "total_viewers": total,
                "total_viewers_formatted": format_viewers(total) if total else "0",
                "has_credentials": True,
                "user_avatars": self._api._user_avatars,
            }
        )
        self._eval_js(f"window.onStreamsUpdate({data})")

    # ── Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _stream_login(stream: dict[str, Any]) -> str:
        return (
            stream.get("login")
            or stream.get("user_login")
            or stream.get("channel", {}).get("slug", "")
            or stream.get("slug", "")
        ).lower()

    @staticmethod
    def _stream_platform(stream: dict[str, Any]) -> str:
        return str(stream.get("platform", "twitch"))

    def _find_live_stream(self, channel: str) -> dict[str, Any] | None:
        channel_lower = channel.lower()
        for stream in self._live_streams:
            if self._stream_login(stream) == channel_lower:
                return stream
        return None

    # ── Notifications ───────────────────────────────────────────

    def _send_notification(self, name: str, title: str, game: str) -> None:
        def _esc(s: str) -> str:
            return s.replace("\\", "\\\\").replace('"', '\\"')

        safe_name = _esc(name)
        safe_title = _esc(title[:80])
        safe_game = _esc(game)

        script = (
            f'display notification "{safe_name} is now live: {safe_title}" '
            f'with title "TwitchX" subtitle "{safe_game}"'
        )

        def do_notify() -> None:
            if sys.platform != "darwin":
                return
            with contextlib.suppress(Exception):
                subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    timeout=5,
                )

        self._run_in_thread(do_notify)

    # ── Browse ─────────────────────────────────────────────────

    def get_browse_categories(self, platform_filter: str = "all") -> None:
        self._run_in_thread(lambda: self._fetch_browse_categories(platform_filter))

    def _fetch_browse_categories(self, platform_filter: str) -> None:
        platforms = (
            ["twitch", "kick", "youtube"]
            if platform_filter == "all"
            else [platform_filter]
        )
        config = load_config()
        enabled = [
            p
            for p in platforms
            if config.get("platforms", {}).get(p, {}).get("enabled", False)
        ]
        cache = load_browse_cache()
        now = time.time()
        results: dict[str, list[dict[str, Any]]] = {}
        to_fetch: list[str] = []
        for platform in enabled:
            slot = f"categories_{platform}"
            if is_browse_slot_fresh(cache, slot):
                results[platform] = cache[slot]["data"]
            else:
                to_fetch.append(platform)
        if to_fetch:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:

                async def _fetch_categories_parallel() -> None:
                    clients = {
                        p: self._get_platform(p)
                        for p in to_fetch
                        if self._get_platform(p) is not None
                    }
                    for p in to_fetch:
                        if p not in clients:
                            logger.warning("browse: unknown platform %r, skipping", p)
                    gathered = await asyncio.gather(
                        *[c.get_categories() for c in clients.values()],
                        return_exceptions=True,
                    )
                    for p, result in zip(clients.keys(), gathered, strict=True):
                        if isinstance(result, BaseException):
                            logger.warning(
                                "browse categories failed for %s: %s", p, result
                            )
                            results[p] = []
                        else:
                            results[p] = result
                            cache[f"categories_{p}"] = {
                                "data": result,
                                "fetched_at": now,
                            }

                loop.run_until_complete(_fetch_categories_parallel())
                save_browse_cache(cache)
            finally:
                self._close_thread_loop(loop)
        merged = _aggregate_categories(results)
        self._eval_js(f"window.onBrowseCategories({json.dumps(merged)})")

    def get_browse_top_streams(
        self,
        category_name: str,
        platform_ids: dict[str, str],
        platform_filter: str = "all",
    ) -> None:
        self._run_in_thread(
            lambda: self._fetch_browse_top_streams(
                category_name, platform_ids, platform_filter
            )
        )

    def _fetch_browse_top_streams(
        self,
        category_name: str,
        platform_ids: dict[str, str],
        platform_filter: str,
    ) -> None:
        in_filter = (
            list(platform_ids.keys()) if platform_filter == "all" else [platform_filter]
        )
        platforms_to_query = [p for p in in_filter if p in platform_ids]
        cache = load_browse_cache()
        now = time.time()
        all_streams: list[dict[str, Any]] = []
        to_fetch: list[str] = []
        for platform in platforms_to_query:
            cat_id = platform_ids[platform]
            slot = f"top_streams_{platform}_{cat_id}"
            if is_browse_slot_fresh(cache, slot):
                all_streams.extend(cache[slot]["data"])
            else:
                to_fetch.append(platform)
        if to_fetch:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:

                async def _fetch_top_streams_parallel() -> None:
                    clients = {
                        p: self._get_platform(p)
                        for p in to_fetch
                        if self._get_platform(p) is not None
                    }
                    for p in to_fetch:
                        if p not in clients:
                            logger.warning("browse: unknown platform %r, skipping", p)
                    gathered = await asyncio.gather(
                        *[
                            c.get_top_streams(category_id=platform_ids[p], limit=20)
                            for p, c in clients.items()
                        ],
                        return_exceptions=True,
                    )
                    for p, result in zip(clients.keys(), gathered, strict=True):
                        if isinstance(result, BaseException):
                            logger.warning(
                                "browse top streams failed for %s: %s", p, result
                            )
                        else:
                            all_streams.extend(result)
                            cache[f"top_streams_{p}_{platform_ids[p]}"] = {
                                "data": result,
                                "fetched_at": now,
                            }

                loop.run_until_complete(_fetch_top_streams_parallel())
            finally:
                self._close_thread_loop(loop)
            save_browse_cache(cache)
        all_streams.sort(key=lambda s: s.get("viewers", 0), reverse=True)
        payload = {"category": category_name, "streams": all_streams[:40]}
        self._eval_js(f"window.onBrowseTopStreams({json.dumps(payload)})")

    # ── Channel profile ─────────────────────────────────────────

    @staticmethod
    def _normalize_channel_info_to_profile(
        raw: dict[str, Any], login: str, platform: str
    ) -> dict[str, Any]:
        if platform == "twitch":
            return {
                "platform": "twitch",
                "channel_id": raw.get("channel_id", ""),
                "login": raw.get("login", login),
                "display_name": raw.get("display_name", login),
                "bio": raw.get("bio", ""),
                "avatar_url": raw.get("avatar_url", ""),
                "followers": raw.get("followers", -1),
                "is_live": bool(raw.get("is_live", False)),
                "can_follow_via_api": False,
            }
        if platform == "kick":
            user = raw.get("user") or {}
            cid = raw.get("channel_id")
            if cid is None:
                cid = raw.get("id")
            return {
                "platform": "kick",
                "channel_id": str(cid) if cid is not None else "",
                "login": raw.get("slug", login),
                "display_name": (
                    user.get("username")
                    or raw.get("username")
                    or raw.get("slug", login)
                ),
                "bio": raw.get("description") or raw.get("bio", ""),
                "avatar_url": user.get("profile_pic") or raw.get("profile_picture", ""),
                "followers": raw.get("followers_count", 0),
                "is_live": bool(raw.get("is_live", False)) or bool(raw.get("stream")),
                "can_follow_via_api": False,
            }
        if platform == "youtube":
            channel_id = raw.get("channel_id", login)
            return {
                "platform": "youtube",
                "channel_id": channel_id,
                "login": channel_id,
                "display_name": raw.get("display_name", login),
                "bio": raw.get("description", ""),
                "avatar_url": raw.get("avatar_url", ""),
                "followers": raw.get("followers", 0),
                "is_live": False,
                "can_follow_via_api": False,
            }
        return {}

    def get_channel_profile(self, login: str, platform: str = "twitch") -> None:
        client = self._get_platform(platform)
        if client is None:
            return

        def do_fetch() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                raw = loop.run_until_complete(client.get_channel_info(login))
                if not raw:
                    self._eval_js("window.onChannelProfile(null)")
                    return
                profile = self._normalize_channel_info_to_profile(raw, login, platform)
                if not profile:
                    self._eval_js("window.onChannelProfile(null)")
                    return
                if platform == "youtube":
                    profile["is_live"] = any(
                        s.get("login", "") == profile["login"]
                        for s in self._live_streams
                        if s.get("platform") == "youtube"
                    )
                fresh_config = load_config()
                favs = get_favorites(fresh_config)
                profile["is_favorited"] = any(
                    f.get("login") == profile["login"] and f.get("platform") == platform
                    for f in favs
                )
                self._eval_js(f"window.onChannelProfile({json.dumps(profile)})")
            except Exception as e:
                logger.warning("get_channel_profile failed: %s", e)
                self._eval_js("window.onChannelProfile(null)")
            finally:
                self._close_thread_loop(loop)

        self._run_in_thread(do_fetch)

    def get_channel_media(
        self,
        login: str,
        platform: str = "twitch",
        tab: str = "vods",
    ) -> None:
        if tab not in ("vods", "clips"):
            return
        client = self._get_platform(platform)
        if client is None:
            return
        if platform == "kick":
            payload = {
                "login": login,
                "platform": platform,
                "tab": tab,
                "items": [],
                "supported": False,
                "error": False,
                "message": "Kick's official API does not expose VODs or clips yet.",
            }
            self._eval_js(f"window.onChannelMedia({json.dumps(payload)})")
            return

        fetcher_name = "get_channel_vods" if tab == "vods" else "get_channel_clips"
        fetcher = getattr(client, fetcher_name, None)
        if fetcher is None:
            payload = {
                "login": login,
                "platform": platform,
                "tab": tab,
                "items": [],
                "supported": False,
                "error": False,
                "message": f"{platform.title()} does not support {tab} in this build.",
            }
            self._eval_js(f"window.onChannelMedia({json.dumps(payload)})")
            return

        def do_fetch() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                items = loop.run_until_complete(fetcher(login, limit=12))
                payload = {
                    "login": login,
                    "platform": platform,
                    "tab": tab,
                    "items": items,
                    "supported": True,
                    "error": False,
                    "message": "",
                }
            except Exception as e:
                logger.warning("get_channel_media failed: %s", e)
                payload = {
                    "login": login,
                    "platform": platform,
                    "tab": tab,
                    "items": [],
                    "supported": True,
                    "error": True,
                    "message": f"Could not load {tab} right now.",
                }
            finally:
                self._close_thread_loop(loop)

            self._eval_js(f"window.onChannelMedia({json.dumps(payload)})")

        self._run_in_thread(do_fetch)
