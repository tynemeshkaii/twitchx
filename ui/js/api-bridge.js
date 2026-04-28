const TwitchX = window.TwitchX || {};

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
  document.getElementById('login-btn').style.display = 'none';
  const info = document.getElementById('user-info');
  info.style.display = 'flex';
  document.getElementById('user-display-name').textContent = user.display_name;
  const avatar = document.getElementById('user-avatar');
  avatar.dataset.login = (user.login || '').toLowerCase();
  if (TwitchX.state.avatars[(user.login || '').toLowerCase()]) {
    avatar.src = TwitchX.state.avatars[(user.login || '').toLowerCase()];
  }
}

function hideUserProfile() {
  TwitchX.state.currentUser = null;
  document.getElementById('login-btn').style.display = 'block';
  document.getElementById('user-info').style.display = 'none';
}

function showKickProfile(user) {
  TwitchX.state.kickUser = user;
  document.getElementById('kick-login-sidebar-btn').style.display = 'none';
  const info = document.getElementById('kick-user-info');
  info.style.display = 'flex';
  document.getElementById('kick-user-name').textContent = user.display_name || user.login;
}

function hideKickProfile() {
  TwitchX.state.kickUser = null;
  document.getElementById('kick-login-sidebar-btn').style.display = 'block';
  document.getElementById('kick-user-info').style.display = 'none';
}

function doLogout() {
  if (TwitchX.api) TwitchX.api.logout();
}

function doBrowser() {
  if (!TwitchX.state.selectedChannel || !TwitchX.api) return;
  const selectedStream = TwitchX.state.streams.find(function(s) { return s.login === TwitchX.state.selectedChannel; });
  const platform = (selectedStream && selectedStream.platform) || (TwitchX.state.favoritesMeta[TwitchX.state.selectedChannel] && TwitchX.state.favoritesMeta[TwitchX.state.selectedChannel].platform) || 'twitch';
  TwitchX.api.open_browser(TwitchX.state.selectedChannel, platform);
}

function doRefresh() {
  if (TwitchX.api) TwitchX.api.refresh();
}

/* ── pywebview ready ────────────────────────────────────── */
window.addEventListener('pywebviewready', function() {
  TwitchX.api = window.pywebview.api;
  if (!TwitchX.api) return;
  try {
    const config = TwitchX.api.get_config();
    TwitchX.state.kickScopes = (config && config.kick_scopes) || '';
    if (config && config.current_user) {
      showUserProfile(config.current_user);
    }
    if (config && config.kick_user) {
      showKickProfile(config.kick_user);
    }
    if (config && config.keyboard_shortcuts) {
      TwitchX.state.shortcuts = Object.assign({}, TwitchX.DEFAULT_SHORTCUTS, config.keyboard_shortcuts);
    }
    TwitchX.state.pipEnabled = !!(config && config.pip_enabled);
    const pipBtn = document.getElementById('pip-player-btn');
    if (pipBtn) pipBtn.style.display = TwitchX.state.pipEnabled ? '' : 'none';
  } catch(e) {
    setTimeout(function() {
      if (TwitchX.api) {
        try {
          const retryConfig = TwitchX.api.get_config();
          TwitchX.state.kickScopes = (retryConfig && retryConfig.kick_scopes) || '';
          if (retryConfig && retryConfig.current_user) showUserProfile(retryConfig.current_user);
          if (retryConfig && retryConfig.kick_user) showKickProfile(retryConfig.kick_user);
          if (retryConfig && retryConfig.keyboard_shortcuts) {
            TwitchX.state.shortcuts = Object.assign({}, TwitchX.DEFAULT_SHORTCUTS, retryConfig.keyboard_shortcuts);
          }
        } catch(e2) {}
      }
    }, 200);
  }
});

window.addEventListener('resize', function() {
  if (TwitchX.sidebarResizeFrame) {
    cancelAnimationFrame(TwitchX.sidebarResizeFrame);
  }
  TwitchX.sidebarResizeFrame = requestAnimationFrame(function() {
    TwitchX.sidebarResizeFrame = null;
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
