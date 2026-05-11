window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

function setChatReply(id, display, body) {
  TwitchX.chatReplyTo = { id: id, display: display, body: body };
  const bar = document.getElementById('chat-reply-bar');
  document.getElementById('chat-reply-nick').textContent = display;
  document.getElementById('chat-reply-body').textContent = body;
  bar.classList.add('active');
  const input = document.getElementById('chat-input');
  if (input && !input.disabled) input.focus();
}

function clearChatReply() {
  TwitchX.chatReplyTo = null;
  document.getElementById('chat-reply-bar').classList.remove('active');
}

function submitChatMessage() {
  const input = document.getElementById('chat-input');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;
  const r = TwitchX.chatReplyTo;
  const requestId = 'chat-send-' + Date.now() + '-' + (++TwitchX.chatSendCounter);
  TwitchX.chatPendingSends[requestId] = {
    text: text,
    reply: r ? { id: r.id, display: r.display, body: r.body } : null
  };
  setTimeout(function() {
    if (TwitchX.chatPendingSends[requestId]) {
      delete TwitchX.chatPendingSends[requestId];
    }
  }, 30000);
  if (TwitchX.api) TwitchX.api.send_chat(
    text,
    r ? r.id : null,
    r ? r.display : null,
    r ? r.body : null,
    requestId
  );
  input.value = '';
  clearChatReply();
  if (TwitchX.closeEmotePicker) TwitchX.closeEmotePicker();
}

function _getChatMessagesEl() {
  return document.getElementById(
    TwitchX.multiState.open ? 'ms-chat-messages' : 'chat-messages'
  );
}

function _getChatNewMsgEl() {
  return document.getElementById(
    TwitchX.multiState.open ? 'ms-chat-new-messages' : 'chat-new-messages'
  );
}

function _getChatAutoScroll() {
  return TwitchX.multiState.open ? TwitchX.msChatAutoScroll : TwitchX.chatAutoScroll;
}

function _setChatAutoScroll(val) {
  if (TwitchX.multiState.open) TwitchX.msChatAutoScroll = val;
  else TwitchX.chatAutoScroll = val;
}

function renderChatEmotes(parent, text, emotes) {
  var all = emotes ? emotes.slice() : [];

  var tp = TwitchX.thirdPartyEmotes;
  if (tp && Object.keys(tp).length > 0 && text) {
    var wordRe = /\S+/g;
    var m;
    while ((m = wordRe.exec(text)) !== null) {
      var raw = m[0];
      var code = raw;
      var url = tp[code];
      if (!url) {
        var stripped = raw.replace(/^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$/g, '');
        if (stripped && stripped !== raw) {
          url = tp[stripped];
          if (url) code = stripped;
        }
      }
      if (url) {
        var start = m.index, end = m.index + raw.length - 1;
        var overlaps = all.some(function(e) {
          return e.start <= end && e.end >= start;
        });
        if (!overlaps) {
          all.push({ code: code, url: url, start: start, end: end });
        }
      }
    }
  }

  if (all.length === 0) {
    parent.appendChild(document.createTextNode(text));
    return;
  }

  var sorted = all.slice().sort(function(a, b) { return a.start - b.start; });
  var lastIdx = 0;
  for (var i = 0; i < sorted.length; i++) {
    var emote = sorted[i];
    if (emote.start > lastIdx) {
      parent.appendChild(document.createTextNode(text.slice(lastIdx, emote.start)));
    }
    var img = document.createElement('img');
    img.className = 'emote';
    img.src = emote.url;
    img.alt = emote.code;
    img.title = emote.code;
    img.onerror = function() { this.style.display = 'none'; };
    parent.appendChild(img);
    lastIdx = emote.end + 1;
  }
  if (lastIdx < text.length) {
    parent.appendChild(document.createTextNode(text.slice(lastIdx)));
  }
}

function clearChatMessages() {
  const container = document.getElementById('chat-messages');
  if (container) {
    while (container.firstChild) {
      container.removeChild(container.firstChild);
    }
    var emptyEl = document.createElement('div');
    emptyEl.className = 'chat-empty-state';
    emptyEl.style.cssText = 'text-align:center;padding:20px;color:var(--text-muted);font-size:12px;';
    emptyEl.textContent = 'No messages yet';
    container.appendChild(emptyEl);
  }
  if (TwitchX.multiState.open) {
    const msContainer = document.getElementById('ms-chat-messages');
    if (msContainer) {
      while (msContainer.firstChild) {
        msContainer.removeChild(msContainer.firstChild);
      }
    }
  }
  clearChatReply();
  TwitchX.chatLog = [];
  TwitchX.chatSpamMap = {};
  if (TwitchX.clearChatBatch) TwitchX.clearChatBatch();
}

