# Phase 2: Twitch Chat — Implementation Notes

> Дата реализации: апрель 2026
> Статус: завершено, протестировано, задокументировано

---

## Обзор

Phase 2 добавляет в TwitchX встроенный чат для Twitch-стримов. Чат отображается справа от видеоплеера в `#player-view` и подключается к Twitch IRC через WebSocket. Поддерживаются badges, emotes, цветные ники, отправка сообщений, reply-threading, анонимное чтение и автоматический реконнект.

---

## Файловая структура

```
core/
└── chats/
    ├── __init__.py          (существовал)
    └── twitch_chat.py       (создан — IRC парсер + WebSocket клиент)

core/
└── chat.py                  (изменён — добавлены поля в ChatMessage, ChatStatus)

ui/
├── api.py                   (изменён — методы чата в TwitchXApi)
└── index.html               (изменён — HTML/CSS/JS панели чата)

tests/
└── chats/
    ├── __init__.py          (существовал)
    └── test_twitch_chat.py  (создан — 35 тестов)

pyproject.toml               (изменён — добавлена зависимость websockets>=16.0)
```

---

## 1. Модели данных (`core/chat.py`)

### `ChatMessage` — поля, добавленные в Phase 2

```python
@dataclass
class ChatMessage:
    # ... существующие поля ...
    msg_id: str | None = None               # UUID сообщения (тег id)
    reply_to_id: str | None = None          # reply-parent-msg-id
    reply_to_display: str | None = None     # reply-parent-display-name
    reply_to_body: str | None = None        # reply-parent-msg-body (unescaped)
```

### `ChatStatus` — поля, добавленные в Phase 2

```python
@dataclass
class ChatStatus:
    connected: bool
    platform: str
    channel_id: str
    error: str | None
    authenticated: bool = False  # True только при IRC-аутентификации (не justinfan)
```

`authenticated` — ключевой флаг: `True` означает, что IRC-соединение использует реальный OAuth-токен с `chat:read chat:edit` скоупами. При анонимном режиме или после логин-фейла — `False`. JS использует это поле, чтобы включать/выключать инпут.

---

## 2. IRC парсер (`core/chats/twitch_chat.py`)

### Протокол Twitch IRC

- **Эндпоинт:** `wss://irc-ws.chat.twitch.tv:443`
- **Authenticated:** `PASS oauth:<token>` + `NICK <user_login>`
- **Anonymous:** `PASS SCHMOOPIIE` + `NICK justinfan12345`
- **Capabilities:** `CAP REQ :twitch.tv/tags twitch.tv/commands`
- **Join:** `JOIN #<channel_login>`
- **PING/PONG:** Twitch шлёт `PING :tmi.twitch.tv`, обязательно отвечать `PONG :tmi.twitch.tv`
- **Send:** `PRIVMSG #<channel> :<text>`
- **Reply:** `@reply-parent-msg-id=<uuid> PRIVMSG #<channel> :<text>`

### Чистые функции парсинга

| Функция | Вход | Выход | Назначение |
|---------|------|-------|-----------|
| `parse_tags(raw)` | `"color=#FF4500;display-name=User"` | `dict[str, str]` | Парсинг IRCv3 тегов |
| `parse_badges(raw)` | `"subscriber/12,premium/1"` | `list[Badge]` | Badges (icon_url пустой, имя берётся из слэш-нотации) |
| `parse_emotes(raw, text)` | `"25:0-4,354:6-10"` | `list[Emote]` | Emote позиции + CDN URL |
| `parse_irc_message(line, channel)` | Сырая IRC строка | `ChatMessage \| None` | Главный парсер — PRIVMSG и USERNOTICE |
| `_unescape_tag(value)` | `"hello\\sworld"` | `"hello world"` | IRCv3 escape sequences |

### IRC-сообщение — формат

```
@badge-info=subscriber/12;badges=subscriber/12;color=#FF4500;
display-name=UserName;emotes=25:0-4;id=abc123;tmi-sent-ts=1234567890
:username!username@username.tmi.twitch.tv PRIVMSG #channel :Kappa hello
```

Регулярное выражение (`_IRC_RE`) извлекает:
- `tags` — всё после `@` до первого пробела
- `prefix` — `:nick!user@host`
- `command` — `PRIVMSG` или `USERNOTICE`
- `params` — `#channel :text`

### Эмоты — URL формат

```
https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/default/dark/1.0
```

Позиции emote в IRC — индексы Unicode code points в Python str (ASCII совпадает; emoji после Twitch API следует учитывать, но для MVP это нормально).

