# Фаза 2: Декомпозиция ui/api.py (God Class → модули)

> **Дата:** 2026-04-28  
> **Статус:** План  
> **Зависит от:** Фаза 1 (ABC restore)  
> **Обзорный документ:** [architecture-refactoring.md](./2026-04-28-architecture-refactoring.md)

---

## Цель

Разбить `ui/api.py` (2,926 строк) — God-класс `TwitchXApi` с 36 публичными методами, 22 приватными методами и 30+ вложенными замыканиями — на 5 модулей по зонам ответственности. Каждый модуль ≤ 400 строк.

---

## Текущее состояние

### Масштаб проблемы

`ui/api.py` — 2,926 строк, что составляет **42% всей Python-кодовой базы** (6,940 строк production-кода).

Распределение ответственности внутри класса `TwitchXApi`:

| Зона ответственности | Методы | Примерная длина (строк) |
|---------------------|--------|------------------------|
| Конфигурация (get/save config) | `get_config`, `get_full_config_for_settings`, `save_settings` | ~130 |
| OAuth аутентификация (3 платформы) | `login`, `logout`, `kick_login`, `kick_logout`, `youtube_login`, `youtube_logout`, `test_connection`, `kick_test_connection`, `youtube_test_connection` | ~400 |
| Избранное и поиск | `add_channel`, `remove_channel`, `reorder_channels`, `import_follows`, `youtube_import_follows`, `search_channels` | ~330 |
| Данные / опрос | `refresh`, `start_polling`, `stop_polling`, `_fetch_data`, `_async_fetch`, `_on_data_fetched` | ~430 |
| Стриминг / плеер | `watch`, `watch_direct`, `watch_external`, `watch_media`, `stop_player`, `add_multi_slot`, `stop_multi` | ~520 |
| Браузинг | `get_browse_categories`, `get_browse_top_streams`, `_fetch_browse_categories`, `_fetch_browse_top_streams` | ~180 |
| Канал / медиа | `get_channel_profile`, `get_channel_media`, `open_browser`, `open_url` | ~140 |
| Изображения | `get_avatar`, `get_thumbnail` | ~80 |
| Чат | `start_chat`, `stop_chat`, `send_chat`, `save_chat_width`, `save_chat_visibility`, `_on_chat_message`, `_on_chat_status` | ~260 |
| Инфраструктура | `__init__`, `set_window`, `_eval_js`, `_run_in_thread`, `close`, `_get_platform`, config accessors, таймеры, уведомления | ~250 |

### Проблема 1: Ad-hoc замыкания вместо методов (~30 штук)

Каждый логин/логаут, каждый watch, каждый импорт определяет вложенную функцию, передаваемую в `_run_in_thread()`:

```python
# ui/api.py — текущий паттерн (пример: login, строки ~547-623)
def login(self):
    def do_login():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # ... 50 строк логики ...
            def _save_tokens(tokens):  # ← вложенное замыкание внутри замыкания
                def _apply(cfg):       # ← третий уровень вложенности
                    ...
                self._config = update_config(_apply)
        except Exception as e:
            self._eval_js(f"window.onLoginError('{str(e)[:80]}')")
        finally:
            loop.close()
    self._run_in_thread(do_login)
```

Этот паттерн повторяется для **каждого** асинхронного действия:
- `login`, `logout`, `kick_login`, `kick_logout`, `youtube_login`, `youtube_logout` — 6 раз
- `test_connection`, `kick_test_connection`, `youtube_test_connection` — 3 раза
- `import_follows`, `youtube_import_follows` — 2 раза
- `watch`, `watch_direct`, `watch_external`, `watch_media` — 4 раза
- `add_channel` — 1 раз (с 3-уровневой вложенностью)
- `get_browse_categories`, `get_browse_top_streams` — 2 раза
- `search_channels`, `refresh` — 2 раза
- `get_channel_profile`, `get_channel_media` — 2 раза
- `start_chat` — 1 раз
- `get_avatar`, `get_thumbnail` — 2 раза (через `_image_pool.submit`)

