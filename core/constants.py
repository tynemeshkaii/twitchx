"""Shared constants for the application."""

from __future__ import annotations

from pathlib import Path

# IINA
DEFAULT_IINA_PATH = "/Applications/IINA.app/Contents/MacOS/iina-cli"

# mpv
DEFAULT_MPV_PATH = "/opt/homebrew/bin/mpv"

# Config
CONFIG_DIR_NAME = "twitchx"
CONFIG_FILE_NAME = "config.json"

# Cache
AVATAR_CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 days
BROWSE_CACHE_TTL_SECONDS = 10 * 60  # 10 minutes

# OAuth
OAUTH_PORT = 3457
OAUTH_TIMEOUT_SECONDS = 120

# Images
AVATAR_SIZE = (56, 56)
THUMBNAIL_SIZE = (440, 248)
JPEG_QUALITY = 85

# Chat
CHAT_WIDTH_MIN = 250
CHAT_WIDTH_MAX = 500
CHAT_RECONNECT_DELAYS = [3, 6, 12, 24, 48]

# Watch Statistics
WATCH_STATS_DB_NAME = "watch_stats.db"
WATCH_STATS_SESSION_CLEANUP_DAYS = 90  # sessions older than this are pruned

# Recording
DEFAULT_RECORDING_DIR = str(Path.home() / "Movies" / "TwitchX")
