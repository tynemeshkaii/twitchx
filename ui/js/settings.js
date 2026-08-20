window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

const ACCENT_PALETTE = [
  { value: '#FF9F0A', label: 'Amber' },
  { value: '#BF5AF2', label: 'Purple' },
  { value: '#0A84FF', label: 'Blue' },
  { value: '#30D158', label: 'Green' },
  { value: '#FF453A', label: 'Red' },
  { value: '#FF2D55', label: 'Pink' },
];

function _hexToRgb(hex) {
  var m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (!m) return null;
  return {
    r: parseInt(m[1], 16) / 255,
    g: parseInt(m[2], 16) / 255,
    b: parseInt(m[3], 16) / 255,
  };
}

function _rgbToHsl(r, g, b) {
  var max = Math.max(r, g, b);
  var min = Math.min(r, g, b);
  var h = 0;
  var s = 0;
  var l = (max + min) / 2;

  if (max !== min) {
    var d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      case b: h = (r - g) / d + 4; break;
    }
    h = h / 6;
  }

  return {
    h: Math.round(h * 360),
    s: Math.round(s * 100),
    l: Math.round(l * 100),
  };
}

function _contrastColorForRgb(rgb) {
  // YIQ perceived brightness; choose black or white for best contrast.
  var yiq = ((rgb.r * 255) * 299 + (rgb.g * 255) * 587 + (rgb.b * 255) * 114) / 1000;
  return yiq >= 128 ? '#0A0A0C' : '#FFFFFF';
}

function applyAccentColor(color) {
  var entry = ACCENT_PALETTE.find(function(p) { return p.value === color; }) || ACCENT_PALETTE[0];
  var rgb = _hexToRgb(entry.value);
  if (!rgb) return;
  var hsl = _rgbToHsl(rgb.r, rgb.g, rgb.b);
  var root = document.documentElement;
  root.style.setProperty('--accent-h', hsl.h);
  root.style.setProperty('--accent-s', hsl.s + '%');
  root.style.setProperty('--accent-l', hsl.l + '%');
  root.style.setProperty('--text-on-accent', _contrastColorForRgb(rgb));
  localStorage.setItem('twitchx.accent', entry.value);
}

function resolveTheme(mode) {
  if (mode === 'auto') {
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }
  return mode === 'light' ? 'light' : 'dark';
}

function applyTheme(mode) {
  var resolved = resolveTheme(mode);
  document.documentElement.setAttribute('data-theme', resolved);
  localStorage.setItem('twitchx.theme.mode', mode);
  localStorage.setItem('twitchx.theme.resolved', resolved);
}

function formatDuration(seconds) {
  if (!seconds || seconds < 0) return '0m';
  if (seconds < 60) return seconds + 's';
  var m = Math.floor(seconds / 60);
  if (m < 60) return m + 'm';
  var h = Math.floor(m / 60);
  m = m % 60;
  if (h < 24) return h + 'h ' + m + 'm';
  var d = Math.floor(h / 24);
  h = h % 24;
  return d + 'd ' + h + 'h ' + m + 'm';
}

function createStatCard(value, label) {
  var card = document.createElement('div');
  card.className = 'stat-card';
  var valEl = document.createElement('span');
  valEl.className = 'stat-value';
  valEl.textContent = value;
  var lblEl = document.createElement('span');
  lblEl.className = 'stat-label';
  lblEl.textContent = label;
  card.appendChild(valEl);
  card.appendChild(lblEl);
  return card;
}

