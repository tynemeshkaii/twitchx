"""Phase 1 — config is pushed from Python, never read synchronously by JS."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ui.api import TwitchXApi

UI_JS = Path(__file__).parent.parent / "ui" / "js"


def _payload(calls: list[str], fn_name: str) -> dict[str, Any]:
    """Extract the JSON argument of the first window.<fn_name>(...) call."""
    for call in calls:
        match = re.match(rf"window\.{fn_name}\((.*)\)$", call, re.DOTALL)
        if match:
            return json.loads(match.group(1))
    raise AssertionError(f"No window.{fn_name}(...) call in {calls}")


def test_push_config_emits_on_config_loaded(temp_config_dir, capture_eval_js):
    api = TwitchXApi()
    api._eval_js = capture_eval_js

    api.push_config()

    capture_eval_js.assert_any("onConfigLoaded")
    snapshot = _payload(capture_eval_js.calls, "onConfigLoaded")
    # get_config payload
    assert "favorites" in snapshot
    assert "favorites_meta" in snapshot
    assert snapshot["has_credentials"] is True
    # settings payload for the Settings modal
    assert snapshot["settings"]["quality"] == "best"
    assert "theme" in snapshot["settings"]
    assert "keyboard_shortcuts" in snapshot["settings"]
    # version footer
    assert re.match(r"^\d+\.\d+", snapshot["version"])


def test_request_config_pushes_snapshot(temp_config_dir, capture_eval_js):
    api = TwitchXApi()
    api._eval_js = capture_eval_js

    api.request_config()

    capture_eval_js.assert_any("onConfigLoaded")


def test_snapshot_carries_restored_twitch_profile(
    config_with_twitch_auth, capture_eval_js
):
    cfg = json.loads(config_with_twitch_auth.read_text())
    cfg["platforms"]["twitch"].update(
        {
            "user_id": "1234",
            "user_login": "tester",
            "user_display_name": "Tester",
        }
    )
    config_with_twitch_auth.write_text(json.dumps(cfg))

    api = TwitchXApi()
    api._eval_js = capture_eval_js
    api.push_config()

    snapshot = _payload(capture_eval_js.calls, "onConfigLoaded")
    assert snapshot["current_user"]["login"] == "tester"
    assert snapshot["current_user"]["display_name"] == "Tester"


def test_save_settings_pushes_fresh_config(temp_config_dir, capture_eval_js):
    api = TwitchXApi()
    api._eval_js = capture_eval_js
    api.stop_polling()

    api.save_settings(json.dumps({"quality": "720p", "theme": "light"}))
    api.stop_polling()

    capture_eval_js.assert_any("onConfigLoaded")
    capture_eval_js.assert_any("onSettingsSaved")
    snapshot = _payload(capture_eval_js.calls, "onConfigLoaded")
    assert snapshot["settings"]["quality"] == "720p"
    assert snapshot["settings"]["theme"] == "light"


def test_request_watch_statistics_pushes_result(
    temp_config_dir, run_sync, capture_eval_js
):
    api = TwitchXApi()
    api._eval_js = capture_eval_js

    api.request_watch_statistics("all")

    capture_eval_js.assert_any("onWatchStatistics")
    payload = _payload(capture_eval_js.calls, "onWatchStatistics")
    assert payload["ok"] is True
    assert payload["period"] == "all"
    assert "today" in payload["stats"]


def test_js_never_reads_config_synchronously():
    """No JS module may call the Promise-returning config getters."""
    offenders = []
    for path in sorted(UI_JS.glob("*.js")):
        source = path.read_text(encoding="utf-8")
        for name in (
            "get_config",
            "get_full_config_for_settings",
            "get_watch_statistics",
            "get_version",
        ):
            if f"api.{name}(" in source:
                offenders.append(f"{path.name}: {name}")
    assert offenders == []
