window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

function truncate(s, n) {
  if (!s) return '';
  return s.length > n ? s.substring(0, n) + '\u2026' : s;
}

function formatViewers(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
  return String(n);
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

function setStatus(text, type) {
  const el = document.getElementById('status-text');
  el.textContent = text;
  const colors = {
    info: 'var(--text-secondary)',
    success: 'var(--live-green)',
    warn: 'var(--warn-yellow)',
    error: 'var(--error-red)',
  };
  el.style.color = colors[type] || colors.info;
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

TwitchX.truncate = truncate;
TwitchX.formatViewers = formatViewers;
TwitchX.formatUptime = formatUptime;
TwitchX.setStatus = setStatus;
TwitchX.formatMediaDate = formatMediaDate;
TwitchX.formatDuration = formatDuration;
TwitchX.buildChannelMediaMeta = buildChannelMediaMeta;

function viewFadeIn(el, showClass) {
  el.classList.add(showClass);
  el.style.opacity = '0';
  requestAnimationFrame(function() {
    requestAnimationFrame(function() {
      el.style.opacity = '';
    });
  });
}

function viewFadeOut(el, hideClass, onDone) {
  el.style.opacity = '0';
  var done = false;
  function finish() {
    if (done) return;
    done = true;
    el.style.opacity = '';
    el.classList.add(hideClass);
    if (onDone) onDone();
  }
  el.addEventListener('transitionend', finish, { once: true });
  setTimeout(finish, 250);
}

TwitchX.viewFadeIn = viewFadeIn;
TwitchX.viewFadeOut = viewFadeOut;
