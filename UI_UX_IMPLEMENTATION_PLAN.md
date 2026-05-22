# План реализации UI/UX-улучшений TwitchX

Документ фиксирует поэтапный план исправлений визуальной части, UX-потоков и клиентской логики интерфейса. План составлен с учетом правил из `AGENTS.md`: не использовать `style.display` в JS, не lower-case YouTube channel IDs, не добавлять `innerHTML` с пользовательскими данными, сохранять `const TwitchX = window.TwitchX;` в каждом JS-модуле и после UI-изменений выполнять визуальную проверку приложения.

## Цели

- Убрать UI-ошибки, которые могут ломать мультиплатформенность Twitch/Kick/YouTube.
- Привести JS-интерфейс к правилам проекта и снизить риск поломок pywebview inline merge.
- Улучшить доступность: клавиатура, фокус, роли, подписи, размеры интерактивных элементов.
- Сделать настройки, onboarding, browse, player, chat и multistream понятнее и стабильнее.
- Сохранить текущую визуальную идентичность TwitchX: темный нативный macOS-интерфейс, компактность, быстрый доступ к стримам.

## Базовые проверки перед началом

1. Зафиксировать состояние рабочей директории:
   - `git status --short`
   - не откатывать существующие пользовательские изменения.
2. Запустить базовую проверку:
   - `make lint`
   - если `uv` недоступен, отдельно запустить `.venv/bin/ruff check .` и `.venv/bin/pyright .`.
3. Зафиксировать текущие известные проблемы baseline:
   - `ui/api/data.py`: неиспользуемая переменная `twitch_conf`.
   - возможные pyright-проблемы окружения: отсутствующие типы/импорты для локальных зависимостей.
4. После каждой фазы, где менялись `ui/js/` или `ui/css/`:
   - запустить приложение через `make run` или доступный fallback;
   - визуально проверить основные экраны;
   - запустить релевантные тесты;
   - перед финалом запустить `make check` или документировать, почему команда недоступна.

## Фаза 1. Платформенная идентичность в UI

### Проблема

Состояние UI во многих местах завязано только на `login`. Для Twitch/Kick/YouTube это создает риск коллизий: одинаковые логины на разных платформах могут смешивать аватарки, избранное, live state, выбранный канал, viewer history и контекстные действия.

### Файлы

- `ui/js/state.js`
- `ui/js/utils.js`
- `ui/js/sidebar.js`
- `ui/js/channel.js`
- `ui/js/callbacks.js`
- `ui/js/context-menu.js`
- `ui/js/api-bridge.js`
- при необходимости `ui/api/data.py`, `ui/api/favorites.py`, `ui/api/images.py`

### Действия

1. Ввести единый helper для ключа канала:
   - формат: `platform:login`;
   - платформа обязательна, fallback только для совместимости со старым состоянием.
2. Перевести UI-карты состояния на compound key:
   - `liveSet`;
   - `prevViewers`;
   - `avatars`;
   - `thumbnails`;
   - `favoritesMeta`;
   - selected/watching state.
3. Обновить sidebar/grid/channel selection так, чтобы сравнения выполнялись по compound key, а не по lower-case login.
4. Обновить context menu:
   - add/remove favorite;
   - open channel;
   - copy/open links;
   - platform-aware labels and actions.
5. Проверить backward compatibility:
   - старый config с favorites без platform metadata не должен ломать UI;
   - `TwitchX.getFavoriteMeta(login, platform)` остается основным способом доступа.

### Критерии готовности

- Каналы с одинаковым login на Twitch/Kick/YouTube отображаются как разные сущности.
- Аватарки, thumbnails и viewer deltas не перетекают между платформами.
- Избранное добавляется/удаляется для правильной платформы.
- Не появляется `.toLowerCase()` на YouTube channel ID.

## Фаза 2. Соблюдение JS-правил проекта

### Проблема

В JS есть нарушения правил из `AGENTS.md`: `style.display`, потенциально опасный `innerHTML` с динамическими данными и lower-case сравнения для идентификаторов.

### Файлы

