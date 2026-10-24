// Screens the harness knows how to reach. Shared by shoot.js (screenshots)
// and focus-walk.js (keyboard focus check).
//
// name → {
//   opts     → window.__boot(opts) (see mock.js)
//   action   → async (page) after boot
//   sizes    → extra [w, h] on top of the default sizes
//   only     → [w, h] list that replaces the default sizes
//   media    → page.emulateMedia(media) before load (reducedMotion, contrast, forcedColors)
//   storage  → localStorage entries set before the app script runs
//   check    → async (page) → error string or null, run after the action
// }

// The minimum window (app.py min_size) for the screens most likely to clip.
const MIN_SIZE = [700, 500];
const DEFAULT_SIZE = [960, 640];

const scenario = name => p => p.evaluate(n => window.__scenario[n](), name);

// Under reduced motion nothing may still be moving once the page settles.
async function noRunningAnimations(page) {
  const moving = await page.evaluate(() => document.getAnimations()
    .filter(a => a.playState === 'running')
    .map(a => {
      const t = a.effect && a.effect.target;
      const name = a.animationName || a.transitionProperty || 'animation';
      return (t ? (t.id ? '#' + t.id : t.className || t.tagName) : '?') + ' ' + name;
    }));
  return moving.length ? 'still animating under reduced motion: ' + moving.slice(0, 8).join(', ') : null;
}

