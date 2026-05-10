# AGENTS.md — TwitchX Project Context

TwitchX — мультиплатформенный клиент прямых трансляций для macOS. Однооконное pywebview-приложение с нативным WebKit WebView. Опрашивает API Twitch, Kick и YouTube; воспроизводит стримы через нативный AVPlayer или IINA (fallback).

---

## 1. At a Glance

### Dev Commands

```bash
make run     # запуск (uv run python main.py)
make debug   # запуск с TWITCHX_DEBUG=1 (логирование httpx)
make lint    # ruff check . && pyright .
make fmt     # ruff format .
make test    # uv run pytest tests/ -v
make check   # lint + test (перед коммитом)
```

Запуск одного файла: `uv run pytest tests/test_app.py -v`

Покрытие: `make cov` (терминал) или `make cov-html` (`htmlcov/`).

Если `uv` недоступен в `PATH`, используй локальное окружение:
```bash
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m ruff check .
.venv/bin/pyright --pythonpath .venv/bin/python .
```

### Directory Map

| Path | Что находится | Зачем агенту знать |
|------|---------------|-------------------|
| `main.py` | Точка входа | Запускает `TwitchXApp` |
| `app.py` | `TwitchXApp` | Создаёт `TwitchXApi` + окно pywebview |
| `core/platforms/` | TwitchClient, KickClient, YouTubeClient | Наследуют `BasePlatformClient` → `PlatformClient` |
| `core/chats/` | TwitchChatClient, KickChatClient, YouTubeChatClient | Наследуют `BaseChatClient` → `ChatClient` |
| `core/third_party_emotes.py` | BTTV/FFZ/7TV emote fetcher + disk cache | `fetch_channel_emotes()` для Twitch чата |
| `core/storage.py` | Config v2, миграции, DEFAULT_CONFIG | Все операции с `~/.config/twitchx/` |
| `core/constants.py` | Общие константы | TTL кэша, порты OAuth, размеры изображений, watch_stats |
| `core/watch_stats.py` | `WatchStatsDB` — SQLite-трекер статистики просмотров | start_session/end_session, daily_summary, get_top_channels, err-handled |
| `core/stream_resolver.py` | `resolve_hls_url()` | Принимает `PlatformClient` instance, опциональные `extra_args` для streamlink |
| `core/launcher.py` | `launch_stream()`, `launch_stream_mpv()` | Принимает `PlatformClient` instance, поддержка IINA и mpv |
| `core/recorder.py` | `Recorder` — менеджер записи стримов | start/stop/state_dict через streamlink subprocess |
| `ui/api/` | Python↔JS bridge (7 модулей) | См. §5 |
| `ui/index.html` | Shell (~414 строк) | pywebview 6.x требует inline ресурсов |
| `ui/css/` | 6 CSS-модулей | См. §3.1 |
| `ui/js/` | 14 JS-модулей | См. §3.2 |
| `tests/` | Pytest suite | `conftest.py` с фикстурами |

---

## 2. Architecture Overview

### Entry Points & Data Flow

```
main.py → app.py (TwitchXApp)
              ↓
        TwitchXApi  ←———  pywebview.api.<method>()
              ↓                  ↑
    threading.Thread      window.evaluate_js('window.onCallback(data)')
              ↓
    asyncio.new_event_loop()
              ↓
        httpx.AsyncClient  →  Twitch/Kick/YouTube APIs
```

**Правило:** весь сетевой I/O — в `threading.Thread` с отдельным `asyncio` event loop. Результаты пушатся в JS через `_eval_js(code)`. `_shutdown` (`threading.Event`) защищает все вызовы `_eval_js` из фоновых потоков при закрытии окна.

### Class Hierarchy

**Platform Clients**
```
PlatformClient (ABC)          ← core/platform.py
    ↑
BasePlatformClient            ← core/platforms/base.py
    ↑
TwitchClient / KickClient / YouTubeClient
```

**Chat Clients**
```
ChatClient (ABC)              ← core/chat.py
    ↑
BaseChatClient                ← core/chats/base.py
    ↑
TwitchChatClient / KickChatClient / YouTubeChatClient
```

### Config & Storage

- **Путь:** `~/.config/twitchx/config.json` (v2 nested format).
- **Watch Statistics DB:** `~/.config/twitchx/watch_stats.db` (SQLite).
- **Корневые ключи:** `platforms.{twitch,kick,youtube}`, `settings`, `favorites`.
- **Favorites:** список `{login, platform, display_name}`.
- **Миграция:** v1 flat config → v2 автоматически при первой загрузке.
- **Merge-on-load:** недостающие ключи заполняются из `DEFAULT_CONFIG`, приложение никогда не падает на устаревшем формате.
- **Новые ключи settings:** `low_latency_mode` (bool), `external_player` ("iina"|"mpv"), `mpv_path` (str), `recording_path` (str), `chat_filter_sub_only` (bool), `chat_filter_mod_only` (bool), `chat_anti_spam` (bool), `chat_block_list` (list[str]).
- **`save_settings()`** — сохраняет только присутствующие в `parsed` ключи. Пустые строки очищают credential-поля (client_id, client_secret, api_key). Ранее игнорировались через `if new_value:` guard.
- **Важно:** из фоновых потоков используйте **локальный** `config = load_config()`, никогда не записывайте в `self._config` из треда (race condition с polling thread).

---

## 3. Frontend Reference (ui/)

### 3.1 CSS Decomposition

| File | Зона ответственности |
|------|---------------------|
| `tokens.css` | CSS custom properties (`:root`) |
| `reset.css` | Base resets, scrollbar, accessibility media queries |
| `layout.css` | `#app`, `#main`, `#sidebar`, `#content`, `#toolbar` |
| `components.css` | Buttons, inputs, cards, badges, sidebar sections, chat messages |
| `views.css` | `#player-view`, `#browse-view`, `#channel-view`, `#multistream-view` |
| `player.css` | `#player-bar`, `#chat-panel`, `#chat-resize-handle`, `#live-dot`, PiP button active states |

**Containment:** `#player-view`, `#player-content`, `#chat-panel` имеют `contain: layout style paint` для изоляции пересчётов от видео-композитинга.

### 3.2 JS Module Dependency & Load Order

Все модули — IIFE + `TwitchX` namespace. Нет глобалов, кроме `window.on*` callbacks.

Порядок загрузки:
```
state → utils → api-bridge → render → sidebar → player → multistream → browse → channel → chat → settings → context-menu → keyboard → callbacks → init
```

