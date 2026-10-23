# Redesign phase 2: каркас и навигация

Ты — senior frontend-инженер в репозитории TwitchX с опытом macOS (pyobjc,
AppKit, WKWebView). Это третья из пяти фаз редизайна и самая рискованная:
меняется структура окна. После фазы в окне одна верхняя панель, навигация
живёт в сайдбаре, каждая функция — в одном месте, глобального нижнего
плеер-бара нет, клик по карточке сразу запускает стрим.

Компоненты (карточка, строка сайдбара, настройки) в этой фазе **не
перерисовываются** по новому образцу — это фаза 3. Здесь меняются каркас,
навигация и места контролов. Новые элементы стилизуй токенами фазы 1 аккуратно,
но без полировки.

## Перед началом

1. Прочитай `CLAUDE.md` и `docs/prompts/redesign/README.md`. Особенно раздел
   «Принятые решения»: клик сразу запускает стрим, mini mode остаётся.
2. Убедись, что фаза 1 смержена: в `main` есть `tests/test_css_tokens.py`, в
   `ui/css/layout.css` у `#app` нет `mesh-drift`. Если нет — остановись и
   сообщи пользователю.
3. `make check`, `css_ownership`, `make preview` → копия в `.preview-before/`.
4. Прочитай целиком: `ui/index.html`, `ui/js/init.js`, `ui/js/player.js`,
   `ui/js/keyboard.js`, `ui/js/sidebar.js` (функции `renderSidebar`,
   `renderRail`, `applySidebarLayout`, обработчики клика строк), `ui/js/render.js`
   (`createCard`/обработчики клика ~строка 307), `ui/js/palette.js`,
   `ui/js/callbacks.js` (`onSearchResults`, `onStreamsUpdate`, `onStatusUpdate`),
   `ui/js/utils.js` (`setStatus`), `ui/js/api-bridge.js`,
   `ui/js/view-transitions.js`, `ui/js/channel.js`, `app.py`,
   `ui/css/layout.css`, `ui/css/components/{player-bar,search-toolbar,sidebar,player-view}.css`,
   `tests/test_ui_a11y.py`, `tests/test_accessibility.py`, `tests/test_js_bundle.py`.

## Карта зависимостей (проверено по коду на момент написания)

Перед удалением любого элемента перепроверь grep'ом — числа могли сдвинуться.

| Элемент | Кто ссылается | Куда переезжает |
|---|---|---|
| `#watch-btn` | `init.js`, `keyboard.js`, `player.js`, `channel.js` | удаляется; вызовы `TwitchX.doWatch()` остаются |
| `#quality-select` | 12 мест: `api-bridge.js`, `callbacks.js`, `channel.js`, `init.js`, `player.js` | меню качества в оверлее плеера; значение в `TwitchX.state.quality` |
| `#stop-player-btn` | `init.js`, `player.js` | закрытие плеера (`#close-player-btn`) уже есть |
| `#watch-external-btn` | `callbacks.js`, `init.js`, `player.js` | меню «…» оверлея + контекстное меню (уже есть) |
| `#volume-group`, `#mute-btn`, `#volume-slider` | `init.js`, `player.js` | оверлей плеера, ID сохраняются |
| `#seek-bar`, `#seek-bar-container` | `init.js`, `player.js`, `test_ui_player_views.py` | оверлей плеера, ID сохраняются |
| `#status-text` | `utils.js` (`setStatus`, ≈43 вызова по всему JS) | мета заголовка раздела + тосты |
| `#total-viewers`, `#updated-time` | `callbacks.js` | мета заголовка раздела |
| `#live-dot`, `#record-dot` | `callbacks.js`, `player.js` | оверлей плеера |
| `#browser-btn` | `init.js` | контекстное меню + «…» в плеере |
| `#refresh-btn` | `init.js` | удаляется, остаётся `#toolbar-refresh-btn` |
| `#mini-mode-btn` | `init.js` (`toggleMiniMode`, `applyMiniMode`) | поповер аккаунта |
| `#settings-btn` | `init.js` | шестерёнка в чипе аккаунта |
| `#stream-loader` | `callbacks.js` | полоска наверху `#player-stage` |
| `#platform-tabs` / `.platform-tab` | `init.js` (`setPlatformFilter` синхронизирует с `.platform-chip`), `api-bridge.js` (YouTube gating) | удаляется, остаётся `#toolbar-platform-chips` |
| `#toolbar-platform-chips` | `init.js`, `view-transitions.js` (`CHROME_IDS`) | внутрь `#toolbar`, ID сохраняется |
| `#search-area`, `#search-input`, `#search-dropdown`, `#add-btn` | `init.js`, `callbacks.js`, `channel.js`, `render.js` | палитра ⌘K |
| `#filter-input` | `init.js` | палитра ⌘K (раздел «Игры») |
| `#sort-select` | `init.js` | меню сортировки у заголовка раздела |
| `#browse-nav-btn` | `init.js` | навигация сайдбара |
| `#profile-area`, `#kick-profile-area` | ID нигде, внутренние ID — в `api-bridge.js`, `callbacks.js`, `sidebar.js` | поповер аккаунта, внутренние ID сохраняются |

