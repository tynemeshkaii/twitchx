# Multi-Platform Streaming Client Design

**Date:** 2026-03-28
**Status:** Approved
**Approach:** Phased evolutionary refactor (no frameworks, vanilla JS + pywebview)

## Overview

Expand TwitchX from a Twitch-only client into a multi-platform streaming client supporting Twitch, Kick, and YouTube. Core principles: keep vanilla JS + pywebview stack, no new frameworks, phased delivery where every phase produces a working release.

## Supported Platforms

| Platform | API | Auth | Chat Protocol | Playback | Limitations |
|----------|-----|------|--------------|----------|-------------|
| Twitch | Helix REST | OAuth 2.0 (Authorization Code) | IRC WebSocket (`irc-ws.chat.twitch.tv`) | streamlink -> HLS -> `<video>` | Generous: 800 req/min |
| Kick | Official REST (`api.kick.com`) | OAuth 2.1 + PKCE (`id.kick.com`) | Pusher WebSocket (read) + REST (send) | streamlink -> HLS -> `<video>` | No follow/unfollow API, no VODs/clips in official API, Cloudflare on unofficial endpoints |
| YouTube | Data API v3 | Google OAuth 2.0 (loopback redirect) | HTTP polling (`liveChatMessages.list`) | Embedded iframe only (ToS requirement) | 10,000 quota units/day, `search.list` = 100 units, no game directory, no custom playback |

## Section 1: Platform Abstraction Layer

### Abstract Contract

```python
# core/platform.py

class PlatformClient(ABC):
    platform_id: str          # "twitch", "kick", "youtube"
    platform_name: str        # "Twitch", "Kick", "YouTube"

    # --- Auth ---
    async def get_auth_url(self) -> str
    async def exchange_code(self, code: str) -> TokenData
    async def refresh_token(self) -> TokenData
    async def get_current_user(self) -> UserInfo

    # --- Streams ---
    async def get_live_streams(self, channel_ids: list[str]) -> list[StreamInfo]
    async def get_top_streams(self, category: str | None, limit: int) -> list[StreamInfo]
    async def search_channels(self, query: str) -> list[ChannelInfo]

    # --- Channel ---
    async def get_channel_info(self, channel_id: str) -> ChannelInfo
    async def get_followed_channels(self, user_id: str) -> list[str]

    # --- Social ---
    async def follow(self, channel_id: str) -> bool
    async def unfollow(self, channel_id: str) -> bool

    # --- Browse ---
    async def get_categories(self, query: str | None) -> list[CategoryInfo]

    # --- Playback ---
    async def resolve_stream_url(self, channel_id: str, quality: str) -> PlaybackInfo
```

### Unified Data Models

```python
@dataclass
class StreamInfo:
    platform: str              # "twitch" / "kick" / "youtube"
    channel_id: str
    channel_login: str
    display_name: str
    title: str
    category: str
    viewers: int
    started_at: str            # ISO 8601
    thumbnail_url: str
    avatar_url: str

@dataclass
class PlaybackInfo:
    url: str                   # HLS URL or video ID
    playback_type: str         # "hls" | "youtube_embed"
    quality: str

@dataclass
class ChannelInfo:
    platform: str
    channel_id: str
    login: str
    display_name: str
    bio: str
    avatar_url: str
    followers: int
    is_live: bool
    can_follow_via_api: bool

@dataclass
class CategoryInfo:
    platform: str
    category_id: str
    name: str
    box_art_url: str
    viewers: int               # total viewers in category

@dataclass
class TokenData:
    access_token: str
    refresh_token: str
    expires_at: float
    token_type: str

@dataclass
class UserInfo:
    platform: str
    user_id: str
    login: str
    display_name: str
    avatar_url: str
```

### Implementation Matrix

