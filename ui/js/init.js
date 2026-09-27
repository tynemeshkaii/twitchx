window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

// Capture-phase listener intercepts keydowns during shortcut rebinding
document.addEventListener('keydown', function(e) {
  if (!TwitchX._rebindAction) return;
  e.preventDefault();
  e.stopPropagation();
  if (e.key === 'Escape') {
    TwitchX._rebindAction = null;
    TwitchX.renderHotkeysSettings();
    return;
  }

  // Phase 9: duplicate-key detection with confirm-swap
  // Merge defaults + current state so we catch collisions with untouched defaults too.
  const allShortcuts = Object.assign({}, TwitchX.DEFAULT_SHORTCUTS, TwitchX.state.shortcuts);
  const existing = Object.keys(allShortcuts).find(function(action) {
    return action !== TwitchX._rebindAction && allShortcuts[action] === e.key;
  });
  if (existing) {
    var msg = '"' + TwitchX.formatKeyName(e.key) + '" is already bound to "' +
              TwitchX.SHORTCUT_LABELS[existing] + '". Swap bindings?';
    if (window.confirm(msg)) {
      TwitchX.state.shortcuts[existing] = TwitchX.DEFAULT_SHORTCUTS[TwitchX._rebindAction];
      TwitchX.state.shortcuts[TwitchX._rebindAction] = e.key;
    }
    TwitchX._rebindAction = null;
    TwitchX.renderHotkeysSettings();
    return;
  }

  TwitchX.state.shortcuts[TwitchX._rebindAction] = e.key;
  TwitchX._rebindAction = null;
  TwitchX.renderHotkeysSettings();
}, true);

document.addEventListener('DOMContentLoaded', function() {
  if (TwitchX.mountIcons) TwitchX.mountIcons();
  if (TwitchX.applyYoutubeGating) TwitchX.applyYoutubeGating();
  TwitchX.loadPinnedStreams();
  TwitchX._bindSidebarEvents();
  TwitchX._bindToolbarEvents();
  TwitchX._bindPlayerEvents();
  TwitchX._bindBrowseEvents();
  TwitchX._bindChannelEvents();
  TwitchX._bindChatEvents();
  TwitchX._bindSettingsEvents();
  TwitchX._bindContextMenuEvents();
  TwitchX._bindKeyboardEvents();
  TwitchX._bindGlobalEvents();
  TwitchX._bindMultistreamEvents();
  TwitchX._bindPaletteEvents();
  TwitchX._initMultistreamSlots();
  TwitchX._watchFullscreenChanges();
  TwitchX._watchNetworkChanges();

  // Apply saved theme and accent color immediately from localStorage cache
  (function() {
    var savedTheme = localStorage.getItem('twitchx.theme.mode') || 'dark';
    if (TwitchX.applyTheme) TwitchX.applyTheme(savedTheme);
    var saved = localStorage.getItem('twitchx.accent') || '#FF9F0A';
    if (TwitchX.applyAccentColor) TwitchX.applyAccentColor(saved);
  })();

  // Watch system theme changes when in Auto mode
  (function() {
    var mediaQuery = window.matchMedia('(prefers-color-scheme: light)');
    var handler = function() {
      var mode = localStorage.getItem('twitchx.theme.mode') || 'dark';
      if (mode === 'auto' && TwitchX.applyTheme) {
        TwitchX.applyTheme('auto');
      }
    };
    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', handler);
    } else if (mediaQuery.addListener) {
      mediaQuery.addListener(handler);
    }
  })();

  // Restore saved grid density mode
  (function() {
    var validModes = ['grid', 'comfortable', 'compact', 'list'];
    var saved = localStorage.getItem('twitchx.grid_mode') || 'grid';
    if (validModes.indexOf(saved) === -1) saved = 'grid';
    TwitchX.state.gridMode = saved;
    var btn = document.getElementById('grid-toggle-btn');
    if (btn) {
      var iconMap = {
        grid: 'grid-toggle',
        comfortable: 'grid-toggle',
        compact: 'compact-toggle',
        list: 'list-toggle'
      };
      var titleMap = {
        grid: 'Switch to comfortable view',
        comfortable: 'Switch to compact view',
        compact: 'Switch to list view',
        list: 'Switch to grid view'
      };
      btn.title = titleMap[saved];
      TwitchX.setIconOnly(btn, iconMap[saved], 16);
    }
  })();

  // Apply saved mini mode
  TwitchX.applyMiniMode();

  // Restore sidebar collapse state
  (function() {
    var saved = localStorage.getItem('twitchx.sidebar.collapsed');
    if (saved === '1') {
      document.getElementById('sidebar').classList.add('collapsed-sidebar');
      TwitchX.renderSidebar();
    }
  })();

  // Restore chat timestamps state
  (function() {
    var saved = localStorage.getItem('twitchx.chat_timestamps');
    if (saved === '1') {
      TwitchX.chatTimestamps = true;
      var btn = document.getElementById('chat-timestamp-btn');
      if (btn) btn.classList.add('active');
    } else {
      TwitchX.chatTimestamps = false;
    }
  })();

  // Show skeleton grid while waiting for first data
  if (TwitchX.state.favorites && TwitchX.state.favorites.length > 0) {
    TwitchX.showSkeletonGrid();
  }
});

