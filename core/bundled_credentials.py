"""Single import point for the app's bundled OAuth credentials.

core/credentials.py (gitignored) holds the real keys. A clean checkout — CI
included — has no such file, so fall back to the empty placeholders in
core/credentials_example.py instead of failing at import time. Code that
needs credentials still goes through ``_effective_creds()``, which prefers
the user's own keys from config.
"""

from __future__ import annotations

try:
    from core import credentials as _source  # pyright: ignore[reportAttributeAccessIssue]

    HAS_BUNDLED_CREDENTIALS = True
except ImportError:
    from core import credentials_example as _source

    HAS_BUNDLED_CREDENTIALS = False

TWITCH_CLIENT_ID: str = _source.TWITCH_CLIENT_ID
TWITCH_CLIENT_SECRET: str = _source.TWITCH_CLIENT_SECRET
KICK_CLIENT_ID: str = _source.KICK_CLIENT_ID
KICK_CLIENT_SECRET: str = _source.KICK_CLIENT_SECRET
YOUTUBE_CLIENT_ID: str = _source.YOUTUBE_CLIENT_ID
YOUTUBE_CLIENT_SECRET: str = _source.YOUTUBE_CLIENT_SECRET
YOUTUBE_API_KEY: str = _source.YOUTUBE_API_KEY
