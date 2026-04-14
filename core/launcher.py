from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.stream_resolver import resolve_hls_url

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


def launch_stream(
    channel: str,
    quality: str,
    streamlink_path: str = "streamlink",
    iina_path: str = DEFAULT_IINA_PATH,
    platform: str = "twitch",
) -> LaunchResult:
    sl_err = check_streamlink(streamlink_path)
    if sl_err:
        return LaunchResult(success=False, message=sl_err)
    iina_err = check_iina(iina_path)
    if iina_err:
        return LaunchResult(success=False, message=iina_err)

    # Resolve the direct HLS URL via stream_resolver (shared with native player)
    hls_url, err = resolve_hls_url(channel, quality, streamlink_path, platform=platform)

    if not hls_url:
        return LaunchResult(
            success=False,
            message=f"streamlink error: {err}"
            if err
            else "Could not resolve stream URL",
        )

    # Pass the HLS URL directly to iina-cli.
    # IINA handles HLS natively with full hardware-accelerated decoding.
    try:
        subprocess.Popen(
            [iina_path, hls_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return LaunchResult(success=True, message=f"Launched {channel} ({quality})")
    except Exception as e:
        return LaunchResult(success=False, message=f"Failed to launch IINA: {e}")
