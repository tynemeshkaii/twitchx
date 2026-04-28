# Фаза 1: Восстановление ABC (BasePlatformClient + BaseChatClient)

> **Дата:** 2026-04-28  
> **Статус:** План  
> **Обзорный документ:** [architecture-refactoring.md](./2026-04-28-architecture-refactoring.md)

---

## Цель

Восстановить работающие абстрактные базовые классы для платформенных и чат-клиентов:
- Вынести общую инфраструктуру из трёх платформенных клиентов в `BasePlatformClient`
- Вынести общую инфраструктуру из двух чат-клиентов в `BaseChatClient`
- Сделать ABC реально наследуемыми (сейчас `PlatformClient` и `ChatClient` не используются никем)
- Убрать ~260 строк дублированного кода

---

## Текущее состояние

### Проблема 1: `PlatformClient(ABC)` — мёртвый ABC

Файл `core/platform.py` (131 строка) определяет `PlatformClient(ABC)` с 14 абстрактными методами. **Ни один из трёх клиентов не наследует от него:**

```python
# core/platform.py:87 — ABC, который никто не использует
class PlatformClient(ABC):
    platform_id: str       # ← эти атрибуты никогда не устанавливаются
    platform_name: str     # ← потому что никто не наследует

    @abstractmethod
    async def get_auth_url(self) -> str: ...
    @abstractmethod
    async def exchange_code(self, code: str) -> TokenData: ...  # ← возвращает TokenData,
    # но все реализации возвращают dict[str, Any]
    # ... ещё 12 методов
```

```python
# core/platforms/twitch.py:25 — не наследует PlatformClient
class TwitchClient:        # ← нет "(PlatformClient)"
    ...

# core/platforms/kick.py:49 — тоже
class KickClient:          # ← нет "(PlatformClient)"
    ...

# core/platforms/youtube.py:124 — тоже
class YouTubeClient:       # ← нет "(PlatformClient)"
    ...
```

### Проблема 2: ~200 строк дублирования между тремя платформенными клиентами

Идентичный код в **каждом** из трёх файлов:

**А. Per-event-loop HTTP client pooling (~25 строк × 3 = 75 строк)**

```python
# core/platforms/twitch.py:28-30
_loop_clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}
_token_locks: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}
_loop_state_lock = threading.Lock()

# core/platforms/kick.py:52-54 — ИДЕНТИЧНО
_loop_clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}
_token_locks: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}
_loop_state_lock = threading.Lock()

# core/platforms/youtube.py:129-131 — ИДЕНТИЧНО
_loop_clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}
_token_locks: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}
_loop_state_lock = threading.Lock()
```

**Б. `_get_client()` — идентичен во всех трёх (Twitch:47-54 = Kick:72-79 = YouTube:141-148)**

```python
# Twitch (строки 47-54)
def _get_client(self) -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    if loop not in self._loop_clients:
        self._loop_clients[loop] = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={"User-Agent": "TwitchX/2.0", "Accept": "application/json"},
        )
    return self._loop_clients[loop]

# Kick (строки 72-79) — отличается только User-Agent и timeout
def _get_client(self) -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    if loop not in self._loop_clients:
        self._loop_clients[loop] = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),                    # ← 15 vs 30
            headers={"User-Agent": "TwitchX/2.0 (Kick)"},  # ← "(Kick)"
        )
    return self._loop_clients[loop]

# YouTube (строки 141-148) — отличается User-Agent, без Accept
def _get_client(self) -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    if loop not in self._loop_clients:
        self._loop_clients[loop] = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={"User-Agent": "TwitchX/2.0 (YouTube)"},
        )
    return self._loop_clients[loop]
```

**В. `_get_token_lock()`, `close_loop_resources()`, `reset_client()`, `_reload_config()`, конфиг-аксессоры `_tconf()`/`_kconf()`/`_yconf()`** — все дублируются с минимальными отличиями.

**Г. `_get()` и `_yt_get()` — общий паттерн 429-retry и 401-token-refresh**