TwitchX._bindSidebarEvents = function() {
  const loginBtn = document.getElementById('login-btn');
  if (loginBtn) loginBtn.addEventListener('click', function() { if (TwitchX.api) TwitchX.api.login(); });
  const logoutLink = document.getElementById('logout-link');
  if (logoutLink) logoutLink.addEventListener('click', TwitchX.doLogout);
  const importLink = document.getElementById('import-link');
  if (importLink) importLink.addEventListener('click', function() { if (TwitchX.api) TwitchX.api.import_follows(); });
  const kickLoginBtn = document.getElementById('kick-login-sidebar-btn');
  if (kickLoginBtn) kickLoginBtn.addEventListener('click', function() { if (TwitchX.api) TwitchX.api.kick_login(); });
  const kickLogoutLink = document.getElementById('kick-logout-link');
  if (kickLogoutLink) kickLogoutLink.addEventListener('click', function() { if (TwitchX.api) TwitchX.api.kick_logout(); });
  const addBtn = document.getElementById('add-btn');
  if (addBtn) addBtn.addEventListener('click', TwitchX.addChannel);

  // Sidebar collapse toggle
  var collapseBtn = document.getElementById('sidebar-collapse-btn');
  if (collapseBtn) collapseBtn.addEventListener('click', function() {
    var sidebar = document.getElementById('sidebar');
    var collapsed = sidebar.classList.toggle('collapsed-sidebar');
    localStorage.setItem('twitchx.sidebar.collapsed', collapsed ? '1' : '0');
    // Force reflow so browser commits the new width before rebuilding
    sidebar.offsetHeight;
    TwitchX.renderSidebar();
  });

  function setPlatformFilter(platform) {
    TwitchX.state.activePlatformFilter = platform;
    TwitchX.renderGrid();
    TwitchX.renderSidebar();
    // Sync sidebar tabs and toolbar chips
    document.querySelectorAll('.platform-tab').forEach(function(tab) {
      var active = tab.dataset.platform === platform;
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    document.querySelectorAll('.platform-chip').forEach(function(chip) {
      var active = chip.dataset.platform === platform;
      chip.classList.toggle('active', active);
      chip.setAttribute('aria-selected', String(active));
      chip.tabIndex = active ? 0 : -1;
    });
  }

  // Platform tab switching (sidebar)
  document.querySelectorAll('.platform-tab').forEach(function(btn) {
    btn.addEventListener('click', function() {
      setPlatformFilter(btn.dataset.platform);
    });
    btn.addEventListener('keydown', function(e) {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      e.preventDefault();
      TwitchX.focusAdjacentTab(Array.from(document.querySelectorAll('.platform-tab')), btn, e.key === 'ArrowRight' ? 1 : -1);
    });
  });

  // Platform chip switching (toolbar)
  document.querySelectorAll('.platform-chip').forEach(function(btn) {
    btn.addEventListener('click', function() {
      setPlatformFilter(btn.dataset.platform);
    });
    btn.addEventListener('keydown', function(e) {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      e.preventDefault();
      TwitchX.focusAdjacentTab(Array.from(document.querySelectorAll('.platform-chip')), btn, e.key === 'ArrowRight' ? 1 : -1);
    });
  });

  const searchInput = document.getElementById('search-input');
  if (searchInput) {
    searchInput.addEventListener('input', function(e) {
      const query = e.target.value.trim();
      clearTimeout(TwitchX.state.searchDebounce);
      if (!query) {
        TwitchX.state.searchResults = [];
        document.getElementById('search-dropdown').classList.remove('visible');
        searchInput.setAttribute('aria-expanded', 'false');
        return;
      }
      TwitchX.state.searchDebounce = setTimeout(function() {
        const searchPlatform = TwitchX.state.activePlatformFilter === 'all' ? 'all' : TwitchX.state.activePlatformFilter;
        if (TwitchX.api) TwitchX.api.search_channels(query, searchPlatform);
      }, 400);
    });
    searchInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') { e.preventDefault(); TwitchX.addChannel(); }
    });
  }
};

TwitchX._bindToolbarEvents = function() {
  const sortSelect = document.getElementById('sort-select');
  if (sortSelect) sortSelect.addEventListener('change', function(e) {
    TwitchX.state.sortKey = e.target.value;
    TwitchX.renderGrid();
  });
  const filterInput = document.getElementById('filter-input');
  if (filterInput) filterInput.addEventListener('input', function(e) {
    TwitchX.state.filterText = e.target.value;
    TwitchX.renderGrid();
  });
  const browseNavBtn = document.getElementById('browse-nav-btn');
  if (browseNavBtn) browseNavBtn.addEventListener('click', TwitchX.showBrowseView);
  const toolbarRefreshBtn = document.getElementById('toolbar-refresh-btn');
  if (toolbarRefreshBtn) toolbarRefreshBtn.addEventListener('click', TwitchX.doRefresh);
  var gridToggleBtn = document.getElementById('grid-toggle-btn');
  var DENSITY_MODES = ['grid', 'comfortable', 'compact', 'list'];
  var DENSITY_ICONS = {
    grid: 'grid-toggle',
    comfortable: 'grid-toggle',
    compact: 'compact-toggle',
    list: 'list-toggle'
  };
  var DENSITY_TITLES = {
    grid: 'Switch to comfortable view',
    comfortable: 'Switch to compact view',
    compact: 'Switch to list view',
    list: 'Switch to grid view'
  };
  if (gridToggleBtn) gridToggleBtn.addEventListener('click', function() {
    var idx = DENSITY_MODES.indexOf(TwitchX.state.gridMode);
    var next = DENSITY_MODES[(idx + 1) % DENSITY_MODES.length];
    TwitchX.state.gridMode = next;
    localStorage.setItem('twitchx.grid_mode', next);
    gridToggleBtn.title = DENSITY_TITLES[next];
    TwitchX.setIconOnly(gridToggleBtn, DENSITY_ICONS[next], 16);
    TwitchX.renderGrid();
  });
};

