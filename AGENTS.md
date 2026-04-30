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

## 2026-04-29 — Phase 4: polymorphic platform strategy + constants consolidation

Replaced platform-branching `if/elif` chains with polymorphic `PlatformClient` methods; consolidated constants; removed dead code; migrated favorites logic into `storage.py`.

### `core/constants.py` (new)
Consolidated shared constants previously scattered across modules:
- `IINA_PATH` — fallback media player executable
- `BROWSE_CACHE_TTL_SECONDS` (600), `BROWSE_CACHE_FILE`
- `OAUTH_REDIRECT_PORT` (3457), `OAUTH_TIMEOUT_SECONDS` (120)
- `AVATAR_SIZE`, `THUMBNAIL_SIZE`
- `RECONNECT_DELAYS` — chat exponential backoff

### Polymorphic `PlatformClient` methods (`core/platform.py`)
Added to `PlatformClient` ABC and implemented in all three subclasses:

| Method | Twitch | Kick | YouTube |
|--------|--------|------|---------|
| `sanitize_identifier(raw)` | `sanitize_twitch_login` | `sanitize_kick_slug` | preserves `UC…` case, `@handle`, `v:` prefix |
| `normalize_search_result(raw)` | maps Twitch Helix shape | maps Typesense shape | maps YouTube search shape |
| `normalize_stream_item(raw)` | maps `search_channels`/`followed` item | maps browse/top stream item | maps browse/top stream item |
| `build_stream_url(channel, **kwargs)` | `https://twitch.tv/{channel}` | `https://kick.com/{channel}` | `https://youtube.com/channel/{channel}` or `https://youtube.com/watch?v={id}` |

### `core/stream_resolver.py` & `core/launcher.py`
- `resolve_hls_url(url, platform_client, quality)` — accepts `PlatformClient` instance instead of `platform: str`
- `launch_stream(url, platform_client, quality, player)` — same; calls `platform_client.build_stream_url(...)` when no direct URL

### Dead code removal
- Deleted `Tooltip` class and `tkinter` import from `core/utils.py`
- Deleted `ui/theme.py`

### Favorites migration into `core/storage.py`
- Moved `_migrate_favorites` from `app.py` → `storage._migrate_favorites_v2`
- Added `sanitize_twitch_login`, `sanitize_kick_slug`, `sanitize_youtube_login` to `core/utils.py` (pure functions, avoids circular imports)
- `_migrate_favorites_v2` handles:
  - v1 string favorites → v2 dict conversion
  - URL extraction (`twitch.tv/…`, `kick.com/…`, `youtube.com/channel/…`)
  - YouTube `UC…` case preservation, `@handle` and `v:` prefix preservation
  - Deduplication with human-readable `display_name` preference for YouTube
  - Kick slug hyphen preservation
- Removed static normalizers from `ui/api/__init__.py`: `_sanitize_channel_name`, `_normalize_*_search_result`, `_build_*_stream_item`

### `ui/api/` updates for polymorphism
- `favorites.py`: uses `client.sanitize_identifier()` and `client.normalize_search_result()`
- `data.py`: uses `client.normalize_stream_item()` in `_on_data_fetched`
- `streams.py`: updated `resolve_hls_url()` and `launch_stream()` calls for new signatures

### Post-audit fixes
- `sanitize_youtube_login("v:dQw4w9WgXcQ")` now correctly returns `"v:dQw4w9WgXcQ"` instead of mangling to `@vdqw4w9wgxcq`
- `_migrate_favorites_v2` keeps sanitized entry login when merging best display name, preventing stale `yt_best` entries from overwriting a freshly-sanitized `v:` or `@handle` login

---

## 2026-04-29 — pywebview 6.x + WKWebView loading fixes

### Problem
pywebview 6.x injects its bridge code (`pywebview.state`, `pywebview.api`, `finish.js`) via `evaluateJavaScript` during HTML parsing. When using `html=` (inline HTML) with **multiple** inline `<script>` blocks, WKWebView silently drops all blocks **after** the pywebview injection point. This caused:
- `TwitchX.api` never being set (`api-bridge.js` handler ran after injection)
- All `TwitchX.*` methods missing (utils.js, render.js, etc. never executed)
- Entire UI non-functional (buttons, settings, browse — nothing worked)

### Solution
`app.py` now uses `_inline_resources()` to:
1. **Inline CSS** — replace `<link rel="stylesheet" href="...">` with `<style>content</style>`
2. **Merge all JS modules into a single `<script>` block** — replace all `<script src="..."></script>` tags with one merged inline script. This prevents pywebview from interleaving injection between script blocks.
3. **Remove duplicate `window.TwitchX` bootstrap** — only `state.js` declares `window.TwitchX = window.TwitchX || {}; const TwitchX = window.TwitchX;`, subsequent modules skip the redeclaration.

