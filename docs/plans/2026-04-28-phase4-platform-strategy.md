# Фаза 4: Стратегия вместо platform-branching

> **Дата:** 2026-04-28  
> **Статус:** План  
> **Зависит от:** Фаза 1 (ABC restore) — рекомендуется, но не блокирует  
> **Параллельно с:** Фаза 2 (api.py decomposition)  
> **Обзорный документ:** [architecture-refactoring.md](./2026-04-28-architecture-refactoring.md)

---

## Цель

Устранить platform-branching (`if platform == "youtube" elif platform == "kick" ...`), разбросанный по не-платформенным файлам. Консолидировать платформенную логику в соответствующих `PlatformClient` через полиморфные методы. Заодно перенести всю миграцию конфига в `storage.py` и удалить мёртвый код (tkinter `Tooltip`).

---

## Текущее состояние

### Проблема 1: Platform-branching в `app.py` — `_sanitize_favorite_login()`

```python
# app.py:130-158 (примерно)
@staticmethod
def _sanitize_favorite_login(raw: str, platform: str) -> str:
    if platform == "youtube":
        return YouTubeClient.normalize_channel_id(raw)
    elif platform == "kick":
        return KickClient.normalize_slug(raw)
    else:
        return TwitchClient.normalize_login(raw)
```

Каждый новый клиент требует изменения в app.py. Логика нормализации принадлежит платформенному клиенту, а не app.py.

### Проблема 2: Platform-branching в `stream_resolver.py` — построение URL

```python
# core/stream_resolver.py:31-50 (примерно)
def resolve_hls_url(channel: str, platform: str, quality: str = "best") -> str:
    if platform == "twitch":
        url = f"https://twitch.tv/{channel}"
    elif platform == "youtube":
        url = f"https://youtube.com/watch?v={channel}"
    elif platform == "kick":
        url = f"https://kick.com/{channel}"
    elif channel.startswith("http"):
        url = channel  # уже URL
    else:
        raise ValueError(f"Unknown platform: {platform}")
    # ... streamlink ...
```

То же самое: каждый новый клиент требует изменения в `stream_resolver.py`.

### Проблема 3: Platform-branching в `api.py` — нормализация

```python
# ui/api.py (текущий) — разбросано по нескольким методам
@staticmethod
def _sanitize_channel_name(raw: str, platform: str) -> str:
    if platform == "twitch":
        return _extract_twitch_login(raw)
    elif platform == "kick":
        return _extract_kick_slug(raw)
    elif platform == "youtube":
        return _extract_youtube_id(raw)
    return raw
```

И ещё `_normalize_twitch_search_result()`, `_normalize_kick_search_result()`, `_normalize_youtube_search_result()` — три отдельных статических метода, хотя это одна и та же операция «нормализовать результат поиска».

### Проблема 4: Миграция конфига разделена

- `core/storage.py` — мигрирует v1→v2 конфиг (старая)
- `app.py:__init__` → `_migrate_favorites()` — чистит избранное (YouTube дедупликация, нормализация, конвертация строк в dict)

Два файла меняют одну структуру, возможны гонки. `_migrate_favorites` (105 строк) — это логика, которая по своей природе принадлежит `storage.py` (она знает о схеме конфига).

### Проблема 5: Мёртвый код — `tkinter` в `core/utils.py`

```python
# core/utils.py
import tkinter as tk  # ← подтягивает весь GUI-тулкит

class Tooltip:
    """Hover tooltip for tkinter widgets."""
    ...
```

Если `Tooltip` не используется нигде в приложении (а приложение — pywebview, не tkinter), удалить и класс, и зависимость.

### Проблема 6: Дублирование магических констант

```python
# core/launcher.py:16
DEFAULT_IINA_PATH = "/Applications/IINA.app/Contents/MacOS/iina-cli"

# core/storage.py (в DEFAULT_SETTINGS)
"iina_path": "/Applications/IINA.app/Contents/MacOS/iina-cli"
```

Один и тот же путь в двух местах.

---

## Целевое состояние

### Решение 1: Полиморфные методы в `PlatformClient`

