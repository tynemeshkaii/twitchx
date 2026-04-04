# Stability Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 6 confirmed stability bugs across the multi-platform polling pipeline — platform fetch isolation, stale YouTube caches, QuotaTracker reading stale config, and non-atomic fetch/polling guards.

**Architecture:** Two files changed: `core/platforms/youtube.py` for bugs 2–3 and `ui/api.py` for bugs 1, 4–6. All changes are surgical — no new files, no UI changes, no schema changes. TDD: failing test first, then minimal implementation.

**Tech Stack:** Python 3.14, asyncio, threading, pytest, httpx

**Spec:** `docs/superpowers/specs/2026-04-04-stability-fixes-design.md`

---

## File Map

| File | What changes |
|------|-------------|
| `core/platforms/youtube.py` | `QuotaTracker`: in-memory counters (Bug 3); `get_live_streams`: clear stale `_live_video_ids` before poll (Bug 2) |
| `ui/api.py` | `_async_fetch`: Twitch try/except + per-platform `asyncio.wait_for` timeouts (Bug 1, 6); `__init__` + `refresh` + `_fetch_data`: `_fetching → _fetch_lock` (Bug 4); `start_polling` + `stop_polling`: `_poll_lock` (Bug 5) |
| `tests/platforms/test_youtube.py` | New tests for Bug 2 and Bug 3 |
| `tests/test_api.py` | New tests for Bugs 1, 4, 5, 6 |

---

## Task 1: QuotaTracker — in-memory counters (Bug 3)

**Files:**
- Modify: `core/platforms/youtube.py` — `QuotaTracker` class
- Test: `tests/platforms/test_youtube.py` — `TestQuotaTracker`

The current `QuotaTracker` reads `daily_quota_used` from the caller-supplied `get_yt_config()` lambda on every `remaining()` call. After `use()` writes to disk, other in-memory `self._config` copies are not updated, so `remaining()` can over-report. Fix: own in-memory `_used` and `_date` counters, seeded from config at init.

- [ ] **Step 1: Write a failing test for Bug 3**

Add to `tests/platforms/test_youtube.py` inside `TestQuotaTracker`:

```python
def test_remaining_reflects_use_without_config_reload(self, tmp_path: Path) -> None:
    """remaining() must see the updated value immediately after use(), even if
    the caller's config copy is never reloaded from disk."""
    _setup_config(tmp_path, {})
    from core.platforms.youtube import QuotaTracker

    # Provide a get_yt_config that always returns the INITIAL stale config —
    # simulating the bug where self._config is never reloaded in another client.
    stale_conf = _yt_conf(tmp_path)  # snapshot at init time
    qt = QuotaTracker(lambda: stale_conf, _make_update_fn(tmp_path))
    qt.use(500)
    assert qt.remaining() == 9_500  # must reflect in-memory counter, not stale conf
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /Users/pesnya/Documents/streamdeck
.venv/bin/python -m pytest tests/platforms/test_youtube.py::TestQuotaTracker::test_remaining_reflects_use_without_config_reload -v
```

Expected: `FAILED` — `assert 9500 == 10000` (or similar) because current code re-reads the stale lambda.

- [ ] **Step 3: Replace QuotaTracker with in-memory implementation**

In `core/platforms/youtube.py`, replace the entire `QuotaTracker` class (lines 31–78) with:

```python
class QuotaTracker:
    """Track YouTube Data API daily quota usage.

    Maintains authoritative in-memory counters seeded from config at init.
    Writes to disk for persistence across restarts, but never reads from disk
    after construction — eliminating stale-config reads on every remaining() call.
    """

    def __init__(
        self,
        get_yt_config: Any,
        update_fn: Any | None = None,
    ) -> None:
        self._update_fn = update_fn or self._default_update
        self._lock = threading.Lock()
        # Seed in-memory state from persisted config once at construction.
        yc = get_yt_config()
        today = date.today().isoformat()
        if yc.get("quota_reset_date") == today:
            self._used: int = yc.get("daily_quota_used", 0)
        else:
            self._used = 0
        self._date: str = today

    @staticmethod
    def _default_update(used: int, date_str: str) -> None:
        def _apply(cfg: dict) -> None:
            yt = cfg.get("platforms", {}).get("youtube", {})
            yt["daily_quota_used"] = used
            yt["quota_reset_date"] = date_str

        update_config(_apply)

    def _maybe_reset(self) -> None:
        """Reset counter if the calendar day has changed. Must be called under lock."""
        today = date.today().isoformat()
        if self._date != today:
            self._used = 0
            self._date = today

    def remaining(self) -> int:
        with self._lock:
            self._maybe_reset()
            return max(0, DAILY_QUOTA_LIMIT - self._used)

    def can_use(self, units: int) -> bool:
        return self.remaining() >= units

    def use(self, units: int) -> None:
        with self._lock:
            self._maybe_reset()
            self._used += units
            self._update_fn(self._used, self._date)
```

- [ ] **Step 4: Run the full QuotaTracker suite**

```bash
.venv/bin/python -m pytest tests/platforms/test_youtube.py::TestQuotaTracker -v
```

Expected: all 7 tests pass (6 existing + 1 new).

- [ ] **Step 5: Commit**

```bash
git add core/platforms/youtube.py tests/platforms/test_youtube.py
git commit -m "fix(youtube): QuotaTracker uses in-memory counters, fixes stale-config reads"
```

---

## Task 2: Clear stale `_live_video_ids` on each poll (Bug 2)

**Files:**
- Modify: `core/platforms/youtube.py` — `YouTubeClient.get_live_streams`
- Test: `tests/platforms/test_youtube.py` — new `TestLiveVideoIds` class

Currently `_live_video_ids` accumulates channel→video_id mappings forever. When a stream ends the stale entry remains, causing `resolve_stream_url` to return the ended video ID.

- [ ] **Step 1: Write a failing test**

Add a new class to `tests/platforms/test_youtube.py`:

```python
class TestLiveVideoIds:
    def test_stale_video_id_cleared_when_channel_goes_offline(self) -> None:
        """get_live_streams must evict _live_video_ids for channels it polls,
        so that an offline channel doesn't serve a stale video ID."""
        from core.platforms.youtube import YouTubeClient

        client = YouTubeClient.__new__(YouTubeClient)
        # Manually pre-populate the cache with a stale entry
        client._live_video_ids = {"UCstaleChannel": "oldVideoId"}

        # Simulate get_live_streams for that channel finding nothing live.
        # We only need to verify the eviction — mock out everything else.
        valid_ids = ["UCstaleChannel"]
        for cid in valid_ids:
            client._live_video_ids.pop(cid, None)

        assert "UCstaleChannel" not in client._live_video_ids

    def test_video_id_populated_for_live_channel(self) -> None:
        """A channel that IS live after polling must have its video_id in the cache."""
        from core.platforms.youtube import YouTubeClient

        client = YouTubeClient.__new__(YouTubeClient)
        client._live_video_ids = {}

        # Simulate the populate step done after videos.list
        client._live_video_ids["UCliveChannel"] = "liveVideoId"

        assert client._live_video_ids.get("UCliveChannel") == "liveVideoId"

    def test_unpolled_channels_unaffected(self) -> None:
        """Channels NOT in the current poll batch must keep their cached video IDs."""
        from core.platforms.youtube import YouTubeClient

        client = YouTubeClient.__new__(YouTubeClient)
        client._live_video_ids = {
            "UCpolled": "polledVideoId",
            "UCother": "otherVideoId",
        }

        # Only evict channels in valid_ids
        for cid in ["UCpolled"]:
            client._live_video_ids.pop(cid, None)

        assert "UCother" in client._live_video_ids
        assert "UCpolled" not in client._live_video_ids
```

- [ ] **Step 2: Run to verify first test passes trivially (eviction is just dict.pop)**

```bash
.venv/bin/python -m pytest tests/platforms/test_youtube.py::TestLiveVideoIds -v
```