Горячие клавиши (`TwitchX.DEFAULT_SHORTCUTS` в `state.js`): `refresh r`,
`watch Space`, `fullscreen f`, `toggle_chat c`, `mute m`, `pip p`,
`volume_up/down ↑↓`, `next/prev_stream →←`. `watch`, `next_stream` и
`prev_stream` работают через состояние выбора — **его нельзя удалять**.

## Шаги

Порядок важен: сначала у контролов появляется новый дом, потом удаляется
старый. Каждый шаг — отдельный коммит, после каждого `make check` +
`make preview` + просмотр скринов.

### 2.0 Спайк: прозрачный заголовок окна (ограничен по времени)

Цель — светофор внутри сайдбара и одна верхняя панель высотой 52 px вместо
нативного заголовка плюс пустой строки `#sidebar-header`.

В `app.py`, рядом с `_enable_video_fullscreen`, добавь
`_integrate_titlebar()` и вызывай её из `_on_loaded` через
`AppHelper.callAfter`:

```python
win = <NSWindow из cocoa.BrowserView.instances>  # как в _enable_video_fullscreen
win.setStyleMask_(win.styleMask() | NSWindowStyleMaskFullSizeContentView)
win.setTitlebarAppearsTransparent_(True)
win.setTitleVisibility_(NSWindowTitleHidden)
toolbar = NSToolbar.alloc().initWithIdentifier_("twitchx.main")
toolbar.setShowsBaselineSeparator_(False)
win.setToolbar_(toolbar)
win.setToolbarStyle_(NSWindowToolbarStyleUnifiedCompact)  # центрирует светофор в ~52px
```

Главная проблема — **перетаскивание окна**: WKWebView забирает события мыши в
зоне заголовка, а `-webkit-app-region` в WKWebView не работает. Пробуй по
порядку и остановись на первом рабочем варианте:

1. механизм drag-region pywebview 5 (класс из `webview.DRAG_REGION_SELECTOR`)
   — проверь в исходниках установленного pywebview, работает ли он без
   `frameless=True`/`easy_drag`;
2. JS: `mousedown` на пустой зоне `.titlebar-drag` → мост
   `pywebview.api.begin_window_drag()` → в Python
   `AppHelper.callAfter(lambda: win.performWindowDragWithEvent_(NSApp.currentEvent()))`;
   двойной клик по зоне → `win.zoom_(None)` (или по системной настройке
   `AppleActionOnDoubleClick`);
3. прозрачный нативный `NSView` поверх полосы заголовка с
   `mouseDownCanMoveWindow = True` и пропуском кликов в зонах кнопок.

Весь pyobjc-код — в `try/except` с логированием: если что-то не так, окно
обязано остаться рабочим с нативным заголовком.

**Лимит — полдня.** В облачной сессии без мака ты не можешь это проверить:
напиши код за фичефлагом `settings["integrated_titlebar"]` (по умолчанию
`False`, ключ в `DEFAULT_CONFIG`), вёрстку сделай так, чтобы она работала в
обоих режимах (класс `#app.titlebar-integrated` добавляется из Python через
`_eval_js` после успешной интеграции и даёт отступ под светофор), и опиши в
PR чек-лист проверки на маке. Если флаг выключен — нативный заголовок
остаётся, а пустая строка `#sidebar-header` всё равно исчезает (кнопка
сворачивания переезжает в шапку сайдбара рядом с навигацией).

Удали из `layout.css` слой `drag-regions` (`-webkit-app-region` не работает в
WKWebView), если выбранный вариант его не использует. Обнови
`tools/css_ownership.py`, если меняется список слоёв.

### 2.1 Верхняя панель контента

