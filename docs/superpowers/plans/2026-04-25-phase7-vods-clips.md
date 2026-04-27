# Phase 7: VODs & Clips Implementation Plan

**Goal:** Fill the `VODs` and `Clips` tabs in the existing channel profile view with real data and playback actions, while staying inside the current TwitchX architecture: Python background threads, async platform clients, pywebview callbacks, and a single self-contained `ui/index.html`.

**Important scope correction:** the user referenced `docs/superpowers/specs/2026-03-28-favorites-sidebar-sections-design.md`, but `Phase 7: VODs & Clips` is actually specified in `docs/superpowers/specs/2026-03-28-multiplatform-streaming-client-design.md`. The sidebar spec is still useful as a style reference because it reinforces two repo-wide constraints that matter here as well: keep the work in `ui/index.html` on the frontend and continue using safe DOM creation only.

**Platform stance:**
- **Twitch:** implement with official Helix `videos` and `clips`.
- **YouTube:** implement with `channels.list` -> uploads playlist -> `playlistItems.list` -> `videos.list`.
- **Kick:** degrade gracefully. The older multiplatform spec mentions unofficial endpoints, but current repo guidance explicitly avoids unofficial Kick media endpoints because of Cloudflare breakage and stability risk.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `core/platforms/twitch.py` | Official Twitch VOD/clip fetchers + duration normalization |
| Modify | `core/platforms/youtube.py` | Uploads-playlist media fetchers + short-video clip heuristic |
| Modify | `core/stream_resolver.py` | Allow direct media URLs, not only live channel URLs |
| Modify | `ui/api.py` | Channel-media bridge + generic media playback + browser open helper |
| Modify | `ui/index.html` | VOD/clip panels, CSS, state, lazy loading, rendering, playback actions |
| Modify | `tests/platforms/test_twitch.py` | Twitch VOD/clip normalization tests |
| Modify | `tests/platforms/test_youtube.py` | YouTube VOD/clip fetch tests |
| Modify | `tests/test_channel_api.py` | Bridge payload tests for channel media |
| Modify | `tests/test_stream_resolver.py` | Direct URL resolver coverage |

---

## Task 1: Platform Media Fetchers

- Add `TwitchClient.get_channel_vods(login, limit=12)`:
  - Resolve broadcaster via `/users`.
  - Fetch `/videos?user_id=...&type=archive`.
  - Normalize to a shared media shape: `id`, `title`, `url`, `thumbnail_url`, `published_at`, `duration_seconds`, `views`, `platform`, `kind`.

- Add `TwitchClient.get_channel_clips(login, limit=12)`:
  - Resolve broadcaster via `/users`.
  - Fetch `/clips?broadcaster_id=...`.
  - Normalize to the same shape.

- Add `YouTubeClient.get_channel_vods(channel_id_or_handle, limit=12)`:
  - Resolve uploads playlist from `channels.list(part=contentDetails,snippet)`.
  - Read recent uploads via `playlistItems.list`.
  - Hydrate metadata via `videos.list(part=snippet,contentDetails,status,liveStreamingDetails)`.
  - Exclude live/upcoming/private entries.

- Add `YouTubeClient.get_channel_clips(channel_id_or_handle, limit=12)`:
  - Reuse uploads pipeline.
  - Treat short-form uploads as clips using a conservative duration heuristic.
  - Preserve reverse-chronological order.

- Kick returns an unsupported state at the bridge layer instead of inventing unofficial HTTP calls.

## Task 2: Bridge and Playback Plumbing

- Add a public `TwitchXApi.get_channel_media(login, platform, tab)` bridge:
  - Emits `window.onChannelMedia(payload)`.
  - Payload contains `login`, `platform`, `tab`, `items`, `supported`, `error`, `message`.
  - All work runs in the existing background-thread + per-thread event-loop pattern.

- Add `TwitchXApi.watch_media(url, quality, platform, channel, title, with_chat=False)`:
  - Reuse `resolve_hls_url`.
  - Emit `window.onStreamReady(...)` with `has_chat: false`.
  - Reuse the existing player view without starting chat.

- Add `TwitchXApi.open_url(url)` for “open original” actions from media cards.

## Task 3: Channel View UI

- Replace stub tab bodies with real containers:
  - loading
  - empty
  - unsupported/error message
  - content list/grid

- Add JS state for per-tab fetch lifecycle:
  - `idle` -> `loading` -> `ready`
  - reset on every `showChannelView(...)`
  - cache only for the currently opened channel view

- Trigger lazy fetch when the user opens `VODs` or `Clips`.
- If the user switches channels before the async response returns, ignore stale payloads.
- Continue using `createElement`, `textContent`, and `replaceChildren` only.

## Task 4: UX Details

- `VODs` render as compact rows with thumbnail, title, date, duration, and views.
- `Clips` render as a preview grid with stronger thumbnail emphasis.
- Actions:
  - `Play` -> resolves direct media URL into the existing player view
  - `Open` -> opens the platform URL in the system browser

- Player reuse rules:
  - media playback hides the channel view before starting
  - chat toggle/panel stay hidden for VOD/clip playback
  - live playback keeps current behavior unchanged

## Task 5: Verification

- Add focused unit tests for:
  - Twitch media normalization
  - YouTube uploads/short-video filtering
  - bridge payload emission
  - direct URL resolution in `stream_resolver`

- Run targeted pytest slices first, then the combined relevant suite.

---

## Implementation Notes

- The “YouTube clips” bucket is necessarily heuristic because the current app has no dedicated cross-channel YouTube clips API surface comparable to Twitch Helix clips.
- We prefer a truthful unsupported state for Kick over brittle unofficial scraping, which matches the repository’s current operational constraints better than the older exploratory spec.
