from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import core.storage as storage
from core.storage import DEFAULT_CONFIG
from ui.api import TwitchXApi

# ==========================================================================
# Config / Storage fixtures
# ==========================================================================


@pytest.fixture
def temp_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect config directory to a temporary path.

    Writes a minimal default config so load_config() returns sensible defaults.
    Use this fixture in any test that reads or writes config via core.storage.
    """
    config_dir = tmp_path / "twitchx"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps(DEFAULT_CONFIG))

    monkeypatch.setattr(storage, "CONFIG_DIR", config_dir)  # type: ignore[attr-defined]
    monkeypatch.setattr(storage, "CONFIG_FILE", config_file)  # type: ignore[attr-defined]
    monkeypatch.setattr(storage, "_OLD_CONFIG_DIR", config_dir / "old")  # type: ignore[attr-defined]

    return config_file


@pytest.fixture
def config_with_twitch_auth(temp_config_dir: Path) -> Path:
    """Config file with valid Twitch OAuth tokens."""
    cfg = json.loads(temp_config_dir.read_text())
    cfg["platforms"]["twitch"] = {
        **cfg["platforms"]["twitch"],
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
        "token_type": "user",
        "token_is_valid": True,
    }
    temp_config_dir.write_text(json.dumps(cfg))
    return temp_config_dir


# ==========================================================================
# Platform client mock factories
# ==========================================================================


@pytest.fixture
def mock_twitch_client() -> MagicMock:
    """Return a MagicMock configured as a TwitchClient."""
    client = MagicMock()
    client.PLATFORM_ID = "twitch"
    client.PLATFORM_NAME = "Twitch"
    client.build_stream_url = MagicMock(return_value="https://twitch.tv/test")
    client.sanitize_identifier = MagicMock(return_value="test")
    client.get_live_streams = AsyncMock(return_value=[])
    client.search_channels = AsyncMock(return_value=[])
    client.get_channel_info = AsyncMock(return_value={})
    client.get_auth_url = MagicMock(
        return_value="https://id.twitch.tv/oauth2/authorize?..."
    )
    client.exchange_code = AsyncMock(
        return_value={"access_token": "tok", "refresh_token": "ref"}
    )
    client.get_current_user = AsyncMock(
        return_value={"login": "test", "display_name": "Test"}
    )
    client.get_followed_channels = AsyncMock(return_value=["streamer1", "streamer2"])
    client.get_channel_vods = AsyncMock(return_value=[])
    client.get_channel_clips = AsyncMock(return_value=[])
    client.normalize_search_result = AsyncMock(
        return_value={"login": "test", "display_name": "Test", "platform": "twitch"}
    )
    client.normalize_stream_item = AsyncMock(
        return_value={"login": "test", "display_name": "Test", "platform": "twitch"}
    )
    return client


@pytest.fixture
def mock_kick_client() -> MagicMock:
    """Return a MagicMock configured as a KickClient."""
    client = MagicMock()
    client.PLATFORM_ID = "kick"
    client.PLATFORM_NAME = "Kick"
    client.build_stream_url = MagicMock(return_value="https://kick.com/test")
    client.sanitize_identifier = MagicMock(return_value="test-slug")
    client.get_live_streams = AsyncMock(return_value=[])
    client.search_channels = AsyncMock(return_value=[])
    client.get_channel_info = AsyncMock(return_value={})
    client.get_auth_url = MagicMock(
        return_value="https://id.kick.com/oauth2/authorize?..."
    )
    client.exchange_code = AsyncMock(return_value={"access_token": "tok"})
    client.get_current_user = AsyncMock(
        return_value={"login": "test", "display_name": "Test"}
    )
    client.get_followed_channels = AsyncMock(return_value=[])
    client.normalize_search_result = AsyncMock(
        return_value={"login": "test-slug", "display_name": "Test", "platform": "kick"}
    )
    client.normalize_stream_item = AsyncMock(
        return_value={"login": "test-slug", "display_name": "Test", "platform": "kick"}
    )
    return client


@pytest.fixture
def mock_youtube_client() -> MagicMock:
    """Return a MagicMock configured as a YouTubeClient."""
    client = MagicMock()
    client.PLATFORM_ID = "youtube"
    client.PLATFORM_NAME = "YouTube"
    client.build_stream_url = MagicMock(return_value="https://youtube.com/watch?v=test")
    client.sanitize_identifier = MagicMock(return_value="UCtest")
    client.get_live_streams = AsyncMock(return_value=[])
    client.search_channels = AsyncMock(return_value=[])
    client.get_channel_info = AsyncMock(return_value={})
    client.normalize_search_result = AsyncMock(
        return_value={"login": "UCtest", "display_name": "Test", "platform": "youtube"}
    )
    client.normalize_stream_item = AsyncMock(
        return_value={"login": "UCtest", "display_name": "Test", "platform": "youtube"}
    )
    client.get_followed_channels = AsyncMock(
        return_value=[
            {"channel_id": "UCaaaaaaaaaaaaaaaaaaaaaa", "display_name": "Channel One"},
            {"channel_id": "UCbbbbbbbbbbbbbbbbbbbbbb", "display_name": "Channel Two"},
        ]
    )
    return client


# ==========================================================================
# JS callback capture fixture
# ==========================================================================


@pytest.fixture
def capture_eval_js() -> Any:
    """Captures all _eval_js() calls for assertion.

    Usage:
        def test_foo(capture_eval_js):
            api._eval_js = capture_eval_js
            api.some_method()
            assert capture_eval_js.calls[0] == "window.onSomething(...)"
    """

    class Capture:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def __call__(self, code: str) -> None:
            self.calls.append(code)

        def assert_any(self, fragment: str) -> None:
            for call in self.calls:
                if fragment in call:
                    return
            raise AssertionError(f"No call containing '{fragment}' in {self.calls}")

    return Capture()


# ==========================================================================
# Thread mocking fixture (sync execution)
# ==========================================================================


@pytest.fixture
def run_sync(monkeypatch: pytest.MonkeyPatch):  # type: ignore[return-type]
    """Patch TwitchXApi._run_in_thread so all background work runs synchronously.

    Usage:
        def test_foo(temp_config_dir, run_sync):
            api = TwitchXApi()
            # _run_in_thread is already patched — calls fn() directly
    """
    original = TwitchXApi._run_in_thread
    monkeypatch.setattr(TwitchXApi, "_run_in_thread", lambda self, fn: fn())
    yield
    monkeypatch.setattr(TwitchXApi, "_run_in_thread", original)