| File | Ответственность |
|------|-----------------|
| `state.js` | `TwitchX.state`, `TwitchX.multiState`, shortcuts, chat state, `TwitchX.getFavoriteMeta(login)` — helper для поиска меты по bare login в compound-ключевом `favoritesMeta` |
| `utils.js` | `truncate`, `formatViewers`, `formatUptime`, `setStatus` |
| `api-bridge.js` | `pywebviewready`, `TwitchX.api`, profile helpers |
| `render.js` | `renderGrid`, `createStreamCard`, `createOnboardingCard` |
| `sidebar.js` | `renderSidebar`, diff-based updates, layout logic |
| `player.js` | Video lifecycle, health monitors, fullscreen, gentle reset, recording toggle, stats overlay, VOD time display |
| `multistream.js` | Slot management, audio/chat focus, health monitor |
| `browse.js` | `showBrowseView`, breadcrumb nav (`Following > Browse > Category`), category/top-stream loading |
| `channel.js` | `showChannelView`, tabs, media cards, follow/watch actions |
| `chat.js` | `submitChatMessage`, `renderChatEmotes`, reply handling, chat filters, log export, emote picker, user list |
| `settings.js` | `openSettings`, `saveSettings`, connection tests |
| `context-menu.js` | `showContextMenu`, `showSidebarContextMenu` |
| `keyboard.js` | `handleKeydown`, shortcut rebinding, hotkeys (player + multistream scopes), duplicate-key confirm-swap |
| `callbacks.js` | Все `window.on*` — thin proxies к `TwitchX.*`, chat batching (`flushChatBatch`), `_shouldFilter`, `_hasBadge`, `onThirdPartyEmotes`, `onChatUserList`, `onChatModeChanged` |
| `init.js` | `DOMContentLoaded`, `_bind*()` wiring, uptime interval |

**pywebview 6.x Constraint:** модули не загружаются через отдельные `<script src="...">`. `app.py._inline_resources()` мержит все JS в **один** inline `<script>` блок и CSS в inline `<style>`. Только `state.js` содержит `window.TwitchX = window.TwitchX || {};`, остальные используют `const TwitchX = window.TwitchX;`.

### 3.3 Video Player Lifecycle (Player.js)

**Единый источник правды.** Все методы — свойства `window.TwitchX`.

#### Video Element Abstraction
- `TwitchX._playerVideo` — текущий живой `<video>` элемент.
- `TwitchX.getPlayerVideo()` — единая точка доступа. Никогда не кешируй `document.getElementById('stream-video')`.
- `hidePlayerView()` уничтожает старый `<video>` и вставляет свежий пустой элемент через `insertBefore(fresh, firstChild)` (сохраняет порядок DOM: video → handle → chat).

#### Gentle Reset (Crossfade Swap)
`gentleResetVideo(reason)` — основной способ сброса HLS-буфера:
1. Создаёт **shadow `<video>`** (`position:absolute`, `opacity:0`) через `insertBefore(newVideo, oldVideo)`.
2. Новый DOM-нод заставляет WKWebView создать свежий `MediaPlayer`.
3. Shadow video грузит тот же HLS `src` в mute.
4. По событию `playing` / `loadeddata` (или fallback 2.5 с) — CSS crossfade 150 мс.
5. Старый video: `pause() → removeAttribute('src') → load() → remove()`.
6. Shadow video становится активным (`_playerVideo = newVideo`).

**Guard'ы:**
- Если `isVideoFullscreen(oldVideo)` → вызывает `softResetVideo(reason)` и возвращает (fullscreen привязан к DOM-ноду, gentle reset убьёт его).
- Если `isVideoPiP(oldVideo)` → вызывает `softResetVideo(reason)` и возвращает (PiP аналогично привязан к DOM-ноду).
- `_gentleResetInProgress` + `_gentleResetTimer` — отменяет предыдущий pending reset при повторном вызове.
- `_playerVideo = null` выставляется **сразу** в начале, предотвращая re-entrancy.

#### Soft Reset (Same-DOM)
`softResetVideo(reason)` — для случаев, когда нельзя уничтожать DOM-нод (fullscreen):
- `pause → src = '' → load() → restore src/muted/volume → play()`.
- Не создаёт новый MediaPlayer, поэтому back-buffer может частично сохраниться.
- `_softResetInProgress` guard сбрасывается через `setTimeout(..., 100)`.

#### Fullscreen Detection & Toggle
`isVideoFullscreen(video)`:
- Проверяет `document.fullscreenElement` / `document.webkitFullscreenElement` через `.contains(video)` (не глобально!).
- Проверяет `video.webkitPresentationMode === 'fullscreen'` (Safari Video Presentation Mode в WKWebView).

`toggleVideoFullscreen()`:
- Early return если `getPlayerVideo()` вернул `null` (защита от race при recursive call после PiP exit).
- Вход: `video.webkitEnterFullscreen()` или `video.requestFullscreen()`.
- Выход: `video.webkitSetPresentationMode('inline')`, fallback на `document.webkitExitFullscreen()` / `video.webkitExitFullscreen()`.
- **PiP guard:** если `isVideoPiP(video)` — вызывает `togglePiP(video)` и через 50 мс рекурсивно вызывает себя (WebKit должен выйти из PiP до входа в fullscreen).

#### PiP Detection & Safety
`isVideoPiP(video)`:
- Проверяет `video.webkitPresentationMode === 'picture-in-picture'`.
- Проверяет `document.pictureInPictureElement === video`.

`togglePiP(video)`:
- WebKit path: `webkitSetPresentationMode('picture-in-picture' / 'inline')`.
- W3C fallback: `requestPictureInPicture()` / `exitPictureInPicture()`.

**Guards:**
- `gentleResetVideo`: если `isVideoPiP(oldVideo)` → `softResetVideo(reason)` (не уничтожать DOM-нод в PiP).
- `hidePlayerView`: перед `video.remove()` вызывает `togglePiP(video)` (иначе нативное PiP окно крашится).
- `_reloadMultiSlot`: аналогичный guard для `.ms-video` (soft reset при PiP/fullscreen).
- `_clearMultiSlot`: перед `video.remove()` выходит из PiP (`togglePiP`) — иначе краш нативного окна.

**Events:**
- `_bindPiPEvents(video)` добавляет `enterpictureinpicture`, `leavepictureinpicture`, `webkitpresentationmodechanged`.
- Обновляет `#pip-player-btn.active` и `.ms-pip-btn.active`.
- Вызывается при создании свежего video в `hidePlayerView`, при swap в `gentleResetVideo.doSwap`, и в `showPlayerView` если флаг `_pipEventsBound` отсутствует.
- **Multistream:** `_bindSlotPiPEvents(video, pipBtn)` — отдельная helper-функция в `multistream.js`, привязывает `webkitpresentationmodechanged` к `.ms-video` и обновляет `.ms-pip-btn.active`. Вызывается при создании слота, после `_reloadMultiSlot`, и после `_clearMultiSlot` (при создании нового video).

#### Health Monitors
- **`checkVideoHealth()`** — каждые 60 с:
  - Live-edge drift: `currentTime` отстаёт от `seekable.end` на >120 с → `seekTo(liveEdge)`.
  - Buffer accumulation: `buffered.end - currentTime > 180` с → `gentleResetVideo('buffer-overflow')`.
- **`checkFrozenVideo()`** — каждые 10 с:
  - Если `currentTime` не изменился 10 с при `!paused && readyState >= 2` → `gentleResetVideo('frozen')`.
- **FPS Monitor** — `requestAnimationFrame` loop:
  - Пропускает замер при `document.hidden`, `paused`, `readyState < 2`.
  - Порог: кадр >66 мс (<15 FPS) **подряд** ~5 с → `gentleResetVideo('fps')`.