### USERNOTICE — системные сообщения

`msg-id` тег определяет тип:
- `sub`, `resub`, `subgift`, `submysterygift`, `giftpaidupgrade` → `message_type="sub"`, `is_system=True`
- `raid` → `message_type="raid"`, `is_system=True`
- Прочие → `message_type="text"`, `is_system=True`

Текст: поле `trailing` (пользовательское сообщение) имеет приоритет над `system-msg` тегом.

---

## 3. `TwitchChatClient` — WebSocket клиент

### Ключевые атрибуты

```python
self._ws: Any                               # websockets.ClientConnection
self._loop: asyncio.AbstractEventLoop       # event loop чата (для run_coroutine_threadsafe)
self._authenticated: bool                   # False = justinfan режим
self._running: bool                         # False = сигнал к остановке
```

### Жизненный цикл подключения

```
connect()
  ├── Выбор credentials (oauth vs justinfan)
  ├── while _running:
  │     websockets.connect() → PASS → NICK → CAP REQ → JOIN
  │     _emit_status(connected=True)
  │     while _running and not login_failed:
  │       recv() → split \r\n → for each line:
  │         PING → PONG
  │         "Login unsuccessful" → login_failed=True, break
  │         parse_irc_message() → _message_callback(msg)
  │     if login_failed → fallback to justinfan, continue
  │   ConnectionClosedOK → _emit_status(False), break
  │   Exception → backoff + retry (макс 5 попыток)
  └── _ws = None
```

### Логин-фейл и анонимный fallback

Если OAuth-токен не имеет `chat:read chat:edit` скоупов, Twitch отвечает:
```
:tmi.twitch.tv NOTICE * :Login unsuccessful
```

Клиент обнаруживает эту строку внутри `while _running and not login_failed`, устанавливает `login_failed=True`, выходит из цикла, переключается на `justinfan` credentials и повторяет подключение без задержки. JS получает `onChatStatus({connected: false, error: "anonymous"})`, а затем `{connected: true, authenticated: false}`.

### Реконнект с backoff

```python
RECONNECT_DELAYS = [3, 6, 12, 24, 48]  # секунды
```

При любом `Exception` (кроме `ConnectionClosedOK` и `_running=False`):
- Задержка `RECONNECT_DELAYS[attempt]` секунд
- Инкремент счётчика
- При `attempt >= 5` — эмит `"Max reconnect attempts reached"`, выход
- При успешном подключении — `attempt` сбрасывается в 0

### Отправка сообщения

```python
async def send_message(text, reply_to=None) -> ChatSendResult:
```

Охрана от пост-disconnect отправки:
```python
if not self._authenticated or not self._running:
    return ChatSendResult(ok=False, ...)
```

Reply-threading:
```
@reply-parent-msg-id=<uuid> PRIVMSG #<channel> :<text>
```

---

## 4. API bridge (`ui/api.py`)

### Новые методы в `TwitchXApi`

| Метод | Вызывается из | Назначение |
|-------|--------------|-----------|
| `start_chat(channel, platform)` | `watch()` | Создаёт клиент, запускает thread |
| `stop_chat()` | `stop_player()`, `close()`, `start_chat()` | Корректно останавливает клиент |
| `send_chat(text, reply_to, reply_display, reply_body)` | JS | Отправка + локальный echo |
| `save_chat_width(width)` | JS | Сохранение ширины панели |
| `save_chat_visibility(visible)` | JS | Сохранение видимости |
| `_on_chat_message(msg)` | `TwitchChatClient` callback | Пуш в JS `window.onChatMessage()` |
| `_on_chat_status(status)` | `TwitchChatClient` callback | Пуш в JS `window.onChatStatus()` |

### Threading model

```
Главный поток (pywebview)
  │
  ├─ chat_thread (daemon)
  │    asyncio.new_event_loop()
  │    loop.run_until_complete(client.connect(...))
  │    ↓
  │    _message_callback(msg) → _eval_js("window.onChatMessage(...)") ← thread-safe
  │    _status_callback(status) → _eval_js("window.onChatStatus(...)") ← thread-safe
  │
  └─ send_chat() вызывается из pywebview thread:
       asyncio.run_coroutine_threadsafe(client.send_message(...), client._loop)
       # client._loop — loop чата, сохранённый в connect()
```

**Критически важно:** `client._loop` сохраняется при входе в `connect()` через `asyncio.get_event_loop()`. `send_chat()` и `stop_chat()` используют `run_coroutine_threadsafe()` именно на этот loop — только так WebSocket остаётся на своём event loop.

