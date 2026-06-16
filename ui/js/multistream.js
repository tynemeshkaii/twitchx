window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

const MULTISTREAM_PRESETS = ['grid', 'focus-left', 'rows', 'columns'];
const MULTISTREAM_PRESET_LABELS = {
  grid: 'Grid',
  'focus-left': 'Focus',
  rows: 'Rows',
  columns: 'Columns',
};

function openMultistreamView() {
  TwitchX.multiState.open = true;
  _updateMultiGridLayout();
  if (document.getElementById('player-view').classList.contains('view-active')) {
    TwitchX.hidePlayerView(true);
  }
  TwitchX.setChromeVisible(false);
  TwitchX.switchView('multistream-view', 'forward');
  TwitchX.startMultiHealthMonitor();
}

function _getMultiSlotEl(idx) {
  return document.querySelector('.ms-slot[data-slot-idx="' + idx + '"]');
}

function _multiOccupiedCount() {
  return TwitchX.multiState.slots.filter(function(slot) {
    return slot !== null;
  }).length;
}

function _applyMultistreamPreset(preset) {
  const grid = document.getElementById('multistream-grid');
  if (!grid) return;
  const valid = MULTISTREAM_PRESETS.indexOf(preset) >= 0 ? preset : 'grid';
  TwitchX.multiState.activePreset = valid;
  MULTISTREAM_PRESETS.forEach(function(p) {
    grid.classList.remove('ms-preset-' + p);
  });
  grid.classList.add('ms-preset-' + valid);
  const select = document.getElementById('ms-preset-select');
  if (select && select.value !== valid) select.value = valid;
}

function _loadMultistreamPresets() {
  if (!TwitchX.api) return;
  try {
    const data = TwitchX.api.get_multistream_presets();
    const preset = (data && data.presets && data.presets[data.active]) || 'grid';
    _applyMultistreamPreset(preset);
  } catch (e) {
    console.warn('[Multistream] failed to load presets', e);
    _applyMultistreamPreset('grid');
  }
}

function setMultistreamPreset(preset) {
  const idx = MULTISTREAM_PRESETS.indexOf(preset);
  if (idx < 0) return;
  _applyMultistreamPreset(preset);
  if (TwitchX.api) {
    try { TwitchX.api.set_multistream_preset(idx); } catch (e) {}
  }
}

function _updateMultiGridLayout() {
  const grid = document.getElementById('multistream-grid');
  if (!grid) return;
  const count = _multiOccupiedCount();
  const openFormCount = document.querySelectorAll('.ms-slot.ms-add-form-open').length;
  const visualCount = Math.min(4, count + openFormCount);
  grid.classList.remove('ms-grid-empty', 'ms-grid-count-1', 'ms-grid-count-2', 'ms-grid-count-3', 'ms-grid-count-4');
  grid.classList.add(visualCount === 0 ? 'ms-grid-empty' : 'ms-grid-count-' + visualCount);
  _applyMultistreamPreset(TwitchX.multiState.activePreset);

  let nextEmptyMarked = false;
  document.querySelectorAll('.ms-slot').forEach(function(slotEl) {
    const idx = parseInt(slotEl.dataset.slotIdx, 10);
    const isEmpty = TwitchX.multiState.slots[idx] === null;
    const isNextEmpty = isEmpty && !nextEmptyMarked;
    slotEl.classList.toggle('ms-next-empty', isNextEmpty);
    if (isNextEmpty) nextEmptyMarked = true;
  });

  const addSlotBtn = document.getElementById('ms-add-slot-btn');
  if (addSlotBtn) {
    addSlotBtn.disabled = count >= 4;
    addSlotBtn.classList.toggle('disabled', count >= 4);
  }
}

function _setMultiSlotState(idx, state, message) {
  const slotEl = _getMultiSlotEl(idx);
  if (!slotEl) return;
  slotEl.dataset.state = state;
  slotEl.classList.remove(
    'ms-state-empty',
    'ms-state-loading',
    'ms-state-playing',
    'ms-state-error',
    'ms-state-removing'
  );
  slotEl.classList.add('ms-state-' + state);
  const status = slotEl.querySelector('.ms-slot-status');
  if (status) {
    status.textContent = message || state.charAt(0).toUpperCase() + state.slice(1);
  }
  if (TwitchX.multiState.slots[idx]) TwitchX.multiState.slots[idx].state = state;
  _updateMultiGridLayout();
}

