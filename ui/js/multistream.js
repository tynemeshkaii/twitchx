const TwitchX = window.TwitchX || {};

function openMultistreamView() {
  TwitchX.multiState.open = true;
  if (document.getElementById('player-view').classList.contains('active')) {
    TwitchX.hidePlayerView();
  }
  document.getElementById('browse-view').classList.add('hidden');
  document.getElementById('channel-view').classList.add('hidden');
  document.getElementById('toolbar').classList.add('hidden');
  document.getElementById('stream-grid').classList.add('hidden');
  document.getElementById('multistream-view').classList.remove('hidden');
}

function closeMultistreamView() {
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
  document.getElementById('multistream-view').classList.remove('ms-sidebar-open');
  document.getElementById('multistream-view').classList.add('hidden');
  document.getElementById('ms-chat-panel').classList.add('hidden');
  document.getElementById('toolbar').classList.remove('hidden');
  document.getElementById('stream-grid').classList.remove('hidden');
  document.getElementById('ms-chat-messages').replaceChildren();
  const btn = document.getElementById('ms-sidebar-btn');
  if (btn) btn.classList.remove('active');
}

function toggleMsSidebar() {
  const main = document.getElementById('main');
  const mv = document.getElementById('multistream-view');
  const btn = document.getElementById('ms-sidebar-btn');
  const open = main.classList.toggle('ms-sidebar-open');
  mv.classList.toggle('ms-sidebar-open', open);
  if (btn) btn.classList.toggle('active', open);
}

function _clearMultiSlot(idx) {
  const slotEl = document.querySelector('.ms-slot[data-slot-idx="' + idx + '"]');
  if (!slotEl) return;
  const video = slotEl.querySelector('.ms-video');
  if (video) { video.pause(); video.removeAttribute('src'); video.load(); }
  slotEl.querySelector('.ms-slot-active').style.display = 'none';
  slotEl.querySelector('.ms-slot-empty').style.display = '';
  slotEl.querySelector('.ms-add-form').style.display = 'none';
  slotEl.classList.remove('audio-focus', 'chat-focus');
}

function addMultiSlot(idx, channel, platform) {
  const cfg = TwitchX.api ? TwitchX.api.get_full_config_for_settings() : {};
  const quality = (cfg && cfg.settings && cfg.settings.quality) || 'best';
  TwitchX.multiState.slots[idx] = { channel: channel, platform: platform, quality: quality, title: '' };
  const slotEl = document.querySelector('.ms-slot[data-slot-idx="' + idx + '"]');
  if (!slotEl) return;
  slotEl.querySelector('.ms-slot-empty').style.display = 'none';
  slotEl.querySelector('.ms-add-form').style.display = 'none';
  const active = slotEl.querySelector('.ms-slot-active');
  active.style.display = 'block';
  active.querySelector('.ms-loading').style.display = '';
  active.querySelector('.ms-error-msg').style.display = 'none';
  active.querySelector('.ms-video').muted = true;
  if (TwitchX.api) TwitchX.api.add_multi_slot(idx, channel, platform, quality);
}

function removeMultiSlot(idx) {
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
  }
}

function setAudioFocus(idx) {
  document.querySelectorAll('.ms-slot').forEach(function(el) {
    el.classList.remove('audio-focus');
    const v = el.querySelector('.ms-video');
    if (v) v.muted = true;
  });
  const focusEl = document.querySelector('.ms-slot[data-slot-idx="' + idx + '"]');
  if (focusEl) {
    focusEl.classList.add('audio-focus');
    const v = focusEl.querySelector('.ms-video');
    if (v) v.muted = false;
  }
  TwitchX.multiState.audioFocus = idx;
}

function switchMultiChat(idx) {
  const slot = TwitchX.multiState.slots[idx];
  if (!slot) return;
  document.getElementById('ms-chat-input').disabled = true;
  document.getElementById('ms-chat-send-btn').disabled = true;
  document.querySelectorAll('.ms-slot').forEach(function(el) {
    el.classList.remove('chat-focus');
  });
  const el = document.querySelector('.ms-slot[data-slot-idx="' + idx + '"]');
  if (el) el.classList.add('chat-focus');
  TwitchX.multiState.chatSlot = idx;
  document.getElementById('ms-chat-messages').replaceChildren();
  document.getElementById('ms-chat-title').textContent = slot.channel;
  if (TwitchX.api) {
    TwitchX.api.stop_chat();
    TwitchX.api.start_chat(slot.channel, slot.platform);
  }
  if (!TwitchX.multiState.chatVisible) toggleMsChat();
}

function toggleMsChat() {
  TwitchX.multiState.chatVisible = !TwitchX.multiState.chatVisible;
  document.getElementById('ms-chat-panel').classList.toggle('hidden', !TwitchX.multiState.chatVisible);
}

