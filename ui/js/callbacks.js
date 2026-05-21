window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

window.onStreamsUpdate = function(data) {
  TwitchX.state.hasCredentials = data.has_credentials !== false;
  TwitchX.state.favorites = data.favorites || [];
  TwitchX.state.favoritesMeta = data.favorites_meta || {};
  TwitchX.state.liveSet = new Set(data.live_set || []);
  TwitchX.state.userAvatars = data.user_avatars || {};

  if (TwitchX.hideSkeletonGrid) TwitchX.hideSkeletonGrid();

  // Phase 9: keep PiP button visibility in sync with server config
  TwitchX.state.pipEnabled = data.pip_enabled === true;
  const pipBtn = document.getElementById('pip-player-btn');
  if (pipBtn) pipBtn.classList.toggle('hidden', !TwitchX.state.pipEnabled);

  // Compute viewer trends
  const newStreams = data.streams || [];
  for (const s of newStreams) {
    const prev = TwitchX.state.prevViewers[s.login];
    if (prev !== undefined && prev !== s.viewers) {
      s.viewer_trend = s.viewers > prev ? 'up' : 'down';
    } else {
      s.viewer_trend = null;
    }
    TwitchX.state.prevViewers[s.login] = s.viewers;
  }
  TwitchX.state.streams = newStreams;

  // Detect offline→online transitions for notification badges
  if (!TwitchX._prevLiveSet) TwitchX._prevLiveSet = new Set();
  var newLive = new Set(data.live_set || []);
  var badgeLogins = [];
  newLive.forEach(function(login) {
    if (!TwitchX._prevLiveSet.has(login)) {
      badgeLogins.push(login);
    }
  });
  TwitchX._prevLiveSet = newLive;
  TwitchX._notifBadgeLogins = badgeLogins;

  TwitchX.renderGrid();
  TwitchX.renderSidebar();

  // Update player bar
  if (data.updated_time) {
    document.getElementById('updated-time').textContent = 'Updated ' + data.updated_time;
    document.getElementById('updated-time').classList.remove('stale');
  }
  if (data.total_viewers > 0) {
    document.getElementById('total-viewers').textContent =
      (data.total_viewers_formatted || data.total_viewers) + ' viewers';
  } else {
    document.getElementById('total-viewers').textContent = '';
  }

  const liveCount = TwitchX.state.liveSet.size;
  TwitchX.setStatus(
    liveCount + ' channel' + (liveCount !== 1 ? 's' : '') + ' live',
    liveCount > 0 ? 'success' : 'info'
  );

  // Throttle background image fetching when player is active
  const playerActive = document.getElementById('player-view').classList.contains('active');

  // Request avatars for sidebar
    if (!playerActive) {
    for (const fav of TwitchX.state.favorites) {
      if (!TwitchX.state.avatars[fav]) {
        const meta = TwitchX.getFavoriteMeta(fav);
        const platform = (meta && meta.platform) || 'twitch';
        if (TwitchX.api) TwitchX.api.get_avatar(fav, platform);
      }
    }
  } else {
    // When player is active, only fetch avatars for currently visible sidebar items
    // via requestIdleCallback to avoid main-thread contention with video compositing
    if (typeof requestIdleCallback === 'function') {
      requestIdleCallback(function() {
        for (const fav of TwitchX.state.favorites) {
          if (!TwitchX.state.avatars[fav]) {
            const meta = TwitchX.getFavoriteMeta(fav);
            const platform = (meta && meta.platform) || 'twitch';
            if (TwitchX.api) TwitchX.api.get_avatar(fav, platform);
          }
        }
      }, { timeout: 2000 });
    }
  }

  // Request thumbnails for live streams
  if (!playerActive) {
    for (const s of TwitchX.state.streams) {
      if (!TwitchX.state.thumbnails[s.login] && s.thumbnail_url) {
        TwitchX.api.get_thumbnail(s.login, s.thumbnail_url);
      }
    }
  }

  // Prune stale caches — keep only entries for current favorites or live streams.
  const keepLogins = new Set(TwitchX.state.favorites.concat(TwitchX.state.streams.map(function(s) { return s.login; })));
  for (const key in TwitchX.state.avatars) {
    if (!keepLogins.has(key)) delete TwitchX.state.avatars[key];
  }
  for (const key in TwitchX.state.thumbnails) {
    if (!keepLogins.has(key)) delete TwitchX.state.thumbnails[key];
  }
  for (const key in TwitchX.state.prevViewers) {
    if (!keepLogins.has(key)) delete TwitchX.state.prevViewers[key];
  }
};

