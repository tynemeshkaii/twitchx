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


def test_version_read_from_meipass_in_frozen_bundle(tmp_path, monkeypatch):
    """PyInstaller bundles pyproject.toml at the _MEIPASS root (TwitchX.spec)."""
    import sys

    from ui.api import _read_project_version

    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "9.8.7"\n')
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert _read_project_version() == "9.8.7"


def test_spec_bundles_pyproject():
    from pathlib import Path

    spec = (Path(__file__).parent.parent / "TwitchX.spec").read_text()
    assert '("pyproject.toml", ".")' in spec
