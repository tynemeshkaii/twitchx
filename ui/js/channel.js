window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

function selectChannel(login, platform) {
  const resolvedPlatform = platform || TwitchX.getChannelPlatform(login);
  const key = TwitchX.channelKey(login, resolvedPlatform);
  TwitchX.state.selectedChannel = login;
  TwitchX.state.selectedPlatform = resolvedPlatform;
  TwitchX.state.selectedChannelKey = key;
  if (TwitchX.expandSidebarSectionForLogin(login, key)) {
    TwitchX.renderSidebar();
  }
  TwitchX.acknowledgeNotifBadge(key);
  document.querySelectorAll('.stream-card').forEach(function(c) {
    c.classList.toggle('selected', c.dataset.key === key);
  });
  document.querySelectorAll('.channel-item').forEach(function(c) {
    const isSelected = c.dataset.key === key;
    c.classList.toggle('selected', isSelected);
    c.setAttribute('aria-pressed', String(isSelected));
  });
  document.querySelectorAll('.rail-avatar').forEach(function(c) {
    const isSelected = c.dataset.key === key;
    c.classList.toggle('selected', isSelected);
    c.setAttribute('aria-pressed', String(isSelected));
  });
  document.getElementById('watch-btn').classList.add('active');
  TwitchX.setStatus('Selected: ' + login + ' on ' + TwitchX.platformLabel(resolvedPlatform), 'info');
}

function addChannel() {
  const input = document.getElementById('search-input');
  const val = input.value.trim();
  if (val && TwitchX.api) {
    const platform = TwitchX.state.activePlatformFilter;
    const inputLower = val.toLowerCase();
    let choice = null;
    if (platform === 'all') {
      if ((inputLower.indexOf('youtube.com/') !== -1 || val.charAt(0) === '@') && TwitchX.state.youtubeEnabled) {
        choice = { login: val, platform: 'youtube' };
      } else if (inputLower.indexOf('kick.com/') !== -1) {
        choice = { login: val, platform: 'kick' };
      } else if (inputLower.indexOf('twitch.tv/') !== -1) {
        choice = { login: val, platform: 'twitch' };
      } else {
        const exactLoginMatches = TwitchX.state.searchResults.filter(function(result) {
          return result.login && result.login.toLowerCase() === inputLower;
        });
        if (exactLoginMatches.length === 1) {
          choice = exactLoginMatches[0];
        } else if (exactLoginMatches.length === 0 && TwitchX.state.searchResults.length > 0) {
          // No exact match: fall back to the top search result only if its display name matches.
          const displayMatch = TwitchX.state.searchResults.find(function(result) {
            return (result.display_name || '').toLowerCase() === inputLower;
          });
          if (displayMatch) choice = displayMatch;
        }
      }
    }
    const targetPlatform = (choice && choice.platform) || (platform === 'all' ? 'twitch' : platform) || 'twitch';
    const loginToAdd = (choice && choice.login) || val;
    const displayToAdd = (choice && choice.display_name) || '';
    TwitchX.api.add_channel(loginToAdd, targetPlatform, displayToAdd);
    input.value = '';
    TwitchX.state.searchResults = [];
    document.getElementById('search-dropdown').classList.remove('visible');
  }
}

function addChannelDirect(login, platform, displayName) {
  if (TwitchX.api) TwitchX.api.add_channel(login, platform || 'twitch', displayName || '');
}

function doWatch() {
  if (!TwitchX.state.selectedChannel || !TwitchX.api) return;
  if (
    TwitchX.state.watchingChannelKey &&
    TwitchX.state.watchingChannelKey === TwitchX.state.selectedChannelKey
  ) {
    TwitchX.setStatus('Already watching ' + TwitchX.state.selectedChannel, 'info');
    return;
  }
  const quality = document.getElementById('quality-select').value;
  const platform = TwitchX.state.selectedPlatform || TwitchX.getChannelPlatform(TwitchX.state.selectedChannel, TwitchX.state.selectedChannelKey);
  if (TwitchX.api.watch_platform) {
    TwitchX.api.watch_platform(TwitchX.state.selectedChannel, platform, quality);
  } else if (platform === 'twitch') {
    TwitchX.api.watch(TwitchX.state.selectedChannel, quality);
  } else {
    TwitchX.api.watch_direct(TwitchX.state.selectedChannel, platform, quality);
  }
}

