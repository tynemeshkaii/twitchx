# TwitchX — UX/UI аудит

Дата: 2026-08-20 | Статус: **Active** | Формат: находки → план фаз (по одной фазе на сессию)

## Методика

- Статический разбор всего `ui/` (18 JS-модулей, 27 CSS-файлов, index.html) + связанных мест `ui/api/` и `app.py`.
- Визуальный прогон UI в браузерном харнессе: копия `ui/` + воспроизведение инлайн-слияния из `app.py._inline_resources` + заглушка `window.pywebview.api` с мок-данными. Проверены: grid (4 режима плотности), sidebar (развёрнутый/collapsed rail), context menu, settings (все вкладки), browse, channel view, multistream, player+chat, palette, тосты, light/dark темы, mini mode, окно 960×640 и 700×500 (min).
- Харнесс одноразовый (scratchpad), в репозиторий не входит. Повторить: скопировать `ui/`, смержить JS в один `<script>` тем же кодом, что в `app.py`, подложить sync-стаб `pywebview.api`, открыть в браузере.

Пометки: ✅ = воспроизведено визуально/эмпирически; 📖 = подтверждено чтением кода; ❓ = требует проверки на реальном `.app`.

---

## P0 — критические

### 1. Все синхронные вызовы `TwitchX.api.*` получают Promise вместо данных (системный баг) 📖
pywebview 5.4 всегда возвращает Promise из JS-моста (`webview/js/api.js`: `var promise = new Promise(...)`). Код читает результат синхронно:

| Место | Что ломается |
|---|---|
| `ui/js/api-bridge.js:99` (`pywebviewready`) | `get_config()` → профиль Twitch/Kick не восстанавливается после рестарта (сайдбар показывает "Login with Twitch" залогиненному юзеру), кастомные шорткаты не грузятся, `youtubeEnabled`/`kickScopes` не выставляются, favorites не гидрируются до первого поллинга |
| `ui/js/settings.js:277` (`openSettings`) | все поля настроек открываются пустыми/дефолтными; **Save после этого перезаписывает конфиг дефолтами** (theme → dark, accent → amber, пути → JS-дефолты) — класс data-loss |
| `ui/js/settings.js:203` | `JSON.parse(Promise)` → исключение → Watch Statistics **всегда** «Failed to load statistics» |
| `ui/js/settings.js:422` | футер настроек показывает `v[object Promise]` ❓ (легко проверить глазами в .app) |
| `ui/js/chat.js:233` | чат-фильтры/блоклист никогда не грузятся из конфига |
| `ui/js/player.js:72` | ширина чата и chat_visible не восстанавливаются |
| `ui/js/multistream.js:207` | quality слота всегда падает в 'best' |

**Fix:** единый асинхронный путь. Либо (а) все места переводятся на `await`/`.then`, либо (б) Python пушит снапшот конфига сам: `_eval_js('window.onConfigLoaded(...)')` при `loaded` + после `save_settings`, а JS-геттеры выпиливаются. Вариант (б) укладывается в существующую архитектуру callbacks.

### 2. Empty-state / Welcome-экран невидим (opacity: 0 навсегда) ✅
`renderEmptyState()` (`ui/js/render.js:362`) ставит `.view-active` и снимает `.hidden`, но класс `.visible` не добавляет никто (только снимается в `render.js:320`). CSS требует его: `#empty-state { opacity: 0 }`, `#empty-state.visible { opacity: 1 }` (`ui/css/components/empty-state.css`). Итог: новый пользователь после первого запуска видит **пустой чёрный экран** вместо «Welcome to TwitchX» с кнопкой логина; «No favorites yet» и «All quiet right now» так же невидимы. Проваливает пункт 1 QA-чеклиста P0-3b.
**Fix:** в `renderEmptyState` добавить `target.classList.add('visible')` (и снимать при скрытии), либо убрать opacity-гейт из CSS для `.view-active`.

