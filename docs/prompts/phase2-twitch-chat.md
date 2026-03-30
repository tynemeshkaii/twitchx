# Phase 2: Twitch Chat (Native) — Implementation Prompt

Перед началом работы ознакомься со всеми файлами проекта: CLAUDE.md, docs/superpowers/specs/2026-03-28-multiplatform-streaming-client-design.md, а также изучи текущее состояние кода (core/, ui/, tests/).

Используй цепочку: **writing-plans** → **subagent-driven-development** для реализации. Дизайн уже утверждён — brainstorming не нужен.

---

## Цель

Добавить встроенный чат для Twitch стримов. Чат отображается справа от видео в player-view, с поддержкой badges, emotes, ников с цветами, отправки сообщений и анонимного чтения. Эта фаза устанавливает паттерн чата, который в Phase 3 будет переиспользован для Kick.

## Что нужно реализовать

### 1. `core/chats/twitch_chat.py` — IRC WebSocket клиент

Twitch IRC через WebSocket. Файл `core/chats/__init__.py` уже существует.

**Протокол:**
- URL: `wss://irc-ws.chat.twitch.tv:443`
- Библиотека: `websockets` (добавь в зависимости через `uv add websockets`)
- Anonymous: `PASS SCHMOOPIIE`, `NICK justinfan12345` (чтение без логина)
- Authenticated: `PASS oauth:<access_token>`, `NICK <user_login>`
- Capabilities: `CAP REQ :twitch.tv/tags twitch.tv/commands` (IRCv3 tags для badges, emotes, color)
- Join: `JOIN #<channel_login>`
- PING/PONG: Twitch шлёт `PING :tmi.twitch.tv`, ответ `PONG :tmi.twitch.tv`
- Send: `PRIVMSG #<channel> :<text>` (только authenticated)
- Rate limit: 20 msg / 30s (normal user), 100 msg / 30s (mod)

**Парсинг IRC сообщения:**
Входящая строка с tags:
```
@badge-info=subscriber/12;badges=subscriber/12,premium/1;color=#FF4500;display-name=UserName;emotes=25:0-4;id=abc123;tmi-sent-ts=1234567890 :username!username@username.tmi.twitch.tv PRIVMSG #channel :Kappa hello world
```

Нужно парсить:
- **tags** (всё до первого пробела после `@`): `badge-info`, `badges`, `color`, `display-name`, `emotes`, `tmi-sent-ts`
- **prefix**: `:username!username@username.tmi.twitch.tv`
- **command**: `PRIVMSG`
- **channel**: `#channel`
- **message**: всё после ` :`

**Badges parsing:**
`badges=subscriber/12,premium/1` → `[Badge(name="subscriber", icon_url="..."), Badge(name="premium", icon_url="...")]`

Badge URLs формат: `https://static-cdn.jtvnw.net/badges/v1/{badge_id}/3` (можно использовать заглушку, реальные URL через Twitch Badge API дорого — начни с name-only, icon_url пустой или стандартные имена).

**Emotes parsing:**
`emotes=25:0-4,354:6-10` → означает emote ID 25 на позициях 0-4, emote ID 354 на позициях 6-10.
Emote URL: `https://static-cdn.jtvnw.net/emoticons/v2/{id}/default/dark/1.0`

Парси в `list[Emote]`:
```python
Emote(code="Kappa", url="https://static-cdn.jtvnw.net/emoticons/v2/25/default/dark/1.0", start=0, end=4)
```

**Специальные сообщения (USERNOTICE):**
- `msg-id=sub` / `resub` / `subgift` → `message_type="sub"`
- `msg-id=raid` → `message_type="raid"`
- Эти приходят как `USERNOTICE` (не PRIVMSG). System message с `is_system=True`.

