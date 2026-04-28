const TwitchX = window.TwitchX || {};

function loadSidebarSections() {
  const fallback = { online: false, offline: true };
  try {
    const raw = window.localStorage.getItem('twitchx.sidebar.sections');
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    if (!parsed || parsed.version !== 2) {
      return fallback;
    }
    return {
      online: !!parsed.online,
      offline: !!parsed.offline,
    };
  } catch (e) {
    return fallback;
  }
}

function saveSidebarSections() {
  try {
    window.localStorage.setItem(
      'twitchx.sidebar.sections',
      JSON.stringify({
        version: 2,
        online: !!TwitchX.state.sidebarSections.online,
        offline: !!TwitchX.state.sidebarSections.offline,
      })
    );
  } catch (e) {}
}

function expandSidebarSectionForLogin(login) {
  if (!login) return false;
  const sectionKey = TwitchX.state.liveSet.has(login) ? 'online' : 'offline';
  if (TwitchX.state.sidebarSections[sectionKey]) {
    TwitchX.state.sidebarSections[sectionKey] = false;
    saveSidebarSections();
    return true;
  }
  return false;
}

function getSidebarGroups() {
  const streamMap = {};
  TwitchX.state.streams.forEach(function(stream) {
    streamMap[stream.login] = stream;
  });

  const online = TwitchX.state.favorites
    .filter(function(login) { return TwitchX.state.liveSet.has(login); })
    .sort(function(a, b) {
      const diff = (streamMap[b] ? streamMap[b].viewers : 0) - (streamMap[a] ? streamMap[a].viewers : 0);
      return diff !== 0 ? diff : a.localeCompare(b);
    });

  const offline = TwitchX.state.favorites
    .filter(function(login) { return !TwitchX.state.liveSet.has(login); })
    .sort(function(a, b) { return a.localeCompare(b); });

  return {
    online: online,
    offline: offline,
    streamMap: streamMap,
  };
}

function applySidebarLayout(groups) {
  const list = document.getElementById('channel-list');
  const onlineSection = list.querySelector('.sidebar-section.online');
  const offlineSection = list.querySelector('.sidebar-section.offline');
  if (!onlineSection || !offlineSection) return;

  const listHeight = Math.max(list.clientHeight, 320);
  const sectionGap = 10;
  const onlineCollapsed = !!TwitchX.state.sidebarSections.online;
  const offlineCollapsed = !!TwitchX.state.sidebarSections.offline;
  const onlineBody = onlineSection.querySelector('.section-body');
  const offlineBody = offlineSection.querySelector('.section-body');
  const onlineHeaderHeight = onlineSection.querySelector('.section-toggle').offsetHeight;
  const offlineHeaderHeight = offlineSection.querySelector('.section-toggle').offsetHeight;

  onlineSection.style.flex = onlineCollapsed ? '0 0 auto' : '0 0 auto';
  onlineSection.style.height = '';
  onlineSection.style.minHeight = onlineCollapsed ? onlineHeaderHeight + 'px' : '';

  offlineSection.style.height = '';
  offlineSection.style.minHeight = offlineHeaderHeight + 'px';
  offlineSection.style.flex = offlineCollapsed ? '0 0 auto' : '1 1 0px';

  if (onlineCollapsed) {
    return;
  }

  const onlineNaturalHeight = onlineHeaderHeight + onlineBody.scrollHeight;
  let offlineReservedHeight;

  if (offlineCollapsed) {
    offlineReservedHeight = offlineSection.offsetHeight;
  } else if (groups.offline.length === 0) {
    offlineReservedHeight = offlineHeaderHeight + offlineBody.scrollHeight;
  } else {
    const offlineMinRows = Math.min(Math.max(groups.offline.length, 2), 4);
    const offlineRowHeight = 52;
    offlineReservedHeight = Math.max(
      offlineHeaderHeight + 24,
      offlineHeaderHeight + (offlineMinRows * offlineRowHeight)
    );
  }

  const onlineMaxHeight = Math.max(
    onlineHeaderHeight + 96,
    listHeight - offlineReservedHeight - sectionGap
  );
  const onlineTargetHeight = Math.min(onlineNaturalHeight, onlineMaxHeight);

  onlineSection.style.height = onlineTargetHeight + 'px';
  onlineSection.style.minHeight = onlineTargetHeight + 'px';

  if (!offlineCollapsed) {
    offlineSection.style.minHeight = Math.min(
      Math.max(offlineReservedHeight, offlineHeaderHeight + 72),
      Math.max(listHeight - onlineTargetHeight - sectionGap, offlineHeaderHeight)
    ) + 'px';
  }
}

