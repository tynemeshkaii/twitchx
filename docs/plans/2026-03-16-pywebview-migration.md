# pywebview Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the CustomTkinter UI layer with a pywebview-based web UI while keeping all core/ business logic untouched.

**Architecture:** pywebview opens a native WebKit window. Python exposes a `TwitchXApi` bridge class to JS via `window.pywebview.api.*`. JS calls Python methods; Python pushes updates back via `window.evaluate_js()`. Single HTML file with all CSS/JS inline.

**Tech Stack:** pywebview 5.x, Pillow (image resize + base64), existing core/ modules unchanged.

---

### Task 1: Update pyproject.toml dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Edit pyproject.toml**

Replace `"customtkinter>=5.2.0"` with `"pywebview>=5.0"` in dependencies. Keep `"pillow>=10.0.0"`. Remove `"ui"` from hatch packages (it will contain HTML now, not Python packages).

```toml
dependencies = [
    "httpx>=0.27.0",
    "pillow>=10.0.0",
    "pywebview>=5.0",
]

# hatch packages:
packages = ["core"]
```

**Step 2: Run uv sync**

Run: `uv sync`
Expected: pywebview installed, customtkinter removed.

**Step 3: Commit**

```
feat: swap customtkinter for pywebview in dependencies
```

---

### Task 2: Create ui/api.py — the Python↔JS bridge

**Files:**
- Create: `ui/api.py`
- Read (reference only): `app.py` (lines 314-1190), `core/twitch.py`, `core/storage.py`, `core/launcher.py`, `core/oauth_server.py`

This is the largest task. The `TwitchXApi` class wraps all core/ modules and exposes methods to JS.

**Step 1: Write ui/api.py**

The class must implement:

- `__init__`: Create `TwitchClient`, load config, init state (shutdown event, polling timer, live streams, games dict, prev_live_logins, first_fetch_done, watching_channel, selected_channel, fetching lock, current_user)
- `set_window(window)`: Store window reference for `evaluate_js`
- `_eval_js(code)`: Safe wrapper that catches exceptions when window is closing
- `_run_in_thread(fn)`: Helper to run a function in a daemon thread

**Config methods:**
- `get_config()`: Returns config dict (mask client_secret to first 4 chars + ****)
- `save_settings(data)`: Saves client_id, client_secret, streamlink_path, iina_path, refresh_interval. Clears token if credentials changed. Calls JS `onSettingsSaved()`.
- `test_connection(client_id, secret)`: POST to Twitch token endpoint in thread, calls JS `onTestResult({success, message})`

**Auth methods:**
- `login()`: Check credentials exist, get auth URL from TwitchClient, open browser, start oauth server in thread, exchange code, fetch user profile, call JS `onLoginComplete({display_name, login, avatar_url})` or `onLoginError(msg)`. Always `reset_client()` after.
- `logout()`: Clear user tokens in config, save, call JS `onLogout()`
- `import_follows()`: Get user_id, fetch followed channels in thread, merge into favorites, call JS `onImportComplete({added})` or `onImportError(msg)`. Always `reset_client()` after.

**Channel methods:**
- `add_channel(username)`: Sanitize, add to favorites, save config, trigger refresh
- `remove_channel(channel)`: Remove from favorites, save config, trigger refresh
- `reorder_channels(new_order)`: Update favorites order, save config, trigger refresh
- `search_channels(query)`: Search via TwitchClient in thread, call JS `onSearchResults([...])`

**Data fetch methods:**
- `refresh()`: Same retry logic as old app.py `_fetch_data`. Fetches streams+users+games, sends notification for newly-live channels, calls JS `onStreamsUpdate({streams, favorites, live_set, updated_time, total_viewers})`. Each stream item: `{login, display_name, title, game, viewers, started_at, thumbnail_url, viewer_trend}`.
- `start_polling(interval_seconds)`: Start a `threading.Timer` loop
- `stop_polling()`: Cancel timer

**Stream launch methods:**
- `watch(channel, quality)`: Check channel selected + live, call `launch_stream` in thread with progress timer, call JS `onLaunchProgress({channel, elapsed})` during wait, then `onLaunchResult({success, message, channel})`
- `open_browser(channel)`: `webbrowser.open()`

