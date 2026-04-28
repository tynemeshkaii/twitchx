# Архитектурный рефакторинг TwitchX — Обзорный документ

> **Дата:** 2026-04-28  
> **Статус:** План  
> **Читай первым** — перед погружением в отдельные фазы.

---

## Цель

Привести структуру кода TwitchX к лучшим мировым практикам:
- Устранить God-классы и монолитные файлы
- Восстановить работающие абстрактные базовые классы
- Избавиться от дублирования кода
- Модуляризировать фронтенд
- Поднять тестовое покрытие и стандартизировать тестовую инфраструктуру

---

## Текущее состояние: обзор проблем

### Проблемы, ранжированные по критичности

| # | Проблема | Файлы | Строки | Фаза |
|---|----------|-------|--------|------|
| 🔴 | Orphaned ABC — `PlatformClient` и `ChatClient` не наследуются никем | `core/platform.py`, `core/chat.py` | 131+93 | 1 |
| 🔴 | ~200 строк дублирования платформенной инфраструктуры | `core/platforms/{twitch,kick,youtube}.py` | 3×~70 | 1 |
| 🔴 | ~60 строк дублирования чат-инфраструктуры | `core/chats/{twitch,kick}_chat.py` | 2×~40 | 1 |
| 🔴 | God Object `TwitchXApi` — 36 методов, 30+ замыканий | `ui/api.py` | 2,926 | 2 |
| 🔴 | Монолитный фронтенд — HTML+CSS+JS в одном файле | `ui/index.html` | 5,414 | 3 |
| 🟡 | Ad-hoc замыкания вместо методов | `ui/api.py` | ~30 шт. | 2 |
| 🟡 | Platform-branching разбросан по кодовой базе | `app.py`, `stream_resolver.py`, `api.py` | ~50 строк | 4 |
| 🟡 | Миграция конфига разделена между `storage.py` и `app.py` | `core/storage.py`, `app.py` | ~150 строк | 4 |
| 🟢 | 5 механизмов конкурентности в одном классе | `ui/api.py` | — | 2 |
| 🟢 | Нет conftest.py, дублирование test-helper'ов | `tests/` | 3 файла | 5 |
| 🟢 | `pytest-httpx` в зависимостях, но не используется | `pyproject.toml` | — | 5 |
| 🟢 | Зависимость `tkinter` ради одного класса `Tooltip` | `core/utils.py` | 71 | 4 |

---

## Карта текущей архитектуры

```
main.py (17 строк)
  └── app.py (200 строк) — TwitchXApp
        ├── Создаёт pywebview окно
        ├── Создаёт TwitchXApi (ui/api.py, 2926 строк) — МОСТ Python↔JS
        │     ├── Хранит ссылки на:
        │     │   ├── TwitchClient  (core/platforms/twitch.py, 489 строк)
        │     │   ├── KickClient    (core/platforms/kick.py, 504 строки)
        │     │   ├── YouTubeClient (core/platforms/youtube.py, 841 строка)
        │     │   ├── TwitchChatClient  (core/chats/twitch_chat.py, 371 строка)
        │     │   └── KickChatClient    (core/chats/kick_chat.py, 424 строки)
        │     ├── Использует:
        │     │   ├── core/storage.py — конфиг, кэш аватаров, брауз-кэш
        │     │   ├── core/stream_resolver.py — streamlink HLS
        │     │   ├── core/launcher.py — внешний IINA плеер
        │     │   ├── core/oauth_server.py — OAuth redirect сервер
        │     │   └── core/utils.py — format_viewers, Tooltip (tkinter)
        │     └── Экспонирует методы для JS через pywebview.api
        └── Загружает ui/index.html (5414 строк) — весь фронтенд

Неиспользуемые ABC (никто не наследует):
  core/platform.py — PlatformClient(ABC), 14 методов
  core/chat.py — ChatClient(ABC), 5 методов
```

---

## Карта целевой архитектуры

