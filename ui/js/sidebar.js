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
  const onlineHeaderHeight = onlineSection.querySelector('.section-head').offsetHeight;
  const offlineHeaderHeight = offlineSection.querySelector('.section-head').offsetHeight;

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
    // .channel-item: 40px live rows, 32px offline rows (sidebar.css).
    const offlineRowHeight = 32;
    offlineReservedHeight = Math.max(
      offlineHeaderHeight + 24,
      offlineHeaderHeight + (offlineMinRows * offlineRowHeight)
    );
  }

  const onlineMaxHeight = Math.max(
    onlineHeaderHeight + 80,
    listHeight - offlineReservedHeight - sectionGap
  );
  const onlineTargetHeight = Math.min(onlineNaturalHeight, onlineMaxHeight);

  setVar(onlineSection, '--section-height', onlineTargetHeight + 'px');
  setVar(onlineSection, '--section-min-height', onlineTargetHeight + 'px');

  if (!offlineCollapsed) {
    setVar(offlineSection, '--section-min-height', Math.min(
      Math.max(offlineReservedHeight, offlineHeaderHeight + 64),
      Math.max(listHeight - onlineTargetHeight - sectionGap, offlineHeaderHeight)
    ) + 'px');
  }
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

function _sidebarItemLabel(login, platform, stream) {
  return stream
    ? login + ', live, ' + Number(stream.viewers || 0).toLocaleString() + ' viewers'
    : login + ', offline on ' + TwitchX.platformLabel(platform);
}

// Avatar with the platform dot in its lower-right corner (row and rail).
function _createSidebarAvatar(key, platform, imgClass) {
  const wrap = document.createElement('span');
  wrap.className = 'sidebar-avatar';
  const avatar = document.createElement('img');
  avatar.className = imgClass;
  if (TwitchX.state.avatars[key]) {
    avatar.src = TwitchX.state.avatars[key];
  }
  avatar.alt = '';
  avatar.onerror = function() {
    avatar.classList.add('is-empty');
  };
  wrap.appendChild(avatar);
  const dot = document.createElement('span');
  dot.className = 'platform-dot ' + platform;
  wrap.appendChild(dot);
  return wrap;
}

