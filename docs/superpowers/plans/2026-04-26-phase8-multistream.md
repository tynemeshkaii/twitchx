# Phase 8: Multi-stream Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a multistream view that plays 2–4 simultaneous Twitch/Kick HLS streams in a 2×2 grid, with switchable audio focus, per-slot chat that routes to a shared chat panel, and cross-platform mixing — all inside the existing pywebview stack with no new dependencies.

**Architecture:** A new `#multistream-view` section in `ui/index.html` holds a 2×2 CSS grid of `<video>` elements (WKWebView/macOS WebKit supports HLS natively via AVFoundation). Python exposes `add_multi_slot(slot_idx, channel, platform, quality)` which resolves each HLS URL in a background thread (same `resolve_hls_url` + threading pattern as `watch_direct`) and emits `window.onMultiSlotReady`. Chat routing is extended: `window.onChatMessage` / `window.onChatStatus` check `multiState.open` and target either `#chat-messages` (player-view) or `#ms-chat-messages` (multistream-view). Entry point: context menu "Add to Multi-stream" on any Twitch/Kick stream card in the main grid.

**Tech Stack:** Existing pywebview + vanilla JS + macOS WebKit HLS + Python threading + `resolve_hls_url` + existing `start_chat` / `stop_chat` bridge methods.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `ui/api.py` | `add_multi_slot`, `stop_multi` bridge methods |
| Modify | `ui/index.html` | Multistream HTML section, CSS, JS state + functions, chat routing, context menu wiring |
| Modify | `tests/test_api.py` | `TestAddMultiSlot` unit tests |

---

## Task 1: Failing tests for `add_multi_slot` and `stop_multi`

**Files:**
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Append a new test class at the bottom of `tests/test_api.py`:

```python
class TestAddMultiSlot:
    def test_success_emits_onMultiSlotReady(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_storage(monkeypatch, tmp_path)
        api = TwitchXApi()
        emitted: list[str] = []
        monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
        monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))
        monkeypatch.setattr(
            "ui.api.resolve_hls_url",
            lambda ch, q, sl, platform: ("https://hls.example.com/s.m3u8", ""),
        )

        api.add_multi_slot(0, "xqc", "twitch", "best")

        assert len(emitted) == 1
        assert "onMultiSlotReady" in emitted[0]
        payload = json.loads(emitted[0].split("(", 1)[1].rstrip(")"))
        assert payload["slot_idx"] == 0
        assert payload["url"] == "https://hls.example.com/s.m3u8"
        assert payload["channel"] == "xqc"
        assert payload["platform"] == "twitch"
        assert "error" not in payload

    def test_resolve_error_emits_error_payload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_storage(monkeypatch, tmp_path)
        api = TwitchXApi()
        emitted: list[str] = []
        monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
        monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))
        monkeypatch.setattr(
            "ui.api.resolve_hls_url",
            lambda ch, q, sl, platform: (None, "streamlink not found"),
        )

        api.add_multi_slot(2, "ninja", "twitch", "720p")

        assert len(emitted) == 1
        payload = json.loads(emitted[0].split("(", 1)[1].rstrip(")"))
        assert payload["slot_idx"] == 2
        assert "error" in payload
        assert "url" not in payload

    def test_out_of_range_slot_idx_is_noop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_storage(monkeypatch, tmp_path)
        api = TwitchXApi()
        emitted: list[str] = []
        monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
        monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

        api.add_multi_slot(4, "xqc", "twitch", "best")

        assert emitted == []

    def test_negative_slot_idx_is_noop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_storage(monkeypatch, tmp_path)
        api = TwitchXApi()
        emitted: list[str] = []
        monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
        monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

        api.add_multi_slot(-1, "xqc", "twitch", "best")

        assert emitted == []

    def test_title_populated_from_live_streams_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_storage(monkeypatch, tmp_path)
        api = TwitchXApi()
        api._live_streams = [
            {"login": "xqc", "platform": "twitch", "title": "Gaming Session"}
        ]
        emitted: list[str] = []
        monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
        monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))
        monkeypatch.setattr(
            "ui.api.resolve_hls_url",
            lambda ch, q, sl, platform: ("https://hls.example.com/s.m3u8", ""),
        )

        api.add_multi_slot(0, "xqc", "twitch", "best")

        payload = json.loads(emitted[0].split("(", 1)[1].rstrip(")"))
        assert payload["title"] == "Gaming Session"

    def test_kick_slot_passes_kick_platform_to_resolver(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_storage(monkeypatch, tmp_path)
        api = TwitchXApi()
        emitted: list[str] = []
        captured: dict[str, str] = {}
        monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
        monkeypatch.setattr(api, "_eval_js", lambda code: emitted.append(code))

        def fake_resolve(
            ch: str, q: str, sl: str, platform: str
        ) -> tuple[str, str]:
            captured["platform"] = platform
            return "https://hls.example.com/s.m3u8", ""

        monkeypatch.setattr("ui.api.resolve_hls_url", fake_resolve)

        api.add_multi_slot(1, "xqcow", "kick", "best")

        assert captured["platform"] == "kick"
        payload = json.loads(emitted[0].split("(", 1)[1].rstrip(")"))
        assert payload["platform"] == "kick"
```