**Итого: ~25+ замыканий**, каждое из которых:
- Создаёт свой `asyncio.new_event_loop()`
- Обрабатывает ошибки через try/except
- Передаёт результат в JS через `self._eval_js()`
- Не может быть протестировано в изоляции

### Проблема 2: 5 механизмов конкурентности в одном классе

```python
# ui/api.py
class TwitchXApi:
    def __init__(self):
        self._image_pool = ThreadPoolExecutor(max_workers=8)       # (1) пул для картинок
        self._send_pool = ThreadPoolExecutor(max_workers=2)        # (2) пул для чата

    def _run_in_thread(self, fn):
        threading.Thread(target=fn, daemon=True).start()           # (3) сырые потоки

    def start_polling(self, interval_seconds):
        self._poll_timer = threading.Timer(...)                     # (4) Timer для polling

    def _start_launch_timer(self):
        self._launch_timer = threading.Timer(...)                   # (5) Timer для UI
```

Нет единой стратегии — где-то пул, где-то сырой Thread, где-то Timer. При быстром UI-взаимодействии можно создать десятки сырых потоков.

### Проблема 3: `__init__` слишком большой (61 строка)

```python
# ui/api.py:86-147 — __init__
def __init__(self):
    self._shutdown = threading.Event()
    self._fetch_lock = threading.Lock()        # для предотвращения гонок refresh
    self._poll_lock = threading.Lock()         # для предотвращения гонок polling
    self._poll_generation = 0                  # generation counter для таймеров
    self._poll_timer = None
    self._launch_timer = None
    self._config = load_config()
    self._window = None
    self._user_avatars: dict[str, str] = {}
    self._fetching_avatars: set[str] = set()
    self._last_kick_streams: list[dict] = []
    self._last_youtube_streams: list[dict] = []
    self._kick_user_id: str | None = None
    self._youtube_user_id: str | None = None
    self._youtube_channel_id: str | None = None
    self._chat_client = None
    self._chat_channel: str | None = None
    self._chat_platform: str | None = None
    self._chat_authenticated = False
    self._image_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="img")
    self._send_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="chat-send")
    self._live_streams: dict[str, dict] = {}
    self._twitch = self._make_twitch_client()
    self._kick = self._make_kick_client()
    self._youtube = self._make_youtube_client()
```

30+ атрибутов, перемешанных зон ответственности (чат, плеер, изображения, платформы, таймеры).

### Проблема 4: Длинные методы со смешанными уровнями абстракции

`watch()` (150 строк) смешивает:
- Валидацию входных данных
- Проверку live-статуса через `_live_streams` кэш
- Сохранение выбранного качества
- Специальную обработку YouTube
- Управление launch-таймером
- Разрешение HLS URL через streamlink
- Запуск чата
- Отправку результатов в JS

Всё в одном методе, с вложенными замыканиями.

---

## Целевое состояние

### Новая структура: `ui/api/` (пакет)

```
ui/
├── __init__.py
├── api/
│   ├── __init__.py          (~30 строк)  — TwitchXApi (оркестратор, экспортирует старые имена)
│   ├── _base.py              (~60 строк)  — BaseApiComponent (общая инфраструктура)
│   ├── auth.py              (~300 строк)  — AuthComponent (логин, логаут, test_connection)
│   ├── favorites.py         (~220 строк)  — FavoritesComponent (add, remove, reorder, import, search)
│   ├── data.py              (~450 строк)  — DataComponent (refresh, poll, browse, channel_profile)
│   ├── streams.py           (~520 строк)  — StreamsComponent (watch, watch_direct, multistream, stop)
│   ├── chat.py              (~280 строк)  — ChatComponent (start, stop, send, callbacks)
│   └── images.py            (~100 строк)  — ImagesComponent (avatars, thumbnails)
├── index.html               (не меняется в этой фазе)
├── native_player.py
└── theme.py
```

