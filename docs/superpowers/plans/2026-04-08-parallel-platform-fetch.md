# Parallel Platform Fetch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run Twitch, Kick, and YouTube fetches concurrently via `asyncio.gather`, with independent error handling so Kick/YouTube always update even when Twitch fails.

**Architecture:** Extract three inner coroutines (`_do_twitch`, `_do_kick`, `_do_youtube`) inside `_async_fetch`, run them with `asyncio.gather(..., return_exceptions=True)`, and return a 5-tuple that includes a `twitch_error` field. `_fetch_data` always calls `_on_data_fetched` first (Variant B), then handles the Twitch error for retry/status display.

**Tech Stack:** Python `asyncio.gather`, `httpx`, `threading`, `pytest`

---

## Files

- Modify: `ui/api.py` — `__init__`, `_async_fetch`, `_fetch_data`
- Modify: `tests/test_api.py` — update 4-tuple unpacks → 5-tuple; add `TestParallelFetch`

---

### Task 1: Write failing tests

**Files:**
- Modify: `tests/test_api.py`

- [ ] **Step 1: Update existing `TestAsyncFetchIsolation` tests to unpack 5-tuple**

Find both tests that unpack `_, _, kick, _` and change to `_, _, kick, _, _`:

In `test_twitch_error_does_not_discard_kick_streams` (line ~767):
```python
                _, _, kick, _, _ = await api._async_fetch(
                    twitch_favorites=["somestreamer"],
                    kick_favorites=["streamer"],
                )
```

In `test_twitch_timeout_does_not_discard_kick_streams` (line ~824):
```python
                _, _, kick, _, _ = await api._async_fetch(
                    twitch_favorites=["somestreamer"],
                    kick_favorites=["streamer"],
                    _twitch_timeout=0.05,
                )
```

- [ ] **Step 2: Add `TestParallelFetch` class at the end of `tests/test_api.py`**

