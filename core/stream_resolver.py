"""Resolve Twitch HLS URLs via streamlink CLI.

Extracts URL-resolution logic so both native AVPlayer and external IINA
can share the same resolver.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.platform import PlatformClient

# Platforms whose master (multivariant) playlist AVPlayer can consume directly.
# Handing AVPlayer the master playlist enables native HLS adaptive bitrate:
# it downshifts on bandwidth drops instead of stalling, then recovers.
# Requesting a concrete quality from streamlink yields a single-rendition media
# playlist, which locks playback to one bitrate and removes ABR entirely.
ADAPTIVE_PLATFORMS = frozenset({"twitch", "kick"})

# Descending fallback ladders. streamlink picks the first available entry from
# the comma-separated list, so a channel missing the exact rendition steps *down*
# rather than jumping to source. "best" closes every ladder so playback still
# starts on channels that only offer higher renditions.
_QUALITY_LADDERS: dict[str, tuple[str, ...]] = {
    # 1440p60 exists only on Enhanced Broadcasting channels, so its ladder must
    # step down to the ordinary renditions everywhere else.
    "1440p60": ("1440p60", "1440p", "1080p60", "1080p", "720p60", "720p", "best"),
    "1440p": ("1440p", "1080p60", "1080p", "720p60", "720p", "best"),
    "1080p60": ("1080p60", "1080p", "936p60", "900p60", "720p60", "720p", "best"),
    "720p60": ("720p60", "720p", "480p", "360p", "160p", "best"),
    "720p": ("720p", "480p", "360p", "160p", "best"),
    "480p": ("480p", "360p", "160p", "best"),
    "360p": ("360p", "160p", "best"),
    # These two close on "worst" instead of "best": someone who picked the
    # smallest rendition (or audio only) is asking to save bandwidth, so falling
    # back *up* to source would do the opposite of what they asked for.
    "160p": ("160p", "worst"),
    "audio_only": ("audio_only", "worst"),
}

# Resolved URLs are reused for this long. Re-opening a channel, switching quality
# back and forth, or re-resolving after a recoverable player error then costs no
# subprocess spawn (~1.5-4s of interpreter startup + API round trip).
RESOLVE_CACHE_TTL_SECONDS = 60.0

# Stands in for the quality slot of a master-playlist cache entry, which has no
# single quality of its own.
_MASTER_CACHE_TAG = "__master__"

_cache: dict[tuple[str, str, tuple[str, ...]], tuple[str, float]] = {}
_cache_lock = threading.Lock()


def _quality_arg(quality: str) -> str:
    """Build the streamlink quality argument, with a descending fallback ladder."""
    if quality == "best":
        return "best"
    ladder = _QUALITY_LADDERS.get(quality)
    if ladder is None:
        return f"{quality},best"
    return ",".join(ladder)


def _cache_key(
    stream_url: str, quality_arg: str, extra_args: list[str] | None
) -> tuple[str, str, tuple[str, ...]]:
    return (stream_url, quality_arg, tuple(extra_args or ()))


def _cache_get(key: tuple[str, str, tuple[str, ...]]) -> str | None:
    now = time.time()
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        url, expires_at = entry
        if expires_at <= now:
            del _cache[key]
            return None
        return url


def _cache_put(key: tuple[str, str, tuple[str, ...]], url: str, ttl: float) -> None:
    if ttl <= 0:
        return
    now = time.time()
    with _cache_lock:
        # Opportunistically evict expired entries so the dict cannot grow forever.
        for stale in [k for k, (_, exp) in _cache.items() if exp <= now]:
            del _cache[stale]
        _cache[key] = (url, now + ttl)


def invalidate_resolve_cache(stream_url: str | None = None) -> None:
    """Drop cached resolutions — all of them, or only those for one stream URL."""
    with _cache_lock:
        if stream_url is None:
            _cache.clear()
            return
        for key in [k for k in _cache if k[0] == stream_url]:
            del _cache[key]


def _run_streamlink(
    resolved_sl: str,
    stream_url: str,
    quality: str | None,
    extra_args: list[str] | None = None,
) -> tuple[str | None, str]:
    """Run `streamlink --stream-url` and return (hls_url, error_text).

    With ``quality`` set, streamlink prints the media playlist URL of that single
    rendition. With ``quality`` None it prints the master playlist URL instead.
    """
    cmd = [resolved_sl, "--stream-url", stream_url]
    if quality is not None:
        cmd.append(quality)
    if extra_args:
        cmd.extend(extra_args)
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=15)
    except subprocess.TimeoutExpired:
        return None, "streamlink timed out resolving stream URL"

    if result.returncode == 0:
        hls_url = result.stdout.decode(errors="replace").strip()
        if hls_url:
            return hls_url, ""
        return None, "streamlink returned empty URL"

    return None, result.stderr.decode(errors="replace")[:300]


def resolve_hls_url(
    channel: str,
    quality: str,
    streamlink_path: str = "streamlink",
    platform_client: PlatformClient | None = None,
    extra_args: list[str] | None = None,
    adaptive: bool = False,
    use_cache: bool = False,
) -> tuple[str | None, str]:
    """Resolve HLS URL for a stream channel.

    Returns (hls_url, error_message). Falls back down a quality ladder if the
    requested quality is unavailable.

    extra_args are appended to the streamlink command (e.g. ["--twitch-low-latency"]).
    adaptive requests the master playlist (all renditions) instead of a single one,
    which is only meaningful for quality="best" and for players that do their own
    ABR. It falls back to a single-rendition resolve if the master resolve fails.
    use_cache reuses a recent resolution for the same (url, quality, args) triple.
    """
    resolved_sl = shutil.which(streamlink_path)
    if resolved_sl is None:
        logger.warning("streamlink not found at %s", streamlink_path)
        return (
            None,
            "streamlink not found.\n\nInstall it with:\n  brew install streamlink",
        )

    if channel.startswith("http://") or channel.startswith("https://"):
        stream_url = channel
        logger.debug("Resolving HLS from direct URL: %s", channel[:80])
    elif platform_client is not None:
        stream_url = platform_client.build_stream_url(channel)
        logger.debug(
            "Resolving HLS for %s via %s", channel, platform_client.PLATFORM_ID
        )
    else:
        logger.error("No platform client and channel is not a URL: %s", channel)
        return None, "No platform client provided and channel is not a direct URL"

    want_master = adaptive and quality == "best"
    quality_arg = _quality_arg(quality)
    master_key = _cache_key(stream_url, _MASTER_CACHE_TAG, extra_args)
    single_key = _cache_key(stream_url, quality_arg, extra_args)

    if want_master:
        if use_cache:
            cached = _cache_get(master_key)
            if cached is not None:
                logger.debug("Master playlist served from resolve cache")
                return cached, ""
        logger.debug("Running streamlink for master playlist (adaptive)")
        hls_url, err = _run_streamlink(resolved_sl, stream_url, None, extra_args)
        if hls_url:
            logger.info("Master playlist resolved (length=%d)", len(hls_url))
            _cache_put(master_key, hls_url, RESOLVE_CACHE_TTL_SECONDS)
            return hls_url, ""
        logger.warning(
            "Master playlist resolve failed (%s), falling back to single rendition", err
        )

    # Checked here rather than above so the master fallback path can reuse a
    # cached single-rendition URL instead of spawning streamlink a second time.
    if use_cache:
        cached = _cache_get(single_key)
        if cached is not None:
            logger.debug("HLS URL served from resolve cache")
            return cached, ""

    logger.debug("Running streamlink with quality=%s", quality_arg)
    hls_url, err = _run_streamlink(resolved_sl, stream_url, quality_arg, extra_args)

    if hls_url:
        logger.info("HLS URL resolved successfully (length=%d)", len(hls_url))
        _cache_put(single_key, hls_url, RESOLVE_CACHE_TTL_SECONDS)
    else:
        logger.warning("HLS resolution failed: %s", err)
    return hls_url, err
