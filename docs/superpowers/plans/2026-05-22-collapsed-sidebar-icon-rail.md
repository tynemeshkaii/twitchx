# Collapsed Sidebar Icon Rail — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken clipped collapsed sidebar with a proper 52px icon rail showing only channel avatars with live/offline indicators.

**Architecture:** `renderSidebar()` branches at the top — if `#sidebar` has `collapsed-sidebar` class, delegates to new `renderRail(groups)` function; otherwise runs existing full-sidebar logic untouched. `renderRail` builds a completely separate DOM structure (`.rail-avatar` nodes) inside `#channel-list`. CSS adds rail-specific styles and cleans up the dead collapsed-item overrides.

**Tech Stack:** Vanilla JS (IIFE + `TwitchX` namespace), CSS custom properties, no build step.

---

## File Map

| File | Change |
|---|---|
| `ui/css/components.css` | Change collapsed width 56→52px; add `.rail-avatar`, `.rail-av-img`, `.rail-av-ring`, `.rail-av-dot`, `.rail-divider`; override `#channel-list` padding/gap in collapsed mode |
| `ui/js/sidebar.js` | Add `createRailAvatar(login, isLive, streamMap)`, add `renderRail(groups)`, add collapsed branch at top of `renderSidebar()`, expose both on `TwitchX` |
| `ui/js/init.js` | Call `TwitchX.renderSidebar()` after toggling `collapsed-sidebar` class |

---

## Task 1 — CSS: Rail styles

**Files:**
- Modify: `ui/css/components.css` lines 101–118 (collapsed-sidebar block)

- [ ] **Step 1: Change collapsed width and add #channel-list override**

Find the existing collapsed-sidebar block (lines 100–118 in components.css) and update it. The block currently starts with:

```css
/* ── Sidebar collapsed mode (icons-only) ───────────────── */
#sidebar.collapsed-sidebar { width: 56px; transition: width var(--duration-normal) var(--ease-default); }
```

Replace `width: 56px` with `width: 52px` and add a `#channel-list` override immediately after the existing rules:

```css
/* ── Sidebar collapsed mode (icons-only) ───────────────── */
#sidebar.collapsed-sidebar { width: 52px; transition: width var(--duration-normal) var(--ease-default); }
#sidebar.collapsed-sidebar #profile-area { display: none; }
#sidebar.collapsed-sidebar #kick-profile-area { display: none; }
#sidebar.collapsed-sidebar #platform-tabs { display: none; }
#sidebar.collapsed-sidebar #favorites-header .favorites-label { display: none; }
#sidebar.collapsed-sidebar #favorites-count-badge { display: none; }
#sidebar.collapsed-sidebar #search-area { display: none; }
#sidebar.collapsed-sidebar #browse-nav-wrapper { display: none; }
#sidebar.collapsed-sidebar #favorites-header {
  justify-content: center;
  padding: 10px 6px 6px;
}
#sidebar.collapsed-sidebar .sidebar-collapse-btn {
  margin-left: 0;
}
#sidebar.collapsed-sidebar .sidebar-collapse-btn svg {
  transform: rotate(180deg);
}
#sidebar.collapsed-sidebar #channel-list {
  padding: 4px 0 8px;
  align-items: center;
  gap: 5px;
}
```

- [ ] **Step 2: Add rail avatar styles**

Append these rules after the collapsed-sidebar block (after line 118):

```css
/* ── Icon rail — avatar items ───────────────────────────── */
.rail-avatar {
  position: relative;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  cursor: pointer;
  border-radius: 50%;
  outline: none;
}
.rail-avatar:focus-visible {
  box-shadow: 0 0 0 2px rgba(255, 159, 10, 0.6);
}
.rail-avatar.offline {
  filter: grayscale(0.7) opacity(0.5);
}
.rail-av-img {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  object-fit: cover;
  background: var(--bg-elevated);
  display: block;
}
.rail-av-ring {
  position: absolute;
  inset: -2px;
  border-radius: 50%;
  border: 2px solid #30d158;
  pointer-events: none;
}
.rail-av-dot {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #30d158;
  border: 2px solid var(--bg-surface);
  pointer-events: none;
}

/* ── Icon rail — section divider ────────────────────────── */
.rail-divider {
  width: 24px;
  height: 1px;
  background: rgba(255, 255, 255, 0.1);
  margin: 2px 0;
  flex-shrink: 0;
}
```

- [ ] **Step 3: Verify CSS with make lint**

