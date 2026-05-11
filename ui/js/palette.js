window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

var PALETTE_COMMANDS = [
  { label: 'Refresh Streams',     icon: '\u21BB', hint: 'R',   action: function() { TwitchX.doRefresh(); } },
  { label: 'Open Settings',       icon: '\u2699', hint: '\u2318,', action: function() { TwitchX.openSettings(); } },
  { label: 'Browse Categories',   icon: '\uD83D\uDCFA', hint: '', action: function() { TwitchX.showBrowseView(); } },
  { label: 'Toggle Chat',         icon: '\uD83D\uDCAC', hint: 'C', action: function() {
    if (TwitchX.multiState.open) TwitchX.toggleMsChat();
    else TwitchX.toggleChatPanel();
  }},
  { label: 'Stop Player',         icon: '\u23F9', hint: '', action: function() { if (TwitchX.api) TwitchX.api.stop_player(); } },
  { label: 'Toggle Mini Mode',    icon: '\uD83D\uDDD5', hint: '', action: function() { TwitchX.toggleMiniMode(); } },
];

TwitchX._paletteActiveIdx = -1;
TwitchX._paletteItems = [];

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
  TwitchX._paletteActiveIdx = -1;
  TwitchX._paletteItems = [];
}

function _buildPaletteItem(icon, label, hint, action) {
  var item = document.createElement('div');
  item.className = 'palette-item';
  item.setAttribute('role', 'option');

  var iconEl = document.createElement('span');
  iconEl.className = 'palette-item-icon';
  iconEl.textContent = icon;

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
    TwitchX._paletteItems.forEach(function(i) { i.classList.remove('palette-active'); });
    item.classList.add('palette-active');
    TwitchX._paletteActiveIdx = TwitchX._paletteItems.indexOf(item);
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
        '\uD83D\uDD34',
        s.display_name,
        TwitchX.formatViewers(s.viewers) + ' viewers',
        function() { TwitchX.selectChannel(s.login); TwitchX.doWatch(); }
      );
      container.appendChild(item);
      allItems.push(item);
    });
  }

  // Offline favorites
  var liveLogins = new Set(TwitchX.state.streams.map(function(s) { return s.login; }));
  var favMatches = TwitchX.state.favorites.filter(function(login) {
    if (liveLogins.has(login)) return false;
    if (!q) return true;
    var meta = TwitchX.state.favoritesMeta[login] || {};
    var name = meta.display_name || login;
    return login.toLowerCase().indexOf(q) !== -1 || name.toLowerCase().indexOf(q) !== -1;
  }).slice(0, 3);

  if (favMatches.length > 0) {
    var favHeader = document.createElement('div');
    favHeader.className = 'palette-section-header';
    favHeader.textContent = 'Favorites';
    container.appendChild(favHeader);
    favMatches.forEach(function(login) {
      var meta = TwitchX.state.favoritesMeta[login] || {};
      var displayName = meta.display_name || login;
      var item = _buildPaletteItem('\u2605', displayName, 'Offline', function() {
        TwitchX.selectChannel(login);
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
    TwitchX._paletteActiveIdx = 0;
    allItems[0].classList.add('palette-active');
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
    if (items[TwitchX._paletteActiveIdx]) items[TwitchX._paletteActiveIdx].classList.remove('palette-active');
    TwitchX._paletteActiveIdx = (TwitchX._paletteActiveIdx + 1) % items.length;
    items[TwitchX._paletteActiveIdx].classList.add('palette-active');
    items[TwitchX._paletteActiveIdx].scrollIntoView({ block: 'nearest' });
    return;
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (items.length === 0) return;
    if (items[TwitchX._paletteActiveIdx]) items[TwitchX._paletteActiveIdx].classList.remove('palette-active');
    TwitchX._paletteActiveIdx = (TwitchX._paletteActiveIdx - 1 + items.length) % items.length;
    items[TwitchX._paletteActiveIdx].classList.add('palette-active');
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
