window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

function getFilteredSortedStreams() {
  var streams = TwitchX.state.streams.slice();
  if (TwitchX.state.activePlatformFilter !== 'all') {
    streams = streams.filter(function(s) { return s.platform === TwitchX.state.activePlatformFilter; });
  }
  if (TwitchX.state.filterText) {
    var ft = TwitchX.state.filterText.toLowerCase();
    streams = streams.filter(function(s) { return s.game.toLowerCase().indexOf(ft) !== -1; });
  }

  var pinned = streams.filter(function(s) {
    return TwitchX.isPinned(s.platform || 'twitch', s.login);
  });
  var rest = streams.filter(function(s) {
    return !TwitchX.isPinned(s.platform || 'twitch', s.login);
  });

  function sortGroup(arr) {
    if (TwitchX.state.sortKey === 'viewers') {
      arr.sort(function(a, b) { return b.viewers - a.viewers; });
    } else if (TwitchX.state.sortKey === 'recent') {
      arr.sort(function(a, b) { return new Date(b.started_at) - new Date(a.started_at); });
    } else if (TwitchX.state.sortKey === 'alpha') {
      arr.sort(function(a, b) { return a.display_name.localeCompare(b.display_name); });
    }
    return arr;
  }

  return sortGroup(pinned).concat(sortGroup(rest));
}

function renderGrid() {
  // Skip rendering when player view is active — grid is hidden
  if (document.getElementById('player-view').classList.contains('active')) return;
  // Skip rendering when browse view is open — avoids restoring grid inline style
  if (document.getElementById('browse-view') &&
      !document.getElementById('browse-view').classList.contains('hidden')) return;
  // Skip rendering when multistream view is open — same inline-style conflict
  if (TwitchX.multiState.open) return;

  const grid = document.getElementById('stream-grid');
  grid.classList.toggle('list-mode', TwitchX.state.gridMode === 'list');
  const empty = document.getElementById('empty-state');
  const streams = getFilteredSortedStreams();

  // Empty states
  if (TwitchX.state.favorites.length === 0 && !TwitchX.state.hasCredentials) {
    grid.classList.add('hidden');
    empty.classList.add('visible');
    empty.querySelector('.empty-icon').textContent = '\u26A1';
    empty.querySelector('.empty-title').textContent = 'Welcome to TwitchX';
    const sub = empty.querySelector('.empty-subtitle');
    while (sub.firstChild) sub.removeChild(sub.firstChild);
    const card1 = createOnboardingCard('Step 1', 'Open Settings and enter your Twitch API credentials');
    const card2 = createOnboardingCard('Step 2', 'Add your favorite channels using the search bar');
    const btn = document.createElement('button');
    btn.className = 'onboarding-btn';
    btn.textContent = 'Open Settings';
    btn.addEventListener('click', TwitchX.openSettings);
    sub.appendChild(card1);
    sub.appendChild(card2);
    sub.appendChild(btn);
    return;
  }

  if (TwitchX.state.favorites.length === 0 && TwitchX.state.hasCredentials) {
    grid.classList.add('hidden');
    empty.classList.add('visible');
    empty.querySelector('.empty-icon').textContent = '\uD83D\uDCFA';
    empty.querySelector('.empty-title').textContent = 'No favorites yet';
    empty.querySelector('.empty-subtitle').textContent = 'Add channels using the search bar in the sidebar';
    return;
  }

  if (streams.length === 0 && TwitchX.state.favorites.length > 0) {
    grid.classList.add('hidden');
    empty.classList.add('visible');
    empty.querySelector('.empty-icon').textContent = '\uD83D\uDE34';
    empty.querySelector('.empty-title').textContent = 'All quiet right now';
    empty.querySelector('.empty-subtitle').textContent = 'None of your favorites are live';
    return;
  }

  empty.classList.remove('visible');
  grid.classList.remove('hidden');

  // Diff-based update
  const existingLogins = new Set();
  grid.querySelectorAll('.stream-card').forEach(function(c) { existingLogins.add(c.dataset.login); });
  const newLogins = new Set(streams.map(function(s) { return s.login; }));

  let setsEqual = existingLogins.size === newLogins.size;
  if (setsEqual) {
    existingLogins.forEach(function(l) { if (!newLogins.has(l)) setsEqual = false; });
  }

  if (setsEqual && existingLogins.size > 0) {
    // In-place update
    streams.forEach(function(s) {
      const card = grid.querySelector('.stream-card[data-login="' + s.login + '"]');
      if (!card) return;
      card.querySelector('.viewers').textContent = TwitchX.formatViewers(s.viewers) + ' viewers';
      const trend = card.querySelector('.trend');
      if (s.viewer_trend === 'up') {
        trend.textContent = '\u25B2'; trend.className = 'trend up';
      } else if (s.viewer_trend === 'down') {
        trend.textContent = '\u25BC'; trend.className = 'trend down';
      } else {
        trend.textContent = ''; trend.className = 'trend';
      }
      card.querySelector('.card-title').textContent = s.title;
      card.querySelector('.card-title').title = s.title;
      card.querySelector('.card-game').textContent = TwitchX.truncate(s.game, 28);
      card.querySelector('.uptime-badge').textContent = TwitchX.formatUptime(s.started_at);
      const wb = card.querySelector('.watching-badge');
      wb.classList.toggle('visible', TwitchX.state.watchingChannel === s.login);
      card.classList.toggle('selected', TwitchX.state.selectedChannel === s.login);
    });
    // Reorder cards to match sort
    streams.forEach(function(s) {
      const card = grid.querySelector('.stream-card[data-login="' + s.login + '"]');
      if (card) grid.appendChild(card);
    });
  } else {
    // Full rebuild using safe DOM methods
    while (grid.firstChild) grid.removeChild(grid.firstChild);
    streams.forEach(function(s) {
      const card = createStreamCard(s);
      grid.appendChild(card);
    });
    // Request missing thumbnails
    streams.forEach(function(s) {
      if (!TwitchX.state.thumbnails[s.login] && s.thumbnail_url) {
        TwitchX.api.get_thumbnail(s.login, s.thumbnail_url);
      }
    });
  }
}

