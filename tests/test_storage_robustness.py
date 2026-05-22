from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from core.storage import DEFAULT_CONFIG, DEFAULT_SETTINGS, load_config, save_config


def test_load_config_malformed_json_falls_back_to_defaults(
    temp_config_dir: Path,
) -> None:
    temp_config_dir.write_text("{this is not valid json}")
    config = load_config()
    assert config["platforms"]["twitch"]["client_id"] == ""
    assert config["settings"]["refresh_interval"] == 60
    assert config["favorites"] == []


def test_load_config_corrupt_json_overwrites_file_with_defaults(
    temp_config_dir: Path,
) -> None:
    temp_config_dir.write_text("{bad}")
    load_config()
    # The corrupt file should now be valid JSON containing the defaults
    restored = json.loads(temp_config_dir.read_text())
    assert restored["settings"]["quality"] == "best"
    assert restored["favorites"] == []


def test_load_config_empty_file_raises_json_decode_falls_back_to_defaults(
    temp_config_dir: Path,
) -> None:
    temp_config_dir.write_text("")
    config = load_config()
    assert config["settings"]["quality"] == "best"
    assert config["favorites"] == []


def test_load_config_logs_warning_on_corrupt_json(
    temp_config_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    temp_config_dir.write_text("{bad}")
    with caplog.at_level(logging.WARNING, logger="core.storage"):
        load_config()
    assert any("corrupt" in r.message.lower() or "Corrupt" in r.message for r in caplog.records)


def test_load_config_coerces_string_int_to_int(temp_config_dir: Path) -> None:
    cfg = json.loads(temp_config_dir.read_text())
    cfg["settings"]["refresh_interval"] = "30"
    cfg["settings"]["player_height"] = "400"
    temp_config_dir.write_text(json.dumps(cfg))
    config = load_config()
    assert config["settings"]["refresh_interval"] == 30
    assert isinstance(config["settings"]["refresh_interval"], int)
    assert config["settings"]["player_height"] == 400


def test_load_config_invalid_int_string_falls_back_to_default(
    temp_config_dir: Path,
) -> None:
    cfg = json.loads(temp_config_dir.read_text())
    cfg["settings"]["refresh_interval"] = "banana"
    temp_config_dir.write_text(json.dumps(cfg))
    config = load_config()
    assert config["settings"]["refresh_interval"] == DEFAULT_SETTINGS["refresh_interval"]


def test_save_config_logs_error_on_permission_denied(
    temp_config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    original_open = open

    def failing_open(path, mode="r", **kw):  # type: ignore[override]
        if "w" in str(mode):
            raise PermissionError("read-only filesystem")
        return original_open(path, mode, **kw)

    monkeypatch.setattr("builtins.open", failing_open)
    with caplog.at_level(logging.ERROR, logger="core.storage"):
        save_config(DEFAULT_CONFIG)  # must not raise
    assert any(
        "Cannot save" in r.message or "Permission" in r.message or "permission" in r.message
        for r in caplog.records
    )