- `ui/js/callbacks.js`
- `ui/js/settings.js`
- `ui/js/chat.js`
- `ui/js/player.js`
- `ui/js/multistream.js`
- `ui/js/init.js`
- `ui/js/sidebar.js`
- `ui/js/channel.js`
- `ui/js/api-bridge.js`
- `ui/css/*.css`

### Действия

1. Заменить `style.display` на классы:
   - `.hidden` для обычного скрытия;
   - `.visible` / `.menu-visible` для opacity transitions;
   - при необходимости добавить узкие CSS-классы для специальных случаев.
2. Переписать динамический `innerHTML`:
   - user/API data вставлять только через `textContent`;
   - icon-only markup оставить только там, где он статический и безопасный;
   - для смешанных блоков создать small DOM builder helpers.
3. Убрать lower-case сравнения channel IDs:
   - Twitch/Kick login можно нормализовать только в безопасных местах;
   - YouTube `UC...` всегда сравнивать case-sensitive через compound key.
4. Проверить все JS-модули:
   - каждый модуль начинается с `const TwitchX = window.TwitchX;`;
   - не добавлен `var TwitchX`.

### Критерии готовности

- `rg "style\\.display" ui/js` не находит нарушений.
- `innerHTML` не используется с пользовательскими/API-данными.
- `rg "toLowerCase\\(\\)" ui/js` не показывает опасных сравнений channel ID.
- Приложение стартует без JS syntax/runtime ошибок после inline merge.

## Фаза 3. Доступность и клавиатурная навигация

### Проблема

В интерфейсе уже есть хорошая база: skip-link, focus-visible, reduced-motion. Но часть интерактивных зон мала, некоторые menu/tab элементы не имеют полноценной семантики, а настройки не везде связаны с labels.

### Файлы

- `ui/index.html`
- `ui/css/reset.css`
- `ui/css/components.css`
- `ui/css/views.css`
- `ui/css/player.css`
- `ui/js/keyboard.js`
- `ui/js/context-menu.js`
- `ui/js/palette.js`
- `ui/js/settings.js`

### Действия

1. Привести размеры интерактивных элементов к удобным hit targets:
   - минимум 32x32 для плотных desktop controls;
   - 40-44px там, где элемент используется часто или находится у края окна.
2. Добавить/уточнить `aria-label` для icon-only кнопок.
3. Настроить роли и состояния:
   - tabs: `role="tablist"`, `role="tab"`, `aria-selected`, `aria-controls`;
   - context menu: `role="menu"`, `role="menuitem"`;
   - command palette: корректный active descendant или явный focus model.
4. Связать поля настроек с `<label for="...">`.
5. Проверить `Escape`, стрелки, Enter/Space:
   - модалки;
   - context menu;
   - palette;
   - настройки;
   - multistream slots.

### Критерии готовности

- Основные сценарии можно пройти с клавиатуры.
- Фокус виден и не теряется при открытии/закрытии modal/menu.
- Icon-only controls понятны screen reader.
- В настройках все поля имеют видимые и программные labels.

## Фаза 4. Настройки и первый запуск

### Проблема

Настройки перегружены и местами противоречивы: UI сообщает о bundled credentials, но test connection может требовать client id/secret. Вкладок много, а модальное окно узкое.

### Файлы

- `ui/index.html`
- `ui/css/components.css`
- `ui/js/settings.js`
- `ui/api/auth.py`
- `tests/test_uiux_settings.py`
- `tests/test_first_run.py`
- при необходимости `core/credentials.py`

### Действия

1. Разделить настройки на более понятные группы:
   - Accounts / Platforms;
   - Player;
   - Chat;
   - Appearance;
   - Advanced.
2. Уточнить тексты credential states:
   - bundled credentials available;
   - custom credentials configured;
   - credentials missing;
   - connection failed.
3. Сделать test connection честным:
   - если bundled fallback доступен, не показывать ложную ошибку пустых custom fields;
   - если нужна ручная настройка, явно подсветить недостающие поля.
4. Улучшить empty/first-run flow:
   - единая стартовая точка для логина Twitch/Kick/YouTube;
   - понятные действия при пустом избранном;
   - отсутствие мертвых кнопок.
5. Добавить недостающие стили для onboarding-классов:
   - `.onboarding-desc`;
   - `.onboarding-login-btns`.

