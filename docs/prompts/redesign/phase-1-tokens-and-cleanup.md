# Redesign phase 1: токены и визуальная чистка

Ты — senior frontend-инженер и дизайнер интерфейсов в репозитории TwitchX.
Это вторая из пяти фаз редизайна. Задача фазы — сделать приложение
**спокойнее при той же раскладке**: меняются только значения токенов, шкалы и
эффекты. DOM (`ui/index.html`) и JS (`ui/js/`) в этой фазе не трогаются, кроме
случаев, явно названных ниже. После фазы компоненты фазы 3 собираются из
готовой системы.

## Перед началом

1. Прочитай `CLAUDE.md` и `docs/prompts/redesign/README.md`.
2. Убедись, что фаза 0 смержена: в `main` есть `tools/ui_preview/`, цель
   `make preview` и `tests/test_icons.py`. Если нет — остановись и сообщи
   пользователю, ничего не делая.
3. `make check`, `uv run python tools/css_ownership.py` — зелёные до правок.
4. `make preview` → сохрани копию `.preview/` в `.preview-before/` (тоже в
   `.gitignore`, если ещё нет) для сравнения в конце.
5. Прочитай целиком: `ui/css/tokens.css`, `ui/css/themes/dark.css`,
   `ui/css/themes/light.css`, `ui/css/layout.css`, `ui/css/animations.css`,
   `ui/css/reset.css`, `tests/test_contrast.py`, `tests/test_overlay_contrast.py`,
   `tools/css_ownership.py`. Остальные `components/*.css` — по мере правок.

## Жёсткие ограничения

- **Имена существующих токенов не меняются.** Тесты контраста читают их по
  имени. Удалять можно только токены, которые после миграции нигде не
  используются (проверяй `grep -rn "var(--name)" ui/`).
- Текстовые пары из `tests/test_contrast.py` (`TEXT_PAIRS`, `STATUS_PAIRS`)
  обязаны держать ≥ 4.5:1 в обеих темах. Значения ниже уже посчитаны под это,
  не «улучшай» их на глаз.
- Раскладка на скринах после фазы должна совпадать с `.preview-before/` с
  точностью до отступов. Если элемент переехал или исчез — это ошибка.

## Шаги

Каждый шаг — отдельный коммит, после каждого `make check` + `make preview` +
просмотр минимум `grid`, `player`, `settings` в обеих темах.

### 1.1 Нейтрали и текст

`ui/css/themes/dark.css`:

| токен | было | станет |
|---|---|---|
| `--bg-base` | `#111113` | `#0F1012` |
| `--bg-surface` | `#1A1A1D` | `#16171A` |
| `--bg-elevated` | `#242427` | `#1E2024` |
| `--bg-overlay` | `#303034` | `#272A2F` |
| `--bg-panel` | `#202024` | `#1A1B1F` |
| `--bg-control` | `#27272B` | `#22242A` |
| `--bg-control-hover` | `#323238` | `#2A2D33` |
| `--text-primary` | `#F2F2F7` | `#EDEEF0` |
| `--text-secondary` | `#AEAEB2` | `#A1A4AB` |
| `--text-muted` | `#A8A8AD` | `#868A92` (5.5:1 на base, 4.7:1 на elevated) |
| `--text-muted-elevated` | `#99999F` | `#8A8E96` |
| `--border-subtle / default / strong` | `.08 / .13 / .22` | `.06 / .10 / .16` |

`ui/css/themes/light.css`:

| токен | станет |
|---|---|
| `--bg-base` | `#FFFFFF` |
| `--bg-surface` | `#F3F3F5` (сайдбар) |
| `--bg-elevated` | `#F2F2F4` |
| `--text-primary` | `#17181A` |
| `--text-secondary` | `#5D6067` |
| `--text-muted` | `#6A6D74` (5.2:1 на base, 4.6:1 на elevated; `#6E7178` **не проходит**) |
| `--border-*` | `.06 / .09 / .15` |

Добавь в обе темы `--icon-muted` (dark `#5F636B`, light `#9A9DA3`) — для
глифов и разделителей, **не для текста**.

Обнови функцию `window_background()` в `app.py` под новые `--bg-base` (её
завела фаза 0) и её тест.

Готово, когда: `test_contrast` и `test_overlay_contrast` зелёные без правок
списков пар.

### 1.2 Цвета по смыслу

1. Добавь в обе темы `--live` (dark `#FF453A`, light `#D32F2F`) — только
   «в эфире» — и `--viewers: var(--text-secondary)`.
