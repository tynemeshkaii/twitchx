window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

function getFilteredSortedStreams() {
  var streams = TwitchX.state.streams.slice();
  if (TwitchX.state.activePlatformFilter !== 'all') {
    streams = streams.filter(function(s) { return s.platform === TwitchX.state.activePlatformFilter; });
  }
  if (TwitchX.state.filterText) {
    var ft = TwitchX.state.filterText.toLowerCase();
    streams = streams.filter(function(s) {
      var hay = (s.game || '') + ' ' + (s.display_name || '') + ' ' + (s.login || '');
      return hay.toLowerCase().indexOf(ft) !== -1;
    });
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

function getStreamCardLabel(s) {
  return 'Select ' + (s.display_name || s.login) + ' on ' +
    TwitchX.platformLabel(s.platform || 'twitch') + ', ' +
    TwitchX.formatViewers(s.viewers) + ' viewers';
}

// Pin state changes without a full rebuild, so the diff branch has to keep the
// badge in sync — otherwise the card reorders but the icon lags a poll behind.
function _syncPinBadge(card, s) {
  const thumb = card.querySelector('.card-thumb') || card;
  const existing = card.querySelector('.pin-badge');
  const pinned = TwitchX.isPinned(s.platform || 'twitch', s.login);
  if (pinned && !existing) {
    const pinBadge = document.createElement('span');
    pinBadge.className = 'pin-badge';
    TwitchX.setIconOnly(pinBadge, 'pin', 12);
    pinBadge.title = 'Pinned';
    thumb.appendChild(pinBadge);
  } else if (!pinned && existing) {
    existing.remove();
  }
}

function renderGrid() {
  // Skip rendering when player view is active — grid is hidden
  if (document.getElementById('player-view').classList.contains('view-active')) return;
  // Skip rendering when browse view is open — avoids restoring grid inline style
  if (document.getElementById('browse-view') &&
      document.getElementById('browse-view').classList.contains('view-active')) return;
  // Skip rendering when multistream view is open — same inline-style conflict
  if (TwitchX.multiState.open) return;

  const grid = document.getElementById('stream-grid');
  grid.classList.remove('grid-mode', 'comfortable-mode', 'compact-mode', 'list-mode');
  grid.classList.add('view', 'view-active');
  if (TwitchX.state.gridMode) grid.classList.add(TwitchX.state.gridMode + '-mode');
  grid.querySelectorAll('.stream-card').forEach(function(card) {
    card.classList.remove('grid-mode', 'comfortable-mode', 'compact-mode', 'list-mode');
    if (TwitchX.state.gridMode) card.classList.add(TwitchX.state.gridMode + '-mode');
  });
  const empty = document.getElementById('empty-state');
  const streams = getFilteredSortedStreams();

  // Empty states
  var anyLoggedIn = TwitchX.state.currentUser || TwitchX.state.kickUser || TwitchX.state.youtubeUser;
  if (TwitchX.state.favorites.length === 0 && !anyLoggedIn) {
    grid.classList.add('hidden');
    var welcomeOpts = {
      illustration: 'empty-favorites',
      title: 'Welcome to TwitchX',
      subtitle: 'Log in to see followed channels, or add channels manually from search.',
      primaryAction: { label: 'Login with Twitch', callback: function() { if (TwitchX.api) TwitchX.api.login(); } },
    };
    if (TwitchX.state.youtubeEnabled) {
      welcomeOpts.secondaryAction = { label: 'Connect YouTube', callback: function() { if (TwitchX.api) TwitchX.api.youtube_login(); } };
    }
    TwitchX.renderEmptyState(empty, welcomeOpts);

    return;
  }

  if (TwitchX.state.favorites.length === 0) {
    grid.classList.add('hidden');
    TwitchX.renderEmptyState(empty, {
      illustration: 'empty-favorites',
      title: 'No favorites yet',
      subtitle: 'Add channels using the search bar in the sidebar.',
      primaryAction: { label: 'Focus Search', callback: function() { document.getElementById('search-input').focus(); } },
    });
    return;
  }

  if (streams.length === 0 && TwitchX.state.favorites.length > 0) {
    grid.classList.add('hidden');
    TwitchX.renderEmptyState(empty, {
      illustration: 'empty-live',
      title: 'All quiet right now',
      subtitle: 'None of your favorites are live. Refresh or browse live categories.',
      primaryAction: { label: 'Refresh', callback: function() { if (TwitchX.api) TwitchX.api.refresh(); } },
      secondaryAction: { label: 'Browse', callback: function() { TwitchX.showBrowseView(); } },
    });
    return;
  }

  TwitchX.hideEmptyState(empty);
  grid.classList.add('view-active');
  grid.classList.remove('hidden');

  // Diff-based update
  const existingLogins = new Set();
  grid.querySelectorAll('.stream-card').forEach(function(c) { existingLogins.add(c.dataset.key); });
  const newLogins = new Set(streams.map(function(s) { return TwitchX.channelKey(s.login, s.platform || 'twitch'); }));

  let setsEqual = existingLogins.size === newLogins.size;
  if (setsEqual) {
    existingLogins.forEach(function(l) { if (!newLogins.has(l)) setsEqual = false; });
  }

  if (setsEqual && existingLogins.size > 0) {
    // In-place update
    streams.forEach(function(s) {
      const streamKey = TwitchX.channelKey(s.login, s.platform || 'twitch');
      const card = grid.querySelector('.stream-card[data-key="' + streamKey + '"]');
      if (!card) return;
      card.querySelector('.card-viewers').textContent = TwitchX.formatViewers(s.viewers);
      const trend = card.querySelector('.trend');
      if (s.viewer_trend === 'up') {
        TwitchX.setIconOnly(trend, 'trend-up', 14); trend.className = 'trend up';
      } else if (s.viewer_trend === 'down') {
        TwitchX.setIconOnly(trend, 'trend-down', 14); trend.className = 'trend down';
      } else {
        trend.textContent = ''; trend.className = 'trend';
      }
      card.querySelector('.card-title').textContent = s.title;
      card.querySelector('.card-title').title = s.title;
      card.querySelector('.card-game').textContent = TwitchX.truncate(s.game, 28);
      card.querySelector('.uptime-badge').textContent = TwitchX.formatUptime(s.started_at);
      const wb = card.querySelector('.watching-badge');
      wb.classList.toggle('visible', TwitchX.state.watchingChannelKey === streamKey);
      card.classList.toggle('selected', TwitchX.state.selectedChannelKey === streamKey);
      card.setAttribute('aria-pressed', String(TwitchX.state.selectedChannelKey === streamKey));
      card.setAttribute('aria-label', getStreamCardLabel(s));
      _syncPinBadge(card, s);
    });
    // Reorder cards to match sort
    streams.forEach(function(s) {
      const card = grid.querySelector('.stream-card[data-key="' + TwitchX.channelKey(s.login, s.platform || 'twitch') + '"]');
      if (card) grid.appendChild(card);
    });
  } else {
    const frag = document.createDocumentFragment();
    streams.forEach(function(s) {
      frag.appendChild(createStreamCard(s));
    });
    grid.replaceChildren(frag);
    // Request missing thumbnails
    streams.forEach(function(s) {
      const streamKey = TwitchX.channelKey(s.login, s.platform || 'twitch');
      if (!TwitchX.state.thumbnails[streamKey] && s.thumbnail_url) {
        TwitchX.api.get_thumbnail(streamKey, s.thumbnail_url);
      }
    });
  }
}

function createStreamCard(s) {
  const streamKey = TwitchX.channelKey(s.login, s.platform || 'twitch');
  const card = document.createElement('div');
  card.className = 'stream-card card-enter' + (TwitchX.state.selectedChannelKey === streamKey ? ' selected' : '');
  card.dataset.login = s.login;
  card.dataset.key = streamKey;
  card.dataset.started = s.started_at;
  card.dataset.platform = s.platform || 'twitch';
  card.tabIndex = 0;
  card.setAttribute('role', 'button');
  card.setAttribute('aria-pressed', String(TwitchX.state.selectedChannelKey === streamKey));
  card.setAttribute('aria-label', getStreamCardLabel(s));
  card.addEventListener('animationend', function() { card.classList.remove('card-enter'); }, { once: true });
  if (TwitchX.state.gridMode) card.classList.add(TwitchX.state.gridMode + '-mode');

  // Thumb area
  const thumb = document.createElement('div');
  thumb.className = 'card-thumb';

  const img = document.createElement('img');
  img.className = 'thumb-img' + (TwitchX.state.thumbnails[streamKey] ? ' loaded' : '');
  // No src until the thumbnail arrives — an empty src fires onerror in WebKit,
  // which would permanently hide both the image and the shimmer placeholder.
  if (TwitchX.state.thumbnails[streamKey]) img.src = TwitchX.state.thumbnails[streamKey];
  img.alt = '';
  img.loading = 'lazy';
  img.decoding = 'async';
  img.onerror = function() {
    img.classList.add('hidden');
    shimmer.classList.add('hidden');
  };
  thumb.appendChild(img);

  const shimmer = document.createElement('div');
  shimmer.className = 'thumb-shimmer';
  thumb.appendChild(shimmer);

  const overlay = document.createElement('div');
  overlay.className = 'card-overlay';

  const liveBadge = document.createElement('span');
  liveBadge.className = 'live-badge';
  liveBadge.textContent = 'LIVE';
  overlay.appendChild(liveBadge);

  const platformBadge = document.createElement('span');
  platformBadge.className = 'platform-badge ' + (s.platform || 'twitch');
  platformBadge.textContent = s.platform === 'kick' ? 'K' : s.platform === 'youtube' ? 'YT' : 'T';
  overlay.appendChild(platformBadge);

  const watchBadge = document.createElement('span');
  watchBadge.className = 'watching-badge' + (TwitchX.state.watchingChannelKey === streamKey ? ' visible' : '');
  TwitchX.setIconText(watchBadge, 'play', 10, 'WATCHING');
  thumb.appendChild(watchBadge);

  const uptime = document.createElement('span');
  uptime.className = 'uptime-badge';
  uptime.textContent = TwitchX.formatUptime(s.started_at);
  overlay.appendChild(uptime);
  thumb.appendChild(overlay);

  if (TwitchX.isPinned(s.platform || 'twitch', s.login)) {
    var pinBadge = document.createElement('span');
    pinBadge.className = 'pin-badge';
    TwitchX.setIconOnly(pinBadge, 'pin', 12);
    pinBadge.title = 'Pinned';
    thumb.appendChild(pinBadge);
  }

  card.appendChild(thumb);

  // Info area
  const info = document.createElement('div');
  info.className = 'card-body card-info';

  const titleRow = document.createElement('div');
  titleRow.className = 'card-title-row';

  const avatar = document.createElement('img');
  avatar.className = 'card-avatar';
  avatar.alt = '';
  avatar.loading = 'lazy';
  avatar.decoding = 'async';
  // Same rule as the thumbnail above: never assign an empty src — WebKit
  // treats it as a failed load and paints its broken-image glyph.
  var avatarUrl = TwitchX.state.avatars[streamKey];
  if (avatarUrl) avatar.src = avatarUrl;
  avatar.classList.toggle('is-empty', !avatarUrl);
  titleRow.appendChild(avatar);

  const channelName = document.createElement('span');
  channelName.className = 'card-channel';
  channelName.textContent = s.display_name;
  titleRow.appendChild(channelName);

  const viewers = document.createElement('span');
  viewers.className = 'card-viewers viewers';
  viewers.textContent = TwitchX.formatViewers(s.viewers);
  titleRow.appendChild(viewers);

  const trend = document.createElement('span');
  trend.className = 'trend' + (s.viewer_trend === 'up' ? ' up' : s.viewer_trend === 'down' ? ' down' : '');
  if (s.viewer_trend === 'up') {
    TwitchX.setIconOnly(trend, 'trend-up', 14);
  } else if (s.viewer_trend === 'down') {
    TwitchX.setIconOnly(trend, 'trend-down', 14);
  }
  titleRow.appendChild(trend);
  info.appendChild(titleRow);

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
  card.addEventListener('click', function() { TwitchX.selectChannel(s.login, s.platform || 'twitch'); });
  card.addEventListener('dblclick', function() { TwitchX.selectChannel(s.login, s.platform || 'twitch'); TwitchX.doWatch(); });
  card.addEventListener('contextmenu', function(e) { TwitchX.showContextMenu(e, s.login, s.platform || 'twitch'); });
  card.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      TwitchX.selectChannel(s.login, s.platform || 'twitch');
    }
  });

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
  TwitchX.hideEmptyState(empty);
  grid.classList.add('view-active');
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