### 3. Multistream: кнопка «Add Stream» прячет весь grid ✅
Клик по `+` / «Add Stream» на пустом гриде → чёрный экран без слотов. Механика: `openFirstEmptyMultiSlot` оставляет слоту `ms-state-empty` + добавляет `ms-add-form-open`; `_updateMultiGridLayout` считает открытую форму за visualCount → grid теряет `ms-grid-empty`; правило `#multistream-grid:not(.ms-grid-empty) .ms-slot.ms-state-empty { display:none }` (`ui/css/views.css:283`) по специфичности бьёт `#multistream-grid .ms-slot.ms-add-form-open { display:block }` (`views.css:320`) → все 4 слота display:none.
**Fix:** исключить форму: `#multistream-grid:not(.ms-grid-empty) .ms-slot.ms-state-empty:not(.ms-add-form-open) { display:none }`, или вводить отдельный `ms-state-adding` вместо 'empty' в `openFirstEmptyMultiSlot`.

### 4. Каждый Kick/YouTube-фаворит дублируется фантомной offline-строкой Twitch ✅📖
`data.py:123,472` шлёт `favorites` как плоский список логинов всех платформ; `getFavoriteEntries()` (`ui/js/state.js:203`) для логинов не найденных в meta по ключу `twitch:<login>` создаёт legacy-запись с platform='twitch'. Kick-фаворит `kick:trainwreckstv` есть в meta, но `twitch:trainwreckstv` — нет → фантомная offline-строка в сайдбаре, лишний счётчик Favorites, лишние avatar-фетчи.
**Fix:** в `onStreamsUpdate`/`hydrateFavoritesFromConfig` не подмешивать legacy-логины, уже покрытые meta любой платформы (сравнивать по `login`, не по ключу), или перестать слать kick/youtube-логины в legacy-массиве из Python.

---

## P1 — серьёзные

### 5. Контекстное меню: пункты Watch/Multi-stream/External продублированы ✅
`ui/index.html:390–396` — блок из трёх пунктов вставлен дважды подряд с сепаратором. Меню показывает 6 пунктов вместо 3. Хуже: `showContextMenu` дизейблит через `querySelector` (первое совпадение) → для YouTube-каналов первая копия disabled, **вторая остаётся кликабельной** и запускает недоступное действие. **Fix:** удалить дубликат из HTML.

### 6. Enter/Space глобально перехвачены → клавиатурная навигация сломана (a11y) 📖
`ui/js/keyboard.js:171`: `if (e.key === sc.watch || e.key === 'Enter') { e.preventDefault(); TwitchX.doWatch(); }` — исключены только INPUT/SELECT/TEXTAREA, но не кнопки. Tab на любую кнопку (Browse, Settings, карточка) → Enter активирует не кнопку, а doWatch выбранного канала. Space аналогично.
**Fix:** ранний выход, если `document.activeElement` — button/[role=button]/a, или вешать Enter/Space-активацию только когда фокус на грид-области.

### 7. Кнопки Logout / «Import follows» — нестилизованные UA-кнопки ✅
`.logout-link` (`ui/css/components/settings.css:338`) задаёт только цвет/курсор, а элементы — `<button>` без сброса фона/рамки. Итог: серые системные кнопки; в light-теме текст `rgb(107,107,113)` на фоне `rgb(107,107,107)` — **контраст ≈1:1, текст невидим**. Глобального `button {}`-сброса в проекте нет.
**Fix:** добавить `background:none; border:none; padding:0; font:inherit` в `.logout-link` (или глобальный сброс кнопок в reset.css — тогда проверить все кнопки).

### 8. Light-тема: нечитаемые оверлеи на фиксированно-тёмных подложках ✅
- `.uptime-badge` (`ui/css/components/stream-card.css:144`): `background: rgba(0,0,0,.74)` + `color: var(--text-secondary)` → в light `#5A5A5F` на чёрном ≈2.4:1.
- `.ms-audio-state` (`ui/css/components/multistream.css`): `--text-secondary` поверх видео.
**Fix:** на фиксированно-тёмных оверлеях использовать `--text-inverse`/фиксированный светлый цвет (как уже сделано у `.ms-channel-name`). Прогнать поиск по `rgba(0,0,0,0.5+)`-фонам с var-текстом.

### 9. VOD seek-бар не убирается после закрытия плеера 📖
`hidePlayerView` и `showPlayerView` (`ui/js/player.js`) не вызывают `stopVodSeekBar()` — останавливаются все мониторы, кроме него. Сценарий: посмотрел VOD → закрыл → seek-бар остаётся видимым над player-bar в гриде и на следующем live-стриме; интервал 250ms продолжает тикать. **Fix:** добавить `stopVodSeekBar()` в оба места.