function openFirstEmptyMultiSlot(preferredIdx) {
  const idx = Number.isInteger(preferredIdx) && TwitchX.multiState.slots[preferredIdx] === null
    ? preferredIdx
    : TwitchX.multiState.slots.indexOf(null);
  if (idx === -1) return;
  const slotEl = _getMultiSlotEl(idx);
  if (!slotEl) return;
  slotEl.classList.add('ms-add-form-open');
  slotEl.querySelector('.ms-slot-empty').classList.add('hidden');
  slotEl.querySelector('.ms-add-form').classList.remove('hidden');
  _setMultiSlotState(idx, 'empty', 'Ready to add');
  slotEl.querySelector('.ms-add-input').focus();
}

function closeMultistreamView() {
  TwitchX.stopMultiHealthMonitor();
  for (let i = 0; i < 4; i++) {
    if (TwitchX.multiState.slots[i]) _clearMultiSlot(i);
  }
  if (TwitchX.api) TwitchX.api.stop_multi();
  TwitchX.multiState.slots = [null, null, null, null];
  TwitchX.multiState.audioFocus = -1;
  TwitchX.multiState.chatSlot = -1;
  TwitchX.multiState.open = false;
  TwitchX.multiState.chatVisible = false;
  document.getElementById('main').classList.remove('ms-sidebar-open');
  TwitchX.switchView('stream-grid', 'back');
  TwitchX.setChromeVisible(true);
  document.getElementById('ms-chat-messages').replaceChildren();
  const btn = document.getElementById('ms-sidebar-btn');
  if (btn) btn.classList.remove('active');
  _updateMultiGridLayout();
}

function toggleMsSidebar() {
  const main = document.getElementById('main');
  const btn = document.getElementById('ms-sidebar-btn');
  const open = main.classList.toggle('ms-sidebar-open');
  if (btn) btn.classList.toggle('active', open);
}

function _bindSlotPiPEvents(video, pipBtn) {
  if (!video || video._pipEventsBound) return;
  video._pipEventsBound = true;
  video.addEventListener('webkitpresentationmodechanged', function() {
    const inPiP = video.webkitPresentationMode === 'picture-in-picture';
    if (pipBtn) pipBtn.classList.toggle('active', inPiP);
  });
}

function _clearMultiSlot(idx) {
  const slotEl = _getMultiSlotEl(idx);
  if (!slotEl) return;
  const video = slotEl.querySelector('.ms-video');
  if (video) {
    if (TwitchX.isVideoPiP && TwitchX.isVideoPiP(video)) {
      TwitchX.togglePiP(video);
    }
    video.pause();
    video.removeAttribute('src');
    video.load();
    video.remove();

    const fresh = document.createElement('video');
    fresh.className = 'ms-video';
    fresh.autoplay = true;
    fresh.muted = true;
    fresh.playsInline = true;
    slotEl.querySelector('.ms-slot-active').insertBefore(fresh, slotEl.querySelector('.ms-loading'));
    const pipBtn = slotEl.querySelector('.ms-pip-btn');
    _bindSlotPiPEvents(fresh, pipBtn);
  }
  const activeEl = slotEl.querySelector('.ms-slot-active');
  activeEl.classList.add('hidden');
  slotEl.classList.remove('ms-add-form-open');
  slotEl.querySelector('.ms-slot-empty').classList.remove('hidden');
  slotEl.querySelector('.ms-add-form').classList.add('hidden');
  slotEl.classList.remove('audio-focus', 'chat-focus');
  slotEl.querySelector('.ms-error-msg').textContent = '';
  _setMultiSlotState(idx, 'empty', 'Empty');
  delete slotEl.dataset._lastTime;
  delete slotEl.dataset._frozenCount;
}