**Image methods:**
- `get_avatar(login)`: Check disk cache → fetch from URL → resize 56x56 LANCZOS → base64 PNG → call JS `onAvatar({login, data})`
- `get_thumbnail(login, url)`: Fetch → resize 440x248 LANCZOS → base64 JPEG quality=85 → call JS `onThumbnail({login, data})`

**Cleanup:**
- `close()`: Set shutdown, close TwitchClient

**Critical patterns to preserve:**
- `_sanitize_username` must be a `@staticmethod` (tests import it)
- `asyncio.new_event_loop()` + `loop.run_until_complete()` in each thread
- `reset_client()` after every OAuth flow
- Notification via `osascript` in background thread
- Retry with backoff on ConnectError (delays [5, 15, 30])
- `_fetching` guard to prevent concurrent fetches
- Closure safety: capture variables via default args in lambdas

**Step 2: Verify imports work**

Run: `uv run python -c "from ui.api import TwitchXApi; print('OK')"`
Expected: OK

**Step 3: Commit**

```
feat: add pywebview Python↔JS bridge (ui/api.py)
```

---

### Task 3: Create ui/index.html — the web UI

**Files:**
- Create: `ui/index.html`

Single self-contained HTML file with inline CSS and JS. No external dependencies.

**Step 1: Write ui/index.html**

Structure (all inline):
1. `<style>` block with full CSS (colors as CSS custom properties, glassmorphism, animations, scrollbar, responsive grid)
2. `<body>` with layout: sidebar | content (toolbar + grid) | player bar | settings modal
3. `<script>` block with all JS

**CSS must include:**
- `:root` variables matching the spec palette
- Glassmorphism on cards and sidebar (`backdrop-filter: blur(20px)`)
- `@keyframes pulse` for live dot
- `@keyframes shimmer` for thumbnail placeholders
- WebKit scrollbar styling
- All transition/hover effects from spec
- Drag-to-reorder visual indicator

**JS state object:**
```javascript
const state = {
  streams: [], favorites: [], liveSet: new Set(),
  selectedChannel: null, watchingChannel: null,
  prevViewers: {}, config: {},
  sortKey: 'viewers', filterText: '',
  avatars: {}, thumbnails: {},
  searchDebounce: null,
};
```

**JS must implement:**
- Global callbacks: `onStreamsUpdate`, `onSearchResults`, `onLoginComplete`, `onLogout`, `onImportComplete`, `onLaunchResult`, `onLaunchProgress`, `onTestResult`, `onAvatar`, `onThumbnail`, `onStatusUpdate`, `onSettingsSaved`
- `renderGrid()`: Diff-based — compare logins, update in-place if set unchanged, rebuild if changed. Request thumbnails for new cards.
- `renderSidebar()`: Diff-based — update live dots, names, avatars in-place
- `renderPlayerBar()`: Update status, viewers, time, watching state
- Keyboard shortcuts: r/F5/Cmd+R refresh, Space/Enter watch, Cmd+comma settings, Escape deselect/close
- Custom right-click context menu (Watch / Open in Browser / Copy URL / Add to Favorites)
- Settings modal with all fields, test connection, save, eye toggle for secret
- Search with 400ms debounce
- Drag-to-reorder sidebar channels
- Uptime counter (setInterval every 60s)
- Sort (viewers/recent/alpha) and game filter

**Step 2: Validate HTML is well-formed**

Run: `python3 -c "open('ui/index.html').read(); print('File readable, size:', len(open('ui/index.html').read()))"`

**Step 3: Commit**

```
feat: add pywebview web UI (ui/index.html)
```

---

### Task 4: Rewrite app.py — pywebview launcher

**Files:**
- Rewrite: `app.py`

The new `app.py` must:
1. Keep `TwitchXApp` class name (tests import it)
2. Keep `_sanitize_username` as `@staticmethod` (tests use it)
3. Keep `_migrate_favorites` method (tests reference the pattern)
4. Use pywebview instead of CTk

```python
class TwitchXApp:
    """pywebview-based TwitchX application."""

    def __init__(self):
        self._api = TwitchXApi()

    @staticmethod
    def _sanitize_username(raw: str) -> str:
        # exact same implementation as before
        ...

    def _migrate_favorites(self):
        # exact same implementation as before
        ...

    def mainloop(self):
        html = read ui/index.html
        window = webview.create_window(
            'TwitchX', html=html,
            js_api=self._api,
            width=960, height=640,
            min_size=(700, 500),
            background_color='#0E0E1A'
        )
        self._api.set_window(window)
        window.events.loaded += self._on_loaded
        webview.start(debug=os.environ.get('TWITCHX_DEBUG'))

    def _on_loaded(self):
        # send initial config to JS
        # start polling
        ...
```