function renderWatchStats(stats) {
  if (!stats) return;

  if (stats.today) {
    document.getElementById('stat-today-time').textContent = formatDuration(stats.today.total_sec);
    document.getElementById('stat-today-streams').textContent = stats.today.streams_count || 0;
    document.getElementById('stat-today-channels').textContent = stats.today.unique_channels || 0;
  }

  var weeklyContainer = document.getElementById('stats-weekly');
  weeklyContainer.textContent = '';
  if (stats.weekly && stats.weekly.length > 0) {
    var table = document.createElement('table');
    table.className = 'stats-table';
    var thead = document.createElement('thead');
    var headerRow = document.createElement('tr');
    ['Date', 'Platform', 'Time', 'Streams', 'Channels'].forEach(function(h) {
      var th = document.createElement('th');
      th.textContent = h;
      headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);

    var tbody = document.createElement('tbody');
    stats.weekly.forEach(function(row) {
      var tr = document.createElement('tr');
      var cells = [
        row.date,
        row.platform.charAt(0).toUpperCase() + row.platform.slice(1),
        formatDuration(row.total_sec),
        String(row.streams_count),
        String(row.unique_channels),
      ];
      cells.forEach(function(c) {
        var td = document.createElement('td');
        td.textContent = c;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    weeklyContainer.appendChild(table);
  } else {
    var emptyMsg = document.createElement('div');
    emptyMsg.className = 'stats-empty-msg';
    emptyMsg.textContent = 'No data for this week yet.';
    weeklyContainer.appendChild(emptyMsg);
  }

  if (stats.total) {
    document.getElementById('stat-total-time').textContent = formatDuration(stats.total.total_sec);
    document.getElementById('stat-total-channels').textContent = stats.total.unique_channels || 0;
  }

  var topContainer = document.getElementById('stats-top-channels');
  topContainer.textContent = '';
  if (stats.top_channels && stats.top_channels.length > 0) {
    stats.top_channels.forEach(function(ch) {
      var item = document.createElement('div');
      item.className = 'stats-list-item';

      var leftSpan = document.createElement('span');
      var chName = document.createElement('span');
      chName.className = 'stats-channel';
      chName.textContent = ch.display_name || ch.channel;
      leftSpan.appendChild(chName);

      var badge = document.createElement('span');
      badge.className = 'stats-platform-badge';
      badge.textContent = ch.platform.charAt(0).toUpperCase();
      leftSpan.appendChild(badge);

      var rightSpan = document.createElement('span');
      rightSpan.className = 'stats-value';
      rightSpan.textContent = formatDuration(ch.total_sec) + ' \u00b7 ' + ch.sessions_count + ' sessions';

      item.appendChild(leftSpan);
      item.appendChild(rightSpan);
      topContainer.appendChild(item);
    });
  } else {
    var emptyMsg = document.createElement('div');
    emptyMsg.className = 'stats-empty-msg';
    emptyMsg.textContent = 'No watch data yet.';
    topContainer.appendChild(emptyMsg);
  }

  document.getElementById('stats-loading').classList.add('hidden');
  document.getElementById('stats-content').classList.remove('hidden');
}

function loadWatchStatistics() {
  if (!TwitchX.api) return;
  var loading = document.getElementById('stats-loading');
  if (loading) {
    loading.textContent = 'Loading statistics...';
    loading.classList.remove('hidden');
  }
  document.getElementById('stats-content').classList.add('hidden');
  // Results arrive asynchronously via window.onWatchStatistics
  try {
    TwitchX.api.request_watch_statistics('all');
  } catch (e) {
    console.warn('Failed to request watch statistics:', e);
    if (loading) loading.textContent = 'Failed to load statistics';
  }
  // Show compact toggle
  var toggleBtn = document.getElementById('stats-compact-toggle');
  if (toggleBtn) toggleBtn.classList.remove('hidden');
  // Restore compact state
  var compact = localStorage.getItem('twitchx.stats.compact') === '1';
  _applyStatsCompact(compact);
}

function _toggleStatsCompact() {
  var compact = localStorage.getItem('twitchx.stats.compact') !== '1';
  localStorage.setItem('twitchx.stats.compact', compact ? '1' : '0');
  _applyStatsCompact(compact);
}

function _applyStatsCompact(compact) {
  var grids = document.querySelectorAll('.stats-grid');
  var cards = document.querySelectorAll('.stat-card');
  var toggleBtn = document.getElementById('stats-compact-toggle');
  grids.forEach(function(g) { g.classList.toggle('compact', compact); });
  cards.forEach(function(c) { c.classList.toggle('compact', compact); });
  if (toggleBtn) toggleBtn.textContent = compact ? 'Normal' : 'Compact';
}

function _getSelectedTheme() {
  var checked = document.querySelector('input[name="theme"]:checked');
  return checked ? checked.value : 'dark';
}

function _readAllFormValues() {
  var activeSwatch = document.querySelector('.accent-swatch.active');
  return {
    theme: _getSelectedTheme(),
    client_id: document.getElementById('s-client-id').value.trim(),
    client_secret: document.getElementById('s-client-secret').value.trim(),
    streamlink_path: document.getElementById('s-streamlink').value.trim(),
    iina_path: document.getElementById('s-iina').value.trim(),
    mpv_path: document.getElementById('s-mpv').value.trim(),
    external_player: document.getElementById('s-external-player').value,
    refresh_interval: document.getElementById('s-interval').value,
    kick_client_id: document.getElementById('s-kick-client-id').value.trim(),
    kick_client_secret: document.getElementById('s-kick-client-secret').value.trim(),
    youtube_api_key: document.getElementById('yt-api-key').value.trim(),
    youtube_client_id: document.getElementById('yt-client-id').value.trim(),
    youtube_client_secret: document.getElementById('yt-client-secret').value.trim(),
    recording_path: document.getElementById('s-recording-path').value.trim(),
    low_latency_mode: document.getElementById('s-low-latency').checked,
    pip_enabled: document.getElementById('s-pip-enabled').checked,
    accent_color: activeSwatch ? activeSwatch.dataset.color : '#FF9F0A',
    keyboard_shortcuts: JSON.stringify(TwitchX.state.shortcuts || {}),
  };
}

function _isSettingsDirty() {
  if (!TwitchX._settingsSnapshot) return false;
  var current = JSON.stringify(_readAllFormValues());
  return current !== TwitchX._settingsSnapshot;
}

function _setFeedback(msg, type) {
  var fb = document.getElementById('settings-feedback');
  if (!fb) return;
  fb.textContent = msg;
  fb.className = type || '';
}

// The interval dropdown only lists a few presets. A config value outside that
// list used to leave the select empty, and saving then reset it to 60.
function _setIntervalValue(interval) {
  var select = document.getElementById('s-interval');
  if (!select) return;
  var previous = select.querySelector('option[data-custom]');
  if (previous) previous.remove();
  var known = Array.prototype.some.call(select.options, function(opt) {
    return opt.value === interval;
  });
  if (!known) {
    var opt = document.createElement('option');
    opt.value = interval;
    opt.textContent = interval + 's';
    opt.dataset.custom = 'true';
    select.appendChild(opt);
  }
  select.value = interval;
}

function openSettings() {
  if (!TwitchX.api) return;
  // The config snapshot is pushed from Python; without it the form would open
  // with defaults and a Save would overwrite the real config.
  if (!TwitchX.state.configLoaded) {
    TwitchX._settingsPendingOpen = true;
    TwitchX.requestConfig();
    return;
  }
  TwitchX._settingsReturnFocus = document.activeElement;
  const config = TwitchX.state.fullConfig || {};
  document.getElementById('s-client-id').value = config.client_id || '';
  document.getElementById('s-client-secret').value = config.client_secret || '';
  document.getElementById('s-streamlink').value = config.streamlink_path || 'streamlink';
  document.getElementById('s-iina').value = config.iina_path || '/Applications/IINA.app/Contents/MacOS/iina-cli';
  document.getElementById('s-mpv').value = config.mpv_path || '/opt/homebrew/bin/mpv';
  var extPlayer = config.external_player || 'iina';
  document.getElementById('s-external-player').value = extPlayer;
  document.getElementById('s-mpv-group').classList.toggle('hidden', extPlayer !== 'mpv');
  _setIntervalValue(String(config.refresh_interval || 60));
  document.getElementById('s-kick-client-id').value = config.kick_client_id || '';
  document.getElementById('s-kick-client-secret').value = config.kick_client_secret || '';
  if (config.kick_display_name) {
    document.getElementById('kick-login-area').classList.add('hidden');
    document.getElementById('kick-user-area').classList.remove('hidden');
    document.getElementById('kick-user-display').textContent = 'Logged in as ' + config.kick_display_name;
  } else {
    document.getElementById('kick-login-area').classList.remove('hidden');
    document.getElementById('kick-user-area').classList.add('hidden');
  }
  document.getElementById('yt-api-key').value = config.youtube_api_key || '';
  document.getElementById('yt-client-id').value = config.youtube_client_id || '';
  document.getElementById('yt-client-secret').value = config.youtube_client_secret || '';
  if (config.youtube_display_name) {
    document.getElementById('yt-login-area').classList.add('hidden');
    document.getElementById('yt-user-area').classList.remove('hidden');
    document.getElementById('yt-display-name').textContent = 'Logged in as ' + config.youtube_display_name;
    document.getElementById('yt-quota-display').textContent = 'Quota remaining: ' + (config.youtube_quota_remaining != null ? config.youtube_quota_remaining : '?');
  } else {
    document.getElementById('yt-login-area').classList.remove('hidden');
    document.getElementById('yt-user-area').classList.add('hidden');
  }
  document.getElementById('yt-test-result').classList.add('hidden');
  if (config.keyboard_shortcuts) {
    TwitchX.state.shortcuts = Object.assign({}, TwitchX.DEFAULT_SHORTCUTS, config.keyboard_shortcuts);
  }
  document.getElementById('s-pip-enabled').checked = !!config.pip_enabled;
  document.getElementById('s-low-latency').checked = !!config.low_latency_mode;
  var currentTheme = config.theme || 'dark';
  document.querySelectorAll('input[name="theme"]').forEach(function(radio) {
    radio.checked = radio.value === currentTheme;
  });
  var currentAccent = config.accent_color || '#FF9F0A';
  var swatchContainer = document.getElementById('accent-swatches');
  if (swatchContainer) {
    swatchContainer.replaceChildren();
    ACCENT_PALETTE.forEach(function(p) {
      var btn = document.createElement('button');
      btn.className = 'accent-swatch' + (p.value === currentAccent ? ' active' : '');
      btn.style.setProperty('--swatch-color', p.value);
      btn.title = p.label;
      btn.dataset.color = p.value;
      btn.setAttribute('aria-label', 'Use ' + p.label + ' accent color');
      btn.setAttribute('aria-pressed', String(p.value === currentAccent));
      btn.addEventListener('click', function() {
        document.querySelectorAll('.accent-swatch').forEach(function(s) {
          s.classList.remove('active');
          s.setAttribute('aria-pressed', 'false');
        });
        btn.classList.add('active');
        btn.setAttribute('aria-pressed', 'true');
        applyAccentColor(p.value);
      });
      swatchContainer.appendChild(btn);
    });
  }
  // Auto-expand Twitch/Kick advanced sections when user already has custom credentials;
  // collapse them when switching back to bundled so state is always fresh on open
  var tAdv = document.getElementById('twitch-advanced-section');
  var tToggle = document.getElementById('twitch-advanced-toggle');
  if (config.twitch_using_bundled === false) {
    if (tAdv) tAdv.classList.remove('hidden');
    if (tToggle) tToggle.textContent = 'Hide custom credentials ▴';
  } else {
    if (tAdv) tAdv.classList.add('hidden');
    if (tToggle) tToggle.textContent = 'Use custom credentials ▾';
  }
  var kAdv = document.getElementById('kick-advanced-section');
  var kToggle = document.getElementById('kick-advanced-toggle');
  if (config.kick_using_bundled === false) {
    if (kAdv) kAdv.classList.remove('hidden');
    if (kToggle) kToggle.textContent = 'Hide custom credentials ▴';
  } else {
    if (kAdv) kAdv.classList.add('hidden');
    if (kToggle) kToggle.textContent = 'Use custom credentials ▾';
  }

  // Update credential status badges
  var tBadge = document.getElementById('twitch-cred-status');
  if (tBadge) {
    if (config.twitch_using_bundled === false) {
      tBadge.textContent = 'Custom credentials';
      tBadge.className = 'cred-badge cred-custom';
    } else {
      tBadge.textContent = 'Built-in credentials';
      tBadge.className = 'cred-badge cred-bundled';
    }
  }
  var kBadge = document.getElementById('kick-cred-status');
  if (kBadge) {
    if (config.kick_using_bundled === false) {
      kBadge.textContent = 'Custom credentials';
      kBadge.className = 'cred-badge cred-custom';
    } else {
      kBadge.textContent = 'Built-in credentials';
      kBadge.className = 'cred-badge cred-bundled';
    }
  }
  var yBadge = document.getElementById('yt-cred-status');
  if (yBadge) {
    if (config.youtube_display_name) {
      yBadge.textContent = 'Connected';
      yBadge.className = 'cred-badge cred-custom';
    } else if (config.youtube_api_key) {
      yBadge.textContent = 'API key set';
      yBadge.className = 'cred-badge cred-custom';
    } else {
      yBadge.textContent = 'API key required';
      yBadge.className = 'cred-badge cred-missing';
    }
  }

  TwitchX.renderHotkeysSettings();
  var accountsTab = document.querySelector('.settings-tab[data-tab="accounts"]');
  document.querySelectorAll('.settings-tab').forEach(function(b) {
    var isAccounts = b === accountsTab;
    b.classList.toggle('active', isAccounts);
    b.setAttribute('aria-selected', String(isAccounts));
    b.tabIndex = isAccounts ? 0 : -1;
  });
  document.querySelectorAll('.settings-panel').forEach(function(p) { p.classList.remove('active'); });
  document.getElementById('settings-panel-accounts').classList.add('active');
  document.getElementById('stats-loading').classList.remove('hidden');
  document.getElementById('stats-content').classList.add('hidden');
  _setFeedback('');
  var overlay = document.getElementById('settings-overlay');
  if (overlay) {
    overlay.classList.add('visible');
    overlay.setAttribute('aria-hidden', 'false');
    overlay.removeAttribute('inert');
  }
  TwitchX._settingsSnapshot = JSON.stringify(_readAllFormValues());
  var versionEl = document.getElementById('settings-version-footer');
  if (versionEl) {
    versionEl.textContent = TwitchX.state.version ? 'v' + TwitchX.state.version : '';
  }
  var closeBtn = document.getElementById('close-settings');
  if (closeBtn) closeBtn.focus();
}

function openSettingsToTab(tab) {
  // Map legacy tab names to new tab structure
  var tabAliases = { general: 'player', twitch: 'accounts', kick: 'accounts', youtube: 'accounts', hotkeys: 'advanced', statistics: 'advanced' };
  tab = tabAliases[tab] || tab;
  TwitchX._settingsPendingTab = tab;
  openSettings();
  if (!TwitchX.state.configLoaded) return;
  TwitchX._settingsPendingTab = null;
  const tabBtn = document.querySelector('.settings-tab[data-tab="' + tab + '"]');
  document.querySelectorAll('.settings-tab').forEach(function(b) {
    var active = b === tabBtn;
    b.classList.toggle('active', active);
    b.setAttribute('aria-selected', String(active));
    b.tabIndex = active ? 0 : -1;
  });
  document.querySelectorAll('.settings-panel').forEach(function(p) { p.classList.remove('active'); });
  const panel = document.getElementById('settings-panel-' + tab);
  if (panel) panel.classList.add('active');
  if (tab === 'advanced') {
    loadWatchStatistics();
  }
}

function closeSettings() {
  if (_isSettingsDirty()) {
    if (!window.confirm('You have unsaved changes. Discard them?')) return;
  }
  var overlay = document.getElementById('settings-overlay');
  if (overlay) {
    overlay.classList.remove('visible');
    overlay.setAttribute('aria-hidden', 'true');
    overlay.setAttribute('inert', '');
  }
  TwitchX._settingsSnapshot = null;
  if (TwitchX._settingsReturnFocus && TwitchX._settingsReturnFocus.focus) {
    TwitchX._settingsReturnFocus.focus();
    TwitchX._settingsReturnFocus = null;
  }
}

function toggleSecret() {
  const input = document.getElementById('s-client-secret');
  input.type = input.type === 'password' ? 'text' : 'password';
}

function testConnection() {
  const cid = document.getElementById('s-client-id').value.trim();
  const cs = document.getElementById('s-client-secret').value.trim();
  // Empty fields are fine — Python falls back to bundled credentials
  document.getElementById('test-btn').disabled = true;
  _setFeedback('Testing Twitch...');
  TwitchX.api.test_connection(cid, cs);
}

function saveSettings() {
  const pipEnabled = document.getElementById('s-pip-enabled').checked;
  var activeSwatchEl = document.querySelector('.accent-swatch.active');
  var accentColor = activeSwatchEl ? activeSwatchEl.dataset.color : '#FF9F0A';
  const data = {
    theme: _getSelectedTheme(),
    client_id: document.getElementById('s-client-id').value.trim(),
    client_secret: document.getElementById('s-client-secret').value.trim(),
    streamlink_path: document.getElementById('s-streamlink').value.trim(),
    iina_path: document.getElementById('s-iina').value.trim(),
    refresh_interval: Math.max(30, parseInt(document.getElementById('s-interval').value, 10) || 60),
    kick_client_id: document.getElementById('s-kick-client-id').value.trim(),
    kick_client_secret: document.getElementById('s-kick-client-secret').value.trim(),
    youtube_api_key: document.getElementById('yt-api-key').value.trim(),
    youtube_client_id: document.getElementById('yt-client-id').value.trim(),
    youtube_client_secret: document.getElementById('yt-client-secret').value.trim(),
    external_player: document.getElementById('s-external-player').value,
    mpv_path: document.getElementById('s-mpv').value.trim(),
    keyboard_shortcuts: Object.assign({}, TwitchX.state.shortcuts),
    pip_enabled: pipEnabled,
    low_latency_mode: document.getElementById('s-low-latency').checked,
    recording_path: document.getElementById('s-recording-path').value.trim(),
    accent_color: accentColor,
  };
  TwitchX.state.pipEnabled = pipEnabled;
  const pipBtn = document.getElementById('pip-player-btn');
  if (pipBtn) pipBtn.classList.toggle('hidden', !pipEnabled);
  _setFeedback('Saving...', '');
  if (TwitchX.api) TwitchX.api.save_settings(JSON.stringify(data));
  TwitchX._settingsSnapshot = JSON.stringify(_readAllFormValues());
}

// Resume an open that was blocked waiting for the config push.
TwitchX.onConfigApplied = function() {
  if (!TwitchX._settingsPendingOpen) return;
  TwitchX._settingsPendingOpen = false;
  var tab = TwitchX._settingsPendingTab;
  TwitchX._settingsPendingTab = null;
  if (tab) {
    openSettingsToTab(tab);
  } else {
    openSettings();
  }
};

TwitchX.ACCENT_PALETTE = ACCENT_PALETTE;
TwitchX.applyAccentColor = applyAccentColor;
TwitchX.applyTheme = applyTheme;
TwitchX.resolveTheme = resolveTheme;
TwitchX.openSettings = openSettings;
TwitchX.openSettingsToTab = openSettingsToTab;
TwitchX.closeSettings = closeSettings;
TwitchX.toggleSecret = toggleSecret;
TwitchX.testConnection = testConnection;
TwitchX.saveSettings = saveSettings;
TwitchX.loadWatchStatistics = loadWatchStatistics;
TwitchX.renderWatchStats = renderWatchStats;
TwitchX._toggleStatsCompact = _toggleStatsCompact;
