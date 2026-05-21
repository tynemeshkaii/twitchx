# pyright: reportAttributeAccessIssue=false, reportCallIssue=false
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from PIL import Image

from ui.api import TwitchXApi


def _make_png(width: int = 56, height: int = 56, color: str = "red") -> bytes:
    """Create a minimal valid PNG image and return its bytes."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _create_api() -> TwitchXApi:
    """Create a TwitchXApi with httpx.Client mocked to avoid proxy issues."""
    with patch("httpx.Client"):
        api = TwitchXApi()
    api._http = MagicMock()
    return api


# ──────────────────────────────────────────────────────────────
# Avatar tests
# ──────────────────────────────────────────────────────────────


class TestGetAvatar:
    def test_cache_hit_emits_on_avatar(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _create_api()
        api._eval_js = capture_eval_js
        api._image_pool.submit = lambda fn: fn()

        cached_bytes = _make_png()
        with patch("ui.api.images.get_cached_avatar", return_value=cached_bytes):
            api._images.get_avatar("TestUser")

        capture_eval_js.assert_any("onAvatar")
        assert "testuser" in capture_eval_js.calls[0]

    def test_cache_hit_no_http_fetch(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _create_api()
        api._eval_js = capture_eval_js
        api._image_pool.submit = lambda fn: fn()
        api._http = MagicMock()

        cached_bytes = _make_png()
        with patch("ui.api.images.get_cached_avatar", return_value=cached_bytes):
            api._images.get_avatar("SomeUser")

        api._http.get.assert_not_called()

    def test_network_fetch_resizes_and_emits(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _create_api()
        api._eval_js = capture_eval_js
        api._image_pool.submit = lambda fn: fn()
        api._user_avatars["netuser"] = "https://example.com/avatar.png"

        raw_png = _make_png(100, 100, "green")
        mock_resp = MagicMock()
        mock_resp.content = raw_png
        api._http = MagicMock()
        api._http.get.return_value = mock_resp

        with patch("ui.api.images.get_cached_avatar", return_value=None), patch(
            "ui.api.images.save_avatar"
        ) as mock_save:
            api._images.get_avatar("NetUser")

        capture_eval_js.assert_any("onAvatar")
        assert "netuser" in capture_eval_js.calls[0]
        assert "data:image/png;base64," in capture_eval_js.calls[0]
        mock_save.assert_called_once()
        saved_login = mock_save.call_args[0][0]
        assert saved_login == "netuser"

    def test_network_fetch_saves_avatar_with_platform(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _create_api()
        api._eval_js = capture_eval_js
        api._image_pool.submit = lambda fn: fn()
        api._user_avatars["saveuser"] = "https://example.com/avatar.png"

        raw_png = _make_png(80, 80)
        mock_resp = MagicMock()
        mock_resp.content = raw_png
        api._http = MagicMock()
        api._http.get.return_value = mock_resp

        with patch("ui.api.images.get_cached_avatar", return_value=None), patch(
            "ui.api.images.save_avatar"
        ) as mock_save:
            api._images.get_avatar("SaveUser", platform="kick")

        mock_save.assert_called_once()
        args = mock_save.call_args[0]
        assert args[0] == "saveuser"
        assert isinstance(args[1], bytes)
        assert args[2] == "kick"

    def test_no_url_available_silent_return(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _create_api()
        api._eval_js = capture_eval_js
        api._image_pool.submit = lambda fn: fn()

        with patch("ui.api.images.get_cached_avatar", return_value=None):
            api._images.get_avatar("NoUrlUser")

        assert len(capture_eval_js.calls) == 0

    def test_corrupt_cache_falls_through_to_network(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _create_api()
        api._image_pool.submit = lambda fn: fn()
        api._user_avatars["corruptuser"] = "https://example.com/avatar.png"

        raw_png = _make_png(64, 64)
        mock_resp = MagicMock()
        mock_resp.content = raw_png
        api._http = MagicMock()
        api._http.get.return_value = mock_resp

        call_count = 0

        def eval_js_fail_first(code: str) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("simulated JS error")
            capture_eval_js(code)

        api._eval_js = eval_js_fail_first

        with patch(
            "ui.api.images.get_cached_avatar", return_value=_make_png()
        ), patch("ui.api.images.save_avatar"):
            api._images.get_avatar("CorruptUser")

        # The cache path raised on _eval_js, so it fell through to network fetch
        assert call_count == 2

    def test_network_error_logs_warning_and_cleans_dedup(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _create_api()
        api._eval_js = capture_eval_js
        api._image_pool.submit = lambda fn: fn()
        api._user_avatars["erruser"] = "https://example.com/avatar.png"

        api._http = MagicMock()
        api._http.get.side_effect = Exception("connection failed")

        with patch("ui.api.images.get_cached_avatar", return_value=None):
            api._images.get_avatar("ErrUser")

        assert len(capture_eval_js.calls) == 0
        assert "twitch:erruser" not in api._fetching_avatars

    def test_dedup_second_call_skipped(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _create_api()
        api._eval_js = capture_eval_js

        submit_calls: list[Any] = []
        api._image_pool.submit = lambda fn: submit_calls.append(fn)

        api._images.get_avatar("DedupUser")
        api._images.get_avatar("DedupUser")

        # Only one submit call should have happened
        assert len(submit_calls) == 1

    def test_dedup_cleaned_after_completion(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _create_api()
        api._eval_js = capture_eval_js
        api._image_pool.submit = lambda fn: fn()

        with patch("ui.api.images.get_cached_avatar", return_value=None):
            api._images.get_avatar("CleanUser")

        assert "twitch:cleanuser" not in api._fetching_avatars

    def test_pool_shutdown_cleans_dedup(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _create_api()
        api._eval_js = capture_eval_js
        api._image_pool.submit = MagicMock(side_effect=RuntimeError("pool shut down"))

        api._images.get_avatar("ShutdownUser")

        assert "twitch:shutdownuser" not in api._fetching_avatars

    def test_platform_parameter_in_dedup_key(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _create_api()
        api._eval_js = capture_eval_js

        submit_calls: list[Any] = []
        api._image_pool.submit = lambda fn: submit_calls.append(fn)

        api._images.get_avatar("SameUser", platform="twitch")
        api._images.get_avatar("SameUser", platform="kick")

        # Different platforms, so both should submit
        assert len(submit_calls) == 2

    def test_login_lowercased(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _create_api()
        api._eval_js = capture_eval_js
        api._image_pool.submit = lambda fn: fn()

        cached_bytes = _make_png()
        with patch("ui.api.images.get_cached_avatar", return_value=cached_bytes):
            api._images.get_avatar("MiXeDcAsE")

        capture_eval_js.assert_any("onAvatar")
        payload = capture_eval_js.calls[0]
        assert "mixedcase" in payload
        assert "MiXeDcAsE" not in payload


# ──────────────────────────────────────────────────────────────
# Thumbnail tests
# ──────────────────────────────────────────────────────────────


class TestGetThumbnail:
    def test_success_emits_on_thumbnail(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _create_api()
        api._eval_js = capture_eval_js
        api._image_pool.submit = lambda fn: fn()

        raw_png = _make_png(640, 360)
        mock_resp = MagicMock()
        mock_resp.content = raw_png
        api._http = MagicMock()
        api._http.get.return_value = mock_resp

        api._images.get_thumbnail("thumbuser", "https://example.com/thumb.jpg")

        capture_eval_js.assert_any("onThumbnail")
        assert "thumbuser" in capture_eval_js.calls[0]
        assert "data:image/jpeg;base64," in capture_eval_js.calls[0]

    def test_resizes_to_jpeg(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _create_api()
        api._eval_js = capture_eval_js
        api._image_pool.submit = lambda fn: fn()

        raw_png = _make_png(1920, 1080)
        mock_resp = MagicMock()
        mock_resp.content = raw_png
        api._http = MagicMock()
        api._http.get.return_value = mock_resp

        api._images.get_thumbnail("resizeuser", "https://example.com/thumb.jpg")

        capture_eval_js.assert_any("onThumbnail")
        call = capture_eval_js.calls[0]
        json_start = call.index("{")
        json_end = call.rindex("}") + 1
        data = json.loads(call[json_start:json_end])
        assert data["login"] == "resizeuser"
        assert data["data"].startswith("data:image/jpeg;base64,")

    def test_network_error_logs_and_cleans_dedup(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _create_api()
        api._eval_js = capture_eval_js
        api._image_pool.submit = lambda fn: fn()

        api._http = MagicMock()
        api._http.get.side_effect = Exception("timeout")

        api._images.get_thumbnail("errthumb", "https://example.com/thumb.jpg")

        assert len(capture_eval_js.calls) == 0
        assert "errthumb" not in api._fetching_thumbnails

    def test_dedup_second_call_skipped(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _create_api()
        api._eval_js = capture_eval_js

        submit_calls: list[Any] = []
        api._image_pool.submit = lambda fn: submit_calls.append(fn)

        api._images.get_thumbnail("dedupthumb", "https://example.com/thumb.jpg")
        api._images.get_thumbnail("dedupthumb", "https://example.com/thumb.jpg")

        assert len(submit_calls) == 1

    def test_dedup_cleaned_after_completion(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _create_api()
        api._eval_js = capture_eval_js
        api._image_pool.submit = lambda fn: fn()

        raw_png = _make_png(200, 200)
        mock_resp = MagicMock()
        mock_resp.content = raw_png
        api._http = MagicMock()
        api._http.get.return_value = mock_resp

        api._images.get_thumbnail("cleanthumb", "https://example.com/thumb.jpg")

        assert "cleanthumb" not in api._fetching_thumbnails

    def test_pool_shutdown_cleans_dedup(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _create_api()
        api._eval_js = capture_eval_js
        api._image_pool.submit = MagicMock(side_effect=RuntimeError("pool shut down"))

        api._images.get_thumbnail("shutthumb", "https://example.com/thumb.jpg")

        assert "shutthumb" not in api._fetching_thumbnails

    def test_login_preserved_as_is(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        """Thumbnail does not lowercase login (unlike avatar)."""
        api = _create_api()
        api._eval_js = capture_eval_js
        api._image_pool.submit = lambda fn: fn()

        raw_png = _make_png(200, 200)
        mock_resp = MagicMock()
        mock_resp.content = raw_png
        api._http = MagicMock()
        api._http.get.return_value = mock_resp

        api._images.get_thumbnail("MixedCase", "https://example.com/thumb.jpg")

        capture_eval_js.assert_any("onThumbnail")
        assert "MixedCase" in capture_eval_js.calls[0]
