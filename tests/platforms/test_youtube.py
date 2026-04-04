from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path
from typing import Any

import pytest


# ── Helpers ───────────────────────────────────────────────────


def _setup_config(tmp_path: Path, yt_overrides: dict[str, Any]) -> None:
    """Write a minimal config.json under tmp_path for testing."""
    from core.storage import DEFAULT_PLATFORM_YOUTUBE

    yt = {**DEFAULT_PLATFORM_YOUTUBE, **yt_overrides}
    config = {"platforms": {"twitch": {}, "kick": {}, "youtube": yt}, "favorites": [], "settings": {}}
    config_dir = tmp_path / ".config" / "twitchx"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(json.dumps(config))


def _yt_conf(tmp_path: Path) -> dict[str, Any]:
    """Read youtube config section from tmp_path config."""
    config_file = tmp_path / ".config" / "twitchx" / "config.json"
    config = json.loads(config_file.read_text())
    return config.get("platforms", {}).get("youtube", {})


def _make_update_fn(tmp_path: Path):
    """Return an update function that writes to tmp_path config."""

    def _update(used: int, date_str: str) -> None:
        config_file = tmp_path / ".config" / "twitchx" / "config.json"
        config = json.loads(config_file.read_text())
        yt = config.get("platforms", {}).get("youtube", {})
        yt["daily_quota_used"] = used
        yt["quota_reset_date"] = date_str
        config_file.write_text(json.dumps(config))

    return _update


# ── QuotaTracker ──────────────────────────────────────────────


class TestQuotaTracker:
    def test_initial_remaining_is_full_budget(self, tmp_path: Path) -> None:
        _setup_config(tmp_path, {})
        from core.platforms.youtube import QuotaTracker

        qt = QuotaTracker(lambda: _yt_conf(tmp_path), _make_update_fn(tmp_path))
        assert qt.remaining() == 10_000

    def test_use_decrements_remaining(self, tmp_path: Path) -> None:
        _setup_config(tmp_path, {})
        from core.platforms.youtube import QuotaTracker

        qt = QuotaTracker(lambda: _yt_conf(tmp_path), _make_update_fn(tmp_path))
        qt.use(100)
        assert qt.remaining() == 9_900

    def test_resets_on_new_day(self, tmp_path: Path) -> None:
        _setup_config(
            tmp_path,
            {"daily_quota_used": 5000, "quota_reset_date": "2025-01-01"},
        )
        from core.platforms.youtube import QuotaTracker

        qt = QuotaTracker(lambda: _yt_conf(tmp_path), _make_update_fn(tmp_path))
        # Today is not 2025-01-01, so remaining should be full
        assert qt.remaining() == 10_000

    def test_same_day_preserves_usage(self, tmp_path: Path) -> None:
        today = date.today().isoformat()
        _setup_config(
            tmp_path,
            {"daily_quota_used": 3000, "quota_reset_date": today},
        )
        from core.platforms.youtube import QuotaTracker

        qt = QuotaTracker(lambda: _yt_conf(tmp_path), _make_update_fn(tmp_path))
        assert qt.remaining() == 7_000

    def test_can_use_returns_false_when_exhausted(self, tmp_path: Path) -> None:
        today = date.today().isoformat()
        _setup_config(
            tmp_path,
            {"daily_quota_used": 10_000, "quota_reset_date": today},
        )
        from core.platforms.youtube import QuotaTracker

        qt = QuotaTracker(lambda: _yt_conf(tmp_path), _make_update_fn(tmp_path))
        assert not qt.can_use(1)

    def test_can_use_returns_true_when_budget_available(self, tmp_path: Path) -> None:
        _setup_config(tmp_path, {})
        from core.platforms.youtube import QuotaTracker

        qt = QuotaTracker(lambda: _yt_conf(tmp_path), _make_update_fn(tmp_path))
        assert qt.can_use(100)
