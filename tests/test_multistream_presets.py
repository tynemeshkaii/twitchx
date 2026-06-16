from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from core.storage import load_config, save_config
from ui.api import TwitchXApi


def test_get_multistream_presets_returns_defaults(temp_config_dir: Path) -> None:
    api = TwitchXApi()
    result = api.get_multistream_presets()
    assert result["active"] == 0
    assert result["presets"] == ["grid", "focus-left", "rows", "columns"]


def test_set_multistream_preset_persists_active_index(
    temp_config_dir: Path,
) -> None:
    api = TwitchXApi()
    api._eval_js = MagicMock()

    api.set_multistream_preset(2)

    cfg = load_config()
    assert cfg["settings"]["multistream_active_preset"] == 2
    api._eval_js.assert_called_once()
    call_arg = api._eval_js.call_args[0][0]
    assert "onMultistreamPresetChanged" in call_arg
    assert '"active": 2' in call_arg


def test_set_multistream_preset_ignores_invalid_index(
    temp_config_dir: Path,
) -> None:
    api = TwitchXApi()
    api._eval_js = MagicMock()

    api.set_multistream_preset(10)

    cfg = load_config()
    assert cfg["settings"]["multistream_active_preset"] == 0
    api._eval_js.assert_not_called()


def test_set_multistream_preset_clamps_negative_index(
    temp_config_dir: Path,
) -> None:
    api = TwitchXApi()
    api._eval_js = MagicMock()

    api.set_multistream_preset(-1)

    cfg = load_config()
    assert cfg["settings"]["multistream_active_preset"] == 0
    api._eval_js.assert_not_called()


def test_get_multistream_presets_handles_corrupted_settings(
    temp_config_dir: Path,
) -> None:
    cfg = json.loads(temp_config_dir.read_text())
    cfg["settings"]["multistream_presets"] = "not-a-list"
    cfg["settings"]["multistream_active_preset"] = "invalid"
    save_config(cfg)

    api = TwitchXApi()
    result = api.get_multistream_presets()
    assert result["active"] == 0
    assert result["presets"] == ["grid", "focus-left", "rows", "columns"]
