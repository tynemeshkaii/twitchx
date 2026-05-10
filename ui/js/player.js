window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

/* ── Video element abstraction ──────────────────────────── */

TwitchX._playerVideo = null;

function getPlayerVideo() {
  return TwitchX._playerVideo || document.getElementById('stream-video');
}

function isVideoFullscreen(video) {
  if (!video) return false;
  const fs = document.fullscreenElement || document.webkitFullscreenElement;
  if (fs && (fs === video || fs.contains(video))) return true;
  return video.webkitPresentationMode === 'fullscreen';
}

function isVideoPiP(video) {
  if (!video) return false;
  if (video.webkitPresentationMode === 'picture-in-picture') return true;
  if (document.pictureInPictureElement === video) return true;
  return false;
}

function _bindPiPEvents(video) {
  if (!video || video._pipEventsBound) return;
  video._pipEventsBound = true;
  video.addEventListener('enterpictureinpicture', function() {
    const btn = document.getElementById('pip-player-btn');
    if (btn) btn.classList.add('active');
  });
  video.addEventListener('leavepictureinpicture', function() {
    const btn = document.getElementById('pip-player-btn');
    if (btn) btn.classList.remove('active');
  });
  video.addEventListener('webkitpresentationmodechanged', function() {
    const btn = document.getElementById('pip-player-btn');
    if (btn) btn.classList.toggle('active', video.webkitPresentationMode === 'picture-in-picture');
  });
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

  const video = getPlayerVideo();
  if (video && !video._pipEventsBound) _bindPiPEvents(video);

  var recordBtn = document.getElementById('record-btn');
  if (recordBtn) recordBtn.style.display = 'inline-flex';
  var statsBtn = document.getElementById('stats-overlay-btn');
  if (statsBtn) statsBtn.style.display = 'inline-flex';

  TwitchX.stopVodTimeDisplay();
  TwitchX.stopVideoHealthMonitor();
  TwitchX.stopFpsMonitor();
  TwitchX.stopFrozenMonitor();
  TwitchX.stopProactiveReset();

  if (TwitchX.state.streamType === 'vod') {
    TwitchX.startVodTimeDisplay();
  } else {
    TwitchX.startVideoHealthMonitor();
    TwitchX.startFpsMonitor();
    TwitchX.startFrozenMonitor();
    TwitchX.startProactiveReset();
  }

  TwitchX.renderSidebar();
}

