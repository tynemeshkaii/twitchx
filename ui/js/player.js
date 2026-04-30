window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

/* ── Video element abstraction ──────────────────────────── */

TwitchX._playerVideo = null;

function getPlayerVideo() {
  return TwitchX._playerVideo || document.getElementById('stream-video');
}

/* ── Player view ────────────────────────────────────────── */

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
  TwitchX.startFrozenMonitor();
  TwitchX.startProactiveReset();
}

function hidePlayerView() {
  TwitchX.stopVideoHealthMonitor();
  TwitchX.stopFpsMonitor();
  TwitchX.stopFrozenMonitor();
  TwitchX.stopProactiveReset();

  const video = getPlayerVideo();
  if (video) {
    video.pause();
    video.removeAttribute('src');
    video.load();
    video.style.display = '';

    // Phase 6: guaranteed cleanup — destroy the MediaPlayer
    video.remove();
  }

  const fresh = document.createElement('video');
  fresh.id = 'stream-video';
  fresh.autoplay = true;
  fresh.controls = true;
  fresh.playsInline = true;
  document.getElementById('player-content').appendChild(fresh);
  TwitchX._playerVideo = null;

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
    return getPlayerVideo();
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
  const video = getPlayerVideo();

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
  const video = getPlayerVideo();
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

  // If buffered end is far ahead, do a gentle reset to clear accumulated buffers
  if (video.buffered && video.buffered.length > 0) {
    const bufferedEnd = video.buffered.end(video.buffered.length - 1);
    const bufferedDrift = bufferedEnd - video.currentTime;
    if (bufferedDrift > 180) {
      gentleResetVideo('buffer-overflow');
      TwitchX.setStatus('Stream buffer cleared for smooth playback', 'info');
      return;
    }
  }
}

/* ── Frozen Video Monitor ───────────────────────────────── */

function startFrozenMonitor() {
  stopFrozenMonitor();
  TwitchX._frozenLastTime = undefined;
  TwitchX._frozenStreak = 0;
  TwitchX._frozenTimer = setInterval(checkFrozenVideo, 10000);
}

function stopFrozenMonitor() {
  if (TwitchX._frozenTimer) {
    clearInterval(TwitchX._frozenTimer);
    TwitchX._frozenTimer = null;
  }
  TwitchX._frozenLastTime = undefined;
  TwitchX._frozenStreak = 0;
}

function checkFrozenVideo() {
  const video = getPlayerVideo();
  if (!video || video.paused || !video.src || video.readyState < 2) return;

  const now = video.currentTime;
  if (TwitchX._frozenLastTime !== undefined && now === TwitchX._frozenLastTime) {
    TwitchX._frozenStreak = (TwitchX._frozenStreak || 0) + 1;
    if (TwitchX._frozenStreak >= 1) { // 10 seconds frozen
      gentleResetVideo('frozen');
      TwitchX.setStatus('Auto-recovered playback smoothness', 'info');
      TwitchX._frozenStreak = 0;
      TwitchX._frozenLastTime = undefined;
      return;
    }
  } else {
    TwitchX._frozenStreak = 0;
  }
  TwitchX._frozenLastTime = now;
}

/* ── Gentle Video Reset (crossfade swap) ────────────────── */

