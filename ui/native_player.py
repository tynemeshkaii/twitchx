"""macOS native AVPlayer controller for in-app HLS playback.

Manages an NSSplitView with AVPlayerView (top) and WKWebView (bottom).
All AppKit/AVKit calls must run on the main thread.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from typing import Any

import objc
from AppKit import NSSplitView
from AVFoundation import (
    AVPlayer,
    AVPlayerItem,
    AVPlayerItemDidPlayToEndTimeNotification,
    AVURLAsset,
)
from AVKit import AVPlayerView
from Foundation import (
    NSURL,
    NSKeyValueObservingOptionNew,
    NSNotificationCenter,
)

logger = logging.getLogger(__name__)

# Player state constants pushed to JS
STATE_IDLE = "idle"
STATE_LOADING = "loading"
STATE_PLAYING = "playing"
STATE_PAUSED = "paused"
STATE_FAILED = "failed"
STATE_ENDED = "ended"

# Default player pane height
DEFAULT_PLAYER_HEIGHT = 360.0
MIN_PLAYER_HEIGHT = 200.0


class NativePlayerController:
    """Controls AVPlayerView docked in an NSSplitView above the WKWebView."""

    def __init__(self, on_state_change: Callable[[dict[str, Any]], None]) -> None:
        self._on_state_change = on_state_change
        self._player: Any = None
        self._player_view: Any = None
        self._split_view: Any = None
        self._web_view: Any = None
        self._window: Any = None
        self._current_channel: str | None = None
        self._current_title: str | None = None
        self._attached = False
        self._player_height = DEFAULT_PLAYER_HEIGHT
        self._player_visible = False
        self._item_status_observer: Any = None
        self._time_control_observer: Any = None

    # ── Attach to pywebview window ──────────────────────────────

    def attach(self, pywebview_window: Any) -> None:
        """Reparent WebKitHost into NSSplitView. Must be called on main thread.

        pywebview cocoa backend structure:
          NSWindow.contentView = WebKitHost (custom NSView)
            └── WKFlippedView (WKWebView internals)

        We reparent the entire WebKitHost into the bottom pane of an
        NSSplitView and place AVPlayerView in the top pane.
        """
        if self._attached:
            return

        ns_window = None

        # pywebview cocoa backend: BrowserView.instances is a dict
        # Each value has .window (NSWindow) and .webview (WKWebView)
        try:
            from webview.platforms import cocoa

            for bv in cocoa.BrowserView.instances.values():
                ns_window = bv.window
                break
        except Exception:
            pass

        if ns_window is None:
            raise RuntimeError("Cannot access NSWindow from pywebview")

        self._window = ns_window
        content_view = ns_window.contentView()  # WebKitHost
        self._web_view = content_view

        # Create AVPlayerView
        self._player = AVPlayer.alloc().init()
        self._player_view = AVPlayerView.alloc().initWithFrame_(
            content_view.bounds()
        )
        self._player_view.setPlayer_(self._player)
        self._player_view.setControlsStyle_(1)  # AVPlayerViewControlsStyleFloating

        # Create NSSplitView (horizontal split: top=player, bottom=webview)
        self._split_view = NSSplitView.alloc().initWithFrame_(
            content_view.bounds()
        )
        self._split_view.setVertical_(False)  # horizontal = top/bottom
        self._split_view.setDividerStyle_(2)  # thin divider
        self._split_view.setAutoresizingMask_(
            18  # NSViewWidthSizable | NSViewHeightSizable
        )

        # Reparent: retain WebKitHost, swap contentView atomically, then add subviews.
        # setContentView_ removes the old contentView from the view hierarchy,
        # so we retain it first to prevent deallocation.
        content_view.retain()
        ns_window.setContentView_(self._split_view)
        self._split_view.addSubview_(self._player_view)
        self._split_view.addSubview_(content_view)
        content_view.release()

        # Collapse player pane initially (height = 0)
        self._set_player_height(0)

        self._attached = True
        logger.debug("NativePlayerController attached to window")

    # ── Playback ────────────────────────────────────────────────

    def play_stream(self, hls_url: str, channel: str, title: str = "") -> None:
        """Start playing an HLS stream. Must be called on main thread."""
        if not self._attached:
            raise RuntimeError("NativePlayerController not attached to window")

        self._current_channel = channel
        self._current_title = title
        self._notify_state(STATE_LOADING)

        # Remove observers from previous item
        self._remove_observers()

        # Create new player item
        url = NSURL.URLWithString_(hls_url)
        asset = AVURLAsset.URLAssetWithURL_options_(url, None)
        item = AVPlayerItem.playerItemWithAsset_(asset)

        # Observe item status
        item.addObserver_forKeyPath_options_context_(
            self, "status", NSKeyValueObservingOptionNew, None
        )
        self._item_status_observer = item

        # Observe player timeControlStatus
        self._player.addObserver_forKeyPath_options_context_(
            self, "timeControlStatus", NSKeyValueObservingOptionNew, None
        )
        self._time_control_observer = self._player

        # Listen for playback end
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self,
            objc.selector(self._player_did_finish_, signature=b"v@:@"),
            AVPlayerItemDidPlayToEndTimeNotification,
            item,
        )

        # Replace current item and play
        self._player.replaceCurrentItemWithPlayerItem_(item)
        self._player.play()

        # Show player pane
        if not self._player_visible:
            self._show_player()

    def stop(self) -> None:
        """Stop playback and collapse the player pane."""
        if self._player:
            self._player.pause()
            self._remove_observers()
            self._player.replaceCurrentItemWithPlayerItem_(None)

        self._current_channel = None
        self._current_title = None
        self._hide_player()
        self._notify_state(STATE_IDLE)

    def pause(self) -> None:
        if self._player:
            self._player.pause()

    def resume(self) -> None:
        if self._player:
            self._player.play()

    @property
    def current_channel(self) -> str | None:
        return self._current_channel

    @property
    def is_playing(self) -> bool:
        if self._player is None:
            return False
        # timeControlStatus: 0=paused, 1=waitingToPlay, 2=playing
        return self._player.timeControlStatus() == 2

    # ── KVO ──────────────────────────────────────────────────────

    def observeValueForKeyPath_ofObject_change_context_(
        self, key_path: str, obj: Any, change: Any, context: Any
    ) -> None:
        """KVO callback for AVPlayerItem.status and AVPlayer.timeControlStatus."""
        if key_path == "status":
            status = obj.status()
            if status == 1:  # AVPlayerItemStatusReadyToPlay
                logger.debug("Player item ready")
            elif status == 2:  # AVPlayerItemStatusFailed
                error = obj.error()
                msg = error.localizedDescription() if error else "Unknown error"
                logger.error("Player item failed: %s", msg)
                self._notify_state(STATE_FAILED, error=str(msg))

        elif key_path == "timeControlStatus":
            tcs = obj.timeControlStatus()
            if tcs == 0:  # paused
                if self._current_channel:
                    self._notify_state(STATE_PAUSED)
            elif tcs == 1:  # waitingToPlay
                self._notify_state(STATE_LOADING)
            elif tcs == 2:  # playing
                self._notify_state(STATE_PLAYING)

    def _player_did_finish_(self, notification: Any) -> None:
        """Called when playback reaches the end."""
        self._notify_state(STATE_ENDED)

    # ── Split view management ────────────────────────────────────

    def _show_player(self) -> None:
        if self._split_view and not self._player_visible:
            self._set_player_height(self._player_height or DEFAULT_PLAYER_HEIGHT)
            self._player_visible = True

    def _hide_player(self) -> None:
        if self._split_view and self._player_visible:
            # Save current height before collapsing
            pos = self._split_view.subviews()[0].frame().size.height
            if pos >= MIN_PLAYER_HEIGHT:
                self._player_height = pos
            self._set_player_height(0)
            self._player_visible = False

    def _set_player_height(self, height: float) -> None:
        if not self._split_view:
            return
        total = self._split_view.frame().size.height
        divider = self._split_view.dividerThickness()
        web_height = total - height - (divider if height > 0 else 0)

        player_frame = self._split_view.subviews()[0].frame()
        player_frame.size.height = height
        self._split_view.subviews()[0].setFrame_(player_frame)

        web_frame = self._split_view.subviews()[1].frame()
        web_frame.size.height = web_height
        web_frame.origin.y = 0
        self._split_view.subviews()[1].setFrame_(web_frame)

        self._split_view.adjustSubviews()

    def get_player_height(self) -> float:
        """Return current player pane height for config persistence."""
        if self._split_view and self._player_visible:
            return self._split_view.subviews()[0].frame().size.height
        return self._player_height

    def set_player_height(self, height: float) -> None:
        """Restore player height from config."""
        self._player_height = max(height, MIN_PLAYER_HEIGHT)

    # ── Internal helpers ─────────────────────────────────────────

    def _notify_state(self, state: str, **extra: Any) -> None:
        data: dict[str, Any] = {
            "state": state,
            "channel": self._current_channel,
            "title": self._current_title,
        }
        data.update(extra)
        self._on_state_change(data)

    def _remove_observers(self) -> None:
        """Remove KVO observers and notification listeners."""
        if self._item_status_observer is not None:
            with contextlib.suppress(Exception):
                self._item_status_observer.removeObserver_forKeyPath_(self, "status")
            NSNotificationCenter.defaultCenter().removeObserver_name_object_(
                self,
                AVPlayerItemDidPlayToEndTimeNotification,
                self._item_status_observer,
            )
            self._item_status_observer = None

        if self._time_control_observer is not None:
            with contextlib.suppress(Exception):
                self._time_control_observer.removeObserver_forKeyPath_(
                    self, "timeControlStatus"
                )
            self._time_control_observer = None

    def cleanup(self) -> None:
        """Clean up all player resources. Call on app close."""
        self.stop()
        self._player = None
        self._player_view = None
