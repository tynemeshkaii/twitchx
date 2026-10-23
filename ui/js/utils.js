window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

function truncate(s, n) {
  if (!s) return '';
  return s.length > n ? s.substring(0, n) + '\u2026' : s;
}

// 950, 9.7K, 88.3K, 210K, 1.2M, 12M — keep in sync with format_viewers in
// core/utils.py. Integer half-up rounding, so 99 950 → 100K and 999 950 → 1M.
function formatViewersTenths(tenths, suffix) {
  const whole = Math.floor(tenths / 10);
  const frac = tenths % 10;
  return (frac === 0 ? String(whole) : whole + '.' + frac) + suffix;
}

function formatViewers(n) {
  if (!(n >= 1000)) return String(n); // also non-numbers, as before
  const tenthsK = Math.floor((n + 50) / 100);
  if (tenthsK < 1000) return formatViewersTenths(tenthsK, 'K');
  const wholeK = Math.floor((n + 500) / 1000);
  if (wholeK < 1000) return wholeK + 'K';
  return formatViewersTenths(Math.floor((n + 50000) / 100000), 'M');
}

function formatUptime(isoStr) {
  if (!isoStr) return '';
  const start = new Date(isoStr);
  const now = new Date();
  const diff = Math.floor((now - start) / 1000);
  const h = Math.floor(diff / 3600);
  const m = Math.floor((diff % 3600) / 60);
  if (h > 0) return h + 'h ' + m + 'm';
  return m + 'm';
}

const STATUS_META_MS = 4000;
let statusMetaTimer = null;

// info/success: a short note in the section header, standing in for
// "updated …" for a few seconds. warn/error: a toast, so it is seen from any view.
function setStatus(text, type) {
  if (type === 'warn' || type === 'error') {
    if (text && TwitchX.showToast) TwitchX.showToast(text, type);
    return;
  }
  const el = document.getElementById('status-text');
  const meta = document.getElementById('section-meta');
  if (!el) return;
  if (statusMetaTimer) {
    clearTimeout(statusMetaTimer);
    statusMetaTimer = null;
  }
  el.textContent = text || '';
  if (meta) meta.classList.toggle('showing-status', !!text);
  if (!text) return;
  statusMetaTimer = setTimeout(function() {
    statusMetaTimer = null;
    el.textContent = '';
    if (meta) meta.classList.remove('showing-status');
  }, STATUS_META_MS);
}

function formatMediaDate(isoStr) {
  if (!isoStr) return '';
  const date = new Date(isoStr);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function formatDuration(seconds) {
  if (!seconds || seconds < 0) return '';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return h + 'h ' + m + 'm';
  if (m > 0) return m + 'm';
  return s + 's';
}

function setFeedbackClass(el, type) {
  if (!el) return;
  el.classList.remove('feedback-success', 'feedback-error', 'feedback-warn', 'feedback-muted');
  if (type) el.classList.add('feedback-' + type);
}

function buildChannelMediaMeta(item, tab) {
  const parts = [];
  const dateText = formatMediaDate(item.published_at);
  const durationText = formatDuration(item.duration_seconds || 0);
  if (dateText) parts.push(dateText);
  if (durationText) parts.push(durationText);
  if (item.views) {
    parts.push(formatViewers(item.views) + ' views');
  }
  return parts.join(' \u2022 ');
}

function makeIcon(name, size) {
  const icon = document.createElement('span');
  icon.className = 'icon';
  icon.innerHTML = TwitchX.renderIcon(name, size || 14);
  return icon;
}

function setIconText(el, iconName, size, text) {
  if (!el) return;
  el.replaceChildren(makeIcon(iconName, size), document.createTextNode(' ' + (text || '')));
}

function setIconOnly(el, iconName, size) {
  if (!el) return;
  el.replaceChildren(makeIcon(iconName, size));
}

function setActiveTab(buttons, activeBtn) {
  buttons.forEach(function(btn) {
    var active = btn === activeBtn;
    btn.classList.toggle('active', active);
    if (btn.getAttribute('role') === 'radio') {
      btn.setAttribute('aria-checked', String(active));
      btn.removeAttribute('aria-selected');
    } else {
      btn.setAttribute('aria-selected', String(active));
      btn.removeAttribute('aria-checked');
    }
    btn.tabIndex = active ? 0 : -1;
  });
}

function focusAdjacentTab(buttons, currentBtn, direction) {
  if (!buttons.length) return;
  var idx = buttons.indexOf(currentBtn);
  if (idx < 0) idx = 0;
  var next = buttons[(idx + direction + buttons.length) % buttons.length];
  next.focus();
  next.click();
}

TwitchX.truncate = truncate;
TwitchX.formatViewers = formatViewers;
TwitchX.formatUptime = formatUptime;
TwitchX.setStatus = setStatus;
TwitchX.formatMediaDate = formatMediaDate;
TwitchX.formatDuration = formatDuration;
TwitchX.buildChannelMediaMeta = buildChannelMediaMeta;
TwitchX.makeIcon = makeIcon;
TwitchX.setIconText = setIconText;
TwitchX.setFeedbackClass = setFeedbackClass;
TwitchX.setIconOnly = setIconOnly;
TwitchX.setActiveTab = setActiveTab;
TwitchX.focusAdjacentTab = focusAdjacentTab;