2. Зелёный `--live-green` остаётся только для успеха и статуса
   «подключено». Переведи на нейтральные цвета:
   - `.channel-item.live .metric` → `var(--viewers)`;
   - `.sidebar-section.online .section-count` → как у offline (нейтральная
     капсула);
   - `#status-text.status-success` → `var(--text-secondary)`;
   - `.tooltip-viewers` → `var(--text-secondary)`;
   - `.search-result .sr-live` → `var(--live)`.
   Перед правкой каждого селектора сделай `grep` и убедись, что не ломаешь
   смысл «успех» (тосты успеха, «Connected» в чате, «Built-in credentials» в
   настройках остаются зелёными).
3. Индикаторы «в эфире» (`.live-badge`, `#live-dot`, `.channel-item.live
   .live-dot`, `.rail-av-ring`, `.rail-av-dot`) → `var(--live)`. Да,
   live-индикаторы в сайдбаре становятся красными точками вместо зелёных: так
   «в эфире» обозначается одним цветом везде.
4. Платформы — только точки и глифы:
   - `.platform-badge.{twitch,kick,youtube}`: фон — цвет платформы на 16%
     (`color-mix(in srgb, var(--platform-x) 16%, transparent)`), текст — цвет
     платформы (для Kick в светлой теме — `--platform-kick-on-light: #2E8A0E`),
     без `box-shadow` и `backdrop-filter`;
   - `#login-btn`, `#kick-login-sidebar-btn` → вид `btn-secondary` (фон
     `--bg-control`, текст `--text-primary`) + цветная точка 8 px слева через
     `::before` цветом платформы. В фазе 2 они переедут в поповер.

### 1.3 Шкала текста: 6 размеров, 4 веса

`tokens.css`:

| токен | было | станет | для чего |
|---|---|---|---|
| `--font-xs` | 11 | 11 | бейджи, подписи секций |
| `--font-sm` | 12 | 12 | мета: канал, игра, время |
| `--font-md` | 13 | 13 | основной текст, названия |
| `--font-lg` | 16 | 15 | заголовки панелей |
| `--font-xl` | 20 | 22 | заголовок раздела |
| `--font-2xl` | 24 | 28 | редкие крупные цифры (статистика) |

Миграция: `--font-2xs` (10, 6 мест) → `--font-xs`; `--font-base` (14, 4
места) → `--font-md` или `--font-lg` по смыслу; `--font-3xl` не используется →
удалить. Сырые значения: `8px`, `9px` → `--font-xs` (бейдж 11/600 uppercase с
`letter-spacing: .04em` читается лучше, чем 9/800); `15px`, `16px`, `17px` →
`--font-lg`; `22px`, `24px` → `--font-xl`; `28px` → `--font-2xl`.

Веса: оставить `400`, `500`, `600`, `700` (700 — только заголовки разделов и
крупные цифры). `750` и `800` → `600`. Пройдись по `700` (39 мест): в
названиях каналов, кнопках, бейджах, счётчиках → `600`, в заголовках
модалок и разделов оставить `700`.

Добавь токены весов `--weight-regular/medium/semibold/bold` и используй их.

### 1.4 Отступы на сетке 4 px и радиусы

Новая шкала в `tokens.css`: `--space-4`, `--space-8`, `--space-12`,
`--space-16`, `--space-20`, `--space-24`, `--space-32`, `--space-40`,
`--space-48`.

Миграция старых шагов (решай по контексту, смотри скрин после каждого
файла):

| старый | использований | куда |
|---|---|---|
| `--space-1` (1px) | 3 | 1 px допустим только для полосок — замени литералом `1px` с комментарием или на `--space-4` |
| `--space-2` (2px) | 13 | `--space-4` (или оставь `2px` литералом в зазорах сегментов/иконок) |
| `--space-6` | 28 | `--space-4` или `--space-8` |
| `--space-10` | 18 | `--space-8` или `--space-12` |
| `--space-14` | 18 | `--space-12` или `--space-16` |

После миграции удали `--space-1/2/6/10/14` из `tokens.css`. Затем переведи
сырые `padding`/`margin`/`gap` в `components/*.css` (≈127 мест) на токены.

Радиусы: `--radius-sm 6`, `--radius-md 10`, `--radius-lg 14`,
`--radius-full`. `--radius-xl` (20, 4 места) → `--radius-lg`, удалить. Сырые
`2px/3px/4px` → `--radius-sm` (для полосок-индикаторов допустим `1px`/`2px`
литералом), `20px/24px` → `--radius-lg`.

Когда меняешь `#platform-tabs`, `.segmented`, `.platform-tab` — радиус
внутреннего элемента = радиус контейнера минус padding (`calc(var(--radius-md) - 2px)`
уже так сделан, сохрани принцип).

### 1.5 Убрать лишние эффекты

