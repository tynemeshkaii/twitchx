window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

function showBrowseView() {
  TwitchX.setChromeVisible(false);
  TwitchX.switchView('browse-view', 'forward');
  TwitchX.state.browseMode = 'categories';
  TwitchX.state.browseCategory = null;
  TwitchX.state.browsePlatformFilter = 'all';
  document.querySelectorAll('.browse-platform-tab').forEach(function(t) {
    var active = t.dataset.platform === 'all';
    t.classList.toggle('active', active);
    t.setAttribute('aria-selected', String(active));
    t.tabIndex = active ? 0 : -1;
  });
  document.getElementById('browse-back-btn').classList.add('hidden');
  document.getElementById('browse-categories-grid').classList.remove('hidden');
  document.getElementById('browse-streams-grid').classList.add('hidden');
  loadBrowseCategories();
  renderBrowseBreadcrumbs();
}

function hideBrowseView() {
  if (document.getElementById('player-view').classList.contains('view-active')) return;
  TwitchX.switchView('stream-grid', 'back');
  TwitchX.setChromeVisible(true);
  TwitchX.renderGrid();
}

function browseGoBack() {
  if (TwitchX.state.browseMode === 'streams') {
    TwitchX.state.browseMode = 'categories';
    TwitchX.state.browseCategory = null;
    document.getElementById('browse-back-btn').classList.add('hidden');
  document.getElementById('browse-categories-grid').classList.remove('hidden');
  document.getElementById('browse-streams-grid').classList.add('hidden');
  document.getElementById('browse-loading').classList.add('hidden');
  clearBrowseEmpty();
    renderBrowseBreadcrumbs();
  } else {
    hideBrowseView();
  }
}

function setBrowsePlatform(btn, platform) {
  TwitchX.setActiveTab(Array.from(document.querySelectorAll('.browse-platform-tab')), btn);
  TwitchX.state.browsePlatformFilter = platform;
  if (TwitchX.state.browseMode === 'categories') {
    loadBrowseCategories();
  } else if (TwitchX.state.browseCategory) {
    _triggerBrowseTopStreams(TwitchX.state.browseCategory);
  }
}

function loadBrowseCategories() {
  var grid = document.getElementById('browse-categories-grid');
  grid.replaceChildren();
  for (var i = 0; i < 12; i++) {
    var s = document.createElement('div');
    s.className = 'skeleton skeleton-browse-card';
    grid.appendChild(s);
  }
  document.getElementById('browse-loading').classList.add('hidden');
  clearBrowseEmpty();
  if (TwitchX.api) TwitchX.api.get_browse_categories(TwitchX.state.browsePlatformFilter);
}

function setBrowseEmpty(message, detail, kind) {
  var emptyEl = document.getElementById('browse-empty');
  if (!emptyEl) return;
  emptyEl.className = 'browse-empty' + (kind ? ' ' + kind : '');
  TwitchX.renderEmptyState(emptyEl, {
    illustration: 'empty-browse',
    title: message || 'No results found.',
    subtitle: detail || 'Try a different platform filter or search again.',
    primaryAction: { label: 'Refresh Browse', callback: function() { loadBrowseCategories(); } },
  });
}

function clearBrowseEmpty() {
  var emptyEl = document.getElementById('browse-empty');
  if (!emptyEl) return;
  emptyEl.className = 'browse-empty hidden';
  emptyEl.textContent = '';
}

function browseErrorSummary(errors) {
  if (!errors) return '';
  var parts = [];
  Object.keys(errors).forEach(function(platform) {
    if (errors[platform]) {
      parts.push(TwitchX.platformLabel(platform) + ': ' + errors[platform]);
    }
  });
  return parts.join(' ');
}

function browseStreamRestriction(stream) {
  var platform = stream.platform || 'twitch';
  if (platform === 'youtube') {
    return {
      canWatch: false,
      reason: 'YouTube live search results cannot be opened directly here. View the channel for details, or open it in the browser.',
    };
  }
  if (stream.is_live === false) {
    return { canWatch: false, reason: 'This channel is offline.' };
  }
  return { canWatch: true, reason: '' };
}

