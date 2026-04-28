# Фаза 3: Модуляризация фронтенда (ui/index.html)

> **Дата:** 2026-04-28  
> **Статус:** План  
> **Зависит от:** Не блокируется другими фазами (можно делать параллельно)  
> **Обзорный документ:** [architecture-refactoring.md](./2026-04-28-architecture-refactoring.md)

---

## Цель

Разделить `ui/index.html` (5,414 строк — HTML, CSS и JS в одном файле) на модульную структуру:
- Выделить CSS в отдельные файлы (токены, лейаут, компоненты, вьюхи)
- Разбить JS на модули по зонам ответственности (~15 файлов, каждый ≤ 400 строк)
- Убрать `var` в пользу `const`/`let`
- Выделить повторяющийся HTML (мультистрим-слоты) в шаблоны

---

## Текущее состояние

### Структура index.html (5414 строк)

```
  7-1830   CSS  (~1,824 строки) — все стили в одном <style>
1832-2355   HTML (~524 строки) — вся DOM-структура
2356-5412   JS   (~3,057 строк) — весь JavaScript в одном <script>
5413-5414   </body></html>
```

### Проблемы фронтенда

**Проблема 1: Монолитность.** Три языка в одном файле. Невозможно работать с одним аспектом, не прокручивая тысячи строк.

**Проблема 2: Глобальная область видимости.** ~80 функций и ~20 переменных в глобальном `window`. Риск коллизий имён. Нет инкапсуляции.

```javascript
// Всё в глобальном scope
var state = { ... };           // строка 2395
var multiState = { ... };      // строка 2434
var api = null;                // строка 2443
var ctxChannel = null;         // строка 2444

function renderGrid() { ... }  // строка 4398
function showBrowseView() { ... }  // строка 3603
function handleKeydown(e) { ... }  // строка 5305
// ... ещё ~75 функций
```

**Проблема 3: `var` вместо `const`/`let`.** Почти все переменные объявлены через `var`, что даёт function scope и hoisting — неожиданное поведение при отладке.

**Проблема 4: Дублирование HTML.** Четыре `.ms-slot` элемента (строки 1979–2117) — идентичная структура, скопированная 4 раза. При изменении слота нужно править 4 места.

**Проблема 5: 30+ колбэков `window.on*`.** Python вызывает JS через `window.evaluate_js('window.onStreamsUpdate(data)')`. Все 30 колбэков в глобальном scope.

**Проблема 6: 375-строчный `DOMContentLoaded`.** Один обработчик привязывает ~50-70 event listener'ов. Тяжело найти конкретный биндинг.

**Проблема 7: Inline `onclick`.** Часть обработчиков задана через HTML-атрибуты (`onclick="showBrowseView()"`), часть через `addEventListener`. Два разных подхода вперемешку.

---

## Целевое состояние

### Новая структура: `ui/`

```
ui/
├── index.html              (~60 строк)  — shell: подключает CSS и JS модули
├── css/
│   ├── tokens.css          (~200 строк) — CSS custom properties (:root)
│   ├── reset.css           (~30 строк)  — сброс стилей
│   ├── layout.css          (~300 строк) — #app, #main, #sidebar, #content
│   ├── components.css      (~400 строк) — кнопки, карточки, модалки, инпуты
│   ├── views.css           (~400 строк) — плеер, мультистрим, брауз, настройки, профиль
│   └── player.css          (~200 строк) — player-bar, chat-panel, resize
├── js/
│   ├── state.js            (~80 строк)  — state, multiState (единственные глобалы)
│   ├── api-bridge.js       (~80 строк)  — callApi(), pywebviewready, retry
│   ├── callbacks.js        (~400 строк) — window.on* обработчики от Python
│   ├── render.js           (~350 строк) — renderGrid, renderSidebar, createStreamCard
│   ├── player.js           (~200 строк) — showPlayerView, volume, PiP, fullscreen
│   ├── multistream.js      (~250 строк) — openMultistreamView, slot management
│   ├── browse.js           (~200 строк) — showBrowseView, loadBrowseCategories
│   ├── channel.js          (~250 строк) — showChannelView, tabs, media, profile
│   ├── chat.js             (~280 строк) — submitChatMessage, renderChatEmotes, callbacks
│   ├── settings.js         (~200 строк) — openSettings, saveSettings, hotkeys UI
│   ├── context-menu.js     (~80 строк)  — showContextMenu, showSidebarContextMenu
│   ├── keyboard.js         (~100 строк) — handleKeydown, formatKeyName, rebind
│   ├── sidebar.js          (~150 строк) — renderSidebar, getSidebarGroups, sections
│   └── utils.js            (~80 строк)  — truncate, formatViewers, formatUptime
└── templates/
    └── slot.html           (~40 строк)  — шаблон .ms-slot (используется 4 раза)
```