TwitchX._bindPlayerEvents = function() {
  const watchBtn = document.getElementById('watch-btn');
  if (watchBtn) watchBtn.addEventListener('click', TwitchX.doWatch);
  const stopBtn = document.getElementById('stop-player-btn');
  if (stopBtn) stopBtn.addEventListener('click', function() { if (TwitchX.api) TwitchX.api.stop_player(); });
  const closeBtn = document.getElementById('close-player-btn');
  if (closeBtn) closeBtn.addEventListener('click', function() { if (TwitchX.api) TwitchX.api.stop_player(); });
  const fsBtn = document.getElementById('fullscreen-player-btn');
  if (fsBtn) fsBtn.addEventListener('click', TwitchX.toggleVideoFullscreen);
  const playerContent = document.getElementById('player-content');
  if (playerContent) {
    playerContent.addEventListener('dblclick', function(e) {
      if (e.target.closest('#stream-video')) TwitchX.toggleVideoFullscreen();
    });
  }
  const pipBtn = document.getElementById('pip-player-btn');
  if (pipBtn) pipBtn.addEventListener('click', function() {
    TwitchX.togglePiP(TwitchX.getPlayerVideo());
  });
  const extBtn = document.getElementById('watch-external-btn');
  if (extBtn) extBtn.addEventListener('click', function() {
    if (!TwitchX.state.selectedChannel || !TwitchX.api) return;
    const quality = document.getElementById('quality-select').value;
    const platform = TwitchX.state.selectedPlatform ||
      TwitchX.getChannelPlatform(TwitchX.state.selectedChannel, TwitchX.state.selectedChannelKey);
    if (TwitchX.api.watch_external_platform) TwitchX.api.watch_external_platform(TwitchX.state.selectedChannel, platform, quality);
    else TwitchX.api.watch_external(TwitchX.state.selectedChannel, quality);
  });
  const browserBtn = document.getElementById('browser-btn');
  if (browserBtn) browserBtn.addEventListener('click', TwitchX.doBrowser);
  const refreshBtn = document.getElementById('refresh-btn');
  if (refreshBtn) refreshBtn.addEventListener('click', TwitchX.doRefresh);
  const settingsBtn = document.getElementById('settings-btn');
  if (settingsBtn) settingsBtn.addEventListener('click', TwitchX.openSettings);
  const toggleChatBtn = document.getElementById('toggle-chat-btn');
  if (toggleChatBtn) toggleChatBtn.addEventListener('click', TwitchX.toggleChatPanel);
  const recordBtn = document.getElementById('record-btn');
  if (recordBtn) recordBtn.addEventListener('click', TwitchX.toggleRecording);
  const statsOverlayBtn = document.getElementById('stats-overlay-btn');
  if (statsOverlayBtn) statsOverlayBtn.addEventListener('click', TwitchX.toggleStatsOverlay);
  var miniBtn = document.getElementById('mini-mode-btn');
  if (miniBtn) miniBtn.addEventListener('click', TwitchX.toggleMiniMode);

  // Volume slider
  var muteBtn = document.getElementById('mute-btn');
  if (muteBtn) muteBtn.addEventListener('click', TwitchX._handleMuteBtnClick);
  var volSlider = document.getElementById('volume-slider');
  if (volSlider) volSlider.addEventListener('input', TwitchX._handleVolumeSliderInput);

  // VOD seek bar
  var seekBar = document.getElementById('seek-bar');
  if (seekBar) {
    seekBar.addEventListener('input', TwitchX._handleSeekBarInput);
    seekBar.addEventListener('change', TwitchX._handleSeekBarChange);
    seekBar.addEventListener('mouseleave', TwitchX._handleSeekBarLeave);
  }

  // Quality changes apply to the running stream instead of waiting for a relaunch
  var qualitySelect = document.getElementById('quality-select');
  if (qualitySelect) {
    qualitySelect.addEventListener('change', TwitchX._handleQualitySelectChange);
  }

  // Playback recovery
  var retryBtn = document.getElementById('player-retry-btn');
  if (retryBtn) retryBtn.addEventListener('click', TwitchX._handlePlayerRetryClick);
};

TwitchX._bindBrowseEvents = function() {
  const backBtn = document.getElementById('browse-back-btn');
  if (backBtn) backBtn.addEventListener('click', TwitchX.browseGoBack);
  document.querySelectorAll('.browse-platform-tab').forEach(function(btn) {
    btn.addEventListener('click', function() {
      TwitchX.setActiveTab(Array.from(document.querySelectorAll('.browse-platform-tab')), btn);
      TwitchX.state.browsePlatformFilter = btn.dataset.platform;
      if (TwitchX.state.browseMode === 'categories') {
        TwitchX.loadBrowseCategories();
      } else if (TwitchX.state.browseCategory) {
        TwitchX._triggerBrowseTopStreams(TwitchX.state.browseCategory);
      }
    });
    btn.addEventListener('keydown', function(e) {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      e.preventDefault();
      TwitchX.focusAdjacentTab(Array.from(document.querySelectorAll('.browse-platform-tab')), btn, e.key === 'ArrowRight' ? 1 : -1);
    });
  });
};

TwitchX._bindChannelEvents = function() {
  const backBtn = document.getElementById('channel-back-btn');
  if (backBtn) backBtn.addEventListener('click', TwitchX.hideChannelView);
  document.querySelectorAll('.channel-tab').forEach(function(btn) {
    // switchChannelTab also records state.channelTabs.active, which is what
    // keeps the active tab after a profile refresh.
    btn.addEventListener('click', function() {
      TwitchX.switchChannelTab(btn, btn.dataset.tab);
    });
    btn.addEventListener('keydown', function(e) {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      e.preventDefault();
      TwitchX.focusAdjacentTab(Array.from(document.querySelectorAll('.channel-tab')), btn, e.key === 'ArrowRight' ? 1 : -1);
    });
  });
  const followBtn = document.getElementById('channel-follow-btn');
  if (followBtn) followBtn.addEventListener('click', TwitchX.toggleChannelFollow);
  const openBtn = document.getElementById('channel-open-btn');
  if (openBtn) openBtn.addEventListener('click', TwitchX.openChannelInBrowser);
  const watchBtn = document.getElementById('channel-watch-btn');
  if (watchBtn) watchBtn.addEventListener('click', TwitchX.watchChannelStream);
};

