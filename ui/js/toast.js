window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

var TOAST_ICONS = {
  success: '\u2713',
  error: '\u2717',
  info: '\u2139',
  warn: '\u26A0',
};
var TOAST_DURATION = 4000;
var MAX_TOASTS = 5;

function showToast(message, type) {
  type = type || 'info';
  message = String(message);
  var container = document.getElementById('toast-container');
  if (!container) return;

  while (container.children.length >= MAX_TOASTS) {
    var oldest = container.firstChild;
    if (oldest._toastTimer) clearTimeout(oldest._toastTimer);
    container.removeChild(oldest);
  }

  var el = document.createElement('div');
  el.className = 'toast toast--' + type;

  var icon = document.createElement('span');
  icon.className = 'toast-icon';
  icon.textContent = TOAST_ICONS[type] || TOAST_ICONS.info;
  el.appendChild(icon);

  var text = document.createElement('span');
  text.className = 'toast-text';
  text.textContent = message;
  el.appendChild(text);

  el.addEventListener('click', function() {
    dismissToast(el);
  });

  container.appendChild(el);

  requestAnimationFrame(function() {
    requestAnimationFrame(function() {
      el.classList.add('toast--visible');
    });
  });

  el._toastTimer = setTimeout(function() {
    dismissToast(el);
  }, TOAST_DURATION);

  return el;
}

function dismissToast(el) {
  if (!el) return;
  if (el._dismissing) return;
  el._dismissing = true;
  if (el._toastTimer) {
    clearTimeout(el._toastTimer);
    el._toastTimer = null;
  }
  el.classList.remove('toast--visible');
  el.classList.add('toast--leaving');
  var removeFn = function() {
    if (el.parentNode) el.parentNode.removeChild(el);
  };
  el.addEventListener('transitionend', removeFn, { once: true });
  setTimeout(removeFn, 300);
}

function clearToasts() {
  var container = document.getElementById('toast-container');
  if (!container) return;
  while (container.firstChild) {
    var el = container.firstChild;
    if (el._toastTimer) {
      clearTimeout(el._toastTimer);
      el._toastTimer = null;
    }
    container.removeChild(el);
  }
}

TwitchX.showToast = showToast;
TwitchX.dismissToast = dismissToast;
TwitchX.clearToasts = clearToasts;