function resetChannelMediaPanels() {
  ['vods', 'clips'].forEach(function(tab) {
    const loading = document.getElementById('channel-' + tab + '-loading');
    const empty = document.getElementById('channel-' + tab + '-empty');
    const container = document.getElementById(
      tab === 'vods' ? 'channel-vods-list' : 'channel-clips-grid'
    );
    if (loading) loading.classList.add('hidden');
    if (empty) {
      TwitchX.hideEmptyState(empty);
      empty.textContent = '';
    }
    if (container) container.replaceChildren();
    TwitchX.state.channelTabs[tab] = TwitchX.createChannelMediaState();
  });
  TwitchX.state.channelTabs.active = 'live';
}

function getChannelMediaElements(tab) {
  return {
    loading: document.getElementById('channel-' + tab + '-loading'),
    empty: document.getElementById('channel-' + tab + '-empty'),
    container: document.getElementById(
      tab === 'vods' ? 'channel-vods-list' : 'channel-clips-grid'
    ),
  };
}

function playChannelMedia(item) {
  if (!TwitchX.api || !item || !item.url) return;
  if (item.play_supported === false) {
    TwitchX.showToast(item.play_disabled_reason || 'This media cannot be played in app.', 'warn');
    return;
  }
  const quality = document.getElementById('quality-select')
    ? document.getElementById('quality-select').value
    : 'best';
  hideChannelView();
  TwitchX.api.watch_media(
    item.url,
    quality,
    item.platform || (TwitchX.channelProfile && TwitchX.channelProfile.platform) || 'twitch',
    item.channel_login || (TwitchX.channelProfile && TwitchX.channelProfile.login) || '',
    item.title || '',
    false
  );
}

function openChannelMedia(item) {
  if (TwitchX.api && item && item.url) TwitchX.api.open_url(item.url);
}

function openChannelInBrowser() {
  if (!TwitchX.channelProfile || !TwitchX.api) return;
  TwitchX.api.open_browser(TwitchX.channelProfile.login, TwitchX.channelProfile.platform);
}

function createChannelMediaCard(item, tab) {
  const card = document.createElement('div');
  card.className = 'channel-media-card' + (tab === 'clips' ? ' clip' : '');

  const thumbWrap = document.createElement('button');
  thumbWrap.className = 'channel-media-thumb-wrap';
  thumbWrap.type = 'button';
  thumbWrap.disabled = item.play_supported === false;
  thumbWrap.setAttribute('aria-label', 'Play ' + (item.title || (tab === 'clips' ? 'untitled clip' : 'untitled VOD')));
  if (thumbWrap.disabled) {
    thumbWrap.title = item.play_disabled_reason || 'This media cannot be played in app.';
  }
  thumbWrap.onclick = function() { playChannelMedia(item); };

  if (item.thumbnail_url) {
    const thumb = document.createElement('img');
    thumb.className = 'channel-media-thumb';
    thumb.alt = '';
    thumb.src = item.thumbnail_url;
    thumb.loading = 'lazy';
    thumb.decoding = 'async';
    thumb.onerror = function() {
      thumb.remove();
      thumbWrap.appendChild(TwitchX.createImageFallback(item.title || item.channel_login, 'channel-media-thumb-fallback'));
    };
    thumbWrap.appendChild(thumb);
  } else {
    thumbWrap.appendChild(TwitchX.createImageFallback(item.title || item.channel_login, 'channel-media-thumb-fallback'));
  }

  const body = document.createElement('div');
  body.className = 'channel-media-body';

  const title = document.createElement('div');
  title.className = 'channel-media-title';
  title.textContent = item.title || (tab === 'clips' ? 'Untitled clip' : 'Untitled VOD');

  const meta = document.createElement('div');
  meta.className = 'channel-media-meta';
  meta.textContent = TwitchX.buildChannelMediaMeta(item, tab);

  const platformRow = document.createElement('div');
  platformRow.className = 'channel-media-platform-row';
  platformRow.appendChild(TwitchX.createPlatformBadge(item.platform || (TwitchX.channelProfile && TwitchX.channelProfile.platform) || 'twitch'));

  const actions = document.createElement('div');
  actions.className = 'channel-media-actions';

  const playBtn = document.createElement('button');
  playBtn.className = 'channel-media-btn';
  playBtn.type = 'button';
  playBtn.textContent = 'Play';
  playBtn.disabled = item.play_supported === false;
  if (playBtn.disabled) {
    playBtn.title = item.play_disabled_reason || 'This media cannot be played in app.';
  }
  playBtn.onclick = function() { playChannelMedia(item); };

  const openBtn = document.createElement('button');
  openBtn.className = 'channel-media-btn secondary';
  openBtn.type = 'button';
  openBtn.textContent = 'Open';
  openBtn.onclick = function() { openChannelMedia(item); };

  actions.appendChild(playBtn);
  actions.appendChild(openBtn);
  body.appendChild(title);
  body.appendChild(platformRow);
  body.appendChild(meta);
  body.appendChild(actions);
  card.appendChild(thumbWrap);
  card.appendChild(body);
  return card;
}