// Right edge of a live row: viewers, or a small equalizer while it plays.
function _syncSidebarItemEnd(item, stream, isWatching) {
  let end = item.querySelector('.channel-end');
  if (!stream) {
    if (end) end.remove();
    return;
  }
  if (!end) {
    end = document.createElement('span');
    end.className = 'channel-end';
    item.insertBefore(end, item.querySelector('.notif-dot'));
  }
  if (isWatching) {
    if (!end.querySelector('.watching-eq')) {
      const eq = document.createElement('span');
      eq.className = 'watching-eq';
      eq.setAttribute('aria-hidden', 'true');
      for (let i = 0; i < 3; i++) eq.appendChild(document.createElement('span'));
      end.replaceChildren(eq);
    }
    end.title = 'Watching';
    return;
  }
  const viewers = TwitchX.formatViewers(stream.viewers);
  if (end.textContent !== viewers || end.querySelector('.watching-eq')) end.textContent = viewers;
  end.title = Number(stream.viewers || 0).toLocaleString() + ' viewers';
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
  item.setAttribute('aria-label', _sidebarItemLabel(login, platform, stream));

  const dragHandle = document.createElement('span');
  dragHandle.className = 'drag-handle';
  dragHandle.setAttribute('aria-hidden', 'true');
  item.appendChild(dragHandle);

  item.appendChild(_createSidebarAvatar(key, platform, 'avatar'));

  const copy = document.createElement('div');
  copy.className = 'channel-copy';

  const name = document.createElement('span');
  name.className = 'name';
  const favMeta = TwitchX.getFavoriteMeta(login, platform) || {};
  name.textContent = (stream && stream.display_name) || favMeta.display_name || entry.display_name || login;
  copy.appendChild(name);

  const meta = document.createElement('span');
  meta.className = 'channel-meta';
  meta.textContent = isLive ? (stream.game || 'Live now') : '';
  copy.appendChild(meta);
  item.appendChild(copy);

  // Notification dot for new live channels
  var notifDot = document.createElement('span');
  notifDot.className = 'notif-dot';
  notifDot.setAttribute('aria-label', 'New');
  item.appendChild(notifDot);

  _syncSidebarItemEnd(item, stream, isWatching);

  _setupSidebarTooltip(item, entry, streamMap);

  item.addEventListener('click', function() { TwitchX.selectChannel(login, platform); TwitchX.doWatch(); });
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

function createSidebarSection(sectionKey, title, entries, streamMap) {
  const isCollapsed = !!TwitchX.state.sidebarSections[sectionKey];

  const section = document.createElement('section');
  section.className = 'sidebar-section ' + sectionKey + (isCollapsed ? ' collapsed' : '');
  section.dataset.section = sectionKey;

  // "Live  9": the label toggles the section; the count (and, for Live, the
  // new-live badge) sit outside the button so the badge stays clickable.
  const head = document.createElement('div');
  head.className = 'section-head';

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

  const titleEl = document.createElement('span');
  titleEl.className = 'section-title';
  titleEl.textContent = title;
  toggle.appendChild(titleEl);

  const chevron = document.createElement('span');
  chevron.className = 'section-chevron';
  TwitchX.setIconOnly(chevron, 'chevron-down', 12);
  toggle.appendChild(chevron);
  head.appendChild(toggle);

  const count = document.createElement('span');
  count.className = 'section-count';
  count.textContent = String(entries.length);
  head.appendChild(count);

  section.appendChild(head);

  const body = document.createElement('div');
  body.className = 'section-body';
  body.id = 'sidebar-section-body-' + sectionKey;
  body.dataset.group = sectionKey === 'online' || sectionKey === 'offline' ? '' : null;

  if (entries.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'section-empty';
    empty.textContent = sectionKey === 'online'
      ? 'No one is live right now'
      : 'No offline channels';
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

  item.classList.toggle('live', isLive);
  item.setAttribute('aria-label', _sidebarItemLabel(login, platform, stream));
  if (isSelected !== item.classList.contains('selected')) {
    item.classList.toggle('selected', isSelected);
    item.setAttribute('aria-pressed', String(isSelected));
  }

  var isWatching = _matchWatching(login, key);
  item.classList.toggle('watching', isWatching);

  const nameEl = item.querySelector('.name');
  const favMeta = TwitchX.getFavoriteMeta(login, platform) || {};
  const newName = (stream && stream.display_name) || favMeta.display_name || entry.display_name || login;
  if (nameEl.textContent !== newName) {
    nameEl.textContent = newName;
  }

  const metaEl = item.querySelector('.channel-meta');
  const newMeta = isLive ? (stream.game || 'Live now') : '';
  if (metaEl.textContent !== newMeta) {
    metaEl.textContent = newMeta;
  }

  const avatar = item.querySelector('.avatar');
  const newAvatar = TwitchX.state.avatars[key];
  if (avatar && newAvatar && avatar.src !== newAvatar) {
    avatar.src = newAvatar;
  }

  _syncSidebarItemEnd(item, stream, isWatching);
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

  item.appendChild(_createSidebarAvatar(key, platform, 'rail-av-img'));

  var newDot = document.createElement('span');
  newDot.className = 'rail-notif-dot' + (isNewLive ? ' visible' : '');
  newDot.setAttribute('aria-label', 'New live channel');
  item.appendChild(newDot);

  _setupSidebarTooltip(item, entry, streamMap);

  item.addEventListener('click', function() { TwitchX.selectChannel(login, platform); TwitchX.doWatch(); });
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
      var newSrc = TwitchX.state.avatars[key];
      if (img && newSrc && img.src !== newSrc) {
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

  const title = document.createElement('span');
  title.className = 'section-title';
  title.textContent = name;
  header.appendChild(title);

  const chevron = document.createElement('span');
  chevron.className = 'section-chevron';
  TwitchX.setIconOnly(chevron, 'chevron-down', 12);
  header.appendChild(chevron);

  const countEl = document.createElement('span');
  countEl.className = 'section-count';
  countEl.textContent = String(count);
  header.appendChild(countEl);

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

  if (TwitchX.getFavoriteEntries().length === 0) {
    list.replaceChildren();
    updatePlatformStatusDots();
    return;
  }

  sidebarFrag.appendChild(
    createSidebarSection(
      'online',
      'Live',
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
  updateNavLiveCount();
  if (TwitchX.updateAccountChip) TwitchX.updateAccountChip();
}

/* ── Sidebar navigation ─────────────────────────────────── */
// Following / Browse / Multi-view. The channel profile and the player keep
// whichever item they were opened from, so switchView only reports the views
// that own an item.
const NAV_FOR_VIEW = {
  'stream-grid': 'following',
  'empty-state': 'following',
  'browse-view': 'browse',
  'multistream-view': 'multiview',
};

function setActiveNav(name) {
  document.querySelectorAll('#sidebar-nav .sidebar-nav-item').forEach(function(item) {
    if (item.dataset.nav === name) item.setAttribute('aria-current', 'page');
    else item.removeAttribute('aria-current');
  });
}

function syncNavForView(viewId) {
  if (Object.prototype.hasOwnProperty.call(NAV_FOR_VIEW, viewId)) setActiveNav(NAV_FOR_VIEW[viewId]);
}

function _isViewActive(id) {
  var el = document.getElementById(id);
  return !!el && el.classList.contains('view-active');
}

function showFollowingView() {
  if (TwitchX.multiState.open) { TwitchX.closeMultistreamView(); return; }
  if (_isViewActive('player-view')) { TwitchX.hidePlayerView(); return; }
  if (_isViewActive('channel-view')) {
    TwitchX.channelViewSource = 'grid';
    TwitchX.hideChannelView();
    return;
  }
  if (_isViewActive('browse-view')) TwitchX.hideBrowseView();
}

function navigateTo(name) {
  if (name === 'following') { showFollowingView(); return; }
  if (name === 'browse') {
    if (_isViewActive('browse-view')) return;
    if (TwitchX.multiState.open) TwitchX.closeMultistreamView();
    // Browse does not stop the player by itself; leaving it playing behind
    // another view would keep its audio running.
    if (_isViewActive('player-view')) TwitchX.hidePlayerView(true);
    TwitchX.showBrowseView();
    return;
  }
  if (name === 'multiview' && !TwitchX.multiState.open) TwitchX.openMultistreamView();
}

TwitchX._bindSidebarNavEvents = function() {
  document.querySelectorAll('#sidebar-nav .sidebar-nav-item').forEach(function(item) {
    item.addEventListener('click', function() { navigateTo(item.dataset.nav); });
  });
};

function updateNavLiveCount() {
  var el = document.getElementById('sidebar-nav-live-count');
  if (!el) return;
  var count = TwitchX.state.liveSet ? TwitchX.state.liveSet.size : 0;
  el.textContent = count > 0 ? String(count) : '';
}

TwitchX.setActiveNav = setActiveNav;
TwitchX.syncNavForView = syncNavForView;
TwitchX.showFollowingView = showFollowingView;
TwitchX.navigateTo = navigateTo;

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
  // Lives in the Live section label; the rail shows per-avatar dots instead.
  var header = document.querySelector('#channel-list .sidebar-section.online .section-head');
  var notifBadge = header ? header.querySelector('.notif-badge') : null;
  if (header && !notifBadge) {
    notifBadge = document.createElement('button');
    notifBadge.type = 'button';
    notifBadge.className = 'notif-badge';
    notifBadge.addEventListener('click', function(e) {
      e.stopPropagation();
      _clearNotifBadges();
    });
    header.insertBefore(notifBadge, header.querySelector('.section-count'));
  }
  if (notifBadge && badgeLogins.length > 0) {
    notifBadge.textContent = String(badgeLogins.length);
    notifBadge.title = 'Dismiss ' + badgeLogins.length + ' new live notification' +
      (badgeLogins.length === 1 ? '' : 's');
    notifBadge.setAttribute('aria-label', notifBadge.title);
    notifBadge.classList.add('visible');
  } else if (notifBadge) {
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
