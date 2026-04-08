# `ui/api.py` Decomposition — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the 2197-line `TwitchXApi` monolith into four focused handler objects (`AuthHandler`, `ChatHandler`, `ChannelHandler`, `PlayerHandler`) using composition and a shared `ConfigStore`. The pywebview JS interface is unchanged.

**Architecture:** Each handler is a plain Python class that receives `ConfigStore` and callables as constructor arguments. `TwitchXApi` is a thin facade that owns fetch/poll state and delegates to handler instances. All new handlers live in `ui/`.

**Tech Stack:** Python, `threading`, `asyncio`, `pytest`

---

## Files

- **Create:** `ui/config_store.py`
- **Create:** `ui/chat.py`
- **Create:** `ui/channels.py`
- **Create:** `ui/auth.py`
- **Create:** `ui/player.py`
- **Modify:** `ui/api.py` — replace self._config with store, wire handlers, add delegation wrappers
- **Test:** `tests/test_api.py` — verify existing tests still pass after each task
- **Test:** `tests/test_app.py` — verify static method re-exports still work

---

### Transformation rules (apply throughout all handler moves)

Whenever a method body is moved from `TwitchXApi` to a handler, apply these substitutions:

| Old (in TwitchXApi) | New (in handler) |
|---|---|
| `self._config` (read) | `self._store.config` |
| `self._config = update_config(fn)` | `self._store.update(fn)` |
| `self._config = load_config()` | `self._store.reload()` |
| `self._eval_js(...)` | `self._eval_js(...)` (already injected) |
| `self._run_in_thread(fn)` | `self._run_in_thread(fn)` (already injected) |
| `self._close_thread_loop(loop)` | `self._close_thread_loop(loop)` (already injected) |
| `self._shutdown.is_set()` | `self._shutdown.is_set()` (already injected) |
| `self._twitch` / `self._kick` / `self._youtube` | `self._twitch` / `self._kick` / `self._youtube` (already stored) |
| `get_platform_config(self._config, "twitch")` | `get_platform_config(self._store.config, "twitch")` |
| `get_settings(self._config)` | `get_settings(self._store.config)` |
| `get_favorites(self._config)` | `get_favorites(self._store.config)` |
| `get_favorite_logins(self._config, x)` | `get_favorite_logins(self._store.config, x)` |

---

### Task 1: Create `ui/config_store.py`

**Files:**
- Create: `ui/config_store.py`

- [ ] **Step 1: Create `ui/config_store.py` with complete content**

```python
from __future__ import annotations

from typing import Any, Callable

from core.storage import load_config
from core.storage import update_config as _update_config


class ConfigStore:
    """Shared mutable config container for all UI handlers.

    All handlers hold a reference to one ConfigStore. Any handler that
    calls update() immediately makes the new snapshot visible to every
    other handler via the config property — no staleness.
    """

    def __init__(self) -> None:
        self._config: dict[str, Any] = load_config()

    @property
    def config(self) -> dict[str, Any]:
        """Current in-memory config snapshot."""
        return self._config

    def update(self, fn: Callable[[dict[str, Any]], None]) -> None:
        """Apply fn to config, persist to disk, update in-memory snapshot."""
        self._config = _update_config(fn)

    def reload(self) -> None:
        """Re-read config from disk (call before a fetch cycle)."""
        self._config = load_config()
```

- [ ] **Step 2: Run existing tests — verify baseline**

```bash
source .venv/bin/activate && pytest tests/ -v --tb=short -q
```

Expected: same result as before (245 pass, 4 stream_resolver failures unrelated).

---

### Task 2: Migrate `ui/api.py` to use `ConfigStore`

**Files:**
- Modify: `ui/api.py`

This task touches only `api.py` — no handler extractions yet. After this task, `api.py` uses `self._store` everywhere instead of `self._config`.

- [ ] **Step 1: Add import and replace `__init__` config setup**

Add at the top of imports in `ui/api.py`:
```python
from ui.config_store import ConfigStore
```

In `__init__`, replace:
```python
self._config = load_config()
```
with:
```python
self._store = ConfigStore()
```

Remove the line that restores `_current_user` from config (it will move to `AuthHandler` in Task 5). Keep `self._current_user` initialisation for now — just remove the `twitch_conf = get_platform_config(...)` + `if twitch_conf.get("user_id")...` block at the end of `__init__`. It will be restored inside `AuthHandler.__init__`.

- [ ] **Step 2: Apply transformation rules throughout `api.py`**

Do a global find-and-replace pass. For each occurrence in `api.py`:

Replace every `self._config = load_config()` with `self._store.reload()` — except in `__init__` which is already handled.

Replace every `self._config = update_config(fn)` with `self._store.update(fn)`.

