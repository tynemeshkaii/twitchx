from pathlib import Path

import pytest

import core.bundled_credentials as creds
from core.bundled_credentials import (
    HAS_BUNDLED_CREDENTIALS,
    KICK_CLIENT_ID,
    KICK_CLIENT_SECRET,
    TWITCH_CLIENT_ID,
    TWITCH_CLIENT_SECRET,
    YOUTUBE_API_KEY,
    YOUTUBE_CLIENT_ID,
    YOUTUBE_CLIENT_SECRET,
)
from core.platforms.kick import KickClient
from core.platforms.twitch import TwitchClient
from core.platforms.youtube import YouTubeClient

needs_bundled = pytest.mark.skipif(
    not HAS_BUNDLED_CREDENTIALS,
    reason="core/credentials.py is gitignored; absent in a clean checkout / CI",
)


@needs_bundled
def test_bundled_credentials_are_non_empty():
    assert TWITCH_CLIENT_ID, "TWITCH_CLIENT_ID must be set"
    assert TWITCH_CLIENT_SECRET, "TWITCH_CLIENT_SECRET must be set"
    assert KICK_CLIENT_ID, "KICK_CLIENT_ID must be set"
    assert KICK_CLIENT_SECRET, "KICK_CLIENT_SECRET must be set"
    assert YOUTUBE_CLIENT_ID, "YOUTUBE_CLIENT_ID must be set"
    assert YOUTUBE_CLIENT_SECRET, "YOUTUBE_CLIENT_SECRET must be set"
    assert YOUTUBE_API_KEY, "YOUTUBE_API_KEY must be set"


@needs_bundled
def test_bundled_client_ids_look_reasonable():
    # Twitch client IDs are 30-char alphanumeric
    assert len(TWITCH_CLIENT_ID) >= 10
    # YouTube client IDs contain .apps.googleusercontent.com
    assert "." in YOUTUBE_CLIENT_ID or len(YOUTUBE_CLIENT_ID) >= 10
    # API key has minimum length
    assert len(YOUTUBE_API_KEY) >= 10


def test_example_credentials_are_empty_placeholders():
    """The tracked fallback must never carry real keys."""
    import core.credentials_example as example

    names = [n for n in dir(example) if n.isupper()]
    assert names, "credentials_example must define the credential constants"
    assert all(getattr(example, n) == "" for n in names)
    assert set(names) <= set(dir(creds))


def test_effective_creds_returns_bundled_when_config_empty(temp_config_dir: Path):
    """Empty config → bundled credentials returned."""
    client = TwitchClient()
    cid, csec = client._effective_creds()
    assert cid == creds.TWITCH_CLIENT_ID
    assert csec == creds.TWITCH_CLIENT_SECRET


def test_effective_creds_returns_config_when_set(temp_config_dir: Path):
    """Non-empty config credentials take priority over bundled."""
    from core.storage import update_config

    def _set(cfg):
        cfg["platforms"]["twitch"]["client_id"] = "custom_id"
        cfg["platforms"]["twitch"]["client_secret"] = "custom_secret"

    update_config(_set)
    client = TwitchClient()
    cid, csec = client._effective_creds()
    assert cid == "custom_id"
    assert csec == "custom_secret"


def test_effective_creds_kick(temp_config_dir: Path):
    client = KickClient()
    cid, csec = client._effective_creds()
    assert cid == creds.KICK_CLIENT_ID
    assert csec == creds.KICK_CLIENT_SECRET


def test_effective_creds_youtube(temp_config_dir: Path):
    client = YouTubeClient()
    cid, csec = client._effective_creds()
    assert cid == creds.YOUTUBE_CLIENT_ID
    assert csec == creds.YOUTUBE_CLIENT_SECRET
