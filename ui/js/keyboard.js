window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

function formatKeyName(key) {
  if (key === ' ')          return 'Space';
  if (key === 'ArrowUp')    return '\u2191';
  if (key === 'ArrowDown')  return '\u2193';
  if (key === 'ArrowLeft')  return '\u2190';
  if (key === 'ArrowRight') return '\u2192';
  if (key === 'Enter')      return '\u21B5';
  if (key === 'Backspace')  return '\u232B';
  if (key === 'Tab')        return '\u21E5';
  return key;
}

function formatKeyDisplay(key) {
  if (key === ' ')          return 'Space';
  if (key === 'ArrowUp')    return '\u2191';
  if (key === 'ArrowDown')  return '\u2193';
  if (key === 'ArrowLeft')  return '\u2190';
  if (key === 'ArrowRight') return '\u2192';
  if (key === 'Enter')      return '\u21B5';
  if (key === 'Backspace')  return '\u232B';
  if (key === 'Tab')        return '\u21E5';
  return key;
}

function startRebind(action) {
  TwitchX._rebindAction = action;
  renderHotkeysSettings();
}

function renderHotkeysSettings() {
  const tbl = document.getElementById('hotkeys-table');
  if (!tbl) return;
  tbl.replaceChildren();
  Object.keys(TwitchX.SHORTCUT_LABELS).forEach(function(action) {
    const key = TwitchX.state.shortcuts[action] !== undefined
      ? TwitchX.state.shortcuts[action]
      : TwitchX.DEFAULT_SHORTCUTS[action];
    const isCapturing = TwitchX._rebindAction === action;
    const tr = document.createElement('tr');

    const labelTd = document.createElement('td');
    labelTd.textContent = TwitchX.SHORTCUT_LABELS[action];

    const keyTd = document.createElement('td');

    const kbd = document.createElement('kbd');
    kbd.className = isCapturing ? 'hotkey-capturing' : 'hotkey-idle';
    kbd.replaceChildren();
    if (isCapturing) {
      kbd.textContent = 'Press key\u2026';
    } else {
      var keyEl = document.createElement('span');
      keyEl.className = 'hotkey-icon';
      keyEl.textContent = formatKeyDisplay(key);
      kbd.appendChild(keyEl);
    }
    kbd.title = isCapturing ? 'Press Esc to cancel' : 'Click to rebind';
    kbd.tabIndex = 0;
    kbd.setAttribute('role', 'button');
    kbd.setAttribute('aria-label', 'Rebind ' + TwitchX.SHORTCUT_LABELS[action]);
    kbd.addEventListener('click', function() { startRebind(action); });
    kbd.addEventListener('keydown', function(e) {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      e.preventDefault();
      startRebind(action);
    });

    keyTd.appendChild(kbd);
    tr.appendChild(labelTd);
    tr.appendChild(keyTd);
    tbl.appendChild(tr);
  });
}

// Enter/Space belong to whatever control has focus. Grabbing them globally
// broke Tab navigation: Enter on Browse/Settings/any button ran doWatch()
// instead of activating the button.
const ACTIVATION_TARGET_SELECTOR =
  'button, a[href], summary, [role="button"], [role="menuitem"], [role="tab"], [role="option"], [contenteditable="true"]';
// Channel targets are the exception: their own handler selects the channel and
// the global watch shortcut then completes the same intent as a double-click.
const CHANNEL_TARGET_SELECTOR = '.stream-card, .channel-item, .rail-avatar';

function focusOwnsActivationKeys() {
  const el = document.activeElement;
  if (!el || el === document.body || typeof el.closest !== 'function') return false;
  if (el.closest(CHANNEL_TARGET_SELECTOR)) return false;
  return !!el.closest(ACTIVATION_TARGET_SELECTOR);
}

