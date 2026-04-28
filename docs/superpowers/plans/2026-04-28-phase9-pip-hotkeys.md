# Phase 9: Picture-in-Picture + Hotkeys Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Picture-in-Picture support for the HLS video player and multistream slots, extend keyboard shortcuts with volume/mute/PiP/next-prev-stream, and add a Hotkeys settings tab where all single-key shortcuts are rebindable.

**Architecture:** PiP is purely JS — uses `webkitSetPresentationMode('picture-in-picture')` (reliable WKWebView path) with a fallback to W3C `requestPictureInPicture()`. Extended hotkeys refactor `handleKeydown` from hardcoded key strings to a `state.shortcuts` map loaded from config. A new Hotkeys settings tab renders a click-to-rebind table using a capture-phase keydown listener that intercepts the next key press.

**Tech Stack:** Python (`core/storage.py`, `ui/api.py`), vanilla JS + HTML/CSS (`ui/index.html`), pytest.

---

### Task 1: Storage — keyboard_shortcuts defaults

**Files:**
- Modify: `core/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_storage.py` (after the last existing test):

```python
from core.storage import DEFAULT_SETTINGS


def test_keyboard_shortcuts_in_default_settings() -> None:
    sc = DEFAULT_SETTINGS["keyboard_shortcuts"]
    assert sc["refresh"] == "r"
    assert sc["watch"] == " "
    assert sc["fullscreen"] == "f"
    assert sc["toggle_chat"] == "c"
    assert sc["mute"] == "m"
    assert sc["pip"] == "p"
    assert sc["volume_up"] == "ArrowUp"
    assert sc["volume_down"] == "ArrowDown"
    assert sc["next_stream"] == "ArrowRight"
    assert sc["prev_stream"] == "ArrowLeft"


def test_keyboard_shortcuts_deep_merged_from_stored(
    tmp_path: Path, monkeypatch: object
) -> None:
    config_file = _patch_storage(monkeypatch, tmp_path)
    config_file.write_text(
        json.dumps({
            "platforms": {},
            "favorites": [],
            "settings": {
                "keyboard_shortcuts": {"refresh": "G", "mute": "N"},
            },
        })
    )
    config = load_config()
    sc = config["settings"]["keyboard_shortcuts"]
    assert sc["refresh"] == "G"       # stored value wins
    assert sc["mute"] == "N"          # stored value wins
    assert sc["watch"] == " "         # default kept
    assert sc["fullscreen"] == "f"    # default kept
    assert sc["pip"] == "p"           # default kept
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_storage.py::test_keyboard_shortcuts_in_default_settings -v
```

Expected: FAIL — `KeyError: 'keyboard_shortcuts'`

- [ ] **Step 3: Add keyboard_shortcuts to DEFAULT_SETTINGS**

In `core/storage.py`, find `DEFAULT_SETTINGS` dict and add `keyboard_shortcuts` after `"pip_enabled": False,`:

```python
DEFAULT_SETTINGS: dict[str, Any] = {
    "quality": "best",
    "refresh_interval": 60,
    "youtube_refresh_interval": 300,
    "streamlink_path": "streamlink",
    "iina_path": "/Applications/IINA.app/Contents/MacOS/iina-cli",
    "notifications_enabled": True,
    "player_height": 360,
    "chat_visible": True,
    "chat_width": 340,
    "active_platform_filter": "all",
    "pip_enabled": False,
    "keyboard_shortcuts": {
        "refresh": "r",
        "watch": " ",
        "fullscreen": "f",
        "toggle_chat": "c",
        "mute": "m",
        "pip": "p",
        "volume_up": "ArrowUp",
        "volume_down": "ArrowDown",
        "next_stream": "ArrowRight",
        "prev_stream": "ArrowLeft",
    },
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_storage.py::test_keyboard_shortcuts_in_default_settings tests/test_storage.py::test_keyboard_shortcuts_deep_merged_from_stored -v
```

Expected: both PASS

- [ ] **Step 5: Run full suite**

```bash
uv run pytest tests/ -v
```

Expected: 300 passed (was 298 + 2 new)

- [ ] **Step 6: Commit**

```bash
git add core/storage.py tests/test_storage.py
git commit -m "feat(storage): add keyboard_shortcuts defaults to DEFAULT_SETTINGS"
```

---

### Task 2: API bridge — pip_enabled + keyboard_shortcuts settings round-trip

**Files:**
- Modify: `ui/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api.py` (after the last existing test):