### Проекция методов в новые модули

| Старый метод (в `TwitchXApi`) | Новый модуль |
|------------------------------|-------------|
| `get_config`, `get_full_config_for_settings`, `save_settings` | Остаются в `TwitchXApi` (короткие, ~130 строк) |
| `login`, `logout`, `kick_login`, `kick_logout`, `youtube_login`, `youtube_logout` | `api/auth.py` |
| `test_connection`, `kick_test_connection`, `youtube_test_connection` | `api/auth.py` |
| `add_channel`, `remove_channel`, `reorder_channels` | `api/favorites.py` |
| `import_follows`, `youtube_import_follows` | `api/favorites.py` |
| `search_channels` | `api/favorites.py` |
| `refresh`, `start_polling`, `stop_polling` | `api/data.py` |
| `get_browse_categories`, `get_browse_top_streams` | `api/data.py` |
| `get_channel_profile`, `get_channel_media` | `api/data.py` |
| `watch`, `watch_direct`, `watch_external`, `watch_media` | `api/streams.py` |
| `stop_player`, `add_multi_slot`, `stop_multi` | `api/streams.py` |
| `start_chat`, `stop_chat`, `send_chat` | `api/chat.py` |
| `save_chat_width`, `save_chat_visibility` | `api/chat.py` |
| `get_avatar`, `get_thumbnail` | `api/images.py` |
| `open_browser`, `open_url` | Остаются в `TwitchXApi` (короткие, делегируют в webbrowser) |
| `close`, `set_window` | Остаются в `TwitchXApi` (управление жизненным циклом) |

### Базовый класс: `BaseApiComponent`

```python
# ui/api/_base.py
import asyncio
import threading
from typing import Any, Callable

class BaseApiComponent:
    """Shared infrastructure for all API sub-components.

    Provides:
        - _eval_js(code) — safe JS evaluation, guarded by _shutdown
        - _run_in_thread(fn) — dispatch to daemon thread
        - _async_run(coro) — run async coroutine in a new event loop (common pattern)
        - Access to shared state: _config, _live_streams, platform clients
    """

    def __init__(self, parent: "TwitchXApi"):
        self._api = parent  # ссылка на оркестратор

    # Делегирование в оркестратор
    @property
    def _shutdown(self) -> threading.Event:
        return self._api._shutdown

    @property
    def _config(self) -> dict:
        return self._api._config

    @_config.setter
    def _config(self, value: dict):
        self._api._config = value

    @property
    def _live_streams(self) -> dict:
        return self._api._live_streams

    @property
    def _twitch(self):
        return self._api._twitch

    @property
    def _kick(self):
        return self._api._kick

    @property
    def _youtube(self):
        return self._api._youtube

    def _eval_js(self, code: str) -> None:
        """Safe JS evaluation — delegates to parent's _eval_js."""
        self._api._eval_js(code)

    def _run_in_thread(self, fn: Callable[[], None]) -> None:
        """Dispatch to daemon thread — delegates to parent's _run_in_thread."""
        self._api._run_in_thread(fn)

    def _async_run(self, coro) -> None:
        """Run async coroutine in a new event loop, in a daemon thread.
        
        This is the most common pattern in the codebase: every JS API call
        spawns a background thread with its own asyncio event loop.
        """
        def _runner():
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(coro)
            except Exception as e:
                # Обработка ошибок — в наследнике
                self._handle_async_error(e)
            finally:
                loop.close()
        self._run_in_thread(_runner)

    def _handle_async_error(self, error: Exception) -> None:
        """Override in subclass for domain-specific error handling."""
        pass
```

### Пример: `AuthComponent`