```
main.py
  └── app.py — TwitchXApp (облегчённый, без миграций)
        ├── Создаёт pywebview окно
        ├── Создаёт TwitchXApi — ОРКЕСТРАТОР (200 строк)
        │     ├── Делегирует в:
        │     │   ├── api/auth.py — AuthManager
        │     │   ├── api/streams.py — StreamManager
        │     │   ├── api/data.py — DataManager (poll, refresh, browse, search)
        │     │   ├── api/favorites.py — FavoritesManager
        │     │   └── api/chat.py — ChatManager
        │     ├── Платформенные клиенты (реальные наследники ABC):
        │     │   ├── core/platforms/base.py — BasePlatformClient (общая инфраструктура)
        │     │   │   ├── core/platforms/twitch.py — TwitchClient(BasePlatformClient)
        │     │   │   ├── core/platforms/kick.py — KickClient(BasePlatformClient)
        │     │   │   └── core/platforms/youtube.py — YouTubeClient(BasePlatformClient)
        │     │   └── Каждый реализует build_stream_url(), sanitize_channel_id(), normalize_*()
        │     └── Чат-клиенты (реальные наследники ABC):
        │         ├── core/chats/base.py — BaseChatClient (reconnect, emit_status, ...)
        │         │   ├── core/chats/twitch_chat.py — TwitchChatClient(BaseChatClient)
        │         │   └── core/chats/kick_chat.py — KickChatClient(BaseChatClient)
        │         └── core/chat.py — ChatClient(ABC) + модели данных (исправлен)
        └── Загружает ui/index.html — shell, подключающий модули:
              ├── css/tokens.css, layout.css, components.css, views.css
              └── js/*.js — ES modules, каждый ~100-400 строк

Миграции в одном месте:
  core/storage.py — ВСЯ конфиг-миграция (v1→v2 И чистка избранного)

Общая тестовая инфраструктура:
  tests/conftest.py — общие фикстуры и фабрики моков
```

---

## Зависимости между фазами

```
Фаза 1 (ABC restore) ──┬──> Фаза 2 (api.py decomposition)
                       │        │
                       │        └──> Фаза 3 (frontend modularization)
                       │               (можно параллельно с фазой 2 во второй половине)
                       │
                       ├──> Фаза 4 (platform strategy) — можно параллельно с фазой 2
                       │
                       └──> Фаза 5 (test infrastructure) — идёт ПАРАЛЛЕЛЬНО со всеми
                            (обновляется после каждой фазы)
```

**Рекомендуемый порядок выполнения:**
1. **Фаза 1** — фундамент, затрагивает все платформенные и чат-клиенты. Делать первой.
2. **Фаза 5 (частично)** — `conftest.py` и общие фикстуры. Создать до фазы 2, чтобы использовать в ней.
3. **Фаза 2** — самая объёмная. Разбивать на подшаги, коммитить после каждого.
4. **Фаза 4** — хорошо идёт параллельно с фазой 2, так как решает смежную проблему.
5. **Фаза 3** — можно делать в любое время, не блокируется Python-рефакторингом.
6. **Фаза 5 (остальное)** — `pytest-cov`, чистка `pytest-httpx`, OAuth-тесты.

---

## Правила работы (для каждой фазы)

1. **Один коммит на логический шаг** — не смешивать изменения.
2. **`make check` после каждого коммита** — линтер + тесты должны проходить.
3. **Не добавлять новую функциональность** — только структурные изменения.
4. **Поведение приложения не должно измениться** — рефакторинг, не редизайн.
5. **Если фаза требует больше 3 дней** — разбить на подфазы и создать отдельные документы.

---

## Метрики успеха

| Метрика | Текущее | Целевое |
|---------|---------|---------|
| Максимальный размер Python-файла | 2,926 строк (`api.py`) | ≤ 500 строк |
| Максимальный размер JS-файла | 3,057 строк (`index.html`) | ≤ 400 строк |
| Количество неиспользуемых ABC | 2 (`PlatformClient`, `ChatClient`) | 0 |
| Строк дублирования между платформами | ~200 | 0 |
| Механизмов конкурентности в одном классе | 5 | 1-2 |
| Platform-branching в не-платформенных файлах | 3 файла | 0 |
| Наличие conftest.py | Нет | Есть |
| Тестовое покрытие (оценка) | ~55% Python | ~70%+ Python |
| Фронтенд тесты | 0 | Базовая структура для будущих тестов |

---

## Файлы документации по фазам

1. **[Фаза 1: Восстановление ABC](./2026-04-28-phase1-abc-restore.md)** — `BasePlatformClient` и `BaseChatClient`
2. **[Фаза 2: Декомпозиция ui/api.py](./2026-04-28-phase2-api-decomposition.md)** — разбиение God-класса
3. **[Фаза 3: Модуляризация фронтенда](./2026-04-28-phase3-frontend-modularization.md)** — разделение `index.html`
4. **[Фаза 4: Стратегия вместо platform-branching](./2026-04-28-phase4-platform-strategy.md)** — консолидация платформенной логики
5. **[Фаза 5: Инфраструктура тестов](./2026-04-28-phase5-test-infrastructure.md)** — `conftest.py`, общие фикстуры, `pytest-cov`
