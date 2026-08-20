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

function expandSidebarSectionForLogin(login, key) {
  if (!login && !key) return false;
  const channelKey = key || TwitchX.channelKey(login, TwitchX.getChannelPlatform(login));
  const sectionKey = TwitchX.state.liveSet.has(channelKey) ? 'online' : 'offline';
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
    streamMap[TwitchX.channelKey(stream.login, stream.platform || 'twitch')] = stream;
  });

  const entries = TwitchX.getFavoriteEntries();
  entries.forEach(function(entry) {
    const meta = TwitchX.state.favoritesMeta[entry.key] || {};
    entry.group = meta.group || null;
    entry.order = typeof meta.order === 'number' ? meta.order : 0;
  });

  const online = entries
    .filter(function(entry) { return TwitchX.state.liveSet.has(entry.key) && !entry.group; })
    .sort(function(a, b) {
      const diff = a.order - b.order;
      if (diff !== 0) return diff;
      const viewerDiff = (streamMap[b.key] ? streamMap[b.key].viewers : 0) - (streamMap[a.key] ? streamMap[a.key].viewers : 0);
      return viewerDiff !== 0 ? viewerDiff : a.display_name.localeCompare(b.display_name);
    });

  const offline = entries
    .filter(function(entry) { return !TwitchX.state.liveSet.has(entry.key) && !entry.group; })
    .sort(function(a, b) {
      const diff = a.order - b.order;
      if (diff !== 0) return diff;
      return a.display_name.localeCompare(b.display_name);
    });

  const customGroups = {};
  entries.forEach(function(entry) {
    if (!entry.group) return;
    if (!customGroups[entry.group]) customGroups[entry.group] = [];
    customGroups[entry.group].push(entry);
  });
  Object.keys(customGroups).forEach(function(groupName) {
    customGroups[groupName].sort(function(a, b) {
      const diff = a.order - b.order;
      return diff !== 0 ? diff : a.display_name.localeCompare(b.display_name);
    });
  });

  return {
    online: online,
    offline: offline,
    custom: customGroups,
    streamMap: streamMap,
  };
}

function applySidebarLayout(groups) {
  const sidebar = document.getElementById('sidebar');
  if (sidebar && sidebar.classList.contains('collapsed-sidebar')) return;
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

  function setVar(el, name, value) {
    if (value === '' || value === null || value === undefined) {
      el.style.removeProperty(name);
    } else {
      el.style.setProperty(name, value);
    }
  }

  setVar(onlineSection, '--section-flex', '0 0 auto');
  setVar(onlineSection, '--section-height', '');
  setVar(onlineSection, '--section-min-height', onlineCollapsed ? onlineHeaderHeight + 'px' : '');

  setVar(offlineSection, '--section-height', '');
  setVar(offlineSection, '--section-min-height', offlineHeaderHeight + 'px');
  setVar(offlineSection, '--section-flex', offlineCollapsed ? '0 0 auto' : '1 1 0px');

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

  setVar(onlineSection, '--section-height', onlineTargetHeight + 'px');
  setVar(onlineSection, '--section-min-height', onlineTargetHeight + 'px');

  if (!offlineCollapsed) {
    setVar(offlineSection, '--section-min-height', Math.min(
      Math.max(offlineReservedHeight, offlineHeaderHeight + 72),
      Math.max(listHeight - onlineTargetHeight - sectionGap, offlineHeaderHeight)
    ) + 'px');
  }
}

function getSidebarSectionMeta(sectionKey, entries, streamMap) {
  if (sectionKey === 'online') {
    if (entries.length === 0) {
      return 'Waiting for the next live channel';
    }
    const totalViewers = entries.reduce(function(sum, entry) {
      return sum + ((streamMap[entry.key] && streamMap[entry.key].viewers) || 0);
    }, 0);
    return entries.length + ' live now • ' + TwitchX.formatViewers(totalViewers) + ' combined viewers';
  }
  if (entries.length === 0) {
    return 'Saved channels appear here';
  }
  return entries.length + ' saved • sorted A to Z';
}

