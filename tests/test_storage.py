from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from core.storage import (
    DEFAULT_CONFIG,
    get_cached_avatar,
    load_config,
    save_avatar,
    save_config,
)


def test_load_config_defaults(tmp_path: Path, monkeypatch: object) -> None:
    import core.storage as mod

    config_file = tmp_path / "config.json"
    monkeypatch.setattr(mod, "CONFIG_DIR", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "CONFIG_FILE", config_file)  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "_OLD_CONFIG_DIR", tmp_path / "nonexistent")  # type: ignore[attr-defined]

    config = load_config()
    for key in DEFAULT_CONFIG:
        assert key in config, f"Missing key: {key}"
    assert config["client_id"] == ""
    assert config["kick_client_id"] == ""
    assert config["kick_access_token"] == ""
    assert config["refresh_interval"] == 60
    assert config_file.exists()


def test_load_config_merges(tmp_path: Path, monkeypatch: object) -> None:
    import core.storage as mod

    config_file = tmp_path / "config.json"
    monkeypatch.setattr(mod, "CONFIG_DIR", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "CONFIG_FILE", config_file)  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "_OLD_CONFIG_DIR", tmp_path / "nonexistent")  # type: ignore[attr-defined]

    config_file.write_text(json.dumps({"client_id": "test123", "favorites": ["xqc"]}))

    config = load_config()
    assert config["client_id"] == "test123"
    assert config["favorites"] == ["xqc"]
    assert config["refresh_interval"] == DEFAULT_CONFIG["refresh_interval"]
    assert config["quality"] == DEFAULT_CONFIG["quality"]


def test_save_and_reload(tmp_path: Path, monkeypatch: object) -> None:
    import core.storage as mod

    config_file = tmp_path / "config.json"
    monkeypatch.setattr(mod, "CONFIG_DIR", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "CONFIG_FILE", config_file)  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "_OLD_CONFIG_DIR", tmp_path / "nonexistent")  # type: ignore[attr-defined]

    data = {**DEFAULT_CONFIG, "client_id": "abc", "favorites": ["streamer1"]}
    save_config(data)

    loaded = load_config()
    assert loaded["client_id"] == "abc"
    assert loaded["favorites"] == ["streamer1"]


def test_get_cached_avatar_missing(tmp_path: Path, monkeypatch: object) -> None:
    import core.storage as mod

    monkeypatch.setattr(mod, "AVATAR_DIR", tmp_path)  # type: ignore[attr-defined]

    result = get_cached_avatar("nonexistent_user")
    assert result is None


def test_get_cached_avatar_expired(tmp_path: Path, monkeypatch: object) -> None:
    import core.storage as mod

    monkeypatch.setattr(mod, "AVATAR_DIR", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "_AVATAR_MAX_AGE", 0)  # type: ignore[attr-defined]

    avatar_file = tmp_path / "olduser.png"
    avatar_file.write_bytes(b"fake_png_data")
    os.utime(avatar_file, (time.time() - 100, time.time() - 100))

    result = get_cached_avatar("olduser")
    assert result is None


def test_get_cached_avatar_fresh(tmp_path: Path, monkeypatch: object) -> None:
    import core.storage as mod

    monkeypatch.setattr(mod, "AVATAR_DIR", tmp_path)  # type: ignore[attr-defined]

    avatar_file = tmp_path / "freshuser.png"
    avatar_file.write_bytes(b"fresh_avatar_data")

    result = get_cached_avatar("freshuser")
    assert result == b"fresh_avatar_data"


def test_save_avatar_creates_dir(tmp_path: Path, monkeypatch: object) -> None:
    import core.storage as mod

    avatar_dir = tmp_path / "avatars_new"
    monkeypatch.setattr(mod, "AVATAR_DIR", avatar_dir)  # type: ignore[attr-defined]

    assert not avatar_dir.exists()
    save_avatar("testuser", b"\x89PNG_fake_data")
    assert avatar_dir.exists()
    assert (avatar_dir / "testuser.png").read_bytes() == b"\x89PNG_fake_data"


def test_save_config_uses_private_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import core.storage as mod

    config_file = tmp_path / "config.json"
    monkeypatch.setattr(mod, "CONFIG_DIR", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "CONFIG_FILE", config_file)  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "_OLD_CONFIG_DIR", tmp_path / "nonexistent")  # type: ignore[attr-defined]

    save_config({**DEFAULT_CONFIG, "client_secret": "super-secret"})

    assert oct(config_file.stat().st_mode & 0o777) == "0o600"


def test_load_config_recovers_from_invalid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import core.storage as mod

    config_file = tmp_path / "config.json"
    monkeypatch.setattr(mod, "CONFIG_DIR", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "CONFIG_FILE", config_file)  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "_OLD_CONFIG_DIR", tmp_path / "nonexistent")  # type: ignore[attr-defined]

    config_file.write_text("{invalid json")

    config = load_config()

    assert config == DEFAULT_CONFIG
    assert json.loads(config_file.read_text()) == DEFAULT_CONFIG


def test_load_config_recovers_from_non_object_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import core.storage as mod

    config_file = tmp_path / "config.json"
    monkeypatch.setattr(mod, "CONFIG_DIR", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "CONFIG_FILE", config_file)  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "_OLD_CONFIG_DIR", tmp_path / "nonexistent")  # type: ignore[attr-defined]

    config_file.write_text(json.dumps(["not", "a", "mapping"]))

    config = load_config()

    assert config == DEFAULT_CONFIG
    assert json.loads(config_file.read_text()) == DEFAULT_CONFIG