var EMPTY_STATE_ICONS = {
  'empty-favorites': 'star',
  'empty-live': 'sleeping',
  'empty-browse': 'search',
  'empty-channel': 'user',
  'empty-vods': 'play',
  'empty-clips': 'film',
};

function renderEmptyState(target, opts) {
  if (!target) return;
  var config = opts || {};
  target.replaceChildren();
  target.classList.remove('hidden');
  target.classList.add('empty-state', 'view-active', 'visible');

  var art = document.createElement('div');
  art.className = 'empty-illustration ' + (config.illustration || 'empty-generic');
  TwitchX.setIconOnly(art, EMPTY_STATE_ICONS[config.illustration] || 'info', 36);
  target.appendChild(art);

  var title = document.createElement('div');
  title.className = 'empty-title';
  title.textContent = config.title || 'Nothing here yet';
  target.appendChild(title);

  if (config.subtitle) {
    var subtitle = document.createElement('div');
    subtitle.className = 'empty-subtitle';
    subtitle.textContent = config.subtitle;
    target.appendChild(subtitle);
  }

  var actions = document.createElement('div');
  actions.className = 'empty-actions';
  [config.primaryAction, config.secondaryAction].forEach(function(action, idx) {
    if (!action || !action.label || !action.callback) return;
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = idx === 0 ? 'empty-action primary' : 'empty-action secondary';
    btn.textContent = action.label;
    btn.addEventListener('click', action.callback);
    actions.appendChild(btn);
  });
  if (actions.children.length) target.appendChild(actions);
}

function hideEmptyState(target) {
  if (!target) return;
  target.classList.remove('view-active', 'visible');
  target.classList.add('hidden');
}

TwitchX.renderEmptyState = renderEmptyState;
TwitchX.hideEmptyState = hideEmptyState;