```python
# ui/api/auth.py
import asyncio
import webbrowser

import httpx

from core.oauth_server import wait_for_oauth_code
from core.storage import update_config

from ._base import BaseApiComponent


class AuthComponent(BaseApiComponent):
    """OAuth authentication for all platforms."""

    # ── Twitch ──────────────────────────────────────────

    def login(self):
        """Start Twitch OAuth flow."""
        twitch = self._twitch
        auth_url = twitch.get_auth_url()
        webbrowser.open(auth_url)

        def _run():
            try:
                code = wait_for_oauth_code()
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(twitch.exchange_code(code))
                    self._config = update_config(self._apply_twitch_tokens(result))
                    self._eval_js(f"window.onLoginComplete({json.dumps(user)})")
                finally:
                    loop.close()
            except Exception as e:
                self._eval_js(f"window.onLoginError('{str(e)[:80]}')")

        self._run_in_thread(_run)

    def _apply_twitch_tokens(self, result: dict):
        """Return config update closure for Twitch tokens."""
        def _apply(cfg):
            platform = cfg.setdefault("platforms", {}).setdefault("twitch", {})
            platform.update({
                "access_token": result["access_token"],
                "refresh_token": result.get("refresh_token"),
                "token_type": "user",
                "token_is_valid": True,
            })
            return cfg
        return _apply

    def logout(self):
        """Twitch logout."""
        def _apply(cfg):
            p = cfg.setdefault("platforms", {}).setdefault("twitch", {})
            for key in ("access_token", "refresh_token", "user_login", "user_id"):
                p.pop(key, None)
            p["token_is_valid"] = False
            p["token_type"] = "app"
            return cfg
        self._config = update_config(_apply)
        self._eval_js("window.onLogout()")

    # ── Kick ────────────────────────────────────────────
    # ... аналогично login/logout/test_connection для Kick

    # ── YouTube ─────────────────────────────────────────
    # ... аналогично login/logout/test_connection для YouTube

    # ── Connection tests ────────────────────────────────

    def test_connection(self, cid: str, csec: str):
        """Test Twitch API credentials."""
        async def _test():
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://id.twitch.tv/oauth2/token",
                    params={"client_id": cid, "client_secret": csec, "grant_type": "client_credentials"},
                )
                return resp.status_code == 200

        def _run():
            try:
                loop = asyncio.new_event_loop()
                ok = loop.run_until_complete(_test())
                loop.close()
                self._eval_js(f"window.onTestResult({{ok: {json.dumps(ok)}}})")
            except Exception as e:
                self._eval_js(f"window.onTestResult({{ok: false, error: '{str(e)[:60]}'}})")

        self._run_in_thread(_run)
```

### TwitchXApi — становится оркестратором