**Класс:**
```python
class TwitchChatClient:
    """Twitch IRC chat client via WebSocket."""

    platform = "twitch"

    def __init__(self) -> None:
        self._ws: websockets.ClientConnection | None = None
        self._message_callback: Callable[[ChatMessage], None] | None = None
        self._status_callback: Callable[[ChatStatus], None] | None = None
        self._channel: str | None = None
        self._running = False
        self._send_queue: asyncio.Queue[str] = asyncio.Queue()

    async def connect(self, channel_id: str, token: str | None = None) -> None:
        """Connect to Twitch IRC and join channel. token=None for anonymous."""
        ...

    async def disconnect(self) -> None:
        """Disconnect from IRC."""
        ...

    async def send_message(self, text: str) -> bool:
        """Send a chat message. Returns False if not authenticated."""
        ...

    def on_message(self, callback: Callable[[ChatMessage], None]) -> None:
        self._message_callback = callback

    def on_status(self, callback: Callable[[ChatStatus], None]) -> None:
        self._status_callback = callback
```

**Threading model:**
- Chat клиент работает в отдельном `threading.Thread` с `asyncio.new_event_loop()`
- `connect()` запускает бесконечный цикл приёма сообщений
- Callback `on_message` вызывается из этого потока
- `TwitchXApi._eval_js()` безопасен для вызова из любого потока

**Reconnection:**
- При разрыве соединения — автоматический реконнект через 3с, макс 5 попыток
- Экспоненциальный backoff: 3, 6, 12, 24, 48 секунд
- При успешном реконнекте — сброс счётчика

**НЕ наследуй от ChatClient ABC** — как и с PlatformClient, ABC интеграция будет позже. Просто повтори тот же интерфейс.

### 2. `ui/api.py` — Chat bridge методы

Добавь в TwitchXApi:

```python
from core.chats.twitch_chat import TwitchChatClient

# В __init__:
self._chat_client: TwitchChatClient | None = None
self._chat_thread: threading.Thread | None = None
```

**Новые методы:**

```python
def start_chat(self, channel: str, platform: str = "twitch") -> None:
    """Start chat for a channel. Called when entering player-view."""
    # Stop existing chat if any
    self.stop_chat()

    # Get token for authenticated mode (or None for anonymous)
    twitch_conf = get_platform_config(self._config, "twitch")
    token = twitch_conf.get("access_token") or None

    self._chat_client = TwitchChatClient()
    self._chat_client.on_message(self._on_chat_message)
    self._chat_client.on_status(self._on_chat_status)

    def run_chat():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._chat_client.connect(channel, token))
        except Exception:
            pass
        finally:
            loop.close()

    self._chat_thread = threading.Thread(target=run_chat, daemon=True)
    self._chat_thread.start()

def stop_chat(self) -> None:
    """Stop current chat connection."""
    if self._chat_client:
        # Signal disconnect
        ...
    self._chat_client = None

def send_chat(self, text: str) -> None:
    """Send a chat message."""
    if not self._chat_client:
        return
    # Dispatch to chat client's send
    ...

def _on_chat_message(self, msg: ChatMessage) -> None:
    """Callback from chat client — push to JS."""
    data = json.dumps({
        "platform": msg.platform,
        "author": msg.author,
        "author_display": msg.author_display,
        "author_color": msg.author_color,
        "text": msg.text,
        "timestamp": msg.timestamp,
        "badges": [{"name": b.name, "icon_url": b.icon_url} for b in msg.badges],
        "emotes": [{"code": e.code, "url": e.url, "start": e.start, "end": e.end} for e in msg.emotes],
        "is_system": msg.is_system,
        "message_type": msg.message_type,
    })
    self._eval_js(f"window.onChatMessage({data})")

def _on_chat_status(self, status: ChatStatus) -> None:
    """Callback from chat client — push connection status to JS."""
    data = json.dumps({
        "connected": status.connected,
        "platform": status.platform,
        "channel_id": status.channel_id,
        "error": status.error,
    })
    self._eval_js(f"window.onChatStatus({data})")
```

**Интеграция с player lifecycle:**
- `watch()` → после `onStreamReady`, вызывай `start_chat(channel, "twitch")`
- `stop_player()` → вызывай `stop_chat()` перед `onPlayerStop`
- `close()` → вызывай `stop_chat()`

### 3. `ui/index.html` — Chat panel UI

**Layout изменения в player-view:**