### 10. Удаление последнего фаворита оставляет мёртвые строки в сайдбаре ✅📖
`renderSidebar` (`ui/js/sidebar.js:919`): при `favorites.length === 0` — ранний return без очистки `#channel-list`; старые секции с каналами и счётчиком «N live now» остаются на экране. **Fix:** перед return делать `list.replaceChildren()`.

### 11. Chat export скорее всего no-op в WKWebView ❓📖
`exportChatLog` (`ui/js/chat.js:311`) качает blob через `<a download>`. pywebview 5.4: `webview.settings['ALLOW_DOWNLOADS']` по умолчанию False и в проекте нигде не включён → WKWebView игнорирует клик, файл не сохраняется, а статус врёт «Chat log saved: …». **Проверить на .app**; fix — сохранять через Python-метод (`save_file` + NSSavePanel) либо включить ALLOW_DOWNLOADS.

---

## P2 — средние

12. **Broken-image глифы на аватарках** ✅ — `render.js:249` ставит `avatar.src = ''` (пустой src → onerror/глиф в WebKit; комментарий на 60 строк выше в этом же файле сам предупреждает об этом для thumb-img). Плюс `#user-avatar` в `index.html:63` с `src=""` — глиф в профиле до прихода аватарки. Fix: не ставить src, пока нет данных; placeholder-фон через `.is-empty`.
13. **Тултип сайдбара залипает** ✅ — при ре-рендере списка (поллинг каждые 30–120 c) hover-элемент уничтожается, `mouseleave` не приходит, тултип висит поверх UI до следующего hover. Fix: прятать `#sidebar-tooltip` в начале `renderSidebar`/`renderRail`.
14. **Тосты перекрывают тулбар** ✅ — `#toast-container { top:0; right:0 }` ложится на кнопки density/refresh и (полупрозрачные) выглядят как каша поверх контролов; клики по тулбару блокируются на 4 с. Fix: сдвинуть под тулбар (`top: 56px`) или в правый нижний угол; поднять непрозрачность фона.
15. **Skip-link торчит на ~1px сверху слева на каждом экране** ✅ — `transform: translateY(-120%)` недопрячет из-за `top:8px` (`reset.css:44`). Оранжевая полоска видна во всех скриншотах. Fix: `top:-100px` в покое + `top:8px` на :focus, или `visibility:hidden` вне фокуса.
16. **Секции сайдбара самораскрываются** 📖 — `expandSidebarSectionForLogin` вызывается из каждого `renderSidebar` (`sidebar.js:905`): пока канал выбран, его секцию невозможно держать свёрнутой — каждый поллинг раскрывает обратно. Fix: вызывать только из `selectChannel` (там уже есть вызов), из renderSidebar убрать.
17. **Pin badge не обновляется** 📖 — in-place diff в `renderGrid` не трогает пин-бейдж на карточке; после «Pin to top» порядок меняется, а иконка появляется только после полной перестройки грида. Fix: обновлять бейдж в diff-ветке.
18. **Channel view: вкладка «Live Now» пустая для живого канала** ✅ — при `is_live && watch_supported` empty-state скрывается (`callbacks.js:1234`), но карточку/превью стрима никто не рендерит → пустая зона под табами. Fix: рендерить карточку live-стрима или не скрывать empty-state (у него уже есть текст «Use Watch Now»).
19. **`switchChannelTab` мёртвый, `channelTabs.active` не обновляется** 📖 — init.js вешает свой обработчик на `.channel-tab` без установки `state.channelTabs.active`; экспортированный `switchChannelTab` не используется. После обновления профиля активная вкладка сбрасывается на Live. Fix: использовать `switchChannelTab` в init.js.
20. **Notif-бейдж (красный счётчик у Favorites)** 📖 — не кликается, нельзя сбросить, живёт ровно до следующего поллинга; `_clearNotifBadges` не вызывается никем. Fix: сбрасывать по клику/по просмотру секции, либо убрать счётчик.
21. **CSS-дубли: 89 селекторов определены в 2+ файлах** 📖 — legacy `layout.css` / `views.css` / `player.css` конфликтуют с новыми `components/*` (`#platform-tabs` padding/border задан в обоих, `.filter-row`/`.mod-row` разные gap, `#record-dot` разнесён на два файла, `#toolbar-platform-chips`, `#player-header`…). Порядок загрузки спасает местами случайно (components позже layout, но views/player позже components). Единый владелец на селектор нужен до любых дальнейших правок дизайна.