| Method | Twitch | Kick | YouTube |
|--------|--------|------|---------|
| `get_live_streams` | Helix `streams` | `/public/v1/livestreams` | `videos.list` on known IDs (1 unit) |
| `get_top_streams` | Helix `streams` | `/public/v1/livestreams` sort | `search.list` (100 units, cached 10 min) |
| `search_channels` | Helix `search/channels` | `/public/v1/channels` by slug | `search.list type=channel` (100 units) |
| `get_followed_channels` | Helix API | Local favorites only | `subscriptions.list` (1 unit) |
| `follow/unfollow` | API supported | Local only | API supported (50 units each) |
| `resolve_stream_url` | streamlink -> HLS | streamlink -> HLS | video ID -> iframe embed |
| `get_categories` | Helix `games/top` | `/public/v2/categories` | `videoCategories.list` (limited) |

### YouTube Quota Strategy

Daily budget of 10,000 units:
- Polling subscriptions: ~200 units (every 5 min x 1 unit x ~7 pages)
- Live status check: ~300 units (every 5 min x 1 unit x batches of 50)
- Browse/search: ~2,000 units (20 user searches x 100 units)
- Chat: ~5,000 units (1 stream x 5 units x ~1000 polls)
- Reserve: ~2,500 units

Rules:
- Never use `search.list` for polling (100 units/call)
- YouTube polling interval: minimum 5 minutes (vs 60s for Twitch/Kick)
- Cache browse/search results for 10 minutes
- QuotaTracker persists daily usage in config, auto-resets daily
- UI warning when quota > 80%

### Two Playback Modes

- **HLS mode** (Twitch, Kick): streamlink resolves URL -> `<video src="...m3u8">`
- **Embed mode** (YouTube): `<iframe src="youtube.com/embed/VIDEO_ID">` in `#player-view`

JS player checks `playback_type` from `PlaybackInfo` and renders the appropriate element.

## Section 2: Chat System

### Abstract Contract

```python
# core/chat.py

class ChatClient(ABC):
    platform: str

    async def connect(self, channel_id: str, token: str | None) -> None
    async def disconnect(self) -> None
    async def send_message(self, text: str) -> bool
    def on_message(self, callback: Callable[[ChatMessage], None]) -> None
    def on_status(self, callback: Callable[[ChatStatus], None]) -> None

@dataclass
class ChatMessage:
    platform: str
    author: str
    author_display: str
    author_color: str | None
    avatar_url: str | None
    text: str
    timestamp: str
    badges: list[Badge]
    emotes: list[Emote]
    is_system: bool
    message_type: str          # "text" | "super_chat" | "sub" | "raid" | "donation"
    raw: dict

@dataclass
class Badge:
    name: str
    icon_url: str

@dataclass
class Emote:
    code: str
    url: str
    start: int
    end: int

@dataclass
class ChatStatus:
    connected: bool
    platform: str
    channel_id: str
    error: str | None          # None if connected OK
```

### Platform Implementations

**Twitch IRC WebSocket:**
- WSS connection to `irc-ws.chat.twitch.tv:443`
- Auth: `PASS oauth:<token>`, `NICK <username>` (anonymous: `NICK justinfan12345`)
- Subscribe: `JOIN #<channel>`
- IRCv3 tags provide badges, emote positions, nick color
- Rate limit: 20 msg/30s (normal), 100/30s (mod)

**Kick Pusher WebSocket + REST:**
- WSS to `ws-us2.pusher.com` (app key: `eb1d5f283081a78b932c`)
- Subscribe: `pusher:subscribe` -> channel `chatrooms.<chatroom_id>.v2`
- Messages: `App\Events\ChatMessageSentEvent` (double-encoded JSON)
- Send: `POST /public/v1/chat` (OAuth scope `chat:write`)
- chatroom_id obtained from channel info

**YouTube HTTP Polling:**
- `GET liveChatMessages.list?liveChatId=<id>&pageToken=<token>`
- liveChatId from `videos.list` -> `liveStreamingDetails.activeLiveChatId`
- Server-dictated polling interval via `pollingIntervalMillis` (5-10s)
- Send: `POST liveChatMessages.insert` (50 units, scope `youtube.force-ssl`)
- ~5 quota units per poll

### Threading Model

Each chat client runs in its own thread:
- Twitch/Kick: `threading.Thread` with `asyncio.new_event_loop()` for WebSocket
- YouTube: `threading.Timer` polling loop
- Channel switch: `disconnect()` old -> `connect()` new
- Window closing: `_shutdown` Event stops all chat threads

