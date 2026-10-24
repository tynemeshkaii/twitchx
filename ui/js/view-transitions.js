window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

const VIEW_IDS = [
  'stream-grid',
  'empty-state',
  'browse-view',
  'channel-view',
  'multistream-view',
  'player-view',
];

const CHROME_IDS = [
  'toolbar',
  'toolbar-platform-chips',
  'section-header',
];

// Match --view-exit / --view-enter in tokens.css. The timers are a fallback
// for a missed animationend (hidden window, reduced motion), with slack.
const VIEW_EXIT_MS = 160;
const VIEW_ENTER_MS = 240;
const VIEW_FALLBACK_SLACK_MS = 60;

const DIRECTIONS = {
  forward: 'anim-view-enter-right',
  back: 'anim-view-enter-left',
  up: 'anim-view-enter-bottom',
  none: 'anim-view-enter-bottom',
};

function _getViewElement(id) {
  if (!id) return null;
  return document.getElementById(id);
}

function _isViewVisible(el) {
  if (!el) return false;
  return !el.classList.contains('hidden') || el.classList.contains('view-active');
}

function _setViewVisible(el, visible) {
  if (!el) return;
  if (visible) {
    el.classList.remove('hidden');
    el.classList.add('view-active');
  } else {
    el.classList.add('hidden');
    el.classList.remove('view-active');
  }
}

function _setInert(el, inert) {
  if (!el) return;
  if (inert) {
    el.setAttribute('inert', '');
  } else {
    el.removeAttribute('inert');
  }
}

function _clearAnimation(el) {
  if (!el) return;
  el.classList.remove(
    'anim-view-exit',
    'anim-view-enter-bottom',
    'anim-view-enter-right',
    'anim-view-enter-left'
  );
}

function _getFirstFocusable(container) {
  if (!container) return null;
  const selector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
  return container.querySelector(selector);
}

// Moving focus to the first control of a new view helps keyboard users; after
// a click it only paints a focus ring on that control. Track the last input.
let _vtLastInputKeyboard = false;
document.addEventListener('keydown', function() { _vtLastInputKeyboard = true; }, true);
document.addEventListener('pointerdown', function() { _vtLastInputKeyboard = false; }, true);

function _focusEnteredView(target) {
  if (!target) return;
  if (_vtLastInputKeyboard) {
    const first = _getFirstFocusable(target);
    if (first && first.focus) {
      first.focus({ preventScroll: true });
      return;
    }
  }
  // Mouse: focus the view itself so Tab starts inside it, without a ring.
  if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
  target.focus({ preventScroll: true });
}

TwitchX.setChromeVisible = function(visible) {
  CHROME_IDS.forEach(function(id) {
    const el = document.getElementById(id);
    if (!el) return;
    if (visible) {
      el.classList.remove('hidden');
    } else {
      el.classList.add('hidden');
    }
  });
};

TwitchX.switchView = function(targetId, direction) {
  var tooltip = document.getElementById('sidebar-tooltip');
  if (tooltip) { tooltip.classList.remove('visible'); tooltip.classList.add('hidden'); }
  var filterPanel = document.getElementById('chat-filter-panel');
  if (filterPanel) filterPanel.classList.add('hidden');
  var ctxMenu = document.getElementById('context-menu');
  if (ctxMenu) ctxMenu.classList.remove('menu-visible');
  var grpMenu = document.getElementById('group-context-menu');
  if (grpMenu) grpMenu.classList.remove('menu-visible');

  const target = _getViewElement(targetId);
  if (!target) return;
  if (TwitchX.syncNavForView) TwitchX.syncNavForView(targetId);

  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Find currently visible view
  let current = null;
  for (let i = 0; i < VIEW_IDS.length; i++) {
    const el = _getViewElement(VIEW_IDS[i]);
    if (el && el.id !== targetId && _isViewVisible(el)) {
      current = el;
      break;
    }
  }

  const previousFocus = document.activeElement;

  if (!current || current === target) {
    _clearAnimation(target);
    _setViewVisible(target, true);
    _setInert(target, false);
    return;
  }

  // Accessibility: mark outgoing view inert so it is removed from tab order
  // and screen readers during transition.
  _setInert(current, true);
  _setInert(target, false);

  if (prefersReduced) {
    _clearAnimation(current);
    _clearAnimation(target);
    _setViewVisible(current, false);
    _setViewVisible(target, true);
    _focusEnteredView(target);
    return;
  }

  const enterClass = DIRECTIONS[direction] || DIRECTIONS.none;

  _clearAnimation(current);
  _clearAnimation(target);

  // opacity: 0 first, then display — otherwise the new view flashes for a
  // frame before its entrance animation starts.
  target.classList.add('view-enter-prep');
  _setViewVisible(target, true);
  requestAnimationFrame(function() {
    requestAnimationFrame(function() {
      target.classList.remove('view-enter-prep');
      target.classList.add(enterClass);
    });
  });
  current.classList.add('anim-view-exit');

  // Each runs once (animationend or the fallback timer). A view that was
  // re-entered before its exit finished has lost anim-view-exit: keep it.
  function onExitDone() {
    if (!current.classList.contains('anim-view-exit')) return;
    _clearAnimation(current);
    _setViewVisible(current, false);
  }

  let entered = false;
  function onEnterDone() {
    if (entered) return;
    entered = true;
    _clearAnimation(target);
    _focusEnteredView(target);
  }

  current.addEventListener('animationend', onExitDone, { once: true });
  target.addEventListener('animationend', onEnterDone, { once: true });
  setTimeout(onExitDone, VIEW_EXIT_MS + VIEW_FALLBACK_SLACK_MS);
  setTimeout(onEnterDone, VIEW_ENTER_MS + VIEW_FALLBACK_SLACK_MS);
};

TwitchX.viewFadeIn = function(el, showClass) {
  if (!el) return;
  _setViewVisible(el, true);
  _setInert(el, false);
  _clearAnimation(el);
  el.classList.add('anim-view-enter-bottom');
  el.addEventListener('animationend', function handler() {
    el.removeEventListener('animationend', handler);
    _clearAnimation(el);
  }, { once: true });
};

TwitchX.viewFadeOut = function(el, hideClass, onDone) {
  if (!el) {
    if (onDone) onDone();
    return;
  }
  _setInert(el, true);
  _clearAnimation(el);
  el.classList.add('anim-view-exit');
  function finish() {
    _setViewVisible(el, false);
    _clearAnimation(el);
    if (onDone) onDone();
  }
  el.addEventListener('animationend', finish, { once: true });
  setTimeout(finish, VIEW_EXIT_MS + VIEW_FALLBACK_SLACK_MS);
};

TwitchX.hideAllViews = function() {
  VIEW_IDS.forEach(function(id) {
    const el = _getViewElement(id);
    if (el) {
      _clearAnimation(el);
      _setViewVisible(el, false);
      _setInert(el, true);
    }
  });
};
