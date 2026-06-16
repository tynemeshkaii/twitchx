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
];

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
  const target = _getViewElement(targetId);
  if (!target) return;

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
    const focusTarget = _getFirstFocusable(target) || target;
    if (focusTarget && focusTarget.focus) focusTarget.focus({ preventScroll: true });
    return;
  }

  const enterClass = DIRECTIONS[direction] || DIRECTIONS.none;

  _clearAnimation(current);
  _clearAnimation(target);

  _setViewVisible(target, true);
  target.classList.add('view-enter-prep');
  requestAnimationFrame(function() {
    requestAnimationFrame(function() {
      target.classList.remove('view-enter-prep');
      target.classList.add(enterClass);
    });
  });
  current.classList.add('anim-view-exit');

  function onExitDone() {
    _clearAnimation(current);
    _setViewVisible(current, false);
  }

  function onEnterDone() {
    _clearAnimation(target);
    // Restore focus inside the new view for keyboard navigation.
    const focusTarget = _getFirstFocusable(target) || target;
    if (focusTarget && focusTarget.focus) {
      focusTarget.focus({ preventScroll: true });
    }
  }

  current.addEventListener('animationend', onExitDone, { once: true });
  target.addEventListener('animationend', onEnterDone, { once: true });
  setTimeout(onExitDone, 300);
  setTimeout(onEnterDone, 350);
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
  setTimeout(finish, 250);
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