window.onSearchResults = function(results) {
  TwitchX.state.searchResults = results || [];
  const dd = document.getElementById('search-dropdown');
  while (dd.firstChild) dd.removeChild(dd.firstChild);
  if (!results || results.length === 0) {
    dd.classList.remove('visible');
    while (dd.firstChild) dd.removeChild(dd.firstChild);
    return;
  }
  // Build search results using safe DOM methods
  while (dd.firstChild) dd.removeChild(dd.firstChild);
  results.forEach(function(r) {
    const row = document.createElement('div');
    row.className = 'search-result';
    row.dataset.login = r.login;

    const info = document.createElement('div');
    info.className = 'sr-info';

    const name = document.createElement('div');
    name.className = 'sr-name';
    name.textContent = r.display_name;
    if (r.platform) {
      const badge = document.createElement('span');
      badge.className = 'platform-badge ' + r.platform;
      badge.textContent = r.platform === 'kick' ? 'Kick' : r.platform === 'youtube' ? 'YouTube' : 'Twitch';
      name.appendChild(document.createTextNode(' '));
      name.appendChild(badge);
    }
    info.appendChild(name);

    const game = document.createElement('div');
    game.className = 'sr-game';
    if (r.is_live) {
      const liveSpan = document.createElement('span');
      liveSpan.className = 'sr-live';
      liveSpan.textContent = 'LIVE';
      game.appendChild(liveSpan);
      game.appendChild(document.createTextNode(' '));
    }
    game.appendChild(document.createTextNode(r.game_name || ''));
    info.appendChild(game);

    const addBtn = document.createElement('button');
    addBtn.className = 'sr-add';
    addBtn.textContent = '+';
    addBtn.title = 'Add to favorites';
    addBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      TwitchX.addChannelDirect(r.login, r.platform || 'twitch', r.display_name);
      TwitchX.state.searchResults = [];
    });

    row.appendChild(info);
    row.appendChild(addBtn);
    row.addEventListener('click', function() {
      TwitchX.addChannelDirect(r.login, r.platform || 'twitch', r.display_name);
      dd.classList.remove('visible');
      TwitchX.state.searchResults = [];
      document.getElementById('search-input').value = '';
    });
    dd.appendChild(row);
  });
  dd.classList.add('visible');
};

window.onLoginComplete = function(user) {
  TwitchX.showUserProfile(user);
  TwitchX.showToast('Logged in as ' + user.display_name, 'success');
};

window.onLoginError = function(msg) {
  TwitchX.showToast('Login error: ' + msg, 'error');
};

window.onLogout = function() {
  TwitchX.hideUserProfile();
  TwitchX.showToast('Logged out', 'info');
};

window.onImportComplete = function(data) {
  TwitchX.showToast('Imported ' + data.added + ' channel' + (data.added !== 1 ? 's' : ''), 'success');
};

window.onImportError = function(msg) {
  TwitchX.showToast('Import error: ' + msg, 'error');
};

window.onLaunchResult = function(data) {
  var loader = document.getElementById('stream-loader');
  if (loader) loader.classList.add('hidden');
  if (data.success) {
    TwitchX.state.watchingChannel = data.channel;
    TwitchX.setStatus(data.message, 'success');
    document.getElementById('live-dot').classList.add('visible');
    TwitchX.renderGrid();
  } else {
    TwitchX.setStatus(data.message, 'error');
  }
};

window.onLaunchProgress = function(data) {
  TwitchX.setStatus('Launching ' + data.channel + '... (' + data.elapsed + 's)', 'warn');
  var loader = document.getElementById('stream-loader');
  if (loader) loader.classList.remove('hidden');
};

window.onStreamReady = function(data) {
  // Clear stale chat messages from the previous stream before switching
  TwitchX.clearChatMessages();
  if (TwitchX.clearChatBatch) TwitchX.clearChatBatch();
  var loader = document.getElementById('stream-loader');
  if (loader) loader.classList.add('hidden');

  TwitchX.state.playerPlatform = data.platform || 'twitch';
  TwitchX.state.playerHasChat = data.has_chat !== false;
  TwitchX.state.streamType = data.stream_type || 'live';
  document.getElementById('player-channel-name').textContent = data.channel || '';
  document.getElementById('player-stream-title').textContent = data.title || '';

  // HLS / native video path (Twitch, Kick, YouTube via streamlink)
  // Cancel any in-flight gentle reset so the new src lands on the correct element.
  if (TwitchX.cancelGentleReset) TwitchX.cancelGentleReset();
  const video = TwitchX.getPlayerVideo();
  if (!video) return;
  video.src = data.url;
  video.play().catch(function(e) {
    console.warn('[Player] video.play() rejected:', e && e.message || e);
    TwitchX.setStatus('Playback blocked — click to resume', 'warn');
  });
  const extBtn = document.getElementById('watch-external-btn');
  if (extBtn) { extBtn.disabled = false; extBtn.style.opacity = ''; }
  var modBtn = document.getElementById('chat-mod-btn');
  if (modBtn) {
    var isTwitch = data.platform === 'twitch';
    var isBroadcaster = isTwitch && TwitchX.chatSelfLogin &&
      TwitchX.chatSelfLogin.toLowerCase() === (data.channel || '').toLowerCase();
    modBtn.classList.toggle('hidden', !isBroadcaster);
  }

  TwitchX.showPlayerView();
};

