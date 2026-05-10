# TwitchX

<p align="center">
  <img src="https://img.shields.io/badge/platform-macOS-000000?logo=apple&style=for-the-badge" alt="macOS">
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?logo=python&style=for-the-badge" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/tests-pytest-brightgreen?style=for-the-badge" alt="Tests">
  <img src="https://img.shields.io/badge/license-MIT-blue?style=for-the-badge" alt="License">
</p>

<p align="center">
  <b>A native-feeling multi-platform live streaming client for macOS.</b><br>
  Watch Twitch, Kick, and YouTube streams in a single window with native AVPlayer playback, advanced chat, and multistream support.
</p>

---

## Features

### Multi-Platform Support
- **Twitch** — full OAuth integration, follows import, live chat with mod tools
- **Kick** — browse and watch streams with native chat
- **YouTube** — live streams and VODs via YouTube API
- **Unified sidebar** — all your followed channels across platforms in one place

### Native Video Playback
- **AVPlayer first** — uses native macOS media framework for optimal performance
- **Streamlink-powered** — HLS stream resolution via `streamlink` with quality selection
- **Low-latency HLS** — optional `--twitch-low-latency` mode for Twitch
- **External players** — fallback to IINA or mpv if preferred
- **VOD support** — watch past broadcasts and clips with time display

### Advanced Chat
- **Real-time chat** — WebSocket-based for Twitch, Pusher for Kick, polling for YouTube
- **Third-party emotes** — BTTV, FFZ, and 7TV emote support with disk cache
- **Emote picker** — searchable grid with auto-insertion
- **Filters & anti-spam** — subscriber-only, moderator-only, block list, and spam detection
- **Mention highlighting** — your username highlighted in messages
- **User list** — Twitch channel viewer list via `twitch.tv/membership`
- **Moderation tools** — emote-only and slow mode toggles (Twitch broadcaster only)
- **Chat log export** — download logs as JSON or TXT

### Multistream
- Watch up to **4 streams simultaneously** in a grid layout
- Independent audio controls per slot
- Focus audio or chat on any slot
- PiP (Picture-in-Picture) support per stream

### Stream Recording
- One-click recording of current stream
- Saves to `~/Movies/TwitchX/` (configurable)
- Uses streamlink for lossless `.ts` capture
- Recording indicator in player bar

### Watch Statistics
- Automatic session tracking in local SQLite database
- Daily summaries and top channels
- Statistics dashboard in Settings
- Data stays local — complete privacy

### Player & UI
- **Gentle reset** — crossfade video swap to recover from stalls without dropping fullscreen/PiP
- **Health monitors** — automatic recovery from frozen video, buffer overflow, and FPS drops
- **Stats overlay** — real-time latency, buffer, dropped frames, and resolution
- **Picture-in-Picture** — native WebKit PiP with safe enter/exit
- **Fullscreen** — double-click or hotkey, with proper PiP coordination
- **Keyboard shortcuts** — customizable hotkeys for all actions
- **Breadcrumb navigation** — Following → Browse → Category flow
- **Dark theme** — native macOS aesthetic

---

## Screenshots

> _Screenshots will be added here. The app features a clean dark sidebar with online/offline channel lists, a central player view with chat panel, browse view with game categories, and a multistream grid layout._

---

## Requirements

