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
  if (!emotes || emotes.length === 0) {
    parent.appendChild(document.createTextNode(text));
    return;
  }
  const sorted = emotes.slice().sort(function(a, b) { return a.start - b.start; });
  let lastIdx = 0;
  for (let i = 0; i < sorted.length; i++) {
    const emote = sorted[i];
    if (emote.start > lastIdx) {
      parent.appendChild(document.createTextNode(text.slice(lastIdx, emote.start)));
    }
    const img = document.createElement('img');
    img.className = 'emote';
    img.src = emote.url;
    img.alt = emote.code;
    img.title = emote.code;
    parent.appendChild(img);
    lastIdx = emote.end + 1;
  }
  if (lastIdx < text.length) {
    parent.appendChild(document.createTextNode(text.slice(lastIdx)));
  }
}

function clearChatMessages() {
  const container = document.getElementById('chat-messages');
  if (!container) return;
  while (container.firstChild) {
    container.removeChild(container.firstChild);
  }
  clearChatReply();
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