- **Proactive Reset** — `gentleResetVideo('proactive')` каждые 30 мин (self-rescheduling `setTimeout`).

**Все reset-пути логируют:** `console.log('[VideoHealth]', reason, src, currentTime)`.

#### Race Safety
- `hidePlayerView()` при active gentle reset: отменяет таймер, удаляет shadow video, чистит `_gentleReset*` flags.
- Event delegation для dblclick на `#player-content` вместо прямого `video.addEventListener` — переживает recreation.

#### VOD Mode
Когда стрим запущен через `watch_media()` (VOD, clips), плеер входит в VOD mode:
- `stream_type: "vod"` передаётся в `onStreamReady` → `TwitchX.state.streamType = 'vod'`.
- Health monitors (live-edge drift, buffer accumulation, frozen, FPS, proactive reset) **отключаются** — они рассчитаны на live HLS, не на seekable VOD.
- Включается `startVodTimeDisplay()` — `setInterval(1 с)` обновляет `#vod-time-display` в формате `currentTime / duration`.
- `formatVideoTime()` форматирует секунды в `HH:MM:SS` или `MM:SS`.
- **Guard:** при переключении VOD↔Live без закрытия плеера, `showPlayerView()` безусловно останавливает все мониторы/таймеры (`stopVodTimeDisplay`, `stopVideoHealthMonitor`, ...) перед ветвлением на `streamType`. Это предотвращает orphaned timers (VOD-таймер при Live и health-мониторы при VOD).

#### Stream Recording
- `core/recorder.py` — `Recorder` класс управляет одним `streamlink ... --output file.ts` subprocess.
- `Recorder.start(stream_url, channel, output_dir)` — создаёт папку, формирует имя `twitchx_{channel}_{timestamp}.ts`, запускает subprocess.
- `Recorder.stop()` — `proc.terminate()` + сброс состояния.
- `Recorder.state_dict()` → `{active, filename, elapsed}` — для JS callback.
- Кнопка `#record-btn` в `#player-header-actions` (показывается при `showPlayerView()`).
- `#record-dot` в `#player-bar` — пульсирующий индикатор активной записи.
- Файлы по умолчанию сохраняются в `~/Movies/TwitchX/` (настраивается в Settings → Recording Directory).
- При закрытии плеера или остановке стрима запись автоматически останавливается.

#### Stream Stats Overlay
- Toggleable панель `#stats-overlay` в правом верхнем углу player-content.
- Показывает: Latency (отставание от live edge), Buffer (буфер впереди), Dropped (дропнутые кадры с baseline), Resolution (videoWidth×videoHeight).
- `updateStatsOverlay()` — rAF + setTimeout(500ms) цикл. Автоматически приостанавливается при скрытой странице (rAF не срабатывает).
- Baseline dropped frames сбрасывается при показе оверлея через `getVideoPlaybackQuality()`.
- Кнопка `#stats-overlay-btn` в `#player-header-actions`.

### 3.4 Sidebar Lifecycle (Sidebar.js)

**Diff-based rendering** — полная перестройка заменена на in-place updates:
- `renderSidebar()` сравнивает текущий и новый набор `login` для Online/Offline секций.
- Если состав не изменился → `updateSidebarItem()` обновляет только текст/classes/src.
- Если состав изменился → перестраивается только затронутая секция.
- `applySidebarLayout()` отложен через `requestAnimationFrame`.
- `updateSidebarItem()` обновляет `aria-label` и кеширует `dataset._lastViewers`.

### 3.5 Chat Lifecycle (Chat.js + Callbacks)

**Batching:**
- Лимит сообщений: **150** (не 500).
- Входящие сообщения собираются 50 мс, затем flush одним `DocumentFragment`.
- `clearChatBatch()` экспортирован как `TwitchX.clearChatBatch`. **Обязательно** вызывать при:
  - `clearChatMessages()`
  - `hidePlayerView()`
  - `switchMultiChat()`
  - `onChatStatus(connected=true)`
  - `window.onStreamReady()` (чтобы старые сообщения не висели под новым заголовком)

**Filters & Anti-Spam:**
- Четыре фильтра в `TwitchX.chatFilters`: `subOnly`, `modOnly`, `antiSpam`, `blockList`.
- `_shouldFilter(msg)` в `flushChatBatch()` IIFE — последовательные проверки:
  - `is_system` → пропустить (never filtered).
  - subOnly/modOnly → проверка через `_hasBadge(msg, prefix)`.
  - blockList → `msg.text.toLowerCase().indexOf(word)`.
  - antiSpam → дубликат текста от того же автора (через `TwitchX.chatSpamMap`) + CAPS-рейт >70%.
- `chatSpamMap` очищается в `clearChatMessages()` при смене канала.
- `chatBlockList` обрезается до 100 слов, каждое ≤50 символов, `.strip().lower()` на Python side.
- Фильтр-панель `#chat-filter-panel` с чекбоксами; `loadChatFiltersFromConfig()` синхронизирует чекбоксы при открытии панели и подключении чата.

**Mention Highlighting:**
- `TwitchX.chatSelfLogin` устанавливается из `status.self_login` (передаётся из `platform_conf.user_login`).
- В `flushChatBatch()`: если `msg.text.toLowerCase().indexOf(selfLogin.toLowerCase()) !== -1`, добавляется CSS class `mention` (жёлтый фон).
- `chatSelfLogin` сбрасывается в `''` при `onChatStatus(connected=false)`.

**Chat Log Export:**
- `TwitchX.chatLog` — кольцевой буфер на 5000 сообщений.
- `_appendChatLog(msg)` — сохраняет `{ts, platform, author, text, badges, is_system}`.
- `exportChatFormat(format)` — скачивание через Blob + `<a download>`; `format='json'` или `'txt'`.
- Имя файла: `twitchx-chat-{channel}-{timestamp}.json/.txt` (спецсимволы заменяются на `_`).
- `chatLog` очищается в `clearChatMessages()`.

**Third-Party Emotes (BTTV/FFZ/7TV):**
- `core/third_party_emotes.py` — `fetch_channel_emotes(channel, twitch_user_id, cache_dir) → {code: url}`.
- Дисковый кэш в `~/.config/twitchx/emotes/` на 1 час.
- `renderChatEmotes(parent, text, emotes)` — word-scanning через `/\S+/g`; для каждого слова проверяет `TwitchX.thirdPartyEmotes`; при совпадении вставляет `<img class="emote">`.
- Пунктуация на границах слова: strip `[^a-zA-Z0-9]` с обеих сторон перед поиском.
- `img.onerror = function() { this.style.display = 'none' }` для битых URL.
- `TwitchX.thirdPartyEmotes = {}` сбрасывается в `hidePlayerView()`.