### `const TwitchX` → `window.TwitchX` fix
All `ui/js/*.js` files now use:
```javascript
window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;
```
instead of `const TwitchX = window.TwitchX || {};` which threw `SyntaxError` when modules were merged into one lexical scope.

### `favorites_meta` bare-login keys
`ui/api/data.py` now builds `favorites_meta` with bare `login` keys (not `"platform:login"` compound keys), matching what JS expects when looking up platform info for sidebar avatars and context menus.

### Multistream quality lookup
`ui/js/multistream.js` reads `(cfg && cfg.quality) || 'best'` instead of `cfg.settings.quality`.

### Multiplatform `get_config()`
`ui/api/__init__.py` `get_config()` now:
- Returns favorites from **all** platforms (Twitch + Kick + YouTube)
- Sets `has_credentials = True` if **any** platform has credentials

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

---

## 2026-04-30 — Playback stability: HLS health monitor, FPS recovery, sidebar diffing, chat batching

### Problem
During long Twitch viewing sessions (>30–60 min), stream playback gradually degraded: FPS dropped, video stuttered. Pausing and resuming temporarily restored smoothness, indicating HLS back-buffer accumulation in WKWebView’s `AVPlayer`.

### Solution

#### `ui/js/player.js` — Video Health Monitor + FPS Monitor
- **`checkVideoHealth()`** runs every 60 s while player is active:
  - **Live-edge drift**: if `currentTime` lags `seekable.end` by >120 s → `seek` to live edge.
  - **Buffer accumulation**: if `buffered.end` exceeds `currentTime` by >300 s → `softResetVideo()`.
- **`softResetVideo()`** — preserves `src`, `muted`, `volume`; does `pause → load → src → play` to reset `MediaPlayer` without page reload.
- **FPS monitor** — `requestAnimationFrame` loop measures frame time. Sustained >50 ms frames for 5 s triggers auto `softResetVideo()`.
- Both monitors start in `showPlayerView()` and cleanly stop in `hidePlayerView()`.

#### `ui/js/sidebar.js` — Diff-based rendering
- Replaced full `while (list.firstChild) removeChild(...)` rebuild on every poll with **in-place updates**.
- `renderSidebar()` compares current vs new `login` sets for Online/Offline sections:
  - If membership unchanged → updates text/classes/src via `updateSidebarItem()` only.
  - If membership changed → rebuilds only the affected section.
- `applySidebarLayout()` deferred via `requestAnimationFrame` to avoid forced reflow during video compositing.
- `updateSidebarItem()` also updates `aria-label` and caches last viewer count in `dataset._lastViewers` for accessibility.

#### `ui/js/callbacks.js` — Chat batching + throttled fetching
- **Chat limit**: reduced from 500 → **150** messages.
- **Batch insertion**: incoming messages collect for 50 ms, then flushed as one `DocumentFragment` to reduce layout thrashing.
- **Background image throttle**: when `player-view` is active, avatar/thumbnail fetches are skipped or deferred via `requestIdleCallback` (timeout 2 s) to free main thread for video.

#### CSS containment (`ui/css/views.css`, `ui/css/player.css`)
Added `contain: layout style paint` to:
- `#player-view`
- `#player-content`
- `#chat-panel`
This isolates layout/paint recalculations of chat and sidebar from video compositing.

### Post-implementation debug audit & bug fixes

Three bugs were found during a debug audit and fixed:

1. **Chat batch leak (critical)** — Pending batched messages could flush into the wrong chat after a channel/context switch.
   - Added `clearChatBatch()` inside the chat-batching IIFE and exported it as `TwitchX.clearChatBatch`.
   - Called from: `clearChatMessages()`, `hidePlayerView()`, `switchMultiChat()`, and `onChatStatus(connected=true)`.

2. **Missing `TwitchX.api` null-check** — `get_avatar()` was called without guard in the non-player-active path.
   - Added `if (TwitchX.api)` check before `TwitchX.api.get_avatar()` in `onStreamsUpdate`.

3. **Stale `aria-label` in sidebar** — `updateSidebarItem()` did not refresh the accessibility label when live status or viewer count changed.
   - `updateSidebarItem()` now updates `aria-label` on `isLive` transition and viewer-count delta, tracking last viewers via `dataset._lastViewers`.

---

## 2026-04-29 — Gentle Video Reset + Frozen Detection + Multistream Health

### Problem
The previous `softResetVideo()` (pause → load → src → play) did not reliably destroy WKWebView's internal `MediaPlayer`, so HLS back-buffers kept accumulating and FPS degraded after 30–60 min of Twitch playback. Manual pause/resume fixed it temporarily, proving the issue was buffer state, not network.

### Solution