function _matchWatching(login, key) {
  if (TwitchX.state.watchingChannelKey && key) {
    return TwitchX.state.watchingChannelKey === key;
  }
  if (!TwitchX.state.watchingChannel) return false;
  return TwitchX.state.watchingChannel === login;
}

function hideSidebarTooltip() {
  var tooltip = document.getElementById('sidebar-tooltip');
  if (!tooltip) return;
  tooltip.classList.remove('visible');
  tooltip.classList.add('hidden');
}

function _setupSidebarTooltip(item, entry, streamMap) {
  let tooltipTimer = null;
  function showTooltip(e) {
    var tooltip = document.getElementById('sidebar-tooltip');
    if (!tooltip) return;
    // A poll can replace the row while the 180ms hover timer is pending. The
    // detached node reports a zero rect, which used to park the tooltip in the
    // top-left corner with no mouseleave left to dismiss it.
    if (!item.isConnected) return;
    var stream = streamMap[entry.key];
    var thumb = document.getElementById('tooltip-thumb');
    var title = document.getElementById('tooltip-title');
    var game = document.getElementById('tooltip-game');
    var viewers = document.getElementById('tooltip-viewers');
    if (thumb && stream && stream.thumbnail_url) {
      thumb.src = stream.thumbnail_url;
      thumb.classList.remove('hidden');
    } else if (thumb) {
      thumb.classList.add('hidden');
    }
    if (title) title.textContent = (stream && stream.display_name) || entry.display_name || entry.login;
    if (game) {
      game.textContent = stream
        ? (stream.game || (stream.title ? stream.title : 'Live now'))
        : 'Offline on ' + TwitchX.platformLabel(entry.platform);
    }
    if (viewers) {
      viewers.textContent = stream
        ? TwitchX.formatViewers(stream.viewers) + ' viewers'
        : TwitchX.platformLabel(entry.platform);
      viewers.classList.toggle('offline', !stream);
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
  item.addEventListener('mouseenter', function(e) {
    tooltipTimer = setTimeout(function() {
      tooltipTimer = null;
      showTooltip(e);
    }, 180);
  });
  item.addEventListener('mousemove', function(e) {
    if (tooltipTimer) return;
    showTooltip(e);
  });
  item.addEventListener('mouseleave', function() {
    if (tooltipTimer) { clearTimeout(tooltipTimer); tooltipTimer = null; }
    hideSidebarTooltip();
  });
}

function createSidebarItem(entry, streamMap) {
  const login = entry.login;
  const key = entry.key;
  const platform = entry.platform;
  const stream = streamMap[key] || null;
  const isLive = !!stream;
  const isSelected = TwitchX.state.selectedChannelKey === key;
  const isWatching = _matchWatching(login, key);

  const item = document.createElement('div');
  item.className = 'channel-item' + (isLive ? ' live' : '') + (isSelected ? ' selected' : '') + (isWatching ? ' watching' : '');
  item.dataset.login = login;
  item.dataset.key = key;
  item.dataset.platform = platform;
  item.tabIndex = 0;
  item.setAttribute('role', 'button');
  item.setAttribute('aria-pressed', String(isSelected));
  item.setAttribute(
    'aria-label',
    isLive
      ? login + ', live, ' + Number(stream.viewers || 0).toLocaleString() + ' viewers'
      : login + ', offline on ' + TwitchX.platformLabel(platform)
  );

  const dragHandle = document.createElement('span');
  dragHandle.className = 'drag-handle';
  dragHandle.setAttribute('aria-hidden', 'true');
  item.appendChild(dragHandle);

  const bar = document.createElement('div');
  bar.className = 'accent-bar';
  item.appendChild(bar);

  const dot = document.createElement('span');
  dot.className = 'live-dot';
  TwitchX.setIconOnly(dot, 'live-dot', 10);
  item.appendChild(dot);

  const avatar = document.createElement('img');
  avatar.className = 'avatar';
  if (TwitchX.state.avatars[key]) {
    avatar.src = TwitchX.state.avatars[key];
  }
  avatar.alt = '';
  avatar.onerror = function() {
    avatar.classList.add('is-empty');
  };
  item.appendChild(avatar);

  const copy = document.createElement('div');
  copy.className = 'channel-copy';

  const name = document.createElement('span');
  name.className = 'name';
  const favMeta = TwitchX.getFavoriteMeta(login, platform) || {};
  name.textContent = (stream && stream.display_name) || favMeta.display_name || entry.display_name || login;
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

  _setupSidebarTooltip(item, entry, streamMap);

  item.addEventListener('click', function() { TwitchX.selectChannel(login, platform); });
  item.addEventListener('dblclick', function() { TwitchX.selectChannel(login, platform); TwitchX.doWatch(); });
  item.addEventListener('contextmenu', function(e) { TwitchX.showSidebarContextMenu(e, login, platform); });
  item.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      TwitchX.selectChannel(login, platform);
    }
  });

  // Drag to reorder or to multistream
  item.draggable = true;
  item.addEventListener('dragstart', function(e) {
    e.dataTransfer.setData('text/plain', JSON.stringify({ login: login, platform: platform, key: key }));
    e.dataTransfer.effectAllowed = 'move';
    item.classList.add('dragging');
  });
  item.addEventListener('dragend', function() {
    item.classList.remove('dragging');
  });

  return item;
}

