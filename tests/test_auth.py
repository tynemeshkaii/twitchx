# pyright: reportAttributeAccessIssue=false
"""Tests for ui/api/auth.py — OAuth login/logout and connection tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from core.storage import load_config
from ui.api import TwitchXApi

# ── Helpers ────────────────────────────────────────────────────────


def _make_api(
    capture_eval_js: Any,
    mock_twitch: MagicMock | None = None,
    mock_kick: MagicMock | None = None,
    mock_youtube: MagicMock | None = None,
) -> TwitchXApi:
    """Build a TwitchXApi with mocked sub-components and platform clients."""
    with patch("ui.api.httpx.Client"):
        api = TwitchXApi()
    api._eval_js = capture_eval_js

    if mock_twitch is not None:
        api._twitch = mock_twitch
        api._platforms["twitch"] = mock_twitch
    if mock_kick is not None:
        api._kick = mock_kick
        api._platforms["kick"] = mock_kick
    if mock_youtube is not None:
        api._youtube = mock_youtube
        api._platforms["youtube"] = mock_youtube

    # Mock sub-components that login methods call into
    api._data = MagicMock()
    api._data.stop_polling = MagicMock()
    api._data.restart_polling = MagicMock()
    api._data.refresh = MagicMock()
    api._favorites = MagicMock()
    api._favorites.import_follows = MagicMock()
    api._favorites.youtube_import_follows = MagicMock()
    api._images = MagicMock()
    api._images.get_avatar = MagicMock()

    # Re-create auth component so it picks up the new platform clients
    from ui.api.auth import AuthComponent

    api._auth = AuthComponent(api)

    return api


# ═══════════════════════════════════════════════════════════════════
# Twitch login
# ═══════════════════════════════════════════════════════════════════


class TestTwitchLogin:
    def test_login_success(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_twitch_client: MagicMock,
    ) -> None:
        mock_twitch_client.exchange_code = AsyncMock(
            return_value={
                "access_token": "new-tok",
                "refresh_token": "new-ref",
                "expires_in": 7200,
            }
        )
        mock_twitch_client.get_current_user = AsyncMock(
            return_value={
                "id": "12345",
                "login": "testuser",
                "display_name": "TestUser",
                "profile_image_url": "https://example.com/avatar.png",
            }
        )
        # close_loop_resources needed by _close_thread_loop
        mock_twitch_client.close_loop_resources = AsyncMock()

        api = _make_api(capture_eval_js, mock_twitch=mock_twitch_client)

        with (
            patch("ui.api.auth.webbrowser.open"),
            patch("ui.api.auth.wait_for_oauth_code", return_value="auth-code-123"),
        ):
            api.login()

        capture_eval_js.assert_any("onLoginComplete")
        # Verify tokens saved
        cfg = load_config()
        tc = cfg["platforms"]["twitch"]
        assert tc["access_token"] == "new-tok"
        assert tc["refresh_token"] == "new-ref"
        assert tc["token_type"] == "user"
        assert tc["user_id"] == "12345"
        assert tc["user_login"] == "testuser"
        assert tc["user_display_name"] == "TestUser"
        # Verify post-login actions
        api._images.get_avatar.assert_called_once_with("testuser")
        api._data.refresh.assert_called_once()
        api._favorites.import_follows.assert_called_once_with(silent=True)

    def test_login_timeout(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_twitch_client: MagicMock,
    ) -> None:
        api = _make_api(capture_eval_js, mock_twitch=mock_twitch_client)

        with (
            patch("ui.api.auth.webbrowser.open"),
            patch("ui.api.auth.wait_for_oauth_code", return_value=None),
        ):
            api.login()

        capture_eval_js.assert_any("onLoginError")
        capture_eval_js.assert_any("Login timed out")
        api._data.restart_polling.assert_called_once()

    def test_login_shutdown(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_twitch_client: MagicMock,
    ) -> None:
        api = _make_api(capture_eval_js, mock_twitch=mock_twitch_client)
        api._shutdown.set()

        with (
            patch("ui.api.auth.webbrowser.open"),
            patch("ui.api.auth.wait_for_oauth_code", return_value=None),
        ):
            api.login()

        # No callbacks should fire after shutdown
        assert not any(
            "onLoginError" in c
            for c in capture_eval_js.calls
            if "onStatusUpdate" not in c
        )

    def test_login_exchange_exception(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_twitch_client: MagicMock,
    ) -> None:
        mock_twitch_client.exchange_code = AsyncMock(
            side_effect=Exception("Token exchange failed")
        )
        mock_twitch_client.close_loop_resources = AsyncMock()

        api = _make_api(capture_eval_js, mock_twitch=mock_twitch_client)

        with (
            patch("ui.api.auth.webbrowser.open"),
            patch("ui.api.auth.wait_for_oauth_code", return_value="code"),
        ):
            api.login()

        capture_eval_js.assert_any("onLoginError")
        capture_eval_js.assert_any("Token exchange failed")
        api._data.restart_polling.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# Twitch logout
# ═══════════════════════════════════════════════════════════════════


class TestTwitchLogout:
    def test_logout_clears_tokens(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _make_api(capture_eval_js)
        api.logout()

        capture_eval_js.assert_any("onLogout")
        cfg = load_config()
        tc = cfg["platforms"]["twitch"]
        assert tc["access_token"] == ""
        assert tc["refresh_token"] == ""
        assert tc["token_type"] == "app"
        assert tc["user_id"] == ""
        assert tc["user_login"] == ""
        assert api._current_user is None


# ═══════════════════════════════════════════════════════════════════
# Kick login
# ═══════════════════════════════════════════════════════════════════


class TestKickLogin:
    def test_kick_login_success_with_custom_creds(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_kick_client: MagicMock,
    ) -> None:
        mock_kick_client.exchange_code = AsyncMock(
            return_value={
                "access_token": "kick-tok",
                "refresh_token": "kick-ref",
                "expires_in": 3600,
                "scope": "user:read",
            }
        )
        mock_kick_client.get_current_user = AsyncMock(
            return_value={
                "user_id": 999,
                "slug": "kickuser",
                "name": "KickUser",
            }
        )
        mock_kick_client.close_loop_resources = AsyncMock()

        api = _make_api(capture_eval_js, mock_kick=mock_kick_client)

        with (
            patch("ui.api.auth.webbrowser.open"),
            patch("ui.api.auth.wait_for_oauth_code", return_value="kick-code"),
        ):
            api.kick_login(client_id="  my-cid  ", client_secret="  my-csec  ")

        capture_eval_js.assert_any("onKickLoginComplete")
        cfg = load_config()
        kc = cfg["platforms"]["kick"]
        assert kc["client_id"] == "my-cid"
        assert kc["client_secret"] == "my-csec"
        assert kc["access_token"] == "kick-tok"
        assert kc["user_id"] == "999"
        assert kc["user_login"] == "kickuser"
        api._data.refresh.assert_called_once()

    def test_kick_login_timeout(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_kick_client: MagicMock,
    ) -> None:
        api = _make_api(capture_eval_js, mock_kick=mock_kick_client)

        with (
            patch("ui.api.auth.webbrowser.open"),
            patch("ui.api.auth.wait_for_oauth_code", return_value=None),
        ):
            api.kick_login()

        capture_eval_js.assert_any("onKickLoginError")
        capture_eval_js.assert_any("Login timed out")
        api._data.restart_polling.assert_called_once()

    def test_kick_login_exception(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_kick_client: MagicMock,
    ) -> None:
        mock_kick_client.exchange_code = AsyncMock(
            side_effect=RuntimeError("Kick OAuth boom")
        )
        mock_kick_client.close_loop_resources = AsyncMock()

        api = _make_api(capture_eval_js, mock_kick=mock_kick_client)

        with (
            patch("ui.api.auth.webbrowser.open"),
            patch("ui.api.auth.wait_for_oauth_code", return_value="code"),
        ):
            api.kick_login()

        capture_eval_js.assert_any("onKickLoginError")
        capture_eval_js.assert_any("Kick OAuth boom")
        api._data.restart_polling.assert_called_once()

    def test_kick_login_shutdown(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_kick_client: MagicMock,
    ) -> None:
        api = _make_api(capture_eval_js, mock_kick=mock_kick_client)
        api._shutdown.set()

        with (
            patch("ui.api.auth.webbrowser.open"),
            patch("ui.api.auth.wait_for_oauth_code", return_value=None),
        ):
            api.kick_login()

        assert not any("onKickLoginError" in c for c in capture_eval_js.calls)


# ═══════════════════════════════════════════════════════════════════
# Kick logout
# ═══════════════════════════════════════════════════════════════════


class TestKickLogout:
    def test_kick_logout_clears_fields(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _make_api(capture_eval_js)
        api.kick_logout()

        capture_eval_js.assert_any("onKickLogout")
        cfg = load_config()
        kc = cfg["platforms"]["kick"]
        assert kc["access_token"] == ""
        assert kc["refresh_token"] == ""
        assert kc["user_id"] == ""
        assert kc["user_login"] == ""
        assert kc["oauth_scopes"] == ""


# ═══════════════════════════════════════════════════════════════════
# YouTube login
# ═══════════════════════════════════════════════════════════════════


class TestYouTubeLogin:
    def test_youtube_login_success(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_youtube_client: MagicMock,
    ) -> None:
        mock_youtube_client.get_auth_url = MagicMock(
            return_value="https://accounts.google.com/o/oauth2/v2/auth?..."
        )
        mock_youtube_client.exchange_code = AsyncMock(
            return_value={
                "access_token": "yt-tok",
                "refresh_token": "yt-ref",
                "expires_in": 3600,
            }
        )
        mock_youtube_client.get_current_user = AsyncMock(
            return_value={
                "id": "UC123",
                "login": "ytchannel",
                "display_name": "YTChannel",
            }
        )
        mock_youtube_client.close_loop_resources = AsyncMock()

        api = _make_api(capture_eval_js, mock_youtube=mock_youtube_client)

        with (
            patch("ui.api.auth.webbrowser.open"),
            patch("ui.api.auth.wait_for_oauth_code", return_value="yt-code"),
        ):
            api.youtube_login(client_id="yt-cid", client_secret="yt-csec")

        capture_eval_js.assert_any("onYouTubeLoginComplete")
        cfg = load_config()
        yc = cfg["platforms"]["youtube"]
        assert yc["access_token"] == "yt-tok"
        assert yc["refresh_token"] == "yt-ref"
        assert yc["client_id"] == "yt-cid"
        assert yc["client_secret"] == "yt-csec"
        assert yc["user_id"] == "UC123"
        assert yc["user_login"] == "ytchannel"
        api._data.refresh.assert_called_once()
        api._favorites.youtube_import_follows.assert_called_once_with(silent=True)

    def test_youtube_login_timeout(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_youtube_client: MagicMock,
    ) -> None:
        mock_youtube_client.get_auth_url = MagicMock(
            return_value="https://accounts.google.com/..."
        )
        api = _make_api(capture_eval_js, mock_youtube=mock_youtube_client)

        with (
            patch("ui.api.auth.webbrowser.open"),
            patch("ui.api.auth.wait_for_oauth_code", return_value=None),
        ):
            api.youtube_login()

        capture_eval_js.assert_any("onYouTubeLoginError")
        capture_eval_js.assert_any("Login timed out")
        api._data.restart_polling.assert_called_once()

    def test_youtube_login_exception(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_youtube_client: MagicMock,
    ) -> None:
        mock_youtube_client.get_auth_url = MagicMock(
            return_value="https://accounts.google.com/..."
        )
        mock_youtube_client.exchange_code = AsyncMock(
            side_effect=Exception("YouTube OAuth error")
        )
        mock_youtube_client.close_loop_resources = AsyncMock()

        api = _make_api(capture_eval_js, mock_youtube=mock_youtube_client)

        with (
            patch("ui.api.auth.webbrowser.open"),
            patch("ui.api.auth.wait_for_oauth_code", return_value="code"),
        ):
            api.youtube_login()

        capture_eval_js.assert_any("onYouTubeLoginError")
        capture_eval_js.assert_any("YouTube OAuth error")
        api._data.restart_polling.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# YouTube logout
# ═══════════════════════════════════════════════════════════════════


class TestYouTubeLogout:
    def test_youtube_logout_clears_fields(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        api = _make_api(capture_eval_js)
        api.youtube_logout()

        capture_eval_js.assert_any("onYouTubeLogout")
        cfg = load_config()
        yc = cfg["platforms"]["youtube"]
        assert yc["access_token"] == ""
        assert yc["refresh_token"] == ""
        assert yc["user_id"] == ""
        assert yc["user_login"] == ""


# ═══════════════════════════════════════════════════════════════════
# test_connection (Twitch)
# ═══════════════════════════════════════════════════════════════════


class TestTwitchTestConnection:
    def test_success(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_twitch_client: MagicMock,
    ) -> None:
        mock_twitch_client._effective_creds = MagicMock(return_value=("cid", "csec"))
        api = _make_api(capture_eval_js, mock_twitch=mock_twitch_client)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("ui.api.auth.httpx.post", return_value=mock_resp):
            api.test_connection("cid", "csec")

        capture_eval_js.assert_any("onTestResult")
        # Parse the result
        call = [c for c in capture_eval_js.calls if "onTestResult" in c][0]
        data = json.loads(call.split("onTestResult(")[1].rstrip(")"))
        assert data["success"] is True
        assert data["message"] == "Connected"

    def test_invalid_credentials(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_twitch_client: MagicMock,
    ) -> None:
        mock_twitch_client._effective_creds = MagicMock(return_value=("cid", "csec"))
        api = _make_api(capture_eval_js, mock_twitch=mock_twitch_client)

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch("ui.api.auth.httpx.post", return_value=mock_resp):
            api.test_connection("bad-cid", "bad-csec")

        call = [c for c in capture_eval_js.calls if "onTestResult" in c][0]
        data = json.loads(call.split("onTestResult(")[1].rstrip(")"))
        assert data["success"] is False
        assert "Invalid credentials" in data["message"]

    def test_network_error(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_twitch_client: MagicMock,
    ) -> None:
        mock_twitch_client._effective_creds = MagicMock(return_value=("cid", "csec"))
        api = _make_api(capture_eval_js, mock_twitch=mock_twitch_client)

        with patch("ui.api.auth.httpx.post", side_effect=httpx.ConnectError("timeout")):
            api.test_connection("cid", "csec")

        call = [c for c in capture_eval_js.calls if "onTestResult" in c][0]
        data = json.loads(call.split("onTestResult(")[1].rstrip(")"))
        assert data["success"] is False
        assert "No internet" in data["message"]

    def test_generic_exception(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_twitch_client: MagicMock,
    ) -> None:
        mock_twitch_client._effective_creds = MagicMock(return_value=("cid", "csec"))
        api = _make_api(capture_eval_js, mock_twitch=mock_twitch_client)

        with patch("ui.api.auth.httpx.post", side_effect=RuntimeError("weird")):
            api.test_connection("cid", "csec")

        call = [c for c in capture_eval_js.calls if "onTestResult" in c][0]
        data = json.loads(call.split("onTestResult(")[1].rstrip(")"))
        assert data["success"] is False
        assert "weird" in data["message"]

    def test_uses_effective_creds_when_empty(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_twitch_client: MagicMock,
    ) -> None:
        mock_twitch_client._effective_creds = MagicMock(
            return_value=("fallback-cid", "fallback-csec")
        )
        api = _make_api(capture_eval_js, mock_twitch=mock_twitch_client)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("ui.api.auth.httpx.post", return_value=mock_resp) as mock_post:
            api.test_connection("", "")

        # Should have used fallback creds
        call_data = mock_post.call_args[1]["data"]
        assert call_data["client_id"] == "fallback-cid"
        assert call_data["client_secret"] == "fallback-csec"


# ═══════════════════════════════════════════════════════════════════
# kick_test_connection
# ═══════════════════════════════════════════════════════════════════


class TestKickTestConnection:
    def test_success(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_kick_client: MagicMock,
    ) -> None:
        mock_kick_client._effective_creds = MagicMock(return_value=("kcid", "kcsec"))
        api = _make_api(capture_eval_js, mock_kick=mock_kick_client)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("ui.api.auth.httpx.post", return_value=mock_resp):
            api.kick_test_connection("kcid", "kcsec")

        call = [c for c in capture_eval_js.calls if "onKickTestResult" in c][0]
        data = json.loads(call.split("onKickTestResult(")[1].rstrip(")"))
        assert data["success"] is True

    def test_invalid_credentials(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_kick_client: MagicMock,
    ) -> None:
        mock_kick_client._effective_creds = MagicMock(return_value=("kcid", "kcsec"))
        api = _make_api(capture_eval_js, mock_kick=mock_kick_client)

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch("ui.api.auth.httpx.post", return_value=mock_resp):
            api.kick_test_connection("kcid", "kcsec")

        call = [c for c in capture_eval_js.calls if "onKickTestResult" in c][0]
        data = json.loads(call.split("onKickTestResult(")[1].rstrip(")"))
        assert data["success"] is False

    def test_network_error(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_kick_client: MagicMock,
    ) -> None:
        mock_kick_client._effective_creds = MagicMock(return_value=("kcid", "kcsec"))
        api = _make_api(capture_eval_js, mock_kick=mock_kick_client)

        with patch("ui.api.auth.httpx.post", side_effect=httpx.ConnectError("err")):
            api.kick_test_connection("kcid", "kcsec")

        call = [c for c in capture_eval_js.calls if "onKickTestResult" in c][0]
        data = json.loads(call.split("onKickTestResult(")[1].rstrip(")"))
        assert data["success"] is False
        assert "No internet" in data["message"]


# ═══════════════════════════════════════════════════════════════════
# youtube_test_connection
# ═══════════════════════════════════════════════════════════════════


class TestYouTubeTestConnection:
    def test_success(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_youtube_client: MagicMock,
    ) -> None:
        mock_youtube_client._effective_api_key = MagicMock(return_value="yt-key")
        api = _make_api(capture_eval_js, mock_youtube=mock_youtube_client)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("ui.api.auth.httpx.get", return_value=mock_resp):
            api.youtube_test_connection("yt-key")

        call = [c for c in capture_eval_js.calls if "onYouTubeTestResult" in c][0]
        data = json.loads(call.split("onYouTubeTestResult(")[1].rstrip(")"))
        assert data["success"] is True
        assert data["message"] == "Connected"

    def test_no_api_key(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        mock_youtube_client: MagicMock,
    ) -> None:
        mock_youtube_client._effective_api_key = MagicMock(return_value="")
        api = _make_api(capture_eval_js, mock_youtube=mock_youtube_client)

        api.youtube_test_connection("")

        call = [c for c in capture_eval_js.calls if "onYouTubeTestResult" in c][0]
        data = json.loads(call.split("onYouTubeTestResult(")[1].rstrip(")"))
        assert data["success"] is False
        assert "No API key" in data["message"]

    def test_quota_exceeded_403(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_youtube_client: MagicMock,
    ) -> None:
        mock_youtube_client._effective_api_key = MagicMock(return_value="yt-key")
        api = _make_api(capture_eval_js, mock_youtube=mock_youtube_client)

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        with patch("ui.api.auth.httpx.get", return_value=mock_resp):
            api.youtube_test_connection("yt-key")

        call = [c for c in capture_eval_js.calls if "onYouTubeTestResult" in c][0]
        data = json.loads(call.split("onYouTubeTestResult(")[1].rstrip(")"))
        assert data["success"] is False
        assert (
            "quota" in data["message"].lower() or "invalid" in data["message"].lower()
        )

    def test_other_http_error(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_youtube_client: MagicMock,
    ) -> None:
        mock_youtube_client._effective_api_key = MagicMock(return_value="yt-key")
        api = _make_api(capture_eval_js, mock_youtube=mock_youtube_client)

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("ui.api.auth.httpx.get", return_value=mock_resp):
            api.youtube_test_connection("yt-key")

        call = [c for c in capture_eval_js.calls if "onYouTubeTestResult" in c][0]
        data = json.loads(call.split("onYouTubeTestResult(")[1].rstrip(")"))
        assert data["success"] is False
        assert "500" in data["message"]

    def test_network_error(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_youtube_client: MagicMock,
    ) -> None:
        mock_youtube_client._effective_api_key = MagicMock(return_value="yt-key")
        api = _make_api(capture_eval_js, mock_youtube=mock_youtube_client)

        with patch("ui.api.auth.httpx.get", side_effect=httpx.ConnectError("err")):
            api.youtube_test_connection("yt-key")

        call = [c for c in capture_eval_js.calls if "onYouTubeTestResult" in c][0]
        data = json.loads(call.split("onYouTubeTestResult(")[1].rstrip(")"))
        assert data["success"] is False
        assert "No internet" in data["message"]

    def test_generic_exception(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_youtube_client: MagicMock,
    ) -> None:
        mock_youtube_client._effective_api_key = MagicMock(return_value="yt-key")
        api = _make_api(capture_eval_js, mock_youtube=mock_youtube_client)

        with patch("ui.api.auth.httpx.get", side_effect=ValueError("parse error")):
            api.youtube_test_connection("yt-key")

        call = [c for c in capture_eval_js.calls if "onYouTubeTestResult" in c][0]
        data = json.loads(call.split("onYouTubeTestResult(")[1].rstrip(")"))
        assert data["success"] is False
        assert "parse error" in data["message"]


# ═══════════════════════════════════════════════════════════════════
# OAuth port busy / concurrent login guard
# ═══════════════════════════════════════════════════════════════════


class TestOAuthPortBusy:
    def test_port_busy_reports_error_and_restarts_polling(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_twitch_client: MagicMock,
    ) -> None:
        from core.oauth_server import OAuthPortBusy

        api = _make_api(capture_eval_js, mock_twitch=mock_twitch_client)

        with (
            patch("ui.api.auth.webbrowser.open"),
            patch(
                "ui.api.auth.wait_for_oauth_code",
                side_effect=OAuthPortBusy("port busy"),
            ),
        ):
            api.login()

        capture_eval_js.assert_any("onLoginError")
        capture_eval_js.assert_any("Another login is already in progress")
        api._data.restart_polling.assert_called_once()

    def test_kick_port_busy_restarts_polling(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_kick_client: MagicMock,
    ) -> None:
        from core.oauth_server import OAuthPortBusy

        api = _make_api(capture_eval_js, mock_kick=mock_kick_client)

        with (
            patch("ui.api.auth.webbrowser.open"),
            patch(
                "ui.api.auth.wait_for_oauth_code",
                side_effect=OAuthPortBusy("port busy"),
            ),
        ):
            api.kick_login()

        capture_eval_js.assert_any("onKickLoginError")
        api._data.restart_polling.assert_called_once()

    def test_youtube_port_busy_restarts_polling(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_youtube_client: MagicMock,
    ) -> None:
        from core.oauth_server import OAuthPortBusy

        api = _make_api(capture_eval_js, mock_youtube=mock_youtube_client)

        with (
            patch("ui.api.auth.webbrowser.open"),
            patch(
                "ui.api.auth.wait_for_oauth_code",
                side_effect=OAuthPortBusy("port busy"),
            ),
        ):
            api.youtube_login()

        capture_eval_js.assert_any("onYouTubeLoginError")
        api._data.restart_polling.assert_called_once()

    def test_second_login_while_first_in_progress_is_rejected(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        mock_twitch_client: MagicMock,
        mock_kick_client: MagicMock,
    ) -> None:
        api = _make_api(
            capture_eval_js,
            mock_twitch=mock_twitch_client,
            mock_kick=mock_kick_client,
        )
        # First login's worker thread never runs → flow stays "in progress"
        api._run_in_thread = lambda fn: None  # type: ignore[method-assign]

        api.login()
        api.kick_login()

        api._data.stop_polling.assert_called_once()
        capture_eval_js.assert_any("onKickLoginError")
        capture_eval_js.assert_any("Another login is already in progress")

    def test_lock_released_after_login_finishes(
        self,
        temp_config_dir: Path,
        capture_eval_js: Any,
        run_sync: Any,
        mock_twitch_client: MagicMock,
    ) -> None:
        api = _make_api(capture_eval_js, mock_twitch=mock_twitch_client)

        with (
            patch("ui.api.auth.webbrowser.open"),
            patch("ui.api.auth.wait_for_oauth_code", return_value=None),
        ):
            api.login()
            api.login()

        assert api._data.stop_polling.call_count == 2


# ═══════════════════════════════════════════════════════════════════
# OAuth state + platform-initiated revocation (audit phase 2)
# ═══════════════════════════════════════════════════════════════════


class TestOAuthState:
    def test_each_login_waits_for_its_own_state(
        self, temp_config_dir: Path, capture_eval_js: Any, run_sync: Any
    ) -> None:
        from urllib.parse import parse_qs, urlparse

        api = _make_api(capture_eval_js)
        for platform, start in (
            ("twitch", api.login),
            ("kick", api.kick_login),
            ("youtube", api.youtube_login),
        ):
            opened: list[str] = []
            with (
                patch("ui.api.auth.webbrowser.open", side_effect=opened.append),
                patch("ui.api.auth.wait_for_oauth_code", return_value=None) as wait,
            ):
                start()
            stored = load_config()["platforms"][platform]["oauth_state"]
            url_state = parse_qs(urlparse(opened[0]).query)["state"][0]
            assert stored and url_state == stored, platform
            wait.assert_called_once_with(expected_state=stored)

    async def test_exchange_clears_oauth_state(
        self, temp_config_dir: Path, httpx_mock: Any
    ) -> None:
        from core.platforms.twitch import TWITCH_AUTH_URL, TwitchClient

        client = TwitchClient()
        client.get_auth_url()
        assert load_config()["platforms"]["twitch"]["oauth_state"]
        httpx_mock.add_response(url=TWITCH_AUTH_URL, json={"access_token": "t"})
        await client.exchange_code("code")
        await client.close()
        tc = load_config()["platforms"]["twitch"]
        assert tc["oauth_state"] == ""
        assert tc["pkce_verifier"] == ""


class TestAuthRevoked:
    def test_twitch_revoked_resets_user_and_notifies_js(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        with patch("ui.api.httpx.Client"):
            api = TwitchXApi()
        api._eval_js = capture_eval_js
        api._run_in_thread = lambda fn: fn()
        api._current_user = {"id": "1", "login": "me"}

        api._twitch.on_auth_revoked()  # type: ignore[misc]

        assert api._current_user is None
        capture_eval_js.assert_any("onLogout")
        capture_eval_js.assert_any("Twitch session expired")
        capture_eval_js.assert_any("onConfigLoaded")

    def test_kick_revoked_notifies_js(
        self, temp_config_dir: Path, capture_eval_js: Any
    ) -> None:
        with patch("ui.api.httpx.Client"):
            api = TwitchXApi()
        api._eval_js = capture_eval_js
        api._run_in_thread = lambda fn: fn()

        api._kick.on_auth_revoked()  # type: ignore[misc]

        capture_eval_js.assert_any("onKickLogout")
        capture_eval_js.assert_any("Kick session expired")