Добавить в `PlatformClient` ABC (и реализовать в каждом клиенте) методы, инкапсулирующие платформенную специфику:

```python
# core/platform.py — дополнения к ABC
class PlatformClient(ABC):
    # ... существующие методы ...

    # ── Новые полиморфные методы ──

    @staticmethod
    @abstractmethod
    def build_stream_url(channel: str) -> str:
        """Build a platform-specific URL for streamlink."""
        ...

    @staticmethod
    @abstractmethod
    def sanitize_identifier(raw: str) -> str:
        """Extract platform-specific channel identifier from raw input
        (URL, handle, etc.) — e.g. 'https://twitch.tv/foo' → 'foo'."""
        ...

    @abstractmethod
    async def normalize_search_result(self, raw: dict) -> dict:
        """Convert a platform-specific search result to unified format."""
        ...

    @abstractmethod
    async def normalize_channel_info(self, raw: dict, login: str) -> dict:
        """Convert platform-specific channel info to unified profile format."""
        ...
```

Реализация в Twitch:

```python
# core/platforms/twitch.py
class TwitchClient(BasePlatformClient):
    @staticmethod
    def build_stream_url(channel: str) -> str:
        return f"https://twitch.tv/{channel}"

    @staticmethod
    def sanitize_identifier(raw: str) -> str:
        """Extract Twitch login from raw string.
        Handles: 'https://twitch.tv/foo' → 'foo', '@foo' → 'foo', 'foo' → 'foo'."""
        import re
        raw = raw.strip().lower()
        match = re.search(r'twitch\.tv/([a-zA-Z0-9_]+)', raw)
        if match:
            return match.group(1)
        return raw.lstrip('@')

    async def normalize_search_result(self, raw: dict) -> dict:
        return {
            "login": raw.get("broadcaster_login", ""),
            "display_name": raw.get("display_name", ""),
            "platform": "twitch",
            "avatar_url": raw.get("thumbnail_url", ""),
            "is_live": raw.get("is_live", False),
        }

    # normalize_channel_info — уже существует как _normalize_channel_info_to_profile
    # в api.py, нужно перенести сюда
```

### Решение 2: Убрать branching из `stream_resolver.py`

```python
# core/stream_resolver.py (после рефакторинга)
import shutil
import subprocess

from core.platform import PlatformClient


def resolve_hls_url(
    channel: str,
    platform_client: PlatformClient,  # ← принимает клиент вместо строки
    quality: str = "best",
) -> str:
    """Resolve HLS URL using streamlink."""
    streamlink_bin = shutil.which("streamlink")
    if not streamlink_bin:
        raise RuntimeError("streamlink not found")

    url = platform_client.build_stream_url(channel)

    cmd = [streamlink_bin, "--stream-url", url, quality]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutError:
        raise TimeoutError(f"streamlink timed out for {url}")

    if result.returncode != 0:
        if quality != "best":
            return resolve_hls_url(channel, platform_client, "best")
        raise RuntimeError(f"streamlink failed: {result.stderr.strip()}")

    return result.stdout.strip()
```

**Вызывающий код в `api.py`** теперь передаёт платформенный клиент:

```python
# БЫЛО:
hls_url = resolve_hls_url(channel, platform_string, quality)

# СТАЛО:
platform_client = self._get_platform(platform_string)  # уже есть такой метод
hls_url = resolve_hls_url(channel, platform_client, quality)
```

### Решение 3: Убрать branching из `app.py`

```python
# app.py (после рефакторинга)
@staticmethod
def _sanitize_favorite_login(raw: str, platform_client) -> str:
    """Delegate to platform-specific sanitizer."""
    return platform_client.sanitize_identifier(raw)
```

`app.py` больше не содержит `if platform == ...` цепочек.

### Решение 4: Перенести `_migrate_favorites` в `storage.py`

`_migrate_favorites` (сейчас в `app.py`, 105 строк) — это операции над конфигом:
- Поиск дубликатов YouTube по Channel ID
- Восстановление сломанных YouTube логинов
- Конвертация строковых избранных (v1) в dict (v2)

