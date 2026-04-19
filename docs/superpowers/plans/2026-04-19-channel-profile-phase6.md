# Channel Profile (Phase 6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a channel profile view with avatar, bio, follower count, live indicator, and follow/unfollow toggle; accessible from the main stream grid (context menu) and the browse streams view (card link).

**Architecture:** 5 tasks in dependency order — (1) `TwitchClient.get_channel_info` backend method, (2) `TwitchXApi.get_channel_profile` bridge with cross-platform normalization, (3) HTML/CSS shell, (4) JS rendering and navigation, (5) entry-point wiring. Follow/unfollow delegates to the existing `add_channel`/`remove_channel` methods (local favorites) for all three platforms — Twitch dropped their follow API in 2023, Kick never had one, and YouTube's subscribe API requires a new OAuth scope not worth adding here.

**Tech Stack:** Python (asyncio, httpx), vanilla JS, pywebview bridge, pytest

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `core/platforms/twitch.py` | Add `get_channel_info(login)` — parallel `/users` + `/streams` fetch |
| Modify | `ui/api.py` | Add `_normalize_channel_info_to_profile()` static + `get_channel_profile()` public |
| Modify | `ui/index.html` | Channel view HTML, CSS, JS functions, entry-point wiring |
| Modify | `tests/platforms/test_twitch.py` | 4 new tests for `get_channel_info` |
| Create | `tests/test_channel_api.py` | 6 tests for `TwitchXApi.get_channel_profile` |

---

## Task 1: TwitchClient.get_channel_info

**Files:**
- Modify: `core/platforms/twitch.py` — append after `get_top_streams` (after line 364)
- Modify: `tests/platforms/test_twitch.py` — append new class

`KickClient.get_channel_info` and `YouTubeClient.get_channel_info` already exist. This task closes the only gap in the platform layer.

- [ ] **Step 1: Write the failing tests**

