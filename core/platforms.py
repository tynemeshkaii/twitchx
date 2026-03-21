from __future__ import annotations

import re

DEFAULT_PLATFORM = "twitch"
SUPPORTED_PLATFORMS = ("twitch", "kick")

_CHANNEL_REF_RE = re.compile(
    r"^(?P<platform>twitch|kick):(?P<login>[A-Za-z0-9._-]+)$",
    re.IGNORECASE,
)
_TWITCH_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?twitch\.tv/(?P<login>[A-Za-z0-9_]+)",
    re.IGNORECASE,
)
_KICK_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?kick\.com/(?P<login>[A-Za-z0-9._-]+)",
    re.IGNORECASE,
)
_PLAIN_LOGIN_RE = re.compile(r"[A-Za-z0-9._-]+")


def split_channel_ref(
    value: str,
    default_platform: str = DEFAULT_PLATFORM,
) -> tuple[str, str]:
    raw = value.strip()
    if not raw:
        return default_platform, ""

    match = _CHANNEL_REF_RE.match(raw)
    if match:
        platform = match.group("platform").lower()
        login = match.group("login").lower()
        return platform, login

    match = _TWITCH_URL_RE.search(raw)
    if match:
        return "twitch", match.group("login").lower()

    match = _KICK_URL_RE.search(raw)
    if match:
        return "kick", match.group("login").lower()

    match = _PLAIN_LOGIN_RE.search(raw)
    if not match:
        return default_platform, ""
    return default_platform, match.group(0).lower()


def normalize_channel_ref(
    value: str,
    default_platform: str = DEFAULT_PLATFORM,
) -> str:
    platform, login = split_channel_ref(value, default_platform=default_platform)
    if not login:
        return ""
    return f"{platform}:{login}"


def build_channel_ref(
    platform: str,
    login: str,
    default_platform: str = DEFAULT_PLATFORM,
) -> str:
    normalized_platform = platform.strip().lower()
    normalized_login = login.strip().lower()
    if not normalized_login:
        return ""
    if normalized_platform == default_platform:
        return normalized_login
    return f"{normalized_platform}:{normalized_login}"


def build_channel_url(
    value: str,
    default_platform: str = DEFAULT_PLATFORM,
) -> str:
    platform, login = split_channel_ref(value, default_platform=default_platform)
    if platform == "kick":
        return f"https://kick.com/{login}"
    return f"https://twitch.tv/{login}"


def format_channel_ref(
    value: str,
    default_platform: str = DEFAULT_PLATFORM,
) -> str:
    platform, login = split_channel_ref(value, default_platform=default_platform)
    if not login:
        return ""
    if platform == default_platform:
        return login
    return f"{platform}:{login}"