Replace every remaining read of `self._config` (used as argument to storage functions) with `self._store.config`.

**Verify the substitutions** by running:
```bash
grep -n "self\._config\b" ui/api.py
```

Expected output after substitution: only lines inside methods of handlers-not-yet-extracted (auth, channels, chat, player methods still in api.py). Every line should be either `self._store.update(fn)`, `self._store.reload()`, or `get_*(self._store.config, ...)`.

- [ ] **Step 3: Update `_restart_polling` to use store**

```python
def _restart_polling(self) -> None:
    """Restart polling with the configured interval."""
    interval = get_settings(self._store.config).get("refresh_interval", 60)
    self.start_polling(interval)
```

- [ ] **Step 4: Run tests — verify nothing broke**

```bash
source .venv/bin/activate && pytest tests/ -v --tb=short -q
```

Expected: same pass/fail count as Task 1 Step 2.

---

### Task 3: Extract `ChatHandler` to `ui/chat.py`

**Files:**
- Create: `ui/chat.py`
- Modify: `ui/api.py`

- [ ] **Step 1: Create `ui/chat.py` with the complete `ChatHandler` class**

```python
from __future__ import annotations

import asyncio
import contextlib
import json
import threading
from typing import TYPE_CHECKING, Any, Callable

from core.chat import ChatMessage, ChatSendResult, ChatStatus
from core.chats.kick_chat import KickChatClient
from core.chats.twitch_chat import TwitchChatClient
from core.storage import get_platform_config, update_config

if TYPE_CHECKING:
    from core.platforms.kick import KickClient
    from ui.config_store import ConfigStore


def parse_scopes(raw: str) -> set[str]:
    return {part.strip() for part in raw.split() if part.strip()}


class ChatHandler:
    """Manages live chat connections for Twitch and Kick channels."""

    def __init__(
        self,
        store: ConfigStore,
        kick_platform: KickClient,
        eval_js: Callable[[str], None],
        shutdown: threading.Event,
    ) -> None:
        self._store = store
        self._kick_platform = kick_platform
        self._eval_js = eval_js
        self._shutdown = shutdown
        self._client: TwitchChatClient | KickChatClient | None = None
        self._thread: threading.Thread | None = None

    def start(self, channel: str, platform: str = "twitch") -> None:
        """Start chat for a channel."""
        self.stop()

        if platform == "twitch":
            twitch_conf = get_platform_config(self._store.config, "twitch")
            token = twitch_conf.get("access_token") or None
            login = twitch_conf.get("user_login") or None

            self._client = TwitchChatClient()
            self._client.on_message(self._on_message)
            self._client.on_status(self._on_status)

            def run_chat() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        self._client.connect(channel, token=token, login=login)  # type: ignore[union-attr]
                    )
                except Exception:
                    pass
                finally:
                    loop.close()

            self._thread = threading.Thread(target=run_chat, daemon=True)
            self._thread.start()

        elif platform == "kick":
            kick_conf = get_platform_config(self._store.config, "kick")
            token = kick_conf.get("access_token") or None
            scopes = parse_scopes(kick_conf.get("oauth_scopes", ""))

            self._client = KickChatClient()
            self._client.on_message(self._on_message)
            self._client.on_status(self._on_status)
            kick_chat_client = self._client

            def run_kick_chat() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    if not isinstance(kick_chat_client, KickChatClient):
                        return
                    info = loop.run_until_complete(
                        self._kick_platform.get_channel_info(channel)
                    )
                    chatroom_id = None
                    broadcaster_user_id = None
                    if isinstance(info, dict):
                        chatroom = info.get("chatroom", {})
                        chatroom_id = (
                            chatroom.get("id")
                            if isinstance(chatroom, dict)
                            else info.get("chatroom_id")
                        )
                        broadcaster_user_id = (
                            info.get("broadcaster_user_id")
                            or info.get("user_id")
                            or info.get("user", {}).get("id")
                        )
                    if chatroom_id is None:
                        self._on_status(
                            ChatStatus(
                                connected=False,
                                platform="kick",
                                channel_id=channel,
                                error="No chatroom found",
                            )
                        )
                        return
                    can_send = bool(
                        token and broadcaster_user_id and "chat:write" in scopes
                    )
                    loop.run_until_complete(
                        kick_chat_client.connect(
                            channel,
                            token=token,
                            chatroom_id=chatroom_id,
                            broadcaster_user_id=int(broadcaster_user_id)
                            if broadcaster_user_id
                            else None,
                            can_send=can_send,
                        )
                    )
                except Exception as exc:
                    self._on_status(
                        ChatStatus(
                            connected=False,
                            platform="kick",
                            channel_id=channel,
                            error=str(exc)[:120] or "Kick chat failed",
                        )
                    )
                finally:
                    loop.close()

            self._thread = threading.Thread(target=run_kick_chat, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Disconnect current chat client."""
        if self._client:
            client = self._client
            client._running = False
            loop = client._loop
            if loop and not loop.is_closed():
                fut = asyncio.run_coroutine_threadsafe(client.disconnect(), loop)
                with contextlib.suppress(Exception):
                    fut.result(timeout=3)
        self._client = None
        self._thread = None

    def send(
        self,
        text: str,
        reply_to: str | None = None,
        reply_display: str | None = None,
        reply_body: str | None = None,
        request_id: str | None = None,
    ) -> None:
        """Send a chat message, optionally as a reply."""
        if not self._client or not text.strip():
            return

        client = self._client

        def _do_send() -> None:
            if isinstance(client, TwitchChatClient):
                result = client.send_message_sync(text, reply_to_id=reply_to)
            elif isinstance(client, KickChatClient):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    ok, err = loop.run_until_complete(
                        client.send(text, reply_to_id=reply_to)
                    )
                    result = ChatSendResult(success=ok, error=err)
                finally:
                    loop.close()
            else:
                return

            payload = json.dumps(
                {
                    "success": result.success,
                    "error": result.error or "",
                    "request_id": request_id or "",
                }
            )
            self._eval_js(f"window.onChatSendResult({payload})")

        threading.Thread(target=_do_send, daemon=True).start()

    def save_width(self, width: int) -> None:
        def _apply(cfg: dict) -> None:
            cfg.get("settings", {})["chat_width"] = width

        self._store.update(_apply)

    def save_visibility(self, visible: bool) -> None:
        def _apply(cfg: dict) -> None:
            cfg.get("settings", {})["chat_visible"] = visible

        self._store.update(_apply)

    # ── Internal callbacks ────────────────────────────────────────

    def _on_message(self, msg: ChatMessage) -> None:
        if self._shutdown.is_set():
            return
        payload = json.dumps(
            {
                "id": msg.id,
                "author": msg.author,
                "author_color": msg.author_color,
                "body": msg.body,
                "emotes": [
                    {"id": e.id, "name": e.name, "url": e.url, "positions": e.positions}
                    for e in msg.emotes
                ],
                "badges": msg.badges,
                "is_system": msg.is_system,
                "reply": msg.reply.__dict__ if msg.reply else None,
            }
        )
        self._eval_js(f"window.onChatMessage({payload})")

    def _on_status(self, status: ChatStatus) -> None:
        if self._shutdown.is_set():
            return
        payload = json.dumps(
            {
                "connected": status.connected,
                "platform": status.platform,
                "channel_id": status.channel_id,
                "error": status.error or "",
            }
        )
        self._eval_js(f"window.onChatStatus({payload})")
```

