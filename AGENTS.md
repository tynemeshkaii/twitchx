# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Running the App

```bash
./run.sh                    # or: uv run python main.py
TWITCHX_DEBUG=1 ./run.sh    # verbose logging (httpx requests, API params)
```

## Dev Commands

```bash
make run     # launch the app
make debug   # launch with TWITCHX_DEBUG=1
make lint    # ruff check + pyright
make fmt     # ruff format
make test    # pytest tests/ -v
make check   # lint + test
make push    # git add, commit with timestamp, push
```

## Architecture

TwitchX is a single-window pywebview app that polls the Twitch Helix API for live streams and launches them via streamlink + IINA. Uses a native WebKit WebView on macOS. Supports both app-level (client_credentials) and user-level (Authorization Code) OAuth flows.

**Data flow:** JS event → `pywebview.api.<method>()` → `TwitchXApi` method → background `threading.Thread` → `asyncio.new_event_loop()` runs async httpx calls → results pushed back to JS via `window.evaluate_js('window.onCallback(data)')`.

### Design system (`ui/index.html` CSS)

All design tokens are CSS custom properties in `:root`. Layered background depths (`--bg-base` < `--bg-surface` < `--bg-elevated` < `--bg-overlay`), text hierarchy (`--text-primary` / `--text-secondary` / `--text-muted`), status colors (`--live-green`, `--live-red`, `--warn-yellow`, `--error-red`), brand colors (`--accent` / `--accent-hover`), spacing radii (`--radius-sm` / `--radius-md` / `--radius-lg` / `--radius-xl`), and `-apple-system` font for native macOS SF Pro rendering. Glassmorphism on cards and modals via `backdrop-filter: blur()`.

A minimal `ui/theme.py` exists only to provide `ACCENT`, `BG_ELEVATED`, `FONT_SYSTEM`, `TEXT_PRIMARY` constants for `core/utils.py` compatibility.

### Core modules (`core/`)

- **twitch.py** — Async Twitch Helix client (`TwitchClient`). Supports dual auth: client-credentials (app-level) and Authorization Code (user-level) OAuth with `user:read:follows` scope. Auto-refresh on expiry/401 (prefers user token when available, falls back to app token), rate-limit retry (429 + Ratelimit-Reset header), batching (100 items per request), `asyncio.Lock` to prevent concurrent token refreshes. Methods: `get_live_streams`, `get_users`, `get_games`, `search_channels`, `get_auth_url`, `exchange_code`, `refresh_user_token`, `get_current_user`, `get_followed_channels` (paginated). `reset_client()` replaces the `httpx.AsyncClient` to discard stale connections after temporary event loops close.
- **storage.py** — Reads/writes `~/.config/twitchx/config.json`. Merges stored config with `DEFAULT_CONFIG` so missing keys never crash the app. `DEFAULT_CONFIG` includes OAuth user fields (`user_id`, `user_login`, `user_display_name`, `refresh_token`, `token_type`). `token_is_valid()` checks token existence and expiry. Also manages avatar disk cache (`~/.config/twitchx/avatars/`) with 7-day expiry. Includes one-time migration from `~/.config/streamdeck/` on first load.
- **stream_resolver.py** — Resolves Twitch HLS URLs via `streamlink --stream-url`. Falls back to `best` quality if the requested quality is unavailable. Shared by native AVPlayer playback and IINA fallback.
- **launcher.py** — External IINA launch (fallback): resolves HLS URL via streamlink, then passes it to `iina-cli`. Returns `LaunchResult` dataclass.
- **utils.py** — Shared helpers: `format_viewers()` (1.2k / 3.4M formatting) and `Tooltip` (legacy tkinter tooltip, retained for compatibility). Imports theme tokens from `ui/theme.py`.
- **oauth_server.py** — Temporary HTTP server on `localhost:3457` that captures the OAuth authorization code callback and serves a confirmation page. Used for the Twitch OAuth login flow. 120s timeout, auto-shutdown after handling callback.

### UI modules (`ui/`)