- [ ] **Step 2: Run to verify failure**

```
uv run pytest tests/test_api.py::TestAddMultiSlot -v
```

Expected: `AttributeError: 'TwitchXApi' object has no attribute 'add_multi_slot'`

---

## Task 2: Implement `add_multi_slot` and `stop_multi`

**Files:**
- Modify: `ui/api.py`

- [ ] **Step 1: Add the two methods after `stop_player`**

Find `def stop_player(self)` in `ui/api.py` (around line 1897). Insert immediately after its closing line:

```python
def add_multi_slot(
    self, slot_idx: int, channel: str, platform: str, quality: str
) -> None:
    """Resolve HLS URL for one multistream slot. Emits window.onMultiSlotReady."""
    if not 0 <= slot_idx <= 3:
        return
    channel_lower = channel.lower() if platform != "youtube" else channel
    title = ""
    for s in self._live_streams:
        if (
            self._stream_platform(s) == platform
            and self._stream_login(s) == channel_lower
        ):
            title = s.get("title", "")
            break

    def do_resolve() -> None:
        cfg = load_config()
        settings = get_settings(cfg)
        hls_url, err = resolve_hls_url(
            channel,
            quality,
            settings.get("streamlink_path", "streamlink"),
            platform=platform,
        )
        payload: dict[str, Any] = {
            "slot_idx": slot_idx,
            "channel": channel,
            "platform": platform,
            "title": title,
        }
        if hls_url:
            payload["url"] = hls_url
        else:
            payload["error"] = err or "Could not resolve stream URL"
        self._eval_js(f"window.onMultiSlotReady({json.dumps(payload)})")

    self._run_in_thread(do_resolve)

def stop_multi(self) -> None:
    """Stop chat for all multistream slots."""
    self.stop_chat()
```

- [ ] **Step 2: Run the new tests**

```
uv run pytest tests/test_api.py::TestAddMultiSlot -v
```

Expected: 6 passed.

- [ ] **Step 3: Run full test suite**

```
make test
```

Expected: all existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add ui/api.py tests/test_api.py
git commit -m "feat(multistream): add_multi_slot + stop_multi bridge methods with tests"
```

---

## Task 3: Multistream HTML skeleton and CSS

**Files:**
- Modify: `ui/index.html`

- [ ] **Step 1: Add CSS**

In the `<style>` block, find the `#channel-view` section and append after it:

