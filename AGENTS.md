# AGENTS.md — TwitchX

TwitchX — мультиплатформенный клиент прямых трансляций для macOS. pywebview + WebKit WebView, опрашивает Twitch/Kick/YouTube API, воспроизводит через AVPlayer или IINA/mpv.

---

## Команды

```bash
make run     # uv run python main.py
make debug   # + TWITCHX_DEBUG=1
make lint    # ruff check . && pyright .
make fmt     # ruff format .
make test    # uv run pytest tests/ -v
make check   # lint + test
```

Если `uv` недоступен: `.venv/bin/python -m pytest tests/ -q`

---

## Как работать с этим проектом

### Перед тем как писать код

1. Запусти `make lint` — убедись, что текущий код чистый
2. Для JS-изменений: файлы в `ui/js/` — **всегда `const TwitchX = window.TwitchX;`**, никогда `var` (ломает inline merge в pywebview)
3. Для новых Python-модулей: добавь в `core/`, унаследуй от существующего base class

### После изменений

- Запусти `make check` перед финализацией
- Если трогал `ui/js/` или `ui/css/` — запусти приложение и проверь визуально (тесты не покрывают JS)
- Если добавил новый Python-модуль — напиши тесты в `tests/`

### Чего не делать

- **Не блокировать main thread** — весь I/O в `threading.Thread`
- **Не писать `style.display` в JS** — используй `classList.toggle('hidden')`
- **Не использовать persistent inline-стили в JS** (`style.cssText`, `style.color`, `style.opacity`, `style.background`) — используй CSS-классы и CSS-переменные; исключение: эфемерные стили при drag/resize и динамические CSS-переменные (`--chat-width`, `--author-color`)
- **Не читать конфиг напрямую в фоновом треде** — используй локальный `config = load_config()`
- **Не использовать `_effective_creds()` bypass** — все проверки credentials только через него
- **Не lower-case YouTube channel IDs** (`UCxxxx…`) — они case-sensitive везде
- **Не сравнивать UI-каналы только по `login`** — для Twitch/Kick/YouTube используй compound key `platform:login`
- **Не добавлять `innerHTML` с user data** — только `createElement` + `textContent`
- **Не вызывать AppKit/AVKit вне main thread** — через `AppHelper.callAfter()`

---

## Структура проекта

| Path | Что делает |
|------|-----------|
| `main.py` | Точка входа, логирование (`RotatingFileHandler` 5MB×2) |
| `app.py` | `TwitchXApp` — окно pywebview, инлайнит CSS/JS из `ui/` |
| `core/platforms/` | `TwitchClient`, `KickClient`, `YouTubeClient` |
| `core/chats/` | `TwitchChatClient`, `KickChatClient`, `YouTubeChatClient` |
| `core/storage.py` | Config v2, миграции, avatar cache |
| `core/constants.py` | Все константы |
| `core/credentials.py` | Bundled OAuth fallback |
| `core/watch_stats.py` | SQLite-трекер статистики просмотров |
| `core/stream_resolver.py` | `resolve_hls_url(url, platform_client, quality)` |
| `core/launcher.py` | IINA/mpv launch |
| `core/recorder.py` | Запись стрима через streamlink |
| `ui/api/` | Python↔JS bridge (7 компонентов, см. ниже) |
| `ui/index.html` | Shell, pywebview 6.x требует inline ресурсов |
| `ui/css/` | `tokens`, `reset`, `layout`, `components`, `views`, `player` |
| `ui/js/` | 18 модулей (IIFE + `TwitchX` namespace) |
| `tests/` | pytest, `conftest.py` с фикстурами |

---

## Архитектура

### Data flow

```
JS: pywebview.api.method()
        ↓
TwitchXApi (ui/api/__init__.py)
        ↓
threading.Thread → asyncio.new_event_loop() → httpx → API
        ↓
_eval_js('window.onCallback(data)')
        ↑
JS: window.onCallback = function(data) { ... }
```

### Иерархия классов

```
PlatformClient (ABC)  ←  BasePlatformClient  ←  TwitchClient/KickClient/YouTubeClient
ChatClient (ABC)      ←  BaseChatClient      ←  TwitchChatClient/KickChatClient/YouTubeChatClient
```