### Целевой index.html (shell)

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TwitchX</title>
    <!-- CSS -->
    <link rel="stylesheet" href="css/tokens.css">
    <link rel="stylesheet" href="css/reset.css">
    <link rel="stylesheet" href="css/layout.css">
    <link rel="stylesheet" href="css/components.css">
    <link rel="stylesheet" href="css/views.css">
    <link rel="stylesheet" href="css/player.css">
</head>
<body>
    <div id="app">
        <div id="main">
            <!-- Сайдбар -->
            <div id="sidebar">
                <!-- ... вся структура ... -->
            </div>
            <!-- Контент -->
            <div id="content">
                <!-- ... вся структура ... -->
            </div>
        </div>
    </div>

    <!-- Оверлеи (вне потока) -->
    <div id="context-menu" class="hidden">...</div>
    <div id="settings-overlay" class="hidden">...</div>

    <!-- JS модули (в порядке зависимостей: сначала состояние, потом утилиты, потом модули) -->
    <script src="js/state.js"></script>
    <script src="js/utils.js"></script>
    <script src="js/api-bridge.js"></script>
    <script src="js/callbacks.js"></script>
    <script src="js/render.js"></script>
    <script src="js/sidebar.js"></script>
    <script src="js/player.js"></script>
    <script src="js/multistream.js"></script>
    <script src="js/browse.js"></script>
    <script src="js/channel.js"></script>
    <script src="js/chat.js"></script>
    <script src="js/settings.js"></script>
    <script src="js/context-menu.js"></script>
    <script src="js/keyboard.js"></script>
    <script src="js/init.js"></script>  <!-- DOMContentLoaded + биндинги -->
</body>
</html>
```

**Важно:** Поскольку pywebview загружает HTML из локальной файловой системы, `<link>` и `<script src="...">` с относительными путями работают. Пути разрешаются относительно `ui/index.html`.

### Стратегия модульности: IIFE (без бандлера)

Поскольку нет шага сборки (нет webpack/vite), используем **IIFE** (Immediately Invoked Function Expression) для инкапсуляции и экспорта в глобальный неймспейс `TwitchX`:

```javascript
// js/player.js
const TwitchX = window.TwitchX || {};

(function (TX) {
    // Приватные переменные (не в глобальном scope)
    let currentQuality = 'best';

    // Публичные функции (экспортируются в TX)
    TX.showPlayerView = function () {
        // ...
    };

    TX.hidePlayerView = function () {
        // ...
    };

    TX.getActiveVideo = function () {
        return document.querySelector('#stream-video');
    };

    // Приватные хелперы (не экспортируются)
    function _setVideoSource(url) {
        const video = document.getElementById('stream-video');
        // ...
    }
})(TwitchX);
```

**Неймспейс `TwitchX`** заменяет разрозненные глобалы:
- `state` → `TwitchX.state`
- `multiState` → `TwitchX.multiState`
- `renderGrid()` → `TwitchX.renderGrid()`
- `showBrowseView()` → `TwitchX.showBrowseView()`

### Python-колбэки — остаются `window.on*`, но становятся тонкими

```javascript
// js/callbacks.js — все window.on* обработчики
window.onStreamsUpdate = function (data) {
    TwitchX.state.streams = data.streams;
    TwitchX.state.liveSet = new Set(data.live_streams);
    TwitchX.state.totalViewers = data.total_viewers;
    TwitchX.renderGrid();
    TwitchX.renderSidebar();
    TwitchX.setStatus(data.updated_at, '');
};

