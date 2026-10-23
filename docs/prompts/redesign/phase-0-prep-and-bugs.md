# Redesign phase 0: превью-харнесс и визуальные баги

Ты — senior frontend-инженер, который работает в репозитории TwitchX
(pywebview + WKWebView, плоские JS-модули, CSS на токенах). Это первая из пяти
фаз редизайна. Дизайн в этой фазе **не меняется**: ты чинишь то, что сломано, и
заводишь инструмент визуальной проверки, без которого остальные фазы делаются
вслепую.

## Перед началом

1. Прочитай `CLAUDE.md` и `docs/prompts/redesign/README.md` целиком. Правила
   оттуда обязательны и здесь не повторяются.
2. Запусти `make check` и `uv run python tools/css_ownership.py`. Если что-то
   красное ещё до твоих правок — зафиксируй это в описании PR и не чини, если
   оно не входит в шаги ниже.
3. Прочитай файлы, которые будешь трогать: `ui/css/components/stream-card.css`,
   `ui/css/components/stream-extras.css`, `ui/js/icons.js`, `app.py`,
   `ui/css/themes/dark.css`, `ui/js/utils.js`, `core/utils.py`, `ui/index.html`
   (строки с `profile-area`, `kick-profile-area`, `settings-modal`).

## Цель

После фазы:
- превью стримов имеют честное соотношение 16:9 при любом размере окна;
- в меню нет заглушек вместо иконок, и тест не даёт этому повториться;
- при запуске нет вспышки чужого цвета;
- предупреждения визуально отличаются от акцента;
- числа зрителей пишутся одинаково везде;
- `make preview` снимает скрины всех ключевых экранов в обеих темах.

## Шаги

### 0.0 `make check-linux` для облачных сессий

`make check` на Linux падает ещё на установке: `uv` собирает
`pyobjc-framework-avfoundation`/`avkit`, а это только macOS. Все следующие
фазы часто выполняются в облачной Linux-сессии, поэтому нужна рабочая
проверка там.

- Добавь в `Makefile` цель `check-linux`:
  - `uvx ruff@<версия из pyproject> check .`;
  - pytest через `uv run --no-project --python 3.12 --with …` с
    зависимостями проекта без pyobjc (рабочий набор: `pytest pytest-asyncio
    pytest-httpx pytest-cov httpx curl-cffi "pillow<12" "websockets>=16"
    "pywebview>=5,<6"`; сверь версии с `pyproject.toml`);
  - pyright тем же способом, но его вывод фильтруется: проходят только
    ошибки `reportMissingImports` для `AppKit`, `Foundation`, `PyObjCTools`,
    `objc`, `webview.platforms.cocoa`. Любая другая ошибка — провал. Сделай
    это маленьким скриптом `tools/pyright_linux.py`, а не однострочником на
    `grep`, чтобы правило было читаемым.
- Не меняй `pyproject.toml` и обычный `make check` (на маке всё работает как
  раньше).
- Опиши цель в `CLAUDE.md`, раздел «Команды».

Готово, когда: на Linux `make check-linux` зелёный (сейчас это 997 passed,
2 skipped), а на маке `make check` не изменился.

### 0.1 Превью-харнесс → `tools/ui_preview/`

Перенеси `docs/prompts/redesign/reference/ui_preview/{build.js,mock.js,shoot.js}`
в `tools/ui_preview/` (они уже рассчитаны на это место: `ROOT` — два уровня
вверх). Затем:

- Добавь в `Makefile` цель `preview`:
  `node tools/ui_preview/build.js && node tools/ui_preview/shoot.js $(ARGS)`.
  Если `node` нет, цель печатает понятное сообщение и выходит с кодом 0.
  `shoot.js` уже сам выходит с 0, если не находит `playwright`.
- Добавь `.preview/` в `.gitignore`.
- Напиши `tools/ui_preview/README.md`: зачем, как запустить, как выбрать
  сценарии (`make preview ARGS="grid player"`), как добавить сценарий, что
  мок обязан повторять форму данных Python (`onStreamsUpdate`,
  `onConfigLoaded`, `onChatMessage` с `author_color`, `onBrowseCategories`,
  `onChannelProfile`).
- Не добавляй Playwright в зависимости проекта: это dev-инструмент, CI его
  не запускает.
- Прогони `make preview` и **открой несколько PNG**. Особенно
  `grid-dark-960x640.png`: на нём сейчас карточки без превью (это баг 0.2).
  Сохрани для себя пару скринов «до», они понадобятся для описания PR.