function createStreamCard(s) {
  const card = document.createElement('div');
  card.className = 'stream-card' + (TwitchX.state.selectedChannel === s.login ? ' selected' : '');
  card.dataset.login = s.login;
  card.dataset.started = s.started_at;
  card.dataset.platform = s.platform || 'twitch';
  if (TwitchX.state.gridMode === 'list') card.classList.add('list-mode');

  // Thumb area
  const thumb = document.createElement('div');
  thumb.className = 'card-thumb';

  const img = document.createElement('img');
  img.className = 'thumb-img' + (TwitchX.state.thumbnails[s.login] ? ' loaded' : '');
  img.src = TwitchX.state.thumbnails[s.login] || '';
  img.alt = '';
  thumb.appendChild(img);

  const shimmer = document.createElement('div');
  shimmer.className = 'thumb-shimmer';
  thumb.appendChild(shimmer);

  const liveBadge = document.createElement('span');
  liveBadge.className = 'live-badge';
  liveBadge.textContent = 'LIVE';
  thumb.appendChild(liveBadge);

  const platformBadge = document.createElement('span');
  platformBadge.className = 'platform-badge ' + (s.platform || 'twitch');
  platformBadge.textContent = s.platform === 'kick' ? 'K' : s.platform === 'youtube' ? 'YT' : 'T';
  thumb.appendChild(platformBadge);

  const watchBadge = document.createElement('span');
  watchBadge.className = 'watching-badge' + (TwitchX.state.watchingChannel === s.login ? ' visible' : '');
  watchBadge.textContent = '\u25B6 WATCHING';
  thumb.appendChild(watchBadge);

  const uptime = document.createElement('span');
  uptime.className = 'uptime-badge';
  uptime.textContent = TwitchX.formatUptime(s.started_at);
  thumb.appendChild(uptime);

  if (TwitchX.isPinned(s.platform || 'twitch', s.login)) {
    var pinBadge = document.createElement('span');
    pinBadge.className = 'pin-badge';
    pinBadge.textContent = '\uD83D\uDCCC';
    pinBadge.title = 'Pinned';
    thumb.appendChild(pinBadge);
  }

  card.appendChild(thumb);

  // Info area
  const info = document.createElement('div');
  info.className = 'card-info';

  const meta = document.createElement('div');
  meta.className = 'card-meta';

  const viewers = document.createElement('span');
  viewers.className = 'viewers';
  viewers.textContent = TwitchX.formatViewers(s.viewers) + ' viewers';
  meta.appendChild(viewers);

  const trend = document.createElement('span');
  trend.className = 'trend' + (s.viewer_trend === 'up' ? ' up' : s.viewer_trend === 'down' ? ' down' : '');
  trend.textContent = s.viewer_trend === 'up' ? '\u25B2' : s.viewer_trend === 'down' ? '\u25BC' : '';
  meta.appendChild(trend);
  info.appendChild(meta);

  const channelName = document.createElement('div');
  channelName.className = 'card-channel';
  channelName.textContent = s.display_name;
  info.appendChild(channelName);

  const title = document.createElement('div');
  title.className = 'card-title';
  title.textContent = s.title;
  title.title = s.title;
  info.appendChild(title);

  const game = document.createElement('div');
  game.className = 'card-game';
  game.textContent = TwitchX.truncate(s.game, 28);
  info.appendChild(game);

  card.appendChild(info);

  // Events
  card.addEventListener('click', function() { TwitchX.selectChannel(s.login); });
  card.addEventListener('dblclick', function() { TwitchX.selectChannel(s.login); TwitchX.doWatch(); });
  card.addEventListener('contextmenu', function(e) { TwitchX.showContextMenu(e, s.login); });

  return card;
}