function createSidebarSection(sectionKey, title, metaText, entries, streamMap) {
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
  TwitchX.setIconOnly(chevron, 'chevron-right', 12);
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
  count.textContent = String(entries.length);
  toggle.appendChild(count);

  section.appendChild(toggle);

  const body = document.createElement('div');
  body.className = 'section-body';
  body.id = 'sidebar-section-body-' + sectionKey;
  body.dataset.group = sectionKey === 'online' || sectionKey === 'offline' ? '' : null;

  if (entries.length === 0) {
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
    entries.forEach(function(entry) {
      body.appendChild(createSidebarItem(entry, streamMap));
    });
  }

  section.appendChild(body);
  _bindSidebarDropZone(body);
  return section;
}

function updateSidebarItem(item, entry, streamMap) {
  const login = entry.login;
  const key = entry.key;
  const platform = entry.platform;
  const stream = streamMap[key] || null;
  const isLive = !!stream;
  const isSelected = TwitchX.state.selectedChannelKey === key;

  const wasLive = item.classList.contains('live');
  const wasSelected = item.classList.contains('selected');

  if (isLive !== wasLive) {
    item.classList.toggle('live', isLive);
    item.setAttribute('aria-label',
      isLive
        ? login + ', live, ' + Number(stream.viewers || 0).toLocaleString() + ' viewers'
        : login + ', offline on ' + TwitchX.platformLabel(platform));
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
  var isWatching = _matchWatching(login, key);
  item.classList.toggle('watching', isWatching);

  const nameEl = item.querySelector('.name');
  const favMeta = TwitchX.getFavoriteMeta(login, platform) || {};
  const newName = (stream && stream.display_name) || favMeta.display_name || entry.display_name || login;
  if (nameEl.textContent !== newName) {
    nameEl.textContent = newName;
  }

  const metaEl = item.querySelector('.channel-meta');
  const newMeta = isLive ? TwitchX.truncate(stream.game || 'Live now', 24) : 'Offline';
  if (metaEl.textContent !== newMeta) {
    metaEl.textContent = newMeta;
  }

  const avatar = item.querySelector('.avatar');
  const newAvatar = TwitchX.state.avatars[key] || '';
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

function createRailAvatar(entry, isLive, streamMap) {
  var login = entry.login;
  var key = entry.key;
  var platform = entry.platform;
  var item = document.createElement('div');
  var isWatching = _matchWatching(login, key);
  var isSelected = TwitchX.state.selectedChannelKey === key;
  var isNewLive = TwitchX._notifBadgeLogins && TwitchX._notifBadgeLogins.indexOf(key) !== -1;
  var stream = streamMap[key] || null;
  item.className = 'rail-avatar' +
    (isLive ? ' live' : ' offline') +
    (isSelected ? ' selected' : '') +
    (isWatching ? ' watching' : '');
  item.dataset.login = login;
  item.dataset.key = key;
  item.dataset.platform = platform;
  item.tabIndex = 0;
  item.setAttribute('role', 'button');
  item.setAttribute('aria-pressed', String(isSelected));
  item.setAttribute(
    'aria-label',
    isLive
      ? login + ', live on ' + TwitchX.platformLabel(platform) + ', ' + Number((stream && stream.viewers) || 0).toLocaleString() + ' viewers'
      : login + ', offline on ' + TwitchX.platformLabel(platform)
  );

  var img = document.createElement('img');
  img.className = 'rail-av-img';
  img.alt = '';
  if (TwitchX.state.avatars[key]) {
    img.src = TwitchX.state.avatars[key];
  }
  img.onerror = function() {
    img.classList.add('is-empty');
  };
  item.appendChild(img);

  if (isLive) {
    var ring = document.createElement('div');
    ring.className = 'rail-av-ring';
    item.appendChild(ring);

    var dot = document.createElement('div');
    dot.className = 'rail-av-dot';
    item.appendChild(dot);
  }

  var newDot = document.createElement('span');
  newDot.className = 'rail-notif-dot' + (isNewLive ? ' visible' : '');
  newDot.setAttribute('aria-label', 'New live channel');
  item.appendChild(newDot);

  _setupSidebarTooltip(item, entry, streamMap);

  item.addEventListener('click', function() { TwitchX.selectChannel(login, platform); });
  item.addEventListener('dblclick', function() { TwitchX.selectChannel(login, platform); TwitchX.doWatch(); });
  item.addEventListener('contextmenu', function(e) { TwitchX.showSidebarContextMenu(e, login, platform); });
  item.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      TwitchX.selectChannel(login, platform);
    }
  });

  return item;
}