function hidePlayerView() {
  TwitchX.stopVideoHealthMonitor();
  TwitchX.stopFpsMonitor();
  TwitchX.stopFrozenMonitor();
  TwitchX.stopProactiveReset();
  TwitchX.stopVodTimeDisplay();
  TwitchX.hideStatsOverlay();
  TwitchX.thirdPartyEmotes = {};

  if (TwitchX._recordingActive && TwitchX.api) TwitchX.api.stop_recording();
  TwitchX._recordingActive = false;
  var recordBtn = document.getElementById('record-btn');
  if (recordBtn) { recordBtn.style.display = 'none'; recordBtn.style.color = ''; }
  var recordDot = document.getElementById('record-dot');
  if (recordDot) recordDot.style.display = 'none';
  var statsBtn = document.getElementById('stats-overlay-btn');
  if (statsBtn) statsBtn.style.display = 'none';

  // Cancel any pending gentle reset to prevent orphaned shadow videos
  if (TwitchX._gentleResetInProgress) {
    if (TwitchX._gentleResetTimer) {
      clearTimeout(TwitchX._gentleResetTimer);
      TwitchX._gentleResetTimer = null;
    }
    if (TwitchX._gentleResetNewVideo) {
      if (TwitchX._gentleResetDoSwap) {
        TwitchX._gentleResetNewVideo.removeEventListener('playing', TwitchX._gentleResetDoSwap);
        TwitchX._gentleResetNewVideo.removeEventListener('loadeddata', TwitchX._gentleResetDoSwap);
      }
      if (TwitchX._gentleResetNewVideo.parentNode) {
        TwitchX._gentleResetNewVideo.pause();
        TwitchX._gentleResetNewVideo.removeAttribute('src');
        TwitchX._gentleResetNewVideo.load();
        TwitchX._gentleResetNewVideo.remove();
      }
    }
    TwitchX._gentleResetInProgress = false;
    TwitchX._gentleResetNewVideo = null;
    TwitchX._gentleResetDoSwap = null;
  }

  const video = getPlayerVideo();
  if (video) {
    // Exit PiP before destroying the element, otherwise the native PiP window
    // may outlive the DOM node and show a frozen frame or black screen.
    if (isVideoPiP(video)) {
      togglePiP(video);
    }
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
  const playerContent = document.getElementById('player-content');
  playerContent.insertBefore(fresh, playerContent.firstChild);
  _bindPiPEvents(fresh);
  TwitchX._playerVideo = null;

  // Restore external player button
  const extBtn = document.getElementById('watch-external-btn');
  if (extBtn) { extBtn.disabled = false; extBtn.style.opacity = ''; }

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
  if (!video) return;

  // If currently in PiP, exit PiP first, then recurse to enter fullscreen
  if (isVideoPiP(video)) {
    togglePiP(video);
    setTimeout(toggleVideoFullscreen, 50);
    return;
  }

  // Exit Safari Video Presentation Mode (WKWebView)
  if (video.webkitPresentationMode === 'fullscreen') {
    if (typeof video.webkitSetPresentationMode === 'function') {
      video.webkitSetPresentationMode('inline');
    } else if (document.webkitExitFullscreen) {
      document.webkitExitFullscreen();
    } else if (video.webkitExitFullscreen) {
      video.webkitExitFullscreen();
    }
    return;
  }

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

/* ── Soft Video Reset (same DOM element, fullscreen-safe) ─ */

function softResetVideo(reason) {
  if (TwitchX._softResetInProgress) return;
  const video = getPlayerVideo();
  if (!video || !video.src) return;
  TwitchX._softResetInProgress = true;
  console.log('[VideoHealth]', reason, 'soft reset at', new Date().toISOString(),
    'src=', video.src.split('?')[0], 'currentTime=', video.currentTime);
  const savedSrc = video.src;
  const savedMuted = video.muted;
  const savedVolume = video.volume;
  video.pause();
  video.removeAttribute('src');
  video.src = '';
  video.load();
  video.src = savedSrc;
  video.muted = savedMuted;
  video.volume = savedVolume;
  video.play().catch(function() {});
  setTimeout(function() {
    TwitchX._softResetInProgress = false;
  }, 100);
}

/* ── Gentle Video Reset (crossfade swap) ────────────────── */

function gentleResetVideo(reason) {
  const oldVideo = getPlayerVideo();
  if (!oldVideo || !oldVideo.src) return;

  // Do not destroy the DOM element while in PiP or fullscreen — that kills the session
  if (isVideoPiP(oldVideo)) {
    softResetVideo(reason);
    return;
  }
  if (isVideoFullscreen(oldVideo)) {
    softResetVideo(reason);
    return;
  }

  // Cancel any previous pending gentle reset to avoid orphaned shadow videos
  if (TwitchX._gentleResetInProgress) {
    if (TwitchX._gentleResetTimer) {
      clearTimeout(TwitchX._gentleResetTimer);
      TwitchX._gentleResetTimer = null;
    }
    if (TwitchX._gentleResetNewVideo) {
      if (TwitchX._gentleResetDoSwap) {
        TwitchX._gentleResetNewVideo.removeEventListener('playing', TwitchX._gentleResetDoSwap);
        TwitchX._gentleResetNewVideo.removeEventListener('loadeddata', TwitchX._gentleResetDoSwap);
      }
      if (TwitchX._gentleResetNewVideo.parentNode) {
        TwitchX._gentleResetNewVideo.pause();
        TwitchX._gentleResetNewVideo.removeAttribute('src');
        TwitchX._gentleResetNewVideo.load();
        TwitchX._gentleResetNewVideo.remove();
      }
      TwitchX._gentleResetNewVideo = null;
    }
    TwitchX._gentleResetDoSwap = null;
  }

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
    TwitchX._gentleResetInProgress = false;
    TwitchX._gentleResetTimer = null;
    TwitchX._gentleResetDoSwap = null;
    TwitchX._gentleResetNewVideo = null;

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
      _bindPiPEvents(newVideo);
      console.log('[VideoHealth]', reason, 'reset completed');
    }, 160);
  }

  TwitchX._gentleResetDoSwap = doSwap;
  newVideo.addEventListener('playing', doSwap, { once: true });
  newVideo.addEventListener('loadeddata', doSwap, { once: true });

  TwitchX._gentleResetNewVideo = newVideo;
  TwitchX._gentleResetInProgress = true;
  TwitchX._gentleResetTimer = setTimeout(function() {
    TwitchX._gentleResetTimer = null;
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
TwitchX.isVideoFullscreen = isVideoFullscreen;
TwitchX.isVideoPiP = isVideoPiP;
TwitchX._bindPiPEvents = _bindPiPEvents;
TwitchX.softResetVideo = softResetVideo;

/* ── Recording ──────────────────────────────────────── */

TwitchX._recordingActive = false;

function toggleRecording() {
  if (!TwitchX.api) return;
  if (TwitchX._recordingActive) {
    TwitchX.api.stop_recording();
  } else {
    TwitchX.api.start_recording();
  }
}

function updateRecordButton() {
  var btn = document.getElementById('record-btn');
  var dot = document.getElementById('record-dot');
  if (!btn) return;
  if (TwitchX._recordingActive) {
    btn.textContent = '\u25a0 Stop REC';
    btn.style.color = '#e53935';
    if (dot) dot.style.display = '';
  } else {
    btn.textContent = '\u25cf REC';
    btn.style.color = '';
    if (dot) dot.style.display = 'none';
  }
}

TwitchX.toggleRecording = toggleRecording;
TwitchX.updateRecordButton = updateRecordButton;

/* ── Stats Overlay ──────────────────────────────────── */

TwitchX._statsOverlayActive = false;
TwitchX._statsRafId = null;
TwitchX._statsDroppedBaseline = 0;
TwitchX._statsTotalBaseline = 0;

function updateStatsOverlay() {
  if (!TwitchX._statsOverlayActive) return;
  var video = getPlayerVideo();
  if (!video || !video.src) {
    TwitchX._statsRafId = requestAnimationFrame(updateStatsOverlay);
    return;
  }

  var latency = '--';
  if (video.seekable && video.seekable.length > 0) {
    var edge = video.seekable.end(video.seekable.length - 1);
    var lag = edge - video.currentTime;
    latency = lag >= 0 ? lag.toFixed(1) + 's' : '--';
  }

  var buffer = '--';
  if (video.buffered && video.buffered.length > 0) {
    var ahead = video.buffered.end(video.buffered.length - 1) - video.currentTime;
    buffer = ahead >= 0 ? ahead.toFixed(1) + 's' : '--';
  }

  var dropped = '--';
  if (typeof video.getVideoPlaybackQuality === 'function') {
    var q = video.getVideoPlaybackQuality();
    var d = q.droppedVideoFrames - TwitchX._statsDroppedBaseline;
    var t = q.totalVideoFrames - TwitchX._statsTotalBaseline;
    if (t > 0) {
      dropped = d + ' (' + ((d / t) * 100).toFixed(1) + '%)';
    }
  }

  var resolution = '--';
  if (video.videoWidth && video.videoHeight) {
    resolution = video.videoWidth + '\u00d7' + video.videoHeight;
  }

  var el = function(id) { return document.getElementById(id); };
  if (el('so-latency')) el('so-latency').textContent = latency;
  if (el('so-buffer'))  el('so-buffer').textContent  = buffer;
  if (el('so-dropped')) el('so-dropped').textContent = dropped;
  if (el('so-resolution')) el('so-resolution').textContent = resolution;

  TwitchX._statsRafId = requestAnimationFrame(function() {
    setTimeout(updateStatsOverlay, 500);
  });
}

function showStatsOverlay() {
  TwitchX._statsOverlayActive = true;
  var overlay = document.getElementById('stats-overlay');
  var btn = document.getElementById('stats-overlay-btn');
  if (overlay) overlay.style.display = '';
  if (btn) btn.classList.add('active');
  var video = getPlayerVideo();
  if (video && typeof video.getVideoPlaybackQuality === 'function') {
    var q = video.getVideoPlaybackQuality();
    TwitchX._statsDroppedBaseline = q.droppedVideoFrames;
    TwitchX._statsTotalBaseline   = q.totalVideoFrames;
  }
  updateStatsOverlay();
}

function hideStatsOverlay() {
  TwitchX._statsOverlayActive = false;
  if (TwitchX._statsRafId) {
    cancelAnimationFrame(TwitchX._statsRafId);
    TwitchX._statsRafId = null;
  }
  var overlay = document.getElementById('stats-overlay');
  var btn = document.getElementById('stats-overlay-btn');
  if (overlay) overlay.style.display = 'none';
  if (btn) btn.classList.remove('active');
}

function toggleStatsOverlay() {
  if (TwitchX._statsOverlayActive) {
    hideStatsOverlay();
  } else {
    showStatsOverlay();
  }
}

TwitchX.toggleStatsOverlay = toggleStatsOverlay;
TwitchX.hideStatsOverlay = hideStatsOverlay;

/* ── VOD Mode ───────────────────────────────────────── */

TwitchX._vodTimer = null;

function formatVideoTime(seconds) {
  if (!isFinite(seconds) || seconds < 0) return '--:--';
  var s = Math.floor(seconds);
  var h = Math.floor(s / 3600);
  var m = Math.floor((s % 3600) / 60);
  var sec = s % 60;
  var pad = function(n) { return n < 10 ? '0' + n : String(n); };
  if (h > 0) return h + ':' + pad(m) + ':' + pad(sec);
  return m + ':' + pad(sec);
}

function startVodTimeDisplay() {
  stopVodTimeDisplay();
  var el = document.getElementById('vod-time-display');
  if (el) el.style.display = '';
  TwitchX._vodTimer = setInterval(function() {
    var video = getPlayerVideo();
    var display = document.getElementById('vod-time-display');
    if (!display) return;
    if (!video || !video.src) return;
    var cur = formatVideoTime(video.currentTime);
    var dur = isFinite(video.duration) && video.duration > 0
      ? formatVideoTime(video.duration)
      : '--:--';
    display.textContent = cur + ' / ' + dur;
  }, 1000);
}

function stopVodTimeDisplay() {
  if (TwitchX._vodTimer) {
    clearInterval(TwitchX._vodTimer);
    TwitchX._vodTimer = null;
  }
  var el = document.getElementById('vod-time-display');
  if (el) { el.style.display = 'none'; el.textContent = ''; }
}

TwitchX.startVodTimeDisplay = startVodTimeDisplay;
TwitchX.stopVodTimeDisplay  = stopVodTimeDisplay;