---

## P3 — полировка

- Метатекст секции «Online … combined viewers» обрезается при штатной ширине сайдбара 244px — сократить формат («4 live • 109k»).
- Settings-модал: высота контента 644px > 558px видимых, скролл только внутри панели и колесом в WebKit ловится не всегда; кнопка Save может уходить из виду на маленьких окнах — прижать футер с Save к низу модалки (sticky).
- Mini mode: `.segmented` platform-табы растягиваются на всю ширину окна — выглядит разболтано; ограничить max-width.
- `player.js:519` — голый `setStatus(...)` без `TwitchX.` (работает только благодаря инлайн-мержу; в раздельной загрузке — ReferenceError).
- Тосты в light-теме на полупрозрачном фоне поверх пёстрого контента читаются слабо — поднять alpha `--toast-bg-*`.
- ❓ Проверить на .app: переживает ли `localStorage` перезапуск (pywebview `html=` может грузиться с null-origin в WKWebView). Если нет — тема/акцент/пины/collapsed-состояние тихо сбрасываются при каждом запуске, и их надо переносить в Python-конфиг.

---

## План исправления (фазы — по одной на сессию)

### Phase 1 — API bridge (P0-1) ✅ выполнено (2026-08-20)
Перевести Python→JS конфиг на push-модель: Python вызывает `window.onConfigLoaded(config)` при `loaded` и после каждого `save_settings`; выпилить все синхронные чтения `get_config`/`get_full_config_for_settings`/`get_watch_statistics`/`get_version` из JS (7 мест из таблицы выше), статистику отдавать через `window.onWatchStatistics(...)`.
**Acceptance:** после рестарта залогиненный профиль виден сразу; Settings открывается с реальными значениями; повторный Save ничего не сбрасывает; Watch Statistics рендерится; футер показывает реальную версию. Тест: `capture_eval_js.assert_any('onConfigLoaded')`.

**Реализовано:** `TwitchXApi.push_config()` / `request_config()` шлют снапшот (`get_config` + `settings` + `version`) в `window.onConfigLoaded`; пуш при `loaded` (`app.py`), после `save_settings` и после каждого login/logout (`ui/api/auth.py`). Статистика — `request_watch_statistics()` → `window.onWatchStatistics`. JS читает кэш из `TwitchX.state.config` / `state.fullConfig` / `state.version` (`applyConfigSnapshot` в `api-bridge.js`); синхронных геттеров в `ui/js/` больше нет — покрыто тестом `test_js_never_reads_config_synchronously` в `tests/test_config_push.py`.

### Phase 2 — Критические состояния UI (P0-2, P0-3, P1-5) ✅ выполнено (2026-08-20)
`renderEmptyState` + `.visible`; CSS-фикс multistream add-form; дедуп контекстного меню.
**Acceptance:** чистый конфиг → виден Welcome-экран с кнопкой Login; «Add Stream» открывает форму, grid не исчезает, Esc возвращает пустое состояние; в контекстном меню каждый пункт один раз, disable работает.

**Реализовано:** `#empty-state` теперь раскрывается и по `.view-active` (контракт `#view-stack`), и по `.visible`; `renderEmptyState` ставит оба класса, парный `TwitchX.hideEmptyState()` снимает их — все места скрытия (`render.js`, `channel.js`, `callbacks.js`) переведены на него. Правило коллапса пустых слотов в `views.css` исключает `:not(.ms-add-form-open)`; закрытие add-формы сведено к `TwitchX.closeMultiAddForm(idx, {restoreFocus})` (4 вызова в `init.js`), Esc в форме гасит всплытие, чтобы не закрывать всю мультистрим-вью. Дубликат блока Watch/Multi-stream/External удалён из `ui/index.html`.
**Проверено в браузерном харнессе** (merged-бандл + стаб `pywebview.api`): Welcome/«No favorites yet»/«All quiet» рендерятся с `opacity: 1`; при одном играющем слоте открытая add-форма видна, пустые слоты скрыты; Esc закрывает форму, чистит инпут, возвращает фокус на `+`, мультистрим остаётся открытым; контекстное меню — 8 пунктов без повторов, три YouTube-действия disabled. Тесты: `tests/test_ui_states.py` (7).