function createOnboardingCard(stepNum, stepText) {
  const card = document.createElement('div');
  card.className = 'onboarding-card';
  const num = document.createElement('div');
  num.className = 'step-num';
  num.textContent = stepNum;
  const text = document.createElement('div');
  text.className = 'step-text';
  text.textContent = stepText;
  card.appendChild(num);
  card.appendChild(text);
  return card;
}

TwitchX.getFilteredSortedStreams = getFilteredSortedStreams;
TwitchX.renderGrid = renderGrid;

function showSkeletonGrid() {
  var grid = document.getElementById('stream-grid');
  var empty = document.getElementById('empty-state');
  empty.classList.remove('visible');
  grid.classList.remove('hidden');
  grid.replaceChildren();
  for (var i = 0; i < 8; i++) {
    var card = document.createElement('div');
    card.className = 'skeleton-card';
    var thumb = document.createElement('div');
    thumb.className = 'skeleton skeleton-thumb';
    card.appendChild(thumb);
    var line1 = document.createElement('div');
    line1.className = 'skeleton skeleton-text skeleton-text-medium';
    card.appendChild(line1);
    var line2 = document.createElement('div');
    line2.className = 'skeleton skeleton-text skeleton-text-short';
    card.appendChild(line2);
    grid.appendChild(card);
  }
}

function hideSkeletonGrid() {
  var grid = document.getElementById('stream-grid');
  var skeletons = grid.querySelectorAll('.skeleton-card');
  if (skeletons.length > 0) grid.replaceChildren();
}

TwitchX.showSkeletonGrid = showSkeletonGrid;
TwitchX.hideSkeletonGrid = hideSkeletonGrid;
TwitchX.createStreamCard = createStreamCard;
TwitchX.createOnboardingCard = createOnboardingCard;
