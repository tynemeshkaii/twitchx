window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

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
    emptyMsg.style.cssText = 'font-size:12px;color:var(--text-muted);padding:8px 0;';
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
    emptyMsg.style.cssText = 'font-size:12px;color:var(--text-muted);padding:8px 0;';
    emptyMsg.textContent = 'No watch data yet.';
    topContainer.appendChild(emptyMsg);
  }

  document.getElementById('stats-loading').style.display = 'none';
  document.getElementById('stats-content').style.display = 'block';
}

function loadWatchStatistics() {
  if (!TwitchX.api) return;
  try {
    var stats = JSON.parse(TwitchX.api.get_watch_statistics('all'));
    renderWatchStats(stats);
  } catch (e) {
    console.warn('Failed to load watch statistics:', e);
    document.getElementById('stats-loading').textContent = 'Failed to load statistics';
  }
}

function openSettings() {
  if (!TwitchX.api) return;
  const config = TwitchX.api.get_full_config_for_settings();
  document.getElementById('s-client-id').value = config.client_id || '';
  document.getElementById('s-client-secret').value = config.client_secret || '';
  document.getElementById('s-streamlink').value = config.streamlink_path || 'streamlink';
  document.getElementById('s-iina').value = config.iina_path || '/Applications/IINA.app/Contents/MacOS/iina-cli';
  document.getElementById('s-interval').value = String(config.refresh_interval || 60);
  document.getElementById('s-kick-client-id').value = config.kick_client_id || '';
  document.getElementById('s-kick-client-secret').value = config.kick_client_secret || '';
  if (config.kick_display_name) {
    document.getElementById('kick-login-area').style.display = 'none';
    document.getElementById('kick-user-area').style.display = 'block';
    document.getElementById('kick-user-display').textContent = 'Logged in as ' + config.kick_display_name;
  } else {
    document.getElementById('kick-login-area').style.display = 'block';
    document.getElementById('kick-user-area').style.display = 'none';
  }
  document.getElementById('yt-api-key').value = config.youtube_api_key || '';
  document.getElementById('yt-client-id').value = config.youtube_client_id || '';
  document.getElementById('yt-client-secret').value = config.youtube_client_secret || '';
  if (config.youtube_display_name) {
    document.getElementById('yt-login-area').style.display = 'none';
    document.getElementById('yt-user-area').style.display = 'block';
    document.getElementById('yt-display-name').textContent = 'Logged in as ' + config.youtube_display_name;
    document.getElementById('yt-quota-display').textContent = 'Quota remaining: ' + (config.youtube_quota_remaining != null ? config.youtube_quota_remaining : '?');
  } else {
    document.getElementById('yt-login-area').style.display = 'block';
    document.getElementById('yt-user-area').style.display = 'none';
  }
  document.getElementById('yt-test-result').style.display = 'none';
  if (config.keyboard_shortcuts) {
    TwitchX.state.shortcuts = Object.assign({}, TwitchX.DEFAULT_SHORTCUTS, config.keyboard_shortcuts);
  }
  document.getElementById('s-pip-enabled').checked = !!config.pip_enabled;
  TwitchX.renderHotkeysSettings();
  document.querySelectorAll('.settings-tab').forEach(function(b) { b.classList.remove('active'); });
  document.querySelectorAll('.settings-panel').forEach(function(p) { p.classList.remove('active'); });
  document.querySelector('.settings-tab[data-tab="general"]').classList.add('active');
  document.getElementById('settings-panel-general').classList.add('active');
  document.getElementById('stats-loading').style.display = 'block';
  document.getElementById('stats-content').style.display = 'none';
  document.getElementById('settings-feedback').textContent = '';
  document.getElementById('settings-overlay').classList.add('visible');
}

function openSettingsToTab(tab) {
  openSettings();
  document.querySelectorAll('.settings-tab').forEach(function(b) { b.classList.remove('active'); });
  document.querySelectorAll('.settings-panel').forEach(function(p) { p.classList.remove('active'); });
  const tabBtn = document.querySelector('.settings-tab[data-tab="' + tab + '"]');
  const panel = document.getElementById('settings-panel-' + tab);
  if (tabBtn) tabBtn.classList.add('active');
  if (panel) panel.classList.add('active');
  if (tab === 'statistics') {
    loadWatchStatistics();
  }
}

function closeSettings() {
  document.getElementById('settings-overlay').classList.remove('visible');
}

function toggleSecret() {
  const input = document.getElementById('s-client-secret');
  input.type = input.type === 'password' ? 'text' : 'password';
}

function testConnection() {
  const cid = document.getElementById('s-client-id').value.trim();
  const cs = document.getElementById('s-client-secret').value.trim();
  if (!cid || !cs) {
    const fb = document.getElementById('settings-feedback');
    fb.textContent = 'Client ID and Secret are required';
    fb.style.color = 'var(--error-red)';
    return;
  }
  document.getElementById('test-btn').disabled = true;
  document.getElementById('settings-feedback').textContent = 'Testing...';
  document.getElementById('settings-feedback').style.color = 'var(--text-muted)';
  TwitchX.api.test_connection(cid, cs);
}

function saveSettings() {
  const pipEnabled = document.getElementById('s-pip-enabled').checked;
  const data = {
    client_id: document.getElementById('s-client-id').value.trim(),
    client_secret: document.getElementById('s-client-secret').value.trim(),
    streamlink_path: document.getElementById('s-streamlink').value.trim(),
    iina_path: document.getElementById('s-iina').value.trim(),
    refresh_interval: parseInt(document.getElementById('s-interval').value, 10),
    kick_client_id: document.getElementById('s-kick-client-id').value.trim(),
    kick_client_secret: document.getElementById('s-kick-client-secret').value.trim(),
    youtube_api_key: document.getElementById('yt-api-key').value.trim(),
    youtube_client_id: document.getElementById('yt-client-id').value.trim(),
    youtube_client_secret: document.getElementById('yt-client-secret').value.trim(),
    keyboard_shortcuts: Object.assign({}, TwitchX.state.shortcuts),
    pip_enabled: pipEnabled,
  };
  TwitchX.state.pipEnabled = pipEnabled;
  const pipBtn = document.getElementById('pip-player-btn');
  if (pipBtn) pipBtn.style.display = pipEnabled ? '' : 'none';
  if (TwitchX.api) TwitchX.api.save_settings(JSON.stringify(data));
}

TwitchX.openSettings = openSettings;
TwitchX.openSettingsToTab = openSettingsToTab;
TwitchX.closeSettings = closeSettings;
TwitchX.toggleSecret = toggleSecret;
TwitchX.testConnection = testConnection;
TwitchX.saveSettings = saveSettings;
TwitchX.loadWatchStatistics = loadWatchStatistics;
TwitchX.renderWatchStats = renderWatchStats;