TwitchX._bindChatEvents = function() {
  // Chat scroll detection
  const chatMessages = document.getElementById('chat-messages');
  if (chatMessages) chatMessages.addEventListener('scroll', function() {
    const el = this;
    TwitchX.chatAutoScroll = (el.scrollHeight - el.scrollTop - el.clientHeight) < 60;
    if (TwitchX.chatAutoScroll) {
      const btn = document.getElementById('chat-new-messages');
      if (btn) btn.classList.remove('visible');
    }
  });

  const chatNewBtn = document.getElementById('chat-new-messages');
  if (chatNewBtn) chatNewBtn.addEventListener('click', function() {
    const container = document.getElementById('chat-messages');
    container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
    TwitchX.chatAutoScroll = true;
    this.classList.remove('visible');
  });

  // Chat input
  const chatInput = document.getElementById('chat-input');
  if (chatInput) chatInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && this.value.trim()) {
      TwitchX.submitChatMessage();
    }
    if (e.key === 'Escape') {
      if (TwitchX.chatReplyTo) TwitchX.clearChatReply();
      e.stopPropagation();
    }
  });

  const chatSendBtn = document.getElementById('chat-send-btn');
  if (chatSendBtn) chatSendBtn.addEventListener('click', function() {
    TwitchX.submitChatMessage();
  });

  const chatReplyClose = document.getElementById('chat-reply-close');
  if (chatReplyClose) chatReplyClose.addEventListener('click', function() {
    TwitchX.clearChatReply();
  });

  // Chat timestamps toggle
  var chatTsBtn = document.getElementById('chat-timestamp-btn');
  if (chatTsBtn) chatTsBtn.addEventListener('click', function() {
    TwitchX.chatTimestamps = !TwitchX.chatTimestamps;
    localStorage.setItem('twitchx.chat_timestamps', TwitchX.chatTimestamps ? '1' : '0');
    this.classList.toggle('active', TwitchX.chatTimestamps);
    document.querySelectorAll('.chat-msg .msg-time').forEach(function(el) {
      el.classList.toggle('hidden', !TwitchX.chatTimestamps);
    });
  });

  // Chat filter panel
  var chatFilterBtn = document.getElementById('chat-filter-btn');
  if (chatFilterBtn) chatFilterBtn.addEventListener('click', TwitchX.toggleChatFilterPanel);

  ['chat-filter-sub', 'chat-filter-mod', 'chat-filter-spam'].forEach(function(id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('change', function() {
      TwitchX.chatFilters.subOnly = document.getElementById('chat-filter-sub').checked;
      TwitchX.chatFilters.modOnly = document.getElementById('chat-filter-mod').checked;
      TwitchX.chatFilters.antiSpam = document.getElementById('chat-filter-spam').checked;
      TwitchX.saveChatFilters();
    });
  });

  var blockInput = document.getElementById('chat-blocklist-input');
  if (blockInput) {
    blockInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        var word = this.value.trim().toLowerCase();
        if (word && TwitchX.chatBlockList.indexOf(word) === -1) {
          TwitchX.chatBlockList.push(word);
          if (TwitchX.api) TwitchX.api.save_chat_block_list(JSON.stringify(TwitchX.chatBlockList));
        }
        this.value = '';
      }
    });
  }

  // Chat export
  var chatExportBtn = document.getElementById('chat-export-btn');
  var chatExportMenu = document.getElementById('chat-export-menu');
  if (chatExportBtn) {
    chatExportBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      if (chatExportMenu) {
        var opening = chatExportMenu.classList.toggle('hidden') === false;
        chatExportBtn.setAttribute('aria-expanded', String(opening));
        if (opening) {
          var firstExport = chatExportMenu.querySelector('[role="menuitem"]');
          if (firstExport) firstExport.tabIndex = 0;
        }
      }
    });
  }
  if (document.getElementById('chat-export-json')) {
    document.getElementById('chat-export-json').addEventListener('click', function() {
      if (chatExportMenu) chatExportMenu.classList.add('hidden');
      if (chatExportBtn) chatExportBtn.setAttribute('aria-expanded', 'false');
      TwitchX.exportChatLog('json');
    });
  }
  if (document.getElementById('chat-export-txt')) {
    document.getElementById('chat-export-txt').addEventListener('click', function() {
      if (chatExportMenu) chatExportMenu.classList.add('hidden');
      if (chatExportBtn) chatExportBtn.setAttribute('aria-expanded', 'false');
      TwitchX.exportChatLog('txt');
    });
  }
  document.addEventListener('click', function(e) {
    if (chatExportMenu && chatExportBtn && !chatExportMenu.contains(e.target) && e.target !== chatExportBtn) {
      chatExportMenu.classList.add('hidden');
      chatExportBtn.setAttribute('aria-expanded', 'false');
    }
  });
  if (chatExportMenu) chatExportMenu.addEventListener('keydown', function(e) {
    var items = Array.from(chatExportMenu.querySelectorAll('[role="menuitem"]'));
    var idx = items.indexOf(document.activeElement);
    if (e.key === 'Escape') {
      e.preventDefault();
      chatExportMenu.classList.add('hidden');
      if (chatExportBtn) {
        chatExportBtn.setAttribute('aria-expanded', 'false');
        chatExportBtn.focus();
      }
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      var next = (idx + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      items.forEach(function(item) { item.tabIndex = -1; });
      items[next].tabIndex = 0;
      items[next].focus();
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (document.activeElement && document.activeElement.click) document.activeElement.click();
    }
  });

  // Chat user list
  var chatUserlistBtn = document.getElementById('chat-userlist-btn');
  if (chatUserlistBtn) chatUserlistBtn.addEventListener('click', TwitchX.toggleChatUserList);
  var chatUserlistSearch = document.getElementById('chat-userlist-search');
  if (chatUserlistSearch) {
    chatUserlistSearch.addEventListener('input', function() {
      TwitchX.renderChatUserList(this.value.trim());
    });
  }

  // Emote picker
  var emotePickerBtn = document.getElementById('emote-picker-btn');
  if (emotePickerBtn) emotePickerBtn.addEventListener('click', TwitchX.toggleEmotePicker);
  var emoteSearch = document.getElementById('emote-search');
  if (emoteSearch) {
    emoteSearch.addEventListener('input', function() {
      TwitchX.renderEmotePicker(this.value.trim());
    });
  }
  document.addEventListener('click', function(e) {
    if (TwitchX._emotePickerOpen) {
      var picker = document.getElementById('emote-picker');
      var btn = document.getElementById('emote-picker-btn');
      if (picker && btn && !picker.contains(e.target) && e.target !== btn) {
        TwitchX.closeEmotePicker();
      }
    }
  });

  // Mod controls
  var chatModBtn = document.getElementById('chat-mod-btn');
  if (chatModBtn) {
    chatModBtn.addEventListener('click', function() {
      var panel = document.getElementById('chat-mod-panel');
      if (panel) {
        var open = panel.classList.toggle('hidden') === false;
        chatModBtn.setAttribute('aria-expanded', String(open));
      }
    });
  }

  function _bindModToggle(id, mode) {
    var el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('change', function() {
      var slowWait = parseInt(document.getElementById('mod-slow-wait').value, 10) || 30;
      if (TwitchX.api) TwitchX.api.set_chat_mode(mode, this.checked, slowWait);
    });
  }
  _bindModToggle('mod-emote-only', 'emote_mode');
  _bindModToggle('mod-slow', 'slow_mode');

  // Chat resize
  (function() {
    const handle = document.getElementById('chat-resize-handle');
    const panel = document.getElementById('chat-panel');
    if (!handle || !panel) return;
    let dragging = false;

    handle.addEventListener('mousedown', function(e) {
      e.preventDefault();
      dragging = true;
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', function(e) {
      if (!dragging) return;
      const container = document.getElementById('player-content');
      const rect = container.getBoundingClientRect();
      let newWidth = rect.right - e.clientX;
      newWidth = Math.max(250, Math.min(500, newWidth));
      panel.style.setProperty('--chat-width', newWidth + 'px');
    });

    document.addEventListener('mouseup', function() {
      if (!dragging) return;
      dragging = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      const computed = parseInt(getComputedStyle(panel).width, 10);
      const w = isNaN(computed) ? 340 : computed;
      if (TwitchX.api) TwitchX.api.save_chat_width(w);
    });
  })();
};