- [ ] **Step 2: Wire `ChatHandler` into `TwitchXApi.__init__`**

Inside `TwitchXApi.__init__`, after creating platform clients and `self._store`, add:

```python
from ui.chat import ChatHandler

self._chat = ChatHandler(
    store=self._store,
    kick_platform=self._kick,
    eval_js=self._eval_js,
    shutdown=self._shutdown,
)
```

- [ ] **Step 3: Replace chat methods in `TwitchXApi` with delegation wrappers**

Delete the bodies of `start_chat`, `stop_chat`, `send_chat`, `save_chat_width`, `save_chat_visibility`, `_on_chat_message`, `_on_chat_status` from `api.py`.

Replace them with:

```python
# ── Chat (delegated to ChatHandler) ──────────────────────────

def start_chat(self, channel: str, platform: str = "twitch") -> None:
    self._chat.start(channel, platform)

def stop_chat(self) -> None:
    self._chat.stop()

def send_chat(
    self,
    text: str,
    reply_to: str | None = None,
    reply_display: str | None = None,
    reply_body: str | None = None,
    request_id: str | None = None,
) -> None:
    self._chat.send(text, reply_to, reply_display, reply_body, request_id)

def save_chat_width(self, width: int) -> None:
    self._chat.save_width(width)

def save_chat_visibility(self, visible: bool) -> None:
    self._chat.save_visibility(visible)
```

Also remove `_on_chat_message` and `_on_chat_status` from `api.py` entirely (they are now internal to `ChatHandler`).

- [ ] **Step 4: Remove now-unused imports from `api.py`**

Remove from `api.py` imports (if no longer referenced elsewhere in the file):
```python
from core.chat import ChatMessage, ChatSendResult, ChatStatus
from core.chats.kick_chat import KickChatClient
from core.chats.twitch_chat import TwitchChatClient
```

