from __future__ import annotations

import os
import re
from pathlib import Path

import webview

from core.storage import load_config, save_config
from ui.api import TwitchXApi


class TwitchXApp:
    """pywebview-based TwitchX application."""

    def __init__(self) -> None:
        self._api = TwitchXApi()
        self._config = load_config()
        self._migrate_favorites()

    @staticmethod
    def _sanitize_username(raw: str) -> str:
        raw = raw.strip()
        match = re.search(r"(?:twitch\.tv/)([A-Za-z0-9_]+)", raw)
        if match:
            return match.group(1).lower()
        return re.sub(r"[^A-Za-z0-9_]", "", raw).lower()

    @staticmethod
    def _sanitize_favorite_login(raw: str, platform: str = "twitch") -> str:
        raw = raw.strip()
        if platform == "kick":
            match = re.search(r"(?:kick\.com/)([A-Za-z0-9_-]+)", raw, re.IGNORECASE)
            if match:
                return match.group(1).lower()
            return re.sub(r"[^A-Za-z0-9_-]", "", raw).lower()
        return TwitchXApp._sanitize_username(raw)

    def _migrate_favorites(self) -> None:
        raw = self._config.get("favorites", [])
        cleaned: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        changed = False
        for entry in raw:
            if isinstance(entry, str):
                # v1 legacy string — convert to v2 object
                name = self._sanitize_favorite_login(entry, "twitch")
                if not name:
                    changed = True
                    continue
                key = ("twitch", name)
                if key in seen:
                    changed = True
                    continue
                seen.add(key)
                cleaned.append(
                    {"platform": "twitch", "login": name, "display_name": name}
                )
                changed = True
            elif isinstance(entry, dict):
                login = entry.get("login", "")
                platform = entry.get("platform", "twitch")
                name = self._sanitize_favorite_login(login, platform) if login else ""
                if not name:
                    changed = True
                    continue
                key = (platform, name)
                if key in seen:
                    changed = True
                    continue
                seen.add(key)
                if name != login:
                    entry = {**entry, "login": name}
                    changed = True
                cleaned.append(entry)
            else:
                changed = True
        if changed:
            self._config["favorites"] = cleaned
            save_config(self._config)

    def _on_loaded(self) -> None:
        """Called when the webview window finishes loading.

        NOTE: pywebview fires this on a background thread (Thread-2),
        so AppKit operations must be dispatched to the main thread.
        """
        from PyObjCTools import AppHelper

        AppHelper.callAfter(self._enable_video_fullscreen)
        interval = self._config.get("refresh_interval", 60)
        self._api.start_polling(interval)

    @staticmethod
    def _enable_video_fullscreen() -> None:
        """Enable HTML5 Fullscreen API for <video> in WKWebView."""
        try:
            from webview.platforms import cocoa

            for bv in cocoa.BrowserView.instances.values():
                prefs = bv.webview.configuration().preferences()
                prefs.setValue_forKey_(True, "elementFullscreenEnabled")
                break
        except Exception:
            pass

    def _on_closing(self) -> None:
        """Called when the webview window is closing."""
        self._api.close()

    def mainloop(self) -> None:
        html_path = Path(__file__).parent / "ui" / "index.html"
        html_content = html_path.read_text(encoding="utf-8")

        window = webview.create_window(
            "TwitchX",
            html=html_content,
            js_api=self._api,
            width=960,
            height=640,
            min_size=(700, 500),
            background_color="#0E0E1A",
        )
        if window is None:
            raise RuntimeError("Failed to create the TwitchX window")
        self._window = window
        self._api.set_window(window)
        window.events.loaded += self._on_loaded
        window.events.closing += self._on_closing

        debug = bool(os.environ.get("TWITCHX_DEBUG"))
        webview.start(debug=debug)
