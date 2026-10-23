window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

// Key ("platform:login") of the channel whose chat is on screen, or '' if none.
TwitchX._activeChatKey = function() {
  if (TwitchX.multiState.open) {
    var activeSlot = TwitchX.multiState.slots[TwitchX.multiState.chatSlot];
    return activeSlot ? TwitchX.channelKey(activeSlot.channel, activeSlot.platform) : '';
  }
  return TwitchX.state.watchingChannelKey || '';
};

// Chat callbacks from Python carry their source channel; events of a channel
// we already switched away from must not leak into the current chat.
TwitchX._isActiveChatKey = function(channelId, platform) {
  var key = TwitchX.channelKey(channelId, platform || TwitchX.state.playerPlatform || 'twitch');
  var active = TwitchX._activeChatKey();
  return !key || !active || key === active;
};

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

  // Notification badges: accumulate offline→online transitions until the user
  // acknowledges them (click on a channel, or on the badge itself). The first
  // update only seeds the baseline — everything live at startup is not "new".
  var newLive = new Set(Array.from(TwitchX.state.liveSet));
  if (!TwitchX._prevLiveSet) {
    TwitchX._notifBadgeLogins = [];
  } else {
    var pending = (TwitchX._notifBadgeLogins || []).filter(function(key) {
      return newLive.has(key);
    });
    newLive.forEach(function(key) {
      if (!TwitchX._prevLiveSet.has(key) && pending.indexOf(key) === -1) {
        pending.push(key);
      }
    });
    TwitchX._notifBadgeLogins = pending;
  }
  TwitchX._prevLiveSet = newLive;

  TwitchX.renderGrid();
  TwitchX.renderSidebar();

  // Section header meta: "9 live · 495K watching · updated 15:42"
  if (data.updated_time) {
    // HH:MM is enough at a glance; Python sends HH:MM:SS.
    var shortTime = String(data.updated_time).replace(/^(\d{1,2}:\d{2}):\d{2}$/, '$1');
    document.getElementById('updated-time').textContent = 'updated ' + shortTime;
    document.getElementById('updated-time').classList.remove('stale');
  }
  if (data.total_viewers > 0) {
    document.getElementById('total-viewers').textContent =
      (data.total_viewers_formatted || data.total_viewers) + ' watching';
  } else {
    document.getElementById('total-viewers').textContent = '';
  }
  document.getElementById('section-live-count').textContent = TwitchX.state.liveSet.size + ' live';

  // Throttle background image fetching when player is active
  const playerActive = document.getElementById('player-view').classList.contains('view-active');

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
      if (s.thumbnail_url && TwitchX.thumbnailNeedsFetch(streamKey)) {
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
  for (const key in TwitchX.state.thumbnailFetchedAt) {
    if (!keepLogins.has(key)) delete TwitchX.state.thumbnailFetchedAt[key];
  }
  for (const key in TwitchX.state.prevViewers) {
    if (!keepLogins.has(key)) delete TwitchX.state.prevViewers[key];
  }
};

// Channel search runs from the command palette only.
window.onSearchResults = function(results, meta) {
  if (TwitchX.receivePaletteSearch) TwitchX.receivePaletteSearch(results, meta);
};

window.onLoginComplete = function(user) {
  TwitchX.showUserProfile(user);
  TwitchX.showToast('Logged in as ' + user.display_name, 'success');
};

window.onLoginError = function(msg) {
  TwitchX.showToast('Login error: ' + msg, 'error');
};

window.onLogout = function(reason) {
  TwitchX.hideUserProfile();
  if (reason) {
    TwitchX.showToast(reason, 'warn');
  } else {
    TwitchX.showToast('Logged out', 'info');
  }
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
    // An in-app launch already set the watched channel in onStreamReady. Only
    // an external-player launch, with no stream in the player, may set it here:
    // overwriting the in-app key would cut the player's chat off.
    if (!TwitchX.state.playerPlatform) {
      TwitchX.state.watchingChannel = data.channel;
      TwitchX.state.watchingChannelKey = TwitchX.channelKey(data.channel, data.platform || TwitchX.state.selectedPlatform || 'twitch');
    }
    TwitchX.setStatus(data.message, 'success');
    document.getElementById('live-dot').classList.add('visible');
    TwitchX.renderGrid();
  } else {
    TwitchX.showToast(data.message, 'error');
  }
};