function getSidebarSectionMeta(sectionKey, logins, streamMap) {
  if (sectionKey === 'online') {
    if (logins.length === 0) {
      return 'Waiting for the next live channel';
    }
    const totalViewers = logins.reduce(function(sum, login) {
      return sum + ((streamMap[login] && streamMap[login].viewers) || 0);
    }, 0);
    return logins.length + ' live now • ' + TwitchX.formatViewers(totalViewers) + ' combined viewers';
  }
  if (logins.length === 0) {
    return 'Saved channels appear here';
  }
  return logins.length + ' saved • sorted A to Z';
}

function createSidebarItem(login, streamMap) {
  const stream = streamMap[login] || null;
  const isLive = !!stream;
  const isSelected = TwitchX.state.selectedChannel === login;

  const item = document.createElement('div');
  item.className = 'channel-item' + (isLive ? ' live' : '') + (isSelected ? ' selected' : '');
  item.dataset.login = login;
  item.tabIndex = 0;
  item.setAttribute('role', 'button');
  item.setAttribute('aria-pressed', String(isSelected));
  item.setAttribute(
    'aria-label',
    isLive
      ? login + ', live, ' + Number(stream.viewers || 0).toLocaleString() + ' viewers'
      : login + ', offline'
  );

  const bar = document.createElement('div');
  bar.className = 'accent-bar';
  item.appendChild(bar);

  const dot = document.createElement('span');
  dot.className = 'live-dot';
  dot.textContent = '\u25CF';
  item.appendChild(dot);

  const avatar = document.createElement('img');
  avatar.className = 'avatar';
  if (TwitchX.state.avatars[login]) {
    avatar.src = TwitchX.state.avatars[login];
  }
  avatar.alt = '';
  item.appendChild(avatar);

  const copy = document.createElement('div');
  copy.className = 'channel-copy';

  const name = document.createElement('span');
  name.className = 'name';
  const favMeta = TwitchX.state.favoritesMeta[login] || {};
  name.textContent = (stream && stream.display_name) || favMeta.display_name || login;
  copy.appendChild(name);

  const meta = document.createElement('span');
  meta.className = 'channel-meta';
  meta.textContent = isLive ? TwitchX.truncate(stream.game || 'Live now', 24) : 'Offline';
  copy.appendChild(meta);
  item.appendChild(copy);

  if (isLive) {
    const metric = document.createElement('span');
    metric.className = 'metric';
    metric.textContent = TwitchX.formatViewers(stream.viewers);
    metric.title = Number(stream.viewers || 0).toLocaleString() + ' viewers';
    item.appendChild(metric);
  } else {
    const status = document.createElement('span');
    status.className = 'status-badge';
    status.textContent = 'Off';
    item.appendChild(status);
  }

  item.addEventListener('click', function() { TwitchX.selectChannel(login); });
  item.addEventListener('dblclick', function() { TwitchX.selectChannel(login); TwitchX.doWatch(); });
  item.addEventListener('contextmenu', function(e) { TwitchX.showSidebarContextMenu(e, login); });
  item.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      TwitchX.selectChannel(login);
    }
  });

  return item;
}