**Step 1: Write the new app.py**

**Step 2: Run existing tests**

Run: `uv run pytest tests/test_app.py -v`
Expected: All tests pass (they test `_sanitize_username` and `_migrate_favorites`)

**Step 3: Commit**

```
feat: rewrite app.py as pywebview launcher
```

---

### Task 5: Update main.py

**Files:**
- Modify: `main.py`

Minimal change — the import stays the same (`from app import TwitchXApp`), but the call changes since `TwitchXApp` is no longer a CTk widget.

```python
import logging
import os

from app import TwitchXApp

if os.environ.get("TWITCHX_DEBUG"):
    logging.basicConfig(level=logging.DEBUG, format="%(name)s %(message)s")

def main() -> None:
    app = TwitchXApp()
    app.mainloop()

if __name__ == "__main__":
    main()
```

**Step 1: Update main.py** (likely no changes needed if TwitchXApp.mainloop() exists)

**Step 2: Commit if changed**

---

### Task 6: Delete old UI files

**Files:**
- Delete: `ui/theme.py`
- Delete: `ui/sidebar.py`
- Delete: `ui/stream_grid.py`
- Delete: `ui/player_bar.py`
- Keep: `ui/__init__.py` (may need it empty for package)
- Keep: `ui/api.py`
- Keep: `ui/index.html`

**Step 1: Remove old files**

```bash
rm ui/theme.py ui/sidebar.py ui/stream_grid.py ui/player_bar.py
```

**Step 2: Update ui/__init__.py**

Empty file or minimal exports.

**Step 3: Commit**

```
chore: remove old CustomTkinter UI files
```

---

### Task 7: Fix core/utils.py import (if needed)

**Files:**
- Check: `core/utils.py` (imports from `ui/theme.py`)

`core/utils.py` imports theme tokens from `ui/theme.py`. Since we're deleting `theme.py`, we need to either:
- Inline the constants in `core/utils.py` (violates "don't touch core/" — BUT the spec says "do not modify any file in core/ unless explicitly instructed")
- Keep `ui/theme.py` with just the constants that `core/utils.py` needs

Best approach: Keep a minimal `ui/theme.py` with ONLY the constants that `core/utils.py` imports (`ACCENT`, `BG_ELEVATED`, `FONT_SYSTEM`, `TEXT_PRIMARY`). This avoids touching core/.

**Step 1: Check what core/utils.py imports**

It imports: `ACCENT, BG_ELEVATED, FONT_SYSTEM, TEXT_PRIMARY`

**Step 2: Create minimal ui/theme.py** with just those 4 constants

**Step 3: Run tests**

Run: `uv run pytest tests/ -v`
Expected: All 41 tests pass

**Step 4: Commit**

```
fix: keep minimal ui/theme.py for core/utils.py compatibility
```

---

### Task 8: Lint and full test suite

**Files:**
- All modified files

**Step 1: Run linter**

Run: `uv run ruff check .`
Fix any issues.

Run: `uv run ruff format .`

**Step 2: Run type checker**

Run: `uv run pyright`
Fix critical errors (pywebview types may need ignores).

**Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All 41 tests pass.

**Step 4: Commit fixes**

```
fix: lint and type fixes for pywebview migration
```

---

### Task 9: Smoke test the app

**Step 1: Launch**

Run: `uv run python main.py`
Expected: Native window opens with dark UI, sidebar, empty grid.

**Step 2: Verify settings modal**

Click gear icon → modal should open with fields.

**Step 3: Verify basic interactions**

- Type in search box → debounce works
- Keyboard shortcuts respond
- Window resizes properly

**Step 4: Fix any runtime issues found**

---

### Task 10: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

Update architecture section to reflect pywebview instead of CustomTkinter. Update UI modules section. Update gotchas. Remove references to CTk widgets.

**Step 1: Update CLAUDE.md**

**Step 2: Commit**

```
docs: update CLAUDE.md for pywebview architecture
```
