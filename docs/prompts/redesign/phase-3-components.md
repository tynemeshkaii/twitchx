# Redesign phase 3: компоненты

Ты — senior frontend-инженер с сильным дизайнерским вкусом в репозитории
TwitchX. Это четвёртая из пяти фаз редизайна. Каркас (фаза 2) и токены
(фаза 1) готовы, теперь каждый компонент собирается по новому образцу:
«тихий интерфейс, громкий контент». **Один компонент — один коммит** со
скринами до и после: так ревью читается, а неудачный коммит откатывается
отдельно.

## Перед началом

1. Прочитай `CLAUDE.md` и `docs/prompts/redesign/README.md` (макет главного
   экрана и «Принятые решения»: режимы плотности — только `grid` и `list`,
   настройки — модалка в стиле окна настроек macOS).
2. Убедись, что фаза 2 смержена: в `main` нет `#player-bar` в `ui/index.html`,
   есть `ui/js/account.js`. Если нет — остановись и сообщи пользователю.
3. `make check`, `css_ownership`, `make preview` → копия в `.preview-before/`.
4. Прочитай `ui/css/tokens.css` и обе темы: это твой единственный источник
   значений. Сырые px, новые цвета-литералы и веса вне шкалы `test_css_tokens.py`
   не пропустит — так и задумано. Если токена не хватает, добавь его в
   `tokens.css`/темы осознанно и опиши в PR.

## Общие правила компонентов

- Глубина — тоном фона, не рамкой и тенью. Тень и blur только у парящих слоёв
  (`--surface-floating`, шаг 3.8).
- Типографика: название 13/600, мета 12/400 `--text-secondary`, подписи
  секций 11/600 `--text-muted`, заголовок раздела 22/700.
- Цвет платформы — только точка 8–11 px или глиф 18 px. Live — только
  `--live`. Зрители — `--viewers`.
- Ховер: фон `--hover-bg` или кольцо 2 px `--accent` вокруг медиа. Без
  подъёмов, свечения и масштабов больше 1.02.
- Фокус клавиатуры видим везде (`:focus-visible`, `--focus-ring`).
- Видимость — только через классы (`hidden`, `visible`), `innerHTML` с
  данными запрещён: только `createElement` + `textContent`.
- После каждого шага — `make preview` нужных сценариев в обеих темах и
  размерах 960×640 и 1280×800, **просмотр PNG глазами**.

## Шаги

### 3.1 Карточка стрима

Разметку строит `render.js` (функция создания карточки + diff-ветка
in-place обновления, `_syncPinBadge`). Новая структура:

```
.stream-card                      (без фона, рамки, тени; display:flex column; gap 10px)
  .card-thumb                     (16:9, radius --radius-md, overflow hidden)
    img.thumb-img / .thumb-shimmer
    .card-platform                (глиф 18px сверху слева: тёмная подложка rgba(0,0,0,.45), точка цвета платформы)
    .pin-badge                    (сверху справа, если закреплён)
    .card-viewers-overlay         (снизу слева: точка --live + "42.1K", белый 11.5/600, tabular-nums)
    .uptime-badge                 (снизу справа: "5:12:04", без подложки, белый .82)
    .card-play                    (кнопка play по центру, только при :hover/:focus-visible)
  .card-meta                      (flex, gap 10px)
    img.card-avatar               (28px, круг)
    .card-text
      .card-title                 (название стрима, 13/600, одна строка, ellipsis)
      .card-sub                   ("shroud · VALORANT": канал --text-secondary, игра --text-muted)
```

- Удалить `.live-badge` (в сетке Following и так только лайв), старый
  `.platform-badge` на превью, рамку/фон `.card-body`.
- Стрелка тренда (`.trend.up/.down`) — маленькая, рядом с числом зрителей на
  превью, цветом белый .7 (не зелёный/красный: на кадре они не читаются).
- Ховер: кольцо `box-shadow: 0 0 0 2px var(--accent)` на `.card-thumb`, превью
  `brightness(1.05)`, появляется `.card-play`. Фокус — то же кольцо.
- `.offline` и `.watching` состояния перерисовать в том же языке
  (watching — плашка «Watching» на кадре вместо зелёной заливки).
