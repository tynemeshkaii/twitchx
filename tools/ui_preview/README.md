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
make focus-walk                  # проверка клавиатурного фокуса
```

Результат — `.preview/` (в `.gitignore`): `app.html` и PNG вида
`<сценарий>-<тема>-<ширина>x<высота>.png`. Каждый сценарий снимается в
темах `dark`/`light` и размерах 960×640 (дефолтное окно, см. `app.py`) и
1280×800; `sizes` добавляет размеры (700×500 — минимальное окно), `only`
заменяет их одним размером: 48 сценариев → 158 PNG. Открывай PNG и
смотри, а не просто проверяй, что файлы появились.

`shoot.js` выходит с кодом 1, если на странице был `pageerror` (исключение в
JS) или не прошла проверка сценария (`check`), и печатает их список.

`focus-walk.js` открывает каждый сценарий (тёмная тема, 960×640, reduced
motion), жмёт Tab 40 раз и падает, если на какой-то остановке фокус не
виден (у элемента, его детей и `:focus-within`-родителя нет ни `outline`,
ни `box-shadow`, или у элемента нет бокса на экране) или у контрола нет
доступного имени. Скрин каждой такой остановки — в `.preview/focus/`.
Варианты экранов (`accent-*`, `*-contrast`, `*-forced-colors`,
`*-reduced`) пропускает; их можно передать явно аргументами.

## Сценарии

| Группа | Сценарии |
|------|-----------|
| Экраны | `grid` (+700×500), `welcome`, `list`, `sort`, `selected`, `context`, `settings`, `settings-player`, `settings-appearance`, `settings-advanced`, `palette`, `palette-empty`, `sidebar-watching`, `collapsed`, `account`, `browse`, `browse-streams`, `channel`, `channel-vods`, `player` (+700×500), `player-menus`, `multistream`, `multistream-add`, `multistream-slots`, `mini` |
| Движение | `grid-reduced` — `prefers-reduced-motion: reduce`; `check` падает, если после загрузки что-то ещё анимируется |
| Контраст | `grid-contrast`, `account-contrast`, `player-contrast` — `prefers-contrast: more` (проверено на Playwright 1.64); `grid-forced-colors` — `forced-colors: active` |
| Акценты | `accent-purple`, `accent-blue`, `accent-teal`, `accent-indigo`, `accent-graphite` — акцент через `localStorage`, рядом live-точки, тост-предупреждение и фокус на карточке. Список = `ACCENT_PALETTE` в `ui/js/settings.js` |
| Загрузка | `state-skeleton`, `state-browse-loading`, `state-vods-loading` |
| Ошибки | `state-error-toast`, `state-player-error`, `state-browse-errors` |
| Пусто | `state-no-favorites`, `state-all-quiet`, `state-browse-empty`, `state-channel-offline`, `multistream` |
| Длинные данные | `state-long` (+700×500), `state-long-list` — название 140 символов, ники 25 символов, 50 избранных, 1.2M зрителей |
| Устаревшие данные | `state-stale` |

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
| `scenarios.js` | Таблица `SCENARIOS` — общая для `shoot.js` и `focus-walk.js`. |
| `shoot.js` | Перебор сценариев, тем и размеров, скрины; `openScenario()` переиспользует `focus-walk.js`. |
| `focus-walk.js` | Tab-обход каждого экрана, невидимый фокус и контролы без имени. |

## Как добавить сценарий

1. Если экрану нужны данные, которых нет после `__boot`, добавь функцию в
   `window.__scenario` в `mock.js`: открой вид через `TwitchX.*` и вызови те
   же `window.on*` колбэки, что вызывает Python.
2. Добавь запись в `SCENARIOS` в `scenarios.js`:
   ```js
   mything: { opts: { empty: true }, action: p => p.evaluate(() => window.__scenario.mything()) },
   ```
   `opts` уходят в `__boot` (`empty`, `loggedOut`, `noStreams`, `allOffline`,
   `long`), `action` получает Playwright `page` и выполняется после
   загрузки. Ещё поля: `sizes`/`only` (размеры), `media`
   (`page.emulateMedia`: `reducedMotion`, `contrast`, `forcedColors`),
   `storage` (ключи `localStorage` до старта приложения), `check`
   (`page → строка ошибки | null`).
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