Twitch `_get()` (строки 220-258), Kick `_get()` (строки 255-291), YouTube `_yt_get()` (строки 198-240) — все три содержат:
1. Логирование запроса (DEBUG)
2. Отправку запроса через `self._get_client()`
3. Обработку 429 → `asyncio.sleep(retry_after)` → повтор
4. Обработку 401 → сброс токена → `refresh_user_token()` → повтор
5. `resp.raise_for_status()`

YouTube добавляет обработку 403 (quota exceeded), но общая структура идентична.

### Проблема 3: `ChatClient(ABC)` — тоже мёртвый ABC

```python
# core/chat.py:73 — ABC, никем не наследуется
class ChatClient(ABC):
    @abstractmethod
    async def connect(self, channel_id: str, token: str | None = None) -> None: ...
    # ...
```

```python
# core/chats/twitch_chat.py:188 — не наследует ChatClient
class TwitchChatClient:    # ← нет "(ChatClient)"

# core/chats/kick_chat.py:157 — тоже
class KickChatClient:      # ← нет "(ChatClient)"
```

При этом **модели данных** из `core/chat.py` (`ChatMessage`, `ChatStatus`, `ChatSendResult`, `Badge`, `Emote`) реально **используются** обоими чат-клиентами — это лучше, чем в платформенной стороне.

### Проблема 4: ~60 строк дублирования между чат-клиентами

**А. Reconnect с exponential backoff — идентичен**

```python
# core/chats/twitch_chat.py:23 — константа
RECONNECT_DELAYS = [3, 6, 12, 24, 48]

# core/chats/kick_chat.py:154 — такая же константа
RECONNECT_DELAYS = [3, 6, 12, 24, 48]
```

Reconnect-логика (~25 строк в каждом файле): `attempt`-счётчик, `while self._running`, `asyncio.sleep(delay)`, проверка `attempt >= len(RECONNECT_DELAYS)` → постоянная ошибка.

**Б. `_emit_status()` — идентичен (Twitch:360-371, Kick:414-423)**

```python
def _emit_status(self, **kwargs):
    if self._status_callback and self._channel:
        self._status_callback(ChatStatus(
            platform=self.PLATFORM,  # ← отличается только эта строка
            channel_id=self._channel,
            **kwargs,
        ))
```

**В. `disconnect()` — идентичен (Twitch:304-310, Kick:291-297)**

```python
async def disconnect(self):
    self._running = False
    if self._ws:
        await self._ws.close()
    self._emit_status(connected=False)
```

**Г. `on_message()` / `on_status()` — идентичны**

```python
def on_message(self, callback):
    self._message_callback = callback

def on_status(self, callback):
    self._status_callback = callback
```

---

## Целевое состояние

### 1. Новый файл: `core/platforms/base.py` (~150 строк)

Содержит `BasePlatformClient(PlatformClient)` с общей инфраструктурой:

```python
# core/platforms/base.py
import asyncio
import logging
import threading
from typing import Any

import httpx

from core.platform import PlatformClient, TokenData
from core.storage import get_platform_config, load_config, update_config

logger = logging.getLogger(__name__)


class BasePlatformClient(PlatformClient):
    """Shared infrastructure for all platform API clients.

    Subclasses must set:
        PLATFORM_ID: str      — e.g. "twitch", "kick", "youtube"
        PLATFORM_NAME: str    — e.g. "Twitch", "Kick", "YouTube"
        AUTH_URL: str         — OAuth authorization endpoint
        TOKEN_URL: str        — OAuth token endpoint
    """

    PLATFORM_ID: str = ""
    PLATFORM_NAME: str = ""

    # --- Per-event-loop httpx client pooling ---
    _loop_clients: dict = {}
    _token_locks: dict = {}
    _loop_state_lock = threading.Lock()

    def __init__(self):
        self.platform_id = self.PLATFORM_ID
        self.platform_name = self.PLATFORM_NAME

    # --- Конфиг-аксессоры (бывшие _tconf/_kconf/_yconf) ---
    def _reload_config(self):
        return load_config()

    def _platform_config(self) -> dict[str, Any]:
        """Return platform-specific config section (e.g. config.platforms.twitch)."""
        return get_platform_config(self.PLATFORM_ID, load_config())

    # --- Per-loop httpx client ---
    def _client_headers(self) -> dict[str, str]:
        """Override in subclass to customise User-Agent / Accept headers."""
        return {
            "User-Agent": f"TwitchX/2.0 ({self.PLATFORM_NAME})",
            "Accept": "application/json",
        }

    def _client_timeout(self) -> float:
        """Override in subclass to customise HTTP timeout."""
        return 30.0

    def _get_client(self) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        if loop not in self._loop_clients:
            self._loop_clients[loop] = httpx.AsyncClient(
                timeout=httpx.Timeout(self._client_timeout()),
                headers=self._client_headers(),
            )
        return self._loop_clients[loop]

    # --- Per-loop token lock ---
    def _get_token_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if loop not in self._token_locks:
            self._token_locks[loop] = asyncio.Lock()
        return self._token_locks[loop]

    # --- Cleanup ---
    def close(self):
        pass  # default no-op

    def close_loop_resources(self):
        loop = asyncio.get_running_loop()
        with self._loop_state_lock:
            self._loop_clients.pop(loop, None)
            self._token_locks.pop(loop, None)

    def reset_client(self):
        """No-op: each event loop gets its own httpx.AsyncClient."""
        pass

    # --- Token management (общий для Twitch и Kick) ---
    async def _ensure_token(self) -> str | None:
        """Check and refresh token if needed. Returns token or None."""
        async with self._get_token_lock():
            cfg = self._reload_config()
            platform_cfg = get_platform_config(self.PLATFORM_ID, cfg)
            # Если есть user-токен — используем его
            if platform_cfg.get("access_token") and platform_cfg.get("token_is_valid", True):
                return platform_cfg["access_token"]
            # Пробуем обновить
            return await self.refresh_user_token()

    # --- Общий _get() с retry/refresh паттерном ---
    async def _get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """GET wrapper with rate-limit retry and 401 token refresh."""
        client = self._get_client()
        merged_headers = {**client.headers, **(headers or {})}

        while True:
            logger.debug("GET %s params=%s", url, params)
            resp = await client.get(url, params=params, headers=merged_headers)

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("retry-after", "5"))
                logger.debug("429 rate-limited, waiting %ds", retry_after)
                await asyncio.sleep(retry_after)
                continue

            if resp.status_code == 401:
                logger.debug("401 unauthorized, refreshing token")
                new_token = await self.refresh_user_token()
                if new_token:
                    merged_headers["Authorization"] = f"Bearer {new_token}"
                    continue
                # Token refresh failed — let raise_for_status handle it
                break

            # Subclass hook for platform-specific error handling
            self._check_response_errors(resp)
            resp.raise_for_status()
            return resp

    def _check_response_errors(self, resp: httpx.Response) -> None:
        """Override to handle platform-specific HTTP errors (e.g. YouTube 403 quota)."""
        pass  # default: no extra checks
```

### 2. `TwitchClient` наследует от `BasePlatformClient`

```python
# core/platforms/twitch.py (после рефакторинга)
class TwitchClient(BasePlatformClient):
    PLATFORM_ID = "twitch"
    PLATFORM_NAME = "Twitch"
    AUTH_URL = "https://id.twitch.tv/oauth2/authorize"
    TOKEN_URL = "https://id.twitch.tv/oauth2/token"

    def __init__(self):
        super().__init__()
        self._user_id: str | None = None

    # _get_client(), _get_token_lock(), close_loop_resources(),
    # reset_client(), _reload_config(), _ensure_token(),
    # _get() — БОЛЬШЕ НЕ ОПРЕДЕЛЕНЫ ЗДЕСЬ (наследуются)

    async def get_auth_url(self) -> str:
        ...  # специфичная для Twitch логика

    async def get_live_streams(self, logins: list[str]) -> list[dict[str, Any]]:
        ...  # специфичная для Twitch логика

    # ... остальные специфичные методы
```

### 3. `YouTubeClient` наследует от `BasePlatformClient`

YouTube переопределяет `_get()` → `_yt_get()` (добавляет 403 quota handling). Используем **Template Method**:

```python
# core/platforms/youtube.py (после рефакторинга)
class YouTubeClient(BasePlatformClient):
    PLATFORM_ID = "youtube"
    PLATFORM_NAME = "YouTube"

    def _client_headers(self) -> dict[str, str]:
        # YouTube не шлёт Accept: application/json
        return {"User-Agent": "TwitchX/2.0 (YouTube)"}

    def _check_response_errors(self, resp: httpx.Response) -> None:
        """Handle YouTube-specific 403 quota exceeded."""
        if resp.status_code == 403:
            try:
                body = resp.json()
            except Exception:
                raise ValueError("YouTube API quota exceeded")
            if "quota" in str(body).lower() or "quotaExceeded" in str(body):
                raise ValueError("YouTube API quota exceeded")
```

Больше не нужен отдельный `_yt_get()` — используется родительский `_get()`, который вызывает `_check_response_errors()` перед `raise_for_status()`.

### 4. `KickClient` наследует от `BasePlatformClient`

```python
# core/platforms/kick.py (после рефакторинга)
class KickClient(BasePlatformClient):
    PLATFORM_ID = "kick"
    PLATFORM_NAME = "Kick"

    def _client_timeout(self) -> float:
        return 15.0  # Kick использует 15s timeout

    def _client_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "TwitchX/2.0 (Kick)",
            "Accept": "application/json",
        }
```

### 5. `BaseChatClient` — новый файл `core/chats/base.py` (~80 строк)

```python
# core/chats/base.py
import asyncio
import logging
from typing import Callable

from core.chat import ChatClient, ChatMessage, ChatSendResult, ChatStatus

logger = logging.getLogger(__name__)

# Общая константа
RECONNECT_DELAYS = [3, 6, 12, 24, 48]


class BaseChatClient(ChatClient):
    """Shared infrastructure for chat clients.

    Subclasses must set:
        PLATFORM: str  — "twitch" or "kick"
    """

    PLATFORM: str = ""

    def __init__(self):
        self._ws = None
        self._loop = None
        self._message_callback: Callable[[ChatMessage], None] | None = None
        self._status_callback: Callable[[ChatStatus], None] | None = None
        self._channel: str | None = None
        self._running = False
        self._authenticated = False

    def on_message(self, callback: Callable[[ChatMessage], None]) -> None:
        self._message_callback = callback

    def on_status(self, callback: Callable[[ChatStatus], None]) -> None:
        self._status_callback = callback

    def _emit_status(self, **kwargs):
        """Push status update to registered callback."""
        if self._status_callback and self._channel:
            self._status_callback(ChatStatus(
                platform=self.PLATFORM,
                channel_id=self._channel,
                **kwargs,
            ))

    async def disconnect(self):
        """Disconnect WebSocket and emit offline status."""
        self._running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._emit_status(connected=False)

    async def _reconnect_loop(self, connect_fn: Callable[[], None]):
        """Outer reconnection loop with exponential backoff.

        Args:
            connect_fn: Async callable that establishes a new WebSocket connection
                        and sets self._ws. Should raise on failure.
        """
        attempt = 0
        while self._running:
            try:
                await connect_fn()
                attempt = 0  # reset on successful connection
            except Exception as e:
                attempt += 1
                if attempt >= len(RECONNECT_DELAYS):
                    self._emit_status(connected=False, error=f"Max reconnect attempts: {e}")
                    return
                delay = RECONNECT_DELAYS[min(attempt - 1, len(RECONNECT_DELAYS) - 1)]
                self._emit_status(connected=False, error=f"Reconnecting in {delay}s: {e}")
                await asyncio.sleep(delay)
```

### 6. `TwitchChatClient` и `KickChatClient` наследуют от `BaseChatClient`

```python
# core/chats/twitch_chat.py (после рефакторинга)
class TwitchChatClient(BaseChatClient):
    PLATFORM = "twitch"

    # _emit_status(), disconnect(), on_message(), on_status(),
    # _reconnect_loop() — БОЛЬШЕ НЕ ОПРЕДЕЛЕНЫ ЗДЕСЬ
    # _running, _authenticated, _channel — в базовом классе

    async def connect(self, channel_id: str, token=None, login=None):
        self._channel = channel_id
        self._running = True
        # ... специфичная для Twitch логика
```