- Обнови diff-ветку и `_syncPinBadge` под новую разметку. Тест
  `test_live_channel_renders_a_card`, `test_pin_badge_is_synced_in_the_diff_branch`
  должны остаться зелёными (поправь, если они ищут старые классы, но не
  ослабляй проверку).
- Сетка: `grid-template-columns: repeat(auto-fill, minmax(240px, 1fr))`,
  `gap: 24px 16px`, `grid-auto-rows: max-content` (из фазы 0) сохранить.

Готово, когда: `grid-*` скрины совпадают с макетом в README по структуре.

### 3.2 Режимы плотности: Grid и List

- `init.js`: `DENSITY_MODES` и `validModes` → `['grid', 'list']`. При чтении
  сохранённого значения `comfortable` и `compact` → `grid` (и перезаписать
  localStorage).
- List — строка 56 px: мини-превью 80×45 с radius `--radius-sm`, аватар 24,
  название + «канал · игра», справа зрители и аптайм. Стили в
  `stream-extras.css` (удали правила `comfortable-mode`, `compact-mode`).
- Пункт плотности в меню сортировки (фаза 2) — два варианта с галочкой.
- Иконки `compact-toggle`, если больше не используются, удалить из
  `icons.js` (`tests/test_icons.py` подскажет обратное).

### 3.3 Строка сайдбара, рейл, секции, группы

`sidebar.js` (`renderSidebar`, `renderSidebarGroupBody`, `renderRail`,
`applySidebarLayout`, построение строки ~343, ~589), `sidebar.css`.

- Строка live: высота 40, `padding 0 10px`, radius `--radius-sm`. Аватар 26
  с точкой платформы 11 px в правом нижнем углу (обводка цветом фона
  сайдбара), колонка «имя 13/500 / игра 11.5 `--text-muted`», справа зрители
  12 `--viewers` tabular-nums.
- Строка offline: высота 32, аватар 22 grayscale, только имя, прозрачность
  45%.
- Удалить `.accent-bar`, `.live-dot`, кольцо аватара, зелёные метрики, рамку
  при ховере. Выбранный (клавиатура) и `watching` — фон `--hover-bg-strong`,
  у watching — маленький индикатор «эквалайзер» или точка `--accent` справа
  вместо числа зрителей.
- Заголовки секций «Live 9», «Offline 5» — подпись 11/600 `--text-muted` с
  числом справа, без кружка-шеврона и капсулы; сворачивание по клику на
  подпись сохраняется (шеврон 12 px появляется при ховере). Убрать мету
  «9 live now • 494.9k combined» (она теперь в заголовке раздела).
  `#favorites-header` с бейджем количества — удалить, если секции его
  заменяют (проверь, что `notif-badge` «новые в эфире» не потерялся —
  перенеси его в подпись секции Live).
- Группы (`.group-header`): та же подпись 11/600, без uppercase.
- Drag-handle, `.drop-indicator`, `.dragging` — проверь, что DnD
  избранного (`test_favorites_reorder.py`, `test_ui_favorites.py`) работает и
  выглядит в новом языке.
- Рейл (`.rail-avatar`): аватар 30 с точкой платформы, live — полная яркость,
  offline — 45%; выбранный — кольцо 2 px `--accent`. Индикатор-полоска слева
  оставить.
- Пересчитай высоты в `applySidebarLayout` под новые высоты строк.
- `#sidebar-tooltip` — `--surface-floating`, превью 16:9 radius `--radius-sm`.

### 3.4 Плеер: шапка в оверлее и чат

- `#player-header` становится верхней полосой оверлея поверх видео
  (градиент `rgba(0,0,0,.6)` → прозрачный): аватар 24, канал 13/600, название
  стрима 12 `--text-on-overlay`, справа «…» (поповер: Stream stats, Start
  recording, Open in external player, Open in browser) и закрыть. Скрывается
  вместе с нижней полосой (автоскрытие из фазы 2).
  `#stats-overlay-btn`, `#record-btn`, `#toggle-chat-btn`,
  `#fullscreen-player-btn`, `#close-player-btn` — ID сохраняются там, куда
  переезжают (`#toggle-chat-btn` — в нижнюю полосу справа).
- Все цвета на видео — фиксированные светлые (`--text-on-overlay`), никогда
  `--text-*` (`test_overlay_contrast.py`).