**Emote Picker:**
- `#emote-picker` — оверлей с гридом эмодзи и поиском (`#emote-search`).
- `buildPickerEmoteList()` → `TwitchX.thirdPartyEmotes`.
- `renderEmotePicker(filter)` — отображает до 200 эмодзи, отсортированных по коду.
- При клике на эмодзи вставляет `${code} ` в `#chat-input` и закрывает picker.
- Picker автоматически закрывается при отправке сообщения (`submitChatMessage`).
- `onThirdPartyEmotes` сбрасывает `_cachedPickerEmotes = null` и перерисовывает picker, если открыт.

**Twitch Chat User List:**
- `TwitchChatClient` — `twitch.tv/membership` CAP; NAMES reply → `parse_names_reply()`; JOIN/PART → `parse_join_part()`.
- `_users: set[str]` — текущий список пользователей в канале.
- `on_user_list(users: list[str])` callback → `window.onChatUserList({count, users})`.
- `#chat-userlist-panel` — панель со списком (до 200), поиск через `#chat-userlist-search`.

**Twitch Moderation Tools:**
- Twitch OAuth scope `moderator:manage:chat_settings` (103).
- `TwitchClient.set_chat_settings(broadcaster_id, moderator_id, ...)` — `PATCH /helix/chat/settings`.
- `ChatComponent.set_chat_mode(mode, value, slow_wait)` — bridge из JS.
- `#chat-mod-panel` — чекбоксы `emote_mode` (`#mod-emote-only`), `slow_mode` (`#mod-slow`), `slow_wait` (`#mod-slow-wait`).
- Кнопка `#chat-mod-btn` показывается **только** если `data.platform === 'twitch'` и `chatSelfLogin` совпадает с `data.channel` (broadcaster check).
- `window.onChatModeChanged(data)` — фидбек об успехе/ошибке.

**Background throttle:** когда `player-view` активен, аватарки/тамбнейлы откладываются через `requestIdleCallback` (timeout 2 с) или пропускаются.

