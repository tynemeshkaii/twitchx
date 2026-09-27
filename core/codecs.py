"""Decide which video codecs to advertise to Twitch when resolving a stream.

Twitch only exposes its highest renditions — notably 1440p60 from Enhanced
Broadcasting — to clients that accept HEVC or AV1. streamlink asks for h264
alone by default, which caps every resolve at 1080p60 no matter what quality
the user picked. The codec list is a parameter of the signed usher URL, so the
choice has to be made before resolving, not at playback time.
"""

from __future__ import annotations

import logging

from core.constants import (
    CODEC_BASELINE,
    CODEC_H264_ONLY,
    CODEC_MODE_AUTO,
    CODEC_MODES,
)

logger = logging.getLogger(__name__)

_AV1_SUFFIX = ",av1"


def resolve_supported_codecs(mode: str, av1_capable: bool | None) -> str:
    """Return the value for streamlink's --twitch-supported-codecs.

    ``mode`` is the user's ``stream_codecs`` setting. ``av1_capable`` is what the
    player reported about its own AV1 decoding: True when it decodes AV1 both
    smoothly and power-efficiently (i.e. in hardware), False when it does not,
    and None while the probe has not answered yet.

    In "auto" mode HEVC is always requested — AVFoundation decodes it in hardware
    on every Apple Silicon Mac and on Intel Macs with a T2 or Skylake-or-newer
    iGPU — while AV1 is added only on a confirmed hardware-class report. AV1
    hardware decode starts at M3, and decoding 1440p60 AV1 in software would cost
    more than the extra sharpness is worth.
    """
    if mode not in CODEC_MODES:
        logger.debug("Unknown stream_codecs value %r, falling back to auto", mode)
        mode = CODEC_MODE_AUTO

    if mode != CODEC_MODE_AUTO:
        return mode

    if av1_capable:
        return CODEC_BASELINE + _AV1_SUFFIX
    return CODEC_BASELINE


def twitch_codec_args(mode: str, av1_capable: bool | None) -> list[str]:
    """Build the streamlink argument list for the chosen codec set.

    h264-only is streamlink's own default, so the flag is omitted there to keep
    the command (and the resolve cache key) identical to the pre-codec behaviour.
    """
    codecs = resolve_supported_codecs(mode, av1_capable)
    if codecs == CODEC_H264_ONLY:
        return []
    return [f"--twitch-supported-codecs={codecs}"]