### JS Rendering

- Unified `ChatMessage` format rendered identically across platforms
- Emotes: platform URLs -> `<img>` replacement during render
- Badges: `Badge.icon_url` -> `<img>` before nick
- Nick color: Twitch/Kick provide it, YouTube -> hash-based generation
- Special messages: Super Chat, subs, raids -> distinct styling by `message_type`
- Buffer: max 500 messages in DOM, oldest removed from top
- Auto-scroll: scrolls down unless user has scrolled up manually

### Data Flow

```
Python ChatClient (background thread)
  -> on_message callback
  -> TwitchXApi._eval_js("window.onChatMessage({json})")
  -> JS renders message in chat panel

JS input submit
  -> pywebview.api.send_chat(text)
  -> TwitchXApi dispatches to active ChatClient.send_message()
```

## Section 3: Navigation & UI Structure

### View System

Simple show/hide of `<div>` sections (no router, no framework):

```javascript
const views = ['streams', 'player', 'browse', 'channel', 'vods', 'multistream'];

function navigateTo(viewName, params = {}) {
    views.forEach(v => {
        document.getElementById(v + '-view').classList.toggle('hidden', v !== viewName);
    });
    state.currentView = viewName;
    state.viewParams = params;
    if (viewName === 'browse') initBrowseView(params);
    if (viewName === 'channel') initChannelView(params);
}
```

### Views

**1. streams-view** (existing, extended):
- Stream cards show platform badge icon
- Filter by platform: All / Twitch / Kick / YouTube
- Cross-platform sorting

**2. player-view** (existing, extended):
- Video + Chat side-by-side (resizable split)
- Chat panel toggleable
- Channel header: avatar, name, game, viewers, uptime, fullscreen, PiP
- Controls: quality, stop, IINA, mute, volume, channel info
- YouTube streams: `<iframe>` instead of `<video>`

**3. browse-view** (new):
- Platform filter tabs
- Category cards grid (aggregated across platforms)
- Click category -> top streams grid with platform badges
- YouTube results cached 10 minutes

**4. channel-view** (new):
- Banner, avatar, display name, bio, follower count
- Follow button (API where supported, local otherwise)
- Tabs: Live Now / VODs / Clips

**5. vods-view** (new):
- Reuses player-view layout without chat
- For VOD and clip playback

**6. multistream-view** (new):
- 2-4 streams in grid layout
- One stream with audio, others muted
- Click to switch audio focus
- Switchable chat (one stream at a time)
- Cross-platform mixing supported

### Sidebar Structure

```
[T] [K] [Y] [ALL]        <- Platform filter tabs
Profile area              <- Per-platform login/logout
Search input              <- Cross-platform search
[Browse]                  <- Link to browse-view
ONLINE (N)                <- Live favorites (platform badge per channel)
OFFLINE (N)               <- Offline favorites
```

Platform filter affects both sidebar and main content simultaneously.

## Section 4: Storage & Configuration

### Config Structure (v2)

```json
{
  "platforms": {
    "twitch": {
      "enabled": true,
      "client_id": "",
      "client_secret": "",
      "access_token": "",
      "refresh_token": "",
      "token_expires_at": 0,
      "token_type": "app",
      "user_id": "",
      "user_login": "",
      "user_display_name": ""
    },
    "kick": {
      "enabled": true,
      "client_id": "",
      "client_secret": "",
      "access_token": "",
      "refresh_token": "",
      "token_expires_at": 0,
      "pkce_verifier": "",
      "user_id": "",
      "user_login": "",
      "user_display_name": ""
    },
    "youtube": {
      "enabled": true,
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
  "favorites": [
    {"platform": "twitch", "login": "xqc", "display_name": "xQc"}
  ],
  "settings": {
    "quality": "best",
    "refresh_interval": 60,
    "youtube_refresh_interval": 300,
    "streamlink_path": "streamlink",
    "iina_path": "/Applications/IINA.app/Contents/MacOS/iina-cli",
    "notifications_enabled": true,
    "player_height": 360,
    "chat_visible": true,
    "chat_width": 340,
    "active_platform_filter": "all",
    "pip_enabled": false
  }
}
```

