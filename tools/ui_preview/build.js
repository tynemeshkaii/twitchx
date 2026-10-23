// Builds .preview/app.html the same way app.py::_inline_resources does:
// every <link rel="stylesheet"> becomes an inline <style>, every JS module is
// merged into ONE <script> with the TwitchX bootstrap pair stripped from all
// files but the first. mock.js is appended last and stubs window.pywebview.
//
// Designed to live in tools/ui_preview/ (ROOT is two levels up).
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const UI = path.join(ROOT, 'ui');
const OUT = path.join(ROOT, '.preview');
const BOOTSTRAP = "window.TwitchX = window.TwitchX || {};\nconst TwitchX = window.TwitchX;";

let html = fs.readFileSync(path.join(UI, 'index.html'), 'utf8');
html = html.replace(/<link rel="stylesheet" href="([^"]+)">/g, (m, href) =>
  `<style>\n${fs.readFileSync(path.join(UI, href), 'utf8')}\n</style>`);

const modules = [];
html = html.replace(/<script src="([^"]+)"><\/script>\s*/g, (m, src) => {
  modules.push(fs.readFileSync(path.join(UI, src), 'utf8'));
  return '';
});
const merged = modules
  .map((code, i) => (i ? code.replace(BOOTSTRAP, '// TwitchX already initialised by state.js') : code))
  .join('\n');
const mock = fs.readFileSync(path.join(__dirname, 'mock.js'), 'utf8');

html = html.replace('</body>', `<script>\n${merged}\n</script>\n<script>\n${mock}\n</script>\n</body>`);
fs.mkdirSync(OUT, { recursive: true });
fs.writeFileSync(path.join(OUT, 'app.html'), html);
console.log('built', path.relative(ROOT, path.join(OUT, 'app.html')));