window.onPlayerStop = function() {
  TwitchX.state.streamType = 'live';
  var loader = document.getElementById('stream-loader');
  if (loader) loader.classList.add('hidden');
  TwitchX._hidePlayerFromPython = true;
  TwitchX.hidePlayerView();
  TwitchX._hidePlayerFromPython = false;
};

window.onRecordingState = function(data) {
  TwitchX._recordingActive = !!data.active;
  TwitchX.updateRecordButton();
  if (data.error) {
    TwitchX.showToast('Recording error: ' + data.error, 'error');
  } else if (data.active && data.filename) {
    var name = data.filename.split('/').pop();
    TwitchX.setStatus('Recording: ' + name, 'info');
  } else {
    TwitchX.showToast('Recording stopped', 'info');
  }
};

window.onPlayerState = function(data) {
  TwitchX.state.playerState = data.state;
  TwitchX.state.playerChannel = data.channel;
  TwitchX.state.playerTitle = data.title || '';
  TwitchX.state.playerError = data.error || '';
};

window.onMultiSlotReady = function(data) {
  const idx = data.slot_idx;
  const slotEl = document.querySelector('.ms-slot[data-slot-idx="' + idx + '"]');
  if (!slotEl || !TwitchX.multiState.slots[idx]) return;
  const active = slotEl.querySelector('.ms-slot-active');
  const loading = active.querySelector('.ms-loading');
  const errEl = active.querySelector('.ms-error-msg');

  if (data.error) {
    loading.classList.add('hidden');
    errEl.textContent = data.error;
    errEl.classList.remove('hidden');
    return;
  }

  const video = active.querySelector('.ms-video');
  video.src = data.url;
  video.muted = (TwitchX.multiState.audioFocus !== idx);
  video.play().catch(function(e) {
    console.warn('[Multistream] slot', idx, 'video.play() rejected:', e && e.message || e);
  });
  loading.classList.add('hidden');
  errEl.classList.add('hidden');

  active.querySelector('.ms-channel-name').textContent = data.channel || '';
  var badge = active.querySelector('.ms-platform-badge');
  badge.className = 'ms-platform-badge ' + (data.platform || 'twitch');
  badge.textContent = (data.platform || '').charAt(0).toUpperCase();
  if (data.title) TwitchX.multiState.slots[idx].title = data.title;

  if (TwitchX.multiState.audioFocus === -1) TwitchX.setAudioFocus(idx);
  if (TwitchX.multiState.chatSlot === -1) TwitchX.switchMultiChat(idx);
};