### API Bridge компоненты (`ui/api/`)

| Модуль | Класс | Что делает |
|--------|-------|-----------|
| `__init__.py` | `TwitchXApi` | Оркестратор, делегирует компонентам |
| `_base.py` | `BaseApiComponent` | `_eval_js`, `_run_in_thread` |
| `auth.py` | `AuthComponent` | OAuth login/logout, тесты подключения |
| `favorites.py` | `FavoritesComponent` | add/remove/reorder, import follows |
| `data.py` | `DataComponent` | polling, browse, channel profiles |
| `streams.py` | `StreamsComponent` | watch, watch_direct, watch_media, multistream |
| `chat.py` | `ChatComponent` | чат, эмодзи, мод-инструменты |
| `images.py` | `ImagesComponent` | аватарки, тамбнейлы |

---

## Как добавлять новое

### Новый Twitch API endpoint
1. Async метод в `TwitchClient` (`core/platforms/twitch.py`)
2. Вызов в `DataComponent._async_fetch` (`ui/api/data.py`)
3. Результат через `self._eval_js(f"window.onNewCallback({json.dumps(data)})")`
4. Обработчик `window.onNewCallback = function(data) {...}` в `callbacks.js`

### Новый JS-модуль
1. Создай `ui/js/mymodule.js` с шаблоном:
   ```js
   (function() {
     const TwitchX = window.TwitchX;
     // ... код ...
   })();
   ```
2. Добавь `<script src="ui/js/mymodule.js"></script>` в `ui/index.html` в правильном месте порядка загрузки
3. Порядок: `state → utils → view-transitions → icons → api-bridge → render → sidebar → player → multistream → browse → channel → chat → settings → context-menu → keyboard → palette → toast → callbacks → init`

### Новый UI компонент
1. HTML в `ui/index.html`
2. Стили через CSS custom properties из `tokens.css`
3. JS в подходящем модуле или новом (если большой)
4. Python-метод в `TwitchXApi` если нужны данные

### Новый config ключ
1. Добавь дефолт в `DEFAULT_CONFIG` в `storage.py`
2. Merge-on-load подхватит автоматически, обратная совместимость обеспечена

### Новый тест
```python
def test_my_feature(temp_config_dir, run_sync, capture_eval_js):
    api = TwitchXApi()
    api._eval_js = capture_eval_js
    api.my_method("arg")
    capture_eval_js.assert_any("onSomething")
```

---

## Критические правила

### pywebview 6.x
- `_inline_resources()` в `app.py` мержит все JS в **один** `<script>` блок
- Каждый модуль **обязан** начинаться с `const TwitchX = window.TwitchX;` — не `var`, не `window.TwitchX.X = ...` напрямую
- `var` → `SyntaxError: Identifier 'TwitchX' has already been declared` — ломает всё приложение

### Watch methods — выбирай правильный
| Ситуация | Метод |
|----------|-------|
| Канал из live grid/sidebar, когда известна платформа | `watch_platform(channel, platform, quality)` |
| Старый Twitch-only fallback | `watch(channel, quality)` |
| Канал из Browse (нет в live cache) | `watch_direct(channel, platform, quality)` |
| Внешний плеер, когда известна платформа | `watch_external_platform(channel, platform, quality)` |
| VOD/clip | `watch_media(url, quality, platform, channel, title, with_chat)` |
| Мультистрим слот | `add_multi_slot(slot_idx, channel, platform, quality)` |

### Credentials
- Все проверки через `_effective_creds()` (config → bundled fallback)
- Twitch `exchange_code` требует `client_secret` в POST body (RFC 6749 §4.1.3)

### Platform identity
- YouTube `UCxxxx…` IDs — **case-sensitive везде**, никогда `.lower()`
- Compound key в UI: всегда `TwitchX.channelKey(login, platform)` → `"platform:login"`
- `favorites_meta` использует `"platform:login"`, JS — `TwitchX.getFavoriteMeta(login, platform)`
- Для списков избранного используй `TwitchX.getFavoriteEntries()`, а не `state.favorites` напрямую, если важна платформа
- Для live/cache/selection/watching state используй `selectedChannelKey`, `watchingChannelKey`, `liveSet` с compound key
- DOM-элементы каналов должны иметь `data-key="platform:login"` и `data-platform`, `data-login` оставляй только как совместимый raw login
- `avatars`, `thumbnails`, `prevViewers` в JS индексируются по compound key, чтобы одинаковые логины на разных платформах не смешивались
- `TwitchX.getChannelPlatform(login, key)` и `TwitchX.findStreamByKey(key)` — основные helpers для восстановления платформы в UI
- Kick `channel_id` — integer в raw API, всегда `str()` при нормализации