```python
def test_get_config_includes_pip_and_shortcuts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_storage(monkeypatch, tmp_path)
    api = TwitchXApi()
    cfg = api.get_config()
    assert "pip_enabled" in cfg
    assert cfg["pip_enabled"] is False
    assert "keyboard_shortcuts" in cfg
    assert cfg["keyboard_shortcuts"]["refresh"] == "r"
    assert cfg["keyboard_shortcuts"]["pip"] == "p"


def test_get_full_config_for_settings_includes_pip_and_shortcuts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_storage(monkeypatch, tmp_path)
    api = TwitchXApi()
    cfg = api.get_full_config_for_settings()
    assert "pip_enabled" in cfg
    assert cfg["pip_enabled"] is False
    assert "keyboard_shortcuts" in cfg
    assert cfg["keyboard_shortcuts"]["refresh"] == "r"
    assert cfg["keyboard_shortcuts"]["mute"] == "m"


def test_save_settings_persists_pip_enabled_and_shortcuts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_storage(monkeypatch, tmp_path)
    api = TwitchXApi()
    monkeypatch.setattr(api, "start_polling", lambda interval: None)
    monkeypatch.setattr(api, "_eval_js", lambda code: None)

    api.save_settings(
        json.dumps({
            "pip_enabled": True,
            "keyboard_shortcuts": {"refresh": "g", "mute": "n"},
        })
    )

    stored = load_config()
    settings = stored["settings"]
    assert settings["pip_enabled"] is True
    sc = settings["keyboard_shortcuts"]
    assert sc["refresh"] == "g"
    assert sc["mute"] == "n"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_api.py::test_get_config_includes_pip_and_shortcuts tests/test_api.py::test_get_full_config_for_settings_includes_pip_and_shortcuts tests/test_api.py::test_save_settings_persists_pip_enabled_and_shortcuts -v
```

Expected: all FAIL — `KeyError` or `AssertionError`

- [ ] **Step 3: Update get_config() to include pip_enabled and keyboard_shortcuts**

In `ui/api.py`, locate `get_config()`. After the line `masked["youtube_quota_remaining"] = self._youtube.quota_remaining()`, add:

```python
        settings = get_settings(self._config)
        masked["pip_enabled"] = settings.get("pip_enabled", False)
        masked["keyboard_shortcuts"] = settings.get("keyboard_shortcuts", {})
```

Note: `get_settings(self._config)` is already called earlier in the method (to read `quality` and `refresh_interval`). Move the call or reuse. In the actual method, `settings` is not yet a local variable at this point — add this code just before `return masked`:

```python
        _st = get_settings(self._config)
        masked["pip_enabled"] = _st.get("pip_enabled", False)
        masked["keyboard_shortcuts"] = _st.get("keyboard_shortcuts", {})
        return masked
```

- [ ] **Step 4: Update get_full_config_for_settings() to include pip_enabled and keyboard_shortcuts**

In `get_full_config_for_settings()`, `settings` is already a local variable. After the last existing return entry (`"youtube_quota_remaining": self._youtube.quota_remaining()`), add two more keys before the closing `}`:

```python
        return {
            "client_id": twitch_conf.get("client_id", ""),
            # ... existing keys ...
            "youtube_quota_remaining": self._youtube.quota_remaining(),
            "pip_enabled": settings.get("pip_enabled", False),
            "keyboard_shortcuts": settings.get("keyboard_shortcuts", {}),
        }
```

- [ ] **Step 5: Update save_settings() to persist pip_enabled and keyboard_shortcuts**

In `save_settings()` / `_apply()`, after the last `if "youtube_client_secret"` block, add:

```python
            if "pip_enabled" in parsed:
                st["pip_enabled"] = bool(parsed["pip_enabled"])
            if "keyboard_shortcuts" in parsed and isinstance(
                parsed["keyboard_shortcuts"], dict
            ):
                st["keyboard_shortcuts"] = parsed["keyboard_shortcuts"]
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run pytest tests/test_api.py::test_get_config_includes_pip_and_shortcuts tests/test_api.py::test_get_full_config_for_settings_includes_pip_and_shortcuts tests/test_api.py::test_save_settings_persists_pip_enabled_and_shortcuts -v
```

Expected: all PASS

- [ ] **Step 7: Run full suite**

```bash
uv run pytest tests/ -v
```

Expected: 303 passed

- [ ] **Step 8: Commit**

```bash
git add ui/api.py tests/test_api.py
git commit -m "feat(api): expose pip_enabled and keyboard_shortcuts in settings bridge"
```

---

### Task 3: PiP button — CSS, HTML, and togglePiP() function

> No Python unit tests for JS/HTML changes. Run `uv run pytest tests/ -v` after each HTML task to catch any Python regressions.

**Files:**
- Modify: `ui/index.html`

- [ ] **Step 1: Add CSS for #pip-player-btn**

In `ui/index.html`, locate the existing `#fullscreen-player-btn:hover` CSS block. After it (before `#close-player-btn`), add:

Find:
```css
#fullscreen-player-btn:hover {
  border-color: rgba(255,255,255,0.15); color: var(--text-primary);
}
#close-player-btn {
```

Replace with:
```css
#fullscreen-player-btn:hover {
  border-color: rgba(255,255,255,0.15); color: var(--text-primary);
}
#pip-player-btn {
  height: 26px; padding: 0 10px;
  background: var(--bg-elevated); color: var(--text-secondary);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-sm);
  font-size: 12px; cursor: pointer; font-family: inherit;
  transition: all 0.12s ease;
}
#pip-player-btn:hover {
  border-color: rgba(255,255,255,0.15); color: var(--text-primary);
}
#close-player-btn {
```

