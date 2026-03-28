# Native AVPlayer Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Play Twitch HLS streams inside the TwitchX window using macOS AVPlayerView, replacing IINA as the primary playback method.

**Architecture:** A `NativePlayerController` manages an `NSSplitView` that docks `AVPlayerView` (top) above the existing `WKWebView` (bottom). The player pane is collapsed by default and expands when playback starts. Streamlink CLI resolves HLS URLs in a background thread; the URL is handed to `AVPlayer` on the main thread. IINA remains as a fallback "Open externally" action.

**Tech Stack:** pyobjc-framework-AVKit, pyobjc-framework-AVFoundation, AppKit (NSSplitView, NSView), existing pywebview + streamlink CLI.

---

### Task 1: Create `core/stream_resolver.py` — extract HLS URL resolution

Extract the URL-resolution logic from `launcher.py` into a standalone function so both native playback and IINA can share it.

**Files:**
- Create: `core/stream_resolver.py`
- Test: `tests/test_stream_resolver.py`

**Step 1: Write failing tests**

```python
# tests/test_stream_resolver.py
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from core.stream_resolver import resolve_hls_url


class TestResolveHlsUrl:
    @patch("core.stream_resolver.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"https://example.com/stream.m3u8\n",
        )
        url, err = resolve_hls_url("xqc", "best")
        assert url == "https://example.com/stream.m3u8"
        assert err == ""

    @patch("core.stream_resolver.subprocess.run")
    def test_quality_fallback(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr=b"quality not available"),
            MagicMock(returncode=0, stdout=b"https://example.com/best.m3u8\n"),
        ]
        url, err = resolve_hls_url("xqc", "720p60")
        assert url == "https://example.com/best.m3u8"
        assert mock_run.call_count == 2

    @patch("core.stream_resolver.subprocess.run")
    def test_timeout(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="streamlink", timeout=15)
        url, err = resolve_hls_url("xqc", "best")
        assert url is None
        assert "timed out" in err.lower()

    @patch("core.stream_resolver.shutil.which", return_value=None)
    def test_missing_streamlink(self, mock_which: MagicMock) -> None:
        url, err = resolve_hls_url("xqc", "best")
        assert url is None
        assert "not found" in err.lower()

    @patch("core.stream_resolver.subprocess.run")
    def test_all_qualities_fail(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stderr=b"No streams found")
        url, err = resolve_hls_url("xqc", "720p60")
        assert url is None
        assert err != ""
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_stream_resolver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.stream_resolver'`

**Step 3: Write the implementation**

```python
# core/stream_resolver.py
"""Resolve Twitch HLS URLs via streamlink CLI.

Extracts URL-resolution logic so both native AVPlayer and external IINA
can share the same resolver.
"""

from __future__ import annotations

import shutil
import subprocess


def _run_streamlink(
    resolved_sl: str, twitch_url: str, quality: str
) -> tuple[str | None, str]:
    """Run `streamlink --stream-url` and return (hls_url, error_text)."""
    try:
        result = subprocess.run(
            [resolved_sl, "--stream-url", twitch_url, quality],
            capture_output=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return None, "streamlink timed out resolving stream URL"

    if result.returncode == 0:
        hls_url = result.stdout.decode(errors="replace").strip()
        if hls_url:
            return hls_url, ""
        return None, "streamlink returned empty URL"

    return None, result.stderr.decode(errors="replace")[:300]


def resolve_hls_url(
    channel: str,
    quality: str,
    streamlink_path: str = "streamlink",
) -> tuple[str | None, str]:
    """Resolve HLS URL for a Twitch channel.

    Returns (hls_url, error_message). Falls back to 'best' quality
    if the requested quality is unavailable.
    """
    resolved_sl = shutil.which(streamlink_path)
    if resolved_sl is None:
        return None, "streamlink not found.\n\nInstall it with:\n  brew install streamlink"

    twitch_url = f"https://twitch.tv/{channel}"
    hls_url, err = _run_streamlink(resolved_sl, twitch_url, quality)

    if not hls_url and quality != "best":
        hls_url, err = _run_streamlink(resolved_sl, twitch_url, "best")

    return hls_url, err
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_stream_resolver.py -v`
Expected: All 5 PASS

