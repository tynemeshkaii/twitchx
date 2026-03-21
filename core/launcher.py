from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.platforms import build_channel_url, format_channel_ref

QUALITIES = ["best", "1080p60", "720p60", "480p", "360p", "audio_only"]

DEFAULT_IINA_PATH = "/Applications/IINA.app/Contents/MacOS/iina-cli"


@dataclass
class LaunchResult:
    success: bool
    message: str


def check_streamlink(streamlink_path: str = "streamlink") -> str | None:
    """Returns an error message if streamlink is not found, else None."""
    resolved = shutil.which(streamlink_path)
    if resolved is None:
        return "streamlink not found.\n\nInstall it with:\n  brew install streamlink"
    return None


def check_iina(iina_path: str = DEFAULT_IINA_PATH) -> str | None:
    """Returns an error message if IINA is not found, else None."""
    if not Path(iina_path).exists():
        return "IINA not found.\n\nDownload it from:\n  https://iina.io"
    return None


def _get_stream_url(
    resolved_sl: str, twitch_url: str, quality: str
) -> tuple[str | None, str]:
    """Run `streamlink --stream-url` and return (hls_url, stderr_text)."""
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


def launch_stream(
    channel: str,
    quality: str,
    streamlink_path: str = "streamlink",
    iina_path: str = DEFAULT_IINA_PATH,
) -> LaunchResult:
    sl_err = check_streamlink(streamlink_path)
    if sl_err:
        return LaunchResult(success=False, message=sl_err)
    iina_err = check_iina(iina_path)
    if iina_err:
        return LaunchResult(success=False, message=iina_err)

    resolved_sl = shutil.which(streamlink_path) or streamlink_path
    stream_url = build_channel_url(channel)
    display_channel = format_channel_ref(channel)

    # Step 1: resolve the direct HLS URL via streamlink --stream-url
    hls_url, err = _get_stream_url(resolved_sl, stream_url, quality)

    # Quality fallback: if requested quality unavailable, retry with "best"
    if not hls_url and quality != "best":
        hls_url, err = _get_stream_url(resolved_sl, stream_url, "best")

    if not hls_url:
        return LaunchResult(
            success=False,
            message=f"streamlink error: {err}"
            if err
            else "Could not resolve stream URL",
        )

    # Step 2: pass the HLS URL directly to iina-cli
    # IINA handles HLS natively with full hardware-accelerated decoding.
    try:
        subprocess.Popen(
            [iina_path, hls_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return LaunchResult(
            success=True, message=f"Launched {display_channel} ({quality})"
        )
    except Exception as e:
        return LaunchResult(success=False, message=f"Failed to launch IINA: {e}")