function renderRail(groups) {
  hideSidebarTooltip();
  var list = document.getElementById('channel-list');
  var liveLogins = groups.online;
  var offlineLogins = groups.offline;
  if (
    liveLogins.length === 0 &&
    offlineLogins.length === 0 &&
    !TwitchX.state.favoritesHydrated &&
    !TwitchX.state.streamsLoaded
  ) {
    return;
  }

  // If #channel-list still has expanded-sidebar DOM, skip diff and force full rebuild
  var hasStaleDom = !!list.querySelector('.sidebar-section');

  // In-place update if membership unchanged (and no stale section DOM to clear)
  var existingLive = Array.from(list.querySelectorAll('.rail-avatar.live'))
    .map(function(el) { return el.dataset.key; });
  var existingOffline = Array.from(list.querySelectorAll('.rail-avatar.offline'))
    .map(function(el) { return el.dataset.key; });

  var liveChanged = existingLive.length !== liveLogins.length ||
    liveLogins.some(function(entry, i) { return existingLive[i] !== entry.key; });
  var offlineChanged = existingOffline.length !== offlineLogins.length ||
    offlineLogins.some(function(entry, i) { return existingOffline[i] !== entry.key; });

  if (!hasStaleDom && !liveChanged && !offlineChanged) {
    list.querySelectorAll('.rail-avatar').forEach(function(el) {
      var key = el.dataset.key;
      var platform = el.dataset.platform || TwitchX.getChannelPlatform(el.dataset.login, key);
      var stream = groups.streamMap[key] || null;

      // Sync avatar image
      var img = el.querySelector('.rail-av-img');
      var newSrc = TwitchX.state.avatars[key] || '';
      if (img && img.src !== newSrc) {
        img.src = newSrc;
      }

      // Sync selected state
      var isSelected = TwitchX.state.selectedChannelKey === key;
      el.classList.toggle('selected', isSelected);
      el.setAttribute('aria-pressed', String(isSelected));
      el.setAttribute(
        'aria-label',
        stream
          ? el.dataset.login + ', live on ' + TwitchX.platformLabel(platform) + ', ' + Number(stream.viewers || 0).toLocaleString() + ' viewers'
          : el.dataset.login + ', offline on ' + TwitchX.platformLabel(platform)
      );

      // Sync watching state
      var isWatching = _matchWatching(el.dataset.login, key);
      el.classList.toggle('watching', isWatching);

      var notif = el.querySelector('.rail-notif-dot');
      var isNewLive = TwitchX._notifBadgeLogins && TwitchX._notifBadgeLogins.indexOf(key) !== -1;
      if (notif) notif.classList.toggle('visible', !!isNewLive);
    });
    return;
  }

  // Full rebuild
  while (list.firstChild) list.removeChild(list.firstChild);

  liveLogins.forEach(function(entry) {
    list.appendChild(createRailAvatar(entry, true, groups.streamMap));
  });

  if (liveLogins.length > 0 && offlineLogins.length > 0) {
    var divider = document.createElement('div');
    divider.className = 'rail-divider';
    list.appendChild(divider);
  }

  offlineLogins.forEach(function(entry) {
    list.appendChild(createRailAvatar(entry, false, groups.streamMap));
  });
}

