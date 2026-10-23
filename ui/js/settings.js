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

function formatStatsDuration(seconds) {
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
    document.getElementById('stat-today-time').textContent = formatStatsDuration(stats.today.total_sec);
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
        formatStatsDuration(row.total_sec),
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
    document.getElementById('stat-total-time').textContent = formatStatsDuration(stats.total.total_sec);
    document.getElementById('stat-total-channels').textContent = stats.total.unique_channels || 0;
  }

  var topContainer = document.getElementById('stats-top-channels');
  topContainer.textContent = '';
  if (stats.top_channels && stats.top_channels.length > 0) {
    stats.top_channels.forEach(function(ch) {
      var item = document.createElement('div');

      var leftSpan = document.createElement('span');
      leftSpan.className = 'stats-channel-wrap';
      var dot = document.createElement('span');
      dot.className = 'platform-dot ' + (ch.platform || 'twitch');
      dot.title = TwitchX.platformLabel(ch.platform || 'twitch');
      leftSpan.appendChild(dot);
      var chName = document.createElement('span');
      chName.className = 'stats-channel';
      chName.textContent = ch.display_name || ch.channel;
      leftSpan.appendChild(chName);

      var rightSpan = document.createElement('span');
      rightSpan.className = 'stats-value';
      item.className = 'stats-list-item settings-row';
      rightSpan.textContent = formatStatsDuration(ch.total_sec) + ' \u00b7 ' + ch.sessions_count + ' sessions';

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
}

// ── Instant apply ────────────────────────────────────────
// Every control saves on change through the partial save_settings payload.
// Text paths wait 300ms after the last keystroke; toggles and selects go at
// once. Credentials are the exception: they save from their own button.

const SETTINGS_TEXT_DEBOUNCE_MS = 300;
const SETTINGS_SAVED_MS = 1600;
const _settingsTextTimers = {};
let _settingsSavedRow = null;
let _settingsSavedTimer = null;

const CREDENTIAL_FIELDS = {
  twitch: { 's-client-id': 'client_id', 's-client-secret': 'client_secret' },
  kick: { 's-kick-client-id': 'kick_client_id', 's-kick-client-secret': 'kick_client_secret' },
  youtube: {
    'yt-api-key': 'youtube_api_key',
    'yt-client-id': 'youtube_client_id',
    'yt-client-secret': 'youtube_client_secret',
  },
};

function _setFeedback(msg, type) {
  var fb = document.getElementById('settings-feedback');
  if (!fb) return;
  fb.textContent = msg;
  fb.className = type || '';
}

// row: the .settings-row whose control changed; it shows a quiet "Saved".
function saveSettingsPartial(partial, row) {
  if (!TwitchX.api) return;
  _settingsSavedRow = row || null;
  TwitchX.api.save_settings(JSON.stringify(partial));
}

function _markRowSaved(row) {
  document.querySelectorAll('.settings-saved.visible').forEach(function(el) { el.classList.remove('visible'); });
  if (_settingsSavedTimer) clearTimeout(_settingsSavedTimer);
  if (!row) return;
  var mark = row.querySelector('.settings-saved');
  if (!mark) {
    mark = document.createElement('span');
    mark.className = 'settings-saved';
    mark.textContent = 'Saved';
    var control = row.querySelector('input, select, .segmented, .accent-swatches, .settings-btn.primary');
    row.insertBefore(mark, control ? control.closest('.secret-row') || control : null);
  }
  mark.classList.add('visible');
  _settingsSavedTimer = setTimeout(function() { mark.classList.remove('visible'); }, SETTINGS_SAVED_MS);
}

function _settingValue(el) {
  if (el.type === 'checkbox') return el.checked;
  if (el.dataset.setting === 'refresh_interval') return Math.max(30, parseInt(el.value, 10) || 60);
  return el.tagName === 'SELECT' ? el.value : el.value.trim();
}

function _saveSettingControl(el) {
  var partial = {};
  partial[el.dataset.setting] = _settingValue(el);
  if (el.dataset.setting === 'pip_enabled') {
    TwitchX.state.pipEnabled = el.checked;
    var pipBtn = document.getElementById('pip-player-btn');
    if (pipBtn) pipBtn.classList.toggle('hidden', !el.checked);
  }
  if (el.dataset.setting === 'external_player') {
    document.getElementById('s-mpv-group').classList.toggle('hidden', el.value !== 'mpv');
  }
  saveSettingsPartial(partial, el.closest('.settings-row'));
}

function _bindInstantSettings() {
  document.querySelectorAll('#settings-modal [data-setting]').forEach(function(el) {
    if (el.hasAttribute('data-debounce')) {
      el.addEventListener('input', function() {
        clearTimeout(_settingsTextTimers[el.id]);
        _settingsTextTimers[el.id] = setTimeout(function() { _saveSettingControl(el); }, SETTINGS_TEXT_DEBOUNCE_MS);
      });
      // Leaving the field flushes a pending save at once.
      el.addEventListener('blur', function() {
        if (!_settingsTextTimers[el.id]) return;
        clearTimeout(_settingsTextTimers[el.id]);
        _settingsTextTimers[el.id] = null;
        _saveSettingControl(el);
      });
    } else {
      // The interval select too: change fires once per pick, never per step.
      el.addEventListener('change', function() { _saveSettingControl(el); });
    }
  });

  document.querySelectorAll('#theme-options [role="radio"]').forEach(function(btn) {
    btn.addEventListener('click', function() { _pickTheme(btn.dataset.themeValue, true); });
    btn.addEventListener('keydown', function(e) {
      if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].indexOf(e.key) === -1) return;
      e.preventDefault();
      var all = Array.from(document.querySelectorAll('#theme-options [role="radio"]'));
      var step = (e.key === 'ArrowRight' || e.key === 'ArrowDown') ? 1 : -1;
      var next = all[(all.indexOf(btn) + step + all.length) % all.length];
      next.focus();
      _pickTheme(next.dataset.themeValue, true);
    });
  });

  document.querySelectorAll('#settings-modal [data-creds]').forEach(function(btn) {
    btn.addEventListener('click', function() { saveCredentials(btn.dataset.creds, btn); });
  });

  var connect = document.getElementById('twitch-connect-btn');
  if (connect) connect.addEventListener('click', function() {
    if (!TwitchX.api) return;
    if (TwitchX.state.currentUser) TwitchX.api.logout();
    else TwitchX.api.login();
  });
}

