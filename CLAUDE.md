# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
./run.sh                    # or: uv run python main.py
TWITCHX_DEBUG=1 ./run.sh    # verbose logging (httpx requests, API params)
```

Requires `python-tk` for tkinter support (e.g. `brew install python-tk@3.14`).

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

TwitchX is a single-window CustomTkinter app that polls the Twitch Helix API for live streams and launches them via streamlink + IINA. Supports both app-level (client_credentials) and user-level (Authorization Code) OAuth flows.

**Data flow:** UI event → `TwitchXApp` callback → background `threading.Thread` → `asyncio.new_event_loop()` runs async httpx calls → results marshalled back to UI via `self.after(0, callback)`.

### Design system (`ui/theme.py`)

Centralized design token file imported by all UI modules and `core/utils.py`. Defines layered background depths (`BG_BASE` < `BG_SURFACE` < `BG_ELEVATED` < `BG_OVERLAY`), text hierarchy (`TEXT_PRIMARY` / `TEXT_SECONDARY` / `TEXT_MUTED`), status colors (`LIVE_GREEN`, `LIVE_RED`, `WARN_YELLOW`, `ERROR_RED`), brand colors (`ACCENT` / `ACCENT_HOVER` / `ACCENT_DIM`), spacing radii (`RADIUS_SM=6`, `RADIUS_MD=10`, `RADIUS_LG=14`), and `FONT_SYSTEM="-apple-system"` for native macOS SF Pro rendering. No hardcoded color strings in UI files — all colors come from theme tokens.

### Core modules (`core/`)

- **twitch.py** — Async Twitch Helix client (`TwitchClient`). Supports dual auth: client-credentials (app-level) and Authorization Code (user-level) OAuth with `user:read:follows` scope. Auto-refresh on expiry/401 (prefers user token when available, falls back to app token), rate-limit retry (429 + Ratelimit-Reset header), batching (100 items per request), `asyncio.Lock` to prevent concurrent token refreshes. Methods: `get_live_streams`, `get_users`, `get_games`, `search_channels`, `get_auth_url`, `exchange_code`, `refresh_user_token`, `get_current_user`, `get_followed_channels` (paginated). `reset_client()` replaces the `httpx.AsyncClient` to discard stale connections after temporary event loops close.
- **storage.py** — Reads/writes `~/.config/twitchx/config.json`. Merges stored config with `DEFAULT_CONFIG` so missing keys never crash the app. `DEFAULT_CONFIG` includes OAuth user fields (`user_id`, `user_login`, `user_display_name`, `refresh_token`, `token_type`). `token_is_valid()` checks token existence and expiry. Also manages avatar disk cache (`~/.config/twitchx/avatars/`) with 7-day expiry. Includes one-time migration from `~/.config/streamdeck/` on first load.
- **launcher.py** — Two-step stream launch: runs `streamlink --stream-url` to resolve an HLS URL, then passes it to `iina-cli` as a positional argument. Falls back to `best` quality if the requested quality is unavailable. Returns `LaunchResult` dataclass.
- **utils.py** — Shared helpers: `format_viewers()` (1.2k / 3.4M formatting) and `Tooltip` (lightweight hover tooltip using an undecorated `tk.Toplevel` with delayed show/hide). Imports theme tokens from `ui/theme.py`.
- **oauth_server.py** — Temporary HTTP server on `localhost:3457` that captures the OAuth authorization code callback and serves a confirmation page. Used for the Twitch OAuth login flow. 120s timeout, auto-shutdown after handling callback.

### UI modules (`ui/`)

- **theme.py** — Centralized design tokens (see "Design system" above). All UI files import from here — never define colors/fonts/spacing inline.
- **sidebar.py** — `BG_SURFACE` background, Discord-style layout. Profile area at top (login button or avatar + display name + logout link with hover effect + import follows button). "FAVORITES" section label (uppercase, `TEXT_MUTED`) with live count badge. Scrollable channel list with `ChannelItem` widgets: accent bar on left (3px, rounded), live dot (`LIVE_GREEN` / `TEXT_MUTED` for offline), avatar, channel name (bold only when selected; `TEXT_PRIMARY` for live, `TEXT_MUTED` for offline). Hover effect (`BG_OVERLAY`). Dark-styled right-click context menu. Drag-to-reorder favorites (5px threshold, visual indicator line) with manual order persistence via `on_reorder_channel` callback. Bottom area separated by 1px `BG_BORDER` line with search entry (`BG_ELEVATED`, bordered) and add button. Integrated channel search: 400ms debounce, dropdown with up to 8 results (bordered, `BG_ELEVATED`). Callback-driven (accepts `on_click`, `on_add_channel`, `on_remove_channel`, `on_search_channels`, `on_login`, `on_logout`, `on_import_follows`, `on_reorder_channel`).
- **stream_grid.py** — `BG_BASE` background (darkest, so cards pop). 3-column scrollable grid of `StreamCard` widgets with `BG_ELEVATED` background, `RADIUS_LG` corners, `BG_BORDER` border (hover adds `ACCENT` border). LIVE badge (`LIVE_RED`, `RADIUS_SM`), uptime, viewer count with trend indicator (▲/▼), channel name (`TEXT_PRIMARY`, bold), title (`TEXT_SECONDARY`, wraplength 200), game name (`ACCENT`, bold, truncated at 28 chars), `LIVE_GREEN` WATCHING overlay. Title tooltip on hover for long titles (>60 chars). Dark-styled context menu (Watch / Open in Browser / Copy URL / Add to favorites). Shimmer animation (`BG_ELEVATED`/`BG_OVERLAY` alternating). Smart onboarding: ⚡ icon + step cards (`BG_ELEVATED`) for new users, or 📺 "No favorites yet" when credentials set. "All quiet right now" empty state with subtitle. Diff-based in-place updates, sort (viewers/recent/alpha), game filter. Scrollbar themed (`BG_BORDER`/`ACCENT`).
- **player_bar.py** — `BG_SURFACE` background, height 48. Quality dropdown (`BG_ELEVATED`), Watch button with `set_channel_selected()` (disabled: `BG_ELEVATED`/`TEXT_MUTED`, active: `ACCENT`/white). Bordered icon buttons (`BG_ELEVATED`, `BG_BORDER` border, `RADIUS_SM`). Animated LIVE pulse dot (800ms alternating, hidden when not watching via `BG_SURFACE` text color). `set_watching()` starts/stops pulse. Status text, total viewers, last-updated timestamp (turns red when stale), refresh/settings buttons.

### Orchestrator (`app.py`)

`TwitchXApp` owns all mutable state. 3-column grid layout: sidebar (col 0) | 1px `BG_BORDER` separator (col 1) | main content (col 2). Main content has toolbar (row 0, `BG_SURFACE`) | 1px separator (row 1) | stream grid (row 2). Below main: 1px separator | player bar. Window opens at 960×640, min 700×500, `BG_BASE` background.

UI components are view-only and updated via their `update_*` methods. A single long-lived `TwitchClient` instance (`self._twitch`) is created in `__init__` and reused across all fetch cycles. Settings dialog (`SettingsDialog`) is a modal `CTkToplevel` (`BG_SURFACE` background, themed title, bordered inputs, `BG_ELEVATED`/`BG_BORDER` styled) with "Test Connection" button and show/hide toggle (👁) for client secret. Token is cleared when credentials change.

OAuth login: opens browser with auth URL → background thread starts temporary HTTP server (`oauth_server.py`) → captures code → exchanges for tokens → fetches user profile → imports follows on demand. `reset_client()` called after each OAuth flow to discard stale connections.

`set_channel_selected(True/False)` toggles Watch button appearance on channel click/deselect.

## Key Patterns

- **Never block the main thread.** All network I/O runs in `threading.Thread`. Use `self.after(0, callback)` to update UI from background threads.
- **Design token system.** All colors, fonts, and spacing are defined in `ui/theme.py` and imported by name. No hardcoded color strings in UI files. Layered depth: `BG_BASE` (window) → `BG_SURFACE` (sidebar, toolbar, player bar) → `BG_ELEVATED` (cards, inputs) → `BG_OVERLAY` (hover states). All typography uses `FONT_SYSTEM` ("-apple-system" → SF Pro on macOS).
- **Diff-based updates.** `StreamGrid.update_streams()` compares incoming logins against existing cards — if the set hasn't changed, it updates viewer counts / titles / thumbnails in-place (no flicker). Full rebuild only when channels go live/offline. `Sidebar.update_channels()` similarly patches avatars in-place when only images change.
- **Image caching.** `ImageCache` is an LRU `OrderedDict` (max 50 entries). Separate caches for avatars (28×28) and thumbnails (220×124). Avatars also have a disk cache (`~/.config/twitchx/avatars/<login>.png`, 7-day TTL). All image downscaling uses `Image.Resampling.LANCZOS` for sharp Retina output.
- **Parallel thumbnail loading.** `_load_thumbnails` uses `ThreadPoolExecutor(max_workers=5)` with `as_completed` for concurrent fetching. Thumbnails are Retina 2x (880×496 fetched, displayed at 220×124).
- **Retry with backoff.** `_fetch_data` retries up to 4 times on `httpx.ConnectError` with delays of [5, 15, 30]s. Status bar shows "Reconnecting... (attempt N/4)". A stale-data indicator turns the "Updated" timestamp red when data is older than 2× the refresh interval.
- **Launch progress timer.** While streamlink resolves the HLS URL (up to 15s), a `threading.Timer` ticks every 3s updating the status bar with elapsed time.
- **Channel search.** Sidebar entry doubles as a search box — typing triggers `TwitchClient.search_channels()` via background thread with 400ms debounce. Results appear in a bordered dropdown below the entry.
- **Refresh scheduling.** `tkinter.after()` drives periodic polling (configurable 30/60/120s). Manual refresh cancels and reschedules to avoid stacking.
- **Notifications.** When a channel transitions offline→live (not on first fetch), a native macOS notification fires via `osascript` in a background thread.
- **Keyboard shortcuts.** `r`/`F5`/`Cmd+R` refresh, `Space`/`Return` watch, `Cmd+,` settings, `Escape` deselect. Shortcuts are suppressed when a `CTkEntry` has focus.
- **Input sanitization.** `_sanitize_username()` strips Twitch URLs and invalid characters. `_migrate_favorites()` cleans dirty entries in config on startup.
- **Closure safety.** Lambdas passed to `self.after()` must capture exception variables via default arguments (e.g. `lambda code=status_code: ...`) because Python deletes `except ... as e` bindings after the block exits.
- **Drag-to-reorder.** Sidebar favorites support drag reordering via `<ButtonPress-1>`, `<B1-Motion>`, `<ButtonRelease-1>` with a 5px dead-zone threshold. A 2px accent-colored indicator line shows the drop position. When `respect_manual_order` is set, the sort preserves user-defined order (live channels first, then offline, each group in manual order).
- **Viewer trend tracking.** `StreamCard` stores `_prev_viewers` and shows ▲ (green) / ▼ (red) arrows when viewer count changes between refreshes.
- **Pulse animation.** `PlayerBar._pulse_tick()` alternates the live dot color every 800ms using `self.after()`. Starts on `set_watching(True)`, cancelled on `set_watching(False)`.
- **OAuth client reset.** After OAuth flows that create temporary event loops, `TwitchClient.reset_client()` replaces the `httpx.AsyncClient` to discard stale TCP connections bound to the closed loop.
- **Dark-styled context menus.** All `tk.Menu` instances are configured with theme tokens (`BG_ELEVATED` background, `TEXT_PRIMARY` foreground, `ACCENT` active background, `FONT_SYSTEM` font) for consistent dark appearance.
- **Visual separator lines.** 1px `CTkFrame` widgets with `fg_color=BG_BORDER` are used as horizontal/vertical separators between layout sections (sidebar/main, toolbar/grid, grid/player bar).
- **Channel selection state.** `PlayerBar.set_channel_selected()` toggles Watch button between disabled appearance (`BG_ELEVATED`/`TEXT_MUTED`) and active appearance (`ACCENT`/white) based on whether a channel is selected.

## Testing

41 unit tests across 4 files in `tests/`:

- **test_app.py** — `_sanitize_username` (plain names, URLs, whitespace, invalid chars, empty strings), `_migrate_favorites` (cleans URLs and deduplicates, noop on clean list)
- **test_twitch.py** — `VALID_USERNAME` regex (parametrized valid/invalid), filtering logic for `get_live_streams` and `get_users`, empty list handling, game ID deduplication
- **test_launcher.py** — `_get_stream_url` (success/failure/timeout/empty output), `launch_stream` (quality fallback, missing streamlink/IINA)
- **test_storage.py** — Config defaults/merge/roundtrip, avatar disk cache (missing/expired/fresh/write, dir creation)

Run with `make test` or `uv run pytest tests/ -v`.

## Adding New Functionality

- **New Twitch API endpoint:** Add async method to `TwitchClient`, call it in `_async_fetch` (app.py), handle result in `_on_data_fetched`.
- **New UI component:** Inherit from `ctk.CTkFrame`, accept callbacks in `__init__`, expose `update_*` methods. Wire into `TwitchXApp._build_ui`. Keep components stateless — `TwitchXApp` owns the data. Import colors/fonts/spacing from `ui/theme.py` — never hardcode.
- **New config field:** Add default to `DEFAULT_CONFIG` in `storage.py`. The merge-on-load pattern ensures backward compatibility.
- **New shared utility:** Put it in `core/utils.py` so both UI and core modules can import it.
- **New sort/filter option:** Add constant to `SORT_OPTIONS` in `stream_grid.py`, handle in `_apply_sort_filter`, wire dropdown in `app.py._build_ui`.
- **New design token:** Add to `ui/theme.py` and import by name where needed. Follow the layered depth and text hierarchy conventions.

## Gotchas

- `TwitchClient` is now long-lived (created once in `TwitchXApp.__init__`). Each fetch cycle reuses the same `httpx.AsyncClient` and TCP connections. The client is closed in `destroy()`. Don't share the client across threads — each background thread gets its own `asyncio.new_event_loop()`. After OAuth flows that close their event loop, always call `reset_client()` to avoid `RuntimeError: Event loop is closed` on the next fetch.
- `streamlink --stream-url` can take up to 15s; the timeout is set accordingly. If the quality isn't available, `launcher.py` automatically retries with `best`.
- The `_shutdown` `threading.Event` guards all `self.after()` calls from background threads to prevent callbacks after window destruction.
- The `_clear_fetching` call is in a `finally` block to guarantee the fetching lock is always released, even on retry exhaustion.
- Config migrated from `~/.config/streamdeck/` to `~/.config/twitchx/` — old config and avatars are copied automatically on first load if the new directory doesn't exist yet.
- `core/utils.py` imports from `ui/theme.py` — this creates a core→ui dependency. Keep it minimal (only color/font constants, no widget imports).
- When adding OAuth redirect URI to the Twitch dev console, use `http://localhost:3457/callback`.