TwitchX.setChatReply = setChatReply;
TwitchX.clearChatReply = clearChatReply;
TwitchX.submitChatMessage = submitChatMessage;
TwitchX.renderChatEmotes = renderChatEmotes;
TwitchX.clearChatMessages = clearChatMessages;
TwitchX._getChatMessagesEl = _getChatMessagesEl;
TwitchX._getChatNewMsgEl = _getChatNewMsgEl;
TwitchX._getChatAutoScroll = _getChatAutoScroll;
TwitchX._setChatAutoScroll = _setChatAutoScroll;

/* ── Chat filter state ──────────────────────────────────── */

TwitchX.chatFilters = {
  subOnly: false,
  modOnly: false,
  antiSpam: true,
};

TwitchX.chatSelfLogin = '';
TwitchX.chatSpamMap = {};
TwitchX.chatBlockList = [];

function loadChatFiltersFromConfig() {
  var cfg = TwitchX.api ? TwitchX.api.get_full_config_for_settings() : null;
  if (!cfg) return;
  TwitchX.chatFilters.subOnly = !!cfg.chat_filter_sub_only;
  TwitchX.chatFilters.modOnly = !!cfg.chat_filter_mod_only;
  TwitchX.chatFilters.antiSpam = cfg.chat_anti_spam !== false;
  TwitchX.chatBlockList = (cfg.chat_block_list || []).map(function(w) {
    return String(w).toLowerCase();
  });
  var subEl = document.getElementById('chat-filter-sub');
  var modEl = document.getElementById('chat-filter-mod');
  var spamEl = document.getElementById('chat-filter-spam');
  if (subEl) subEl.checked = TwitchX.chatFilters.subOnly;
  if (modEl) modEl.checked = TwitchX.chatFilters.modOnly;
  if (spamEl) spamEl.checked = TwitchX.chatFilters.antiSpam;
}

function saveChatFilters() {
  var data = JSON.stringify({
    chat_filter_sub_only: TwitchX.chatFilters.subOnly,
    chat_filter_mod_only: TwitchX.chatFilters.modOnly,
    chat_anti_spam: TwitchX.chatFilters.antiSpam,
  });
  if (TwitchX.api) TwitchX.api.save_settings(data);
}

function toggleChatFilterPanel() {
  var panel = document.getElementById('chat-filter-panel');
  if (!panel) return;
  var opening = panel.classList.contains('hidden');
  panel.classList.toggle('hidden', !opening);
  if (opening) loadChatFiltersFromConfig();
}

TwitchX.loadChatFiltersFromConfig = loadChatFiltersFromConfig;
TwitchX.saveChatFilters = saveChatFilters;
TwitchX.toggleChatFilterPanel = toggleChatFilterPanel;

/* ── Chat Log Export ────────────────────────────────────── */

var CHAT_LOG_MAX = 5000;
TwitchX.chatLog = [];

function _appendChatLog(msg) {
  TwitchX.chatLog.push({
    ts: msg.timestamp || new Date().toISOString(),
    platform: msg.platform,
    author: msg.author_display || msg.author,
    text: msg.text,
    badges: (msg.badges || []).map(function(b) { return b.name; }),
    is_system: msg.is_system,
  });
  if (TwitchX.chatLog.length > CHAT_LOG_MAX) {
    TwitchX.chatLog.shift();
  }
}

