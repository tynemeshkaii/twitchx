from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from core.watch_stats import WatchStatsDB


@pytest.fixture
def stats_db(tmp_path: Path) -> WatchStatsDB:
    return WatchStatsDB(str(tmp_path / "test_watch_stats.db"))


class TestWatchStatsDB:
    def _sid(self, sid: Any) -> int:
        assert sid is not None
        return sid

    def test_start_session_returns_id(self, stats_db: WatchStatsDB) -> None:
        sid = self._sid(stats_db.start_session("xqc", "twitch", display_name="xQc", title="Stream Title"))
        assert isinstance(sid, int)
        assert sid > 0

    def test_end_session_updates_duration(self, stats_db: WatchStatsDB) -> None:
        sid = self._sid(stats_db.start_session("xqc", "twitch", display_name="xQc"))
        stats_db.end_session(sid)
        sess = stats_db.get_recent_sessions(1)
        assert len(sess) == 1
        assert sess[0]["id"] == sid
        assert sess[0]["channel"] == "xqc"
        assert sess[0]["platform"] == "twitch"
        assert sess[0]["ended_at"] is not None
        assert sess[0]["duration_sec"] >= 0

    def test_end_session_unknown_id(self, stats_db: WatchStatsDB) -> None:
        stats_db.end_session(99999)

    def test_get_today_stats_empty(self, stats_db: WatchStatsDB) -> None:
        stats = stats_db.get_today_stats()
        assert stats["total_sec"] == 0
        assert stats["streams_count"] == 0
        assert stats["unique_channels"] == 0
        assert stats["per_platform"] == []

    def test_get_today_stats_after_session(self, stats_db: WatchStatsDB) -> None:
        sid = self._sid(stats_db.start_session("xqc", "twitch", display_name="xQc"))
        stats_db.end_session(sid)
        stats = stats_db.get_today_stats()
        assert stats["streams_count"] == 1
        assert stats["unique_channels"] == 1
        assert stats["total_sec"] >= 0

    def test_get_today_stats_multi_channel(self, stats_db: WatchStatsDB) -> None:
        s1 = self._sid(stats_db.start_session("xqc", "twitch", display_name="xQc"))
        s2 = self._sid(stats_db.start_session("forsen", "twitch", display_name="Forsen"))
        s3 = self._sid(stats_db.start_session("summit1g", "twitch", display_name="Summit"))
        stats_db.end_session(s1)
        stats_db.end_session(s2)
        stats_db.end_session(s3)
        stats = stats_db.get_today_stats()
        assert stats["streams_count"] == 3
        assert stats["unique_channels"] == 3

    def test_get_today_stats_per_platform(self, stats_db: WatchStatsDB) -> None:
        s1 = self._sid(stats_db.start_session("xqc", "twitch"))
        s2 = self._sid(stats_db.start_session("example", "kick"))
        stats_db.end_session(s1)
        stats_db.end_session(s2)
        stats = stats_db.get_today_stats()
        assert len(stats["per_platform"]) == 2
        platforms = {p["platform"] for p in stats["per_platform"]}
        assert platforms == {"twitch", "kick"}

    def test_daily_summary_updated(self, stats_db: WatchStatsDB) -> None:
        s1 = self._sid(stats_db.start_session("xqc", "twitch"))
        s2 = self._sid(stats_db.start_session("forsen", "twitch"))
        stats_db.end_session(s1)
        stats_db.end_session(s2)
        weekly = stats_db.get_weekly_stats()
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        today_rows = [r for r in weekly if r["date"] == today]
        assert len(today_rows) >= 1
        twitch_row = [r for r in today_rows if r["platform"] == "twitch"]
        assert len(twitch_row) > 0
        assert twitch_row[0]["streams_count"] == 2

    def test_total_stats(self, stats_db: WatchStatsDB) -> None:
        s1 = self._sid(stats_db.start_session("xqc", "twitch", display_name="xQc"))
        s2 = self._sid(stats_db.start_session("forsen", "twitch", display_name="Forsen"))
        stats_db.end_session(s1)
        stats_db.end_session(s2)
        total = stats_db.get_total_stats()
        assert total["total_sessions"] == 2
        assert total["unique_channels"] == 2
        assert total["total_hours"] >= 0

    def test_top_channels(self, stats_db: WatchStatsDB) -> None:
        s1 = self._sid(stats_db.start_session("xqc", "twitch", display_name="xQc"))
        s2 = self._sid(stats_db.start_session("xqc", "twitch", display_name="xQc"))
        s3 = self._sid(stats_db.start_session("forsen", "twitch", display_name="Forsen"))
        stats_db.end_session(s1)
        stats_db.end_session(s2)
        stats_db.end_session(s3)
        top = stats_db.get_top_channels(5)
        assert len(top) >= 2
        xqc = next(ch for ch in top if ch["channel"] == "xqc")
        forsen = next(ch for ch in top if ch["channel"] == "forsen")
        assert xqc["sessions_count"] == 2
        assert forsen["sessions_count"] == 1

    def test_recent_sessions_ordered(self, stats_db: WatchStatsDB) -> None:
        s1 = self._sid(stats_db.start_session("xqc", "twitch"))
        s2 = self._sid(stats_db.start_session("forsen", "twitch"))
        stats_db.end_session(s1)
        stats_db.end_session(s2)
        recent = stats_db.get_recent_sessions(10)
        assert len(recent) >= 2
        assert recent[0]["started_at"] >= recent[1]["started_at"]

    def test_get_active_session(self, stats_db: WatchStatsDB) -> None:
        sid = self._sid(stats_db.start_session("xqc", "twitch"))
        active = stats_db.get_active_session()
        assert active is not None
        assert active["id"] == sid
        assert active["channel"] == "xqc"
        stats_db.end_session(sid)
        active = stats_db.get_active_session()
        assert active is None

    def test_cleanup_old_sessions(self, stats_db: WatchStatsDB) -> None:
        s1 = self._sid(stats_db.start_session("old_channel", "twitch"))
        s2 = self._sid(stats_db.start_session("new_channel", "twitch"))
        stats_db.end_session(s1)
        stats_db.end_session(s2)
        deleted = stats_db.cleanup_old_sessions(0)
        assert deleted == 0
        recent = stats_db.get_recent_sessions(10)
        assert len(recent) == 2

    def test_get_stats_for_period_today(self, stats_db: WatchStatsDB) -> None:
        sid = self._sid(stats_db.start_session("xqc", "twitch"))
        stats_db.end_session(sid)
        result = stats_db.get_stats_for_period("today")
        assert "today" in result
        assert "weekly" not in result

    def test_get_stats_for_period_all(self, stats_db: WatchStatsDB) -> None:
        sid = self._sid(stats_db.start_session("xqc", "twitch"))
        stats_db.end_session(sid)
        result = stats_db.get_stats_for_period("all")
        assert "today" in result
        assert "weekly" in result
        assert "total" in result
        assert "top_channels" in result
        assert "recent_sessions" in result

    def test_multiple_platforms(self, stats_db: WatchStatsDB) -> None:
        s1 = self._sid(stats_db.start_session("twitch_streamer", "twitch"))
        s2 = self._sid(stats_db.start_session("kick_streamer", "kick"))
        s3 = self._sid(stats_db.start_session("yt_streamer", "youtube"))
        stats_db.end_session(s1)
        stats_db.end_session(s2)
        stats_db.end_session(s3)
        total = stats_db.get_total_stats()
        assert total["unique_channels"] == 3

    def test_cleanup_does_not_remove_recent(self, stats_db: WatchStatsDB) -> None:
        sid = self._sid(stats_db.start_session("current", "twitch"))
        stats_db.end_session(sid)
        deleted = stats_db.cleanup_old_sessions(days=30)
        assert deleted == 0
        recent = stats_db.get_recent_sessions(10)
        assert len(recent) == 1

    def test_cleanup_preserves_recent_daily_summary(self, stats_db: WatchStatsDB) -> None:
        with sqlite3.connect(stats_db._db_path) as conn:
            conn.execute(
                """INSERT INTO daily_summary
                   (date, platform, total_sec, streams_count, unique_channels)
                   VALUES (date('now', '-1 day'), 'twitch', 60, 1, 1)"""
            )
            conn.execute(
                """INSERT INTO daily_summary
                   (date, platform, total_sec, streams_count, unique_channels)
                   VALUES (date('now', '-120 day'), 'kick', 60, 1, 1)"""
            )

        stats_db.cleanup_old_sessions(days=90)
        weekly = stats_db.get_weekly_stats()
        assert any(row["platform"] == "twitch" for row in weekly)
        assert all(row["platform"] != "kick" for row in weekly)
