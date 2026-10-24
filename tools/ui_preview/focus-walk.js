// Keyboard focus check: on every scenario press Tab 40 times and report each
// stop where focus cannot be seen — the focused element has no outline and no
// box-shadow (neither has a child, e.g. the card frame, nor a :focus-within
// parent), or it has no box on screen at all — or where the control has no
// accessible name (catches icon-only buttons built in JS, which
// tests/test_accessibility.py cannot see). Each such stop is screenshotted
// to .preview/focus/<scenario>-<step>.png. Exit 1 if any stop fails.
//
// Run:  node tools/ui_preview/build.js && node tools/ui_preview/focus-walk.js [names…]
// Same Playwright setup as shoot.js (see README.md).
const fs = require('fs');
const path = require('path');
let chromium;
try {
  ({ chromium } = require('playwright'));
} catch (e) {
  console.log('playwright not found — skipping focus walk (install it or set NODE_PATH)');
  process.exit(0);
}
const { SCENARIOS, DEFAULT_SIZE } = require('./scenarios');
const { openScenario } = require('./shoot');

const ROOT = path.resolve(__dirname, '..', '..');
const OUT = path.join(ROOT, '.preview', 'focus');
const TABS = 40;
// Variants of another screen that only change colours or media features.
const SKIP = /^accent-|-contrast$|-forced-colors$|-reduced$/;

// Runs in the page: describes the focused element, or null if it is fine.
function describeFocus() {
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) return null;
  const label = el.id ? '#' + el.id
    : el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : '');
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  if (r.width < 1 || r.height < 1 || cs.visibility === 'hidden' || r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) {
    return label + ' (no visible box)';
  }
  const marked = node => {
    const s = getComputedStyle(node);
    const outline = s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0;
    return outline || (s.boxShadow && s.boxShadow !== 'none');
  };
  const byIds = (el.getAttribute('aria-labelledby') || '').split(/\s+/)
    .map(id => document.getElementById(id)).filter(Boolean).map(n => n.textContent).join(' ');
  const name = (el.getAttribute('aria-label') || byIds || el.getAttribute('title') ||
    (el.labels && el.labels.length ? el.labels[0].textContent : '') ||
    el.getAttribute('placeholder') || el.innerText || '').trim();
  const nameless = el.matches('input[type="range"], select') ? !(el.getAttribute('aria-label') || byIds || (el.labels && el.labels.length)) : !name;
  if (nameless) return label + ' (no accessible name)';
  if (marked(el)) return null;
  const kids = el.querySelectorAll(':scope > *, :scope > * > *');
  for (const k of kids) if (marked(k)) return null;
  if (el.parentElement && el.parentElement.matches(':focus-within') && marked(el.parentElement)) return null;
  return label + ' (no outline or box-shadow)';
}

(async () => {
  const only = process.argv.slice(2);
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const errors = [];
  const invisible = [];
  for (const [name, sc] of Object.entries(SCENARIOS)) {
    if (only.length ? !only.includes(name) : SKIP.test(name)) continue;
    // No transitions: the ring must be there the moment focus lands.
    const run = Object.assign({}, sc, { media: Object.assign({ reducedMotion: 'reduce' }, sc.media || {}) });
    const { ctx, page } = await openScenario(browser, name, run, 'dark', DEFAULT_SIZE, errors);
    const seen = new Set();
    for (let i = 1; i <= TABS; i++) {
      await page.keyboard.press('Tab');
      await page.waitForTimeout(30);  // let a 0.01ms transition (skip link) land
      const problem = await page.evaluate(describeFocus);
      if (problem && !seen.has(problem)) {
        seen.add(problem);
        invisible.push(`${name} #${i}: ${problem}`);
        await page.screenshot({ path: path.join(OUT, `${name}-${String(i).padStart(2, '0')}.png`) });
      }
    }
    await ctx.close();
  }
  await browser.close();
  if (errors.length) console.error('page errors:\n' + errors.join('\n'));
  if (invisible.length) {
    console.error('focus problems:\n' + invisible.join('\n'));
    process.exit(1);
  }
  if (errors.length) process.exit(1);
  console.log('focus visible and named on every Tab stop');
})();
