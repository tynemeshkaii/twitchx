window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

TwitchX.DEFAULT_SHORTCUTS = {
  refresh:      'r',
  watch:        ' ',
  fullscreen:   'f',
  toggle_chat:  'c',
  mute:         'm',
  pip:          'p',
  volume_up:    'ArrowUp',
  volume_down:  'ArrowDown',
  next_stream:  'ArrowRight',
  prev_stream:  'ArrowLeft',
};

TwitchX.SHORTCUT_LABELS = {
  refresh:      'Refresh streams',
  watch:        'Watch selected stream',
  fullscreen:   'Toggle fullscreen',
  toggle_chat:  'Toggle chat panel',
  mute:         'Toggle mute',
  pip:          'Toggle Picture-in-Picture',
  volume_up:    'Volume up (+10%)',
  volume_down:  'Volume down (-10%)',
  next_stream:  'Select next stream',
  prev_stream:  'Select previous stream',
};

function createChannelMediaState() {
  return {
    status: 'idle',
    items: [],
    supported: true,
    error: false,
    message: '',
  };
}

TwitchX.state = {
  streams: [],
  favorites: [],
  liveSet: new Set(),
  selectedChannel: null,
  selectedChannelKey: null,
  selectedPlatform: null,
  watchingChannel: null,
  watchingChannelKey: null,
  playerPlatform: null,
  playerHasChat: true,
  streamType: 'live',
  prevViewers: {},
  config: {},
  sortKey: 'viewers',
  filterText: '',
  avatars: {},
  thumbnails: {},
  searchResults: [],
  searchDebounce: null,
  hasCredentials: false,
  userAvatars: {},
  kickUser: null,
  kickScopes: '',
  youtubeUser: null,
  playerState: 'idle',
  playerChannel: null,
  playerTitle: '',
  playerError: '',
  sidebarSections: { online: false, offline: true },
  favoritesMeta: {},
  activePlatformFilter: 'all',
  browseMode: 'categories',
  browseCategory: null,
  browsePlatformFilter: 'all',
  channelTabs: {
    active: 'live',
    vods: createChannelMediaState(),
    clips: createChannelMediaState(),
  },
  shortcuts: Object.assign({}, TwitchX.DEFAULT_SHORTCUTS),
  pipEnabled: false,
  gridMode: 'grid',
  streamsLoaded: false,
  favoritesHydrated: false,
};

TwitchX.state.pinnedStreams = new Set();

TwitchX.loadPinnedStreams = function() {
  try {
    var raw = localStorage.getItem('twitchx.pinned');
    TwitchX.state.pinnedStreams = new Set(raw ? JSON.parse(raw) : []);
  } catch (e) {
    TwitchX.state.pinnedStreams = new Set();
  }
};

TwitchX.savePinnedStreams = function() {
  localStorage.setItem('twitchx.pinned', JSON.stringify(Array.from(TwitchX.state.pinnedStreams)));
};

TwitchX.isPinned = function(platform, login) {
  return TwitchX.state.pinnedStreams.has(platform + ':' + login);
};

TwitchX.togglePin = function(platform, login) {
  var key = platform + ':' + login;
  if (TwitchX.state.pinnedStreams.has(key)) {
    TwitchX.state.pinnedStreams.delete(key);
  } else {
    TwitchX.state.pinnedStreams.add(key);
  }
  TwitchX.savePinnedStreams();
  TwitchX.renderGrid();
};

TwitchX.multiState = {
  slots: [null, null, null, null],
  audioFocus: -1,
  chatSlot: -1,
  open: false,
  chatVisible: false,
  activePreset: 'grid',
};

TwitchX.msChatAutoScroll = true;
TwitchX.chatAutoScroll = true;
TwitchX.chatAuthenticated = false;
TwitchX.chatPlatform = null;
TwitchX.chatReplyTo = null;
TwitchX.chatPendingSends = Object.create(null);
TwitchX.chatSendCounter = 0;

TwitchX.sidebarResizeFrame = null;
TwitchX.ctxChannel = null;
TwitchX.ctxChannelKey = null;
TwitchX.channelViewSource = 'grid';
TwitchX.channelProfile = null;
TwitchX._rebindAction = null;
TwitchX.thirdPartyEmotes = {};

TwitchX.createChannelMediaState = createChannelMediaState;

TwitchX.channelKey = function(login, platform) {
  if (!login) return '';
  if (platform) return platform + ':' + login;
  return String(login);
};

TwitchX.platformLabel = function(platform) {
  if (platform === 'kick') return 'Kick';
  if (platform === 'youtube') return 'YouTube';
  return 'Twitch';
};

TwitchX.findStreamByKey = function(key) {
  if (!key) return null;
  return TwitchX.state.streams.find(function(stream) {
    return TwitchX.channelKey(stream.login, stream.platform || 'twitch') === key;
  }) || null;
};

TwitchX.findStreamForChannel = function(login, platform) {
  if (!login || !platform) return null;
  return TwitchX.findStreamByKey(TwitchX.channelKey(login, platform));
};

TwitchX.getFavoriteMeta = function(login, platform) {
  if (!login || !platform) return null;
  var key = TwitchX.channelKey(login, platform);
  return TwitchX.state.favoritesMeta[key] || null;
};

TwitchX.getFavoriteGroup = function(login, platform) {
  var meta = TwitchX.getFavoriteMeta(login, platform);
  return meta && meta.group ? meta.group : null;
};

TwitchX.SYSTEM_FAVORITE_GROUPS = ['Online', 'Offline'];

TwitchX.getFavoriteEntries = function() {
  var entries = [];
  var seen = Object.create(null);

  // Authoritative source: favoritesMeta is keyed by platform:login.
  for (var key in TwitchX.state.favoritesMeta) {
    var meta = TwitchX.state.favoritesMeta[key] || {};
    var login = meta.login || key.split(':').slice(1).join(':');
    var platform = meta.platform || key.split(':')[0] || 'twitch';
    if (!seen[key]) {
      seen[key] = true;
      entries.push({
        login: login,
        platform: platform,
        key: key,
        display_name: meta.display_name || login,
      });
    }
  }

  // Legacy fallback: raw logins not present in favoritesMeta default to Twitch.
  TwitchX.state.favorites.forEach(function(login) {
    if (!login || typeof login !== 'string') return;
    var key = TwitchX.channelKey(login, 'twitch');
    if (!seen[key]) {
      seen[key] = true;
      entries.push({
        login: login,
        platform: 'twitch',
        key: key,
        display_name: login,
      });
    }
  });

  return entries;
};

TwitchX.getChannelPlatform = function(login, key) {
  if (key) {
    var keyedStream = TwitchX.findStreamByKey(key);
    if (keyedStream && keyedStream.platform) return keyedStream.platform;
    var keyedMeta = TwitchX.state.favoritesMeta[key];
    if (keyedMeta && keyedMeta.platform) return keyedMeta.platform;
    if (key.indexOf(':') !== -1) return key.split(':')[0];
  }
  if (login) {
    var stream = TwitchX.state.streams.find(function(s) { return s.login === login; });
    if (stream && stream.platform) return stream.platform;
  }
  return 'twitch';
};
