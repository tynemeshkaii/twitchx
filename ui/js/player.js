window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

/* ── Video element abstraction ──────────────────────────── */

TwitchX._playerVideo = null;

/* Every automatic reset interrupts playback for a moment, so the health, frozen
   and FPS monitors share one cooldown instead of each firing independently and
   stacking recoveries on top of one another. */
const RESET_COOLDOWN_MS = 30000;

/* Backoff for re-resolving a dead stream. The last entry repeats until
   RECOVERY_MAX_ATTEMPTS is reached, after which the user gets a Reconnect button. */
const RECOVERY_BACKOFF_MS = [1000, 2000, 4000, 8000, 15000];
const RECOVERY_MAX_ATTEMPTS = 5;

/* How long playback may sit in `waiting` before it counts as a dead stream
   rather than ordinary rebuffering. */
const STALL_RECOVERY_MS = 20000;

TwitchX._lastResetAt = 0;
// requestId rises on every refresh request and on every cancellation, so a reply
// that arrives after the player recovered on its own — or after the user moved
// to another channel — can be recognised as stale and dropped.
TwitchX._recovery = {
  attempts: 0,
  timer: null,
  active: false,
  pending: false,
  requestId: 0,
};

function getPlayerVideo() {
  return TwitchX._playerVideo || document.getElementById('stream-video');
}

function _isLivePlayback() {
  return TwitchX.state.streamType !== 'vod';
}

function _createVideoElement(id) {
  const v = document.createElement('video');
  v.id = id || 'stream-video';
  v.autoplay = true;
  v.controls = true;
  v.playsInline = true;
  // AVPlayer keeps a fuller buffer with an explicit hint, which shortens the
  // rebuffering window after a source swap.
  v.preload = 'auto';
  return v;
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
    // WebKit native fullscreen auto-hide (event does NOT bubble to document)
    if (video.webkitPresentationMode === 'fullscreen') {
      if (!TwitchX._fsAutoHideActive) _startFullscreenAutoHide();
    } else if (!isVideoFullscreen(video) && !isVideoPiP(video)) {
      _stopFullscreenAutoHide();
    }
  });
}

/* ── Player view ────────────────────────────────────────── */

function showPlayerView() {
  TwitchX.setChromeVisible(false);
  TwitchX.switchView('player-view', 'forward');
  var pLoader = document.getElementById('player-loader');
  if (pLoader) pLoader.classList.remove('hidden');

  TwitchX.state.watchingChannel = TwitchX.state.selectedChannel;
  TwitchX.state.watchingChannelKey = TwitchX.state.selectedChannelKey;
  document.getElementById('watch-btn').classList.add('active');
  document.getElementById('stop-player-btn').classList.remove('hidden');
  document.getElementById('live-dot').classList.add('visible');

  const chatPanel = document.getElementById('chat-panel');
  const chatHandle = document.getElementById('chat-resize-handle');
  const toggleBtn = document.getElementById('toggle-chat-btn');
  if (!TwitchX.state.playerHasChat) {
    chatPanel.classList.add('hidden');
    if (chatHandle) chatHandle.classList.add('hidden');
    if (toggleBtn) toggleBtn.classList.add('hidden');
  } else {
    if (toggleBtn) toggleBtn.classList.remove('hidden');
    const cfg = TwitchX.state.configLoaded ? TwitchX.state.fullConfig : null;
    if (cfg && cfg.chat_width) chatPanel.style.setProperty('--chat-width', cfg.chat_width + 'px');
    if (cfg && cfg.chat_visible === false) {
      chatPanel.classList.add('hidden');
      if (chatHandle) chatHandle.classList.add('hidden');
    } else {
      chatPanel.classList.remove('hidden');
      if (chatHandle) chatHandle.classList.remove('hidden');
    }
  }
  updateChatInput();

  hidePlayerError();
  const video = getPlayerVideo();
  if (video) {
    if (!video._pipEventsBound) _bindPiPEvents(video);
    var hideLoader = function() {
      var pl = document.getElementById('player-loader');
      if (pl) pl.classList.add('hidden');
    };
    video.addEventListener('playing', hideLoader, { once: true });
    video.addEventListener('error', hideLoader, { once: true });
    // If nothing ever plays, replace the spinner with something actionable
    // instead of leaving the user in front of an empty frame.
    if (TwitchX._playerLoaderTimer) clearTimeout(TwitchX._playerLoaderTimer);
    TwitchX._playerLoaderTimer = setTimeout(function() {
      TwitchX._playerLoaderTimer = null;
      hideLoader();
      const v = getPlayerVideo();
      if (!v || v.readyState >= 3) return;
      if (TwitchX._recovery.active) return;
      beginStreamRecovery('never-started');
    }, 15000);
  }

  _bindPlayerContentEvents();

  var recordBtn = document.getElementById('record-btn');
  if (recordBtn) recordBtn.classList.remove('hidden');
  var statsBtn = document.getElementById('stats-overlay-btn');
  if (statsBtn) statsBtn.classList.remove('hidden');

  TwitchX.stopVodTimeDisplay();
  TwitchX.stopVodSeekBar();
  TwitchX.stopVideoHealthMonitor();
  TwitchX.stopFpsMonitor();
  TwitchX.stopFrozenMonitor();
  TwitchX.stopProactiveReset();

  if (TwitchX.state.streamType === 'vod') {
    TwitchX.startVodTimeDisplay();
    TwitchX.startVodSeekBar();
  } else {
    TwitchX.startVideoHealthMonitor();
    TwitchX.startFpsMonitor();
    TwitchX.startFrozenMonitor();
    TwitchX.startProactiveReset();
  }

  TwitchX.syncVolumeSlider(getPlayerVideo());
  TwitchX.renderSidebar();
}