TwitchX._bindSettingsEvents = function() {
  const closeSettingsBtn = document.getElementById('close-settings');
  if (closeSettingsBtn) closeSettingsBtn.addEventListener('click', TwitchX.closeSettings);
  const eyeToggleBtn = document.getElementById('eye-toggle-btn');
  if (eyeToggleBtn) eyeToggleBtn.addEventListener('click', TwitchX.toggleSecret);
  const testBtn = document.getElementById('test-btn');
  if (testBtn) testBtn.addEventListener('click', TwitchX.testConnection);
  const saveBtn = document.getElementById('save-btn');
  if (saveBtn) saveBtn.addEventListener('click', TwitchX.saveSettings);
  const resetShortcutsBtn = document.getElementById('reset-shortcuts-btn');
  if (resetShortcutsBtn) resetShortcutsBtn.addEventListener('click', function() {
    TwitchX.state.shortcuts = Object.assign({}, TwitchX.DEFAULT_SHORTCUTS);
    TwitchX.renderHotkeysSettings();
  });
  const extPlayerSelect = document.getElementById('s-external-player');
  if (extPlayerSelect) extPlayerSelect.addEventListener('change', function() {
    document.getElementById('s-mpv-group').classList.toggle('hidden', this.value !== 'mpv');
  });

  // Stats compact toggle
  var statsCompactBtn = document.getElementById('stats-compact-toggle');
  if (statsCompactBtn) statsCompactBtn.addEventListener('click', TwitchX._toggleStatsCompact);

  // Settings tab switching
  document.querySelectorAll('.settings-tab').forEach(function(btn) {
    btn.addEventListener('click', function() {
      TwitchX.setActiveTab(Array.from(document.querySelectorAll('.settings-tab')), btn);
      document.querySelectorAll('.settings-panel').forEach(function(p) { p.classList.remove('active'); });
      document.getElementById('settings-panel-' + btn.dataset.tab).classList.add('active');
      if (btn.dataset.tab === 'advanced') {
        TwitchX.loadWatchStatistics();
      }
    });
    btn.addEventListener('keydown', function(e) {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      e.preventDefault();
      TwitchX.focusAdjacentTab(Array.from(document.querySelectorAll('.settings-tab')), btn, e.key === 'ArrowRight' ? 1 : -1);
    });
  });

  // Theme radio buttons
  document.querySelectorAll('input[name="theme"]').forEach(function(radio) {
    radio.addEventListener('change', function() {
      if (this.checked && TwitchX.applyTheme) {
        TwitchX.applyTheme(this.value);
      }
    });
  });

  // Kick eye toggle
  const kickEyeBtn = document.getElementById('kick-eye-toggle-btn');
  if (kickEyeBtn) kickEyeBtn.addEventListener('click', function() {
    const input = document.getElementById('s-kick-client-secret');
    input.type = input.type === 'password' ? 'text' : 'password';
  });

  // Kick login/logout
  const kickLoginBtn = document.getElementById('kick-login-btn');
  if (kickLoginBtn) kickLoginBtn.addEventListener('click', function() {
    const cid = document.getElementById('s-kick-client-id').value.trim();
    const cs = document.getElementById('s-kick-client-secret').value.trim();
    // Empty fields are fine — Python uses bundled Kick credentials
    if (TwitchX.api) TwitchX.api.kick_login(cid, cs);
  });
  const kickLogoutSettings = document.getElementById('kick-logout-settings-link');
  if (kickLogoutSettings) kickLogoutSettings.addEventListener('click', function() {
    if (TwitchX.api) TwitchX.api.kick_logout();
  });

  // Kick test connection
  const kickTestBtn = document.getElementById('kick-test-btn');
  if (kickTestBtn) kickTestBtn.addEventListener('click', function() {
    const cid = document.getElementById('s-kick-client-id').value.trim();
    const cs = document.getElementById('s-kick-client-secret').value.trim();
    // Empty fields are fine — Python falls back to bundled Kick credentials
    document.getElementById('kick-test-btn').disabled = true;
    _setFeedback('Testing Kick...');
    TwitchX.api.kick_test_connection(cid, cs);
  });

  // YouTube eye toggles
  const ytApiEyeBtn = document.getElementById('yt-api-key-eye-btn');
  if (ytApiEyeBtn) ytApiEyeBtn.addEventListener('click', function() {
    const input = document.getElementById('yt-api-key');
    input.type = input.type === 'password' ? 'text' : 'password';
  });
  const ytSecretEyeBtn = document.getElementById('yt-client-secret-eye-btn');
  if (ytSecretEyeBtn) ytSecretEyeBtn.addEventListener('click', function() {
    const input = document.getElementById('yt-client-secret');
    input.type = input.type === 'password' ? 'text' : 'password';
  });

  // YouTube login/logout/import
  const ytLoginBtn = document.getElementById('yt-login-btn');
  if (ytLoginBtn) ytLoginBtn.addEventListener('click', function() {
    if (!TwitchX.state.youtubeEnabled) return;
    const cid = document.getElementById('yt-client-id').value.trim();
    const cs = document.getElementById('yt-client-secret').value.trim();
    if (!cid || !cs) {
      const fb = document.getElementById('yt-test-result');
      fb.classList.remove('hidden');
      fb.textContent = 'OAuth Client ID and Secret are required to log in — enter them above first.';
      TwitchX.setFeedbackClass(fb, 'error');
      return;
    }
    if (TwitchX.api) TwitchX.api.youtube_login(cid, cs);
  });
  const ytLogoutBtn = document.getElementById('yt-logout-btn');
  if (ytLogoutBtn) ytLogoutBtn.addEventListener('click', function() {
    if (TwitchX.api) TwitchX.api.youtube_logout();
  });
  const ytImportBtn = document.getElementById('yt-import-btn');
  if (ytImportBtn) ytImportBtn.addEventListener('click', function() {
    if (TwitchX.api) TwitchX.api.youtube_import_follows();
  });

  // YouTube test connection
  const ytTestBtn = document.getElementById('yt-test-btn');
  if (ytTestBtn) ytTestBtn.addEventListener('click', function() {
    if (!TwitchX.api) return;
    const tr = document.getElementById('yt-test-result');
    tr.classList.remove('hidden');
    tr.textContent = 'Testing...';
    TwitchX.setFeedbackClass(tr, 'muted');
    document.getElementById('yt-test-btn').disabled = true;
    TwitchX.api.youtube_test_connection();
  });

  TwitchX._bindAdvancedToggles();
};