function handleKeydown(e) {
  // Phase 9: when a shortcut is being rebound, swallow all keys in capture phase
  if (TwitchX._rebindAction) return;

  const tag = document.activeElement ? document.activeElement.tagName : '';
  const inInput = tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA';
  const sc = TwitchX.state.shortcuts;

  if (e.key === 'Tab') {
    var overlay = document.getElementById('settings-overlay');
    var paletteOverlay = document.getElementById('palette-overlay');
    var trapRoot = null;
    if (overlay && overlay.classList.contains('visible')) trapRoot = overlay;
    else if (paletteOverlay && !paletteOverlay.classList.contains('hidden')) trapRoot = paletteOverlay;
    if (trapRoot) {
      var focusable = trapRoot.querySelectorAll(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (focusable.length === 0) return;
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
  }

  if (e.key === 'Escape') {
    if (document.getElementById('context-menu').classList.contains('menu-visible')) {
      TwitchX.closeContextMenu(); return;
    }
    if (!document.getElementById('palette-overlay').classList.contains('hidden')) {
      e.preventDefault();
      if (TwitchX.closePalette) TwitchX.closePalette();
      return;
    }
    if (document.getElementById('settings-overlay').classList.contains('visible')) {
      TwitchX.closeSettings(); return;
    }
    if (document.getElementById('player-view').classList.contains('view-active')) {
      TwitchX.hidePlayerView();
      return;
    }
    if (document.getElementById('channel-view').classList.contains('view-active')) {
      TwitchX.hideChannelView(); return;
    }
    if (document.getElementById('browse-view').classList.contains('view-active')) {
      TwitchX.browseGoBack(); return;
    }
    if (TwitchX.multiState.open) { TwitchX.closeMultistreamView(); return; }
    if (document.getElementById('search-dropdown').classList.contains('visible')) {
      document.getElementById('search-dropdown').classList.remove('visible'); return;
    }
    TwitchX.state.selectedChannel = null;
    TwitchX.state.selectedChannelKey = null;
    TwitchX.state.selectedPlatform = null;
    document.querySelectorAll('.stream-card').forEach(function(c) { c.classList.remove('selected'); });
    document.querySelectorAll('.channel-item').forEach(function(c) { c.classList.remove('selected'); });
    document.getElementById('watch-btn').classList.remove('active');
    TwitchX.setStatus('', 'info');
    return;
  }

  // Modifier-based shortcuts (not rebindable)
  if (e.key === 'F5' || (e.metaKey && e.key === 'r')) {
    e.preventDefault(); TwitchX.doRefresh(); return;
  }
  if (e.metaKey && e.key === ',') {
    e.preventDefault(); TwitchX.openSettings(); return;
  }
  if (e.metaKey && e.key === 'k') {
    e.preventDefault();
    if (TwitchX.openPalette) TwitchX.openPalette();
    return;
  }

  if (inInput) return;

  const inPlayer = document.getElementById('player-view').classList.contains('view-active');
  const inMulti = TwitchX.multiState.open;

  // Single-key shortcuts — skip if any modifier is held
  if (e.metaKey || e.ctrlKey || e.altKey) return;

  if ((e.key === 'Enter' || e.key === ' ') && focusOwnsActivationKeys()) return;

  if (e.key === sc.refresh) { e.preventDefault(); TwitchX.doRefresh(); return; }
  if (e.key === sc.watch || e.key === 'Enter') { e.preventDefault(); TwitchX.doWatch(); return; }

  if (inPlayer || inMulti) {
    if (e.key === sc.volume_up)   { e.preventDefault(); TwitchX.adjustVolume(0.1);  return; }
    if (e.key === sc.volume_down) { e.preventDefault(); TwitchX.adjustVolume(-0.1); return; }
    if (e.key === sc.mute)        { e.preventDefault(); TwitchX.toggleMute();        return; }
    if (e.key === sc.toggle_chat) {
      e.preventDefault();
      if (inMulti) TwitchX.toggleMsChat();
      else TwitchX.toggleChatPanel();
      return;
    }
  }

  if (inPlayer) {
    if (e.key === sc.fullscreen) { e.preventDefault(); TwitchX.toggleVideoFullscreen(); return; }
    if (e.key === sc.pip) { e.preventDefault(); TwitchX.togglePiP(TwitchX.getPlayerVideo()); return; }
  }

  if (inMulti) {
    if (e.key === sc.pip) {
      e.preventDefault();
      const focusIdx = TwitchX.multiState.audioFocus;
      if (focusIdx >= 0) {
        const slotEl = document.querySelector('.ms-slot[data-slot-idx="' + focusIdx + '"]');
        if (slotEl) TwitchX.togglePiP(slotEl.querySelector('.ms-video'));
      }
      return;
    }
  }

  if (!inPlayer && !inMulti) {
    if (e.key === sc.next_stream) { e.preventDefault(); TwitchX.cycleStream(1);  return; }
    if (e.key === sc.prev_stream) { e.preventDefault(); TwitchX.cycleStream(-1); return; }
  }
}

TwitchX.formatKeyName = formatKeyName;
TwitchX.startRebind = startRebind;
TwitchX.renderHotkeysSettings = renderHotkeysSettings;
TwitchX.handleKeydown = handleKeydown;
TwitchX.focusOwnsActivationKeys = focusOwnsActivationKeys;