function createSidebarGroupHeader(name, count, collapsed) {
  const header = document.createElement('button');
  header.className = 'group-header' + (collapsed ? ' collapsed' : '');
  header.type = 'button';
  header.dataset.group = name;
  header.setAttribute('aria-expanded', String(!collapsed));
  header.setAttribute('aria-controls', sidebarGroupBodyId(name));

  const copy = document.createElement('div');
  copy.className = 'section-copy';

  const title = document.createElement('div');
  title.className = 'section-title';
  title.textContent = name;
  copy.appendChild(title);

  const meta = document.createElement('div');
  meta.className = 'section-meta';
  meta.textContent = count + ' channel' + (count !== 1 ? 's' : '');
  copy.appendChild(meta);

  header.appendChild(copy);

  const chevron = document.createElement('span');
  chevron.className = 'group-chevron';
  TwitchX.setIconOnly(chevron, 'chevron-right', 12);
  header.appendChild(chevron);

  header.addEventListener('click', function() {
    const key = 'group:' + name;
    TwitchX.state.sidebarSections[key] = !TwitchX.state.sidebarSections[key];
    saveSidebarSections();
    renderSidebar();
  });
  header.addEventListener('contextmenu', function(e) {
    e.preventDefault();
    if (TwitchX.showGroupContextMenu) TwitchX.showGroupContextMenu(e, name);
  });

  return header;
}

function renderSidebarGroupBody(name, entries, streamMap) {
  const body = document.createElement('div');
  body.className = 'group-items';
  body.id = sidebarGroupBodyId(name);
  body.dataset.group = name;

  entries.forEach(function(entry) {
    body.appendChild(createSidebarItem(entry, streamMap));
  });

  _bindSidebarDropZone(body);
  return body;
}

function sidebarGroupBodyId(name) {
  return 'sidebar-group-body-' + String(name).replace(/[^a-zA-Z0-9_-]/g, '-');
}