const SCENARIOS = {
  grid: { sizes: [MIN_SIZE] },
  welcome: { opts: { empty: true, loggedOut: true } },
  list: { action: p => p.evaluate(() => { TwitchX.state.gridMode = 'list'; TwitchX.renderGrid(); }) },
  sort: { action: p => p.click('#sort-menu-btn') },
  selected: { action: p => p.click('.stream-card') },
  context: { action: p => p.click('.stream-card', { button: 'right' }) },
  settings: { action: p => p.evaluate(() => TwitchX.openSettings()) },
  'settings-player': { action: p => p.evaluate(() => { TwitchX.openSettings(); TwitchX.showSettingsTab('player'); }) },
  'settings-appearance': { action: p => p.evaluate(() => { TwitchX.openSettings(); TwitchX.showSettingsTab('appearance'); }) },
  'settings-advanced': { action: p => p.evaluate(() => { TwitchX.openSettings(); TwitchX.showSettingsTab('advanced'); window.onWatchStatistics({ ok: true, stats: { today: { total_sec: 7260, streams_count: 3, unique_channels: 2 }, total: { total_sec: 912000, unique_channels: 41 }, weekly: [], top_channels: [{ channel: 'shroud', display_name: 'shroud', platform: 'twitch', total_sec: 54000, sessions_count: 12 }, { channel: 'xqc', display_name: 'xQc', platform: 'kick', total_sec: 32000, sessions_count: 8 }] } }); }) },
  palette: { action: async p => { await p.evaluate(() => TwitchX.openPalette()); await p.keyboard.type('sh'); await p.waitForTimeout(500); } },
  'palette-empty': { action: p => p.evaluate(() => TwitchX.openPalette()) },
  'sidebar-watching': { action: p => p.evaluate(() => { TwitchX._notifBadgeLogins = ['twitch:shroud', 'kick:xqc']; TwitchX.state.watchingChannelKey = 'twitch:shroud'; TwitchX.state.watchingChannel = 'shroud'; TwitchX.state.sidebarSections.offline = false; TwitchX.renderSidebar(); }) },
  collapsed: { action: p => p.click('#sidebar-collapse-btn') },
  account: { action: p => p.click('#account-chip') },
  browse: { action: scenario('browse') },
  'browse-streams': { action: scenario('browse-streams') },
  'channel-vods': { action: scenario('channel-vods') },
  channel: { action: scenario('channel') },
  player: { sizes: [MIN_SIZE], action: scenario('player') },
  'player-menus': { action: async p => { await p.evaluate(() => { window.__scenario.player(); TwitchX.showPlayerView(); document.querySelectorAll('.toast').forEach(t => t.remove()); }); await p.click('#chat-more-btn'); await p.waitForTimeout(200); await p.mouse.move(400, 300); await p.evaluate(() => { document.getElementById('player-more-btn').click(); document.getElementById('chat-more-menu').classList.remove('hidden'); }); } },
  'multistream-slots': { action: async p => { await p.evaluate(() => { TwitchX.openMultistreamView(); TwitchX.addMultiSlot(0, 'shroud', 'twitch'); TwitchX.addMultiSlot(1, 'xqc', 'kick'); }); await p.hover('.ms-slot[data-slot-idx="1"]'); } },
  'multistream-add': { action: p => p.evaluate(() => { TwitchX.openMultistreamView(); TwitchX.openFirstEmptyMultiSlot(); }) },
  mini: { action: p => p.evaluate(() => TwitchX.toggleMiniMode()) },
  multistream: { action: p => p.evaluate(() => TwitchX.openMultistreamView()) },

  // ── Motion and contrast (phase 4.1, 4.2) ─────────────────
  'grid-reduced': { media: { reducedMotion: 'reduce' }, check: noRunningAnimations },
  'grid-contrast': { only: [DEFAULT_SIZE], media: { contrast: 'more' }, action: async p => { await p.keyboard.press('Tab'); await p.focus('.stream-card'); } },
  'account-contrast': { only: [DEFAULT_SIZE], media: { contrast: 'more' }, action: p => p.click('#account-chip') },
  'player-contrast': { only: [DEFAULT_SIZE], media: { contrast: 'more' }, action: async p => { await p.evaluate(() => { window.__scenario.player(); document.querySelectorAll('.toast').forEach(t => t.remove()); }); await p.click('#player-more-btn'); } },
  'grid-forced-colors': { only: [DEFAULT_SIZE], media: { forcedColors: 'active' } },

  // ── States (phase 4.4) ───────────────────────────────────
  'state-skeleton': { opts: { noStreams: true }, action: scenario('state-skeleton') },
  'state-browse-loading': { only: [DEFAULT_SIZE], action: scenario('state-browse-loading') },
  'state-vods-loading': { only: [DEFAULT_SIZE], action: scenario('state-vods-loading') },
  'state-error-toast': { only: [DEFAULT_SIZE], action: scenario('state-error-toast') },
  'state-player-error': { only: [DEFAULT_SIZE], action: scenario('state-player-error') },
  'state-browse-errors': { only: [DEFAULT_SIZE], action: scenario('state-browse-errors') },
  'state-browse-empty': { only: [DEFAULT_SIZE], action: scenario('state-browse-empty') },
  'state-no-favorites': { only: [DEFAULT_SIZE], opts: { empty: true } },
  'state-all-quiet': { only: [DEFAULT_SIZE], opts: { allOffline: true } },
  'state-channel-offline': { only: [DEFAULT_SIZE], action: scenario('state-channel-offline') },
  'state-stale': { only: [DEFAULT_SIZE], action: scenario('state-stale') },
  'state-long': { sizes: [MIN_SIZE], opts: { long: true }, action: scenario('state-long') },
  'state-long-list': { only: [DEFAULT_SIZE], opts: { long: true }, action: p => p.evaluate(() => { TwitchX.state.gridMode = 'list'; TwitchX.renderGrid(); }) },
};

// ── Accents (phase 4.3): every swatch next to live dots and a warning ──
// Must match ACCENT_PALETTE in ui/js/settings.js.
const ACCENTS = { purple: '#BF5AF2', blue: '#0A84FF', teal: '#40C8E0', indigo: '#5E5CE6', graphite: '#8E8E93' };
for (const [name, value] of Object.entries(ACCENTS)) {
  SCENARIOS['accent-' + name] = {
    only: [DEFAULT_SIZE],
    storage: { 'twitchx.accent': value },
    action: async p => {
      await p.evaluate(() => {
        TwitchX.showToast('Kick did not respond — retrying', 'warn');
        TwitchX.state.watchingChannelKey = 'twitch:shroud';
        TwitchX.renderSidebar();
      });
      await p.keyboard.press('Tab');
      await p.focus('.stream-card');
    },
  };
}

module.exports = { SCENARIOS, DEFAULT_SIZE, MIN_SIZE };