/* ── Chat message batching ──────────────────────────────── */
(function() {
  let chatBatch = [];
  let chatBatchTimer = null;
  const BATCH_MS = 50;
  const MAX_CHAT_MESSAGES = 150;

  function flushChatBatch() {
    if (chatBatch.length === 0) return;
    const msgs = chatBatch;
    chatBatch = [];
    const container = TwitchX._getChatMessagesEl();
    if (!container) return;

    function _hasBadge(msg, prefix) {
      return msg.badges && msg.badges.some(function(b) {
        return b.name === prefix || b.name.startsWith(prefix + '/') || b.name.startsWith(prefix + '_');
      });
    }

    function _shouldFilter(msg) {
      if (msg.is_system) return false;
      if (TwitchX.chatFilters.subOnly && !_hasBadge(msg, 'subscriber') && !_hasBadge(msg, 'broadcaster')) return true;
      if (TwitchX.chatFilters.modOnly && !_hasBadge(msg, 'moderator') && !_hasBadge(msg, 'broadcaster')) return true;
      if (TwitchX.chatBlockList.length > 0) {
        var lower = (msg.text || '').toLowerCase();
        for (var bi = 0; bi < TwitchX.chatBlockList.length; bi++) {
          if (lower.indexOf(TwitchX.chatBlockList[bi]) !== -1) return true;
        }
      }
      if (TwitchX.chatFilters.antiSpam && msg.author) {
        var prev = TwitchX.chatSpamMap[msg.author];
        if (prev && prev === msg.text) return true;
        TwitchX.chatSpamMap[msg.author] = msg.text;
        if (msg.text && msg.text.length >= 10) {
          var letters = msg.text.replace(/[^a-zA-Z]/g, '');
          if (letters.length >= 6) {
            var uppers = letters.replace(/[^A-Z]/g, '').length;
            if (uppers / letters.length > 0.70) return true;
          }
        }
      }
      return false;
    }

    const fragment = document.createDocumentFragment();
    const isMulti = TwitchX.multiState.open;
    const maxMsgs = isMulti ? MAX_CHAT_MESSAGES : MAX_CHAT_MESSAGES;

    msgs.forEach(function(msg) {
      if (_shouldFilter(msg)) return;
      if (TwitchX._appendChatLog) TwitchX._appendChatLog(msg);

      if (msg.msg_id) {
        const existing = container.querySelector('.chat-msg[data-msg-id="' + String(msg.msg_id).replace(/"/g, '\\"') + '"]');
        if (existing) return;
      }

      const el = document.createElement('div');
      let cls = 'chat-msg';
      if (msg.is_system) cls += ' system';
      if (msg.is_self) cls += ' self';
      el.className = cls;
      if (msg.msg_id) el.dataset.msgId = msg.msg_id;

      var selfLogin = TwitchX.chatSelfLogin;
      if (selfLogin && !msg.is_self && msg.text &&
          msg.text.toLowerCase().indexOf(selfLogin.toLowerCase()) !== -1) {
        el.className += ' mention';
      }

      // Reply context line
      if (msg.reply_to_display && msg.reply_to_body) {
        const ctx = document.createElement('div');
        ctx.className = 'chat-reply-ctx';
        const rNick = document.createElement('span');
        rNick.className = 'reply-nick';
        rNick.textContent = '@' + msg.reply_to_display;
        ctx.appendChild(rNick);
        ctx.appendChild(document.createTextNode(': ' + msg.reply_to_body));
        el.appendChild(ctx);
      }

      // Timestamp (hidden by default, shown when TwitchX.chatTimestamps is true)
      var tsEl = document.createElement('span');
      tsEl.className = 'msg-time';
      if (msg.timestamp) {
        try { tsEl.textContent = new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }); }
        catch(e) { tsEl.textContent = '--:--:--'; }
      } else {
        tsEl.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      }
      if (TwitchX.chatTimestamps) tsEl.style.display = 'inline';
      el.appendChild(tsEl);

      for (let i = 0; i < msg.badges.length; i++) {
        const badge = msg.badges[i];
        if (badge.icon_url) {
          const img = document.createElement('img');
          img.className = 'badge';
          img.src = badge.icon_url;
          img.alt = badge.name;
          el.appendChild(img);
        }
      }

      if (!msg.is_system) {
        const nick = document.createElement('span');
        nick.className = 'nick';
        nick.textContent = msg.author_display;
        if (msg.author_color) nick.style.color = msg.author_color;
        el.appendChild(nick);

        const sep = document.createElement('span');
        sep.textContent = ': ';
        el.appendChild(sep);
      }

      TwitchX.renderChatEmotes(el, msg.text, msg.emotes);

      // Reply button (hover) — for non-system messages with an id, when authenticated
      if (!msg.is_system && msg.msg_id && TwitchX.chatAuthenticated) {
        const replyBtn = document.createElement('button');
        replyBtn.className = 'reply-btn';
        replyBtn.title = 'Reply';
        replyBtn.innerHTML = TwitchX.renderIcon('reply', 14);
        replyBtn.addEventListener('click', function(e) {
          e.stopPropagation();
          TwitchX.setChatReply(msg.msg_id, msg.author_display, msg.text);
        });
        el.appendChild(replyBtn);
      }

      fragment.appendChild(el);
    });

    container.appendChild(fragment);

    while (container.children.length > maxMsgs) {
      container.removeChild(container.firstChild);
    }

    if (TwitchX._getChatAutoScroll()) {
      container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
    } else {
      const btn = TwitchX._getChatNewMsgEl();
      if (btn) btn.classList.add('visible');
    }
  }

  function clearChatBatch() {
    chatBatch = [];
    if (chatBatchTimer) {
      clearTimeout(chatBatchTimer);
      chatBatchTimer = null;
    }
  }

  window.onChatMessage = function(msg) {
    chatBatch.push(msg);
    if (!chatBatchTimer) {
      chatBatchTimer = setTimeout(function() {
        chatBatchTimer = null;
        flushChatBatch();
      }, BATCH_MS);
    }
  };

  TwitchX.clearChatBatch = clearChatBatch;
})();

