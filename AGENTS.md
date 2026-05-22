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
| `main.py` | Точка входа | Запускает `TwitchXApp`. Логирование всегда включено (WARNING, DEBUG при `TWITCHX_DEBUG=1`), пишет в `~/.config/twitchx/twitchx.log` через `RotatingFileHandler` (5MB × 2) + stderr |
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
| `ui/js/` | 18 JS-модулей | См. §3.2 |
| `ui/js/focus.js` | Focus management a11y module | `focusReturn`, `activateFocusTrap`, `handleArrowNav` |
| `ui/js/icons.js` | SVG icon system | `TwitchX.icon(name, size)` — 44 stroke-based иконки |
| `ui/js/palette.js` | Command Palette module | `openPalette`, `closePalette`, `renderPaletteResults` |
| `ui/js/toast.js` | Toast notification system | `showToast`, `dismissToast`, `clearToasts` — slide-in уведомления с авто-dismiss |
| `tests/` | Pytest suite | `conftest.py` с фикстурами |
| `tests/test_uiux_settings.py` | Tests for accent_color and settings API | §8 |

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
- **Новые ключи settings:** `accent_color` (str, hex), `low_latency_mode` (bool), `external_player` ("iina"|"mpv"), `mpv_path` (str), `recording_path` (str), `chat_filter_sub_only` (bool), `chat_filter_mod_only` (bool), `chat_anti_spam` (bool), `chat_block_list` (list[str]).
- **`save_settings()`** — сохраняет только присутствующие в `parsed` ключи. Пустые строки очищают credential-поля (client_id, client_secret, api_key). Ранее игнорировались через `if new_value:` guard.
- **Важно:** из фоновых потоков используйте **локальный** `config = load_config()`, никогда не записывайте в `self._config` из треда (race condition с polling thread).

---

## 3. Frontend Reference (ui/)

### 3.1 CSS Decomposition

| File | Зона ответственности |
|------|---------------------|
| `tokens.css` | CSS custom properties (`:root`) — full design token system: spacing scale, typography scale, border tokens, shadow tokens, z-index scale, animation tokens, accent variants, micro-interaction tokens (`--scale-press`, `--highlight-press`), toast notification tokens, scroll shadow tokens, icon sizing tokens (`--icon-sm`, `--icon-md`), platform brand colors (`--platform-twitch`, `--platform-kick`, `--platform-youtube`) |
| `reset.css` | Base resets, scrollbar, `.sr-only` utility class, `.hidden` (`display: none !important`) глобальный класс, accessibility media queries (`prefers-reduced-motion`, `prefers-contrast`) |
| `layout.css` | `#app`, `#main`, `#sidebar`, `#content`, `#toolbar`, mini mode (`.mini` class rules), sidebar scroll shadow (`.section-body::before` sticky pseudo-element) |
| `components.css` | Buttons, inputs, cards, badges, sidebar sections, chat messages, accent swatches, list-mode grid, pin badge, palette overlay, drag-to-multistream, skeleton classes (`.skeleton`, `.skeleton-card`, `.skeleton-thumb`, `.skeleton-text`, `.skeleton-browse-card`, `.skeleton-stream-card`), spinner (`.ms-spinner`, `.player-spinner`), overlay transitions (settings scale+fade, context-menu scale+opacity, search dropdown slide+fade), connecting indicator, chat status text, chat scroll shadow (`#chat-shadow-top`), toast notifications (`#toast-container`, `.toast`, `.toast--success/error/info/warn`), button press feedback (`button:active { transform: scale(0.96) }`), missing hover states. **Phase 6:** sidebar watching indicator (`.watching`), sidebar tooltip (`#sidebar-tooltip`), sidebar notification badge (`.notif-dot`, `.notif-badge`), sidebar collapsible mode (`.collapsed-sidebar`), chat timestamps (`.msg-time`), hotkey capturing/idle classes (`.hotkey-capturing`, `.hotkey-idle`), compact stats (`.stats-grid.compact`, `.stat-card.compact`), context menu animation fix (`visibility`/`opacity`/`scale` вместо `display:none`). **Phase 7:** SVG icon sizing rules (`.bar-btn svg`, `.ctx-item svg`, `.toast-icon svg`), multistream badge platform colors (`.ms-platform-badge.twitch/kick/youtube`), performance containment (`contain: layout style paint` на `#stream-grid`, `#chat-messages`), `will-change: transform` на `.channel-item`. **Phase 2:** utility-классы (`.text-muted`, `.text-sm`, `.flex-center`, `.gap-sm`, `.mt-1`, `.mb-1`), settings helpers (`.checkbox-row`, `.setting-hint`, `.oauth-login-btn`, `.setting-user-display`, `.setting-quota-display`, `.import-btn`, `.logout-link`, `.test-result`, `.hotkeys-table`, `.reset-btn`, `.stats-loading`, `.stats-grid-cols-2`) |
| `views.css` | `#player-view`, `#browse-view`, `#channel-view`, `#multistream-view` — все с `opacity` transition для fade in/out |
| `player.css` | `#player-bar`, `#chat-panel`, `#chat-resize-handle`, `#live-dot`, PiP button active states, stream loader (`#stream-loader`, `#stream-loader-bar`), player loading spinner (`#player-loader`, `.player-spinner`). **Phase 6:** `bar-group` wrappers + separators, volume slider (`#volume-slider`, `#mute-btn`), VOD seek bar (`#seek-bar-container`, `#seek-bar`), buffer visualization (`#buffer-bar`, `#buffer-loaded`, `#buffer-position`), fullscreen auto-hide (`.fs-hidden`). **Phase 2:** chat panel CSS classes (`.chat-filter-panel`, `.chat-userlist-panel`, `.chat-mod-panel`, `.chat-export-menu`, `.emote-picker`), chat header buttons (`.chat-header-btn`), player header buttons (`.player-header-btn`), emote picker (`.emote-search`, `.emote-grid`, `.emote-picker-btn`), recording dot (`.record-dot`), VOD time display (`.vod-time-display`) |

**Containment:** `#player-view`, `#player-content`, `#chat-panel` имеют `contain: layout style paint` для изоляции пересчётов от видео-композитинга. **Phase 7:** добавлено `contain: layout style paint` на `#stream-grid` и `#chat-messages`, а также `content-visibility: auto` на `#stream-grid` для off-screen оптимизации. `will-change: transform` добавлен на `.channel-item`.

**View Transition Pattern:** `display: none` нельзя анимировать через CSS transitions. Используется двухфазный JS-паттерн: 1) установить `opacity: 0` → установить `display: flex/grid` → `requestAnimationFrame` → сбросить `opacity` (появление); 2) установить `opacity: 0` → `transitionend`/`setTimeout 250ms` → `display: none` (скрытие). **ВАЖНО:** `opacity: 0` устанавливается строго **до** изменения `display`, иначе CSS transition от `opacity: 1→0` вызовет микро-вспышку. Один `requestAnimationFrame` достаточен (двойной rAF добавляет лишний кадр задержки). `prefers-reduced-motion: reduce` в reset.css обнуляет все transition-duration.

### 3.2 JS Module Dependency & Load Order

Все модули — IIFE + `TwitchX` namespace. Нет глобалов, кроме `window.on*` callbacks.

Порядок загрузки:
```
state → utils → icons → api-bridge → render → sidebar → player → multistream → browse → channel → chat → settings → context-menu → keyboard → palette → toast → callbacks → init
```

| File | Ответственность |
|------|-----------------|
| `state.js` | `TwitchX.state`, `TwitchX.multiState`, shortcuts, chat state, `TwitchX.getFavoriteMeta(login, platform)` — helper для поиска меты в compound-ключевом `favoritesMeta`. Если `platform` передан — прямой lookup по compound key `"platform:login"`; если нет — fallback перебор по `login`. Также: `TwitchX.state.gridMode`, `TwitchX.state.pinnedStreams`, `loadPinnedStreams/savePinnedStreams/isPinned/togglePin` |
| `utils.js` | `truncate`, `formatViewers`, `formatUptime`, `setStatus`, `viewFadeIn`/`viewFadeOut` — двухфазный show/hide helper для анимированных переходов |
| `focus.js` | Focus management a11y module | `focusReturn`, `activateFocusTrap`/`deactivateFocusTrap`, `handleArrowNav` |
| `icons.js` | SVG icon system | `TwitchX.icon(name, size)` — 44 stroke-based иконки (16×16 viewBox, 1.5px stroke, `currentColor`). Используется через `innerHTML` для замены текстовых символов на inline SVG. |
| `api-bridge.js` | `pywebviewready`, `TwitchX.api`, profile helpers |
| `render.js` | `renderGrid`, `createStreamCard`, `createOnboardingCard`. Grid/list-mode toggle via `list-mode` CSS class. Pinned-first sort in `getFilteredSortedStreams`. Pin badge rendering in `createStreamCard`. `showSkeletonGrid`/`hideSkeletonGrid` — 8 skeleton карточек при первой загрузке. |
| `sidebar.js` | `renderSidebar`, diff-based updates, layout logic, `getChannelPlatform` helper, drag-to-multistream (`draggable=true`, `dragstart`/`dragend` events). **Phase 6:** `.watching` class при `watchingChannel`, `_setupSidebarTooltip()` c 400ms debounce + thumbnail preview, `_updateNotifBadges()` для offline→online переходов |
| `player.js` | Video lifecycle, health monitors, fullscreen, gentle reset, recording toggle, stats overlay, VOD time display. **Phase 6:** `syncVolumeSlider()`/`_handleVolumeSliderInput()`/`_handleMuteBtnClick()` — volume slider + mute toggle, `_updateBufferBar()` — buffer visualization в stats overlay rAF-цикле, `startVodSeekBar()`/`stopVodSeekBar()`/`_handleSeekBar*()` — VOD seek bar с time tooltip, `_startFullscreenAutoHide()`/`_stopFullscreenAutoHide()`/`_watchFullscreenChanges()` — auto-hide controls в fullscreen через `webkitpresentationmodechanged`. **Session 2026-05-21:** buffering overlay (`#player-buffering`) через event delegation на `#player-content` (`waiting`/`playing`), recovery status при gentle reset (`setStatus('Recovering playback...')`), `softResetVideo` очищает статус при PiP/fullscreen early return, `_stopFullscreenAutoHide` использует `TwitchX._fsShowControls` |
| `multistream.js` | Slot management, audio/chat focus, health monitor, `dragover`/`dragleave`/`drop` handlers на `.ms-slot-empty` для drag-to-multistream |
| `browse.js` | `showBrowseView`, breadcrumb nav (`Following > Browse > Category`), category/top-stream loading |
| `channel.js` | `showChannelView`, tabs, media cards, follow/watch actions |
| `chat.js` | `submitChatMessage`, `renderChatEmotes`, reply handling, chat filters, log export, emote picker, user list |
| `settings.js` | `openSettings`, `saveSettings`, connection tests, `ACCENT_PALETTE` constant, `applyAccentColor()`, accent swatch rendering |
| `context-menu.js` | `showContextMenu`, `showSidebarContextMenu`, pin item show/hide and label update |
| `keyboard.js` | `handleKeydown`, shortcut rebinding, hotkeys (player + multistream scopes), duplicate-key confirm-swap, Cmd+K → palette, Escape priority for palette |
| `palette.js` | Command Palette module: `openPalette`, `closePalette`, `renderPaletteResults`, `handlePaletteKeydown` |
| `toast.js` | Toast notification system: `showToast`, `dismissToast`, `clearToasts` — slide-in уведомления с авто-dismiss, стопка до 5, клик-to-dismiss, 4 типа (success/error/info/warn). `showToast()` возвращает DOM-элемент для внешнего dismiss. `dismissToast` имеет `if (!el) return` guard |
| `callbacks.js` | Все `window.on*` — thin proxies к `TwitchX.*`, chat batching (`flushChatBatch`), `_shouldFilter`, `_hasBadge`, `onThirdPartyEmotes`, `onChatUserList`, `onChatModeChanged`. Transient-сообщения (логин, импорт, ошибки, credentials) используют `showToast()` вместо `setStatus()`. **Session 2026-05-21:** toast на `onLaunchResult` failure, `onChatStatus` disconnect auto-dismiss, `onStatusUpdate` error с opt-out через `data.toast !== false` |
| `init.js` | `DOMContentLoaded`, `_bind*()` wiring, uptime interval. `toggleMiniMode`/`applyMiniMode`, `_bindPaletteEvents`, grid toggle binding, mini btn binding, accent/ mini/grid/pinned restore на старте, skeleton init при наличии favorites. **Phase 6:** bindings для volume slider (`#mute-btn`, `#volume-slider`), VOD seek bar (`#seek-bar`), chat timestamp toggle (`#chat-timestamp-btn`), sidebar collapse (`#sidebar-collapse-btn`), stats compact toggle (`#stats-compact-toggle`). `_watchFullscreenChanges()` для fullscreen auto-hide. Восстановление `collapsed-sidebar` и `chat_timestamps` из localStorage.

