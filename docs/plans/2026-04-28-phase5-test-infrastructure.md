# Фаза 5: Инфраструктура тестов

> **Дата:** 2026-04-28  
> **Статус:** План  
> **Зависит от:** Фаза 1 (ABC restore) — для обновления моков  
> **Выполняется:** Параллельно со всеми фазами, обновляется после каждой  
> **Обзорный документ:** [architecture-refactoring.md](./2026-04-28-architecture-refactoring.md)

---

## Цель

Стандартизировать тестовую инфраструктуру:
- Создать `tests/conftest.py` с общими фикстурами и фабриками моков
- Убрать дублирование test-helper'ов (3 разных `_patch_storage`)
- Добавить `pytest-cov` для измерения покрытия
- Удалить неиспользуемый `pytest-httpx` из зависимостей
- Добавить тесты на OAuth-флоу (сейчас 0)

---

## Текущее состояние

### Проблема 1: Дублирование `_patch_storage()` в 3 файлах

```python
# tests/test_api.py:74-80
def _patch_storage(monkeypatch, tmp_path):
    """Размещает config.json во временной директории."""
    ...

# tests/test_storage.py:13-18  — ДРУГАЯ реализация
def _patch_storage(monkeypatch, tmp_path):
    ...

# tests/test_channel_api.py:19-23  — ТРЕТЬЯ реализация
def _patch_storage(monkeypatch, tmp_path):
    ...
```

Три файла, три разные реализации одного и того же хелпера. Должен быть один — в `conftest.py`.

### Проблема 2: Нет `conftest.py`

Нет общих фикстур, нет фабрик моков, нет переиспользования. Каждый тестовый файл — самодостаточный остров. Это приводит к дублированию.

### Проблема 3: `pytest-httpx` в зависимостях, но не используется

```toml
# pyproject.toml
[project.optional-dependencies]
dev = [
    "pytest-httpx>=0.35.0",  # ← ни разу не используется
]
```

Все HTTP-моки делаются через `monkeypatch.setattr`. Либо начать использовать `pytest-httpx` для платформенных тестов (он удобнее), либо удалить.

### Проблема 4: Нет измерения покрытия

Нет `pytest-cov` в зависимостях. Неизвестно реальное покрытие — только оценки.

### Проблема 5: Пробелы в тестовом покрытии

- **OAuth-флоу:** 0 тестов (`core/oauth_server.py` не тестируется)
- **Фронтенд JS:** 0 тестов
- **Интеграционные тесты:** 0 (все тесты — юниты на моках)
- **Twitch token refresh:** не тестируется
- **Kick чат send errors (кроме 403):** не тестируются

---

## Целевое состояние

### 1. `tests/conftest.py` (~150 строк)