- В `#toolbar` слева — `#toolbar-platform-chips` (ID сохраняется,
  `view-transitions.js` знает его в `CHROME_IDS`), стиль — общий `.segmented`
  из `buttons.css`, не отдельные таблетки с заливкой акцентом.
- Справа — кнопка-поле «Search channels, games ⌘K» (`button`,
  `aria-keyshortcuts="Meta+K"`), открывает `TwitchX.openPalette()`, и
  `#toolbar-refresh-btn`.
- Отдельный ряд чипов под тулбаром исчезает (у `#toolbar-platform-chips`
  больше нет своей полосы и `border-bottom`).
- Высота панели — 52 px.

### 2.2 Заголовок раздела вместо статус-бара

- Над сеткой (внутри `#stream-grid`-вью или сразу над `#view-stack` для
  вью Following): `h1` «Following», рядом мета `#section-meta`:
  `9 live · 495K watching · updated 15:42`. `#total-viewers` и
  `#updated-time` переезжают внутрь меты с сохранением ID (их заполняет
  `onStreamsUpdate`). Класс `.stale` у `#updated-time` продолжает работать.
- Справа — кнопка-меню сортировки «Most viewers ▾» (поповер с тремя пунктами
  и пунктом плотности, который сейчас делает `#grid-toggle-btn`). Состояние —
  `TwitchX.state.sortKey`; `#sort-select` удаляется вместе с обработчиком в
  `init.js`, запись в localStorage (если есть) сохраняется.
- `#filter-input` удаляется (фильтр по игре уходит в палитру, шаг 2.4);
  `TwitchX.state.filterText` остаётся источником правды для `render.js`.
- `TwitchX.setStatus(text, type)` сохраняет сигнатуру, меняется реализация:
  `info`/`success` → короткий текст в `#section-meta` (временно заменяет
  «updated …» на 4 с), `warn`/`error` → `TwitchX.showToast`. Найди вызовы,
  которые уже сами показывают тост после `setStatus` (`onStatusUpdate` в
  `callbacks.js`), и не дублируй тосты.
- Заголовок раздела меняется по вью: Following / Browse / название канала;
  Browse и канал уже имеют свои шапки — приведи их к той же высоте и
  стилю, не переделывая содержимое.

### 2.3 Сайдбар: навигация и аккаунты

1. Сверху сайдбара (под зоной светофора) — `nav` с тремя пунктами:
   Following (показывает сетку), Browse (`TwitchX.showBrowseView()`),
   Multi-view (`TwitchX.openMultistreamView()`). Активный пункт — `aria-current="page"`
   и фон `--hover-bg-strong`. Синхронизируй его со сменой вью (найди, где
   вызываются `showBrowseView`, `showPlayerView`, `openMultistreamView`,
   `showChannelView`, закрытия; профиль канала и плеер подсвечивают пункт, из
   которого пришли, или ни один). Удали `#browse-nav-btn` и `#browse-nav-wrapper`.
2. Удали `#platform-tabs` из HTML, его обработчики в `init.js` и синхронизацию
   в `setPlatformFilter`, селектор в `applyYoutubeGating`
   (`api-bridge.js:92`), стили в `sidebar.css`. Сайдбар фильтруется общим
   `activePlatformFilter`, как и сейчас.
3. `#profile-area` и `#kick-profile-area` заменяются **чипом аккаунта** внизу
   сайдбара: аватар (Twitch-аватар или инициал), имя (первый залогиненный
   аккаунт или «Not signed in»), ряд точек подключения
   (`.platform-status-dots` — один контейнер, его заполняет `sidebar.js:987`),
   кнопка-шестерёнка (`TwitchX.openSettings`, заменяет `#settings-btn`).
4. Клик по чипу открывает **поповер аккаунтов**: секция на платформу
   (Twitch, Kick, YouTube — если `youtubeEnabled`) с состоянием и
   действиями. Существующие элементы переезжают в поповер **с теми же ID**:
   `login-btn`, `user-info`, `user-avatar`, `user-display-name`,
   `logout-link`, `import-link`, `kick-login-sidebar-btn`, `kick-user-info`,
   `kick-user-name`, `kick-logout-link`. Плюс пункт «Mini mode» (вызывает
   `TwitchX.toggleMiniMode`, заменяет `#mini-mode-btn`; обнови
   `toggleMiniMode`/`applyMiniMode`, чтобы они не искали удалённую кнопку) и
   «Settings… ⌘,».