---

## Список действий

### Шаг 1: Создать `core/platforms/base.py` (новый файл)

**Создать** `core/platforms/base.py` с классом `BasePlatformClient(PlatformClient)`, содержащим:

- [ ] Константы `PLATFORM_ID`, `PLATFORM_NAME` (пустые — переопределяются в наследниках)
- [ ] Поля `_loop_clients`, `_token_locks`, `_loop_state_lock`
- [ ] Метод `_reload_config()` → `load_config()`
- [ ] Метод `_platform_config()` → `get_platform_config(self.PLATFORM_ID, ...)`
- [ ] Метод `_client_headers()` → возвращает `dict[str, str]` (переопределяемый)
- [ ] Метод `_client_timeout()` → возвращает `float` (переопределяемый)
- [ ] Метод `_get_client()` → per-loop httpx.AsyncClient
- [ ] Метод `_get_token_lock()` → per-loop asyncio.Lock
- [ ] Метод `close_loop_resources()` → чистка per-loop ресурсов
- [ ] Метод `reset_client()` → no-op
- [ ] Метод `_ensure_token()` → проверка + обновление токена
- [ ] Метод `_get(url, params, headers)` → 429-retry, 401-refresh, хук `_check_response_errors()`
- [ ] Метод `_check_response_errors(resp)` → no-op (переопределяется в YouTube)

### Шаг 2: Мигрировать `TwitchClient` на `BasePlatformClient`

- [ ] Добавить `from core.platforms.base import BasePlatformClient`
- [ ] `class TwitchClient(BasePlatformClient):` (вместо `class TwitchClient:`)
- [ ] Добавить `PLATFORM_ID = "twitch"`, `PLATFORM_NAME = "Twitch"`
- [ ] Добавить `super().__init__()` в `__init__`
- [ ] **Удалить** поля `_loop_clients`, `_token_locks`, `_loop_state_lock`
- [ ] **Удалить** методы: `_get_client()`, `_get_token_lock()`, `close_loop_resources()`, `reset_client()`, `_reload_config()`, `_tconf()`, `_ensure_token()`, `_get()`
- [ ] Заменить вызовы `self._tconf()` на `self._platform_config()`
- [ ] Заменить вызовы `self._get(...)` — оставить как есть (теперь наследуется)
- [ ] Прогнать `make check`

### Шаг 3: Мигрировать `KickClient` на `BasePlatformClient`

- [ ] Аналогично шагу 2:
  - [ ] `PLATFORM_ID = "kick"`, `PLATFORM_NAME = "Kick"`
  - [ ] Переопределить `_client_timeout()` → 15.0
  - [ ] Переопределить `_client_headers()` → `"TwitchX/2.0 (Kick)"`
- [ ] Удалить дублированные поля/методы
- [ ] Заменить `self._kconf()` → `self._platform_config()`
- [ ] **Особенность Kick:** `_get()` использует `_legacy_get_json()` и `asyncio.to_thread()` для curl-запросов. Проверить, что `_get()` из базового класса совместим — скорее всего, Kick не переопределяет `_get()`, а просто вызывает его для OAuth API, а для публичного API использует отдельный `requests`/`curl_cffi`. **Оставить как есть**, не трогать публичные API-вызовы.
- [ ] Прогнать `make check`

### Шаг 4: Мигрировать `YouTubeClient` на `BasePlatformClient`

- [ ] `PLATFORM_ID = "youtube"`, `PLATFORM_NAME = "YouTube"`
- [ ] Переопределить `_client_headers()` → без `Accept` заголовка
- [ ] Переопределить `_check_response_errors()` → обработка 403 quota exceeded
- [ ] Удалить дублированные поля/методы
- [ ] **Заменить `_yt_get()`** → использовать родительский `_get()` (который теперь вызывает `_check_response_errors()`)
- [ ] Заменить вызовы `self._yt_get(...)` на `self._get(...)`
- [ ] Заменить `self._yconf()` → `self._platform_config()`
- [ ] **ВНИМАНИЕ:** сигнатуры могут отличаться. Сейчас `_yt_get(url)` возвращает `httpx.Response`, а `_get()` из base тоже будет возвращать `httpx.Response`. Проверить все места вызова.
- [ ] Прогнать `make check`

