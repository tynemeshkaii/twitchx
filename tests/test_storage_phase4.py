"""Audit phase 4: config/cache storage reliability (#14, #15)."""

from __future__ import annotations

import copy
import json
import stat
import threading
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from core import storage
from core.storage import (
    DEFAULT_CONFIG,
    DEFAULT_SETTINGS,
    load_browse_cache,
    load_config,
    save_config,
    update_browse_cache,
    update_config,
)
from ui.api import TwitchXApi


def _payloads(calls: list[str], callback: str) -> list[Any]:
    prefix = f"window.{callback}("
    return [json.loads(c[len(prefix) : -1]) for c in calls if c.startswith(prefix)]


def _backups(config_file: Path) -> list[Path]:
    return sorted(config_file.parent.glob(f"{config_file.name}.corrupt-*"))


@pytest.fixture(autouse=True)
def _reset_recovery_flag() -> Any:
    storage.last_recovery_backup = None
    yield
    storage.last_recovery_backup = None


# ── 4.1 Mutable default aliasing ────────────────────────────────


class TestDefaultAliasing:
    def test_fresh_config_does_not_alias_defaults(self, temp_config_dir: Path) -> None:
        pristine_config = copy.deepcopy(DEFAULT_CONFIG)
        pristine_settings = copy.deepcopy(DEFAULT_SETTINGS)
        temp_config_dir.unlink()

        cfg = load_config()
        cfg["favorites"].append({"platform": "twitch", "login": "x"})
        cfg["settings"]["keyboard_shortcuts"]["refresh"] = "z"
        cfg["settings"]["chat_block_list"].append("spam")
        cfg["platforms"]["twitch"]["client_id"] = "leak"

        assert pristine_config == DEFAULT_CONFIG
        assert pristine_settings == DEFAULT_SETTINGS

        temp_config_dir.unlink()
        again = load_config()
        assert again["favorites"] == []
        assert again["settings"]["keyboard_shortcuts"]["refresh"] == "r"
        assert again["settings"]["chat_block_list"] == []
        assert again["platforms"]["twitch"]["client_id"] == ""

    def test_missing_nested_keys_do_not_alias_defaults(
        self, temp_config_dir: Path
    ) -> None:
        temp_config_dir.write_text(json.dumps({"platforms": {}, "settings": {}}))
        cfg = load_config()
        cfg["settings"]["keyboard_shortcuts"]["mute"] = "q"
        cfg["settings"]["multistream_presets"].append("extra")
        assert DEFAULT_SETTINGS["keyboard_shortcuts"]["mute"] == "m"
        assert "extra" not in DEFAULT_SETTINGS["multistream_presets"]

    def test_default_config_does_not_share_with_default_settings(self) -> None:
        assert DEFAULT_CONFIG["settings"] is not DEFAULT_SETTINGS
        assert (
            DEFAULT_CONFIG["settings"]["keyboard_shortcuts"]
            is not DEFAULT_SETTINGS["keyboard_shortcuts"]
        )
        assert (
            DEFAULT_CONFIG["settings"]["chat_block_list"]
            is not DEFAULT_SETTINGS["chat_block_list"]
        )

    def test_update_config_on_fresh_dir_does_not_mutate_defaults(
        self, temp_config_dir: Path
    ) -> None:
        temp_config_dir.unlink()
        update_config(lambda c: c["favorites"].append({"login": "a"}))
        assert DEFAULT_CONFIG["favorites"] == []

    def test_v1_migration_does_not_alias_defaults(self, temp_config_dir: Path) -> None:
        temp_config_dir.write_text(json.dumps({"quality": "720p", "favorites": ["a"]}))
        cfg = load_config()
        cfg["settings"]["keyboard_shortcuts"]["pip"] = "x"
        assert DEFAULT_SETTINGS["keyboard_shortcuts"]["pip"] == "p"


# ── 4.2 Corrupt config backup ───────────────────────────────────


CORRUPTIONS: list[tuple[str, bytes]] = [
    ("json", b"{"),
    ("unicode", b'{"a": "\xff\xfe"}'),
    ("list", b"[]"),
    ("null", b"null"),
    ("string", b'"x"'),
]


