window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

function showContextMenu(e, login) {
  e.preventDefault();
  TwitchX.ctxChannel = login;
  const menu = document.getElementById('context-menu');
  menu.style.display = 'block';
  // Let the browser compute the menu size before positioning
  menu.style.visibility = 'hidden';
  menu.style.left = '0';
  menu.style.top = '0';
  let left = e.clientX;
  let top = e.clientY;
  const mw = menu.offsetWidth;
  const mh = menu.offsetHeight;
  if (left + mw > window.innerWidth - 4)  left = window.innerWidth - mw - 4;
  if (top + mh > window.innerHeight - 4) top = window.innerHeight - mh - 4;
  if (left < 0) left = 0;
  if (top < 0) top = 0;
  menu.style.left = left + 'px';
  menu.style.top = top + 'px';
  menu.style.visibility = '';
  const favItem = menu.querySelector('[data-action="favorite"]');
  const removeItem = menu.querySelector('[data-action="remove"]');
  if (TwitchX.state.favorites.indexOf(login) !== -1) {
    favItem.style.display = 'none';
    removeItem.style.display = 'block';
  } else {
    favItem.style.display = 'block';
    removeItem.style.display = 'none';
  }
  const msItem = menu.querySelector('[data-action="multistream"]');
  if (msItem) {
    const allFull = TwitchX.multiState.slots.every(function(s) { return s !== null; });
    const ctxStream = TwitchX.state.streams.find(function(s) { return s.login === login; });
    const isYT = (ctxStream && ctxStream.platform === 'youtube') ||
      (TwitchX.state.favoritesMeta['youtube:' + login] !== undefined);
    msItem.style.display = (allFull || isYT) ? 'none' : 'block';
  }
}

function showSidebarContextMenu(e, login) {
  e.preventDefault();
  TwitchX.ctxChannel = login;
  const menu = document.getElementById('context-menu');
  menu.style.display = 'block';
  menu.style.visibility = 'hidden';
  menu.style.left = '0';
  menu.style.top = '0';
  let left = e.clientX;
  let top = e.clientY;
  const mw = menu.offsetWidth;
  const mh = menu.offsetHeight;
  if (left + mw > window.innerWidth - 4)  left = window.innerWidth - mw - 4;
  if (top + mh > window.innerHeight - 4) top = window.innerHeight - mh - 4;
  if (left < 0) left = 0;
  if (top < 0) top = 0;
  menu.style.left = left + 'px';
  menu.style.top = top + 'px';
  menu.style.visibility = '';
  menu.querySelector('[data-action="favorite"]').style.display = 'none';
  menu.querySelector('[data-action="remove"]').style.display = 'block';
  const msItem = menu.querySelector('[data-action="multistream"]');
  if (msItem) {
    const allFull = TwitchX.multiState.slots.every(function(s) { return s !== null; });
    const ctxStream = TwitchX.state.streams.find(function(s) { return s.login === login; });
    const isYT = (ctxStream && ctxStream.platform === 'youtube') ||
      (TwitchX.state.favoritesMeta['youtube:' + login] !== undefined);
    msItem.style.display = (allFull || isYT) ? 'none' : 'block';
  }
}

TwitchX.showContextMenu = showContextMenu;
TwitchX.showSidebarContextMenu = showSidebarContextMenu;