5. Поповер — новый модуль `ui/js/account.js` по шаблону из CLAUDE.md
   (bootstrap-пара, уникальные top-level имена, экспорт через
   `TwitchX.openAccountPopover` / `closeAccountPopover`), подключение в
   `ui/index.html` сразу после `sidebar.js`. Обнови порядок модулей в
   CLAUDE.md. Стили — новый `ui/css/components/account-popover.css`
   (подключить в `index.html`), один владелец селекторов.
6. Поведение поповера: `role="dialog"`, `aria-labelledby`, фокус на первый
   элемент при открытии, Esc и клик мимо закрывают, фокус возвращается на
   чип, Tab зациклен внутри. Видимость через класс (`.visible`/`hidden`), не
   `style.display`.
7. В свёрнутом сайдбаре (рейл) навигация — иконки 32 px с тултипами, чип
   аккаунта — только аватар.

### 2.4 Палитра забирает поиск, добавление каналов и фильтр по игре

`palette.js` сейчас ищет по локальным каналам и командам (`PALETTE_COMMANDS`,
`renderPaletteResults`). Добавь:

- Раздел **Channels (search)**: при вводе ≥ 2 символов с дебаунсом 400 мс
  вызывает `TwitchX.api.search_channels(query, platform)` (как сейчас делает
  `init.js:218`, платформа из `activePlatformFilter`). Результаты приходят в
  `window.onSearchResults(results, meta)` (`callbacks.js:142`): научи его
  отдавать результаты палитре, если палитра открыта, иначе — старому
  дропдауну (пока он существует). Пункт результата: аватар, имя, платформа,
  «live» и действие Enter = открыть профиль канала, ⌘Enter = добавить в
  избранное (`TwitchX.addChannel` или его внутренняя функция — посмотри, что
  он делает с `#search-input`, и вынеси логику добавления в функцию с
  параметрами `(login, platform)`).
- Раздел **Games**: уникальные игры из `TwitchX.state.streams`, Enter
  выставляет `TwitchX.state.filterText` и перерисовывает сетку; в меню
  заголовка появляется чип «Game: VALORANT ✕» для сброса.
- Команда **Add channel…** в `PALETTE_COMMANDS`.
- После этого удали `#search-area` (и `#search-dropdown`, `#add-btn`,
  `#search-row`), их обработчики в `init.js`, ссылки в `callbacks.js`,
  `channel.js`, `render.js` (пустое состояние «Focus Search» должно открывать
  палитру), стили в `search-toolbar.css`. `onSearchResults` теперь отдаёт
  результаты только палитре.
- Палитра — `role="dialog"` с `combobox`/`listbox` уже размечена; новые
  разделы — `role="group"` с `aria-label`.

### 2.5 Контролы плеера в оверлей

До удаления бара у его контролов должен появиться новый дом внутри
`#player-stage`:

- Нижняя полоса оверлея: play/pause, `#mute-btn` + `#volume-slider` (ID
  сохраняются), live-индикатор (`#live-dot`, `#record-dot`), для VOD —
  `#seek-bar-container` и `#vod-time-display`, справа меню качества, PiP
  (`#pip-player-btn` переезжает из шапки), fullscreen.
- Меню качества — кнопка с текущим значением («Best», «1080p60») и поповер.
  Значение хранится в `TwitchX.state.quality`, но **на этом шаге** скрытый
  `#quality-select` остаётся источником, который читают 12 мест: меню пишет в
  него значение и диспатчит `change`. Перевод всех мест на `state.quality` и
  удаление селекта — отдельный коммит в конце шага, с grep до и после.
- Снять `controls` с `<video>` (`player.js:46` и атрибут в `index.html`).
  Fullscreen идёт через `video.webkitEnterFullscreen()` (`player.js:404`) —
  нативный AVKit со своими контролами. **Риск:** нужно проверить на маке, что
  AVKit показывает контролы при снятом атрибуте. Сделай защиту: перед
  `webkitEnterFullscreen` ставь `video.controls = true`, на
  `webkitendfullscreen`/`fullscreenchange` при выходе — снимай. Проверь
  совместимость с `isVideoFullscreen()`, `gentleResetVideo` и
  `softResetVideo` (CLAUDE.md: «Fullscreen сам выходит»). То же для
  мультистрима (`multistream.js:404`).
- Автоскрытие оверлея: переиспользуй код из `player.js` (раздел
  «Fullscreen auto-hide controls», ~строка 1589) для оконного режима —
  прятать через 2 с без движения мыши над `#player-stage`, показывать по
  движению, фокусу внутри оверлея и паузе. Курсор прячется вместе с
  оверлеем.
