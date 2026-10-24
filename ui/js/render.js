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
  const corner = card.querySelector('.card-corner') || card;
  const existing = card.querySelector('.pin-badge');
  const pinned = TwitchX.isPinned(s.platform || 'twitch', s.login);
  if (pinned && !existing) {
    corner.insertBefore(_createPinBadge(), corner.firstChild);
  } else if (!pinned && existing) {
    existing.remove();
  }
}

function _createPinBadge() {
  const pinBadge = document.createElement('span');
  pinBadge.className = 'pin-badge';
  TwitchX.setIconOnly(pinBadge, 'pin', 10);
  pinBadge.title = 'Pinned';
  return pinBadge;
}

function _setTrend(trend, direction) {
  if (direction === 'up') {
    TwitchX.setIconOnly(trend, 'trend-up', 10); trend.className = 'trend up';
  } else if (direction === 'down') {
    TwitchX.setIconOnly(trend, 'trend-down', 10); trend.className = 'trend down';
  } else {
    trend.replaceChildren(); trend.className = 'trend';
  }
}

let gridCardsEntered = false;

// Staggered entrance: 15ms per card via --i (see stream-card.css), capped so
// the last card never waits more than 8 steps.
TwitchX.markCardEnter = function(card, index) {
  card.classList.add('card-enter');
  card.style.setProperty('--i', String(Math.min(index, 7)));
  card.addEventListener('animationend', function(e) {
    if (e.target === card) card.classList.remove('card-enter');
  });
};