window.onSearchResults = function (results) {
    TwitchX.state.searchResults = results;
    TwitchX._renderSearchDropdown();
};

// ... ещё ~25 колбэков, все делегируют в TwitchX.*
```

Сами `window.on*` остаются глобальными (это требование pywebview — `window.evaluate_js()` вызывает глобальные функции), но они становятся **тонкими прокси**, делегирующими в модули.

### `state` и `multiState` — централизованное состояние

```javascript
// js/state.js — единственный источник правды
const TwitchX = window.TwitchX || {};

// ======================================================================
// Application state — the single source of truth.
// Mutable. Read by render functions, written by callbacks.
// ======================================================================
TwitchX.state = {
    streams: [],
    favorites: [],
    favoritesMeta: {},        // { login: { platform, display_name } }
    liveSet: new Set(),
    selectedChannel: null,
    watchingChannel: null,
    config: {},
    sortKey: 'viewers',
    filterText: '',
    avatars: {},              // { login: dataURI }
    thumbnails: {},           // { login: dataURI }
    searchResults: [],
    currentUser: null,
    channelTabs: {},          // per-channel media state
    shortcuts: {},
    pipEnabled: false,
    sidebarSections: { online: true, offline: false },
};

TwitchX.multiState = {
    slots: [null, null, null, null],
    audioFocus: -1,
    chatSlot: -1,
    open: false,
    chatVisible: false,
};
```

### Обработка событий: `js/init.js`

Весь `DOMContentLoaded` (сейчас 375 строк) переносится в `init.js` и разбивается на секции:

```javascript
// js/init.js
(function (TX) {
    document.addEventListener('DOMContentLoaded', function () {
        TX._bindSidebarEvents();
        TX._bindToolbarEvents();
        TX._bindPlayerEvents();
        TX._bindBrowseEvents();
        TX._bindChannelEvents();
        TX._bindChatEvents();
        TX._bindSettingsEvents();
        TX._bindContextMenuEvents();
        TX._bindKeyboardEvents();
        TX._bindGlobalEvents();
    });

    TX._bindSidebarEvents = function () {
        document.getElementById('login-btn')?.addEventListener('click', TX.api.login);
        document.getElementById('search-input')?.addEventListener('input', TX._onSearchInput);
        // ...
    };

    // ... остальные _bind* функции
})(TwitchX);
```

### Дублирование HTML: шаблон слота

Вместо 4× идентичного HTML в `index.html`:

```javascript
// js/multistream.js — создание слотов динамически
TX._createMultiSlot = function (idx) {
    const slot = document.createElement('div');
    slot.className = 'ms-slot';
    slot.setAttribute('data-slot-idx', idx);
    slot.tabIndex = -1;
    slot.innerHTML = `
        <div class="ms-slot-overlay">
            <span class="ms-slot-placeholder">Slot ${idx + 1}</span>
            <span class="ms-slot-hint">Drop a stream here</span>
            <button class="ms-slot-close hidden" onclick="TwitchX.removeMultiSlot(${idx})">✕</button>
        </div>
        <video class="ms-slot-video" muted playsinline></video>
        <div class="ms-slot-info hidden">
            <span class="ms-slot-channel"></span>
            <span class="ms-slot-title"></span>
        </div>
    `;
    return slot;
};

// В index.html — только контейнер:
// <div id="multistream-grid"></div>
```

**НО:** Учитывая правило AGENTS.md — "All dynamic content uses `document.createElement()` + `textContent` — no `innerHTML` with user data" — для статического шаблона слота `innerHTML` допустим, т.к. там нет пользовательских данных. Но для консистентности можно использовать `createElement`.

---

## Список действий

### Шаг 1: Подготовка — разбить CSS (без изменения поведения)

- [ ] Создать директорию `ui/css/`
- [ ] **Вырезать** CSS из `<style>` в `index.html` → разнести по файлам:
  - [ ] `css/tokens.css` — всё из `:root { ... }` (CSS custom properties)
  - [ ] `css/reset.css` — `*`, `body`, базовые сбросы
  - [ ] `css/layout.css` — `#app`, `#main`, `#sidebar`, `#content`, flex/grid контейнеры
  - [ ] `css/components.css` — кнопки, инпуты, карточки, скроллбары, тултипы
  - [ ] `css/views.css` — `#player-view`, `#browse-view`, `#channel-view`, `#multistream-view`, `#settings-overlay`, `#context-menu`
  - [ ] `css/player.css` — `#player-bar`, `#chat-panel`, `#chat-resize-handle`, `#live-dot`