function addMultiSlot(idx, channel, platform, quality) {
  const cfg = TwitchX.api ? TwitchX.api.get_full_config_for_settings() : {};
  const q = quality || (cfg && cfg.quality) || 'best';
  TwitchX.multiState.slots[idx] = { channel: channel, platform: platform, quality: q, title: '', state: 'loading' };
  const slotEl = _getMultiSlotEl(idx);
  if (!slotEl) return;
  slotEl.dataset.platform = platform || 'twitch';
  slotEl.classList.remove('ms-add-form-open');
  slotEl.querySelector('.ms-slot-empty').classList.add('hidden');
  slotEl.querySelector('.ms-add-form').classList.add('hidden');
  const active = slotEl.querySelector('.ms-slot-active');
  active.classList.remove('hidden');
  active.querySelector('.ms-loading').classList.remove('hidden');
  active.querySelector('.ms-error-msg').classList.add('hidden');
  active.querySelector('.ms-channel-name').textContent = channel || '';
  const badge = active.querySelector('.ms-platform-badge');
  badge.className = 'ms-platform-badge ' + (platform || 'twitch');
  badge.textContent = TwitchX.platformLabel(platform || 'twitch');
  const msVideo = active.querySelector('.ms-video');
  if (msVideo) msVideo.muted = true;
  _setMultiSlotState(idx, 'loading', 'Loading');
  if (TwitchX.api) TwitchX.api.add_multi_slot(idx, channel, platform, q);
}

function _swapMultiSlots(sourceIdx, targetIdx) {
  if (sourceIdx === targetIdx) return;
  const source = TwitchX.multiState.slots[sourceIdx];
  const target = TwitchX.multiState.slots[targetIdx];
  if (!source) return;

  const sourceWasAudio = TwitchX.multiState.audioFocus === sourceIdx;
  const sourceWasChat = TwitchX.multiState.chatSlot === sourceIdx;
  const targetWasAudio = TwitchX.multiState.audioFocus === targetIdx;
  const targetWasChat = TwitchX.multiState.chatSlot === targetIdx;

  _clearMultiSlot(sourceIdx);
  TwitchX.multiState.slots[sourceIdx] = null;
  if (target) {
    _clearMultiSlot(targetIdx);
    TwitchX.multiState.slots[targetIdx] = null;
    addMultiSlot(targetIdx, source.channel, source.platform, source.quality);
    addMultiSlot(sourceIdx, target.channel, target.platform, target.quality);
  } else {
    addMultiSlot(targetIdx, source.channel, source.platform, source.quality);
  }

  if (sourceWasAudio) TwitchX.multiState.audioFocus = targetIdx;
  else if (targetWasAudio) TwitchX.multiState.audioFocus = sourceIdx;
  if (sourceWasChat) TwitchX.multiState.chatSlot = targetIdx;
  else if (targetWasChat) TwitchX.multiState.chatSlot = sourceIdx;

  _updateMultiGridLayout();
}

function removeMultiSlot(idx) {
  _setMultiSlotState(idx, 'removing', 'Removing');
  setTimeout(function() {
    _clearMultiSlot(idx);
    TwitchX.multiState.slots[idx] = null;
    if (TwitchX.multiState.audioFocus === idx) {
      TwitchX.multiState.audioFocus = -1;
      for (let i = 0; i < 4; i++) {
        if (TwitchX.multiState.slots[i]) { setAudioFocus(i); break; }
      }
    }
    if (TwitchX.multiState.chatSlot === idx) {
      TwitchX.multiState.chatSlot = -1;
      if (TwitchX.api) TwitchX.api.stop_chat();
      document.getElementById('ms-chat-title').textContent = 'Chat';
      document.getElementById('ms-chat-status-dot').className = '';
      document.getElementById('ms-chat-input').disabled = true;
      document.getElementById('ms-chat-send-btn').disabled = true;
      document.querySelectorAll('.ms-slot').forEach(function(el) {
        el.classList.remove('chat-focus');
      });
    }
    _updateMultiGridLayout();
  }, 120);
}

function setAudioFocus(idx) {
  document.querySelectorAll('.ms-slot').forEach(function(el) {
    el.classList.remove('audio-focus');
    el.classList.add('audio-muted');
    const v = el.querySelector('.ms-video');
    if (v) v.muted = true;
    const label = el.querySelector('.ms-audio-state');
    if (label) label.textContent = 'Muted';
  });
  const focusEl = _getMultiSlotEl(idx);
  if (focusEl && TwitchX.multiState.slots[idx]) {
    focusEl.classList.add('audio-focus');
    focusEl.classList.remove('audio-muted');
    const v = focusEl.querySelector('.ms-video');
    if (v) v.muted = false;
    const label = focusEl.querySelector('.ms-audio-state');
    if (label) label.textContent = 'Audio';
  }
  TwitchX.multiState.audioFocus = idx;
}