Append to `tests/platforms/test_twitch.py` (add `from typing import Any` to imports at top if missing — it's already there):

```python
class TestGetChannelInfo:
    def test_returns_normalized_profile_for_live_user(self) -> None:
        client = TwitchClient()

        async def fake_get(endpoint: str, params: Any = None) -> Any:
            if endpoint == "/users":
                return {
                    "data": [{
                        "id": "44322889",
                        "login": "xqc",
                        "display_name": "xQc",
                        "profile_image_url": "https://img.jpg",
                        "description": "lulw",
                    }]
                }
            return {"data": [{"user_login": "xqc"}]}  # /streams

        loop = asyncio.new_event_loop()
        client._get = fake_get  # type: ignore[method-assign]
        result = loop.run_until_complete(client.get_channel_info("xQc"))
        loop.close()

        assert result["platform"] == "twitch"
        assert result["login"] == "xqc"
        assert result["display_name"] == "xQc"
        assert result["bio"] == "lulw"
        assert result["avatar_url"] == "https://img.jpg"
        assert result["is_live"] is True
        assert result["followers"] == -1
        assert result["can_follow_via_api"] is False

    def test_returns_empty_dict_for_unknown_user(self) -> None:
        client = TwitchClient()

        async def fake_get(endpoint: str, params: Any = None) -> Any:
            return {"data": []}

        loop = asyncio.new_event_loop()
        client._get = fake_get  # type: ignore[method-assign]
        result = loop.run_until_complete(client.get_channel_info("nobody"))
        loop.close()

        assert result == {}

    def test_empty_login_returns_empty_dict_without_http(self) -> None:
        client = TwitchClient()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(client.get_channel_info(""))
        loop.run_until_complete(client.close_loop_resources())
        loop.close()

        assert result == {}

    def test_offline_user_sets_is_live_false(self) -> None:
        client = TwitchClient()

        async def fake_get(endpoint: str, params: Any = None) -> Any:
            if endpoint == "/users":
                return {
                    "data": [{
                        "id": "999",
                        "login": "streamerfoo",
                        "display_name": "StreamerFoo",
                        "profile_image_url": "",
                        "description": "",
                    }]
                }
            return {"data": []}  # /streams — not live

        loop = asyncio.new_event_loop()
        client._get = fake_get  # type: ignore[method-assign]
        result = loop.run_until_complete(client.get_channel_info("streamerfoo"))
        loop.close()

        assert result["is_live"] is False
```

- [ ] **Step 2: Run test, verify it fails**

```bash
cd /Users/pesnya/Documents/streamdeck && uv run pytest tests/platforms/test_twitch.py::TestGetChannelInfo -v
```

Expected: `FAILED` — `AttributeError: 'TwitchClient' object has no attribute 'get_channel_info'`

- [ ] **Step 3: Implement the method**

In `core/platforms/twitch.py`, append after the last line of `get_top_streams` (after the closing `]` of the list comprehension at line 364). Insert before the end of the file:

```python
    async def get_channel_info(self, login: str) -> dict[str, Any]:
        """Return normalized channel profile dict. Costs 2 API calls (/users + /streams).

        followers is always -1 — /channels/followers requires broadcaster-level auth.
        """
        login = login.strip().lower()
        if not login:
            return {}
        users_data, streams_data = await asyncio.gather(
            self._get("/users", [("login", login)]),
            self._get("/streams", [("user_login", login)]),
        )
        users = users_data.get("data", [])
        if not users:
            return {}
        u = users[0]
        is_live = bool(streams_data.get("data", []))
        return {
            "platform": "twitch",
            "channel_id": u.get("id", ""),
            "login": u.get("login", login),
            "display_name": u.get("display_name", ""),
            "bio": u.get("description", ""),
            "avatar_url": u.get("profile_image_url", ""),
            "followers": -1,
            "is_live": is_live,
            "can_follow_via_api": False,
        }
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
uv run pytest tests/platforms/test_twitch.py::TestGetChannelInfo -v
```

Expected: `4 passed`

- [ ] **Step 5: Run full test suite to confirm no regressions**

```bash
uv run pytest tests/ -v
```

Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add core/platforms/twitch.py tests/platforms/test_twitch.py
git commit -m "feat(twitch): add get_channel_info — parallel /users+/streams, normalized profile dict"
```

---

## Task 2: TwitchXApi.get_channel_profile bridge

**Files:**
- Modify: `ui/api.py` — add after `open_browser` method (after line 2133)
- Create: `tests/test_channel_api.py`

The private `_normalize_channel_info_to_profile` handles per-platform key mapping (Kick returns a deep-merged dict with nested `user.profile_pic` / `followers_count`; YouTube uses `description` not `bio`). The public `get_channel_profile` follows the exact same thread+loop pattern as every other API method.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_channel_api.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

import core.storage as storage
from core.storage import DEFAULT_CONFIG, save_config
from ui.api import TwitchXApi


def _patch_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(storage, "CONFIG_DIR", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(storage, "CONFIG_FILE", tmp_path / "config.json")  # type: ignore[attr-defined]
    monkeypatch.setattr(storage, "_OLD_CONFIG_DIR", tmp_path / "old")  # type: ignore[attr-defined]


def _parse_channel_profile(emitted: list[str]) -> dict:
    raw = emitted[-1]
    assert "window.onChannelProfile(" in raw
    return json.loads(raw.split("window.onChannelProfile(", 1)[1].rstrip(")"))


def test_get_channel_profile_twitch_emits_js_callback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_storage(monkeypatch, tmp_path)
    api = TwitchXApi()
    emitted: list[str] = []

    async def fake_channel_info(login: str) -> dict:
        return {
            "platform": "twitch",
            "channel_id": "44322889",
            "login": "xqc",
            "display_name": "xQc",
            "bio": "lulw",
            "avatar_url": "https://img.jpg",
            "followers": -1,
            "is_live": True,
            "can_follow_via_api": False,
        }

    monkeypatch.setattr(api._twitch, "get_channel_info", fake_channel_info)
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.get_channel_profile("xqc", "twitch")

    payload = _parse_channel_profile(emitted)
    assert payload["login"] == "xqc"
    assert payload["display_name"] == "xQc"
    assert payload["platform"] == "twitch"
    assert payload["is_live"] is True
    assert payload["is_favorited"] is False


def test_get_channel_profile_marks_is_favorited_when_in_favorites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_storage(monkeypatch, tmp_path)

    config = {
        **DEFAULT_CONFIG,
        "favorites": [{"platform": "twitch", "login": "xqc", "display_name": "xQc"}],
    }
    save_config(config)

    api = TwitchXApi()
    emitted: list[str] = []

    async def fake_channel_info(login: str) -> dict:
        return {
            "platform": "twitch",
            "channel_id": "44322889",
            "login": "xqc",
            "display_name": "xQc",
            "bio": "",
            "avatar_url": "",
            "followers": -1,
            "is_live": False,
            "can_follow_via_api": False,
        }

    monkeypatch.setattr(api._twitch, "get_channel_info", fake_channel_info)
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.get_channel_profile("xqc", "twitch")

    payload = _parse_channel_profile(emitted)
    assert payload["is_favorited"] is True


def test_get_channel_profile_kick_normalizes_raw_dict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_storage(monkeypatch, tmp_path)
    api = TwitchXApi()
    emitted: list[str] = []

    async def fake_channel_info(slug: str) -> dict:
        return {
            "slug": "trainwreckstv",
            "channel_id": 99,
            "user": {"username": "Trainwreckstv", "profile_pic": "https://avatar.jpg"},
            "description": "slots and poker",
            "followers_count": 500000,
            "is_live": True,
        }

    monkeypatch.setattr(api._kick, "get_channel_info", fake_channel_info)
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.get_channel_profile("trainwreckstv", "kick")

    payload = _parse_channel_profile(emitted)
    assert payload["platform"] == "kick"
    assert payload["login"] == "trainwreckstv"
    assert payload["display_name"] == "Trainwreckstv"
    assert payload["bio"] == "slots and poker"
    assert payload["avatar_url"] == "https://avatar.jpg"
    assert payload["followers"] == 500000
    assert payload["is_live"] is True


def test_get_channel_profile_youtube_normalizes_raw_dict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_storage(monkeypatch, tmp_path)
    api = TwitchXApi()
    emitted: list[str] = []

    async def fake_channel_info(channel_id: str) -> dict:
        return {
            "channel_id": "UCxxxxxx",
            "display_name": "SomeYouTuber",
            "description": "gaming videos",
            "avatar_url": "https://yt.jpg",
            "followers": 1_000_000,
        }

    monkeypatch.setattr(api._youtube, "get_channel_info", fake_channel_info)
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.get_channel_profile("UCxxxxxx", "youtube")

    payload = _parse_channel_profile(emitted)
    assert payload["platform"] == "youtube"
    assert payload["login"] == "UCxxxxxx"
    assert payload["display_name"] == "SomeYouTuber"
    assert payload["bio"] == "gaming videos"
    assert payload["followers"] == 1_000_000
    assert payload["is_live"] is False


def test_get_channel_profile_emits_null_on_empty_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_storage(monkeypatch, tmp_path)
    api = TwitchXApi()
    emitted: list[str] = []

    async def fake_channel_info(login: str) -> dict:
        return {}

    monkeypatch.setattr(api._twitch, "get_channel_info", fake_channel_info)
    monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.get_channel_profile("nobody", "twitch")

    assert emitted[-1] == "window.onChannelProfile(null)"


def test_get_channel_profile_ignores_unknown_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_storage(monkeypatch, tmp_path)
    api = TwitchXApi()
    emitted: list[str] = []
    monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

    api.get_channel_profile("someone", "nonexistent")

    assert not emitted
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_channel_api.py -v
```

Expected: `FAILED` — `AttributeError: 'TwitchXApi' object has no attribute 'get_channel_profile'`

- [ ] **Step 3: Implement in ui/api.py**

In `ui/api.py`, after the `open_browser` method (after line 2133, before `# ── Avatars + Thumbnails`), insert:

```python
    # ── Channel profile ─────────────────────────────────────────

    @staticmethod
    def _normalize_channel_info_to_profile(
        raw: dict[str, Any], login: str, platform: str
    ) -> dict[str, Any]:
        if platform == "twitch":
            return {
                "platform": "twitch",
                "channel_id": raw.get("channel_id", ""),
                "login": raw.get("login", login),
                "display_name": raw.get("display_name", login),
                "bio": raw.get("bio", ""),
                "avatar_url": raw.get("avatar_url", ""),
                "followers": raw.get("followers", -1),
                "is_live": bool(raw.get("is_live", False)),
                "can_follow_via_api": False,
            }
        if platform == "kick":
            user = raw.get("user") or {}
            return {
                "platform": "kick",
                "channel_id": str(raw.get("channel_id") or raw.get("id", "")),
                "login": raw.get("slug", login),
                "display_name": (
                    user.get("username")
                    or raw.get("username")
                    or raw.get("slug", login)
                ),
                "bio": raw.get("description") or raw.get("bio", ""),
                "avatar_url": user.get("profile_pic") or raw.get("profile_picture", ""),
                "followers": raw.get("followers_count", 0),
                "is_live": bool(raw.get("is_live", False)) or bool(raw.get("stream")),
                "can_follow_via_api": False,
            }
        if platform == "youtube":
            channel_id = raw.get("channel_id", login)
            return {
                "platform": "youtube",
                "channel_id": channel_id,
                "login": channel_id,
                "display_name": raw.get("display_name", login),
                "bio": raw.get("description", ""),
                "avatar_url": raw.get("avatar_url", ""),
                "followers": raw.get("followers", 0),
                "is_live": False,
                "can_follow_via_api": False,
            }
        return {}

    def get_channel_profile(self, login: str, platform: str = "twitch") -> None:
        client = self._get_platform(platform)
        if client is None:
            return

        def do_fetch() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                raw = loop.run_until_complete(client.get_channel_info(login))
                if not raw:
                    self._eval_js("window.onChannelProfile(null)")
                    return
                profile = self._normalize_channel_info_to_profile(raw, login, platform)
                if not profile:
                    self._eval_js("window.onChannelProfile(null)")
                    return
                favs = get_favorites(self._config)
                profile["is_favorited"] = any(
                    f.get("login") == profile["login"] and f.get("platform") == platform
                    for f in favs
                )
                self._eval_js(f"window.onChannelProfile({json.dumps(profile)})")
            except Exception as e:
                logger.warning("get_channel_profile failed: %s", e)
                self._eval_js("window.onChannelProfile(null)")
            finally:
                self._close_thread_loop(loop)

        self._run_in_thread(do_fetch)
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
uv run pytest tests/test_channel_api.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Run full suite**

```bash
uv run pytest tests/ -v
```

Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add ui/api.py tests/test_channel_api.py
git commit -m "feat(api): add get_channel_profile bridge with cross-platform normalization"
```

---

## Task 3: Channel view HTML + CSS

**Files:**
- Modify: `ui/index.html`
  - HTML: insert after closing `</div>` of `#browse-view` (line 1229), before `<!-- Player view -->`
  - CSS: insert after `.browse-loading.hidden, .browse-empty.hidden { display: none; }` (line 1120)

- [ ] **Step 1: Add the HTML**

In `ui/index.html`, find the following exact string (line 1229–1230):

```
        </div>
      </div>
      <!-- Player view (replaces grid when a stream is playing) -->
```

Replace it with:

```
        </div>
      </div>

      <!-- Channel profile view -->
      <div id="channel-view" class="hidden">
        <div id="channel-header">
          <button id="channel-back-btn" class="browse-back-btn" onclick="hideChannelView()">&#8592; Back</button>
          <span id="channel-header-title"></span>
        </div>
        <div id="channel-body">
          <div id="channel-profile-card">
            <img id="channel-avatar" class="channel-avatar hidden" src="" alt="">
            <div id="channel-meta">
              <div id="channel-display-name"></div>
              <div id="channel-login-text"></div>
              <div id="channel-live-badge" class="channel-live-badge hidden">LIVE</div>
              <div id="channel-followers"></div>
            </div>
            <div id="channel-actions">
              <button id="channel-follow-btn" class="channel-follow-btn" onclick="toggleChannelFollow()">Follow</button>
              <button id="channel-watch-btn" class="channel-watch-btn hidden" onclick="watchChannelStream()">&#9654; Watch Now</button>
            </div>
          </div>
          <div id="channel-bio"></div>
          <div id="channel-tabs">
            <button class="channel-tab active" data-tab="live" onclick="switchChannelTab(this,'live')">Live Now</button>
            <button class="channel-tab" data-tab="vods" onclick="switchChannelTab(this,'vods')">VODs</button>
            <button class="channel-tab" data-tab="clips" onclick="switchChannelTab(this,'clips')">Clips</button>
          </div>
          <div id="channel-tab-live" class="channel-tab-panel">
            <div id="channel-live-empty" class="channel-empty hidden">Channel is not live right now.</div>
          </div>
          <div id="channel-tab-vods" class="channel-tab-panel hidden">
            <div class="channel-empty">VODs coming in a future update.</div>
          </div>
          <div id="channel-tab-clips" class="channel-tab-panel hidden">
            <div class="channel-empty">Clips coming in a future update.</div>
          </div>
          <div id="channel-loading" class="browse-loading hidden">Loading...</div>
        </div>
      </div>

      <!-- Player view (replaces grid when a stream is playing) -->
```

- [ ] **Step 2: Add the CSS**

In `ui/index.html`, find the exact line:

```
.browse-loading.hidden, .browse-empty.hidden { display: none; }
```

After it, insert:

```css

/* ── Channel profile view ────────────────────────────── */
#channel-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--bg-base);
}
#channel-view.hidden { display: none; }

#channel-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

#channel-profile-card {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 14px;
  background: var(--bg-elevated);
  border-radius: var(--radius-lg);
  border: 1px solid rgba(255,255,255,0.06);
}

.channel-avatar {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
}
.channel-avatar.hidden { display: none; }

#channel-meta {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

#channel-display-name {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-primary);
}

#channel-login-text {
  font-size: 12px;
  color: var(--text-muted);
}

.channel-live-badge {
  display: inline-block;
  background: var(--live-red);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  letter-spacing: 0.05em;
  margin-top: 2px;
  width: fit-content;
}
.channel-live-badge.hidden { display: none; }

#channel-followers {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
}

#channel-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex-shrink: 0;
}

.channel-follow-btn {
  padding: 6px 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--accent);
  background: transparent;
  color: var(--accent);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.channel-follow-btn:hover { background: var(--accent); color: #fff; }
.channel-follow-btn.following { background: var(--accent); color: #fff; }

.channel-watch-btn {
  padding: 6px 14px;
  border-radius: var(--radius-md);
  border: none;
  background: var(--live-green);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.channel-watch-btn:hover { filter: brightness(1.1); }
.channel-watch-btn.hidden { display: none; }

#channel-bio {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

#channel-tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  padding-bottom: 8px;
}

.channel-tab {
  padding: 4px 12px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
}
.channel-tab:hover { background: var(--bg-elevated); color: var(--text-primary); }
.channel-tab.active { background: var(--bg-elevated); color: var(--text-primary); font-weight: 600; }

.channel-tab-panel { display: flex; flex-direction: column; gap: 8px; }
.channel-tab-panel.hidden { display: none; }

.channel-empty {
  color: var(--text-muted);
  font-size: 13px;
  padding: 24px 0;
  text-align: center;
}
```

- [ ] **Step 3: Verify Python still loads**

```bash
uv run python -c "from ui.api import TwitchXApi; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add ui/index.html
git commit -m "feat(ui): add channel-view HTML and CSS"
```

---

## Task 4: Channel view JavaScript

**Files:**
- Modify: `ui/index.html`
  - Module-level vars: after `let ctxChannel = null;` (line 1465)
  - Navigation functions: after `hideBrowseView` function (after line 2253)
  - `window.onChannelProfile` callback: after the closing `};` of `window.onBrowseTopStreams` (after line 2598)

- [ ] **Step 1: Add module-level state vars**

In `ui/index.html`, find:

```javascript
let ctxChannel = null;
```

Replace with:

```javascript
let ctxChannel = null;
let channelViewSource = 'grid';
let channelProfile = null;
```

- [ ] **Step 2: Add navigation + interaction functions**

In `ui/index.html`, find the exact string:

```javascript
function browseGoBack() {
```

Insert the following block **before** it (i.e., just before `function browseGoBack`):

```javascript
function showChannelView(login, platform, source) {
  channelViewSource = source || 'grid';
  channelProfile = null;

  if (channelViewSource === 'browse') {
    document.getElementById('browse-view').classList.add('hidden');
  } else {
    document.getElementById('toolbar').classList.add('hidden');
    document.getElementById('stream-grid').classList.add('hidden');
  }

  document.getElementById('channel-view').classList.remove('hidden');
  document.getElementById('channel-loading').classList.remove('hidden');
  document.getElementById('channel-profile-card').style.opacity = '0';
  document.getElementById('channel-header-title').textContent = login;
  document.getElementById('channel-display-name').textContent = '';
  document.getElementById('channel-login-text').textContent = '';
  document.getElementById('channel-followers').textContent = '';
  document.getElementById('channel-bio').textContent = '';
  document.getElementById('channel-avatar').classList.add('hidden');
  document.getElementById('channel-live-badge').classList.add('hidden');
  document.getElementById('channel-watch-btn').classList.add('hidden');
  document.getElementById('channel-follow-btn').textContent = 'Follow';
  document.getElementById('channel-follow-btn').classList.remove('following');
  document.getElementById('channel-live-empty').classList.add('hidden');
  document.querySelectorAll('.channel-tab').forEach(function(t) {
    t.classList.toggle('active', t.dataset.tab === 'live');
  });
  document.querySelectorAll('.channel-tab-panel').forEach(function(p) {
    p.classList.toggle('hidden', p.id !== 'channel-tab-live');
  });

  if (api) api.get_channel_profile(login, platform);
}

function hideChannelView() {
  document.getElementById('channel-view').classList.add('hidden');
  if (channelViewSource === 'browse') {
    document.getElementById('browse-view').classList.remove('hidden');
  } else {
    document.getElementById('toolbar').classList.remove('hidden');
    document.getElementById('stream-grid').classList.remove('hidden');
  }
}

function switchChannelTab(btn, tab) {
  document.querySelectorAll('.channel-tab').forEach(function(t) {
    t.classList.toggle('active', t === btn);
  });
  document.querySelectorAll('.channel-tab-panel').forEach(function(p) {
    p.classList.toggle('hidden', p.id !== 'channel-tab-' + tab);
  });
}

function toggleChannelFollow() {
  if (!channelProfile || !api) return;
  var p = channelProfile;
  if (p.is_favorited) {
    api.remove_channel(p.login, p.platform);
    p.is_favorited = false;
    document.getElementById('channel-follow-btn').textContent = 'Follow';
    document.getElementById('channel-follow-btn').classList.remove('following');
  } else {
    api.add_channel(p.login, p.platform, p.display_name);
    p.is_favorited = true;
    document.getElementById('channel-follow-btn').textContent = 'Following';
    document.getElementById('channel-follow-btn').classList.add('following');
  }
}

function watchChannelStream() {
  if (!channelProfile || !api) return;
  var p = channelProfile;
  if (p.platform === 'youtube') return;
  hideChannelView();
  var quality = document.getElementById('quality-select')
    ? document.getElementById('quality-select').value
    : 'best';
  api.watch_direct(p.login, p.platform, quality);
}

```

- [ ] **Step 3: Add the window.onChannelProfile callback**

In `ui/index.html`, find the exact string that ends `window.onBrowseTopStreams`:

```javascript
    grid.appendChild(card);
  });
};

/* ── Rendering ──────────────────────────────────────────── */
```

Replace with:

```javascript
    grid.appendChild(card);
  });
};

window.onChannelProfile = function(profile) {
  document.getElementById('channel-loading').classList.add('hidden');

  if (!profile) {
    document.getElementById('channel-bio').textContent = 'Channel not found.';
    document.getElementById('channel-profile-card').style.opacity = '1';
    return;
  }

  channelProfile = profile;

  document.getElementById('channel-header-title').textContent = profile.display_name || profile.login;
  document.getElementById('channel-display-name').textContent = profile.display_name || profile.login;
  document.getElementById('channel-login-text').textContent = '@' + profile.login;

  var followersEl = document.getElementById('channel-followers');
  followersEl.textContent = profile.followers >= 0
    ? formatViewers(profile.followers) + ' followers'
    : '';

  document.getElementById('channel-bio').textContent = profile.bio || '';

  var avatarEl = document.getElementById('channel-avatar');
  if (profile.avatar_url) {
    avatarEl.src = profile.avatar_url;
    avatarEl.classList.remove('hidden');
  }

  document.getElementById('channel-live-badge').classList.toggle('hidden', !profile.is_live);
  document.getElementById('channel-live-empty').classList.toggle('hidden', !!profile.is_live);

  var followBtn = document.getElementById('channel-follow-btn');
  followBtn.textContent = profile.is_favorited ? 'Following' : 'Follow';
  followBtn.classList.toggle('following', !!profile.is_favorited);

  var canWatch = profile.is_live && profile.platform !== 'youtube';
  document.getElementById('channel-watch-btn').classList.toggle('hidden', !canWatch);

  document.getElementById('channel-profile-card').style.opacity = '1';
};

/* ── Rendering ──────────────────────────────────────────── */
```

- [ ] **Step 4: Verify Python still loads**

```bash
uv run python -c "from ui.api import TwitchXApi; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add ui/index.html
git commit -m "feat(ui): channel view JS — showChannelView, onChannelProfile, follow toggle, watch now"
```

---

## Task 5: Entry-point wiring

**Files:**
- Modify: `ui/index.html`
  - Context menu HTML: add "View Channel" item
  - Context menu JS handler: handle `profile` action
  - Browse stream cards: add profile link per card
  - Browse stream card CSS: style the profile link

- [ ] **Step 1: Add the context menu item**

In `ui/index.html`, find the context menu HTML:

```html
  <div class="ctx-item" data-action="browser">&#127760; Open in Browser</div>
  <div class="ctx-item" data-action="copy">&#128203; Copy URL</div>
```

Replace with:

```html
  <div class="ctx-item" data-action="browser">&#127760; Open in Browser</div>
  <div class="ctx-item" data-action="profile">&#128100; View Channel</div>
  <div class="ctx-item" data-action="copy">&#128203; Copy URL</div>
```

- [ ] **Step 2: Handle the profile action in the context menu click listener**

In `ui/index.html`, find:

```javascript
    else if (action === 'browser') { if (api) api.open_browser(ctxChannel, ctxPlat); }
```

Replace with:

```javascript
    else if (action === 'browser') { if (api) api.open_browser(ctxChannel, ctxPlat); }
    else if (action === 'profile') { showChannelView(ctxChannel, ctxPlat, 'grid'); }
```

- [ ] **Step 3: Add profile link CSS for browse stream cards**

In `ui/index.html`, find:

```css
.browse-stream-card:hover { transform: translateY(-2px); }
```

After it, insert:

```css
.browse-stream-profile-link {
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
  padding: 4px 0 2px;
  cursor: pointer;
  text-decoration: underline;
}
.browse-stream-profile-link:hover { color: var(--accent); }
```

- [ ] **Step 4: Add profile link to browse stream cards**

In `ui/index.html`, find this exact string inside `window.onBrowseTopStreams`:

```javascript
    card.appendChild(thumb);
    card.appendChild(info);
    grid.appendChild(card);
```

Replace with:

```javascript
    card.appendChild(thumb);
    card.appendChild(info);

    var profileLink = document.createElement('div');
    profileLink.className = 'browse-stream-profile-link';
    profileLink.textContent = 'View Channel';
    (function(s) {
      profileLink.onclick = function(e) {
        e.stopPropagation();
        showChannelView(s.channel_login, s.platform, 'browse');
      };
    })(stream);
    card.appendChild(profileLink);

    grid.appendChild(card);
```

Note: the IIFE `(function(s) { ... })(stream)` captures `stream` by value, preventing the closure-in-loop bug.

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests pass (no Python changed in this task).

- [ ] **Step 6: Commit**

```bash
git add ui/index.html
git commit -m "feat(ui): wire channel view — context menu item + browse card profile link"
```

---

## Self-Review

### Spec coverage

| Spec requirement | Task |
|-----------------|------|
| Banner, avatar, display name | Task 3 HTML + Task 4 JS (`window.onChannelProfile`) |
| Bio | Task 3 HTML + Task 4 JS |
| Follower count | Task 3 HTML + Task 4 JS |
| Follow button (API where supported, local otherwise) | Task 4 JS (`toggleChannelFollow`) + Tasks 1-2 backend; all platforms use local favorites — correct, see Architecture note |
| Live Now tab | Task 3 HTML + Task 4 JS (watch button, live badge, empty state) |
| VODs tab | Task 3 HTML (stub with "coming in future update") |
| Clips tab | Task 3 HTML (stub with "coming in future update") |
| `TwitchClient.get_channel_info` missing | Task 1 |
| Cross-platform normalization | Task 2 (`_normalize_channel_info_to_profile`) |
| Navigation entry points | Task 5 (context menu + browse card) |

### Known gaps (deferred to Phase 7)

- VODs and Clips tab content — stubs are in place for Phase 7 to fill
- Twitch follower count — always -1 because `/channels/followers` requires broadcaster auth; hidden in UI when -1

### Type consistency check

- `_normalize_channel_info_to_profile` returns keys: `platform`, `channel_id`, `login`, `display_name`, `bio`, `avatar_url`, `followers`, `is_live`, `can_follow_via_api`
- `window.onChannelProfile` reads: same keys + `is_favorited` (added in `get_channel_profile`)
- `toggleChannelFollow` reads: `p.login`, `p.platform`, `p.display_name`, `p.is_favorited` ✓
- `watchChannelStream` reads: `p.is_live`, `p.platform`, `p.login` ✓
- `showChannelView(login, platform, source)` — called with same arg order in Task 5 Step 2 (`ctxChannel, ctxPlat, 'grid'`) and Step 4 (`s.channel_login, s.platform, 'browse'`) ✓

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-19-channel-profile-phase6.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