- Чат (`chat.css`, `chat.js`, рендер сообщений в `callbacks.js` ~554):
  - ширина по умолчанию 320 (настройка `chat_width` сохраняется);
  - шапка 44 px: «Chat» 13/600 + точка статуса (зелёная — connected,
    серая — connecting) без текста статуса (текст — в `title`); справа
    одна кнопка «…» с пунктами Timestamps, Filters, Users (N), Export,
    Mod tools. Существующие панели (`#chat-filter-panel`,
    `#chat-userlist-panel`, `#chat-mod-panel`, `#chat-export-menu`)
    открываются из этого меню, их ID и ARIA-связи сохраняются;
  - сообщение: ник 13/600 цветом `--author-color` (уже выставляется), текст
    13/400 `--text-primary`, межстрочный 1.45, отступ между сообщениями 4 px,
    бейджи 14 px с отступом 4;
  - упоминания — фон `--accent-dim` и полоска 2 px `--accent` слева;
  - поле ввода — 36 px, radius `--radius-md`, кнопка эмодзи внутри поля
    слева, Send — иконка-стрелка внутри поля справа (кнопка
    `#chat-send-btn` сохраняет ID).
- Мультистрим-чат (`#ms-chat-panel`) — те же стили.

### 3.5 Настройки

`ui/index.html` (`#settings-overlay`), `settings.js`, `settings.css`,
`forms.css`. Python `save_settings` уже принимает частичный payload — это
видно по `tests/test_uiux_settings.py::test_save_settings_chat_filter_only_does_not_restart_polling`.
Прочитай `saveSettings()` (`settings.js` ~516) и `ui/api/__init__.py`
`save_settings`/валидацию, прежде чем менять поток данных.

- Раскладка: модалка 720×560, слева список разделов (Accounts, Player, Chat,
  Appearance, Advanced) с иконками 16, справа контент с заголовком раздела
  22/700. Контент — группы «inset list»: строки 44 px «подпись слева ·
  контрол справа», разделители между строками, группа на фоне
  `--bg-elevated` с radius `--radius-md`. Подсказки (`.setting-hint`) —
  12 `--text-muted` под группой.
- **Мгновенное применение:** тумблеры, селекты, тема, акцент, интервал
  обновления сохраняются сразу — `save_settings(JSON.stringify(partial))` с
  дебаунсом 300 мс для текстовых путей (IINA, mpv, streamlink, recording) и
  без дебаунса для тумблеров/селектов. Интервал — по `change`, не на каждый
  шаг. Фидбек — тихий «Saved» в строке, ошибки — `onSettingsError` как
  сейчас.
- **Секреты — явно:** Client ID / Secret / API key каждой платформы живут в
  раскрывающемся блоке «Advanced» внутри секции платформы и сохраняются
  кнопкой «Save credentials» этого блока (секрет не уходит в конфиг на каждое
  нажатие). Глобальный `#save-btn` и `.settings-btns` удалить (обнови
  `init.js`).
- Accounts: секция на платформу — иконка/точка платформы, имя, статус
  («Signed in as tynemesh» / «Not connected» / «API key required»), одна
  кнопка Connect/Disconnect. `cred-badge` → текст статуса с цветной точкой.
- Appearance: тема — `.segmented` (Auto / Dark / Light) **без радио-точек**
  (сохрани `role="radiogroup"` семантику через `role="radio"` +
  `aria-checked` на кнопках, обнови `settings.js`); акцент — свотчи 20 px с
  кольцом выбора 2 px, `aria-label` с названием цвета.
- Hotkeys-таблица — строки inset list, клавиша — `kbd` 11/500 на
  `--bg-control`.
- Статистика просмотров — плитки только в разделе Advanced → Statistics, на
  токенах.
- Обнови тесты `test_uiux_settings.py`, если они завязаны на Save-кнопку
  (Python-контракт не меняется).

### 3.6 Browse и профиль канала

- Категория (`onBrowseCategories` в `callbacks.js` ~1030, `browse.css`):
  обложка 3:4 radius `--radius-md`, под ней название 13/600 и строка
  «310K watching» 12 `--text-secondary` (поле `viewers` уже приходит из
  `data.py`; отформатируй через `formatViewers`), платформы — ряд глифов
  12 px `--icon-muted`, а не цветные плашки. Сетка `minmax(150px, 1fr)`.
  Фолбэк без обложки (`createImageFallback`) — буква на `--bg-elevated`.