### Критерии готовности

- Новый пользователь понимает, что делать на первом экране.
- Test connection соответствует реальному способу авторизации.
- Настройки не требуют чтения длинных пояснений внутри UI.
- Modal остается читаемым на минимальном размере окна.

## Фаза 5. Player bar и поведение просмотра

### Проблема

Нижняя панель плеера функциональна, но плотная. На малой ширине есть риск конфликтов между названием канала, статусом, качеством, таймерами, кнопками записи/чат/внешний плеер и fullscreen.

### Файлы

- `ui/index.html`
- `ui/css/player.css`
- `ui/css/layout.css`
- `ui/js/player.js`
- `ui/js/channel.js`
- `ui/js/callbacks.js`

### Действия

1. Стабилизировать layout player bar:
   - фиксированные зоны: info, status, actions;
   - predictable truncation для названия/статуса;
   - no layout jump при изменении качества/статуса.
2. Увеличить hit targets для частых действий.
3. Проверить состояния:
   - loading;
   - ready;
   - error/offline;
   - recording;
   - external player;
   - fullscreen.
4. Уточнить визуальную иерархию:
   - primary action не должен теряться;
   - опасные/разрушающие действия визуально отличимы.
5. Проверить адаптивность:
   - 700x500 minimum window;
   - 960px default;
   - wide desktop.

### Критерии готовности

- Панель не ломается и не перекрывает контент на минимальном размере окна.
- Текст не вылезает за контейнеры.
- Изменение stream status не дергает layout.
- Кнопки остаются доступными с клавиатуры.

## Фаза 6. Chat UX

### Проблема

Чат поддерживает много полезных функций, но требует улучшения состояний и DOM-безопасности. Нужно проверить очистку, переключение, image handling, download anchors и feedback для действий.

### Файлы

- `ui/js/chat.js`
- `ui/js/callbacks.js`
- `ui/css/components.css`
- `ui/index.html`
- `ui/api/chat.py`

### Действия

1. Убрать `style.display` и небезопасный dynamic HTML.
2. Проверить состояния:
   - connecting;
   - connected;
   - disconnected;
   - error;
   - empty chat;
   - switching stream/multichat.
3. Добавить более ясный feedback:
   - отправка сообщения;
   - ошибка модераторского действия;
   - чат недоступен для платформы;
   - reconnect.
4. Проверить скролл:
   - auto-scroll только когда пользователь у низа;
   - при чтении старых сообщений новые не должны резко уводить вниз.
5. Проверить отображение emotes/images:
   - reserved dimensions;
   - error fallback;
   - alt/label где нужно.

### Критерии готовности

- Chat не ломает layout при длинных сообщениях, emotes и ошибках загрузки.
- Переключение stream очищает/обновляет чат предсказуемо.
- Пользователь понимает статус подключения.

## Фаза 7. Browse и экран канала

### Проблема

Browse и channel profile должны явно объяснять ограничения платформ, особенно YouTube. Сейчас часть действий скрывается, что может выглядеть как поломка.

### Файлы

- `ui/js/browse.js`
- `ui/js/channel.js`
- `ui/js/callbacks.js`
- `ui/css/views.css`
- `ui/index.html`
- `ui/api/data.py`

### Действия

1. Сделать platform-aware cards:
   - Twitch/Kick live channel;
   - YouTube live/VOD/channel where applicable;
   - offline state.
2. Не скрывать критичные действия без объяснения:
   - если YouTube нельзя смотреть напрямую, показать disabled action с tooltip/status;
   - если данные ограничены quota/API, показать понятный empty/error state.
3. Улучшить card layout:
   - стабильные размеры thumbnails;
   - avatar fallback;
   - platform badge;
   - viewer count/title/category hierarchy.
4. Проверить click behavior:
   - card click;
   - secondary buttons;
   - context menu;
   - favorite toggle.

### Критерии готовности

- Пользователь понимает, почему действие доступно или недоступно.
- YouTube IDs не нормализуются через lower-case.
- Карточки не меняют размер при загрузке изображений.

## Фаза 8. Multistream

### Проблема

Multistream работает как отдельный режим, но нуждается в более ясной UX-модели слотов, platform selection, empty states и responsive layout.