- [ ] **Step 2: Add .ms-pip-btn to multistream slot button CSS**

Find:
```css
.ms-audio-btn, .ms-chat-sw-btn, .ms-fullscreen-btn, .ms-remove-btn {
```

Replace with:
```css
.ms-audio-btn, .ms-chat-sw-btn, .ms-fullscreen-btn, .ms-pip-btn, .ms-remove-btn {
```

Find:
```css
.ms-audio-btn:hover, .ms-chat-sw-btn:hover, .ms-fullscreen-btn:hover, .ms-remove-btn:hover {
```

Replace with:
```css
.ms-audio-btn:hover, .ms-chat-sw-btn:hover, .ms-fullscreen-btn:hover, .ms-pip-btn:hover, .ms-remove-btn:hover {
```

- [ ] **Step 3: Add #pip-player-btn to player header**

Find:
```html
          <div id="player-header-actions">
            <button id="toggle-chat-btn" title="Toggle Chat (C)">&#128172;</button>
            <button id="fullscreen-player-btn" title="Fullscreen (F)">&#9974;</button>
            <button id="close-player-btn">&#10005; Close</button>
          </div>
```

Replace with:
```html
          <div id="player-header-actions">
            <button id="toggle-chat-btn" title="Toggle Chat (C)">&#128172;</button>
            <button id="pip-player-btn" title="Picture-in-Picture (P)" style="display:none;">&#10697; PiP</button>
            <button id="fullscreen-player-btn" title="Fullscreen (F)">&#9974;</button>
            <button id="close-player-btn">&#10005; Close</button>
          </div>
```

- [ ] **Step 4: Add ms-pip-btn to multistream slot 0**

Find (slot 0 controls):
```html
                  <div class="ms-slot-controls">
                    <button class="ms-audio-btn" data-slot="0" title="Focus audio">&#128266;</button>
                    <button class="ms-chat-sw-btn" data-slot="0" title="Switch chat">&#128172;</button>
                    <button class="ms-fullscreen-btn" data-slot="0" title="Fullscreen (double-click)">&#9974;</button>
                    <button class="ms-remove-btn" data-slot="0" title="Remove">&times;</button>
                  </div>
```

Replace with:
```html
                  <div class="ms-slot-controls">
                    <button class="ms-audio-btn" data-slot="0" title="Focus audio">&#128266;</button>
                    <button class="ms-chat-sw-btn" data-slot="0" title="Switch chat">&#128172;</button>
                    <button class="ms-fullscreen-btn" data-slot="0" title="Fullscreen (double-click)">&#9974;</button>
                    <button class="ms-pip-btn" data-slot="0" title="Picture-in-Picture">&#10697;</button>
                    <button class="ms-remove-btn" data-slot="0" title="Remove">&times;</button>
                  </div>
```

- [ ] **Step 5: Add ms-pip-btn to multistream slots 1, 2, 3**

Repeat the same pattern for slots 1, 2, and 3 (same structure, `data-slot="1"`, `data-slot="2"`, `data-slot="3"`). Each slot's `ms-slot-controls` block needs a `ms-pip-btn` added between `ms-fullscreen-btn` and `ms-remove-btn`.

For slot 1, find:
```html
                    <button class="ms-fullscreen-btn" data-slot="1" title="Fullscreen (double-click)">&#9974;</button>
                    <button class="ms-remove-btn" data-slot="1" title="Remove">&times;</button>
```
Replace with:
```html
                    <button class="ms-fullscreen-btn" data-slot="1" title="Fullscreen (double-click)">&#9974;</button>
                    <button class="ms-pip-btn" data-slot="1" title="Picture-in-Picture">&#10697;</button>
                    <button class="ms-remove-btn" data-slot="1" title="Remove">&times;</button>
```

For slot 2, find:
```html
                    <button class="ms-fullscreen-btn" data-slot="2" title="Fullscreen (double-click)">&#9974;</button>
                    <button class="ms-remove-btn" data-slot="2" title="Remove">&times;</button>
```
Replace with:
```html
                    <button class="ms-fullscreen-btn" data-slot="2" title="Fullscreen (double-click)">&#9974;</button>
                    <button class="ms-pip-btn" data-slot="2" title="Picture-in-Picture">&#10697;</button>
                    <button class="ms-remove-btn" data-slot="2" title="Remove">&times;</button>
```

For slot 3, find:
```html
                    <button class="ms-fullscreen-btn" data-slot="3" title="Fullscreen (double-click)">&#9974;</button>
                    <button class="ms-remove-btn" data-slot="3" title="Remove">&times;</button>
```
Replace with:
```html
                    <button class="ms-fullscreen-btn" data-slot="3" title="Fullscreen (double-click)">&#9974;</button>
                    <button class="ms-pip-btn" data-slot="3" title="Picture-in-Picture">&#10697;</button>
                    <button class="ms-remove-btn" data-slot="3" title="Remove">&times;</button>
```

- [ ] **Step 6: Wire #pip-player-btn click handler in DOMContentLoaded**