function _bindSidebarDropZone(container) {
  container.addEventListener('dragover', function(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    const target = e.target.closest('.channel-item');
    if (target && !target.classList.contains('drag-over')) {
      container.querySelectorAll('.channel-item').forEach(function(el) { el.classList.remove('drag-over'); });
      target.classList.add('drag-over');
    }
  });

  container.addEventListener('dragleave', function(e) {
    const target = e.target.closest('.channel-item');
    if (target && !target.contains(e.relatedTarget)) {
      target.classList.remove('drag-over');
    }
  });

  container.addEventListener('drop', function(e) {
    e.preventDefault();
    container.querySelectorAll('.channel-item').forEach(function(el) { el.classList.remove('drag-over'); });
    var data;
    try {
      data = JSON.parse(e.dataTransfer.getData('text/plain'));
    } catch (err) {
      return;
    }
    if (!data || !data.key) return;

    const target = e.target.closest('.channel-item');
    const groupName = container.dataset.group || null;
    const items = Array.from(container.querySelectorAll('.channel-item'));
    let insertIndex = items.length;
    if (target) {
      insertIndex = items.indexOf(target);
    }

    TwitchX.moveFavoriteInGroup(data.key, groupName, insertIndex);
  });
}

TwitchX.moveFavoriteInGroup = function(key, groupName, insertIndex) {
  const allEntries = TwitchX.getFavoriteEntries();
  const moving = allEntries.find(function(e) { return e.key === key; });
  if (!moving) return;

  const targetGroupEntries = allEntries.filter(function(e) {
    const g = TwitchX.getFavoriteGroup(e.login, e.platform);
    return g === groupName;
  });

  const currentIdx = targetGroupEntries.findIndex(function(e) { return e.key === key; });
  if (currentIdx !== -1) targetGroupEntries.splice(currentIdx, 1);

  const meta = TwitchX.state.favoritesMeta[key] || {};
  meta.group = groupName;

  targetGroupEntries.splice(Math.min(insertIndex, targetGroupEntries.length), 0, {
    login: moving.login,
    platform: moving.platform,
    key: key,
    display_name: moving.display_name,
    group: groupName,
    order: 0,
  });

  const payload = [];
  const groupBuckets = {};

  allEntries.forEach(function(e) {
    const g = e.key === key ? groupName : TwitchX.getFavoriteGroup(e.login, e.platform);
    if (!groupBuckets[g]) groupBuckets[g] = [];
    groupBuckets[g].push(e);
  });

  Object.keys(groupBuckets).forEach(function(g) {
    const list = groupBuckets[g];
    if (g === groupName) {
      targetGroupEntries.forEach(function(e, idx) {
        payload.push({ key: e.key, group: g, order: idx });
      });
    } else {
      list.forEach(function(e, idx) {
        payload.push({ key: e.key, group: g, order: idx });
      });
    }
  });

  if (TwitchX.api) TwitchX.api.reorder_favorites(JSON.stringify(payload));
  TwitchX._applyFavoriteOrder(payload);
  TwitchX.renderSidebar();
};

TwitchX._applyFavoriteOrder = function(payload) {
  payload.forEach(function(item) {
    const meta = TwitchX.state.favoritesMeta[item.key];
    if (meta) {
      meta.group = item.group;
      meta.order = item.order;
    }
  });
};

TwitchX.createFavoriteGroup = function(name) {
  if (!name || TwitchX.SYSTEM_FAVORITE_GROUPS.indexOf(name) !== -1) return;
  const payload = [];
  TwitchX.getFavoriteEntries().forEach(function(e, idx) {
    payload.push({ key: e.key, group: TwitchX.getFavoriteGroup(e.login, e.platform), order: idx });
  });
  if (TwitchX.api) TwitchX.api.reorder_favorites(JSON.stringify(payload));
  TwitchX._applyFavoriteOrder(payload);
  TwitchX.renderSidebar();
};

