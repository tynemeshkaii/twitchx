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
    tr.style.borderBottom = '1px solid rgba(255,255,255,0.05)';

    const labelTd = document.createElement('td');
    labelTd.style.cssText = 'padding:7px 0;font-size:12px;color:var(--text-secondary);';
    labelTd.textContent = TwitchX.SHORTCUT_LABELS[action];

    const keyTd = document.createElement('td');
    keyTd.style.cssText = 'padding:7px 0;text-align:right;';

    const kbd = document.createElement('kbd');
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
    kbd.textContent = isCapturing ? 'Press key\u2026' : formatKeyName(key);
    kbd.title = isCapturing ? 'Press Esc to cancel' : 'Click to rebind';
    kbd.addEventListener('click', function() { startRebind(action); });

    keyTd.appendChild(kbd);
    tr.appendChild(labelTd);
    tr.appendChild(keyTd);
    tbl.appendChild(tr);
  });
}

function handleKeydown(e) {
  // Phase 9: when a shortcut is being rebound, swallow all keys in capture phase
  if (TwitchX._rebindAction) return;

  const tag = document.activeElement ? document.activeElement.tagName : '';
  const inInput = tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA';
  const sc = TwitchX.state.shortcuts;

  if (e.key === 'Escape') {
    if (!document.getElementById('palette-overlay').classList.contains('hidden')) {
      if (TwitchX.closePalette) TwitchX.closePalette();
      return;
    }
    if (document.getElementById('settings-overlay').classList.contains('visible')) {
      TwitchX.closeSettings(); return;
    }
    if (document.getElementById('player-view').classList.contains('active')) {
      TwitchX.hidePlayerView();
      return;
    }
    if (!document.getElementById('channel-view').classList.contains('hidden')) {
      TwitchX.hideChannelView(); return;
    }
    if (!document.getElementById('browse-view').classList.contains('hidden')) {
      TwitchX.browseGoBack(); return;
    }
    if (TwitchX.multiState.open) { TwitchX.closeMultistreamView(); return; }
    if (!document.getElementById('context-menu').classList.contains('hidden')) {
      document.getElementById('context-menu').classList.add('hidden'); return;
    }
    if (!document.getElementById('search-dropdown').classList.contains('hidden')) {
      document.getElementById('search-dropdown').classList.add('hidden'); return;
    }
    TwitchX.state.selectedChannel = null;
    document.querySelectorAll('.stream-card').forEach(function(c) { c.classList.remove('selected'); });
    document.querySelectorAll('.channel-item').forEach(function(c) { c.classList.remove('selected'); });
    document.getElementById('watch-btn').classList.remove('active');
    TwitchX.setStatus('', 'info');
    return;
  }

  if (inInput) return;

  const inPlayer = document.getElementById('player-view').classList.contains('active');
  const inMulti = TwitchX.multiState.open;

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

  // Single-key shortcuts — skip if any modifier is held
  if (e.metaKey || e.ctrlKey || e.altKey) return;

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