window.onLaunchProgress = function(data) {
  TwitchX.setStatus('Launching ' + data.channel + '... (' + data.elapsed + 's)', 'info');
  var loader = document.getElementById('stream-loader');
  if (loader) loader.classList.remove('hidden');
};

window.onStreamReady = function(data) {
  // Clear stale chat messages from the previous stream before switching
  TwitchX.clearChatMessages();
  if (TwitchX.clearChatBatch) TwitchX.clearChatBatch();
  // Third-party emotes belong to the previous channel; the new set arrives
  // via onThirdPartyEmotes once start_chat fetched it.
  TwitchX.thirdPartyEmotes = {};
  TwitchX._cachedPickerEmotes = null;
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
  const pcName = document.getElementById('player-channel-name');
  if (pcName) pcName.textContent = data.channel || '';
  const pcTitle = document.getElementById('player-stream-title');
  if (pcTitle) pcTitle.textContent = data.title || '';
  const pcAvatar = document.getElementById('player-header-avatar');
  if (pcAvatar) {
    const avatarUrl = TwitchX.state.avatars[TwitchX.state.watchingChannelKey];
    if (avatarUrl) pcAvatar.src = avatarUrl;
    pcAvatar.classList.toggle('hidden', !avatarUrl);
  }
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
  // A fresh stream starts from a clean recovery slate — otherwise the backoff of
  // the previous channel carries over into the new one.
  if (TwitchX.cancelStreamRecovery) TwitchX.cancelStreamRecovery();
  if (TwitchX.hidePlayerError) TwitchX.hidePlayerError();
  TwitchX._lastResetAt = 0;
  const video = TwitchX.getPlayerVideo();
  if (!video) return;
  video.src = data.url;
  video.play().catch(function(e) {
    console.warn('[Player] video.play() rejected:', e && e.message || e);
    TwitchX.setStatus('Playback blocked — click to resume', 'warn');
  });
  const extBtn = document.getElementById('watch-external-btn');
  if (extBtn) extBtn.disabled = false;
  var modBtn = document.getElementById('chat-mod-btn');
  if (modBtn) {
    var isTwitch = data.platform === 'twitch';
    var isBroadcaster = isTwitch && TwitchX.chatSelfLogin &&
      TwitchX.chatSelfLogin.toLowerCase() === (data.channel || '').toLowerCase();
    modBtn.classList.toggle('hidden', !isBroadcaster);
  }

  TwitchX.showPlayerView();
};

window.onStreamUrlRefreshed = function(data) {
  TwitchX._onStreamUrlRefreshed(data);
};

window.onMultiSlotUrlRefreshed = function(data) {
  TwitchX._onMultiSlotUrlRefreshed(data);
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
    if (TwitchX.multiState.slots[idx] && TwitchX.multiState.slots[idx]._loadTimer) {
      clearTimeout(TwitchX.multiState.slots[idx]._loadTimer);
      TwitchX.multiState.slots[idx]._loadTimer = null;
    }
    return;
  }

  if (TwitchX.multiState.slots[idx] && TwitchX.multiState.slots[idx]._loadTimer) {
    clearTimeout(TwitchX.multiState.slots[idx]._loadTimer);
    TwitchX.multiState.slots[idx]._loadTimer = null;
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
  badge.className = 'ms-platform-badge platform-dot ' + (data.platform || 'twitch');
  badge.title = TwitchX.platformLabel(data.platform || 'twitch');
  if (data.title) TwitchX.multiState.slots[idx].title = data.title;

  if (TwitchX.multiState.audioFocus === -1) TwitchX.setAudioFocus(idx);
  if (TwitchX.multiState.chatSlot === -1) TwitchX.switchMultiChat(idx);
};