TwitchX.renameFavoriteGroup = function(oldName, newName) {
  if (!oldName || !newName || TwitchX.SYSTEM_FAVORITE_GROUPS.indexOf(newName) !== -1) return;
  const payload = [];
  TwitchX.getFavoriteEntries().forEach(function(e) {
    var group = TwitchX.getFavoriteGroup(e.login, e.platform);
    if (group === oldName) group = newName;
    payload.push({ key: e.key, group: group, order: e.order || 0 });
  });
  if (TwitchX.api) TwitchX.api.reorder_favorites(JSON.stringify(payload));
  TwitchX._applyFavoriteOrder(payload);
  TwitchX.renderSidebar();
};

TwitchX.deleteFavoriteGroup = function(name) {
  if (!name || TwitchX.SYSTEM_FAVORITE_GROUPS.indexOf(name) !== -1) return;
  const payload = [];
  TwitchX.getFavoriteEntries().forEach(function(e) {
    var group = TwitchX.getFavoriteGroup(e.login, e.platform);
    if (group === name) group = null;
    payload.push({ key: e.key, group: group, order: e.order || 0 });
  });
  if (TwitchX.api) TwitchX.api.reorder_favorites(JSON.stringify(payload));
  TwitchX._applyFavoriteOrder(payload);
  TwitchX.renderSidebar();
};

TwitchX.moveFavoriteToGroup = function(key, groupName) {
  const meta = TwitchX.state.favoritesMeta[key];
  if (!meta) return;
  meta.group = groupName;
  const payload = [];
  TwitchX.getFavoriteEntries().forEach(function(e, idx) {
    payload.push({ key: e.key, group: TwitchX.getFavoriteGroup(e.login, e.platform), order: idx });
  });
  if (TwitchX.api) TwitchX.api.reorder_favorites(JSON.stringify(payload));
  TwitchX._applyFavoriteOrder(payload);
  TwitchX.renderSidebar();
};

function renderSidebar() {
  // The hovered row is about to be replaced, and a destroyed element never
  // fires mouseleave — the tooltip would hang over the UI until the next hover.
  hideSidebarTooltip();
  var _sidebar = document.getElementById('sidebar');
  if (_sidebar && _sidebar.classList.contains('collapsed-sidebar')) {
    renderRail(getSidebarGroups());
    return;
  }

  const list = document.getElementById('channel-list');
  const groups = getSidebarGroups();
  if (
    TwitchX.state.favorites.length === 0 &&
    !TwitchX.state.favoritesHydrated &&
    !TwitchX.state.streamsLoaded
  ) {
    return;
  }

  // NOTE: no expandSidebarSectionForLogin() here — selectChannel() owns that.
  // Calling it per render re-opened the selected channel's section on every poll.
  const sidebarFrag = document.createDocumentFragment();

  function updateFavoritesCountBadge(count) {
    const badge = document.getElementById('favorites-count-badge');
    if (!badge) return;
    badge.textContent = String(count);
    badge.setAttribute('aria-label', count + ' favorite' + (count === 1 ? '' : 's'));
  }

  if (TwitchX.getFavoriteEntries().length === 0) {
    list.replaceChildren();
    updateFavoritesCountBadge(0);
    updatePlatformStatusDots();
    return;
  }

  const totalCount = groups.online.length + groups.offline.length +
    Object.keys(groups.custom).reduce(function(sum, k) { return sum + groups.custom[k].length; }, 0);
  updateFavoritesCountBadge(totalCount);

  sidebarFrag.appendChild(
    createSidebarSection(
      'online',
      'Online',
      getSidebarSectionMeta('online', groups.online, groups.streamMap),
      groups.online,
      groups.streamMap
    )
  );

  Object.keys(groups.custom).sort().forEach(function(groupName) {
    const entries = groups.custom[groupName];
    const collapsed = !!TwitchX.state.sidebarSections['group:' + groupName];
    const groupEl = document.createElement('div');
    groupEl.className = 'sidebar-group';
    groupEl.appendChild(createSidebarGroupHeader(groupName, entries.length, collapsed));
    if (!collapsed) {
      groupEl.appendChild(renderSidebarGroupBody(groupName, entries, groups.streamMap));
    }
    sidebarFrag.appendChild(groupEl);
  });

  sidebarFrag.appendChild(
    createSidebarSection(
      'offline',
      'Offline',
      getSidebarSectionMeta('offline', groups.offline, groups.streamMap),
      groups.offline,
      groups.streamMap
    )
  );

  list.replaceChildren(sidebarFrag);

  requestAnimationFrame(function() {
    applySidebarLayout(groups);
  });
  initSidebarScrollShadow();
  updatePlatformStatusDots();
}