window.onChatSendResult = function(result) {
  if (!result) return;
  const pending = result.request_id ? TwitchX.chatPendingSends[result.request_id] : null;
  if (result.request_id) delete TwitchX.chatPendingSends[result.request_id];
  if (result.ok) return;

  TwitchX.showToast(result.error || 'Failed to send chat message', 'error');
  const input = document.getElementById(TwitchX.multiState.open ? 'ms-chat-input' : 'chat-input');
  if (input && !input.value && pending && pending.text) {
    input.value = pending.text;
  }
  if (pending && pending.reply && !TwitchX.chatReplyTo) {
    TwitchX.setChatReply(pending.reply.id, pending.reply.display, pending.reply.body);
  }
  if (input && !input.disabled) input.focus();
};

window.onChatStatus = function(status) {
  if (TwitchX.multiState.open) {
    const dot = document.getElementById('ms-chat-status-dot');
    if (dot) {
      dot.className = status.connected ? 'connected' : '';
      dot.title = status.connected ? 'Connected' : (status.error || 'Disconnected');
    }
    const inp = document.getElementById('ms-chat-input');
    const btn = document.getElementById('ms-chat-send-btn');
    if (inp) inp.disabled = !(status.connected && status.authenticated);
    if (btn) btn.disabled = !(status.connected && status.authenticated);
    return;
  }
  TwitchX.chatAuthenticated = !!(status.authenticated);
  TwitchX.chatPlatform = status.platform || TwitchX.state.playerPlatform || 'twitch';
  if (status.self_login) TwitchX.chatSelfLogin = status.self_login;
  const dot = document.getElementById('chat-status-dot');
  var statusText = document.getElementById('chat-status-text');
  if (dot) {
    if (status.connected) {
      dot.classList.remove('connecting');
      dot.classList.add('connected');
      dot.title = status.authenticated ? 'Connected' : 'Connected (read-only)';
      if (statusText) statusText.textContent = '';
      if (TwitchX.clearChatBatch) TwitchX.clearChatBatch();
      TwitchX.clearChatMessages();
      TwitchX.chatAutoScroll = true;
      TwitchX.loadChatFiltersFromConfig();
      const newBtn = document.getElementById('chat-new-messages');
      if (newBtn) newBtn.classList.remove('visible');
    } else {
      dot.classList.remove('connected');
      dot.classList.remove('connecting');
      dot.title = status.error || 'Disconnected';
      if (statusText) statusText.textContent = status.error ? status.error : 'Disconnected';
      TwitchX.chatSelfLogin = '';
      TwitchX.clearChatReply();
    }
  }
  TwitchX.updateChatInput();
};

window.onThirdPartyEmotes = function(data) {
  if (!data || !data.emotes) return;
  Object.assign(TwitchX.thirdPartyEmotes, data.emotes);
  TwitchX._cachedPickerEmotes = null;
  if (TwitchX._emotePickerOpen) {
    var searchEl = document.getElementById('emote-search');
    TwitchX.renderEmotePicker(searchEl ? searchEl.value : '');
  }
};

window.onChatUserList = function(data) {
  TwitchX._chatUserList = data.users || [];
  var countEl = document.getElementById('chat-userlist-count');
  if (countEl) countEl.textContent = data.count || TwitchX._chatUserList.length;
  var panel = document.getElementById('chat-userlist-panel');
  if (panel && !panel.classList.contains('hidden')) {
    TwitchX.renderChatUserList('');
  }
};

window.onChatModeChanged = function(data) {
  if (!data.ok) {
    TwitchX.showToast('Chat mode error: ' + (data.error || 'unknown'), 'error');
    return;
  }
  TwitchX.showToast(
    (data.value ? 'Enabled' : 'Disabled') + ' ' + data.mode.replace(/_/g, ' '),
    'info'
  );
};

window.onTestResult = function(data) {
  const fb = document.getElementById('settings-feedback');
  if (data.success) {
    fb.innerHTML = TwitchX.renderIcon('check', 14) + ' ' + data.message;
    fb.style.color = 'var(--live-green)';
  } else {
    fb.innerHTML = TwitchX.renderIcon('cross', 14) + ' ' + data.message;
    fb.style.color = 'var(--error-red)';
  }
  document.getElementById('test-btn').disabled = false;
};

window.onSettingsSaved = function() {
  TwitchX.closeSettings();
};

