# Parallel Platform Fetch — Design Spec
**Date:** 2026-04-08
**Scope:** `ui/api.py`, `tests/test_api.py`

---

## Problem

`_async_fetch` currently polls Twitch, Kick, and YouTube **sequentially**. Each platform waits for the previous one to finish, even though the three fetches are completely independent. A typical poll cycle:

- Twitch: ~2–4 s (token check + streams + users + games)
- Kick: ~1–2 s
- YouTube: 0 s (cache hit, polled every 5 min) or ~3–5 s (RSS + videos.list)

Sequential worst case: **~11 s**. Parallel worst case: **~5 s** (max of the three).

Additionally, a Twitch `ConnectError` currently aborts the entire cycle — Kick and YouTube never update. Users with all three platforms configured see Kick/YouTube go stale whenever Twitch is unreachable.

---

## Goal

- Run all three platform fetches concurrently via `asyncio.gather`.
- Kick and YouTube always update regardless of Twitch errors (Variant B).
- Twitch retry semantics preserved: `ConnectError`, `HTTPStatusError`, `ValueError` still trigger the existing backoff retry loop.
- During Twitch retry, show the **last known** Twitch streams (not empty) so channels don't flash offline.

---

## Architecture

### New state (`TwitchXApi.__init__`)

```python
self._last_twitch_streams: list[dict[str, Any]] = []
self._last_twitch_users: list[dict[str, Any]] = []
```

Mirrors the existing `_last_youtube_streams` / `_last_youtube_fetch` pattern. Updated on every successful Twitch fetch; read when Twitch errors or times out.

---

### `_async_fetch` — restructured

Three inner coroutines replace the sequential blocks:

**`_do_twitch() -> tuple[list, list]`**
- No internal exception handling — errors propagate naturally.
- Logic unchanged: `_ensure_token` → `gather(streams, users)` → `get_games`.
- Wrapped in `asyncio.wait_for(..., timeout=_twitch_timeout)` at the gather call site.

**`_do_kick() -> list`**
- Wraps the existing `asyncio.wait_for(get_live_streams, _kick_timeout)` in try/except.
- Returns `[]` on any error (logs warning). Never raises.

**`_do_youtube() -> list`**
- Contains the existing cache-check logic (`yt_due`, `_last_youtube_fetch` update).
- `ValueError` → log + `_eval_js` status message, return `_last_youtube_streams`.
- Other exceptions → log, return `_last_youtube_streams`.
- Never raises.

**Gather call:**

```python
twitch_result, kick_streams, youtube_streams = await asyncio.gather(
    asyncio.wait_for(_do_twitch(), timeout=_twitch_timeout),
    _do_kick(),
    _do_youtube(),
    return_exceptions=True,
)
```

`return_exceptions=True` is required so that a Twitch exception does **not** cancel the Kick/YouTube tasks.

**Post-gather Twitch result handling:**

| `twitch_result` type | `twitch_streams` | `twitch_error` | Retry? |
|---|---|---|---|
| `tuple` (success) | fresh data → update cache | `None` | — |
| `TimeoutError` | `_last_twitch_streams` | `None` | No |
| `ConnectError` | `_last_twitch_streams` | exception | Yes |
| `HTTPStatusError` | `_last_twitch_streams` | exception | Yes |
| `ValueError` | `_last_twitch_streams` | exception | Yes |
| Other `Exception` | `_last_twitch_streams` | `None` | No |

**Return type changes** from `tuple[list, list, list, list]` to:

```python
tuple[list, list, list, list, BaseException | None]
# (twitch_streams, twitch_users, kick_streams, youtube_streams, twitch_error)
```

---

### `_fetch_data` — restructured

```python
twitch_streams, twitch_users, kick_streams, youtube_streams, twitch_error = (
    loop.run_until_complete(_async_fetch(...))
)

# Variant B: always update UI with what we have
self._on_data_fetched(
    twitch_favorites, kick_favorites, youtube_favorites,
    twitch_streams, twitch_users, kick_streams, youtube_streams,
)

# Then handle Twitch retry if needed
if isinstance(twitch_error, httpx.ConnectError):
    # existing backoff + "Reconnecting..." status
elif isinstance(twitch_error, httpx.HTTPStatusError):
    # show credentials error, return
elif isinstance(twitch_error, ValueError):
    # show "set credentials" error, return
# None → return (success or non-retriable, already logged)
```

The retry loop (`for attempt in range(1, max_attempts + 1)`) stays in place. On retry, `_async_fetch` runs again: Kick re-fetches, YouTube serves from cache (since `_last_youtube_fetch` was just updated), Twitch retries the network call.

---

## Error handling summary

| Scenario | Twitch | Kick | YouTube | UI |
|---|---|---|---|---|
| All succeed | Fresh | Fresh | Fresh or cached | Full update |
| Twitch timeout | Cached | Fresh | Fresh or cached | Kick/YT update, Twitch unchanged |
| Twitch ConnectError | Cached | Fresh | Fresh or cached | Kick/YT update, Twitch unchanged, retry |
| Kick fails | Fresh | `[]` | Fresh or cached | Twitch/YT update, Kick empty |
| YouTube config error | Fresh | Fresh | Cached + JS error msg | Twitch/Kick update, YT unchanged |

---

## Testing

New class `TestParallelFetch` in `tests/test_api.py`:

1. **`test_kick_updates_when_twitch_raises_connect_error`** — Twitch coroutine raises `ConnectError`, Kick returns data. Assert `_on_data_fetched` called with non-empty `kick_streams` and `twitch_error` is `ConnectError`.
2. **`test_youtube_updates_when_twitch_raises_connect_error`** — Same for YouTube.
3. **`test_twitch_cache_used_on_error`** — Pre-populate `_last_twitch_streams`, trigger Twitch error. Assert `twitch_streams` returned equals the cached value.
4. **`test_twitch_cache_updated_on_success`** — Twitch returns fresh data, assert `_last_twitch_streams` updated.
5. **`test_twitch_timeout_no_retry`** — Twitch coroutine raises `TimeoutError`. Assert `twitch_error = None` (no retry triggered).

---

## Out of scope

- Per-platform independent polling timers (topic B in the roadmap).
- Caching Kick results across poll cycles.
- Changing `_on_data_fetched` notification logic.
