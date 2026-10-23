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
  { label: 'Toggle Mini Mode',    icon: 'minimize', hint: '\u21E7\u2318M', action: function() { TwitchX.toggleMiniMode(); } },
  { label: 'Add channel\u2026',   icon: 'plus', hint: '', keepOpen: true, action: function() { openPalette('add'); } },
];

// Remote channel search: the palette asks Python once the query has settled
// and window.onSearchResults hands the reply back through receivePaletteSearch.
const PALETTE_SEARCH_MIN_CHARS = 2;
const PALETTE_SEARCH_DEBOUNCE_MS = 400;
const PALETTE_GAME_LIMIT = 5;

TwitchX._paletteActiveIdx = -1;
TwitchX._paletteItems = [];
TwitchX._paletteItemCounter = 0;
TwitchX._paletteReturnFocus = null;
// 'search' (channels, games, commands) or 'add' (Enter adds the typed channel).
TwitchX._paletteMode = 'search';
TwitchX._paletteSearch = { query: '', results: [], status: 'idle', timer: null };

const PALETTE_PLACEHOLDERS = {
  search: 'Search channels, games and commands...',
  add: 'Add a channel: name, URL or @handle',
};

function isPaletteOpen() {
  var overlay = document.getElementById('palette-overlay');
  return !!overlay && !overlay.classList.contains('hidden');
}

function _resetPaletteSearch() {
  var search = TwitchX._paletteSearch;
  if (search.timer) clearTimeout(search.timer);
  TwitchX._paletteSearch = { query: '', results: [], status: 'idle', timer: null };
}

function openPalette(mode) {
  var overlay = document.getElementById('palette-overlay');
  if (!overlay) return;
  var wasOpen = isPaletteOpen();
  if (wasOpen && (mode || 'search') === TwitchX._paletteMode) return;
  if (!wasOpen) TwitchX._paletteReturnFocus = document.activeElement;
  TwitchX._paletteMode = mode === 'add' ? 'add' : 'search';
  overlay.classList.remove('hidden');
  var input = document.getElementById('palette-input');
  input.value = '';
  input.placeholder = PALETTE_PLACEHOLDERS[TwitchX._paletteMode];
  input.setAttribute('aria-label', PALETTE_PLACEHOLDERS[TwitchX._paletteMode]);
  _resetPaletteSearch();
  TwitchX._paletteActiveIdx = -1;
  TwitchX._paletteItems = [];
  renderPaletteResults('');
  // Focus now so keys typed right after ⌘K land in the field; the deferred
  // call covers a focus change made by whatever opened the palette.
  input.focus();
  setTimeout(function() { input.focus(); }, 0);
}