### Config robustness
- `load_config()` должен переживать пустой/битый JSON: логировать warning, восстанавливать defaults и не падать
- `save_config()` не должен ронять приложение при `OSError`/permission errors: логировать error
- Settings с числовыми defaults (`refresh_interval`, `player_height`, etc.) должны приводиться обратно к `int`; невалидные строки откатываются к default
- Новый config key добавляй в `DEFAULT_CONFIG`/`DEFAULT_SETTINGS`; merge-on-load и type coercion должны сохранить обратную совместимость

### Async safety
- `_loop_clients` ключ `(loop, PLATFORM_ID)` — изоляция платформ
- `token_expires_at` сравнивать с `time.time()` (wall clock), не monotonic
- `_async_run` → `_close_thread_loop(loop)` в `finally` (не bare `loop.close()`)
- `stop_chat`: `self._chat_client = None` **перед** async disconnect

### Visibility в JS
- `.hidden` (`classList.add/remove/toggle`) — для большинства элементов
- `.visible` / `.menu-visible` — для элементов с CSS opacity transition (search-dropdown, context-menu)
- View transitions: `opacity: 0` **до** изменения `display`, иначе микро-вспышка

### Multistream
- Показывать slot: `classList.remove('hidden')`, не `style.display = 'block'`
- WKWebView играет audio даже когда parent `display: none` — никогда `style.display = ''`

---

## Тестирование

### Фикстуры (`tests/conftest.py`)

| Fixture | Что делает |
|---------|-----------|
| `temp_config_dir` | Временная директория вместо `~/.config/twitchx/` |
| `config_with_twitch_auth` | То же + Twitch OAuth tokens |
| `mock_twitch_client` | `MagicMock` + `AsyncMock` |
| `capture_eval_js` | Перехватывает `_eval_js()` вызовы, `capture.assert_any(fragment)` |
| `run_sync` | `_run_in_thread` → синхронное исполнение |

### Запуск

```bash
make test                              # все тесты
uv run pytest tests/test_api.py -v    # один файл
uv run pytest -k "test_watch" -v      # по имени
.venv/bin/pyright --pythonpath .venv/bin/python .  # типы
```

---

## Частые баги и где искать

| Симптом | Где смотреть |
|---------|-------------|
| Приложение не стартует после JS-изменений | `var` вместо `const` в новом модуле → `SyntaxError` |
| Одинаковые логины Twitch/Kick/YouTube смешиваются | `ui/js/state.js`, `sidebar.js`, `render.js`, `callbacks.js` — ищи сравнения/cache по `login` вместо `platform:login` |
| YouTube стримы пропадают после логина | `data.py` — использует `_effective_creds()`? Не прямое чтение конфига? |
| Видео зависает после 30+ мин | `player.js`: `gentleResetVideo`, health monitors, proactive reset |
| Fullscreen сам выходит | `isVideoFullscreen()` guard в `gentleResetVideo` → `softResetVideo` |
| Чат не очищается | `clearChatBatch()` в `onStreamReady`, `hidePlayerView`, `switchMultiChat`? |
| Watch stats остаётся с `ended_at NULL` | `_start_watch_session()` под `_active_watch_lock` завершает предыдущую? |
| Token refresh не работает | `time.time()` или monotonic? `_loop_clients` ключ с `PLATFORM_ID`? |
| Browse пустой | YouTube quota? Browse cache TTL 10 мин? `load_config()` локальный в треде? |
| VOD запускает live / падает offline | `watch_media()` передаёт `url`, не `channel`, в `resolve_hls_url()` |
| httpx клиенты утекают | `_close_thread_loop(loop)` в `finally`? Не bare `loop.close()`? |