```python
class TestParallelFetch:
    """Verify asyncio.gather parallel fetch: independent errors per platform."""

    def _setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import core.storage as storage

        monkeypatch.setattr(storage, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(storage, "CONFIG_FILE", tmp_path / "config.json")
        monkeypatch.setattr(storage, "_OLD_CONFIG_DIR", tmp_path / "old")
        from core.storage import DEFAULT_CONFIG, save_config

        cfg = {
            **DEFAULT_CONFIG,
            "platforms": {
                **DEFAULT_CONFIG["platforms"],
                "twitch": {
                    **DEFAULT_CONFIG["platforms"]["twitch"],
                    "client_id": "fakeid",
                    "client_secret": "fakesecret",
                },
            },
        }
        save_config(cfg)

    def test_twitch_cache_used_on_connect_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ConnectError → _last_twitch_streams returned, twitch_error set."""
        self._setup(tmp_path, monkeypatch)
        import httpx
        from ui.api import TwitchXApi

        api = TwitchXApi()
        cached = [{"user_login": "cached_streamer", "platform": "twitch"}]
        api._last_twitch_streams = list(cached)

        async def run():
            with patch.object(
                api._twitch, "_ensure_token", side_effect=httpx.ConnectError("down")
            ):
                return await api._async_fetch(
                    twitch_favorites=["cached_streamer"],
                    kick_favorites=[],
                )

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(run())
        loop.close()

        twitch_streams, _, _, _, twitch_error = result
        assert twitch_streams == cached
        assert isinstance(twitch_error, httpx.ConnectError)

    def test_twitch_cache_updated_on_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Successful Twitch fetch updates _last_twitch_streams; twitch_error is None."""
        self._setup(tmp_path, monkeypatch)
        from ui.api import TwitchXApi

        api = TwitchXApi()
        fresh = [{"user_login": "live_streamer", "platform": "twitch"}]

        async def run():
            with (
                patch.object(api._twitch, "_ensure_token", return_value=None),
                patch.object(api._twitch, "get_live_streams", return_value=fresh),
                patch.object(api._twitch, "get_users", return_value=[]),
            ):
                return await api._async_fetch(
                    twitch_favorites=["live_streamer"],
                    kick_favorites=[],
                )

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(run())
        loop.close()

        twitch_streams, _, _, _, twitch_error = result
        assert twitch_streams == fresh
        assert twitch_error is None
        assert api._last_twitch_streams == fresh

    def test_twitch_timeout_sets_error_to_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Twitch TimeoutError → twitch_error=None (timeout is non-retriable)."""
        self._setup(tmp_path, monkeypatch)
        from ui.api import TwitchXApi

        api = TwitchXApi()

        async def slow_token():
            await asyncio.sleep(999)

        async def run():
            with patch.object(api._twitch, "_ensure_token", side_effect=slow_token):
                return await api._async_fetch(
                    twitch_favorites=["somestreamer"],
                    kick_favorites=[],
                    _twitch_timeout=0.05,
                )

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(run())
        loop.close()

        _, _, _, _, twitch_error = result
        assert twitch_error is None

    def test_youtube_cache_served_when_twitch_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """YouTube _last_youtube_streams served even when Twitch raises ConnectError."""
        self._setup(tmp_path, monkeypatch)
        import httpx
        import time
        from ui.api import TwitchXApi

        api = TwitchXApi()
        fake_yt = [{"login": "UCfakechannel1234567890", "platform": "youtube"}]
        api._last_youtube_streams = list(fake_yt)
        api._last_youtube_fetch = time.time()  # just fetched → cache hit, no API call

        async def run():
            with patch.object(
                api._twitch, "_ensure_token", side_effect=httpx.ConnectError("down")
            ):
                return await api._async_fetch(
                    twitch_favorites=["somestreamer"],
                    kick_favorites=[],
                    youtube_favorites=["UCfakechannel1234567890"],
                )

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(run())
        loop.close()

        _, _, _, youtube_streams, twitch_error = result
        assert youtube_streams == fake_yt
        assert isinstance(twitch_error, httpx.ConnectError)
```

- [ ] **Step 3: Run tests — verify they fail as expected**

```bash
source .venv/bin/activate && pytest tests/test_api.py::TestAsyncFetchIsolation tests/test_api.py::TestParallelFetch -v
```

Expected: `TestAsyncFetchIsolation` fails with `ValueError: too many values to unpack`, `TestParallelFetch` fails similarly. All new tests fail.

---

### Task 2: Add Twitch cache fields to `__init__`

**Files:**
- Modify: `ui/api.py` — `__init__` method

- [ ] **Step 1: Add `_last_twitch_streams` and `_last_twitch_users` after `_last_youtube_streams`**

Find the lines (around line 77):
```python
        self._last_youtube_streams: list[dict[str, Any]] = []
```

Add immediately after:
```python
        self._last_twitch_streams: list[dict[str, Any]] = []
        self._last_twitch_users: list[dict[str, Any]] = []
```

---

### Task 3: Restructure `_async_fetch`

**Files:**
- Modify: `ui/api.py` — `_async_fetch` method (lines 1329–1416)

- [ ] **Step 1: Replace the entire `_async_fetch` body with the parallel implementation**

Replace from `async def _async_fetch(` to the closing `return twitch_streams, twitch_users, kick_streams, youtube_streams` with:

```python
    async def _async_fetch(
        self,
        twitch_favorites: list[str],
        kick_favorites: list[str],
        youtube_favorites: list[str] | None = None,
        _twitch_timeout: float = 12.0,
        _kick_timeout: float = 12.0,
        _youtube_timeout: float = 20.0,
    ) -> tuple[list[dict], list[dict], list[dict], list[dict], BaseException | None]:
        youtube_favorites = youtube_favorites or []

        async def _do_twitch() -> tuple[list[dict], list[dict]]:
            twitch_conf = get_platform_config(self._config, "twitch")
            if not (
                twitch_favorites
                and twitch_conf.get("client_id")
                and twitch_conf.get("client_secret")
            ):
                return [], []
            await self._twitch._ensure_token()
            streams, users = await asyncio.gather(
                self._twitch.get_live_streams(twitch_favorites),
                self._twitch.get_users(twitch_favorites),
            )
            game_ids = [s.get("game_id", "") for s in streams if s.get("game_id")]
            if game_ids:
                games = await self._twitch.get_games(game_ids)
                self._games.update(games)
            return streams, users

        async def _do_kick() -> list[dict]:
            if not kick_favorites:
                return []
            try:
                return await asyncio.wait_for(
                    self._kick.get_live_streams(kick_favorites),
                    timeout=_kick_timeout,
                )
            except Exception as e:
                logger.warning("Kick fetch failed: %s", e)
                return []

        async def _do_youtube() -> list[dict]:
            if not youtube_favorites:
                return []
            yt_conf = get_platform_config(self._config, "youtube")
            settings = get_settings(self._config)
            yt_interval = settings.get("youtube_refresh_interval", 300)
            yt_due = time.time() - self._last_youtube_fetch >= yt_interval
            if not yt_due or not (yt_conf.get("api_key") or yt_conf.get("access_token")):
                return list(self._last_youtube_streams)
            try:
                youtube_streams = await asyncio.wait_for(
                    self._youtube.get_live_streams(youtube_favorites),
                    timeout=_youtube_timeout,
                )
                self._last_youtube_fetch = time.time()
                self._last_youtube_streams = youtube_streams
                return youtube_streams
            except ValueError as e:
                msg = str(e)[:120]
                logger.warning("YouTube config error: %s", msg)
                self._eval_js(
                    "window.onStatusUpdate("
                    + json.dumps({"text": f"YouTube: {msg}", "type": "error"})
                    + ")"
                )
                return list(self._last_youtube_streams)
            except Exception as e:
                logger.warning("YouTube fetch failed: %s", e)
                return list(self._last_youtube_streams)

        twitch_result, kick_result, yt_result = await asyncio.gather(
            asyncio.wait_for(_do_twitch(), timeout=_twitch_timeout),
            _do_kick(),
            _do_youtube(),
            return_exceptions=True,
        )

        # Handle Twitch — ConnectError/HTTPStatusError/ValueError are retriable
        twitch_error: BaseException | None = None
        if isinstance(twitch_result, BaseException):
            if isinstance(twitch_result, TimeoutError):
                logger.warning("Twitch fetch timed out after %.1fs", _twitch_timeout)
            elif isinstance(
                twitch_result, (httpx.ConnectError, httpx.HTTPStatusError, ValueError)
            ):
                twitch_error = twitch_result
            else:
                logger.warning("Twitch fetch failed: %s", twitch_result)
            twitch_streams: list[dict] = list(self._last_twitch_streams)
            twitch_users: list[dict] = list(self._last_twitch_users)
        else:
            twitch_streams, twitch_users = twitch_result
            self._last_twitch_streams = twitch_streams
            self._last_twitch_users = twitch_users

        # _do_kick/_do_youtube never raise; isinstance guards against programming errors
        kick_streams: list[dict] = kick_result if isinstance(kick_result, list) else []
        youtube_streams: list[dict] = yt_result if isinstance(yt_result, list) else []

        return twitch_streams, twitch_users, kick_streams, youtube_streams, twitch_error
```

---

### Task 4: Update `_fetch_data`

**Files:**
- Modify: `ui/api.py` — `_fetch_data` method (lines 1253–1327)

- [ ] **Step 1: Replace the inner `try` block inside the `for` loop**

The outer structure (`try/finally: self._fetch_lock.release()`, `for attempt in range(...)`, `loop = asyncio.new_event_loop()`, `finally: self._close_thread_loop(loop)`) stays. Replace only the inner `try` block content:

```python
    def _fetch_data(
        self,
        twitch_favorites: list[str],
        kick_favorites: list[str],
        youtube_favorites: list[str] | None = None,
    ) -> None:
        if youtube_favorites is None:
            youtube_favorites = []
        retry_delays = [5, 15, 30]
        max_attempts = len(retry_delays) + 1

        try:
            for attempt in range(1, max_attempts + 1):
                if self._shutdown.is_set():
                    return
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    (
                        twitch_streams,
                        twitch_users,
                        kick_streams,
                        youtube_streams,
                        twitch_error,
                    ) = loop.run_until_complete(
                        self._async_fetch(
                            twitch_favorites, kick_favorites, youtube_favorites
                        )
                    )
                    # Variant B: always update UI so Kick/YouTube reflect fresh data
                    # even while Twitch is retrying. Twitch shows its last known state.
                    self._on_data_fetched(
                        twitch_favorites,
                        kick_favorites,
                        youtube_favorites,
                        twitch_streams,
                        twitch_users,
                        kick_streams,
                        youtube_streams,
                    )
                    if twitch_error is None:
                        return
                    if isinstance(twitch_error, httpx.ConnectError):
                        if attempt < max_attempts:
                            delay = retry_delays[attempt - 1]
                            att = attempt + 1
                            self._eval_js(
                                f"window.onStatusUpdate({{text: 'Reconnecting... (attempt {att}/{max_attempts})', type: 'warn'}})"
                            )
                            time.sleep(delay)
                        else:
                            self._eval_js(
                                "window.onStatusUpdate({text: 'No internet connection', type: 'error'})"
                            )
                    elif isinstance(twitch_error, httpx.HTTPStatusError):
                        status_code = twitch_error.response.status_code
                        if status_code in (401, 403):
                            self._eval_js(
                                "window.onStatusUpdate({text: 'Check your API credentials in Settings', type: 'error'})"
                            )
                        else:
                            self._eval_js(
                                f"window.onStatusUpdate({{text: 'API error: {status_code}', type: 'error'}})"
                            )
                        return
                    elif isinstance(twitch_error, ValueError):
                        self._eval_js(
                            "window.onStatusUpdate({text: 'Set API credentials in Settings', type: 'error'})"
                        )
                        return
                except Exception as e:
                    traceback.print_exc()
                    msg = str(e)[:80] if str(e) else "Unknown error"
                    safe_msg = json.dumps(msg)
                    self._eval_js(
                        f"window.onStatusUpdate({{text: 'Error: ' + String({safe_msg}), type: 'error'}})"
                    )
                    return
                finally:
                    self._close_thread_loop(loop)
        finally:
            self._fetch_lock.release()
```

---

### Task 5: Run all tests and commit

**Files:** none

- [ ] **Step 1: Run the full test suite**

```bash
source .venv/bin/activate && pytest tests/ -v
```

Expected: all tests pass except the 4 pre-existing `test_stream_resolver` failures (streamlink not installed on this machine — unrelated to this change).

- [ ] **Step 2: Verify the parallel tests pass specifically**

```bash
source .venv/bin/activate && pytest tests/test_api.py::TestAsyncFetchIsolation tests/test_api.py::TestParallelFetch -v
```

Expected: 6 tests pass (2 existing + 4 new).

- [ ] **Step 3: Commit**

```bash
git add ui/api.py tests/test_api.py
git commit -m "$(cat <<'EOF'
perf(api): parallel platform fetch with independent error handling

Replace sequential Twitch→Kick→YouTube fetches in _async_fetch with
asyncio.gather(return_exceptions=True) so all three platforms run
concurrently. Kick and YouTube always update even when Twitch fails
(Variant B). Twitch errors set twitch_error in the 5-tuple return;
_fetch_data calls _on_data_fetched before deciding whether to retry.
Add _last_twitch_streams/users cache so Twitch channels show their
last known state during retries instead of flashing offline.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```
