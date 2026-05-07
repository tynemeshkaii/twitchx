from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.constants import WATCH_STATS_SESSION_CLEANUP_DAYS

logger = logging.getLogger(__name__)


class WatchStatsDB:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        try:
            with self._lock, sqlite3.connect(self._db_path) as conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS watch_sessions (
                        id           INTEGER PRIMARY KEY AUTOINCREMENT,
                        channel      TEXT NOT NULL,
                        platform     TEXT NOT NULL,
                        display_name TEXT DEFAULT '',
                        title        TEXT DEFAULT '',
                        started_at   TEXT NOT NULL,
                        ended_at     TEXT,
                        duration_sec INTEGER DEFAULT 0,
                        stream_type  TEXT DEFAULT 'live'
                    );

                    CREATE INDEX IF NOT EXISTS idx_sessions_started
                        ON watch_sessions(started_at);

                    CREATE INDEX IF NOT EXISTS idx_sessions_channel
                        ON watch_sessions(channel, platform);

                    CREATE INDEX IF NOT EXISTS idx_sessions_active
                        ON watch_sessions(ended_at) WHERE ended_at IS NULL;

                    CREATE TABLE IF NOT EXISTS daily_summary (
                        date             TEXT NOT NULL,
                        platform         TEXT NOT NULL,
                        total_sec        INTEGER DEFAULT 0,
                        streams_count    INTEGER DEFAULT 0,
                        unique_channels  INTEGER DEFAULT 0,
                        PRIMARY KEY (date, platform)
                    );
                """)
        except sqlite3.Error as e:
            logger.error("Failed to initialize watch stats DB: %s", e)

    def start_session(
        self,
        channel: str,
        platform: str,
        display_name: str = "",
        title: str = "",
        stream_type: str = "live",
    ) -> int | None:
        now = datetime.now(UTC).isoformat()
        try:
            with self._lock, sqlite3.connect(self._db_path) as conn:
                cur = conn.execute(
                    """INSERT INTO watch_sessions
                       (channel, platform, display_name, title, started_at, stream_type)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (channel, platform, display_name, title, now, stream_type),
                )
                conn.commit()
                last_id = cur.lastrowid
                if last_id is None:
                    raise RuntimeError("Failed to insert watch session")
                return last_id
        except (sqlite3.Error, RuntimeError) as e:
            logger.error("start_session failed: %s", e)
            return None

    def end_session(self, session_id: int) -> None:
        try:
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                try:
                    cur = conn.execute(
                        "SELECT started_at, channel, platform FROM watch_sessions WHERE id = ?",
                        (session_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        logger.warning("end_session: session %s not found", session_id)
                        return

                    started_at_iso, channel, platform = row
                    started = datetime.fromisoformat(started_at_iso)
                    ended = datetime.now(UTC)
                    duration = max(0, int((ended - started).total_seconds()))

                    conn.execute(
                        """UPDATE watch_sessions
                           SET ended_at = ?, duration_sec = ?
                           WHERE id = ?""",
                        (ended.isoformat(), duration, session_id),
                    )

                    date_key = started.strftime("%Y-%m-%d")
                    conn.execute(
                        """INSERT INTO daily_summary (date, platform, total_sec, streams_count, unique_channels)
                           VALUES (?, ?, ?, ?, 1)
                           ON CONFLICT(date, platform) DO UPDATE SET
                               total_sec = total_sec + ?,
                               streams_count = streams_count + 1,
                               unique_channels = (
                                   SELECT COUNT(DISTINCT channel)
                                   FROM watch_sessions
                                   WHERE date(started_at) = ? AND platform = ?
                               )""",
                        (date_key, platform, duration, 1, duration, date_key, platform),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except sqlite3.Error as e:
            logger.error("end_session failed for session %s: %s", session_id, e)

    def get_today_stats(self) -> dict[str, Any]:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """SELECT
                           COALESCE(SUM(duration_sec), 0) as total_sec,
                           COUNT(*) as streams_count,
                           COUNT(DISTINCT channel) as unique_channels
                       FROM watch_sessions
                       WHERE date(started_at) = ?""",
                    (today,),
                ).fetchone()

                result: dict[str, Any] = dict(row)

                cur = conn.execute(
                    """SELECT platform,
                              COALESCE(SUM(duration_sec), 0) as total_sec,
                              COUNT(*) as streams_count
                       FROM watch_sessions
                       WHERE date(started_at) = ?
                       GROUP BY platform""",
                    (today,),
                )
                result["per_platform"] = [dict(r) for r in cur.fetchall()]

                return result
        except sqlite3.Error as e:
            logger.error("get_today_stats failed: %s", e)
            return {"total_sec": 0, "streams_count": 0, "unique_channels": 0, "per_platform": []}

    def get_weekly_stats(self) -> list[dict[str, Any]]:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    """SELECT date, platform, total_sec, streams_count, unique_channels
                       FROM daily_summary
                       WHERE date(date) >= date(?, '-7 days')
                       ORDER BY date DESC, platform""",
                    (today,),
                )
                return [dict(r) for r in cur.fetchall()]
        except sqlite3.Error as e:
            logger.error("get_weekly_stats failed: %s", e)
            return []

    def get_total_stats(self) -> dict[str, Any]:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """SELECT
                           COALESCE(SUM(duration_sec), 0) as total_sec,
                           COUNT(*) as total_sessions,
                           COUNT(DISTINCT channel) as unique_channels
                       FROM watch_sessions"""
                ).fetchone()
                result: dict[str, Any] = dict(row)

                result["total_hours"] = result["total_sec"] // 3600
                result["total_minutes"] = (result["total_sec"] % 3600) // 60

                cur = conn.execute(
                    """SELECT platform,
                              COALESCE(SUM(duration_sec), 0) as total_sec,
                              COUNT(*) as streams_count
                       FROM watch_sessions
                       GROUP BY platform
                       ORDER BY total_sec DESC"""
                )
                result["per_platform"] = [dict(r) for r in cur.fetchall()]

                return result
        except sqlite3.Error as e:
            logger.error("get_total_stats failed: %s", e)
            return {
                "total_sec": 0, "total_sessions": 0, "unique_channels": 0,
                "total_hours": 0, "total_minutes": 0, "per_platform": [],
            }

    def get_top_channels(self, limit: int = 10) -> list[dict[str, Any]]:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    """SELECT channel, platform, display_name,
                              COALESCE(SUM(duration_sec), 0) as total_sec,
                              COUNT(*) as sessions_count,
                              MAX(started_at) as last_watched
                       FROM watch_sessions
                       GROUP BY channel, platform
                       ORDER BY total_sec DESC
                       LIMIT ?""",
                    (limit,),
                )
                return [dict(r) for r in cur.fetchall()]
        except sqlite3.Error as e:
            logger.error("get_top_channels failed: %s", e)
            return []

    def get_recent_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    """SELECT id, channel, platform, display_name, title,
                              started_at, ended_at, duration_sec, stream_type
                       FROM watch_sessions
                       ORDER BY started_at DESC
                       LIMIT ?""",
                    (limit,),
                )
                return [dict(r) for r in cur.fetchall()]
        except sqlite3.Error as e:
            logger.error("get_recent_sessions failed: %s", e)
            return []

    def get_active_session(self) -> dict[str, Any] | None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """SELECT id, channel, platform, display_name, title,
                              started_at, stream_type
                       FROM watch_sessions
                       WHERE ended_at IS NULL
                       ORDER BY started_at DESC
                       LIMIT 1"""
                ).fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error("get_active_session failed: %s", e)
            return None

    def cleanup_old_sessions(self, days: int = WATCH_STATS_SESSION_CLEANUP_DAYS) -> int:
        try:
            with self._lock, sqlite3.connect(self._db_path) as conn:
                now = datetime.now(UTC).strftime("%Y-%m-%d")
                cur = conn.execute(
                    """DELETE FROM watch_sessions
                       WHERE date(started_at) < date(?, ?)""",
                    (now, f"-{days} days"),
                )
                deleted = cur.rowcount

                conn.execute(
                    """DELETE FROM daily_summary
                       WHERE date < date(?, ?)""",
                    (now, f"-{days} days"),
                )
                conn.commit()
                return deleted
        except sqlite3.Error as e:
            logger.error("cleanup_old_sessions failed: %s", e)
            return 0

    def get_stats_for_period(self, period: str = "today") -> dict[str, Any]:
        result: dict[str, Any] = {}
        if period in ("today", "all"):
            result["today"] = self.get_today_stats()
        if period in ("weekly", "all"):
            result["weekly"] = self.get_weekly_stats()
        if period == "all":
            result["total"] = self.get_total_stats()
            result["top_channels"] = self.get_top_channels(10)
            result["recent_sessions"] = self.get_recent_sessions(20)
        return result