**Step 5: Update `launcher.py` to use the shared resolver**

Replace the duplicated `_get_stream_url` logic in `launch_stream()` with a call to `resolve_hls_url`:

```python
# In core/launcher.py, replace lines 56-85 of launch_stream() body:
def launch_stream(
    channel: str,
    quality: str,
    streamlink_path: str = "streamlink",
    iina_path: str = DEFAULT_IINA_PATH,
) -> LaunchResult:
    iina_err = check_iina(iina_path)
    if iina_err:
        return LaunchResult(success=False, message=iina_err)

    from core.stream_resolver import resolve_hls_url

    hls_url, err = resolve_hls_url(channel, quality, streamlink_path)
    if not hls_url:
        return LaunchResult(
            success=False,
            message=f"streamlink error: {err}" if err else "Could not resolve stream URL",
        )

    try:
        subprocess.Popen(
            [iina_path, hls_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return LaunchResult(success=True, message=f"Launched {channel} ({quality})")
    except Exception as e:
        return LaunchResult(success=False, message=f"Failed to launch IINA: {e}")
```

Keep `_get_stream_url`, `check_streamlink`, `check_iina` exported from `launcher.py` for backward compat (existing tests import them). They stay as-is.

**Step 6: Run all existing launcher tests**

Run: `uv run pytest tests/test_launcher.py tests/test_stream_resolver.py -v`
Expected: All pass

**Step 7: Commit**

```
feat: extract stream URL resolver into core/stream_resolver.py
```

---

### Task 2: Create `ui/native_player.py` — AVPlayerView + NSSplitView controller

This is the core macOS-native module. It manages the player pane, NSSplitView layout, and AVPlayer lifecycle.

**Files:**
- Create: `ui/native_player.py`
- Test: `tests/test_native_player.py`

**Step 1: Write the unit tests**

These tests verify the controller's logic without requiring actual AppKit (mock the ObjC layer).

```python
# tests/test_native_player.py
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest


class TestNativePlayerController:
    """Test NativePlayerController logic with mocked ObjC objects."""

    @patch("ui.native_player.AVPlayer", create=True)
    @patch("ui.native_player.AVPlayerView", create=True)
    @patch("ui.native_player.NSSplitView", create=True)
    def test_init_state(self, mock_split, mock_pv, mock_player) -> None:
        from ui.native_player import NativePlayerController
        ctrl = NativePlayerController(on_state_change=lambda s: None)
        assert ctrl._current_channel is None
        assert ctrl._attached is False

    def test_play_stream_without_attach_raises(self) -> None:
        with patch.dict("sys.modules", {
            "AVFoundation": MagicMock(),
            "AVKit": MagicMock(),
            "AppKit": MagicMock(),
            "objc": MagicMock(),
        }):
            from ui.native_player import NativePlayerController
            ctrl = NativePlayerController(on_state_change=lambda s: None)
            with pytest.raises(RuntimeError, match="not attached"):
                ctrl.play_stream("https://example.com/stream.m3u8", "xqc", "Test Stream")
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_native_player.py -v`
Expected: FAIL — no module

**Step 3: Write the implementation**