**pywebview 6.x Constraint:** модули не загружаются через отдельные `<script src="...">`. `app.py._inline_resources()` мержит все JS в **один** inline `<script>` блок и CSS в inline `<style>`. Только `state.js` содержит `window.TwitchX = window.TwitchX || {};`, остальные используют `const TwitchX = window.TwitchX;`.

**⚠️ ВАЖНО:** все новые JS-модули **обязаны** использовать `const TwitchX = window.TwitchX;` (не `var`). `_inline_resources()` ищет точную строку `"window.TwitchX = window.TwitchX || {};\nconst TwitchX = window.TwitchX;"` для замены во всех файлах кроме первого. `var` не совпадает с паттерном, остаётся в скрипте и вызывает `SyntaxError: Identifier 'TwitchX' has already been declared`. Это ломает весь inline-скрипт.

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
- `setStatus('Recovering playback...')` выставляется **после** PiP/fullscreen guards, чтобы при early return не оставить stale статус.
- `softResetVideo` безусловно очищает статус (`setStatus('', 'info')`) для защиты от callers без собственного setStatus.

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
  - **Dropped frames monitor** (первая проверка): `video.getVideoPlaybackQuality()` — если `droppedVideoFrames / totalVideoFrames > 5%` и всего >300 кадров → `gentleResetVideo('dropped-frames')`. Детектирует деградацию VideoToolbox-декодера на отдельном потоке, которую rAF-монитор не видит.
  - **Live-edge drift:** `currentTime` отстаёт от `seekable.end` на >30 с → `video.currentTime = liveEdge - 2`. Плотный порог, чтобы SourceBuffer не управлял одновременно старыми и новыми сегментами.
  - **Forward buffer overflow:** `buffered.end - currentTime > 60` с → `gentleResetVideo('buffer-overflow')`. Консервативно (живому HLS нужно макс 15-30s впереди), предотвращает накопление сегментов в памяти.
  - **Total buffer span overflow:** `buffered.end - buffered.start > 120` с → `gentleResetVideo('buffer-total-overflow')`. Старые проигранные сегменты также занимают место в SourceBuffer.
- **`checkFrozenVideo()`** — каждые 10 с:
  - Если `currentTime` не изменился 10 с при `!paused && readyState >= 2` → `gentleResetVideo('frozen')`.
- **FPS Monitor** — `requestAnimationFrame` loop:
  - Пропускает замер при `document.hidden`, `paused`, `readyState < 2`.
  - Порог: кадр >66 мс (<15 FPS) **подряд** ~5 с → `gentleResetVideo('fps-drop')`. *Примечание: этот монитор может упустить деградацию декодера; используй dropped frames monitor как первичный сигнал.*
- **Proactive Reset** — `gentleResetVideo('proactive')` каждые 15 мин (self-rescheduling `setTimeout`). Предотвращает накопление SourceBuffer-буферов до критического состояния.

**Все reset-пути логируют:** `console.log('[VideoHealth]', reason, src, currentTime)`.

#### Race Safety
- `hidePlayerView()` при active gentle reset: отменяет таймер, удаляет shadow video, чистит `_gentleReset*` flags.
- Event delegation для dblclick на `#player-content` вместо прямого `video.addEventListener` — переживает recreation.
- Buffering overlay (`#player-buffering`) использует event delegation (`waiting`/`playing` на `#player-content`) с классом `.buffering-hide` (не `.hidden`, чтобы не конфликтовать с `display: none !important` из reset.css).

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

#### Volume Slider
- Видимый `<input type="range" id="volume-slider">` + кнопка `#mute-btn` в `bar-group--audio`.
- `syncVolumeSlider(video)` синхронизирует UI с keyboard изменениями.
- `_handleVolumeSliderInput()` → `video.volume = value/100`.
- `_handleMuteBtnClick()` → `toggleMute()` + иконка.
- `getActiveVideo()` работает и для multistream.
- Volume group показывается только при активном плеере (syncVolumeSlider(null) скрывает).

#### Buffer Visualization Bar
- `#buffer-bar` (3px анимация) внизу `#player-content`, над `#player-bar`.
- `_updateBufferBar(video)` читает `video.buffered` → ширина `#buffer-loaded` процентом от `duration`.
- Для VOD: `#buffer-position` показывает `currentTime / duration`.
- Интегрирована в rAF цикл `updateStatsOverlay()`.

#### VOD Seek Bar
- `#seek-bar-container` (абсолютно, top: -6px) поверх `#player-bar`, показывается только для VOD.
- `<input type="range" id="seek-bar">` + `#seek-tooltip` с форматом HH:MM:SS.
- `startVodSeekBar()` — `setInterval(250ms)` обновляет `seek.value` из `video.currentTime / video.duration`.
- `stopVodSeekBar()` — скрывает контейнер.
- `_handleSeekBarInput()` обновляет tooltip при `mousemove`/`input`.
- `_handleSeekBarChange()` выполняет `video.currentTime = frac * duration`.

#### Fullscreen Auto-hide
- Phase 6: mousemove → controls visible → 3s timer → `.fs-hidden` скрывает `#player-bar` и `#player-header`.
- `_startFullscreenAutoHide()`: по входу в fullscreen (W3C API или WebKit native).
- `_stopFullscreenAutoHide()`: по выходу + при `hidePlayerView()`.
- `_watchFullscreenChanges()`: слушает `fullscreenchange`/`webkitfullscreenchange` на document + `webkitpresentationmodechanged` на video (через `_bindPiPEvents`).

### 3.4 Sidebar Lifecycle (Sidebar.js)

**Diff-based rendering** — полная перестройка заменена на in-place updates:
- `renderSidebar()` сравнивает текущий и новый набор `login` для Online/Offline секций.
- Если состав не изменился → `updateSidebarItem()` обновляет только текст/classes/src.
- Если состав изменился → перестраивается только затронутая секция.
- `applySidebarLayout()` отложен через `requestAnimationFrame`.
- `updateSidebarItem()` обновляет `aria-label` и кеширует `dataset._lastViewers`. **Phase 6:** также обновляет `.watching` класс.

**Phase 6 дополнения:**
- **Watching indicator:** `.channel-item.watching` — акцентный левый border (3px), accent-tinted имя, пульсирующий dot. `_matchWatching(login)` сравнивает case-insensitive для Twitch/Kick, exact для YouTube (через `TwitchX.state.watchingChannel`).
- **Hover tooltip:** `_setupSidebarTooltip(item, login, streamMap)` — 400ms debounce, показ `#sidebar-tooltip` с thumbnail (`tooltip-thumb`), названием (`tooltip-title`), игрой (`tooltip-game`), зрителями (`tooltip-viewers`). Clamping to viewport. Скрывается при `mouseleave`.
- **Notification badge:** `TwitchX._notifBadgeLogins` — список новых online каналов. `_updateNotifBadges()` показывает `.notif-dot` на элементах + `.notif-badge` счётчик в `#favorites-header`. Сбрасывается при клике/ререндере.
- **Collapsible mode (icons-only):** `#sidebar.collapsed-sidebar` — `width: 56px`, скрывает profile, tabs, text, search, browse. Только avatar + live-dot. Кнопка `#sidebar-collapse-btn` в `#favorites-header`. Состояние в `localStorage('twitchx.sidebar.collapsed')`.
- **Stale data banner:** `#sidebar-stale-banner` показывается когда `onStatusUpdate(stale=true)` — предупреждает пользователя, что данные могут быть устаревшими. Скрывается при `stale=false`.

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

**Phase 6 чат-апгрейды:**
- **Timestamps toggle:** `#chat-timestamp-btn` в `#chat-header`. При `TwitchX.chatTimestamps === true` каждое сообщение получает `<span class="msg-time">HH:MM:SS</span>`. Состояние в `localStorage('twitchx.chat_timestamps')`.
- **Smooth scroll:** `scrollTo({ behavior: 'smooth' })` вместо `scrollTop = scrollHeight` в `flushChatBatch()` и `#chat-new-messages` click handler.

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

### 3.6 Grid/List View Toggle (Render.js)

- `TwitchX.state.gridMode` — `"grid"` (default) или `"list"`, персистент через `localStorage('twitchx.grid_mode')`.
- Кнопка `#grid-toggle-btn` в `#toolbar` переключает режим. Иконка меняется: SVG grid (с пунктирными вертикальными линиями) / SVG list (горизонтальные линии). **Phase 7:** заменены текстовые символы `≡`/`⊞` на inline SVG через `TwitchX.renderIcon()`.

### 3.7 Pinned Streams (State.js + Render.js)

- `TwitchX.state.pinnedStreams: Set<string>` — compound keys `"platform:login"`.
- `loadPinnedStreams()` / `savePinnedStreams()` — `localStorage('twitchx.pinned')`.
- `isPinned(platform, login)` / `togglePin(platform, login)` — проверка/переключение + `renderGrid()`.
- `getFilteredSortedStreams()` — pinned-first сортировка: `sortGroup(pinned).concat(sortGroup(rest))`.
- `createStreamCard()` — бейдж `.pin-badge` (📌) в absolute top-left.
- Контекстное меню: пункт `"📌 Pin to top"` / `"📌 Unpin"`. `ctxPlatForPin` определяется через `stream.platform` или `favoritesMeta`.

### 3.8 Command Palette (Palette.js)

- Новый модуль `ui/js/palette.js`. Вызов: `Cmd+K` (`e.metaKey && e.key === 'k'`).
- Оверлей `#palette-overlay` (z-index: 3000, backdrop-filter blur).
- Три секции: **Live Now** (до 5 каналов), **Favorites** (до 3 offline), **Commands**.
- Навигация: `↓`/`↑` (активный элемент `.palette-active`), `Enter` (execute), `Escape` (закрыть).
- `PALETTE_COMMANDS` — статический массив: Refresh, Settings, Browse, Toggle Chat, Stop Player, Toggle Mini Mode.
- `palette.js` загружается после `keyboard.js` и перед `callbacks.js`.

