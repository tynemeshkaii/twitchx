window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

var ICON_STROKE_WIDTH = 1.5;

var ICONS = {
  play: '<path d="M5.35 3.25v9.5L12 8z"/>',
  stop: '<rect x="3" y="3" width="10" height="10" rx="2.2"/>',
  fullscreen: '<path d="M5.75 2.5H3.5v2.25M10.25 2.5h2.25v2.25M12.5 10.25v2.25h-2.25M5.75 12.5H3.5v-2.25"/>',
  pip: '<rect x="2.25" y="3" width="11.5" height="8.25" rx="2"/><rect x="8.35" y="6.85" width="4.15" height="2.9" rx="0.95" fill="currentColor" stroke="none"/>',
  volume: '<path d="M3 8h2.8L8.9 5v6L5.8 8H3z"/><path d="M11 5.5a3.4 3.4 0 0 1 0 5"/><path d="M12.9 3.7a6.05 6.05 0 0 1 0 8.6"/>',
  record: '<circle cx="8" cy="8" r="4" fill="currentColor" stroke="none"/>',
  close: '<path d="M4.15 4.15 11.85 11.85M11.85 4.15l-7.7 7.7"/>',
  settings: '<path d="M8 5.1a2.9 2.9 0 1 0 0 5.8 2.9 2.9 0 0 0 0-5.8z"/><path d="M8 1.5v1.5M8 13v1.5M13 8h1.5M1.5 8H3M11.3 4.7l1.05-1.05M3.65 11.35l1.05-1.05M11.3 11.3l1.05 1.05M3.65 4.65l1.05 1.05"/>',
  refresh: '<path d="M12.4 6.2A4.95 4.95 0 1 0 13 8.5"/><path d="M10.1 2.95h3.2v3.2"/>',
  download: '<path d="M8 2.5v7.15"/><path d="m4.95 7.6 3.05 3.05 3.05-3.05"/><path d="M3 12.75h10"/>',
  filter: '<path d="M2.5 4h11l-4.2 4.5v3.1L6.7 13V8.5z"/>',
  clock: '<circle cx="8" cy="8" r="5.85"/><path d="M8 4.85v3.35l2.35 2.1"/>',
  eye: '<path d="M2.25 8c1.4-2.45 3.5-3.95 5.75-3.95S12.35 5.55 13.75 8c-1.4 2.45-3.5 3.95-5.75 3.95S3.65 10.45 2.25 8Z"/><circle cx="8" cy="8" r="1.7"/>',
  smile: '<circle cx="8" cy="8" r="5.9"/><path d="M5.75 9.55c.65.9 1.45 1.35 2.25 1.35s1.6-.45 2.25-1.35"/><circle cx="6.1" cy="6.35" r=".55" fill="currentColor" stroke="none"/><circle cx="9.9" cy="6.35" r=".55" fill="currentColor" stroke="none"/>',
  users: '<circle cx="6" cy="5.2" r="1.95"/><path d="M2.8 12.35c.35-1.95 1.7-3.05 3.2-3.05s2.85 1.1 3.2 3.05"/><circle cx="10.95" cy="5.8" r="1.45"/><path d="M10.05 9.9c1.35.15 2.45 1 2.95 2.45"/>',
  shield: '<path d="M8 2.2 12.6 4v3.6c0 2.85-1.7 4.85-4.6 6.15C5.1 12.45 3.4 10.45 3.4 7.6V4z"/>',
  chart: '<path d="M3 12.5h10"/><rect x="3.15" y="8.45" width="1.95" height="4.05" rx="0.95"/><rect x="7.05" y="5.65" width="1.95" height="6.85" rx="0.95"/><rect x="10.95" y="3.2" width="1.95" height="9.3" rx="0.95"/>',
  external: '<circle cx="8" cy="8" r="5.75"/><path d="M8 3.55v4.1l2.9 1.6"/><path d="m9.95 2.75 2.1.35-.35 2.1"/>',
  browser: '<circle cx="8" cy="8" r="5.75"/><path d="M2.65 6h10.7M2.65 10h10.7M8 2.25c1.1 1.3 1.75 3.45 1.75 5.75S9.1 12.45 8 13.75c-1.1-1.3-1.75-3.45-1.75-5.75S6.9 3.55 8 2.25Z"/>',
  copy: '<rect x="5.15" y="4.4" width="7.2" height="8.45" rx="1.65"/><path d="M10.45 4.4V3.3c0-.75-.6-1.35-1.35-1.35H4.3c-.75 0-1.35.6-1.35 1.35v6.2c0 .75.6 1.35 1.35 1.35h.85"/>',
  pin: '<path d="m9.95 2.85 3.2 3.2-1.5.55-2.1 2.1.55 1.5-2.2.8L4.25 14.65l2.65-3.65-.8-2.2 1.5.55 2.1-2.1z"/>',
  star: '<path d="m8 2.45 1.55 3.2 3.55.5-2.55 2.45.6 3.45L8 10.35l-3.15 1.7.6-3.45L2.9 6.15l3.55-.5z"/>',
  user: '<circle cx="8" cy="5.25" r="2.55"/><path d="M3.05 13.15c.55-2.1 2.35-3.4 4.95-3.4s4.4 1.3 4.95 3.4"/>',
  chat: '<path d="M3 3.55h10c.55 0 1 .45 1 1v5.55c0 .55-.45 1-1 1H8.8l-3.45 2.35v-2.35H3c-.55 0-1-.45-1-1V4.55c0-.55.45-1 1-1Z"/>',
  'grid-layout': '<rect x="2.35" y="2.35" width="4.5" height="4.5" rx="1.2"/><rect x="9.15" y="2.35" width="4.5" height="4.5" rx="1.2"/><rect x="2.35" y="9.15" width="4.5" height="4.5" rx="1.2"/><rect x="9.15" y="9.15" width="4.5" height="4.5" rx="1.2"/>',
  minimize: '<path d="M3.25 12.3h9.5"/>',
  'grid-toggle': '<rect x="2.4" y="3" width="4.3" height="4.3" rx="1.1"/><rect x="9.3" y="3" width="4.3" height="4.3" rx="1.1"/><rect x="2.4" y="8.7" width="4.3" height="4.3" rx="1.1"/><rect x="9.3" y="8.7" width="4.3" height="4.3" rx="1.1"/>',
  'list-toggle': '<path d="M5.35 4h8.1M5.35 8h8.1M5.35 12h8.1"/><circle cx="3.2" cy="4" r=".7" fill="currentColor" stroke="none"/><circle cx="3.2" cy="8" r=".7" fill="currentColor" stroke="none"/><circle cx="3.2" cy="12" r=".7" fill="currentColor" stroke="none"/>',
  sidebar: '<rect x="2.35" y="2.75" width="11.3" height="10.5" rx="2"/><path d="M6.4 2.75v10.5"/>',
  plus: '<path d="M8 3.25v9.5M3.25 8h9.5"/>',
  'mini-exit': '<rect x="2.4" y="2.9" width="11.2" height="10.2" rx="2"/><path d="M10.2 8H5.8"/><path d="m7.85 5.95-2.05 2.05 2.05 2.05"/>',
  'external-link': '<path d="M5.75 3H4A1.75 1.75 0 0 0 2.25 4.75V12A1.75 1.75 0 0 0 4 13.75h7.25A1.75 1.75 0 0 0 13 12V10.25"/><path d="M9.25 2.25H13.75V6.75"/><path d="M13.45 2.55 7.9 8.1"/>',
  'arrow-left': '<path d="m10.85 3.1-4.7 4.9 4.7 4.9"/>',
  'arrow-down': '<path d="m3.1 5.7 4.9 4.6 4.9-4.6"/>',
  'arrow-up': '<path d="m3.1 10.3 4.9-4.6 4.9 4.6"/>',
  'arrow-right': '<path d="m5.15 3.1 4.7 4.9-4.7 4.9"/>',
  'chevron-left': '<path d="m10.15 3.9-3.95 4.1 3.95 4.1"/>',
  'chevron-down': '<path d="m3.9 6.15 4.1 3.95 4.1-3.95"/>',
  'chevron-right': '<path d="m5.85 3.9 3.95 4.1-3.95 4.1"/>',
  enter: '<path d="M12.8 3.2v5H5.15"/><path d="m7.5 6.15-2.35 2.05 2.35 2.05"/><path d="M3.2 12.8h9.6"/>',
  backspace: '<path d="M6.2 3.65h7.1v8.7H6.2L2.65 8z"/><path d="m8.1 6.2 3.1 3.1M11.2 6.2 8.1 9.3"/>',
  tab: '<path d="M2.75 5.2h6.2l2.25 2.8L8.95 10.8h-6.2"/><path d="M11.85 4.65v6.7M14 4.65v6.7"/>',
  reply: '<path d="m6.1 5.15-3.1 3 3.1 3"/><path d="M3.1 8.15h4.15c3.2 0 5.15 1.55 5.65 4.15"/>',
  check: '<path d="M3.35 8.35 6.45 11.35 12.65 4.95"/>',
  cross: '<path d="M4.15 4.15 11.85 11.85M11.85 4.15l-7.7 7.7"/>',
  warn: '<path d="M8 2.35 13.1 12.45H2.9z"/><path d="M8 5.8v3.15"/><circle cx="8" cy="10.95" r=".62" fill="currentColor" stroke="none"/>',
  info: '<circle cx="8" cy="8" r="5.75"/><path d="M8 7.15v3.55"/><circle cx="8" cy="4.85" r=".58" fill="currentColor" stroke="none"/>',
  lightning: '<path d="M8.95 2.3 4.25 8.35h3.05L6.85 13.7l4.9-6.2H8.6z"/>',
  'trend-up': '<path d="M3 10.7 6.15 7.55l2.2 2.2 4.65-4.65"/><path d="M10.1 5.1h2.9V8"/>',
  'trend-down': '<path d="M3 5.3 6.15 8.45l2.2-2.2 4.65 4.65"/><path d="M10.1 10.9h2.9V8"/>',
  tv: '<rect x="2.25" y="3" width="11.5" height="7.8" rx="2.1"/><path d="M6.15 13h3.7"/><path d="M8 10.8V13"/>',
  'live-dot': '<circle cx="8" cy="8" r="3.7" fill="currentColor" stroke="none"/>',
  sleeping: '<path d="M10.9 3.1A5.85 5.85 0 1 0 12.9 11c-.45.2-.95.3-1.45.3-2.1 0-3.8-1.7-3.8-3.8 0-1.8 1.25-3.3 3.25-4.4Z"/>'
};

function renderIcon(name, size) {
  var body = ICONS[name];
  size = size || 16;
  if (!body) {
    body = '<circle cx="8" cy="8" r="2.7"/>';
  }
  return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="' + ICON_STROKE_WIDTH + '" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + body + '</svg>';
}

function mountIcons(root) {
  (root || document).querySelectorAll('[data-icon]').forEach(function(el) {
    var name = el.dataset.icon;
    var size = parseInt(el.dataset.size || '16', 10);
    el.innerHTML = renderIcon(name, size);
  });
}

TwitchX.renderIcon = renderIcon;
TwitchX.mountIcons = mountIcons;
TwitchX.icon = function(name, size) {
  return renderIcon(name, size);
};
