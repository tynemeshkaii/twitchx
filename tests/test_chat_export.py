"""Phase 6 / P1-11 — chat export is written by Python, not by <a download>.

WKWebView ignores `<a download>` unless ALLOW_DOWNLOADS is enabled, so the old
blob route wrote nothing while the UI reported success.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from core.constants import WATCH_STATS_DB_NAME
from ui.api import TwitchXApi

UI_JS = Path(__file__).parent.parent / "ui" / "js"


def _payload(calls: list[str], fn_name: str) -> dict:
    for call in calls:
        match = re.match(rf"window\.{fn_name}\((.*)\)$", call, re.DOTALL)
        if match:
            return json.loads(match.group(1))
    raise AssertionError(f"No window.{fn_name}(...) call in {calls}")


def test_save_chat_log_writes_file_and_reports_path(
    temp_config_dir, run_sync, capture_eval_js, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / "Downloads").mkdir()

    api = TwitchXApi()
    api._eval_js = capture_eval_js
    api.save_chat_log("twitchx-chat-shroud.txt", "[12:00] shroud: hello")

    result = _payload(capture_eval_js.calls, "onChatLogSaved")
    assert result["ok"] is True
    written = Path(result["path"])
    assert written.parent == tmp_path / "Downloads"
    assert written.read_text(encoding="utf-8") == "[12:00] shroud: hello"


def test_save_chat_log_never_escapes_the_target_directory(
    temp_config_dir, run_sync, capture_eval_js, tmp_path, monkeypatch
):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / "Downloads").mkdir()

    api = TwitchXApi()
    api._eval_js = capture_eval_js
    api.save_chat_log("../../etc/passwd", "x")

    result = _payload(capture_eval_js.calls, "onChatLogSaved")
    assert result["ok"] is True
    written = Path(result["path"])
    assert written.parent == tmp_path / "Downloads"
    assert written.name == "passwd.txt"


def test_save_chat_log_does_not_overwrite(
    temp_config_dir, run_sync, capture_eval_js, tmp_path, monkeypatch
):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "log.txt").write_text("first", encoding="utf-8")

    api = TwitchXApi()
    api._eval_js = capture_eval_js
    api.save_chat_log("log.txt", "second")

    result = _payload(capture_eval_js.calls, "onChatLogSaved")
    assert Path(result["path"]).name == "log-1.txt"
    assert (downloads / "log.txt").read_text(encoding="utf-8") == "first"


def test_save_chat_log_falls_back_to_config_dir(
    temp_config_dir, run_sync, capture_eval_js, tmp_path, monkeypatch
):
    """No ~/Downloads (locked-down account): still write somewhere real.

    temp_config_dir already redirects core.storage.CONFIG_DIR, so the fallback
    must resolve it at call time — otherwise this test writes into the real
    ~/.config/twitchx.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "nonexistent")

    api = TwitchXApi()
    api._eval_js = capture_eval_js
    api.save_chat_log("log.json", "[]")

    result = _payload(capture_eval_js.calls, "onChatLogSaved")
    assert result["ok"] is True
    written = Path(result["path"])
    assert written.exists()
    assert written.parent == temp_config_dir.parent, written


def test_js_no_longer_uses_anchor_download() -> None:
    chat_js = (UI_JS / "chat.js").read_text(encoding="utf-8")
    assert "a.download" not in chat_js
    assert "createObjectURL" not in chat_js
    assert "TwitchX.api.save_chat_log(filename, content);" in chat_js
    callbacks = (UI_JS / "callbacks.js").read_text(encoding="utf-8")
    assert "window.onChatLogSaved = function(result)" in callbacks


def test_api_keeps_all_state_inside_the_configured_dir(temp_config_dir) -> None:
    """Binding CONFIG_DIR at import time made every TwitchXApi() open the real
    watch-stats DB — tests wrote fake sessions into the user's statistics."""
    api = TwitchXApi()
    db_path = Path(api._watch_stats._db_path)
    assert db_path.parent == temp_config_dir.parent, db_path
    assert db_path.name == WATCH_STATS_DB_NAME