function _pickTheme(mode, save) {
  document.querySelectorAll('#theme-options [role="radio"]').forEach(function(btn) {
    var on = btn.dataset.themeValue === mode;
    btn.setAttribute('aria-checked', String(on));
    btn.classList.toggle('active', on);
    btn.tabIndex = on ? 0 : -1;
  });
  if (!save) return;
  applyTheme(mode);
  saveSettingsPartial({ theme: mode }, document.getElementById('theme-options').closest('.settings-row'));
}

function _renderAccentSwatches(current) {
  var container = document.getElementById('accent-swatches');
  if (!container) return;
  container.replaceChildren();
  ACCENT_PALETTE.forEach(function(p) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'accent-swatch' + (p.value === current ? ' active' : '');
    btn.style.setProperty('--swatch-color', p.value);
    btn.title = p.label;
    btn.dataset.color = p.value;
    btn.setAttribute('role', 'radio');
    btn.setAttribute('aria-label', p.label);
    btn.setAttribute('aria-checked', String(p.value === current));
    btn.tabIndex = p.value === current ? 0 : -1;
    btn.addEventListener('click', function() {
      container.querySelectorAll('.accent-swatch').forEach(function(sw) {
        var on = sw === btn;
        sw.classList.toggle('active', on);
        sw.setAttribute('aria-checked', String(on));
        sw.tabIndex = on ? 0 : -1;
      });
      applyAccentColor(p.value);
      saveSettingsPartial({ accent_color: p.value }, container.closest('.settings-row'));
    });
    btn.addEventListener('keydown', function(e) {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      e.preventDefault();
      var all = Array.from(container.querySelectorAll('.accent-swatch'));
      var next = all[(all.indexOf(btn) + (e.key === 'ArrowRight' ? 1 : -1) + all.length) % all.length];
      next.focus();
      next.click();
    });
    container.appendChild(btn);
  });
}