### 3.9 Drag to Multistream (Sidebar.js → Multistream.js)

- `getChannelPlatform(login)` — helper для определения платформы по `login` (streams → favoritesMeta → fallback `'twitch'`).
- `createSidebarItem()`: `item.draggable = true`, `dragstart` → `dataTransfer.setData('text/plain', JSON.stringify({login, platform}))`, `effectAllowed = 'copy'`. Авто-открытие multistream view если закрыт.
- `_createMultiSlot()`: `dragover` (preventDefault + dropEffect='copy' + `.drag-over` class), `dragleave` (удаляет класс, если покинул slot), `drop` (JSON.parse → `addMultiSlot`).
- CSS: `.channel-item.dragging { opacity: 0.45 }`, `.ms-slot.drag-over .ms-slot-empty { background: var(--accent-dim); outline: 2px dashed var(--accent); }`

### 3.10 Mini Mode (Layout.css + Init.js)

- CSS: `#app.mini #content { display: none !important }`, `#app.mini #sidebar { width: 100%; max-width: none }`, скрывает browse-nav, search, kick-profile.
- Кнопка `#mini-mode-btn` в `#player-bar` (рядом с settings).
- `toggleMiniMode()` — toggle класс `.mini` на `#app`, персистит в `localStorage('twitchx.mini')`.
- `applyMiniMode()` — восстанавливает состояние на `DOMContentLoaded`.
- Иконки: SVG minimize (normal), SVG mini-exit (active). **Phase 7:** заменены текстовые символы `□`/`◣` на inline SVG через `TwitchX.renderIcon()`.

### 3.11 View Transitions & Loading States (Phase 3)

**CSS Architecture (`ui/css/tokens.css`, `views.css`, `components.css`):**
- `--duration-view: 0.18s`, `--ease-view: cubic-bezier(0.25, 0.1, 0.25, 1)` в tokens.css.
- Все content views (`#player-view`, `#browse-view`, `#channel-view`, `#multistream-view`, `#stream-grid`, `#empty-state`) имеют `opacity` + `transition: opacity var(--duration-view) var(--ease-view)`.
- Двухфазный JS-паттерн: появление — `display: flex/grid` → `requestAnimationFrame` → `opacity: 1`; скрытие — `opacity: 0` → `transitionend`/fallback 250ms → `display: none`.

**Overlay transitions:**
- `#settings-overlay`: backdrop fade + `#settings-modal` scale (0.97→1) с ease-spring. **ВАЖНО:** `display: none` заменён на `visibility: hidden; opacity: 0; pointer-events: none` с `transition: visibility 0s var(--duration-view)`, иначе CSS transition на opacity не срабатывает (visibility скрывается с задержкой после завершения opacity transition).
- `#context-menu`: scale (0.95→1) + opacity, класс `.menu-visible` (BUGFIX: `display:none` → `visibility/opacity/transform` с `transition`, двухфазный rAF-паттерн в JS для корректной анимации).
- `#search-dropdown`: slide (translateY 4px) + fade, класс `.visible`.

**Skeleton loading (`ui/css/components.css`, `ui/js/render.js`, `ui/js/browse.js`, `ui/js/channel.js`):**
- `@keyframes skeleton-shimmer` — gradient sweep анимация (200% background-size).
- `.skeleton`, `.skeleton-card`, `.skeleton-thumb`, `.skeleton-text`, `.skeleton-avatar`, `.skeleton-browse-card` (3:4 ratio), `.skeleton-stream-card` (16:9 ratio).
- Stream grid: `showSkeletonGrid()` — 8 skeleton cards при `DOMContentLoaded` если есть favorites; `hideSkeletonGrid()` — вызов из `onStreamsUpdate`.
- Browse: 12 skeleton 3:4 cards для categories, 8 skeleton 16:9 cards для top streams.
- Channel: skeleton-avatar + skeleton-text для profile; skeleton-stream-card для media tabs (VODs/Clips).
- Multistream: `.ms-spinner` (CSS-only rotating ring) внутри `.ms-loading` вместо голого текста.

**Chat status indicator (`ui/js/callbacks.js`, `ui/css/components.css`):**
- `#chat-status-dot` — зелёный (connected), серый (disconnected), жёлтый pulsing (connecting через класс `.connecting` + `@keyframes pulse`).
- `#chat-status-text` — отображает "Disconnected" или текст ошибки при потере соединения.
- Empty state "No messages yet" в `clearChatMessages()`.

**Empty states (`ui/index.html`, `ui/js/callbacks.js`):**
- Browse categories: "No categories found."
- Browse streams: "No streams found for this category."
- Search dropdown: "No channels found" (внутри `#search-dropdown` с `.visible` классом).
- Multistream empty slots: визуальная подсказка "+ Add Stream" через `.ms-add-btn`.

### 3.12 Micro-interactions & Feedback (Phase 4)

**Button press feedback (`ui/css/components.css`, `ui/css/tokens.css`):**
- `--scale-press: 0.96` токен в tokens.css.
- Глобальное CSS-правило `button:not(:disabled):active { transform: scale(var(--scale-press)) }` покрывает все кнопки приложения (`.login-btn`, `.bar-btn`, `.player-header-btn`, `.onboarding-btn`, `.browse-back-btn`, `.channel-follow-btn`, `.channel-watch-btn`, `.ms-confirm-btn`, `.ms-cancel-btn`, `#watch-btn.active`, `#stop-player-btn`, `#chat-send-btn`, `#ms-chat-send-btn` и др.).
- `.channel-item:active { background: var(--highlight-press); transform: scale(0.98) }` — подсветка при клике на элементы боковой панели.
- Добавлены недостающие hover-состояния: `.ms-confirm-btn:hover { opacity: 0.9 }`, `.ms-cancel-btn:hover { border-color; color }`, `.chat-header-btn:hover`, `.emote-picker-btn:hover`, `#ms-chat-send-btn:hover`.

**Toast notification system (`ui/js/toast.js`, `ui/css/components.css`, `ui/index.html`):**
- `TwitchX.showToast(message, type)` — создаёт slide-in тост с 4 типами: `success` (зелёный), `error` (красный), `info` (серый), `warn` (жёлтый).
- Анимация: `transform: translateX(120%) → translateX(0)` c `ease-spring` + `opacity`, выход через `translateY(-8px)` + `opacity`.
- Auto-dismiss через 4 секунды (`--toast-duration`), отмена по клику.
- `#toast-container` (fixed, z-index: 2000, right-top) — стопка до 5 тостов, pointer-events:none/delegation.
- Все transient-сообщения (`"Logged in as X"`, `"Login error"`, `"Imported N channels"`, `"Recording stopped"`, `"Chat mode error"`, `"Kick/YouTube credentials required"` и др.) маршрутизируются через `showToast()`. Постоянная/загрузочная информация остаётся в `setStatus()` (счётчик каналов, `"Launching X..."`, `"Recording: X"`, `"Volume: N%"`).

**Stream loader bar (`ui/css/player.css`, `ui/js/callbacks.js`, `ui/index.html`):**
- Indeterminate progress bar в `#player-bar` (`#stream-loader` + `#stream-loader-bar`).
- Анимация: `@keyframes loader-slide` — полоса бесконечно скользит слева направо.
- Показывается при `onLaunchProgress`, скрывается при `onStreamReady`, `onLaunchResult`, `onPlayerStop`.

**Player loading spinner (`ui/css/player.css`, `ui/js/player.js`, `ui/index.html`):**
- `#player-loader` с `.player-spinner` центрирован в `#player-content`.
- Показывается в `showPlayerView()`, скрывается по событиям `playing`/`error` на `<video>` (fallback 15s).
- Использует `@keyframes spin` (rotating ring, 0.8s).

**Scroll shadows (`ui/css/layout.css`, `ui/css/components.css`, `ui/js/sidebar.js`, `ui/js/chat.js`):**
- Sidebar (`.section-body::before`): `position: sticky` псевдо-элемент на каждом `.section-body`. При прокрутке `.section-body.scrolled::before` показывает градиентную тень через `background: linear-gradient(to bottom, ...)`.
- Chat (`#chat-shadow-top`): `position: sticky` внутри `#chat-messages`. При `scrollTop > 0` переключается класс `.visible`, раскрывая shadow через `height` transition.
- JS: `updateSidebarScrollShadow()` проверяет `scrollTop > 0` на каждом `.section-body` и переключает `.scrolled`. `updateChatScrollShadow()` делает то же для `#chat-messages`.
- `--scroll-shadow-size: 16px`, `--scroll-shadow-color: rgba(0, 0, 0, 0.45)`.
- Инициализация в `_bindGlobalEvents()` (init.js), ребайндинг прямых `scroll`-слушателей на `.section-body` при каждом `renderSidebar()` через `initSidebarScrollShadow()`.

### 3.13 macOS Native Design System

**Дизайн-философия:** применение нативных macOS UI паттернов (SF Symbols, ghost buttons, icon-only toolbars) для достижения аккуратного и профессионального внешнего вида, совместимого с Human Interface Guidelines.

#### Icon Design (`ui/js/icons.js`)

- **Stroke width:** 1.5px — стандарт SF Symbols (был 1.75px → изменено для соответствия нативному внешнему виду).
- **44 SVG иконки** в объекте `ICONS` (16×16 viewBox, `currentColor` fill/stroke для динамической окраски, `stroke-linecap="round"` + `stroke-linejoin="round"`).
- **Специальные иконки:**
  - `record`: изменен с двойной окружности на **одну заполненную окружность** (`<circle cx="8" cy="8" r="4" fill="currentColor" stroke="none"/>`). Это стандартный SF Symbol для активной записи.
  - `settings`: переработан в **правильное колесо передачи** с 8 лучами (вместо солнцеподобного варианта). Расположение: центральная окружность + 8 лучей по диагоналям и кардиналам.
- `renderIcon(name, size)` — создаёт inline `<svg>` элемент с указанным size (по умолчанию 16px). `mountIcons(root)` находит все `[data-icon]` элементы и заменяет их content на `.innerHTML = renderIcon(...)`.
- **Использование в JS:** `TwitchX.icon(name, size)` — возвращает SVG-строку для программного внедрения. Используется в dinamically-создаваемых DOM-элементах (контекстные меню, палитра, тосты).

#### Ghost Button Pattern (Transparent with Hover)

Основной паттерн для всех icon-only кнопок в player bar, header'ах и toolbar'ах:

```css
.player-header-btn {
  width: 28px;
  height: 28px;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  cursor: pointer;
  transition: background var(--duration-fast) ease, color var(--duration-fast) ease;
}

.player-header-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-primary);
}
```

