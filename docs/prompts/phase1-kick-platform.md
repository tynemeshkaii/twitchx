# Phase 1: Kick Platform — Implementation Prompt

Перед началом работы ознакомься со всеми файлами проекта: CLAUDE.md, docs/superpowers/specs/2026-03-28-multiplatform-streaming-client-design.md, а также изучи текущее состояние кода (core/, ui/, tests/).

Используй цепочку: **brainstorming** (пропусти, т.к. дизайн уже есть — сразу используй **writing-plans**) → **subagent-driven-development** для реализации.

---

## Цель

Добавить полноценную поддержку Kick.com как второй стриминговой платформы. После этой фазы приложение должно показывать стримы Twitch и Kick одновременно, с фильтрацией по платформе, отдельным OAuth логином для Kick и Kick-вкладкой в настройках.

## Что нужно реализовать

### 1. `core/platforms/kick.py` — KickClient

Создай KickClient по образцу TwitchClient (`core/platforms/twitch.py`), но для Kick API.

**Kick API:**
- Base URL: `https://api.kick.com`
- Auth: OAuth 2.1 + PKCE через `https://id.kick.com`
- Redirect URI: `http://localhost:3457/callback` (тот же порт, что и для Twitch)

**Эндпоинты (официальный API):**

| Метод | Kick API endpoint | Примечания |
|-------|------------------|------------|
| `get_live_streams(channel_ids)` | `GET /public/v1/livestreams` | Фильтрация по slug'ам из favorites |
| `get_top_streams(category, limit)` | `GET /public/v1/livestreams` + sort | Сортировка по viewers |
| `search_channels(query)` | `GET /public/v1/channels?search={query}` | Поиск по slug/username |
| `get_channel_info(channel_id)` | `GET /public/v1/channels/{slug}` | Профиль канала |
| `get_followed_channels(user_id)` | Не поддерживается API | Возвращай `[]` (используем локальные favorites) |
| `follow/unfollow` | Не поддерживается API | Возвращай `False` |
| `get_categories(query)` | `GET /public/v2/categories` | Для будущего Browse |
| `resolve_stream_url(channel_id, quality)` | Через streamlink | `streamlink https://kick.com/{slug} {quality} --stream-url` |
| `exchange_code(code)` | `POST https://id.kick.com/oauth/token` | С PKCE verifier |
| `refresh_token()` | `POST https://id.kick.com/oauth/token` grant_type=refresh_token |
| `get_current_user()` | `GET /api/v1/user` с Bearer token |

**PKCE OAuth flow:**
1. Генерируй `code_verifier` (random 128 символов) и `code_challenge` = base64url(sha256(verifier))
2. Сохраняй `pkce_verifier` в `config["platforms"]["kick"]["pkce_verifier"]`
3. Auth URL: `https://id.kick.com/oauth/authorize?client_id=...&redirect_uri=...&response_type=code&scope=user:read&code_challenge=...&code_challenge_method=S256`
4. Exchange: POST с `code_verifier` в теле

**Паттерны из TwitchClient, которые нужно воспроизвести:**
- `_tconf()` → `_kconf()` для доступа к `config["platforms"]["kick"]`
- Per-event-loop httpx.AsyncClient (тот же `_get_client()` / `_loop_clients` паттерн)
- Per-event-loop asyncio.Lock для token refresh
- Авто-refresh токена при 401
- `close_loop_resources()` для cleanup
- `_reload_config()` для перечитывания конфига

**Важно:**
- KickClient НЕ наследуется от PlatformClient пока (это будет в будущей фазе, когда ABC будет полностью интегрирован). Сейчас он просто повторяет тот же интерфейс что и TwitchClient
- Streamlink поддерживает Kick нативно: `streamlink https://kick.com/username best --stream-url`

### 2. `core/oauth_server.py` — Поддержка PKCE callback

Текущий oauth_server (94 строки) работает на порту 3457 и ловит `?code=...`. Он уже подходит для Kick OAuth — менять его не нужно. Kick отправит code на тот же `http://localhost:3457/callback?code=...`.

**Но:** нужно убедиться что oauth_server не конфликтует при параллельных логинах. Если Twitch и Kick используют один порт — добавь `state` параметр в OAuth URL, чтобы отличать платформу в callback. Или просто запрещай параллельный логин (проще).

### 3. `ui/api.py` — Интеграция Kick в bridge

Расширь TwitchXApi:

**Новые поля в `__init__`:**
```python
from core.platforms.kick import KickClient

self._kick = KickClient()
self._platforms = {"twitch": self._twitch, "kick": self._kick}
```

**Новые методы (по аналогии с Twitch):**
- `kick_login()` — OAuth PKCE flow для Kick
- `kick_logout()` — очистка credentials в `config["platforms"]["kick"]`
- `kick_test_connection(client_id, client_secret)` — тест API доступа

**Модификация существующих методов:**
- `refresh()` — после Twitch fetch, запускай аналогичный Kick fetch. Объединяй стримы в один массив с полем `"platform": "kick"` / `"twitch"`.
- `add_channel(username, platform="twitch")` — добавь параметр platform, по умолчанию "twitch" для обратной совместимости
- `remove_channel(channel, platform="twitch")` — аналогично
- `search_channels(query, platform="twitch")` — аналогично, для Kick ищи по slug
- `get_config()` — включай Kick credentials status
- `get_full_config_for_settings()` — включай Kick client_id/client_secret
- `save_settings(data)` — обрабатывай Kick credentials
- `close()` — закрывай и `self._kick`
- `watch()` / `watch_external()` — для Kick стримов используй `streamlink https://kick.com/{channel} {quality}`

