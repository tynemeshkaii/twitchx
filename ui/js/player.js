window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

function showPlayerView() {
  document.getElementById('toolbar').style.display = 'none';
  document.getElementById('stream-grid').style.display = 'none';
  document.getElementById('empty-state').style.display = 'none';
  document.getElementById('player-view').classList.add('active');

  TwitchX.state.watchingChannel = TwitchX.state.selectedChannel;
  document.getElementById('watch-btn').classList.add('active');
  document.getElementById('stop-player-btn').style.display = 'inline-flex';
  document.getElementById('live-dot').classList.add('visible');

  const chatPanel = document.getElementById('chat-panel');
  const chatHandle = document.getElementById('chat-resize-handle');
  const toggleBtn = document.getElementById('toggle-chat-btn');
  if (!TwitchX.state.playerHasChat) {
    chatPanel.classList.add('hidden');
    if (chatHandle) chatHandle.style.display = 'none';
    if (toggleBtn) toggleBtn.style.display = 'none';
  } else {
    if (toggleBtn) toggleBtn.style.display = '';
    const cfg = TwitchX.api ? TwitchX.api.get_full_config_for_settings() : null;
    if (cfg && cfg.chat_width) chatPanel.style.width = cfg.chat_width + 'px';
    if (cfg && cfg.chat_visible === false) {
      chatPanel.classList.add('hidden');
      if (chatHandle) chatHandle.style.display = 'none';
    } else {
      chatPanel.classList.remove('hidden');
      if (chatHandle) chatHandle.style.display = '';
    }
  }
  updateChatInput();

  TwitchX.renderSidebar();
  TwitchX.startVideoHealthMonitor();
  TwitchX.startFpsMonitor();
}

function hidePlayerView() {
  TwitchX.stopVideoHealthMonitor();
  TwitchX.stopFpsMonitor();

  const video = document.getElementById('stream-video');
  video.pause();
  video.removeAttribute('src');
  video.load();
  video.style.display = '';

  // Restore IINA button
  const iinaBtn = document.getElementById('watch-external-btn');
  if (iinaBtn) { iinaBtn.disabled = false; iinaBtn.style.opacity = ''; }

  // Clear chat
  TwitchX.clearChatMessages();
  if (TwitchX.clearChatBatch) TwitchX.clearChatBatch();
  if (TwitchX.api) TwitchX.api.stop_chat();

  document.getElementById('player-view').classList.remove('active');
  document.getElementById('toolbar').style.display = '';
  document.getElementById('stream-grid').style.display = '';

  TwitchX.state.watchingChannel = null;
  TwitchX.state.playerPlatform = null;
  TwitchX.state.playerHasChat = true;
  TwitchX.chatPlatform = null;
  TwitchX.chatAuthenticated = false;
  TwitchX.state.playerState = 'idle';
  document.getElementById('watch-btn').classList.remove('active');
  document.getElementById('stop-player-btn').style.display = 'none';
  document.getElementById('live-dot').classList.remove('visible');
  document.getElementById('toggle-chat-btn').style.display = '';
  TwitchX.setStatus('', 'info');
  TwitchX.renderGrid();
  TwitchX.renderSidebar();
}

function getActiveVideo() {
  if (document.getElementById('player-view').classList.contains('active')) {
    return document.getElementById('stream-video');
  }
  if (TwitchX.multiState.open && TwitchX.multiState.audioFocus >= 0) {
    const slotEl = document.querySelector('.ms-slot[data-slot-idx="' + TwitchX.multiState.audioFocus + '"]');
    return slotEl ? slotEl.querySelector('.ms-video') : null;
  }
  return null;
}

function adjustVolume(delta) {
  const video = getActiveVideo();
  if (!video) return;
  video.muted = false;
  video.volume = Math.max(0, Math.min(1, video.volume + delta));
  TwitchX.setStatus('Volume: ' + Math.round(video.volume * 100) + '%', 'info');
}

function toggleMute() {
  const video = getActiveVideo();
  if (!video) return;
  video.muted = !video.muted;
  TwitchX.setStatus(video.muted ? 'Muted' : 'Unmuted', 'info');
}

function cycleStream(dir) {
  const streams = TwitchX.getFilteredSortedStreams();
  if (streams.length === 0) return;
  let idx = streams.findIndex(function(s) { return s.login === TwitchX.state.selectedChannel; });
  if (idx === -1) {
    idx = dir > 0 ? 0 : streams.length - 1;
  } else {
    idx = (idx + dir + streams.length) % streams.length;
  }
  TwitchX.selectChannel(streams[idx].login);
}

