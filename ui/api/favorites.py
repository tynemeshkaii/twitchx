from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from core.storage import get_platform_config, update_config

from ._base import BaseApiComponent

logger = logging.getLogger(__name__)


class FavoritesComponent(BaseApiComponent):
    """Channel favorites management, search, and import."""

    # ── Import ──────────────────────────────────────────────────

    def import_follows(self) -> None:
        if not self._api._current_user:
            self._eval_js('window.onImportError("Not logged in")')
            return
        twitch_conf = self._get_twitch_config()
        user_id = self._api._current_user.get("id", twitch_conf.get("user_id", ""))
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
                added = 0
                new_logins = [name.lower() for name in logins]

                def _apply(cfg: dict) -> None:
                    nonlocal added
                    existing = {
                        f["login"]
                        for f in cfg.get("favorites", [])
                        if f.get("platform") == "twitch"
                    }
                    for login in new_logins:
                        if login not in existing:
                            cfg["favorites"].append(
                                {
                                    "platform": "twitch",
                                    "login": login,
                                    "display_name": login,
                                }
                            )
                            existing.add(login)
                            added += 1

                self._config = update_config(_apply)
                result = json.dumps({"added": added})
                self._eval_js(f"window.onImportComplete({result})")
                self._api._data.refresh()
            except Exception as e:
                msg = str(e)[:80] if str(e) else "Import failed"
                safe_msg = json.dumps(msg)
                self._eval_js(f"window.onImportError({safe_msg})")
            finally:
                self._close_thread_loop(loop)

        self._run_in_thread(do_import)

    def youtube_import_follows(self) -> None:
        yt_conf = self._get_youtube_config()
        if not yt_conf.get("access_token"):
            self._eval_js('window.onYouTubeImportError("Not logged in to YouTube")')
            return
        self._eval_js(
            "window.onStatusUpdate({text: 'Importing YouTube subscriptions...', type: 'warn'})"
        )

        def do_import() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                subs = loop.run_until_complete(
                    self._youtube.get_followed_channels("me")
                )
                added = 0

                def _apply(cfg: dict) -> None:
                    nonlocal added
                    existing = {
                        f["login"]
                        for f in cfg.get("favorites", [])
                        if f.get("platform") == "youtube"
                    }
                    for sub in subs:
                        cid = sub["channel_id"]
                        if cid not in existing:
                            cfg["favorites"].append(
                                {
                                    "platform": "youtube",
                                    "login": cid,
                                    "display_name": sub["display_name"],
                                }
                            )
                            existing.add(cid)
                            added += 1

                self._config = update_config(_apply)
                result = json.dumps({"added": added})
                self._eval_js(f"window.onYouTubeImportComplete({result})")
                self._api._data.refresh()
            except Exception as e:
                msg = str(e)[:80] if str(e) else "YouTube import failed"
                safe_msg = json.dumps(msg)
                self._eval_js(f"window.onYouTubeImportError({safe_msg})")
            finally:
                self._close_thread_loop(loop)

        self._run_in_thread(do_import)

    # ── Add / Remove / Reorder ──────────────────────────────────

    def add_channel(
        self, username: str, platform: str = "twitch", display_name: str = ""
    ) -> None:
        clean = self._api._sanitize_channel_name(username, platform)
        if not clean:
            self._eval_js(
                "window.onStatusUpdate("
                + json.dumps({"text": "Invalid channel name or URL", "type": "error"})
                + ")"
            )
            return

        if platform == "youtube" and (clean.startswith("@") or clean.startswith("v:")):
            resolve_input = clean[2:] if clean.startswith("v:") else clean

            def do_resolve() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    info = loop.run_until_complete(
                        self._youtube.get_channel_info(resolve_input)
                    )
                    channel_id = info.get("channel_id", "")
                    if not channel_id:
                        self._eval_js(
                            "window.onStatusUpdate("
                            + json.dumps(
                                {
                                    "text": "YouTube channel not found. Check the URL or username.",
                                    "type": "error",
                                }
                            )
                            + ")"
                        )
                        return
                    display_name = info.get("display_name", channel_id)
                    added = False

                    def _apply(cfg: dict) -> None:
                        nonlocal added
                        favorites = cfg.get("favorites", [])
                        if any(
                            f.get("login", "").lower() == channel_id.lower()
                            and f.get("platform") == "youtube"
                            for f in favorites
                        ):
                            return
                        favorites.append(
                            {
                                "platform": "youtube",
                                "login": channel_id,
                                "display_name": display_name,
                            }
                        )
                        cfg["favorites"] = favorites
                        added = True

                    self._config = update_config(_apply)
                    if added:
                        self._api._data.refresh()
                        self._eval_js(
                            "window.onStatusUpdate("
                            + json.dumps(
                                {
                                    "text": f"Added {display_name} to YouTube favorites",
                                    "type": "success",
                                }
                            )
                            + ")"
                        )
                    else:
                        self._eval_js(
                            "window.onStatusUpdate("
                            + json.dumps(
                                {
                                    "text": f"{display_name} is already in YouTube favorites",
                                    "type": "info",
                                }
                            )
                            + ")"
                        )
                except ValueError as e:
                    msg = str(e)[:120]
                    self._eval_js(
                        "window.onStatusUpdate("
                        + json.dumps({"text": msg, "type": "error"})
                        + ")"
                    )
                except Exception:
                    logger.warning("YouTube channel resolve failed", exc_info=True)
                    self._eval_js(
                        "window.onStatusUpdate("
                        + json.dumps(
                            {
                                "text": "Could not resolve YouTube channel. Check your API key in Settings.",
                                "type": "error",
                            }
                        )
                        + ")"
                    )
                finally:
                    self._close_thread_loop(loop)

            self._run_in_thread(do_resolve)
            return

        added = False

        def _apply(cfg: dict) -> None:
            nonlocal added
            favorites = cfg.get("favorites", [])
            if platform == "youtube":
                already = any(
                    f.get("login", "").lower() == clean.lower()
                    and f.get("platform") == "youtube"
                    for f in favorites
                )
            else:
                already = any(
                    f.get("login") == clean and f.get("platform") == platform
                    for f in favorites
                )
            if already:
                return
            favorites.append(
                {
                    "platform": platform,
                    "login": clean,
                    "display_name": display_name or clean,
                }
            )
            cfg["favorites"] = favorites
            added = True

        self._config = update_config(_apply)
        if added:
            self._api._data.refresh()
            self._eval_js(
                "window.onStatusUpdate("
                + json.dumps(
                    {
                        "text": f"Added {clean} from {platform.title()}",
                        "type": "success",
                    }
                )
                + ")"
            )
        else:
            self._eval_js(
                "window.onStatusUpdate("
                + json.dumps(
                    {
                        "text": f"{clean} is already in {platform.title()} favorites",
                        "type": "warn",
                    }
                )
                + ")"
            )

    def remove_channel(self, channel: str, platform: str = "twitch") -> None:
        login_cmp = channel if platform == "youtube" else channel.lower()

        def _apply(cfg: dict) -> None:
            cfg["favorites"] = [
                f
                for f in cfg.get("favorites", [])
                if not (f.get("login") == login_cmp and f.get("platform") == platform)
            ]

        self._config = update_config(_apply)
        self._api._data.refresh()

    def reorder_channels(self, new_order_json: str, platform: str = "twitch") -> None:
        new_order = (
            json.loads(new_order_json)
            if isinstance(new_order_json, str)
            else new_order_json
        )

        def _apply(cfg: dict) -> None:
            old_favs = {
                f["login"]: f
                for f in cfg.get("favorites", [])
                if f.get("platform") == platform
            }
            reordered = [
                old_favs.get(
                    login, {"platform": platform, "login": login, "display_name": login}
                )
                for login in new_order
            ]
            result: list[dict] = []
            inserted = False
            for f in cfg.get("favorites", []):
                if f.get("platform") == platform:
                    if not inserted:
                        result.extend(reordered)
                        inserted = True
                else:
                    result.append(f)
            if not inserted:
                result.extend(reordered)
            cfg["favorites"] = result

        self._config = update_config(_apply)

    # ── Search ──────────────────────────────────────────────────

    def search_channels(self, query: str, platform: str = "twitch") -> None:
        def do_search() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                items: list[dict[str, Any]] = []
                if platform in {"kick", "all"}:
                    kick_results = loop.run_until_complete(
                        self._kick.search_channels(query)
                    )
                    items.extend(
                        self._api._normalize_kick_search_result(result)
                        for result in kick_results
                    )

                if platform in {"twitch", "all"}:
                    twitch_conf = self._get_twitch_config()
                    if twitch_conf.get("client_id") and twitch_conf.get(
                        "client_secret"
                    ):
                        twitch_results = loop.run_until_complete(
                            self._twitch.search_channels(query)
                        )
                        items.extend(
                            self._api._normalize_twitch_search_result(result)
                            for result in twitch_results
                        )

                if platform in {"youtube", "all"}:
                    yt_conf = get_platform_config(self._config, "youtube")
                    if yt_conf.get("api_key") or yt_conf.get("access_token"):
                        yt_results = loop.run_until_complete(
                            self._youtube.search_channels(query)
                        )
                        items.extend(
                            self._api._normalize_youtube_search_result(result)
                            for result in yt_results
                        )

                deduped: list[dict[str, Any]] = []
                seen: set[tuple[str, str]] = set()
                exact_query = query.strip().lower()
                for item in sorted(
                    items,
                    key=lambda item: (
                        item["login"] != exact_query,
                        not item["is_live"],
                        item["platform"] != "kick",
                        item["display_name"].lower(),
                    ),
                ):
                    key = (item["platform"], item["login"])
                    if key in seen or not item["login"]:
                        continue
                    seen.add(key)
                    deduped.append(item)

                self._eval_js(f"window.onSearchResults({json.dumps(deduped)})")
            except Exception as e:
                logger.warning("search_channels failed: %s", e, exc_info=True)
                self._eval_js("window.onSearchResults([])")
            finally:
                self._close_thread_loop(loop)

        self._run_in_thread(do_search)