// P2-18: a live channel showed an empty panel — the empty state was hidden and
// nothing replaced it. Render a real card for the live stream instead.
function renderChannelLivePanel(profile) {
  const panel = document.getElementById('channel-tab-live');
  const empty = document.getElementById('channel-live-empty');
  if (!panel) return;

  const existing = document.getElementById('channel-live-card');
  if (existing) existing.remove();

  if (!profile || !profile.is_live || !profile.watch_supported) return;
  TwitchX.hideEmptyState(empty);

  const platform = profile.platform || 'twitch';
  const stream = TwitchX.findStreamForChannel(profile.login, platform);
  const key = TwitchX.channelKey(profile.login, platform);
  const label = profile.display_name || profile.login;

  const card = document.createElement('div');
  card.id = 'channel-live-card';
  card.className = 'channel-media-card';

  const thumbWrap = document.createElement('button');
  thumbWrap.className = 'channel-media-thumb-wrap';
  thumbWrap.type = 'button';
  thumbWrap.setAttribute('aria-label', 'Watch ' + label + ' now');
  thumbWrap.addEventListener('click', watchChannelStream);

  const thumbUrl = TwitchX.state.thumbnails[key] || (stream && stream.thumbnail_url);
  if (thumbUrl) {
    const thumb = document.createElement('img');
    thumb.className = 'channel-media-thumb';
    thumb.alt = '';
    thumb.loading = 'lazy';
    thumb.decoding = 'async';
    thumb.onerror = function() {
      thumb.remove();
      thumbWrap.appendChild(TwitchX.createImageFallback(label, 'channel-media-thumb-fallback'));
    };
    thumb.src = thumbUrl;
    thumbWrap.appendChild(thumb);
  } else {
    thumbWrap.appendChild(TwitchX.createImageFallback(label, 'channel-media-thumb-fallback'));
  }

  const body = document.createElement('div');
  body.className = 'channel-media-body';

  const title = document.createElement('div');
  title.className = 'channel-media-title';
  title.textContent = (stream && stream.title) || label + ' is live';
  body.appendChild(title);

  const platformRow = document.createElement('div');
  platformRow.className = 'channel-media-platform-row';
  platformRow.appendChild(TwitchX.createPlatformBadge(platform));
  body.appendChild(platformRow);

  const meta = document.createElement('div');
  meta.className = 'channel-media-meta';
  const parts = [];
  if (stream && stream.game) parts.push(stream.game);
  if (stream && typeof stream.viewers === 'number') {
    parts.push(TwitchX.formatViewers(stream.viewers) + ' viewers');
  }
  if (stream && stream.started_at) parts.push(TwitchX.formatUptime(stream.started_at));
  meta.textContent = parts.length ? parts.join(' \u00b7 ') : 'Live now';
  body.appendChild(meta);

  const actions = document.createElement('div');
  actions.className = 'channel-media-actions';
  const watchBtn = document.createElement('button');
  watchBtn.className = 'channel-media-btn';
  watchBtn.type = 'button';
  watchBtn.textContent = 'Watch Now';
  watchBtn.addEventListener('click', watchChannelStream);
  actions.appendChild(watchBtn);

  const openBtn = document.createElement('button');
  openBtn.className = 'channel-media-btn secondary';
  openBtn.type = 'button';
  openBtn.textContent = 'Open';
  openBtn.addEventListener('click', openChannelInBrowser);
  actions.appendChild(openBtn);
  body.appendChild(actions);

  card.appendChild(thumbWrap);
  card.appendChild(body);
  panel.appendChild(card);
}