**Python side:**
- `send_chat` → `_send_pool` (`ThreadPoolExecutor(max_workers=2)`), не raw threads.
- `send_chat` принимает `reply_to`, `reply_display`, `reply_body` для echo-рендеринга отправленного сообщения с reply-контекстом.
- `KickChatClient` — дедупликация через LRU `_seen_msg_ids` (3 Pusher alias'а).
- `YouTubeChatClient` — polling-based (liveChatMessages.list), через `asyncio` event loop с `_poll_messages()`.
- `TwitchChatClient` — `twitch.tv/membership` CAP для user list; `parse_names_reply()` / `parse_join_part()`.
- `start_chat()` в `ChatComponent` — ветвится по `platform`; для Twitch запускает фоновый `_fetch_emotes()` тред.
- `stop_chat`: `self._chat_client = None` **перед** dispatch async disconnect (race safety).
- `onChatStatus` в JS gate'ит input на `status.connected && status.authenticated`.
- `save_chat_block_list()` — принимает JSON-массив слов, сохраняет с `.strip().lower()` и лимитом 100×50.
- Multistream чат (`#ms-chat-send-btn`, `#ms-chat-input`) в `init.js` зеркалирует `submitChatMessage()` — читает `TwitchX.chatReplyTo`, передаёт reply-параметры в `send_chat()` и вызывает `clearChatReply()` после отправки. `Escape` на `ms-chat-input` отменяет reply.

---

## 4. Backend Reference (core/)

### 4.1 Platform Client Hierarchy

**BasePlatformClient** (`core/platforms/base.py`) — общая инфраструктура:

| Member | Назначение |
|--------|-----------|
| `PLATFORM_ID` / `PLATFORM_NAME` | `"twitch"` / `"Twitch"` и т.д. |
| `_loop_clients` / `_token_locks` | Кеш `httpx.AsyncClient` и `asyncio.Lock` per-loop, ключ `(loop, PLATFORM_ID)` — изоляция платформ |
| `_get_client()` | Возвращает/создаёт `httpx.AsyncClient` для текущего loop + платформы |
| `_get_token_lock()` | Возвращает/создаёт `asyncio.Lock` для текущего loop + платформы |
| `_platform_config()` | Секция конфига платформы через `get_platform_config()` |
| `_ensure_token()` | Проверка/рефреш user token; сравнивает `token_expires_at` с `time.time()` (wall clock) |
| `_request(method, url, ...)` | HTTP wrapper: 429-retry, 401-refresh, возвращает `httpx.Response` |
| `_check_response_errors(resp)` | Override hook (YouTube: 403 quota exceeded) |
| `_client_headers()` / `_client_timeout()` | Override hooks |

### 4.2 Polymorphic Platform Methods

Реализованы в каждом подклассе (`core/platform.py`):

| Method | Twitch | Kick | YouTube |
|--------|--------|------|---------|
| `sanitize_identifier(raw)` | `sanitize_twitch_login` | `sanitize_kick_slug` | сохраняет `UC…` case, `@handle`, `v:` prefix |
| `normalize_search_result(raw)` | Twitch Helix shape | Typesense shape | YouTube search shape |
| `normalize_stream_item(raw)` | `search_channels` / `followed` | browse/top stream item | browse/top stream item |
| `build_stream_url(channel, **kwargs)` | `https://twitch.tv/{channel}` | `https://kick.com/{channel}` | `https://youtube.com/channel/{channel}` или `/watch?v={id}` |

### 4.3 Stream Resolution & Launcher

- `resolve_hls_url(url, platform_client, quality)` — принимает **instance** `PlatformClient`, не строку `platform`.
- `launch_stream(url, platform_client, quality, player)` — аналогично.
- `launch_stream_mpv(url, platform_client, quality, mpv_path, extra_args)` — mpv-вариант launcher'а.
- `streamlink --stream-url` — timeout до 15 с; если запрошенное качество недоступно, fallback на `best`.
- `extra_args: list[str] | None` — опциональные флаги streamlink (напр. `["--twitch-low-latency"]`). Пробрасывается через `resolve_hls_url()` → `_run_streamlink()` в subprocess команду.
- `_low_latency_args(platform, settings)` в `StreamsComponent` — возвращает `["--twitch-low-latency"]` если платформа twitch и `settings.low_latency_mode == True`. Принимает `settings` dict напрямую (не читает `self._config`).

### 4.4 Chat Client Hierarchy

**BaseChatClient** (`core/chats/base.py`):

| Member | Назначение |
|--------|-----------|
| `platform` | `"twitch"`, `"kick"` или `"youtube"` |
| `on_message()` / `on_status()` | Регистрация колбэков |
| `_emit_status(connected, error)` | Пуш статуса в JS |
| `disconnect()` | Закрытие WS, offline статус |
| `_reconnect_loop(connect_fn)` | Экспоненциальный backoff (`RECONNECT_DELAYS = [3, 6, 12, 24, 48]`) |
| `StopReconnect` | Исключение для чистого выхода из reconnect loop |

### 4.5 Config & Constants

**core/constants.py**
- `DEFAULT_IINA_PATH`, `DEFAULT_MPV_PATH` — fallback media players
- `BROWSE_CACHE_TTL_SECONDS` = 600, `BROWSE_CACHE_FILE`
- `OAUTH_REDIRECT_PORT` = 3457, `OAUTH_TIMEOUT_SECONDS` = 120
- `AVATAR_SIZE`, `THUMBNAIL_SIZE`
- `RECONNECT_DELAYS`
- `WATCH_STATS_DB_NAME` = `"watch_stats.db"`, `WATCH_STATS_SESSION_CLEANUP_DAYS` = 90
- `DEFAULT_RECORDING_DIR` = `~/Movies/TwitchX`

**core/storage.py**
- `_migrate_favorites_v2` — v1 string favorites → v2 dict; URL extraction; сохранение `UC…` case, `@handle`, `v:` prefix; дедупликация.
- `sanitize_twitch_login`, `sanitize_kick_slug`, `sanitize_youtube_login` — pure functions в `core/utils.py`.

**OAuth:**
- Redirect URI: `http://localhost:3457/callback`
- OAuth server в `core/oauth_server.py` — 120 с timeout, авто-остановка после callback.
- `reset_client()` — no-op (каждый loop получает свой `httpx.AsyncClient`).

---

## 5. API Bridge (ui/api/)

### 5.1 Component Decomposition

| Module | Class | Ответственность |
|--------|-------|-----------------|
| `__init__.py` | `TwitchXApi` | Оркестратор, shared state, config methods |
| `_base.py` | `BaseApiComponent` | `_eval_js`, `_run_in_thread`, доступ к клиентам |
| `auth.py` | `AuthComponent` | OAuth login/logout, connection tests |
| `favorites.py` | `FavoritesComponent` | add/remove/reorder, import follows, search |
| `data.py` | `DataComponent` | refresh, polling, browse categories/streams, profiles |
| `streams.py` | `StreamsComponent` | watch, watch_direct, watch_external, watch_media, multistream |
| `chat.py` | `ChatComponent` | start/stop/send chat, width/visibility, block list, third-party emotes, mod controls, YouTube chat |
| `images.py` | `ImagesComponent` | avatar/thumbnail fetching via `_image_pool` |

### 5.2 Key Patterns

- `BaseApiComponent` предоставляет `_twitch`, `_kick`, `_youtube`, `_config`, `_live_streams` через property delegation на `self._api`.
- `TwitchXApi.__init__` создаёт все sub-components, передавая `self`.
- Все public методы `TwitchXApi` делегируют sub-component (например, `self.login()` → `self._auth.login()`).
- `_eval_js(code)` — suppress errors при закрытии окна (`_shutdown` guard).
- `_run_in_thread(fn)` — `threading.Thread(daemon=True)` для всего async I/O.
- `_async_run(coro)` — создаёт `asyncio.new_event_loop()`, запускает корутину, в `finally` вызывает `_close_thread_loop(loop)` (а не `loop.close()` напрямую), что гарантирует очистку `httpx.AsyncClient` из `BasePlatformClient._loop_clients`.
- Thread pools: `_image_pool` (max 8) для аватарок, `_send_pool` (max 2) для отправки чата.
- `_active_watch_session` защищён `_active_watch_lock` (`threading.Lock`) от race между background resolve-тредом и main-thread `stop_player`. `_start_watch_session()` всегда завершает предыдущую active session под этим lock перед записью нового `session_id`.
- `_launch_id` — generation guard для запуска стрима. Все `watch*` пути должны брать id через `_begin_launch()` и проверять `_is_launch_current()` перед `onStreamReady`/`onLaunchResult(success)`, чтобы late `streamlink` result после timeout не стартовал плеер. `_finish_launch()` также инкрементирует `_launch_id`, чтобы concurrent `tick()` launch-таймера не мог перезапустить себя (streams.py:70).
- `_watch_stats.cleanup_old_sessions()` вынесен в daemon-поток при старте (не блокирует `__init__`). Он удаляет `watch_sessions` и `daily_summary` только старше `WATCH_STATS_SESSION_CLEANUP_DAYS`, не всю историю до сегодняшнего дня.
- `_recorder` — `Recorder` instance. `start_recording()`/`stop_recording()` вызываются из JS (main thread), `Recorder.start()` spawn'ит неблокирующий subprocess. `close()` вызывает `_recorder.stop()` перед `_shutdown.set()`.

### 5.3 Watch Methods — When to Use

| Method | Когда использовать | Ограничения |
|--------|-------------------|-------------|
| `watch(channel)` | Канал из live grid (sidebar/poller) | Гейт на `self._live_streams` cache; Twitch/Kick/YouTube live, YouTube требует `video_id` в cache |
| `watch_direct(channel, platform, quality)` | Открыт из Browse (нет в live cache) | Twitch/Kick only; YouTube browse cards не имеют `video_id` |
| `watch_media(url, quality, platform, channel, title, with_chat)` | VOD/clip/media карточка из Channel view | В `resolve_hls_url()` всегда передавать исходный `url`, не `channel` |
| `add_multi_slot(slot_idx, channel, platform, quality)` | Multistream | Зовёт `resolve_hls_url` напрямую; YouTube lookup через exact-case channel id + cached `video_id` |

**No-op guard:** `watch()` и `watch_direct()` возвращают `"Already watching ..."`, если `_watching_channel.lower() == channel.lower()`. `_launch_channel is not None` блокирует только concurrent resolve attempts. Timeout должен инвалидировать `_launch_id`, иначе late resolver может отправить противоречивый success после failure.

**Chat preservation:** `stop_chat()` вызывается **внутри** resolve thread **после** `if not hls_url: return`, но **перед** присвоением нового `_watching_channel`. Если `streamlink` упал, старый чат остаётся жив.

**Watch stats:** успешные `watch()`, `watch_direct()`, `watch_media()` и первый multistream slot стартуют session только после успешного HLS resolve. Старт новой session обязан атомарно завершить предыдущую, иначе в SQLite останется `ended_at NULL`.

**Low-latency HLS:** `_low_latency_args(platform, settings)` возвращает `["--twitch-low-latency"]` для Twitch если `settings.low_latency_mode == True`. Пробрасывается через `extra_args` во все вызовы `resolve_hls_url()` и `launch_stream_mpv()`.

**Recording:** `start_recording()` / `stop_recording()` — запись текущего стрима в `{recording_path}/twitchx_{channel}_{timestamp}.ts` через `streamlink --output`. Кнопка `#record-btn` в `#player-header-actions`, индикатор `#record-dot` в `#player-bar`.

### 5.4 get_config()

- Возвращает favorites из **всех** платформ (Twitch + Kick + YouTube).
- `has_credentials = True` если **хотя бы одна** платформа имеет credentials.
- `refresh()` обязан сохранять ту же семантику `has_credentials` даже когда favorites пустые: Twitch OAuth, Kick cookies/credentials или YouTube API key достаточно для `true`.

---

## 6. Critical Rules & Gotchas

### 6.1 Platform Identity
- **YouTube channel IDs (`UCxxxx…`)** — case-sensitive. Никогда не lower-case. `remove_channel`, favorite lookups, live-cache checks и multistream lookup — exact-case comparison для YouTube.
- Для live stream comparisons используй `DataComponent._stream_matches_channel()`, а не ручной `.lower()`. `DataComponent._stream_login()` сохраняет case для YouTube и lower-case только для Twitch/Kick.
- **`favorites_meta` использует compound keys `"platform:login"`** (не bare `login`). Предотвращает перезапись метаданных при одинаковом логине на разных платформах. JS использует `TwitchX.getFavoriteMeta(login)` для lookup по bare login через values. `context-menu.js` использует compound key `"youtube:" + login` напрямую для offline-Youtube гварда.
- **Kick `channel_id`** — integer в raw API. Всегда приводить `str()` в `_normalize_channel_info_to_profile`.

### 6.2 Multistream Display
- Показывать slot: `element.style.display = 'block'` — **никогда** `style.display = ''`. Очистка inline style отдаёт управление CSS, а `.ms-slot-active { display: none }` — default.
- WKWebView проигрывает audio на `<video>` даже когда parent имеет `display: none`.

### 6.3 Browse & Quota
- Browse cache: `~/.config/twitchx/cache/browse_cache.json`, TTL 10 мин.
- YouTube: `get_categories()` = 1 unit, `get_top_streams()` = 100 units. При исчерпании quota — silent `[]`.

### 6.4 UI Safety
- **DOM safety:** весь динамический контент через `document.createElement()` + `textContent`. Никакого `innerHTML` с user data.
- **Escape key priority:** Settings overlay → player view → channel view → browse view → multistream view → context menu → search dropdown. Всегда закрывать верхний слой первым. Escape в player view вызывает `TwitchX.hidePlayerView()`.
- **renderGrid guards:** возвращает early, если открыт `#browse-view` или `#multistream-view` (prevent poller от восстановления `stream-grid` display).

### 6.5 pyright & Native Code
- `ui/native_player.py` исключён в `pyproject.toml` (pyobjc stubs incomplete).
- Все AppKit/AVKit операции в `native_player.py` — только на main thread через `AppHelper.callAfter()`.

### 6.6 Config Idempotency
- `get_full_config_for_settings()` — **синхронный** (JS вызывает, получает immediate return).
- Для async ops — всегда callback pattern.

---

## 7. Decision Log

Краткая история ключевых архитектурных решений. Текущее состояние — см. тематические секции выше.

| Date | Phase | Problem | Solution | Status |
|------|-------|---------|----------|--------|
| 2026-04-28 | Phase 1-3 | Монолитные `app.py` и `index.html` | Декомпозиция `ui/api/` (7 модулей), CSS (6 файлов), JS (14 модулей). Base class hierarchy для platform/chat clients. | ✅ Active |
| 2026-04-29 | Phase 4 | `if/elif` chains по платформам | Полиморфные методы в `PlatformClient` (sanitize/normalize/build_stream_url). Консолидация констант в `core/constants.py`. Миграция favorites в `storage.py`. | ✅ Active |
| 2026-04-29 | pywebview 6.x | WKWebView silent drop script blocks после bridge injection | `_inline_resources()` в `app.py`: inline CSS + single merged JS block. `window.TwitchX` bootstrap только в `state.js`. | ✅ Active |
| 2026-04-30 | Playback stability | FPS drop, stutter после 30–60 мин | Health monitor (live-edge drift, buffer accumulation). FPS monitor (66 ms threshold). Sidebar diff-based rendering. Chat batching (50 мс). CSS containment. | ✅ Active |
| 2026-04-30 | Gentle reset | `softResetVideo()` не уничтожал MediaPlayer | `gentleResetVideo()` — shadow video + crossfade swap. Frozen detection (10 с). Proactive reset (30 мин). Multistream health monitor. | ✅ Active |
| 2026-04-30 | Sidebar switching | Нельзя переключить канал без закрытия плеера | Убран hard block `_watching_channel is not None`. Case-insensitive no-op guard. `stop_chat()` после проверки `hls_url`. | ✅ Active |
| 2026-05-02 | Fullscreen fixes | Chat слева, auto fullscreen exit, dblclick не выходит | `insertBefore` для DOM order. `isVideoFullscreen()` с `webkitPresentationMode`. `softResetVideo()` для fullscreen. Re-entrancy guards. | ✅ Active |
| 2026-05-04 | Browse navigation | Нет способа вернуться из Browse в Following, нет breadcrumb-навигации | Breadcrumb `Following > Browse > Category` через `<nav id="browse-breadcrumbs">`. Event delegation для click-обработчиков. Escape закрывает channel → browse → multistream. `hideBrowseView()`/`hideChannelView()` вызывают `renderGrid()`. Guard на `player-view.active` при возврате. | ✅ Active |
| 2026-05-05 | Phase 9 | PiP крашится при gentle reset, hotkeys не работают в multistream | `isVideoPiP()` guard (softReset fallback), `toggleVideoFullscreen` выходит из PiP перед входом, `hidePlayerView` выходит из PiP перед удалением, expanded hotkey scope (`pip`/`toggle_chat` в multistream), duplicate-key detection с `window.confirm()` swap. | ✅ Active |
| 2026-05-05 | Phase 9 fixes | Null dereference в toggleVideoFullscreen, PiP event listener loss после _reloadMultiSlot, duplicate-key detection blind spot | `if (!video) return` guard, `_bindSlotPiPEvents()` helper с rebinding после reload/clear, merged `DEFAULT_SHORTCUTS + state.shortcuts` для поиска дубликатов. | ✅ Active |
| 2026-05-05 | Phase 10 | Import follows не было авто-импорта после логина, не было статистики просмотров | `WatchStatsDB` (core/watch_stats.py) с SQLite-трекингом сессий и daily_summary. Авто-импорт follows после Twitch и YouTube логина. `silent` параметр в import_follows. Statistics dashboard в Settings. | ✅ Active |
| 2026-05-05 | Phase 10 fixes | Code review выявил 14 багов: assert в production, close() не завершал сессию, рассинхрон дат, нет SQLite error handling, innerHTML, orphaned daily_summary, race на session_id | `raise RuntimeError` вместо `assert`, `_end_watch_session` в `close()`, стандартизация `date(started_at)` везде, `try/except sqlite3.Error` во всех методах, DOM-создание вместо innerHTML, `daily_summary` cleanup, `_active_watch_lock` mutex, daemon-thread cleanup, логгирование silent-ошибок | ✅ Active |
| 2026-05-07 | Phase 10 review fixes | Code review выявил regressions в stats/playback/config: orphan sessions при switch, VOD игнорировал media URL, weekly stats стирались cleanup, YouTube IDs lower-case, Kick/YouTube credentials терялись при empty favorites, launch timeout race | `_start_watch_session()` завершает предыдущую session, `watch_media()` resolve по `url`, `daily_summary` cleanup по retention window, `_stream_matches_channel()` с exact-case YouTube, `refresh()` считает credentials по всем платформам, `_launch_id` инвалидирует late resolver, JS import callback принимает `{added}` | ✅ Active |
| 2026-05-07 | Phase 11 | Пять улучшений видеоплеера: low-latency HLS, mpv external player, stream recording, stats overlay, VOD mode | `extra_args` в `stream_resolver`/`launcher`. `Recorder` (core/recorder.py) для записи через streamlink subprocess. `_low_latency_args(platform, settings)` принимает settings dict напрямую. mpv через `launch_stream_mpv()`. Stats overlay на rAF. VOD mode: health monitors отключаются, time display через setInterval. `showPlayerView()` безусловно останавливает все мониторы перед ветвлением на streamType. | ✅ Active |
| 2026-05-08 | Phase 12 | 7 чат-апгрейдов: фильтры, mentions, анти-спам, лог экспорт, third-party emotes, emote picker, user list, YouTube чат, мод инструменты | `_shouldFilter()`/`_hasBadge()` в flushChatBatch, `chatSpamMap` с очисткой при смене канала, `chatSelfLogin` + CSS `mention`. Кольцевой буфер `chatLog`. `core/third_party_emotes.py` (BTTV/FFZ/7TV + disk cache). Emote picker с поиском. `parse_names_reply()` + membership CAP для user list. `YouTubeChatClient` — polling-based. Twitch mod tools через `PATCH /helix/chat/settings`. Code review: 15 багов зафиксировано (event loop leak, spamMap pollution, reconnect delay lookup, и др.) | ✅ Active |
| 2026-05-08 | Phase 13 | Debug audit: shared httpx pool + token refresh never fired | `_loop_clients`/`_token_locks` ключи `(loop, PLATFORM_ID)` вместо bare `loop` (изоляция платформ). `_ensure_token` сравнивает `token_expires_at` с `time.time()` (wall clock) вместо `asyncio.get_running_loop().time()` (monotonic). Исправлено в `base.py` и `youtube.py`. | ✅ Active |
| 2026-05-10 | Phase 14 | Debug audit Phase 2: JS callback bugs — YouTube test always fails, onStreamReady stale video ref, multistream chat not cleared | `onYouTubeTestResult`: `result.ok` → `result.success` (callbacks.js:643). `onStreamReady`: `getElementById('stream-video')` → `TwitchX.getPlayerVideo()` с null guard (callbacks.js:212). `clearChatMessages()` очищает также `#ms-chat-messages` когда `multiState.open` (chat.js:131). | ✅ Active |
| 2026-05-10 | Phase 3 fixes | Watch session race, save_settings ignores empty values, launch timer leak | `_start_watch_session()` — `start_session()` перенесён внутрь `_active_watch_lock` (streams.py:42). `save_settings()` — убраны `if new_value:` guard'ы для всех credential-полей; пустые строки очищают ключи (__init__.py:397–442). `_finish_launch()` — добавлен `_launch_id += 1` для инвалидации concurrent `tick()` (streams.py:70). Тесты: `test_save_settings_clears_credentials_when_empty`, `test_start_watch_session_is_atomic_under_lock`, `test_finish_launch_invalidates_launch_id`. | ✅ Active |
| 2026-05-10 | Phase 4 data layer | Debug audit Phase 4: favorites_meta collision при одинаковых login на разных платформах; deprecated asyncio.get_event_loop(); unresolved placeholder thumbnail_url | `favorites_meta` ключи → `"platform:login"` (compound). Добавлен `TwitchX.getFavoriteMeta(login)` в JS для lookup. `asyncio.get_event_loop()` → переданный `loop` параметр. Twitch thumbnail_url: 440×248 вместо 880×496. | ✅ Active |
| 2026-05-10 | Phase 5 | Debug audit Phase 5: multistream reply context, Escape no-op, httpx client leak | `send_chat` reply params в multistream (init.js), Escape → `hidePlayerView()` (keyboard.js), `_async_run` → `_close_thread_loop(loop)` (_base.py). Тесты: `test_async_run_closes_thread_loop`, `test_send_chat_forwards_reply_params`. | ✅ Active |

## 8. Testing Guide

### 8.1 Shared Fixtures (`tests/conftest.py`)

| Fixture | Назначение |
|---------|-----------|
| `temp_config_dir` | Перенаправляет `~/.config/twitchx/` во временную директорию с `DEFAULT_CONFIG` |
| `config_with_twitch_auth` | Как `temp_config_dir`, но с предзаполненными Twitch OAuth tokens |
| `mock_twitch_client` | `MagicMock` как `TwitchClient`, методы — `AsyncMock` |
| `mock_kick_client` | Аналогично для `KickClient` |
| `mock_youtube_client` | Аналогично для `YouTubeClient` |
| `capture_eval_js` | Записывает все `_eval_js(code)` вызовы; `capture.assert_any(fragment)` |
| `run_sync` | Патчит `TwitchXApi._run_in_thread` на синхронное исполнение |

### 8.2 Patterns

- Используй `temp_config_dir` вместо ручного патчинга `CONFIG_DIR` / `CONFIG_FILE`.
- Используй `run_sync` вместо `monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())`.
- Используй `capture_eval_js` вместо ручного списка `emitted`.
- Для launch-timeout race тестов вручную инвалидируй `_launch_id` и проверяй, что late resolver не вызывает `onStreamReady`/success.
- Для YouTube live-cache тестов используй mixed-case `UC...` id и `_stream_matches_channel()`, чтобы не спрятать bug за `.lower()`.

### 8.3 Verification Commands

```bash
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m ruff check .
.venv/bin/pyright --pythonpath .venv/bin/python .
```

Прямой `.venv/bin/pyright .` может не увидеть зависимости в локальном venv; для этого проекта используй `--pythonpath .venv/bin/python`.

### 8.4 Example

```python
def test_my_feature(temp_config_dir, run_sync, capture_eval_js):
    api = TwitchXApi()
    api._eval_js = capture_eval_js
    api.my_method("arg")
    capture_eval_js.assert_any("onSomething")
```

---

## 9. Troubleshooting / Agent Cheat Sheet

| Симптом | Искать в | Проверить |
|---------|---------|-----------|
| «Видео зависает/тормозит после 30+ мин» | §3.3 | `gentleResetVideo()`, `checkVideoHealth()`, `checkFrozenVideo()`, FPS monitor threshold, proactive reset timer |
| «Чат не очищается при смене канала» | §3.5 | `clearChatBatch()` вызывается в `onStreamReady`, `hidePlayerView`, `switchMultiChat`? |
| «Fullscreen сам выходит» | §3.3 | `isVideoFullscreen()` guard в `gentleResetVideo()`. `softResetVideo()` при fullscreen. Multistream `_reloadMultiSlot()` guard. |
| «Чат оказался слева от видео» | §3.3 | `hidePlayerView()` использует `insertBefore(fresh, firstChild)`, не `appendChild`. |
| «Двойной клик не выходит из fullscreen» | §3.3 | `toggleVideoFullscreen()` обрабатывает `webkitSetPresentationMode('inline')`. |
| «PiP окно зависает/крашится» | §3.3 | `isVideoPiP()` guard в `gentleResetVideo()`. `hidePlayerView()` выходит из PiP перед `video.remove()`. Multistream `_clearMultiSlot()` и `_reloadMultiSlot()` имеют аналогичные guards. |
| «Хоткей не срабатывает в multistream» | §3.2, keyboard.js | Проверить что `pip` и `toggle_chat` расширены на `inMulti` scope. |
| «Duplicate key warning не появился при rebind» | §3.2, init.js | Проверка ведётся по merged map `DEFAULT_SHORTCUTS + state.shortcuts`. |
| «Добавляю новую платформу» | §4.1, §4.2, §5 | `PlatformClient` ABC → `BasePlatformClient` → concrete class. Полиморфные методы. `build_stream_url()`. |
| «Favorites теряются/дублируются» | §2 (Config), §4.5 | `_migrate_favorites_v2`. Case sensitivity YouTube (`UC…`). compound keys в `favorites_meta` (`"platform:login"`). |
| «Browse показывает пустоту» | §6.3 | YouTube quota exhausted? Browse cache TTL (10 мин)? `load_config()` локальный в треде? |
| «Chat messages дублируются» | §3.5 | `KickChatClient._seen_msg_ids` LRU set. `clearChatBatch()` при смене канала. |
| «Watch stats не обновляются» | §4.5, core/watch_stats.py | `_end_watch_session()` вызывается в `stop_player`/`stop_multi`? `_start_watch_session()` — после `_watching_channel` в streams.py? `close()` вызывает `_end_watch_session`? |
| «Watch stats остаётся с `ended_at NULL` после переключения» | §5.2, streams.py | `_start_watch_session()` завершает текущую session под `_active_watch_lock` перед стартом новой? |
| «Weekly stats пустая после рестарта» | §5.2, core/watch_stats.py | `cleanup_old_sessions()` удаляет `daily_summary` только старше retention window, не все даты `< today`? |
| «VOD/clip Play запускает live или падает offline» | §5.3, streams.py | `watch_media()` передаёт `url` в `resolve_hls_url()`, а не `channel`? |
| «YouTube multistream/live slot unavailable при `UC...`» | §6.1, data.py | `_stream_login()` не lower-case YouTube? Сравнение идёт через `_stream_matches_channel()`? Есть cached `video_id`? |
| «После timeout stream всё равно стартует» | §5.2, streams.py | `_launch_id` инвалидируется на timeout? Resolve thread проверяет `_is_launch_current()` перед callbacks? |
| «Watch stats не отображаются в Settings» | §3.2, settings.js | `loadWatchStatistics()` экспортирован в `TwitchX.loadWatchStatistics`? В `init.js` вызов через `TwitchX.loadWatchStatistics()`? |
| «Не могу очистить credentials в Settings» | §2 Config, §5.2 | `save_settings()` раньше игнорировал пустые строки через `if new_value:` guard. После Phase 3 fixes пустые строки корректно очищают client_id/client_secret/api_key. |
| «Watch session остаётся с `ended_at NULL` после concurrent switch» | §5.2, streams.py | `_start_watch_session()` вызывает `start_session()` под `_active_watch_lock`? Проверь что lock-границы не регрессировали (streams.py:42). |
| «pytest падает с race» | §8 | `run_sync` применён? `temp_config_dir` используется? `_eval_js` замокан? |
| «VOD не показывает время» | §3.3 VOD Mode | `stream_type: "vod"` в `onStreamReady` payload? `TwitchX.state.streamType === 'vod'`? `hidePlayerView()` не сбросил `streamType`? |
| «Health monitors работают на VOD / VOD timer работает на live» | §3.3 VOD Mode | `showPlayerView()` вызывает все `stop*()` перед ветвлением на `streamType`? |
| «Запись не начинается» | §3.3 Stream Recording | `_watching_channel` установлен? `recording_path` указан в Settings? streamlink установлен? |
| «Stats overlay не обновляется» | §3.3 Stream Stats | `#stats-overlay` не `display:none`? rAF loop активен (`_statsOverlayActive`)? `getVideoPlaybackQuality()` доступен в WKWebView? |
| «External player открывает IINA вместо mpv» | §4.3 | `external_player` в Settings = `"mpv"`? `mpv_path` корректен? `check_mpv()` не вернул ошибку? |
| «Low-latency не применяется» | §4.3, §5.3 | `low_latency_mode: true` в Settings? Платформа = twitch? `extra_args` доходят до `_run_streamlink()`? |
| «Чат-фильтры не работают» | §3.5 | `TwitchX.chatFilters` синхронизирован? `loadChatFiltersFromConfig()` вызывается? `chatSpamMap` очищен при смене канала? |
| «Third-party эмодзи не появляются в чате» | §3.5, core/third_party_emotes.py | `onThirdPartyEmotes` вызван? `TwitchX.thirdPartyEmotes` не пуст? `renderChatEmotes()` сканирует слова? Кэш не устарел (TTL 1 ч)? |
| «Emote picker пустой для не-Twitch каналов» | §3.5 | `TwitchX.thirdPartyEmotes` заполняется только для Twitch. Для Kick/YouTube picker покажет «No emotes loaded yet». |
| «User list не показывает пользователей» | §3.5 | `twitch.tv/membership` CAP включён? NAMES reply получен? `on_user_list` callback зарегистрирован? |
| «Mod кнопка не видна на моём канале» | §3.5, callbacks.js | `chatSelfLogin` установлен? Сравнение идёт по `toLowerCase()`? |
| «YouTube чат не подключается» | §3.5, core/chats/youtube_chat.py | `live_chat_id` передан или разрешён? `liveChatId` активен? YouTube API quota не исчерпана? |
| «YouTube тест подключения всегда показывает ошибку» | §3.2, callbacks.js | `onYouTubeTestResult` проверяет `result.success`, а не `result.ok`? Python отправляет `{"success": ...}`. |
| «Видео не загружается после gentle reset» | §3.3, callbacks.js | `onStreamReady` использует `TwitchX.getPlayerVideo()` с null guard, а не `getElementById('stream-video')`? |
| «Чат не очищается в multistream при смене канала» | §3.5, chat.js | `clearChatMessages()` очищает также `#ms-chat-messages` когда `multiState.open`? |
| «Token refresh не срабатывает» | §4.1, base.py | `_ensure_token` сравнивает `token_expires_at` с `time.time()`? Не `asyncio.get_running_loop().time()` (monotonic)? |
| «Платформы используют один httpx client» | §4.1, base.py | `_loop_clients` ключ — `(loop, PLATFORM_ID)`, не bare `loop`? Изоляция платформ? |
| «Multistream reply не работает» | §3.5, init.js | `ms-chat-send-btn` handler читает `TwitchX.chatReplyTo` и передаёт reply params в `send_chat()`? После отправки вызывает `clearChatReply()`? |
| «httpx клиенты утекают / растёт потребление памяти» | §5.2, _base.py | `_async_run` вызывает `_close_thread_loop(loop)` в `finally`? Не bare `loop.close()`? |
| «Escape не закрывает плеер» | §6.4, keyboard.js | `player-view.active` branch вызывает `TwitchX.hidePlayerView()` вместо bare `return`? |

---

*Archive: предыдущая версия файла сохранена как `AGENTS.md.archive`.*