Find in the DOMContentLoaded block:
```javascript
  document.getElementById('fullscreen-player-btn').addEventListener('click', toggleVideoFullscreen);
  document.getElementById('stream-video').addEventListener('dblclick', toggleVideoFullscreen);
```

Replace with:
```javascript
  document.getElementById('fullscreen-player-btn').addEventListener('click', toggleVideoFullscreen);
  document.getElementById('stream-video').addEventListener('dblclick', toggleVideoFullscreen);
  document.getElementById('pip-player-btn').addEventListener('click', function() {
    togglePiP(document.getElementById('stream-video'));
  });
```

- [ ] **Step 7: Wire .ms-pip-btn click handler in multistream grid listener**

Find the multistream grid click handler section:
```javascript
    var fsBtn = e.target.closest('.ms-fullscreen-btn');
    if (fsBtn) { toggleMsSlotFullscreen(parseInt(fsBtn.dataset.slot, 10)); return; }
    var removeBtn = e.target.closest('.ms-remove-btn');
```

Replace with:
```javascript
    var fsBtn = e.target.closest('.ms-fullscreen-btn');
    if (fsBtn) { toggleMsSlotFullscreen(parseInt(fsBtn.dataset.slot, 10)); return; }
    var pipBtn = e.target.closest('.ms-pip-btn');
    if (pipBtn) {
      var slot = parseInt(pipBtn.dataset.slot, 10);
      var slotEl = document.querySelector('.ms-slot[data-slot-idx="' + slot + '"]');
      if (slotEl) togglePiP(slotEl.querySelector('.ms-video'));
      return;
    }
    var removeBtn = e.target.closest('.ms-remove-btn');
```

- [ ] **Step 8: Add togglePiP() function**

Find the `toggleVideoFullscreen` function:
```javascript
function toggleVideoFullscreen() {
```

Just before it, add:

```javascript
function togglePiP(video) {
  if (!video) return;
  // Webkit path — most reliable in WKWebView on macOS
  if (typeof video.webkitSupportsPresentationMode === 'function' &&
      video.webkitSupportsPresentationMode('picture-in-picture')) {
    var next = video.webkitPresentationMode === 'picture-in-picture' ? 'inline' : 'picture-in-picture';
    video.webkitSetPresentationMode(next);
    return;
  }
  // W3C fallback
  if (document.pictureInPictureEnabled) {
    if (document.pictureInPictureElement === video) {
      document.exitPictureInPicture().catch(function() {});
    } else {
      video.requestPictureInPicture().catch(function() {});
    }
  }
}

```

- [ ] **Step 9: Run Python tests to confirm no regressions**

```bash
uv run pytest tests/ -v
```

Expected: 303 passed

- [ ] **Step 10: Commit**

```bash
git add ui/index.html
git commit -m "feat(pip): add PiP button to player header and multistream slots"
```

---

### Task 4: Extended hotkeys — state.shortcuts + helpers + handleKeydown

**Files:**
- Modify: `ui/index.html`

- [ ] **Step 1: Add DEFAULT_SHORTCUTS and SHORTCUT_LABELS constants before state**

Find the line that starts `const state = {` in the `<script>` section. Just before it, add:

```javascript
/* ── Keyboard shortcuts ─────────────────────────────────── */
const DEFAULT_SHORTCUTS = {
  refresh:      'r',
  watch:        ' ',
  fullscreen:   'f',
  toggle_chat:  'c',
  mute:         'm',
  pip:          'p',
  volume_up:    'ArrowUp',
  volume_down:  'ArrowDown',
  next_stream:  'ArrowRight',
  prev_stream:  'ArrowLeft',
};

const SHORTCUT_LABELS = {
  refresh:      'Refresh streams',
  watch:        'Watch selected stream',
  fullscreen:   'Toggle fullscreen',
  toggle_chat:  'Toggle chat panel',
  mute:         'Toggle mute',
  pip:          'Toggle Picture-in-Picture',
  volume_up:    'Volume up (+10%)',
  volume_down:  'Volume down (-10%)',
  next_stream:  'Select next stream',
  prev_stream:  'Select previous stream',
};

```

- [ ] **Step 2: Add shortcuts and pipEnabled fields to state**

Find the end of the `state` object — the `channelTabs` block followed by `};`:
```javascript
  channelTabs: {
    active: 'live',
    vods: createChannelMediaState(),
    clips: createChannelMediaState(),
  },
};
```

Replace with:
```javascript
  channelTabs: {
    active: 'live',
    vods: createChannelMediaState(),
    clips: createChannelMediaState(),
  },
  shortcuts: Object.assign({}, DEFAULT_SHORTCUTS),
  pipEnabled: false,
};
```

- [ ] **Step 3: Load shortcuts and pip_enabled in pywebviewready**

Find the pywebviewready handler content:
```javascript
  setTimeout(function() {
    if (!api) return;
    const config = api.get_config();
    state.kickScopes = (config && config.kick_scopes) || '';
    if (config && config.current_user) {
      showUserProfile(config.current_user);
    }
    if (config && config.kick_user) {
      showKickProfile(config.kick_user);
    }
  }, 100);
```

