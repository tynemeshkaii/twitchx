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
  watchingChannel: null,
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
TwitchX.channelViewSource = 'grid';
TwitchX.channelProfile = null;
TwitchX._rebindAction = null;
TwitchX.thirdPartyEmotes = {};

TwitchX.createChannelMediaState = createChannelMediaState;

TwitchX.getFavoriteMeta = function(login, platform) {
  if (platform) {
    var key = platform + ':' + login;
    return TwitchX.state.favoritesMeta[key] || null;
  }
  for (var key in TwitchX.state.favoritesMeta) {
    if (TwitchX.state.favoritesMeta[key].login === login) {
      return TwitchX.state.favoritesMeta[key];
    }
  }
  return null;
};