TwitchX._bindAdvancedToggles = function() {
  function _makeToggle(toggleId, sectionId, showText, hideText) {
    var btn = document.getElementById(toggleId);
    if (!btn) return;
    btn.addEventListener('click', function(e) {
      e.preventDefault();
      var section = document.getElementById(sectionId);
      if (!section) return;
      var isHidden = section.classList.toggle('hidden');
      btn.textContent = isHidden ? showText : hideText;
    });
  }
  _makeToggle('twitch-advanced-toggle', 'twitch-advanced-section',
    'Use custom credentials ▾', 'Hide custom credentials ▴');
  _makeToggle('kick-advanced-toggle', 'kick-advanced-section',
    'Use custom credentials ▾', 'Hide custom credentials ▴');
};

TwitchX._bindContextMenuEvents = function() {
  const contextMenu = document.getElementById('context-menu');
  if (contextMenu) contextMenu.addEventListener('click', function(e) {
    const target = e.target.closest('[data-action]');
    const action = target ? target.dataset.action : null;
    if (!action || !TwitchX.ctxChannel) return;
    if (target.getAttribute('aria-disabled') === 'true') {
      const reason = target.dataset.disabledReason || target.title || 'This action is not available for this platform.';
      TwitchX.setStatus(reason, 'warn');
      TwitchX.showToast(reason, 'warn');
      e.preventDefault();
      return;
    }
    const ctxStream = TwitchX.findStreamByKey(TwitchX.ctxChannelKey);
    const ctxPlat = (ctxStream && ctxStream.platform) ||
      TwitchX.getChannelPlatform(TwitchX.ctxChannel, TwitchX.ctxChannelKey);
    if (action === 'watch') { TwitchX.selectChannel(TwitchX.ctxChannel, ctxPlat); TwitchX.doWatch(); }
    else if (action === 'watch-external') {
      TwitchX.selectChannel(TwitchX.ctxChannel, ctxPlat);
      const quality = document.getElementById('quality-select').value;
      if (TwitchX.api.watch_external_platform) TwitchX.api.watch_external_platform(TwitchX.ctxChannel, ctxPlat, quality);
      else if (TwitchX.api) TwitchX.api.watch_external(TwitchX.ctxChannel, quality);
    }
    else if (action === 'browser') { if (TwitchX.api) TwitchX.api.open_browser(TwitchX.ctxChannel, ctxPlat); }
    else if (action === 'profile') { TwitchX.showChannelView(TwitchX.ctxChannel, ctxPlat, 'grid'); }
    else if (action === 'copy') {
      const baseUrl = ctxPlat === 'kick'
        ? 'https://kick.com/'
        : ctxPlat === 'youtube'
          ? 'https://www.youtube.com/channel/'
          : 'https://twitch.tv/';
      navigator.clipboard.writeText(baseUrl + TwitchX.ctxChannel).catch(function() {});
    }
    else if (action === 'favorite') { if (TwitchX.api) TwitchX.api.add_channel(TwitchX.ctxChannel, ctxPlat); }
    else if (action === 'remove') { if (TwitchX.api) TwitchX.api.remove_channel(TwitchX.ctxChannel, ctxPlat); }
    else if (action === 'create-group') {
      const name = window.prompt('Name your new group:');
      if (name && TwitchX.createFavoriteGroup) {
        TwitchX.createFavoriteGroup(name.trim());
        if (TwitchX.moveFavoriteToGroup) TwitchX.moveFavoriteToGroup(TwitchX.ctxChannelKey, name.trim());
      }
    }
    else if (action === 'move-to-group') {
      const existing = [];
      TwitchX.getFavoriteEntries().forEach(function(e) {
        const g = TwitchX.getFavoriteGroup(e.login, e.platform);
        if (g && existing.indexOf(g) === -1) existing.push(g);
      });
      const name = window.prompt(
        existing.length
          ? 'Group name (existing: ' + existing.join(', ') + ')'
          : 'Group name'
      );
      if (name && TwitchX.moveFavoriteToGroup) {
        TwitchX.moveFavoriteToGroup(TwitchX.ctxChannelKey, name.trim());
      }
    }
    else if (action === 'pin') {
      var pinItem = contextMenu.querySelector('[data-action="pin"]');
      var pinPlat = pinItem ? (pinItem.dataset.pinPlatform || 'twitch') : 'twitch';
      TwitchX.togglePin(pinPlat, TwitchX.ctxChannel);
    }
    else if (action === 'multistream') {
      const emptyIdx = TwitchX.multiState.slots.indexOf(null);
      if (emptyIdx !== -1) {
        TwitchX.openMultistreamView();
        TwitchX.addMultiSlot(emptyIdx, TwitchX.ctxChannel, ctxPlat);
      }
    }
    TwitchX.closeContextMenu();
  });
  if (contextMenu) contextMenu.addEventListener('keydown', function(e) {
    const items = TwitchX.getVisibleContextMenuItems
      ? TwitchX.getVisibleContextMenuItems(contextMenu)
      : [];
    if (e.key === 'Escape') {
      e.preventDefault();
      TwitchX.closeContextMenu();
      return;
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const activeIdx = Math.max(0, items.indexOf(document.activeElement));
      TwitchX.focusContextMenuItem(contextMenu, activeIdx + (e.key === 'ArrowDown' ? 1 : -1));
      return;
    }
    if (e.key === 'Home') {
      e.preventDefault();
      TwitchX.focusContextMenuItem(contextMenu, 0);
      return;
    }
    if (e.key === 'End') {
      e.preventDefault();
      TwitchX.focusContextMenuItem(contextMenu, items.length - 1);
      return;
    }
    if (e.key === 'Enter' || e.key === ' ') {
      const item = document.activeElement.closest('[data-action]');
      if (!item || !contextMenu.contains(item)) return;
      e.preventDefault();
      item.click();
    }
  });

  // Hide context menu on click outside
  document.addEventListener('click', function(e) {
    const menu = document.getElementById('context-menu');
    if (menu && menu.classList.contains('menu-visible') && !menu.contains(e.target)) {
      TwitchX.closeContextMenu();
    }
    const groupMenu = document.getElementById('group-context-menu');
    if (groupMenu && groupMenu.classList.contains('menu-visible') && !groupMenu.contains(e.target)) {
      TwitchX.closeGroupContextMenu();
    }
  });

  const groupContextMenu = document.getElementById('group-context-menu');
  if (groupContextMenu) groupContextMenu.addEventListener('click', function(e) {
    const target = e.target.closest('[data-action]');
    const action = target ? target.dataset.action : null;
    const groupName = TwitchX._ctxGroupName;
    if (!action || !groupName) return;
    if (action === 'rename-group') {
      const newName = window.prompt('Rename group:', groupName);
      if (newName && TwitchX.renameFavoriteGroup) TwitchX.renameFavoriteGroup(groupName, newName.trim());
    } else if (action === 'delete-group') {
      if (window.confirm('Delete group "' + groupName + '"? Channels will return to Online/Offline.')) {
        if (TwitchX.deleteFavoriteGroup) TwitchX.deleteFavoriteGroup(groupName);
      }
    }
    TwitchX.closeGroupContextMenu();
  });
};