function hidePlayerView(skipViewTransition) {
  const playerView = document.getElementById('player-view');
  if (!playerView || !playerView.classList.contains('view-active')) return;

  // When hidePlayerView is called directly from JS (Escape key, opening multistream),
  // Python state is not cleared automatically. Notify Python to clear _watching_channel
  // and end the watch session. Guard against re-entry from onPlayerStop (which already
  // cleared state before calling us).
  if (!TwitchX._hidePlayerFromPython && TwitchX.api) {
    TwitchX.api.notify_player_hidden();
  }

  TwitchX.stopVideoHealthMonitor();
  TwitchX.stopFpsMonitor();
  TwitchX.stopFrozenMonitor();
  TwitchX.stopProactiveReset();
  TwitchX.stopVodTimeDisplay();
  // Without this the 250ms interval kept ticking and the seek bar stayed on
  // screen over the grid and over the next live stream.
  TwitchX.stopVodSeekBar();
  TwitchX.hideStatsOverlay();
  cancelStreamRecovery();
  hidePlayerError();
  if (TwitchX._playerLoaderTimer) {
    clearTimeout(TwitchX._playerLoaderTimer);
    TwitchX._playerLoaderTimer = null;
  }
  TwitchX._lastResetAt = 0;
  TwitchX.thirdPartyEmotes = {};
  var pLoader = document.getElementById('player-loader');
  if (pLoader) pLoader.classList.add('hidden');

  if (TwitchX._recordingActive && TwitchX.api) TwitchX.api.stop_recording();
  TwitchX._recordingActive = false;
  var recordBtn = document.getElementById('record-btn');
  if (recordBtn) { recordBtn.classList.add('hidden'); recordBtn.classList.remove('recording'); }
  var recordDot = document.getElementById('record-dot');
  if (recordDot) recordDot.classList.add('hidden');
  var statsBtn = document.getElementById('stats-overlay-btn');
  if (statsBtn) statsBtn.classList.add('hidden');

  // Cancel any pending gentle reset to prevent orphaned shadow videos
  cancelGentleReset();

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

    // Phase 6: guaranteed cleanup — destroy the MediaPlayer
    video.remove();
  }

  const fresh = _createVideoElement('stream-video');
  const stage = document.getElementById('player-stage');
  if (stage) stage.insertBefore(fresh, stage.firstChild);
  _bindPiPEvents(fresh);
  TwitchX._playerVideo = null;

  // Restore external player button
  const extBtn = document.getElementById('watch-external-btn');
  if (extBtn) extBtn.disabled = false;

  // Clear chat
  TwitchX.clearChatMessages();
  if (TwitchX.clearChatBatch) TwitchX.clearChatBatch();
  if (TwitchX.api) TwitchX.api.stop_chat();

  if (!skipViewTransition) {
    TwitchX.switchView('stream-grid', 'back');
    TwitchX.setChromeVisible(true);
  } else {
    document.getElementById('player-view').classList.remove('view-active');
    document.getElementById('player-view').classList.add('hidden');
  }

  TwitchX.state.watchingChannel = null;
  TwitchX.state.watchingChannelKey = null;
  TwitchX.state.playerPlatform = null;
  TwitchX.state.playerHasChat = true;
  TwitchX.chatPlatform = null;
  TwitchX.chatAuthenticated = false;
  TwitchX.state.playerState = 'idle';
  document.getElementById('watch-btn').classList.remove('active');
  document.getElementById('stop-player-btn').classList.add('hidden');
  document.getElementById('live-dot').classList.remove('visible');
  document.getElementById('toggle-chat-btn').classList.remove('hidden');
  TwitchX.setStatus('', 'info');
  TwitchX.syncVolumeSlider(null);
  TwitchX.renderGrid();
  TwitchX.renderSidebar();
}

function getActiveVideo() {
  if (document.getElementById('player-view').classList.contains('view-active')) {
    return getPlayerVideo();
  }
  if (TwitchX.multiState.open && TwitchX.multiState.audioFocus >= 0) {
    const slotEl = document.querySelector('.ms-slot[data-slot-idx="' + TwitchX.multiState.audioFocus + '"]');
    return slotEl ? slotEl.querySelector('.ms-video') : null;
  }
  return null;
}

function syncVolumeSlider(video) {
  const slider = document.getElementById('volume-slider');
  const muteBtn = document.getElementById('mute-btn');
  const volGroup = document.getElementById('volume-group');
  if (!slider || !volGroup) return;
  if (video) {
    volGroup.classList.remove('hidden');
    var pct = Math.round(video.muted ? 0 : video.volume * 100);
    slider.value = pct;
    slider.style.setProperty('--volume-pct', pct + '%');
    if (muteBtn) muteBtn.classList.toggle('muted', video.muted);
  } else {
    volGroup.classList.add('hidden');
  }
}

function adjustVolume(delta) {
  const video = getActiveVideo();
  if (!video) return;
  video.muted = false;
  video.volume = Math.max(0, Math.min(1, video.volume + delta));
  TwitchX.setStatus('Volume: ' + Math.round(video.volume * 100) + '%', 'info');
  syncVolumeSlider(video);
}

function toggleMute() {
  const video = getActiveVideo();
  if (!video) return;
  video.muted = !video.muted;
  TwitchX.setStatus(video.muted ? 'Muted' : 'Unmuted', 'info');
  syncVolumeSlider(video);
}

function _handleVolumeSliderInput() {
  const slider = document.getElementById('volume-slider');
  const video = getActiveVideo();
  if (!slider || !video) return;
  var pct = parseInt(slider.value, 10) / 100;
  video.muted = false;
  video.volume = pct;
  slider.style.setProperty('--volume-pct', Math.round(pct * 100) + '%');
  TwitchX.setStatus('Volume: ' + Math.round(pct * 100) + '%', 'info');
  var muteBtn = document.getElementById('mute-btn');
  if (muteBtn) muteBtn.classList.remove('muted');
}

function _handleMuteBtnClick() {
  toggleMute();
}