Replace with:
```javascript
  setTimeout(function() {
    if (!api) return;
    const config = api.get_config();
    state.kickScopes = (config && config.kick_scopes) || '';
    if (config && config.current_user) {
      showUserProfile(config.current_user);
    }
    if (config && config.kick_user) {
      showKickProfile(config.kick_user);
    }
    if (config && config.keyboard_shortcuts) {
      state.shortcuts = Object.assign({}, DEFAULT_SHORTCUTS, config.keyboard_shortcuts);
    }
    state.pipEnabled = !!(config && config.pip_enabled);
    document.getElementById('pip-player-btn').style.display = state.pipEnabled ? '' : 'none';
  }, 100);
```

- [ ] **Step 4: Add getActiveVideo(), adjustVolume(), toggleMute(), cycleStream() helpers**

Find the `togglePiP` function we added in Task 3. Just before it, add these four helpers:

```javascript
function getActiveVideo() {
  if (document.getElementById('player-view').classList.contains('active')) {
    return document.getElementById('stream-video');
  }
  if (multiState.open && multiState.audioFocus >= 0) {
    var slotEl = document.querySelector('.ms-slot[data-slot-idx="' + multiState.audioFocus + '"]');
    return slotEl ? slotEl.querySelector('.ms-video') : null;
  }
  return null;
}

function adjustVolume(delta) {
  var video = getActiveVideo();
  if (!video) return;
  video.muted = false;
  video.volume = Math.max(0, Math.min(1, video.volume + delta));
  setStatus('Volume: ' + Math.round(video.volume * 100) + '%', 'info');
}

function toggleMute() {
  var video = getActiveVideo();
  if (!video) return;
  video.muted = !video.muted;
  setStatus(video.muted ? 'Muted' : 'Unmuted', 'info');
}

function cycleStream(dir) {
  var streams = getFilteredSortedStreams();
  if (streams.length === 0) return;
  var idx = streams.findIndex(function(s) { return s.login === state.selectedChannel; });
  idx = (idx + dir + streams.length) % streams.length;
  selectChannel(streams[idx].login);
}

```

- [ ] **Step 5: Rewrite handleKeydown to use state.shortcuts**

Find the existing `handleKeydown` function:

```javascript
function handleKeydown(e) {
  var tag = document.activeElement ? document.activeElement.tagName : '';
  var inInput = tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA';

  if (e.key === 'Escape') {
    if (document.getElementById('settings-overlay').classList.contains('visible')) {
      closeSettings(); return;
    }
    if (multiState.open) { closeMultistreamView(); return; }
    if (document.getElementById('context-menu').style.display === 'block') {
      document.getElementById('context-menu').style.display = 'none'; return;
    }
    if (document.getElementById('search-dropdown').style.display === 'block') {
      document.getElementById('search-dropdown').style.display = 'none'; return;
    }
    state.selectedChannel = null;
    document.querySelectorAll('.stream-card').forEach(function(c) { c.classList.remove('selected'); });
    document.querySelectorAll('.channel-item').forEach(function(c) { c.classList.remove('selected'); });
    document.getElementById('watch-btn').classList.remove('active');
    setStatus('', 'info');
    return;
  }

  if (inInput) return;

  if (e.key === 'r' || e.key === 'F5' || (e.metaKey && e.key === 'r')) {
    e.preventDefault(); doRefresh();
  } else if (e.key === ' ' || e.key === 'Enter') {
    e.preventDefault(); doWatch();
  } else if (e.key === 'f' && document.getElementById('player-view').classList.contains('active')) {
    e.preventDefault(); toggleVideoFullscreen();
  } else if (e.key === 'c' && document.getElementById('player-view').classList.contains('active')) {
    e.preventDefault(); toggleChatPanel();
  } else if (e.metaKey && e.key === ',') {
    e.preventDefault(); openSettings();
  }
}
```

Replace the entire function with:

```javascript
function handleKeydown(e) {
  var tag = document.activeElement ? document.activeElement.tagName : '';
  var inInput = tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA';
  var sc = state.shortcuts;

  if (e.key === 'Escape') {
    if (document.getElementById('settings-overlay').classList.contains('visible')) {
      closeSettings(); return;
    }
    if (multiState.open) { closeMultistreamView(); return; }
    if (document.getElementById('context-menu').style.display === 'block') {
      document.getElementById('context-menu').style.display = 'none'; return;
    }
    if (document.getElementById('search-dropdown').style.display === 'block') {
      document.getElementById('search-dropdown').style.display = 'none'; return;
    }
    state.selectedChannel = null;
    document.querySelectorAll('.stream-card').forEach(function(c) { c.classList.remove('selected'); });
    document.querySelectorAll('.channel-item').forEach(function(c) { c.classList.remove('selected'); });
    document.getElementById('watch-btn').classList.remove('active');
    setStatus('', 'info');
    return;
  }

  if (inInput) return;

  var inPlayer = document.getElementById('player-view').classList.contains('active');
  var inMulti = multiState.open;

  // Modifier-based shortcuts (not rebindable)
  if (e.key === 'F5' || (e.metaKey && e.key === 'r')) {
    e.preventDefault(); doRefresh(); return;
  }
  if (e.metaKey && e.key === ',') {
    e.preventDefault(); openSettings(); return;
  }

  // Single-key shortcuts — skip if any modifier is held
  if (e.metaKey || e.ctrlKey || e.altKey) return;

  if (e.key === sc.refresh) { e.preventDefault(); doRefresh(); return; }
  if (e.key === sc.watch || e.key === 'Enter') { e.preventDefault(); doWatch(); return; }

  if (inPlayer) {
    if (e.key === sc.fullscreen) { e.preventDefault(); toggleVideoFullscreen(); return; }
    if (e.key === sc.toggle_chat) { e.preventDefault(); toggleChatPanel(); return; }
    if (e.key === sc.pip) { e.preventDefault(); togglePiP(document.getElementById('stream-video')); return; }
  }

  if (inPlayer || inMulti) {
    if (e.key === sc.volume_up)   { e.preventDefault(); adjustVolume(0.1);  return; }
    if (e.key === sc.volume_down) { e.preventDefault(); adjustVolume(-0.1); return; }
    if (e.key === sc.mute)        { e.preventDefault(); toggleMute();        return; }
  }

  if (!inPlayer && !inMulti) {
    if (e.key === sc.next_stream) { e.preventDefault(); cycleStream(1);  return; }
    if (e.key === sc.prev_stream) { e.preventDefault(); cycleStream(-1); return; }
  }
}
```

- [ ] **Step 6: Run Python tests to confirm no regressions**

```bash
uv run pytest tests/ -v
```

Expected: 303 passed

- [ ] **Step 7: Commit**

```bash
git add ui/index.html
git commit -m "feat(hotkeys): add volume/mute/pip/cycle-stream shortcuts using configurable state.shortcuts"
```

---

### Task 5: Hotkeys settings tab — HTML + key-capture UI + openSettings/saveSettings

**Files:**
- Modify: `ui/index.html`

- [ ] **Step 1: Add "Hotkeys" tab button to settings**

Find the settings tabs HTML:
```html
    <div class="settings-tabs">
      <button class="settings-tab active" data-tab="general">General</button>
      <button class="settings-tab" data-tab="twitch">Twitch</button>
      <button class="settings-tab" data-tab="kick">Kick</button>
      <button class="settings-tab" data-tab="youtube">YouTube</button>
    </div>
```

Replace with:
```html
    <div class="settings-tabs">
      <button class="settings-tab active" data-tab="general">General</button>
      <button class="settings-tab" data-tab="twitch">Twitch</button>
      <button class="settings-tab" data-tab="kick">Kick</button>
      <button class="settings-tab" data-tab="youtube">YouTube</button>
      <button class="settings-tab" data-tab="hotkeys">Hotkeys</button>
    </div>
```

- [ ] **Step 2: Add #settings-panel-hotkeys HTML**

Find the closing tag of the YouTube settings panel. Look for the line right after the YouTube panel ends and before the `</div>` that closes the settings modal body. Insert the Hotkeys panel between the YouTube panel closing tag and whatever follows.

Locate:
```html
        <a id="yt-logout-btn" style="font-size:12px;color:var(--text-muted);cursor:pointer;text-decoration:none;">Logout from YouTube</a>
      </div>
    </div>
```

(This is the end of the YouTube panel.) After it, add:

```html
    <!-- Hotkeys panel -->
    <div class="settings-panel" id="settings-panel-hotkeys">
      <div class="setting-group">
        <label>Keyboard Shortcuts</label>
        <p style="font-size:11px;color:var(--text-muted);margin:4px 0 10px;">Click a key badge to rebind it. Press Esc to cancel.</p>
        <table id="hotkeys-table" style="width:100%;border-collapse:collapse;"></table>
        <button id="reset-shortcuts-btn" style="margin-top:10px;font-size:12px;padding:4px 10px;background:var(--bg-elevated);color:var(--text-secondary);border:1px solid var(--bg-border);border-radius:var(--radius-sm);cursor:pointer;">Reset to Defaults</button>
      </div>
      <div class="setting-group" style="margin-top:4px;">
        <label>Picture-in-Picture</label>
        <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;">
          <input type="checkbox" id="s-pip-enabled"> Show PiP button in player header
        </label>
      </div>
    </div>
```

- [ ] **Step 3: Add _rebindAction variable and capture-phase keydown listener**

Find the line with the other top-level `let` / `var` declarations near the top of the script (near `let ctxChannel = null`):

```javascript
let api = null;
let ctxChannel = null;
let channelViewSource = 'grid';
let channelProfile = null;
let sidebarResizeFrame = null;
```

Replace with:
```javascript
let api = null;
let ctxChannel = null;
let channelViewSource = 'grid';
let channelProfile = null;
let sidebarResizeFrame = null;
let _rebindAction = null;
```

Then, find the `document.addEventListener('keydown', handleKeydown);` line in the DOMContentLoaded block. After it, add a **capture-phase** listener for rebinding (must be placed OUTSIDE of DOMContentLoaded so it fires before `handleKeydown`):