function togglePiP(video) {
  if (!video) return;
  // Webkit path — most reliable in WKWebView on macOS
  if (typeof video.webkitSupportsPresentationMode === 'function' &&
      video.webkitSupportsPresentationMode('picture-in-picture')) {
    const next = video.webkitPresentationMode === 'picture-in-picture' ? 'inline' : 'picture-in-picture';
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

function toggleVideoFullscreen() {
  const video = document.getElementById('stream-video');

  // Exit fullscreen
  if (document.fullscreenElement || document.webkitFullscreenElement) {
    if (document.exitFullscreen) document.exitFullscreen();
    else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
    return;
  }

  // Native video fullscreen (works in WKWebView without extra preferences)
  if (video.webkitEnterFullscreen) {
    video.webkitEnterFullscreen();
  } else if (video.requestFullscreen) {
    video.requestFullscreen();
  } else if (video.webkitRequestFullscreen) {
    video.webkitRequestFullscreen();
  }
}

function toggleChatPanel() {
  if (!TwitchX.state.playerHasChat) return;
  const panel = document.getElementById('chat-panel');
  const handle = document.getElementById('chat-resize-handle');
  panel.classList.toggle('hidden');
  if (handle) handle.style.display = panel.classList.contains('hidden') ? 'none' : '';
  if (TwitchX.api) TwitchX.api.save_chat_visibility(!panel.classList.contains('hidden'));
}

function updateChatInput() {
  const input = document.getElementById('chat-input');
  const btn = document.getElementById('chat-send-btn');
  if (!input || !btn) return;
  const platform = TwitchX.chatPlatform || TwitchX.state.playerPlatform || 'twitch';
  const chatUser = platform === 'kick' ? TwitchX.state.kickUser : TwitchX.state.currentUser;
  const kickHasChatWrite = (TwitchX.state.kickScopes || '').split(/\s+/).indexOf('chat:write') !== -1;
  const canSend = !!chatUser && TwitchX.chatAuthenticated;
  input.disabled = !canSend;
  btn.disabled = !canSend;
  if (!chatUser) {
    input.placeholder = platform === 'kick' ? 'Log in to Kick to chat' : 'Log in to chat';
  } else if (!TwitchX.chatAuthenticated) {
    if (platform === 'kick' && !kickHasChatWrite) {
      input.placeholder = 'Kick token is missing chat:write (enable it for the app and re-login)';
    } else {
      input.placeholder = platform === 'kick'
        ? 'Kick chat is read-only (re-login to grant chat access)'
        : 'Chat is read-only (re-login to send)';
    }
  } else {
    input.placeholder = 'Send a message...';
  }
}

/* ── Video Health Monitor ───────────────────────────────── */

function startVideoHealthMonitor() {
  stopVideoHealthMonitor();
  TwitchX._healthMonitorTimer = setInterval(checkVideoHealth, 60000);
}

function stopVideoHealthMonitor() {
  if (TwitchX._healthMonitorTimer) {
    clearInterval(TwitchX._healthMonitorTimer);
    TwitchX._healthMonitorTimer = null;
  }
}

function checkVideoHealth() {
  const video = document.getElementById('stream-video');
  if (!video || video.paused || !video.src) return;

  // Seek to live edge if we're lagging behind (>120s back-buffer drift)
  if (video.seekable && video.seekable.length > 0) {
    const liveEdge = video.seekable.end(video.seekable.length - 1);
    const drift = liveEdge - video.currentTime;
    if (drift > 120) {
      video.currentTime = liveEdge - 2;
      TwitchX.setStatus('Caught up to live edge', 'info');
      return;
    }
  }

  // If buffered end is far ahead, do a soft reset to clear accumulated buffers
  if (video.buffered && video.buffered.length > 0) {
    const bufferedEnd = video.buffered.end(video.buffered.length - 1);
    const bufferedDrift = bufferedEnd - video.currentTime;
    if (bufferedDrift > 300) {
      softResetVideo();
      TwitchX.setStatus('Stream buffer cleared for smooth playback', 'info');
      return;
    }
  }
}

function softResetVideo() {
  const video = document.getElementById('stream-video');
  if (!video || !video.src) return;
  const currentSrc = video.src;
  const wasMuted = video.muted;
  const currentVolume = video.volume;
  video.pause();
  video.removeAttribute('src');
  video.load();
  video.src = currentSrc;
  video.muted = wasMuted;
  video.volume = currentVolume;
  video.play().catch(function() {});
}

/* ── FPS Monitor ────────────────────────────────────────── */

function startFpsMonitor() {
  stopFpsMonitor();
  TwitchX._fpsBadFrameCount = 0;
  TwitchX._fpsLastTimestamp = 0;
  TwitchX._fpsRafId = 0;

  function tick(timestamp) {
    if (!TwitchX._fpsRafId) return;
    if (TwitchX._fpsLastTimestamp) {
      const delta = timestamp - TwitchX._fpsLastTimestamp;
      if (delta > 50) { // < 20 FPS
        TwitchX._fpsBadFrameCount += 1;
        if (TwitchX._fpsBadFrameCount >= 150) { // ~5s sustained bad frames @ 30fps check
          softResetVideo();
          TwitchX.setStatus('Auto-recovered playback smoothness', 'info');
          TwitchX._fpsBadFrameCount = 0;
        }
      } else {
        TwitchX._fpsBadFrameCount = Math.max(0, TwitchX._fpsBadFrameCount - 1);
      }
    }
    TwitchX._fpsLastTimestamp = timestamp;
    TwitchX._fpsRafId = requestAnimationFrame(tick);
  }
  TwitchX._fpsRafId = requestAnimationFrame(tick);
}

function stopFpsMonitor() {
  if (TwitchX._fpsRafId) {
    cancelAnimationFrame(TwitchX._fpsRafId);
    TwitchX._fpsRafId = 0;
  }
  TwitchX._fpsLastTimestamp = 0;
  TwitchX._fpsBadFrameCount = 0;
}

TwitchX.showPlayerView = showPlayerView;
TwitchX.hidePlayerView = hidePlayerView;
TwitchX.getActiveVideo = getActiveVideo;
TwitchX.adjustVolume = adjustVolume;
TwitchX.toggleMute = toggleMute;
TwitchX.cycleStream = cycleStream;
TwitchX.togglePiP = togglePiP;
TwitchX.toggleVideoFullscreen = toggleVideoFullscreen;
TwitchX.toggleChatPanel = toggleChatPanel;
TwitchX.updateChatInput = updateChatInput;
TwitchX.startVideoHealthMonitor = startVideoHealthMonitor;
TwitchX.stopVideoHealthMonitor = stopVideoHealthMonitor;
TwitchX.checkVideoHealth = checkVideoHealth;
TwitchX.softResetVideo = softResetVideo;
TwitchX.startFpsMonitor = startFpsMonitor;
TwitchX.stopFpsMonitor = stopFpsMonitor;
