"""Placeholder TwitchX application credentials (tracked in git).

The real keys live in core/credentials.py, which is gitignored. To build a
release with bundled keys, copy this file to core/credentials.py and fill in
the values. Without that file (clean checkout, CI) core.bundled_credentials
falls back to these empty strings: users then enter their own keys in
Settings.
"""

# Twitch — https://dev.twitch.tv/console
TWITCH_CLIENT_ID: str = ""
TWITCH_CLIENT_SECRET: str = ""

# Kick — https://kick.com/settings/developer
KICK_CLIENT_ID: str = ""
KICK_CLIENT_SECRET: str = ""

# YouTube / Google Cloud — https://console.cloud.google.com
YOUTUBE_CLIENT_ID: str = ""
YOUTUBE_CLIENT_SECRET: str = ""
YOUTUBE_API_KEY: str = ""
