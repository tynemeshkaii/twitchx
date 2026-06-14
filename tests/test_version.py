from __future__ import annotations

from unittest.mock import patch


def test_get_version_returns_semver_string(temp_config_dir):
    from ui.api import TwitchXApi

    with patch("httpx.Client"):
        api = TwitchXApi()
    version = api.get_version()
    assert isinstance(version, str)
    parts = version.split(".")
    assert len(parts) == 3, f"Expected semver X.Y.Z, got: {version}"
