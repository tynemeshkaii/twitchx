# Changelog

## v0.1.0-beta — 2026-05

### Features

- **Multi-platform live grid** — Twitch, Kick, and YouTube favorites in a unified sidebar. Live channels update automatically on a configurable interval (30s / 60s / 120s).
- **Native video playback** — AVPlayer-based HLS player embedded via pywebview. Supports quality selection (best/high/medium/low/audio), volume, seek for VODs, PiP, and fullscreen.
- **External player launch** — Open any stream in IINA or mpv with a single click.
- **Stream recording** — Record to disk via streamlink; configurable output directory.
- **Chat integration** — Twitch (IRC over WebSocket), Kick, and YouTube live chat with third-party emotes (7TV, BTTV, FFZ).
- **Multistream** — Watch up to 4 streams simultaneously in a resizable grid with audio focus and per-slot chat.
- **Browse & search** — Browse Twitch categories and top games; search channels across platforms.
- **Channel profiles** — Per-channel overlay with bio, stream history, and quick-follow.
- **Command palette** — ⌘K universal search across channels and actions.
- **Watch statistics** — Per-channel and total session tracking stored in SQLite; visible in Settings → Statistics.
- **OAuth login** — Twitch and YouTube OAuth 2.0 PKCE flows; Kick session auth. Bundled credentials allow login without custom app registration.
- **Accent theming** — 6 accent colors configurable in Settings.
- **Keyboard shortcuts** — Fully rebindable. Defaults: ⌘K palette, M mute, F fullscreen, R refresh, C toggle chat, P PiP, Esc close.
- **Low-latency Twitch mode** — Optional HLS low-latency flag via streamlink ≥6.x.

### Known Limitations

- **macOS only** — Requires macOS 12+. AVPlayer and pywebview/WebKit are platform-specific.
- **streamlink required** — Must be installed and on `$PATH` (or configured path) for stream playback. Minimum version: 6.x for low-latency mode.
- **IINA optional** — Only needed if using IINA as external player.
- **YouTube quota** — Uses YouTube Data API v3 quota (10,000 units/day on free tier). Heavy usage of Browse may exhaust the daily quota.
- **Kick auth instability** — Kick does not have an official public API; the integration may break on Kick-side changes.
- **No sandboxed distribution** — The beta is unsigned. macOS Gatekeeper will block launch from Finder unless right-click → Open is used, or the app is explicitly trusted in System Settings → Privacy & Security.
- **No auto-update** — Manual update by pulling the repo and restarting.

### Prerequisites

| Dependency | Version | Required |
|-----------|---------|----------|
| Python | ≥ 3.11 | Yes |
| [streamlink](https://streamlink.github.io/) | ≥ 6.x | Yes |
| [IINA](https://iina.io/) | Any | Optional |
| [mpv](https://mpv.io/) | Any | Optional |
| [uv](https://docs.astral.sh/uv/) | Any | For dev/install |

Install streamlink: `brew install streamlink`