- **api.py** — `TwitchXApi` class: the Python↔JS bridge exposed to pywebview via `js_api`. Wraps all `core/` modules. All network I/O runs in `threading.Thread` with `asyncio.new_event_loop()`. Results are pushed to JS via `window.evaluate_js()` calling global callbacks (`onStreamsUpdate`, `onAvatar`, `onThumbnail`, `onLaunchResult`, `onPlayerState`, etc.). `watch()` resolves HLS URL in background thread, then plays via native AVPlayer on main thread. `watch_external()` launches IINA as fallback. `stop_player()` stops native playback. Images are resized via Pillow and base64-encoded before sending to JS.
- **native_player.py** — macOS `NativePlayerController`: manages `AVPlayerView` docked in an `NSSplitView` above the `WKWebView`. Player pane collapsed by default, expands on play. KVO observes `AVPlayerItem.status` and `AVPlayer.timeControlStatus`. State changes pushed to JS via `onPlayerState` callback. Player height persisted in config. Fullscreen and PiP from native `AVPlayerView` controls. All AppKit/AVKit operations must run on main thread.
- **index.html** — Single self-contained HTML file with all CSS and JS inline. No external dependencies. Contains the full UI: sidebar (profile, favorites, search), stream grid (glassmorphism cards with shimmer placeholders), toolbar (sort/filter), player bar (quality, watch, stop, IINA fallback, status), settings modal, and custom context menus. Uses diff-based rendering (compares login sets, updates in-place when unchanged). All DOM manipulation uses safe methods (createElement, textContent) — no innerHTML with user data.
- **theme.py** — Minimal constants (`ACCENT`, `BG_ELEVATED`, `FONT_SYSTEM`, `TEXT_PRIMARY`) retained only for `core/utils.py` imports.

### Orchestrator (`app.py`)

`TwitchXApp` creates the `TwitchXApi` bridge, reads `ui/index.html`, opens a pywebview window (960×640, min 700×500, `#0E0E1A` background), wires `window.events.loaded` to start polling, and `window.events.closing` to clean up. Retains `_sanitize_username()` and `_migrate_favorites()` as static/instance methods for test compatibility.

## Key Patterns

- **Never block the main thread.** All network I/O runs in `threading.Thread`. Results are pushed to JS via `window.evaluate_js()`.
- **Python↔JS bridge.** JS calls Python via `pywebview.api.<method>()`. Python calls JS via `self._window.evaluate_js('window.onCallback(data)')`. All callbacks use `json.dumps()` for safe data serialization.
- **Design tokens in CSS.** All colors, fonts, and spacing are CSS custom properties in `ui/index.html`. The layered depth system: `--bg-base` (window) → `--bg-surface` (sidebar, toolbar, player bar) → `--bg-elevated` (cards, inputs) → `--bg-overlay` (hover states).
- **Diff-based rendering.** `renderGrid()` compares incoming stream logins against existing DOM cards — if the set hasn't changed, it updates viewer counts / titles / thumbnails in-place (no DOM rebuild). Full rebuild only when channels go live/offline. `renderSidebar()` similarly patches in-place when order unchanged.
- **Image pipeline.** Avatars (56×56 LANCZOS → base64 PNG) and thumbnails (440×248 LANCZOS → base64 JPEG quality=85) are resized in Python, base64-encoded, and pushed to JS via `onAvatar`/`onThumbnail` callbacks. Avatars also have a disk cache (`~/.config/twitchx/avatars/<login>.png`, 7-day TTL).
- **Retry with backoff.** `_fetch_data` retries up to 4 times on `httpx.ConnectError` with delays of [5, 15, 30]s. Status bar shows "Reconnecting... (attempt N/4)". A stale-data indicator turns the "Updated" timestamp red when data is older than 2× the refresh interval.
- **Launch progress timer.** While streamlink resolves the HLS URL (up to 15s), a `threading.Timer` ticks every 3s updating the status bar with elapsed time.
- **Channel search.** Sidebar search input triggers `TwitchClient.search_channels()` via background thread with 400ms JS debounce. Results appear in a dropdown below the input.
- **Refresh scheduling.** `threading.Timer` loop drives periodic polling (configurable 30/60/120s). `start_polling()` cancels existing timer before scheduling new one.
- **Notifications.** When a channel transitions offline→live (not on first fetch), a native macOS notification fires via `osascript` in a background thread.
- **Keyboard shortcuts.** `r`/`F5`/`Cmd+R` refresh, `Space`/`Return` watch, `Cmd+,` settings, `Escape` deselect. Shortcuts are suppressed when an input element has focus.
- **Input sanitization.** `_sanitize_username()` strips Twitch URLs and invalid characters. `_migrate_favorites()` cleans dirty entries in config on startup.
- **Drag-to-reorder.** Sidebar favorites support HTML5 drag-and-drop reordering. Live channels sort first (in manual order), then offline (in manual order).
- **Viewer trend tracking.** JS `state.prevViewers` tracks previous viewer counts, showing ▲ (green) / ▼ (red) arrows when counts change between refreshes.
- **Pulse animation.** CSS `@keyframes pulse` animates the live dot in the player bar (1.6s ease-in-out infinite). Toggled via `.visible` class.
- **OAuth client reset.** After OAuth flows that create temporary event loops, `TwitchClient.reset_client()` replaces the `httpx.AsyncClient` to discard stale TCP connections bound to the closed loop.
- **Safe DOM manipulation.** All dynamic content uses `document.createElement()` and `textContent` — no innerHTML with user-supplied data.
- **Glassmorphism.** Stream cards and settings modal use `backdrop-filter: blur(20px) saturate(180%)` with semi-transparent backgrounds and subtle borders.
- **Native playback.** `watch()` resolves HLS URL in background thread via `core/stream_resolver.py`, then hands URL to `NativePlayerController.play_stream()` on the main thread via `AppHelper.callAfter()`. Player state pushed to JS via `onPlayerState` callback.
- **IINA fallback.** `watch_external()` retains the original IINA launch path via `core/launcher.py` for users who prefer external playback.