### Локальный echo

Twitch IRC **не** отправляет ваши собственные сообщения обратно (нет `echo-message` capability). После успешной отправки `send_chat()` создаёт синтетический `ChatMessage` и пушит его в JS:

```python
echo = json.dumps({
    "author": login,
    "author_display": display,
    "is_self": True,
    "reply_to_id": reply_to,
    "reply_to_display": reply_display,
    "reply_to_body": reply_body,
    ...
})
self._eval_js(f"window.onChatMessage({echo})")
```

`is_self: True` → CSS класс `.self` → акцентный цвет ника.

---

## 5. UI (`ui/index.html`)

### HTML структура

```html
<div id="player-view">
  <div id="player-header">
    ...
    <button id="toggle-chat-btn" title="Toggle Chat (C)">💬</button>
  </div>
  <div id="player-content">             <!-- flex row -->
    <video id="stream-video" .../>
    <div id="chat-resize-handle"/>
    <div id="chat-panel">
      <div id="chat-header">
        <span id="chat-title">Chat</span>
        <span id="chat-status-dot"/>     <!-- зелёная точка при подключении -->
      </div>
      <div id="chat-messages"/>
      <div id="chat-new-messages">↓ New messages</div>
      <div id="chat-reply-bar">          <!-- появляется при активном reply -->
        <span>Replying to</span>
        <span id="chat-reply-nick"/>
        <span id="chat-reply-body"/>
        <button id="chat-reply-close">×</button>
      </div>
      <div id="chat-input-area">
        <input id="chat-input" maxlength="500"/>
        <button id="chat-send-btn">Send</button>
      </div>
    </div>
  </div>
</div>
```

### CSS layout

- `#player-content` — `display: flex` (row). Видео берёт `flex: 1; min-width: 0`, чат имеет фиксированную ширину с `--chat-width` CSS-переменной.
- `#chat-resize-handle` — 4px полоска, `cursor: col-resize`, при hover меняет цвет на accent.
- `#chat-panel.hidden` — `display: none`, видео в этом случае занимает всю ширину.

### JS state

```javascript
var chatAutoScroll = true;      // сброс при скролле пользователя
var chatAuthenticated = false;  // из status.authenticated
var chatReplyTo = null;         // { id, display, body } | null
```

### JS функции

| Функция | Назначение |
|---------|-----------|
| `window.onChatMessage(msg)` | Рендеринг нового сообщения |
| `window.onChatStatus(status)` | Обновление статуса, включение/выключение инпута |
| `renderChatEmotes(parent, text, emotes)` | Встройка emote-картинок в текст |
| `clearChatMessages()` | Очистка при реконнекте |
| `updateChatInput()` | Enabled/disabled логика инпута |
| `setChatReply(id, display, body)` | Активация reply-режима |
| `clearChatReply()` | Сброс reply-режима |
| `toggleChatPanel()` | Показ/скрытие панели + persist |

### Reply UX

1. При hover на сообщение появляется кнопка `↩` (position: absolute, right: 4px)
2. Клик → `setChatReply(msg_id, author_display, text)` → показывается `#chat-reply-bar`
3. Enter или клик Send → `pywebview.api.send_chat(text, reply_to_id, reply_display, reply_body)`
4. Escape → `clearChatReply()` + `stopPropagation()` (предотвращает деселект стрима)
5. Disconnect → автоматически `clearChatReply()`

### Безопасность (no XSS)

Все пользовательские данные устанавливаются только через `textContent`, `img.src`, `img.alt` — никакого `innerHTML` с данными от сервера. Badge и emote URL — только с CDN Twitch (`static-cdn.jtvnw.net`).

### Автоскролл

- `chatAutoScroll = true` по умолчанию
- При скролле: если расстояние до низа > 60px → `chatAutoScroll = false`, показывается `#chat-new-messages`
- При `chatAutoScroll = true` → каждое новое сообщение скроллит вниз
- При клике на `#chat-new-messages` → скролл вниз + `chatAutoScroll = true`
- Буфер: максимум 500 сообщений (старые удаляются из начала)

### Ресайз панели

Mouse drag на `#chat-resize-handle`:
- `mousedown` → начало drag
- `mousemove` → `newWidth = container.getBoundingClientRect().right - e.clientX`, clamp `[250, 500]`
- `mouseup` → `pywebview.api.save_chat_width(width)`

---

## 6. OAuth скоупы