Check with: `grep -n "ChatMessage\|ChatSendResult\|ChatStatus\|KickChatClient\|TwitchChatClient" ui/api.py`

Remove any that are zero-referenced.

- [ ] **Step 5: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -v --tb=short -q
```

Expected: same pass/fail count as Task 2.

---

### Task 4: Extract `ChannelHandler` to `ui/channels.py`

**Files:**
- Create: `ui/channels.py`
- Modify: `ui/api.py`

- [ ] **Step 1: Create `ui/channels.py` with the complete `ChannelHandler` class**

The module-level functions `sanitize_username` and `sanitize_channel_name` are the current static methods `_sanitize_username` / `_sanitize_channel_name` on `TwitchXApi` — move them verbatim as module-level functions (drop the leading underscore). The normalize/build statics move the same way.

```python
from __future__ import annotations

import asyncio
import json
import re
import threading
from typing import TYPE_CHECKING, Any, Callable

from core.storage import (
    get_favorite_logins,
    get_favorites,
    get_platform_config,
    update_config,
)

if TYPE_CHECKING:
    from core.platforms.kick import KickClient
    from core.platforms.twitch import TwitchClient
    from core.platforms.youtube import YouTubeClient
    from ui.config_store import ConfigStore


# ── Module-level helpers (previously static methods on TwitchXApi) ────────────

def sanitize_username(raw: str) -> str:
    raw = raw.strip()
    match = re.search(r"(?:twitch\.tv/)([A-Za-z0-9_]+)", raw)
    if match:
        return match.group(1).lower()
    return re.sub(r"[^A-Za-z0-9_]", "", raw).lower()


def sanitize_channel_name(raw: str, platform: str = "twitch") -> str:
    raw = raw.strip()
    if platform == "youtube":
        match = re.search(r"youtube\.com/channel/(UC[\w-]{22})", raw, re.IGNORECASE)
        if match:
            return match.group(1)
        match = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", raw)
        if match:
            return "v:" + match.group(1)
        match = re.search(
            r"(?:youtube\.com/)?(@[A-Za-z0-9][A-Za-z0-9_.-]{2,29})",
            raw,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).lower()
        clean = re.sub(r"[^A-Za-z0-9_-]", "", raw)
        if re.match(r"^UC[\w-]{22}$", clean, re.IGNORECASE):
            return clean
        if re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,29}$", clean):
            return "@" + clean.lower()
        return ""
    if platform == "kick":
        match = re.search(r"(?:kick\.com/)([A-Za-z0-9_-]+)", raw, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        return re.sub(r"[^A-Za-z0-9_-]", "", raw).lower()
    return sanitize_username(raw)


def normalize_twitch_search_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "login": result.get(
            "broadcaster_login", result.get("display_name", "")
        ).lower(),
        "display_name": result.get("display_name", ""),
        "is_live": result.get("is_live", False),
        "game_name": result.get("game_name", ""),
        "platform": "twitch",
    }


def normalize_kick_search_result(result: dict[str, Any]) -> dict[str, Any]:
    slug = result.get("slug", result.get("channel", {}).get("slug", "")).lower()
    return {
        "login": slug,
        "display_name": result.get(
            "username", result.get("user", {}).get("username", slug)
        ),
        "is_live": result.get("is_live", False),
        "game_name": result.get("category", {}).get("name", ""),
        "platform": "kick",
        "avatar_url": result.get("user", {}).get("profile_pic", ""),
    }


def normalize_youtube_search_result(result: dict[str, Any]) -> dict[str, Any]:
    # Body: move verbatim from TwitchXApi._normalize_youtube_search_result
    return result  # placeholder — use exact body from api.py


# ── ChannelHandler ────────────────────────────────────────────────────────────