window.onKickLoginComplete = function(data) {
  TwitchX.state.kickUser = { login: data.login, display_name: data.display_name };
  TwitchX.state.kickScopes = data.scopes || TwitchX.state.kickScopes || '';
  document.getElementById('kick-login-area').classList.add('hidden');
  document.getElementById('kick-user-area').classList.remove('hidden');
  document.getElementById('kick-user-display').textContent = 'Logged in as ' + (data.display_name || data.login);
  const fb = document.getElementById('settings-feedback');
  if ((TwitchX.state.kickScopes || '').split(/\s+/).indexOf('chat:write') === -1) {
    fb.textContent = 'Kick login succeeded, but granted scopes are: ' + (TwitchX.state.kickScopes || 'user:read channel:read');
    fb.style.color = 'var(--warn-yellow)';
    TwitchX.showToast('Kick login is missing chat:write, so chat stays read-only', 'warn');
  } else {
    fb.innerHTML = TwitchX.renderIcon('check', 14) + ' Kick login successful';
    fb.style.color = 'var(--live-green)';
    TwitchX.showToast('Logged in to Kick as ' + (data.display_name || data.login), 'success');
  }
  TwitchX.showKickProfile(data);
  TwitchX.updateChatInput();
};

window.onKickLoginError = function(msg) {
  const fb = document.getElementById('settings-feedback');
  fb.innerHTML = TwitchX.renderIcon('cross', 14) + ' Kick login failed: ' + msg;
  fb.style.color = 'var(--error-red)';
  TwitchX.showToast('Kick login: ' + msg, 'error');
};

window.onKickLogout = function() {
  TwitchX.state.kickUser = null;
  TwitchX.state.kickScopes = '';
  document.getElementById('kick-login-area').classList.remove('hidden');
  document.getElementById('kick-user-area').classList.add('hidden');
  document.getElementById('kick-user-display').textContent = '';
  const fb = document.getElementById('settings-feedback');
  fb.textContent = 'Logged out from Kick';
  fb.style.color = 'var(--text-muted)';
  TwitchX.hideKickProfile();
  TwitchX.updateChatInput();
};

window.onKickTestResult = function(data) {
  const fb = document.getElementById('settings-feedback');
  if (data.success) {
    fb.innerHTML = TwitchX.renderIcon('check', 14) + ' ' + data.message;
    fb.style.color = 'var(--live-green)';
  } else {
    fb.innerHTML = TwitchX.renderIcon('cross', 14) + ' ' + data.message;
    fb.style.color = 'var(--error-red)';
  }
  document.getElementById('kick-test-btn').disabled = false;
};

window.onYouTubeLoginComplete = function(data) {
  TwitchX.state.youtubeUser = { login: data.login, display_name: data.display_name };
  document.getElementById('yt-login-area').classList.add('hidden');
  document.getElementById('yt-user-area').classList.remove('hidden');
  document.getElementById('yt-display-name').textContent = 'Logged in as ' + (data.display_name || data.login);
  document.getElementById('yt-quota-display').textContent = 'Quota remaining: ' + (data.youtube_quota_remaining != null ? data.youtube_quota_remaining : '?');
  const fb = document.getElementById('settings-feedback');
  fb.innerHTML = TwitchX.renderIcon('check', 14) + ' YouTube login successful';
  fb.style.color = 'var(--live-green)';
  TwitchX.showToast('Logged in to YouTube as ' + (data.display_name || data.login), 'success');
};

window.onYouTubeLoginError = function(msg) {
  const fb = document.getElementById('settings-feedback');
  fb.innerHTML = TwitchX.renderIcon('cross', 14) + ' YouTube login failed: ' + msg;
  fb.style.color = 'var(--error-red)';
  TwitchX.showToast('YouTube login: ' + msg, 'error');
};

window.onYouTubeLogout = function() {
  TwitchX.state.youtubeUser = null;
  document.getElementById('yt-login-area').classList.remove('hidden');
  document.getElementById('yt-user-area').classList.add('hidden');
  document.getElementById('yt-display-name').textContent = '';
  document.getElementById('yt-quota-display').textContent = '';
  const fb = document.getElementById('settings-feedback');
  fb.textContent = 'Logged out from YouTube';
  fb.style.color = 'var(--text-muted)';
};

window.onYouTubeTestResult = function(result) {
  const tr = document.getElementById('yt-test-result');
  tr.classList.remove('hidden');
  if (result.success) {
    tr.innerHTML = TwitchX.renderIcon('check', 14) + ' ' + result.message;
    tr.style.color = 'var(--live-green)';
  } else {
    tr.innerHTML = TwitchX.renderIcon('cross', 14) + ' ' + result.message;
    tr.style.color = 'var(--error-red)';
  }
  document.getElementById('yt-test-btn').disabled = false;
};