1. `layout.css`, `#app`: удалить `animation: mesh-drift`, `background-size:
   200% 200%`, оба `radial-gradient`, весь `#app::before` (шум). Фон —
   `var(--bg-base)`. Удалить `@keyframes mesh-drift` из `animations.css`,
   токены `--app-noise`, `--glass-content` (и его использование в `#content`),
   `--glass-sidebar`.
2. `--btn-primary-bg` и `--btn-primary-bg-hover` (12 использований) → сплошные:
   `var(--accent)` и `hsl(var(--accent-h) var(--accent-s) calc(var(--accent-l) + 6%))`.
3. `--shadow-glow-accent` (12 использований) убрать из всех правил. Сам токен
   удалить. Для выделения хватает `--border-accent`.
4. `backdrop-filter`: оставить только на парящих слоях поверх контента —
   `#settings-overlay`/модалки, `#context-menu`, `#group-context-menu`,
   `#palette-overlay`/`#palette-modal`, тосты, `#sidebar-tooltip`,
   `.uptime-badge` и другие чипы поверх видео/превью, контролы слотов
   мультистрима. Убрать с `#toolbar`, `#toolbar-platform-chips`,
   `#player-bar`, `#sidebar`, `.live-badge`, `.platform-badge`. Поверхности
   под ними сделай непрозрачными (`--bg-surface` / `--bg-base`).
5. Ховер `.stream-card`: убрать `transform: translateY(-4px)`,
   `.card-thumb::before` (радиальный блик) целиком, смену `border-color` и
   `box-shadow`. Оставить `filter: brightness(1.05)` превью и `scale(1.02)`
   вместо `1.04`. Сам `box-shadow: var(--shadow-card)` у карточки в покое
   убрать (в фазе 3 рамки не станет совсем).
6. Бесконечные анимации: оставить скелетоны/спиннеры/лоадеры (`skeleton.css`,
   `spin`, `loader-slide`, `shimmer-card`), `#record-dot` и `#live-dot` в
   плеер-баре. Сделать статичными: `.channel-item.watching .live-dot`,
   `.live-badge::before`, пульс в `chat.css` и `settings.css`. `spotlight-pulse`
   в `.drop-indicator` и онбординге оставить (они временные по смыслу).

### 1.6 Тест-страж для CSS

Новый `tests/test_css_tokens.py`. Переиспользуй парсер правил из
`tools/css_ownership.py` (импортируй `iter_rules` или вынеси общую функцию,
не копируй). Проверки для `ui/css/components/*.css` и `layout.css`:

1. Нет сырых `px` в `font-size`, `border-radius`, `gap`, `padding`, `margin`,
   `font-weight` вне шкалы. Allowlist значений: `0`, `1px`, `2px` (только
   `border-radius` полосок и зазоры сегментов — перечисли селекторы явно),
   `50%`, `auto`, `inherit`.
2. `backdrop-filter` встречается только у селекторов из явного allowlist
   (список из 1.5.4).
3. У `#app` нет `animation`.
4. Уникальных значений `font-weight` не больше четырёх.
5. `--shadow-glow-accent`, `--app-noise`, `--glass-content` не встречаются.

Сообщения об ошибках — с файлом, селектором и значением, чтобы следующий
человек понял, что поправить.

### 1.7 Светлая тема отдельным проходом

Пройди светлую тему по скринам всех сценариев. Это не инверсия тёмной:
- тени слабее (`--shadow-*` с альфой 0.06–0.12), разделители заметнее;
- `--surface-card` / `--surface-card-hover` — плоские цвета, без градиентов;
- проверь Kick-глифы и бейджи на белом (`--platform-kick-on-light`);
- `--thumb-overlay` в светлой теме не светлее тёмной: превью — это видео,
  оно тёмное в обеих темах.

## Чего не делать

- Не менять HTML-структуру, не удалять элементы, не переносить контролы: это
  фаза 2.
- Не переделывать компоненты (карточку, строку сайдбара) по новому образцу:
  это фаза 3.
- Не трогать JS, кроме случаев, когда JS выставляет инлайн-цвет, который
  противоречит шагу 1.2. Такие места перечисли в PR.

## Выход из фазы

- [ ] `make check` зелёный, включая новый `test_css_tokens.py` и неизменённые
      тесты контраста.
- [ ] `css_ownership` → 0.
- [ ] Скрины `.preview/` сравнены с `.preview-before/` по всем сценариям:
      раскладка та же, интерфейс тише. В PR — пары «до/после» для `grid`,
      `player`, `settings`, `welcome` в обеих темах.
- [ ] В PR чек-лист для мака: визуальная проверка обеих тем; замер GPU в
      Activity Monitor за минуту воспроизведения до и после (ожидаем
      снижение из-за удаления `mesh-drift` и `backdrop-filter`).
