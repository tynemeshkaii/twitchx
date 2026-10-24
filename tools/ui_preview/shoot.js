// Screenshots every scenario (scenarios.js) in both themes at the app's
// default window size (960x640, see app.py) and at 1280x800. Fails (exit 1)
// on any page error or failed scenario check.
//
// Run:  node tools/ui_preview/build.js && node tools/ui_preview/shoot.js [names…]
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
const { SCENARIOS, DEFAULT_SIZE } = require('./scenarios');

const ROOT = path.resolve(__dirname, '..', '..');
const OUT = path.join(ROOT, '.preview');
const APP = 'file://' + path.join(OUT, 'app.html');
const SIZES = [DEFAULT_SIZE, [1280, 800]];
const THEMES = ['dark', 'light'];

// Opens a fresh page on one scenario and leaves it after the action.
async function openScenario(browser, name, sc, theme, [w, h], errors) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2, colorScheme: theme });
  const storage = Object.assign({ 'twitchx.theme.mode': theme }, sc.storage || {});
  await ctx.addInitScript(s => {
    try { Object.entries(s).forEach(([k, v]) => localStorage.setItem(k, v)); } catch (e) {}
  }, storage);
  const page = await ctx.newPage();
  page.on('pageerror', e => errors.push(`${name}/${theme}/${w}: ${e.message}`));
  if (sc.media) await page.emulateMedia(sc.media);
  await page.goto(APP);
  await page.evaluate(o => window.__boot(o), sc.opts || {});
  await page.waitForTimeout(600);
  if (sc.action) await sc.action(page);
  await page.waitForTimeout(400);
  return { ctx, page };
}

async function main() {
  const only = process.argv.slice(2);
  const unknown = only.filter(n => !SCENARIOS[n]);
  if (unknown.length) {
    console.error('unknown scenarios: ' + unknown.join(', '));
    process.exit(1);
  }
  const browser = await chromium.launch();
  const errors = [];
  for (const [name, sc] of Object.entries(SCENARIOS)) {
    if (only.length && !only.includes(name)) continue;
    for (const theme of THEMES) {
      for (const size of sc.only || SIZES.concat(sc.sizes || [])) {
        const { ctx, page } = await openScenario(browser, name, sc, theme, size, errors);
        if (sc.check) {
          const problem = await sc.check(page);
          if (problem) errors.push(`${name}/${theme}/${size[0]}: ${problem}`);
        }
        await page.screenshot({ path: path.join(OUT, `${name}-${theme}-${size[0]}x${size[1]}.png`) });
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
}

if (require.main === module) main();

module.exports = { openScenario };