```python
# ui/native_player.py
"""macOS native AVPlayer controller for in-app HLS playback.

Manages an NSSplitView with AVPlayerView (top) and WKWebView (bottom).
All AppKit/AVKit calls must run on the main thread.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import objc
from AppKit import NSView, NSSplitView, NSWindow
from AVFoundation import (
    AVPlayer,
    AVPlayerItem,
    AVPlayerItemDidPlayToEndTimeNotification,
    AVURLAsset,
)
from AVKit import AVPlayerView
from Foundation import (
    NSNotificationCenter,
    NSURL,
    NSKeyValueObservingOptionNew,
)
from PyObjCTools import AppHelper

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
        self._player: AVPlayer | None = None
        self._player_view: AVPlayerView | None = None
        self._split_view: NSSplitView | None = None
        self._web_view: NSView | None = None
        self._window: NSWindow | None = None
        self._current_channel: str | None = None
        self._current_title: str | None = None
        self._attached = False
        self._player_height = DEFAULT_PLAYER_HEIGHT
        self._player_visible = False
        self._item_status_observer = None
        self._time_control_observer = None

    # ── Attach to pywebview window ──────────────────────────────

    def attach(self, pywebview_window: Any) -> None:
        """Reparent WKWebView into NSSplitView. Must be called on main thread."""
        if self._attached:
            return

        # pywebview cocoa backend exposes the NSWindow
        ns_window = pywebview_window.gui.BrowserView.nativeWindowHandle()
        if ns_window is None:
            # Alternative access path
            for wv in pywebview_window.gui.BrowserView.instances.values():
                ns_window = wv.window
                self._web_view = wv.webkit
                break

        if ns_window is None:
            raise RuntimeError("Cannot access NSWindow from pywebview")

        self._window = ns_window
        content_view = ns_window.contentView()

        if self._web_view is None:
            # The content view is the WKWebView (or contains it)
            self._web_view = content_view

        # Create AVPlayerView
        self._player = AVPlayer.alloc().init()
        self._player_view = AVPlayerView.alloc().initWithFrame_(
            content_view.bounds()
        )
        self._player_view.setPlayer_(self._player)
        self._player_view.setControlsStyle_(1)  # AVPlayerViewControlsStyleFloating

        # Create NSSplitView (vertical split: top=player, bottom=webview)
        self._split_view = NSSplitView.alloc().initWithFrame_(
            content_view.bounds()
        )
        self._split_view.setVertical_(False)  # horizontal split (top/bottom)
        self._split_view.setDividerStyle_(2)  # thin divider
        self._split_view.setAutoresizingMask_(
            18  # NSViewWidthSizable | NSViewHeightSizable
        )

        # Remove webview from its current parent
        self._web_view.removeFromSuperview()

        # Add subviews: player on top, webview on bottom
        self._split_view.addSubview_(self._player_view)
        self._split_view.addSubview_(self._web_view)

        # Set as content view
        ns_window.setContentView_(self._split_view)

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
        self, key_path, obj, change, context
    ):
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

    def _player_did_finish_(self, notification) -> None:
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
            try:
                self._item_status_observer.removeObserver_forKeyPath_(self, "status")
            except Exception:
                pass
            NSNotificationCenter.defaultCenter().removeObserver_name_object_(
                self, AVPlayerItemDidPlayToEndTimeNotification, self._item_status_observer
            )
            self._item_status_observer = None

        if self._time_control_observer is not None:
            try:
                self._time_control_observer.removeObserver_forKeyPath_(
                    self, "timeControlStatus"
                )
            except Exception:
                pass
            self._time_control_observer = None

    def cleanup(self) -> None:
        """Clean up all player resources. Call on app close."""
        self.stop()
        self._player = None
        self._player_view = None
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_native_player.py -v`
Expected: All pass

**Step 5: Commit**

```
feat: add NativePlayerController with AVPlayerView + NSSplitView
```

---

### Task 3: Add `player_height` to config defaults

**Files:**
- Modify: `core/storage.py`

**Step 1: Add default to `DEFAULT_CONFIG`**

Add `"player_height": 360` to the `DEFAULT_CONFIG` dict in `core/storage.py`.

**Step 2: Run storage tests**

Run: `uv run pytest tests/test_storage.py -v`
Expected: All pass

**Step 3: Commit**

```
feat: add player_height to config defaults
```

---

### Task 4: Wire native player into `ui/api.py`

Update the `TwitchXApi` to use `NativePlayerController` for in-app playback and keep IINA as a fallback.

**Files:**
- Modify: `ui/api.py`

**Step 1: Add native player integration**

Changes to `TwitchXApi`:

1. **Import** `NativePlayerController` and `resolve_hls_url`:

```python
from core.stream_resolver import resolve_hls_url
from ui.native_player import NativePlayerController
```

2. **In `__init__`**, create the native player controller:

```python
self._native_player = NativePlayerController(on_state_change=self._on_player_state)
```

3. **Add `_on_player_state` callback** — pushes state to JS:

```python
def _on_player_state(self, state_data: dict) -> None:
    self._eval_js(f"window.onPlayerState({json.dumps(state_data)})")
```

4. **Add `attach_native_player` method** — called from `app.py` after window loaded:

```python
def attach_native_player(self, pywebview_window: Any) -> None:
    """Attach native player to the pywebview window. Called on main thread."""
    try:
        self._native_player.attach(pywebview_window)
        # Restore saved player height
        saved_height = self._config.get("player_height", 360)
        self._native_player.set_player_height(float(saved_height))
    except Exception as e:
        logger.warning("Native player attach failed: %s", e)
```

5. **Rewrite `watch()` method** — resolve URL in bg thread, play natively on main thread:

```python
def watch(self, channel: str, quality: str) -> None:
    if not channel:
        self._eval_js(
            "window.onLaunchResult({success: false, message: 'Select a channel first', channel: ''})"
        )
        return
    live_logins = {s["user_login"].lower() for s in self._live_streams}
    if channel.lower() not in live_logins:
        safe_ch = json.dumps(channel)
        self._eval_js(
            f"window.onLaunchResult({{success: false, message: {safe_ch} + ' is offline', channel: {safe_ch}}})"
        )
        return

    self._config["quality"] = quality
    save_config(self._config)
    safe_ch = json.dumps(channel)
    self._eval_js(
        f"window.onStatusUpdate({{text: 'Loading ' + {safe_ch} + '...', type: 'warn'}})"
    )

    # Start progress timer
    self._launch_channel = channel
    self._launch_elapsed = 0
    self._start_launch_timer()

    # Find stream title for player
    title = ""
    for s in self._live_streams:
        if s["user_login"].lower() == channel.lower():
            title = s.get("title", "")
            break

    def do_resolve() -> None:
        hls_url, err = resolve_hls_url(
            channel,
            quality,
            self._config.get("streamlink_path", "streamlink"),
        )
        self._cancel_launch_timer()
        self._launch_channel = None

        if not hls_url:
            r = json.dumps({
                "success": False,
                "message": f"streamlink error: {err}" if err else "Could not resolve stream URL",
                "channel": channel,
            })
            self._eval_js(f"window.onLaunchResult({r})")
            return

        # Play on main thread via AppHelper
        from PyObjCTools import AppHelper
        AppHelper.callAfter(
            self._native_player.play_stream, hls_url, channel, title
        )
        self._watching_channel = channel
        r = json.dumps({
            "success": True,
            "message": f"Playing {channel}",
            "channel": channel,
        })
        self._eval_js(f"window.onLaunchResult({r})")

    self._run_in_thread(do_resolve)
```

6. **Add `stop_player()` method** — called from JS "Close Player" button:

```python
def stop_player(self) -> None:
    """Stop native playback and collapse the player pane."""
    from PyObjCTools import AppHelper
    AppHelper.callAfter(self._native_player.stop)
    self._watching_channel = None
```

7. **Add `watch_external()` method** — IINA fallback:

```python
def watch_external(self, channel: str, quality: str) -> None:
    """Launch stream in IINA (fallback). Same as old watch() behavior."""
    if not channel:
        return
    live_logins = {s["user_login"].lower() for s in self._live_streams}
    if channel.lower() not in live_logins:
        return

    def do_launch() -> None:
        result = launch_stream(
            channel,
            quality,
            self._config.get("streamlink_path", "streamlink"),
            self._config.get("iina_path", "/Applications/IINA.app/Contents/MacOS/iina-cli"),
        )
        r = json.dumps({
            "success": result.success,
            "message": result.message,
            "channel": channel,
        })
        self._eval_js(f"window.onLaunchResult({r})")

    self._run_in_thread(do_launch)
```

