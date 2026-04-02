# Phase 3: Kick Chat — Implementation Prompt

Перед началом работы ознакомься с CLAUDE.md, docs/superpowers/specs/2026-03-28-multiplatform-streaming-client-design.md, а также изучи текущий код: `core/chats/twitch_chat.py` (346 строк — образец для Kick), `ui/api.py` (1345 строк — bridge), `core/platforms/kick.py` (280 строк — KickClient).

Используй цепочку: **writing-plans** → **subagent-driven-development**.

---

## Цель

Добавить чат для Kick стримов. Kick использует Pusher WebSocket для чтения и REST API для отправки. Chat panel из Phase 2 уже есть и полностью переиспользуется — нужен только Python backend (KickChatClient) и интеграция в bridge.

## Что нужно реализовать

### 1. `core/chats/kick_chat.py` — Pusher WebSocket клиент

**Протокол Kick Chat (Pusher):**

Kick использует Pusher protocol version 7 через WebSocket.

- URL: `wss://ws-us2.pusher.com/app/eb1d5f283081a78b932c?protocol=7&client=js&version=8.4.0-rc2&flash=false`
- Подключение: после connect приходит `{"event":"pusher:connection_established","data":"{\"socket_id\":\"...\",\"activity_timeout\":120}"}`
- Подписка на канал чата: отправить `{"event":"pusher:subscribe","data":{"channel":"chatrooms.<chatroom_id>.v2"}}`
- Подтверждение: приходит `{"event":"pusher_internal:subscription_succeeded","channel":"chatrooms.<chatroom_id>.v2"}`
- Сообщения чата: приходят как `{"event":"App\\Events\\ChatMessageSentEvent","data":"<double-encoded JSON string>","channel":"chatrooms.<chatroom_id>.v2"}`
- PING: Pusher шлёт `{"event":"pusher:ping"}`, ответ — `{"event":"pusher:pong"}`
- Activity timeout: если нет данных 120 секунд, клиент отправляет ping

**Структура chat message (после двойного JSON decode):**

Поле `data` в event — это JSON-строка, которую нужно распарсить ещё раз. Результат:
```json
{
  "id": "uuid",
  "chatroom_id": 12345,
  "content": "hello world",
  "type": "message",
  "created_at": "2024-01-01T00:00:00.000000Z",
  "sender": {
    "id": 67890,
    "username": "user_name",
    "slug": "user-name",
    "identity": {
      "color": "#FF4500",
      "badges": [
        {"type": "subscriber", "text": "Subscriber", "count": 6}
      ]
    }
  }
}
```

**Маппинг в ChatMessage:**
- `platform` → `"kick"`
- `author` → `sender.slug`
- `author_display` → `sender.username`
- `author_color` → `sender.identity.color`
- `text` → `content`
- `timestamp` → `created_at`
- `badges` → из `sender.identity.badges`: `Badge(name=badge["type"], icon_url="")`
- `emotes` → Kick emotes встроены в текст как `[emote:12345:KickEmoteName]`. Парси их: `Emote(code="KickEmoteName", url="https://files.kick.com/emotes/12345/fullsize", start=..., end=...)`
- `is_system` → `type != "message"` (тип "subscription", "gifted_subscription" и т.д. — системные)
- `message_type` → маппинг из `type`: "message" → "text", "subscription"/"gifted_subscription" → "sub", "raid" → "raid"
- `msg_id` → `id`
- `raw` → полный dict сообщения

**Emotes в Kick:**

Kick emotes в тексте выглядят как `[emote:12345:KickEmoteName]`. Нужно:
1. Найти все `[emote:\d+:\w+]` в тексте
2. Заменить на Emote объект с URL: `https://files.kick.com/emotes/{id}/fullsize`
3. Для JS рендеринга: заменить текст `[emote:...]` на чистый code, установить start/end позиции

**Получение chatroom_id:**

chatroom_id нужен для подписки на Pusher канал. Его можно получить из channel info:
- Вызвать `KickClient.get_channel_info(slug)` — в ответе есть `chatroom.id` (или `chatroom_id` в зависимости от ответа API)
- chatroom_id передаётся в `connect()` напрямую (caller в api.py получит его заранее)

**Отправка сообщений (REST):**
- `POST https://api.kick.com/public/v1/chat` (или аналогичный эндпоинт)
- Headers: `Authorization: Bearer <access_token>`, `Content-Type: application/json`
- Body: `{"content": "текст", "chatroom_id": 12345, "type": "message"}`
- Нужен OAuth scope `chat:write`
- Если нет токена — send_message возвращает False

**Класс (по образцу TwitchChatClient):**
```
KickChatClient:
    platform = "kick"
    __init__() — ws, callbacks, channel, running, authenticated
    connect(channel_id, token=None, chatroom_id=None) — подключение к Pusher
    disconnect() — отключение
    send_message(text, reply_to=None) — POST REST
    on_message(callback) — регистрация callback
    on_status(callback) — регистрация callback
```

**Reconnection:** тот же паттерн что в TwitchChatClient — backoff delays [3, 6, 12, 24, 48].

**Анонимное чтение:** Pusher WebSocket не требует авторизации для чтения. Любой может подписаться и читать. Токен нужен только для отправки.

### 2. `ui/api.py` — Интеграция Kick chat

**Текущее состояние `start_chat()`:**
```python
def start_chat(self, channel: str, platform: str = "twitch") -> None:
    self.stop_chat()
    if platform != "twitch":
        return  # Only Twitch chat for now   ← УБРАТЬ
    ...
```

**Нужные изменения:**

1. Убрать `if platform != "twitch": return`

