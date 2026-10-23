from __future__ import annotations

import importlib
import logging
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any

import webview

from core.storage import get_settings, load_config
from ui.api import TwitchXApi
from ui.api.settings_schema import clamp_refresh_interval

logger = logging.getLogger(__name__)

# Native window background, shown before the WebView paints. Must match
# --bg-base in ui/css/themes/dark.css and ui/css/themes/light.css — update
# these together, or a different colour flashes at startup.
WINDOW_BG_DARK = "#0F1012"
WINDOW_BG_LIGHT = "#FFFFFF"


def window_background(theme_mode: str, system_is_dark: bool) -> str:
    """Window background for the ``theme`` setting ("auto" | "dark" | "light")."""
    if theme_mode == "light":
        return WINDOW_BG_LIGHT
    if theme_mode == "auto":
        return WINDOW_BG_DARK if system_is_dark else WINDOW_BG_LIGHT
    return WINDOW_BG_DARK


def _system_is_dark() -> bool:
    """Whether macOS is in Dark Mode; True if it cannot be determined.

    Called before the window exists (no WebView/AppKit UI yet), so reading the
    app appearance here does not need AppHelper.callAfter.
    """
    try:
        # pyobjc builds AppKit lazily, so pyright cannot see its symbols.
        appkit: Any = importlib.import_module("AppKit")
        aqua = appkit.NSAppearanceNameAqua
        appearance = appkit.NSApplication.sharedApplication().effectiveAppearance()
        best = appearance.bestMatchFromAppearancesWithNames_(
            [aqua, appkit.NSAppearanceNameDarkAqua]
        )
        return best != aqua
    except Exception:
        return True


