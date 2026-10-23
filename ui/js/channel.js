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
  TwitchX.setStatus('Selected: ' + login + ' on ' + TwitchX.platformLabel(resolvedPlatform), 'info');
}

// Resolve what the user typed (a name, a channel URL or an @handle) to a
// platform and add it. `results` are the channel search results for the same
// text, used to pick the platform of an exact login match.
function addChannelFromQuery(query, results) {
  const val = (query || '').trim();
  if (!val || !TwitchX.api) return;
  results = results || [];
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
      const exactLoginMatches = results.filter(function(result) {
        return result.login && result.login.toLowerCase() === inputLower;
      });
      if (exactLoginMatches.length === 1) {
        choice = exactLoginMatches[0];
      } else if (exactLoginMatches.length === 0 && results.length > 0) {
        // No exact match: fall back to the top search result only if its display name matches.
        const displayMatch = results.find(function(result) {
          return (result.display_name || '').toLowerCase() === inputLower;
        });
        if (displayMatch) choice = displayMatch;
      }
    }
  }
  const targetPlatform = (choice && choice.platform) || (platform === 'all' ? 'twitch' : platform) || 'twitch';
  addChannel((choice && choice.login) || val, targetPlatform, (choice && choice.display_name) || '');
}

function addChannel(login, platform, displayName) {
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
  const quality = TwitchX.state.quality;
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
  const quality = TwitchX.state.quality;
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

// VODs and clips use the stream card (render.js buildMediaCard) with the
// length in the corner instead of uptime.
function createChannelMediaCard(item, tab) {
  const profile = TwitchX.channelProfile || {};
  const untitled = tab === 'clips' ? 'Untitled clip' : 'Untitled VOD';
  const parts = [];
  const dateText = TwitchX.formatMediaDate(item.published_at);
  if (dateText) parts.push(dateText);
  if (item.views) parts.push(TwitchX.formatViewers(item.views) + ' views');
  const card = TwitchX.buildMediaCard({
    platform: item.platform || profile.platform || 'twitch',
    thumb: item.thumbnail_url || null,
    fallbackLabel: item.title || item.channel_login || profile.login,
    showAvatar: false,
    title: item.title || untitled,
    channel: parts.join(' \u00b7 '),
    corner: TwitchX.formatDuration(item.duration_seconds || 0),
    label: 'Play ' + (item.title || untitled),
  });
  card.classList.add('channel-media-card');
  // Media that cannot play in the app opens in the browser instead.
  const playable = item.play_supported !== false;
  if (!playable) card.title = (item.play_disabled_reason || 'This media cannot be played in app.') + ' Opens in the browser.';
  function activate() {
    if (playable) playChannelMedia(item);
    else openChannelMedia(item);
  }
  card.addEventListener('click', activate);
  card.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      activate();
    }
  });
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

  const card = TwitchX.buildMediaCard({
    platform: platform,
    thumb: TwitchX.state.thumbnails[key] || (stream && stream.thumbnail_url) || null,
    fallbackLabel: label,
    avatar: TwitchX.state.avatars[key] || profile.avatar_url || null,
    title: (stream && stream.title) || label + ' is live',
    channel: label,
    game: stream && stream.game,
    viewers: stream && typeof stream.viewers === 'number' ? stream.viewers : null,
    corner: stream && stream.started_at ? TwitchX.formatUptimeClock(stream.started_at) : '',
    watching: TwitchX.state.watchingChannelKey === key,
    label: 'Watch ' + label + ' now',
  });
  card.id = 'channel-live-card';
  card.classList.add('channel-media-card');
  card.addEventListener('click', watchChannelStream);
  card.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      watchChannelStream();
    }
  });
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
  document.getElementById('channel-platform-badge').replaceChildren();
  document.getElementById('channel-platform-badge').className = 'hidden';
  document.getElementById('channel-banner').style.removeProperty('--banner-color');
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

  TwitchX.state.pendingProfileKey = TwitchX.channelKey(login, platform);
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
  TwitchX.state.pendingProfileKey = '';
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

// The profile banner takes the avatar's average colour. A cross-origin avatar
// taints the canvas; the banner then keeps its neutral gradient.
function tintChannelBanner(img) {
  const banner = document.getElementById('channel-banner');
  if (!banner || !img || !img.naturalWidth) return;
  try {
    const canvas = document.createElement('canvas');
    canvas.width = 8;
    canvas.height = 8;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0, 8, 8);
    const px = ctx.getImageData(0, 0, 8, 8).data;
    let r = 0, g = 0, b = 0;
    for (let i = 0; i < px.length; i += 4) { r += px[i]; g += px[i + 1]; b += px[i + 2]; }
    const n = px.length / 4;
    banner.style.setProperty('--banner-color', 'rgb(' + Math.round(r / n) + ', ' + Math.round(g / n) + ', ' + Math.round(b / n) + ')');
  } catch (e) {
    banner.style.removeProperty('--banner-color');
  }
}

function watchChannelStream() {
  if (!TwitchX.channelProfile || !TwitchX.api) return;
  const p = TwitchX.channelProfile;
  if (!p.watch_supported) {
    const reason = p.watch_disabled_reason || 'This channel cannot be watched directly right now.';
    TwitchX.setStatus(reason, 'warn');
    return;
  }
  hideChannelView();
  const quality = TwitchX.state.quality;
  TwitchX.api.watch_direct(p.login, p.platform, quality);
}

TwitchX.selectChannel = selectChannel;
TwitchX.addChannel = addChannel;
TwitchX.addChannelDirect = addChannel;
TwitchX.addChannelFromQuery = addChannelFromQuery;
TwitchX.doWatch = doWatch;
TwitchX.resetChannelMediaPanels = resetChannelMediaPanels;
TwitchX.getChannelMediaElements = getChannelMediaElements;
TwitchX.playChannelMedia = playChannelMedia;
TwitchX.openChannelMedia = openChannelMedia;
TwitchX.openChannelInBrowser = openChannelInBrowser;
TwitchX.createChannelMediaCard = createChannelMediaCard;
TwitchX.renderChannelLivePanel = renderChannelLivePanel;
TwitchX.tintChannelBanner = tintChannelBanner;
TwitchX.renderChannelMediaTab = renderChannelMediaTab;
TwitchX.ensureChannelTabLoaded = ensureChannelTabLoaded;
TwitchX.showChannelView = showChannelView;
TwitchX.hideChannelView = hideChannelView;
TwitchX.switchChannelTab = switchChannelTab;
TwitchX.toggleChannelFollow = toggleChannelFollow;
TwitchX.watchChannelStream = watchChannelStream;
