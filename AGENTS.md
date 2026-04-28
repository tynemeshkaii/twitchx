# AGENTS.md

TwitchX — a multi-platform live-stream client for macOS. Single-window pywebview app with native WebKit WebView. Polls Twitch, Kick, and YouTube APIs for live streams; plays via native AVPlayer or IINA fallback.

## Dev Commands

```bash
make run     # launch (uv run python main.py)
make debug   # launch with TWITCHX_DEBUG=1 (httpx request/response logging)
make lint    # ruff check . && pyright .
make fmt     # ruff format .
make test    # uv run pytest tests/ -v
make check   # lint + test (run before committing)
```

Run a single test file: `uv run pytest tests/test_app.py -v`

## Architecture

**Entrypoint:** `main.py` → `app.py` (TwitchXApp) → creates `ui/api.py` (TwitchXApi bridge) + pywebview window from `ui/index.html`.

**Data flow:** JS event → `pywebview.api.<method>()` → `TwitchXApi` method → `threading.Thread` → `asyncio.new_event_loop()` runs async httpx → results pushed back to JS via `window.evaluate_js('window.onCallback(data)')`.

**Platform clients** (`core/platforms/`): `TwitchClient`, `KickClient`, `YouTubeClient` — each extends the abstract `PlatformClient` in `core/platform.py`. Shared data models live there too: `StreamInfo`, `ChannelInfo`, `CategoryInfo`, `PlaybackInfo`, `TokenData`, `UserInfo`.

**Chat clients** (`core/chats/`): `TwitchChatClient` (IRC over WebSocket), `KickChatClient` (Pusher WebSocket) — both implement `ChatClient` ABC in `core/chat.py`. Shared models: `ChatMessage`, `ChatStatus`, `ChatSendResult`.

**Config** (`core/storage.py`): v2 nested format at `~/.config/twitchx/config.json`:
- `config.platforms.twitch`, `config.platforms.kick`, `config.platforms.youtube` — per-platform OAuth/API credentials
- `config.settings` — quality, refresh intervals, paths, shortcuts
- `config.favorites` — list of `{login, platform, display_name}` dicts
- Auto-migrates v1 flat config on first load (keys like `client_id`, `quality` at root)
- Merge-on-load: missing keys filled from `DEFAULT_CONFIG`, never crash on stale format

**`ui/api.py`** is the Python↔JS bridge (2855 lines). Holds references to all three platform clients + chat client. Key patterns:
- `_eval_js(code)` wrapper suppresses errors when window is closing (`_shutdown` Event guard)
- `_run_in_thread(fn)` dispatches to `threading.Thread(daemon=True)` for all async I/O
- Bounded thread pools: `_image_pool` (max 8) for avatar/thumbnail fetches, `_send_pool` (max 2) for chat sends

**`ui/index.html`** — all HTML/CSS/JS inline, no external dependencies. All design tokens as CSS custom properties in `:root`.

## Key Gotchas

### Never block the main thread
All network I/O runs in `threading.Thread` with `asyncio.new_event_loop()`. Results pushed to JS via `window.evaluate_js()`. The `_shutdown` `threading.Event` guards all `_eval_js()` calls from background threads.

### `watch()` vs `watch_direct()` vs `add_multi_slot()`
- `watch()` gates on `self._live_streams` cache — use for channels in the poller's grid
- `watch_direct(channel, platform, quality)` for streams opened from browse (not in live cache). Works for Twitch/Kick only; YouTube browse cards have no `video_id`
- `add_multi_slot(slot_idx, channel, platform, quality)` for multistream — calls `resolve_hls_url` directly

### Platform-specific identity rules
- **YouTube channel IDs (`UCxxxx…`)** are case-sensitive — never lowercase them. `remove_channel` and favorite lookups must use exact-case comparison for YouTube
- **`favorites_meta` uses `"platform:login"` compound keys** (not bare `login`) to avoid collisions when two platforms have identically-named streamers
- **Kick `channel_id`** is an integer in raw API responses — always coerce with `str()` in `_normalize_channel_info_to_profile`

### `_normalize_channel_info_to_profile(platform)` patterns
Maps three different raw API shapes to a unified dict. YouTube's `is_live` is set `False` by the normalizer, then corrected by `get_channel_profile` checking `self._live_streams` cache. Kick's `avatar_url` comes from `user.profile_pic`.

### Browse cache
`_fetch_browse_categories` and `_fetch_browse_top_streams` cache per-platform slots in `~/.config/twitchx/cache/browse_cache.json` (10-min TTL). Use a **local** `config = load_config()` in browse threads — never assign `self._config` from a background thread (shared-state race with polling thread).

### Multistream display rules
- Show a slot container with **`element.style.display = 'block'`** — never `style.display = ''`. Clearing the inline style hands control to CSS, and `.ms-slot-active { display: none }` is default
- WKWebView plays audio on `<video>` elements even when parent is `display: none`

### YouTube browse quota
`get_categories()` costs 1 unit; `get_top_streams()` costs 100 units. Both silently return `[]` when quota exhausted. The 10-min browse cache prevents re-calling on every category click.

### `streamlink --stream-url` timeout
Can take up to 15s. If the requested quality isn't available, falls back to `best` automatically.

### OAuth flow
- Redirect URI: `http://localhost:3457/callback`
- OAuth server in `core/oauth_server.py` has 120s timeout, auto-shuts after handling callback
- After OAuth flows, HTTP clients are event-loop-scoped — `reset_client()` is now a no-op (each loop gets its own `httpx.AsyncClient`)

### Chat
- `send_chat` dispatches via `_send_pool` (`ThreadPoolExecutor(max_workers=2)`) — not raw threads
- `KickChatClient` subscribes to three Pusher aliases — deduplicates via LRU set of `_seen_msg_ids`
- `stop_chat`: null `self._chat_client` before dispatching async disconnect (race safety)
- `onChatStatus` gates send input on `status.connected && status.authenticated`, not `connected` alone

### Escape key priority
Settings overlay → multistream view → context menu → search dropdown. Always dismiss topmost layer first.

### `renderGrid` view guards
Returns early when `#browse-view` or `#multistream-view` is open — prevents the periodic poller from restoring `stream-grid`'s inline `style.display` over `class="hidden"`.

### pyright exclusion
`ui/native_player.py` is excluded in `pyproject.toml` — pyobjc type stubs are incomplete. All AppKit/AVKit ops in that file must run on main thread via `AppHelper.callAfter()`.

### DOM safety
All dynamic content uses `document.createElement()` + `textContent` — no `innerHTML` with user data.

### Config idempotency
`pywebview` `get_full_config_for_settings()` is synchronous (JS calls, gets immediate return). For async ops, always use callback pattern.

## Testing

Run all: `make test` or `uv run pytest tests/ -v`. Run a single file: `uv run pytest tests/test_app.py -v`.