/* ── Chat message batching ──────────────────────────────── */
(function() {
  let chatBatch = [];
  let chatBatchTimer = null;
  const BATCH_MS = 50;
  // Cap DOM nodes to keep scroll performance smooth on modest hardware.
  // 150 rendered messages is well below the threshold where virtualization
  // becomes necessary; pruning keeps memory and layout cost bounded.
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

      const badges = msg.badges || [];
      for (let i = 0; i < badges.length; i++) {
        const badge = badges[i];
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
        if (msg.author_color) nick.style.setProperty('--author-color', msg.author_color);
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
        replyBtn.type = 'button';
        replyBtn.title = 'Reply';
        replyBtn.setAttribute('aria-label', 'Reply to ' + msg.author_display);
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
      var oldHeight = container.scrollHeight;
      container.removeChild(container.firstChild);
      var newHeight = container.scrollHeight;
      if (!TwitchX._getChatAutoScroll()) {
        container.scrollTop -= (oldHeight - newHeight);
      }
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
    if (!msg || !TwitchX._isActiveChatKey(msg.channel_id, msg.platform)) return;
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
  if (!status || !TwitchX._isActiveChatKey(status.channel_id, status.platform)) return;
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
  if (!data || !data.emotes || !data.channel) return;
  // Strict: emotes of a channel that is no longer on screen are dropped.
  var active = TwitchX._activeChatKey();
  if (!active || active !== TwitchX.channelKey(data.channel, 'twitch')) return;
  Object.assign(TwitchX.thirdPartyEmotes, data.emotes);
  TwitchX._cachedPickerEmotes = null;
  if (TwitchX._emotePickerOpen) {
    var searchEl = document.getElementById('emote-search');
    TwitchX.renderEmotePicker(searchEl ? searchEl.value : '');
  }
};

window.onChatUserList = function(data) {
  if (!data || !TwitchX._isActiveChatKey(data.channel_id, data.platform)) return;
  TwitchX._chatUserList = data.users || [];
  var countEl = document.getElementById('chat-userlist-count');
  if (countEl) countEl.textContent = data.count || TwitchX._chatUserList.length;
  var panel = document.getElementById('chat-userlist-panel');
  if (panel && !panel.classList.contains('hidden')) {
    TwitchX.renderChatUserList('');
  }
};

// Twitch rejected a message we sent (slow mode, followers-only, duplicate, ...).
window.onChatNotice = function(data) {
  if (!data || !TwitchX._isActiveChatKey(data.channel_id, data.platform)) return;
  var text = data.text || 'Message was not sent';
  window.onChatMessage({
    channel_id: data.channel_id,
    platform: data.platform,
    author: '',
    author_display: '',
    author_color: null,
    text: text,
    timestamp: '',
    badges: [],
    emotes: [],
    is_system: true,
    message_type: 'notice',
    msg_id: null,
    is_self: false
  });
  TwitchX.showToast(text, 'error');
  if (data.failed_text) {
    var input = document.getElementById(TwitchX.multiState.open ? 'ms-chat-input' : 'chat-input');
    if (input && !input.value) input.value = data.failed_text;
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
    TwitchX.setFeedbackClass(fb, 'success');
  } else {
    TwitchX.setIconText(fb, 'cross', 14, data.message);
    TwitchX.setFeedbackClass(fb, 'error');
    TwitchX.showToast(data.message, 'error');
  }
  document.getElementById('test-btn').disabled = false;
};

window.onConfigLoaded = function(config) {
  TwitchX.applyConfigSnapshot(config);
};

window.onWatchStatistics = function(payload) {
  var loading = document.getElementById('stats-loading');
  if (payload && payload.ok) {
    TwitchX.renderWatchStats(payload.stats);
    return;
  }
  if (loading) {
    loading.classList.remove('hidden');
    loading.textContent = 'Failed to load statistics';
  }
  var content = document.getElementById('stats-content');
  if (content) content.classList.add('hidden');
};

window.onChatLogSaved = function(result) {
  if (result && result.ok) {
    TwitchX.setStatus('Chat log saved: ' + result.name, 'success');
    TwitchX.showToast('Chat log saved to ' + result.path, 'success');
    return;
  }
  var reason = (result && result.error) || 'unknown error';
  TwitchX.setStatus('Chat export failed: ' + reason, 'error');
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
    TwitchX.setFeedbackClass(fb, 'warn');
    TwitchX.showToast('Kick login is missing chat:write, so chat stays read-only', 'warn');
  } else {
    TwitchX.setIconText(fb, 'check', 14, 'Kick login successful');
    TwitchX.setFeedbackClass(fb, 'success');
    TwitchX.showToast('Logged in to Kick as ' + (data.display_name || data.login), 'success');
  }
  TwitchX.showKickProfile(data);
  TwitchX.updateChatInput();
};

window.onKickLoginError = function(msg) {
  const fb = document.getElementById('settings-feedback');
  TwitchX.setIconText(fb, 'cross', 14, 'Kick login failed: ' + msg);
  TwitchX.setFeedbackClass(fb, 'error');
  TwitchX.showToast('Kick login: ' + msg, 'error');
};

window.onKickLogout = function(reason) {
  TwitchX.state.kickUser = null;
  TwitchX.state.kickScopes = '';
  document.getElementById('kick-login-area').classList.remove('hidden');
  document.getElementById('kick-user-area').classList.add('hidden');
  document.getElementById('kick-user-display').textContent = '';
  const fb = document.getElementById('settings-feedback');
  fb.textContent = reason || 'Logged out from Kick';
  TwitchX.setFeedbackClass(fb, 'muted');
  TwitchX.hideKickProfile();
  TwitchX.updateChatInput();
  if (reason) TwitchX.showToast(reason, 'warn');
};

window.onKickTestResult = function(data) {
  const fb = document.getElementById('settings-feedback');
  if (data.success) {
    TwitchX.setIconText(fb, 'check', 14, data.message);
    TwitchX.setFeedbackClass(fb, 'success');
  } else {
    TwitchX.setIconText(fb, 'cross', 14, data.message);
    TwitchX.setFeedbackClass(fb, 'error');
    TwitchX.showToast(data.message, 'error');
  }
  document.getElementById('kick-test-btn').disabled = false;
};

window.onYouTubeLoginComplete = function(data) {
  TwitchX.state.youtubeUser = { login: data.login, display_name: data.display_name };
  if (TwitchX.updatePlatformStatusDots) TwitchX.updatePlatformStatusDots();
  document.getElementById('yt-login-area').classList.add('hidden');
  document.getElementById('yt-user-area').classList.remove('hidden');
  document.getElementById('yt-display-name').textContent = 'Logged in as ' + (data.display_name || data.login);
  document.getElementById('yt-quota-display').textContent = 'Quota remaining: ' + (data.youtube_quota_remaining != null ? data.youtube_quota_remaining : '?');
  const fb = document.getElementById('settings-feedback');
  TwitchX.setIconText(fb, 'check', 14, 'YouTube login successful');
  TwitchX.setFeedbackClass(fb, 'success');
  TwitchX.showToast('Logged in to YouTube as ' + (data.display_name || data.login), 'success');
};

window.onYouTubeLoginError = function(msg) {
  const fb = document.getElementById('settings-feedback');
  TwitchX.setIconText(fb, 'cross', 14, 'YouTube login failed: ' + msg);
  TwitchX.setFeedbackClass(fb, 'error');
  TwitchX.showToast('YouTube login: ' + msg, 'error');
};

window.onYouTubeLogout = function() {
  TwitchX.state.youtubeUser = null;
  if (TwitchX.updatePlatformStatusDots) TwitchX.updatePlatformStatusDots();
  document.getElementById('yt-login-area').classList.remove('hidden');
  document.getElementById('yt-user-area').classList.add('hidden');
  document.getElementById('yt-display-name').textContent = '';
  document.getElementById('yt-quota-display').textContent = '';
  const fb = document.getElementById('settings-feedback');
  fb.textContent = 'Logged out from YouTube';
  TwitchX.setFeedbackClass(fb, 'muted');
};

window.onYouTubeTestResult = function(result) {
  const tr = document.getElementById('yt-test-result');
  if (tr) {
    tr.classList.remove('hidden');
    if (result.success) {
      TwitchX.setIconText(tr, 'check', 14, result.message);
      TwitchX.setFeedbackClass(tr, 'success');
    } else {
      TwitchX.setIconText(tr, 'cross', 14, result.message);
      TwitchX.setFeedbackClass(tr, 'error');
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
    TwitchX.setFeedbackClass(tr, 'success');
  }
  TwitchX.showToast('Imported ' + count + ' channel(s)', 'success');
};

window.onYouTubeImportError = function(msg) {
  const tr = document.getElementById('yt-test-result');
  if (tr) {
    tr.classList.remove('hidden');
    TwitchX.setIconText(tr, 'cross', 14, 'Import failed: ' + msg);
    TwitchX.setFeedbackClass(tr, 'error');
  }
  TwitchX.showToast('Import error: ' + msg, 'error');
};

window.onAvatar = function(data) {
  const key = TwitchX.channelKey(data.login, data.platform || 'twitch');
  TwitchX.state.avatars[key] = data.data;
  function setAvatarSrc(img) {
    img.onerror = function() {
      img.onerror = null;
      img.classList.add('is-empty');
      img.removeAttribute('src');
    };
    img.src = data.data;
    img.classList.remove('is-empty');
  }
  // Update expanded sidebar avatars
  document.querySelectorAll('.channel-item[data-key="' + key + '"] .avatar').forEach(setAvatarSrc);
  // Update collapsed rail avatars
  document.querySelectorAll('.rail-avatar[data-key="' + key + '"] .rail-av-img').forEach(setAvatarSrc);
  document.querySelectorAll('.stream-card[data-key="' + key + '"] .card-avatar').forEach(setAvatarSrc);
  // Update user profile avatar (Twitch-only)
  const userAvatar = document.getElementById('user-avatar');
  if (userAvatar && data.platform === 'twitch' && userAvatar.dataset.key === key) {
    setAvatarSrc(userAvatar);
    if (TwitchX.updateAccountChip) TwitchX.updateAccountChip();
  }
};

window.onThumbnail = function(data) {
  // Backend returns the compound key in the `login` field for backwards compatibility.
  const streamKey = data.login;
  TwitchX.state.thumbnails[streamKey] = data.data;
  TwitchX.state.thumbnailFetchedAt[streamKey] = Date.now();
  const img = document.querySelector('.stream-card[data-key="' + streamKey + '"] .thumb-img');
  if (img) {
    // A previous load error may have hidden the image — restore it before retrying.
    img.classList.remove('hidden');
    img.src = data.data;
    img.classList.add('loaded');
  }
};

window.onStatusUpdate = function(data) {
  var type = data.type || 'info';
  // setStatus already toasts warnings and errors. The stale-data warning
  // arrives with every failed poll and has its own banner, so it stays quiet;
  // an explicit toast: false does too.
  var quiet = data.stale || data.toast === false;
  if (type === 'warn' || type === 'error') {
    if (!quiet) TwitchX.setStatus(data.text, type);
  } else {
    TwitchX.setStatus(data.text, type);
    if (data.toast === true) TwitchX.showToast(data.text, type);
  }
  if (data.stale) {
    document.getElementById('updated-time').classList.add('stale');
    document.getElementById('sidebar-stale-banner').classList.remove('hidden');
  } else {
    document.getElementById('updated-time').classList.remove('stale');
    document.getElementById('sidebar-stale-banner').classList.add('hidden');
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
    nameEl.title = cat.name;
    info.appendChild(nameEl);

    // "310K watching" + platform glyphs on one line.
    const metaRow = document.createElement('div');
    metaRow.className = 'browse-category-meta';
    if (typeof cat.viewers === 'number' && cat.viewers > 0) {
      const viewersEl = document.createElement('span');
      viewersEl.className = 'browse-category-viewers';
      viewersEl.textContent = TwitchX.formatViewers(cat.viewers) + ' watching';
      metaRow.appendChild(viewersEl);
    }
    const glyphs = document.createElement('span');
    glyphs.className = 'browse-category-platforms';
    (cat.platforms || []).forEach(function(p) {
      glyphs.appendChild(TwitchX.createPlatformGlyph(p, 12));
    });
    metaRow.appendChild(glyphs);
    info.appendChild(metaRow);

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
    const platform = stream.platform || 'twitch';
    const key = TwitchX.channelKey(stream.channel_login, platform);
    const name = stream.display_name || stream.channel_login || 'Unknown channel';
    const restriction = TwitchX.browseStreamRestriction
      ? TwitchX.browseStreamRestriction(stream)
      : { canWatch: platform !== 'youtube', reason: '' };
    // The same card as the Following grid (render.js buildMediaCard).
    const card = TwitchX.buildMediaCard({
      platform: platform,
      thumb: stream.thumbnail_url || null,
      fallbackLabel: name,
      avatar: TwitchX.state.avatars[key] || stream.avatar_url || null,
      title: stream.title || 'Untitled stream',
      channel: name,
      game: stream.category || payload.category || '',
      viewers: stream.viewers ? stream.viewers : null,
      corner: stream.started_at ? TwitchX.formatUptimeClock(stream.started_at) : '',
      watching: TwitchX.state.watchingChannelKey === key,
      label: (restriction.canWatch ? 'Watch ' : 'View ') + name + ' on ' + TwitchX.platformLabel(platform),
    });
    card.classList.add('browse-stream-card');
    card.dataset.platform = platform;
    card.dataset.login = stream.channel_login || '';
    card.dataset.key = key;
    // One click watches, like the Following grid. Streams that cannot play
    // here (YouTube search results) open the channel profile instead.
    function activate() {
      if (!restriction.canWatch) {
        TwitchX.showChannelView(stream.channel_login, platform, 'browse');
        return;
      }
      TwitchX.hideBrowseView();
      if (TwitchX.api) TwitchX.api.watch_direct(stream.channel_login, platform, TwitchX.state.quality);
    }
    if (!restriction.canWatch) card.title = restriction.reason;
    card.addEventListener('click', activate);
    card.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        activate();
      }
    });
    card.addEventListener('contextmenu', function(e) {
      if (TwitchX.showContextMenu) TwitchX.showContextMenu(e, stream.channel_login, platform);
    });
    grid.appendChild(card);
  });
};