Текущий player-view:
```html
<div id="player-view">
  <div id="player-header">...</div>
  <video id="stream-video" autoplay controls playsinline></video>
</div>
```

Нужно превратить в split layout:
```html
<div id="player-view">
  <div id="player-header">
    ...existing...
    <button id="toggle-chat-btn" title="Toggle Chat (C)">💬</button>
  </div>
  <div id="player-content">
    <video id="stream-video" autoplay controls playsinline></video>
    <div id="chat-panel">
      <div id="chat-header">
        <span id="chat-title">Chat</span>
        <span id="chat-status-dot"></span>
      </div>
      <div id="chat-messages"></div>
      <div id="chat-input-area">
        <input id="chat-input" type="text" placeholder="Send a message..." maxlength="500" />
        <button id="chat-send-btn">Send</button>
      </div>
    </div>
  </div>
</div>
```

**CSS:**
```css
#player-content {
    display: flex;
    flex: 1;
    overflow: hidden;
}

#stream-video {
    flex: 1;
    min-width: 0;
}

#chat-panel {
    width: var(--chat-width, 340px);
    min-width: 250px;
    max-width: 500px;
    display: flex;
    flex-direction: column;
    background: var(--bg-surface);
    border-left: 1px solid var(--border);
}

#chat-panel.hidden {
    display: none;
}

#chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
    font-size: 13px;
    line-height: 1.4;
}

.chat-msg {
    padding: 2px 0;
    word-wrap: break-word;
}

.chat-msg .badge {
    width: 18px;
    height: 18px;
    vertical-align: middle;
    margin-right: 2px;
}

.chat-msg .nick {
    font-weight: 600;
    cursor: pointer;
}

.chat-msg .emote {
    height: 28px;
    vertical-align: middle;
}

.chat-msg.system {
    color: var(--text-muted);
    font-style: italic;
}

#chat-input-area {
    display: flex;
    padding: 8px;
    gap: 6px;
    border-top: 1px solid var(--border);
}

#chat-input {
    flex: 1;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-primary);
    padding: 6px 10px;
    font-size: 13px;
}
```

**JS обработчики:**

```javascript
// Chat message rendering
window.onChatMessage = function(msg) {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    const el = document.createElement('div');
    el.className = 'chat-msg' + (msg.is_system ? ' system' : '');

    // Badges
    for (const badge of msg.badges) {
        if (badge.icon_url) {
            const img = document.createElement('img');
            img.className = 'badge';
            img.src = badge.icon_url;
            img.alt = badge.name;
            el.appendChild(img);
        }
    }

    // Nick
    const nick = document.createElement('span');
    nick.className = 'nick';
    nick.textContent = msg.author_display;
    if (msg.author_color) nick.style.color = msg.author_color;
    el.appendChild(nick);

    // Separator
    const sep = document.createElement('span');
    sep.textContent = ': ';
    el.appendChild(sep);

    // Message text with emotes
    renderMessageWithEmotes(el, msg.text, msg.emotes);

    container.appendChild(el);

    // Buffer limit: 500 messages
    while (container.children.length > 500) {
        container.removeChild(container.firstChild);
    }

    // Auto-scroll (only if user hasn't scrolled up)
    if (isNearBottom(container)) {
        container.scrollTop = container.scrollHeight;
    }
};

function renderMessageWithEmotes(parent, text, emotes) {
    if (!emotes || emotes.length === 0) {
        parent.appendChild(document.createTextNode(text));
        return;
    }

    // Sort emotes by start position descending, then replace
    const sorted = [...emotes].sort((a, b) => a.start - b.start);
    let lastIdx = 0;

    for (const emote of sorted) {
        // Text before emote
        if (emote.start > lastIdx) {
            parent.appendChild(document.createTextNode(text.slice(lastIdx, emote.start)));
        }
        // Emote image
        const img = document.createElement('img');
        img.className = 'emote';
        img.src = emote.url;
        img.alt = emote.code;
        img.title = emote.code;
        parent.appendChild(img);
        lastIdx = emote.end + 1;
    }

    // Remaining text
    if (lastIdx < text.length) {
        parent.appendChild(document.createTextNode(text.slice(lastIdx)));
    }
}

function isNearBottom(el) {
    return el.scrollHeight - el.scrollTop - el.clientHeight < 60;
}

// Chat status
window.onChatStatus = function(status) {
    const dot = document.getElementById('chat-status-dot');
    if (dot) {
        dot.style.color = status.connected ? 'var(--live-green)' : 'var(--error-red)';
        dot.title = status.connected ? 'Connected' : (status.error || 'Disconnected');
    }
};

// Send message
document.getElementById('chat-input').addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && this.value.trim()) {
        pywebview.api.send_chat(this.value.trim());
        this.value = '';
    }
});

document.getElementById('chat-send-btn').addEventListener('click', function() {
    const input = document.getElementById('chat-input');
    if (input.value.trim()) {
        pywebview.api.send_chat(input.value.trim());
        input.value = '';
    }
});

// Toggle chat visibility
document.getElementById('toggle-chat-btn').addEventListener('click', function() {
    const panel = document.getElementById('chat-panel');
    panel.classList.toggle('hidden');
    pywebview.api.save_chat_visibility(!panel.classList.contains('hidden'));
});
```