### Файлы

- `ui/js/multistream.js`
- `ui/css/views.css`
- `ui/index.html`
- `ui/api/streams.py`

### Действия

1. Убрать `style.display` для slots.
2. Пересмотреть slot states:
   - empty;
   - loading;
   - playing;
   - error;
   - muted/active audio;
   - removing.
3. Добавить platform-aware selection:
   - Twitch;
   - Kick;
   - YouTube, если backend-поток реально поддерживает сценарий;
   - если не поддерживает, явно указать ограничение.
4. Улучшить responsive grid:
   - 1 slot: full;
   - 2 slots: split;
   - 3-4 slots: stable grid;
   - minimum window не должен ломать controls.
5. Улучшить управление audio/chat:
   - понятно, какой слот активен;
   - переключение multi chat не теряет фокус и состояние.

### Критерии готовности

- Slot layout не дергается при добавлении/удалении.
- Empty state ясно говорит, что можно сделать.
- Пользователь понимает активный звук/чат.

## Фаза 9. Command palette, hotkeys и быстрые действия

### Проблема

Command palette уже есть, но ее нужно синхронизировать с обновленной моделью platform identity и доступностью.

### Файлы

- `ui/js/palette.js`
- `ui/js/keyboard.js`
- `ui/js/state.js`
- `ui/js/utils.js`
- `ui/css/components.css`

### Действия

1. Перевести palette actions на compound key.
2. Проверить keyboard model:
   - open/close;
   - arrows;
   - Enter;
   - Escape;
   - focus restore.
3. Добавить platform labels/badges в результаты.
4. Убрать неоднозначные действия при совпадающих login.
5. Проверить empty/no-results/loading states.

### Критерии готовности

- Palette не путает одинаковые login на разных платформах.
- Результаты понятны без мыши.
- Фокус возвращается туда, откуда palette была открыта.

## Фаза 10. Визуальная полировка и дизайн-система

### Проблема

Интерфейс уже имеет токены, темную тему и компоненты, но нужно выровнять плотность, цвета, spacing, состояния и повторяющиеся паттерны.

### Файлы

- `ui/css/tokens.css`
- `ui/css/reset.css`
- `ui/css/layout.css`
- `ui/css/components.css`
- `ui/css/views.css`
- `ui/css/player.css`
- `ui/index.html`

### Действия

1. Проверить цветовые пары на контраст:
   - body text;
   - secondary text;
   - disabled text;
   - badges;
   - buttons;
   - error/success/warning.
2. Упорядочить spacing scale:
   - sidebar;
   - cards;
   - modals;
   - player bar;
   - forms.
3. Уточнить visual hierarchy:
   - screen title;
   - section title;
   - card title;
   - metadata;
   - helper/error text.
4. Унифицировать states:
   - hover;
   - pressed;
   - active;
   - selected;
   - disabled;
   - loading.
5. Проверить radius/shadow/elevation:
   - не вкладывать card в card;
   - не создавать лишние декоративные слои.

### Критерии готовности

- UI выглядит цельно между основными экранами.
- Нет случайных raw colors в новых стилях, используются tokens.
- Hover/focus/active состояния легко различимы.

## Фаза 11. Тестирование и визуальная QA

### Обязательные сценарии

1. Первый запуск:
   - нет credentials;
   - bundled credentials доступны;
   - пользователь добавляет/импортирует избранное.
2. Избранное:
   - Twitch channel;
   - Kick channel;
   - YouTube channel;
   - одинаковый login на разных платформах.
3. Browse:
   - live results;
   - empty results;
   - API/quota error;
   - YouTube limitation state.
4. Player:
   - запуск stream;
   - смена качества;
   - fullscreen;
   - stop/hide player;
   - recording state;
   - external player action.
5. Chat:
   - connect/disconnect;
   - send message;
   - emotes/images;
   - reconnect/error.
6. Multistream:
   - add/remove slots;
   - switch active slot/chat;
   - 1/2/3/4 slot layouts.
7. Settings:
   - tabs;
   - forms;
   - test connection;
   - save/cancel.
8. Keyboard:
   - Tab order;
   - Escape;
   - command palette;
   - context menu.

