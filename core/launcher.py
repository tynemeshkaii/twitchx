from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from core.constants import DEFAULT_IINA_PATH, DEFAULT_MPV_PATH
from core.stream_resolver import resolve_hls_url

if TYPE_CHECKING:
    from core.platform import PlatformClient

QUALITIES = ["best", "1080p60", "720p60", "480p", "360p", "audio_only"]


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


def check_mpv(mpv_path: str = DEFAULT_MPV_PATH) -> str | None:
    """Returns an error message if mpv is not found, else None."""
    if shutil.which(mpv_path) is None:
        return f"mpv not found at {mpv_path}.\n\nInstall it with:\n  brew install mpv"
    return None


def launch_stream(
    channel: str,
    quality: str,
    streamlink_path: str = "streamlink",
    iina_path: str = DEFAULT_IINA_PATH,
    platform_client: PlatformClient | None = None,
    extra_args: list[str] | None = None,
) -> LaunchResult:
    sl_err = check_streamlink(streamlink_path)
    if sl_err:
        return LaunchResult(success=False, message=sl_err)
    iina_err = check_iina(iina_path)
    if iina_err:
        return LaunchResult(success=False, message=iina_err)

    # Resolve the direct HLS URL via stream_resolver (shared with native player)
    hls_url, err = resolve_hls_url(channel, quality, streamlink_path, platform_client, extra_args)

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


def launch_stream_mpv(
    channel: str,
    quality: str,
    streamlink_path: str = "streamlink",
    mpv_path: str = DEFAULT_MPV_PATH,
    platform_client: PlatformClient | None = None,
    extra_args: list[str] | None = None,
) -> LaunchResult:
    sl_err = check_streamlink(streamlink_path)
    if sl_err:
        return LaunchResult(success=False, message=sl_err)
    mpv_err = check_mpv(mpv_path)
    if mpv_err:
        return LaunchResult(success=False, message=mpv_err)

    hls_url, err = resolve_hls_url(channel, quality, streamlink_path, platform_client, extra_args)
    if not hls_url:
        return LaunchResult(
            success=False,
            message=f"streamlink error: {err}" if err else "Could not resolve stream URL",
        )

    try:
        subprocess.Popen(
            [mpv_path, "--no-terminal", hls_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return LaunchResult(success=True, message=f"Launched {channel} in mpv ({quality})")
    except Exception as e:
        return LaunchResult(success=False, message=f"Failed to launch mpv: {e}")