```python
# tests/conftest.py
"""Shared fixtures and mock factories for all tests."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest


# ==========================================================================
# Config / Storage fixtures
# ==========================================================================

@pytest.fixture
def temp_config_dir(tmp_path, monkeypatch):
    """Redirect config directory to a temporary path.

    Use this fixture in any test that reads or writes config via core.storage.
    """
    config_dir = tmp_path / "twitchx"
    config_dir.mkdir()
    config_file = config_dir / "config.json"

    # Write a minimal default config
    default_config = {
        "version": 2,
        "platforms": {
            "twitch": {},
            "kick": {},
            "youtube": {},
        },
        "settings": {},
        "favorites": [],
    }
    config_file.write_text(json.dumps(default_config))

    # Patch CONFIG_DIR and CONFIG_FILE in core.storage
    monkeypatch.setattr("core.storage.CONFIG_DIR", config_dir)
    monkeypatch.setattr("core.storage.CONFIG_FILE", config_file)

    return config_file


@pytest.fixture
def config_with_twitch_auth(temp_config_dir):
    """Config file with valid Twitch OAuth tokens."""
    cfg = json.loads(temp_config_dir.read_text())
    cfg["platforms"]["twitch"] = {
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
        "token_type": "user",
        "token_is_valid": True,
    }
    temp_config_dir.write_text(json.dumps(cfg))
    return temp_config_dir


# ==========================================================================
# Platform client mock factories
# ==========================================================================

@pytest.fixture
def mock_twitch_client():
    """Return a MagicMock configured as a TwitchClient."""
    client = MagicMock()
    client.PLATFORM_ID = "twitch"
    client.PLATFORM_NAME = "Twitch"
    client.build_stream_url = MagicMock(return_value="https://twitch.tv/test")
    client.sanitize_identifier = MagicMock(return_value="test")
    client.get_live_streams = AsyncMock(return_value=[])
    client.search_channels = AsyncMock(return_value=[])
    client.get_channel_info = AsyncMock(return_value={})
    client.get_auth_url = MagicMock(return_value="https://id.twitch.tv/oauth2/authorize?...")
    client.exchange_code = AsyncMock(return_value={"access_token": "tok", "refresh_token": "ref"})
    client.get_current_user = AsyncMock(return_value={"login": "test", "display_name": "Test"})
    client.get_followed_channels = AsyncMock(return_value=["streamer1", "streamer2"])
    return client


@pytest.fixture
def mock_kick_client():
    """Return a MagicMock configured as a KickClient."""
    client = MagicMock()
    client.PLATFORM_ID = "kick"
    client.PLATFORM_NAME = "Kick"
    client.build_stream_url = MagicMock(return_value="https://kick.com/test")
    client.sanitize_identifier = MagicMock(return_value="test-slug")
    client.get_live_streams = AsyncMock(return_value=[])
    client.search_channels = AsyncMock(return_value=[])
    client.get_channel_info = AsyncMock(return_value={})
    client.get_auth_url = MagicMock(return_value="https://id.kick.com/oauth2/authorize?...")
    client.exchange_code = AsyncMock(return_value={"access_token": "tok"})
    client.get_current_user = AsyncMock(return_value={"login": "test", "display_name": "Test"})
    client.get_followed_channels = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_youtube_client():
    """Return a MagicMock configured as a YouTubeClient."""
    client = MagicMock()
    client.PLATFORM_ID = "youtube"
    client.PLATFORM_NAME = "YouTube"
    client.build_stream_url = MagicMock(return_value="https://youtube.com/watch?v=test")
    client.sanitize_identifier = MagicMock(return_value="UCtest")
    client.get_live_streams = AsyncMock(return_value=[])
    client.search_channels = AsyncMock(return_value=[])
    client.get_channel_info = AsyncMock(return_value={})
    return client


# ==========================================================================
# JS callback capture fixture
# ==========================================================================

@pytest.fixture
def capture_eval_js():
    """Captures all _eval_js() calls for assertion.

    Usage:
        def test_foo(capture_eval_js):
            api._eval_js = capture_eval_js
            api.some_method()
            assert capture_eval_js.calls[0] == "window.onSomething(...)"
    """
    class Capture:
        def __init__(self):
            self.calls: list[str] = []

        def __call__(self, code: str):
            self.calls.append(code)

        def assert_any(self, fragment: str):
            for call in self.calls:
                if fragment in call:
                    return
            raise AssertionError(f"No call containing '{fragment}' in {self.calls}")

    return Capture()


# ==========================================================================
# Thread mocking fixture (sync execution)
# ==========================================================================

@pytest.fixture
def run_sync():
    """Patch _run_in_thread to execute synchronously."""
    import ui.api
    original = ui.api.TwitchXApi._run_in_thread

    def _patch(api_instance):
        def sync_run(fn):
            fn()
        api_instance._run_in_thread = sync_run

    yield _patch
    # restore
    ui.api.TwitchXApi._run_in_thread = original
```

### 2. Удаление дубликатов из тестов

После создания `conftest.py`:

```python
# tests/test_api.py (после рефакторинга)
# УДАЛИТЬ: _patch_storage, _make_twitch_client, _make_kick_client, InlineThread, FakeKickChatClient
# ЗАМЕНИТЬ: на фикстуры из conftest

def test_add_channel_accepts_kick_url_with_hyphen(temp_config_dir, mock_kick_client, capture_eval_js):
    from ui.api import TwitchXApi
    api = TwitchXApi()
    api._kick = mock_kick_client
    api._eval_js = capture_eval_js
    api._run_in_thread = lambda fn: fn()  # синхронное выполнение

    api.add_channel("https://kick.com/test-user", "kick", "Test User")

    capture_eval_js.assert_any("onChannelAdded")
```

### 3. Добавить `pytest-cov` и настроить покрытие

```toml
# pyproject.toml — дополнения
[project.optional-dependencies]
dev = [
    "pytest>=9.0.2",
    "pytest-asyncio>=1.3.0",
    "pytest-cov>=6.0.0",       # ← добавить
    # "pytest-httpx>=0.35.0",  # ← удалить (или оставить, если решим использовать)
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = [
    "--cov=core",
    "--cov=ui",
    "--cov-report=term-missing",
    "--cov-report=html",
]
```

Обновить Makefile:

```makefile
# Makefile
test:
	uv run pytest tests/ -v

cov:                     # ← новый target
	uv run pytest tests/ -v --cov=core --cov=ui --cov-report=term-missing

cov-html:                # ← новый target
	uv run pytest tests/ -v --cov=core --cov=ui --cov-report=html
```

### 4. Добавить тесты на OAuth-флоу

```python
# tests/test_oauth_server.py (новый файл)
"""Tests for the OAuth callback server."""

import threading
import time
import urllib.request
import urllib.error

from core.oauth_server import wait_for_oauth_code


def test_oauth_server_receives_code():
    """OAuth сервер получает код из callback URL."""
    result = []

    def _request():
        time.sleep(0.1)  # дать серверу запуститься
        try:
            urllib.request.urlopen("http://localhost:3457/callback?code=test-auth-code&scope=read")
        except Exception:
            pass  # сервер может закрыться до ответа

    thread = threading.Thread(target=_request)
    thread.start()

    code = wait_for_oauth_code(timeout=5)
    assert code == "test-auth-code"


def test_oauth_server_timeout():
    """OAuth сервер возвращает None по таймауту."""
    code = wait_for_oauth_code(timeout=1)
    assert code is None


def test_oauth_server_ignores_non_callback_paths():
    """Запросы не на /callback игнорируются."""
    result = []

    def _bad_request():
        time.sleep(0.1)
        try:
            urllib.request.urlopen("http://localhost:3457/other")
        except Exception:
            pass

    def _good_request():
        time.sleep(0.2)
        try:
            urllib.request.urlopen("http://localhost:3457/callback?code=real-code")
        except Exception:
            pass

    threading.Thread(target=_bad_request).start()
    threading.Thread(target=_good_request).start()

    code = wait_for_oauth_code(timeout=5)
    assert code == "real-code"
```

---

## Список действий

### Шаг 1: Создать `tests/conftest.py`

- [ ] Создать `tests/conftest.py`
- [ ] Добавить фикстуру `temp_config_dir` (замена `_patch_storage`)
- [ ] Добавить фикстуры `mock_twitch_client`, `mock_kick_client`, `mock_youtube_client`
- [ ] Добавить фикстуру `capture_eval_js`
- [ ] Добавить фикстуру `run_sync` (замена ручного monkeypatch `_run_in_thread`)
- [ ] Прогнать `make test` — убедиться, что conftest не ломает существующие тесты

### Шаг 2: Мигрировать `test_storage.py` на фикстуры

- [ ] Заменить вызовы `_patch_storage` на использование `temp_config_dir`
- [ ] Удалить локальный `_patch_storage`
- [ ] Прогнать `make test`

### Шаг 3: Мигрировать `test_api.py` на фикстуры

- [ ] Заменить вызовы `_patch_storage` на `temp_config_dir`
- [ ] Заменить `_make_*_client()` на фикстуры `mock_*_client`
- [ ] Заменить `InlineThread` / `lambda fn: fn()` на `run_sync`
- [ ] Заменить ручной сбор `emitted` на `capture_eval_js`
- [ ] Удалить локальные хелперы
- [ ] Прогнать `make test`

### Шаг 4: Мигрировать `test_channel_api.py` на фикстуры

- [ ] Аналогично шагу 3
- [ ] Прогнать `make test`

### Шаг 5: Мигрировать платформенные тесты на фикстуры

- [ ] `tests/platforms/test_twitch.py`
- [ ] `tests/platforms/test_kick.py`
- [ ] `tests/platforms/test_youtube.py`
- [ ] `tests/platforms/test_*_browse.py`
- [ ] Заменить локальные `_setup_config`, `_make_update_fn` и т.д. на фикстуры
- [ ] Прогнать `make test`

### Шаг 6: Мигрировать чат-тесты на фикстуры

- [ ] `tests/chats/test_twitch_chat.py`
- [ ] `tests/chats/test_kick_chat.py`
- [ ] Заменить `_make_ws_mock` / `_patch_ws` на фикстуры
- [ ] Прогнать `make test`

### Шаг 7: Добавить `pytest-cov` и настроить покрытие

- [ ] `uv add --dev pytest-cov`
- [ ] Обновить `pyproject.toml` — добавить `--cov` в `addopts`
- [ ] Обновить `Makefile` — добавить `cov` и `cov-html` targets
- [ ] `make cov` — посмотреть текущее покрытие
- [ ] Зафиксировать baseline покрытия в документе (для отслеживания улучшений)

### Шаг 8: Удалить `pytest-httpx` (если не используется)