### Команды

```bash
make lint
make test
make check
```

Fallback, если `uv` недоступен:

```bash
.venv/bin/ruff check .
.venv/bin/pyright .
.venv/bin/python -m pytest tests/ -q
```

### Визуальная проверка

После изменений в `ui/js/` или `ui/css/`:

1. Запустить приложение.
2. Проверить минимальный размер окна `700x500`.
3. Проверить дефолтный размер окна `960x700`.
4. Проверить широкий desktop.
5. Пройти основные сценарии мышью и клавиатурой.

## Рекомендуемый порядок реализации

### PR 1. Baseline и platform identity

- Зафиксировать baseline-проверки.
- Исправить минимальные lint-проблемы, если они блокируют дальнейшую работу.
- Ввести compound key helpers.
- Перевести ключевые state maps и сравнения каналов.

Почему первым: это фундамент. Если сначала полировать UI, часть изменений придется переделывать после исправления идентичности.

### PR 2. JS safety rules

- Убрать `style.display`.
- Убрать dynamic `innerHTML` с пользовательскими данными.
- Убрать опасные lower-case сравнения.
- Проверить inline merge requirements.

Почему вторым: это снижает риск скрытых runtime-поломок и делает дальнейшие UI-изменения безопаснее.

### PR 3. Accessibility и hit targets

- Tabs, context menu, palette roles.
- Labels в settings.
- Aria для icon-only controls.
- Размеры кнопок и focus states.

Почему третьим: после стабилизации состояния можно уверенно улучшать взаимодействие без изменения бизнес-логики.

### PR 4. Settings и onboarding

- Пересобрать структуру настроек.
- Исправить credential messaging/test connection.
- Добавить недостающие onboarding styles.
- Улучшить empty states.

Почему четвертым: это влияет на первый опыт пользователя и снижает количество непонятных состояний.

### PR 5. Player и chat

- Стабилизировать player bar.
- Улучшить статусы playback/recording/errors.
- Улучшить chat states, scroll behavior и feedback.

Почему пятым: это основной ежедневный сценарий приложения.

### PR 6. Browse, channel screen и multistream

- Platform-aware browse cards.
- Ясные ограничения YouTube.
- Улучшенные состояния multistream slots.
- Responsive multistream grid.

Почему шестым: эти экраны зависят от исправленной идентичности и общих UI-паттернов.

### PR 7. Visual polish и финальная QA

- Контраст, spacing, states, typography hierarchy.
- Финальная визуальная проверка.
- Полный `make check`.
- Список остаточных ограничений, если что-то нельзя проверить локально.

Почему последним: полировка эффективнее после того, как структура и поведение уже стабильны.

## Риски и меры контроля

| Риск | Как контролировать |
|------|--------------------|
| Сломать pywebview inline JS merge | Проверять `const TwitchX = window.TwitchX;`, не использовать `var TwitchX`, запускать приложение после JS-правок |
| Смешать Twitch/Kick/YouTube каналы | Использовать compound key в UI state и тестировать одинаковые login |
| Повредить YouTube channel IDs | Запретить lower-case для channel IDs, сравнивать по platform-aware key |
| Внести XSS через UI-рендер | Не использовать `innerHTML` для user/API data |
| Сломать fullscreen/player behavior | Тестировать player states вручную после изменений |
| Ухудшить компактность интерфейса | Увеличивать hit targets точечно, сохранять desktop-density |
| Не пройти baseline из-за окружения | Документировать недоступный `uv`/типовые pyright env errors и запускать доступные fallback-команды |

## Definition of Done

- Все изменения разбиты на небольшие фазы/PR.
- `make check` проходит или есть четко задокументированная причина, почему команда недоступна.
- После изменений в `ui/js/` или `ui/css/` приложение запускалось и было визуально проверено.
- Нет новых нарушений правил:
  - `style.display` в JS;
  - lower-case YouTube channel IDs;
  - `innerHTML` с user/API data;
  - `var TwitchX`;
  - AppKit/AVKit вне main thread.
- Основные сценарии Twitch/Kick/YouTube проверены вручную.
- Интерфейс остается компактным, читаемым и управляемым с клавиатуры.
