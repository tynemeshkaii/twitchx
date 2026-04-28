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

**Entrypoint:** `main.py` → `app.py` (TwitchXApp) → creates `TwitchXApi` (from `ui/api/` package) + pywebview window from `ui/index.html`.

**Data flow:** JS event → `pywebview.api.<method>()` → `TwitchXApi` method → `threading.Thread` → `asyncio.new_event_loop()` runs async httpx → results pushed back to JS via `window.evaluate_js('window.onCallback(data)')`.

**Platform clients** (`core/platforms/`): `TwitchClient`, `KickClient`, `YouTubeClient` — each extends `BasePlatformClient` in `core/platforms/base.py`, which itself extends the abstract `PlatformClient` in `core/platform.py`. Shared data models live there too: `StreamInfo`, `ChannelInfo`, `CategoryInfo`, `PlaybackInfo`, `TokenData`, `UserInfo`.

**Chat clients** (`core/chats/`): `TwitchChatClient` (IRC over WebSocket), `KickChatClient` (Pusher WebSocket) — both extend `BaseChatClient` in `core/chats/base.py`, which itself extends the `ChatClient` ABC in `core/chat.py`. Shared models: `ChatMessage`, `ChatStatus`, `ChatSendResult`.

**Config** (`core/storage.py`): v2 nested format at `~/.config/twitchx/config.json`:
- `config.platforms.twitch`, `config.platforms.kick`, `config.platforms.youtube` — per-platform OAuth/API credentials
- `config.settings` — quality, refresh intervals, paths, shortcuts
- `config.favorites` — list of `{login, platform, display_name}` dicts
- Auto-migrates v1 flat config on first load (keys like `client_id`, `quality` at root)
- Merge-on-load: missing keys filled from `DEFAULT_CONFIG`, never crash on stale format

**`ui/api/`** (package, after 2026-04-28 Phase 2 decomposition) — Python↔JS bridge split into 7 modules:

| Module | Class | Responsibility |
|--------|-------|----------------|
| `ui/api/__init__.py` | `TwitchXApi` | Orchestrator — owns shared state, delegates to sub-components, config methods |
| `ui/api/_base.py` | `BaseApiComponent` | Shared infra: `_eval_js`, `_run_in_thread`, platform client accessors |
| `ui/api/auth.py` | `AuthComponent` | OAuth login/logout for Twitch, Kick, YouTube + connection tests |
| `ui/api/favorites.py` | `FavoritesComponent` | add/remove/reorder channels, import follows, search |
| `ui/api/data.py` | `DataComponent` | refresh, polling, browse categories/streams, channel profiles |
| `ui/api/streams.py` | `StreamsComponent` | watch, watch_direct, watch_external, watch_media, multistream, launch timer |
| `ui/api/chat.py` | `ChatComponent` | start/stop/send chat, save width/visibility, message callbacks |
| `ui/api/images.py` | `ImagesComponent` | avatar and thumbnail fetching via `_image_pool` |

Key patterns:
- `BaseApiComponent` provides `_twitch`, `_kick`, `_youtube`, `_config`, `_live_streams` via property delegation to `self._api` (the parent `TwitchXApi`)
- `TwitchXApi.__init__` creates all sub-components, passing `self` — components access shared state through the orchestrator
- All public `TwitchXApi` methods delegate to the appropriate sub-component (e.g. `self.login()` → `self._auth.login()`)
- `_eval_js(code)` wrapper suppresses errors when window is closing (`_shutdown` Event guard)
- `_run_in_thread(fn)` dispatches to `threading.Thread(daemon=True)` for all async I/O
- Bounded thread pools: `_image_pool` (max 8) for avatar/thumbnail fetches, `_send_pool` (max 2) for chat sends
- `app.py` unchanged — `from ui.api import TwitchXApi` imports from the package's `__init__.py`

**`ui/index.html`** — shell (~414 lines) that loads external CSS and JS modules. After 2026-04-28 Phase 3 decomposition:

| Directory | File | Responsibility |
|-----------|------|----------------|
| `ui/css/` | `tokens.css` | CSS custom properties (`:root`) |
| `ui/css/` | `reset.css` | Base resets, scrollbar, accessibility media queries |
| `ui/css/` | `layout.css` | `#app`, `#main`, `#sidebar`, `#content`, `#toolbar` |
| `ui/css/` | `components.css` | Buttons, inputs, cards, badges, sidebar sections, chat messages |
| `ui/css/` | `views.css` | `#player-view`, `#browse-view`, `#channel-view`, `#multistream-view` |
| `ui/css/` | `player.css` | `#player-bar`, `#chat-panel`, `#chat-resize-handle`, `#live-dot` |
| `ui/js/` | `state.js` | `TwitchX.state`, `TwitchX.multiState`, shortcuts, chat state |
| `ui/js/` | `utils.js` | `truncate`, `formatViewers`, `formatUptime`, `setStatus` |
| `ui/js/` | `api-bridge.js` | `pywebviewready`, `TwitchX.api`, profile helpers |
| `ui/js/` | `render.js` | `renderGrid`, `createStreamCard`, `createOnboardingCard` |
| `ui/js/` | `sidebar.js` | `renderSidebar`, `createSidebarItem/Section`, layout logic |
| `ui/js/` | `player.js` | `showPlayerView`, `hidePlayerView`, volume, fullscreen, PiP |
| `ui/js/` | `multistream.js` | Slot management, audio/chat focus, dynamic slot creation |
| `ui/js/` | `browse.js` | `showBrowseView`, category/top-stream loading |
| `ui/js/` | `channel.js` | `showChannelView`, tabs, media cards, follow/watch actions |
| `ui/js/` | `chat.js` | `submitChatMessage`, `renderChatEmotes`, reply handling |
| `ui/js/` | `settings.js` | `openSettings`, `saveSettings`, connection tests |
| `ui/js/` | `context-menu.js` | `showContextMenu`, `showSidebarContextMenu` |
| `ui/js/` | `keyboard.js` | `handleKeydown`, shortcut rebinding, hotkeys settings |
| `ui/js/` | `callbacks.js` | All `window.on*` thin proxies delegating to `TwitchX.*` |
| `ui/js/` | `init.js` | `DOMContentLoaded`, `_bind*()` event wiring, uptime interval |