function switchMultiChat(idx) {
  const slot = TwitchX.multiState.slots[idx];
  if (!slot) return;
  const input = document.getElementById('ms-chat-input');
  const hadFocus = document.activeElement === input;
  document.getElementById('ms-chat-input').disabled = true;
  document.getElementById('ms-chat-send-btn').disabled = true;
  document.querySelectorAll('.ms-slot').forEach(function(el) {
    el.classList.remove('chat-focus');
  });
  const el = _getMultiSlotEl(idx);
  if (el) el.classList.add('chat-focus');
  TwitchX.multiState.chatSlot = idx;
  if (TwitchX.setChatNotice) {
    TwitchX.setChatNotice('Switching chat...', 'connecting', 'multi');
  } else {
    document.getElementById('ms-chat-messages').replaceChildren();
  }
  if (TwitchX.clearChatBatch) TwitchX.clearChatBatch();
  document.getElementById('ms-chat-title').textContent = slot.channel;
  if (TwitchX.api) {
    TwitchX.api.stop_chat();
    TwitchX.api.start_chat(slot.channel, slot.platform);
  }
  if (!TwitchX.multiState.chatVisible) toggleMsChat();
  if (hadFocus) {
    requestAnimationFrame(function() {
      document.getElementById('ms-chat-input').focus();
    });
  }
}

function toggleMsChat() {
  TwitchX.multiState.chatVisible = !TwitchX.multiState.chatVisible;
  document.getElementById('ms-chat-panel').classList.toggle('hidden', !TwitchX.multiState.chatVisible);
}

function toggleMsSlotFullscreen(idx) {
  const slotEl = _getMultiSlotEl(idx);
  const video = slotEl ? slotEl.querySelector('.ms-video') : null;

  // Exit Safari Video Presentation Mode (WKWebView)
  if (video && video.webkitPresentationMode === 'fullscreen') {
    if (typeof video.webkitSetPresentationMode === 'function') {
      video.webkitSetPresentationMode('inline');
    }
    return;
  }

  // Exit if already fullscreen
  if (document.fullscreenElement || document.webkitFullscreenElement) {
    if (document.exitFullscreen) document.exitFullscreen();
    else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
    return;
  }
  if (!TwitchX.multiState.slots[idx]) return;
  if (!slotEl) return;
  if (!video) return;
  // webkitEnterFullscreen is the most reliable path in WKWebView (uses native AVKit)
  if (video.webkitEnterFullscreen) {
    video.webkitEnterFullscreen();
  } else if (video.requestFullscreen) {
    video.requestFullscreen();
  } else if (video.webkitRequestFullscreen) {
    video.webkitRequestFullscreen();
  }
}

