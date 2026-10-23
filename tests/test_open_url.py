"""open_url / open_browser must only hand http(s) URLs to the OS."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from ui.api import TwitchXApi


@pytest.fixture
def api(temp_config_dir: Path) -> TwitchXApi:
    return TwitchXApi()


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "x-apple.systempreferences:com.apple.preference.security",
        "ftp://example.com/x",
        "//example.com",
        "example.com",
        "",
    ],
)
def test_open_url_rejects_non_http_schemes(api: TwitchXApi, url: str) -> None:
    with patch("ui.api.webbrowser.open") as wb_open:
        api.open_url(url)
    wb_open.assert_not_called()


@pytest.mark.parametrize(
    "url", ["https://example.com/a?b=c", "http://example.com", "HTTPS://Example.com"]
)
def test_open_url_allows_http_and_https(api: TwitchXApi, url: str) -> None:
    with patch("ui.api.webbrowser.open") as wb_open:
        api.open_url(url)
    wb_open.assert_called_once_with(url)


@pytest.mark.parametrize(
    ("channel", "platform", "expected"),
    [
        ("@SomeHandle", "youtube", "https://youtube.com/@SomeHandle"),
        ("UCabcDEF123", "youtube", "https://youtube.com/channel/UCabcDEF123"),
        ("v:dQw4w9WgXcQ", "youtube", "https://youtube.com/watch?v=dQw4w9WgXcQ"),
        ("xqc", "twitch", "https://twitch.tv/xqc"),
        ("train wreck", "kick", "https://kick.com/train%20wreck"),
        ("../settings", "twitch", "https://twitch.tv/..%2Fsettings"),
    ],
)
def test_open_browser_builds_platform_urls(
    api: TwitchXApi, channel: str, platform: str, expected: str
) -> None:
    with patch("ui.api.webbrowser.open") as wb_open:
        api.open_browser(channel, platform)
    wb_open.assert_called_once_with(expected)


def test_open_browser_ignores_empty_channel(api: TwitchXApi) -> None:
    with patch("ui.api.webbrowser.open") as wb_open:
        api.open_browser("", "twitch")
    wb_open.assert_not_called()