TwitchX._bindKeyboardEvents = function() {
  document.addEventListener('keydown', TwitchX.handleKeydown);
};

TwitchX.toggleMiniMode = function() {
  var isMini = document.getElementById('app').classList.toggle('mini');
  var content = document.getElementById('content');
  if (content) {
    if (isMini) {
      content.setAttribute('inert', '');
    } else {
      content.removeAttribute('inert');
    }
  }
  localStorage.setItem('twitchx.mini', isMini ? '1' : '0');
  var btn = document.getElementById('mini-mode-btn');
  if (btn) {
    btn.title = isMini ? 'Exit mini mode' : 'Mini mode';
    btn.setAttribute('aria-label', isMini ? 'Exit mini mode' : 'Mini mode');
    TwitchX.setIconOnly(btn, isMini ? 'mini-exit' : 'minimize', 16);
  }
};

TwitchX.applyMiniMode = function() {
  var saved = localStorage.getItem('twitchx.mini') === '1';
  if (saved) {
    document.getElementById('app').classList.add('mini');
    var content = document.getElementById('content');
    if (content) content.setAttribute('inert', '');
    var btn = document.getElementById('mini-mode-btn');
    if (btn) {
      btn.title = 'Exit mini mode';
      btn.setAttribute('aria-label', 'Exit mini mode');
      TwitchX.setIconOnly(btn, 'mini-exit', 16);
    }
  }
};

TwitchX._bindPaletteEvents = function() {
  var overlay = document.getElementById('palette-overlay');
  if (overlay) overlay.addEventListener('click', function(e) {
    if (e.target === overlay) TwitchX.closePalette();
  });
  var input = document.getElementById('palette-input');
  if (input) {
    input.addEventListener('input', function() {
      TwitchX.renderPaletteResults(this.value);
    });
    input.addEventListener('keydown', TwitchX.handlePaletteKeydown);
  }
};

TwitchX._bindGlobalEvents = function() {
  TwitchX.initSidebarScrollShadow();
  TwitchX.initChatScrollShadow();
  document.addEventListener('keydown', function(e) {
    if ((e.key !== 'Enter' && e.key !== ' ') || !e.target.matches('a[role="button"]')) return;
    e.preventDefault();
    e.target.click();
  });
};