#### `ui/js/player.js` — Gentle Video Reset (crossfade swap)
Replaced `softResetVideo()` with **`gentleResetVideo(reason)`**:
1. Creates a **shadow `<video>`** with `position:absolute` and `opacity:0`, sharing the same parent as the old element.
2. New DOM node forces WKWebView to spawn a **fresh `MediaPlayer`**.
3. Shadow video pre-loads the same HLS `src` muted.
4. On `playing` or `loadeddata` (or 2.5 s fallback), performs a **150 ms CSS crossfade** (`opacity` transition).
5. Old video is `pause() → removeAttribute('src') → load() → remove()` to guarantee buffer release.
6. Shadow video is promoted to the active element (`TwitchX._playerVideo = newVideo`).

This produces no perceptible black screen — only a sub-second opacity blend.

#### `ui/js/player.js` — Video element abstraction
- Added `TwitchX._playerVideo` and `TwitchX.getPlayerVideo()` so all player code references the current live element, not a stale `document.getElementById` cache.
- `hidePlayerView()` now **destroys** the old `<video>` and inserts a fresh empty one, preventing a dead MediaPlayer from leaking across sessions.

#### `ui/js/player.js` — Frozen Video Monitor (new)
- `checkFrozenVideo()` runs every **10 s** while player is active.
- If `currentTime` has not changed for 10 s while `!paused && readyState >= 2`, the decoder is stuck → triggers `gentleResetVideo('frozen')`.

#### `ui/js/player.js` — Improved Health Monitor triggers
- Buffer threshold reduced from **300 s → 180 s** (problem starts earlier).
- Live-edge drift unchanged (>120 s → seek).
- Proactive reset: silent `gentleResetVideo('proactive')` every **30 min** to prevent accumulation before symptoms appear.

#### `ui/js/player.js` — Improved FPS Monitor
- Skips measurement when `document.hidden` (macOS throttles rAF on background) or `video.paused` or `readyState < 2`.
- Threshold raised from **50 ms → 66 ms** (< 15 FPS) to reduce false positives.
- Requires **consecutive** bad frames for ~5 s, not cumulative count.

#### `ui/js/multistream.js` — Multistream Health Monitor
- `startMultiHealthMonitor()` / `stopMultiHealthMonitor()` run every **60 s** while multistream is open.
- Per-slot checks:
  - **Frozen**: `currentTime` stale for 120 s (2 checks) → `_reloadMultiSlot(idx, 'frozen')`.
  - **Buffer**: `buffered.end - currentTime > 180 s` → `_reloadMultiSlot(idx, 'buffer-overflow')`.
  - **Live-edge drift**: `seekable.end - currentTime > 120 s` → seek to edge.
- `_reloadMultiSlot()` recreates the `<video>` element inside the slot (new MediaPlayer) and restores `src`.
- `_clearMultiSlot()` now fully destroys the old video and inserts a fresh element.

### Post-implementation bug-fix audit

1. **`gentleResetVideo()` shadow video position** — `appendChild` inserted the shadow video after `#chat-panel`, breaking the flex row order (`video → handle → chat`).
   - Fixed: `container.insertBefore(newVideo, oldVideo)` preserves DOM order.
2. **Re-entrant `gentleResetVideo()`** — `getPlayerVideo()` returned the old element during the 160 ms crossfade, so concurrent health checks could trigger a second reset.
   - Fixed: `TwitchX._playerVideo = null` is set immediately at the start of `gentleResetVideo()`.
3. **Proactive reset fired only once** — `setTimeout` is single-shot; after the first 30-min reset the timer expired.
   - Fixed: `startProactiveReset()` now uses a self-rescheduling `setTimeout` callback (acts like `setInterval` but survives resets cleanly).
4. **`hidePlayerView()` null-reference risk** — `getPlayerVideo()` could theoretically return `null` if DOM was empty.
   - Fixed: added `if (video) { ... }` guard before `pause()` / `remove()`.
5. **Multistream frozen detection float jitter** — `String(nowTime) === lastTime` failed on tiny floating-point differences (e.g. `120.5000001` vs `"120.5"`).
   - Fixed: `Math.abs(nowTime - parseFloat(lastTime)) < 0.5`.
6. **`addMultiSlot()` missing `.ms-video` guard** — `active.querySelector('.ms-video').muted = true` threw TypeError when the element was absent.
   - Fixed: stored result in `msVideo` variable with `if (msVideo)` guard.
7. **PiP button stale reference** — `document.getElementById('stream-video')` in `init.js` could reference a removed element after `gentleResetVideo()`.
   - Fixed: uses `TwitchX.getPlayerVideo()` instead.

#### `ui/js/init.js` & `ui/js/keyboard.js` — Event delegation
- Replaced direct `video.addEventListener('dblclick', ...)` with **delegation** on `#player-content` using `e.target.closest('#stream-video')`. This survives video recreation.
- `keyboard.js` PiP shortcut now uses `TwitchX.getPlayerVideo()` instead of `document.getElementById('stream-video')`.

#### Diagnostic logging
All reset paths log to `console.log('[VideoHealth]', reason, ...)` with timestamp, src (query-stripped), and currentTime for future debugging.