function renderGrid() {
  // Skip rendering when player view is active — grid is hidden
  if (document.getElementById('player-view').classList.contains('view-active')) return;
  // Skip rendering when browse view is open — avoids restoring grid inline style
  if (document.getElementById('browse-view') &&
      document.getElementById('browse-view').classList.contains('view-active')) return;
  // Skip rendering when multistream view is open — same inline-style conflict
  if (TwitchX.multiState.open) return;

  const grid = document.getElementById('stream-grid');
  grid.classList.remove('grid-mode', 'list-mode');
  grid.classList.add('view', 'view-active');
  if (TwitchX.state.gridMode) grid.classList.add(TwitchX.state.gridMode + '-mode');
  grid.querySelectorAll('.stream-card').forEach(function(card) {
    card.classList.remove('grid-mode', 'list-mode');
    if (TwitchX.state.gridMode) card.classList.add(TwitchX.state.gridMode + '-mode');
  });
  const empty = document.getElementById('empty-state');
  const streams = getFilteredSortedStreams();

  // Empty states
  var anyLoggedIn = TwitchX.state.currentUser || TwitchX.state.kickUser || TwitchX.state.youtubeUser;
  // Without favorites there is nothing to sort or count: keep only the title.
  var noFavorites = TwitchX.state.favorites.length === 0;
  var sectionActions = document.querySelector('#section-header .section-actions');
  if (sectionActions) sectionActions.classList.toggle('hidden', noFavorites);
  var liveCount = document.getElementById('section-live-count');
  if (liveCount) liveCount.classList.toggle('hidden', noFavorites);
  if (TwitchX.state.favorites.length === 0 && !anyLoggedIn) {
    grid.classList.add('hidden');
    // No brand colours here: one neutral Connect opens the account popover,
    // where each platform has its own sign-in.
    TwitchX.renderEmptyState(empty, {
      illustration: 'empty-favorites',
      title: 'Welcome to TwitchX',
      subtitle: 'Connect Twitch, Kick or YouTube to see the channels you follow, or add channels with \u2318K.',
      primaryAction: { label: 'Connect account', callback: function() { if (TwitchX.openAccountPopover) TwitchX.openAccountPopover(); } },
      secondaryAction: { label: 'Browse live channels', callback: function() { TwitchX.navigateTo('browse'); } },
    });

    return;
  }

  if (TwitchX.state.favorites.length === 0) {
    grid.classList.add('hidden');
    TwitchX.renderEmptyState(empty, {
      illustration: 'empty-favorites',
      title: 'No favorites yet',
      subtitle: 'Search for channels and add them to your favorites.',
      primaryAction: { label: 'Add channel', callback: function() { TwitchX.openPalette('add'); } },
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
      card.querySelectorAll('.card-viewers').forEach(function(el) { el.textContent = TwitchX.formatViewers(s.viewers); });
      _setTrend(card.querySelector('.trend'), s.viewer_trend);
      card.querySelector('.card-title').textContent = s.title;
      card.querySelector('.card-title').title = s.title;
      card.querySelector('.card-game').textContent = s.game || '';
      card.querySelectorAll('.card-uptime').forEach(function(el) { el.textContent = TwitchX.formatUptimeClock(s.started_at); });
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
    // Cards rise in only on the first fill; later rebuilds swap in place.
    const stagger = !gridCardsEntered;
    gridCardsEntered = true;
    const frag = document.createDocumentFragment();
    streams.forEach(function(s, i) {
      frag.appendChild(createStreamCard(s, stagger ? i : undefined));
    });
    grid.replaceChildren(frag);
    // Request missing thumbnails
    streams.forEach(function(s) {
      const streamKey = TwitchX.channelKey(s.login, s.platform || 'twitch');
      if (s.thumbnail_url && TwitchX.thumbnailNeedsFetch(streamKey)) {
        TwitchX.api.get_thumbnail(streamKey, s.thumbnail_url);
      }
    });
  }
}

// One card for every stream-like item: the Following grid, Browse top streams
// and the channel's VODs/clips. The caller sets data-* and events.
//   o.thumb / o.avatar   image URLs (null → shimmer / empty disc)
//   o.viewers, o.trend   number + 'up'|'down' → the chip bottom-left
//   o.corner             uptime or duration → bottom-right
//   o.pinned, o.watching chips top-right
//   o.enterIndex         position for the first-load stagger (omit → no entrance)
function buildMediaCard(o) {
  const card = document.createElement('div');
  card.className = 'stream-card';
  card.tabIndex = 0;
  card.setAttribute('role', 'button');
  if (o.label) card.setAttribute('aria-label', o.label);
  if (typeof o.enterIndex === 'number') TwitchX.markCardEnter(card, o.enterIndex);

  const thumb = document.createElement('div');
  thumb.className = 'card-thumb';

  const img = document.createElement('img');
  img.className = 'thumb-img' + (o.thumb ? ' loaded' : '');
  // No src until the thumbnail arrives — an empty src fires onerror in WebKit,
  // which would permanently hide both the image and the shimmer placeholder.
  if (o.thumb) img.src = o.thumb;
  img.alt = '';
  img.loading = 'lazy';
  img.decoding = 'async';
  thumb.appendChild(img);

  const shimmer = document.createElement('div');
  shimmer.className = 'thumb-shimmer';
  thumb.appendChild(shimmer);
  img.onerror = function() {
    img.classList.add('hidden');
    img.classList.remove('loaded');
    if (o.fallbackLabel) {
      shimmer.replaceWith(TwitchX.createImageFallback(o.fallbackLabel, 'card-thumb-fallback'));
    } else {
      shimmer.classList.add('hidden');
    }
  };

  const platform = document.createElement('span');
  platform.className = 'card-platform platform-glyph';
  platform.title = TwitchX.platformLabel(o.platform || 'twitch');
  const dot = document.createElement('span');
  dot.className = 'platform-dot ' + (o.platform || 'twitch');
  platform.appendChild(dot);
  thumb.appendChild(platform);

  const corner = document.createElement('div');
  corner.className = 'card-corner';
  if (o.pinned) corner.appendChild(_createPinBadge());
  const watchBadge = document.createElement('span');
  watchBadge.className = 'watching-badge' + (o.watching ? ' visible' : '');
  watchBadge.textContent = 'Watching';
  corner.appendChild(watchBadge);
  thumb.appendChild(corner);

  if (o.viewers !== undefined && o.viewers !== null) {
    const chip = document.createElement('span');
    chip.className = 'card-viewers-overlay';
    const liveDot = document.createElement('span');
    liveDot.className = 'card-live-dot';
    chip.appendChild(liveDot);
    const viewers = document.createElement('span');
    viewers.className = 'card-viewers';
    viewers.textContent = TwitchX.formatViewers(o.viewers);
    chip.appendChild(viewers);
    const trend = document.createElement('span');
    _setTrend(trend, o.trend);
    chip.appendChild(trend);
    thumb.appendChild(chip);
  }

  const uptime = document.createElement('span');
  uptime.className = 'uptime-badge card-uptime';
  uptime.textContent = o.corner || '';
  thumb.appendChild(uptime);

  const play = document.createElement('span');
  play.className = 'card-play';
  play.setAttribute('aria-hidden', 'true');
  TwitchX.setIconOnly(play, 'play', 18);
  thumb.appendChild(play);

  card.appendChild(thumb);

  const meta = document.createElement('div');
  meta.className = 'card-meta';

  if (o.showAvatar !== false) {
    const avatar = document.createElement('img');
    avatar.className = 'card-avatar';
    avatar.alt = '';
    avatar.loading = 'lazy';
    avatar.decoding = 'async';
    // Same rule as the thumbnail above: never assign an empty src — WebKit
    // treats it as a failed load and paints its broken-image glyph.
    if (o.avatar) avatar.src = o.avatar;
    avatar.classList.toggle('is-empty', !o.avatar);
    meta.appendChild(avatar);
  }

  const text = document.createElement('div');
  text.className = 'card-text';

  const title = document.createElement('div');
  title.className = 'card-title';
  title.textContent = o.title || '';
  title.title = o.title || '';
  text.appendChild(title);

  const sub = document.createElement('div');
  sub.className = 'card-sub';
  const channelName = document.createElement('span');
  channelName.className = 'card-channel';
  channelName.textContent = o.channel || '';
  sub.appendChild(channelName);
  const game = document.createElement('span');
  game.className = 'card-game';
  game.textContent = o.game || '';
  sub.appendChild(game);
  text.appendChild(sub);

  meta.appendChild(text);

  // List mode shows viewers and uptime at the row's end instead of on the
  // (tiny) frame; grid mode hides this.
  const aside = document.createElement('div');
  aside.className = 'card-aside';
  if (o.viewers !== undefined && o.viewers !== null) {
    const asideViewers = document.createElement('span');
    asideViewers.className = 'card-aside-viewers card-viewers';
    asideViewers.textContent = TwitchX.formatViewers(o.viewers);
    aside.appendChild(asideViewers);
  }
  const asideUptime = document.createElement('span');
  asideUptime.className = 'card-aside-uptime card-uptime';
  asideUptime.textContent = o.corner || '';
  aside.appendChild(asideUptime);
  meta.appendChild(aside);

  card.appendChild(meta);
  return card;
}

function createStreamCard(s, enterIndex) {
  const platform = s.platform || 'twitch';
  const streamKey = TwitchX.channelKey(s.login, platform);
  const card = buildMediaCard({
    platform: platform,
    thumb: TwitchX.state.thumbnails[streamKey],
    avatar: TwitchX.state.avatars[streamKey],
    title: s.title,
    channel: s.display_name,
    game: s.game,
    viewers: s.viewers,
    trend: s.viewer_trend,
    corner: TwitchX.formatUptimeClock(s.started_at),
    pinned: TwitchX.isPinned(platform, s.login),
    watching: TwitchX.state.watchingChannelKey === streamKey,
    label: getStreamCardLabel(s),
    enterIndex: enterIndex,
  });
  if (TwitchX.state.selectedChannelKey === streamKey) card.classList.add('selected');
  card.dataset.login = s.login;
  card.dataset.key = streamKey;
  card.dataset.started = s.started_at;
  card.dataset.platform = platform;
  card.setAttribute('aria-pressed', String(TwitchX.state.selectedChannelKey === streamKey));
  if (TwitchX.state.gridMode) card.classList.add(TwitchX.state.gridMode + '-mode');

  // One click starts the stream. The selection stays: the keyboard shortcuts
  // (watch, next/previous stream) work from it.
  card.addEventListener('click', function() { TwitchX.selectChannel(s.login, platform); TwitchX.doWatch(); });
  card.addEventListener('contextmenu', function(e) { TwitchX.showContextMenu(e, s.login, platform); });
  card.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      TwitchX.selectChannel(s.login, platform);
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

// The game filter is picked in the palette and cleared from the chip in the
// section header; state.filterText stays the single source for the grid.
function syncGameFilterChip() {
  var chip = document.getElementById('game-filter-chip');
  var label = document.getElementById('game-filter-label');
  if (!chip) return;
  var text = TwitchX.state.filterText || '';
  chip.classList.toggle('hidden', !text);
  if (label) label.textContent = 'Game: ' + text;
  chip.setAttribute('aria-label', 'Clear game filter ' + text);
}

function setGameFilter(game) {
  TwitchX.state.filterText = game || '';
  syncGameFilterChip();
  if (TwitchX.showFollowingView) TwitchX.showFollowingView();
  renderGrid();
}

TwitchX.getFilteredSortedStreams = getFilteredSortedStreams;
TwitchX.setGameFilter = setGameFilter;
TwitchX.syncGameFilterChip = syncGameFilterChip;
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
TwitchX.buildMediaCard = buildMediaCard;
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
  art.setAttribute('aria-hidden', 'true');
  TwitchX.setIconOnly(art, EMPTY_STATE_ICONS[config.illustration] || 'info', 40);
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
    // At most two: the first is primary, the second secondary.
    btn.className = 'btn ' + (idx === 0 ? 'btn-primary' : 'btn-secondary');
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