```python
# ui/api/__init__.py (~200 строк вместо 2926)
import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from core.storage import load_config
from ._base import BaseApiComponent
from .auth import AuthComponent
from .favorites import FavoritesComponent
from .data import DataComponent
from .streams import StreamsComponent
from .chat import ChatComponent
from .images import ImagesComponent

logger = logging.getLogger(__name__)


class TwitchXApi:
    """Python↔JS bridge. Orchestrates sub-components, owns shared state.

    Each sub-component handles one domain:
        AuthComponent       — OAuth login/logout for all platforms
        FavoritesComponent  — channel management, search, import
        DataComponent       — polling, refresh, browse, channel profiles
        StreamsComponent    — video playback (native, external, multistream)
        ChatComponent       — chat connection and message sending
        ImagesComponent     — avatar and thumbnail fetching
    """

    def __init__(self):
        # ─── Shared state owned by the orchestrator ───
        self._shutdown = threading.Event()
        self._config = load_config()
        self._window = None
        self._live_streams: dict[str, dict] = {}

        # ─── Threading infrastructure ───
        self._image_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="img")
        self._send_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="send")
        self._fetch_lock = threading.Lock()

        # ─── Platform clients ───
        self._twitch = self._make_twitch_client()
        self._kick = self._make_kick_client()
        self._youtube = self._make_youtube_client()

        # ─── Sub-components ───
        self._auth = AuthComponent(self)
        self._favorites = FavoritesComponent(self)
        self._data = DataComponent(self)
        self._streams = StreamsComponent(self)
        self._chat = ChatComponent(self)
        self._images = ImagesComponent(self)

    # ─── Delegate to sub-components ───

    def login(self):
        self._auth.login()

    def logout(self):
        self._auth.logout()

    # ... все публичные методы делегируют в соответствующий компонент ...

    # ─── Shared infrastructure methods (используются компонентами) ───

    def _eval_js(self, code: str):
        if self._shutdown.is_set():
            return
        try:
            if self._window:
                self._window.evaluate_js(code)
        except Exception:
            logger.debug("_eval_js suppressed", exc_info=True)

    def _run_in_thread(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    # ─── Lifecycle ───

    def set_window(self, window):
        self._window = window

    def close(self):
        self._shutdown.set()
        self._streams.stop_player()
        self._data.stop_polling()
        self._chat.stop_chat()
        self._image_pool.shutdown(wait=False)
        self._send_pool.shutdown(wait=False)
        for client in (self._twitch, self._kick, self._youtube):
            try:
                client.close()
            except Exception:
                pass
```

### Сохранение обратной совместимости

Чтобы не менять `app.py` и внешних потребителей:

```python
# ui/api.py (старый файл — становится реэкспортом)
"""DEPRECATED: use ui.api instead. Kept for backward compatibility."""
from ui.api import TwitchXApi  # noqa: F401
```

**Или** (предпочтительно) — оставить `ui/api.py` empty-init реэкспортом, а сам код перенести в пакет `ui/api/`. Тогда `app.py` не меняется:

```python
# app.py — без изменений
from ui.api import TwitchXApi  # импорт работает как раньше
```

---

## Список действий

### Шаг 0: Подготовка (рефакторинг на месте, в одном файле)

**Перед разбиением на файлы** — сначала привести код в порядок внутри `api.py`:

- [ ] **Заменить замыкания на приватные методы.** Для каждого публичного метода, использующего `def do_*():`, создать приватный метод `_do_*()`:

  ```python
  # БЫЛО (замыкание внутри login)
  def login(self):
      def do_login():
          ...

  # СТАЛО (приватный метод)
  def login(self):
      self._run_in_thread(self._do_login)

  def _do_login(self):
      ...
  ```

  Применить ко **всем** 25+ замыканиям. Это даёт:
  - Возможность тестировать логику в изоляции
  - Чистую границу для последующего разбиения на файлы
  - Устранение nonlocal-мутаций (вместо них — `self._*` атрибуты)

- [ ] **Выделить константы.** Магические числа — в классовые константы:
  - `_MAX_LAUNCH_SECONDS = 20` (уже есть)
  - `_AVATAR_SIZE = (56, 56)`
  - `_THUMBNAIL_SIZE = (440, 248)`
  - `_JPEG_QUALITY = 85`
  - `_CHAT_WIDTH_MIN = 250`
  - `_CHAT_WIDTH_MAX = 500`
  - `_YOUTUBE_DEFAULT_REFRESH = 300`
  - `_RETRY_DELAYS = [5, 15, 30]`
  - `_BROWSE_CACHE_TTL = 600`

- [ ] **Прогнать `make check` после каждых 3-4 замен.** Не делать всё сразу — по одному методу за коммит.

### Шаг 1: Создать пакет `ui/api/`

- [ ] Создать директорию `ui/api/`
- [ ] Создать `ui/api/__init__.py` — пока пустой (реэкспорт потом)
- [ ] Создать `ui/api/_base.py` с классом `BaseApiComponent`

### Шаг 2: Выделить `AuthComponent` (`ui/api/auth.py`)

