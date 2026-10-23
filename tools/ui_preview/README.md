# UI preview harness

Тесты не покрывают JS и вёрстку, поэтому UI проверяется глазами. Харнесс
собирает `ui/` в один HTML так же, как это делает приложение, подменяет
Python-мост моком с фейковыми стримами и снимает скрины ключевых экранов в
Chromium через Playwright.

Chromium ≠ WKWebView: всё, что зависит от macOS (titlebar, fullscreen, PiP,
AVKit), всё равно нужно проверять в приложении на маке.

## Запуск

```bash
make preview                     # все сценарии
make preview ARGS="grid player"  # только выбранные
```

Результат — `.preview/` (в `.gitignore`): `app.html` и PNG вида
`<сценарий>-<тема>-<ширина>x<высота>.png`. Каждый сценарий снимается в
темах `dark`/`light` и размерах 960×640 (дефолтное окно, см. `app.py`) и
1280×800, а `grid` и `player` ещё и в минимальном окне 700×500
(`sizes` в записи сценария): 14 сценариев → 60 PNG. Открывай PNG и смотри, а не просто проверяй,
что файлы появились.

`shoot.js` выходит с кодом 1, если на странице был `pageerror` (исключение в
JS), и печатает их список.

### Зависимости

Нужны Node.js и npm-пакет `playwright` с установленным Chromium. В проект
Playwright **не** добавляется (нет `package.json`, CI харнесс не запускает):

- без `node` `make preview` печатает сообщение и выходит с 0;
- без `playwright` `shoot.js` печатает сообщение и выходит с 0;
- в облачных сессиях Claude Code Playwright стоит глобально:
  `NODE_PATH=/opt/node-tools/node_modules`, Chromium в `/opt/pw-browsers`,
  `playwright install` не запускать;
- локально поставь его куда угодно вне репозитория и укажи `NODE_PATH`:
  ```bash
  npm install --prefix ~/.cache/twitchx-preview playwright
  NODE_PATH=~/.cache/twitchx-preview/node_modules make preview
  ```

## Файлы

| Файл | Что делает |
|------|-----------|
| `build.js` | Пишет `.preview/app.html`: инлайнит CSS, склеивает JS-модули в один `<script>` (вырезая пару `window.TwitchX = …; const TwitchX = …;` во всех файлах, кроме первого) — как `app.py::_inline_resources`. В конец добавляет `mock.js`. |
| `mock.js` | Мок `window.pywebview.api` (Proxy: любой метод → `Promise<null>`, `get_avatar`/`get_thumbnail` отвечают картинками), фейковые стримы, `window.__boot(opts)` и `window.__scenario.*`. |
| `shoot.js` | Таблица `SCENARIOS`, перебор тем и размеров, скрины. |

## Как добавить сценарий

1. Если экрану нужны данные, которых нет после `__boot`, добавь функцию в
   `window.__scenario` в `mock.js`: открой вид через `TwitchX.*` и вызови те
   же `window.on*` колбэки, что вызывает Python.
2. Добавь запись в `SCENARIOS` в `shoot.js`:
   ```js
   mything: { opts: { empty: true }, action: p => p.evaluate(() => window.__scenario.mything()) },
   ```
   `opts` уходят в `__boot` (`empty`, `loggedOut`, `noStreams`), `action`
   получает Playwright `page` и выполняется после загрузки.
3. `make preview ARGS="mything"` и посмотри PNG.

Разовую проверку можно сделать и без нового сценария: открой
`.preview/app.html` в браузере, вызови в консоли `__boot()` и нужный колбэк,
например `window.onStatusUpdate({text: 'x', stale: true})`.

## Мок обязан повторять форму данных Python

Мок — это контракт с `ui/api/`. Если поле в Python переименовано или
добавлено, а в моке нет, скрины врут. Сверяйся с тем, что реально шлёт
`_eval_js(...)`:

- `onStreamsUpdate` — `streams` (`login`, `display_name`, `platform`, `game`,
  `title`, `viewers`, `started_at`, `thumbnail_url`, `viewer_trend`),
  `favorites`, `favorites_meta` (ключи `"platform:login"`), `updated_time`,
  `total_viewers`, `total_viewers_formatted` (строка из
  `core.utils.format_viewers`), `has_credentials`, `user_avatars`;
- `onConfigLoaded` — `current_user`, `kick_user`, `favorites`,
  `favorites_meta`, `settings`, `has_credentials`, `youtube_enabled`, …;
- `onChatMessage` — `platform`, `channel_id`, `author`, `author_display`,
  `author_color`, `badges`, `text`, `timestamp`, `emotes`;
- `onBrowseCategories` — список `{name, box_art_url, viewers, platforms}`;
- `onChannelProfile` — `login`, `display_name`, `platform`, `bio`,
  `followers`, `is_live`, `avatar_url`, `can_follow`.
