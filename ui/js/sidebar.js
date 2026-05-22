window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

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

function _isWatching(login) {
  if (!TwitchX.state.watchingChannel) return false;
  return TwitchX.state.watchingChannel.toLowerCase() === login.toLowerCase();
}

function _matchWatching(login) {
  if (!TwitchX.state.watchingChannel) return false;
  const wc = TwitchX.state.watchingChannel;
  const wcLower = wc.toLowerCase();
  if (wcLower === login.toLowerCase()) return true;
  return wc === login;
}

function _setupSidebarTooltip(item, login, streamMap) {
  let tooltipTimer = null;
  function showTooltip(e) {
    var tooltip = document.getElementById('sidebar-tooltip');
    if (!tooltip) return;
    var stream = streamMap[login];
    if (!stream) return;
    var thumb = document.getElementById('tooltip-thumb');
    var title = document.getElementById('tooltip-title');
    var game = document.getElementById('tooltip-game');
    var viewers = document.getElementById('tooltip-viewers');
    if (thumb && stream.thumbnail_url) {
      thumb.src = stream.thumbnail_url;
      thumb.style.display = '';
    } else if (thumb) {
      thumb.style.display = 'none';
    }
    if (title) title.textContent = stream.display_name || login;
    if (game) game.textContent = stream.game || (stream.title ? stream.title : '');
    if (viewers) {
      viewers.textContent = TwitchX.formatViewers(stream.viewers) + ' viewers';
    }
    var r = item.getBoundingClientRect();
    var tx = r.right + 8;
    var ty = r.top + (r.height / 2) - 40;
    if (tx + 260 > window.innerWidth) tx = r.left - 268;
    if (ty < 4) ty = 4;
    if (ty + 80 > window.innerHeight) ty = window.innerHeight - 84;
    tooltip.style.left = tx + 'px';
    tooltip.style.top = ty + 'px';
    tooltip.classList.remove('hidden');
    tooltip.classList.add('visible');
  }
  function hideTooltip() {
    var tooltip = document.getElementById('sidebar-tooltip');
    if (tooltip) { tooltip.classList.remove('visible'); tooltip.classList.add('hidden'); }
  }
  item.addEventListener('mouseenter', function(e) {
    tooltipTimer = setTimeout(function() { showTooltip(e); }, 400);
  });
  item.addEventListener('mousemove', function(e) {
    if (tooltipTimer) { clearTimeout(tooltipTimer); tooltipTimer = null; }
    tooltipTimer = setTimeout(function() { showTooltip(e); }, 400);
  });
  item.addEventListener('mouseleave', function() {
    if (tooltipTimer) { clearTimeout(tooltipTimer); tooltipTimer = null; }
    hideTooltip();
  });
}