- [ ] Заменить `<style>...</style>` на `<link rel="stylesheet" href="...">`
- [ ] Прогнать `make run` — проверить, что стили применяются (визуально идентично)
- [ ] Закоммитить

### Шаг 2: Создать `state.js` и `utils.js`

- [ ] Создать `ui/js/` директорию
- [ ] `js/state.js` — перенести `state`, `multiState`, `msChatAutoScroll`, `chatAutoScroll`, `chatPlatform`, `chatAuthenticated`, `chatReplyTo`, `chatPendingSends`, `chatSendCounter`
- [ ] `js/utils.js` — перенести `truncate()`, `formatViewers()`, `formatUptime()`, `setStatus()`, `formatMediaDate()`, `formatDuration()`, `buildChannelMediaMeta()`
- [ ] Добавить `<script src="js/state.js">` и `<script src="js/utils.js">` в `index.html`
- [ ] Прогнать `make run`
- [ ] Закоммитить

### Шаг 3: Создать `api-bridge.js`

- [ ] Перенести `callApi()`, `pywebviewready` listener, retry-логику
- [ ] Обернуть в IIFE, экспортировать `TX.callApi`, `TX.api`
- [ ] Прогнать `make run`
- [ ] Закоммитить

### Шаг 4: Создать `callbacks.js` (все `window.on*`)

- [ ] Перенести ВСЕ `window.on*` функции:
  - `onStreamsUpdate`, `onSearchResults`, `onLoginComplete`, `onLoginError`, `onLogout`
  - `onImportComplete`, `onImportError`, `onLaunchResult`, `onLaunchProgress`
  - `onStreamReady`, `onPlayerStop`, `onPlayerState`
  - `onMultiSlotReady`, `onChatMessage`, `onChatSendResult`, `onChatStatus`
  - `onTestResult`, `onSettingsSaved`
  - `onKickLoginComplete`, `onKickLoginError`, `onKickNeedsCredentials`, `onKickLogout`, `onKickTestResult`
  - `onYouTubeLoginComplete`, `onYouTubeLoginError`, `onYouTubeNeedsCredentials`, `onYouTubeLogout`, `onYouTubeTestResult`
  - `onYouTubeImportComplete`, `onYouTubeImportError`
  - `onAvatar`, `onThumbnail`, `onStatusUpdate`
  - `onBrowseCategories`, `onBrowseTopStreams`
  - `onChannelProfile`, `onChannelMedia`
- [ ] Каждый колбэк вызывает `TX.*` вместо прямых глобальных вызовов
- [ ] Прогнать `make run`
- [ ] Закоммитить

### Шаг 5: Поочерёдно выделять UI-модули

Для каждого модуля ниже:
- [ ] Вырезать соответствующие функции из `index.html`
- [ ] Обернуть в IIFE `(function(TX) { ... })(TwitchX)`
- [ ] Экспортировать публичные функции в `TX`
- [ ] Обновить вызовы в других модулях (`renderGrid()` → `TX.renderGrid()`)
- [ ] `make run` + закоммитить

**Порядок выделения (от независимых к зависимым):**