Actually, add the capture-phase listener at module level (after the variable declarations), not inside DOMContentLoaded:

Find:
```javascript
let _rebindAction = null;
```

After it add:

```javascript
// Capture-phase listener intercepts keydowns during shortcut rebinding
document.addEventListener('keydown', function(e) {
  if (!_rebindAction) return;
  e.preventDefault();
  e.stopPropagation();
  if (e.key === 'Escape') {
    _rebindAction = null;
    renderHotkeysSettings();
    return;
  }
  state.shortcuts[_rebindAction] = e.key;
  _rebindAction = null;
  renderHotkeysSettings();
}, true);
```

- [ ] **Step 4: Wire #reset-shortcuts-btn in DOMContentLoaded**

In the DOMContentLoaded block, find where `#save-btn` is wired:
```javascript
  document.getElementById('save-btn').addEventListener('click', saveSettings);
```

After it, add:
```javascript
  document.getElementById('reset-shortcuts-btn').addEventListener('click', function() {
    state.shortcuts = Object.assign({}, DEFAULT_SHORTCUTS);
    renderHotkeysSettings();
  });
```

- [ ] **Step 5: Add renderHotkeysSettings(), formatKeyName(), startRebind() functions**

Find the `/* ── Settings ───────────────────────────────────────────── */` comment before `openSettings()`. Just before it, add:

```javascript
/* ── Hotkeys settings helpers ───────────────────────────── */
function formatKeyName(key) {
  if (key === ' ')          return 'Space';
  if (key === 'ArrowUp')    return '↑';
  if (key === 'ArrowDown')  return '↓';
  if (key === 'ArrowLeft')  return '←';
  if (key === 'ArrowRight') return '→';
  if (key === 'Enter')      return '↵';
  if (key === 'Backspace')  return '⌫';
  if (key === 'Tab')        return '⇥';
  return key;
}

function startRebind(action) {
  _rebindAction = action;
  renderHotkeysSettings();
}

function renderHotkeysSettings() {
  var tbl = document.getElementById('hotkeys-table');
  if (!tbl) return;
  tbl.innerHTML = '';
  Object.keys(SHORTCUT_LABELS).forEach(function(action) {
    var key = state.shortcuts[action] !== undefined ? state.shortcuts[action] : DEFAULT_SHORTCUTS[action];
    var isCapturing = _rebindAction === action;
    var tr = document.createElement('tr');
    tr.style.borderBottom = '1px solid rgba(255,255,255,0.05)';

    var labelTd = document.createElement('td');
    labelTd.style.cssText = 'padding:7px 0;font-size:12px;color:var(--text-secondary);';
    labelTd.textContent = SHORTCUT_LABELS[action];

    var keyTd = document.createElement('td');
    keyTd.style.cssText = 'padding:7px 0;text-align:right;';

    var kbd = document.createElement('kbd');
    kbd.style.cssText = [
      'display:inline-block',
      'padding:2px 8px',
      'border-radius:4px',
      'font-size:11px',
      'font-family:inherit',
      'cursor:pointer',
      'transition:all 0.1s',
      isCapturing
        ? 'background:var(--accent);color:#000;border:1px solid var(--accent);'
        : 'background:var(--bg-elevated);color:var(--text-primary);border:1px solid rgba(255,255,255,0.15);',
    ].join(';');
    kbd.textContent = isCapturing ? 'Press key…' : formatKeyName(key);
    kbd.title = isCapturing ? 'Press Esc to cancel' : 'Click to rebind';
    kbd.addEventListener('click', function() { startRebind(action); });

    keyTd.appendChild(kbd);
    tr.appendChild(labelTd);
    tr.appendChild(keyTd);
    tbl.appendChild(tr);
  });
}

```

- [ ] **Step 6: Update openSettings() to load and render hotkeys**

Find in `openSettings()` the block that sets the YouTube quota display:
```javascript
  document.getElementById('yt-test-result').style.display = 'none';
  // Reset to General tab
```

Replace with:
```javascript
  document.getElementById('yt-test-result').style.display = 'none';
  // Hotkeys tab
  if (config.keyboard_shortcuts) {
    state.shortcuts = Object.assign({}, DEFAULT_SHORTCUTS, config.keyboard_shortcuts);
  }
  document.getElementById('s-pip-enabled').checked = !!config.pip_enabled;
  renderHotkeysSettings();
  // Reset to General tab
```

- [ ] **Step 7: Update saveSettings() to include shortcuts and pip_enabled**

Find the current `saveSettings()` function body:
```javascript
function saveSettings() {
  var data = {
    client_id: document.getElementById('s-client-id').value.trim(),
    client_secret: document.getElementById('s-client-secret').value.trim(),
    streamlink_path: document.getElementById('s-streamlink').value.trim(),
    iina_path: document.getElementById('s-iina').value.trim(),
    refresh_interval: parseInt(document.getElementById('s-interval').value, 10),
    kick_client_id: document.getElementById('s-kick-client-id').value.trim(),
    kick_client_secret: document.getElementById('s-kick-client-secret').value.trim(),
    youtube_api_key: document.getElementById('yt-api-key').value.trim(),
    youtube_client_id: document.getElementById('yt-client-id').value.trim(),
    youtube_client_secret: document.getElementById('yt-client-secret').value.trim(),
  };
  if (api) api.save_settings(JSON.stringify(data));
}
```

