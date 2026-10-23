// Screenshots every scenario in both themes at the app's default window size
// (960x640, see app.py) and at 1280x800. Fails (exit 1) on any page error.
//
// Run:  node tools/ui_preview/build.js && node tools/ui_preview/shoot.js
// Needs the `playwright` npm package. In Claude Code cloud sessions it is
// installed globally: NODE_PATH=/opt/node-tools/node_modules, Chromium in
// /opt/pw-browsers. Do NOT run `playwright install` there.
const path = require('path');
let chromium;
try {
  ({ chromium } = require('playwright'));
} catch (e) {
  console.log('playwright not found — skipping UI preview (install it or set NODE_PATH)');
  process.exit(0);
}

const ROOT = path.resolve(__dirname, '..', '..');
const OUT = path.join(ROOT, '.preview');
const APP = 'file://' + path.join(OUT, 'app.html');

// name → { opts for __boot, action run after boot }
// The minimum window (app.py min_size) for the screens most likely to clip.
const MIN_SIZE = [700, 500];
const SCENARIOS = {
  grid: { sizes: [MIN_SIZE] },
  welcome: { opts: { empty: true, loggedOut: true } },
  selected: { action: p => p.click('.stream-card') },
  context: { action: p => p.click('.stream-card', { button: 'right' }) },
  settings: { action: p => p.evaluate(() => TwitchX.openSettings()) },
  palette: { action: async p => { await p.evaluate(() => TwitchX.openPalette()); await p.keyboard.type('sh'); await p.waitForTimeout(500); } },
  'palette-empty': { action: p => p.evaluate(() => TwitchX.openPalette()) },
  collapsed: { action: p => p.click('#sidebar-collapse-btn') },
  account: { action: p => p.click('#account-chip') },
  browse: { action: p => p.evaluate(() => window.__scenario.browse()) },
  channel: { action: p => p.evaluate(() => window.__scenario.channel()) },
  player: { sizes: [MIN_SIZE], action: p => p.evaluate(() => window.__scenario.player()) },
  mini: { action: p => p.evaluate(() => TwitchX.toggleMiniMode()) },
  multistream: { action: p => p.evaluate(() => TwitchX.openMultistreamView()) },
};
const SIZES = [[960, 640], [1280, 800]];
const THEMES = ['dark', 'light'];

(async () => {
  const only = process.argv.slice(2);
  const browser = await chromium.launch();
  const errors = [];
  for (const [name, sc] of Object.entries(SCENARIOS)) {
    if (only.length && !only.includes(name)) continue;
    for (const theme of THEMES) {
      for (const [w, h] of SIZES.concat(sc.sizes || [])) {
        const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2, colorScheme: theme });
        await ctx.addInitScript(t => { try { localStorage.setItem('twitchx.theme.mode', t); } catch (e) {} }, theme);
        const page = await ctx.newPage();
        page.on('pageerror', e => errors.push(`${name}/${theme}/${w}: ${e.message}`));
        await page.goto(APP);
        await page.evaluate(o => window.__boot(o), sc.opts || {});
        await page.waitForTimeout(600);
        if (sc.action) await sc.action(page);
        await page.waitForTimeout(400);
        await page.screenshot({ path: path.join(OUT, `${name}-${theme}-${w}x${h}.png`) });
        await ctx.close();
      }
    }
  }
  await browser.close();
  if (errors.length) {
    console.error('page errors:\n' + errors.join('\n'));
    process.exit(1);
  }
  console.log('screenshots written to', path.relative(ROOT, OUT));
})();
