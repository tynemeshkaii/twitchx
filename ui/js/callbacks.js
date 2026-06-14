window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

window.onStreamsUpdate = function(data) {
  TwitchX.state.hasCredentials = data.has_credentials !== false;
  TwitchX.state.streamsLoaded = true;
  TwitchX.state.favoritesHydrated = true;
  TwitchX.state.favorites = data.favorites || [];
  TwitchX.state.favoritesMeta = data.favorites_meta || {};
  const newStreams = data.streams || [];
  TwitchX.state.liveSet = new Set(newStreams.map(function(s) {
    return TwitchX.channelKey(s.login, s.platform || 'twitch');
  }));
  TwitchX.state.userAvatars = data.user_avatars || {};

  if (TwitchX.hideSkeletonGrid) TwitchX.hideSkeletonGrid();

  // Phase 9: keep PiP button visibility in sync with server config
  TwitchX.state.pipEnabled = data.pip_enabled === true;
  const pipBtn = document.getElementById('pip-player-btn');
  if (pipBtn) pipBtn.classList.toggle('hidden', !TwitchX.state.pipEnabled);

  // Compute viewer trends
  for (const s of newStreams) {
    const streamKey = TwitchX.channelKey(s.login, s.platform || 'twitch');
    const prev = TwitchX.state.prevViewers[streamKey];
    if (prev !== undefined && prev !== s.viewers) {
      s.viewer_trend = s.viewers > prev ? 'up' : 'down';
    } else {
      s.viewer_trend = null;
    }
    TwitchX.state.prevViewers[streamKey] = s.viewers;
  }
  TwitchX.state.streams = newStreams;

  // Detect offline→online transitions for notification badges
  if (!TwitchX._prevLiveSet) TwitchX._prevLiveSet = new Set();
  var newLive = new Set(Array.from(TwitchX.state.liveSet));
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
    for (const fav of TwitchX.getFavoriteEntries()) {
      if (!TwitchX.state.avatars[fav.key]) {
        if (TwitchX.api) TwitchX.api.get_avatar(fav.login, fav.platform);
      }
    }
  } else {
    // When player is active, only fetch avatars for currently visible sidebar items
    // via requestIdleCallback to avoid main-thread contention with video compositing
    if (typeof requestIdleCallback === 'function') {
      requestIdleCallback(function() {
        for (const fav of TwitchX.getFavoriteEntries()) {
          if (!TwitchX.state.avatars[fav.key]) {
            if (TwitchX.api) TwitchX.api.get_avatar(fav.login, fav.platform);
          }
        }
      }, { timeout: 2000 });
    }
  }

  // Request thumbnails for live streams
  if (!playerActive) {
    for (const s of TwitchX.state.streams) {
      const streamKey = TwitchX.channelKey(s.login, s.platform || 'twitch');
      if (!TwitchX.state.thumbnails[streamKey] && s.thumbnail_url) {
        TwitchX.api.get_thumbnail(streamKey, s.thumbnail_url);
      }
    }
  }

  // Prune stale caches — keep only entries for current favorites or live streams.
  const keepLogins = new Set(
    TwitchX.getFavoriteEntries().map(function(f) { return f.key; }).concat(
      TwitchX.state.streams.map(function(s) { return TwitchX.channelKey(s.login, s.platform || 'twitch'); })
    )
  );
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
  const searchInput = document.getElementById('search-input');
  while (dd.firstChild) dd.removeChild(dd.firstChild);
  if (!results || results.length === 0) {
    dd.classList.remove('visible');
    if (searchInput) searchInput.setAttribute('aria-expanded', 'false');
    while (dd.firstChild) dd.removeChild(dd.firstChild);
    return;
  }
  // Build search results using safe DOM methods
  while (dd.firstChild) dd.removeChild(dd.firstChild);
  results.forEach(function(r) {
    const row = document.createElement('div');
    row.className = 'search-result';
    row.dataset.login = r.login;
    row.tabIndex = 0;
    row.setAttribute('role', 'option');
    row.setAttribute('aria-label', 'Add ' + (r.display_name || r.login) + ' on ' + TwitchX.platformLabel(r.platform || 'twitch'));

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
      if (searchInput) searchInput.setAttribute('aria-expanded', 'false');
      TwitchX.state.searchResults = [];
      document.getElementById('search-input').value = '';
    });
    row.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        row.click();
      }
    });
    dd.appendChild(row);
  });
  dd.classList.add('visible');
  if (searchInput) searchInput.setAttribute('aria-expanded', 'true');
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
    TwitchX.state.watchingChannelKey = TwitchX.channelKey(data.channel, data.platform || TwitchX.state.selectedPlatform || TwitchX.state.playerPlatform || 'twitch');
    TwitchX.setStatus(data.message, 'success');
    document.getElementById('live-dot').classList.add('visible');
    TwitchX.renderGrid();
  } else {
    TwitchX.showToast(data.message, 'error');
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
  TwitchX.state.watchingChannel = data.channel || TwitchX.state.watchingChannel;
  TwitchX.state.watchingChannelKey = TwitchX.channelKey(
    TwitchX.state.watchingChannel,
    TwitchX.state.playerPlatform
  );
  TwitchX.state.playerHasChat = data.has_chat !== false;
  TwitchX.state.streamType = data.stream_type || 'live';
  document.getElementById('player-channel-name').textContent = data.channel || '';
  document.getElementById('player-stream-title').textContent = data.title || '';
  if (TwitchX.state.playerHasChat) {
    TwitchX.chatAuthenticated = false;
    TwitchX.chatPlatform = TwitchX.state.playerPlatform;
    TwitchX.setChatNotice('Connecting to chat...', 'connecting');
    TwitchX.updateChatInput();
  } else {
    TwitchX.chatAuthenticated = false;
    TwitchX.setChatNotice('Chat is not available for this media', 'unavailable');
    TwitchX.updateChatInput();
  }

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
  TwitchX.state.watchingChannelKey = null;
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
    if (TwitchX._setMultiSlotState) TwitchX._setMultiSlotState(idx, 'error', 'Error');
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
  if (TwitchX._setMultiSlotState) TwitchX._setMultiSlotState(idx, 'playing', 'Playing');

  active.querySelector('.ms-channel-name').textContent = data.channel || '';
  var badge = active.querySelector('.ms-platform-badge');
  badge.className = 'ms-platform-badge ' + (data.platform || 'twitch');
  badge.textContent = TwitchX.platformLabel(data.platform || 'twitch');
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
    let addedCount = 0;

    msgs.forEach(function(msg) {
      if (_shouldFilter(msg)) return;
      if (TwitchX._appendChatLog) TwitchX._appendChatLog(msg);

      if (msg.msg_id) {
        const msgId = String(msg.msg_id);
        const existing = Array.prototype.some.call(container.children, function(child) {
          return child.classList && child.classList.contains('chat-msg') && child.dataset.msgId === msgId;
        });
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
      tsEl.classList.toggle('hidden', !TwitchX.chatTimestamps);
      el.appendChild(tsEl);

      for (let i = 0; i < msg.badges.length; i++) {
        const badge = msg.badges[i];
        if (badge.icon_url) {
          const img = document.createElement('img');
          img.className = 'badge';
          img.src = badge.icon_url;
          img.alt = badge.name;
          img.title = badge.name;
          img.width = 16;
          img.height = 16;
          img.decoding = 'async';
          img.loading = 'lazy';
          img.onerror = function() {
            var fallback = document.createElement('span');
            fallback.className = 'badge-fallback';
            fallback.textContent = badge.name ? badge.name.charAt(0).toUpperCase() : '?';
            fallback.title = badge.name || 'Badge';
            this.replaceWith(fallback);
          };
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
        TwitchX.setIconOnly(replyBtn, 'reply', 14);
        replyBtn.addEventListener('click', function(e) {
          e.stopPropagation();
          TwitchX.setChatReply(msg.msg_id, msg.author_display, msg.text);
        });
        el.appendChild(replyBtn);
      }

      fragment.appendChild(el);
      addedCount++;
    });

    if (addedCount === 0) return;
    const wasAtBottom = (container.scrollHeight - container.scrollTop - container.clientHeight) < 60;
    if (wasAtBottom) TwitchX._setChatAutoScroll(true);
    container.querySelectorAll('.chat-empty-state').forEach(function(el) {
      el.remove();
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
  if (TwitchX.multiState.open) {
    const msInput = document.getElementById('ms-chat-input');
    const msBtn = document.getElementById('ms-chat-send-btn');
    const disabled = !TwitchX.chatAuthenticated;
    if (msInput) msInput.disabled = disabled;
    if (msBtn) msBtn.disabled = disabled;
  } else if (TwitchX.updateChatInput) {
    TwitchX.updateChatInput();
  }
  if (result.ok) {
    TwitchX.setStatus('Chat message sent', 'success');
    return;
  }

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
  var statusKey = TwitchX.channelKey(status.channel_id, status.platform || TwitchX.state.playerPlatform || 'twitch');
  if (TwitchX.multiState.open) {
    var activeSlot = TwitchX.multiState.slots[TwitchX.multiState.chatSlot];
    var activeMsKey = activeSlot ? TwitchX.channelKey(activeSlot.channel, activeSlot.platform) : '';
    if (statusKey && activeMsKey && statusKey !== activeMsKey) return;
  } else if (TwitchX.state.watchingChannelKey && statusKey && statusKey !== TwitchX.state.watchingChannelKey) {
    return;
  }
  TwitchX.chatAuthenticated = !!(status.authenticated);
  TwitchX.chatPlatform = status.platform || TwitchX.state.playerPlatform || 'twitch';
  if (status.self_login) TwitchX.chatSelfLogin = status.self_login;
  if (TwitchX.multiState.open) {
    const dot = document.getElementById('ms-chat-status-dot');
    const target = 'multi';
    if (dot) {
      dot.className = status.connected ? 'connected' : (status.connecting ? 'connecting' : (status.error ? 'error' : ''));
      dot.title = status.connected ? 'Connected' : (status.error || (status.connecting ? 'Connecting' : 'Disconnected'));
    }
    const inp = document.getElementById('ms-chat-input');
    const btn = document.getElementById('ms-chat-send-btn');
    if (inp) inp.disabled = !(status.connected && status.authenticated);
    if (btn) btn.disabled = !(status.connected && status.authenticated);
    if (status.connected) {
      TwitchX.setChatNotice('No messages yet', 'empty', target);
      const newBtn = document.getElementById('ms-chat-new-messages');
      if (newBtn) newBtn.classList.remove('visible');
    } else if (status.connecting) {
      TwitchX.setChatNotice('Connecting to chat...', 'connecting', target);
    } else if (status.error) {
      TwitchX.setChatNotice(status.error, 'error', target);
    } else {
      TwitchX.setChatNotice('Chat disconnected', 'disconnected', target);
    }
    return;
  }
  const dot = document.getElementById('chat-status-dot');
  var statusText = document.getElementById('chat-status-text');
  if (dot) {
    if (status.connected) {
      dot.classList.remove('connecting');
      dot.classList.remove('error');
      dot.classList.add('connected');
      dot.title = status.authenticated ? 'Connected' : 'Connected (read-only)';
      if (statusText) statusText.textContent = status.authenticated ? 'Connected' : 'Read-only';
      if (TwitchX.clearChatBatch) TwitchX.clearChatBatch();
      TwitchX.clearChatMessages('No messages yet');
      TwitchX.chatAutoScroll = true;
      TwitchX.loadChatFiltersFromConfig();
      const newBtn = document.getElementById('chat-new-messages');
      if (newBtn) newBtn.classList.remove('visible');
      // Dismiss disconnect toast on reconnect
      if (TwitchX._chatDisconnectToast) {
        TwitchX.dismissToast(TwitchX._chatDisconnectToast);
        TwitchX._chatDisconnectToast = null;
      }
    } else if (status.connecting) {
      dot.classList.remove('connected');
      dot.classList.remove('error');
      dot.classList.add('connecting');
      dot.title = 'Connecting';
      if (statusText) statusText.textContent = 'Connecting...';
      TwitchX.setChatNotice('Connecting to chat...', 'connecting');
    } else {
      dot.classList.remove('connected');
      dot.title = status.error || 'Disconnected';
      if (statusText) statusText.textContent = status.error ? status.error : 'Disconnected';
      TwitchX.chatSelfLogin = '';
      TwitchX.clearChatReply();
      // Show yellow pulsing dot during reconnect backoff
      if (status.error && status.error.indexOf('Reconnect') !== -1) {
        dot.classList.add('connecting');
        dot.classList.remove('error');
        TwitchX.setChatNotice('Reconnecting to chat...', 'connecting');
      } else {
        dot.classList.remove('connecting');
        dot.classList.toggle('error', !!status.error);
        TwitchX.setChatNotice(status.error || 'Chat disconnected', status.error ? 'error' : 'disconnected');
      }
      if (status.error) {
        TwitchX._chatDisconnectToast = TwitchX.showToast(status.error, 'error');
      }
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
    TwitchX.setIconText(fb, 'check', 14, data.message);
    fb.style.color = 'var(--live-green)';
  } else {
    TwitchX.setIconText(fb, 'cross', 14, data.message);
    fb.style.color = 'var(--error-red)';
    TwitchX.showToast(data.message, 'error');
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
    TwitchX.setIconText(fb, 'check', 14, 'Kick login successful');
    fb.style.color = 'var(--live-green)';
    TwitchX.showToast('Logged in to Kick as ' + (data.display_name || data.login), 'success');
  }
  TwitchX.showKickProfile(data);
  TwitchX.updateChatInput();
};

window.onKickLoginError = function(msg) {
  const fb = document.getElementById('settings-feedback');
  TwitchX.setIconText(fb, 'cross', 14, 'Kick login failed: ' + msg);
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
    TwitchX.setIconText(fb, 'check', 14, data.message);
    fb.style.color = 'var(--live-green)';
  } else {
    TwitchX.setIconText(fb, 'cross', 14, data.message);
    fb.style.color = 'var(--error-red)';
    TwitchX.showToast(data.message, 'error');
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
  TwitchX.setIconText(fb, 'check', 14, 'YouTube login successful');
  fb.style.color = 'var(--live-green)';
  TwitchX.showToast('Logged in to YouTube as ' + (data.display_name || data.login), 'success');
};

window.onYouTubeLoginError = function(msg) {
  const fb = document.getElementById('settings-feedback');
  TwitchX.setIconText(fb, 'cross', 14, 'YouTube login failed: ' + msg);
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
  if (tr) {
    tr.classList.remove('hidden');
    if (result.success) {
      TwitchX.setIconText(tr, 'check', 14, result.message);
      tr.style.color = 'var(--live-green)';
    } else {
      TwitchX.setIconText(tr, 'cross', 14, result.message);
      tr.style.color = 'var(--error-red)';
      TwitchX.showToast(result.message, 'error');
    }
  }
  const btn = document.getElementById('yt-test-btn');
  if (btn) btn.disabled = false;
};

window.onYouTubeImportComplete = function(data) {
  const count = data && typeof data === 'object' ? data.added : data;
  const tr = document.getElementById('yt-test-result');
  if (tr) {
    tr.classList.remove('hidden');
    TwitchX.setIconText(tr, 'check', 14, 'Imported ' + count + ' subscriptions');
    tr.style.color = 'var(--live-green)';
  }
  TwitchX.showToast('Imported ' + count + ' channel(s)', 'success');
};

window.onYouTubeImportError = function(msg) {
  const tr = document.getElementById('yt-test-result');
  if (tr) {
    tr.classList.remove('hidden');
    TwitchX.setIconText(tr, 'cross', 14, 'Import failed: ' + msg);
    tr.style.color = 'var(--error-red)';
  }
  TwitchX.showToast('Import error: ' + msg, 'error');
};

window.onAvatar = function(data) {
  const key = TwitchX.channelKey(data.login, data.platform || 'twitch');
  TwitchX.state.avatars[key] = data.data;
  // Update expanded sidebar avatars
  document.querySelectorAll('.channel-item[data-key="' + key + '"] .avatar').forEach(function(img) {
    img.src = data.data;
  });
  // Update collapsed rail avatars
  document.querySelectorAll('.rail-avatar[data-key="' + key + '"] .rail-av-img').forEach(function(img) {
    img.src = data.data;
  });
  // Update user profile avatar
  const userAvatar = document.getElementById('user-avatar');
  if (userAvatar && (userAvatar.dataset.key === key || userAvatar.dataset.login === data.login)) {
    userAvatar.src = data.data;
  }
};

window.onThumbnail = function(data) {
  TwitchX.state.thumbnails[data.login] = data.data;
  const img = document.querySelector('.stream-card[data-key="' + data.login + '"] .thumb-img');
  if (img) {
    img.src = data.data;
    img.classList.add('loaded');
  }
};

window.onStatusUpdate = function(data) {
  TwitchX.setStatus(data.text, data.type || 'info');
  if (data.stale) {
    document.getElementById('updated-time').classList.add('stale');
    document.getElementById('sidebar-stale-banner').classList.remove('hidden');
  } else {
    document.getElementById('updated-time').classList.remove('stale');
    document.getElementById('sidebar-stale-banner').classList.add('hidden');
  }
  if (data.type === 'error' && data.toast !== false) {
    TwitchX.showToast(data.text, 'error');
  }
};

window.onBrowseCategories = function(payload) {
  document.getElementById('browse-loading').classList.add('hidden');
  const grid = document.getElementById('browse-categories-grid');
  grid.replaceChildren();
  const categories = Array.isArray(payload) ? payload : (payload && payload.items) || [];
  const errors = Array.isArray(payload) ? {} : (payload && payload.errors) || {};
  const errorSummary = TwitchX.browseErrorSummary ? TwitchX.browseErrorSummary(errors) : '';
  if (!categories || !categories.length) {
    if (TwitchX.setBrowseEmpty) {
      TwitchX.setBrowseEmpty(
        'No categories found.',
        errorSummary || 'Try another platform filter or check API credentials in Settings.',
        errorSummary ? 'error' : 'empty'
      );
    }
    return;
  }
  if (TwitchX.clearBrowseEmpty) TwitchX.clearBrowseEmpty();
  categories.forEach(function(cat) {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'browse-category-card card-enter';
    card.setAttribute('aria-label', 'Browse ' + cat.name);
    card.addEventListener('animationend', function() { card.classList.remove('card-enter'); }, { once: true });
    card.onclick = function() { TwitchX._triggerBrowseTopStreams(cat); };

    const artWrap = document.createElement('div');
    artWrap.className = 'browse-category-art-wrap';
    if (cat.box_art_url) {
      const img = document.createElement('img');
      img.className = 'browse-category-art';
      img.alt = '';
      img.src = cat.box_art_url;
      img.loading = 'lazy';
      img.decoding = 'async';
      img.onerror = function() {
        img.remove();
        artWrap.appendChild(TwitchX.createImageFallback(cat.name, 'browse-category-fallback'));
      };
      artWrap.appendChild(img);
    } else {
      artWrap.appendChild(TwitchX.createImageFallback(cat.name, 'browse-category-fallback'));
    }

    const info = document.createElement('div');
    info.className = 'browse-category-info';

    const nameEl = document.createElement('span');
    nameEl.className = 'browse-category-name';
    nameEl.textContent = cat.name;

    const badges = document.createElement('div');
    badges.className = 'browse-category-platforms';
    (cat.platforms || []).forEach(function(p) {
      badges.appendChild(TwitchX.createPlatformBadge(p, TwitchX.platformLabel(p)));
    });

    info.appendChild(nameEl);
    info.appendChild(badges);
    card.appendChild(artWrap);
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
  const errorSummary = TwitchX.browseErrorSummary ? TwitchX.browseErrorSummary(payload.errors || {}) : '';
  if (!payload || !payload.streams || !payload.streams.length) {
    if (TwitchX.setBrowseEmpty) {
      TwitchX.setBrowseEmpty(
        'No live streams found for this category.',
        errorSummary || 'Some platforms may not expose this category or may be offline right now.',
        errorSummary ? 'error' : 'empty'
      );
    }
    return;
  }
  if (TwitchX.clearBrowseEmpty) TwitchX.clearBrowseEmpty();
  payload.streams.forEach(function(stream) {
    const card = document.createElement('div');
    const restriction = TwitchX.browseStreamRestriction
      ? TwitchX.browseStreamRestriction(stream)
      : { canWatch: stream.platform !== 'youtube', reason: '' };
    card.className = 'browse-stream-card card-enter platform-' + (stream.platform || 'twitch');
    card.dataset.platform = stream.platform || 'twitch';
    card.dataset.login = stream.channel_login || '';
    card.dataset.key = TwitchX.channelKey(stream.channel_login, stream.platform || 'twitch');
    card.tabIndex = 0;
    card.setAttribute('role', 'button');
    card.setAttribute('aria-label', 'View ' + (stream.display_name || stream.channel_login) + ' on ' + TwitchX.platformLabel(stream.platform || 'twitch'));
    card.addEventListener('animationend', function() { card.classList.remove('card-enter'); }, { once: true });
    card.addEventListener('click', function() {
      TwitchX.showChannelView(stream.channel_login, stream.platform, 'browse');
    });
    card.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        card.click();
      }
    });
    card.addEventListener('contextmenu', function(e) {
      if (TwitchX.showContextMenu) TwitchX.showContextMenu(e, stream.channel_login, stream.platform);
    });

    const thumbWrap = document.createElement('div');
    thumbWrap.className = 'browse-stream-thumb-wrap';
    if (stream.thumbnail_url) {
      const thumb = document.createElement('img');
      thumb.className = 'browse-stream-thumb';
      thumb.alt = '';
      thumb.src = stream.thumbnail_url;
      thumb.loading = 'lazy';
      thumb.decoding = 'async';
      thumb.onerror = function() {
        thumb.remove();
        thumbWrap.appendChild(TwitchX.createImageFallback(stream.display_name || stream.channel_login, 'browse-stream-thumb-fallback'));
      };
      thumbWrap.appendChild(thumb);
    } else {
      thumbWrap.appendChild(TwitchX.createImageFallback(stream.display_name || stream.channel_login, 'browse-stream-thumb-fallback'));
    }
    const liveBadge = document.createElement('span');
    liveBadge.className = 'browse-live-badge';
    liveBadge.textContent = stream.platform === 'youtube' ? 'LIVE SEARCH' : 'LIVE';
    thumbWrap.appendChild(liveBadge);
    thumbWrap.appendChild(TwitchX.createPlatformBadge(stream.platform || 'twitch', TwitchX.platformLabel(stream.platform || 'twitch')));

    const info = document.createElement('div');
    info.className = 'browse-stream-info';

    const nameEl = document.createElement('span');
    nameEl.className = 'browse-stream-name';
    nameEl.textContent = stream.display_name || stream.channel_login || 'Unknown channel';

    const titleEl = document.createElement('span');
    titleEl.className = 'browse-stream-title';
    titleEl.textContent = stream.title || 'Untitled stream';

    const categoryEl = document.createElement('span');
    categoryEl.className = 'browse-stream-category';
    categoryEl.textContent = stream.category || payload.category || '';

    const viewersEl = document.createElement('span');
    viewersEl.className = 'browse-stream-viewers';
    viewersEl.textContent = stream.viewers
      ? TwitchX.formatViewers(stream.viewers) + ' viewers'
      : (stream.platform === 'youtube' ? 'Viewer count unavailable' : '');

    info.appendChild(nameEl);
    info.appendChild(titleEl);
    if (categoryEl.textContent) info.appendChild(categoryEl);
    if (viewersEl.textContent) info.appendChild(viewersEl);
    card.appendChild(thumbWrap);
    card.appendChild(info);

    const actions = document.createElement('div');
    actions.className = 'browse-stream-actions';

    const watchBtn = document.createElement('button');
    watchBtn.className = 'browse-stream-action primary';
    watchBtn.type = 'button';
    watchBtn.textContent = 'Watch';
    if (!restriction.canWatch) {
      watchBtn.classList.add('disabled');
      watchBtn.setAttribute('aria-disabled', 'true');
      watchBtn.title = restriction.reason;
      watchBtn.setAttribute('aria-label', 'Watch unavailable: ' + restriction.reason);
    } else {
      watchBtn.setAttribute('aria-disabled', 'false');
    }
    watchBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      if (!restriction.canWatch) {
        TwitchX.setStatus(restriction.reason, 'warn');
        TwitchX.showToast(restriction.reason, 'warn');
        return;
      }
      TwitchX.hideBrowseView();
      const quality = document.getElementById('quality-select')
        ? document.getElementById('quality-select').value
        : 'best';
      if (TwitchX.api) TwitchX.api.watch_direct(stream.channel_login, stream.platform, quality);
    });
    actions.appendChild(watchBtn);

    const profileBtn = document.createElement('button');
    profileBtn.className = 'browse-stream-action secondary';
    profileBtn.type = 'button';
    profileBtn.textContent = 'Channel';
    profileBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      TwitchX.showChannelView(stream.channel_login, stream.platform, 'browse');
    });
    actions.appendChild(profileBtn);

    const favKey = TwitchX.channelKey(stream.channel_login, stream.platform || 'twitch');
    const favBtn = document.createElement('button');
    favBtn.className = 'browse-stream-action icon';
    favBtn.type = 'button';
    favBtn.title = TwitchX.state.favoritesMeta[favKey] ? 'Remove from favorites' : 'Add to favorites';
    favBtn.setAttribute('aria-label', favBtn.title);
    favBtn.classList.toggle('active', !!TwitchX.state.favoritesMeta[favKey]);
    TwitchX.setIconOnly(favBtn, 'star', 14);
    favBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      if (!TwitchX.api) return;
      if (TwitchX.state.favoritesMeta[favKey]) {
        TwitchX.api.remove_channel(stream.channel_login, stream.platform);
        TwitchX.setStatus('Removed ' + (stream.display_name || stream.channel_login) + ' from favorites', 'info');
      } else {
        TwitchX.api.add_channel(stream.channel_login, stream.platform, stream.display_name || '');
        TwitchX.setStatus('Added ' + (stream.display_name || stream.channel_login) + ' to favorites', 'success');
      };
    });
    actions.appendChild(favBtn);

    card.appendChild(actions);

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
  const platformBadge = document.getElementById('channel-platform-badge');
  if (platformBadge) {
    platformBadge.className = 'platform-badge ' + (profile.platform || 'twitch');
    platformBadge.textContent = TwitchX.platformLabel(profile.platform || 'twitch');
    platformBadge.classList.remove('hidden');
  }

  const followersEl = document.getElementById('channel-followers');
  followersEl.textContent = profile.followers >= 0
    ? TwitchX.formatViewers(profile.followers) + ' followers'
    : '';

  const platformNote = document.getElementById('channel-platform-note');
  if (platformNote) {
    platformNote.textContent = profile.platform_note || '';
    platformNote.classList.toggle('hidden', !profile.platform_note);
  }

  var bioEl = document.getElementById('channel-bio');
  bioEl.textContent = profile.bio || '';
  bioEl.classList.toggle('hidden', !profile.bio);

  const avatarEl = document.getElementById('channel-avatar');
  const avatarFallback = document.getElementById('channel-avatar-fallback');
  if (avatarFallback) {
    avatarFallback.textContent = (profile.display_name || profile.login || '?').charAt(0).toUpperCase();
    avatarFallback.classList.remove('hidden');
  }
  if (profile.avatar_url) {
    avatarEl.src = profile.avatar_url;
    avatarEl.alt = (profile.display_name || profile.login) + ' avatar';
    avatarEl.classList.remove('hidden');
    avatarEl.onerror = function() {
      avatarEl.classList.add('hidden');
      if (avatarFallback) avatarFallback.classList.remove('hidden');
    };
    avatarEl.onload = function() {
      if (avatarFallback) avatarFallback.classList.add('hidden');
    };
  } else {
    avatarEl.classList.add('hidden');
  }

  document.getElementById('channel-live-badge').classList.toggle('hidden', !profile.is_live);
  const liveEmpty = document.getElementById('channel-live-empty');
  if (profile.is_live) {
    liveEmpty.textContent = profile.platform === 'youtube'
      ? 'This YouTube channel appears live, but direct playback from channel profiles is limited. Use Browser or available media items.'
      : 'Channel is live. Use Watch Now to start playback.';
  } else {
    liveEmpty.textContent = profile.platform === 'youtube'
      ? 'No live YouTube stream is known right now. YouTube live discovery depends on API quota and login.'
      : 'Channel is not live right now.';
  }
  liveEmpty.classList.toggle('hidden', !!profile.is_live && profile.watch_supported);

  const followBtn = document.getElementById('channel-follow-btn');
  followBtn.textContent = profile.is_favorited ? 'Following' : 'Follow';
  followBtn.classList.toggle('following', !!profile.is_favorited);

  const watchBtn = document.getElementById('channel-watch-btn');
  const actionNote = document.getElementById('channel-action-note');
  watchBtn.classList.remove('hidden');
  watchBtn.disabled = !profile.watch_supported;
  watchBtn.title = profile.watch_supported ? 'Watch this live stream' : (profile.watch_disabled_reason || 'Unavailable');
  watchBtn.setAttribute('aria-disabled', String(!profile.watch_supported));
  if (actionNote) {
    actionNote.textContent = profile.watch_supported ? '' : (profile.watch_disabled_reason || '');
    actionNote.classList.toggle('hidden', profile.watch_supported || !actionNote.textContent);
  }

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
