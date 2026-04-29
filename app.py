from __future__ import annotations

import os
import re
from pathlib import Path

import webview

from core.storage import get_settings, load_config
from ui.api import TwitchXApi


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
        interval = get_settings(self._config).get("refresh_interval", 60)
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
                html = html.replace(match.group(0), f"<style>\n{css_content}\n</style>", 1)

        # Collect JS modules in order
        js_contents: list[str] = []
        for match in list(re.finditer(r'<script src="([^"]+)"></script>', html)):
            src = match.group(1)
            js_path = base_dir / src
            if js_path.exists():
                js_contents.append(js_path.read_text(encoding="utf-8"))

        # Remove all external script tags
        html = re.sub(r'<script src="[^"]+"></script>\s*', '', html)

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
        html_path = Path(__file__).parent / "ui" / "index.html"
        html_content = html_path.read_text(encoding="utf-8")
        html_content = self._inline_resources(html_content, html_path.parent)

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
