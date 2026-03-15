# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
./run.sh                    # or: uv run python main.py
STREAMDECK_DEBUG=1 ./run.sh # verbose logging (httpx requests, API params)
```

Requires `python-tk` for tkinter support (e.g. `brew install python-tk@3.14`).

## Dev Commands

```bash
make lint    # ruff check + pyright
make fmt     # ruff format
make test    # pytest tests/ -v
make check   # lint + test
```

## Architecture

StreamDeck is a single-window CustomTkinter app that polls the Twitch Helix API for live streams and launches them via streamlink + IINA.

**Data flow:** UI event → `StreamDeckApp` callback → background `threading.Thread` → `asyncio.new_event_loop()` runs async httpx calls → results marshalled back to UI via `self.after(0, callback)`.

### Core modules (`core/`)

- **twitch.py** — Async Twitch Helix client (`TwitchClient`). Handles client-credentials auth with auto-refresh on expiry/401, rate-limit retry (429 + Ratelimit-Reset header), batching (100 items per request), and `asyncio.Lock` to prevent concurrent token refreshes.
- **storage.py** — Reads/writes `~/.config/streamdeck/config.json`. Merges stored config with `DEFAULT_CONFIG` so missing keys never crash the app. Also manages avatar disk cache (`~/.config/streamdeck/avatars/`) with 7-day expiry.
- **launcher.py** — Two-step stream launch: runs `streamlink --stream-url` to resolve an HLS URL, then passes it to `iina-cli` as a positional argument. Falls back to `best` quality if the requested quality is unavailable. Returns `LaunchResult` dataclass.
- **utils.py** — Shared helpers. Currently has `format_viewers()` (1.2k / 3.4M formatting), used by both `stream_grid.py` and `player_bar.py`.

### UI modules (`ui/`)

- **sidebar.py** — Favorites list with live indicator dots, async-loaded avatars, add/remove channels. All channels are clickable (live and offline). Diff-based updates: if channels/live-set haven't changed, only avatar images are patched in-place. Right-click context menu for "Remove from favorites". Callback-driven (accepts `on_click`, `on_add_channel`, `on_remove_channel`).
- **stream_grid.py** — 3-column scrollable grid of `StreamCard` widgets showing thumbnail, game, viewer count, uptime. Supports diff-based in-place updates, sort (viewers/recent/alpha), and game filter. Right-click context menu (Watch / Open in Browser / Copy URL). Green "▶ WATCHING" overlay on the active card. Also renders onboarding screen for new users.
- **player_bar.py** — Bottom bar with quality dropdown, Watch button, globe (🌐) open-in-browser button, status text, total viewer count, last-updated timestamp (turns red when stale), refresh button, settings gear.

### Orchestrator (`app.py`)

`StreamDeckApp` owns all mutable state. UI components are view-only and updated via their `update_*` methods. Settings dialog (`SettingsDialog`) is a modal `CTkToplevel` (Escape closes, `grab_set` makes modal) with a "Test Connection" button that validates credentials before saving. Token is cleared when credentials change.

## Key Patterns

- **Never block the main thread.** All network I/O runs in `threading.Thread`. Use `self.after(0, callback)` to update UI from background threads.
- **Diff-based updates.** `StreamGrid.update_streams()` compares incoming logins against existing cards — if the set hasn't changed, it updates viewer counts / titles / thumbnails in-place (no flicker). Full rebuild only when channels go live/offline. `Sidebar.update_channels()` similarly patches avatars in-place when only images change.
- **Image caching.** `ImageCache` is an LRU `OrderedDict` (max 50 entries). Separate caches for avatars (28×28) and thumbnails (220×124). Avatars also have a disk cache (`~/.config/streamdeck/avatars/<login>.png`, 7-day TTL) to avoid re-downloading on every launch.
- **Parallel thumbnail loading.** `_load_thumbnails` uses `ThreadPoolExecutor(max_workers=5)` with `as_completed` for concurrent fetching. Thumbnails are Retina 2x (880×496 fetched, displayed at 220×124).
- **Retry with backoff.** `_fetch_data` retries up to 4 times on `httpx.ConnectError` with delays of [5, 15, 30]s. Status bar shows "Reconnecting... (attempt N/4)". A stale-data indicator turns the "Updated" timestamp red when data is older than 2× the refresh interval.
- **Launch progress timer.** While streamlink resolves the HLS URL (up to 15s), a `threading.Timer` ticks every 3s updating the status bar with elapsed time.
- **Refresh scheduling.** `tkinter.after()` drives periodic polling (configurable 30/60/120s). Manual refresh cancels and reschedules to avoid stacking.
- **Notifications.** When a channel transitions offline→live (not on first fetch), a native macOS notification fires via `osascript` in a background thread.
- **Keyboard shortcuts.** `r`/`F5` refresh, `Space`/`Return` watch, `Cmd+,` settings, `Escape` deselect. Shortcuts are suppressed when a `CTkEntry` has focus.
- **Input sanitization.** `_sanitize_username()` strips Twitch URLs and invalid characters. `_migrate_favorites()` cleans dirty entries in config on startup.
- **Closure safety.** Lambdas passed to `self.after()` must capture exception variables via default arguments (e.g. `lambda code=status_code: ...`) because Python deletes `except ... as e` bindings after the block exits.
- **Accent color.** `#9146FF` (Twitch purple) is defined as `ACCENT` in multiple UI files.

## Testing

35 unit tests across 4 files in `tests/`:

- **test_app.py** — `_sanitize_username` (plain names, URLs, whitespace, invalid chars, empty strings)
- **test_twitch.py** — `VALID_USERNAME` regex validation, filtering logic for `get_live_streams` and `get_users`
- **test_launcher.py** — `_get_stream_url` (success/failure/empty output), `launch_stream` (quality fallback, missing streamlink/IINA)
- **test_storage.py** — Config load/save/merge, avatar disk cache (missing/expired/fresh/write)

## Adding New Functionality

- **New Twitch API endpoint:** Add async method to `TwitchClient`, call it in `_async_fetch` (app.py), handle result in `_on_data_fetched`.
- **New UI component:** Inherit from `ctk.CTkFrame`, accept callbacks in `__init__`, expose `update_*` methods. Wire into `StreamDeckApp._build_ui`. Keep components stateless — `StreamDeckApp` owns the data.
- **New config field:** Add default to `DEFAULT_CONFIG` in `storage.py`. The merge-on-load pattern ensures backward compatibility.
- **New shared utility:** Put it in `core/utils.py` so both UI and core modules can import it.
- **New sort/filter option:** Add constant to `SORT_OPTIONS` in `stream_grid.py`, handle in `_apply_sort_filter`, wire dropdown in `app.py._build_ui`.

## Gotchas

- `TwitchClient` uses an `asyncio.Lock` for token refresh — creating multiple clients per fetch is fine since each gets its own event loop, but don't share a client across threads.
- `streamlink --stream-url` can take up to 15s; the timeout is set accordingly. If the quality isn't available, `launcher.py` automatically retries with `best`.
- The `_shutdown` `threading.Event` guards all `self.after()` calls from background threads to prevent callbacks after window destruction.
- The `_clear_fetching` call is in a `finally` block to guarantee the fetching lock is always released, even on retry exhaustion.