**Горячая клавиша:** `C` — toggle chat panel (добавь в существующий keyboard handler, с проверкой что не в input)

**Auto-scroll behaviour:**
- По умолчанию — автоскролл к новым сообщениям
- Если пользователь прокрутил вверх (>60px от низа) — не скроллить
- Показывать кнопку "↓ New messages" внизу chat-messages когда есть непрочитанные

### 4. Chat input — анонимный режим

- Если пользователь не залогинен (нет access_token) → chat input disabled с placeholder "Log in to chat"
- Анонимное чтение работает всегда (justinfan)
- При логине → chat переподключается с токеном

### 5. Resizable chat panel

Добавь drag handle между video и chat для ресайза:
```html
<div id="chat-resize-handle"></div>
```
```css
#chat-resize-handle {
    width: 4px;
    cursor: col-resize;
    background: var(--border);
}
#chat-resize-handle:hover {
    background: var(--accent);
}
```
JS: mousedown на handle → mousemove меняет ширину chat-panel → mouseup сохраняет в config через `pywebview.api.save_chat_width(width)`.

### 6. Tests — `tests/chats/test_twitch_chat.py`

Файл `tests/chats/__init__.py` уже существует.

**Тесты:**
- IRC message parsing (PRIVMSG с tags)
- Badge parsing из tag строки
- Emote parsing из tag строки
- USERNOTICE (sub, raid) → system message
- PING → PONG response
- Anonymous nick generation
- Reconnect logic (mock WebSocket)
- Message buffer (не тестируй JS, только Python callbacks)
- Send message formatting

Тестируй парсинг вынеся его в чистые функции. Не тестируй WebSocket подключение в unit тестах — мокай `websockets.connect`.

## Текущая архитектура (после Phase 0 + Phase 1)

```
core/
├── platform.py          # PlatformClient ABC + 6 dataclasses
├── chat.py              # ChatClient ABC + 4 dataclasses (Badge, Emote, ChatMessage, ChatStatus)
├── storage.py           # v2 config, DEFAULT_SETTINGS includes chat_visible=True, chat_width=340
├── stream_resolver.py   # streamlink HLS resolver (supports platform="twitch"|"kick")
├── launcher.py          # IINA external launch
├── utils.py
├── oauth_server.py      # localhost:3457 callback
├── platforms/
│   ├── twitch.py        # TwitchClient (293 строк)
│   └── kick.py          # KickClient (280 строк)
└── chats/
    └── __init__.py      # пусто — сюда пойдёт twitch_chat.py

ui/
├── api.py               # TwitchXApi bridge (1184 строки) — self._platforms = {"twitch": ..., "kick": ...}
├── index.html           # Full UI (2353 строки) — player-view без чата пока
└── theme.py

tests/
├── platforms/
│   ├── test_twitch.py   # 17 тестов
│   └── test_kick.py     # 35 тестов
├── chats/
│   └── __init__.py      # пусто — сюда пойдёт test_twitch_chat.py
├── test_storage.py      # 19 тестов
├── test_app.py          # 13 тестов
├── test_platform_models.py, test_chat_models.py, test_launcher.py, test_stream_resolver.py, test_native_player.py
```