Всё это — ответственность `storage.py`. Перенести как `_migrate_favorites_v2()` и вызывать при первой загрузке конфига (внутри `load_config()` или `_migrate_v1_to_v2()`).

```python
# core/storage.py — дополнение
def load_config() -> dict:
    cfg = _load_config_from_disk()
    cfg = _deep_merge(DEFAULT_CONFIG, cfg)
    if _is_v1_config(cfg):
        cfg = _migrate_v1_to_v2(cfg)
    cfg = _migrate_favorites_v2(cfg)  # ← новый вызов здесь
    return cfg
```

**ВНИМАНИЕ:** `_migrate_favorites` сейчас зависит от `YouTubeClient.normalize_channel_id()` (для проверки корректности YouTube ID). После переноса в `storage.py`, нужно либо:
1. Импортировать `YouTubeClient` внутрь `_migrate_favorites_v2` (локальный импорт, чтобы избежать циркулярных зависимостей)
2. Или вынести `normalize_channel_id` в `core/utils.py` как чистую функцию

**Рекомендация:** Вынести `normalize_channel_id` как отдельную функцию в `core/utils.py` — это pure function без зависимостей.

### Решение 5: Удалить `Tooltip` и `tkinter`

Если `Tooltip` не используется:
- Удалить класс `Tooltip` из `core/utils.py`
- Удалить `import tkinter as tk`
- Удалить импорт `ACCENT`, `BG_ELEVATED`, `FONT_SYSTEM`, `TEXT_PRIMARY` из `ui.theme`
- `ui/theme.py` станет dead code → удалить и его (или оставить, если цвета используются где-то ещё)

**Проверка перед удалением:**
```bash
rg "Tooltip" --type py   # искать использования
rg "from core.utils import.*Tooltip" --type py
rg "ui.theme" --type py  # искать импорты ui.theme
```

### Решение 6: Консолидировать константы

```python
# core/constants.py (новый файл)
"""Shared constants for the application."""

# IINA
DEFAULT_IINA_PATH = "/Applications/IINA.app/Contents/MacOS/iina-cli"

# Config
CONFIG_DIR_NAME = "twitchx"
CONFIG_FILE_NAME = "config.json"

# Cache
AVATAR_CACHE_TTL_SECONDS = 7 * 24 * 3600   # 7 days
BROWSE_CACHE_TTL_SECONDS = 10 * 60          # 10 minutes

# OAuth
OAUTH_PORT = 3457
OAUTH_TIMEOUT_SECONDS = 120

# Images
AVATAR_SIZE = (56, 56)
THUMBNAIL_SIZE = (440, 248)
JPEG_QUALITY = 85

# Chat
CHAT_WIDTH_MIN = 250
CHAT_WIDTH_MAX = 500
CHAT_RECONNECT_DELAYS = [3, 6, 12, 24, 48]
```

Заменить дублирующиеся константы в `launcher.py`, `storage.py`, `oauth_server.py`, `api.py`, `chats/*.py` на импорт из `core/constants.py`.

---

## Список действий

### Шаг 1: Добавить полиморфные методы в ABC и реализации

- [ ] Добавить в `core/platform.py` (PlatformClient ABC):
  - `build_stream_url(channel) -> str` (staticmethod, abstract)
  - `sanitize_identifier(raw) -> str` (staticmethod, abstract)
  - `normalize_search_result(raw) -> dict` (abstract)
- [ ] Реализовать в `TwitchClient`:
  - `build_stream_url` → `f"https://twitch.tv/{channel}"`
  - `sanitize_identifier` → regex для twitch.tv URL, стрип @
  - `normalize_search_result` → маппинг полей Twitch API в унифицированный формат
- [ ] Реализовать в `KickClient`:
  - `build_stream_url` → `f"https://kick.com/{channel}"`
  - `sanitize_identifier` → regex для kick.com URL, сохранение дефисов
  - `normalize_search_result`
- [ ] Реализовать в `YouTubeClient`:
  - `build_stream_url` → `f"https://youtube.com/watch?v={channel}"`
  - `sanitize_identifier` → `normalize_channel_id` (уже существует)
  - `normalize_search_result`