Replace with:
```javascript
function saveSettings() {
  var pipEnabled = document.getElementById('s-pip-enabled').checked;
  var data = {
    client_id: document.getElementById('s-client-id').value.trim(),
    client_secret: document.getElementById('s-client-secret').value.trim(),
    streamlink_path: document.getElementById('s-streamlink').value.trim(),
    iina_path: document.getElementById('s-iina').value.trim(),
    refresh_interval: parseInt(document.getElementById('s-interval').value, 10),
    kick_client_id: document.getElementById('s-kick-client-id').value.trim(),
    kick_client_secret: document.getElementById('s-kick-client-secret').value.trim(),
    youtube_api_key: document.getElementById('yt-api-key').value.trim(),
    youtube_client_id: document.getElementById('yt-client-id').value.trim(),
    youtube_client_secret: document.getElementById('yt-client-secret').value.trim(),
    keyboard_shortcuts: Object.assign({}, state.shortcuts),
    pip_enabled: pipEnabled,
  };
  // Apply pip button visibility immediately
  state.pipEnabled = pipEnabled;
  document.getElementById('pip-player-btn').style.display = pipEnabled ? '' : 'none';
  if (api) api.save_settings(JSON.stringify(data));
}
```

- [ ] **Step 8: Run Python tests to confirm no regressions**

```bash
uv run pytest tests/ -v
```

Expected: 303 passed

- [ ] **Step 9: Commit**

```bash
git add ui/index.html
git commit -m "feat(hotkeys): add Hotkeys settings tab with click-to-rebind UI and pip_enabled toggle"
```

---

## Self-Review

### Spec Coverage Check

| Spec requirement | Covered by |
|---|---|
| PiP via `video.requestPictureInPicture()` or Webkit PiP | Task 3 Step 8 — `togglePiP()` tries webkit first, W3C fallback |
| PiP for main player | Task 3 Steps 3, 6 — `#pip-player-btn`, wired in DOMContentLoaded |
| PiP for multistream slots | Task 3 Steps 4, 5, 7 — `ms-pip-btn` on all 4 slots + click handler |
| Extended hotkeys: volume | Task 4 Steps 4, 5 — `adjustVolume(±0.1)` bound to `volume_up/down` shortcuts |
| Extended hotkeys: mute | Task 4 Steps 4, 5 — `toggleMute()` bound to `mute` shortcut |
| Extended hotkeys: next/prev stream | Task 4 Steps 4, 5 — `cycleStream(±1)` bound to `next/prev_stream` shortcuts |
| Extended hotkeys: toggle chat | Task 4 Step 5 — `toggle_chat` in new `handleKeydown` |
| Extended hotkeys: toggle PiP | Task 4 Step 5 — `pip` key in new `handleKeydown` |
| Configurable keyboard shortcuts in settings | Task 5 — full Hotkeys settings tab with key-capture UI |
| `pip_enabled` config flag | Tasks 1–5 — stored in config, surfaced as checkbox, applied to pip button visibility |

### Placeholder Scan

No TBDs, no "implement later", no "similar to Task N" without full code shown. All steps contain exact code.

### Type Consistency

- `DEFAULT_SHORTCUTS` defined in Task 4 Step 1 → used in Task 4 Steps 2, 3, 5 and Task 5 Steps 5, 6, 7 ✓
- `SHORTCUT_LABELS` defined in Task 4 Step 1 → used in Task 5 Step 5 (`renderHotkeysSettings`) ✓
- `state.shortcuts` added in Task 4 Step 2 → read in Task 4 Step 5 (`handleKeydown`) and Task 5 Steps 5, 6, 7 ✓
- `state.pipEnabled` added in Task 4 Step 2 → set in Task 4 Step 3 (pywebviewready), Task 5 Step 7 (saveSettings) ✓
- `_rebindAction` declared in Task 5 Step 3 → used in Task 5 Steps 3, 4, 5 ✓
- `togglePiP(video)` defined in Task 3 Step 8 → called in Task 3 Steps 6, 7 and Task 4 Step 5 ✓
- `adjustVolume(delta)`, `toggleMute()`, `cycleStream(dir)`, `getActiveVideo()` defined in Task 4 Step 4 → called in Task 4 Step 5 ✓
- `renderHotkeysSettings()`, `formatKeyName()`, `startRebind()` defined in Task 5 Step 5 → called in Task 5 Steps 4, 6 and capture listener in Step 3 ✓
- `keyboard_shortcuts` key in storage.py → matches JS `state.shortcuts` / `DEFAULT_SHORTCUTS` key names (both use `snake_case`) ✓
- `pip_enabled` key in storage.py → `config.pip_enabled` in JS / `s-pip-enabled` checkbox ✓
