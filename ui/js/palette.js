window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

var PALETTE_COMMANDS = [
  { label: 'Refresh Streams',     icon: 'refresh', hint: 'R',   action: function() { TwitchX.doRefresh(); } },
  { label: 'Open Settings',       icon: 'settings', hint: '\u2318,', action: function() { TwitchX.openSettings(); } },
  { label: 'Browse Categories',   icon: 'tv', hint: '', action: function() { TwitchX.showBrowseView(); } },
  { label: 'Toggle Chat',         icon: 'chat', hint: 'C', action: function() {
    if (TwitchX.multiState.open) TwitchX.toggleMsChat();
    else TwitchX.toggleChatPanel();
  }},
  { label: 'Stop Player',         icon: 'stop', hint: '', action: function() { if (TwitchX.api) TwitchX.api.stop_player(); } },
  { label: 'Toggle Mini Mode',    icon: 'minimize', hint: '', action: function() { TwitchX.toggleMiniMode(); } },
];

TwitchX._paletteActiveIdx = -1;
TwitchX._paletteItems = [];
TwitchX._paletteItemCounter = 0;

function openPalette() {
  document.getElementById('palette-overlay').classList.remove('hidden');
  var input = document.getElementById('palette-input');
  input.value = '';
  TwitchX._paletteActiveIdx = -1;
  TwitchX._paletteItems = [];
  renderPaletteResults('');
  setTimeout(function() { input.focus(); }, 0);
}

function closePalette() {
  document.getElementById('palette-overlay').classList.add('hidden');
  var input = document.getElementById('palette-input');
  if (input) input.setAttribute('aria-activedescendant', '');
  TwitchX._paletteActiveIdx = -1;
  TwitchX._paletteItems = [];
}

function _setPaletteActive(idx) {
  var items = TwitchX._paletteItems || [];
  if (items.length === 0) {
    TwitchX._paletteActiveIdx = -1;
    var input = document.getElementById('palette-input');
    if (input) input.setAttribute('aria-activedescendant', '');
    return;
  }
  TwitchX._paletteActiveIdx = (idx + items.length) % items.length;
  items.forEach(function(item, itemIdx) {
    var active = itemIdx === TwitchX._paletteActiveIdx;
    item.classList.toggle('palette-active', active);
    item.setAttribute('aria-selected', String(active));
  });
  var activeItem = items[TwitchX._paletteActiveIdx];
  var paletteInput = document.getElementById('palette-input');
  if (paletteInput && activeItem) {
    paletteInput.setAttribute('aria-activedescendant', activeItem.id || '');
  }
}

function _buildPaletteItem(icon, label, hint, action) {
  var item = document.createElement('div');
  item.className = 'palette-item';
  item.setAttribute('role', 'option');
  TwitchX._paletteItemCounter += 1;
  item.id = 'palette-item-' + TwitchX._paletteItemCounter;

  var iconEl = document.createElement('span');
  iconEl.className = 'palette-item-icon';
  TwitchX.setIconOnly(iconEl, icon, 16);

  var labelEl = document.createElement('span');
  labelEl.className = 'palette-item-label';
  labelEl.textContent = label;

  var hintEl = document.createElement('span');
  hintEl.className = 'palette-item-hint';
  hintEl.textContent = hint;

  item.appendChild(iconEl);
  item.appendChild(labelEl);
  item.appendChild(hintEl);

  item.addEventListener('click', function() {
    closePalette();
    action();
  });
  item.addEventListener('mouseenter', function() {
    _setPaletteActive(TwitchX._paletteItems.indexOf(item));
  });
  return item;
}

function renderPaletteResults(query) {
  var q = query.toLowerCase().trim();
  var container = document.getElementById('palette-results');
  container.replaceChildren();
  var allItems = [];

  // Live channels
  var liveMatches = TwitchX.state.streams.filter(function(s) {
    if (!q) return true;
    return s.login.toLowerCase().indexOf(q) !== -1 ||
           s.display_name.toLowerCase().indexOf(q) !== -1;
  }).slice(0, 5);

  if (liveMatches.length > 0) {
    var liveHeader = document.createElement('div');
    liveHeader.className = 'palette-section-header';
    liveHeader.textContent = 'Live Now';
    container.appendChild(liveHeader);
    liveMatches.forEach(function(s) {
      var item = _buildPaletteItem(
        'live-dot',
        s.display_name,
        TwitchX.platformLabel(s.platform || 'twitch') + ' • ' + TwitchX.formatViewers(s.viewers) + ' viewers',
        function() { TwitchX.selectChannel(s.login, s.platform || 'twitch'); TwitchX.doWatch(); }
      );
      container.appendChild(item);
      allItems.push(item);
    });
  }

  // Offline favorites
  var liveLogins = new Set(TwitchX.state.streams.map(function(s) {
    return TwitchX.channelKey(s.login, s.platform || 'twitch');
  }));
  var favMatches = TwitchX.getFavoriteEntries().filter(function(entry) {
    if (liveLogins.has(entry.key)) return false;
    if (!q) return true;
    var name = entry.display_name || entry.login;
    return entry.login.toLowerCase().indexOf(q) !== -1 || name.toLowerCase().indexOf(q) !== -1;
  }).slice(0, 3);

  if (favMatches.length > 0) {
    var favHeader = document.createElement('div');
    favHeader.className = 'palette-section-header';
    favHeader.textContent = 'Favorites';
    container.appendChild(favHeader);
    favMatches.forEach(function(entry) {
      var displayName = entry.display_name || entry.login;
      var item = _buildPaletteItem('star', displayName, TwitchX.platformLabel(entry.platform) + ' • Offline', function() {
        TwitchX.selectChannel(entry.login, entry.platform);
      });
      container.appendChild(item);
      allItems.push(item);
    });
  }

  // Commands
  var cmdMatches = PALETTE_COMMANDS.filter(function(c) {
    return !q || c.label.toLowerCase().indexOf(q) !== -1;
  });

  if (cmdMatches.length > 0) {
    var cmdHeader = document.createElement('div');
    cmdHeader.className = 'palette-section-header';
    cmdHeader.textContent = 'Commands';
    container.appendChild(cmdHeader);
    cmdMatches.forEach(function(cmd) {
      var item = _buildPaletteItem(cmd.icon, cmd.label, cmd.hint, cmd.action);
      container.appendChild(item);
      allItems.push(item);
    });
  }

  TwitchX._paletteItems = allItems;
  if (allItems.length > 0) {
    _setPaletteActive(0);
  } else {
    _setPaletteActive(-1);
  }
}

function handlePaletteKeydown(e) {
  var items = TwitchX._paletteItems || [];

  if (e.key === 'Escape') {
    e.preventDefault();
    closePalette();
    return;
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    if (items.length === 0) return;
    _setPaletteActive(TwitchX._paletteActiveIdx + 1);
    items[TwitchX._paletteActiveIdx].scrollIntoView({ block: 'nearest' });
    return;
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (items.length === 0) return;
    _setPaletteActive(TwitchX._paletteActiveIdx - 1);
    items[TwitchX._paletteActiveIdx].scrollIntoView({ block: 'nearest' });
    return;
  }
  if (e.key === 'Enter') {
    e.preventDefault();
    var active = items[TwitchX._paletteActiveIdx];
    if (active) active.click();
    return;
  }
}

TwitchX.openPalette = openPalette;
TwitchX.closePalette = closePalette;
TwitchX.renderPaletteResults = renderPaletteResults;
TwitchX.handlePaletteKeydown = handlePaletteKeydown;