TwitchX._bindMultistreamEvents = function() {
  const msSidebarBtn = document.getElementById('ms-sidebar-btn');
  if (msSidebarBtn) msSidebarBtn.addEventListener('click', TwitchX.toggleMsSidebar);
  const msAddSlotBtn = document.getElementById('ms-add-slot-btn');
  if (msAddSlotBtn) msAddSlotBtn.addEventListener('click', TwitchX.openFirstEmptyMultiSlot);
  const msToggleChatBtn = document.getElementById('ms-toggle-chat-btn');
  if (msToggleChatBtn) msToggleChatBtn.addEventListener('click', TwitchX.toggleMsChat);
  const msCloseBtn = document.getElementById('ms-close-btn');
  if (msCloseBtn) msCloseBtn.addEventListener('click', TwitchX.closeMultistreamView);
  const msBackdrop = document.getElementById('ms-sidebar-backdrop');
  if (msBackdrop) msBackdrop.addEventListener('click', TwitchX.toggleMsSidebar);

  // Multi-stream grid click delegation
  const msGrid = document.getElementById('multistream-grid');
  if (msGrid) msGrid.addEventListener('click', function(e) {
    const addBtn = e.target.closest('.ms-add-btn');
    if (addBtn) {
      const slot = parseInt(addBtn.dataset.slot, 10);
      TwitchX.openFirstEmptyMultiSlot(slot);
      return;
    }
    const confirmBtn = e.target.closest('.ms-confirm-btn');
    if (confirmBtn) {
      const slot = parseInt(confirmBtn.dataset.slot, 10);
      const slotEl = document.querySelector('.ms-slot[data-slot-idx="' + slot + '"]');
      const channel = slotEl.querySelector('.ms-add-input').value.trim();
      const platform = slotEl.querySelector('.ms-add-platform').value;
      if (channel) {
        TwitchX.addMultiSlot(slot, channel, platform);
      } else {
        TwitchX.closeMultiAddForm(slot);
      }
      return;
    }
    const cancelBtn = e.target.closest('.ms-cancel-btn');
    if (cancelBtn) {
      TwitchX.closeMultiAddForm(parseInt(cancelBtn.dataset.slot, 10), { restoreFocus: true });
      return;
    }
    const audioBtn = e.target.closest('.ms-audio-btn');
    if (audioBtn) { TwitchX.setAudioFocus(parseInt(audioBtn.dataset.slot, 10)); return; }
    const chatBtn = e.target.closest('.ms-chat-sw-btn');
    if (chatBtn) { TwitchX.switchMultiChat(parseInt(chatBtn.dataset.slot, 10)); return; }
    const fsBtn = e.target.closest('.ms-fullscreen-btn');
    if (fsBtn) { TwitchX.toggleMsSlotFullscreen(parseInt(fsBtn.dataset.slot, 10)); return; }
    const msPipBtn = e.target.closest('.ms-pip-btn');
    if (msPipBtn) {
      const slot = parseInt(msPipBtn.dataset.slot, 10);
      const slotEl = document.querySelector('.ms-slot[data-slot-idx="' + slot + '"]');
      if (slotEl) TwitchX.togglePiP(slotEl.querySelector('.ms-video'));
      return;
    }
    const removeBtn = e.target.closest('.ms-remove-btn');
    if (removeBtn) { TwitchX.removeMultiSlot(parseInt(removeBtn.dataset.slot, 10)); return; }
  });

  // Double-click on a slot video to toggle fullscreen
  if (msGrid) msGrid.addEventListener('dblclick', function(e) {
    if (e.target.closest('.ms-slot-controls') || e.target.closest('.ms-add-form') || e.target.closest('.ms-slot-empty')) return;
    const slotEl = e.target.closest('.ms-slot');
    if (!slotEl) return;
    TwitchX.toggleMsSlotFullscreen(parseInt(slotEl.dataset.slotIdx, 10));
  });

  // Confirm add-form on Enter key
  if (msGrid) msGrid.addEventListener('keydown', function(e) {
    const input = e.target.closest('.ms-add-input');
    const form = e.target.closest('.ms-add-form');
    if (e.key === 'Escape' && form) {
      e.preventDefault();
      e.stopPropagation();
      const slotEl = form.closest('.ms-slot');
      TwitchX.closeMultiAddForm(parseInt(slotEl.dataset.slotIdx, 10), { restoreFocus: true });
      return;
    }
    if (e.key !== 'Enter' || !input) return;
    const slotEl = input.closest('.ms-slot');
    const idx = parseInt(slotEl.dataset.slotIdx, 10);
    const channel = input.value.trim();
    const platform = slotEl.querySelector('.ms-add-platform').value;
    if (channel) {
      TwitchX.addMultiSlot(idx, channel, platform);
    } else {
      TwitchX.closeMultiAddForm(idx);
    }
  });

  // ms-chat send button
  const msChatSendBtn = document.getElementById('ms-chat-send-btn');
  if (msChatSendBtn) msChatSendBtn.addEventListener('click', function() {
    TwitchX.submitChatMessage();
  });
  const msChatInput = document.getElementById('ms-chat-input');
  if (msChatInput) msChatInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      document.getElementById('ms-chat-send-btn').click();
    }
    if (e.key === 'Escape') {
      if (TwitchX.chatReplyTo) TwitchX.clearChatReply();
      e.stopPropagation();
    }
  });

  // ms-chat new-messages scroll button
  const msChatNewBtn = document.getElementById('ms-chat-new-messages');
  if (msChatNewBtn) msChatNewBtn.addEventListener('click', function() {
    const el = document.getElementById('ms-chat-messages');
    el.scrollTop = el.scrollHeight;
    TwitchX.msChatAutoScroll = true;
    document.getElementById('ms-chat-new-messages').classList.remove('visible');
  });
  const msChatMessages = document.getElementById('ms-chat-messages');
  if (msChatMessages) msChatMessages.addEventListener('scroll', function() {
    const el = document.getElementById('ms-chat-messages');
    TwitchX.msChatAutoScroll = (el.scrollHeight - el.scrollTop - el.clientHeight) < 60;
    if (TwitchX.msChatAutoScroll) {
      document.getElementById('ms-chat-new-messages').classList.remove('visible');
    }
  });
};

TwitchX._initMultistreamSlots = function() {
  const grid = document.getElementById('multistream-grid');
  if (!grid) return;
  grid.replaceChildren();
  for (let i = 0; i < 4; i++) {
    grid.appendChild(TwitchX._createMultiSlot(i));
  }
  const select = document.getElementById('ms-preset-select');
  if (select) {
    select.replaceChildren();
    ['grid', 'focus-left', 'rows', 'columns'].forEach(function(p) {
      const opt = document.createElement('option');
      opt.value = p;
      opt.textContent = { grid: 'Grid', 'focus-left': 'Focus', rows: 'Rows', columns: 'Columns' }[p];
      select.appendChild(opt);
    });
    select.addEventListener('change', function() {
      if (TwitchX.setMultistreamPreset) TwitchX.setMultistreamPreset(select.value);
    });
  }
  if (TwitchX._loadMultistreamPresets) TwitchX._loadMultistreamPresets();
  if (TwitchX._updateMultiGridLayout) TwitchX._updateMultiGridLayout();
};

/* ── Uptime counter ─────────────────────────────────────── */
setInterval(function() {
  document.querySelectorAll('.stream-card').forEach(function(card) {
    const started = card.dataset.started;
    if (started) {
      const badge = card.querySelector('.uptime-badge');
      if (badge) badge.textContent = TwitchX.formatUptime(started);
    }
  });
}, 60000);
