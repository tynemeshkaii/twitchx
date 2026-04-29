window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

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
  // Show/hide Kick login/user area
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
  // Show/hide YouTube login/user area
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
  // Hotkeys tab
  if (config.keyboard_shortcuts) {
    TwitchX.state.shortcuts = Object.assign({}, TwitchX.DEFAULT_SHORTCUTS, config.keyboard_shortcuts);
  }
  document.getElementById('s-pip-enabled').checked = !!config.pip_enabled;
  TwitchX.renderHotkeysSettings();
  // Reset to General tab
  document.querySelectorAll('.settings-tab').forEach(function(b) { b.classList.remove('active'); });
  document.querySelectorAll('.settings-panel').forEach(function(p) { p.classList.remove('active'); });
  document.querySelector('.settings-tab[data-tab="general"]').classList.add('active');
  document.getElementById('settings-panel-general').classList.add('active');
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
  // Apply pip button visibility immediately
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
