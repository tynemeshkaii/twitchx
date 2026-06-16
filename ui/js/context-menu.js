window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

function closeContextMenu() {
  const menu = document.getElementById('context-menu');
  if (menu) menu.classList.remove('menu-visible');
  TwitchX.ctxChannel = null;
  TwitchX.ctxChannelKey = null;
  if (TwitchX.deactivateFocusTrap) TwitchX.deactivateFocusTrap();
  if (TwitchX._contextReturnFocus && TwitchX._contextReturnFocus.focus) {
    TwitchX._contextReturnFocus.focus();
  }
  TwitchX._contextReturnFocus = null;
  if (TwitchX.focusReturn && TwitchX.focusReturn.restore) TwitchX.focusReturn.restore();
}

function _visibleMenuItems(menu) {
  return Array.from(menu.querySelectorAll('[role="menuitem"]')).filter(function(item) {
    return !item.classList.contains('hidden');
  });
}

function _focusMenuItem(menu, idx) {
  const items = _visibleMenuItems(menu);
  if (items.length === 0) return;
  var next = ((idx % items.length) + items.length) % items.length;
  items.forEach(function(item) { item.tabIndex = -1; });
  items[next].tabIndex = 0;
  items[next].focus();
}

function _positionContextMenu(e) {
  const menu = document.getElementById('context-menu');
  menu.style.left = '0';
  menu.style.top = '0';
  let left = e.clientX;
  let top = e.clientY;
  const mw = menu.offsetWidth;
  const mh = menu.offsetHeight;
  if (left + mw > window.innerWidth - 8) left = window.innerWidth - mw - 8;
  if (top + mh > window.innerHeight - 8) top = window.innerHeight - mh - 8;
  if (left < 0) left = 0;
  if (top < 0) top = 0;
  menu.style.left = left + 'px';
  menu.style.top = top + 'px';
}

function _showMenu(e, login, platform) {
  TwitchX.ctxChannel = login;
  TwitchX.ctxChannelKey = TwitchX.channelKey(login, platform || TwitchX.getChannelPlatform(login));
  TwitchX._contextReturnFocus = document.activeElement;
  const menu = document.getElementById('context-menu');
  menu.classList.remove('menu-visible');
  menu.style.left = '0';
  menu.style.top = '0';
  // Force layout, then position
  menu.offsetHeight;
  _positionContextMenu(e);
  requestAnimationFrame(function() {
    menu.classList.add('menu-visible');
    _focusMenuItem(menu, 0);
  });
}

function _setMenuDisabled(item, disabled, reason) {
  if (!item) return;
  item.classList.toggle('disabled', !!disabled);
  item.setAttribute('aria-disabled', String(!!disabled));
  if (disabled && reason) {
    item.title = reason;
    item.dataset.disabledReason = reason;
  } else {
    item.title = '';
    delete item.dataset.disabledReason;
  }
}

function showContextMenu(e, login, platform) {
  e.preventDefault();
  const ctxPlatform = platform || TwitchX.getChannelPlatform(login);
  const ctxKey = TwitchX.channelKey(login, ctxPlatform);
  _showMenu(e, login, ctxPlatform);
  const menu = document.getElementById('context-menu');
  const favItem = menu.querySelector('[data-action="favorite"]');
  const removeItem = menu.querySelector('[data-action="remove"]');
  if (TwitchX.state.favoritesMeta[ctxKey]) {
    favItem.classList.add('hidden');
    removeItem.classList.remove('hidden');
  } else {
    favItem.classList.remove('hidden');
    removeItem.classList.add('hidden');
  }
  const msItem = menu.querySelector('[data-action="multistream"]');
  const watchItem = menu.querySelector('[data-action="watch"]');
  const externalItem = menu.querySelector('[data-action="watch-external"]');
  const ctxStream = TwitchX.findStreamByKey(ctxKey);
  const isYTContext = ctxPlatform === 'youtube' || (ctxStream && ctxStream.platform === 'youtube');
  _setMenuDisabled(
    watchItem,
    isYTContext,
    'YouTube items from Browse cannot be watched directly here. View the channel or open it in the browser.'
  );
  _setMenuDisabled(
    externalItem,
    isYTContext,
    'External player launch needs a directly resolvable stream URL; YouTube Browse results are channel-based.'
  );
  if (msItem) {
    const allFull = TwitchX.multiState.slots.every(function(s) { return s !== null; });
    _setMenuDisabled(
      msItem,
      allFull || isYTContext,
      allFull
        ? 'All multistream slots are full.'
        : 'YouTube Browse results cannot be added to multistream directly.'
    );
  }
  var pinItem = menu.querySelector('[data-action="pin"]');
  if (pinItem) {
    var ctxPlatForPin = ctxPlatform;
    var alreadyPinned = TwitchX.isPinned(ctxPlatForPin, login);
    TwitchX.setIconText(pinItem, 'pin', 14, alreadyPinned ? 'Unpin' : 'Pin to top');
    pinItem.dataset.pinPlatform = ctxPlatForPin;
  }
}