### Phase 3 — Идентичность фаворитов и сайдбар (P0-4, P1-10, P2-16, P2-20) ✅ выполнено (2026-08-20)
Убрать фантомные twitch-дубликаты; очистка списка при 0 фаворитов; авто-раскрытие секций только в selectChannel; поведение notif-бейджа.
**Acceptance:** kick-фаворит появляется в сайдбаре ровно один раз; удаление последнего фаворита очищает список; свёрнутая секция остаётся свёрнутой сквозь поллинги.

**Реализовано:** `getFavoriteEntries()` (`state.js`) отбрасывает legacy-логины, уже покрытые meta на любой платформе — сравнение по `login` без `toLowerCase()` (YouTube ID case-sensitive). `renderSidebar` при нуле записей делает `list.replaceChildren()` и обнуляет счётчик; проверка ведётся по записям, а не по плоскому массиву. Вызов `expandSidebarSectionForLogin` из `renderSidebar` убран — раскрытие осталось только в `selectChannel`. Notif-бейдж: `_notifBadgeLogins` копится между поллингами (первый апдейт только сеет baseline, а не помечает весь лайв новым), бейдж стал `<button>` с кликом → `_clearNotifBadges()`, `TwitchX.acknowledgeNotifBadge(key)` гасит отметку при выборе канала.
**Проверено в браузерном харнессе:** kick-фаворит + twitch-фаворит дают ровно 2 строки (`kick:trainwreckstv`, `twitch:shroud`), фантома `twitch:trainwreckstv` нет, счётчик Favorites = 2; свёрнутая Online остаётся свёрнутой после поллинга при выбранном канале; badge: baseline пуст → новый лайв даёт «1» → переживает следующий поллинг → гаснет по выбору канала и по клику; удаление последнего фаворита очищает `#channel-list` (0 строк) и показывает Welcome. Тесты: `tests/test_ui_favorites.py` (6), всего 675 passed.

### Phase 4 — Клавиатура и a11y (P1-6, P1-7, P2-15) ✅ выполнено (2026-08-20)
Guard на Enter/Space; стилизация `.logout-link`; skip-link.
**Acceptance:** Tab+Enter активирует именно сфокусированную кнопку; Logout/Import читаемы в обеих темах; полоска сверху исчезла.

**Реализовано:** в `keyboard.js` добавлен `focusOwnsActivationKeys()` — Enter/Space не перехватываются глобально, если фокус на `button`/`a[href]`/`summary`/`[role=button|menuitem|tab|option]`/`contenteditable`. Исключение — «канальные» цели (`.stream-card`, `.channel-item`, `.rail-avatar`): у них свой обработчик выбирает канал, а глобальный watch-шорткат достраивает то же намерение, что и двойной клик. Гард стоит после проверки модификаторов и до всех однокнопочных шорткатов, поэтому буквенные хоткеи (`r`, `f`, `m`…) продолжают работать при фокусе на кнопке. `.logout-link` получил полноценный сброс UA-кнопки (`background:none; border:none; padding:0; font:inherit`), цвет поднят до `--text-secondary` (6.86:1 на светлой панели, 7.34:1 на тёмной), добавлены `:hover` и `:focus-visible`. Skip-link больше не прячется трансформом: `top:-100px` в покое, `top:var(--space-8)` на `:focus`, анимация по `top`.
**Проверено в браузерном харнессе:** Enter/Space на `#settings-btn` — `defaultPrevented:false`, `watch_platform` не вызывается (нативная активация кнопки сохраняется); `r` при том же фокусе по-прежнему шлёт `refresh`; Enter на карточке грида и Space на строке сайдбара по-прежнему дают select+watch; Enter на пункте контекстного меню не перехвачен. Skip-link: в покое `bottom = -29px` (полностью за экраном, `transform:none`), при фокусе `top: 8px`; на скриншотах оранжевой полоски сверху нет. `.logout-link` в light — `rgb(90,90,95)` на светлой панели, в dark — `rgb(174,174,178)`, фон прозрачный, рамки нет. Тесты: `tests/test_ui_a11y.py` (5), всего 680 passed.