- Сетка стримов Browse (`onBrowseTopStreams`) переиспользует карточку из 3.1
  — вынеси построение карточки в общую функцию, если сейчас это два разных
  кода.
- Шапка Browse: хлебные крошки 13/500 + фильтр платформ общим `.segmented`
  (не отдельные `browse-platform-tab` с заливкой).
- Профиль канала (`channel.js`, `channel.css`): баннер-градиент из цвета
  аватара (или нейтральный), аватар 72, имя 22/700, `@login` + глиф
  платформы, «11.2M followers»; справа одна primary «Watch» (если live) и
  secondary «Follow», «Open in browser». Live-бейдж — точка `--live` +
  «Live» 12/600. Табы Live / VODs / Clips — общий `.segmented`. VOD и клипы —
  карточки в стиле 3.1 с длительностью вместо аптайма. Пустые состояния — из
  3.8.

### 3.7 Мультистрим

- Пустой мультистрим: одна подсказка по центру («Add up to 4 streams»,
  кнопка «Add stream», ниже — пресеты раскладок иконками). Слоты-сетка
  появляется после первого добавления. Не показывать 4 одинаковых
  пунктирных CTA.
- Контролы слота (`.ms-slot-controls`, `multistream.js` ~572) — стиль
  нижней полосы оверлея плеера: иконки 16 на тёмной подложке, автоскрытие.
- Шапка `#multistream-header` — как верхняя панель (52 px), селект пресета —
  кнопка-меню.
- Видимость слотов — только `classList` (CLAUDE.md: WKWebView играет звук
  даже у скрытого родителя, никогда `style.display`).
  `tests/test_ui_states.py` (add form) должен остаться зелёным.

### 3.8 Парящие слои и пустые состояния

- Токен-набор в `tokens.css`/темах: `--surface-floating` (фон
  `--bg-elevated` с альфой .92 + `backdrop-filter: blur(24px) saturate(160%)`),
  `--shadow-floating`, radius `--radius-md`, рамка `--border-subtle`.
  Применить к: `#context-menu`, `#group-context-menu`, поповеру аккаунта,
  меню сортировки/качества/«…», `#palette-modal`, тостам,
  `#sidebar-tooltip`, `#search`-результатам палитры. Обнови allowlist
  `backdrop-filter` в `test_css_tokens.py`.
- Пункт меню: высота 30, radius `--radius-sm`, иконка 16 `--icon-muted`,
  текст 13, хоткей справа 12 `--text-muted`, деструктивный пункт —
  `--error-red`.
- Пустые состояния (`renderEmptyState` в `render.js`, `empty-state.css`) —
  один компонент: иконка 40 `--icon-muted` без подложки, заголовок 15/600,
  текст 13 `--text-secondary` max 360 px, не больше двух кнопок (primary +
  secondary). Всё по центру по обеим осям.
- Приветствие (нет избранного и не залогинен): заголовок «Welcome to
  TwitchX», текст, одна primary «Connect account» (открывает поповер
  аккаунта) и secondary «Browse live channels». Никаких брендовых цветов
  платформ на кнопках.
- Онбординг (`onboarding.css`) — привести к тем же модалкам/кнопкам.

## Чего не делать

- Не менять структуру окна и места контролов (это сделала фаза 2).
- Не менять Python-контракты (`save_settings`, payload'ы колбэков).
- Не добавлять библиотеки, фреймворки, шрифты.
- Не делать анимации и полировку движения — фаза 4.

## Выход из фазы

- [ ] Каждый шаг 3.1–3.8 — отдельный коммит, в PR к каждому — пара скринов
      до/после (обе темы, 960×640).
- [ ] Во всём приложении табы/фильтры — один компонент `.segmented`.
- [ ] `make check`, `css_ownership`, `test_css_tokens`, `make preview` без
      ошибок страницы.
- [ ] Ручной чек-лист фазы 2 (лежит в `phase-2-shell-and-navigation.md`)
      включён в PR как «проверить повторно на маке», плюс: настройки
      применяются сразу и переживают перезапуск; «Save credentials»
      сохраняет ключи; режим List; DnD избранного.
- [ ] PR `Redesign phase 3: components`.