function gentleResetVideo(reason) {
  const oldVideo = getPlayerVideo();
  if (!oldVideo || !oldVideo.src) return;

  // Prevent re-entrant calls from using the old element
  TwitchX._playerVideo = null;

  console.log('[VideoHealth]', reason, 'reset starting at', new Date().toISOString(),
    'src=', oldVideo.src.split('?')[0], 'currentTime=', oldVideo.currentTime);

  const container = oldVideo.parentNode;
  const savedSrc = oldVideo.src;
  const savedMuted = oldVideo.muted;
  const savedVolume = oldVideo.volume;

  const newVideo = document.createElement('video');
  newVideo.autoplay = true;
  newVideo.controls = true;
  newVideo.playsInline = true;
  newVideo.id = 'stream-video';
  newVideo.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;opacity:0;transition:opacity 0.15s';

  newVideo.src = savedSrc;
  newVideo.muted = true;
  newVideo.volume = savedVolume;

  container.insertBefore(newVideo, oldVideo);
  newVideo.play().catch(function() {});

  let swapped = false;

  function doSwap() {
    if (swapped) return;
    swapped = true;

    oldVideo.style.transition = 'opacity 0.15s';
    oldVideo.style.opacity = '0';
    newVideo.style.opacity = '1';

    setTimeout(function() {
      oldVideo.pause();
      oldVideo.removeAttribute('src');
      oldVideo.load();
      oldVideo.remove();

      newVideo.style.position = '';
      newVideo.style.top = '';
      newVideo.style.left = '';
      newVideo.style.width = '';
      newVideo.style.height = '';
      newVideo.style.transition = '';
      newVideo.muted = savedMuted;

      TwitchX._playerVideo = newVideo;
      console.log('[VideoHealth]', reason, 'reset completed');
    }, 160);
  }

  newVideo.addEventListener('playing', doSwap, { once: true });
  newVideo.addEventListener('loadeddata', doSwap, { once: true });

  setTimeout(function() {
    if (!swapped) doSwap();
  }, 2500);
}

/* ── Proactive Reset (30 min) ───────────────────────────── */

function startProactiveReset() {
  stopProactiveReset();
  function tick() {
    const video = getPlayerVideo();
    if (video && !video.paused && video.src) {
      gentleResetVideo('proactive');
    }
    TwitchX._proactiveTimer = setTimeout(tick, 30 * 60 * 1000);
  }
  TwitchX._proactiveTimer = setTimeout(tick, 30 * 60 * 1000);
}

function stopProactiveReset() {
  if (TwitchX._proactiveTimer) {
    clearTimeout(TwitchX._proactiveTimer);
    TwitchX._proactiveTimer = null;
  }
}

/* ── FPS Monitor ────────────────────────────────────────── */

function startFpsMonitor() {
  stopFpsMonitor();
  TwitchX._fpsBadFrameCount = 0;
  TwitchX._fpsLastTimestamp = 0;
  TwitchX._fpsRafId = 0;
  TwitchX._fpsConsecutiveBad = 0;

  function tick(timestamp) {
    if (!TwitchX._fpsRafId) return;
    if (document.hidden) {
      TwitchX._fpsLastTimestamp = timestamp;
      TwitchX._fpsRafId = requestAnimationFrame(tick);
      return;
    }
    const video = getPlayerVideo();
    if (!video || video.paused || video.readyState < 2) {
      TwitchX._fpsLastTimestamp = timestamp;
      TwitchX._fpsRafId = requestAnimationFrame(tick);
      return;
    }
    if (TwitchX._fpsLastTimestamp) {
      const delta = timestamp - TwitchX._fpsLastTimestamp;
      if (delta > 66) { // < 15 FPS
        TwitchX._fpsConsecutiveBad += 1;
        if (TwitchX._fpsConsecutiveBad >= 300) { // ~5s sustained
          gentleResetVideo('fps-drop');
          TwitchX.setStatus('Auto-recovered playback smoothness', 'info');
          TwitchX._fpsConsecutiveBad = 0;
        }
      } else {
        TwitchX._fpsConsecutiveBad = Math.max(0, TwitchX._fpsConsecutiveBad - 1);
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
  TwitchX._fpsConsecutiveBad = 0;
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
TwitchX.startFrozenMonitor = startFrozenMonitor;
TwitchX.stopFrozenMonitor = stopFrozenMonitor;
TwitchX.checkFrozenVideo = checkFrozenVideo;
TwitchX.gentleResetVideo = gentleResetVideo;
TwitchX.startFpsMonitor = startFpsMonitor;
TwitchX.stopFpsMonitor = stopFpsMonitor;
TwitchX.startProactiveReset = startProactiveReset;
TwitchX.stopProactiveReset = stopProactiveReset;
TwitchX.getPlayerVideo = getPlayerVideo;
