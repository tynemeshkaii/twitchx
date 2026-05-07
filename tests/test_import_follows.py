from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

from core.storage import load_config, update_config
from ui.api import TwitchXApi


class TestTwitchImport:
    def test_import_adds_new_favorites(
        self,
        temp_config_dir: Path,
        run_sync: None,
        capture_eval_js: Any,
    ) -> None:
        api = TwitchXApi()
        api._eval_js = capture_eval_js

        cfg = load_config()
        assert len(cfg.get("favorites", [])) == 0

        api._current_user = {"id": "123", "login": "testuser"}
        api._twitch.get_followed_channels = AsyncMock(return_value=["new1", "new2"])
        api.import_follows()

        cfg = load_config()
        twitch_favs = [f for f in cfg["favorites"] if f["platform"] == "twitch"]
        assert len(twitch_favs) == 2
        names = {f["login"] for f in twitch_favs}
        assert names == {"new1", "new2"}
        capture_eval_js.assert_any("onImportComplete")

    def test_import_skips_existing(
        self,
        temp_config_dir: Path,
        run_sync: None,
        capture_eval_js: Any,
    ) -> None:
        api = TwitchXApi()
        api._eval_js = capture_eval_js

        def _add_existing(cfg: dict) -> None:
            cfg["favorites"].append(
                {
                    "platform": "twitch",
                    "login": "streamer1",
                    "display_name": "Streamer1",
                }
            )

        update_config(_add_existing)

        api._current_user = {"id": "123", "login": "testuser"}
        api._twitch.get_followed_channels = AsyncMock(
            return_value=["streamer1", "new1"]
        )
        api.import_follows()

        cfg = load_config()
        twitch_favs = [f for f in cfg["favorites"] if f["platform"] == "twitch"]
        assert len(twitch_favs) == 2
        names = {f["login"] for f in twitch_favs}
        assert names == {"streamer1", "new1"}

        capture_eval_js.assert_any("onImportComplete")
        import_call = [c for c in capture_eval_js.calls if "onImportComplete" in c]
        assert len(import_call) == 1
        data = json.loads(import_call[0].split("onImportComplete(")[1].rstrip(")"))
        assert data["added"] == 1

    def test_import_not_logged_in(
        self,
        temp_config_dir: Path,
        run_sync: None,
        capture_eval_js: Any,
    ) -> None:
        api = TwitchXApi()
        api._eval_js = capture_eval_js
        api.import_follows()
        capture_eval_js.assert_any("onImportError")

    def test_import_silent_no_current_user(
        self,
        temp_config_dir: Path,
        run_sync: None,
        capture_eval_js: Any,
    ) -> None:
        api = TwitchXApi()
        api._eval_js = capture_eval_js
        api._favorites.import_follows(silent=True)
        error_calls = [c for c in capture_eval_js.calls if "onImportError" in c]
        assert len(error_calls) == 0

    def test_import_silent_skips_status(
        self,
        temp_config_dir: Path,
        run_sync: None,
        capture_eval_js: Any,
    ) -> None:
        api = TwitchXApi()
        api._eval_js = capture_eval_js
        api._current_user = {"id": "123", "login": "testuser"}
        api._twitch.get_followed_channels = AsyncMock(return_value=[])
        api._favorites.import_follows(silent=True)
        status_calls = [c for c in capture_eval_js.calls if "onStatusUpdate" in c]
        assert len(status_calls) == 0
        complete_calls = [c for c in capture_eval_js.calls if "onImportComplete" in c]
        assert len(complete_calls) == 0

    def test_import_silent_with_adds(
        self,
        temp_config_dir: Path,
        run_sync: None,
        capture_eval_js: Any,
    ) -> None:
        api = TwitchXApi()
        api._eval_js = capture_eval_js
        api._current_user = {"id": "123", "login": "testuser"}
        api._twitch.get_followed_channels = AsyncMock(return_value=["new_ch"])
        api._favorites.import_follows(silent=True)
        capture_eval_js.assert_any("onImportComplete")


class TestYouTubeImport:
    def test_youtube_import_adds_new(
        self,
        temp_config_dir: Path,
        run_sync: None,
        capture_eval_js: Any,
        mock_youtube_client: Any,
    ) -> None:
        def _add_yt_creds(cfg: dict) -> None:
            cfg["platforms"]["youtube"]["access_token"] = "test-token"

        update_config(_add_yt_creds)

        api = TwitchXApi()
        api._youtube = mock_youtube_client
        api._eval_js = capture_eval_js
        api.youtube_import_follows()

        cfg = load_config()
        yt_favs = [f for f in cfg["favorites"] if f["platform"] == "youtube"]
        assert len(yt_favs) == 2
        names = {f["login"] for f in yt_favs}
        assert names == {"UCaaaaaaaaaaaaaaaaaaaaaa", "UCbbbbbbbbbbbbbbbbbbbbbb"}
        capture_eval_js.assert_any("onYouTubeImportComplete")

    def test_youtube_import_not_logged_in(
        self,
        temp_config_dir: Path,
        run_sync: None,
        capture_eval_js: Any,
    ) -> None:
        api = TwitchXApi()
        api._eval_js = capture_eval_js
        api.youtube_import_follows()
        capture_eval_js.assert_any("onYouTubeImportError")

    def test_youtube_import_silent(
        self,
        temp_config_dir: Path,
        run_sync: None,
        capture_eval_js: Any,
        mock_youtube_client: Any,
    ) -> None:
        def _add_yt_creds(cfg: dict) -> None:
            cfg["platforms"]["youtube"]["access_token"] = "test-token"

        update_config(_add_yt_creds)

        api = TwitchXApi()
        api._youtube = mock_youtube_client
        api._eval_js = capture_eval_js
        api._favorites.youtube_import_follows(silent=True)
        capture_eval_js.assert_any("onYouTubeImportComplete")

    def test_youtube_import_silent_not_logged_in(
        self,
        temp_config_dir: Path,
        run_sync: None,
        capture_eval_js: Any,
    ) -> None:
        api = TwitchXApi()
        api._eval_js = capture_eval_js
        api._favorites.youtube_import_follows(silent=True)
        error_calls = [c for c in capture_eval_js.calls if "onYouTubeImportError" in c]
        assert len(error_calls) == 0