- [ ] **Шаг 5.1 — `render.js`**: `renderGrid`, `createStreamCard`, `createOnboardingCard`, `getFilteredSortedStreams`
- [ ] **Шаг 5.2 — `sidebar.js`**: `renderSidebar`, `createSidebarItem`, `createSidebarSection`, `getSidebarGroups`, `applySidebarLayout`, `getSidebarSectionMeta`, `loadSidebarSections`, `saveSidebarSections`, `expandSidebarSectionForLogin`
- [ ] **Шаг 5.3 — `player.js`**: `showPlayerView`, `hidePlayerView`, `getActiveVideo`, `adjustVolume`, `toggleMute`, `cycleStream`, `togglePiP`, `toggleVideoFullscreen`, `toggleChatPanel`, `updateChatInput`
- [ ] **Шаг 5.4 — `browse.js`**: `showBrowseView`, `hideBrowseView`, `browseGoBack`, `setBrowsePlatform`, `loadBrowseCategories`, `_triggerBrowseTopStreams`
- [ ] **Шаг 5.5 — `channel.js`**: `showChannelView`, `hideChannelView`, `switchChannelTab`, `toggleChannelFollow`, `watchChannelStream`, `createChannelMediaCard`, `renderChannelMediaTab`, `ensureChannelTabLoaded`, `resetChannelMediaPanels`, `playChannelMedia`, `openChannelMedia`
- [ ] **Шаг 5.6 — `multistream.js`**: `openMultistreamView`, `closeMultistreamView`, `toggleMsSidebar`, `addMultiSlot`, `removeMultiSlot`, `setAudioFocus`, `switchMultiChat`, `toggleMsChat`, `toggleMsSlotFullscreen`, `_clearMultiSlot`, `_createMultiSlot`
- [ ] **Шаг 5.7 — `chat.js`**: `setChatReply`, `clearChatReply`, `submitChatMessage`, `renderChatEmotes`, `clearChatMessages`, `_getChatMessagesEl`, `_getChatNewMsgEl`
- [ ] **Шаг 5.8 — `settings.js`**: `openSettings`, `openSettingsToTab`, `closeSettings`, `toggleSecret`, `testConnection`, `saveSettings`
- [ ] **Шаг 5.9 — `context-menu.js`**: `showContextMenu`, `showSidebarContextMenu`
- [ ] **Шаг 5.10 — `keyboard.js`**: `handleKeydown`, `formatKeyName`, `startRebind`, `renderHotkeysSettings`

### Шаг 6: Создать `init.js` (замена DOMContentLoaded)

- [ ] Перенести весь `DOMContentLoaded` в `init.js`
- [ ] Разбить на `_bind*()` функции (по одной на зону)
- [ ] Заменить inline `onclick` атрибуты на `addEventListener` в `_bind*()` (где возможно — для статического HTML)
- [ ] Прогнать `make run`
- [ ] Закоммитить

### Шаг 7: Заменить `var` на `const`/`let`

- [ ] Пройтись по всем JS-файлам
- [ ] `var` → `const` (для неизменяемых) или `let` (для мутабельных)
- [ ] Проверить, что нет проблем с hoisting (переменные, используемые до объявления)
- [ ] `make run` + закоммитить

### Шаг 8: Почистить `index.html`

- [ ] Удалить весь JS (теперь в отдельных файлах)
- [ ] Удалить `<style>` (теперь в CSS файлах)
- [ ] Оставить только HTML-структуру + `<link>` + `<script>` теги
- [ ] `index.html` теперь ~300-500 строк (только HTML)
- [ ] `make run` + закоммитить

---

## Затрагиваемые файлы

### Создаются
| Файл | ~Строк |
|------|--------|
| `ui/css/tokens.css` | 200 |
| `ui/css/reset.css` | 30 |
| `ui/css/layout.css` | 300 |
| `ui/css/components.css` | 400 |
| `ui/css/views.css` | 400 |
| `ui/css/player.css` | 200 |
| `ui/js/state.js` | 80 |
| `ui/js/utils.js` | 80 |
| `ui/js/api-bridge.js` | 80 |
| `ui/js/callbacks.js` | 400 |
| `ui/js/render.js` | 350 |
| `ui/js/sidebar.js` | 150 |
| `ui/js/player.js` | 200 |
| `ui/js/multistream.js` | 250 |
| `ui/js/browse.js` | 200 |
| `ui/js/channel.js` | 250 |
| `ui/js/chat.js` | 280 |
| `ui/js/settings.js` | 200 |
| `ui/js/context-menu.js` | 80 |
| `ui/js/keyboard.js` | 100 |
| `ui/js/init.js` | 250 |

