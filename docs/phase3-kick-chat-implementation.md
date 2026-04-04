# Phase 3: Kick Chat — Implementation Documentation

## Обзор

Phase 3 добавляет чат для Kick стримов. Kick использует **Pusher WebSocket** для чтения сообщений в реальном времени и **REST API** для отправки. Существующий chat panel из Phase 2 переиспользуется без изменений — вся новая логика находится в Python backend.

Реализация состоит из трёх слоёв:

```
core/chats/kick_chat.py      ← парсинг + WebSocket клиент
core/chat.py                 ← общие dataclass-ы (ChatMessage, ChatSendResult)
ui/api.py (start_chat)       ← интеграция в Python↔JS bridge
```

---

## Файлы

| Файл | Роль |
|------|------|
| `core/chats/kick_chat.py` | Парсинг Pusher-событий, эмоутов, `KickChatClient` |
| `core/chat.py` | Добавлен `ChatSendResult` dataclass |
| `core/chats/twitch_chat.py` | `send_message` переведён на `ChatSendResult` |
| `ui/api.py` | `start_chat`, `send_chat` расширены для Kick |
| `tests/chats/test_kick_chat.py` | 25 тестов на парсинг и поведение клиента |

---

## Протокол Kick Chat (Pusher)

Kick использует [Pusher](https://pusher.com/) protocol 7 поверх WebSocket — это **не обычный IRC и не чистый WebSocket** с текстом. Каждое сообщение — JSON-объект с полями `event`, `data`, `channel`.

### WebSocket URL

```
wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679
    ?protocol=7&client=js&version=8.4.0&flash=false
```

### Последовательность подключения

```
Client ──────────────────────────── Server
         <── {"event":"pusher:connection_established",
               "data":"{\"socket_id\":\"123.456\",
                         \"activity_timeout\":120}"}

         ──► {"event":"pusher:subscribe",
               "data":{"channel":"chatrooms.<id>.v2"}}

         <── {"event":"pusher_internal:subscription_succeeded",
               "channel":"chatrooms.<id>.v2", "data":"{}"}

         <── {"event":"App\\Events\\ChatMessageSentEvent",
               "data":"<double-encoded JSON>",
               "channel":"chatrooms.<id>.v2"}

         <── {"event":"pusher:ping"}
         ──► {"event":"pusher:pong"}
```

### Double-encoded JSON

Ключевая особенность протокола: поле `data` в Pusher-событии — это **строка**, содержащая JSON. Нужен двойной `json.loads()`:

```python
outer = json.loads(raw_websocket_frame)  # → dict с event, data, channel
inner = json.loads(outer["data"])        # → настоящее сообщение чата
```

---

## Парсинг: `parse_kick_emotes`

```python
# core/chats/kick_chat.py

def parse_kick_emotes(text: str) -> tuple[str, list[Emote]]:
```

Kick кодирует эмоуты в текст как `[emote:12345:KickEmoteName]`. Функция:

1. Находит все вхождения через regex `\[emote:(\d+):(\w+)\]`
2. Заменяет маркеры на чистый код (`KickEmoteName`)
3. Вычисляет позиции `start`/`end` в **уже очищенном** тексте (не в оригинале)
4. Строит URL: `https://files.kick.com/emotes/{id}/fullsize`

Пример:

```
Input:  "hi [emote:999:PogChamp] gg"
Output: ("hi PogChamp gg", [Emote(code="PogChamp", url="...999...", start=3, end=10)])
```

Позиции в очищенном тексте — это требование JS-рендерера из Phase 2, который делает `renderMessageWithEmotes` по `start`/`end` символам строки.

### Алгоритм (single-pass offset accumulator)

```
offset = 0
for each emote match:
    offset += len(text_before_match)   # накопили позицию в clean string
    start = offset
    end   = offset + len(code) - 1    # включительно
    clean_parts.append(code)
    offset += len(code)
```

---

## Парсинг: `parse_kick_event`

```python
def parse_kick_event(event: dict[str, Any]) -> ChatMessage | None:
```

Обрабатывает Pusher-событие и возвращает нормализованный `ChatMessage`. Возвращает `None` для всех не-чатовых событий (ping, subscription_succeeded и т.д.).

### Поддерживаемые event types

```python
_CHAT_EVENTS = {
    "App\\Events\\ChatMessageEvent",       # старый формат
    "App\\Events\\ChatMessageSentEvent",   # текущий формат
}
```

Kick исторически менял имена событий — поддержка обоих вариантов обеспечивает совместимость.

### Маппинг типов сообщений

```python
_MSG_TYPE_MAP = {
    "message":            "text",
    "reply":              "text",
    "subscription":       "sub",
    "gifted_subscription":"sub",
    "raid":               "raid",
}
```

`is_system = True` для всего, что не `"message"` или `"reply"`.

### Гибкое извлечение sender

Kick API нестабилен в именовании полей. Реализация защищается от двух известных форматов:

```python
sender = data.get("user") or payload.get("sender")
```

### Reply threading

Kick кодирует ответы через `metadata`:

```json
{
  "metadata": {
    "original_sender": {"username": "OtherUser"},
    "original_message": {"id": "uuid-xyz", "content": "original text"}
  }
}
```

Парсер извлекает это в поля `reply_to_id`, `reply_to_display`, `reply_to_body` — те же поля, что у Twitch, поэтому JS-рендерер reply-threads работает без изменений.

### Badges

```python
badges = [
    Badge(name=b["type"], icon_url="")
    for b in identity.get("badges", [])
    if "type" in b
]
```

Kick не отдаёт URL иконок бейджей в payload чата. `icon_url=""` — намеренно, JS-рендерер это обрабатывает.

---

## `KickChatClient`

```python
class KickChatClient:
    platform = "kick"
```

### Инициализация

```python
def __init__(self) -> None:
    self._ws: Any = None
    self._loop: asyncio.AbstractEventLoop | None = None
    self._message_callback: Callable[[ChatMessage], None] | None = None
    self._status_callback: Callable[[ChatStatus], None] | None = None
    self._channel: str | None = None
    self._chatroom_id: int | None = None
    self._broadcaster_user_id: int | None = None
    self._running = False
    self._authenticated = False
    self._token: str | None = None
```

### `connect()`

```python
async def connect(
    self,
    channel_id: str,
    token: str | None = None,
    chatroom_id: int | None = None,
    broadcaster_user_id: int | None = None,
    can_send: bool | None = None,
) -> None:
```

**Параметры:**
- `channel_id` — slug канала (для статус-коллбэков)
- `token` — OAuth access token (если есть, иначе анонимное чтение)
- `chatroom_id` — ID чатрума для подписки на Pusher channel
- `broadcaster_user_id` — ID стримера для REST отправки
- `can_send` — явный флаг: `True` только если есть токен + `broadcaster_user_id` + скоп `chat:write`

**Режим аутентификации:**

```python
self._authenticated = (
    bool(token) if can_send is None else bool(token) and can_send
)
```

Анонимное чтение работает без токена — Pusher публичный.

**Подписка на несколько channel aliases:**

```python
pusher_channels = [
    f"chatrooms.{chatroom_id}.v2",
    f"chatrooms.{chatroom_id}",
    f"chatroom_{chatroom_id}",
]
```

Kick менял naming convention. Подписка на все три варианта защищает от будущих изменений.

**Reconnect с backoff:**

```python
RECONNECT_DELAYS = [3, 6, 12, 24, 48]  # секунды
```

После 5 неудачных попыток — эмитит статус `"Max reconnect attempts reached"` и останавливается. `ConnectionClosedOK` — чистый disconnect, без reconnect.

### `send_message()`

В отличие от Twitch (где отправка идёт через тот же IRC WebSocket), Kick требует **отдельный HTTP POST**:

```
POST https://api.kick.com/public/v1/chat
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "content": "text",
  "broadcaster_user_id": 12345,
  "type": "user",
  "reply_to_message_id": "uuid"   ← только если reply
}
```

Возвращает `ChatSendResult` (не `bool`) с полным описанием результата.

**Обработка ошибок HTTP (`_extract_send_error`):**

| HTTP код | Сообщение |
|----------|-----------|
| 400 | Kick rejected this message. Check the length and reply target. |
| 401 | Kick chat token expired. Re-login to Kick. |
| 403 | Follower-only/subscriber-only или требования к аккаунту |
| 404 + reply_to | Kick could not find the message you're replying to. |
| 404 | Kick could not find this chat channel. |
| 429 | Rate limit hit. Wait a moment. |

**Проверка `is_sent`:**

```python
data = payload.get("data", {})
is_sent = bool(data.get("is_sent"))
```

Kick отвечает HTTP 200, но `is_sent: false` если сообщение было заблокировано фильтром. Проверяем явно.

---

## `ChatSendResult` dataclass

Добавлен в `core/chat.py`:

```python
@dataclass
class ChatSendResult:
    ok: bool
    platform: str
    channel_id: str
    message_id: str | None = None
    error: str | None = None
```

Используется и в `TwitchChatClient.send_message()`, и в `KickChatClient.send_message()` вместо `bool`. Позволяет JS получать точное описание ошибки через `window.onChatSendResult`.

---

## Интеграция в `ui/api.py`

### `start_chat(channel, platform)`

**Twitch:** без изменений.

**Kick:** выполняется в фоновом потоке, внутри нового event loop:

1. Читает `kick.access_token` и `kick.oauth_scopes` из конфига
2. Вызывает `KickClient.get_channel_info(channel)` — async REST запрос
3. Извлекает `chatroom_id` из `info["chatroom"]["id"]`
4. Извлекает `broadcaster_user_id` из `info["broadcaster_user_id"]`
5. Проверяет `can_send = bool(token and broadcaster_user_id and "chat:write" in scopes)`
6. Вызывает `KickChatClient.connect(...)` — блокирует поток до disconnect/error

```python
scopes = self._parse_scopes(kick_conf.get("oauth_scopes", ""))
can_send = bool(token and broadcaster_user_id and "chat:write" in scopes)
```

Если `chatroom_id` не найден — эмитит `onChatStatus` с ошибкой и завершается.

### `send_chat(text, reply_to, ...)`

Ключевое отличие от Twitch:

```python
if result.ok and platform == "twitch":
    # local echo — Twitch IRC не возвращает собственные сообщения
    self._eval_js(f"window.onChatMessage({echo})")

# для Kick local echo НЕ добавляется — Pusher возвращает echo back сам
```

Для обеих платформ вызывается:

```python
self._eval_js(f"window.onChatSendResult({send_result})")
```

JS использует `onChatSendResult` для отображения статуса отправки и обработки ошибок в UI.

### Тип `_chat_client`

```python
self._chat_client: TwitchChatClient | KickChatClient | None = None
```

`stop_chat()` и `_on_chat_message()` / `_on_chat_status()` не требовали изменений — они уже платформо-независимы.

---

## Тесты

Файл: `tests/chats/test_kick_chat.py` — 25 тестов.

| Класс | Что тестирует |
|-------|--------------|
| `TestParseKickEmotes` | single/multiple/no/empty/adjacent emotes, позиции, URL |
| `TestParseKickEvent` | базовое сообщение, эмоуты, бейджи, sub/gifted/raid, не-чат события, отсутствие sender, пустой color |
| `TestKickChatClientInit` | начальное состояние объекта |
| `TestKickChatClientConnect` | подписка на Pusher channel, статус-коллбэк при connect |
| `TestKickChatClientDisconnect` | `_running = False` после disconnect |
| `TestKickChatClientPing` | ping → pong ответ |
| `TestKickChatClientMessageCallback` | chat event вызывает callback с правильным ChatMessage |
| `TestKickChatClientReconnect` | reconnect с backoff при ошибках соединения |
| `TestKickChatClientSend` | без токена → False, с токеном → REST POST, без chatroom_id → False |

WebSocket мокается через `websockets.connect` patch — реальные соединения не открываются.

```bash
uv run pytest tests/chats/test_kick_chat.py -v   # 25 тестов
make check                                         # lint + все 177 тестов
```

---

## Коммиты

| SHA | Описание |
|-----|----------|
| `f04c081` | `feat(kick-chat): add emote parser for [emote:id:name] format` |
| `c61d713` | `feat(kick-chat): add Pusher event parser with badge/emote/system-msg support` |
| `dbe5cbc` | `feat(kick-chat): add KickChatClient with Pusher WebSocket connect/disconnect` |
| `dd4dbab` | `feat(kick-chat): add REST-based send_message for Kick chat` |
| `8f78340` | `feat(kick-chat): integrate KickChatClient into api.py bridge` |
| `f51f08f` | `fix(kick-chat): resolve lint issues in test file` |

---

## Ключевые решения и компромиссы

### Почему broadcaster_user_id, а не chatroom_id для REST

Kick API v1 `/public/v1/chat` принимает `broadcaster_user_id` как идентификатор, а не `chatroom_id`. Оба ID получаются из одного `get_channel_info()` запроса: `chatroom_id` нужен для Pusher подписки, `broadcaster_user_id` — для REST отправки.

### Почему нет local echo для Kick

Pusher WebSocket возвращает собственные сообщения обратно подписчику (echo). Если добавить local echo как для Twitch, сообщение отобразится дважды. Kick-путь полагается на WebSocket echo.

### Почему множественные Pusher aliases

Kick имеет задокументированные изменения naming convention (`chatrooms.{id}.v2`, `chatrooms.{id}`, `chatroom_{id}`). Подписка на все три варианты — превентивная мера от breaking changes на стороне Kick.

### Почему ChatSendResult вместо bool

Twitch и Kick имеют разные режимы сбоя. `bool` не позволяет передать причину в JS. `ChatSendResult` с полем `error` позволяет UI показать конкретное сообщение пользователю (например, "follower-only" или "token expired").

### Анонимное чтение

Pusher не требует авторизации для public channels. Любой может читать Kick чат без токена. Логин нужен только для `send_message`.

---

## Ограничения и известные вопросы

- **Kick emotes regex** `\w+` не захватывает эмоуты с дефисами или Unicode. На практике Kick emote names состоят из `[A-Za-z0-9_]`.
- **Badge icon_url пустой** — Kick не отдаёт URL иконок в чат payload. Потребует отдельного API запроса за badge assets если нужно отображать иконки.
- **Activity timeout** — Pusher отправляет ping каждые 120 секунд; клиент отвечает pong. Таймер активности на стороне клиента (отправлять ping если долго нет данных) не реализован — Pusher инициирует ping сам.
- **`reply` type** — Kick возвращает `"type":"reply"` для ответов на сообщения. Маппится в `"text"`, не `is_system`. Reply threading данные извлекаются из `metadata`.
