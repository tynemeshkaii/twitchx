"""Resolve Twitch HLS URLs via streamlink CLI.

Extracts URL-resolution logic so both native AVPlayer and external IINA
can share the same resolver.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.platform import PlatformClient


def _run_streamlink(
    resolved_sl: str, stream_url: str, quality: str, extra_args: list[str] | None = None
) -> tuple[str | None, str]:
    """Run `streamlink --stream-url` and return (hls_url, error_text)."""
    cmd = [resolved_sl, "--stream-url", stream_url, quality]
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
) -> tuple[str | None, str]:
    """Resolve HLS URL for a stream channel.

    Returns (hls_url, error_message). Falls back to 'best' quality
    if the requested quality is unavailable.
    extra_args are appended to the streamlink command (e.g. ["--twitch-low-latency"]).
    """
    resolved_sl = shutil.which(streamlink_path)
    if resolved_sl is None:
        return (
            None,
            "streamlink not found.\n\nInstall it with:\n  brew install streamlink",
        )

    if channel.startswith("http://") or channel.startswith("https://"):
        stream_url = channel
    elif platform_client is not None:
        stream_url = platform_client.build_stream_url(channel)
    else:
        return None, "No platform client provided and channel is not a direct URL"

    hls_url, err = _run_streamlink(resolved_sl, stream_url, quality, extra_args)

    if not hls_url and quality != "best":
        hls_url, err = _run_streamlink(resolved_sl, stream_url, "best", extra_args)

    return hls_url, err
