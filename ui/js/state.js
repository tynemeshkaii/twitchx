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
  if (platform) return TwitchX.findStreamByKey(TwitchX.channelKey(login, platform));
  return TwitchX.state.streams.find(function(stream) { return stream.login === login; }) || null;
};

TwitchX.getFavoriteMeta = function(login, platform) {
  if (platform) {
    var key = TwitchX.channelKey(login, platform);
    return TwitchX.state.favoritesMeta[key] || null;
  }
  for (var key in TwitchX.state.favoritesMeta) {
    if (TwitchX.state.favoritesMeta[key].login === login) {
      return TwitchX.state.favoritesMeta[key];
    }
  }
  return null;
};

TwitchX.getFavoriteEntries = function() {
  var entries = [];
  var seen = Object.create(null);
  var metaByLogin = Object.create(null);

  for (var key in TwitchX.state.favoritesMeta) {
    var meta = TwitchX.state.favoritesMeta[key] || {};
    var login = meta.login || key.split(':').slice(1).join(':');
    var platform = meta.platform || key.split(':')[0] || 'twitch';
    if (!metaByLogin[login]) metaByLogin[login] = [];
    metaByLogin[login].push({
      login: login,
      platform: platform,
      key: TwitchX.channelKey(login, platform),
      display_name: meta.display_name || login,
    });
  }

  TwitchX.state.favorites.forEach(function(login) {
    var matches = metaByLogin[login];
    if (matches && matches.length) {
      matches.forEach(function(entry) {
        if (!seen[entry.key]) {
          seen[entry.key] = true;
          entries.push(entry);
        }
      });
      return;
    }
    var stream = TwitchX.findStreamForChannel(login);
    var platform = (stream && stream.platform) || 'twitch';
    var fallback = {
      login: login,
      platform: platform,
      key: TwitchX.channelKey(login, platform),
      display_name: login,
    };
    if (!seen[fallback.key]) {
      seen[fallback.key] = true;
      entries.push(fallback);
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
  var stream = TwitchX.findStreamForChannel(login);
  if (stream && stream.platform) return stream.platform;
  var meta = TwitchX.getFavoriteMeta(login);
  return (meta && meta.platform) || 'twitch';
};