Готово, когда: `make preview` без ошибок пишет 44 PNG (11 сценариев ×
2 темы × 2 размера) в `.preview/`.

### 0.2 Превью перестают схлопываться (главный баг)

**Симптом:** при 960×640 (дефолтное окно) превью карточек 0 px, при 960×900 —
42 px, при 1280×800 — 109 px вместо 163.

**Причина:** `#stream-grid` — грид с фиксированной высотой (`.view` с
`position:absolute; inset:0`). Auto-строки грида при нехватке места остаются на
min-content, а у `.card-thumb` с `overflow: hidden` min-content по высоте равен
нулю (flex-элемент в колонке `.stream-card`).

**Исправление:** добавь `grid-auto-rows: max-content;` в правило `#stream-grid`
в `ui/css/components/stream-card.css`. Не используй `flex-shrink: 0` на
`.card-thumb`: тогда превью вылезает за карточку, а строка грида не растёт.

Проверь режимы `list`, `compact`, `comfortable` (`stream-extras.css`, кнопка
`#grid-toggle-btn` циклически их переключает): ни один не должен сломаться.

Добавь в `tests/test_ui_player_views.py` тест, который читает
`stream-card.css` и проверяет, что в правиле `#stream-grid` есть
`grid-auto-rows: max-content`, с комментарием о причине.

Готово, когда: на `grid-*-960x640.png` превью 16:9.

### 0.3 Недостающие иконки + тест

В `ui/js/icons.js` нет `folder-plus`, `folder-move`, `edit`, `trash`. Они
используются в `ui/index.html` (контекстное меню канала и меню группы), поэтому
`renderIcon` рисует вместо них заглушку-кружок.

- Нарисуй четыре иконки в стиле набора: `viewBox 0 0 16 16`, только stroke
  (`fill="currentColor" stroke="none"` — лишь для мелких точек, как в
  существующих), координаты с шагом 0.05, скруглённые концы задаёт
  `renderIcon`. Сверяйся с соседними `copy`, `pin`, `close`.
- Новый `tests/test_icons.py`:
  - собирает имена из `ICONS` (ключи объекта в `icons.js`, с кавычками и
    без);
  - собирает все `data-icon="…"` из `ui/index.html`;
  - собирает строковые литералы, которые передаются вторым аргументом в
    `setIconOnly(el, 'name', …)` и `setIconText(el, 'name', …)` (`ui/js/utils.js`)
    и первым — в `renderIcon('name', …)` (`ui/js/icons.js`), во всех
    `ui/js/*.js`, включая вызовы через `TwitchX.`; имена из переменных
    пропускай, но если такие есть — перечисли их в комментарии теста;
  - падает со списком отсутствующих имён.
- Заглушку в `renderIcon` оставь и добавь `console.warn('[icons] unknown icon:', name)`.

Готово, когда: тест зелёный, на `context-*` скринах у Create group и Move to
group нормальные иконки.

### 0.4 Фон окна совпадает с темой

`app.py` создаёт окно с `background_color="#0E0E1A"` (синеватый), а
`--bg-base` = `#111113` (dark) / `#F5F5F7` (light). При старте мигает синий.

- Добавь в `app.py` чистую функцию `window_background(theme_mode: str,
  system_is_dark: bool) -> str`: `"light"` → `#F5F5F7`, `"dark"` → `#111113`,
  `"auto"` → по `system_is_dark`, неизвестное значение → тёмный.
- Режим темы бери из настроек конфига (ключ `theme`, см. `DEFAULT_CONFIG` в
  `core/storage.py` и `tests/test_uiux_settings.py`).
- `system_is_dark` определи через
  `NSApplication.sharedApplication().effectiveAppearance().bestMatchFromAppearancesWithNames_([NSAppearanceNameAqua, NSAppearanceNameDarkAqua])`
  в `try/except` с фолбэком `True`. Импорт AppKit — внутри функции, чтобы
  тесты на Linux не падали. Окно ещё не создано, поэтому этот вызов не
  нарушает правило «AppKit только через callAfter»; если в этом сомневаешься,
  выбери фолбэк и опиши в PR.
- Если в будущем значения `--bg-base` поменяются (фаза 1), функция должна
  быть очевидным местом для правки: оставь комментарий со ссылкой на
  `ui/css/themes/*.css`.
- Тесты на функцию (все ветки) — в новом `tests/test_window_bg.py`.

### 0.5 Мелкие визуальные баги

