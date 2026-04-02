# Fix: Kick credentials reset + login + favorites display

Перед началом ознакомься с CLAUDE.md, прочитай файлы `ui/api.py`, `ui/index.html`, `core/platforms/kick.py`.

---

## Контекст проблем

После Phase 1 (Kick platform) есть три взаимосвязанных бага:
1. Credentials Kick «сбрасываются» визуально после ввода
2. Kick стримеры не отображаются после добавления в favorites
3. Kick OAuth логин работает некорректно

## Баг 1: Settings modal не показывает Kick login status

**Симптом:** после успешного Kick OAuth логина, при повторном открытии Settings всегда показывается форма "Login" вместо "Logged in as X". Пользователю кажется что credentials сбросились.

**Корневая причина:** `get_full_config_for_settings()` (ui/api.py) не возвращает `kick_display_name`. JS в `openSettings()` (index.html) проверяет `config.kick_display_name` — поле всегда undefined.

**Файлы:**
- `ui/api.py` — метод `get_full_config_for_settings()` (~строка 154): нужно добавить `kick_display_name` и `kick_user_login` из `kick_conf` в возвращаемый dict
- `ui/index.html` — `openSettings()` (~строка 2646): уже правильно проверяет `config.kick_display_name`, просто Python не отдаёт это поле

## Баг 2: `kick_login()` читает данные из устаревшего снимка

**Симптом:** после успешного OAuth flow, `onKickLoginComplete` получает пустые `display_name` и `login`.

**Корневая причина:** в `kick_login()` (ui/api.py ~строка 360), переменная `kick_conf` захватывается на строке 361/373. Затем в `do_login()` вызывается `update_config(_save_kick_user)` на строке 422, который обновляет config на диске. Но на строках 427-428 код читает `kick_conf["user_display_name"]` и `kick_conf["user_login"]` — из СТАРОГО снимка, в котором эти поля ещё пустые.

**Исправление:** использовать локальные переменные `udisplay` и `ulogin` (которые уже есть в scope, строки 413-414) вместо `kick_conf["user_display_name"]` и `kick_conf["user_login"]`.

## Баг 3: Kick стримеры не показываются без credentials

**Симптом:** после добавления Kick каналов в favorites и ввода client_id/client_secret, стримы не загружаются.

**Корневая причина:** в `_async_fetch()` (ui/api.py ~строка 804-810) Kick fetch выполняется ТОЛЬКО если `kick_conf.get("client_id")` и `kick_conf.get("client_secret")` оба непустые. Но публичные Kick API эндпоинты (`/public/v1/livestreams`) НЕ требуют client_id/client_secret — они работают без авторизации. Это ложное ограничение, скопированное с логики Twitch (который действительно требует client_credentials).

**Исправление:** убрать проверку credentials для Kick public API. Kick стримы должны загружаться всегда, когда есть kick favorites, вне зависимости от наличия credentials. Credentials нужны только для OAuth логина и отправки чат-сообщений.

Также проверить: в `refresh()` (~строка 654-709) — есть ли аналогичная проблема с `kick_has_creds` блокирующим отображение.

## Дополнительные проверки

1. **Race condition при save_settings.** `save_settings()` вызывает `start_polling()` в конце, который вызывает `refresh()`, который может конфликтовать с уже запущенным polling timer. Проверь что `start_polling()` корректно отменяет предыдущий timer перед запуском нового (вроде это уже делается через `stop_polling()` внутри `start_polling()`).

2. **TwitchClient `_ensure_token` не ломает Kick.** Убедись что при fetch Twitch и Kick данных параллельно (через `asyncio.gather`), ошибка одного не ломает другой.

3. **KickClient `_ensure_token` для публичных эндпоинтов.** `_get()` всегда вызывает `_ensure_token()`. Если credentials пустые — `_ensure_token` вернёт None, и `_get()` отправит запрос без Authorization header. Для `/public/` это нормально. Убедись что `_ensure_token` не кидает исключение когда credentials пустые.

4. **`refresh()` — проверка `has_credentials`.** В строке ~680-698 есть проверка: если НИ У ОДНОЙ платформы нет credentials — показать пустой экран. Это неправильно для Kick, у которого публичные API работают без credentials. Нужно чтобы Kick стримы показывались даже если kick credentials пустые (но есть kick favorites).

## Порядок исправления

1. Исправь `get_full_config_for_settings()` — добавь `kick_display_name` и `kick_user_login`
2. Исправь `kick_login()` строки 427-428 — используй `udisplay`/`ulogin` вместо `kick_conf`
3. Исправь `_async_fetch()` — убери проверку kick credentials для публичного API
4. Исправь `refresh()` — Kick favorites не должны требовать credentials для fetch
5. Запусти `make check` — все тесты должны проходить
6. Протестируй вручную через `./run.sh`:
   - Добавь Kick канал в favorites → стрим должен появиться без credentials
   - Введи Kick credentials в Settings → они должны сохраниться при переоткрытии Settings
   - Залогинься в Kick → "Logged in as X" должно сохраняться при переоткрытии Settings

## Команды

```bash
make check    # lint + test
make test     # только тесты
./run.sh      # запуск приложения для ручного тестирования
```