### Phase 5 — Контраст и светлая тема (P1-8, P3-toast) ✅ выполнено (2026-08-20)
Uptime-badge, ms-audio-state, alpha тостов; ручной прогон всех вью в light.
**Acceptance:** все тексты на тёмных оверлеях ≥4.5:1 в обеих темах.

**Реализовано:** новый токен `--text-on-overlay: rgba(255,255,255,0.88)` (одинаков в обеих темах) для текста на подложках, которые остаются тёмными независимо от темы. Переведены: `.uptime-badge` (плюс рамка `--border-subtle` → фиксированная `rgba(255,255,255,0.16)`, иначе в light она невидима), `.ms-audio-state` (фон `--border-default` → фиксированный `rgba(0,0,0,0.72)`), `#seek-tooltip` (фон `--bg-tooltip-dark` тёмный в обеих темах, текст был `--text-primary` ≈1.1:1 в light — не было в аудите, нашлось сплошным сканом). Кнопки слота мультистрима: `--bg-dark-50` → `rgba(0,0,0,0.62)`, иначе глиф на белом кадре давал ~4:1. Тосты получили непрозрачную подложку `--toast-surface` (dark `rgba(20,20,24,0.94)`, light `rgba(255,255,255,0.95)`), цветной тинт лёг сверху вторым слоем `linear-gradient(tint,tint)`, alpha тинтов поднята (dark 0.14→0.20, light 0.10→0.16); иконочные токены подкручены до ≥4.6:1 на тинте: light success `#1E7232`, error `#B72727`, warn `#8F5500`, dark error `#FF7068`.
**Проверено:** `tests/test_overlay_contrast.py` (33 теста) считает композит с учётом альфы для худшего фона (белый и чёрный кадр) — все фиксированно-тёмные поверхности и все 4 типа тостов ≥4.5:1 в обеих темах; отдельный сплошной скан всех CSS запрещает `color: var(--text-primary|secondary|muted)` на фонах `rgba(0,0,0,≥0.5)` / `--bg-dark-*` / `--bg-tooltip-dark`. Визуально в харнессе: light-тема — бейдж аптайма «3h 0m» читается на светлом превью, чип «Muted» поверх белого кадра тёмный со светлым текстом, четыре тоста непрозрачны и читаемы; dark-тема — то же без регрессий. Всего 713 passed.

### Phase 6 — Плеер и мелкие вью (P1-9, P1-11, P2-12, P2-13, P2-14, P2-17, P2-18, P2-19) ✅ выполнено (2026-08-20)
stopVodSeekBar в hide/showPlayerView; chat export через Python; пустые src аватарок; тултип при ре-рендере; позиция тостов; pin badge; Live Now вкладка; switchChannelTab.
**Acceptance:** VOD→close→live без seek-бара; export реально пишет файл; нет broken-image глифов на свежем гриде.

**Реализовано:**
- **P1-9** `stopVodSeekBar()` добавлен в `showPlayerView` (блок остановки мониторов) и в `hidePlayerView`.
- **P1-11** экспорт чата ушёл в Python: `TwitchXApi.save_chat_log(filename, content)` пишет в `~/Downloads` (фолбэк — `CONFIG_DIR`), санитизирует имя (`Path.name`, запрещённые символы, принудительный `.txt`/`.json`), не перезаписывает существующий файл (`log-1.txt`) и отвечает в `window.onChatLogSaved({ok, path, name})`. Из JS убраны `Blob`/`createObjectURL`/`<a download>`; статус и тост теперь отражают реальный результат.
- **P2-12** пустой `src` больше нигде не выставляется: карточки грида ставят `src` только при наличии аватарки (иначе `.is-empty`), из `index.html` убраны `src=""` у `#user-avatar` и `#channel-avatar`, `showUserProfile` и `onAvatar` синхронизируют `.is-empty`; для профильной аватарки добавлен плейсхолдер-стиль.
- **P2-13** `hideSidebarTooltip()` вызывается в начале `renderSidebar` и `renderRail`.
- **P2-14** `#toast-container` опущен под тулбар (`top: 46px`).
- **P2-17** `_syncPinBadge(card, s)` вызывается в diff-ветке `renderGrid` — бейдж появляется и исчезает без полной перестройки.
- **P2-18** новый `renderChannelLivePanel(profile)` рисует карточку живого стрима (превью/фолбэк, заголовок, платформа, «игра · зрители · аптайм», кнопки Watch Now / Open) вместо пустой зоны; офлайн — карточка удаляется, empty-state остаётся.
- **P2-19** обработчик `.channel-tab` в `init.js` заменён на `TwitchX.switchChannelTab(btn, tab)`, который пишет `state.channelTabs.active`.