## Testing

57 unit tests across 6 files in `tests/`:

- **test_app.py** — `_sanitize_username` (plain names, URLs, whitespace, invalid chars, empty strings), `_migrate_favorites` (cleans URLs and deduplicates, noop on clean list)
- **test_twitch.py** — `VALID_USERNAME` regex (parametrized valid/invalid), filtering logic for `get_live_streams` and `get_users`, empty list handling, game ID deduplication
- **test_launcher.py** — `_get_stream_url` (success/failure/timeout/empty output), `launch_stream` (quality fallback, missing streamlink/IINA)
- **test_stream_resolver.py** — `resolve_hls_url` (success, quality fallback, timeout, missing streamlink, all-fail)
- **test_native_player.py** — `NativePlayerController` (init state, play without attach, height clamping, cleanup, stop safety, state callback)
- **test_storage.py** — Config defaults/merge/roundtrip, avatar disk cache (missing/expired/fresh/write, dir creation)

Run with `make test` or `uv run pytest tests/ -v`.

## Adding New Functionality

- **New Twitch API endpoint:** Add async method to `TwitchClient`, call it in `_async_fetch` (`ui/api.py`), send results to JS via `_eval_js()` with a new global callback.
- **New UI component:** Add HTML structure in `ui/index.html`, style with CSS custom properties, wire JS event handlers in the `DOMContentLoaded` listener. Add corresponding Python method in `TwitchXApi` if it needs backend data.
- **New Python→JS callback:** Add method in `TwitchXApi` that calls `self._eval_js(f"window.onNewCallback({json.dumps(data)})")`. Add `window.onNewCallback = function(data) { ... }` in the JS.
- **New JS→Python call:** Add public method to `TwitchXApi`. JS calls it via `pywebview.api.method_name(args)`. Method runs network I/O in a thread, pushes result back via `_eval_js()`.
- **New config field:** Add default to `DEFAULT_CONFIG` in `storage.py`. The merge-on-load pattern ensures backward compatibility.
- **New design token:** Add to `:root` CSS custom properties in `ui/index.html`. Use `var(--token-name)` in CSS.
- **New sort/filter option:** Add `<option>` to `#sort-select` in HTML, handle new key in `getFilteredSortedStreams()` JS function.

## Gotchas

- `TwitchClient` is long-lived (created once in `TwitchXApi.__init__`). Each fetch cycle reuses the same `httpx.AsyncClient` and TCP connections. The client is closed in `TwitchXApi.close()`. Don't share the client across threads — each background thread gets its own `asyncio.new_event_loop()`. After OAuth flows that close their event loop, always call `reset_client()` to avoid `RuntimeError: Event loop is closed` on the next fetch.
- `streamlink --stream-url` can take up to 15s; the timeout is set accordingly. If the quality isn't available, `launcher.py` automatically retries with `best`.
- The `_shutdown` `threading.Event` guards all `_eval_js()` calls from background threads to prevent JS evaluation after window destruction.
- The `_fetching` flag is cleared in a `finally` block to guarantee the fetching lock is always released, even on retry exhaustion.
- Config migrated from `~/.config/streamdeck/` to `~/.config/twitchx/` — old config and avatars are copied automatically on first load if the new directory doesn't exist yet.
- `core/utils.py` imports from `ui/theme.py` — this creates a core→ui dependency. Keep `ui/theme.py` minimal (only the 4 constants core/utils needs).
- When adding OAuth redirect URI to the Twitch dev console, use `http://localhost:3457/callback`.
- pywebview `get_full_config_for_settings()` is a synchronous call (JS calls it and gets an immediate return). Use this pattern for simple config reads. For async operations, always use the callback pattern.
- `window.evaluate_js()` can only be called after the window `loaded` event fires. The `_eval_js()` wrapper suppresses errors if the window is closing.
- All AppKit/AVKit operations in `ui/native_player.py` must run on the main thread. Use `AppHelper.callAfter()` from background threads to schedule work on main thread.
- After channel switch, replace `AVPlayerItem` instead of recreating the player. Remove KVO observers from the old item first to avoid zombie observer crashes.
- Twitch HLS URLs are temporary. Long playback sessions may need re-resolve.
- `ui/native_player.py` is excluded from pyright checks (`pyproject.toml` ignore) because pyobjc type stubs are incomplete.