function saveCredentials(platform, btn) {
  var fields = CREDENTIAL_FIELDS[platform];
  if (!fields) return;
  var partial = {};
  Object.keys(fields).forEach(function(id) {
    partial[fields[id]] = document.getElementById(id).value.trim();
  });
  saveSettingsPartial(partial, btn ? btn.closest('.settings-row') : null);
}

function _credentialsDirty() {
  var config = TwitchX.state.fullConfig || {};
  return Object.keys(CREDENTIAL_FIELDS).some(function(platform) {
    var fields = CREDENTIAL_FIELDS[platform];
    return Object.keys(fields).some(function(id) {
      var el = document.getElementById(id);
      return el && el.value.trim() !== (config[fields[id]] || '');
    });
  });
}

function saveShortcuts() {
  saveSettingsPartial({ keyboard_shortcuts: Object.assign({}, TwitchX.state.shortcuts) }, null);
}

// Status line + button of each platform row. Called on open and on every
// auth change (account.js updateAccountChip).
function syncSettingsAccounts() {
  var config = TwitchX.state.fullConfig || {};
  function setStatus(id, text, kind) {
    var el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = 'account-status' + (kind ? ' ' + kind : '');
  }
  function signedIn(user) { return 'Signed in as ' + (user.display_name || user.login); }

  var twitch = TwitchX.state.currentUser;
  setStatus('twitch-cred-status', twitch ? signedIn(twitch) : 'Not connected', twitch ? 'ok' : '');
  var connect = document.getElementById('twitch-connect-btn');
  if (connect) connect.textContent = twitch ? 'Disconnect' : 'Connect';

  var kick = TwitchX.state.kickUser;
  setStatus('kick-cred-status', kick ? signedIn(kick) : 'Not connected', kick ? 'ok' : '');
  var kLogin = document.getElementById('kick-login-area');
  var kUser = document.getElementById('kick-user-area');
  if (kLogin) kLogin.classList.toggle('hidden', !!kick);
  if (kUser) kUser.classList.toggle('hidden', !kick);

  var yt = TwitchX.state.youtubeUser;
  if (yt) setStatus('yt-cred-status', signedIn(yt), 'ok');
  else if (config.youtube_api_key) setStatus('yt-cred-status', 'Not connected', '');
  else setStatus('yt-cred-status', 'API key required', 'warn');
  var yLogin = document.getElementById('yt-login-area');
  var yUser = document.getElementById('yt-user-area');
  var yImport = document.getElementById('yt-import-row');
  if (yLogin) yLogin.classList.toggle('hidden', !!yt);
  if (yUser) yUser.classList.toggle('hidden', !yt);
  if (yImport) yImport.classList.toggle('hidden', !yt);
}

