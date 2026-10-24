"""Validation for the settings payload sent from JS by ``save_settings``."""

from __future__ import annotations

import contextlib
from typing import Any

from core.constants import CODEC_MODES
from core.launcher import QUALITIES
from core.storage import DEFAULT_SETTINGS

REFRESH_INTERVAL_MIN = 30
REFRESH_INTERVAL_MAX = 3600

# Same swatches as ACCENT_PALETTE in ui/js/settings.js.
_ACCENT_PALETTE = {
    "#FF9F0A",
    "#BF5AF2",
    "#0A84FF",
    "#40C8E0",
    "#5E5CE6",
    "#8E8E93",
}

_STRING_FIELDS = (
    "client_id",
    "client_secret",
    "streamlink_path",
    "iina_path",
    "mpv_path",
    "recording_path",
    "kick_client_id",
    "kick_client_secret",
    "youtube_api_key",
    "youtube_client_id",
    "youtube_client_secret",
)

_BOOL_FIELDS = (
    "pip_enabled",
    "low_latency_mode",
    "chat_filter_sub_only",
    "chat_filter_mod_only",
    "chat_anti_spam",
)

_CHOICE_FIELDS: dict[str, Any] = {
    "quality": QUALITIES,
    "external_player": ("iina", "mpv"),
    "stream_codecs": CODEC_MODES,
    "accent_color": _ACCENT_PALETTE,
    "theme": ("auto", "dark", "light"),
}


def clamp_refresh_interval(value: Any, default: int = 60) -> int:
    """Coerce a refresh interval to an int within the allowed range."""
    try:
        interval = int(value)
    except (TypeError, ValueError):
        interval = default
    return max(REFRESH_INTERVAL_MIN, min(REFRESH_INTERVAL_MAX, interval))


def validate_settings_payload(parsed: dict[str, Any]) -> dict[str, Any]:
    """Return only the well-formed fields of a settings payload.

    Malformed values are dropped rather than raising, so one bad field
    never blocks the rest of the save.
    """
    clean: dict[str, Any] = {}

    for key in _STRING_FIELDS:
        value = parsed.get(key)
        if isinstance(value, str):
            clean[key] = value.strip()

    for key in _BOOL_FIELDS:
        value = parsed.get(key)
        if isinstance(value, bool):
            clean[key] = value

    for key, allowed in _CHOICE_FIELDS.items():
        value = parsed.get(key)
        if isinstance(value, str) and value in allowed:
            clean[key] = value

    if "refresh_interval" in parsed:
        raw = parsed["refresh_interval"]
        # bool is an int subclass; True must not become a 30s interval.
        if not isinstance(raw, bool):
            with contextlib.suppress(TypeError, ValueError):
                clean["refresh_interval"] = clamp_refresh_interval(int(raw))

    block_list = parsed.get("chat_block_list")
    if isinstance(block_list, list):
        clean["chat_block_list"] = [str(w)[:50] for w in block_list[:100]]

    shortcuts = parsed.get("keyboard_shortcuts")
    if isinstance(shortcuts, dict):
        known = set(DEFAULT_SETTINGS.get("keyboard_shortcuts", {}).keys())
        clean["keyboard_shortcuts"] = {
            k: v
            for k, v in shortcuts.items()
            if k in known and isinstance(v, str) and 0 < len(v) <= 50
        }

    return clean