2. Добавить ветку для Kick:
   - Если `platform == "kick"`: создать `KickChatClient()` вместо `TwitchChatClient()`
   - Перед connect нужен chatroom_id — получить его через `self._kick.get_channel_info(channel)` в фоновом потоке
   - Передать token из `get_platform_config(self._config, "kick")` для отправки

3. `self._chat_client` должен быть типа `TwitchChatClient | KickChatClient | None`

4. `send_chat()` — для Kick не нужен local echo (Pusher может отправлять echo back, нужно проверить). Если Kick не шлёт echo — добавить аналогичный local echo как для Twitch. Если шлёт — не добавлять (иначе будет дубликат).

5. `_on_chat_message` и `_on_chat_status` — уже universal, работают для любой платформы. Менять не нужно.

**Вызов `start_chat` уже происходит в `watch()`** с правильным platform — никаких изменений в watch не нужно.

### 3. Парсинг Kick emotes для JS

В `_on_chat_message` emotes уже передаются как `[{code, url, start, end}]`. JS рендерер из Phase 2 (`renderMessageWithEmotes`) уже заменяет текст по позициям на `<img>`. Если Kick emote parser правильно устанавливает start/end (позиции в ОЧИЩЕННОМ от `[emote:...]` тексте), JS сработает автоматически.

**Важно:** решить, передавать ли текст с `[emote:...]` маркерами или уже очищенный. Рекомендация: очищай текст в Python (замени `[emote:...]` на code), пересчитай start/end позиции — тогда JS рендерер работает без изменений.

### 4. Tests — `tests/chats/test_kick_chat.py`

По образцу `tests/chats/test_twitch_chat.py` (427 строк):

- Парсинг Kick chat message JSON → ChatMessage
- Парсинг Kick emotes `[emote:12345:Name]` → Emote list с правильными позициями
- Парсинг badges из sender.identity
- System messages (subscription, gifted_subscription, raid)
- Pusher protocol: connection_established, subscription_succeeded, ping/pong
- Double JSON decode (data field is string containing JSON)
- Anonymous mode (no token, read-only)
- Send message REST formatting
- Reconnect logic

**Не тестируй реальный WebSocket** — мокай `websockets.connect`.

## Текущая архитектура

```
core/chats/
├── __init__.py
└── twitch_chat.py       # 346 строк — TwitchChatClient (образец)
                         # Pure functions: parse_tags, parse_badges, parse_emotes, parse_irc_message
                         # Class: TwitchChatClient (connect, disconnect, send_message, on_message, on_status)

core/chat.py             # ChatMessage, ChatStatus, Badge, Emote dataclasses
                         # ChatMessage имеет поля: msg_id, reply_to_id, reply_to_display, reply_to_body
                         # ChatStatus имеет поле: authenticated

core/platforms/kick.py   # KickClient — get_channel_info(slug) возвращает channel data с chatroom info

ui/api.py                # start_chat(channel, platform) — создаёт chat client и поток
                         # stop_chat() — disconnect + cleanup
                         # send_chat(text, reply_to, ...) — отправка + local echo для Twitch
                         # _on_chat_message(msg) → window.onChatMessage(json)
                         # _on_chat_status(status) → window.onChatStatus(json)
                         # self._chat_client: TwitchChatClient | None — нужно расширить тип
```

**Chat panel в UI (index.html) уже готов:**
- `#chat-panel` с `#chat-messages`, `#chat-input`, `#chat-send-btn`
- JS: `window.onChatMessage()` рендерит badges, emotes, nick colors, reply threads
- JS: `window.onChatStatus()` обновляет статус
- Resize handle, toggle кнопка, горячая клавиша C
- 500 message buffer, auto-scroll

**Config (storage.py):**
- `settings.chat_visible: true`, `settings.chat_width: 340`
- `platforms.kick.access_token` — для отправки

**152 теста, 0 ошибок lint/pyright.**

## Ограничения и подводные камни

1. **Pusher protocol.** Это НЕ чистый WebSocket с текстовыми фреймами — это JSON-based protocol поверх WebSocket. Каждое сообщение — JSON объект с полями `event`, `data`, `channel`.
2. **Double-encoded JSON.** Поле `data` в Pusher event — это JSON-строка (не объект), её нужно парсить отдельно через `json.loads(event["data"])`.
3. **chatroom_id.** Нужен для подписки. Получай через `KickClient.get_channel_info()` в `start_chat()`. Это async вызов — запусти его в том же потоке chat или отдельно перед connect.
4. **Kick emotes формат.** `[emote:12345:KickEmoteName]` — нестандартный формат. Парси regex, очищай текст, пересчитывай позиции.
5. **Activity timeout.** Pusher ожидает ping каждые 120 секунд. Если не послать — disconnect. Реализуй activity timer.
6. **Send через REST, не через WebSocket.** В отличие от Twitch IRC где send идёт через тот же WebSocket, Kick требует HTTP POST для отправки.
7. **Local echo.** Проверь, отправляет ли Pusher WebSocket твоё собственное сообщение обратно. Если да — local echo не нужен. Если нет — добавь как в Twitch.
8. **Не наследуй от ChatClient ABC** — как и TwitchChatClient.
9. **websockets библиотека** уже установлена (Phase 2).

## Результат

После Phase 3:
- При просмотре Kick стрима справа отображается чат (тот же chat panel что и для Twitch)
- Kick badges и emotes рендерятся
- Ники с цветами
- Отправка сообщений работает (если залогинен в Kick)
- Анонимное чтение без логина
- Автоматический реконнект при разрыве
- Sub/raid системные сообщения отображаются
- Все 152+ существующих тестов проходят + новые тесты для Kick chat
- Twitch chat продолжает работать как прежде

**Сначала напиши план (writing-plans), затем реализуй через subagent-driven-development.**
