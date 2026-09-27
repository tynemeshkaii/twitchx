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

# Feature flags
# YouTube is disabled for the closed beta — bundled YouTube creds are
# placeholders. Backend code stays intact; flip to True + fill real creds
# in core/credentials.py to re-enable. See ui.api state bootstrap for the
# JS-side mirror (TwitchX.state.youtubeEnabled).
YOUTUBE_ENABLED = False

# OAuth
OAUTH_PORT = 3457
OAUTH_TIMEOUT_SECONDS = 120

# Images
AVATAR_SIZE = (56, 56)
THUMBNAIL_SIZE = (440, 248)
JPEG_QUALITY = 85

# Stream codecs
# streamlink asks Twitch for h264 only by default, and Twitch exposes its highest
# renditions (1440p60 via Enhanced Broadcasting) only to clients that also accept
# HEVC or AV1. The codec set is baked into the signed usher URL, so it has to be
# chosen at resolve time.
#
# h265 is safe to request everywhere: AVFoundation decodes HEVC in HLS with
# hardware support on every Apple Silicon Mac and every Intel Mac with a T2 or
# Skylake-or-newer iGPU. AV1 is not — hardware decode starts at M3, and software
# decoding 1440p60 AV1 would burn the CPU — so "auto" only adds it once the
# WebView reports that it decodes AV1 both smoothly and power-efficiently.
CODEC_MODE_AUTO = "auto"
CODEC_MODES = ("auto", "h264", "h264,h265", "h264,h265,av1")
CODEC_BASELINE = "h264,h265"
CODEC_H264_ONLY = "h264"

# Chat
CHAT_WIDTH_MIN = 250
CHAT_WIDTH_MAX = 500
CHAT_RECONNECT_DELAYS = [3, 6, 12, 24, 48]

# Watch Statistics
WATCH_STATS_DB_NAME = "watch_stats.db"
WATCH_STATS_SESSION_CLEANUP_DAYS = 90  # sessions older than this are pruned

# Recording
DEFAULT_RECORDING_DIR = str(Path.home() / "Movies" / "TwitchX")