Для полноценного чата (отправка сообщений) токен должен содержать:

```python
OAUTH_SCOPE = "user:read:follows chat:read chat:edit"
```

Файл: `core/platforms/twitch.py:22`

Если токен содержит только `user:read:follows` — Twitch IRC отвечает `NOTICE * :Login unsuccessful` и клиент автоматически переходит в анонимный режим (чтение работает, отправка заблокирована, инпут показывает "Chat is read-only (re-login to send)").

Для получения новых скоупов необходимо выйти и войти заново — существующий токен не может быть расширен без повторной авторизации.

---

## 7. Найденные и исправленные ошибки

### Баги при реализации

| Баг | Причина | Исправление |
|-----|---------|-------------|
| Чужие сообщения не появлялись | OAuth-токен без `chat:read` скоупа → IRC `Login unsuccessful` → бесконечный реконнект | Детектирование `NOTICE * :Login unsuccessful`, fallback на justinfan |
| Свои сообщения не появлялись | Twitch IRC не echo-бэкает отправителю | Локальный echo в `send_chat()` после `future.result()` |
| `stop_chat()` вешал процесс | `disconnect()` вызывался на чужом event loop | `run_coroutine_threadsafe(client.disconnect(), client._loop)` |
| Escape в чате снимал выбор стрима | `stopPropagation()` только при активном reply | `stopPropagation()` всегда при Escape в chat-input |
| Disconnect не уведомлял JS | `ConnectionClosedOK` не вызывал `_emit_status` | Добавлен `_emit_status(connected=False)` перед `break` |
| Отправка после disconnect | `send_message()` не проверял `_running` | Добавлена проверка `if not self._running` |

### Баги в аудите (исправлены после тестирования)

- `reply-bar` не очищался при disconnect → добавлен `clearChatReply()` в `onChatStatus` disconnect path
- `chatAuthenticated` не сбрасывался → теперь ставится из `status.authenticated` на каждый вызов `onChatStatus`

---

## 8. Тестирование (`tests/chats/test_twitch_chat.py`)

35 тестов в 7 классах:

| Класс | Что тестируется |
|-------|----------------|
| `TestParseTags` | Парсинг IRCv3 тегов, empty values, boolean-like |
| `TestParseBadges` | Subscriber/moderator/premium badges |
| `TestParseEmotes` | Один emote, несколько, одинаковые на разных позициях |
| `TestParseIrcMessage` | PRIVMSG с/без тегов, USERNOTICE (sub, resub, raid, subgift), PING, JOIN, числовые |
| `TestTwitchChatClientInit` | Начальное состояние |
| `TestTwitchChatClientConnect` | Анонимное и аутентифицированное подключение |
| `TestTwitchChatClientDisconnect` | Установка `_running=False` |
| `TestTwitchChatClientSend` | Анонимный → False, аутентифицированный → True |
| `TestTwitchChatClientPing` | PING → PONG отправка |
| `TestTwitchChatClientMessageCallback` | PRIVMSG вызывает callback |
| `TestTwitchChatClientLoginFailure` | Детект `Login unsuccessful` → fallback на justinfan |

Для мокинга WebSocket используется `_make_ws_mock(recv_side_effect)` + `_patch_ws(mock_ws)`, которые симулируют одно или несколько подключений через `@asynccontextmanager`.

---

## 9. Зависимости

```toml
# pyproject.toml
[project.dependencies]
websockets = ">=16.0"
```

Версия 16.0+ — потому что `websockets.connect()` в этой версии возвращает async context manager совместимый с `async with`.

---

## 10. Известные ограничения

1. **Emote positions и emoji.** Twitch считает позиции в UTF-16 code units. Python `str[start:end]` использует Unicode code points. Для ASCII и большинства Unicode они совпадают, но emoji (суррогатные пары в UTF-16) могут сдвигать позиции. Для MVP допустимо — затрагивает только `Emote.code` (alt-текст), не отображение.

2. **Badge icon URLs.** `parse_badges()` возвращает `icon_url=""`. Реальные URLs требуют Twitch Badge API (GET `/helix/chat/badges` и `/helix/chat/badges/global`), что дорого по запросам. Badges показываются только при наличии icon_url.

3. **Rate limiting.** Twitch ограничивает: 20 сообщений / 30 сек (обычный пользователь), 100 / 30 сек (модератор). Клиент не реализует rate limiting — при превышении Twitch просто не отобразит сообщения.

4. **Только Twitch.** Phase 3 добавит Kick чат по аналогичному паттерну.
