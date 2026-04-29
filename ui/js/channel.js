window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

function selectChannel(login) {
  TwitchX.state.selectedChannel = login;
  if (TwitchX.expandSidebarSectionForLogin(login)) {
    TwitchX.renderSidebar();
  }
  document.querySelectorAll('.stream-card').forEach(function(c) {
    c.classList.toggle('selected', c.dataset.login === login);
  });
  document.querySelectorAll('.channel-item').forEach(function(c) {
    const isSelected = c.dataset.login === login;
    c.classList.toggle('selected', isSelected);
    c.setAttribute('aria-pressed', String(isSelected));
  });
  document.getElementById('watch-btn').classList.add('active');
  TwitchX.setStatus('Selected: ' + login, 'info');
}

function addChannel() {
  const input = document.getElementById('search-input');
  const val = input.value.trim();
  if (val && TwitchX.api) {
    const platform = TwitchX.state.activePlatformFilter;
    const lower = val.toLowerCase();
    let choice = null;
    if (platform === 'all') {
      if (lower.indexOf('youtube.com/') !== -1 || lower.charAt(0) === '@') {
        choice = { login: val, platform: 'youtube' };
      } else if (lower.indexOf('kick.com/') !== -1) {
        choice = { login: val, platform: 'kick' };
      } else if (lower.indexOf('twitch.tv/') !== -1) {
        choice = { login: val, platform: 'twitch' };
      } else {
        const matches = TwitchX.state.searchResults.filter(function(result) {
          return result.login === lower || (result.display_name || '').toLowerCase() === lower;
        });
        if (matches.length === 1) {
          choice = matches[0];
        } else if (TwitchX.state.searchResults.length > 0) {
          choice = TwitchX.state.searchResults[0];
        }
      }
    }
    const targetPlatform = (choice && choice.platform) || (platform === 'all' ? 'twitch' : platform) || 'twitch';
    const loginToAdd = (choice && choice.login) || val;
    const displayToAdd = (choice && choice.display_name) || '';
    TwitchX.api.add_channel(loginToAdd, targetPlatform, displayToAdd);
    input.value = '';
    TwitchX.state.searchResults = [];
    document.getElementById('search-dropdown').style.display = 'none';
  }
}

function addChannelDirect(login, platform, displayName) {
  if (TwitchX.api) TwitchX.api.add_channel(login, platform || 'twitch', displayName || '');
}