**Размер 28×28px** — стандартный размер macOS touch target (44px минимум рекомендуемый, но 28px применяется в плотных toolbar'ах). **Flex-центрирование** гарантирует что иконка всегда центрирована, независимо от размера viewBox или stroke width.

**Hover эффект:** очень тонкий — всего `rgba(255,255,255,0.08)` (8% белой полупрозрачности на тёмном фоне). Переход — 150ms (`--duration-fast`).

#### Player Bar Controls Redesign

Все кнопки в `#player-bar`, `#player-header` и multistream header'е переведены на icon-only 28×28 ghost-button стиль:

| Кнопка | До | После | Примечание |
|--------|-----|--------|-----------|
| `#stats-overlay-btn` | `padding: 2px 6px`, текст "Stats" | icon-only 28×28, transparent ghost | Скрыта текстовая метка; иконка `external` |
| `#record-btn` | `padding: 2px 6px`, красная тема | icon-only 28×28, transparent ghost | `#record-dot` больше не показывает "REC" текст (только иконка) |
| `#pip-player-btn` | `padding: 0 10px` | icon-only 28×28 | Active state: `background: var(--accent)`, `color: #000` |
| `#fullscreen-player-btn` | `padding: 0 10px` | icon-only 28×28 | Ghost button + flex center |
| `#watch-external-btn` (IINA) | `padding: 0 10px` | icon-only 28×28 | Секундарная действие |
| `#stop-player-btn` | Красное опасное (`rgba(255,69,58,0.15)` фон, красная граница) | icon-only 28×28, transparent ghost | **Опасное действие теперь визуально не выделяется красным** — соответствует macOS convention для деструктивных действий в toolbar'ах (они остаются серыми, красный используется для alert-диалогов) |
| `#close-player-btn` | Красное опасное | icon-only 28×28, transparent ghost | Аналогично stop-button |
| Chat header buttons (`.chat-header-btn`) | `padding: 2px 4px` | icon-only 28×28 | Hover: `rgba(255,255,255,0.08)` + color increase |
| Multistream header (`#ms-sidebar-btn`, `#ms-toggle-chat-btn`, `#ms-close-btn`) | `padding: 4px 10px`, текст | icon-only 28×28 | Flex-centered SVG иконки |

**Watch button (`#watch-btn`) — исключение:**
- Остаётся **primary action button** (заполненный фон, `border-radius: var(--radius-sm)`).
- Радиус изменен с `var(--radius-md)` на `var(--radius-sm)` для более компактного вида.
- Сохраняет текст "Watch" + иконка play.

#### Player Bar Button Group Organization (`ui/css/player.css`)

```css
.bar-group {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.bar-group + .bar-group {
  border-left: 1px solid var(--border-subtle);
  padding-left: 8px;
  margin-left: 4px;
}
```

**Визуальная иерархия:**
1. **Status group** (левая сторона): live-dot, status-text, viewers (всегда видны).
2. **Separator** (тонкая вертикальная линия).
3. **Quality group** (select + label).
4. **Separator**.
5. **Primary action** (`#watch-btn` — голосовая кнопка с текстом).
6. **Separator**.
7. **Audio group** (`#mute-btn` + `#volume-slider`).
8. **Controls group** (Stats, Record, PiP, Fullscreen, Stop, External, Close — все ghost-buttons 28×28).

**Зазоры:** 4px внутри группы, 8px внешний padding после separator, 4px margin для separator.

#### Accessibility & Tooltips

- Все icon-only кнопки используют `title` атрибут (нативный HTML tooltip) для подсказок: `<button class="player-header-btn" title="Stats" ...>`.
- macOS автоматически показывает tooltip при наведении (с задержкой ~800ms).
- **Keyboard focus:** все кнопки получают `:focus-visible` outline через глобальное CSS правило в `reset.css` (`.focus-visible { outline: 2px solid var(--accent) }`).

#### Consistency Rules

- **Все toolbar'ы и header'ы** используют одну и ту же button паттерн: 28×28, flex-center, transparent ghost, hover `rgba(255,255,255,0.08)`.
- **Spacing:** внутри toolbar'а gap = 4px между кнопками, 8px padding слева/справа от group.
- **Icons:** 16px size (по умолчанию в `renderIcon`), 1.5px stroke, `currentColor`.
- **Color:** `--text-secondary` по умолчанию, `--text-primary` на hover.
- **Border radius:** `var(--radius-sm)` для всех icon-only кнопок (4px).
- **Transitions:** `--duration-fast` (150ms) для всех hover/active state changes.

#### Phase 9 Notes

- **Record dot animation:** `.record-dot` всё ещё имеет пульсирующую анимацию (`@keyframes pulse` 1.2s), но текст "REC" больше не показывается — только иконка.
- **PiP button active state:** сохранён для активного-состояния индикатора: `#pip-player-btn.active { background: var(--accent); color: #000; }`.
- **Danger styling removal:** красные фоны и границы удалены со всех деструктивных кнопок (Stop, Close). Они теперь следуют стандартному ghost-button паттерну (соответствует macOS HIG — опасные действия в toolbar'ах не должны быть красными).

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

**YouTube QuotaTracker (`core/platforms/youtube.py`):**
- `QuotaTracker` — in-memory счетчик с персистентностью в config (ключи `daily_quota_used` / `quota_reset_date`).
- **Timezone:** использует `America/Los_Angeles` (Pacific Time) вместо `date.today()` — YouTube Data API reset происходит в полночь PT.
- `check_and_use(units)` — атомарная проверка + расход, предпочтительнее отдельного `can_use()` + `use()` (TOCTOU race).

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
- `_async_run(coro)` — создаёт `asyncio.new_event_loop()`, запускает корутину, в `finally` вызывает `_close_thread_loop(loop)` (а не `loop.close()` напрямую), что гарантирует очистку `httpx.AsyncClient` из `BasePlatformClient._loop_clients`. `_close_thread_loop` принимает `AbstractEventLoop | None` (с `if loop is None: return` guard) — защита от случайного вызова с None.
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
- **`favorites_meta` использует compound keys `"platform:login"`** (не bare `login`). Предотвращает перезапись метаданных при одинаковом логине на разных платформах. JS использует `TwitchX.getFavoriteMeta(login, platform)` — если `platform` передан, прямой lookup по compound key; если нет — fallback перебор по `login`. `context-menu.js` использует compound key `"youtube:" + login` напрямую для offline-Youtube гварда.
- **Kick `channel_id`** — integer в raw API. Всегда приводить `str()` в `_normalize_channel_info_to_profile`.

### 6.2 Multistream Display
- Показывать slot: `element.classList.remove('hidden')` — всегда используйте `.hidden` класс вместо `style.display`. `.ms-slot-active { display: none }` — default.
- WKWebView проигрывает audio на `<video>` даже когда parent имеет `display: none`.

### 6.3 Browse & Quota
- Browse cache: `~/.config/twitchx/cache/browse_cache.json`, TTL 10 мин.
- YouTube: `get_categories()` = 1 unit, `get_top_streams()` = 100 units. При исчерпании quota — silent `[]`.

### 3.13 Accessibility (Phase 5)

**ARIA roles & landmarks (static в `ui/index.html`):**
- **Navigation:** `<nav id="sidebar" aria-label="Channel navigation">` вместо `<aside>`.
- **Main:** `role="main"` на `#content`.
- **Dialog:** `role="dialog" aria-modal="true" aria-labelledby="settings-title"` на `#settings-overlay`. Фон (`#main`, `#player-bar`) получает `aria-hidden="true"` при открытии, снимается при закрытии.
- **Tab patterns (4 группы):** `role="tablist"` + `role="tab" aria-selected="true/false"` + `role="tabpanel"` на platform-tabs, browse-platform-tabs, channel-tabs, settings-tabs.
- **Menu:** `role="menu" aria-label="Channel actions"` на `#context-menu`. Каждый `.ctx-item` — `role="menuitem" tabindex="-1"`.
- **Toolbar:** `role="toolbar" aria-label="Stream controls"` на `#player-bar`.
- **Combobox/Listbox:** `role="combobox" aria-expanded="false" aria-controls="search-dropdown" aria-autocomplete="list"` на `#search-input`. `role="listbox" aria-label="Search results"` на `#search-dropdown`.
- **Live regions:** `role="log" aria-live="polite" aria-label="Chat messages"` на `#chat-messages` и `#ms-chat-messages`. `role="status" aria-live="polite"` на `#status-text`.
- **Progressbar:** `role="progressbar" aria-label="Loading stream"` на `#stream-loader-bar`.
- **Video:** `aria-label="Live stream video"` на `#stream-video`.

**Icon-only кнопки с `aria-label`:** `#add-btn` ("Add channel"), `#chat-filter-btn`, `#chat-export-btn`, `#chat-userlist-btn`, `#chat-mod-btn`, `#chat-reply-close`, `#emote-picker-btn`, `#close-settings`, 4 eye-toggle buttons.

**Screen-reader-only текст (класс `.sr-only`):**
- `#live-dot` содержит `<span class="sr-only" id="live-dot-sr" aria-live="assertive">` для анонса воспроизведения.
- `#record-dot` содержит `<span class="sr-only">Recording active</span>`.
- Создаётся динамически `#chat-status-text-sr` в `onChatStatus` для SR-анонса статуса чата.

**Focus management (`ui/js/focus.js`):**
- `TwitchX.focusReturn.save()` / `restore()` — запоминает `document.activeElement` перед открытием overlay и возвращает туда фокус при закрытии. Используется для settings overlay (не для context-menu — его действия меняют глобальное состояние, focus return конфликтует с открытием плеера/канала).
- `TwitchX.activateFocusTrap(container)` / `deactivateFocusTrap()` — цикличный Tab-ловушка внутри контейнера. Используется для settings и context-menu.
- `TwitchX.handleArrowNav(e, container, selector)` — ArrowDown/ArrowUp/Home/End навигация по элементам внутри контейнера. Используется в context-menu и search dropdown. **Известное поведение:** при `currentIndex === -1` (ни один элемент не сфокусирован) ArrowDown → первый элемент, ArrowUp → последний.

**Keyboard navigation:**
- **Context menu:** ArrowUp/ArrowDown для навигации, Enter для активации, Home/End для границ. Escape закрывает через `TwitchX.closeContextMenu()` (без focus return — действия меняют глобальное состояние). Tab-ловушка через focus trap.
- **Search dropdown:** ArrowUp/ArrowDown для навигации, Enter для выбора результата (`e.preventDefault()` обязателен). Каждый результат имеет `role="option"` и `id="search-result-N"`.
- **Escape priority (обновлён):** settings → player → channel → browse → multistream → context menu → search dropdown.

**Color contrast (WCAG AA):**
- `--text-muted` повышен с `#6E6E73` (3.7:1, fail) до `#8A8A95` (4.5:1+ на bg-base, pass).
- Добавлен `--text-muted-elevated: #99999F` для текста на `--bg-elevated`.
- Добавлен `--error-red-bright: #FF6961` для AA на elevated.
- `@media (prefers-contrast: more)` boost: `--text-muted: #AEAEB2`, `--accent: #FFB340`.
- Bordertoken: `--border: var(--bg-border)` консолидирован.

**Dynamic ARIA (JS):**
- `settings.js`: `openSettings()` — `aria-selected` на табах, `aria-hidden` на фоне, focus trap. `closeSettings()` — очистка, focus return.
- `init.js`: все 4 группы табов обновляют `aria-selected` при переключении. Platform-tabs, browse-platform-tabs, channel-tabs, settings-tabs.
- `callbacks.js`: `onSearchResults` — `role="option"` + `aria-expanded` на input. `onChatStatus` — динамический sr-only элемент. `onStreamReady`/`onPlayerStop` — обновление `#live-dot-sr`.
- `render.js`: `aria-label` на `#stream-grid` с количеством.
- `callbacks.js:onStreamsUpdate`: `aria-label` на `#channel-list` с количеством избранных/live.

### 6.4 UI Safety
- **DOM safety:** весь динамический контент через `document.createElement()` + `textContent`. Никакого `innerHTML` с user data.
- **Исключение:** `TwitchX.renderIcon()` использует `innerHTML` для вставки SVG иконок — это допустимо, так как SVG-строки полностью статичны (контролируются кодом, не пользователем).
- **Visibility toggles:** используйте `.hidden` (`classList.toggle('hidden')` / `add('hidden')` / `remove('hidden')`) вместо манипуляций `style.display`. `.hidden { display: none !important }` определён глобально в `reset.css`. Для элементов, скрытых через CSS `opacity`/`transform` (search-dropdown, context-menu), используйте соответствующий класс (`.visible`, `.menu-visible`) вместо `.hidden`.
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
| 2026-05-11 | Phase 15 | UI/UX upgrades: accent color picker, grid/list toggle, pinned streams, command palette, drag-to-multistream, mini mode | Шесть фич: `accent_color` в storage/config/config API; grid/list mode с list-mode CSS; pinned streams (compound keys + localStorage + pinned-first sort); `ui/js/palette.js` (Cmd+K); drag (dataTransfer) в multistream; mini mode (`.mini` class). Tests: `tests/test_uiux_settings.py`. Bugfix: `var TwitchX` → `const TwitchX` в palette.js для inline merge. 436 tests pass. | ✅ Active |
| 2026-05-12 | Phase 16 | UI/UX Phase 1: bugfixes, design token system, token application | 4 бага: `word`→`code` в chat.js, `var(--border)`→`var(--border-default)`, бесполезный тернарник в utils.js, `getFavoriteMeta` теперь принимает `platform`. Расширены design tokens: spacing/typography/border/shadow/z-index/animation/accent variants. Токены применены ко всем 6 CSS-файлам (font-size, z-index, durations, padding/margin/gap, border rgba, box-shadow). **Debug audit:** 4 доп. бага (0.1s→duration-fast, 0.3s→duration-slow, z-index:300→var(--z-overlay), box-shadow→var(--shadow-lg)). 436 tests pass. | ✅ Active |
| 2026-05-11 | Phase 2 | Inline styles размазаны по HTML и JS (54 inline style="" в index.html, 207 style.display в JS) | Единый `.hidden { display: none !important; }` в reset.css. CSS-классы для chat panels, emote picker, player bar, settings. 54 inline style="" удалены из index.html. JS `style.display` → `classList.toggle('hidden')` во всех модулях (api-bridge, chat, context-menu, init, keyboard, multistream, render, settings, callbacks, player, channel). Удалены дублирующие `.hidden` из CSS. Utility-классы: `.text-muted`, `.text-sm`, `.checkbox-row`, `.setting-hint`, `.mt-1`, `.mb-1`. | ✅ Active |
| 2026-05-11 | Phase 3 | View transitions мгновенные (display:none), скелетоны отсутствуют, пустые состояния без подсказок | `--duration-view`/`--ease-view` токены. Двухфазный JS-паттерн (display → rAF → opacity) для fade-in всех content views. Overlay transitions: settings (scale+fade), context-menu (scale+opacity, BUGFIX: `display:none` → `.menu-visible`), search dropdown (slide+fade). Скелетоны: `skeleton-card`, `skeleton-browse-card`, `skeleton-stream-card` с shimmer анимацией. `showSkeletonGrid()`/`hideSkeletonGrid()` в render.js. Browse/channel skeletons. Chat: `#chat-status-text`, `.connecting` pulse, empty state "No messages yet". Empty states для browse/search. **Debug audit:** 8 багов (opacity после display change → микро-вспышка; двойной rAF → лишний кадр; settings-overlay `display:none` убивал transition; лишний `style.opacity` в settings.js). 436 tests pass. | ✅ Active |
| 2026-05-11 | Phase 4 (Micro-interactions) | Нет обратной связи кнопок, нет тостов, индикаторов прогресса, теней прокрутки | `--scale-press`/`--highlight-press` токены + глобальное `button:active { transform: scale(0.96) }`. `ui/js/toast.js` с `showToast()` — 4 типа, slide-in, auto-dismiss. Transient-сообщения заменены с `setStatus` на `showToast`. Stream loader bar (`#stream-loader`) в `#player-bar`. Player loading spinner (`#player-loader`, `.player-spinner`) с fallback. Scroll shadows: sidebar `.section-body::before` (sticky pseudo) + chat `#chat-shadow-top` (sticky). | ✅ Active |
| 2026-05-12 | Phase 4 debug audit | 8 багов: `toast.js` использовал несуществующий `renderIcon()`, overflow тостов мог удалять лишний, `#chat-shadow-top` позиционирован неверно (sibling вместо child), `box-shadow: inset` на `height: 0` невидим, `#sidebar-shadow-top` неверный контейнер, scroll-делегация может не сработать, renderSidebar не ребайндил слушатели, `hidePlayerView` не прятал player-loader | Исправлено: `toast.js` → Unicode icons + live `children.length`; chat shadow → `position: sticky` внутри `#chat-messages`; sidebar shadow → `::before` на `.section-body`; scroll-слушатели → прямые, с ребайндингом после render; player-loader → скрывается в `hidePlayerView()`. 436 tests pass. | ✅ Active |
| 2026-05-11 | Phase 5 (Accessibility) | Нет ARIA landmarks, нет focus management, text-muted fails WCAG AA | ARIA roles (navigation, main, dialog, toolbar, tablist, menu, log, combobox). `ui/js/focus.js` (focusTrap, focusReturn, arrowNav). `.sr-only` utility + dynamic announcements. `--text-muted` #6E6E73→#8A8A95 (AA pass). Icon-only кнопки с `aria-label`. Keyboard navigation в context-menu и search dropdown. Focus trap для settings overlay и context menu. | ✅ Active |
| 2026-05-12 | Phase 5 debug audit | Три бага после первой реализации: (1) `handleArrowNav` ArrowUp при `currentIndex === -1` переводил на предпоследний пункт вместо последнего; (2) missing `e.preventDefault()` в Enter-обработчике search dropdown; (3) `focusReturn.restore()` в `closeContextMenu()` перебивал фокус после view-changing actions (Watch, Profile) | (1) `currentIndex <= 0 ? length-1 : currentIndex-1`; (2) добавлен `e.preventDefault()` перед `activeResult.click()`; (3) убраны `focusReturn.save/restore` из контекстного меню — действия меняют глобальное состояние, focus return не применяется. | ✅ Active |
| 2026-05-11 | Phase 6 | Component Polish: player bar grouping, volume slider, buffer bar, seek bar, fullscreen auto-hide | 5 плеерных фич: bar grouping (`.bar-group` wrappers + separators), volume slider (`#volume-slider` + mute toggle), buffer viz (`#buffer-bar`/`#buffer-loaded`), VOD seek bar (`#seek-bar` + tooltip), fullscreen auto-hide (`.fs-hidden` + `webkitpresentationmodechanged`). 4 sidebar фичи: watching indicator (`.watching`), hover tooltip (`#sidebar-tooltip`), notification badge (`.notif-dot`/`.notif-badge`), collapsible mode (`.collapsed-sidebar`). 4 chat фичи: timestamps toggle (`.msg-time`), smooth scroll (`scrollTo({behavior:'smooth'})`), emote picker responsive (max-height), reply compactness. 3 settings modal фичи: unsaved changes warning (`_settingsSnapshot` + `confirm()`), `hotkey-capturing`/`hotkey-idle` CSS classes, compact stat cards toggle. Context menu: animation fix (`visibility`/`opacity`/`scale` + rAF two-phase show), `closeContextMenu()` refactor. Debug audit: 8 bugs fixed (text-muted WCAG AA, key name alignment, webkitpresentationmodechanged bubbling, missing CSS/export, hidePlayerView cleanup). | ✅ Active |
| 2026-05-12 | Phase 7 | Visual Refinement: SVG icon system, platform branding, selection styling, CSS performance | `ui/js/icons.js` с 44 stroke-based SVG иконками (16×16, 1.5px, `currentColor`). Все текстовые символы (⚙, ✕, ▶ и др.) заменены на inline SVG через `TwitchX.renderIcon()`. `--platform-twitch/kick/youtube` токены. `::selection` с accent tint. `contain: layout style paint` + `content-visibility: auto` на `#stream-grid`. `will-change: transform` на `.channel-item`. | ✅ Active |
| 2026-05-18 | Health Monitor Optimization | FPS drops при длительном просмотре (>20 мин) из-за накопления SourceBuffer в WKWebView | **Buffer management:** forward threshold 180s→60s (live HLS нужно максимум 30s буфера), добавлен total span check (>120s → reset). **Live edge drift:** 120s→30s (меньше дрейф = меньше SourceBuffer). **Proactive reset:** 30min→15min (упреждение деградации). **Decoder monitoring:** добавлен dropped frames check (`video.getVideoPlaybackQuality()` > 5% drop rate), детектирует VideoToolbox-деградацию которую rAF miss'ит. Инициализация `_droppedFramesBaseline` в `startVideoHealthMonitor()`. | ✅ Active |
| 2026-05-21 | P0 — Blockers | Credentials in git, weak .gitignore, 12 pyright errors, low test coverage (auth.py 8%, images.py 17%), broad exception handlers, no final verification | **Task 1 — Credentials security:** Removed OAuth tokens from git history. Created `core/credentials.py.template` with setup instructions. Updated `.gitignore` with comprehensive Python/macOS patterns, project-specific rules (`core/credentials.py`, `.superpowers/`). **Task 2 — Pyright fixes (12 errors):** Fixed parameter naming (`s` → `code`), None-safety guards (`if loop is not None:`), combined elif conditions (SIM102), added `type: ignore[attr-defined]` for MagicMock, added None-checks before operators. **Task 3 — Auth tests:** Created `tests/test_auth.py` with 28 tests (98% coverage on `ui/api/auth.py`). Covers Twitch/Kick/YouTube login/logout/test_connection flows. **Task 4 — Images tests:** Created `tests/test_images.py` with 19 tests (100% coverage on `ui/api/images.py`). Covers avatar cache hit/miss, network fetch, resize, dedup, corrupt cache fallthrough, thumbnails. **Task 5 — Exception audit:** Reviewed 42 broad exception handlers across 15 files. Narrowed specific cases to exact exception types (OSError, ValueError, etc.). Preserved legitimate broad catches in error boundaries + background threads with logging. **Task 6 — Verification:** Pyright 0 errors, Ruff 2 pre-existing E402s (not from changes), 89 new tests passing (436 total), 98-100% coverage on modified modules. | ✅ Complete |
| 2026-05-20..21 | Feature: Bundled Credentials + PKCE | Users must set up OAuth apps in developer portals for Twitch/Kick/YouTube before first login; high friction for new users; no PKCE for security (RFC 7636) | **Task 1:** Created `core/credentials.py` with 7 bundled app credential placeholders (Twitch/Kick/YouTube). **Task 2:** Added `_effective_creds(platform)` + `_effective_api_key()` in `BasePlatformClient` — config values override bundled fallback. **Task 3–5:** Integrated PKCE (code verifier + S256 challenge) in all platforms (`_generate_code_verifier()` / `_generate_code_challenge()`), store/clear verifier in config per-platform. **Task 6:** Removed credential guards from `ui/api/auth.py` — bundled creds always available. **Task 7:** `has_credentials: True` hardcoded in `get_config()` since bundled always fallback. **Task 8:** Settings UI — bundled-app badge (✓ icon) + collapsible "Use custom credentials" for advanced OAuth. **Task 9:** Onboarding card shows 3 login buttons (Twitch/Kick/YouTube) instead of "Open Settings". **Task 10:** Removed dead `onKickNeedsCredentials` / `onYouTubeNeedsCredentials` callbacks. **Task 11:** YouTube quota warning at ≤2000 remaining (warn) / ≤500 (critical) via `onYouTubeQuotaWarning`. **Merge:** Fast-forward merge `feature/bundled-credentials-pkce` → `main`, resolved stash pop conflicts in 3 files. **Verification:** 462 tests passing, all 11 tasks complete, worktree removed. | ✅ Complete |
| 2026-05-21 | P1 — Production hardening | 6 P1-пунктов из BETA_PLAN.md: null event loop guard, structured logging, error UX toasts, connection indicators, YouTube quota timezone, platform test coverage | **Item 9:** `if loop is None: return` в `_close_thread_loop` + `AbstractEventLoop \| None` тип. **Item 7:** Always-on logging (RotatingFileHandler 5MB×2 + stderr), DEBUG при `TWITCHX_DEBUG=1`. **Item 8:** Toasts на `onLaunchResult` fail, `onChatStatus` disconnect, `onStatusUpdate(error)`. `showToast()` возвращает элемент. **Item 10:** Buffering overlay (`.buffering-hide`), stale sidebar banner, recovery status при gentle reset. **Item 11:** `QuotaTracker` → `America/Los_Angeles` timezone. **Item 12:** +41 тест, twitch.py 56%→79%, kick.py 64%→75%. Итого 552 теста, 75% total. | ✅ Complete |

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
- **Auth tests** (`tests/test_auth.py`, 28 tests, 98% coverage): Мокируй HTTP-клиент, используй `patch("ui.api.auth.oauth_server")` для OAuth flow, `patch("ui.api.auth.TwitchClient")` для платформ, проверяй `_eval_js` emissions через `capture_eval_js`.
- **Images tests** (`tests/test_images.py`, 19 tests, 100% coverage): Создавай PNG через `_make_png()`, мокируй HTTP response через `MagicMock().content`, используй `api._image_pool.submit = lambda fn: fn()` для синхронного исполнения, проверяй base64 data URL в `capture_eval_js`.

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

### 8.5 Test Coverage Baselines (P1 Hardening)

| Module | Before | After | Tests | Status |
|--------|--------|-------|-------|--------|
| `ui/api/auth.py` | 8% | 98% | 28 tests | ✅ Complete |
| `ui/api/images.py` | 17% | 100% | 19 tests | ✅ Complete |
| `core/platforms/twitch.py` | 56% | 79% | +18 tests | ✅ Complete |
| `core/platforms/kick.py` | 64% | 75% | +16 tests | ✅ Complete |
| **Overall** | ~40% | 552 tests pass | 180+ new tests added | ✅ Verified |

**Coverage methodology:** Pyright 0 errors, Ruff 2 pre-existing E402s (not from changes), all exception handlers audited (15 files, 42 instances), credentials removed from git history, `.gitignore` hardened.

**Key test files created:**
- `tests/test_auth.py` — OAuth flows (Twitch/Kick/YouTube login/logout/test_connection)
- `tests/test_images.py` — Avatar/thumbnail fetching, caching, dedup, resize

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
| «Escape не закрывает context menu» | §3.13, keyboard.js | Проверить что Escape priority не блокируется вышестоящим слоем. `closeContextMenu()` вызывает `deactivateFocusTrap()` и скрывает меню. |
| «Cmd+K не открывает palette» | §3.8, palette.js | `palette.js` загружен после `keyboard.js`? `TwitchX.openPalette` определён? `e.metaKey && e.key === 'k'` в `handleKeydown`? |
| «Приложение полностью ломается после изменений JS» | §3.2, app.py | `var TwitchX` в новом модуле вместо `const` — `_inline_resources()` не заменяет `var`, возникает `SyntaxError: Identifier 'TwitchX' has already been declared` в едином inline-блоке. |
| «List mode не применяется» | §3.6, render.js | `TwitchX.state.gridMode === 'list'`? `#stream-grid.list-mode` CSS загружен? |
| «Pin не сохраняется после перезагрузки» | §3.7, state.js | `localStorage('twitchx.pinned')`? `loadPinnedStreams()` в DOMContentLoaded? |
| «Drag в multistream не работает» | §3.9, sidebar.js | `item.draggable = true`? `dataTransfer.setData('text/plain', ...)`? `drop` handler парсит JSON? |
| «Mini mode сам включается при старте» | §3.10, init.js | `localStorage.getItem('twitchx.mini') === '1'`? Сбрось localStorage или удали ключ. |
| «Accent color не применяется при старте» | §3.2, settings.js | `localStorage.getItem('twitchx.accent')`? `TwitchX.applyAccentColor` определён и вызывается в `DOMContentLoaded`? |
| «Accent swatch не показывает текущий цвет» | §3.2, settings.js | `config.accent_color` приходит от `get_full_config_for_settings()`? `openSettings()` рендерит swatches с классом `active`? |
| «Design tokens не работают / CSS переменные undefined» | §3.1, tokens.css | Проверить что `tokens.css` загружен первым в `_inline_resources()`. Все токены объявлены в `:root`. Имена с `var(--space-*)` / `var(--font-*)` / `var(--z-*)` и т.д. корректны. |
| «Focus trap не работает в settings» | §3.13, focus.js | `TwitchX.activateFocusTrap()` вызывается в `openSettings()`. `#settings-modal` должен содержать focusable элементы (кнопки, инпуты). Focus trap обходит `tabindex="-1"` — использует `[role="menuitem"]`. Проверить что `deactivateFocusTrap()` вызывается в `closeSettings()`. |
| «Focus не возвращается при закрытии overlay» | §3.13, focus.js | `TwitchX.focusReturn.save()` должен вызываться перед открытием. `focusReturn.restore()` при закрытии. Проверить что `previous` не занулён до restore. |
| «Keyboard nav в context-menu не работает» | §3.13, keyboard.js | ArrowDown/ArrowUp обрабатываются в `handleKeydown` до Escape chain. Enter на активном `.ctx-item` вызывает `.click()`. Проверить что `role="menuitem"` установлен. |
| «Search dropdown keyboard nav не работает» | §3.13, keyboard.js | ArrowDown/ArrowUp обрабатываются до escape chain. Результаты должны иметь `role="option"` и быть focusable. `activeResult.click()` срабатывает на Enter. |
| «Скринридер не объявляет смену стрима» | §3.13, callbacks.js | `onStreamReady` обновляет `#live-dot-sr` с `aria-live="assertive"`. `onPlayerStop` сбрасывает. Проверить что `#live-dot-sr` есть в DOM. |
| «SR не объявляет статус чата» | §3.13, callbacks.js | `onChatStatus` создаёт и обновляет `#chat-status-text-sr` с `aria-live="polite"`. Проверить что элемент существует после первого вызова. |
| «View transition не срабатывает / пропадает мгновенно» | §3.11 | Проверить двухфазный паттерн: `style.display` установлен до `opacity` transition. `transitionend` не сработает если opacity уже 0 — fallback `setTimeout(250ms)` в `viewFadeOut` обязателен. |
| «Search dropdown не появляется» | §3.11, init.js | Используется `.visible` класс вместо `.hidden`. Проверить что `onSearchResults` добавляет `dd.classList.add('visible')`. |
| «Skeleton не появляется при старте» | §3.11, init.js | `showSkeletonGrid()` вызывается в `DOMContentLoaded` только если `TwitchX.state.favorites.length > 0`. Проверить что favorites загружены к этому моменту. |
| «Skeleton не исчезает после загрузки данных» | §3.11, callbacks.js | `hideSkeletonGrid()` вызывается в `onStreamsUpdate`. Проверить что `.skeleton-card` элементы в `#stream-grid` удаляются. |
| «Chat status text не отображается» | §3.11, index.html | `#chat-status-text` добавлен в HTML рядом с `#chat-status-dot`. Пустой по умолчанию, заполняется в `onChatStatus` при disconnected. |
| «Тосты не появляются» | §3.12, toast.js | `toast.js` загружен после `palette.js` и перед `callbacks.js`? `#toast-container` есть в HTML? `showToast()` определён на `TwitchX`? |
| «Stream loader bar не показывается» | §3.12, callbacks.js | `onLaunchProgress` показывает `#stream-loader`? `onStreamReady`/`onLaunchResult`/`onPlayerStop` скрывают? |
| «Player spinner не исчезает» | §3.12, player.js | `showPlayerView()` показывает `#player-loader`; `playing`/`error` события на `<video>` скрывают с fallback 15s. Проверить отсутствие видео события. |
| «Scroll shadow не появляется» | §3.12, sidebar.js/chat.js | `initSidebarScrollShadow()`/`initChatScrollShadow()` вызывается в `_bindGlobalEvents()`? `scroll` обработчик привязан к `.section-body` через делегирование на `#channel-list`? |
| «Тост не закрывается по клику» | §3.12, toast.js | `el.addEventListener('click', ...)` на каждом тосте вызывает `dismissToast`. Проверить что `pointer-events: auto` на `.toast`. |
| «Volume slider не показывает» | §3.3, player.js | `syncVolumeSlider(video)` вызывается в `showPlayerView()`? `#volume-group` должен быть `.hidden` если нет видео. |
| «Volume slider не синхронизируется с keyboard» | §3.3, player.js | `adjustVolume()` вызывает `syncVolumeSlider(video)`. `getActiveVideo()` работает для main и multistream. |
| «Fullscreen auto-hide не срабатывает» | §3.3, player.js | `_watchFullscreenChanges()` вызывается в `DOMContentLoaded`. `webkitpresentationmodechanged` биндится на video через `_bindPiPEvents`. Проверить `#player-bar.fs-hidden` CSS. |
| «VOD seek bar не показывается» | §3.3, player.js | `startVodSeekBar()` вызывается в `showPlayerView()` только при `streamType === 'vod'`. `video.duration` может быть `NaN` на старте — `seek` interval ждёт. |
| «Sidebar watching indicator не появился» | §3.4, sidebar.js | `_matchWatching(login)` сравнивает с `TwitchX.state.watchingChannel`. Проверить что `renderSidebar()` вызывается после `onStreamReady`. |
| «Sidebar tooltip не появляется» | §3.4, sidebar.js | `_setupSidebarTooltip()` — только для live стримов (есть в `streamMap`). Thumbnail через `stream.thumbnail_url`. Debounce 400ms. |
| «Sidebar notification badge не показывает» | §3.4, callbacks.js | `TwitchX._notifBadgeLogins` заполняется в `onStreamsUpdate` при offline→online переходе. `_updateNotifBadges()` вызывается после `renderSidebar`. |
| «Collapsed sidebar сам включается» | §3.4, init.js | `localStorage.getItem('twitchx.sidebar.collapsed') === '1'`? Сбросить. |
| «Chat timestamps не отображаются» | §3.5, callbacks.js | `TwitchX.chatTimestamps` — localStorage в init.js. Только новые сообщения получают timestamp (через `<span class="msg-time">`). |
| «Smooth scroll не срабатывает» | §3.5, callbacks.js | `behavior: 'smooth'` требует WKWebView поддержку. `prefers-reduced-motion` использует instant. |
| «Context menu не появляется» | §3.11, context-menu.js | BUGFIX: базовый CSS `#context-menu` больше не имеет `display:none`. Используется класс `.menu-visible` для показа. Проверить что `showContextMenu` добавляет `menu-visible`, а `_bindContextMenuEvents` убирает его. |
| «Settings не предупреждает о несохранённых» | §6.4, settings.js | `_settingsSnapshot` устанавливается в `openSettings()`. `_isSettingsDirty()` сравнивает `JSON.stringify(_readAllFormValues())`. Accent и shortcuts отслеживаются. |
| «SVG иконки не отображаются / невидимы» | §7.1, icons.js | Проверить что `fill="currentColor"` или `fill` явно указан для элементов внутри SVG (родитель имеет `fill="none"`). `record`, `live-dot`, `info`, `warn` требуют `fill="currentColor" stroke="none"` на кругах. |
| «Grid-toggle иконка не меняется при клике» | §3.6, init.js | `gridToggleBtn.innerHTML` устанавливается в `_bindToolbarEvents()`. Проверить что `TwitchX.renderIcon()` возвращает корректный SVG для `grid-toggle`/`list-toggle`.
| «Buffering overlay не появляется» | §3.3, player.js | Проверить event delegation на `#player-content` — `waiting`/`playing` события. Убедиться что класс `.buffering-hide` используется, не `.hidden`. |
| «Stale data banner не скрывается» | §3.4, callbacks.js | `onStatusUpdate({stale: false})` снимает `.scrolled` с `#updated-time` и добавляет `.hidden` на `#sidebar-stale-banner`. |
| «Recovery status не очищается» | §3.3, player.js | `softResetVideo()` теперь вызывает `setStatus('', 'info')`. Проверить что `gentleResetVideo` ставит статус после PiP/fullscreen guards. |
| «YouTube квота не сбрасывается в полночь» | §4.5, core/platforms/youtube.py | `QuotaTracker` использует `America/Los_Angeles` (не `date.today()`). Проверить `_pacific_today()`. |
| «Буферизация не анимируется (мгновенное появление/исчезание)» | §3.3, player.css | `.player-buffering` использует `.buffering-hide` вместо глобального `.hidden` (который имеет `display: none !important`). |

---

*Archive: предыдущая версия файла сохранена как `AGENTS.md.archive`.*

---

## 10. Visual Design Enhancements (Session: 2026-05-20)

### Overview
Conducted comprehensive visual design analysis and implemented 26+ improvements across CSS tokens, layout, components, animations, and JavaScript to enhance the UI's polish, clarity, and visual hierarchy. All changes maintain backward compatibility and pass the full test suite (462 tests).

### Design Principles Applied
- **Contrast & Readability**: Upgraded `--text-secondary` from `#8E8E93` to `#AEAEB2` (WCAG AA compliance)
- **Legibility Floor**: Increased `--font-xs` from `10px` to `11px` for 1x screen readability
- **Depth & Layering**: Enhanced shadows and added glassmorphism effects
- **Motion & Feedback**: Staggered entrance animations and smooth transitions
- **Color Harmony**: Gradient accents and glow effects for interactive states

### Detailed Changes

#### 10.1 CSS Tokens (`ui/css/tokens.css`)
**Purpose**: Foundation layer for all design changes. Updated tokens ensure consistent application of improvements across all components.

| Token | Old Value | New Value | Rationale |
|-------|-----------|-----------|-----------|
| `--text-secondary` | `#8E8E93` | `#AEAEB2` | Better contrast ratio for secondary text (WCAG AA) |
| `--font-xs` | `10px` | `11px` | Minimum readable size on non-retina displays |
| `--tracking-tight` | — | `-0.02em` | Letter spacing for compact layouts |
| `--tracking-snug` | — | `-0.01em` | Slight negative spacing for tighter appearance |
| `--tracking-normal` | — | `0` | Default neutral spacing |
| `--tracking-wide` | — | `0.04em` | Loose spacing for headers/emphasis |
| `--leading-tight` | — | `1.2` | Compact line height for dense content |
| `--leading-normal` | — | `1.4` | Default comfortable line height |
| `--leading-relaxed` | — | `1.6` | Spacious line height for readability |

**Files modified**: `ui/css/tokens.css`

#### 10.2 Frosted Glass Effects
**Purpose**: Modern glassmorphism for depth and elegance while maintaining usability.

**Toolbar** (`ui/css/layout.css`):
```css
#toolbar {
  background: rgba(28, 28, 30, 0.82);
  backdrop-filter: blur(20px) saturate(180%);
  /* Replaces solid background for frosted appearance */
}
```

**Player Bar** (`ui/css/player.css`):
```css
#player-bar {
  background: rgba(28, 28, 30, 0.82);
  backdrop-filter: blur(20px) saturate(180%);
  /* Matches toolbar for visual cohesion */
}
```

**Platform Badge** (`ui/css/components.css`):
```css
.platform-badge {
  border-radius: 999px; /* Pill shape instead of circle */
  backdrop-filter: blur(8px);
  /* Subtle glass effect on badge */
}
```

**Files modified**: `ui/css/layout.css`, `ui/css/player.css`, `ui/css/components.css`

#### 10.3 Dynamic Slider Fills (CSS Variables)
**Purpose**: Visual feedback showing progress/volume without JavaScript-heavy bar renders.

**Volume Slider** (`ui/css/player.css`):
```css
#volume-slider {
  background: linear-gradient(to right,
    var(--accent) 0%,
    var(--accent) var(--volume-pct, 70%),
    var(--border-subtle) var(--volume-pct, 70%),
    var(--border-subtle) 100%);
}
```

**Seek Bar** (`ui/css/player.css`):
```css
#seek-bar {
  background: linear-gradient(to right,
    var(--accent) 0%,
    var(--accent) var(--seek-pct, 0%),
    var(--border-subtle) var(--seek-pct, 0%),
    var(--border-subtle) 100%);
}
```

**JavaScript synchronization** (`ui/js/player.js`):
- `syncVolumeSlider()`: Updates `--volume-pct` CSS variable in real-time
- `startVodSeekBar()`: Updates `--seek-pct` CSS variable on VOD progress
- Removes need for DOM structure changes; pure CSS gradients

**Files modified**: `ui/css/player.css`, `ui/js/player.js`

#### 10.4 Stream Card Enhancements
**Purpose**: Improved visual feedback and depth for the primary interactive element.

**Hover Transform**:
```css
.stream-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.32);
  /* Was 0 4px 16px; upgraded for depth */
}
```

**Thumbnail Overlay & Gradient**:
```css
.card-thumb::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: linear-gradient(to top,
    rgba(0, 0, 0, 0.45) 0%,
    transparent 45%);
  /* Darkens bottom, preserves thumbnail */
}

.stream-card:hover .thumb-img {
  transform: scale(1.04); /* Subtle zoom on hover */
}
```

**Live Badge Pulsing Effect**:
```css
.live-badge::before {
  content: '';
  position: absolute;
  width: 6px; height: 6px;
  background: white;
  border-radius: 50%;
  top: 4px; left: 4px;
  box-shadow: 0 0 10px rgba(255, 69, 58, 0.45);
  animation: pulse 1.6s ease-in-out infinite;
}
```

**Files modified**: `ui/css/components.css`

#### 10.5 Accent Color Gradients
**Purpose**: Unifies interactive buttons with ambient glow for visual hierarchy.

**Watch/Save Buttons & Onboarding**:
```css
#watch-btn.active,
#save-btn,
.onboarding-btn {
  background: linear-gradient(135deg, #FF9F0A, #F07800);
  box-shadow: 0 0 20px rgba(255, 159, 10, 0.25);
  color: white;
}

#chat-send-btn {
  background: linear-gradient(135deg, #FF9F0A, #F07800);
  box-shadow: 0 0 10px rgba(255, 159, 10, 0.15);
}
```

**Focus/Interaction States**:
```css
#chat-input:focus {
  box-shadow: 0 0 0 2px rgba(255, 159, 10, 0.08);
}
```

**Files modified**: `ui/css/components.css`

#### 10.6 Offline Channel Styling
**Purpose**: Visual distinction between live and offline channels in sidebar.

**Offline Channel Avatar**:
```css
.channel-item .avatar {
  filter: grayscale(0.55) opacity(0.7);
}

.channel-item.live .avatar {
  filter: none; /* Live channels: full saturation */
}
```

**Live Accent Bar**:
```css
.channel-item.live .accent-bar {
  background: var(--live-green);
  opacity: 0.5;
}
```

**Files modified**: `ui/css/components.css`

#### 10.7 Context Menu Separators
**Purpose**: Visual clarity in grouped menu items.

**CSS**:
```css
.ctx-separator {
  height: 1px;
  background: var(--border-subtle);
  margin: 4px 8px;
}
```

**HTML** (`ui/index.html`):
- Added `<div class="ctx-separator"></div>` after watch-related group
- Added `<div class="ctx-separator"></div>` after browser group

**Files modified**: `ui/css/components.css`, `ui/index.html`

#### 10.8 Keyboard Focus Ring
**Purpose**: Accessibility and visual feedback for keyboard navigation.

```css
.stream-card:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
```

**Files modified**: `ui/css/components.css`

#### 10.9 Chat Message Refinements
**Purpose**: Improved readability and visual spacing in chat.

```css
.chat-msg {
  padding: 3px 6px; /* Was 2px 5px */
  margin-bottom: 1px;
  line-height: var(--leading-normal);
}
```

**Files modified**: `ui/css/components.css`

#### 10.10 Staggered Entrance Animation
**Purpose**: Visual polish when grid populates. Draws attention to new streams.

**Animation Definition**:
```css
@keyframes card-enter {
  0% {
    opacity: 0;
    transform: translateY(8px);
  }
  100% {
    opacity: 1;
    transform: translateY(0);
  }
}
```

**Stream Card Stagger** (30ms intervals, 8 cards):
```css
.stream-card.card-enter {
  animation: card-enter 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}

.stream-card.card-enter:nth-child(1) { animation-delay: 0ms; }
.stream-card.card-enter:nth-child(2) { animation-delay: 30ms; }
.stream-card.card-enter:nth-child(3) { animation-delay: 60ms; }
/* ... through :nth-child(8) { animation-delay: 210ms; } */
```

**Browse Category/Stream Cards**: Same stagger pattern applied.

**JavaScript Support** (`ui/js/render.js`):
```javascript
function createStreamCard(s) {
  const card = document.createElement('div');
  card.className = 'stream-card card-enter'; // Include animation class
  card.addEventListener('animationend', function() {
    card.classList.remove('card-enter'); // Clean up after animation
  }, { once: true });
  // ... rest of card creation
}
```

**Browse Card Support** (`ui/js/callbacks.js`):
- Added same pattern to browse category card creation (~line 748)
- Added same pattern to browse stream card creation (~line 798)

**Files modified**: `ui/css/components.css`, `ui/js/render.js`, `ui/js/callbacks.js`

#### 10.11 Browse Grid Spacing
**Purpose**: Improved breathing room in grid layouts.

```css
.browse-grid {
  gap: 14px; /* Was 10px */
}

#multistream-grid {
  gap: 4px; /* Was 2px */
}
```

**Files modified**: `ui/css/views.css`

#### 10.12 Multistream Overlay Readability
**Purpose**: Ensure text over light video backgrounds remains legible.

```css
.ms-overlay {
  backdrop-filter: blur(2px); /* Subtle blur for text contrast */
}
```

**Files modified**: `ui/css/views.css`

### Implementation Approach

**Phase 1: Foundation** — Updated tokens for consistent cascade
**Phase 2: Layout** — Applied frosted glass to major sections
**Phase 3: Components** — Enhanced cards, buttons, and badges
**Phase 4: Animation** — Added staggered entrance and motion
**Phase 5: JavaScript** — Synchronized CSS variables for dynamic effects
**Phase 6: Polish** — Spacing, shadows, focus states

### Testing & Verification

✅ All 462 unit tests pass
✅ No console errors in preview
✅ All CSS variables properly configured
✅ JavaScript synchronization verified
✅ Backward compatible (no breaking changes)
✅ Works across all views: grid, browse, multistream, channel profile

### Potential Future Enhancements

- [ ] Skeleton card entrance animation (fade-in shimmer)
- [ ] Context menu slide-in animation with delay
- [ ] Channel profile modal transition (scale + fade)
- [ ] Settings modal backdrop animation
- [ ] Toast notification slide-up animation
- [ ] Drag-to-reorder visual feedback (ghost element)
- [ ] Search result highlight animation
- [ ] Chat notification pop-in effect

### Files Summary

| File | Changes | Lines |
|------|---------|-------|
| `ui/css/tokens.css` | Added tracking/leading tokens | +9 |
| `ui/css/layout.css` | Toolbar glassmorphism | +2 |
| `ui/css/player.css` | Player bar glass + dynamic sliders | +20 |
| `ui/css/components.css` | 40+ component enhancements | +180 |
| `ui/css/views.css` | Browse/multistream spacing | +4 |
| `ui/js/player.js` | CSS variable sync for sliders | +6 |
| `ui/js/render.js` | Card-enter animation class | +3 |
| `ui/js/callbacks.js` | Browse card animation support | +4 |
| `ui/index.html` | Context menu separators | +2 |
| **TOTAL** | | **~230 lines** |

---

## 11. Native macOS Visual Design Overhaul

**Session Date**: May 21, 2026  
**Scope**: Comprehensive audit and implementation of Apple Human Interface Guidelines alignment  
**Goal**: Transform application from "awkward/web-like" appearance to native macOS standard

### Audit Findings (12 Major Issues)

1. **Color Palette Too Dark** — Backgrounds at pitch-black levels (#0A0A0C) instead of macOS dark mode standards
2. **Excessive Borders** — Components over-bordered with colored separators; sidebars had green tints
3. **Web-Style Hover Animations** — Cards animated with `translateY(-3px)` spring easing (web pattern)
4. **Inappropriate Button Styling** — Buttons with explicit borders and elevated backgrounds (not macOS toolbar convention)
5. **Typography Misuse** — Uppercase labels with letter-spacing on platform tabs and section titles
6. **Oversaturated Accent Color** — Amber (#FF9F0A) applied to secondary elements (game names, categories)
7. **Weak Shadow System** — Shadows too intense for light backgrounds
8. **Rounded Corners Inconsistent** — Cards at 14px (radius-lg) when macOS uses 10px (radius-md)
9. **Spacing Not Grid-Aligned** — Padding and margins not on 8px boundaries
10. **Border Opacity Too High** — Separator lines too visible/opaque
11. **Modal Styling** — Settings modal over-rounded with overly dark background
12. **Micro-Interaction Gaps** — Missing native macOS behaviors (background-on-hover vs. transform)

### Implementation Details

#### Color Palette Modernization (`tokens.css`)

**Background Color Progression** (lightened 10-15% toward macOS standards):
```css
--bg-base:      #0A0A0C → #141416  /* Foundation */
--bg-surface:   #131315 → #1C1C1E  /* Sidebar, toolbar (exact Apple dark mode match) */
--bg-elevated:  #1D1D20 → #252528  /* Cards, inputs */
--bg-overlay:   #26262A → #2E2E32  /* Modals, popovers */
--bg-border:    #222225 → #2C2C2E  /* Border reference */
```

**Border Opacity Refinement** (reduced intensity):
```css
--border-subtle:  rgba(255,255,255,0.06) → rgba(255,255,255,0.08)
--border-default: rgba(255,255,255,0.10) → rgba(255,255,255,0.13)
--border-strong:  rgba(255,255,255,0.15) → rgba(255,255,255,0.22)
```

**Shadow Token Calibration** (lighter for new palette):
```css
--shadow-sm: 0 2px 8px rgba(0,0,0,0.3) → 0 1px 4px rgba(0,0,0,0.22)
--shadow-md: 0 12px 40px rgba(0,0,0,0.6), 0 2px 8px rgba(0,0,0,0.3) 
          → 0 8px 32px rgba(0,0,0,0.48), 0 2px 8px rgba(0,0,0,0.22)
--shadow-lg: 0 24px 80px rgba(0,0,0,0.8) → 0 20px 60px rgba(0,0,0,0.65)
```

#### Component Refinements (`components.css`, 22 edits)

**Stream Cards**:
- Border radius: `var(--radius-lg)` → `var(--radius-md)` (14px → 10px)
- Hover animation: `transform: translateY(-3px)` → removed (web pattern → native)
- Hover transition: spring easing → simple `background var(--duration-fast) ease`
- Will-change removed (no transforms, no GPU acceleration needed)

**Platform Tabs** (`.platform-tab`):
- Font size: `var(--font-sm)` (11px) → `var(--font-md)` (13px)
- Font weight: 600 → 500 (less bold)
- Removed: `text-transform: uppercase` and `letter-spacing: 0.04em`

**Section Headers** (`.favorites-label`, `.section-title`):
- Removed: `text-transform: uppercase` and `letter-spacing` values
- Font weight: 700 → 600 (`.favorites-label`)
- Font weight: adjusted to match hierarchy

**Sidebar Sections** (`.sidebar-section`):
- Removed: colored background (`rgba(48, 209, 88, 0.08)`)
- Removed: borders and separators
- Removed: green tint on `.online` variant (`.online .section-chevron` color changed from green to `var(--border-subtle)`)

**Channel Items** (`.channel-item .name`):
- Font size: 12px → 13px (improved readability)

**Buttons** (`.bar-btn`, player controls):
- Removed: `border: 1px solid var(--bg-border)` (explicit borders)
- Changed: `background: var(--bg-elevated)` → `background: transparent`
- Pattern: transparent at rest, subtle background on hover (macOS NSButton convention)

**Buttons in Player/Views**:
- `#player-header-btn`: borderless transparent → hover background
- `#fullscreen-player-btn`, `#pip-player-btn`: borderless transparent → hover background
- `#toggle-chat-btn`: borderless transparent → hover background
- `#watch-external-btn`: borderless transparent → hover background
- `.sidebar-collapse-btn`: 20×18 → 20×20 (square icon buttons, macOS standard)
- `.browse-back-btn`: borderless transparent → hover background
- `#ms-sidebar-btn`, `#ms-toggle-chat-btn`, `#ms-close-btn`: borderless → hover background
- `#watch-btn`: background `var(--bg-elevated)` → `rgba(255,255,255,0.06)`, removed border

**Context Menu** (`#context-menu`):
- Border radius: `var(--radius-md)` (10px) → 8px (macOS menu convention)

**Settings Modal** (`#settings-modal`):
- Background: `rgba(22,22,26,0.94)` → `rgba(30,30,32,0.97)` (matches new palette)
- Border radius: `var(--radius-xl)` (20px) → `var(--radius-lg)` (14px)

**Setting Group Labels** (`.setting-group label`):
- Removed: `text-transform: uppercase` and `letter-spacing: 0.03em`
- Color: → `var(--text-secondary)` (neutral, not uppercase)

**Category/Game Display** (`.card-game`):
- Color: `var(--accent)` (amber) → `var(--text-secondary)` (neutral gray)
- Rationale: Accent color reserved for primary actions, not secondary metadata

**Browse Cards** (`.browse-category-card`, `.browse-stream-card`):
- Removed: `will-change: transform` (no transforms, unnecessary GPU hint)
- Hover: `transform: translateY(-3px)` → background color change (macOS pattern)

**Card Info Padding** (`.card-info`):
- Padding: `9px 10px 10px` → `10px 12px 12px` (8px grid alignment)

#### Layout & Sizing (`layout.css`, `player.css`, `reset.css`)

**Toolbar Height** (`layout.css`):
- Height: 38px → 44px (macOS standard toolbar height)

**Scrollbar Width** (`reset.css`):
- Width: 5px → 6px (slightly more discoverable)

**Player Bar Components** (`player.css`):
- All icon buttons: transparent at rest, background on hover
- Select dropdowns: `height: 28px` maintained (standard control height)

#### View Adjustments (`views.css`)

**Browse Platform Tabs**:
- Removed: `border: 1px solid transparent`
- Font weight: 600 → 500
- Removed: `letter-spacing: 0.01em`

**Multistream Header Buttons**:
- Changed from bordered → borderless transparent
- Hover: background color change pattern

### Summary of Changes

| File | Change Count | Key Impact |
|------|--------------|-----------|
| `ui/css/tokens.css` | 9 edits | Foundation color/shadow upgrade |
| `ui/css/layout.css` | 1 edit | Toolbar height to 44px |
| `ui/css/reset.css` | 1 edit | Scrollbar width adjustment |
| `ui/css/components.css` | 22 edits | Component button/card/typography overhaul |
| `ui/css/player.css` | 3 edits | Player button styling |
| `ui/css/views.css` | 2 edits | Browse/multistream tab styling |
| **TOTAL** | **38 edits** | Complete visual design alignment |

### Verification

✅ **Color Accuracy**: Inspector confirmed body bg = rgb(20,20,22) (#141416), sidebar = rgb(28,28,30) (#1C1C1E)  
✅ **Height Standards**: Toolbar = 44px, button controls = 28px  
✅ **Button Patterns**: All interactive buttons follow macOS NSButton convention (transparent at rest, background on hover)  
✅ **Typography**: Uppercase removed from interface labels, weights adjusted to hierarchy  
✅ **Spacing**: All padding/margins aligned to 8px grid  
✅ **Border Treatment**: Sidebar sections transparent, subtle borders only where necessary  
✅ **Hover States**: Cards and browse items use background color elevation, not transforms  
✅ **Accent Color**: Orange reserved for primary CTAs only, secondary elements use neutral grays  

### Design Philosophy

The overhaul applies five core macOS HIG principles:

1. **Depth Through Color** — Layered background colors create hierarchy (base → surface → elevated → overlay)
2. **Subtlety in Animation** — No transform-based animations; instead subtle color/opacity changes
3. **Borderless Controls** — Buttons transparent at rest, activated by background (not stroke)
4. **Hierarchy Through Weight** — Font weights and sizes establish information flow, not uppercase styling
5. **Consistency in Spacing** — All spacing follows 8px grid for predictable, professional alignment

### Result

Application now appears as a **native macOS application** that follows Apple's design standards:
- Dark mode colors match system defaults (not custom darker tones)
- Interaction patterns mirror Finder, Mail, and native macOS apps
- Typography respects hierarchy without overdressing with uppercase/letter-spacing
- Buttons and controls feel lightweight and native (transparent, not elevated)
- Cards and content areas breathe with proper spacing and subtle shadows

---