class ChannelHandler:
    """Manages channel add/remove/reorder/search for all platforms."""

    def __init__(
        self,
        store: ConfigStore,
        twitch: TwitchClient,
        kick: KickClient,
        youtube: YouTubeClient,
        eval_js: Callable[[str], None],
        shutdown: threading.Event,
        run_in_thread: Callable,
        close_thread_loop: Callable,
        on_channel_changed: Callable[[], None],
    ) -> None:
        self._store = store
        self._twitch = twitch
        self._kick = kick
        self._youtube = youtube
        self._eval_js = eval_js
        self._shutdown = shutdown
        self._run_in_thread = run_in_thread
        self._close_thread_loop = close_thread_loop
        self._on_channel_changed = on_channel_changed

    def add(self, channel: str, platform: str = "twitch", display_name: str = "") -> None:
        # Move body of TwitchXApi.add_channel verbatim.
        # Apply transformation rules:
        #   self._config reads → self._store.config
        #   self._config = update_config(fn) → self._store.update(fn)
        #   self._sanitize_channel_name → sanitize_channel_name (module-level)
        #   self._normalize_*_search_result → normalize_*_search_result (module-level)
        #   self.refresh() → self._on_channel_changed()
        pass  # replace with actual body from TwitchXApi.add_channel

    def remove(self, channel: str, platform: str = "twitch") -> None:
        # Move body of TwitchXApi.remove_channel verbatim.
        # self.refresh() → self._on_channel_changed()
        pass

    def reorder(self, new_order_json: str, platform: str = "twitch") -> None:
        # Move body of TwitchXApi.reorder_channels verbatim.
        pass

    def search(self, query: str, platform: str = "twitch") -> None:
        # Move body of TwitchXApi.search_channels verbatim.
        # self._normalize_twitch_search_result → normalize_twitch_search_result
        # self._normalize_kick_search_result → normalize_kick_search_result
        # self._normalize_youtube_search_result → normalize_youtube_search_result
        pass
```

**IMPORTANT:** Replace each `pass` with the verbatim method body from the corresponding `TwitchXApi` method in `api.py`, applying the transformation rules from the header of this plan. The `normalize_youtube_search_result` placeholder must also be replaced with the actual body from `TwitchXApi._normalize_youtube_search_result`.

- [ ] **Step 2: Wire `ChannelHandler` into `TwitchXApi.__init__`**

```python
from ui.channels import ChannelHandler

self._channels = ChannelHandler(
    store=self._store,
    twitch=self._twitch,
    kick=self._kick,
    youtube=self._youtube,
    eval_js=self._eval_js,
    shutdown=self._shutdown,
    run_in_thread=self._run_in_thread,
    close_thread_loop=self._close_thread_loop,
    on_channel_changed=self.refresh,
)
```

- [ ] **Step 3: Replace channel methods in `TwitchXApi` with delegation wrappers + re-exports**

Delete bodies of `add_channel`, `remove_channel`, `reorder_channels`, `search_channels`, `_normalize_twitch_search_result`, `_normalize_kick_search_result`, `_normalize_youtube_search_result` from `api.py`.

Add at top of `api.py` (in imports):
```python
from ui.channels import sanitize_username as _sanitize_username_fn
from ui.channels import sanitize_channel_name as _sanitize_channel_name_fn
```

Inside `TwitchXApi` class body, replace with:
```python
# Static re-exports for test compatibility (tests/test_app.py calls these as static methods)
_sanitize_username = staticmethod(_sanitize_username_fn)
_sanitize_channel_name = staticmethod(_sanitize_channel_name_fn)

# ── Channels (delegated to ChannelHandler) ─────────────────────

def add_channel(
    self, channel: str, platform: str = "twitch", display_name: str = ""
) -> None:
    self._channels.add(channel, platform, display_name)

def remove_channel(self, channel: str, platform: str = "twitch") -> None:
    self._channels.remove(channel, platform)

def reorder_channels(
    self, new_order_json: str, platform: str = "twitch"
) -> None:
    self._channels.reorder(new_order_json, platform)

def search_channels(self, query: str, platform: str = "twitch") -> None:
    self._channels.search(query, platform)
```

Remove the old `_sanitize_username` and `_sanitize_channel_name` static method definitions (they are now staticmethod re-exports from ui/channels.py).

- [ ] **Step 4: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -v --tb=short -q
```

Expected: same pass/fail count. In particular `tests/test_app.py` must still pass (it calls `TwitchXApi._sanitize_username`).

---

### Task 5: Extract `AuthHandler` to `ui/auth.py`

**Files:**
- Create: `ui/auth.py`
- Modify: `ui/api.py`

- [ ] **Step 1: Create `ui/auth.py` with the complete `AuthHandler` class**