- [ ] Прогнать `make check`

### Шаг 2: Заменить branching в `stream_resolver.py`

- [ ] `resolve_hls_url(channel, platform: str, ...)` → `resolve_hls_url(channel, platform_client: PlatformClient, ...)`
- [ ] Заменить `if platform == ...` на `platform_client.build_stream_url(channel)`
- [ ] Обновить ВСЕ вызовы `resolve_hls_url` в кодовой базе (в `api.py`, в тестах)
- [ ] Прогнать `make check`

### Шаг 3: Заменить branching в `app.py`

- [ ] `_sanitize_favorite_login(raw, platform: str)` → `_sanitize_favorite_login(raw, platform_client)`
- [ ] Заменить `if platform == ...` на `platform_client.sanitize_identifier(raw)`
- [ ] Обновить вызовы в `_migrate_favorites`
- [ ] Прогнать `make check`

### Шаг 4: Перенести `_migrate_favorites` в `storage.py`

- [ ] Вынести `normalize_channel_id` из `YouTubeClient` в `core/utils.py` как чистую функцию (если она чистая)
- [ ] Скопировать `_migrate_favorites` из `app.py` → `core/storage.py` как `_migrate_favorites_v2`
- [ ] Вызвать `_migrate_favorites_v2` внутри `load_config()`
- [ ] Удалить `_migrate_favorites` из `app.py`
- [ ] Убедиться, что миграция идемпотентна (повторный вызов не ломает данные)
- [ ] Прогнать `make check`

### Шаг 5: Удалить мёртвый код (tkinter/Tooltip)

- [ ] Проверить, что `Tooltip` не используется:
  ```bash
  rg "Tooltip" --type py
  rg "from core.utils import.*Tooltip"
  ```
- [ ] Если не используется:
  - [ ] Удалить класс `Tooltip` из `core/utils.py`
  - [ ] Удалить `import tkinter as tk`
- [ ] Проверить, используется ли `ui/theme.py`:
  ```bash
  rg "from ui.theme import|import ui.theme" --type py
  ```
  - [ ] Если используется только в `core/utils.py` (для Tooltip) — удалить `ui/theme.py`
- [ ] Прогнать `make check`

### Шаг 6: Создать `core/constants.py`

- [ ] Собрать все магические константы в один файл
- [ ] Заменить дублирующиеся константы в:
  - `core/launcher.py` — `DEFAULT_IINA_PATH`
  - `core/storage.py` — `DEFAULT_SETTINGS["iina_path"]`
  - `core/oauth_server.py` — порт, таймаут
  - `ui/api.py` — размеры изображений, качество JPEG
- [ ] Прогнать `make check`

### Шаг 7: Заменить нормализаторы в `api.py` на методы клиентов

- [ ] `_sanitize_channel_name(raw, platform)` → `platform_client.sanitize_identifier(raw)`
- [ ] `_normalize_twitch_search_result`, `_normalize_kick_search_result`, `_normalize_youtube_search_result` → `platform_client.normalize_search_result(raw)`
- [ ] `_build_youtube_stream_item`, `_build_kick_stream_item` → методы клиентов
- [ ] Удалить статические нормализаторы из `api.py`
- [ ] Прогнать `make check`

---

## Затрагиваемые файлы

### Создаются
| Файл | Описание | ~Строк |
|------|----------|--------|
| `core/constants.py` | Общие константы | 40 |

### Изменяются
| Файл | Изменения |
|------|-----------|
| `core/platform.py` | Добавлены `build_stream_url`, `sanitize_identifier`, `normalize_search_result` в ABC |
| `core/platforms/twitch.py` | Реализация новых методов + нормализаторы из `api.py` |
| `core/platforms/kick.py` | Реализация новых методов + нормализаторы |
| `core/platforms/youtube.py` | Реализация новых методов + нормализаторы |
| `core/stream_resolver.py` | Принимает `PlatformClient` вместо строки |
| `app.py` | Делегирует санитизацию в `PlatformClient`, миграция перенесена в `storage.py` |
| `core/storage.py` | Содержит `_migrate_favorites_v2` |
| `ui/api.py` (или `ui/api/favorites.py`, `ui/api/streams.py`, `ui/api/data.py`) | Вызовы через полиморфные методы клиентов |
| `tests/test_stream_resolver.py` | Обновить моки: передавать mock platform_client |
| `tests/test_app.py` | Обновить тесты `_sanitize_favorite_login`, `_migrate_favorites` |