class TwitchXApp:
    """pywebview-based TwitchX application."""

    def __init__(self) -> None:
        self._api = TwitchXApi()
        self._config = load_config()

    def _on_loaded(self) -> None:
        """Called when the webview window finishes loading.

        NOTE: pywebview fires this on a background thread (Thread-2),
        so AppKit operations must be dispatched to the main thread.
        """
        from PyObjCTools import AppHelper

        AppHelper.callAfter(self._enable_video_fullscreen)
        if get_settings(self._config).get("integrated_titlebar", False):
            AppHelper.callAfter(self._integrate_titlebar)
        # JS never reads config synchronously (the bridge returns Promises) —
        # push the snapshot as soon as the document is ready.
        self._api.push_config()
        interval = clamp_refresh_interval(
            get_settings(self._config).get("refresh_interval", 60)
        )
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

    @staticmethod
    def _ns_window() -> Any:
        from webview.platforms import cocoa

        for bv in cocoa.BrowserView.instances.values():
            return bv.window
        return None

    def _integrate_titlebar(self) -> None:
        """Hide the native title bar and let the traffic lights sit in the sidebar.

        Runs on the main thread. Any failure leaves the native title bar as it
        was: the window must stay usable even if the AppKit calls misbehave.
        """
        try:
            appkit: Any = importlib.import_module("AppKit")
            win = self._ns_window()
            if win is None:
                return
            win.setStyleMask_(
                win.styleMask() | appkit.NSWindowStyleMaskFullSizeContentView
            )
            win.setTitlebarAppearsTransparent_(True)
            win.setTitleVisibility_(appkit.NSWindowTitleHidden)
            toolbar = appkit.NSToolbar.alloc().initWithIdentifier_("twitchx.main")
            toolbar.setShowsBaselineSeparator_(False)
            win.setToolbar_(toolbar)
            # Unified toolbar style centres the traffic lights in a taller bar.
            win.setToolbarStyle_(appkit.NSWindowToolbarStyleUnifiedCompact)
        except Exception:
            logger.exception("Integrated title bar failed; keeping the native one")
            return
        self._api._titlebar_handler = self._titlebar_action
        # evaluate_js waits on the main thread, which this method occupies.
        threading.Thread(
            target=self._api._eval_js,
            args=(
                "document.getElementById('app').classList.add('titlebar-integrated')",
            ),
            daemon=True,
        ).start()

    def _titlebar_action(self, action: str) -> None:
        """Bridge side of the title-bar drag zone (called off the main thread)."""
        from PyObjCTools import AppHelper

        AppHelper.callAfter(self._perform_titlebar_action, action)

    def _perform_titlebar_action(self, action: str) -> None:
        try:
            appkit: Any = importlib.import_module("AppKit")
            win = self._ns_window()
            if win is None:
                return
            if action == "drag":
                # WKWebView swallows the mouse-down, so the window never sees a
                # drag of its own. Hand AppKit the event that is still in flight.
                event = appkit.NSApplication.sharedApplication().currentEvent()
                if event is not None and event.type() in (
                    appkit.NSEventTypeLeftMouseDown,
                    appkit.NSEventTypeLeftMouseDragged,
                ):
                    win.performWindowDragWithEvent_(event)
            elif action == "double-click":
                # Honour System Settings › Desktop & Dock › "Double-click a
                # window's title bar to".
                pref = appkit.NSUserDefaults.standardUserDefaults().stringForKey_(
                    "AppleActionOnDoubleClick"
                )
                if pref == "Minimize":
                    win.miniaturize_(None)
                elif pref != "None":
                    win.zoom_(None)
        except Exception:
            logger.exception("Title bar action %r failed", action)

    def _on_closing(self) -> None:
        """Called when the webview window is closing."""
        self._api.close()

    @staticmethod
    def _inline_resources(html: str, base_dir: Path) -> str:
        """Replace external <link> and <script src> with inline <style> / <script>.

        pywebview's ``html=`` param is the only reliable way to load JS on macOS.
        WKWebView silently skips <script src> resources when served over the
        internal HTTP server, and even inline ``<script>`` blocks after the
        first one are dropped when pywebview injects its bridge code between
        them. To avoid both issues we merge *all* JS modules into a single
        inline ``<script>`` block (so there is no interleaving with pywebview
        injection) and do the same for CSS.
        """
        # Inline CSS
        for match in list(re.finditer(r'<link rel="stylesheet" href="([^"]+)">', html)):
            href = match.group(1)
            css_path = base_dir / href
            if css_path.exists():
                css_content = css_path.read_text(encoding="utf-8")
                html = html.replace(
                    match.group(0), f"<style>\n{css_content}\n</style>", 1
                )

        # Collect JS modules in order
        js_contents: list[str] = []
        for match in list(re.finditer(r'<script src="([^"]+)"></script>', html)):
            src = match.group(1)
            js_path = base_dir / src
            if js_path.exists():
                js_contents.append(js_path.read_text(encoding="utf-8"))

        # Remove all external script tags
        html = re.sub(r'<script src="[^"]+"></script>\s*', "", html)

        # Merge into a single block — drop duplicate TwitchX bootstrap lines
        merged_parts: list[str] = []
        for i, content in enumerate(js_contents):
            if i > 0:
                content = content.replace(
                    "window.TwitchX = window.TwitchX || {};\nconst TwitchX = window.TwitchX;",
                    "// TwitchX already initialised by state.js",
                )
            merged_parts.append(content)

        merged_js = "\n".join(merged_parts)
        html = html.replace(
            "</body>",
            f"<script>\n{merged_js}\n</script>\n</body>",
            1,
        )

        return html

    def mainloop(self) -> None:
        # Under a PyInstaller frozen bundle, bundled data lives in sys._MEIPASS,
        # not next to this source file. Fall back to the source dir for `make run`.
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
        html_path = base / "ui" / "index.html"
        html_content = html_path.read_text(encoding="utf-8")
        html_content = self._inline_resources(html_content, html_path.parent)

        theme_mode = str(get_settings(self._config).get("theme", "dark"))
        system_is_dark = _system_is_dark() if theme_mode == "auto" else True
        window = webview.create_window(
            "TwitchX",
            html=html_content,
            js_api=self._api,
            width=960,
            height=640,
            min_size=(700, 500),
            background_color=window_background(theme_mode, system_is_dark),
        )
        if window is None:
            raise RuntimeError("Failed to create the TwitchX window")
        self._window = window
        self._api.set_window(window)
        window.events.loaded += self._on_loaded
        window.events.closing += self._on_closing

        debug = bool(os.environ.get("TWITCHX_DEBUG"))
        webview.start(debug=debug)