### Migration (v1 -> v2)

Automatic on first load. Moves flat Twitch credentials into `platforms.twitch`, converts `favorites` from `["xqc"]` to `[{"platform": "twitch", "login": "xqc", "display_name": "xqc"}]`. No data loss.

### Avatar Cache Structure

```
~/.config/twitchx/
├── config.json
├── avatars/
│   ├── twitch/
│   ├── kick/
│   └── youtube/
└── cache/
    └── browse_categories.json  (10 min TTL)
```

Avatars separated by platform to avoid name collisions.

### Settings Modal

Tabbed interface: General / Twitch / Kick / YouTube. Each platform tab has its own credentials, login button, and connection test. YouTube tab additionally shows daily quota usage.

## Section 5: Project File Structure

```
streamdeck/
├── app.py
├── main.py
├── core/
│   ├── platform.py                 # ABC: PlatformClient + data models
│   ├── chat.py                     # ABC: ChatClient + ChatMessage
│   ├── storage.py                  # Multi-platform config + migration
│   ├── stream_resolver.py          # streamlink HLS (Twitch + Kick)
│   ├── launcher.py                 # IINA fallback
│   ├── utils.py
│   ├── oauth_server.py
│   ├── platforms/
│   │   ├── twitch.py               # TwitchClient(PlatformClient)
│   │   ├── kick.py                 # KickClient(PlatformClient)
│   │   └── youtube.py              # YouTubeClient(PlatformClient) + QuotaTracker
│   └── chats/
│       ├── twitch_chat.py          # IRC WebSocket
│       ├── kick_chat.py            # Pusher WebSocket
│       └── youtube_chat.py         # HTTP polling
├── ui/
│   ├── api.py                      # TwitchXApi bridge (extended)
│   ├── index.html                  # Full UI with all views
│   ├── native_player.py            # Legacy (retained)
│   └── theme.py
└── tests/
    ├── test_app.py
    ├── test_storage.py
    ├── test_stream_resolver.py
    ├── test_launcher.py
    ├── test_native_player.py
    ├── platforms/
    │   ├── test_twitch.py
    │   ├── test_kick.py
    │   └── test_youtube.py
    └── chats/
        ├── test_twitch_chat.py
        ├── test_kick_chat.py
        └── test_youtube_chat.py
```

## Section 6: Implementation Phases

Each phase produces a working release.

### Phase 0: Architectural Refactor (Foundation)

No user-visible changes. Internal reorganization.

- Create `core/platform.py` with ABC and dataclasses
- Create `core/chat.py` with ABC
- Move `core/twitch.py` -> `core/platforms/twitch.py`, adapt to PlatformClient
- Refactor `core/storage.py`: multi-platform config + migration
- Refactor `ui/api.py`: platform registry instead of direct TwitchClient calls
- All existing tests must pass
- App works identically to before

### Phase 1: Kick Platform

First real multi-platform support. Kick chosen first because: official API, no quota limits, OAuth 2.1 + PKCE, streamlink support, HLS playback (same `<video>` as Twitch).

- `core/platforms/kick.py` — KickClient(PlatformClient)
- Kick OAuth flow (PKCE) via `oauth_server.py`
- Platform tabs in sidebar (All / Twitch / Kick)
- Platform badge on stream cards
- Settings modal: Kick tab
- Favorites as objects with platform field
- Tests for KickClient

### Phase 2: Twitch Chat (Native)

Establishes the chat pattern for other platforms.

- `core/chats/twitch_chat.py` — IRC WebSocket client
- Chat panel in player-view (right side, resizable)
- Rendering: badges, emotes as `<img>`, nick colors
- Message sending (authenticated)
- Anonymous reading (no login required)
- JS: `window.onChatMessage()`, auto-scroll, 500-message buffer

### Phase 3: Kick Chat

- `core/chats/kick_chat.py` — Pusher WebSocket + REST send
- Reuses chat panel from Phase 2
- chatroom_id from channel info