### Удаляются
| Файл | Почему |
|------|--------|
| `ui/theme.py` | Если используется только `Tooltip` который удалён |
| Класс `Tooltip` из `core/utils.py` | Мёртвый код |

---

## Риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| **Циркулярный импорт** — `storage.py` импортирует `utils.py`, а `utils.py` может импортировать что-то из `storage` | Низкая | Высокое | `normalize_channel_id` — pure function без зависимостей. Вынести в `utils.py`, и `storage.py` импортирует из `utils` — цикла нет. |
| **`_migrate_favorites` полагается на `YouTubeClient`** | Средняя | Среднее | Заменить `YouTubeClient.normalize_channel_id()` на утилитарную функцию в `utils.py`. |
| **Изменение сигнатуры `resolve_hls_url` ломает тесты** | Высокая | Среднее | Тесты уже мокают `subprocess.run` — нужно обновить мок на `platform_client` аргумент. |
| **Идемпотентность `_migrate_favorites_v2`** — при повторном вызове (перезапуск) не должен дублировать/повреждать данные | Средняя | Высокое | Текущая миграция уже идемпотентна (проверяет, нужна ли миграция). При переносе сохранить эту логику. Добавить тест на двойной вызов. |

---

## План тестирования

```bash
make check     # после каждого шага
```

**Дополнительные проверки:**

```bash
# Проверить, что все клиенты реализуют новые методы ABC
uv run python -c "
from core.platforms.twitch import TwitchClient
from core.platforms.kick import KickClient
from core.platforms.youtube import YouTubeClient
for cls in [TwitchClient, KickClient, YouTubeClient]:
    assert hasattr(cls, 'build_stream_url'), f'{cls.__name__} missing build_stream_url'
    assert hasattr(cls, 'sanitize_identifier'), f'{cls.__name__} missing sanitize_identifier'
    assert hasattr(cls, 'normalize_search_result'), f'{cls.__name__} missing normalize_search_result'
print('All platform methods OK')
"

# Проверить удаление Tooltip
uv run python -c "
from core.utils import format_viewers  # всё ещё работает
try:
    from core.utils import Tooltip
    print('WARNING: Tooltip still importable')
except ImportError:
    print('Tooltip removed OK')
"
```

**Ручное тестирование (после всей фазы):**
1. `make run` — запуск без ошибок
2. Добавить канал на каждой платформе (проверка sanitize_identifier)
3. Открыть стрим на каждой платформе (проверка build_stream_url)
4. Поиск на каждой платформе (проверка normalize_search_result)
5. Проверить настройки (iina_path из constants)
6. Перезапустить приложение — убедиться, что миграция избранного идемпотентна

---

## План отката

```bash
# Полный откат фазы
git reset --hard <hash до начала>

# Частичный откат (если сломалась конкретная часть)
git checkout -- core/stream_resolver.py
git checkout -- app.py
git checkout -- core/storage.py
```

---

## Definition of Done

- [ ] В `PlatformClient` ABC добавлены `build_stream_url`, `sanitize_identifier`, `normalize_search_result`
- [ ] Все три платформенных клиента реализуют новые методы
- [ ] `stream_resolver.py` не содержит `if platform == ...`
- [ ] `app.py` не содержит `if platform == ...`
- [ ] `api.py` делегирует нормализацию в методы клиентов
- [ ] `_migrate_favorites` перенесён из `app.py` в `storage.py`
- [ ] `Tooltip` и `tkinter` удалены (если не использовались)
- [ ] `core/constants.py` создан, дублирующиеся константы заменены
- [ ] `make check` проходит
- [ ] `make run` — приложение работает идентично
- [ ] Все изменения закоммичены