Каждый пункт — отдельный коммит:

1. `.sidebar-stale-banner` (`sidebar.css`): `padding` и `margin` используют
   `--space-1`/`--space-2`, а это 1 и 2 px. Поставь `padding: var(--space-4)
   var(--space-8)`, `margin: var(--space-4) var(--space-10)`, `gap:
   var(--space-6)`. Проверь сценарий вручную: вызови в харнессе
   `window.onStatusUpdate({text:'x', stale:true})`.
2. Дубль точек платформ: в `ui/index.html` блок `.platform-status-dots` есть и
   в `#user-info`, и в `#kick-user-info`. Убери его из Kick-строки. Найди JS,
   который заполняет точки (`grep -rn "platform-status-dots\|platform-status-dot" ui/js`),
   и убедись, что он работает с одним контейнером.
3. Пустое состояние во вкладке Live Now профиля канала: иконка прижата влево,
   текст по центру. Найди причину в `channel.css` / `empty-state.css` (скорее
   всего контейнер иконки не центрируется внутри `.channel-tab-panel`) и
   выровняй по центру. Проверь сценарием `channel`.
4. Заглушка аватарки профиля (`#user-avatar`): `<img alt="User avatar">` без
   `src` рисует alt-текст. Поставь `alt=""` и `aria-hidden="true"` на img,
   имя пользователя рядом и так читается. `test_no_empty_image_src_anywhere`
   должен остаться зелёным.
5. Кнопка Save в настройках уезжает за край на вкладке Accounts. Сделай
   `.settings-btns` липким к низу модалки (`position: sticky; bottom: 0` с
   фоном `--bg-modal` и верхней границей), а контенту — внутреннюю прокрутку.
   Это временно, в фазе 3 Save исчезнет.

### 0.6 Предупреждения отличаются от акцента

В `ui/css/themes/dark.css` `--warn-yellow`, `--toast-bg-warn` и
`--toast-border-warn` построены на `hsl(36 100% 52%)`, а это и есть дефолтный
акцент (`tokens.css`). Переведи тёмную тему на `#FFD60A` (bg 20%, border
35%). Светлая тема уже на `#8A5200`, её не трогай. `tests/test_contrast.py`
проверяет `warn-yellow` на `bg-base`: прогони тесты.

### 0.7 Единый формат чисел

Сейчас два форматтера расходятся: Python `format_viewers` (`core/utils.py`,
идёт в `total_viewers_formatted` в статус-баре) пишет `12.0k` и `1.0M`, а JS
`formatViewers` (`ui/js/utils.js`, карточки и сайдбар) отбрасывает `.0` и пишет
`12k`. Приведи оба к одному формату (заглавные буквы, как в нативных
macOS-приложениях):

| число | вывод |
|---|---|
| 0–999 | `950` |
| 1 000–99 999 | `9.7K`, `88.3K`, `12K` (один знак, `.0` отбрасывается) |
| 100 000–999 999 | `210K` (без дробной части) |
| ≥ 1 000 000 | `1.2M`, `12M` (`.0` отбрасывается) |

Округление на границах должно давать не `1000K`, а `1M` (999 950 → `1M`);
проверь это явно. Обнови существующие тесты, которые ждут старый формат
(`grep -rn "format_viewers" tests`), и добавь параметризованные тесты на
границы (999, 1000, 1050, 99 949, 99 950, 100 000, 999 499, 999 950,
1 000 000, 12 000 000). Для JS проверь те же значения через `node -e` на
копии функции и приложи вывод к PR (JS-тестов в проекте нет, фреймворк не
заводи).

## Чего не делать

- Не менять дизайн, токены, раскладку: это фазы 1–3.
- Не добавлять npm-зависимости в проект и не создавать `package.json`.
- Не трогать Python-логику, кроме `app.py` (0.4) и `core/utils.py` (0.7).

## Выход из фазы

- [ ] `make check` (или `make check-linux` на Linux) зелёный, новые тесты: `test_icons.py`,
      `test_window_bg.py`, правило грида, формат чисел.
- [ ] `uv run python tools/css_ownership.py` → 0.
- [ ] `make preview` без ошибок страницы, скрины просмотрены.
- [ ] PR `Redesign phase 0: preview harness and visual bugs` открыт, в
      описании скрины «до/после» для 960×640 и контекстного меню, чек-лист
      для мака: запуск в светлой и тёмной теме без вспышки, окно 960×640,
      контекстные меню, плашка stale.