function renderChannelMediaTab(tab) {
  const entry = TwitchX.state.channelTabs[tab];
  const els = getChannelMediaElements(tab);
  if (!entry || !els.loading || !els.empty || !els.container) return;

  els.loading.classList.toggle('hidden', entry.status !== 'loading');
  els.container.replaceChildren();

  if (entry.status !== 'ready') {
    TwitchX.hideEmptyState(els.empty);
    return;
  }

  if (!entry.supported || entry.error || !entry.items.length) {
    TwitchX.renderEmptyState(els.empty, {
      illustration: tab === 'vods' ? 'empty-vods' : 'empty-clips',
      title: tab === 'vods' ? 'No recent VODs' : 'No recent clips',
      subtitle: entry.message || (
        tab === 'vods' ? 'This channel has no recent VODs available.' : 'This channel has no recent clips available.'
      ),
      secondaryAction: { label: 'Open Channel', callback: openChannelInBrowser },
    });
    return;
  }

  TwitchX.hideEmptyState(els.empty);
  entry.items.forEach(function(item) {
    els.container.appendChild(createChannelMediaCard(item, tab));
  });
}

function ensureChannelTabLoaded(tab) {
  if (tab === 'live' || !TwitchX.channelProfile || !TwitchX.api) return;
  const entry = TwitchX.state.channelTabs[tab];
  if (!entry || entry.status === 'loading' || entry.status === 'ready') {
    renderChannelMediaTab(tab);
    return;
  }
  entry.status = 'loading';
  renderChannelMediaTab(tab);
  TwitchX.api.get_channel_media(TwitchX.channelProfile.login, TwitchX.channelProfile.platform, tab);
}

function showChannelView(login, platform, source) {
  TwitchX.channelViewSource = source || 'grid';
  TwitchX.channelProfile = null;
  resetChannelMediaPanels();
  var channelBody = document.getElementById('channel-body');
  if (channelBody) channelBody.scrollTop = 0;

  if (TwitchX.channelViewSource !== 'browse') {
    TwitchX.setChromeVisible(false);
  }
  TwitchX.switchView('channel-view', 'forward');
  document.getElementById('channel-loading').classList.remove('hidden');
  document.getElementById('channel-profile-card').classList.add('fade-transparent');
  document.getElementById('channel-header-title').textContent = login;
  document.getElementById('channel-display-name').textContent = '';
  document.getElementById('channel-login-text').textContent = '';
  document.getElementById('channel-platform-badge').textContent = '';
  document.getElementById('channel-platform-badge').className = 'platform-badge hidden';
  document.getElementById('channel-platform-note').textContent = '';
  document.getElementById('channel-platform-note').classList.add('hidden');
  document.getElementById('channel-followers').textContent = '';
  document.getElementById('channel-bio').textContent = '';
  document.getElementById('channel-avatar').classList.add('hidden');
  document.getElementById('channel-avatar-fallback').classList.add('hidden');
  document.getElementById('channel-live-badge').classList.add('hidden');
  document.getElementById('channel-watch-btn').classList.add('hidden');
  document.getElementById('channel-watch-btn').disabled = false;
  document.getElementById('channel-watch-btn').title = '';
  document.getElementById('channel-action-note').textContent = '';
  document.getElementById('channel-action-note').classList.add('hidden');
  document.getElementById('channel-follow-btn').textContent = 'Follow';
  document.getElementById('channel-follow-btn').classList.remove('following');
  document.getElementById('channel-open-btn').title = 'Open channel in browser';
  TwitchX.hideEmptyState(document.getElementById('channel-live-empty'));
  var staleLiveCard = document.getElementById('channel-live-card');
  if (staleLiveCard) staleLiveCard.remove();
  document.querySelectorAll('.channel-tab').forEach(function(t) {
    var active = t.dataset.tab === 'live';
    t.classList.toggle('active', active);
    t.setAttribute('aria-selected', String(active));
    t.tabIndex = active ? 0 : -1;
  });
  document.querySelectorAll('.channel-tab-panel').forEach(function(p) {
    p.classList.toggle('hidden', p.id !== 'channel-tab-live');
  });

  if (TwitchX.api) TwitchX.api.get_channel_profile(login, platform);

  if (TwitchX._channelProfileTimer) clearTimeout(TwitchX._channelProfileTimer);
  TwitchX._channelProfileTimer = setTimeout(function() {
    var loading = document.getElementById('channel-loading');
    if (loading && !loading.classList.contains('hidden')) {
      loading.classList.add('hidden');
      document.getElementById('channel-profile-card').classList.remove('fade-transparent');
      TwitchX.showToast('Failed to load channel profile', 'error');
    }
  }, 15000);
}

