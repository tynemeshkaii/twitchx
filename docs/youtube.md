# YouTube Platform — Implementation Reference

This document covers the complete YouTube Data API v3 integration: architecture,
data flow, authentication, quota management, channel resolution, live-stream
polling, playback, config schema, and the migration that repairs corrupted
channel IDs.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture and Data Flow](#architecture-and-data-flow)
3. [Configuration Schema](#configuration-schema)
4. [core/platforms/youtube.py — YouTubeClient](#coreplatformsyoutubepy--youtubeclient)
   - [Per-event-loop HTTP pooling](#per-event-loop-http-pooling)
   - [Quota tracking (QuotaTracker)](#quota-tracking-quotatracker)
   - [Token management](#token-management)
   - [Live stream discovery](#live-stream-discovery)
   - [Channel resolution (get_channel_info)](#channel-resolution-get_channel_info)
   - [Channel search](#channel-search)
   - [OAuth flow](#oauth-flow)
   - [Subscriptions import](#subscriptions-import)
5. [Multi-interval polling (ui/api.py _async_fetch)](#multi-interval-polling-uiapipy-_async_fetch)
6. [Adding a YouTube channel (ui/api.py add_channel)](#adding-a-youtube-channel-uiapipy-add_channel)
7. [Playback (watch / watch_external)](#playback-watch--watch_external)
8. [Thumbnails (get_thumbnail)](#thumbnails-get_thumbnail)
9. [Config migration (app.py _migrate_favorites)](#config-migration-apppy-_migrate_favorites)
10. [Frontend (ui/index.html)](#frontend-uiindexhtml)
    - [Settings panel](#settings-panel)
    - [Platform tab and grid filtering](#platform-tab-and-grid-filtering)
    - [Adding channels from JS](#adding-channels-from-js)
    - [Sidebar display names (favoritesMeta)](#sidebar-display-names-favoritesmeta)
    - [JS callbacks reference](#js-callbacks-reference)
11. [Quota Budget Reference](#quota-budget-reference)
12. [Known Constraints and Gotchas](#known-constraints-and-gotchas)

---

## Overview

YouTube is a third-party platform alongside Twitch and Kick. It uses the
**YouTube Data API v3** (REST/JSON) rather than a WebSocket or IRC-based
protocol. The integration supports:

- API-key-only mode (read-only, no login required)
- OAuth2 Authorization Code mode (`youtube.readonly` scope, required for subscription import)
- Quota-aware live-stream polling via RSS + `videos.list`
- Channel addition by URL, `@handle`, channel ID (UCxxxx), or video URL
- Native HLS playback via `streamlink` (same pipeline as Twitch/Kick)
- Subscription import, quota display, connection test

---

## Architecture and Data Flow

```
YouTube Data API v3
      │
      ▼
YouTubeClient                 (core/platforms/youtube.py)
  ├── QuotaTracker             tracks 10k daily budget
  ├── _fetch_rss_video_ids()   FREE — gets recent video IDs per channel
  ├── get_live_streams()       1 unit/50 videos via videos.list
  ├── get_channel_info()       1–2 units — resolves @handle / video ID → channel
  ├── search_channels()        100 units — full-text channel search
  └── get_followed_channels()  1 unit/page — subscription list
      │
      ▼
TwitchXApi._async_fetch()     (ui/api.py)
  ├── Polls every 300 s (configurable: settings.youtube_refresh_interval)
  ├── Falls back to _last_youtube_streams cache between polls
  └── Merges YouTube streams with Twitch + Kick results
      │
      ▼
_on_data_fetched()
  ├── Builds stream items with video_id for playback
  ├── Builds favorites_meta {login → {display_name, platform}}
  └── window.onStreamsUpdate(data) → JS renders grid + sidebar
      │
      ▼
watch(channel, quality)
  ├── Gets video_id from cached stream data
  ├── resolve_hls_url(video_id, quality, platform="youtube")
  │     → streamlink https://www.youtube.com/watch?v={video_id}
  └── window.onStreamReady({url: hls_url, platform: "youtube"})
        → native <video> element
```

---

## Configuration Schema

Stored at `~/.config/twitchx/config.json` under `platforms.youtube`.

```json
{
  "platforms": {
    "youtube": {
      "enabled": true,
      "api_key": "",
      "client_id": "",
      "client_secret": "",
      "access_token": "",
      "refresh_token": "",
      "token_expires_at": 0,
      "user_id": "",
      "user_login": "",
      "user_display_name": "",
      "daily_quota_used": 0,
      "quota_reset_date": ""
    }
  },
  "settings": {
    "youtube_refresh_interval": 300
  },
  "favorites": [
    {
      "platform": "youtube",
      "login": "UCLzonkj0KtpdMxt5hiPWkCQ",
      "display_name": "BOVER"
    }
  ]
}
```

**Auth modes:**

| Mode | Required fields | Capabilities |
|------|----------------|--------------|
| API key only | `api_key` | Live stream polling, search, channel lookup |
| OAuth | `access_token` + `refresh_token` + `client_id` + `client_secret` | All above + subscription import |

Polling skips YouTube entirely if neither `api_key` nor `access_token` is set.

---

## core/platforms/youtube.py — YouTubeClient

### Per-event-loop HTTP pooling

TwitchX creates a fresh `asyncio` event loop per background thread
(`asyncio.new_event_loop()`). `httpx.AsyncClient` is bound to the loop it was
created on — sharing one client across loops causes `RuntimeError: Event loop
is closed`.

`YouTubeClient` solves this with a `dict[loop → AsyncClient]`:

```python
def _get_client(self) -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    with self._loop_state_lock:
        client = self._loop_clients.get(loop)
        if client is None:
            client = httpx.AsyncClient(timeout=15.0)
            self._loop_clients[loop] = client
        return client
```

`close_loop_resources()` removes the entry for the current loop and closes the
client. Called from `_close_thread_loop()` in `ui/api.py` at the end of every
background thread.

Token locks follow the same pattern (`_token_locks` dict) so concurrent token
refreshes within the same loop are serialised without blocking other loops.

### Quota tracking (QuotaTracker)

YouTube Data API v3 gives **10,000 units/day** (Pacific Time reset). Each
operation costs:

| Operation | Units |
|-----------|-------|
| `videos.list` (up to 50 IDs) | 1 |
| `channels.list` (lookup by ID or handle) | 1 |
| `videos.list` (resolve video → channel) | 1 |
| `search.list` (channel search) | **100** |
| `subscriptions.list` (50 subs/page) | 1 per page |
| RSS feed fetch | **0** (not an API call) |

`QuotaTracker` persists `daily_quota_used` and `quota_reset_date` to config.
On each call it checks if the stored date matches today; if not, usage resets
to zero automatically:

```python
def remaining(self) -> int:
    yt = self._get_yt()
    today = self._today()
    if yt.get("quota_reset_date") != today:
        return DAILY_QUOTA_LIMIT   # auto-reset
    return max(0, DAILY_QUOTA_LIMIT - yt.get("daily_quota_used", 0))
```

If `can_use(units)` returns `False`, the operation is skipped with a warning
log. A `quotaExceeded` 403 response is re-raised as `ValueError` so the UI
can display a human-readable error.

### Token management

`_ensure_token()` is called before every API request:

1. Reload config (picks up tokens saved from another thread)
2. If `token_is_valid()` → return cached `access_token`
3. Else if `refresh_token` present → call `refresh_user_token()`
4. On 400/401 from Google → clear all auth fields, raise `ValueError`

The lock (`_get_token_lock()`) prevents concurrent refreshes on the same loop
from making multiple refresh calls.

### Live stream discovery

`get_live_streams(channel_ids)` uses a two-step approach to minimise quota use:

**Step 1 — RSS feeds (free)**

```
https://www.youtube.com/feeds/videos.xml?channel_id={UCxxxx}
```

Returns the 15 most-recent uploads as an Atom feed. Parsed by
`parse_rss_video_ids()` using `xml.etree.ElementTree`. Feeds are fetched in
parallel via `asyncio.gather()`. No quota cost.

**Step 2 — `videos.list` (1 unit per 50 IDs)**

Unique video IDs from all RSS feeds are batched into groups of 50 and checked
with `part=snippet,liveStreamingDetails`. A video is considered live when:

```python
@staticmethod
def _is_video_live(item: dict) -> bool:
    details = item.get("liveStreamingDetails", {})
    return bool(details.get("actualStartTime") and not details.get("actualEndTime"))
```

`concurrentViewers` is intentionally **not** required — YouTube omits it for
some valid live streams (API propagation lag, hidden viewer counts, new streams).

The normalized stream dict includes `video_id` for later HLS resolution and
`channel_id` (same as `login`) for config deduplication:

```python
{
    "login": channel_id,         # UCxxxxxx — used as the primary key
    "display_name": channel_title,
    "title": video_title,
    "game": "",
    "viewers": int,              # 0 if concurrentViewers absent
    "started_at": "2025-01-01T12:00:00Z",
    "thumbnail_url": "https://i.ytimg.com/vi/.../maxresdefault.jpg",
    "platform": "youtube",
    "video_id": "bDsXOVkppyc",  # 11-char ID, required for playback
    "channel_id": channel_id,
    "category_id": "20"
}
```

`_live_video_ids[channel_id] = video_id` is cached on the client for fast
lookup in `watch()`.

### Channel resolution (get_channel_info)

Accepts three input forms and costs 1–2 quota units:

| Input | Example | Process |
|-------|---------|---------|
| UC channel ID | `UCLzonkj0KtpdMxt5hiPWkCQ` | `channels.list?id=` (1 unit) |
| `@handle` | `@BOVER` | `channels.list?forHandle=` (1 unit) |
| Video ID (11 chars) | `bDsXOVkppyc` | `videos.list?id=` → extract channelId → `channels.list?id=` (2 units) |

Returns `{channel_id, display_name, description, avatar_url, followers}`.

### Channel search

`search_channels(query)` calls `search.list?type=channel&maxResults=10`.
**Costs 100 units** — the most expensive operation. The UI applies a 400 ms
JS debounce before calling `api.search_channels()` to limit calls while
typing.

### OAuth flow

1. JS calls `api.youtube_login(client_id, client_secret)`
2. Python saves credentials to config (so the embedded server can read them)
3. `get_auth_url()` builds the Google OAuth URL with `access_type=offline&prompt=consent`
4. `webbrowser.open()` opens the URL in the user's default browser
5. `wait_for_oauth_code()` (from `core/oauth_server.py`) starts a temporary
   HTTP server on `http://localhost:3457/callback` (120 s timeout)
6. Google redirects with `?code=...`; server captures and returns the code
7. `exchange_code(code)` POSTs to `https://oauth2.googleapis.com/token`
8. Tokens + user info saved to config; `window.onYouTubeLoginComplete` fired

Redirect URI registered in Google Cloud Console: `http://localhost:3457/callback`

### Subscriptions import

`get_followed_channels("me")` paginates `subscriptions.list?mine=true`
(50 results/page, 1 unit/page). Each subscription is added to favorites if
not already present (case-insensitive dedup). Requires a valid OAuth token.

---

## Multi-interval polling (ui/api.py _async_fetch)

Twitch polls every 60 s; YouTube polls every 300 s (default). Both share
one `_async_fetch()` call triggered by the same `threading.Timer` loop.

**The cache fix** — without it, YouTube streams vanished every 60 s:

```python
yt_due = time.time() - self._last_youtube_fetch >= yt_interval

if yt_due and (yt_conf.get("api_key") or yt_conf.get("access_token")):
    try:
        youtube_streams = await self._youtube.get_live_streams(youtube_favorites)
        self._last_youtube_fetch = time.time()
        self._last_youtube_streams = youtube_streams      # update cache
    except ValueError as e:
        # Quota exceeded or missing API key — show error, use cache
        youtube_streams = list(self._last_youtube_streams)
    except Exception:
        youtube_streams = list(self._last_youtube_streams)
else:
    # Not yet due — serve last result instead of returning empty list
    youtube_streams = list(self._last_youtube_streams)
```

`_last_youtube_streams: list[dict]` is initialised to `[]` in `__init__`.

---

## Adding a YouTube channel (ui/api.py add_channel)

`_sanitize_channel_name(raw, "youtube")` normalises any of the following inputs
into a canonical form:

| Input | Result |
|-------|--------|
| `https://youtube.com/channel/UCLzonkj0KtpdMxt5hiPWkCQ` | `UCLzonkj0KtpdMxt5hiPWkCQ` |
| `https://youtube.com/watch?v=bDsXOVkppyc` | `v:bDsXOVkppyc` |
| `https://youtube.com/@BOVER` | `@bover` |
| `@BOVER` | `@bover` |
| `BOVER` (plain name) | `@bover` |
| `UCLzonkj0KtpdMxt5hiPWkCQ` (channel ID) | `UCLzonkj0KtpdMxt5hiPWkCQ` |
| `uclzonkj0ktpdmxt5hipwkcq` (lowercase ID) | `uclzonkj0ktpdmxt5hipwkcq` (migration fixes later) |

**Async resolution path** (`@handle` or `v:VIDEO_ID`):
- Calls `get_channel_info()` in a background thread
- Resolves to a UC channel ID + real display name
- Dedup check is case-insensitive: `f["login"].lower() == channel_id.lower()`

**Direct path** (UC channel ID already resolved):
- Writes directly to config
- Also uses case-insensitive dedup

---

## Playback (watch / watch_external)

YouTube live streams play through the **same pipeline as Twitch and Kick**.
The original iframe embed approach was abandoned because YouTube's player
detects WKWebView (pywebview's engine on macOS) and returns **Error 153**
("video player setup error").

```
watch(channel, quality)
  → stream.video_id   (from cached _live_streams)
  → resolve_hls_url(video_id, quality, platform="youtube")
      → streamlink https://www.youtube.com/watch?v/{video_id} {quality} --stream-url
  → onStreamReady({url: hls_url, platform: "youtube"})
      → <video>.src = hls_url  (native AVPlayer on macOS)
```

`core/stream_resolver.py` and `core/launcher.py` both have a `youtube` branch:

```python
if platform == "youtube":
    stream_url = f"https://www.youtube.com/watch?v={channel}"
    # `channel` parameter receives video_id, not channel_id
```

`watch_external()` passes `stream.get("video_id", channel)` to `launch_stream()`
so IINA also resolves from the video URL, not the channel ID.

---

## Thumbnails (get_thumbnail)

YouTube thumbnails are fetched from the `thumbnail_url` field in the stream
dict (maxres → high → medium from `snippet.thumbnails`).

**Critical**: `get_thumbnail` must **not** lowercase the login. YouTube channel
IDs are mixed-case (`UCLzonkj0KtpdMxt5hiPWkCQ`). The JS side uses the exact
`s.login` string as the `data-login` attribute on stream cards and as the
`state.thumbnails` cache key. Lowercasing breaks both the DOM lookup and
the cache:

```python
# CORRECT — preserve original case
result = json.dumps({"login": login, "data": data_url})

# WRONG — breaks YouTube channel IDs
result = json.dumps({"login": login.lower(), "data": data_url})
```

---

## Config migration (app.py _migrate_favorites)

Early versions of the add-channel code lowercased YouTube channel IDs and
stripped hyphens, producing invalid entries like:

```json
{"platform": "youtube", "login": "uclzonkj0ktpdmxt5hipwkcq",
 "display_name": "UCLzonkj0KtpdMxt5hiPWkCQ"}
```

`VALID_CHANNEL_ID = re.compile(r"^UC[\w-]{22}$")` is case-sensitive, so these
entries were silently ignored by `get_live_streams()`.

`_migrate_favorites()` runs on every app start and repairs entries in three phases:

**Phase 1 — restore mangled logins**

Two breakage patterns, both detectable from the preserved `display_name`:

```
(a) login.lower() == display_name.lower()
    → display_name is the proper-case channel ID; restore: login = display_name

(b) display_name matches ^UC[\w-]{22}$ but login does NOT
    → hyphen was stripped; restore: login = display_name
```

**Phase 2 — pick best display_name per channel**

After phase 1, there may be two entries with the same channel ID (a repaired
lowercase one and the original proper-case one). The entry whose `display_name`
is a real human name is preferred over one that just stores the channel ID:

```python
_yt_id_re = re.compile(r"^UC[\w-]{22}$", re.IGNORECASE)
# If existing entry has an ID-like display_name but new entry has a real name → prefer new
```

**Phase 3 — case-insensitive dedup**

The dedup key for YouTube is `(platform, login.lower())`, so
`UCLzonkj0KtpdMxt5hiPWkCQ` and `uclzonkj0ktpdmxt5hipwkcq` merge into one
entry (the best one from phase 2).

`_sanitize_favorite_login` for YouTube **preserves case** (unlike Twitch/Kick
which lowercase):

```python
if platform == "youtube":
    return re.sub(r"[^A-Za-z0-9_-]", "", raw)   # strip invalid chars, keep casing
```

---

## Frontend (ui/index.html)

### Settings panel

Tab id: `settings-panel-youtube`. Key element IDs:

| Element | Purpose |
|---------|---------|
| `yt-api-key` | API key input (password type, toggle with `yt-api-key-eye-btn`) |
| `yt-client-id` | OAuth client ID |
| `yt-client-secret` | OAuth client secret (password type + eye toggle) |
| `yt-login-btn` | Triggers `api.youtube_login(clientId, clientSecret)` |
| `yt-logout-btn` | Triggers `api.youtube_logout()` |
| `yt-import-btn` | Triggers `api.youtube_import_follows()` |
| `yt-test-btn` | Triggers `api.youtube_test_connection()` |
| `yt-test-result` | Shows test / import result text |
| `yt-login-area` | Shown when not authenticated |
| `yt-user-area` | Shown when authenticated (display name + quota remaining) |
| `yt-display-name` | "Logged in as {name}" |
| `yt-quota-display` | "Quota remaining: {n}" |

Settings are saved in `saveSettings()` as flat keys:
`youtube_api_key`, `youtube_client_id`, `youtube_client_secret`.

### Platform tab and grid filtering

```html
<button class="platform-tab" data-platform="youtube">YouTube</button>
```

Clicking sets `state.activePlatformFilter = "youtube"`, which filters both
`renderGrid()` and `renderSidebar()` to show only `s.platform === "youtube"`
streams / favorites.

Platform badge CSS:

```css
.platform-badge.youtube { background: rgba(255, 0, 0, 0.85); }
```

Badge text: `"YT"` for YouTube (vs `"T"` Twitch, `"K"` Kick).

### Adding channels from JS

`addChannel()` auto-detects YouTube when the active filter is "all":

```javascript
if (lower.indexOf('youtube.com/') !== -1 || lower.charAt(0) === '@') {
    choice = { login: val, platform: 'youtube' };
}
```

When a search result is selected, `addChannelDirect(login, platform, displayName)`
passes the resolved channel ID and real display name directly to
`api.add_channel()`.

### Sidebar display names (favoritesMeta)

YouTube channel IDs look like `UCLzonkj0KtpdMxt5hiPWkCQ` — not user-friendly
in the sidebar. `onStreamsUpdate` receives a `favorites_meta` dict built in
Python:

```python
favorites_meta = {
    f["login"]: {
        "display_name": f.get("display_name", f["login"]),
        "platform": f.get("platform", "twitch"),
    }
    for f in get_favorites(self._config)
}
```

`createSidebarItem` uses it:

```javascript
var favMeta = state.favoritesMeta[login] || {};
name.textContent = (stream && stream.display_name)
    || favMeta.display_name
    || login;
```

`favoritesMeta` is also used as a platform fallback in context menus
(`ctxPlat`) and `doBrowser()` for offline channels where there is no live
stream object.

### JS callbacks reference

| Callback | Fired by | Payload |
|----------|---------|---------|
| `window.onYouTubeLoginComplete(data)` | `youtube_login()` | `{platform, display_name, login, youtube_quota_remaining}` |
| `window.onYouTubeLoginError(msg)` | `youtube_login()` | string |
| `window.onYouTubeNeedsCredentials()` | `youtube_login()` | — |
| `window.onYouTubeLogout()` | `youtube_logout()` | — |
| `window.onYouTubeTestResult(result)` | `youtube_test_connection()` | `{ok, message}` |
| `window.onYouTubeImportComplete(count)` | `youtube_import_follows()` | integer |
| `window.onYouTubeImportError(msg)` | `youtube_import_follows()` | string |
| `window.onStreamsUpdate(data)` | `_on_data_fetched()` | includes `favorites_meta` |
| `window.onStreamReady(data)` | `watch()` | `{url: hls_url, platform: "youtube", ...}` |
| `window.onThumbnail(data)` | `get_thumbnail()` | `{login, data: base64_jpeg}` |

---

## Quota Budget Reference

With 10 channels and polling every 5 minutes (288 polls/day):

| Operation | Calls/day | Units/call | Total |
|-----------|-----------|-----------|-------|
| RSS feeds (10 channels) | 288 × 10 | 0 | **0** |
| `videos.list` (≤50 IDs/batch) | 288 | 1 | **288** |
| Channel search (user-initiated) | ~5 | 100 | **500** |
| `channels.list` (add channel) | ~2 | 1–2 | **4** |
| `get_current_user` (on login) | 1 | 1 | **1** |
| **Total** | | | **~793 / 10,000** |

With 50 channels: still ~1.3k units/day — well within budget. The expensive
operation is search (100 units). A single day of active searching (10 searches)
costs as much as 3.4 days of normal polling.

---

## Known Constraints and Gotchas

**`VALID_CHANNEL_ID` is case-sensitive.** `re.compile(r"^UC[\w-]{22}$")` (no
`re.IGNORECASE`). Lowercase channel IDs silently pass the dedup check but are
then silently dropped by `get_live_streams()`. The migration fixes this, and
the add-channel dedup now uses `login.lower()` to prevent new lowercase entries.

**`video_id` must be used for playback, not `channel_id`.** Streamlink needs
the video URL (`watch?v=`), not the channel page. `watch()` reads
`stream.get("video_id", "")` from the cached live stream object. If the
polling cache is cold (app just started, YouTube not yet polled), `video_id`
will be empty and the watch will fail with "No live video found".

**RSS feeds return at most 15 recent videos.** If a channel has posted 15+
videos since going live, the live video ID might not appear in the RSS feed.
Extremely prolific channels (live + many regular uploads) could be missed.

**`concurrentViewers` is often absent.** YouTube's API propagates this field
with a delay and omits it entirely for some streams. The viewer count will
display as 0 for new streams or streams with hidden counts. Do not use it as a
liveness signal.

**Search costs 100 units.** With the 400 ms JS debounce, a user typing a
10-character query triggers ~3 search calls = 300 units. Avoid searching on
every keystroke; the debounce is important.

**Token refresh happens inside `_get_token_lock()`.** Never call
`_ensure_token()` while holding the lock from another coroutine on the same
loop — deadlock. Currently safe because all token-needing calls go through
`_yt_get()`, which is the only entry point.

**`resolve_stream_url()` in `youtube.py` is now unused.** It was the iframe
embed path (`playback_type: "youtube_embed"`). The method remains in the class
but is not called by `ui/api.py`. The active path is `core/stream_resolver.py`
→ `streamlink`.

**Thumbnail login must not be lowercased.** See [Thumbnails](#thumbnails-get_thumbnail).
The `.lower()` call was removed from `get_thumbnail()` specifically because
YouTube channel IDs are mixed-case identifiers, not usernames.