function _createMultiSlot(idx) {
  const slot = document.createElement('div');
  slot.className = 'ms-slot ms-state-empty audio-muted';
  slot.setAttribute('data-slot-idx', idx);
  slot.dataset.state = 'empty';
  slot.setAttribute('aria-label', 'Multi-stream slot ' + (idx + 1));
  slot.tabIndex = -1;

  const empty = document.createElement('div');
  empty.className = 'ms-slot-empty';
  const addBtn = document.createElement('button');
  addBtn.className = 'ms-add-btn';
  addBtn.dataset.slot = idx;
  TwitchX.setIconOnly(addBtn, 'plus', 14);
  const span = document.createElement('span');
  span.textContent = 'Add Stream';
  addBtn.appendChild(span);
  const hint = document.createElement('p');
  hint.className = 'ms-empty-hint';
  hint.textContent = 'Drop a channel here or choose a platform.';
  empty.appendChild(addBtn);
  empty.appendChild(hint);

  slot.draggable = true;
  slot.addEventListener('dragstart', function(e) {
    const slotData = TwitchX.multiState.slots[idx];
    if (!slotData || e.target.closest('button, input, select, video')) {
      e.preventDefault();
      return;
    }
    slot.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', JSON.stringify({
      sourceSlot: idx,
      login: slotData.channel,
      platform: slotData.platform,
      quality: slotData.quality,
    }));
  });
  slot.addEventListener('dragend', function() {
    slot.classList.remove('dragging');
    document.querySelectorAll('.ms-slot.drag-over').forEach(function(el) {
      el.classList.remove('drag-over');
    });
  });
  slot.addEventListener('dragover', function(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    slot.classList.add('drag-over');
  });
  slot.addEventListener('dragleave', function(e) {
    if (!slot.contains(e.relatedTarget)) {
      slot.classList.remove('drag-over');
    }
  });
  slot.addEventListener('drop', function(e) {
    e.preventDefault();
    slot.classList.remove('drag-over');
    try {
      const data = JSON.parse(e.dataTransfer.getData('text/plain'));
      if (data && typeof data.sourceSlot === 'number') {
        _swapMultiSlots(data.sourceSlot, idx);
      } else if (data && data.login) {
        addMultiSlot(idx, data.login, data.platform || 'twitch');
      }
    } catch (_) {}
  });

  slot.appendChild(empty);

  const form = document.createElement('div');
  form.className = 'ms-add-form hidden';

  const input = document.createElement('input');
  input.className = 'ms-add-input';
  input.type = 'text';
  input.placeholder = 'channel name';
  input.maxLength = 100;
  input.autocomplete = 'off';
  input.setAttribute('aria-label', 'Channel name for slot ' + (idx + 1));
  form.appendChild(input);
  const select = document.createElement('select');
  select.className = 'ms-add-platform';
  select.setAttribute('aria-label', 'Platform for slot ' + (idx + 1));
  const optTwitch = document.createElement('option');
  optTwitch.value = 'twitch';
  optTwitch.textContent = 'Twitch';
  select.appendChild(optTwitch);
  const optKick = document.createElement('option');
  optKick.value = 'kick';
  optKick.textContent = 'Kick';
  select.appendChild(optKick);
  const optYoutube = document.createElement('option');
  optYoutube.value = 'youtube';
  optYoutube.textContent = 'YouTube live';
  select.appendChild(optYoutube);
  form.appendChild(select);
  const note = document.createElement('div');
  note.className = 'ms-platform-note';
  note.textContent = 'YouTube works when the live stream is already loaded in TwitchX.';
  form.appendChild(note);
  const btns = document.createElement('div');
  btns.className = 'ms-form-btns';
  const confirm = document.createElement('button');
  confirm.className = 'ms-confirm-btn';
  confirm.dataset.slot = idx;
  confirm.textContent = 'Add';
  btns.appendChild(confirm);
  const cancel = document.createElement('button');
  cancel.className = 'ms-cancel-btn';
  cancel.dataset.slot = idx;
  cancel.textContent = 'Cancel';
  btns.appendChild(cancel);
  form.appendChild(btns);
  slot.appendChild(form);

  const active = document.createElement('div');
  active.className = 'ms-slot-active';
  const video = document.createElement('video');
  video.className = 'ms-video';
  video.autoplay = true;
  video.muted = true;
  video.playsInline = true;
  active.appendChild(video);

  const loading = document.createElement('div');
  loading.className = 'ms-loading';
  const spinner = document.createElement('span');
  spinner.className = 'ms-spinner';
  loading.appendChild(spinner);
  loading.appendChild(document.createTextNode('Loading stream...'));
  active.appendChild(loading);
  const errEl = document.createElement('div');
  errEl.className = 'ms-error-msg';
  active.appendChild(errEl);
  const overlay = document.createElement('div');
  overlay.className = 'ms-overlay';
  const info = document.createElement('div');
  info.className = 'ms-slot-info';
  const status = document.createElement('span');
  status.className = 'ms-slot-status';
  status.textContent = 'Empty';
  info.appendChild(status);
  const badge = document.createElement('span');
  badge.className = 'ms-platform-badge';
  info.appendChild(badge);
  const name = document.createElement('span');
  name.className = 'ms-channel-name';
  info.appendChild(name);
  const audioState = document.createElement('span');
  audioState.className = 'ms-audio-state';
  audioState.textContent = 'Muted';
  info.appendChild(audioState);
  overlay.appendChild(info);
  const controls = document.createElement('div');
  controls.className = 'ms-slot-controls';
  const audioBtn = document.createElement('button');
  audioBtn.className = 'ms-audio-btn';
  audioBtn.dataset.slot = idx;
  audioBtn.title = 'Focus audio';
  audioBtn.setAttribute('aria-label', 'Focus audio');
  TwitchX.setIconOnly(audioBtn, 'volume', 14);
  controls.appendChild(audioBtn);
  const chatBtn = document.createElement('button');
  chatBtn.className = 'ms-chat-sw-btn';
  chatBtn.dataset.slot = idx;
  chatBtn.title = 'Switch chat';
  chatBtn.setAttribute('aria-label', 'Switch chat');
  TwitchX.setIconOnly(chatBtn, 'chat', 14);
  controls.appendChild(chatBtn);
  const fsBtn = document.createElement('button');
  fsBtn.className = 'ms-fullscreen-btn';
  fsBtn.dataset.slot = idx;
  fsBtn.title = 'Fullscreen (double-click)';
  fsBtn.setAttribute('aria-label', 'Fullscreen');
  TwitchX.setIconOnly(fsBtn, 'fullscreen', 14);
  controls.appendChild(fsBtn);
  const pipBtn = document.createElement('button');
  pipBtn.className = 'ms-pip-btn';
  pipBtn.dataset.slot = idx;
  pipBtn.title = 'Picture-in-Picture';
  pipBtn.setAttribute('aria-label', 'Picture in Picture');
  TwitchX.setIconOnly(pipBtn, 'pip', 14);
  controls.appendChild(pipBtn);
  _bindSlotPiPEvents(video, pipBtn);
  const removeBtn = document.createElement('button');
  removeBtn.className = 'ms-remove-btn';
  removeBtn.dataset.slot = idx;
  removeBtn.title = 'Remove';
  removeBtn.setAttribute('aria-label', 'Remove');
  TwitchX.setIconOnly(removeBtn, 'close', 14);
  controls.appendChild(removeBtn);
  overlay.appendChild(controls);
  active.appendChild(overlay);
  slot.appendChild(active);

  return slot;
}