**Всего 117 тестов, 0 ошибок lint/pyright.**

**ChatMessage dataclass (core/chat.py):**
```python
@dataclass
class ChatMessage:
    platform: str              # "twitch"
    author: str                # login
    author_display: str        # display_name
    author_color: str | None   # hex color "#FF4500"
    avatar_url: str | None     # not used for IRC (None)
    text: str                  # message text
    timestamp: str             # ISO or tmi-sent-ts
    badges: list[Badge]        # [Badge(name="subscriber", icon_url="...")]
    emotes: list[Emote]        # [Emote(code="Kappa", url="...", start=0, end=4)]
    is_system: bool            # True for USERNOTICE (subs, raids)
    message_type: str          # "text" | "sub" | "raid"
    raw: dict[str, Any]        # original parsed tags dict
```

**Config settings (already in DEFAULT_SETTINGS):**
- `chat_visible: True` — показывать ли chat panel
- `chat_width: 340` — ширина chat panel в px

**Паттерн Python↔JS callback (используй как есть):**
```python
# Python → JS
self._eval_js(f"window.onChatMessage({json.dumps(data)})")

# JS → Python
pywebview.api.send_chat(text)
pywebview.api.start_chat(channel, platform)
pywebview.api.stop_chat()
pywebview.api.save_chat_width(width)
pywebview.api.save_chat_visibility(visible)
```

## Команды

```bash
make test     # pytest tests/ -v
make lint     # ruff check + pyright
make fmt      # ruff format
make check    # lint + test
./run.sh      # запуск приложения
uv add websockets  # добавить зависимость websockets
```

## Ограничения и подводные камни

1. **WebSocket в отдельном потоке.** Каждый chat thread имеет свой event loop. `TwitchChatClient.connect()` блокирует до disconnect. Callback `on_message` вызывается из chat thread — `_eval_js()` safe для этого.
2. **PING/PONG обязателен.** Twitch отключит если не ответить на PING в течение ~5 минут.
3. **Emote позиции в UTF-16.** Twitch emote positions считаются в UTF-16 code units, не в Python Unicode code points. Для ASCII это одинаково, но emoji сломают позиции. Для MVP можно игнорировать — сработает для 99% случаев.
4. **Anonymous rate limit.** justinfan может только читать, `send_message` должен возвращать `False`.
5. **Chat panel не должен ломать video.** Flex layout: video `flex: 1`, chat фиксированная ширина. Если chat hidden — video занимает всё.
6. **_shutdown Event.** При закрытии окна `_shutdown.is_set()` — chat должен корректно закрыться.
7. **Keyboard shortcut `C`.** Не должен срабатывать когда фокус в chat-input или другом input.
8. **Очистка chat** при смене канала. `start_chat()` вызывает `stop_chat()` сначала. JS должен очистить `#chat-messages` при `onChatStatus({connected: true})`.
9. **Не используй innerHTML для пользовательских данных.** Только `document.createElement()` + `textContent`. Emote и badge images через `img.src` с проверенными URL (только CDN twitch).

## Результат

После Phase 2:
- При просмотре Twitch стрима справа отображается чат в реальном времени
- Badges и emotes рендерятся как картинки
- Ники отображаются с цветами
- Можно отправлять сообщения (если залогинен)
- Анонимное чтение работает без логина
- Chat panel можно скрыть/показать (кнопка + горячая клавиша C)
- Chat panel можно ресайзить drag'ом
- Автоскролл к новым сообщениям (с паузой при прокрутке вверх)
- Sub/raid сообщения отображаются как системные
- Автоматический реконнект при разрыве
- Все 117+ существующих тестов проходят + новые тесты для чата

**Сначала напиши план (writing-plans), затем реализуй через subagent-driven-development.**