### Изменяются
| Файл | Изменения |
|------|-----------|
| `ui/index.html` | Сокращается с 5,414 до ~400 строк (только HTML + подключения) |

### НЕ затрагиваются
| Файл | Почему |
|------|--------|
| `ui/api.py` и `ui/api/` | JS вызывает `pywebview.api.*` — имена методов не меняются |
| `app.py` | Загружает `ui/index.html` — путь не меняется |
| `core/` | Никакие core-модули не трогаем |

---

## Риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| **Порядок загрузки скриптов** — модуль B зависит от модуля A, но загружается раньше | Средняя | Высокое | `<script>` теги в `index.html` должны идти в правильном порядке: state → utils → api-bridge → callbacks → render → ... → init. Проверять в консоли WebView. |
| **`window.on*` не находит `TX.*`** — колбэк вызывает `TX.renderGrid()`, а модуль ещё не загружен | Высокая | Высокое | `callbacks.js` должен загружаться ПОСЛЕ всех модулей, которые он вызывает. Либо использовать ленивый вызов: `if (TX.renderGrid) TX.renderGrid()`. |
| **Python вызывает `window.on*` до загрузки JS** — pywebview инжектит JS до полной загрузки DOM | Средняя | Высокое | `callbacks.js` должен загружаться в `<head>` или очень рано в `<body>`, чтобы `window.on*` были определены до первого вызова из Python. |
| **IIFE нарушает `this` контекст** — код использует `this` внутри обработчиков | Низкая | Среднее | Просмотреть код на предмет голых `this` (вне методов объектов). В текущем коде используется `event.target`, а не `this`. |
| **Мультистрим-слоты создаются динамически** — ломается CSS, который полагается на структуру в HTML | Средняя | Среднее | CSS не должен зависеть от того, в HTML элемент или создан через JS. Но проверить all селекторы вручную. |
| **pywebview не загружает внешние CSS/JS из локальных файлов** | Низкая | Высокое | Проверить на старте фазы: создать тестовый `test.css` и подключить через `<link>`. Если не работает — использовать `@import` в `<style>` или встроить обратно. |

---

## План тестирования

После **каждого шага**:

```bash
# Ручной запуск — основной способ проверки для фронтенда
make run
```

**Чеклист ручного тестирования (каждый шаг):**
1. Приложение открывается без ошибок в консоли WebView
2. Загружаются стримы (сетка заполняется)
3. Сайдбар показывает избранное
4. Работает поиск
5. Работает браузинг (категории + топ стримов)
6. Работает просмотр канала (профиль)
7. Работает плеер (watch)
8. Работает мультистрим (4 слота)
9. Работает чат (подключение + отправка)
10. Работают настройки
11. Работает контекстное меню
12. Работают горячие клавиши
13. Escape работает с правильным приоритетом

**После всей фазы — регрессионный тест:**
- Пройти весь чеклист выше
- Сравнить скриншоты до/после для каждого view

---

## План отката

```bash
# Полный откат (если не коммитили между шагами)
git checkout -- ui/index.html
rm -rf ui/css/ ui/js/

# Частичный откат (вернуть конкретный модуль)
git checkout -- ui/js/player.js
```

---

## Definition of Done

- [ ] `ui/index.html` — shell, ~400 строк (только HTML + подключения)
- [ ] CSS разнесён по 6 файлам в `ui/css/`
- [ ] JS разнесён по 15 файлам в `ui/js/`
- [ ] Каждый JS-файл ≤ 400 строк
- [ ] Используется IIFE + неймспейс `TwitchX`
- [ ] `window.on*` колбэки — тонкие прокси, делегирующие в `TX.*`
- [ ] `var` заменён на `const`/`let`
- [ ] Мультистрим-слоты создаются динамически (не 4× копия HTML)
- [ ] `DOMContentLoaded` разбит на `_bind*()` функции в `init.js`
- [ ] `make run` — все view работают идентично
- [ ] Регрессионный чеклист пройден
- [ ] Все изменения закоммичены
