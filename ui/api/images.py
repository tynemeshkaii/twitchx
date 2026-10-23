from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import threading
import time
from typing import Any

from PIL import Image

from core.storage import get_cached_avatar, save_avatar

from ._base import BaseApiComponent

logger = logging.getLogger(__name__)

# A Kick channel whose picture could not be found is not looked up again for
# this long: each lookup costs a public-API call plus two kick.com requests,
# and get_avatar is re-requested for every favorite on every poll.
KICK_AVATAR_MISS_TTL = 30 * 60


class ImagesComponent(BaseApiComponent):
    """Avatar and thumbnail fetching."""

    def __init__(self, parent: Any) -> None:
        super().__init__(parent)
        # slug → time.monotonic() of the last failed Kick avatar lookup
        self._kick_avatar_misses: dict[str, float] = {}
        self._kick_avatar_lock = threading.Lock()

    def get_avatar(self, login: str, platform: str = "twitch") -> None:
        login_key = login if platform == "youtube" else login.lower()
        dedup_key = f"{platform}:{login_key}"
        if dedup_key in self._api._fetching_avatars:
            return
        self._api._fetching_avatars.add(dedup_key)

        def do_fetch() -> None:
            try:
                cached_bytes = get_cached_avatar(login_key, platform)
                if cached_bytes:
                    try:
                        b64 = base64.b64encode(cached_bytes).decode()
                        data_url = f"data:image/png;base64,{b64}"
                        result = json.dumps(
                            {
                                "login": login_key,
                                "platform": platform,
                                "data": data_url,
                            }
                        )
                        self._eval_js(f"window.onAvatar({result})")
                        return
                    except Exception as exc:
                        logger.debug(
                            "Cached avatar decode failed for %s: %s", login_key, exc
                        )

                url = self._api._user_avatars.get(dedup_key, "")
                if not url and platform == "kick":
                    url = self._resolve_kick_avatar(login_key)
                if not url:
                    return

                resp = self._api._http.get(url)
                raw_bytes = resp.content
                img = Image.open(io.BytesIO(raw_bytes)).resize(
                    (56, 56), Image.Resampling.LANCZOS
                )
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                resized_bytes = buf.getvalue()
                b64 = base64.b64encode(resized_bytes).decode()
                data_url = f"data:image/png;base64,{b64}"
                result = json.dumps(
                    {"login": login_key, "platform": platform, "data": data_url}
                )
                self._eval_js(f"window.onAvatar({result})")
                save_avatar(login_key, resized_bytes, platform)
            except Exception as e:
                logger.warning(
                    "get_avatar failed for %s/%s: %s", platform, login_key, e
                )
            finally:
                self._api._fetching_avatars.discard(dedup_key)

        try:
            self._api._image_pool.submit(do_fetch)
        except RuntimeError:
            self._api._fetching_avatars.discard(dedup_key)

    def _resolve_kick_avatar(self, slug: str) -> str:
        """Look up a Kick profile picture URL; the live poll carries none.

        Runs once per channel: the resized image then lives in the disk cache.
        A miss is remembered for KICK_AVATAR_MISS_TTL seconds.
        """
        with self._kick_avatar_lock:
            missed_at = self._kick_avatar_misses.get(slug)
            if missed_at is not None:
                if time.monotonic() - missed_at < KICK_AVATAR_MISS_TTL:
                    return ""
                del self._kick_avatar_misses[slug]
        url = self._lookup_kick_avatar(slug)
        if url:
            self._api._user_avatars[f"kick:{slug}"] = url
        else:
            with self._kick_avatar_lock:
                self._kick_avatar_misses[slug] = time.monotonic()
        return url

    def _lookup_kick_avatar(self, slug: str) -> str:
        loop = asyncio.new_event_loop()
        try:
            info = loop.run_until_complete(self._api._kick.get_channel_info(slug))
        except Exception as exc:
            logger.debug("Kick avatar lookup failed for %s: %s", slug, exc)
            return ""
        finally:
            self._close_thread_loop(loop)
        if not isinstance(info, dict):
            return ""
        user = info.get("user")
        url = (user.get("profile_pic") if isinstance(user, dict) else "") or info.get(
            "profile_picture"
        )
        return url if isinstance(url, str) else ""

    def get_thumbnail(self, login: str, url: str) -> None:
        if login in self._api._fetching_thumbnails:
            return
        self._api._fetching_thumbnails.add(login)

        def do_fetch() -> None:
            try:
                resp = self._api._http.get(url)
                raw_bytes = resp.content
                img = Image.open(io.BytesIO(raw_bytes)).resize(
                    (440, 248), Image.Resampling.LANCZOS
                )
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                b64 = base64.b64encode(buf.getvalue()).decode()
                data_url = f"data:image/jpeg;base64,{b64}"
                result = json.dumps({"login": login, "data": data_url})
                self._eval_js(f"window.onThumbnail({result})")
            except Exception as e:
                logger.warning("get_thumbnail failed for %s: %s", login, e)
            finally:
                self._api._fetching_thumbnails.discard(login)

        try:
            self._api._image_pool.submit(do_fetch)
        except RuntimeError:
            self._api._fetching_thumbnails.discard(login)