```bash
make lint
```

Expected: passes (ruff + pyright don't touch CSS, but this ensures nothing else broke).

- [ ] **Step 4: Commit**

```bash
git add ui/css/components.css
git commit -m "style: add icon rail CSS for collapsed sidebar"
```

---

## Task 2 — JS: `createRailAvatar` and `renderRail`

**Files:**
- Modify: `ui/js/sidebar.js` — add two new functions before the existing `renderSidebar` function

- [ ] **Step 1: Add `createRailAvatar` function**

In `sidebar.js`, find the line `function renderSidebar() {` (line 473). Insert the following two functions immediately above it:

```js
function createRailAvatar(login, isLive, streamMap) {
  var item = document.createElement('div');
  item.className = 'rail-avatar' + (isLive ? ' live' : ' offline');
  item.dataset.login = login;
  item.tabIndex = 0;
  item.setAttribute('role', 'button');
  item.setAttribute(
    'aria-label',
    isLive
      ? login + ', live'
      : login + ', offline'
  );

  var img = document.createElement('img');
  img.className = 'rail-av-img';
  img.alt = '';
  if (TwitchX.state.avatars[login]) {
    img.src = TwitchX.state.avatars[login];
  }
  item.appendChild(img);

  if (isLive) {
    var ring = document.createElement('div');
    ring.className = 'rail-av-ring';
    item.appendChild(ring);

    var dot = document.createElement('div');
    dot.className = 'rail-av-dot';
    item.appendChild(dot);
  }

  _setupSidebarTooltip(item, login, streamMap);

  item.addEventListener('click', function() { TwitchX.selectChannel(login); });
  item.addEventListener('dblclick', function() { TwitchX.selectChannel(login); TwitchX.doWatch(); });
  item.addEventListener('contextmenu', function(e) { TwitchX.showSidebarContextMenu(e, login); });
  item.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      TwitchX.selectChannel(login);
    }
  });

  return item;
}

function renderRail(groups) {
  var list = document.getElementById('channel-list');
  var liveLogins = groups.online;
  var offlineLogins = groups.offline;

  // In-place update if membership unchanged
  var existingLive = Array.from(list.querySelectorAll('.rail-avatar.live'))
    .map(function(el) { return el.dataset.login; });
  var existingOffline = Array.from(list.querySelectorAll('.rail-avatar.offline'))
    .map(function(el) { return el.dataset.login; });

  var liveChanged = existingLive.length !== liveLogins.length ||
    liveLogins.some(function(l, i) { return existingLive[i] !== l; });
  var offlineChanged = existingOffline.length !== offlineLogins.length ||
    offlineLogins.some(function(l, i) { return existingOffline[i] !== l; });

  if (!liveChanged && !offlineChanged) {
    list.querySelectorAll('.rail-avatar').forEach(function(el) {
      var login = el.dataset.login;
      var img = el.querySelector('.rail-av-img');
      var newSrc = TwitchX.state.avatars[login] || '';
      if (img && newSrc && img.src !== newSrc) {
        img.src = newSrc;
      }
    });
    return;
  }

  // Full rebuild
  while (list.firstChild) list.removeChild(list.firstChild);

  liveLogins.forEach(function(login) {
    list.appendChild(createRailAvatar(login, true, groups.streamMap));
  });

  if (liveLogins.length > 0 && offlineLogins.length > 0) {
    var divider = document.createElement('div');
    divider.className = 'rail-divider';
    list.appendChild(divider);
  }

  offlineLogins.forEach(function(login) {
    list.appendChild(createRailAvatar(login, false, groups.streamMap));
  });
}
```

- [ ] **Step 2: Expose on TwitchX namespace**

Find the exports block at the bottom of `sidebar.js` (around line 709, where `TwitchX.renderSidebar = renderSidebar;` etc. are). Add two lines:

```js
TwitchX.createRailAvatar = createRailAvatar;
TwitchX.renderRail = renderRail;
```

- [ ] **Step 3: Verify lint passes**

```bash
make lint
```

Expected: passes.

- [ ] **Step 4: Commit**

```bash
git add ui/js/sidebar.js
git commit -m "feat: add createRailAvatar and renderRail for icon rail mode"
```

---

## Task 3 — JS: Branch `renderSidebar` on collapsed state

**Files:**
- Modify: `ui/js/sidebar.js` — add branch at top of `renderSidebar()`

- [ ] **Step 1: Add collapsed branch**

In `sidebar.js`, find `function renderSidebar() {` (the original function, before the `_origRenderSidebar` wrapper). The first two lines of the function body are:

```js
  const list = document.getElementById('channel-list');
  const groups = getSidebarGroups();
```

Insert the following block before those two lines (i.e., as the very first thing in the function body):

```js
  var _sidebar = document.getElementById('sidebar');
  if (_sidebar && _sidebar.classList.contains('collapsed-sidebar')) {
    renderRail(getSidebarGroups());
    return;
  }
```

The function should now start like this:

```js
function renderSidebar() {
  var _sidebar = document.getElementById('sidebar');
  if (_sidebar && _sidebar.classList.contains('collapsed-sidebar')) {
    renderRail(getSidebarGroups());
    return;
  }

  const list = document.getElementById('channel-list');
  const groups = getSidebarGroups();
  const selectedExpanded = expandSidebarSectionForLogin(TwitchX.state.selectedChannel);
  // ... rest unchanged
```

- [ ] **Step 2: Verify lint passes**

```bash
make lint
```

Expected: passes.

- [ ] **Step 3: Commit**

```bash
git add ui/js/sidebar.js
git commit -m "feat: branch renderSidebar to icon rail when sidebar is collapsed"
```

---

## Task 4 — JS: Trigger re-render on collapse toggle

**Files:**
- Modify: `ui/js/init.js` lines 116–122 (sidebar collapse toggle handler)

- [ ] **Step 1: Add renderSidebar call to collapse toggle**

Find the collapse toggle handler in `init.js`:

```js
  // Sidebar collapse toggle
  var collapseBtn = document.getElementById('sidebar-collapse-btn');
  if (collapseBtn) collapseBtn.addEventListener('click', function() {
    var sidebar = document.getElementById('sidebar');
    var collapsed = sidebar.classList.toggle('collapsed-sidebar');
    localStorage.setItem('twitchx.sidebar.collapsed', collapsed ? '1' : '0');
  });
```

Replace it with:

```js
  // Sidebar collapse toggle
  var collapseBtn = document.getElementById('sidebar-collapse-btn');
  if (collapseBtn) collapseBtn.addEventListener('click', function() {
    var sidebar = document.getElementById('sidebar');
    var collapsed = sidebar.classList.toggle('collapsed-sidebar');
    localStorage.setItem('twitchx.sidebar.collapsed', collapsed ? '1' : '0');
    TwitchX.renderSidebar();
  });
```

- [ ] **Step 2: Verify lint passes**

```bash
make lint
```

Expected: passes.

- [ ] **Step 3: Commit**

```bash
git add ui/js/init.js
git commit -m "fix: re-render sidebar after collapse toggle to show icon rail"
```

---

## Task 5 — Visual verification

No automated tests cover JS/CSS (per CLAUDE.md). Verify manually.

- [ ] **Step 1: Run the app**

```bash
make run
```

- [ ] **Step 2: Verify expanded state is unchanged**

With the sidebar expanded (default), confirm:
- Channel list renders normally with names, viewer counts, section headers
- No visual regression

- [ ] **Step 3: Click the collapse button**

Click the collapse button (top-right of the Favorites header). Verify:
- Sidebar animates to ~52px width
- Channel list shows only avatars (32×32px, circular)
- Live channels have a green ring + green dot (bottom-right)
- Offline channels are desaturated (grayscale + dimmed)
- A thin line separates live from offline (only if both groups non-empty)
- No names, no viewer counts, no section headers visible

- [ ] **Step 4: Hover an avatar**

Hover a live channel avatar. Verify:
- Tooltip appears after ~400ms showing name, game, viewer count, thumbnail
- Tooltip disappears on mouseleave

- [ ] **Step 5: Click an avatar**

Single-click an avatar. Verify:
- Channel is selected (same behavior as in expanded mode)

- [ ] **Step 6: Expand again**

Click the collapse button again. Verify:
- Sidebar animates back to 240px
- Full channel list reappears with names and section headers intact

- [ ] **Step 7: Reload and verify persistence**

Close and reopen the app while sidebar was collapsed. Verify:
- Sidebar restores in collapsed (icon rail) state
- Icon rail renders correctly on startup

- [ ] **Step 8: Commit if any tweaks were needed**

If you made CSS/JS adjustments during manual testing, commit them:

```bash
git add ui/css/components.css ui/js/sidebar.js
git commit -m "fix: visual tweaks to icon rail after manual testing"
```
