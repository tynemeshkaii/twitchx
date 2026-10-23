from __future__ import annotations

import re

_YT_ID_RE = re.compile(r"^UC[\w-]{22}$", re.IGNORECASE)


def _tenths(tenths: int, suffix: str) -> str:
    whole, frac = divmod(tenths, 10)
    return f"{whole}{suffix}" if frac == 0 else f"{whole}.{frac}{suffix}"


def format_viewers(count: int) -> str:
    """950, 9.7K, 88.3K, 210K, 1.2M, 12M — keep in sync with formatViewers in ui/js/utils.js.

    Integer half-up rounding, so a value that rounds up crosses into the next
    unit (99 950 → 100K, 999 950 → 1M) instead of printing 100.0K or 1000K.
    """
    if count < 1_000:
        return str(count)
    tenths_k = (count + 50) // 100
    if tenths_k < 1_000:
        return _tenths(tenths_k, "K")
    whole_k = (count + 500) // 1_000
    if whole_k < 1_000:
        return f"{whole_k}K"
    return _tenths((count + 50_000) // 100_000, "M")


def normalize_channel_id(raw: str) -> str:
    """Sanitize a potential YouTube channel identifier.

    Preserves case for UC IDs (they are case-sensitive) and strips
    characters that cannot appear in a valid channel ID or handle.
    """
    return re.sub(r"[^A-Za-z0-9_-]", "", raw.strip())


def sanitize_twitch_login(raw: str) -> str:
    """Extract Twitch login from raw string."""
    raw = raw.strip()
    match = re.search(r"twitch\.tv/([a-zA-Z0-9_]+)", raw)
    if match:
        return match.group(1).lower()
    return re.sub(r"[^a-zA-Z0-9_]", "", raw).lower()


def sanitize_kick_slug(raw: str) -> str:
    """Extract Kick slug from raw string."""
    raw = raw.strip()
    match = re.search(r"kick\.com/([a-zA-Z0-9_-]+)", raw, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return re.sub(r"[^a-zA-Z0-9_-]", "", raw).lower()


def sanitize_youtube_id(raw: str) -> str:
    """Sanitize a YouTube channel identifier."""
    return normalize_channel_id(raw)


def sanitize_youtube_login(raw: str) -> str:
    """Extract YouTube channel identifier preserving @handle and v: prefixes.

    Mirrors YouTubeClient.sanitize_identifier without importing the client.
    """
    raw = raw.strip()
    # Already a v: prefixed video ID
    if raw.startswith("v:"):
        vid = raw[2:]
        if re.match(r"^[A-Za-z0-9_-]{11}$", vid):
            return raw
    match = re.search(r"youtube\.com/channel/(UC[\w-]{22})", raw, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", raw)
    if match:
        return "v:" + match.group(1)
    match = re.search(
        r"(?:youtube\.com/)?(@[A-Za-z0-9][A-Za-z0-9_.-]{2,29})", raw, re.IGNORECASE
    )
    if match:
        return match.group(1).lower()
    clean = normalize_channel_id(raw)
    if _YT_ID_RE.match(clean):
        return clean
    if re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,29}$", clean):
        return "@" + clean.lower()
    return ""