/* ── Multistream Health Monitor ─────────────────────────── */

function startMultiHealthMonitor() {
  stopMultiHealthMonitor();
  TwitchX._multiHealthTimer = setInterval(checkMultiHealth, 60000);
}

function stopMultiHealthMonitor() {
  if (TwitchX._multiHealthTimer) {
    clearInterval(TwitchX._multiHealthTimer);
    TwitchX._multiHealthTimer = null;
  }
}

function checkMultiHealth() {
  if (!TwitchX.multiState.open) return;
  for (let i = 0; i < 4; i++) {
    if (!TwitchX.multiState.slots[i]) continue;
    const slotEl = document.querySelector('.ms-slot[data-slot-idx="' + i + '"]');
    if (!slotEl) continue;
    const video = slotEl.querySelector('.ms-video');
    if (!video || !video.src || video.paused) continue;

    // Frozen detection (120s threshold — 2 checks at 60s interval)
    const lastTime = slotEl.dataset._lastTime;
    const nowTime = video.currentTime;
    if (lastTime !== undefined && Math.abs(nowTime - parseFloat(lastTime)) < 0.5 && video.readyState >= 2) {
      const frozenCount = parseInt(slotEl.dataset._frozenCount || '0', 10) + 1;
      if (frozenCount >= 2) {
        _reloadMultiSlot(i, 'frozen');
        continue;
      }
      slotEl.dataset._frozenCount = String(frozenCount);
    } else {
      slotEl.dataset._frozenCount = '0';
    }
    slotEl.dataset._lastTime = String(nowTime);

    // Buffer accumulation
    if (video.buffered && video.buffered.length > 0) {
      const bufferedEnd = video.buffered.end(video.buffered.length - 1);
      const bufferedDrift = bufferedEnd - video.currentTime;
      if (bufferedDrift > 180) {
        _reloadMultiSlot(i, 'buffer-overflow');
        continue;
      }
    }

    // Live-edge drift
    if (video.seekable && video.seekable.length > 0) {
      const liveEdge = video.seekable.end(video.seekable.length - 1);
      const drift = liveEdge - video.currentTime;
      if (drift > 120) {
        video.currentTime = liveEdge - 2;
        console.log('[VideoHealth] multistream slot', i, 'caught up to live edge');
      }
    }
  }
}