```python
from __future__ import annotations

import asyncio
import json
import threading
import time
import webbrowser
from typing import TYPE_CHECKING, Any, Callable

from core.oauth_server import wait_for_oauth_code
from core.storage import (
    get_favorite_logins,
    get_platform_config,
    update_config,
)

if TYPE_CHECKING:
    from core.platforms.kick import KickClient
    from core.platforms.twitch import TwitchClient
    from core.platforms.youtube import YouTubeClient
    from ui.config_store import ConfigStore


def parse_scopes(raw: str) -> set[str]:
    return {part.strip() for part in raw.split() if part.strip()}


class AuthHandler:
    """Handles OAuth login/logout/test for Twitch, Kick, and YouTube."""

    def __init__(
        self,
        store: ConfigStore,
        twitch: TwitchClient,
        kick: KickClient,
        youtube: YouTubeClient,
        eval_js: Callable[[str], None],
        shutdown: threading.Event,
        run_in_thread: Callable,
        close_thread_loop: Callable,
        refresh: Callable[[], None],
        restart_polling: Callable[[], None],
        stop_polling: Callable[[], None],
        get_avatar: Callable[[str], None],
    ) -> None:
        self._store = store
        self._twitch = twitch
        self._kick = kick
        self._youtube = youtube
        self._eval_js = eval_js
        self._shutdown = shutdown
        self._run_in_thread = run_in_thread
        self._close_thread_loop = close_thread_loop
        self._refresh = refresh
        self._restart_polling = restart_polling
        self._stop_polling = stop_polling
        self._get_avatar = get_avatar

        # Restore current user from persisted config
        self.current_user: dict[str, Any] | None = None
        tc = get_platform_config(store.config, "twitch")
        if tc.get("user_id") and tc.get("user_login"):
            self.current_user = {
                "id": tc["user_id"],
                "login": tc["user_login"],
                "display_name": tc.get("user_display_name", ""),
            }

    # ── Twitch ────────────────────────────────────────────────────

    def twitch_login(self) -> None:
        # Move body of TwitchXApi.login verbatim.
        # self._current_user = user → self.current_user = user
        # self.stop_polling() → self._stop_polling()
        # self._restart_polling() → self._restart_polling()
        # self.refresh() → self._refresh()
        # self.get_avatar(...) → self._get_avatar(...)
        pass

    def twitch_logout(self) -> None:
        # Move body of TwitchXApi.logout verbatim.
        # Remove self._current_user = None line (replace with self.current_user = None)
        pass

    def twitch_test_connection(self, client_id: str, client_secret: str) -> None:
        # Move body of TwitchXApi.test_connection verbatim.
        pass

    def twitch_import_follows(self) -> None:
        # Move body of TwitchXApi.import_follows verbatim.
        # self._current_user → self.current_user
        # self.refresh() → self._refresh()
        pass

    # ── Kick ──────────────────────────────────────────────────────

    def kick_login(self, client_id: str = "", client_secret: str = "") -> None:
        # Move body of TwitchXApi.kick_login verbatim.
        # self.refresh() → self._refresh()
        # self._restart_polling() → self._restart_polling()
        pass

    def kick_logout(self) -> None:
        # Move body of TwitchXApi.kick_logout verbatim.
        pass

    def kick_test_connection(self, client_id: str, client_secret: str) -> None:
        # Move body of TwitchXApi.kick_test_connection verbatim.
        pass

    # ── YouTube ───────────────────────────────────────────────────

    def youtube_login(self, client_id: str = "", client_secret: str = "") -> None:
        # Move body of TwitchXApi.youtube_login verbatim.
        # self.refresh() → self._refresh()
        pass

    def youtube_logout(self) -> None:
        # Move body of TwitchXApi.youtube_logout verbatim.
        pass

    def youtube_test_connection(self, api_key: str = "") -> None:
        # Move body of TwitchXApi.youtube_test_connection verbatim.
        pass

    def youtube_import_follows(self) -> None:
        # Move body of TwitchXApi.youtube_import_follows verbatim.
        # self.refresh() → self._refresh()
        pass
```

**IMPORTANT:** Replace every `pass` with the verbatim body from the corresponding `TwitchXApi` method, applying transformation rules. The most critical substitution: `self._current_user` → `self.current_user`.

- [ ] **Step 2: Wire `AuthHandler` into `TwitchXApi.__init__`**

```python
from ui.auth import AuthHandler

self._auth = AuthHandler(
    store=self._store,
    twitch=self._twitch,
    kick=self._kick,
    youtube=self._youtube,
    eval_js=self._eval_js,
    shutdown=self._shutdown,
    run_in_thread=self._run_in_thread,
    close_thread_loop=self._close_thread_loop,
    refresh=self.refresh,
    restart_polling=self._restart_polling,
    stop_polling=self.stop_polling,
    get_avatar=self.get_avatar,
)
```

Remove the `self._current_user` declaration from `__init__` (it now lives in `AuthHandler`).

- [ ] **Step 3: Update `get_config()` to read `self._auth.current_user`**

In `TwitchXApi.get_config()`, replace:
```python
if self._current_user:
    masked["current_user"] = self._current_user
```
with:
```python
if self._auth.current_user:
    masked["current_user"] = self._auth.current_user
```

- [ ] **Step 4: Replace auth methods in `TwitchXApi` with delegation wrappers**

Delete the bodies of `login`, `logout`, `test_connection`, `import_follows`, `kick_login`, `kick_logout`, `kick_test_connection`, `youtube_login`, `youtube_logout`, `youtube_test_connection`, `youtube_import_follows`, and `_parse_scopes` from `api.py`.