function createSidebarItem(login, streamMap) {
  const stream = streamMap[login] || null;
  const isLive = !!stream;
  const isSelected = TwitchX.state.selectedChannel === login;
  const isWatching = _matchWatching(login);

  const item = document.createElement('div');
  item.className = 'channel-item' + (isLive ? ' live' : '') + (isSelected ? ' selected' : '') + (isWatching ? ' watching' : '');
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
  dot.innerHTML = TwitchX.renderIcon('live-dot', 10);
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
  const favMeta = TwitchX.getFavoriteMeta(login, stream && stream.platform) || {};
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

  // Notification dot for new live channels
  var notifDot = document.createElement('span');
  notifDot.className = 'notif-dot';
  notifDot.setAttribute('aria-label', 'New');
  item.appendChild(notifDot);

  _setupSidebarTooltip(item, login, streamMap);

  item.addEventListener('click', function() { TwitchX.selectChannel(login); });
  item.addEventListener('dblclick', function() { TwitchX.selectChannel(login); TwitchX.doWatch(); });
  item.addEventListener('contextmenu', function(e) { TwitchX.showSidebarContextMenu(e, login); });
  item.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      TwitchX.selectChannel(login);
    }
  });

  // Drag to multistream
  item.draggable = true;
  item.addEventListener('dragstart', function(e) {
    var platform = getChannelPlatform(login);
    e.dataTransfer.setData('text/plain', JSON.stringify({ login: login, platform: platform }));
    e.dataTransfer.effectAllowed = 'copy';
    item.classList.add('dragging');
    // Auto-open multistream view so the user sees drop zones
    if (!TwitchX.multiState.open) {
      TwitchX.openMultistreamView();
    }
  });
  item.addEventListener('dragend', function() {
    item.classList.remove('dragging');
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
  chevron.innerHTML = TwitchX.renderIcon('chevron-right', 12);
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

function updateSidebarItem(item, login, streamMap) {
  const stream = streamMap[login] || null;
  const isLive = !!stream;
  const isSelected = TwitchX.state.selectedChannel === login;

  const wasLive = item.classList.contains('live');
  const wasSelected = item.classList.contains('selected');

  if (isLive !== wasLive) {
    item.classList.toggle('live', isLive);
    item.setAttribute('aria-label',
      isLive
        ? login + ', live, ' + Number(stream.viewers || 0).toLocaleString() + ' viewers'
        : login + ', offline');
    if (isLive && stream) {
      item.dataset._lastViewers = String(stream.viewers || 0);
    } else {
      delete item.dataset._lastViewers;
    }
  } else if (isLive && stream) {
    const lastViewers = item.dataset._lastViewers;
    const currentViewers = String(stream.viewers || 0);
    if (lastViewers !== currentViewers) {
      item.setAttribute('aria-label', login + ', live, ' + Number(currentViewers).toLocaleString() + ' viewers');
      item.dataset._lastViewers = currentViewers;
    }
  }
  if (isSelected !== wasSelected) {
    item.classList.toggle('selected', isSelected);
    item.setAttribute('aria-pressed', String(isSelected));
  }

  // Watching indicator
  var isWatching = _matchWatching(login);
  item.classList.toggle('watching', isWatching);

  const nameEl = item.querySelector('.name');
  const favMeta = TwitchX.getFavoriteMeta(login, stream && stream.platform) || {};
  const newName = (stream && stream.display_name) || favMeta.display_name || login;
  if (nameEl.textContent !== newName) {
    nameEl.textContent = newName;
  }

  const metaEl = item.querySelector('.channel-meta');
  const newMeta = isLive ? TwitchX.truncate(stream.game || 'Live now', 24) : 'Offline';
  if (metaEl.textContent !== newMeta) {
    metaEl.textContent = newMeta;
  }

  const avatar = item.querySelector('.avatar');
  const newAvatar = TwitchX.state.avatars[login] || '';
  if (avatar && avatar.src !== newAvatar) {
    avatar.src = newAvatar;
  }

  const metricOrStatus = item.querySelector('.metric, .status-badge');
  if (isLive) {
    if (!metricOrStatus || !metricOrStatus.classList.contains('metric')) {
      if (metricOrStatus) metricOrStatus.remove();
      const metric = document.createElement('span');
      metric.className = 'metric';
      metric.textContent = TwitchX.formatViewers(stream.viewers);
      metric.title = Number(stream.viewers || 0).toLocaleString() + ' viewers';
      item.appendChild(metric);
    } else {
      const newViewers = TwitchX.formatViewers(stream.viewers);
      if (metricOrStatus.textContent !== newViewers) {
        metricOrStatus.textContent = newViewers;
        metricOrStatus.title = Number(stream.viewers || 0).toLocaleString() + ' viewers';
      }
    }
  } else {
    if (!metricOrStatus || !metricOrStatus.classList.contains('status-badge')) {
      if (metricOrStatus) metricOrStatus.remove();
      const status = document.createElement('span');
      status.className = 'status-badge';
      status.textContent = 'Off';
      item.appendChild(status);
    }
  }
}

function createRailAvatar(login, isLive, streamMap) {
  var item = document.createElement('div');
  item.className = 'rail-avatar' + (isLive ? ' live' : ' offline');
  item.dataset.login = login;
  item.tabIndex = 0;
  item.setAttribute('role', 'button');
  item.setAttribute(
    'aria-label',
    isLive
      ? login + ', live'
      : login + ', offline'
  );

  var img = document.createElement('img');
  img.className = 'rail-av-img';
  img.alt = '';
  if (TwitchX.state.avatars[login]) {
    img.src = TwitchX.state.avatars[login];
  }
  item.appendChild(img);

  if (isLive) {
    var ring = document.createElement('div');
    ring.className = 'rail-av-ring';
    item.appendChild(ring);

    var dot = document.createElement('div');
    dot.className = 'rail-av-dot';
    item.appendChild(dot);
  }

  _setupSidebarTooltip(item, login, streamMap);

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

function renderRail(groups) {
  var list = document.getElementById('channel-list');
  var liveLogins = groups.online;
  var offlineLogins = groups.offline;

  // In-place update if membership unchanged
  var existingLive = Array.from(list.querySelectorAll('.rail-avatar.live'))
    .map(function(el) { return el.dataset.login; });
  var existingOffline = Array.from(list.querySelectorAll('.rail-avatar.offline'))
    .map(function(el) { return el.dataset.login; });

  var liveChanged = existingLive.length !== liveLogins.length ||
    liveLogins.some(function(l, i) { return existingLive[i] !== l; });
  var offlineChanged = existingOffline.length !== offlineLogins.length ||
    offlineLogins.some(function(l, i) { return existingOffline[i] !== l; });

  if (!liveChanged && !offlineChanged) {
    list.querySelectorAll('.rail-avatar').forEach(function(el) {
      var login = el.dataset.login;
      var img = el.querySelector('.rail-av-img');
      var newSrc = TwitchX.state.avatars[login] || '';
      if (img && newSrc && img.src !== newSrc) {
        img.src = newSrc;
      }
    });
    return;
  }

  // Full rebuild
  while (list.firstChild) list.removeChild(list.firstChild);

  liveLogins.forEach(function(login) {
    list.appendChild(createRailAvatar(login, true, groups.streamMap));
  });

  if (liveLogins.length > 0 && offlineLogins.length > 0) {
    var divider = document.createElement('div');
    divider.className = 'rail-divider';
    list.appendChild(divider);
  }

  offlineLogins.forEach(function(login) {
    list.appendChild(createRailAvatar(login, false, groups.streamMap));
  });
}

function renderSidebar() {
  const list = document.getElementById('channel-list');
  const groups = getSidebarGroups();
  const selectedExpanded = expandSidebarSectionForLogin(TwitchX.state.selectedChannel);

  // Skip full rebuild if sections already exist and membership hasn't changed
  const existingOnlineSection = list.querySelector('.sidebar-section.online');
  const existingOfflineSection = list.querySelector('.sidebar-section.offline');

  if (existingOnlineSection && existingOfflineSection && TwitchX.state.favorites.length > 0) {
    const onlineBody = existingOnlineSection.querySelector('.section-body');
    const offlineBody = existingOfflineSection.querySelector('.section-body');

    const oldOnlineLogins = Array.from(onlineBody.querySelectorAll('.channel-item')).map(function(el) { return el.dataset.login; });
    const oldOfflineLogins = Array.from(offlineBody.querySelectorAll('.channel-item')).map(function(el) { return el.dataset.login; });

    const onlineChanged = oldOnlineLogins.length !== groups.online.length ||
      groups.online.some(function(l, i) { return oldOnlineLogins[i] !== l; });
    const offlineChanged = oldOfflineLogins.length !== groups.offline.length ||
      groups.offline.some(function(l, i) { return oldOfflineLogins[i] !== l; });

    const onlineCollapsed = !!TwitchX.state.sidebarSections.online;
    const offlineCollapsed = !!TwitchX.state.sidebarSections.offline;
    const oldOnlineCollapsed = existingOnlineSection.classList.contains('collapsed');
    const oldOfflineCollapsed = existingOfflineSection.classList.contains('collapsed');

    const collapsedChanged = onlineCollapsed !== oldOnlineCollapsed || offlineCollapsed !== oldOfflineCollapsed;

    if (!onlineChanged && !offlineChanged && !collapsedChanged) {
      // In-place update only
      groups.online.forEach(function(login) {
        const item = onlineBody.querySelector('.channel-item[data-login="' + login + '"]');
        if (item) updateSidebarItem(item, login, groups.streamMap);
      });
      groups.offline.forEach(function(login) {
        const item = offlineBody.querySelector('.channel-item[data-login="' + login + '"]');
        if (item) updateSidebarItem(item, login, groups.streamMap);
      });
      // Update section meta text
      existingOnlineSection.querySelector('.section-meta').textContent =
        getSidebarSectionMeta('online', groups.online, groups.streamMap);
      existingOfflineSection.querySelector('.section-meta').textContent =
        getSidebarSectionMeta('offline', groups.offline, groups.streamMap);
      existingOnlineSection.querySelector('.section-count').textContent = String(groups.online.length);
      existingOfflineSection.querySelector('.section-count').textContent = String(groups.offline.length);

      document.getElementById('favorites-count-badge').textContent = String(TwitchX.state.favorites.length);

      if (selectedExpanded) {
        const selectedItem = list.querySelector('.channel-item.selected');
        if (selectedItem) {
          selectedItem.scrollIntoView({ block: 'nearest' });
        }
      }
      // Defer layout to next frame to avoid forced reflow during video paint
      requestAnimationFrame(function() {
        applySidebarLayout(groups);
      });
      initSidebarScrollShadow();
      return;
    }

    // Membership or collapsed state changed — do diff rebuild of sections
    // Rebuild online section
    if (onlineChanged || collapsedChanged) {
      const newOnlineSection = createSidebarSection(
        'online',
        'Online',
        getSidebarSectionMeta('online', groups.online, groups.streamMap),
        groups.online,
        groups.streamMap
      );
      list.replaceChild(newOnlineSection, existingOnlineSection);
    } else {
      groups.online.forEach(function(login) {
        const item = onlineBody.querySelector('.channel-item[data-login="' + login + '"]');
        if (item) updateSidebarItem(item, login, groups.streamMap);
      });
      existingOnlineSection.querySelector('.section-meta').textContent =
        getSidebarSectionMeta('online', groups.online, groups.streamMap);
      existingOnlineSection.querySelector('.section-count').textContent = String(groups.online.length);
    }

    // Rebuild offline section
    const currentOfflineSection = list.querySelector('.sidebar-section.offline');
    if (offlineChanged || collapsedChanged) {
      const newOfflineSection = createSidebarSection(
        'offline',
        'Offline',
        getSidebarSectionMeta('offline', groups.offline, groups.streamMap),
        groups.offline,
        groups.streamMap
      );
      list.replaceChild(newOfflineSection, currentOfflineSection);
    } else {
      groups.offline.forEach(function(login) {
        const item = offlineBody.querySelector('.channel-item[data-login="' + login + '"]');
        if (item) updateSidebarItem(item, login, groups.streamMap);
      });
      currentOfflineSection.querySelector('.section-meta').textContent =
        getSidebarSectionMeta('offline', groups.offline, groups.streamMap);
      currentOfflineSection.querySelector('.section-count').textContent = String(groups.offline.length);
    }

    document.getElementById('favorites-count-badge').textContent = String(TwitchX.state.favorites.length);

    if (selectedExpanded) {
      const selectedItem = list.querySelector('.channel-item.selected');
      if (selectedItem) {
        selectedItem.scrollIntoView({ block: 'nearest' });
      }
    }
    requestAnimationFrame(function() {
      applySidebarLayout(groups);
    });
    initSidebarScrollShadow();
    return;
  }

  // Full rebuild (first render or empty favorites)
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

  document.getElementById('favorites-count-badge').textContent = String(TwitchX.state.favorites.length);

  if (selectedExpanded) {
    const selectedItem = list.querySelector('.channel-item.selected');
    if (selectedItem) {
      selectedItem.scrollIntoView({ block: 'nearest' });
    }
  }

  requestAnimationFrame(function() {
    applySidebarLayout(groups);
  });
  initSidebarScrollShadow();
}

// Initialize sidebar sections from localStorage on load
TwitchX.state.sidebarSections = loadSidebarSections();

function getChannelPlatform(login) {
  var stream = TwitchX.state.streams.find(function(s) { return s.login === login; });
  if (stream && stream.platform) return stream.platform;
  var plats = ['twitch', 'kick', 'youtube'];
  for (var i = 0; i < plats.length; i++) {
    if (TwitchX.state.favoritesMeta[plats[i] + ':' + login]) return plats[i];
  }
  return 'twitch';
}
TwitchX.getChannelPlatform = getChannelPlatform;

function updateSidebarScrollShadow() {
  var bodies = document.querySelectorAll('#channel-list .section-body');
  for (var i = 0; i < bodies.length; i++) {
    bodies[i].classList.toggle('scrolled', bodies[i].scrollTop > 0);
  }
}

function _onSectionBodyScroll() {
  updateSidebarScrollShadow();
}

function initSidebarScrollShadow() {
  var bodies = document.querySelectorAll('#channel-list .section-body');
  for (var i = 0; i < bodies.length; i++) {
    bodies[i].removeEventListener('scroll', _onSectionBodyScroll);
    bodies[i].addEventListener('scroll', _onSectionBodyScroll);
  }
  updateSidebarScrollShadow();
}

function _updateNotifBadges() {
  var badgeLogins = TwitchX._notifBadgeLogins || [];
  var notifBadge = document.getElementById('favorites-header').querySelector('.notif-badge');
  if (!notifBadge) {
    notifBadge = document.createElement('span');
    notifBadge.className = 'notif-badge';
    document.getElementById('favorites-header').appendChild(notifBadge);
  }
  if (badgeLogins.length > 0) {
    notifBadge.textContent = String(badgeLogins.length);
    notifBadge.classList.add('visible');
  } else {
    notifBadge.classList.remove('visible');
  }
  // Show notif-dot on each new-live item
  var items = document.querySelectorAll('.channel-item');
  items.forEach(function(item) {
    var dot = item.querySelector('.notif-dot');
    if (!dot) return;
    var login = item.dataset.login;
    if (badgeLogins.indexOf(login) !== -1) {
      dot.classList.add('visible');
    } else {
      dot.classList.remove('visible');
    }
  });
}

function _clearNotifBadges() {
  TwitchX._notifBadgeLogins = [];
  _updateNotifBadges();
}

// Update notif badges after sidebar render
var _origRenderSidebar = renderSidebar;
renderSidebar = function() {
  _origRenderSidebar.apply(this, arguments);
  _updateNotifBadges();
};

TwitchX.loadSidebarSections = loadSidebarSections;
TwitchX.saveSidebarSections = saveSidebarSections;
TwitchX.expandSidebarSectionForLogin = expandSidebarSectionForLogin;
TwitchX.getSidebarGroups = getSidebarGroups;
TwitchX.applySidebarLayout = applySidebarLayout;
TwitchX.getSidebarSectionMeta = getSidebarSectionMeta;
TwitchX.createSidebarItem = createSidebarItem;
TwitchX.createSidebarSection = createSidebarSection;
TwitchX.updateSidebarItem = updateSidebarItem;
TwitchX.createRailAvatar = createRailAvatar;
TwitchX.renderRail = renderRail;
TwitchX.renderSidebar = renderSidebar;
TwitchX.updateSidebarScrollShadow = updateSidebarScrollShadow;
TwitchX.initSidebarScrollShadow = initSidebarScrollShadow;
TwitchX._updateNotifBadges = _updateNotifBadges;
TwitchX._clearNotifBadges = _clearNotifBadges;