8. **Update `close()` method** — save player height, clean up player:

```python
def close(self) -> None:
    self._shutdown.set()
    self.stop_polling()
    self._cancel_launch_timer()
    # Save player height
    if self._native_player._attached:
        self._config["player_height"] = self._native_player.get_player_height()
        save_config(self._config)
    # Clean up native player
    self._native_player.cleanup()
    # Close twitch client
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(self._twitch.close())
    finally:
        asyncio.set_event_loop(None)
        loop.close()
```

**Step 2: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All existing tests pass (new native methods aren't directly tested here — they require real AppKit)

**Step 3: Commit**

```
feat: wire NativePlayerController into TwitchXApi bridge
```

---

### Task 5: Update `app.py` — attach native player on window load

**Files:**
- Modify: `app.py`

**Step 1: Update `_on_loaded` to attach the native player**

```python
def _on_loaded(self) -> None:
    """Called when the webview window finishes loading."""
    # Attach native player on main thread (we're already on main thread here)
    self._api.attach_native_player(self._window)
    interval = self._config.get("refresh_interval", 60)
    self._api.start_polling(interval)
```

Store `self._window` reference in `mainloop()`:

```python
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
```

**Step 2: Run app tests**

Run: `uv run pytest tests/test_app.py -v`
Expected: All pass

**Step 3: Commit**

```
feat: attach native player in app.py on window load
```

---

### Task 6: Update `ui/index.html` — player controls and state

**Files:**
- Modify: `ui/index.html`

**Step 1: Add `onPlayerState` JS callback and update player bar UI**

Add the `window.onPlayerState` callback that receives `{state, channel, title, error}`:

```javascript
window.onPlayerState = function(data) {
  state.playerState = data.state;  // idle, loading, playing, paused, failed, ended
  state.playerChannel = data.channel;
  state.playerTitle = data.title || '';
  state.playerError = data.error || '';
  renderPlayerState();
};
```

Add `renderPlayerState()` function that updates the player bar:

```javascript
function renderPlayerState() {
  var ps = state.playerState || 'idle';
  var statusEl = document.getElementById('status-text');
  var watchBtn = document.getElementById('watch-btn');
  var stopBtn = document.getElementById('stop-player-btn');
  var externalBtn = document.getElementById('watch-external-btn');

  // Show/hide stop button
  stopBtn.style.display = (ps === 'playing' || ps === 'paused' || ps === 'loading') ? 'inline-flex' : 'none';

  if (ps === 'loading') {
    statusEl.textContent = 'Buffering ' + (state.playerChannel || '') + '...';
  } else if (ps === 'playing') {
    state.watchingChannel = state.playerChannel;
    watchBtn.classList.add('active');
    statusEl.textContent = 'Playing ' + (state.playerChannel || '');
  } else if (ps === 'paused') {
    statusEl.textContent = 'Paused ' + (state.playerChannel || '');
  } else if (ps === 'failed') {
    statusEl.textContent = 'Playback error: ' + (state.playerError || 'unknown');
    state.watchingChannel = null;
    watchBtn.classList.remove('active');
  } else if (ps === 'ended' || ps === 'idle') {
    state.watchingChannel = null;
    watchBtn.classList.remove('active');
  }
  renderGrid();
}
```

**Step 2: Update player bar HTML**

Replace the current `#player-bar` section (around line 771) to add stop and external buttons:

```html
<div id="player-bar">
  <div class="player-bar-left">
    <select id="quality-select">
      <option value="best">Best</option>
      <option value="1080p60">1080p60</option>
      <option value="720p60">720p60</option>
      <option value="480p">480p</option>
      <option value="360p">360p</option>
      <option value="audio_only">Audio Only</option>
    </select>
    <button id="watch-btn">&#9654; Watch</button>
    <button id="stop-player-btn" style="display:none;" title="Stop playback">&#9632; Stop</button>
    <button id="watch-external-btn" title="Open in IINA">&#8599; IINA</button>
  </div>
  <div class="player-bar-right">
    <span id="status-text"></span>
    <span id="updated-time"></span>
    <span id="total-viewers"></span>
  </div>
</div>
```

**Step 3: Wire JS events for new buttons**

```javascript
document.getElementById('stop-player-btn').addEventListener('click', function() {
  api.stop_player();
});

document.getElementById('watch-external-btn').addEventListener('click', function() {
  if (!state.selectedChannel) return;
  var quality = document.getElementById('quality-select').value;
  api.watch_external(state.selectedChannel, quality);
});
```

**Step 4: Add CSS for new buttons**

```css
#stop-player-btn {
  background: var(--live-red);
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  padding: 6px 12px;
  cursor: pointer;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
#stop-player-btn:hover { opacity: 0.9; }

#watch-external-btn {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 6px 10px;
  cursor: pointer;
  font-size: 11px;
}
#watch-external-btn:hover {
  color: var(--text-primary);
  border-color: var(--text-muted);
}
```

**Step 5: Add `playerState` to JS state object**

Add to the `state` object initialization:

```javascript
playerState: 'idle',
playerChannel: null,
playerTitle: '',
playerError: '',
```

**Step 6: Update context menu**

Update the context menu `data-action="watch"` item and add an "Open in IINA" option:

```html
<div class="ctx-item" data-action="watch">&#9654; Watch in App</div>
<div class="ctx-item" data-action="watch-external">&#8599; Open in IINA</div>
```

Add handler for the new context menu action:

```javascript
if (action === 'watch-external') {
  selectChannel(ctxChannel);
  var quality = document.getElementById('quality-select').value;
  api.watch_external(ctxChannel, quality);
}
```

**Step 7: Commit**

```
feat: add native player controls and state to UI
```

---

### Task 7: Lint, test, and verify

**Files:**
- All modified files

**Step 1: Format and lint**

Run: `uv run ruff format .`
Run: `uv run ruff check . --fix`

**Step 2: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

**Step 3: Run type checker**

Run: `uv run pyright`
Fix critical issues (pyobjc types may need `# type: ignore` comments).

**Step 4: Commit any fixes**

```
fix: lint and type fixes for native AVPlayer integration
```

---

### Task 8: Smoke test

**Step 1: Launch the app**

Run: `uv run python main.py`

Expected:
- Window opens normally
- Player pane is NOT visible (collapsed)
- All existing UI works

**Step 2: Test playback** (requires Twitch API credentials and a live channel)

- Select a live channel
- Click "Watch" — player pane should expand from top, stream should play
- Click "Stop" — player pane should collapse
- Click "IINA" — should launch in IINA externally

**Step 3: Test PiP and fullscreen**

- Float AVPlayerView controls should show PiP and fullscreen buttons

**Step 4: Fix any runtime issues found**

---

### Task 9: Update CLAUDE.md and AGENTS.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`

**Step 1: Add native player documentation**

Add to Core modules:
- `stream_resolver.py` — Resolves Twitch HLS URLs via streamlink CLI. Shared by native player and IINA fallback.

Add to UI modules:
- `native_player.py` — macOS NativePlayerController: AVPlayerView in NSSplitView docked above WKWebView. KVO for player state, main-thread-only AppKit operations.

Update Key Patterns:
- **Native playback.** `watch()` resolves HLS URL in background thread via `core/stream_resolver.py`, then hands URL to `NativePlayerController.play_stream()` on the main thread via `AppHelper.callAfter()`. Player state pushed to JS via `onPlayerState` callback.
- **IINA fallback.** `watch_external()` retains the original IINA launch path via `core/launcher.py`.

Add to Gotchas:
- All AppKit/AVKit operations in `ui/native_player.py` must run on the main thread. Use `AppHelper.callAfter()` from background threads.
- After channel switch, replace `AVPlayerItem` instead of recreating the player. Remove KVO observers from the old item first.
- Twitch HLS URLs are temporary. Long sessions may need re-resolve.

**Step 2: Commit**

```
docs: update CLAUDE.md and AGENTS.md for native AVPlayer
```
