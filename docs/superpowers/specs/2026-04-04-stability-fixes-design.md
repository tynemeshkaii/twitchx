# Stability Fixes Design — Approach C

**Date:** 2026-04-04
**Status:** Approved
**Scope:** Bug fixes + structural pattern corrections + per-platform timeouts

## Overview

Fix all confirmed stability bugs in the multi-platform polling pipeline. No new features, no UI changes. After this pass the architecture must be resistant to the same class of bugs re-entering.

## Bug Inventory

| # | Bug | Location | Impact |
|---|-----|----------|--------|
| 1 | Twitch fetch not isolated | `ui/api.py _async_fetch` | One Twitch API error kills entire fetch, wipes Kick + YouTube from UI |
| 2 | YouTube `_live_video_ids` stale | `core/platforms/youtube.py` | Ended streams return old video ID, iframe embeds broken stream |
| 3 | QuotaTracker reads stale config | `core/platforms/youtube.py` | `remaining()` over-reports, quota can be exceeded silently |
| 4 | `_fetching` not thread-safe | `ui/api.py` | Two concurrent refreshes possible, corrupts stream state |
| 5 | `start_polling` not protected | `ui/api.py` | Double-poll from concurrent login/settings callbacks |
| 6 | No per-platform timeout | `ui/api.py _async_fetch` | One slow/hanging platform blocks entire poll cycle indefinitely |

---

## Section 1: Platform Fetch Isolation + Timeouts

### Fix

Wrap the Twitch fetch block in `_async_fetch` with try/except identical to the existing Kick pattern. Each platform contributes its results independently; a failure produces empty results + warning, not a raised exception.

**Before:**
```python
if twitch_favorites and twitch_conf.get("client_id") ...:
    await self._twitch._ensure_token()
    twitch_streams, twitch_users = await asyncio.gather(...)
    ...  # raises → entire fetch aborted
```

**After:**
```python
if twitch_favorites and twitch_conf.get("client_id") ...:
    try:
        twitch_streams, twitch_users = await asyncio.wait_for(
            _fetch_twitch(), timeout=12.0
        )
    except Exception as e:
        logger.warning("Twitch fetch failed: %s", e)
```

### Per-Platform Timeouts

Wrap each platform's top-level coroutine in `asyncio.wait_for`:

| Platform | Timeout | Rationale |
|----------|---------|-----------|
| Twitch | 12s | streams + users parallel, each httpx call has 15s internal timeout |
| Kick | 12s | single get_live_streams call |
| YouTube | 20s | parallel RSS fetches (N channels) + videos.list batch |

`asyncio.TimeoutError` is caught by the same outer try/except as all other exceptions — empty result, warning logged, other platforms unaffected.

### Inner coroutine helpers

Extract each platform's fetch into a local async helper inside `_async_fetch` to keep the timeout wrapping clean:

```python
async def _do_twitch() -> tuple[list, list]:
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
```

---

## Section 2: YouTube `_live_video_ids` Stale Cache

### Problem

`_live_video_ids: dict[str, str]` maps `channel_id → video_id`. It is written on every poll when a stream is live, but never cleared. When a stream ends the entry remains. `resolve_stream_url(channel_id, quality)` returns the stale video ID.

### Fix

At the start of `get_live_streams(channel_ids)`, before any API calls, evict entries for every channel being polled:

```python
for cid in valid_ids:
    self._live_video_ids.pop(cid, None)
```

Then repopulate only from live streams found in this cycle. Channels not in `valid_ids` are unaffected (unlikely to matter but preserves any cross-channel data).

---

## Section 3: QuotaTracker In-Memory Counter

### Problem

`QuotaTracker.remaining()` reads quota from `YouTubeClient.self._config` (in-memory). After `use()` saves updated quota to disk via `update_config()`, it does NOT update the client's `self._config`. The next `remaining()` call reads the pre-use stale value.

### Fix

`QuotaTracker` owns authoritative in-memory state: `_used: int` and `_date: str`. These are initialised from config once at construction. All reads use in-memory state. Disk writes remain (for persistence across restarts) but reads do not depend on them.

```python
class QuotaTracker:
    def __init__(self, get_yt_config, update_fn=None):
        self._lock = threading.Lock()
        self._update_fn = update_fn or self._default_update
        # Sync in-memory state from persisted config once at init
        yc = get_yt_config()
        today = date.today().isoformat()
        if yc.get("quota_reset_date") == today:
            self._used = yc.get("daily_quota_used", 0)
        else:
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

    def _maybe_reset(self) -> None:
        today = date.today().isoformat()
        if self._date != today:
            self._used = 0
            self._date = today
```

`_maybe_reset` replaces the date-check that was previously scattered across `remaining()` and `use()`. The `get_yt_config` callable is used at construction to seed `_used` and `_date` from persisted config, then discarded — it is not stored as an instance variable. The `update_fn` callable is retained for disk persistence.

---

## Section 4: Thread Safety

### `_fetching` → `threading.Lock`

**Before:**
```python
self._fetching = False

# in refresh():
if self._fetching:
    return
self._fetching = True
# ...
# in _fetch_data finally:
self._fetching = False
```

**After:**
```python
self._fetch_lock = threading.Lock()

# in refresh():
if not self._fetch_lock.acquire(blocking=False):
    return  # already fetching
# ...
# in _fetch_data finally:
self._fetch_lock.release()
```

The `_fetching` attribute is removed entirely. `_fetch_lock` is acquired in `refresh()` (the only public entry point) and released in the `finally` block of `_fetch_data` after the background thread completes. `threading.Lock` in Python is not owner-bound, so a different thread releasing a lock acquired by another thread is valid — this cross-thread transfer is intentional here.

### `start_polling` double-scheduling

**Before:** no lock — two threads can both cancel and reschedule the timer.

**After:**
```python
self._poll_lock = threading.Lock()

def start_polling(self, interval_seconds: int = 60) -> None:
    with self._poll_lock:
        if self._polling_timer:
            self._polling_timer.cancel()
            self._polling_timer = None
        if not self._shutdown.is_set():
            self._polling_timer = threading.Timer(...)
            self._polling_timer.daemon = True
            self._polling_timer.start()
```

---

## Files Changed

| File | Changes |
|------|---------|
| `ui/api.py` | Bug 1: Twitch try/except + per-platform `wait_for` timeouts; Bug 4: `_fetching → _fetch_lock`; Bug 5: `_poll_lock` in `start_polling` |
| `core/platforms/youtube.py` | Bug 2: clear `_live_video_ids` on poll; Bug 3: `QuotaTracker` in-memory counters |

**No new files. No UI changes. All existing tests must pass.**

---

## Testing

Existing tests must continue to pass. New unit tests:

- `test_youtube.py`: `QuotaTracker` resets at midnight, persists across `use()` calls, does not over-report after `use()`
- `test_youtube.py`: `get_live_streams` clears stale video IDs for polled channels
- `test_api.py`: fetch continues with Kick/YouTube data when Twitch raises
- `test_api.py`: concurrent `refresh()` calls — second is a no-op (lock held)
- `test_api.py`: concurrent `start_polling()` calls — only one timer active

---

## Non-Goals

- No new UI features
- No config schema changes
- No changes to chat, launcher, stream_resolver, native_player
- No performance optimisations beyond what is strictly necessary for the fixes
