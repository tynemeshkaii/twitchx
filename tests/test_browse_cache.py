from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

from core.storage import is_browse_slot_fresh, load_browse_cache, save_browse_cache


def test_load_browse_cache_returns_empty_when_file_missing(tmp_path: Path) -> None:
    with patch("core.storage.CONFIG_DIR", tmp_path):
        result = load_browse_cache()
    assert result == {}


def test_load_browse_cache_returns_data_when_file_exists(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    data = {"categories_twitch": {"data": [{"name": "Fortnite"}], "fetched_at": 1000.0}}
    (cache_dir / "browse_cache.json").write_text(json.dumps(data))
    with patch("core.storage.CONFIG_DIR", tmp_path):
        result = load_browse_cache()
    assert result == data


def test_load_browse_cache_returns_empty_on_corrupt_json(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "browse_cache.json").write_text("NOT_JSON{{{")
    with patch("core.storage.CONFIG_DIR", tmp_path):
        result = load_browse_cache()
    assert result == {}


def test_save_browse_cache_creates_dirs_and_writes(tmp_path: Path) -> None:
    data = {"categories_kick": {"data": [], "fetched_at": 9999.0}}
    with patch("core.storage.CONFIG_DIR", tmp_path):
        save_browse_cache(data)
    written = json.loads((tmp_path / "cache" / "browse_cache.json").read_text())
    assert written == data


def test_is_browse_slot_fresh_true_within_ttl() -> None:
    cache = {"categories_twitch": {"data": [], "fetched_at": time.time() - 100}}
    assert is_browse_slot_fresh(cache, "categories_twitch", ttl=600) is True


def test_is_browse_slot_fresh_false_when_expired() -> None:
    cache = {"categories_twitch": {"data": [], "fetched_at": time.time() - 700}}
    assert is_browse_slot_fresh(cache, "categories_twitch", ttl=600) is False


def test_is_browse_slot_fresh_false_when_slot_missing() -> None:
    assert is_browse_slot_fresh({}, "categories_twitch") is False