function toggleMsSlotFullscreen(idx) {
  // Exit if already fullscreen
  if (document.fullscreenElement || document.webkitFullscreenElement) {
    if (document.exitFullscreen) document.exitFullscreen();
    else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
    return;
  }
  if (!TwitchX.multiState.slots[idx]) return;
  const slotEl = document.querySelector('.ms-slot[data-slot-idx="' + idx + '"]');
  if (!slotEl) return;
  const video = slotEl.querySelector('.ms-video');
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
  slot.className = 'ms-slot';
  slot.setAttribute('data-slot-idx', idx);
  slot.tabIndex = -1;

  const empty = document.createElement('div');
  empty.className = 'ms-slot-empty';
  const addBtn = document.createElement('button');
  addBtn.className = 'ms-add-btn';
  addBtn.dataset.slot = idx;
  addBtn.textContent = '+';
  const span = document.createElement('span');
  span.textContent = 'Add Stream';
  addBtn.appendChild(span);
  empty.appendChild(addBtn);
  slot.appendChild(empty);

  const form = document.createElement('div');
  form.className = 'ms-add-form';
  form.style.display = 'none';
  const input = document.createElement('input');
  input.className = 'ms-add-input';
  input.type = 'text';
  input.placeholder = 'channel name';
  input.maxLength = 100;
  input.autocomplete = 'off';
  form.appendChild(input);
  const select = document.createElement('select');
  select.className = 'ms-add-platform';
  const optTwitch = document.createElement('option');
  optTwitch.value = 'twitch';
  optTwitch.textContent = 'Twitch';
  select.appendChild(optTwitch);
  const optKick = document.createElement('option');
  optKick.value = 'kick';
  optKick.textContent = 'Kick';
  select.appendChild(optKick);
  form.appendChild(select);
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
  loading.textContent = 'Loading stream...';
  active.appendChild(loading);
  const errEl = document.createElement('div');
  errEl.className = 'ms-error-msg';
  active.appendChild(errEl);
  const overlay = document.createElement('div');
  overlay.className = 'ms-overlay';
  const info = document.createElement('div');
  info.className = 'ms-slot-info';
  const badge = document.createElement('span');
  badge.className = 'ms-platform-badge';
  info.appendChild(badge);
  const name = document.createElement('span');
  name.className = 'ms-channel-name';
  info.appendChild(name);
  overlay.appendChild(info);
  const controls = document.createElement('div');
  controls.className = 'ms-slot-controls';
  const audioBtn = document.createElement('button');
  audioBtn.className = 'ms-audio-btn';
  audioBtn.dataset.slot = idx;
  audioBtn.title = 'Focus audio';
  audioBtn.setAttribute('aria-label', 'Focus audio');
  audioBtn.textContent = '\uD83D\uDD0A';
  controls.appendChild(audioBtn);
  const chatBtn = document.createElement('button');
  chatBtn.className = 'ms-chat-sw-btn';
  chatBtn.dataset.slot = idx;
  chatBtn.title = 'Switch chat';
  chatBtn.setAttribute('aria-label', 'Switch chat');
  chatBtn.textContent = '\uD83D\uDCAC';
  controls.appendChild(chatBtn);
  const fsBtn = document.createElement('button');
  fsBtn.className = 'ms-fullscreen-btn';
  fsBtn.dataset.slot = idx;
  fsBtn.title = 'Fullscreen (double-click)';
  fsBtn.setAttribute('aria-label', 'Fullscreen');
  fsBtn.textContent = '\u26F6';
  controls.appendChild(fsBtn);
  const pipBtn = document.createElement('button');
  pipBtn.className = 'ms-pip-btn';
  pipBtn.dataset.slot = idx;
  pipBtn.title = 'Picture-in-Picture';
  pipBtn.setAttribute('aria-label', 'Picture in Picture');
  pipBtn.textContent = '\u29C9';
  controls.appendChild(pipBtn);
  const removeBtn = document.createElement('button');
  removeBtn.className = 'ms-remove-btn';
  removeBtn.dataset.slot = idx;
  removeBtn.title = 'Remove';
  removeBtn.setAttribute('aria-label', 'Remove');
  removeBtn.innerHTML = '&times;';
  controls.appendChild(removeBtn);
  overlay.appendChild(controls);
  active.appendChild(overlay);
  slot.appendChild(active);

  return slot;
}

TwitchX.openMultistreamView = openMultistreamView;
TwitchX.closeMultistreamView = closeMultistreamView;
TwitchX.toggleMsSidebar = toggleMsSidebar;
TwitchX.addMultiSlot = addMultiSlot;
TwitchX.removeMultiSlot = removeMultiSlot;
TwitchX.setAudioFocus = setAudioFocus;
TwitchX.switchMultiChat = switchMultiChat;
TwitchX.toggleMsChat = toggleMsChat;
TwitchX.toggleMsSlotFullscreen = toggleMsSlotFullscreen;
TwitchX._clearMultiSlot = _clearMultiSlot;
TwitchX._createMultiSlot = _createMultiSlot;