function updatePlatformStatusDots() {
  var platforms = [
    { key: 'twitch', user: TwitchX.state.currentUser },
    { key: 'kick', user: TwitchX.state.kickUser },
  ];
  if (TwitchX.state.youtubeEnabled) {
    platforms.push({ key: 'youtube', user: TwitchX.state.youtubeUser });
  }
  document.querySelectorAll('.platform-status-dots').forEach(function(container) {
    container.replaceChildren();
    platforms.forEach(function(p) {
      var dot = document.createElement('span');
      dot.className = 'platform-status-dot ' + p.key + (p.user ? ' connected' : '');
      dot.setAttribute('aria-label', p.key + (p.user ? ' connected' : ' not connected'));
      container.appendChild(dot);
    });
  });
}

// Initialize sidebar sections from localStorage on load
TwitchX.state.sidebarSections = loadSidebarSections();

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
  var header = document.getElementById('favorites-header');
  if (!header) return;
  var notifBadge = header.querySelector('.notif-badge');
  if (!notifBadge) {
    notifBadge = document.createElement('button');
    notifBadge.type = 'button';
    notifBadge.className = 'notif-badge';
    notifBadge.addEventListener('click', function(e) {
      e.stopPropagation();
      _clearNotifBadges();
    });
    header.appendChild(notifBadge);
  }
  if (badgeLogins.length > 0) {
    notifBadge.textContent = String(badgeLogins.length);
    notifBadge.title = 'Dismiss ' + badgeLogins.length + ' new live notification' +
      (badgeLogins.length === 1 ? '' : 's');
    notifBadge.setAttribute('aria-label', notifBadge.title);
    notifBadge.classList.add('visible');
  } else {
    notifBadge.classList.remove('visible');
  }
  // Show notif-dot on each new-live item
  var items = document.querySelectorAll('.channel-item');
  items.forEach(function(item) {
    var dot = item.querySelector('.notif-dot');
    if (!dot) return;
    var key = item.dataset.key;
    if (!key) return;
    if (badgeLogins.indexOf(key) !== -1) {
      dot.classList.add('visible');
    } else {
      dot.classList.remove('visible');
    }
  });
  var railItems = document.querySelectorAll('.rail-avatar');
  railItems.forEach(function(item) {
    var dot = item.querySelector('.rail-notif-dot');
    if (!dot) return;
    var key = item.dataset.key;
    if (!key) return;
    dot.classList.toggle('visible', badgeLogins.indexOf(key) !== -1);
  });
}

function _clearNotifBadges() {
  TwitchX._notifBadgeLogins = [];
  _updateNotifBadges();
}

// Drop the badge for one channel — it has been looked at.
function acknowledgeNotifBadge(key) {
  if (!key) return;
  var pending = TwitchX._notifBadgeLogins || [];
  var idx = pending.indexOf(key);
  if (idx === -1) return;
  pending.splice(idx, 1);
  TwitchX._notifBadgeLogins = pending;
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
TwitchX.updatePlatformStatusDots = updatePlatformStatusDots;
TwitchX._updateNotifBadges = _updateNotifBadges;
TwitchX._clearNotifBadges = _clearNotifBadges;
TwitchX.acknowledgeNotifBadge = acknowledgeNotifBadge;
TwitchX.hideSidebarTooltip = hideSidebarTooltip;