function exportChatLog(format) {
  if (TwitchX.chatLog.length === 0) {
    TwitchX.setStatus('Chat log is empty', 'info');
    return;
  }
  var channel = (TwitchX.state.watchingChannel || 'chat').replace(/[/\\:*?"<>|]/g, '_');
  var filename = 'twitchx-chat-' + channel + '-' + new Date().toISOString().slice(0, 19).replace(/:/g, '-');
  var content, mime;
  if (format === 'json') {
    content = JSON.stringify(TwitchX.chatLog, null, 2);
    mime = 'application/json';
    filename += '.json';
  } else {
    content = TwitchX.chatLog.map(function(m) {
      var badge = m.badges.length ? '[' + m.badges.join(',') + '] ' : '';
      return '[' + m.ts + '] ' + badge + m.author + ': ' + m.text;
    }).join('\n');
    mime = 'text/plain';
    filename += '.txt';
  }
  var blob = new Blob([content], { type: mime });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  setTimeout(function() {
    URL.revokeObjectURL(url);
    document.body.removeChild(a);
  }, 500);
  TwitchX.setStatus('Chat log saved: ' + filename, 'info');
}

TwitchX.exportChatLog = exportChatLog;
TwitchX._appendChatLog = _appendChatLog;

/* ── Emote Picker ───────────────────────────────────────── */

TwitchX._emotePickerOpen = false;
TwitchX._cachedPickerEmotes = null;

function buildPickerEmoteList() {
  return TwitchX.thirdPartyEmotes || {};
}

function renderEmotePicker(filter) {
  var grid = document.getElementById('emote-grid');
  if (!grid) return;
  grid.textContent = '';

  var emotes = TwitchX._cachedPickerEmotes || buildPickerEmoteList();
  TwitchX._cachedPickerEmotes = emotes;

  var codes = Object.keys(emotes);
  if (filter) {
    var lf = filter.toLowerCase();
    codes = codes.filter(function(c) { return c.toLowerCase().indexOf(lf) !== -1; });
  }
  codes.sort();
  codes.slice(0, 200).forEach(function(code) {
    var img = document.createElement('img');
    img.className = 'emote emote-pick';
    img.src = emotes[code];
    img.alt = code;
    img.title = code;
    img.onerror = function() { this.style.display = 'none'; };
    img.addEventListener('click', function() {
      var input = document.getElementById('chat-input');
      if (input) {
        var v = input.value;
        input.value = v + (v && !v.endsWith(' ') ? ' ' : '') + code + ' ';
        input.focus();
      }
      closeEmotePicker();
    });
    grid.appendChild(img);
  });

  if (codes.length === 0) {
    var empty = document.createElement('span');
    empty.style.cssText = 'font-size:11px;color:var(--text-muted);padding:8px;';
    empty.textContent = filter ? 'No matches' : 'No emotes loaded yet';
    grid.appendChild(empty);
  }
}

function openEmotePicker() {
  TwitchX._emotePickerOpen = true;
  TwitchX._cachedPickerEmotes = null;
  var picker = document.getElementById('emote-picker');
  if (picker) picker.classList.remove('hidden');
  var searchEl = document.getElementById('emote-search');
  if (searchEl) { searchEl.value = ''; searchEl.focus(); }
  renderEmotePicker('');
}

function closeEmotePicker() {
  TwitchX._emotePickerOpen = false;
  var picker = document.getElementById('emote-picker');
  if (picker) picker.classList.add('hidden');
}

function toggleEmotePicker() {
  if (TwitchX._emotePickerOpen) closeEmotePicker();
  else openEmotePicker();
}

TwitchX.toggleEmotePicker = toggleEmotePicker;
TwitchX.closeEmotePicker = closeEmotePicker;
TwitchX.renderEmotePicker = renderEmotePicker;

/* ── Chat User List ─────────────────────────────────────── */

TwitchX._chatUserList = [];

function renderChatUserList(filter) {
  var container = document.getElementById('chat-userlist-items');
  if (!container) return;
  container.textContent = '';
  var users = TwitchX._chatUserList;
  if (filter) {
    var lf = filter.toLowerCase();
    users = users.filter(function(u) { return u.toLowerCase().indexOf(lf) !== -1; });
  }
  users.slice(0, 200).forEach(function(u) {
    var el = document.createElement('div');
    el.className = 'userlist-item';
    el.textContent = u;
    container.appendChild(el);
  });
}

function toggleChatUserList() {
  var panel = document.getElementById('chat-userlist-panel');
  if (!panel) return;
  var open = !panel.classList.contains('hidden');
  panel.classList.toggle('hidden', open);
  if (!open) renderChatUserList('');
}

TwitchX.toggleChatUserList = toggleChatUserList;
TwitchX.renderChatUserList = renderChatUserList;
