# `ui/api.py` Decomposition — Design Spec
**Date:** 2026-04-08
**Scope:** `ui/api.py` (2197 lines → ~900 lines), 5 new `ui/` modules

---

## Problem

`ui/api.py` is a 2197-line monolith. `TwitchXApi` handles OAuth for three platforms, channel management, chat, player, and stream polling — all in one class with 50+ methods sharing mutable state. Methods are hard to test because they require a full pywebview window, and hard to find because nothing is grouped.

---

## Goal

Split `TwitchXApi` into focused handler objects. The pywebview JS interface (`window.pywebview.api.<method>()`) does **not change** — `TwitchXApi` stays the single `js_api` object exposed to the webview. `index.html` is untouched.

---

## Architecture

### Shared config: `ConfigStore`

All handlers share one `ConfigStore` reference. Eliminates the staleness problem where `self._config` in one part of the code diverges from a write in another.

```python
class ConfigStore:
    @property
    def config(self) -> dict: ...       # read snapshot
    def update(self, fn) -> None: ...   # write + persist
    def reload(self) -> None: ...       # re-read from disk
```

**Transformation rules for moved code:**
- `self._config` (read) → `self._store.config`
- `self._config = update_config(fn)` → `self._store.update(fn)`
- `self._config = load_config()` → `self._store.reload()`

---

### New file structure

```
ui/
├── config_store.py   # ConfigStore (~40 lines)
├── auth.py           # AuthHandler — OAuth for Twitch/Kick/YouTube (~400 lines)
├── channels.py       # ChannelHandler — add/remove/reorder/search (~350 lines)
├── chat.py           # ChatHandler — start/stop/send chat (~270 lines)
├── player.py         # PlayerHandler — watch/stop/external/browser (~290 lines)
└── api.py            # TwitchXApi thin facade + fetch/poll (~900 lines)
```

---

### Handler constructors

**`AuthHandler(ui/auth.py)`**
```python
AuthHandler(
    store: ConfigStore,
    twitch: TwitchClient,
    kick: KickClient,
    youtube: YouTubeClient,
    eval_js: Callable[[str], None],
    shutdown: threading.Event,
    run_in_thread: Callable,
    close_thread_loop: Callable,
    refresh: Callable[[], None],         # trigger refresh after auth
    restart_polling: Callable[[], None], # re-arm polling after failed OAuth
    stop_polling: Callable[[], None],    # pause polling before OAuth
    get_avatar: Callable[[str], None],   # load avatar after Twitch login
)
```
Owns: `current_user: dict | None` (initialised from config at construction).
Exposes: `twitch_login/logout/test/import_follows`, `kick_login/logout/test`, `youtube_login/logout/test/import_follows`.
Module-level: `parse_scopes(raw: str) -> set[str]`.

**`ChannelHandler(ui/channels.py)`**
```python
ChannelHandler(
    store: ConfigStore,
    twitch: TwitchClient,
    kick: KickClient,
    youtube: YouTubeClient,
    eval_js: Callable[[str], None],
    shutdown: threading.Event,
    run_in_thread: Callable,
    close_thread_loop: Callable,
    on_channel_changed: Callable[[], None],  # trigger refresh after add
)
```
Module-level helpers: `sanitize_username()`, `sanitize_channel_name()`, `normalize_twitch/kick/youtube_search_result()`.
Exposes: `add()`, `remove()`, `reorder()`, `search()`.

**`ChatHandler(ui/chat.py)`**
```python
ChatHandler(
    store: ConfigStore,
    kick_platform: KickClient,
    eval_js: Callable[[str], None],
    shutdown: threading.Event,
)
```
Owns: `_client`, `_thread`.
Exposes: `start()`, `stop()`, `send()`, `save_width()`, `save_visibility()`.
Imports `parse_scopes` from `ui/auth.py`.

**`PlayerHandler(ui/player.py)`**
```python
PlayerHandler(
    store: ConfigStore,
    eval_js: Callable[[str], None],
    shutdown: threading.Event,
    run_in_thread: Callable,
    get_live_streams: Callable[[], list[dict]],  # lambda: api._live_streams
    start_chat: Callable[[str, str], None],
    stop_chat: Callable[[], None],
)
```
Owns: `_watching_channel`, `_launch_timer`, `_launch_elapsed`, `_launch_channel`.
Exposes: `watch()`, `stop()`, `watch_external()`, `open_browser()`.

---

### `TwitchXApi` after refactor

**State that stays:**
- `_window`, `_shutdown`, `_fetch_lock`, `_poll_lock`, `_polling_timer`
- `_live_streams`, `_games`, `_prev_live_logins`, `_first_fetch_done`
- `_last_*` caches, `_user_avatars`, `_active_platform`
- `_store: ConfigStore`, `_auth`, `_chat`, `_channels`, `_player`

**Methods that stay:**
- Infrastructure: `_eval_js`, `_run_in_thread`, `_close_thread_loop`, `set_window`, `close`
- Config/settings: `get_config`, `get_full_config_for_settings`, `save_settings`
- Fetch/poll: `refresh`, `_fetch_data`, `_async_fetch`, `_on_data_fetched`, `start_polling`, `stop_polling`, `_restart_polling`, `_send_notification`, helpers
- Images: `get_avatar`, `get_thumbnail`
- Static re-exports for test compat: `_sanitize_username`, `_sanitize_channel_name`, `_migrate_favorites`
- Thin delegation wrappers for all handler methods

**`get_config()` change:** reads `self._auth.current_user` instead of `self._current_user`.

---

## Compatibility constraints

- `TwitchXApi._sanitize_username` and `_sanitize_channel_name` are called in `tests/test_app.py` as static methods. Keep as `staticmethod` re-exports pointing to the module-level functions in `ui/channels.py`.
- `TwitchXApi._migrate_favorites` is tested in `test_app.py` as an instance method — keep it in `api.py`.
- No changes to `ui/index.html`, `app.py`, or any `core/` module.

---

## Testing

Each handler is now independently testable:
```python
def test_chat_handler_stop_is_noop_when_not_started():
    handler = ChatHandler(
        store=Mock(), kick_platform=Mock(),
        eval_js=Mock(), shutdown=threading.Event()
    )
    handler.stop()  # must not raise
```

Existing `tests/test_api.py` continues to pass — delegation wrappers preserve the public interface.