function doWatch() {
  if (!TwitchX.state.selectedChannel || !TwitchX.api) return;
  const quality = document.getElementById('quality-select').value;
  TwitchX.api.watch(TwitchX.state.selectedChannel, quality);
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
      empty.classList.add('hidden');
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

function createChannelMediaCard(item, tab) {
  const card = document.createElement('div');
  card.className = 'channel-media-card' + (tab === 'clips' ? ' clip' : '');

  const thumbWrap = document.createElement('div');
  thumbWrap.className = 'channel-media-thumb-wrap';
  thumbWrap.onclick = function() { playChannelMedia(item); };

  const thumb = document.createElement('img');
  thumb.className = 'channel-media-thumb';
  thumb.alt = '';
  if (item.thumbnail_url) thumb.src = item.thumbnail_url;
  thumb.onerror = function() { thumbWrap.style.display = 'none'; };
  thumbWrap.appendChild(thumb);

  const body = document.createElement('div');
  body.className = 'channel-media-body';

  const title = document.createElement('div');
  title.className = 'channel-media-title';
  title.textContent = item.title || (tab === 'clips' ? 'Untitled clip' : 'Untitled VOD');

  const meta = document.createElement('div');
  meta.className = 'channel-media-meta';
  meta.textContent = TwitchX.buildChannelMediaMeta(item, tab);

  const actions = document.createElement('div');
  actions.className = 'channel-media-actions';

  const playBtn = document.createElement('button');
  playBtn.className = 'channel-media-btn';
  playBtn.textContent = 'Play';
  playBtn.onclick = function() { playChannelMedia(item); };

  const openBtn = document.createElement('button');
  openBtn.className = 'channel-media-btn secondary';
  openBtn.textContent = 'Open';
  openBtn.onclick = function() { openChannelMedia(item); };

  actions.appendChild(playBtn);
  actions.appendChild(openBtn);
  body.appendChild(title);
  body.appendChild(meta);
  body.appendChild(actions);
  card.appendChild(thumbWrap);
  card.appendChild(body);
  return card;
}

function renderChannelMediaTab(tab) {
  const entry = TwitchX.state.channelTabs[tab];
  const els = getChannelMediaElements(tab);
  if (!entry || !els.loading || !els.empty || !els.container) return;

  els.loading.classList.toggle('hidden', entry.status !== 'loading');
  els.container.replaceChildren();

  if (entry.status !== 'ready') {
    els.empty.classList.add('hidden');
    return;
  }

  if (!entry.supported || entry.error || !entry.items.length) {
    els.empty.textContent = entry.message || (
      tab === 'vods' ? 'No recent VODs found.' : 'No recent clips found.'
    );
    els.empty.classList.remove('hidden');
    return;
  }

  els.empty.classList.add('hidden');
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

  if (TwitchX.channelViewSource === 'browse') {
    document.getElementById('browse-view').classList.add('hidden');
  } else {
    document.getElementById('toolbar').classList.add('hidden');
    document.getElementById('stream-grid').classList.add('hidden');
  }

  document.getElementById('channel-view').classList.remove('hidden');
  document.getElementById('channel-loading').classList.remove('hidden');
  document.getElementById('channel-profile-card').style.opacity = '0';
  document.getElementById('channel-header-title').textContent = login;
  document.getElementById('channel-display-name').textContent = '';
  document.getElementById('channel-login-text').textContent = '';
  document.getElementById('channel-followers').textContent = '';
  document.getElementById('channel-bio').textContent = '';
  document.getElementById('channel-avatar').classList.add('hidden');
  document.getElementById('channel-live-badge').classList.add('hidden');
  document.getElementById('channel-watch-btn').classList.add('hidden');
  document.getElementById('channel-follow-btn').textContent = 'Follow';
  document.getElementById('channel-follow-btn').classList.remove('following');
  document.getElementById('channel-live-empty').classList.add('hidden');
  document.querySelectorAll('.channel-tab').forEach(function(t) {
    t.classList.toggle('active', t.dataset.tab === 'live');
  });
  document.querySelectorAll('.channel-tab-panel').forEach(function(p) {
    p.classList.toggle('hidden', p.id !== 'channel-tab-live');
  });

  if (TwitchX.api) TwitchX.api.get_channel_profile(login, platform);
}

function hideChannelView() {
  document.getElementById('channel-view').classList.add('hidden');
  if (TwitchX.channelViewSource === 'browse') {
    document.getElementById('browse-view').classList.remove('hidden');
  } else {
    document.getElementById('toolbar').classList.remove('hidden');
    document.getElementById('stream-grid').classList.remove('hidden');
  }
}

function switchChannelTab(btn, tab) {
  TwitchX.state.channelTabs.active = tab;
  document.querySelectorAll('.channel-tab').forEach(function(t) {
    t.classList.toggle('active', t === btn);
  });
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
TwitchX.createChannelMediaCard = createChannelMediaCard;
TwitchX.renderChannelMediaTab = renderChannelMediaTab;
TwitchX.ensureChannelTabLoaded = ensureChannelTabLoaded;
TwitchX.showChannelView = showChannelView;
TwitchX.hideChannelView = hideChannelView;
TwitchX.switchChannelTab = switchChannelTab;
TwitchX.toggleChannelFollow = toggleChannelFollow;
TwitchX.watchChannelStream = watchChannelStream;