- `#stream-loader` переезжает наверх `#player-stage` (тонкая полоса 2 px
  акцентом).
- Хоткеи из `DEFAULT_SHORTCUTS` должны работать без изменений в
  `keyboard.js`, кроме удаления ссылок на `#watch-btn`.

### 2.6 Удалить глобальный плеер-бар и включить клик-для-запуска

1. Клик по карточке (`render.js` ~307) и строкам сайдбара (`sidebar.js`
   ~343, ~589) вызывает `TwitchX.selectChannel(...)` и сразу `TwitchX.doWatch()`.
   Обработчики `dblclick` удалить. Enter/Space на фокусе — как сейчас
   (`tests/test_ui_a11y.py` должен остаться зелёным).
2. **Состояние выбора остаётся** (`selectChannel`, `state.selectedChannel`,
   `state.selectedChannelKey`): на нём держатся хоткеи `watch`, `next_stream`,
   `prev_stream`. Визуально выбор показывается только при управлении с
   клавиатуры (класс `.selected` рисуется так же, как `:focus-visible`;
   мышиный клик сразу уводит в плеер).
3. Удали `#player-bar` из `index.html`. Все контролы из таблицы зависимостей
   к этому моменту уже переехали. Удали ссылки на `#watch-btn`
   (`init.js`, `keyboard.js:160`, `player.js`, `channel.js:27` — там
   переключается класс `active`; просто убери эти строки), `#browser-btn`,
   `#refresh-btn`, `#mini-mode-btn`, `#settings-btn`, `#stop-player-btn`.
4. «Open in browser» — новый пункт контекстного меню канала
   (`data-action="browser"`, обработчик в `context-menu.js` через существующий
   `TwitchX.api.open_browser(login, platform)`) и пункт меню «…» в плеере.
   Обнови `tests/test_ui_states.py::test_context_menu_keeps_all_channel_actions`,
   если он перечисляет действия.
5. `ui/css/components/player-bar.css`: удали всё, что относилось к бару;
   оставшиеся правила (`#record-btn`, `#vod-time-display`, `.record-dot`,
   `#stream-loader`) перенеси в `player-view.css` и удали файл и его `<link>`.
   `css_ownership` должен остаться зелёным.
6. Mini mode: обнови `#app.mini` в `layout.css` под новый сайдбар (без
   навигации и поповера, только список Live).
7. Проверь минимальное окно 700×500 (`app.py`): добавь его в `SIZES` харнесса
   хотя бы для `grid` и `player`.

## Чего не делать

- Не перерисовывать карточку, строку сайдбара, настройки, Browse по новому
  образцу — это фаза 3. Здесь только структура и места.
- Не переименовывать ID, которые переезжают.
- Не трогать Python-логику, кроме `app.py` (2.0) и, при необходимости,
  одного метода моста для перетаскивания окна.
- Не удалять состояние выбора и не менять `DEFAULT_SHORTCUTS`.

## Выход из фазы: ручной чек-лист (в PR, для проверки на маке)

- [ ] Запуск стрима: клик по карточке, строке сайдбара, аватару рейла,
      карточке Browse, кнопке Watch в профиле канала, пункту палитры, с
      клавиатуры (←/→ + Space, Enter на фокусе).
- [ ] VOD и клип: `watch_media` получает `url`, перемотка, время.
- [ ] Внешний плеер, запись, PiP, fullscreen (контролы AVKit на месте),
      выход из fullscreen не ломает оверлей.
- [ ] Громкость и mute из оверлея и хоткеями, меню качества меняет поток.
- [ ] Мультистрим: добавить, убрать, переключить чат; скрытый слот не играет
      звук (правило из CLAUDE.md).
- [ ] Поповер аккаунта: логин/логаут Twitch, Kick, YouTube, импорт
      фолловов, mini mode, настройки; Esc и клик мимо закрывают.
- [ ] Палитра: поиск и добавление канала, фильтр по игре и сброс.
- [ ] Окно 700×500 и 960×640: ничего не обрезано.
- [ ] Если включён `integrated_titlebar`: светофор на месте, окно
      таскается за пустую часть панели, двойной клик разворачивает.

Плюс автоматические гейты: `make check`, `css_ownership`, `make preview` без
ошибок страницы. PR: `Redesign phase 2: shell and navigation`, в описании
скрины до/после для `grid`, `player`, `welcome`, `collapsed`, `palette` в
960×640.