Replace with:
```python
# ── Auth (delegated to AuthHandler) ─────────────────────────────

def login(self) -> None:
    self._auth.twitch_login()

def logout(self) -> None:
    self._auth.twitch_logout()

def test_connection(self, client_id: str, client_secret: str) -> None:
    self._auth.twitch_test_connection(client_id, client_secret)

def import_follows(self) -> None:
    self._auth.twitch_import_follows()

def kick_login(self, client_id: str = "", client_secret: str = "") -> None:
    self._auth.kick_login(client_id, client_secret)

def kick_logout(self) -> None:
    self._auth.kick_logout()

def kick_test_connection(self, client_id: str, client_secret: str) -> None:
    self._auth.kick_test_connection(client_id, client_secret)

def youtube_login(self, client_id: str = "", client_secret: str = "") -> None:
    self._auth.youtube_login(client_id, client_secret)

def youtube_logout(self) -> None:
    self._auth.youtube_logout()

def youtube_test_connection(self, api_key: str = "") -> None:
    self._auth.youtube_test_connection(api_key)

def youtube_import_follows(self) -> None:
    self._auth.youtube_import_follows()
```

- [ ] **Step 5: Remove now-unused imports from `api.py`**

Check and remove: `import webbrowser`, `from core.oauth_server import wait_for_oauth_code`, `from core.platforms.kick import OAUTH_SCOPE as KICK_OAUTH_SCOPE` — if no longer referenced.

- [ ] **Step 6: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -v --tb=short -q
```

Expected: same pass/fail count.

---

### Task 6: Extract `PlayerHandler` to `ui/player.py`

**Files:**
- Create: `ui/player.py`
- Modify: `ui/api.py`

- [ ] **Step 1: Create `ui/player.py` with the complete `PlayerHandler` class**

```python
from __future__ import annotations

import json
import subprocess
import threading
from typing import TYPE_CHECKING, Any, Callable

from core.launcher import launch_stream
from core.stream_resolver import resolve_hls_url
from core.storage import get_settings, update_config
import webbrowser

if TYPE_CHECKING:
    from ui.config_store import ConfigStore


class PlayerHandler:
    """Manages stream launch, HLS resolution, and external player fallback."""

    def __init__(
        self,
        store: ConfigStore,
        eval_js: Callable[[str], None],
        shutdown: threading.Event,
        run_in_thread: Callable,
        get_live_streams: Callable[[], list[dict[str, Any]]],
        start_chat: Callable[[str, str], None],
        stop_chat: Callable[[], None],
    ) -> None:
        self._store = store
        self._eval_js = eval_js
        self._shutdown = shutdown
        self._run_in_thread = run_in_thread
        self._get_live_streams = get_live_streams
        self._start_chat = start_chat
        self._stop_chat = stop_chat
        self._watching_channel: str | None = None
        self._launch_timer: threading.Timer | None = None
        self._launch_elapsed: int = 0
        self._launch_channel: str | None = None

    def watch(self, channel: str, quality: str) -> None:
        # Move body of TwitchXApi.watch verbatim.
        # self._live_streams → self._get_live_streams()
        # self._find_live_stream(channel) → self._find_live_stream(channel)  [keep as private method below]
        # self._stream_platform(stream) → self._stream_platform(stream)  [keep as private method below]
        # self._stream_login(s) → self._stream_login(s)  [keep as private method below]
        # self.start_chat(...) → self._start_chat(...)
        pass

    def stop(self) -> None:
        # Move body of TwitchXApi.stop_player verbatim.
        # self.stop_chat() → self._stop_chat()
        # self._watching_channel = None  (already owned by PlayerHandler)
        pass

    def watch_external(self, channel: str, quality: str) -> None:
        # Move body of TwitchXApi.watch_external verbatim.
        pass

    def open_browser(self, channel: str, platform: str = "twitch") -> None:
        # Move body of TwitchXApi.open_browser verbatim.
        pass

    def cancel_launch_timer(self) -> None:
        # Move body of TwitchXApi._cancel_launch_timer verbatim.
        pass

    # ── Private helpers (moved from TwitchXApi) ────────────────────

    def _start_launch_timer(self) -> None:
        # Move body of TwitchXApi._start_launch_timer verbatim.
        pass

    @staticmethod
    def _stream_login(stream: dict[str, Any]) -> str:
        # Move body of TwitchXApi._stream_login verbatim.
        pass

    @staticmethod
    def _stream_platform(stream: dict[str, Any]) -> str:
        # Move body of TwitchXApi._stream_platform verbatim.
        pass

    def _find_live_stream(self, channel: str) -> dict[str, Any] | None:
        # Move body of TwitchXApi._find_live_stream verbatim.
        # self._live_streams → self._get_live_streams()
        pass