window.onYouTubeImportComplete = function(data) {
  const count = data && typeof data === 'object' ? data.added : data;
  const tr = document.getElementById('yt-test-result');
  tr.classList.remove('hidden');
  tr.innerHTML = TwitchX.renderIcon('check', 14) + ' Imported ' + count + ' subscriptions';
  tr.style.color = 'var(--live-green)';
};

window.onYouTubeImportError = function(msg) {
  const tr = document.getElementById('yt-test-result');
  tr.classList.remove('hidden');
  tr.innerHTML = TwitchX.renderIcon('cross', 14) + ' Import failed: ' + msg;
  tr.style.color = 'var(--error-red)';
};

window.onAvatar = function(data) {
  TwitchX.state.avatars[data.login] = data.data;
  // Update sidebar avatars
  document.querySelectorAll('.channel-item[data-login="' + data.login + '"] .avatar').forEach(function(img) {
    img.src = data.data;
  });
  // Update user profile avatar
  const userAvatar = document.getElementById('user-avatar');
  if (userAvatar && userAvatar.dataset.login === data.login) {
    userAvatar.src = data.data;
  }
};

window.onThumbnail = function(data) {
  TwitchX.state.thumbnails[data.login] = data.data;
  const img = document.querySelector('.stream-card[data-login="' + data.login + '"] .thumb-img');
  if (img) {
    img.src = data.data;
    img.classList.add('loaded');
  }
};

window.onStatusUpdate = function(data) {
  TwitchX.setStatus(data.text, data.type || 'info');
  if (data.stale) {
    document.getElementById('updated-time').classList.add('stale');
  }
};

window.onBrowseCategories = function(categories) {
  document.getElementById('browse-loading').classList.add('hidden');
  const grid = document.getElementById('browse-categories-grid');
  grid.replaceChildren();
  if (!categories || !categories.length) {
    var emptyEl = document.getElementById('browse-empty');
    emptyEl.textContent = 'No categories found.';
    emptyEl.classList.remove('hidden');
    return;
  }
  categories.forEach(function(cat) {
    const card = document.createElement('div');
    card.className = 'browse-category-card card-enter';
    card.addEventListener('animationend', function() { card.classList.remove('card-enter'); }, { once: true });
    card.onclick = function() { TwitchX._triggerBrowseTopStreams(cat); };

    const img = document.createElement('img');
    img.className = 'browse-category-art';
    img.alt = '';
    if (cat.box_art_url) img.src = cat.box_art_url;
    img.onerror = function() { img.style.display = 'none'; };

    const info = document.createElement('div');
    info.className = 'browse-category-info';

    const nameEl = document.createElement('span');
    nameEl.className = 'browse-category-name';
    nameEl.textContent = cat.name;

    const badges = document.createElement('div');
    badges.className = 'browse-category-platforms';
    (cat.platforms || []).forEach(function(p) {
      const badge = document.createElement('span');
      badge.className = 'platform-badge ' + p;
      badge.textContent = p.charAt(0).toUpperCase();
      badges.appendChild(badge);
    });

    info.appendChild(nameEl);
    info.appendChild(badges);
    card.appendChild(img);
    card.appendChild(info);
    grid.appendChild(card);
  });
};

