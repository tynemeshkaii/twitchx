window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

TwitchX.api = null;

function callApi(name) {
  if (!TwitchX.api) return;
  try {
    const method = TwitchX.api[name];
    if (!method) return;
    return method.apply(TwitchX.api, Array.prototype.slice.call(arguments, 1));
  } catch(e) {
    TwitchX.setStatus('Bridge error. Please restart.', 'error');
  }
}

function showUserProfile(user) {
  TwitchX.state.currentUser = user;
  document.getElementById('login-btn').classList.add('hidden');
  const info = document.getElementById('user-info');
  info.classList.remove('hidden');
  document.getElementById('user-display-name').textContent = user.display_name;
  const avatar = document.getElementById('user-avatar');
  avatar.dataset.login = user.login || '';
  avatar.dataset.key = TwitchX.channelKey(avatar.dataset.login, 'twitch');
  if (TwitchX.state.avatars[avatar.dataset.key]) {
    avatar.src = TwitchX.state.avatars[avatar.dataset.key];
    avatar.classList.remove('is-empty');
  } else {
    // No src at all until the avatar arrives — an empty src renders WebKit's
    // broken-image glyph inside the profile row.
    avatar.removeAttribute('src');
    avatar.classList.add('is-empty');
  }
}

function hideUserProfile() {
  TwitchX.state.currentUser = null;
  document.getElementById('login-btn').classList.remove('hidden');
  document.getElementById('user-info').classList.add('hidden');
}

function showKickProfile(user) {
  TwitchX.state.kickUser = user;
  document.getElementById('kick-login-sidebar-btn').classList.add('hidden');
  const info = document.getElementById('kick-user-info');
  info.classList.remove('hidden');
  document.getElementById('kick-user-name').textContent = user.display_name || user.login;
}

function hideKickProfile() {
  TwitchX.state.kickUser = null;
  document.getElementById('kick-login-sidebar-btn').classList.remove('hidden');
  document.getElementById('kick-user-info').classList.add('hidden');
}

function doLogout() {
  if (TwitchX.api) TwitchX.api.logout();
}

function doBrowser() {
  if (!TwitchX.state.selectedChannel || !TwitchX.api) return;
  const selectedStream = TwitchX.findStreamByKey(TwitchX.state.selectedChannelKey);
  const platform = (selectedStream && selectedStream.platform) || TwitchX.state.selectedPlatform || 'twitch';
  TwitchX.api.open_browser(TwitchX.state.selectedChannel, platform);
}

function doRefresh() {
  if (TwitchX.api) TwitchX.api.refresh();
}

function hydrateFavoritesFromConfig(config) {
  if (!config) return;
  if (Array.isArray(config.favorites)) {
    TwitchX.state.favorites = config.favorites;
  }
  if (config.favorites_meta) {
    TwitchX.state.favoritesMeta = config.favorites_meta;
  }
  TwitchX.state.favoritesHydrated = true;
  if (TwitchX.renderSidebar) {
    TwitchX.renderSidebar();
  }
}

/* ── YouTube feature gating ─────────────────────────────── */
// Closed beta ships with YouTube disabled (placeholder creds). Hides every
// YouTube entry point. Idempotent — re-shows when youtubeEnabled flips true.
TwitchX.applyYoutubeGating = function() {
  const hide = !TwitchX.state.youtubeEnabled;
  document.querySelectorAll(
    '.platform-tab[data-platform="youtube"], .platform-chip[data-platform="youtube"], .browse-platform-tab[data-platform="youtube"]'
  ).forEach(function(el) { el.classList.toggle('hidden', hide); });
  ['yt-settings-section', 'yt-settings-divider'].forEach(function(id) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('hidden', hide);
  });
};

/* ── Config snapshot (Python → JS push) ─────────────────── */
// The pywebview bridge always returns a Promise, so JS can never read config
// synchronously. Python owns the flow: it calls window.onConfigLoaded() on
// document load, after save_settings and after every login/logout. Everything
// in the UI reads the cached snapshot from TwitchX.state.

function requestConfig() {
  if (!TwitchX.api || !TwitchX.api.request_config) return;
  try {
    TwitchX.api.request_config();
  } catch(e) {
    setTimeout(function() {
      if (!TwitchX.api || !TwitchX.api.request_config) return;
      try { TwitchX.api.request_config(); } catch(e2) {}
    }, 200);
  }
}

function applyConfigSnapshot(config) {
  if (!config) return;
  TwitchX.state.config = config;
  TwitchX.state.fullConfig = config.settings || {};
  TwitchX.state.version = config.version || '';
  TwitchX.state.configLoaded = true;
  TwitchX.state.hasCredentials = !!config.has_credentials;

  TwitchX.state.youtubeEnabled = !!config.youtube_enabled;
  TwitchX.applyYoutubeGating();
  TwitchX.state.kickScopes = config.kick_scopes || '';

  if (config.current_user) {
    showUserProfile(config.current_user);
  } else {
    hideUserProfile();
  }
  if (config.kick_user) {
    showKickProfile(config.kick_user);
  } else {
    hideKickProfile();
  }
  if (config.keyboard_shortcuts) {
    TwitchX.state.shortcuts = Object.assign({}, TwitchX.DEFAULT_SHORTCUTS, config.keyboard_shortcuts);
  }
  TwitchX.state.pipEnabled = !!config.pip_enabled;
  const pipBtn = document.getElementById('pip-player-btn');
  if (pipBtn) pipBtn.classList.toggle('hidden', !TwitchX.state.pipEnabled);

  const qualitySelect = document.getElementById('quality-select');
  const savedQuality = (config.settings && config.settings.quality) || '';
  if (qualitySelect && savedQuality) {
    const known = Array.prototype.some.call(qualitySelect.options, function(opt) {
      return opt.value === savedQuality;
    });
    if (known) qualitySelect.value = savedQuality;
  }

  hydrateFavoritesFromConfig(config);

  if (TwitchX.onConfigApplied) TwitchX.onConfigApplied(config);
}

/* ── pywebview ready ────────────────────────────────────── */
window.addEventListener('pywebviewready', function() {
  TwitchX.api = window.pywebview.api;
  if (!TwitchX.api) return;
  requestConfig();
  // Safety net: the `loaded` push can race a slow first paint.
  setTimeout(function() {
    if (!TwitchX.state.configLoaded) requestConfig();
  }, 1500);
});

window.addEventListener('resize', function() {
  if (TwitchX.sidebarResizeFrame) {
    cancelAnimationFrame(TwitchX.sidebarResizeFrame);
  }
  TwitchX.sidebarResizeFrame = requestAnimationFrame(function() {
    TwitchX.sidebarResizeFrame = null;
    var sidebar = document.getElementById('sidebar');
    if (sidebar && sidebar.classList.contains('collapsed-sidebar')) return;
    if (TwitchX.state.favorites.length > 0) {
      TwitchX.applySidebarLayout(TwitchX.getSidebarGroups());
    }
  });
});

TwitchX.callApi = callApi;
TwitchX.showUserProfile = showUserProfile;
TwitchX.hideUserProfile = hideUserProfile;
TwitchX.showKickProfile = showKickProfile;
TwitchX.hideKickProfile = hideKickProfile;
TwitchX.doLogout = doLogout;
TwitchX.doBrowser = doBrowser;
TwitchX.doRefresh = doRefresh;
TwitchX.hydrateFavoritesFromConfig = hydrateFavoritesFromConfig;
TwitchX.requestConfig = requestConfig;
TwitchX.applyConfigSnapshot = applyConfigSnapshot;