### Phase 4: YouTube Platform

Most complex platform due to quota and playback restrictions.

- `core/platforms/youtube.py` — YouTubeClient(PlatformClient) + QuotaTracker
- Google OAuth flow (loopback redirect)
- Iframe embed instead of `<video>` for YouTube streams
- Quota-aware polling (5 min interval)
- YouTube quota indicator in settings
- Platform tabs: All / Twitch / Kick / YouTube
- `core/chats/youtube_chat.py` — HTTP polling chat

### Phase 5: Browse

- browse-view: categories from all platforms
- Aggregate identical categories across platforms
- Top streams by category (cross-platform)
- Category caching (10 min)

### Phase 6: Channel Profile

- channel-view: bio, avatar, followers, follow button
- API follow/unfollow (Twitch, YouTube) + local follow (Kick)
- Tabs: Live / VODs / Clips

### Phase 7: VODs & Clips

- Twitch: Helix API for videos + clips
- Kick: unofficial endpoints (with fallback on 403)
- YouTube: `playlistItems.list` on uploads playlist (1 unit)
- VOD player (reuses player-view without chat)
- Clips: short videos, grid with previews

### Phase 8: Multi-stream

- multistream-view: 2-4 streams in grid
- One with audio, others muted
- Click to switch audio focus
- Switchable chat between streams
- Cross-platform mixing

### Phase 9: Picture-in-Picture + Hotkeys

- PiP: native macOS PiP via `video.requestPictureInPicture()` (HLS) or Webkit PiP
- Extended hotkeys: volume, mute, next/prev stream, toggle chat, toggle PiP
- Configurable keyboard shortcuts in settings

### Phase 10: Import Follows + Watch Statistics

- Import follows: on platform login, offer to import all follows into favorites
- Watch statistics: local SQLite database (watch time, which streams, period)
- Simple dashboard in settings

### Phase Dependencies

```
Phase 0 (refactor) --- mandatory foundation
  |
  +-- Phase 1 (Kick) --- needs Phase 0
  |     |
  |     +-- Phase 3 (Kick Chat) --- needs Phase 2
  |
  +-- Phase 2 (Twitch Chat) --- needs Phase 0
  |
  +-- Phase 4 (YouTube) --- needs Phase 0
  |
  +-- Phase 5 (Browse) --- needs Phases 1 + 4
  |
  +-- Phase 6 (Channel Profile) --- needs Phases 1 + 4
  |     |
  |     +-- Phase 7 (VODs/Clips) --- needs Phase 6
  |
  +-- Phase 8 (Multi-stream) --- needs Phase 2
  |
  +-- Phase 9 (PiP + hotkeys) --- needs Phase 2
  |
  +-- Phase 10 (Import + Stats) --- needs Phases 1 + 4
```

Phases 1, 2, and 4 can be done in any order after Phase 0.

## Additional Features Identified

All included in the phases above:
1. VOD / past broadcast viewing (Phase 7)
2. Clips browsing (Phase 7)
3. Multi-stream 2-4 simultaneous (Phase 8)
4. Picture-in-Picture (Phase 9)
5. Extended hotkeys (Phase 9)
6. Import follows from platform (Phase 10)
7. Watch statistics (Phase 10)

## Known Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| YouTube 10k quota/day | Limited polling, expensive search | Quota-aware strategy, 5-min intervals, aggressive caching |
| YouTube ToS prohibits custom playback | Cannot use streamlink for YouTube | Iframe embed only for YouTube |
| Kick Cloudflare blocks unofficial endpoints | No VODs/clips, no followed channels via API | Use official API only, wait for Kick to expand |
| Kick no follow/unfollow API | Cannot follow via Kick API | Local favorites only for Kick |
| streamlink Kick plugin Cloudflare issues | Playback may fail | Fallback handling, retry with cached token |
| YouTube no game directory | Cannot browse by game like Twitch/Kick | Text search approximation, category ID 20 (Gaming) |
| YouTube chat polling cost | ~5 units per poll, limits chat duration | Respect `pollingIntervalMillis`, budget tracking |