Key patterns:
- All modules use IIFE + `TwitchX` namespace (no globals except `window.on*` callbacks)
- `var` replaced with `const`/`let` throughout
- Multistream slots created dynamically via `TwitchX._createMultiSlot()` (no 4× HTML duplication)
- All inline `onclick` attributes removed; event binding happens in `init.js` via `addEventListener`
- Script load order: `state` → `utils` → `api-bridge` → `render` → `sidebar` → `player` → `multistream` → `browse` → `channel` → `chat` → `settings` → `context-menu` → `keyboard` → `callbacks` → `init`

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

Coverage: `make cov` (terminal report) or `make cov-html` (HTML report in `htmlcov/`).

### Test infrastructure (`tests/conftest.py`)

Shared fixtures reduce duplication across test files:

| Fixture | Purpose |
|---------|---------|
| `temp_config_dir` | Redirects `~/.config/twitchx/` to a temp dir with a minimal `DEFAULT_CONFIG` pre-written. Use in any test that reads/writes config via `core.storage`. |
| `config_with_twitch_auth` | Same as `temp_config_dir` but pre-populates Twitch OAuth tokens. |
| `mock_twitch_client` | `MagicMock` configured as a `TwitchClient` with all common methods stubbed as `AsyncMock` returning sensibles defaults. |
| `mock_kick_client` | Same for `KickClient`. |
| `mock_youtube_client` | Same for `YouTubeClient`. |
| `capture_eval_js` | Callable that records all `_eval_js(code)` calls into `capture.calls`; provides `capture.assert_any(fragment)` helper. |
| `run_sync` | Patches `TwitchXApi._run_in_thread` to execute synchronously (calls `fn()` directly instead of spawning a thread). Apply once per test module and all `TwitchXApi` instances get synchronous dispatch. |

Example usage:
```python
def test_my_feature(temp_config_dir, run_sync, capture_eval_js):
    api = TwitchXApi()
    api._eval_js = capture_eval_js
    api.my_method("arg")
    capture_eval_js.assert_any("onSomething")
```

### Writing new tests

- Use `temp_config_dir` fixture instead of manually patching `core.storage.CONFIG_DIR`/`CONFIG_FILE`/`_OLD_CONFIG_DIR`
- Use `run_sync` fixture instead of `monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())`
- Use `capture_eval_js` fixture instead of `emitted: list[str] = []` + `lambda code: emitted.append(code)`
- Platform/client mocks: use `mock_twitch_client`, `mock_kick_client`, `mock_youtube_client` from conftest
- For OAuth tests, see `tests/test_oauth_server.py` for patterns

## Base class hierarchy (after 2026-04-28 Phase 1 refactoring)

### `BasePlatformClient` (`core/platforms/base.py`)

Shared infrastructure for `TwitchClient`, `KickClient`, `YouTubeClient`:

| Member | Purpose |
|--------|---------|
| `PLATFORM_ID` / `PLATFORM_NAME` | Set by subclasses (e.g. `"twitch"`, `"Twitch"`) |
| `_loop_clients` / `_token_locks` | Per-event-loop `httpx.AsyncClient` and `asyncio.Lock` caching |
| `_get_client()` | Returns or creates a per-loop `httpx.AsyncClient` |
| `_get_token_lock()` | Returns or creates a per-loop `asyncio.Lock` |
| `_platform_config()` | Returns platform config section via `get_platform_config(config, PLATFORM_ID)` |
| `_request(method, url, ...)` | HTTP wrapper with 429-retry and 401-token-refresh; returns `httpx.Response` |
| `_check_response_errors(resp)` | Override hook (YouTube: 403 quota exceeded) |
| `_client_headers()` / `_client_timeout()` | Override hooks for per-platform User-Agent / timeout |

Subclasses keep their own `_get()` with platform-specific auth/URL-building; `_request()` handles common retry logic.

### `BaseChatClient` (`core/chats/base.py`)

Shared infrastructure for `TwitchChatClient`, `KickChatClient`:

| Member | Purpose |
|--------|---------|
| `platform` | Set by subclasses (`"twitch"` or `"kick"`) |
| `on_message()` / `on_status()` | Callback registration |
| `_emit_status(connected, error)` | Push status updates to registered callback |
| `disconnect()` | Close WebSocket, emit offline status |
| `_reconnect_loop(connect_fn)` | Outer reconnect loop with exponential backoff (`RECONNECT_DELAYS = [3, 6, 12, 24, 48]`) |
| `StopReconnect` | Exception class — raise from `connect_fn` to exit reconnect loop cleanly |

Subclasses define `connect()` which sets up credentials and passes a closure `_connect_ws` to `_reconnect_loop()`.

### ABC updates (`core/platform.py`)

- `refresh_token() -> TokenData` → `refresh_user_token() -> str | None`
- `get_live_streams(channel_ids)` → `get_live_streams(identifiers)`
- `get_channel_info(channel_id)` → `get_channel_info(identifier)`
- `resolve_stream_url()` is now optional (`NotImplementedError` default)
- `follow()` / `unfollow()` removed from required interface
- `get_channel_vods()` / `get_channel_clips()` added as optional defaults (return `[]`)
