"""Resolve Twitch HLS URLs via streamlink CLI.

Extracts URL-resolution logic so both native AVPlayer and external IINA
can share the same resolver.
"""

from __future__ import annotations

import shutil
import subprocess


def _run_streamlink(
    resolved_sl: str, twitch_url: str, quality: str
) -> tuple[str | None, str]:
    """Run `streamlink --stream-url` and return (hls_url, error_text)."""
    try:
        result = subprocess.run(
            [resolved_sl, "--stream-url", twitch_url, quality],
            capture_output=True,
            timeout=15,
        )
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
) -> tuple[str | None, str]:
    """Resolve HLS URL for a Twitch channel.

    Returns (hls_url, error_message). Falls back to 'best' quality
    if the requested quality is unavailable.
    """
    resolved_sl = shutil.which(streamlink_path)
    if resolved_sl is None:
        return (
            None,
            "streamlink not found.\n\nInstall it with:\n  brew install streamlink",
        )

    twitch_url = f"https://twitch.tv/{channel}"
    hls_url, err = _run_streamlink(resolved_sl, twitch_url, quality)

    if not hls_url and quality != "best":
        hls_url, err = _run_streamlink(resolved_sl, twitch_url, "best")

    return hls_url, err