window.onChannelProfile = function(profile) {
  if (!profile) return;
  const replyKey = TwitchX.channelKey(profile.requested_login || profile.login, profile.platform);
  if (replyKey !== TwitchX.state.pendingProfileKey) return;
  TwitchX.state.pendingProfileKey = '';
  if (TwitchX._channelProfileTimer) {
    clearTimeout(TwitchX._channelProfileTimer);
    TwitchX._channelProfileTimer = null;
  }
  document.getElementById('channel-loading').classList.add('hidden');

  if (profile.found === false) {
    document.getElementById('channel-bio').textContent = 'Channel not found.';
    document.getElementById('channel-profile-card').classList.remove('fade-transparent');
    return;
  }

  TwitchX.channelProfile = profile;

  document.getElementById('channel-header-title').textContent = profile.display_name || profile.login;
  document.getElementById('channel-display-name').textContent = profile.display_name || profile.login;
  document.getElementById('channel-login-text').textContent = '@' + profile.login;
  const platformBadge = document.getElementById('channel-platform-badge');
  if (platformBadge) {
    platformBadge.className = '';
    platformBadge.replaceChildren(TwitchX.createPlatformGlyph(profile.platform || 'twitch', 14));
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
      if (TwitchX.tintChannelBanner) TwitchX.tintChannelBanner(avatarEl);
    };
  } else {
    avatarEl.classList.add('hidden');
  }

  document.getElementById('channel-live-badge').classList.toggle('hidden', !profile.is_live);
  const liveEmpty = document.getElementById('channel-live-empty');
  var liveEmptyTitle = profile.is_live ? 'Channel is live' : 'Channel is offline';
  var liveEmptySubtitle;
  if (profile.is_live) {
    liveEmptySubtitle = profile.platform === 'youtube'
      ? 'This YouTube channel appears live, but direct playback from channel profiles is limited. Use Browser or available media items.'
      : 'Channel is live. Use Watch Now to start playback.';
  } else {
    liveEmptySubtitle = profile.platform === 'youtube'
      ? 'No live YouTube stream is known right now. YouTube live discovery depends on API quota and login.'
      : 'Channel is not live right now.';
  }
  TwitchX.renderEmptyState(liveEmpty, {
    illustration: 'empty-channel',
    title: liveEmptyTitle,
    subtitle: liveEmptySubtitle,
    secondaryAction: { label: 'Open Channel', callback: TwitchX.openChannelInBrowser },
  });
  TwitchX.renderChannelLivePanel(profile);

  const followBtn = document.getElementById('channel-follow-btn');
  followBtn.textContent = profile.is_favorited ? 'Following' : 'Follow';
  followBtn.classList.toggle('following', !!profile.is_favorited);

  const watchBtn = document.getElementById('channel-watch-btn');
  const actionNote = document.getElementById('channel-action-note');
  // Watch is the primary action, so it only exists while the channel is live.
  watchBtn.classList.toggle('hidden', !profile.is_live);
  watchBtn.disabled = !profile.watch_supported;
  watchBtn.title = profile.watch_supported ? 'Watch this live stream' : (profile.watch_disabled_reason || 'Unavailable');
  watchBtn.setAttribute('aria-disabled', String(!profile.watch_supported));
  if (actionNote) {
    actionNote.textContent = profile.watch_supported ? '' : (profile.watch_disabled_reason || '');
    actionNote.classList.toggle('hidden', profile.watch_supported || !actionNote.textContent);
  }

  document.getElementById('channel-profile-card').classList.remove('fade-transparent');
  TwitchX.ensureChannelTabLoaded(TwitchX.state.channelTabs.active);
};

window.onChannelMedia = function(payload) {
  if (!payload || !payload.tab || !TwitchX.state.channelTabs[payload.tab]) return;
  const channelView = document.getElementById('channel-view');
  if (!channelView || !channelView.classList.contains('view-active')) return;
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
