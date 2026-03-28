# Native AVPlayer Integration

## Goal

Play Twitch streams inside TwitchX on macOS instead of launching IINA as a separate application.

## Architecture

- Keep the existing `pywebview` app shell and HTML interface.
- Add a macOS-only native player controller built with `AVPlayerView` and `NSSplitView`.
- The native controller owns a top docked player pane and keeps the existing `WKWebView` UI in the lower pane.
- The native player pane is collapsed when idle and expands when playback starts.

## Playback Flow

- JS still calls `pywebview.api.watch(channel, quality)`.
- Python resolves the HLS URL with Streamlink.
- The resolved HLS URL is handed to `AVPlayer`/`AVPlayerItem`.
- `AVPlayerView` starts playback in-app.
- Playback state changes are pushed back to JS so the existing status bar and watching indicators stay in sync.

## UX Rules

- The player is embedded in the same window, above the web UI.
- Default layout is a vertical split: player on top, app UI below.
- The player pane should remember a reasonable last-used height.
- Closing playback should collapse the native pane and return the full window to the web UI.
- Fullscreen and Picture in Picture should come from `AVPlayerView` native controls.
- Browser opening remains available; external IINA launch becomes an optional fallback, not the main path.

## Technical Notes

- Implement with `AVKit`, `AVFoundation`, `AppKit`, and `PyObjCTools.AppHelper`.
- All AppKit and AVKit operations must run on the main thread.
- The `NSWindow` comes from `pywebview` via `window.native`.
- Reparent the existing `WKWebView` into an `NSSplitView` instead of replacing the app shell.
- Keep the existing external-launch code path for compatibility, but switch `Watch` to native playback.