- [ ] Перенести методы: `login`, `logout`, `kick_login`, `kick_logout`, `youtube_login`, `youtube_logout`
- [ ] Перенести методы: `test_connection`, `kick_test_connection`, `youtube_test_connection`
- [ ] Перенести приватные хелперы: нормализаторы, парсеры скоупов
- [ ] Заменить вызовы в `TwitchXApi` на делегирование в `self._auth.*`
- [ ] Прогнать `make check`

### Шаг 3: Выделить `FavoritesComponent` (`ui/api/favorites.py`)

- [ ] Перенести: `add_channel`, `remove_channel`, `reorder_channels`
- [ ] Перенести: `import_follows`, `youtube_import_follows`
- [ ] Перенести: `search_channels` + нормализаторы поиска
- [ ] Заменить вызовы в `TwitchXApi` на делегирование
- [ ] Прогнать `make check`

### Шаг 4: Выделить `DataComponent` (`ui/api/data.py`)

- [ ] Перенести: `refresh`, `start_polling`, `stop_polling`
- [ ] Перенести: `get_browse_categories`, `get_browse_top_streams`
- [ ] Перенести: `get_channel_profile`, `get_channel_media`
- [ ] Перенести всё связанное: `_fetch_data`, `_async_fetch`, `_on_data_fetched`, `_fetch_browse_*`, `_find_live_stream`, `_aggregate_categories`
- [ ] Перенести инфраструктуру polling: `_poll_timer`, `_poll_generation`, `_poll_lock`
- [ ] Заменить вызовы в `TwitchXApi` на делегирование
- [ ] Прогнать `make check`

### Шаг 5: Выделить `StreamsComponent` (`ui/api/streams.py`)

- [ ] Перенести: `watch`, `watch_direct`, `watch_external`, `watch_media`
- [ ] Перенести: `stop_player`, `add_multi_slot`, `stop_multi`
- [ ] Перенести: `_start_launch_timer`, `_cancel_launch_timer`, `_send_notification`
- [ ] Заменить вызовы в `TwitchXApi` на делегирование
- [ ] Прогнать `make check`

### Шаг 6: Выделить `ChatComponent` (`ui/api/chat.py`)

- [ ] Перенести: `start_chat`, `stop_chat`, `send_chat`
- [ ] Перенести: `save_chat_width`, `save_chat_visibility`
- [ ] Перенести: `_on_chat_message`, `_on_chat_status`
- [ ] Перенести связанное: `_chat_client`, `_chat_channel`, `_chat_platform`, `_chat_authenticated`
- [ ] Заменить вызовы в `TwitchXApi` на делегирование
- [ ] Прогнать `make check`

### Шаг 7: Выделить `ImagesComponent` (`ui/api/images.py`)

- [ ] Перенести: `get_avatar`, `get_thumbnail`
- [ ] Перенести связанное: `_user_avatars`, `_fetching_avatars`, `_image_pool`
- [ ] Заменить вызовы в `TwitchXApi` на делегирование
- [ ] Прогнать `make check`

### Шаг 8: Финализация

- [ ] `TwitchXApi.__init__` теперь ~30 строк (создание компонентов + общее состояние)
- [ ] `ui/api.py` — реэкспорт: `from ui.api import TwitchXApi`
- [ ] Убедиться, что `app.py` не требует изменений
- [ ] Прогнать `make check`
- [ ] Прогнать `make run` — ручное тестирование

---

## Затрагиваемые файлы

### Создаются
| Файл | Описание | ~Строк |
|------|----------|--------|
| `ui/api/__init__.py` | `TwitchXApi` оркестратор | 200 |
| `ui/api/_base.py` | `BaseApiComponent` | 60 |
| `ui/api/auth.py` | `AuthComponent` | 300 |
| `ui/api/favorites.py` | `FavoritesComponent` | 220 |
| `ui/api/data.py` | `DataComponent` | 450 |
| `ui/api/streams.py` | `StreamsComponent` | 520 |
| `ui/api/chat.py` | `ChatComponent` | 280 |
| `ui/api/images.py` | `ImagesComponent` | 100 |