function hideChannelView() {
  if (TwitchX.channelViewSource === 'browse') {
    TwitchX.switchView('browse-view', 'back');
  } else {
    TwitchX.switchView('stream-grid', 'back');
    TwitchX.setChromeVisible(true);
    TwitchX.renderGrid();
  }
}

function switchChannelTab(btn, tab) {
  TwitchX.state.channelTabs.active = tab;
  TwitchX.setActiveTab(Array.from(document.querySelectorAll('.channel-tab')), btn);
  document.querySelectorAll('.channel-tab-panel').forEach(function(p) {
    p.classList.toggle('hidden', p.id !== 'channel-tab-' + tab);
  });
  ensureChannelTabLoaded(tab);
}

function toggleChannelFollow() {
  if (!TwitchX.channelProfile || !TwitchX.api) return;
  const p = TwitchX.channelProfile;
  if (p.is_favorited) {
    TwitchX.api.remove_channel(p.login, p.platform);
    p.is_favorited = false;
    document.getElementById('channel-follow-btn').textContent = 'Follow';
    document.getElementById('channel-follow-btn').classList.remove('following');
    TwitchX.api.refresh();
  } else {
    TwitchX.api.add_channel(p.login, p.platform, p.display_name);
    p.is_favorited = true;
    document.getElementById('channel-follow-btn').textContent = 'Following';
    document.getElementById('channel-follow-btn').classList.add('following');
    TwitchX.api.refresh();
  }
}

function watchChannelStream() {
  if (!TwitchX.channelProfile || !TwitchX.api) return;
  const p = TwitchX.channelProfile;
  if (!p.watch_supported) {
    const reason = p.watch_disabled_reason || 'This channel cannot be watched directly right now.';
    TwitchX.setStatus(reason, 'warn');
    TwitchX.showToast(reason, 'warn');
    return;
  }
  hideChannelView();
  const quality = document.getElementById('quality-select')
    ? document.getElementById('quality-select').value
    : 'best';
  TwitchX.api.watch_direct(p.login, p.platform, quality);
}

TwitchX.selectChannel = selectChannel;
TwitchX.addChannel = addChannel;
TwitchX.addChannelDirect = addChannelDirect;
TwitchX.doWatch = doWatch;
TwitchX.resetChannelMediaPanels = resetChannelMediaPanels;
TwitchX.getChannelMediaElements = getChannelMediaElements;
TwitchX.playChannelMedia = playChannelMedia;
TwitchX.openChannelMedia = openChannelMedia;
TwitchX.openChannelInBrowser = openChannelInBrowser;
TwitchX.createChannelMediaCard = createChannelMediaCard;
TwitchX.renderChannelLivePanel = renderChannelLivePanel;
TwitchX.renderChannelMediaTab = renderChannelMediaTab;
TwitchX.ensureChannelTabLoaded = ensureChannelTabLoaded;
TwitchX.showChannelView = showChannelView;
TwitchX.hideChannelView = hideChannelView;
TwitchX.switchChannelTab = switchChannelTab;
TwitchX.toggleChannelFollow = toggleChannelFollow;
TwitchX.watchChannelStream = watchChannelStream;