function _openSettingsTab(tab) {
  const tabBtn = document.querySelector('.settings-tab[data-tab="' + tab + '"]');
  if (!tabBtn) return;
  TwitchX.setActiveTab(Array.from(document.querySelectorAll('.settings-tab')), tabBtn);
  document.querySelectorAll('.settings-panel').forEach(function(p) { p.classList.remove('active'); });
  const panel = document.getElementById('settings-panel-' + tab);
  if (panel) panel.classList.add('active');
  if (tab === 'advanced') loadWatchStatistics();
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
  // with defaults and the first change would save them over the real config.
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
  document.getElementById('s-recording-path').value = config.recording_path || '';
  var extPlayer = config.external_player || 'iina';
  document.getElementById('s-external-player').value = extPlayer;
  document.getElementById('s-mpv-group').classList.toggle('hidden', extPlayer !== 'mpv');
  _setIntervalValue(String(config.refresh_interval || 60));
  document.getElementById('s-kick-client-id').value = config.kick_client_id || '';
  document.getElementById('s-kick-client-secret').value = config.kick_client_secret || '';
  document.getElementById('yt-api-key').value = config.youtube_api_key || '';
  document.getElementById('yt-client-id').value = config.youtube_client_id || '';
  document.getElementById('yt-client-secret').value = config.youtube_client_secret || '';
  document.getElementById('yt-quota-display').textContent = config.youtube_display_name
    ? 'Quota remaining: ' + (config.youtube_quota_remaining != null ? config.youtube_quota_remaining : '?')
    : '';
  document.getElementById('yt-test-result').classList.add('hidden');
  if (config.keyboard_shortcuts) {
    TwitchX.state.shortcuts = Object.assign({}, TwitchX.DEFAULT_SHORTCUTS, config.keyboard_shortcuts);
  }
  document.getElementById('s-pip-enabled').checked = !!config.pip_enabled;
  document.getElementById('s-low-latency').checked = !!config.low_latency_mode;
  document.getElementById('s-stream-codecs').value = config.stream_codecs || 'auto';
  _pickTheme(config.theme || 'dark', false);
  _renderAccentSwatches(config.accent_color || '#FF9F0A');

  // Custom credentials open their Advanced block; built-in ones keep it shut.
  var tAdv = document.getElementById('twitch-advanced-section');
  if (tAdv) tAdv.open = config.twitch_using_bundled === false;
  var kAdv = document.getElementById('kick-advanced-section');
  if (kAdv) kAdv.open = config.kick_using_bundled === false;
  var yAdv = document.getElementById('yt-advanced-section');
  if (yAdv) yAdv.open = !config.youtube_api_key;
  syncSettingsAccounts();

  TwitchX.renderHotkeysSettings();
  _openSettingsTab('accounts');
  document.getElementById('stats-loading').classList.remove('hidden');
  document.getElementById('stats-content').classList.add('hidden');
  _setFeedback('');
  var overlay = document.getElementById('settings-overlay');
  if (overlay) {
    overlay.classList.add('visible');
    overlay.setAttribute('aria-hidden', 'false');
    overlay.removeAttribute('inert');
  }
  var versionEl = document.getElementById('settings-version-footer');
  if (versionEl) {
    versionEl.textContent = TwitchX.state.version ? 'TwitchX ' + TwitchX.state.version : '';
  }
  // Focus starts on the section list, like a native settings window.
  var activeTab = document.querySelector('.settings-tab.active');
  if (activeTab) activeTab.focus({ preventScroll: true });
}

function openSettingsToTab(tab) {
  // Map legacy tab names to new tab structure
  var tabAliases = { general: 'player', twitch: 'accounts', kick: 'accounts', youtube: 'accounts', hotkeys: 'advanced', statistics: 'advanced' };
  tab = tabAliases[tab] || tab;
  TwitchX._settingsPendingTab = tab;
  openSettings();
  if (!TwitchX.state.configLoaded) return;
  TwitchX._settingsPendingTab = null;
  _openSettingsTab(tab);
}

function closeSettings() {
  // Everything else is already saved; typed-in credentials are not until
  // their Save button is pressed.
  if (_credentialsDirty()) {
    if (!window.confirm('Discard the credentials you have not saved?')) return;
  }
  // Flush text fields still waiting on their debounce.
  Object.keys(_settingsTextTimers).forEach(function(id) {
    if (!_settingsTextTimers[id]) return;
    clearTimeout(_settingsTextTimers[id]);
    _settingsTextTimers[id] = null;
    _saveSettingControl(document.getElementById(id));
  });
  var overlay = document.getElementById('settings-overlay');
  if (overlay) {
    overlay.classList.remove('visible');
    overlay.setAttribute('aria-hidden', 'true');
    overlay.setAttribute('inert', '');
  }
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

window.onSettingsSaved = function() {
  _markRowSaved(_settingsSavedRow);
  _settingsSavedRow = null;
  if (document.getElementById('settings-overlay').classList.contains('visible')) syncSettingsAccounts();
};

// save_settings rejected the payload.
window.onSettingsError = function(data) {
  var msg = (data && data.message) || 'Could not save settings';
  _settingsSavedRow = null;
  _setFeedback('Error: ' + msg, 'error');
};

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
TwitchX.saveSettingsPartial = saveSettingsPartial;
TwitchX.saveCredentials = saveCredentials;
TwitchX.saveShortcuts = saveShortcuts;
TwitchX.syncSettingsAccounts = syncSettingsAccounts;
TwitchX._bindInstantSettings = _bindInstantSettings;
TwitchX.showSettingsTab = _openSettingsTab;
TwitchX.loadWatchStatistics = loadWatchStatistics;
TwitchX.renderWatchStats = renderWatchStats;