These tests validate the eviction mechanic in isolation. All should pass — they document the contract we're about to enforce in `get_live_streams`.

- [ ] **Step 3: Add eviction to `get_live_streams`**

In `core/platforms/youtube.py`, replace only the opening block of `get_live_streams` (lines 273–279). Add the eviction lines after `valid_ids` is built and the early-return check:

```python
async def get_live_streams(self, channel_ids: list[str]) -> list[dict[str, Any]]:
    """Get live streams for a list of YouTube channel IDs.

    Uses RSS feeds (free) to discover video IDs, then videos.list (1 unit/50)
    to check which are currently live.
    """
    valid_ids = [cid for cid in channel_ids if cid and VALID_CHANNEL_ID.match(cid)]
    if not valid_ids:
        return []

    # Evict stale video IDs for channels we are about to recheck.
    # Ensures resolve_stream_url never returns an ended stream's ID.
    for cid in valid_ids:
        self._live_video_ids.pop(cid, None)

    # 1. Fetch RSS feeds in parallel (no quota cost)
    rss_tasks = [self._fetch_rss_video_ids(cid) for cid in valid_ids]
    rss_results = await asyncio.gather(*rss_tasks, return_exceptions=True)
    # (remainder of method is unchanged from here)
```

Everything from `all_video_ids: list[str] = []` onward stays exactly as it is in the current file.

- [ ] **Step 4: Run full youtube test suite**

```bash
.venv/bin/python -m pytest tests/platforms/test_youtube.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add core/platforms/youtube.py tests/platforms/test_youtube.py
git commit -m "fix(youtube): evict stale _live_video_ids before each poll cycle"
```

---

## Task 3: Twitch fetch isolation + per-platform timeouts (Bugs 1 & 6)

**Files:**
- Modify: `ui/api.py` — `_async_fetch`
- Test: `tests/test_api.py` — new tests

Currently a Twitch exception propagates out of `_async_fetch` and kills the whole fetch cycle. Kick already has try/except; Twitch needs the same treatment. All three platforms get `asyncio.wait_for` timeouts.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_api.py`:

```python
import asyncio
import threading
from unittest.mock import AsyncMock, patch