function createSidebarSection(sectionKey, title, metaText, logins, streamMap) {
  const isCollapsed = !!TwitchX.state.sidebarSections[sectionKey];

  const section = document.createElement('section');
  section.className = 'sidebar-section ' + sectionKey + (isCollapsed ? ' collapsed' : '');
  section.dataset.section = sectionKey;

  const toggle = document.createElement('button');
  toggle.className = 'section-toggle';
  toggle.type = 'button';
  toggle.setAttribute('aria-label', title + ' section');
  toggle.setAttribute('aria-expanded', String(!isCollapsed));
  toggle.setAttribute('aria-controls', 'sidebar-section-body-' + sectionKey);
  toggle.addEventListener('click', function() {
    TwitchX.state.sidebarSections[sectionKey] = !TwitchX.state.sidebarSections[sectionKey];
    saveSidebarSections();
    renderSidebar();
  });

  const titleWrap = document.createElement('div');
  titleWrap.className = 'section-title-wrap';

  const chevron = document.createElement('span');
  chevron.className = 'section-chevron';
  chevron.textContent = '\u203A';
  titleWrap.appendChild(chevron);

  const copy = document.createElement('div');
  copy.className = 'section-copy';

  const titleEl = document.createElement('div');
  titleEl.className = 'section-title';
  titleEl.textContent = title;
  copy.appendChild(titleEl);

  const meta = document.createElement('div');
  meta.className = 'section-meta';
  meta.textContent = metaText;
  copy.appendChild(meta);

  titleWrap.appendChild(copy);
  toggle.appendChild(titleWrap);

  const count = document.createElement('span');
  count.className = 'section-count';
  count.textContent = String(logins.length);
  toggle.appendChild(count);

  section.appendChild(toggle);

  const body = document.createElement('div');
  body.className = 'section-body';
  body.id = 'sidebar-section-body-' + sectionKey;

  if (logins.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'section-empty';
    const emptyTitle = document.createElement('div');
    emptyTitle.className = 'section-empty-title';
    emptyTitle.textContent = sectionKey === 'online'
      ? 'No one is live right now'
      : 'No offline channels yet';
    empty.appendChild(emptyTitle);

    const emptySubtitle = document.createElement('div');
    emptySubtitle.className = 'section-empty-subtitle';
    emptySubtitle.textContent = sectionKey === 'online'
      ? 'As soon as one of your favorites goes live, they will appear here first.'
      : 'Any saved channel that is currently offline will appear in this list.';
    empty.appendChild(emptySubtitle);
    body.appendChild(empty);
  } else {
    logins.forEach(function(login) {
      body.appendChild(createSidebarItem(login, streamMap));
    });
  }

  section.appendChild(body);
  return section;
}

function renderSidebar() {
  const list = document.getElementById('channel-list');
  const groups = getSidebarGroups();
  const selectedExpanded = expandSidebarSectionForLogin(TwitchX.state.selectedChannel);

  while (list.firstChild) list.removeChild(list.firstChild);

  if (TwitchX.state.favorites.length === 0) {
    document.getElementById('favorites-count-badge').textContent = '0';
    return;
  }

  list.appendChild(
    createSidebarSection(
      'online',
      'Online',
      getSidebarSectionMeta('online', groups.online, groups.streamMap),
      groups.online,
      groups.streamMap
    )
  );

  list.appendChild(
    createSidebarSection(
      'offline',
      'Offline',
      getSidebarSectionMeta('offline', groups.offline, groups.streamMap),
      groups.offline,
      groups.streamMap
    )
  );

  applySidebarLayout(groups);

  document.getElementById('favorites-count-badge').textContent = String(TwitchX.state.favorites.length);

  if (selectedExpanded) {
    const selectedItem = list.querySelector('.channel-item.selected');
    if (selectedItem) {
      selectedItem.scrollIntoView({ block: 'nearest' });
    }
  }
}

// Initialize sidebar sections from localStorage on load
TwitchX.state.sidebarSections = loadSidebarSections();

TwitchX.loadSidebarSections = loadSidebarSections;
TwitchX.saveSidebarSections = saveSidebarSections;
TwitchX.expandSidebarSectionForLogin = expandSidebarSectionForLogin;
TwitchX.getSidebarGroups = getSidebarGroups;
TwitchX.applySidebarLayout = applySidebarLayout;
TwitchX.getSidebarSectionMeta = getSidebarSectionMeta;
TwitchX.createSidebarItem = createSidebarItem;
TwitchX.createSidebarSection = createSidebarSection;
TwitchX.renderSidebar = renderSidebar;