function cycleStream(dir) {
  const streams = TwitchX.getFilteredSortedStreams();
  if (streams.length === 0) return;
  let idx = streams.findIndex(function(s) {
    return TwitchX.channelKey(s.login, s.platform || 'twitch') === TwitchX.state.selectedChannelKey;
  });
  if (idx === -1) {
    idx = dir > 0 ? 0 : streams.length - 1;
  } else {
    idx = (idx + dir + streams.length) % streams.length;
  }
  TwitchX.selectChannel(streams[idx].login, streams[idx].platform || 'twitch');
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

  if (isVideoPiP(video)) {
    togglePiP(video);
    setTimeout(function() {
      if (isVideoPiP(video)) return;
      toggleVideoFullscreen();
    }, 150);
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
  if (handle) handle.classList.toggle('hidden', panel.classList.contains('hidden'));
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
  if (!TwitchX.state.playerHasChat) {
    input.placeholder = 'Chat is not available for this media';
  } else if (!chatUser) {
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

/* ── Playback event delegation ──────────────────────────── */
// Media events (waiting, playing, error, stalled, emptied) do NOT bubble, so a
// listener on #player-content only sees them in the capture phase. Delegating
// here rather than binding per element means the swapped-in video created by a
// gentle reset is covered without rebinding anything.

function _isShadowVideo(el) {
  return !!el && el.classList && el.classList.contains('video-shadow');
}

function _bindPlayerContentEvents() {
  var pContent = document.getElementById('player-content');
  if (!pContent || pContent._playbackEventsBound) return;
  pContent._playbackEventsBound = true;

  var onWaiting = function(e) {
    if (e.target.tagName !== 'VIDEO' || _isShadowVideo(e.target)) return;
    var buf = document.getElementById('player-buffering');
    if (buf) buf.classList.remove('buffering-hide');
    if (!_isLivePlayback()) return;
    if (TwitchX._stallTimer) clearTimeout(TwitchX._stallTimer);
    TwitchX._stallTimer = setTimeout(function() {
      TwitchX._stallTimer = null;
      const v = getPlayerVideo();
      if (!v || v.paused || v.readyState >= 3) return;
      beginStreamRecovery('stalled');
    }, STALL_RECOVERY_MS);
  };

  var onPlaying = function(e) {
    if (e.target.tagName !== 'VIDEO' || _isShadowVideo(e.target)) return;
    var buf = document.getElementById('player-buffering');
    if (buf) buf.classList.add('buffering-hide');
    if (TwitchX._stallTimer) { clearTimeout(TwitchX._stallTimer); TwitchX._stallTimer = null; }
    // Playback is alive again — drop any recovery backoff so a later, unrelated
    // failure starts from a short delay rather than a long one.
    cancelStreamRecovery();
  };

  var onError = function(e) {
    if (e.target.tagName !== 'VIDEO' || _isShadowVideo(e.target)) return;
    var err = e.target.error;
    console.warn('[Player] media error', err && err.code, err && err.message);
    if (!_isLivePlayback()) {
      showPlayerError('Playback failed', err && err.message ? err.message : '');
      return;
    }
    beginStreamRecovery('media-error');
  };

  var onEmptied = function(e) {
    if (e.target.tagName !== 'VIDEO' || _isShadowVideo(e.target)) return;
    // Emptied fires as part of a deliberate reset too; only treat it as a
    // failure when no recovery or reset is already running.
    if (TwitchX._gentleResetInProgress || TwitchX._softResetInProgress) return;
    if (!_isLivePlayback() || !e.target.src) return;
    beginStreamRecovery('emptied');
  };

  pContent.addEventListener('waiting', onWaiting, true);
  pContent.addEventListener('playing', onPlaying, true);
  pContent.addEventListener('error', onError, true);
  pContent.addEventListener('emptied', onEmptied, true);
}

/* ── Playback error overlay ─────────────────────────────── */

function showPlayerError(message, hint) {
  var box = document.getElementById('player-error');
  var msg = document.getElementById('player-error-msg');
  var hintEl = document.getElementById('player-error-hint');
  var btn = document.getElementById('player-retry-btn');
  if (msg) msg.textContent = message || 'Playback stopped';
  if (hintEl) hintEl.textContent = hint || '';
  if (btn) btn.disabled = false;
  if (box) box.classList.remove('hidden');
  var loader = document.getElementById('player-loader');
  if (loader) loader.classList.add('hidden');
  var buf = document.getElementById('player-buffering');
  if (buf) buf.classList.add('buffering-hide');
}

function hidePlayerError() {
  var box = document.getElementById('player-error');
  if (box) box.classList.add('hidden');
}

function _handlePlayerRetryClick() {
  // Clear any stuck in-flight state first: the whole point of the button is to
  // break out of a recovery that is no longer going anywhere.
  cancelStreamRecovery();
  hidePlayerError();
  if (!beginStreamRecovery('manual-retry')) {
    showPlayerError(
      'Cannot reconnect',
      'Reopen the channel from the list to start again.'
    );
  }
}

/* ── Stream recovery (re-resolve a dead URL) ────────────── */
// Signed HLS URLs expire, and replaying the URL the player started with cannot
// recover from an expiry, a sleep/wake cycle or a network change. Recovery asks
// Python for a fresh URL and swaps it in through the existing crossfade.

const REFRESH_REPLY_TIMEOUT_MS = 30000;

function _armRefreshWatchdog() {
  if (TwitchX._refreshWatchdog) clearTimeout(TwitchX._refreshWatchdog);
  TwitchX._refreshWatchdog = setTimeout(function() {
    TwitchX._refreshWatchdog = null;
    if (!TwitchX._recovery.pending) return;
    // No reply came back — release the flag so a later failure can retry
    // instead of being blocked by a request that will never complete.
    console.warn('[Player] URL refresh reply timed out');
    TwitchX._recovery.pending = false;
    TwitchX._qualitySwitchPending = false;
    if (TwitchX.state.watchingChannel && _isPlaybackDead()) {
      beginStreamRecovery('refresh-timeout');
    }
  }, REFRESH_REPLY_TIMEOUT_MS);
}

function _disarmRefreshWatchdog() {
  if (TwitchX._refreshWatchdog) {
    clearTimeout(TwitchX._refreshWatchdog);
    TwitchX._refreshWatchdog = null;
  }
}

function cancelStreamRecovery() {
  _disarmRefreshWatchdog();
  if (TwitchX._recovery.timer) {
    clearTimeout(TwitchX._recovery.timer);
    TwitchX._recovery.timer = null;
  }
  TwitchX._recovery.attempts = 0;
  TwitchX._recovery.active = false;
  TwitchX._recovery.pending = false;
  // Invalidate whatever is still in flight — its reply must not swap the source
  // of a stream that is playing again.
  TwitchX._recovery.requestId += 1;
  TwitchX._qualitySwitchPending = false;
  if (TwitchX._stallTimer) { clearTimeout(TwitchX._stallTimer); TwitchX._stallTimer = null; }
}

function beginStreamRecovery(reason) {
  if (!_isLivePlayback()) return false;
  const channel = TwitchX.state.watchingChannel;
  const platform = TwitchX.state.playerPlatform || 'twitch';
  if (!channel || !TwitchX.api || !TwitchX.api.refresh_stream_url) return false;
  if (platform === 'youtube') {
    showPlayerError('Stream interrupted', 'Reopen the channel to continue.');
    return false;
  }
  // A request is already in flight or scheduled — let it finish.
  if (TwitchX._recovery.pending || TwitchX._recovery.timer) return true;

  if (TwitchX._recovery.attempts >= RECOVERY_MAX_ATTEMPTS) {
    TwitchX._recovery.active = false;
    showPlayerError(
      'Lost connection to the stream',
      'The channel may have gone offline.'
    );
    return false;
  }

  const delay = RECOVERY_BACKOFF_MS[
    Math.min(TwitchX._recovery.attempts, RECOVERY_BACKOFF_MS.length - 1)
  ];
  TwitchX._recovery.active = true;
  TwitchX._recovery.attempts += 1;
  console.log('[Player] recovery', reason, 'attempt', TwitchX._recovery.attempts,
    'in', delay + 'ms');
  TwitchX.setStatus('Reconnecting to ' + channel + '...', 'warn');

  TwitchX._recovery.timer = setTimeout(function() {
    TwitchX._recovery.timer = null;
    if (!TwitchX.state.watchingChannel) return;
    TwitchX._recovery.pending = true;
    TwitchX._recovery.requestId += 1;
    const requestId = TwitchX._recovery.requestId;
    _armRefreshWatchdog();
    const quality = _currentQuality();
    try {
      TwitchX.api.refresh_stream_url(channel, platform, quality, requestId);
    } catch (e) {
      TwitchX._recovery.pending = false;
      _disarmRefreshWatchdog();
      console.warn('[Player] refresh_stream_url failed', e);
      beginStreamRecovery('refresh-call-failed');
    }
  }, delay);
  return true;
}

function _currentQuality() {
  var sel = document.getElementById('quality-select');
  return (sel && sel.value) || 'best';
}

function _onStreamUrlRefreshed(data) {
  if (!data) return;
  // Stale reply: the player recovered on its own, the user switched channel, or
  // the request was superseded. Applying it now would interrupt a healthy stream.
  if (data.request_id !== TwitchX._recovery.requestId) {
    console.log('[Player] ignoring stale URL refresh', data.request_id);
    return;
  }
  if (data.channel && data.channel !== TwitchX.state.watchingChannel) {
    console.log('[Player] ignoring URL refresh for a channel we left');
    return;
  }
  _disarmRefreshWatchdog();
  TwitchX._recovery.pending = false;
  const wasQualitySwitch = !!TwitchX._qualitySwitchPending;
  TwitchX._qualitySwitchPending = false;
  if (!TwitchX.state.watchingChannel) return;
  if (!data.ok || !data.url) {
    if (wasQualitySwitch) {
      // The picture that is playing is still fine — report and leave it alone.
      TwitchX.setStatus((data && data.error) || 'Could not switch quality', 'error');
      return;
    }
    beginStreamRecovery('refresh-failed');
    return;
  }
  if (wasQualitySwitch) {
    hidePlayerError();
    TwitchX.setStatus('', 'info');
    // Persist it, or the next launch would silently go back to the old quality
    // and a recording would be made at a quality nobody is watching.
    if (TwitchX.api && TwitchX.api.save_quality && data.quality) {
      try { TwitchX.api.save_quality(data.quality); } catch (e) {}
    }
    applyNewStreamSource(data.url, 'quality-switch');
    return;
  }
  // A refreshed URL is a deliberate swap, not a health-driven one, so it is not
  // subject to the shared reset cooldown.
  hidePlayerError();
  TwitchX.setStatus('', 'info');
  applyNewStreamSource(data.url, 'recovery');
}

/* Swap the playing source without tearing down the player view. */
function applyNewStreamSource(url, reason) {
  const video = getPlayerVideo();
  if (!video) return;
  if (!video.src) {
    video.src = url;
    video.play().catch(function(e) {
      console.warn('[Player] play() after source swap rejected:', e && e.message || e);
    });
    return;
  }
  gentleResetVideo(reason, url);
}

/* ── Network and wake recovery ──────────────────────────── */
// Sleep/wake and Wi-Fi changes leave AVPlayer holding a connection that will
// never produce another segment, and no media event necessarily fires.

function _isPlaybackDead() {
  const video = getPlayerVideo();
  if (!video || !video.src) return false;
  // A paused live player is not automatically healthy: AVPlayer pauses itself
  // when sleep or a dropped connection ends the stream. A pause the user asked
  // for leaves the buffer intact, so readyState tells the two apart without
  // having to guess at intent.
  if (video.paused) return video.readyState < 3;
  if (video.readyState < 3) return true;
  if (video.seekable && video.seekable.length > 0) {
    const drift = video.seekable.end(video.seekable.length - 1) - video.currentTime;
    if (drift > 120) return true;
  }
  return false;
}

function _checkPlaybackAfterWake(reason) {
  if (!TwitchX.state.watchingChannel || !_isLivePlayback()) return;
  // Give the connection a moment to recover on its own before intervening.
  setTimeout(function() {
    if (!TwitchX.state.watchingChannel) return;
    if (_isPlaybackDead()) beginStreamRecovery(reason);
  }, 2000);
}

function _watchNetworkChanges() {
  if (TwitchX._networkWatchBound) return;
  TwitchX._networkWatchBound = true;
  window.addEventListener('online', function() {
    _checkPlaybackAfterWake('network-online');
  });
  window.addEventListener('offline', function() {
    if (TwitchX.state.watchingChannel && _isLivePlayback()) {
      TwitchX.setStatus('Network offline — waiting to reconnect', 'warn');
    }
  });
  document.addEventListener('visibilitychange', function() {
    if (!document.hidden) _checkPlaybackAfterWake('window-visible');
  });
  window.addEventListener('pageshow', function() {
    _checkPlaybackAfterWake('page-show');
  });
}

/* ── Reset cooldown ─────────────────────────────────────── */

function requestVideoReset(reason) {
  const now = Date.now();
  if (now - (TwitchX._lastResetAt || 0) < RESET_COOLDOWN_MS) {
    console.log('[VideoHealth]', reason, 'suppressed by reset cooldown');
    return false;
  }
  const video = getPlayerVideo();
  // Nothing to reset — do not spend the cooldown on a no-op.
  if (!video || !video.src) return false;
  TwitchX._lastResetAt = now;
  gentleResetVideo(reason);
  return true;
}

/* ── Video Health Monitor ───────────────────────────────── */

function startVideoHealthMonitor() {
  stopVideoHealthMonitor();
  TwitchX._droppedFramesBaseline = 0;
  // 20s rather than a minute: decoder degradation is otherwise detected up to a
  // full minute after it starts, which the viewer sees as sustained stutter.
  TwitchX._healthMonitorTimer = setInterval(checkVideoHealth, 20000);
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

  // Detect decoder pipeline degradation via dropped frames.
  // rAF-based FPS monitor misses this because VideoToolbox runs on a separate thread.
  if (typeof video.getVideoPlaybackQuality === 'function') {
    const q = video.getVideoPlaybackQuality();
    const total = q.totalVideoFrames;
    const dropped = q.droppedVideoFrames - (TwitchX._droppedFramesBaseline || 0);
    if (total > 300 && dropped / total > 0.05) {
      TwitchX._droppedFramesBaseline = q.droppedVideoFrames;
      if (requestVideoReset('dropped-frames')) {
        TwitchX.setStatus('Auto-recovered playback smoothness', 'info');
      }
      return;
    }
  }

  // Seek to live edge if we're lagging behind (>30s drift).
  // Tight threshold keeps SourceBuffer small: the player doesn't need to manage
  // both old and new segments simultaneously when drift is large.
  if (video.seekable && video.seekable.length > 0) {
    const liveEdge = video.seekable.end(video.seekable.length - 1);
    const drift = liveEdge - video.currentTime;
    if (drift > 30) {
      // Landing 2s from the edge leaves under a segment of buffer on standard
      // 2s-segment HLS, which immediately rebuffers. Keep ~3 segments of margin
      // unless the user opted into low latency and accepted that trade-off.
      const cfg = TwitchX.state.fullConfig || {};
      const margin = cfg.low_latency_mode ? 2 : 6;
      video.currentTime = Math.max(video.currentTime, liveEdge - margin);
      TwitchX.setStatus('Caught up to live edge', 'info');
      return;
    }
  }

  // If buffered end is far ahead, do a gentle reset to clear accumulated buffers.
  // 60s is intentionally conservative — live HLS needs at most 15-30s ahead;
  // beyond that the SourceBuffer grows unboundedly and causes decode latency.
  if (video.buffered && video.buffered.length > 0) {
    const bufferedEnd = video.buffered.end(video.buffered.length - 1);
    const bufferedDrift = bufferedEnd - video.currentTime;
    if (bufferedDrift > 60) {
      if (requestVideoReset('buffer-overflow')) {
        TwitchX.setStatus('Stream buffer cleared for smooth playback', 'info');
      }
      return;
    }
  }

  // Check total buffered range span (includes segments behind currentTime).
  // Old played-back segments stay in SourceBuffer and consume memory.
  // If total buffered span > 120s, reset to evict them.
  if (video.buffered && video.buffered.length > 0) {
    const totalStart = video.buffered.start(0);
    const totalEnd = video.buffered.end(video.buffered.length - 1);
    if (totalEnd - totalStart > 120) {
      if (requestVideoReset('buffer-total-overflow')) {
        TwitchX.setStatus('Stream buffer cleared for smooth playback', 'info');
      }
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
    // Two consecutive ticks (~20s). A single tick also fires during ad breaks
    // and long GOP stalls, where a visible crossfade is worse than waiting.
    if (TwitchX._frozenStreak >= 2) {
      if (requestVideoReset('frozen')) {
        TwitchX.setStatus('Auto-recovered playback smoothness', 'info');
      } else {
        // Cooldown blocked the reset and the picture is still frozen — the URL
        // itself is the likely culprit, so ask for a fresh one.
        beginStreamRecovery('frozen-persistent');
      }
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

function softResetVideo(reason, newSrc) {
  if (TwitchX._softResetInProgress) return;
  // Clear any recovery status set by gentleResetVideo before it fell through to us
  setStatus('', 'info');
  const video = getPlayerVideo();
  if (!video || !video.src) return;
  TwitchX._softResetInProgress = true;
  console.log('[VideoHealth]', reason, 'soft reset at', new Date().toISOString(),
    'src=', video.src.split('?')[0], 'currentTime=', video.currentTime);
  const savedSrc = newSrc || video.src;
  const savedMuted = video.muted;
  const savedVolume = video.volume;
  video.pause();
  video.removeAttribute('src');
  video.load();
  video.src = savedSrc;
  video.muted = savedMuted;
  video.volume = savedVolume;
  video.play().catch(function(e) {
    console.warn('[Player] softReset play() rejected:', e && e.message || e);
  });
  setTimeout(function() {
    TwitchX._softResetInProgress = false;
  }, 100);
}

/* ── Gentle Video Reset (crossfade swap) ────────────────── */

function cancelGentleReset() {
  if (!TwitchX._gentleResetInProgress) return;
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
  TwitchX._gentleResetInProgress = false;
  // Restore _playerVideo to the original element (the shadow used its own id and
  // has just been removed, so this cannot pick the wrong one)
  const orig = document.getElementById('stream-video');
  if (orig) TwitchX._playerVideo = orig;
}

function gentleResetVideo(reason, newSrc) {
  const oldVideo = getPlayerVideo();
  if (!oldVideo || !oldVideo.src) return;

  // Do not destroy the DOM element while in PiP or fullscreen — that kills the session
  if (isVideoPiP(oldVideo)) {
    softResetVideo(reason, newSrc);
    return;
  }
  if (isVideoFullscreen(oldVideo)) {
    softResetVideo(reason, newSrc);
    return;
  }

  // Show recovery status — only after guards, so early-return paths don't leave it stale
  setStatus('Recovering playback...', 'warn');

  // Cancel any previous pending gentle reset to avoid orphaned shadow videos
  if (TwitchX._gentleResetInProgress) {
    cancelGentleReset();
  }

  // Prevent re-entrant calls from using the old element
  TwitchX._playerVideo = null;

  console.log('[VideoHealth]', reason, 'reset starting at', new Date().toISOString(),
    'src=', oldVideo.src.split('?')[0], 'currentTime=', oldVideo.currentTime);

  const container = oldVideo.parentNode;
  const savedSrc = newSrc || oldVideo.src;
  const savedMuted = oldVideo.muted;
  const savedVolume = oldVideo.volume;

  // The shadow carries its own id until the swap. Two elements sharing
  // #stream-video made getPlayerVideo() depend on DOM order during the overlap.
  const newVideo = _createVideoElement('stream-video-next');
  newVideo.className = 'video-shadow';

  newVideo.src = savedSrc;
  newVideo.muted = true;
  newVideo.volume = savedVolume;

  container.insertBefore(newVideo, oldVideo);
  newVideo.play().catch(function(e) {
    console.warn('[Player] gentleReset new video play() rejected:', e && e.message || e);
  });

  let swapped = false;

  function doSwap() {
    if (swapped) return;
    swapped = true;
    TwitchX._gentleResetInProgress = false;
    TwitchX._gentleResetTimer = null;
    TwitchX._gentleResetDoSwap = null;
    TwitchX._gentleResetNewVideo = null;

    oldVideo.classList.add('video-fading');
    newVideo.classList.remove('video-shadow');

    setTimeout(function() {
      oldVideo.pause();
      oldVideo.removeAttribute('src');
      oldVideo.load();
      oldVideo.remove();

      newVideo.classList.remove('video-shadow');
      newVideo.id = 'stream-video';
      newVideo.muted = savedMuted;

      TwitchX._playerVideo = newVideo;
      _bindPiPEvents(newVideo);
      setStatus('', 'info');
      console.log('[VideoHealth]', reason, 'reset completed');
    }, 160);
  }

  TwitchX._gentleResetDoSwap = doSwap;
  newVideo.addEventListener('playing', doSwap, { once: true });
  newVideo.addEventListener('loadeddata', doSwap, { once: true });
  newVideo.addEventListener('error', function() {
    if (swapped) return;
    // Keep the old element playing rather than crossfading to a broken one.
    console.warn('[VideoHealth]', reason, 'replacement video failed to load');
    cancelGentleReset();
    setStatus('', 'info');
    if (newSrc) {
      // The refreshed URL is the one that failed — go back for another.
      beginStreamRecovery('refreshed-url-failed');
    }
  }, { once: true });

  TwitchX._gentleResetNewVideo = newVideo;
  TwitchX._gentleResetInProgress = true;
  TwitchX._gentleResetTimer = setTimeout(function() {
    TwitchX._gentleResetTimer = null;
    if (!swapped) doSwap();
  }, 2500);
}

/* ── Proactive Reset (15 min) ───────────────────────────── */
// Only resets if there are actual signs of memory/decode degradation.
// Unconditional resets interrupt playback (re-buffering) for users on slow connections.

function _hasPlaybackDegradation(video) {
  if (!video || !video.src || video.paused) return false;

  // Growing buffer ahead of playback head (>45s) indicates SourceBuffer accumulation
  if (video.buffered && video.buffered.length > 0) {
    const ahead = video.buffered.end(video.buffered.length - 1) - video.currentTime;
    if (ahead > 45) return true;
  }

  // Total buffered span > 90s means old segments are piling up
  if (video.buffered && video.buffered.length > 0) {
    const span = video.buffered.end(video.buffered.length - 1) - video.buffered.start(0);
    if (span > 90) return true;
  }

  // Meaningful dropped-frame rate (>3%) signals decode pipeline pressure
  if (typeof video.getVideoPlaybackQuality === 'function') {
    const q = video.getVideoPlaybackQuality();
    if (q.totalVideoFrames > 600 && q.droppedVideoFrames / q.totalVideoFrames > 0.03) return true;
  }

  return false;
}

function startProactiveReset() {
  stopProactiveReset();
  function tick() {
    const video = getPlayerVideo();
    if (_hasPlaybackDegradation(video)) {
      requestVideoReset('proactive');
    }
    TwitchX._proactiveTimer = setTimeout(tick, 15 * 60 * 1000);
  }
  TwitchX._proactiveTimer = setTimeout(tick, 15 * 60 * 1000);
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
  TwitchX._fpsLastTimestamp = 0;
  TwitchX._fpsRafId = 0;
  TwitchX._fpsConsecutiveBad = 0;

  function tick(timestamp) {
    if (!TwitchX._fpsRafId) return;

    // Skip when tab/window is hidden — rAF is throttled by the OS and the delta
    // has no relation to video decode health. Reset baseline to avoid false triggers
    // on the first frame after the window becomes visible again.
    if (document.hidden) {
      TwitchX._fpsLastTimestamp = 0;
      TwitchX._fpsConsecutiveBad = 0;
      TwitchX._fpsRafId = requestAnimationFrame(tick);
      return;
    }

    const video = getPlayerVideo();
    if (!video || video.paused || video.readyState < 2) {
      TwitchX._fpsLastTimestamp = 0;
      TwitchX._fpsConsecutiveBad = 0;
      TwitchX._fpsRafId = requestAnimationFrame(tick);
      return;
    }

    if (TwitchX._fpsLastTimestamp) {
      const delta = timestamp - TwitchX._fpsLastTimestamp;
      // Use a conservative 200ms threshold (< 5 fps) to distinguish genuine UI
      // pipeline stalls from normal macOS power-saving rAF throttling (~10–30 fps).
      if (delta > 200) {
        TwitchX._fpsConsecutiveBad += 1;
        // Require 15 consecutive bad frames (~3s at 5fps) and rate-limit resets
        // to once per 60s so we don't loop on a genuinely slow machine.
        if (TwitchX._fpsConsecutiveBad >= 15) {
          if (requestVideoReset('fps-drop')) {
            TwitchX.setStatus('Auto-recovered playback smoothness', 'info');
          }
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
TwitchX.cancelGentleReset = cancelGentleReset;
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
TwitchX.requestVideoReset = requestVideoReset;
TwitchX.beginStreamRecovery = beginStreamRecovery;
TwitchX.cancelStreamRecovery = cancelStreamRecovery;
TwitchX.applyNewStreamSource = applyNewStreamSource;
TwitchX.showPlayerError = showPlayerError;
TwitchX.hidePlayerError = hidePlayerError;
TwitchX._onStreamUrlRefreshed = _onStreamUrlRefreshed;
TwitchX._handlePlayerRetryClick = _handlePlayerRetryClick;
TwitchX._watchNetworkChanges = _watchNetworkChanges;
TwitchX._currentQuality = _currentQuality;
TwitchX._bindPlayerContentEvents = _bindPlayerContentEvents;

/* ── Codec capability probe ─────────────────────────────── */
// Twitch only offers its Enhanced Broadcasting renditions (1440p60 and up) to
// clients that accept HEVC or AV1, and that choice is baked into the signed
// resolve URL. HEVC is safe to ask for on any modern Mac; AV1 is not, because
// hardware decode starts at M3 and software-decoding 1440p60 AV1 is ruinous.
// mediaCapabilities.decodingInfo answers exactly that question: powerEfficient
// is the hardware-decode signal, smooth is the sustained-framerate one.

function _decodeProbe(codecs, width, height, bitrate) {
  return {
    // Playback goes through a plain <video src> element, so "file" is the mode
    // that matches. media-source is the fallback for WebKit builds that only
    // answer for MSE.
    type: 'file',
    video: {
      contentType: 'video/mp4; codecs="' + codecs + '"',
      width: width,
      height: height,
      bitrate: bitrate,
      framerate: 60,
    },
  };
}

const AV1_PROBE = _decodeProbe('av01.0.09M.08', 2560, 1440, 12000000);
const HEVC_PROBE = _decodeProbe('hvc1.1.6.L153.B0', 2560, 1440, 10000000);

function _decodingInfo(mc, config) {
  return mc.decodingInfo(config)
    .then(function(r) {
      if (r && r.supported) return r;
      // Some WebKit builds only answer for MediaSource.
      return mc.decodingInfo(Object.assign({}, config, { type: 'media-source' }))
        .catch(function() { return r; });
    })
    .catch(function() {
      return mc.decodingInfo(Object.assign({}, config, { type: 'media-source' }))
        .catch(function() { return null; });
    });
}

function probeCodecSupport() {
  if (!TwitchX.api || !TwitchX.api.set_codec_support) return;

  const report = function(av1, hevc) {
    try {
      TwitchX.api.set_codec_support({ av1: av1, hevc: hevc });
    } catch (e) {
      console.warn('[Codecs] reporting support failed', e);
    }
  };

  const mc = navigator.mediaCapabilities;
  if (!mc || typeof mc.decodingInfo !== 'function') {
    // canPlayType cannot distinguish hardware from software decoding, and in
    // this WebView it answers "probably" for AV1 that decodingInfo rejects
    // outright. Without decodingInfo, AV1 stays off and only HEVC is claimed.
    console.log('[Codecs] mediaCapabilities unavailable, assuming HEVC only');
    report(false, true);
    return;
  }

  Promise.all([
    _decodingInfo(mc, AV1_PROBE),
    _decodingInfo(mc, HEVC_PROBE),
  ]).then(function(results) {
    const av1 = results[0];
    const hevc = results[1];
    // All three flags are required: a decoder that is supported but neither
    // smooth nor power-efficient is a software decoder, which is what asking
    // Twitch for AV1 must avoid.
    const av1Hardware = !!(av1 && av1.supported && av1.smooth && av1.powerEfficient);
    const hevcOk = !!(hevc && hevc.supported);
    console.log('[Codecs] av1 hardware:', av1Hardware, 'hevc:', hevcOk);
    report(av1Hardware, hevcOk);
  }).catch(function(e) {
    console.warn('[Codecs] probe failed', e);
    report(false, true);
  });
}

TwitchX.probeCodecSupport = probeCodecSupport;

/* ── Live quality switching ─────────────────────────────── */
// Changing quality used to take effect only on the next launch. Re-resolving and
// crossfading reuses the reset machinery, so the switch costs one short fade
// instead of a full stop/start of the player and the chat.

function changeQualityLive(quality) {
  const channel = TwitchX.state.watchingChannel;
  const platform = TwitchX.state.playerPlatform || 'twitch';
  if (!channel || !_isLivePlayback()) return false;
  if (platform === 'youtube') return false;
  if (!TwitchX.api || !TwitchX.api.refresh_stream_url) return false;
  if (TwitchX._recovery.pending) return false;

  TwitchX._qualitySwitchPending = true;
  TwitchX._recovery.pending = true;
  TwitchX._recovery.requestId += 1;
  const requestId = TwitchX._recovery.requestId;
  _armRefreshWatchdog();
  TwitchX.setStatus('Switching to ' + quality + '...', 'warn');
  try {
    TwitchX.api.refresh_stream_url(channel, platform, quality, requestId);
  } catch (e) {
    TwitchX._qualitySwitchPending = false;
    TwitchX._recovery.pending = false;
    _disarmRefreshWatchdog();
    console.warn('[Player] quality switch failed', e);
    return false;
  }
  return true;
}

function _handleQualitySelectChange() {
  const playerView = document.getElementById('player-view');
  if (!playerView || !playerView.classList.contains('view-active')) return;
  changeQualityLive(_currentQuality());
}

TwitchX.changeQualityLive = changeQualityLive;
TwitchX._handleQualitySelectChange = _handleQualitySelectChange;

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
    TwitchX.setIconText(btn, 'stop', 12, 'Stop REC');
    btn.classList.add('recording');
    btn.title = 'Stop Recording';
    btn.setAttribute('aria-label', 'Stop Recording');
    if (dot) dot.classList.remove('hidden');
  } else {
    TwitchX.setIconText(btn, 'record', 12, 'REC');
    btn.classList.remove('recording');
    btn.title = 'Start Recording';
    btn.setAttribute('aria-label', 'Start Recording');
    if (dot) dot.classList.add('hidden');
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

  // Update buffer visualization bar
  _updateBufferBar(video);

  TwitchX._statsRafId = requestAnimationFrame(function() {
    setTimeout(updateStatsOverlay, 500);
  });
}

function showStatsOverlay() {
  TwitchX._statsOverlayActive = true;
  var overlay = document.getElementById('stats-overlay');
  var btn = document.getElementById('stats-overlay-btn');
  if (overlay) overlay.classList.remove('hidden');
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
  if (overlay) overlay.classList.add('hidden');
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
  if (el) el.classList.remove('hidden');
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
  if (el) { el.classList.add('hidden'); el.textContent = ''; }
}

/* ── Buffer Visualization Bar ─────────────────────────── */

function _updateBufferBar(video) {
  var loaded = document.getElementById('buffer-loaded');
  var pos = document.getElementById('buffer-position');
  if (!loaded) return;
  if (!video || !video.src) {
    loaded.style.setProperty('--buffer-loaded-width', '0%');
    if (pos) pos.classList.add('hidden');
    return;
  }
  var w = 0;
  if (video.buffered && video.buffered.length > 0) {
    var dur = video.duration;
    if (isFinite(dur) && dur > 0) {
      w = (video.buffered.end(video.buffered.length - 1) / dur) * 100;
      if (pos) {
        var pct = (video.currentTime / dur) * 100;
        pos.classList.remove('hidden');
        pos.style.setProperty('--buffer-position-left', Math.min(pct, 100) + '%');
      }
    }
  }
  loaded.style.setProperty('--buffer-loaded-width', Math.min(w, 100) + '%');
}

/* ── VOD Seek Bar ─────────────────────────────────────── */

function startVodSeekBar() {
  stopVodSeekBar();
  var container = document.getElementById('seek-bar-container');
  if (container) container.classList.remove('hidden');
  var seek = document.getElementById('seek-bar');
  if (!seek) return;
  TwitchX._seekBarTimer = setInterval(function() {
    var video = getPlayerVideo();
    if (!video || !video.src) return;
    var dur = video.duration;
    if (isFinite(dur) && dur > 0) {
      seek.max = 1000;
      var val = Math.round((video.currentTime / dur) * 1000);
      seek.value = val;
      seek.style.setProperty('--seek-pct', (val / 10) + '%');
    }
  }, 250);
}

function stopVodSeekBar() {
  if (TwitchX._seekBarTimer) { clearInterval(TwitchX._seekBarTimer); TwitchX._seekBarTimer = null; }
  var container = document.getElementById('seek-bar-container');
  if (container) container.classList.add('hidden');
}

function _handleSeekBarInput() {
  var seek = document.getElementById('seek-bar');
  var tooltip = document.getElementById('seek-tooltip');
  if (!seek) return;
  seek.style.setProperty('--seek-pct', (parseInt(seek.value, 10) / 10) + '%');
  if (tooltip) {
    var frac = parseInt(seek.value, 10) / 1000;
    var video = getPlayerVideo();
    var dur = video && video.duration;
    if (isFinite(dur) && dur > 0) {
      tooltip.textContent = formatVideoTime(frac * dur);
      tooltip.classList.remove('hidden');
      var rect = seek.getBoundingClientRect();
      var pct = frac * rect.width;
      tooltip.style.left = Math.min(Math.max(pct - 20, 0), rect.width - 40) + 'px';
    }
  }
}

function _handleSeekBarChange() {
  var seek = document.getElementById('seek-bar');
  var tooltip = document.getElementById('seek-tooltip');
  var video = getPlayerVideo();
  if (tooltip) tooltip.classList.add('hidden');
  if (!seek || !video) return;
  var frac = parseInt(seek.value, 10) / 1000;
  var dur = video.duration;
  if (isFinite(dur) && dur > 0) {
    video.currentTime = frac * dur;
  }
}

function _handleSeekBarLeave() {
  var tooltip = document.getElementById('seek-tooltip');
  if (tooltip) tooltip.classList.add('hidden');
}

/* ── Fullscreen auto-hide controls ────────────────────── */

function _startFullscreenAutoHide() {
  _stopFullscreenAutoHide();
  TwitchX._fsHideTimer = null;
  TwitchX._fsAutoHideActive = true;

  function _resetControlsTimer() {
    _showControls();
    if (TwitchX._fsHideTimer) clearTimeout(TwitchX._fsHideTimer);
    TwitchX._fsHideTimer = setTimeout(_hideControls, 3000);
  }

  function _showControls() {
    var bar = document.getElementById('player-bar');
    var header = document.getElementById('player-header');
    var stats = document.getElementById('stats-overlay');
    if (bar) bar.classList.remove('fs-hidden');
    if (header) header.classList.remove('fs-hidden');
    if (stats && TwitchX._statsOverlayActive) stats.classList.remove('hidden');
  }

  function _hideControls() {
    if (!TwitchX._fsAutoHideActive) return;
    var video = getPlayerVideo();
    if (!video || !isVideoFullscreen(video)) return;
    var bar = document.getElementById('player-bar');
    var header = document.getElementById('player-header');
    var stats = document.getElementById('stats-overlay');
    if (bar) bar.classList.add('fs-hidden');
    if (header) header.classList.add('fs-hidden');
    if (stats) stats.classList.add('hidden');
  }

  var content = document.getElementById('player-content');
  if (content) {
    content.addEventListener('mousemove', _resetControlsTimer);
    content.addEventListener('mouseenter', _resetControlsTimer);
  }

  TwitchX._fsResetControlsTimer = _resetControlsTimer;
  TwitchX._fsShowControls = _showControls;
  TwitchX._fsHideControls = _hideControls;
  TwitchX._fsMouseTarget = content;
}

function _stopFullscreenAutoHide() {
  TwitchX._fsAutoHideActive = false;
  if (TwitchX._fsHideTimer) { clearTimeout(TwitchX._fsHideTimer); TwitchX._fsHideTimer = null; }
  var content = TwitchX._fsMouseTarget;
  if (content) {
    content.removeEventListener('mousemove', TwitchX._fsResetControlsTimer);
    content.removeEventListener('mouseenter', TwitchX._fsResetControlsTimer);
  }
  TwitchX._fsMouseTarget = null;
  if (TwitchX._fsShowControls) TwitchX._fsShowControls();
}

/* ── Fullscreen change listener ───────────────────────── */

function _watchFullscreenChanges() {
  var handler = function() {
    var video = getPlayerVideo();
    if (video && isVideoFullscreen(video)) {
      _startFullscreenAutoHide();
    } else {
      _stopFullscreenAutoHide();
    }
  };
  document.addEventListener('fullscreenchange', handler);
  document.addEventListener('webkitfullscreenchange', handler);
  document.addEventListener('webkitpresentationmodechanged', handler);
}

TwitchX.startVodTimeDisplay = startVodTimeDisplay;
TwitchX.stopVodTimeDisplay  = stopVodTimeDisplay;
TwitchX.startVodSeekBar = startVodSeekBar;
TwitchX.stopVodSeekBar = stopVodSeekBar;
TwitchX.syncVolumeSlider = syncVolumeSlider;
TwitchX._handleVolumeSliderInput = _handleVolumeSliderInput;
TwitchX._handleMuteBtnClick = _handleMuteBtnClick;
TwitchX._handleSeekBarInput = _handleSeekBarInput;
TwitchX._handleSeekBarChange = _handleSeekBarChange;
TwitchX._handleSeekBarLeave = _handleSeekBarLeave;
TwitchX._watchFullscreenChanges = _watchFullscreenChanges;