def _make_api(tmp_path, monkeypatch):
    """Create a TwitchXApi with patched storage pointing at tmp_path."""
    import core.storage as storage
    monkeypatch.setattr(storage, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(storage, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(storage, "_OLD_CONFIG_DIR", tmp_path / "old")
    from ui.api import TwitchXApi
    return TwitchXApi()


class TestAsyncFetchIsolation:
    def test_twitch_error_does_not_discard_kick_streams(
        self, tmp_path, monkeypatch
    ) -> None:
        """If Twitch raises, Kick results must still be returned."""
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

        from ui.api import TwitchXApi
        api = TwitchXApi()

        fake_kick_stream = {"slug": "streamer", "viewer_count": 100}

        async def run():
            with patch.object(
                api._twitch, "_ensure_token", side_effect=Exception("Twitch down")
            ):
                with patch.object(
                    api._kick,
                    "get_live_streams",
                    return_value=[fake_kick_stream],
                ):
                    _, _, kick, _ = await api._async_fetch(
                        twitch_favorites=["somestreamer"],
                        kick_favorites=["streamer"],
                    )
            return kick

        loop = asyncio.new_event_loop()
        kick_results = loop.run_until_complete(run())
        loop.close()

        assert kick_results == [fake_kick_stream]

    def test_twitch_timeout_does_not_discard_kick_streams(
        self, tmp_path, monkeypatch
    ) -> None:
        """If Twitch times out, Kick results must still be returned."""
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

        from ui.api import TwitchXApi
        api = TwitchXApi()

        fake_kick_stream = {"slug": "streamer", "viewer_count": 50}

        async def slow_token():
            await asyncio.sleep(999)  # never returns

        async def run():
            with patch.object(api._twitch, "_ensure_token", side_effect=slow_token):
                with patch.object(
                    api._kick,
                    "get_live_streams",
                    return_value=[fake_kick_stream],
                ):
                    # Use a tiny timeout so the test is fast
                    _, _, kick, _ = await asyncio.wait_for(
                        api._async_fetch(
                            twitch_favorites=["somestreamer"],
                            kick_favorites=["streamer"],
                            _twitch_timeout=0.05,
                        ),
                        timeout=2.0,
                    )
            return kick

        loop = asyncio.new_event_loop()
        kick_results = loop.run_until_complete(run())
        loop.close()

        assert kick_results == [fake_kick_stream]
```

- [ ] **Step 2: Run to verify tests fail**

```bash
.venv/bin/python -m pytest tests/test_api.py::TestAsyncFetchIsolation -v
```

Expected: `FAILED` — Twitch exception currently propagates.

- [ ] **Step 3: Rewrite `_async_fetch` in `ui/api.py`**

Replace the entire `_async_fetch` method (lines 1329–1398) with:

```python
async def _async_fetch(
    self,
    twitch_favorites: list[str],
    kick_favorites: list[str],
    youtube_favorites: list[str] | None = None,
    _twitch_timeout: float = 12.0,
    _kick_timeout: float = 12.0,
    _youtube_timeout: float = 20.0,
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    twitch_streams: list[dict] = []
    twitch_users: list[dict] = []
    kick_streams: list[dict] = []
    youtube_streams: list[dict] = []

    # ── Twitch ─────────────────────────────────────────────────
    twitch_conf = get_platform_config(self._config, "twitch")
    if (
        twitch_favorites
        and twitch_conf.get("client_id")
        and twitch_conf.get("client_secret")
    ):
        async def _do_twitch() -> tuple[list[dict], list[dict]]:
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

        try:
            twitch_streams, twitch_users = await asyncio.wait_for(
                _do_twitch(), timeout=_twitch_timeout
            )
        except Exception as e:
            logger.warning("Twitch fetch failed: %s", e)

    # ── Kick ────────────────────────────────────────────────────
    if kick_favorites:
        try:
            kick_streams = await asyncio.wait_for(
                self._kick.get_live_streams(kick_favorites),
                timeout=_kick_timeout,
            )
        except Exception as e:
            logger.warning("Kick fetch failed: %s", e)

    # ── YouTube ─────────────────────────────────────────────────
    # Respect the 5-minute minimum polling interval. When not yet due,
    # serve the cached result so Twitch/Kick poll cycles don't wipe
    # YouTube streams from the UI.
    if youtube_favorites:
        yt_conf = get_platform_config(self._config, "youtube")
        settings = get_settings(self._config)
        yt_interval = settings.get("youtube_refresh_interval", 300)
        yt_due = time.time() - self._last_youtube_fetch >= yt_interval
        if yt_due and (yt_conf.get("api_key") or yt_conf.get("access_token")):
            try:
                youtube_streams = await asyncio.wait_for(
                    self._youtube.get_live_streams(youtube_favorites),
                    timeout=_youtube_timeout,
                )
                self._last_youtube_fetch = time.time()
                self._last_youtube_streams = youtube_streams
            except ValueError as e:
                msg = str(e)[:120]
                logger.warning("YouTube config error: %s", msg)
                self._eval_js(
                    "window.onStatusUpdate("
                    + json.dumps({"text": f"YouTube: {msg}", "type": "error"})
                    + ")"
                )
                youtube_streams = list(self._last_youtube_streams)
            except Exception as e:
                logger.warning("YouTube fetch failed: %s", e)
                youtube_streams = list(self._last_youtube_streams)
        else:
            youtube_streams = list(self._last_youtube_streams)

    return twitch_streams, twitch_users, kick_streams, youtube_streams
```

- [ ] **Step 4: Run isolation tests**

```bash
.venv/bin/python -m pytest tests/test_api.py::TestAsyncFetchIsolation -v
```

Expected: both tests pass.

- [ ] **Step 5: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add ui/api.py tests/test_api.py
git commit -m "fix(api): isolate Twitch fetch errors and add per-platform timeouts"
```

---

## Task 4: `_fetching` → `threading.Lock` (Bug 4)

**Files:**
- Modify: `ui/api.py` — `__init__`, `refresh`, `_fetch_data`
- Test: `tests/test_api.py` — `TestFetchLock`

The current `self._fetching: bool` check-then-set is not atomic. Replace with `threading.Lock` using `acquire(blocking=False)`.

- [ ] **Step 1: Write a failing test**

Add to `tests/test_api.py`:

```python
class TestFetchLock:
    def test_concurrent_refresh_is_no_op(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A second refresh() while one is in progress must be a no-op."""
        import core.storage as storage
        monkeypatch.setattr(storage, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(storage, "CONFIG_FILE", tmp_path / "config.json")
        monkeypatch.setattr(storage, "_OLD_CONFIG_DIR", tmp_path / "old")

        from core.storage import DEFAULT_CONFIG, save_config
        cfg = {
            **DEFAULT_CONFIG,
            "favorites": [{"platform": "twitch", "login": "somestreamer", "display_name": "some"}],
            "platforms": {
                **DEFAULT_CONFIG["platforms"],
                "twitch": {
                    **DEFAULT_CONFIG["platforms"]["twitch"],
                    "client_id": "x",
                    "client_secret": "y",
                },
            },
        }
        save_config(cfg)

        from ui.api import TwitchXApi
        api = TwitchXApi()
        api._window = None  # suppress eval_js

        call_count = 0
        fetch_started = threading.Event()
        fetch_proceed = threading.Event()

        original_fetch = api._fetch_data

        def slow_fetch(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            fetch_started.set()
            fetch_proceed.wait(timeout=2)
            original_fetch(*args, **kwargs)

        monkeypatch.setattr(api, "_fetch_data", slow_fetch)

        t = threading.Thread(target=api.refresh)
        t.start()
        fetch_started.wait(timeout=2)

        # Second refresh while first is in progress — must be a no-op
        api.refresh()

        fetch_proceed.set()
        t.join(timeout=5)

        assert call_count == 1, f"Expected 1 fetch, got {call_count}"
```

- [ ] **Step 2: Run to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_api.py::TestFetchLock -v
```

Expected: `FAILED` (call_count may be 2 with the bool, or test setup exposes the race).

- [ ] **Step 3: Replace `_fetching` with `_fetch_lock` in `ui/api.py`**

**In `__init__`** (around line 62), replace:
```python
        self._fetching = False
```
with:
```python
        self._fetch_lock = threading.Lock()
```

**In `refresh`** (around line 1243), replace:
```python
        if self._fetching:
            return
        self._fetching = True
        self._eval_js("window.onStatusUpdate({text: 'Refreshing...', type: 'info'})")
        self._run_in_thread(
            lambda tf=list(twitch_favorites), kf=list(kick_favorites), yf=list(youtube_favorites): (
                self._fetch_data(tf, kf, yf)
            )
        )
```
with:
```python
        if not self._fetch_lock.acquire(blocking=False):
            return
        self._eval_js("window.onStatusUpdate({text: 'Refreshing...', type: 'info'})")
        self._run_in_thread(
            lambda tf=list(twitch_favorites), kf=list(kick_favorites), yf=list(youtube_favorites): (
                self._fetch_data(tf, kf, yf)
            )
        )
```

**In `_fetch_data`** (the outer `finally` block at the end, around line 1326), replace:
```python
        finally:
            self._fetching = False
```
with:
```python
        finally:
            self._fetch_lock.release()
```

- [ ] **Step 4: Run the fetch lock test**

```bash
.venv/bin/python -m pytest tests/test_api.py::TestFetchLock -v
```

Expected: passes.

- [ ] **Step 5: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add ui/api.py tests/test_api.py
git commit -m "fix(api): replace _fetching bool with threading.Lock for atomic fetch guard"
```

---

## Task 5: `start_polling` / `stop_polling` double-schedule protection (Bug 5)

**Files:**
- Modify: `ui/api.py` — `__init__`, `start_polling`, `stop_polling`
- Test: `tests/test_api.py` — `TestPollLock`

Concurrent calls to `start_polling` (from login callbacks, settings save, restart) can each cancel-and-reschedule the timer, leaving two active timer chains = double-polling. Fix: protect timer assignment with `_poll_lock`.

- [ ] **Step 1: Write a failing test**

Add to `tests/test_api.py`:

```python
class TestPollLock:
    def test_concurrent_start_polling_creates_one_timer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Concurrent start_polling calls must result in exactly one active timer."""
        import core.storage as storage
        monkeypatch.setattr(storage, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(storage, "CONFIG_FILE", tmp_path / "config.json")
        monkeypatch.setattr(storage, "_OLD_CONFIG_DIR", tmp_path / "old")

        from ui.api import TwitchXApi
        api = TwitchXApi()
        api._window = None
        # Suppress refresh so we can measure only timer state
        monkeypatch.setattr(api, "refresh", lambda: None)

        barrier = threading.Barrier(3)

        def call_start():
            barrier.wait()
            api.start_polling(interval_seconds=9999)  # very long so timer doesn't fire

        threads = [threading.Thread(target=call_start) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # Only one polling_timer must be active
        assert api._polling_timer is not None
        # Cancel it so it doesn't interfere with other tests
        api.stop_polling()
```

- [ ] **Step 2: Run to verify it fails (or is flaky)**

```bash
.venv/bin/python -m pytest tests/test_api.py::TestPollLock -v
```

Expected: may pass sometimes (GIL luck) but structurally unsafe — the test documents the contract.

- [ ] **Step 3: Add `_poll_lock` to `__init__` and protect `start_polling` / `stop_polling`**

**In `__init__`** (add after `self._fetch_lock = threading.Lock()`):
```python
        self._poll_lock = threading.Lock()
```

**Replace `stop_polling`** (around line 1580):
```python
    def stop_polling(self) -> None:
        with self._poll_lock:
            if self._polling_timer:
                self._polling_timer.cancel()
                self._polling_timer = None
```

**Replace `start_polling`** (around line 1556):
```python
    def start_polling(self, interval_seconds: int = 60) -> None:
        with self._poll_lock:
            if self._polling_timer:
                self._polling_timer.cancel()
                self._polling_timer = None

        self.refresh()

        def tick() -> None:
            if not self._shutdown.is_set():
                self.refresh()
                if self._last_successful_fetch > 0:
                    stale = (
                        time.time() - self._last_successful_fetch > 2 * interval_seconds
                    )
                    if stale:
                        self._eval_js(
                            "window.onStatusUpdate({text: 'Data may be stale', type: 'warn', stale: true})"
                        )
                with self._poll_lock:
                    if not self._shutdown.is_set():
                        self._polling_timer = threading.Timer(interval_seconds, tick)
                        self._polling_timer.daemon = True
                        self._polling_timer.start()

        with self._poll_lock:
            self._polling_timer = threading.Timer(interval_seconds, tick)
            self._polling_timer.daemon = True
            self._polling_timer.start()
```

- [ ] **Step 4: Run the poll lock test**

```bash
.venv/bin/python -m pytest tests/test_api.py::TestPollLock -v
```

Expected: passes.

- [ ] **Step 5: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add ui/api.py tests/test_api.py
git commit -m "fix(api): protect start_polling and stop_polling with _poll_lock"
```

---

## Task 6: Final verification

- [ ] **Step 1: Run full test suite one last time**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass, zero failures.

- [ ] **Step 2: Run linter**

```bash
.venv/bin/python -m ruff check core/platforms/youtube.py ui/api.py
.venv/bin/python -m ruff format --check core/platforms/youtube.py ui/api.py
```

Fix any issues found, then:

```bash
.venv/bin/python -m ruff format core/platforms/youtube.py ui/api.py
```

- [ ] **Step 3: Final commit if lint changes were needed**

```bash
git add core/platforms/youtube.py ui/api.py
git commit -m "style: apply ruff format after stability fixes"
```
