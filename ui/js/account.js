window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

/* ── Account chip + popover ─────────────────────────────── */
// The chip at the bottom of the sidebar names the first signed-in account and
// shows one connection dot per platform. It opens a popover holding the login
// controls that used to live at the top of the sidebar (same element IDs).

const ACCOUNT_FOCUSABLE =
  'button:not([disabled]):not(.hidden), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])';

TwitchX._accountReturnFocus = null;

function _accountPopover() {
  return document.getElementById('account-popover');
}

function isAccountPopoverOpen() {
  var pop = _accountPopover();
  return !!pop && !pop.classList.contains('hidden');
}

function _accountFocusables() {
  var pop = _accountPopover();
  if (!pop) return [];
  return Array.from(pop.querySelectorAll(ACCOUNT_FOCUSABLE)).filter(function(el) {
    return !el.closest('.hidden');
  });
}

function _positionAccountPopover() {
  var pop = _accountPopover();
  var chip = document.getElementById('account-chip');
  if (!pop || !chip) return;
  var rect = chip.getBoundingClientRect();
  pop.style.left = Math.max(8, rect.left) + 'px';
  pop.style.bottom = Math.max(8, window.innerHeight - rect.top + 8) + 'px';
}

function updateAccountChip() {
  var twitch = TwitchX.state.currentUser;
  var kick = TwitchX.state.kickUser;
  var youtube = TwitchX.state.youtubeEnabled ? TwitchX.state.youtubeUser : null;
  var first = twitch || kick || youtube;
  var name = first ? (first.display_name || first.login || '') : '';

  var nameEl = document.getElementById('account-chip-name');
  if (nameEl) nameEl.textContent = name || 'Not signed in';
  var chip = document.getElementById('account-chip');
  if (chip) chip.setAttribute('aria-label', 'Accounts' + (name ? ', signed in as ' + name : ', not signed in'));

  var img = document.getElementById('account-chip-img');
  var initial = document.getElementById('account-chip-initial');
  var avatarKey = twitch ? TwitchX.channelKey(twitch.login || '', 'twitch') : '';
  var avatarUrl = avatarKey ? TwitchX.state.avatars[avatarKey] : '';
  if (img) {
    if (avatarUrl) {
      img.src = avatarUrl;
      img.classList.remove('hidden');
    } else {
      img.removeAttribute('src');
      img.classList.add('hidden');
    }
  }
  if (initial) {
    initial.textContent = name ? name.charAt(0).toUpperCase() : '';
    initial.classList.toggle('hidden', !!avatarUrl);
  }

  var ytStatus = document.getElementById('account-youtube-status');
  if (ytStatus) {
    ytStatus.textContent = TwitchX.state.youtubeUser
      ? 'Connected as ' + (TwitchX.state.youtubeUser.display_name || TwitchX.state.youtubeUser.login)
      : 'Not connected';
  }
  var ytBtn = document.getElementById('account-youtube-btn');
  if (ytBtn) ytBtn.textContent = TwitchX.state.youtubeUser ? 'Manage in Settings' : 'Set up in Settings';
  var ytSection = document.getElementById('account-youtube-section');
  if (ytSection) ytSection.classList.toggle('hidden', !TwitchX.state.youtubeEnabled);

  if (TwitchX.syncSettingsAccounts) TwitchX.syncSettingsAccounts();

  var miniLabel = document.getElementById('account-mini-mode-label');
  if (miniLabel) {
    var isMini = document.getElementById('app').classList.contains('mini');
    miniLabel.textContent = isMini ? 'Exit mini mode' : 'Mini mode';
  }
}

function openAccountPopover() {
  var pop = _accountPopover();
  var chip = document.getElementById('account-chip');
  if (!pop || isAccountPopoverOpen()) return;
  TwitchX._accountReturnFocus = chip || document.activeElement;
  updateAccountChip();
  _positionAccountPopover();
  pop.classList.remove('hidden');
  if (chip) chip.setAttribute('aria-expanded', 'true');
  var first = _accountFocusables()[0];
  if (first) first.focus();
}

function closeAccountPopover(restoreFocus) {
  var pop = _accountPopover();
  if (!pop || !isAccountPopoverOpen()) return false;
  pop.classList.add('hidden');
  var chip = document.getElementById('account-chip');
  if (chip) chip.setAttribute('aria-expanded', 'false');
  var back = TwitchX._accountReturnFocus;
  TwitchX._accountReturnFocus = null;
  if (restoreFocus !== false && back && document.contains(back) && back.focus) back.focus();
  return true;
}

function _onAccountPopoverKeydown(e) {
  if (e.key === 'Escape') {
    e.preventDefault();
    e.stopPropagation();
    closeAccountPopover();
    return;
  }
  if (e.key !== 'Tab') return;
  var items = _accountFocusables();
  if (!items.length) return;
  var first = items[0];
  var last = items[items.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}

TwitchX._bindAccountEvents = function() {
  var chip = document.getElementById('account-chip');
  var pop = _accountPopover();
  if (chip) chip.addEventListener('click', function(e) {
    e.stopPropagation();
    if (!closeAccountPopover()) openAccountPopover();
  });
  var gear = document.getElementById('account-settings-btn');
  if (gear) gear.addEventListener('click', function() { TwitchX.openSettings(); });
  if (!pop) return;
  pop.addEventListener('keydown', _onAccountPopoverKeydown);
  document.addEventListener('mousedown', function(e) {
    if (!isAccountPopoverOpen()) return;
    if (pop.contains(e.target) || (chip && chip.contains(e.target))) return;
    closeAccountPopover(false);
  });
  window.addEventListener('resize', function() {
    if (isAccountPopoverOpen()) _positionAccountPopover();
  });

  var mini = document.getElementById('account-mini-mode-btn');
  if (mini) mini.addEventListener('click', function() {
    closeAccountPopover(false);
    TwitchX.toggleMiniMode();
  });
  var settingsItem = document.getElementById('account-settings-item');
  if (settingsItem) settingsItem.addEventListener('click', function() {
    closeAccountPopover(false);
    TwitchX.openSettings();
  });
  var ytBtn = document.getElementById('account-youtube-btn');
  if (ytBtn) ytBtn.addEventListener('click', function() {
    closeAccountPopover(false);
    TwitchX.openSettings();
  });
};

TwitchX.openAccountPopover = openAccountPopover;
TwitchX.closeAccountPopover = closeAccountPopover;
TwitchX.isAccountPopoverOpen = isAccountPopoverOpen;
TwitchX.updateAccountChip = updateAccountChip;