**Проверено в браузерном харнессе:** на свежем гриде 0 картинок с пустым `src` (аватарки — `card-avatar is-empty` без атрибута); пин через diff-путь даёт бейдж и переупорядочивание, снятие — убирает; тултип гаснет и при обычном ре-рендере, и в rail-режиме; тост-контейнер `top: 46px`, геометрически не пересекается с тулбаром (скриншот подтверждает); VOD → таймер `_seekBarTimer` активен и бар виден, после закрытия — таймер снят, бар `display:none`, следующий live-стрим его не воскрешает; профиль живого канала даёт `#channel-live-card` с «Watch Now»/«Open», офлайн — empty-state «Channel is offline»; клики по вкладкам ставят `channelTabs.active` в `vods`/`clips`; `exportChatLog` зовёт `save_chat_log` с именем и содержимым, `<a download>` в DOM нет, колбэк даёт «Chat log saved: …» / «Chat export failed».
**Тесты:** `tests/test_chat_export.py` (5, включая попытку выхода за директорию `../../etc/passwd` и фолбэк без `~/Downloads`) и `tests/test_ui_player_views.py` (7). Всего 725 passed.

### Phase 7 — Консолидация CSS (P2-21) ✅ выполнено (2026-08-20)
По списку из аудита свести каждый селектор к одному файлу-владельцу: layout.css — только каркас/drag-регионы, views.css/player.css распилить в components/*. Инструмент проверки — скрипт подсчёта дублей (89 → 0 конфликтных, a11y-media-блоки в reset.css легитимны).
**Acceptance:** скрипт дублей чистый; визуальный прогон всех вью без регрессий в обеих темах.

**Инструмент:** `tools/css_ownership.py` (exit code = число нарушений). Считает только top-level правила: блоки `@media`/`@supports` (a11y-оверрайды в `reset.css`) исключены, плюс три явно задекларированных cross-cutting слоя с маркером `/* css-layer: … */` — `theme-tokens` (`:root` в tokens + themes), `drag-regions` (`-webkit-app-region` в layout.css), `text-selection` (allowlist `user-select` в reset.css). Стартовое состояние по этой методике: **25 селекторов в 2+ файлах, 7 с расходящимися значениями**; итог — **0**.

**Разобранные конфликты** (в скобках — что победило раньше по порядку загрузки): `.chat-header-btn:hover` (player.css гасил подсветку, вернув `--text-secondary` → теперь слой ховеров даёт `--text-primary` + фон), `.login-btn:active` (buttons.css `scale(0.98)` → слой press-состояний `scale(var(--scale-press))`), `.mod-row`/`.filter-row` (forms.css + player.css → один владелец forms.css с эффективными значениями), `.setting-label` / `.setting-group input|select(:focus)` (settings.css дублировал forms.css → значения settings.css вплавлены в forms.css), `#record-dot` (анимация из player.css → player-bar.css), `#sidebar.collapsed-sidebar #platform-tabs` (`!important` из layout.css убран), `#browse-nav-btn` (база переехала из multistream.css в sidebar.css), `.browse-empty*` (empty-state.css → browse.css), `.channel-item.dragging` (multistream.css → sidebar.css), press-дубли `:active` в search-toolbar/player-bar/forms → только micro-interactions.css.

