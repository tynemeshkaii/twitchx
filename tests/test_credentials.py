import pytest
from core.credentials import (
    TWITCH_CLIENT_ID,
    TWITCH_CLIENT_SECRET,
    KICK_CLIENT_ID,
    KICK_CLIENT_SECRET,
    YOUTUBE_CLIENT_ID,
    YOUTUBE_CLIENT_SECRET,
    YOUTUBE_API_KEY,
)


def test_bundled_credentials_are_non_empty():
    assert TWITCH_CLIENT_ID, "TWITCH_CLIENT_ID must be set"
    assert TWITCH_CLIENT_SECRET, "TWITCH_CLIENT_SECRET must be set"
    assert KICK_CLIENT_ID, "KICK_CLIENT_ID must be set"
    assert KICK_CLIENT_SECRET, "KICK_CLIENT_SECRET must be set"
    assert YOUTUBE_CLIENT_ID, "YOUTUBE_CLIENT_ID must be set"
    assert YOUTUBE_CLIENT_SECRET, "YOUTUBE_CLIENT_SECRET must be set"
    assert YOUTUBE_API_KEY, "YOUTUBE_API_KEY must be set"


def test_bundled_client_ids_look_reasonable():
    # Twitch client IDs are 30-char alphanumeric
    assert len(TWITCH_CLIENT_ID) >= 10
    # YouTube client IDs contain .apps.googleusercontent.com
    assert "." in YOUTUBE_CLIENT_ID or len(YOUTUBE_CLIENT_ID) >= 10
    # API key has minimum length
    assert len(YOUTUBE_API_KEY) >= 10