function _reloadMultiSlot(idx, reason) {
  const slotEl = document.querySelector('.ms-slot[data-slot-idx="' + idx + '"]');
  if (!slotEl) return;
  const video = slotEl.querySelector('.ms-video');
  if (!video || !video.src) return;

  // Do not destroy the DOM element while in PiP or fullscreen — that kills the session
  function _softResetSlot(label) {
    console.log('[VideoHealth] multistream slot', idx, reason, 'soft reset (' + label + ') at', new Date().toISOString());
    const oldSrc = video.src;
    const wasMuted = video.muted;
    video.pause();
    video.removeAttribute('src');
    video.load();
    video.src = oldSrc;
    video.muted = wasMuted;
    video.play().catch(function(e) {
      console.warn('[Multistream] slot', idx, 'soft reset play() rejected:', e && e.message || e);
    });
    delete slotEl.dataset._lastTime;
    delete slotEl.dataset._frozenCount;
  }

  if (TwitchX.isVideoPiP && TwitchX.isVideoPiP(video)) {
    _softResetSlot('PiP');
    return;
  }

  if (video.webkitPresentationMode === 'fullscreen') {
    _softResetSlot('fullscreen');
    return;
  }

  console.log('[VideoHealth] multistream slot', idx, reason, 'reset at', new Date().toISOString());

  const oldSrc = video.src;
  const wasMuted = video.muted;

  video.pause();
  video.removeAttribute('src');
  video.load();
  video.remove();

  const fresh = document.createElement('video');
  fresh.className = 'ms-video';
  fresh.autoplay = true;
  fresh.muted = wasMuted;
  fresh.playsInline = true;

  const active = slotEl.querySelector('.ms-slot-active');
  active.insertBefore(fresh, active.querySelector('.ms-loading'));

  const pipBtn = slotEl.querySelector('.ms-pip-btn');
  _bindSlotPiPEvents(fresh, pipBtn);

  fresh.src = oldSrc;
  fresh.play().catch(function(e) {
    console.warn('[Multistream] slot', idx, 'reload play() rejected:', e && e.message || e);
  });

  delete slotEl.dataset._lastTime;
  delete slotEl.dataset._frozenCount;
}

TwitchX.openMultistreamView = openMultistreamView;
TwitchX.closeMultistreamView = closeMultistreamView;
TwitchX.toggleMsSidebar = toggleMsSidebar;
TwitchX.addMultiSlot = addMultiSlot;
TwitchX.removeMultiSlot = removeMultiSlot;
TwitchX.setAudioFocus = setAudioFocus;
TwitchX.switchMultiChat = switchMultiChat;
TwitchX.openFirstEmptyMultiSlot = openFirstEmptyMultiSlot;
TwitchX._setMultiSlotState = _setMultiSlotState;
TwitchX._updateMultiGridLayout = _updateMultiGridLayout;
TwitchX._applyMultistreamPreset = _applyMultistreamPreset;
TwitchX._loadMultistreamPresets = _loadMultistreamPresets;
TwitchX.setMultistreamPreset = setMultistreamPreset;
TwitchX.toggleMsChat = toggleMsChat;
TwitchX.toggleMsSlotFullscreen = toggleMsSlotFullscreen;
TwitchX._clearMultiSlot = _clearMultiSlot;
TwitchX._swapMultiSlots = _swapMultiSlots;
TwitchX._createMultiSlot = _createMultiSlot;
TwitchX.startMultiHealthMonitor = startMultiHealthMonitor;
TwitchX.stopMultiHealthMonitor = stopMultiHealthMonitor;
TwitchX.checkMultiHealth = checkMultiHealth;
TwitchX._reloadMultiSlot = _reloadMultiSlot;

window.onMultistreamPresetChanged = function(data) {
  if (data && data.preset) {
    _applyMultistreamPreset(data.preset);
  }
};