```

**IMPORTANT:** Replace every `pass` with the verbatim body from the corresponding `TwitchXApi` method, applying transformation rules. Key substitution: `self._live_streams` (read-only) → `self._get_live_streams()`.

- [ ] **Step 2: Wire `PlayerHandler` into `TwitchXApi.__init__`**

```python
from ui.player import PlayerHandler

self._player = PlayerHandler(
    store=self._store,
    eval_js=self._eval_js,
    shutdown=self._shutdown,
    run_in_thread=self._run_in_thread,
    get_live_streams=lambda: self._live_streams,
    start_chat=self._chat.start,
    stop_chat=self._chat.stop,
)
```

Remove declarations of `self._watching_channel`, `self._launch_timer`, `self._launch_elapsed`, `self._launch_channel` from `TwitchXApi.__init__` (they now live in `PlayerHandler`).

- [ ] **Step 3: Replace player methods in `TwitchXApi` with delegation wrappers**

Delete bodies of `watch`, `stop_player`, `watch_external`, `open_browser`, `_start_launch_timer`, `_cancel_launch_timer`, `_stream_login`, `_stream_platform`, `_find_live_stream` from `api.py`.

Replace with:
```python
# ── Player (delegated to PlayerHandler) ──────────────────────────

def watch(self, channel: str, quality: str) -> None:
    self._player.watch(channel, quality)

def stop_player(self) -> None:
    self._player.stop()

def watch_external(self, channel: str, quality: str) -> None:
    self._player.watch_external(channel, quality)

def open_browser(self, channel: str, platform: str = "twitch") -> None:
    self._player.open_browser(channel, platform)
```

- [ ] **Step 4: Update `close()` to use handler references**

```python
def close(self) -> None:
    self._chat.stop()
    self._shutdown.set()
    self.stop_polling()
    self._player.cancel_launch_timer()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        for client in self._platforms.values():
            loop.run_until_complete(client.close())
    finally:
        asyncio.set_event_loop(None)
        loop.close()
```

- [ ] **Step 5: Update `_on_data_fetched` — remove `_stream_login`/`_stream_platform` references**

`_on_data_fetched` in `api.py` does not call `_stream_login` or `_stream_platform` directly — those are only called from `watch()`. Verify:
```bash
grep -n "_stream_login\|_stream_platform\|_find_live_stream" ui/api.py
```
Expected: zero results (all moved to PlayerHandler).

- [ ] **Step 6: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -v --tb=short -q
```

Expected: same pass/fail count.

---

### Task 7: Final cleanup and commit

**Files:**
- Modify: `ui/api.py` (remove dead code, verify imports)

- [ ] **Step 1: Remove dead imports from `api.py`**

After all extractions, verify each import in `api.py` is still used:
```bash
source .venv/bin/activate && python -c "import ui.api" 2>&1
```
Also run:
```bash
source .venv/bin/activate && python -m ruff check ui/api.py ui/auth.py ui/channels.py ui/chat.py ui/player.py ui/config_store.py --select F401
```
Remove any F401 (unused import) reported.

- [ ] **Step 2: Verify `api.py` line count has dropped significantly**

```bash
wc -l ui/api.py ui/auth.py ui/channels.py ui/chat.py ui/player.py ui/config_store.py
```

Expected: `api.py` ≤ 950 lines, total across all 6 files ≈ 2250 lines (no net gain — just redistributed).

- [ ] **Step 3: Run full test suite**

```bash
source .venv/bin/activate && pytest tests/ -v
```

Expected: same pass count as before this refactor. Specifically:
- `tests/test_app.py` — all pass (`_sanitize_username` re-export works)
- `tests/test_api.py` — all pass (delegation wrappers preserve interface)

- [ ] **Step 4: Run ruff format**

```bash
source .venv/bin/activate && ruff format ui/config_store.py ui/auth.py ui/channels.py ui/chat.py ui/player.py ui/api.py
```

- [ ] **Step 5: Commit**

```bash
git add ui/config_store.py ui/auth.py ui/channels.py ui/chat.py ui/player.py ui/api.py
git commit -m "$(cat <<'EOF'
refactor(api): decompose 2197-line TwitchXApi into handler objects

Extract AuthHandler, ChannelHandler, ChatHandler, PlayerHandler into
focused ui/ modules. Shared mutable config lives in ConfigStore — a
single reference held by all handlers so any update is immediately
visible across the system. TwitchXApi becomes a thin facade that owns
fetch/poll state and delegates to handler instances. JS interface
unchanged; test compat preserved via staticmethod re-exports.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```