function closePalette() {
  var overlay = document.getElementById('palette-overlay');
  if (!overlay || overlay.classList.contains('hidden')) return;
  overlay.classList.add('hidden');
  var input = document.getElementById('palette-input');
  if (input) input.setAttribute('aria-activedescendant', '');
  _resetPaletteSearch();
  TwitchX._paletteMode = 'search';
  TwitchX._paletteActiveIdx = -1;
  TwitchX._paletteItems = [];
  var returnFocus = TwitchX._paletteReturnFocus;
  TwitchX._paletteReturnFocus = null;
  if (returnFocus && document.contains(returnFocus) && returnFocus.focus) {
    setTimeout(function() { returnFocus.focus(); }, 0);
  }
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

function _buildPaletteState(title, detail) {
  var state = document.createElement('div');
  state.className = 'palette-state';

  var titleEl = document.createElement('div');
  titleEl.className = 'palette-state-title';
  titleEl.textContent = title;

  var detailEl = document.createElement('div');
  detailEl.className = 'palette-state-detail';
  detailEl.textContent = detail;

  state.appendChild(titleEl);
  state.appendChild(detailEl);
  return state;
}

function _buildPaletteItem(icon, label, hint, action, options) {
  options = options || {};
  var item = document.createElement('div');
  item.className = 'palette-item';
  item.setAttribute('role', 'option');
  if (options.key) item.dataset.key = options.key;
  if (options.login) item.dataset.login = options.login;
  if (options.platform) item.dataset.platform = options.platform;
  var ariaLabel = label;
  if (options.platform) ariaLabel += ' on ' + TwitchX.platformLabel(options.platform);
  if (hint) ariaLabel += ', ' + hint;
  item.setAttribute('aria-label', ariaLabel);
  TwitchX._paletteItemCounter += 1;
  item.id = 'palette-item-' + TwitchX._paletteItemCounter;

  var iconEl = document.createElement('span');
  iconEl.className = 'palette-item-icon';
  if (options.avatarFor) {
    // Search results carry no avatar URL; use a cached one or the initial.
    iconEl.classList.add('palette-item-avatar');
    var cached = TwitchX.state.avatars[options.key];
    if (cached) {
      var img = document.createElement('img');
      img.alt = '';
      img.src = cached;
      iconEl.appendChild(img);
    } else {
      iconEl.textContent = (options.avatarFor || '?').charAt(0).toUpperCase();
    }
  } else {
    TwitchX.setIconOnly(iconEl, icon, 16);
  }

  var labelWrap = document.createElement('span');
  labelWrap.className = 'palette-item-label';

  var labelEl = document.createElement('span');
  labelEl.className = 'palette-item-title';
  labelEl.textContent = label;
  labelWrap.appendChild(labelEl);
  if (options.platform) {
    var platformDot = document.createElement('span');
    platformDot.className = 'platform-dot ' + options.platform;
    platformDot.title = TwitchX.platformLabel(options.platform);
    labelWrap.appendChild(platformDot);
  }
  if (options.live) {
    var liveEl = document.createElement('span');
    liveEl.className = 'palette-item-live';
    liveEl.textContent = 'Live';
    labelWrap.appendChild(liveEl);
  }

  var hintEl = document.createElement('span');
  hintEl.className = 'palette-item-hint';
  hintEl.textContent = hint;

  item.appendChild(iconEl);
  item.appendChild(labelWrap);
  item.appendChild(hintEl);

  item._paletteAction = action;
  item._paletteAltAction = options.altAction || null;
  item.addEventListener('click', function(e) {
    var run = (e.metaKey && item._paletteAltAction) ? item._paletteAltAction : action;
    if (!options.keepOpen) closePalette();
    run();
  });
  item.addEventListener('mouseenter', function() {
    _setPaletteActive(TwitchX._paletteItems.indexOf(item));
  });
  return item;
}

function _paletteGroup(container, label) {
  var group = document.createElement('div');
  group.className = 'palette-group';
  group.setAttribute('role', 'group');
  group.setAttribute('aria-label', label);
  var header = document.createElement('div');
  header.className = 'palette-section-header';
  header.setAttribute('aria-hidden', 'true');
  header.textContent = label;
  group.appendChild(header);
  container.appendChild(group);
  return group;
}

function _paletteOpenProfile(login, platform) {
  if (TwitchX.multiState.open) TwitchX.closeMultistreamView();
  var player = document.getElementById('player-view');
  if (player && player.classList.contains('view-active')) TwitchX.hidePlayerView(true);
  TwitchX.showChannelView(login, platform, 'grid');
}

// Unique games of the live streams, most watched first.
function _paletteGames(q) {
  var byGame = {};
  TwitchX.state.streams.forEach(function(s) {
    if (!s.game) return;
    var entry = byGame[s.game] || (byGame[s.game] = { name: s.game, live: 0, viewers: 0 });
    entry.live += 1;
    entry.viewers += s.viewers || 0;
  });
  return Object.keys(byGame).map(function(k) { return byGame[k]; }).filter(function(g) {
    return !q || g.name.toLowerCase().indexOf(q) !== -1;
  }).sort(function(a, b) { return b.viewers - a.viewers; }).slice(0, PALETTE_GAME_LIMIT);
}

function _schedulePaletteSearch(query) {
  var q = query.trim();
  var search = TwitchX._paletteSearch;
  if (q.length < PALETTE_SEARCH_MIN_CHARS) {
    _resetPaletteSearch();
    return;
  }
  if (q === search.query) return;
  if (search.timer) clearTimeout(search.timer);
  search.query = q;
  search.results = [];
  search.status = 'loading';
  search.timer = setTimeout(function() {
    search.timer = null;
    var platform = TwitchX.state.activePlatformFilter === 'all' ? 'all' : TwitchX.state.activePlatformFilter;
    if (TwitchX.api) TwitchX.api.search_channels(q, platform);
    else search.status = 'done';
  }, PALETTE_SEARCH_DEBOUNCE_MS);
}

// Called by window.onSearchResults while the palette is open.
function receivePaletteSearch(results, meta) {
  if (!isPaletteOpen()) return false;
  var input = document.getElementById('palette-input');
  var current = input ? input.value.trim() : '';
  if (!current || (meta && meta.query !== current)) return true;
  TwitchX._paletteSearch.query = current;
  TwitchX._paletteSearch.results = results || [];
  TwitchX._paletteSearch.status = 'done';
  var active = TwitchX._paletteItems[TwitchX._paletteActiveIdx];
  var activeKey = active ? (active.dataset.key || active.id) : '';
  renderPaletteResults(input.value, { keepSearch: true });
  // A late reply must not throw the highlight back to the top of the list.
  var keepIdx = TwitchX._paletteItems.findIndex(function(item) {
    return (item.dataset.key || item.id) === activeKey;
  });
  if (keepIdx > 0) _setPaletteActive(keepIdx);
  return true;
}

function _renderPaletteSearchGroup(container, allItems, addMode) {
  var search = TwitchX._paletteSearch;
  if (search.status === 'idle') return;
  var group = _paletteGroup(container, 'Channels (search)');
  if (search.status === 'loading') {
    group.appendChild(_buildPaletteState('Searching...', 'Looking up "' + search.query + '".'));
    return;
  }
  if (!search.results.length) {
    group.appendChild(_buildPaletteState('No channels found', 'Nothing on the selected platforms matches "' + search.query + '".'));
    return;
  }
  search.results.slice(0, 8).forEach(function(r) {
    var platform = r.platform || 'twitch';
    var name = r.display_name || r.login;
    var add = function() { TwitchX.addChannel(r.login, platform, r.display_name || ''); };
    var open = function() { _paletteOpenProfile(r.login, platform); };
    var item = _buildPaletteItem(
      'user',
      name,
      addMode ? 'Add' : (r.game_name || '') + (r.game_name ? ' · ' : '') + '↵ profile · ⌘↵ add',
      addMode ? add : open,
      {
        key: 'search:' + TwitchX.channelKey(r.login, platform),
        login: r.login,
        platform: platform,
        avatarFor: name,
        live: !!r.is_live,
        altAction: addMode ? open : add,
      }
    );
    group.appendChild(item);
    allItems.push(item);
  });
}

function renderPaletteResults(query, opts) {
  var q = query.toLowerCase().trim();
  var addMode = TwitchX._paletteMode === 'add';
  var container = document.getElementById('palette-results');
  container.replaceChildren();
  var allItems = [];
  if (!(opts && opts.keepSearch)) _schedulePaletteSearch(query);

  if (addMode) {
    if (q) {
      var addGroup = _paletteGroup(container, 'Add');
      var addItem = _buildPaletteItem('plus', 'Add “' + query.trim() + '” to favorites', '↵', function() {
        TwitchX.addChannelFromQuery(query.trim(), TwitchX._paletteSearch.results);
      }, { key: 'add-typed' });
      addGroup.appendChild(addItem);
      allItems.push(addItem);
    }
    _renderPaletteSearchGroup(container, allItems, true);
    TwitchX._paletteItems = allItems;
    if (allItems.length > 0) {
      _setPaletteActive(0);
    } else {
      container.appendChild(_buildPaletteState('Add a channel', 'Type a channel name, a twitch.tv / kick.com / youtube.com link or an @handle.'));
      _setPaletteActive(-1);
    }
    return;
  }

  if (!q && !TwitchX.state.streamsLoaded) {
    container.appendChild(_buildPaletteState('Loading channels...', 'Commands are available while streams load.'));
  }

  // Live channels
  var liveMatches = TwitchX.state.streams.filter(function(s) {
    if (!q) return true;
    var displayName = s.display_name || s.login || '';
    return s.login.toLowerCase().indexOf(q) !== -1 ||
           displayName.toLowerCase().indexOf(q) !== -1;
  }).slice(0, 5);

  if (liveMatches.length > 0) {
    var liveGroup = _paletteGroup(container, 'Live Now');
    liveMatches.forEach(function(s) {
      var platform = s.platform || 'twitch';
      var key = TwitchX.channelKey(s.login, platform);
      var item = _buildPaletteItem(
        'live-dot',
        s.display_name || s.login,
        TwitchX.formatViewers(s.viewers) + ' viewers',
        function() { TwitchX.selectChannel(s.login, platform); TwitchX.doWatch(); },
        { key: key, login: s.login, platform: platform }
      );
      liveGroup.appendChild(item);
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
    var favGroup = _paletteGroup(container, 'Favorites');
    favMatches.forEach(function(entry) {
      var displayName = entry.display_name || entry.login;
      var item = _buildPaletteItem('star', displayName, 'Offline', function() {
        _paletteOpenProfile(entry.login, entry.platform);
      }, { key: entry.key, login: entry.login, platform: entry.platform });
      favGroup.appendChild(item);
      allItems.push(item);
    });
  }

  // Games of the live streams: Enter filters the Following grid.
  var games = _paletteGames(q);
  if (games.length > 0) {
    var gameGroup = _paletteGroup(container, 'Games');
    games.forEach(function(g) {
      var item = _buildPaletteItem('tv', g.name, g.live + ' live', function() {
        TwitchX.setGameFilter(g.name);
      }, { key: 'game:' + g.name });
      gameGroup.appendChild(item);
      allItems.push(item);
    });
  }

  _renderPaletteSearchGroup(container, allItems, false);

  // Commands
  var cmdMatches = PALETTE_COMMANDS.filter(function(c) {
    return !q || c.label.toLowerCase().indexOf(q) !== -1;
  });

  if (cmdMatches.length > 0) {
    var cmdGroup = _paletteGroup(container, 'Commands');
    cmdMatches.forEach(function(cmd) {
      var item = _buildPaletteItem(cmd.icon, cmd.label, cmd.hint, cmd.action, { keepOpen: cmd.keepOpen });
      cmdGroup.appendChild(item);
      allItems.push(item);
    });
  }

  TwitchX._paletteItems = allItems;
  if (allItems.length > 0) {
    _setPaletteActive(0);
  } else {
    if (q) {
      container.appendChild(_buildPaletteState('No results', 'No channels or commands match "' + query.trim() + '".'));
    } else {
      container.appendChild(_buildPaletteState('No channels yet', 'Use Add channel… to add favorites or refresh streams.'));
    }
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
    if (!active) return;
    if (e.metaKey && active._paletteAltAction) {
      closePalette();
      active._paletteAltAction();
      return;
    }
    active.click();
    return;
  }
}

TwitchX.openPalette = openPalette;
TwitchX.closePalette = closePalette;
TwitchX.renderPaletteResults = renderPaletteResults;
TwitchX.receivePaletteSearch = receivePaletteSearch;
TwitchX.isPaletteOpen = isPaletteOpen;
TwitchX.handlePaletteKeydown = handlePaletteKeydown;