class TestCorruptConfig:
    @pytest.mark.parametrize(
        ("kind", "raw"), CORRUPTIONS, ids=[c[0] for c in CORRUPTIONS]
    )
    def test_corruption_is_backed_up(
        self, temp_config_dir: Path, kind: str, raw: bytes
    ) -> None:
        temp_config_dir.write_bytes(raw)
        cfg = load_config()

        assert cfg["favorites"] == []
        assert cfg["settings"]["quality"] == "best"
        backups = _backups(temp_config_dir)
        assert len(backups) == 1
        assert backups[0].read_bytes() == raw
        assert storage.last_recovery_backup == backups[0]
        assert json.loads(temp_config_dir.read_text())["settings"]["quality"] == "best"

    def test_os_error_on_read_is_backed_up(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_open = open
        target = str(temp_config_dir)
        state = {"failed": False}

        def flaky_open(path: Any, mode: str = "r", *args: Any, **kw: Any) -> Any:
            if str(path) == target and "r" in mode and not state["failed"]:
                state["failed"] = True
                raise OSError("I/O error")
            return real_open(path, mode, *args, **kw)

        monkeypatch.setattr("builtins.open", flaky_open)
        cfg = load_config()
        assert cfg["settings"]["quality"] == "best"
        assert len(_backups(temp_config_dir)) == 1

    def test_at_most_three_backups_kept(self, temp_config_dir: Path) -> None:
        for _ in range(5):
            temp_config_dir.write_text("{")
            load_config()
        assert len(_backups(temp_config_dir)) <= 3

    def test_recovery_backup_is_consumed_once(self, temp_config_dir: Path) -> None:
        temp_config_dir.write_text("{")
        load_config()
        first = storage.consume_recovery_backup()
        assert first is not None
        assert storage.consume_recovery_backup() is None

    def test_push_config_reports_recovery(
        self, temp_config_dir: Path, run_sync: Any
    ) -> None:
        temp_config_dir.write_text("{")
        api = TwitchXApi()
        calls: list[str] = []
        api._eval_js = calls.append  # type: ignore[method-assign]
        api.push_config()
        statuses = _payloads(calls, "onStatusUpdate")
        assert any("corrupted" in s["text"] for s in statuses)
        assert any(".corrupt-" in s["text"] for s in statuses)
        calls.clear()
        api.push_config()
        assert not _payloads(calls, "onStatusUpdate")


# ── 4.3 Permissions and concurrent writes ───────────────────────


class TestSecureWrites:
    def test_saved_config_is_owner_only(self, temp_config_dir: Path) -> None:
        temp_config_dir.chmod(0o644)
        save_config(DEFAULT_CONFIG)
        assert stat.S_IMODE(temp_config_dir.stat().st_mode) == 0o600

    def test_no_tmp_files_left_behind(self, temp_config_dir: Path) -> None:
        save_config(DEFAULT_CONFIG)
        assert not list(temp_config_dir.parent.glob("*.tmp"))

    def test_failed_write_removes_tmp(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*_a: Any, **_kw: Any) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(storage.os, "replace", boom)
        save_config(DEFAULT_CONFIG)  # must not raise
        assert not list(temp_config_dir.parent.glob("*.tmp"))

    def test_concurrent_update_config(self, temp_config_dir: Path) -> None:
        def bump(cfg: dict[str, Any]) -> None:
            settings = cfg["settings"]
            settings["test_counter"] = settings.get("test_counter", 0) + 1

        threads = [
            threading.Thread(target=update_config, args=(bump,)) for _ in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        stored = json.loads(temp_config_dir.read_text())
        assert stored["settings"]["test_counter"] == 20

    def test_ensure_config_permissions(self, temp_config_dir: Path) -> None:
        temp_config_dir.chmod(0o644)
        temp_config_dir.parent.chmod(0o755)
        storage.ensure_config_permissions()
        assert stat.S_IMODE(temp_config_dir.stat().st_mode) == 0o600
        assert stat.S_IMODE(temp_config_dir.parent.stat().st_mode) == 0o700


# ── 4.4 Settings type coercion ──────────────────────────────────


class TestSettingsCoercion:
    def test_wrong_types_reset_to_defaults(self) -> None:
        cfg: dict[str, Any] = {
            "settings": {
                **copy.deepcopy(DEFAULT_SETTINGS),
                "chat_block_list": "x",
                "theme": 5,
                "keyboard_shortcuts": [],
                "pip_enabled": "yes",
            }
        }
        changed = storage._coerce_settings_types(cfg)
        s = cfg["settings"]
        assert changed is True
        assert s["chat_block_list"] == []
        assert s["theme"] == "dark"
        assert s["keyboard_shortcuts"] == DEFAULT_SETTINGS["keyboard_shortcuts"]
        assert s["keyboard_shortcuts"] is not DEFAULT_SETTINGS["keyboard_shortcuts"]
        assert s["pip_enabled"] is False

    def test_shortcuts_keep_valid_and_fill_missing(self) -> None:
        cfg: dict[str, Any] = {
            "settings": {
                **copy.deepcopy(DEFAULT_SETTINGS),
                "keyboard_shortcuts": {"refresh": "x", "mute": 7, "bogus": "b"},
            }
        }
        assert storage._coerce_settings_types(cfg) is True
        shortcuts = cfg["settings"]["keyboard_shortcuts"]
        assert shortcuts["refresh"] == "x"
        assert shortcuts["mute"] == "m"
        assert "bogus" not in shortcuts
        assert set(shortcuts) == set(DEFAULT_SETTINGS["keyboard_shortcuts"])

    def test_int_in_bool_slot_is_left_alone(self) -> None:
        cfg: dict[str, Any] = {
            "settings": {**copy.deepcopy(DEFAULT_SETTINGS), "pip_enabled": 1}
        }
        assert storage._coerce_settings_types(cfg) is False
        assert cfg["settings"]["pip_enabled"] == 1

    def test_valid_settings_unchanged(self) -> None:
        cfg: dict[str, Any] = {"settings": copy.deepcopy(DEFAULT_SETTINGS)}
        assert storage._coerce_settings_types(cfg) is False

    def test_load_config_persists_coercion(self, temp_config_dir: Path) -> None:
        raw = json.loads(temp_config_dir.read_text())
        raw["settings"]["theme"] = 5
        temp_config_dir.write_text(json.dumps(raw))
        assert load_config()["settings"]["theme"] == "dark"
        assert json.loads(temp_config_dir.read_text())["settings"]["theme"] == "dark"


# ── 4.5 Browse cache ────────────────────────────────────────────


class TestBrowseCache:
    def test_parallel_updates_keep_both_slots(self, temp_config_dir: Path) -> None:
        barrier = threading.Barrier(2)

        def writer(slot: str) -> None:
            def fn(cache: dict[str, Any]) -> None:
                cache[slot] = {"data": [], "fetched_at": 1.0}

            barrier.wait()
            for _ in range(20):
                update_browse_cache(fn)

        threads = [
            threading.Thread(target=writer, args=(s,)) for s in ("slot_a", "slot_b")
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        cache = load_browse_cache()
        assert "slot_a" in cache
        assert "slot_b" in cache

    @pytest.fixture
    def api(self, temp_config_dir: Path, run_sync: Any) -> TwitchXApi:
        platforms = {
            name: {**conf, "enabled": True}
            for name, conf in DEFAULT_CONFIG["platforms"].items()
        }
        platforms["twitch"].update(client_id="fakeid", client_secret="fakesecret")
        save_config({**DEFAULT_CONFIG, "platforms": platforms})
        instance = TwitchXApi()
        calls: list[str] = []
        instance._eval_js = calls.append  # type: ignore[method-assign]
        instance.calls = calls  # type: ignore[attr-defined]
        return instance

    def test_categories_callback_survives_cache_write_error(
        self, api: TwitchXApi
    ) -> None:
        cats = [
            {
                "platform": "twitch",
                "category_id": "1",
                "name": "Chess",
                "box_art_url": "",
                "viewers": 0,
            }
        ]
        with (
            patch.object(api._twitch, "get_categories", AsyncMock(return_value=cats)),
            patch.object(api._kick, "get_categories", AsyncMock(return_value=[])),
            patch("ui.api.data.YOUTUBE_ENABLED", False),
            patch("core.storage.save_browse_cache", side_effect=OSError("ro")),
        ):
            api._data._fetch_browse_categories("all")
        payload = _payloads(api.calls, "onBrowseCategories")[-1]  # type: ignore[attr-defined]
        assert [c["name"] for c in payload["items"]] == ["Chess"]

    def test_top_streams_callback_survives_cache_write_error(
        self, api: TwitchXApi
    ) -> None:
        streams = [{"login": "a", "platform": "twitch", "viewers": 5}]
        with (
            patch.object(
                api._twitch, "get_top_streams", AsyncMock(return_value=streams)
            ),
            patch("core.storage.save_browse_cache", side_effect=OSError("ro")),
        ):
            api._data._fetch_browse_top_streams("Chess", {"twitch": "1"}, "all")
        payload = _payloads(api.calls, "onBrowseTopStreams")[-1]  # type: ignore[attr-defined]
        assert payload["streams"] == streams

    def test_categories_callback_sent_on_unexpected_error(
        self, api: TwitchXApi
    ) -> None:
        with patch.object(api._data, "_get_platform", side_effect=RuntimeError("boom")):
            api._data._fetch_browse_categories("twitch")
        payload = _payloads(api.calls, "onBrowseCategories")[-1]  # type: ignore[attr-defined]
        assert payload["items"] == []
        assert payload["errors"]

    def test_top_streams_callback_sent_on_unexpected_error(
        self, api: TwitchXApi
    ) -> None:
        with patch.object(api._data, "_get_platform", side_effect=RuntimeError("boom")):
            api._data._fetch_browse_top_streams("Chess", {"twitch": "1"}, "twitch")
        payload = _payloads(api.calls, "onBrowseTopStreams")[-1]  # type: ignore[attr-defined]
        assert payload["streams"] == []
        assert payload["errors"]

    def test_cache_read_error_still_fetches(self, api: TwitchXApi) -> None:
        streams = [{"login": "a", "platform": "twitch", "viewers": 5}]
        with (
            patch.object(
                api._twitch, "get_top_streams", AsyncMock(return_value=streams)
            ),
            patch("ui.api.data.load_browse_cache", side_effect=OSError("eio")),
        ):
            api._data._fetch_browse_top_streams("Chess", {"twitch": "1"}, "twitch")
        payload = _payloads(api.calls, "onBrowseTopStreams")[-1]  # type: ignore[attr-defined]
        assert payload["streams"] == streams
        assert load_browse_cache()["top_streams_twitch_1"]["data"] == streams