### Шаг 5: Обновить `core/platform.py` (почистить ABC)

- [ ] Убрать методы, которые гарантированно не будут использоваться: `follow()`, `unfollow()` — или оставить с пометкой `# Not yet implemented`
- [ ] Исправить сигнатуру `get_live_streams(channel_ids: list[str])` → `get_live_streams(identifiers: list[str])` (обобщить, т.к. Twitch использует logins, Kick — slugs)
- [ ] Исправить сигнатуру `get_channel_info(channel_id: str)` → `get_channel_info(identifier: str)`
- [ ] Исправить сигнатуру `refresh_token() -> TokenData` → `refresh_token() -> str | None` (или `refresh_user_token()`)
- [ ] Добавить `get_channel_vods()` и `get_channel_clips()` как опциональные методы (если нужны в ABC)

### Шаг 6: Создать `core/chats/base.py` (новый файл)

- [ ] Создать `core/chats/base.py` с классом `BaseChatClient(ChatClient)`
- [ ] Вынести `RECONNECT_DELAYS` как константу модуля
- [ ] Вынести поля: `_ws`, `_loop`, `_message_callback`, `_status_callback`, `_channel`, `_running`, `_authenticated`
- [ ] Вынести методы: `on_message()`, `on_status()`, `_emit_status()`, `disconnect()`, `_reconnect_loop(connect_fn)`

### Шаг 7: Мигрировать `TwitchChatClient` на `BaseChatClient`

- [ ] `class TwitchChatClient(BaseChatClient):`
- [ ] `PLATFORM = "twitch"`
- [ ] Удалить дублированные поля и методы
- [ ] Переписать `connect()` — использовав `self._reconnect_loop(self._connect_ws)` где `_connect_ws` — приватный метод, устанавливающий WebSocket соединение
- [ ] Прогнать `make check`

### Шаг 8: Мигрировать `KickChatClient` на `BaseChatClient`

- [ ] `class KickChatClient(BaseChatClient):`
- [ ] `PLATFORM = "kick"`
- [ ] Аналогично TwitchChatClient
- [ ] Сохранить специфичную для Kick логику: `_seen_msg_ids` (LRU-дедупликация), `_chatroom_id`, `_broadcaster_user_id`
- [ ] Прогнать `make check`

---

## Затрагиваемые файлы

### Создаются
| Файл | Описание |
|------|----------|
| `core/platforms/base.py` | `BasePlatformClient` — общая инфраструктура (~150 строк) |
| `core/chats/base.py` | `BaseChatClient` — общая инфраструктура (~80 строк) |

### Изменяются
| Файл | Изменения |
|------|-----------|
| `core/platforms/twitch.py` | Наследование от `BasePlatformClient`, удаление ~70 строк дубликатов |
| `core/platforms/kick.py` | Наследование от `BasePlatformClient`, удаление ~70 строк дубликатов |
| `core/platforms/youtube.py` | Наследование от `BasePlatformClient`, замена `_yt_get` → `_get`, удаление ~70 строк |
| `core/platform.py` | Исправление сигнатур ABC, удаление `follow`/`unfollow` (опционально) |
| `core/chats/twitch_chat.py` | Наследование от `BaseChatClient`, удаление ~40 строк дубликатов |
| `core/chats/kick_chat.py` | Наследование от `BaseChatClient`, удаление ~40 строк дубликатов |
| `core/chat.py` | Лёгкая чистка ABC (опционально) |

### НЕ затрагиваются
| Файл | Почему |
|------|--------|
| `ui/api.py` | Он использует клиенты через duck-typing — публичные сигнатуры не меняются |
| `ui/index.html` | Нет изменений в JS |
| `app.py` | Нет изменений |
| `tests/` | Тесты используют monkeypatch на импортируемые имена — если импорты не меняются, тесты проходят |

---

## Риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| **Kick `_get()` несовместим** — Kick использует `_legacy_get_json()` и `asyncio.to_thread()` для публичного API | Средняя | Среднее | Kick НЕ переопределяет `_get()` для публичных запросов — он использует прямые `curl_cffi` вызовы. Базовый `_get()` нужен только для OAuth (токен-эндпоинты). Проверить grep'ом. |
| **YouTube `_yt_get()` возвращает Response, а не dict** — вызывающий код делает `.json()` вручную | Низкая | Низкое | Базовый `_get()` тоже возвращает Response. Вызывающий код не меняется. |
| **`_get_client()` принимает параметр `token` в некоторых реализациях** | Низкая | Среднее | Проверить grep'ом все вызовы `_get_client()` — если где-то передаётся token, вынести в параметр метода. |
| **Тесты сломаются из-за изменения импортов** | Средняя | Среднее | Перед каждым шагом прогонять `make test`. Если тесты используют `monkeypatch.setattr` на внутренние атрибуты (`_loop_clients`), теперь они на базовом классе — обновить таргеты. |
| **`refresh_user_token()` имеет разные возвращаемые типы** — Twitch возвращает `str`, Kick — `str`, YouTube — `str` | Низкая | Низкое | Все три возвращают `str | None`, унифицировано. |

---

## План тестирования

После **каждого шага** (не только в конце фазы):

```bash
make check          # lint + test
```

Дополнительно:
```bash
# Проверить, что все клиенты по-прежнему импортируются
uv run python -c "
from core.platforms.twitch import TwitchClient
from core.platforms.kick import KickClient
from core.platforms.youtube import YouTubeClient
from core.chats.twitch_chat import TwitchChatClient
from core.chats.kick_chat import KickChatClient
print('All imports OK')
"

# Проверить, что платформенные клиенты реально наследуют ABC
uv run python -c "
from core.platforms.twitch import TwitchClient
from core.platforms.base import BasePlatformClient
assert issubclass(TwitchClient, BasePlatformClient), 'TwitchClient must inherit BasePlatformClient'
print('Inheritance OK')
"

# Проверить, что ABC всё ещё абстрактный (нельзя инстанцировать напрямую)
uv run python -c "
from core.platforms.base import BasePlatformClient
try:
    BasePlatformClient()  # должен упасть, т.к. абстрактные методы не реализованы
    print('ERROR: BasePlatformClient should be abstract!')
except TypeError:
    print('Abstract check OK')
"
```

**Ручное тестирование (после всей фазы):**
1. Запустить приложение: `make run`
2. Убедиться, что загружаются стримы со всех трёх платформ
3. Проверить логин/логаут на каждой платформе
4. Проверить чат (Twitch и Kick)
5. Проверить браузинг и поиск

---

## План отката

Каждый шаг — отдельный коммит. Откат простой:

```bash
# Откатить последний шаг
git reset --hard HEAD~1

# Или откатить всю фазу
git log --oneline | head -10   # найти хэш до начала фазы
git reset --hard <hash>

# Или (если ещё не запушили)
git stash
```

**Частичный откат:** Если миграция одного клиента сломалась, а два других работают:
- Откатить только проблемный клиент (`git checkout HEAD~1 -- core/platforms/kick.py`)
- Остальные оставить как есть
- Починить и перекоммитить

---

## Definition of Done

- [ ] `core/platforms/base.py` создан, содержит `BasePlatformClient`
- [ ] `core/chats/base.py` создан, содержит `BaseChatClient`
- [ ] `TwitchClient`, `KickClient`, `YouTubeClient` наследуют от `BasePlatformClient`
- [ ] `TwitchChatClient`, `KickChatClient` наследуют от `BaseChatClient`
- [ ] Дублированные поля и методы удалены из дочерних классов
- [ ] `issubclass(TwitchClient, PlatformClient)` → `True`
- [ ] `issubclass(TwitchChatClient, ChatClient)` → `True`
- [ ] `make check` проходит (линтер + все тесты)
- [ ] `make run` запускает приложение без ошибок
- [ ] Все изменения закоммичены отдельными коммитами
