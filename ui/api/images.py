from __future__ import annotations

import base64
import io
import json
import logging

from PIL import Image

from core.storage import get_cached_avatar, save_avatar

from ._base import BaseApiComponent

logger = logging.getLogger(__name__)


class ImagesComponent(BaseApiComponent):
    """Avatar and thumbnail fetching."""

    def get_avatar(self, login: str, platform: str = "twitch") -> None:
        login_lower = login.lower()
        dedup_key = f"{platform}:{login_lower}"
        if dedup_key in self._api._fetching_avatars:
            return
        self._api._fetching_avatars.add(dedup_key)

        def do_fetch() -> None:
            try:
                cached_bytes = get_cached_avatar(login_lower, platform)
                if cached_bytes:
                    try:
                        b64 = base64.b64encode(cached_bytes).decode()
                        data_url = f"data:image/png;base64,{b64}"
                        result = json.dumps({"login": login_lower, "data": data_url})
                        self._eval_js(f"window.onAvatar({result})")
                        return
                    except Exception:
                        pass

                url = self._api._user_avatars.get(login_lower, "")
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
                result = json.dumps({"login": login_lower, "data": data_url})
                self._eval_js(f"window.onAvatar({result})")
                save_avatar(login_lower, resized_bytes, platform)
            except Exception as e:
                logger.warning(
                    "get_avatar failed for %s/%s: %s", platform, login_lower, e
                )
            finally:
                self._api._fetching_avatars.discard(dedup_key)

        try:
            self._api._image_pool.submit(do_fetch)
        except RuntimeError:
            self._api._fetching_avatars.discard(dedup_key)

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