**Структура:** `views.css` и `player.css` удалены. Их правила разъехались по владельцам: multistream (38 правил + мобильный `@media`), channel (10), browse (6), новый `components/player-view.css` (шелл плеера, видео, seek-бар, буфер, stats-оверлей, player-header, fs-автоскрытие), chat.css (панель чата, resize-хэндл, фильтры, юзерлист, мод-панель, экспорт-меню, эмоут-пикер), player-bar.css (запись, `#stream-loader`, `#vod-time-display`). Из `layout.css` вынесены сайдбар (14 правил → sidebar.css) и `#search-area`/`#search-row` (→ search-toolbar.css); остался каркас: `#app`, drag-регионы, `#main`, `#content`, `#view-stack`, тулбар, mini mode.

**Проверка без регрессий:** собран дифф-харнесс — две копии приложения (до/после рефакторинга) в iframe на одном origin, снимок `getComputedStyle` по 63 свойствам для каждого элемента `body` в 10 состояниях (5 вью × 2 темы) и построчный дифф. До правок инструмент давал 0 расхождений на идентичных деревьях (самопроверка). После рефакторинга осталось 5 элементов: два `<select>` настроек получили в `transition` ещё и `background` (forms.css — общий переход), а три чекбокса/радио в настройках перестали наследовать стилизацию текстовых полей из удалённого дубля `settings.css` — сравнение скриншотов «до/после» показывает идентичный рендер (их внешний вид задаёт `accent-color` из forms.css). Прогон всех вью в обеих темах — без визуальных регрессий.
**Тесты:** `tests/test_css_ownership.py` (7: нулевой дифф владельцев, отсутствие legacy-файлов, все `<link>` существуют, layout.css без сайдбарных селекторов, маркеры трёх слоёв). Всего 732 passed.

## Ревью реализации (2026-08-20)

Сквозной разбор всех изменений фаз 1–7 (декларативный дифф CSS, статический разбор JS/Python, runtime-прогон всех вью в харнессе). Найдено и исправлено:

| # | Проблема | Где | Фикс |
|---|---|---|---|
| R1 | Маркер `/* css-layer: … */` в чекере владельцев был «липким»: всё после него в файле молча получало исключение — реальные дубли могли пройти | `tools/css_ownership.py` | Маркер покрывает ровно одно следующее правило; добавлен тест `test_layer_marker_covers_only_the_next_rule`. Сразу вскрыл спрятанный дубль `#toolbar-platform-chips` (layout.css + search-toolbar.css) — сведён в search-toolbar.css |
| R2 | Тултип сайдбара всё ещё мог всплыть: 180-мс таймер ховера срабатывал уже после ре-рендера, на оторванном узле (нулевой rect → тултип в левом верхнем углу без шанса на `mouseleave`) | `ui/js/sidebar.js` | Гард `if (!item.isConnected) return;` в `showTooltip`, локальный дубль `hideTooltip` заменён на общий `hideSidebarTooltip` |
| R3 | `refresh_interval` вне трёх пресетов (`30/60/120`) оставлял `<select>` пустым, и следующий Save записывал 60 — тихая потеря настройки | `ui/js/settings.js` | `_setIntervalValue()` подставляет недостающее значение отдельной опцией (`data-custom`), Save возвращает исходные 90 |
| R4 | Сохранённое качество (`settings.quality`, которое Python пишет при каждом watch) никогда не возвращалось в `#quality-select` — каждый запуск начинался с «best», а первый же watch перезаписывал конфиг | `ui/js/api-bridge.js` | `applyConfigSnapshot` восстанавливает качество, если такая опция есть в списке |
| R5 | `CONFIG_DIR` связывался на импорте: каждый `TwitchXApi()` в тестах открывал **реальную** `~/.config/twitchx/watch_stats.db`, а фолбэк экспорта чата писал туда же файлы | `ui/api/__init__.py`, `ui/api/chat.py` | Путь резолвится через `core.storage` в момент вызова; тест `test_api_keeps_all_state_inside_the_configured_dir` фиксирует изоляцию |

Проверено после фиксов: 734 passed, `ruff` (check + format) чисто, `pyright` 0 errors, чекер владельцев CSS — 0, дифф computed-стилей до/после фазы 7 не изменился (те же 5 заведомо безобидных элементов), runtime-прогон всех вью — 0 ошибок в консоли.

Порядок: 1 → 2 → 3 (эти три закрывают всё критическое) → 4 → 5 → 6 → 7. Фазы 4–6 независимы, можно параллельно. Фазу 7 делать последней — она перетряхивает CSS, на который опираются проверки остальных фаз.