- macOS 12+ (Monterey or later)
- Python 3.11+
- [streamlink](https://streamlink.github.io/) — for HLS stream resolution
- [pywebview](https://pywebview.flowrl.com/) dependencies (WebKit is built-in)

Optional:
- [IINA](https://iina.io/) or [mpv](https://mpv.io/) — for external player fallback

---

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/yourusername/twitchx.git
cd twitchx

# Create virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Or use uv (recommended)
uv sync

# Run the app
make run
```

### First Launch

1. Open **Settings** (gear icon or `Cmd + ,`)
2. Connect your accounts:
   - **Twitch** — OAuth login (auto-imports your follows)
   - **YouTube** — enter YouTube Data API key
   - **Kick** — optional, works without auth for browsing
3. Your followed channels will appear in the sidebar

---

## Usage

| Action | Shortcut |
|--------|----------|
| Focus search | `Cmd + K` |
| Toggle player fullscreen | `F` |
| Toggle Picture-in-Picture | `P` |
| Toggle chat | `C` |
| Close player / view | `Esc` |
| Send chat message | `Enter` |

All shortcuts are customizable in Settings → Keyboard.

### Watch a Stream
- Click any **live** channel in the sidebar
- Or search and click from Browse view
- Double-click video for fullscreen
- Click the **Record** button to save the stream

### Multistream
- Click the **multistream button** in toolbar
- Add slots by searching for channels
- Click the **speaker icon** on a slot to focus its audio
- Click the **chat icon** to view that slot's chat

---

## Development

```bash
# Run with debug logging (httpx)
make debug

# Lint & type check
make lint        # ruff + pyright

# Format code
make fmt         # ruff format

# Run tests
make test        # pytest -v
make check       # lint + test

# Coverage
make cov         # terminal report
make cov-html    # open htmlcov/index.html
```

### Project Structure

```
twitchx/
├── main.py                 # Entry point
├── app.py                  # TwitchXApp (pywebview window)
├── core/
│   ├── platforms/          # TwitchClient, KickClient, YouTubeClient
│   ├── chats/              # Chat clients (WebSocket / polling)
│   ├── third_party_emotes.py  # BTTV/FFZ/7TV fetcher
│   ├── stream_resolver.py  # HLS URL resolution via streamlink
│   ├── launcher.py         # External player launch (IINA/mpv)
│   ├── recorder.py         # Stream recording manager
│   ├── watch_stats.py      # SQLite watch statistics
│   ├── storage.py          # Config v2 + migrations
│   └── constants.py        # TTL, OAuth ports, defaults
├── ui/
│   ├── index.html          # App shell
│   ├── css/                # 6 CSS modules (tokens, layout, player...)
│   ├── js/                 # 14 JS modules (IIFE + TwitchX namespace)
│   └── api/                # Python↔JS bridge (7 components)
└── tests/                  # Pytest suite with fixtures
```

### Architecture

```
main.py → app.py (TwitchXApp)
              ↓
        TwitchXApi  ←———  pywebview.api
              ↓                  ↑
     threading.Thread      window.evaluate_js()
              ↓
     asyncio.new_event_loop()
              ↓
         httpx.AsyncClient  →  Twitch / Kick / YouTube APIs
```

All network I/O runs in background threads with isolated `asyncio` event loops. The frontend is vanilla JS (IIFE modules) communicating with Python via `pywebview` bridge. Video is rendered via native `<video>` element backed by WebKit's AVPlayer integration.

---

## Testing

```bash
# Run all tests
.venv/bin/python -m pytest tests/ -v

# Run specific file
.venv/bin/python -m pytest tests/test_app.py -v

# With coverage
.venv/bin/python -m pytest tests/ --cov=core --cov=ui
```

We use `pytest` with shared fixtures for temporary config directories, mocked platform clients, and eval-js capture. See `tests/conftest.py` for available fixtures.

---

## Why TwitchX?

| | TwitchX | Browser | Official Apps |
|---|---|---|---|
| **Multi-platform** | Twitch + Kick + YouTube in one window | Separate tabs | Separate apps |
| **Native playback** | AVPlayer (battery efficient) | WASM/JS player | Native |
| **Multistream** | Built-in 4-slot grid | Extensions only | Not available |
| **Chat features** | BTTV/FFZ/7TV, filters, mod tools | Extensions | Limited |
| **Resource usage** | ~150MB | 500MB+ per tab | ~200MB each |
| **macOS integration** | Native PiP, fullscreen, shortcuts | Limited | Limited |

---

## Contributing

Contributions are welcome! Please ensure:

1. `make check` passes (lint + tests)
2. New features include tests
3. AGENTS.md is updated if architecture changes
4. Follow existing code style (ruff + pyright strict)

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  Built with Python, pywebview, and WebKit on macOS.<br>
  Not affiliated with Twitch, Kick, or YouTube.
</p>
