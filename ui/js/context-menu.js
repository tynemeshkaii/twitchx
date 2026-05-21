window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

function closeContextMenu() {
  const menu = document.getElementById('context-menu');
  if (menu) menu.classList.remove('menu-visible');
  TwitchX.ctxChannel = null;
  if (TwitchX.deactivateFocusTrap) TwitchX.deactivateFocusTrap();
  if (TwitchX.focusReturn && TwitchX.focusReturn.restore) TwitchX.focusReturn.restore();
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

function _showMenu(e, login) {
  TwitchX.ctxChannel = login;
  const menu = document.getElementById('context-menu');
  menu.classList.remove('menu-visible');
  menu.style.left = '0';
  menu.style.top = '0';
  // Force layout, then position
  menu.offsetHeight;
  _positionContextMenu(e);
  requestAnimationFrame(function() {
    menu.classList.add('menu-visible');
  });
}

function showContextMenu(e, login) {
  e.preventDefault();
  _showMenu(e, login);
  const menu = document.getElementById('context-menu');
  const favItem = menu.querySelector('[data-action="favorite"]');
  const removeItem = menu.querySelector('[data-action="remove"]');
  if (TwitchX.state.favorites.indexOf(login) !== -1) {
    favItem.classList.add('hidden');
    removeItem.classList.remove('hidden');
  } else {
    favItem.classList.remove('hidden');
    removeItem.classList.add('hidden');
  }
  const msItem = menu.querySelector('[data-action="multistream"]');
  if (msItem) {
    const allFull = TwitchX.multiState.slots.every(function(s) { return s !== null; });
    const ctxStream = TwitchX.state.streams.find(function(s) { return s.login === login; });
    const isYT = (ctxStream && ctxStream.platform === 'youtube') ||
      (TwitchX.state.favoritesMeta['youtube:' + login] !== undefined);
    msItem.classList.toggle('hidden', allFull || isYT);
  }
  var pinItem = menu.querySelector('[data-action="pin"]');
  if (pinItem) {
    var ctxPlatForPin = (function() {
      var s = TwitchX.state.streams.find(function(s) { return s.login === login; });
      if (s && s.platform) return s.platform;
      var plats = ['twitch', 'kick', 'youtube'];
      for (var pi = 0; pi < plats.length; pi++) {
        if (TwitchX.state.favoritesMeta[plats[pi] + ':' + login]) return plats[pi];
      }
      return 'twitch';
    })();
    var alreadyPinned = TwitchX.isPinned(ctxPlatForPin, login);
    pinItem.innerHTML = TwitchX.renderIcon('pin', 14) + ' ' + (alreadyPinned ? 'Unpin' : 'Pin to top');
    pinItem.dataset.pinPlatform = ctxPlatForPin;
  }
}

function showSidebarContextMenu(e, login) {
  e.preventDefault();
  _showMenu(e, login);
  const menu = document.getElementById('context-menu');
  menu.querySelector('[data-action="favorite"]').classList.add('hidden');
  menu.querySelector('[data-action="remove"]').classList.remove('hidden');
  const msItem = menu.querySelector('[data-action="multistream"]');
  if (msItem) {
    const allFull = TwitchX.multiState.slots.every(function(s) { return s !== null; });
    const ctxStream = TwitchX.state.streams.find(function(s) { return s.login === login; });
    const isYT = (ctxStream && ctxStream.platform === 'youtube') ||
      (TwitchX.state.favoritesMeta['youtube:' + login] !== undefined);
    msItem.classList.toggle('hidden', allFull || isYT);
  }
  var pinItem = menu.querySelector('[data-action="pin"]');
  if (pinItem) {
    var ctxPlatForPin = (function() {
      var s = TwitchX.state.streams.find(function(s) { return s.login === login; });
      if (s && s.platform) return s.platform;
      var plats = ['twitch', 'kick', 'youtube'];
      for (var pi = 0; pi < plats.length; pi++) {
        if (TwitchX.state.favoritesMeta[plats[pi] + ':' + login]) return plats[pi];
      }
      return 'twitch';
    })();
    var alreadyPinned = TwitchX.isPinned(ctxPlatForPin, login);
    pinItem.innerHTML = TwitchX.renderIcon('pin', 14) + ' ' + (alreadyPinned ? 'Unpin' : 'Pin to top');
    pinItem.dataset.pinPlatform = ctxPlatForPin;
  }
}

TwitchX.showContextMenu = showContextMenu;
TwitchX.showSidebarContextMenu = showSidebarContextMenu;
TwitchX.closeContextMenu = closeContextMenu;