function showSidebarContextMenu(e, login, platform) {
  e.preventDefault();
  const ctxPlatform = platform || TwitchX.getChannelPlatform(login);
  const ctxKey = TwitchX.channelKey(login, ctxPlatform);
  _showMenu(e, login, ctxPlatform);
  const menu = document.getElementById('context-menu');
  menu.querySelector('[data-action="favorite"]').classList.add('hidden');
  menu.querySelector('[data-action="remove"]').classList.remove('hidden');
  const msItem = menu.querySelector('[data-action="multistream"]');
  const watchItem = menu.querySelector('[data-action="watch"]');
  const externalItem = menu.querySelector('[data-action="watch-external"]');
  const ctxStream = TwitchX.findStreamByKey(ctxKey);
  const isYTContext = ctxPlatform === 'youtube' || (ctxStream && ctxStream.platform === 'youtube');
  _setMenuDisabled(
    watchItem,
    false,
    ''
  );
  _setMenuDisabled(
    externalItem,
    false,
    ''
  );
  if (msItem) {
    const allFull = TwitchX.multiState.slots.every(function(s) { return s !== null; });
    _setMenuDisabled(
      msItem,
      allFull || isYTContext,
      allFull
        ? 'All multistream slots are full.'
        : 'YouTube channels cannot be added to multistream directly from the sidebar.'
    );
  }
  var pinItem = menu.querySelector('[data-action="pin"]');
  if (pinItem) {
    var ctxPlatForPin = ctxPlatform;
    var alreadyPinned = TwitchX.isPinned(ctxPlatForPin, login);
    TwitchX.setIconText(pinItem, 'pin', 14, alreadyPinned ? 'Unpin' : 'Pin to top');
    pinItem.dataset.pinPlatform = ctxPlatForPin;
  }
}

function showGroupContextMenu(e, groupName) {
  TwitchX._ctxGroupName = groupName;
  TwitchX._groupContextReturnFocus = document.activeElement;
  const menu = document.getElementById('group-context-menu');
  if (!menu) return;
  menu.classList.remove('menu-visible');
  menu.style.left = '0';
  menu.style.top = '0';
  menu.offsetHeight;
  let left = e.clientX;
  let top = e.clientY;
  const mw = menu.offsetWidth;
  const mh = menu.offsetHeight;
  if (left + mw > window.innerWidth - 8) left = window.innerWidth - mw - 8;
  if (top + mh > window.innerHeight - 8) top = window.innerHeight - mh - 8;
  if (left < 0) left = 0;
  if (top < 0) top = 0;
  menu.style.left = left + 'px';
  menu.style.top = top + 'px';
  requestAnimationFrame(function() {
    menu.classList.add('menu-visible');
    _focusMenuItem(menu, 0);
  });
}

function closeGroupContextMenu() {
  const menu = document.getElementById('group-context-menu');
  if (menu) menu.classList.remove('menu-visible');
  TwitchX._ctxGroupName = null;
  if (TwitchX._groupContextReturnFocus && TwitchX._groupContextReturnFocus.focus) {
    TwitchX._groupContextReturnFocus.focus();
  }
  TwitchX._groupContextReturnFocus = null;
}

TwitchX.showContextMenu = showContextMenu;
TwitchX.showSidebarContextMenu = showSidebarContextMenu;
TwitchX.showGroupContextMenu = showGroupContextMenu;
TwitchX.closeContextMenu = closeContextMenu;
TwitchX.closeGroupContextMenu = closeGroupContextMenu;
TwitchX.focusContextMenuItem = _focusMenuItem;
TwitchX.getVisibleContextMenuItems = _visibleMenuItems;