**Ключевое:** `_on_data_fetched` и весь data pipeline должен работать с объединённым списком стримов из обеих платформ. JS различает платформу по полю `"platform"`.

### 4. `ui/index.html` — UI изменения

**Фильтр по платформе в sidebar:**
```html
<div class="platform-tabs">
    <button class="platform-tab active" data-platform="all">All</button>
    <button class="platform-tab" data-platform="twitch">Twitch</button>
    <button class="platform-tab" data-platform="kick">Kick</button>
</div>
```
- Клик по табу фильтрует стримы и favorites по платформе
- "All" показывает всё
- Сохраняй активный фильтр в `state.activePlatformFilter` и в `config.settings.active_platform_filter`

**Platform badge на stream cards:**
- Маленький лейбл/иконка в углу карточки стрима показывающий платформу (T для Twitch, K для Kick)
- CSS класс `.platform-badge.twitch` / `.platform-badge.kick` с цветами брендов

**Settings modal — Kick tab:**
- Добавь вкладку "Kick" рядом с существующими настройками
- Поля: Client ID, Client Secret, Login/Logout кнопка, Test Connection
- Тот же паттерн что и для Twitch credentials

**Sidebar поиск:**
- Когда активен фильтр Kick, поиск ищет по Kick API
- Когда "All", ищи по текущей платформе (или обеим параллельно)

### 5. Tests — `tests/platforms/test_kick.py`

По аналогии с `tests/platforms/test_twitch.py`:
- Тесты PKCE challenge generation (verifier → challenge)
- Тесты фильтрации невалидных username/slug
- Тесты формирования API запросов
- Мокай httpx responses

## Текущая архитектура (Phase 0 completed)

```
core/
├── platform.py          # PlatformClient ABC + 6 dataclasses (StreamInfo, PlaybackInfo, etc.)
├── chat.py              # ChatClient ABC + 4 dataclasses
├── storage.py           # v2 config: platforms.twitch/kick/youtube + favorites as objects + settings
├── stream_resolver.py   # streamlink HLS resolver
├── launcher.py          # IINA external launch
├── utils.py
├── oauth_server.py      # localhost:3457 callback server
└── platforms/
    └── twitch.py        # TwitchClient (293 строк)

ui/
├── api.py               # TwitchXApi bridge (847 строк) — platform registry self._platforms
├── index.html           # Full UI (2128 строк)
└── theme.py

tests/
├── platforms/
│   └── test_twitch.py
├── test_storage.py      # 19 tests
├── test_app.py, test_launcher.py, test_stream_resolver.py, test_native_player.py
├── test_platform_models.py, test_chat_models.py
```

**Config v2 format (storage.py):**
```json
{
  "platforms": {
    "twitch": { "client_id": "", "client_secret": "", "access_token": "", "refresh_token": "", "token_expires_at": 0, "token_type": "app", "user_id": "", "user_login": "", "user_display_name": "" },
    "kick": { "client_id": "", "client_secret": "", "access_token": "", "refresh_token": "", "token_expires_at": 0, "pkce_verifier": "", "user_id": "", "user_login": "", "user_display_name": "" },
    "youtube": { ... }
  },
  "favorites": [
    {"platform": "twitch", "login": "xqc", "display_name": "xQc"},
    {"platform": "kick", "login": "xqc", "display_name": "xQc"}
  ],
  "settings": { "quality": "best", "refresh_interval": 60, "streamlink_path": "streamlink", "iina_path": "...", "active_platform_filter": "all", ... }
}
```

**Ключевые хелперы из storage.py:**
- `get_platform_config(config, "kick")` → dict с kick credentials
- `get_settings(config)` → dict с настройками
- `get_favorite_logins(config, "kick")` → `["xqc", "trainwreck"]`
- `get_favorites(config, "kick")` → `[{"platform": "kick", "login": "xqc", ...}]`

**ui/api.py уже имеет:**
- `self._platforms = {"twitch": self._twitch}` — добавь kick
- `self._get_twitch_config()` — аналогичный `_get_kick_config()`
- Все favorites уже объекты с `platform` полем
- `_on_data_fetched` уже добавляет `"platform": "twitch"` к stream items

## Команды

```bash
make test     # pytest tests/ -v
make lint     # ruff check + pyright
make fmt      # ruff format
make check    # lint + test
./run.sh      # запуск приложения
```

## Ограничения и подводные камни

1. **Kick API может измениться** — он относительно новый. Используй текущую документацию: https://docs.kick.com
2. **Streamlink Kick** — иногда Cloudflare блокирует. Добавь обработку ошибок.
3. **Один OAuth порт** — Twitch и Kick делят порт 3457. Не позволяй параллельный логин.
4. **Kick не имеет follow/unfollow API** — всё через локальные favorites.
5. **Kick slugs** — используются как channel ID (аналог login в Twitch).
6. **Не наследуй KickClient от PlatformClient** — ABC интеграция будет позже.

## Результат

После Phase 1:
- Приложение показывает стримы Twitch + Kick одновременно
- Можно фильтровать по платформе (All / Twitch / Kick)
- Kick OAuth логин работает (PKCE)
- Kick каналы можно добавлять в favorites
- Поиск работает для обеих платформ
- Stream cards показывают badge платформы
- Settings имеет вкладку Kick
- Все существующие тесты проходят + новые тесты для Kick

**Сначала напиши план (writing-plans), затем реализуй через subagent-driven-development.**