- [ ] Проверить: `rg "httpx_mock|pytest_httpx" tests/`
- [ ] Если не найдено — `uv remove --dev pytest-httpx`
- [ ] Прогнать `make test` — убедиться, что удаление не сломало тесты

### Шаг 9: Добавить тесты на OAuth

- [ ] Создать `tests/test_oauth_server.py`
- [ ] Добавить тесты: получение кода, таймаут, игнорирование не-callback путей
- [ ] Прогнать `make test`

### Шаг 10: Обновить AGENTS.md

- [ ] Добавить секцию о тестовой инфраструктуре:
  - Где лежат фикстуры (`tests/conftest.py`)
  - Как запускать тесты с покрытием (`make cov`)
  - Как писать новые тесты (использовать фикстуры из conftest)

---

## Затрагиваемые файлы

### Создаются
| Файл | Описание | ~Строк |
|------|----------|--------|
| `tests/conftest.py` | Общие фикстуры и фабрики моков | 150 |
| `tests/test_oauth_server.py` | Тесты OAuth-сервера | 60 |

### Изменяются
| Файл | Изменения |
|------|-----------|
| `tests/test_storage.py` | Удаление `_patch_storage`, использование фикстур |
| `tests/test_api.py` | Замена хелперов на фикстуры |
| `tests/test_channel_api.py` | Замена хелперов на фикстуры |
| `tests/test_browse_api.py` | Использование общих фикстур |
| `tests/test_app.py` | Использование общих фикстур |
| `tests/platforms/test_twitch.py` | Использование `mock_twitch_client` |
| `tests/platforms/test_kick.py` | Использование `mock_kick_client` |
| `tests/platforms/test_youtube.py` | Использование `mock_youtube_client` |
| `tests/platforms/test_*_browse.py` | Использование фикстур |
| `tests/chats/test_twitch_chat.py` | Использование общих фикстур |
| `tests/chats/test_kick_chat.py` | Использование общих фикстур |
| `pyproject.toml` | `pytest-cov`, `--cov` опции, удаление `pytest-httpx` |
| `Makefile` | `cov`, `cov-html` targets |
| `AGENTS.md` | Секция о тестовой инфраструктуре |

### НЕ затрагиваются
| Файл | Почему |
|------|--------|
| `core/` | Никакие production-файлы не трогаем в этой фазе |
| `ui/` | Никакие production-файлы не трогаем |
| `app.py` | Не меняется |

---

## Риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| **Фикстуры conftest.py конфликтуют с локальными определениями** | Низкая | Среднее | Имена фикстур не должны совпадать с именами функций в тестовых файлах. Использовать префиксы (`mock_`, `temp_`, `capture_`). |
| **`pytest-httpx` на самом деле используется где-то косвенно** | Низкая | Высокое | Перед удалением сделать `rg "httpx_mock\|pytest_httpx\|HTTPXMock" tests/ --type py` — если найдено, не удалять. |
| **OAuth тесты ломаются на CI из-за занятого порта** | Средняя | Среднее | Использовать `pytest.mark.skipif` для CI-среды (проверять `os.environ.get("CI")`). |
| **Массовое изменение тестов вносит регрессии** | Средняя | Высокое | Прогонять `make test` после миграции КАЖДОГО файла. Не мигрировать все файлы разом. |

---

## План тестирования

```bash
# После каждого шага
make test

# После шага 7 — проверка покрытия
make cov

# Убедиться, что HTML-отчёт генерируется
make cov-html
ls htmlcov/index.html
```

---

## План отката

```bash
# Полный откат фазы
git checkout -- tests/conftest.py
git checkout -- pyproject.toml
git checkout -- Makefile
git checkout -- tests/

# Или откатить конкретный файл
git checkout -- tests/test_api.py
```

---

## Definition of Done

- [ ] `tests/conftest.py` создан с ≥ 5 фикстурами
- [ ] Ни в одном тестовом файле нет собственной `_patch_storage()` функции (кроме conftest)
- [ ] Платформенные тесты используют `mock_*_client` фикстуры
- [ ] `test_api.py` использует `capture_eval_js` и `run_sync`
- [ ] `pytest-cov` добавлен в зависимости, `make cov` работает
- [ ] `pytest-httpx` удалён (или оставлен осознанно с комментарием)
- [ ] `tests/test_oauth_server.py` создан с ≥ 3 тестами
- [ ] `AGENTS.md` обновлён с информацией о тестовой инфраструктуре
- [ ] `make test` проходит (все существующие тесты зелёные)
- [ ] `make lint` проходит
- [ ] Все изменения закоммичены