```css
/* ── Multi-stream view ─────────────────────────────── */
#multistream-view {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  background: #000;
  z-index: 5;
}
#multistream-view.hidden { display: none; }

#multistream-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  background: var(--bg-surface);
  border-bottom: 1px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
}
#multistream-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  flex: 1;
}
#ms-toggle-chat-btn, #ms-close-btn {
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(255,255,255,0.1);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
}
#ms-toggle-chat-btn:hover, #ms-close-btn:hover {
  color: var(--text-primary);
  border-color: rgba(255,255,255,0.2);
}

#multistream-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

#multistream-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 2px;
  flex: 1;
  background: #111;
}

.ms-slot { position: relative; overflow: hidden; background: var(--bg-elevated); }

.ms-slot-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.ms-add-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 14px 20px;
  border: 2px dashed rgba(255,255,255,0.15);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-muted);
  font-size: 22px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}
.ms-add-btn span { font-size: 11px; }
.ms-add-btn:hover { border-color: var(--accent); color: var(--accent); }

.ms-add-form {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px;
  width: 100%;
  max-width: 220px;
  margin: auto;
}
.ms-add-form input, .ms-add-form select {
  width: 100%;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(255,255,255,0.12);
  background: var(--bg-base);
  color: var(--text-primary);
  font-size: 12px;
  font-family: inherit;
  box-sizing: border-box;
}
.ms-add-form input:focus, .ms-add-form select:focus {
  outline: none;
  border-color: rgba(255,159,10,0.35);
}
.ms-form-btns { display: flex; gap: 6px; width: 100%; }
.ms-confirm-btn {
  flex: 1;
  padding: 5px 0;
  border-radius: var(--radius-sm);
  border: none;
  background: var(--accent);
  color: #000;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}
.ms-cancel-btn {
  padding: 5px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(255,255,255,0.12);
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
}

.ms-slot-active { display: none; position: relative; height: 100%; }
.ms-video { width: 100%; height: 100%; object-fit: cover; display: block; }

.ms-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 12px;
  background: var(--bg-elevated);
}
.ms-error-msg {
  position: absolute;
  inset: 0;
  display: none;
  align-items: center;
  justify-content: center;
  color: var(--error-red);
  font-size: 11px;
  text-align: center;
  padding: 12px;
  background: var(--bg-elevated);
}

.ms-overlay {
  position: absolute;
  top: 0; left: 0; right: 0;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 6px 8px;
  background: linear-gradient(180deg, rgba(0,0,0,0.75) 0%, transparent 100%);
  opacity: 0;
  transition: opacity 0.15s;
}
.ms-slot:hover .ms-overlay,
.ms-slot.audio-focus .ms-overlay { opacity: 1; }

.ms-slot-info { display: flex; align-items: center; gap: 5px; }
.ms-platform-badge {
  font-size: 9px;
  font-weight: 800;
  padding: 1px 4px;
  border-radius: 3px;
  background: var(--accent);
  color: #000;
}
.ms-channel-name { font-size: 12px; font-weight: 600; color: #fff; }
.ms-slot-controls { display: flex; gap: 4px; }
.ms-audio-btn, .ms-chat-sw-btn, .ms-remove-btn {
  padding: 3px 5px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(255,255,255,0.2);
  background: rgba(0,0,0,0.5);
  color: #fff;
  font-size: 11px;
  cursor: pointer;
}
.ms-audio-btn:hover, .ms-chat-sw-btn:hover, .ms-remove-btn:hover {
  background: rgba(0,0,0,0.75);
}
.ms-slot.audio-focus { outline: 2px solid var(--accent); outline-offset: -2px; }
.ms-slot.chat-focus .ms-chat-sw-btn { color: var(--accent); border-color: var(--accent); }

#ms-chat-panel {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-surface);
  border-left: 1px solid rgba(255,255,255,0.06);
}
#ms-chat-panel.hidden { display: none; }
#ms-chat-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
}
#ms-chat-title { font-size: 12px; font-weight: 600; color: var(--text-primary); flex: 1; }
#ms-chat-status-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--text-muted);
  flex-shrink: 0;
}
#ms-chat-status-dot.connected { background: var(--live-green); }
#ms-chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 6px 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
#ms-chat-new-messages {
  display: none;
  text-align: center;
  padding: 4px;
  background: var(--accent);
  color: #000;
  font-size: 11px;
  cursor: pointer;
}
#ms-chat-new-messages.visible { display: block; }
#ms-chat-input-area {
  display: flex;
  gap: 6px;
  padding: 8px;
  border-top: 1px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
}
#ms-chat-input {
  flex: 1;
  padding: 5px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(255,255,255,0.12);
  background: var(--bg-elevated);
  color: var(--text-primary);
  font-size: 12px;
  font-family: inherit;
}
#ms-chat-input:focus { outline: none; border-color: rgba(255,159,10,0.35); }
#ms-chat-input:disabled { opacity: 0.45; cursor: not-allowed; }
#ms-chat-send-btn {
  padding: 5px 10px;
  border-radius: var(--radius-sm);
  border: none;
  background: var(--accent);
  color: #000;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}
#ms-chat-send-btn:disabled { opacity: 0.35; cursor: not-allowed; }
```

- [ ] **Step 2: Add the HTML section**

Find the closing `</div>` of `#channel-view` and insert `#multistream-view` directly after it. Each of the 4 slot cells (`data-slot-idx="0"` through `3`) is identical in structure — only the `data-slot` attribute values change:

```html
<!-- Multi-stream view -->
<div id="multistream-view" class="hidden">
  <div id="multistream-header">
    <span id="multistream-title">&#9706; Multi-stream</span>
    <button id="ms-toggle-chat-btn" onclick="toggleMsChat()">&#128172; Chat</button>
    <button id="ms-close-btn" onclick="closeMultistreamView()">&#10005; Close</button>
  </div>
  <div id="multistream-body">
    <div id="multistream-grid">

      <div class="ms-slot" data-slot-idx="0">
        <div class="ms-slot-empty">
          <button class="ms-add-btn" data-slot="0">+<span>Add Stream</span></button>
        </div>
        <div class="ms-add-form" style="display:none">
          <input class="ms-add-input" type="text" placeholder="channel name" maxlength="100" autocomplete="off" />
          <select class="ms-add-platform">
            <option value="twitch">Twitch</option>
            <option value="kick">Kick</option>
          </select>
          <div class="ms-form-btns">
            <button class="ms-confirm-btn" data-slot="0">Add</button>
            <button class="ms-cancel-btn" data-slot="0">Cancel</button>
          </div>
        </div>
        <div class="ms-slot-active">
          <video class="ms-video" autoplay muted playsinline></video>
          <div class="ms-loading">Loading stream...</div>
          <div class="ms-error-msg"></div>
          <div class="ms-overlay">
            <div class="ms-slot-info">
              <span class="ms-platform-badge"></span>
              <span class="ms-channel-name"></span>
            </div>
            <div class="ms-slot-controls">
              <button class="ms-audio-btn" data-slot="0" title="Focus audio">&#128266;</button>
              <button class="ms-chat-sw-btn" data-slot="0" title="Switch chat">&#128172;</button>
              <button class="ms-remove-btn" data-slot="0" title="Remove">&times;</button>
            </div>
          </div>
        </div>
      </div>

      <div class="ms-slot" data-slot-idx="1">
        <div class="ms-slot-empty">
          <button class="ms-add-btn" data-slot="1">+<span>Add Stream</span></button>
        </div>
        <div class="ms-add-form" style="display:none">
          <input class="ms-add-input" type="text" placeholder="channel name" maxlength="100" autocomplete="off" />
          <select class="ms-add-platform">
            <option value="twitch">Twitch</option>
            <option value="kick">Kick</option>
          </select>
          <div class="ms-form-btns">
            <button class="ms-confirm-btn" data-slot="1">Add</button>
            <button class="ms-cancel-btn" data-slot="1">Cancel</button>
          </div>
        </div>
        <div class="ms-slot-active">
          <video class="ms-video" autoplay muted playsinline></video>
          <div class="ms-loading">Loading stream...</div>
          <div class="ms-error-msg"></div>
          <div class="ms-overlay">
            <div class="ms-slot-info">
              <span class="ms-platform-badge"></span>
              <span class="ms-channel-name"></span>
            </div>
            <div class="ms-slot-controls">
              <button class="ms-audio-btn" data-slot="1" title="Focus audio">&#128266;</button>
              <button class="ms-chat-sw-btn" data-slot="1" title="Switch chat">&#128172;</button>
              <button class="ms-remove-btn" data-slot="1" title="Remove">&times;</button>
            </div>
          </div>
        </div>
      </div>

      <div class="ms-slot" data-slot-idx="2">
        <div class="ms-slot-empty">
          <button class="ms-add-btn" data-slot="2">+<span>Add Stream</span></button>
        </div>
        <div class="ms-add-form" style="display:none">
          <input class="ms-add-input" type="text" placeholder="channel name" maxlength="100" autocomplete="off" />
          <select class="ms-add-platform">
            <option value="twitch">Twitch</option>
            <option value="kick">Kick</option>
          </select>
          <div class="ms-form-btns">
            <button class="ms-confirm-btn" data-slot="2">Add</button>
            <button class="ms-cancel-btn" data-slot="2">Cancel</button>
          </div>
        </div>
        <div class="ms-slot-active">
          <video class="ms-video" autoplay muted playsinline></video>
          <div class="ms-loading">Loading stream...</div>
          <div class="ms-error-msg"></div>
          <div class="ms-overlay">
            <div class="ms-slot-info">
              <span class="ms-platform-badge"></span>
              <span class="ms-channel-name"></span>
            </div>
            <div class="ms-slot-controls">
              <button class="ms-audio-btn" data-slot="2" title="Focus audio">&#128266;</button>
              <button class="ms-chat-sw-btn" data-slot="2" title="Switch chat">&#128172;</button>
              <button class="ms-remove-btn" data-slot="2" title="Remove">&times;</button>
            </div>
          </div>
        </div>
      </div>

      <div class="ms-slot" data-slot-idx="3">
        <div class="ms-slot-empty">
          <button class="ms-add-btn" data-slot="3">+<span>Add Stream</span></button>
        </div>
        <div class="ms-add-form" style="display:none">
          <input class="ms-add-input" type="text" placeholder="channel name" maxlength="100" autocomplete="off" />
          <select class="ms-add-platform">
            <option value="twitch">Twitch</option>
            <option value="kick">Kick</option>
          </select>
          <div class="ms-form-btns">
            <button class="ms-confirm-btn" data-slot="3">Add</button>
            <button class="ms-cancel-btn" data-slot="3">Cancel</button>
          </div>
        </div>
        <div class="ms-slot-active">
          <video class="ms-video" autoplay muted playsinline></video>
          <div class="ms-loading">Loading stream...</div>
          <div class="ms-error-msg"></div>
          <div class="ms-overlay">
            <div class="ms-slot-info">
              <span class="ms-platform-badge"></span>
              <span class="ms-channel-name"></span>
            </div>
            <div class="ms-slot-controls">
              <button class="ms-audio-btn" data-slot="3" title="Focus audio">&#128266;</button>
              <button class="ms-chat-sw-btn" data-slot="3" title="Switch chat">&#128172;</button>
              <button class="ms-remove-btn" data-slot="3" title="Remove">&times;</button>
            </div>
          </div>
        </div>
      </div>

    </div>
    <!-- Multi-stream chat panel -->
    <div id="ms-chat-panel" class="hidden">
      <div id="ms-chat-header">
        <span id="ms-chat-title">Chat</span>
        <span id="ms-chat-status-dot"></span>
      </div>
      <div id="ms-chat-messages"></div>
      <div id="ms-chat-new-messages">&#8595; New messages</div>
      <div id="ms-chat-input-area">
        <input id="ms-chat-input" type="text" placeholder="Send a message..." maxlength="500" disabled />
        <button id="ms-chat-send-btn" disabled>Send</button>
      </div>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Add context menu item**

In `#context-menu`, add after the existing "Watch in App" item:

```html
<div class="ctx-item" data-action="multistream">&#9706; Add to Multi-stream</div>
```

- [ ] **Step 4: Run lint**

```
make lint
```

Expected: clean (Python unchanged, lint checks JS only indirectly).

- [ ] **Step 5: Commit**

```bash
git add ui/index.html
git commit -m "feat(multistream): HTML skeleton, CSS, and context menu item"
```

---

## Task 4: JS core — `multiState`, slot management, `window.onMultiSlotReady`

**Files:**
- Modify: `ui/index.html` (JS section only)

- [ ] **Step 1: Add `multiState` and `msChatAutoScroll`**

Find `var state = {` in the JS and, immediately below the `state` declaration, add:

```javascript
var multiState = {
  slots: [null, null, null, null],
  audioFocus: -1,
  chatSlot: -1,
  open: false,
  chatVisible: false
};
var msChatAutoScroll = true;
```

- [ ] **Step 2: Add `openMultistreamView` and `closeMultistreamView`**

Add near the other show/hide view functions (`showPlayerView`, `showBrowseView`, etc.):

```javascript
function openMultistreamView() {
  if (document.getElementById('player-view').classList.contains('active')) {
    hidePlayerView();
  }
  document.getElementById('browse-view').classList.add('hidden');
  document.getElementById('channel-view').classList.add('hidden');
  document.getElementById('toolbar').classList.add('hidden');
  document.getElementById('stream-grid').classList.add('hidden');
  document.getElementById('multistream-view').classList.remove('hidden');
  multiState.open = true;
}

function closeMultistreamView() {
  for (var i = 0; i < 4; i++) {
    if (multiState.slots[i]) _clearMultiSlot(i);
  }
  if (api) api.stop_multi();
  multiState.slots = [null, null, null, null];
  multiState.audioFocus = -1;
  multiState.chatSlot = -1;
  multiState.open = false;
  multiState.chatVisible = false;
  document.getElementById('multistream-view').classList.add('hidden');
  document.getElementById('ms-chat-panel').classList.add('hidden');
  document.getElementById('toolbar').classList.remove('hidden');
  document.getElementById('stream-grid').classList.remove('hidden');
  document.getElementById('ms-chat-messages').replaceChildren();
}
```

- [ ] **Step 3: Add `_clearMultiSlot` (internal helper)**

```javascript
function _clearMultiSlot(idx) {
  var slotEl = document.querySelector('.ms-slot[data-slot-idx="' + idx + '"]');
  if (!slotEl) return;
  var video = slotEl.querySelector('.ms-video');
  if (video) { video.pause(); video.removeAttribute('src'); video.load(); }
  slotEl.querySelector('.ms-slot-active').style.display = 'none';
  slotEl.querySelector('.ms-slot-empty').style.display = '';
  slotEl.querySelector('.ms-add-form').style.display = 'none';
  slotEl.classList.remove('audio-focus', 'chat-focus');
}
```

- [ ] **Step 4: Add `addMultiSlot` (called from context menu handler and from the add form)**

```javascript
function addMultiSlot(idx, channel, platform) {
  var cfg = (typeof pywebview !== 'undefined' && pywebview.api)
    ? pywebview.api.get_full_config_for_settings()
    : {};
  var quality = (cfg && cfg.settings && cfg.settings.quality) || 'best';
  multiState.slots[idx] = { channel: channel, platform: platform, quality: quality, title: '' };
  var slotEl = document.querySelector('.ms-slot[data-slot-idx="' + idx + '"]');
  slotEl.querySelector('.ms-slot-empty').style.display = 'none';
  slotEl.querySelector('.ms-add-form').style.display = 'none';
  var active = slotEl.querySelector('.ms-slot-active');
  active.style.display = '';
  active.querySelector('.ms-loading').style.display = '';
  active.querySelector('.ms-error-msg').style.display = 'none';
  active.querySelector('.ms-video').muted = true;
  if (api) api.add_multi_slot(idx, channel, platform, quality);
}
```

- [ ] **Step 5: Add `removeMultiSlot`**

