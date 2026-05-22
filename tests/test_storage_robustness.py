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


def test_load_config_empty_file_falls_back_to_defaults(
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
