from __future__ import annotations

import asyncio
import json
import time
import webbrowser

import httpx

from core.oauth_server import wait_for_oauth_code
from core.platforms.kick import OAUTH_SCOPE as KICK_OAUTH_SCOPE
from core.platforms.youtube import YOUTUBE_API_URL
from core.storage import get_platform_config, update_config

from ._base import BaseApiComponent


class AuthComponent(BaseApiComponent):
    """OAuth authentication for all platforms."""

    # ── Twitch ──────────────────────────────────────────────────

    def login(self) -> None:
        twitch_conf = self._get_twitch_config()
        if not twitch_conf.get("client_id") or not twitch_conf.get("client_secret"):
            self._eval_js(
                'window.onLoginError("Set API credentials in Settings first")'
            )
            return
        auth_url = self._twitch.get_auth_url()
        self._api._data.stop_polling()
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
                self._api._data.restart_polling()
                return
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                token_data = loop.run_until_complete(self._twitch.exchange_code(code))
                access_token = token_data["access_token"]
                refresh_token = token_data.get("refresh_token", "")
                expires_at = int(time.time()) + token_data.get("expires_in", 3600)

                def _save_tokens(cfg: dict) -> None:
                    tc = cfg.get("platforms", {}).get("twitch", {})
                    tc["access_token"] = access_token
                    tc["refresh_token"] = refresh_token
                    tc["token_expires_at"] = expires_at
                    tc["token_type"] = "user"

                self._config = update_config(_save_tokens)

                user = loop.run_until_complete(self._twitch.get_current_user())
                uid = user["id"]
                ulogin = user["login"]
                udisplay = user.get("display_name", user["login"])

                def _save_user(cfg: dict) -> None:
                    tc = cfg.get("platforms", {}).get("twitch", {})
                    tc["user_id"] = uid
                    tc["user_login"] = ulogin
                    tc["user_display_name"] = udisplay

                self._config = update_config(_save_user)

                self._api._current_user = user
                avatar_url = user.get("profile_image_url", "")
                result = json.dumps(
                    {
                        "display_name": user.get("display_name", user["login"]),
                        "login": user["login"],
                        "avatar_url": avatar_url,
                    }
                )
                self._eval_js(f"window.onLoginComplete({result})")
                if avatar_url:
                    self._api._images.get_avatar(user["login"].lower())
                self._api._data.refresh()
            except Exception as e:
                msg = str(e)[:80] if str(e) else "Login failed"
                safe_msg = json.dumps(msg)
                self._eval_js(f"window.onLoginError({safe_msg})")
                self._api._data.restart_polling()
            finally:
                self._api._close_thread_loop(loop)

        self._run_in_thread(do_login)

    def logout(self) -> None:
        def _clear(cfg: dict) -> None:
            tc = cfg.get("platforms", {}).get("twitch", {})
            tc["access_token"] = ""
            tc["refresh_token"] = ""
            tc["token_expires_at"] = 0
            tc["token_type"] = "app"
            tc["user_id"] = ""
            tc["user_login"] = ""
            tc["user_display_name"] = ""

        self._config = update_config(_clear)
        self._api._current_user = None
        self._eval_js("window.onLogout()")

    # ── Kick ────────────────────────────────────────────────────

    def kick_login(self, client_id: str = "", client_secret: str = "") -> None:
        kick_conf = self._get_kick_config()
        if client_id.strip() and client_secret.strip():
            cid = client_id.strip()
            csec = client_secret.strip()

            def _save_creds(cfg: dict) -> None:
                kc = cfg.get("platforms", {}).get("kick", {})
                kc["client_id"] = cid
                kc["client_secret"] = csec

            self._config = update_config(_save_creds)
            kick_conf = self._get_kick_config()
        if not kick_conf.get("client_id") or not kick_conf.get("client_secret"):
            self._eval_js("window.onKickNeedsCredentials()")
            return
        auth_url = self._kick.get_auth_url()
        self._api._data.stop_polling()
        self._eval_js(
            "window.onStatusUpdate({text: 'Waiting for Kick login...', type: 'warn'})"
        )

        def do_login() -> None:
            webbrowser.open(auth_url)
            code = wait_for_oauth_code()
            if self._shutdown.is_set():
                return
            if code is None:
                self._eval_js('window.onKickLoginError("Login timed out")')
                self._api._data.restart_polling()
                return
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                token_data = loop.run_until_complete(self._kick.exchange_code(code))
                access_token = token_data["access_token"]
                refresh_token = token_data.get("refresh_token", "")
                expires_at = int(time.time()) + token_data.get("expires_in", 3600)
                oauth_scopes = token_data.get("scope", KICK_OAUTH_SCOPE)

                def _save_kick_tokens(cfg: dict) -> None:
                    kc = cfg.get("platforms", {}).get("kick", {})
                    kc["access_token"] = access_token
                    kc["refresh_token"] = refresh_token
                    kc["token_expires_at"] = expires_at
                    kc["oauth_scopes"] = oauth_scopes

                self._config = update_config(_save_kick_tokens)

                user = loop.run_until_complete(self._kick.get_current_user())
                uid = str(user.get("user_id", user.get("id", "")))
                ulogin = user.get("slug", user.get("username", ""))
                udisplay = user.get("name", user.get("username", ulogin))

                def _save_kick_user(cfg: dict) -> None:
                    kc = cfg.get("platforms", {}).get("kick", {})
                    kc["user_id"] = uid
                    kc["user_login"] = ulogin
                    kc["user_display_name"] = udisplay

                self._config = update_config(_save_kick_user)

                result = json.dumps(
                    {
                        "platform": "kick",
                        "display_name": udisplay,
                        "login": ulogin,
                        "scopes": oauth_scopes,
                    }
                )
                self._eval_js(f"window.onKickLoginComplete({result})")
                self._api._data.refresh()
            except Exception as e:
                msg = str(e)[:80] if str(e) else "Kick login failed"
                safe_msg = json.dumps(msg)
                self._eval_js(f"window.onKickLoginError({safe_msg})")
                self._api._data.restart_polling()
            finally:
                self._api._close_thread_loop(loop)

        self._run_in_thread(do_login)

    def kick_logout(self) -> None:
        def _clear(cfg: dict) -> None:
            kc = cfg.get("platforms", {}).get("kick", {})
            kc["access_token"] = ""
            kc["refresh_token"] = ""
            kc["token_expires_at"] = 0
            kc["oauth_scopes"] = ""
            kc["pkce_verifier"] = ""
            kc["oauth_state"] = ""
            kc["user_id"] = ""
            kc["user_login"] = ""
            kc["user_display_name"] = ""

        self._config = update_config(_clear)
        self._eval_js("window.onKickLogout()")

    # ── YouTube ─────────────────────────────────────────────────

    def youtube_login(self, client_id: str = "", client_secret: str = "") -> None:
        yt_conf = self._get_youtube_config()
        if client_id.strip() and client_secret.strip():
            cid = client_id.strip()
            csec = client_secret.strip()

            def _save_creds(cfg: dict) -> None:
                yc = cfg.get("platforms", {}).get("youtube", {})
                yc["client_id"] = cid
                yc["client_secret"] = csec

            self._config = update_config(_save_creds)
            yt_conf = self._get_youtube_config()
        if not yt_conf.get("client_id") or not yt_conf.get("client_secret"):
            self._eval_js("window.onYouTubeNeedsCredentials()")
            return
        auth_url = self._youtube.get_auth_url()
        self._api._data.stop_polling()
        self._eval_js(
            "window.onStatusUpdate({text: 'Waiting for YouTube login...', type: 'warn'})"
        )

        def do_login() -> None:
            webbrowser.open(auth_url)
            code = wait_for_oauth_code()
            if self._shutdown.is_set():
                return
            if code is None:
                self._eval_js('window.onYouTubeLoginError("Login timed out")')
                self._api._data.restart_polling()
                return
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                token_data = loop.run_until_complete(self._youtube.exchange_code(code))
                access_token = token_data["access_token"]
                refresh_token = token_data.get("refresh_token", "")
                expires_at = int(time.time()) + token_data.get("expires_in", 3600)

                def _save_tokens(cfg: dict) -> None:
                    yc = cfg.get("platforms", {}).get("youtube", {})
                    yc["access_token"] = access_token
                    yc["refresh_token"] = refresh_token
                    yc["token_expires_at"] = expires_at

                self._config = update_config(_save_tokens)

                user = loop.run_until_complete(self._youtube.get_current_user())
                uid = user.get("id", "")
                ulogin = user.get("login", "")
                udisplay = user.get("display_name", ulogin)

                def _save_user(cfg: dict) -> None:
                    yc = cfg.get("platforms", {}).get("youtube", {})
                    yc["user_id"] = uid
                    yc["user_login"] = ulogin
                    yc["user_display_name"] = udisplay

                self._config = update_config(_save_user)

                result = json.dumps(
                    {
                        "platform": "youtube",
                        "display_name": udisplay,
                        "login": ulogin,
                    }
                )
                self._eval_js(f"window.onYouTubeLoginComplete({result})")
                self._api._data.refresh()
            except Exception as e:
                msg = str(e)[:80] if str(e) else "YouTube login failed"
                safe_msg = json.dumps(msg)
                self._eval_js(f"window.onYouTubeLoginError({safe_msg})")
                self._api._data.restart_polling()
            finally:
                self._api._close_thread_loop(loop)

        self._run_in_thread(do_login)

    def youtube_logout(self) -> None:
        def _clear(cfg: dict) -> None:
            yc = cfg.get("platforms", {}).get("youtube", {})
            yc["access_token"] = ""
            yc["refresh_token"] = ""
            yc["token_expires_at"] = 0
            yc["user_id"] = ""
            yc["user_login"] = ""
            yc["user_display_name"] = ""

        self._config = update_config(_clear)
        self._eval_js("window.onYouTubeLogout()")

    # ── Connection tests ────────────────────────────────────────

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

    def kick_test_connection(self, client_id: str, client_secret: str) -> None:
        def do_test() -> None:
            try:
                resp = httpx.post(
                    "https://id.kick.com/oauth/token",
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
            self._eval_js(f"window.onKickTestResult({result})")

        self._run_in_thread(do_test)

    def youtube_test_connection(self, api_key: str = "") -> None:
        if not api_key:
            api_key = get_platform_config(self._config, "youtube").get("api_key", "")
        if not api_key:
            self._eval_js(
                "window.onYouTubeTestResult("
                + json.dumps({"success": False, "message": "No API key configured"})
                + ")"
            )
            return

        def do_test() -> None:
            try:
                resp = httpx.get(
                    f"{YOUTUBE_API_URL}/videos",
                    params={
                        "part": "snippet",
                        "id": "dQw4w9WgXcQ",
                        "key": api_key.strip(),
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    result = json.dumps({"success": True, "message": "Connected"})
                elif resp.status_code == 403:
                    result = json.dumps(
                        {
                            "success": False,
                            "message": "API key invalid or quota exceeded",
                        }
                    )
                else:
                    result = json.dumps(
                        {"success": False, "message": f"HTTP {resp.status_code}"}
                    )
            except httpx.ConnectError:
                result = json.dumps(
                    {"success": False, "message": "No internet connection"}
                )
            except Exception as exc:
                msg = str(exc)[:60]
                result = json.dumps({"success": False, "message": msg})
            self._eval_js(f"window.onYouTubeTestResult({result})")

        self._run_in_thread(do_test)