```javascript
function removeMultiSlot(idx) {
  _clearMultiSlot(idx);
  multiState.slots[idx] = null;
  if (multiState.audioFocus === idx) {
    multiState.audioFocus = -1;
    for (var i = 0; i < 4; i++) {
      if (multiState.slots[i]) { setAudioFocus(i); break; }
    }
  }
  if (multiState.chatSlot === idx) {
    multiState.chatSlot = -1;
    if (api) api.stop_chat();
    document.getElementById('ms-chat-title').textContent = 'Chat';
    document.getElementById('ms-chat-status-dot').className = '';
    document.getElementById('ms-chat-input').disabled = true;
    document.getElementById('ms-chat-send-btn').disabled = true;
  }
}
```

- [ ] **Step 6: Add `setAudioFocus`**

```javascript
function setAudioFocus(idx) {
  document.querySelectorAll('.ms-slot').forEach(function(el) {
    el.classList.remove('audio-focus');
    var v = el.querySelector('.ms-video');
    if (v) v.muted = true;
  });
  var focusEl = document.querySelector('.ms-slot[data-slot-idx="' + idx + '"]');
  if (focusEl) {
    focusEl.classList.add('audio-focus');
    var v = focusEl.querySelector('.ms-video');
    if (v) v.muted = false;
  }
  multiState.audioFocus = idx;
}
```

- [ ] **Step 7: Add `switchMultiChat` and `toggleMsChat`**

```javascript
function switchMultiChat(idx) {
  var slot = multiState.slots[idx];
  if (!slot) return;
  document.querySelectorAll('.ms-slot').forEach(function(el) {
    el.classList.remove('chat-focus');
  });
  var el = document.querySelector('.ms-slot[data-slot-idx="' + idx + '"]');
  if (el) el.classList.add('chat-focus');
  multiState.chatSlot = idx;
  document.getElementById('ms-chat-messages').replaceChildren();
  document.getElementById('ms-chat-title').textContent = slot.channel;
  if (api) {
    api.stop_chat();
    api.start_chat(slot.channel, slot.platform);
  }
  if (!multiState.chatVisible) toggleMsChat();
}

function toggleMsChat() {
  multiState.chatVisible = !multiState.chatVisible;
  document.getElementById('ms-chat-panel').classList.toggle('hidden', !multiState.chatVisible);
}
```

- [ ] **Step 8: Add `window.onMultiSlotReady`**

```javascript
window.onMultiSlotReady = function(data) {
  var idx = data.slot_idx;
  var slotEl = document.querySelector('.ms-slot[data-slot-idx="' + idx + '"]');
  if (!slotEl || !multiState.slots[idx]) return;
  var active = slotEl.querySelector('.ms-slot-active');
  var loading = active.querySelector('.ms-loading');
  var errEl = active.querySelector('.ms-error-msg');

  if (data.error) {
    loading.style.display = 'none';
    errEl.textContent = data.error;
    errEl.style.display = 'flex';
    return;
  }

  var video = active.querySelector('.ms-video');
  video.src = data.url;
  video.muted = (multiState.audioFocus !== idx);
  video.play().catch(function() {});
  loading.style.display = 'none';
  errEl.style.display = 'none';

  active.querySelector('.ms-channel-name').textContent = data.channel || '';
  active.querySelector('.ms-platform-badge').textContent =
    (data.platform || '').charAt(0).toUpperCase();
  if (data.title) multiState.slots[idx].title = data.title;

  if (multiState.audioFocus === -1) setAudioFocus(idx);
  if (multiState.chatSlot === -1) switchMultiChat(idx);
};
```

- [ ] **Step 9: Wire slot button events in `DOMContentLoaded`**

Find the existing `DOMContentLoaded` listener block and add inside it:

```javascript
// Multi-stream grid click delegation
document.getElementById('multistream-grid').addEventListener('click', function(e) {
  var addBtn = e.target.closest('.ms-add-btn');
  if (addBtn) {
    var slot = parseInt(addBtn.dataset.slot, 10);
    var slotEl = document.querySelector('.ms-slot[data-slot-idx="' + slot + '"]');
    slotEl.querySelector('.ms-slot-empty').style.display = 'none';
    slotEl.querySelector('.ms-add-form').style.display = 'flex';
    slotEl.querySelector('.ms-add-input').focus();
    return;
  }
  var confirmBtn = e.target.closest('.ms-confirm-btn');
  if (confirmBtn) {
    var slot = parseInt(confirmBtn.dataset.slot, 10);
    var slotEl = document.querySelector('.ms-slot[data-slot-idx="' + slot + '"]');
    var channel = slotEl.querySelector('.ms-add-input').value.trim();
    var platform = slotEl.querySelector('.ms-add-platform').value;
    if (channel) {
      addMultiSlot(slot, channel, platform);
    } else {
      slotEl.querySelector('.ms-add-form').style.display = 'none';
      slotEl.querySelector('.ms-slot-empty').style.display = '';
    }
    return;
  }
  var cancelBtn = e.target.closest('.ms-cancel-btn');
  if (cancelBtn) {
    var slot = parseInt(cancelBtn.dataset.slot, 10);
    var slotEl = document.querySelector('.ms-slot[data-slot-idx="' + slot + '"]');
    slotEl.querySelector('.ms-add-form').style.display = 'none';
    slotEl.querySelector('.ms-slot-empty').style.display = '';
    return;
  }
  var audioBtn = e.target.closest('.ms-audio-btn');
  if (audioBtn) { setAudioFocus(parseInt(audioBtn.dataset.slot, 10)); return; }
  var chatBtn = e.target.closest('.ms-chat-sw-btn');
  if (chatBtn) { switchMultiChat(parseInt(chatBtn.dataset.slot, 10)); return; }
  var removeBtn = e.target.closest('.ms-remove-btn');
  if (removeBtn) { removeMultiSlot(parseInt(removeBtn.dataset.slot, 10)); return; }
});

// Confirm add-form on Enter key
document.getElementById('multistream-grid').addEventListener('keydown', function(e) {
  if (e.key !== 'Enter') return;
  var input = e.target.closest('.ms-add-input');
  if (!input) return;
  var slotEl = input.closest('.ms-slot');
  var idx = parseInt(slotEl.dataset.slotIdx, 10);
  var channel = input.value.trim();
  var platform = slotEl.querySelector('.ms-add-platform').value;
  if (channel) {
    addMultiSlot(idx, channel, platform);
  } else {
    slotEl.querySelector('.ms-add-form').style.display = 'none';
    slotEl.querySelector('.ms-slot-empty').style.display = '';
  }
});

// ms-chat send button
document.getElementById('ms-chat-send-btn').addEventListener('click', function() {
  var input = document.getElementById('ms-chat-input');
  var text = input.value.trim();
  if (!text || !api) return;
  api.send_chat(text, null, null);
  input.value = '';
});
document.getElementById('ms-chat-input').addEventListener('keydown', function(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    document.getElementById('ms-chat-send-btn').click();
  }
});

// ms-chat new-messages scroll button
document.getElementById('ms-chat-new-messages').addEventListener('click', function() {
  var el = document.getElementById('ms-chat-messages');
  el.scrollTop = el.scrollHeight;
  msChatAutoScroll = true;
  document.getElementById('ms-chat-new-messages').classList.remove('visible');
});
document.getElementById('ms-chat-messages').addEventListener('scroll', function() {
  var el = document.getElementById('ms-chat-messages');
  msChatAutoScroll = (el.scrollHeight - el.scrollTop - el.clientHeight) < 60;
  if (msChatAutoScroll) {
    document.getElementById('ms-chat-new-messages').classList.remove('visible');
  }
});
```

- [ ] **Step 10: Commit**

```bash
git add ui/index.html
git commit -m "feat(multistream): JS state, slot management, onMultiSlotReady callback"
```

---

## Task 5: Chat routing to multistream panel

**Files:**
- Modify: `ui/index.html` (JS section)

The goal is to route `window.onChatMessage` and `window.onChatStatus` to `#ms-chat-messages` / `#ms-chat-status-dot` when `multiState.open` is true, so the same chat infrastructure serves both views without duplication.

- [ ] **Step 1: Add routing helpers**

Immediately before `window.onChatMessage`, add:

```javascript
function _getChatMessagesEl() {
  return document.getElementById(
    multiState.open ? 'ms-chat-messages' : 'chat-messages'
  );
}

function _getChatNewMsgEl() {
  return document.getElementById(
    multiState.open ? 'ms-chat-new-messages' : 'chat-new-messages'
  );
}

function _getChatAutoScroll() {
  return multiState.open ? msChatAutoScroll : chatAutoScroll;
}

function _setChatAutoScroll(val) {
  if (multiState.open) msChatAutoScroll = val;
  else chatAutoScroll = val;
}
```

- [ ] **Step 2: Replace hardcoded container references inside `window.onChatMessage`**

Find every `document.getElementById('chat-messages')` inside the body of `window.onChatMessage` and replace with `_getChatMessagesEl()`.

Find every read of `chatAutoScroll` inside `window.onChatMessage` and replace with `_getChatAutoScroll()`.

Find every write to `chatAutoScroll` (e.g. `chatAutoScroll = true`) inside `window.onChatMessage` and replace with `_setChatAutoScroll(true)` / `_setChatAutoScroll(false)`.

Find the reference to `document.getElementById('chat-new-messages')` inside `window.onChatMessage` and replace with `_getChatNewMsgEl()`.

- [ ] **Step 3: Route `window.onChatStatus`**

Find `window.onChatStatus`. Wrap its existing body so that when `multiState.open` is true it targets the multistream panel instead:

```javascript
window.onChatStatus = function(data) {
  if (multiState.open) {
    var dot = document.getElementById('ms-chat-status-dot');
    if (dot) dot.className = data.connected ? 'connected' : '';
    var inp = document.getElementById('ms-chat-input');
    var btn = document.getElementById('ms-chat-send-btn');
    if (inp) inp.disabled = !data.connected;
    if (btn) btn.disabled = !data.connected;
    return;
  }
  // --- existing onChatStatus body below, unchanged ---
  // (leave the original code here)
};
```

- [ ] **Step 4: Run `make test` to confirm no regressions**

```
make test
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add ui/index.html
git commit -m "feat(multistream): route chat messages and status to multistream panel when open"
```

---

## Task 6: Navigation wiring — context menu + Escape shortcut

**Files:**
- Modify: `ui/index.html` (JS section)

- [ ] **Step 1: Handle `multistream` action in the context menu click handler**

Find the block that handles `data-action` click events (the `if (action === 'watch') ...` chain). Add a new branch for `multistream`:

```javascript
else if (action === 'multistream') {
  var emptyIdx = multiState.slots.indexOf(null);
  if (emptyIdx !== -1) {
    openMultistreamView();
    addMultiSlot(emptyIdx, ctxChannel, ctxPlat);
  }
}
```

- [ ] **Step 2: Hide the context menu item when all slots are full or channel is YouTube**

In `showContextMenu(e, login)`, after the existing `favItem` / `removeItem` visibility logic, add:

```javascript
var msItem = menu.querySelector('[data-action="multistream"]');
if (msItem) {
  var allFull = multiState.slots.every(function(s) { return s !== null; });
  var ctxStream = state.streams.find(function(s) { return s.login === login; });
  var isYT = (ctxStream && ctxStream.platform === 'youtube') ||
    (state.favoritesMeta[login] && state.favoritesMeta[login].platform === 'youtube');
  msItem.style.display = (allFull || isYT) ? 'none' : 'block';
}
```

Apply the same two lines at the end of `showSidebarContextMenu` as well (same logic, same `login` variable).

- [ ] **Step 3: Close multistream on Escape**

In `handleKeydown`, at the very top of the `if (e.key === 'Escape')` block, add:

```javascript
if (multiState.open) { closeMultistreamView(); return; }
```

- [ ] **Step 4: Run full test suite**

```
make test
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add ui/index.html
git commit -m "feat(multistream): context menu entry, slot-full guard, Escape to close"
```

---

## Self-Review

### 1. Spec coverage

| Spec requirement | Task covering it |
|---|---|
| 2–4 streams in grid layout | Task 3 — 2×2 CSS grid, empty slots show "+" |
| One stream with audio, others muted | Task 4 Step 6 — `setAudioFocus` mutes all then unmutes focused |
| Click to switch audio focus | Task 4 Step 9 — `.ms-audio-btn` click delegation |
| Switchable chat between streams | Task 4 Step 7 — `switchMultiChat` + Task 5 routing |
| Cross-platform mixing (Twitch + Kick) | Task 2 — `add_multi_slot` accepts any non-YouTube platform; Task 3 — platform select has Twitch + Kick |
| Python background HLS resolution per slot | Task 2 — `do_resolve` in background thread, same pattern as `watch_direct` |
| Error state per slot | Task 4 Step 8 — `data.error` branch shows `.ms-error-msg` |
| Remove a slot | Task 4 Step 5 — `removeMultiSlot` stops video, frees state |
| Close multistream | Task 4 Step 2 — `closeMultistreamView` stops all videos + chat |
| Context menu entry point | Task 3 Step 3 + Task 6 Steps 1–2 |
| Escape to exit | Task 6 Step 3 |
| Chat send in multistream | Task 4 Step 9 — `ms-chat-send-btn` wired to `api.send_chat` |

### 2. Placeholder scan

No TBDs or vague steps. Every step shows complete, runnable code.

### 3. Type consistency

- `slot_idx` — `int` in Python, parsed with `parseInt(..., 10)` everywhere in JS. Consistent.
- `multiState.slots` — `[null, null, null, null]` with `null` for empty and `{channel, platform, quality, title}` for active. Used consistently in `addMultiSlot`, `removeMultiSlot`, `closeMultistreamView`, `window.onMultiSlotReady`, and `switchMultiChat`.
- `window.onMultiSlotReady` payload fields `{slot_idx, channel, platform, title, url?, error?}` — produced by Python in Task 2 Step 1, consumed by JS in Task 4 Step 8. Fields match.
- `setAudioFocus(idx)` — always receives a numeric literal or `parseInt` result. Consistent.
- `switchMultiChat(idx)` — same.
- `_clearMultiSlot(idx)` — called with the same type everywhere.
- `addMultiSlot(idx, channel, platform)` — 3-arg call consistent between context menu handler (Task 6 Step 1) and add-form confirm handler (Task 4 Step 9).