window.onBrowseTopStreams = function(payload) {
  document.getElementById('browse-loading').classList.add('hidden');
  // Discard if browse view is closed or user navigated away
  const browseView = document.getElementById('browse-view');
  if (!browseView || browseView.classList.contains('hidden')) return;
  if (TwitchX.state.browseMode !== 'streams') return;
  if (!payload || !payload.category || payload.category !== (TwitchX.state.browseCategory && TwitchX.state.browseCategory.name)) return;
  const grid = document.getElementById('browse-streams-grid');
  grid.replaceChildren();
  if (!payload || !payload.streams || !payload.streams.length) {
    var emptyEl = document.getElementById('browse-empty');
    emptyEl.textContent = 'No streams found for this category.';
    emptyEl.classList.remove('hidden');
    return;
  }
  payload.streams.forEach(function(stream) {
    const card = document.createElement('div');
    card.className = 'browse-stream-card card-enter';
    card.addEventListener('animationend', function() { card.classList.remove('card-enter'); }, { once: true });

    if (stream.platform !== 'youtube') {
      card.onclick = function() {
        TwitchX.hideBrowseView();
        const quality = document.getElementById('quality-select')
          ? document.getElementById('quality-select').value
          : 'best';
        if (TwitchX.api) TwitchX.api.watch_direct(stream.channel_login, stream.platform, quality);
      };
    }

    const thumb = document.createElement('img');
    thumb.className = 'browse-stream-thumb';
    thumb.alt = '';
    if (stream.thumbnail_url) thumb.src = stream.thumbnail_url;
    thumb.onerror = function() { thumb.style.display = 'none'; };

    const info = document.createElement('div');
    info.className = 'browse-stream-info';

    const badge = document.createElement('span');
    badge.className = 'platform-badge ' + stream.platform;
    badge.textContent = stream.platform.charAt(0).toUpperCase();

    const nameEl = document.createElement('span');
    nameEl.className = 'browse-stream-name';
    nameEl.textContent = stream.display_name;

    const titleEl = document.createElement('span');
    titleEl.className = 'browse-stream-title';
    titleEl.textContent = stream.title;

    const viewersEl = document.createElement('span');
    viewersEl.className = 'browse-stream-viewers';
    if (stream.viewers) viewersEl.textContent = TwitchX.formatViewers(stream.viewers);

    info.appendChild(badge);
    info.appendChild(nameEl);
    info.appendChild(titleEl);
    info.appendChild(viewersEl);
    card.appendChild(thumb);
    card.appendChild(info);

    const profileLink = document.createElement('div');
    profileLink.className = 'browse-stream-profile-link';
    profileLink.textContent = 'View Channel';
    (function(s) {
      profileLink.onclick = function(e) {
        e.stopPropagation();
        TwitchX.showChannelView(s.channel_login, s.platform, 'browse');
      };
    })(stream);
    card.appendChild(profileLink);

    grid.appendChild(card);
  });
};

window.onChannelProfile = function(profile) {
  document.getElementById('channel-loading').classList.add('hidden');

  if (!profile) {
    document.getElementById('channel-bio').textContent = 'Channel not found.';
    document.getElementById('channel-profile-card').style.opacity = '1';
    return;
  }

  TwitchX.channelProfile = profile;

  document.getElementById('channel-header-title').textContent = profile.display_name || profile.login;
  document.getElementById('channel-display-name').textContent = profile.display_name || profile.login;
  document.getElementById('channel-login-text').textContent = '@' + profile.login;

  const followersEl = document.getElementById('channel-followers');
  followersEl.textContent = profile.followers >= 0
    ? TwitchX.formatViewers(profile.followers) + ' followers'
    : '';

  var bioEl = document.getElementById('channel-bio');
  bioEl.textContent = profile.bio || '';
  bioEl.classList.toggle('hidden', !profile.bio);

  const avatarEl = document.getElementById('channel-avatar');
  if (profile.avatar_url) {
    avatarEl.src = profile.avatar_url;
    avatarEl.classList.remove('hidden');
  }

  document.getElementById('channel-live-badge').classList.toggle('hidden', !profile.is_live);
  document.getElementById('channel-live-empty').classList.toggle('hidden', !!profile.is_live);

  const followBtn = document.getElementById('channel-follow-btn');
  followBtn.textContent = profile.is_favorited ? 'Following' : 'Follow';
  followBtn.classList.toggle('following', !!profile.is_favorited);

  const canWatch = profile.is_live && profile.platform !== 'youtube';
  document.getElementById('channel-watch-btn').classList.toggle('hidden', !canWatch);

  document.getElementById('channel-profile-card').style.opacity = '1';
  TwitchX.ensureChannelTabLoaded(TwitchX.state.channelTabs.active);
};

window.onChannelMedia = function(payload) {
  if (!payload || !payload.tab || !TwitchX.state.channelTabs[payload.tab]) return;
  const channelView = document.getElementById('channel-view');
  if (!channelView || channelView.classList.contains('hidden')) return;
  if (!TwitchX.channelProfile) return;
  if (payload.login !== TwitchX.channelProfile.login || payload.platform !== TwitchX.channelProfile.platform) {
    return;
  }

  TwitchX.state.channelTabs[payload.tab] = {
    status: 'ready',
    items: payload.items || [],
    supported: payload.supported !== false,
    error: !!payload.error,
    message: payload.message || '',
  };
  TwitchX.renderChannelMediaTab(payload.tab);
};

window.onYouTubeQuotaWarning = function(data) {
  if (data.level === 'critical') {
    TwitchX.showToast(
      'YouTube API quota nearly exhausted (' + data.remaining + ' units left). Add a personal API key in Settings → YouTube.',
      'error'
    );
  } else {
    TwitchX.showToast(
      'YouTube quota at 80% (' + data.remaining + ' units left). Consider adding a personal API key in Settings → YouTube.',
      'warn'
    );
  }
};