### Изменяются
| Файл | Изменения |
|------|-----------|
| `ui/api.py` | Становится реэкспортом (2 строки) |
| `tests/test_api.py` | Импорты могут измениться (если тесты импортируют внутренние атрибуты) |

### НЕ затрагиваются
| Файл | Почему |
|------|--------|
| `app.py` | Импортирует `from ui.api import TwitchXApi` — не меняется |
| `ui/index.html` | JS вызывает `pywebview.api.*` — имена методов не меняются |
| `core/` | Никакие core-модули не трогаем |

---

## Риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| **Сломанные тесты** — тесты monkeypatch'ат внутренние атрибуты `TwitchXApi` | Высокая | Среднее | Шаг 0 (замена замыканий на методы) может сломать тесты, которые monkeypatch'ат `_run_in_thread` или `_eval_js`. Обновлять тесты по мере переноса. |
| **Циркулярные импорты** — `BaseApiComponent` ссылается на `TwitchXApi`, и наоборот | Средняя | Высокое | Использовать `TYPE_CHECKING` для аннотаций: `from __future__ import annotations` + `if TYPE_CHECKING: from . import TwitchXApi`. |
| **Гонки между компонентами** — `self._config` теперь мутируется из разных файлов | Средняя | Среднее | `_config` обновляется через `update_config()` с локом — это уже потокобезопасно. Главное — не создавать новых прямых присваиваний. |
| **Слишком много связей** — компоненты зависят друг от друга (напр. `StreamsComponent` вызывает `ChatComponent.start_chat()`) | Средняя | Среднее | Явно передавать зависимости в `__init__` компонента, а не дёргать через `self._api._chat`. Если зависимостей больше 2-3 — пересмотреть границы компонентов. |
| **Размер `data.py` и `streams.py` всё ещё > 400 строк** | Средняя | Низкое | Это приемлемо для первой итерации. Дальнейшее разбиение — в отдельных фазах при необходимости. |

---

## План тестирования

После **каждого шага**:

```bash
make check     # lint + test
```

После каждого крупного шага (выделение компонента):

```bash
# Проверить, что импорты работают
uv run python -c "from ui.api import TwitchXApi; print('Import OK')"

# Проверить, что старые импорты не сломаны
uv run python -c "from ui.api import TwitchXApi; api = TwitchXApi(); print('Init OK')"
```

**Ручное тестирование (после всей фазы):**
1. `make run` — запуск без ошибок
2. Проверить загрузку стримов
3. Проверить логин на каждой платформе
4. Проверить добавление/удаление из избранного
5. Проверить запуск стрима (watch)
6. Проверить браузинг
7. Проверить чат
8. Проверить мультистрим
9. Проверить настройки

---

## План отката

```bash
# Полный откат фазы (если ui/api.py ещё не переписан как реэкспорт)
git checkout -- ui/api.py
rm -rf ui/api/

# Если ui/api.py уже заменён — откатить последние N коммитов
git log --oneline | head -20
git reset --hard <hash до начала фазы>
```

---

## Definition of Done

- [ ] `ui/api/` пакет создан, содержит 7 модулей (включая `__init__.py` и `_base.py`)
- [ ] Ни один модуль не превышает 520 строк (streams.py — самый большой)
- [ ] `TwitchXApi` в `ui/api/__init__.py` — оркестратор, ~200 строк
- [ ] `ui/api.py` — реэкспорт, не ломает `app.py`
- [ ] Все тесты проходят (`make test`)
- [ ] Линтер проходит (`make lint`)
- [ ] `make run` запускает приложение без ошибок
- [ ] Замыкания заменены на приватные методы (тестируемость)
- [ ] Нет циркулярных импортов
- [ ] Все изменения закоммичены