function createPlatformBadge(platform, label) {
  var badge = document.createElement('span');
  badge.className = 'platform-badge ' + (platform || 'twitch');
  badge.textContent = label || TwitchX.platformLabel(platform || 'twitch');
  return badge;
}

function createImageFallback(label, className) {
  var fallback = document.createElement('div');
  fallback.className = className || 'image-fallback';
  fallback.textContent = (label || '?').trim().charAt(0).toUpperCase() || '?';
  fallback.setAttribute('aria-hidden', 'true');
  return fallback;
}

function _triggerBrowseTopStreams(category) {
  if (!category || !category.name) return;
  TwitchX.state.browseMode = 'streams';
  TwitchX.state.browseCategory = category;
  document.getElementById('browse-back-btn').classList.remove('hidden');
  document.getElementById('browse-categories-grid').classList.add('hidden');
  document.getElementById('browse-streams-grid').replaceChildren();
  for (var si = 0; si < 8; si++) {
    var s = document.createElement('div');
    s.className = 'skeleton skeleton-stream-card';
    document.getElementById('browse-streams-grid').appendChild(s);
  }
  document.getElementById('browse-streams-grid').classList.remove('hidden');
  document.getElementById('browse-loading').classList.add('hidden');
  clearBrowseEmpty();
  if (TwitchX.api) {
    TwitchX.api.get_browse_top_streams(
      category.name,
      category.platform_ids,
      TwitchX.state.browsePlatformFilter
    );
  }
  renderBrowseBreadcrumbs();
}

function renderBrowseBreadcrumbs() {
  const nav = document.getElementById('browse-breadcrumbs');
  if (!nav) return;

  if (!nav._breadcrumbHandler) {
    nav.addEventListener('click', function(e) {
      const link = e.target.closest('.breadcrumb-link');
      if (!link) return;
      var action = link.getAttribute('data-action');
      if (action === 'following') hideBrowseView();
      else if (action === 'browse') browseGoBack();
    });
    nav._breadcrumbHandler = true;
  }

  nav.replaceChildren();

  var followingLink = document.createElement('button');
  followingLink.className = 'breadcrumb-link';
  followingLink.setAttribute('data-action', 'following');
  followingLink.setAttribute('aria-label', 'Go back to Following');
  followingLink.textContent = 'Following';
  nav.appendChild(followingLink);

  var sep1 = document.createElement('span');
  sep1.className = 'breadcrumb-separator';
  sep1.textContent = '>';
  nav.appendChild(sep1);

  if (TwitchX.state.browseMode === 'streams' && TwitchX.state.browseCategory && TwitchX.state.browseCategory.name) {
    var browseLink = document.createElement('button');
    browseLink.className = 'breadcrumb-link';
    browseLink.setAttribute('data-action', 'browse');
    browseLink.setAttribute('aria-label', 'Go back to Browse categories');
    browseLink.textContent = 'Browse';
    nav.appendChild(browseLink);

    var sep2 = document.createElement('span');
    sep2.className = 'breadcrumb-separator';
    sep2.textContent = '>';
    nav.appendChild(sep2);

    var current = document.createElement('span');
    current.className = 'breadcrumb-current';
    current.textContent = TwitchX.state.browseCategory.name;
    nav.appendChild(current);
  } else {
    var current = document.createElement('span');
    current.className = 'breadcrumb-current';
    current.textContent = 'Browse';
    nav.appendChild(current);
  }
}

TwitchX.showBrowseView = showBrowseView;
TwitchX.hideBrowseView = hideBrowseView;
TwitchX.browseGoBack = browseGoBack;
TwitchX.setBrowsePlatform = setBrowsePlatform;
TwitchX.loadBrowseCategories = loadBrowseCategories;
TwitchX.setBrowseEmpty = setBrowseEmpty;
TwitchX.clearBrowseEmpty = clearBrowseEmpty;
TwitchX.browseErrorSummary = browseErrorSummary;
TwitchX.browseStreamRestriction = browseStreamRestriction;
TwitchX.createPlatformBadge = createPlatformBadge;
TwitchX.createImageFallback = createImageFallback;
TwitchX._triggerBrowseTopStreams = _triggerBrowseTopStreams;
TwitchX.renderBrowseBreadcrumbs = renderBrowseBreadcrumbs;
