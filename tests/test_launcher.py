from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from core.launcher import _get_stream_url, launch_stream


class TestGetStreamUrl:
    @patch("core.launcher.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"https://example.com/stream.m3u8\n",
        )
        url, err = _get_stream_url("/usr/bin/streamlink", "https://twitch.tv/xqc", "best")
        assert url == "https://example.com/stream.m3u8"
        assert err == ""

    @patch("core.launcher.subprocess.run")
    def test_nonzero(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr=b"error: No streams found",
        )
        url, err = _get_stream_url("/usr/bin/streamlink", "https://twitch.tv/xqc", "best")
        assert url is None
        assert "No streams found" in err

    @patch("core.launcher.subprocess.run")
    def test_timeout(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="streamlink", timeout=15)
        url, err = _get_stream_url("/usr/bin/streamlink", "https://twitch.tv/xqc", "best")
        assert url is None
        assert "timed out" in err.lower()

    @patch("core.launcher.subprocess.run")
    def test_empty_output(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"",
        )
        url, err = _get_stream_url("/usr/bin/streamlink", "https://twitch.tv/xqc", "best")
        assert url is None
        assert "empty" in err.lower()


class TestLaunchStream:
    @patch("core.launcher.check_iina", return_value=None)
    @patch("core.launcher.check_streamlink", return_value=None)
    @patch("core.launcher.shutil.which", return_value="/usr/bin/streamlink")
    @patch("core.launcher._get_stream_url")
    @patch("core.launcher.subprocess.Popen")
    def test_quality_fallback(
        self,
        mock_popen: MagicMock,
        mock_get_url: MagicMock,
        mock_which: MagicMock,
        mock_check_sl: MagicMock,
        mock_check_iina: MagicMock,
    ) -> None:
        mock_get_url.side_effect = [
            (None, "quality not available"),
            ("https://example.com/best.m3u8", ""),
        ]
        result = launch_stream("xqc", "720p60")
        assert result.success is True
        assert mock_get_url.call_count == 2

    @patch("core.launcher.check_iina", return_value=None)
    @patch("core.launcher.check_streamlink", return_value="streamlink not found")
    def test_missing_streamlink(
        self,
        mock_check_sl: MagicMock,
        mock_check_iina: MagicMock,
    ) -> None:
        result = launch_stream("xqc", "best")
        assert result.success is False
        assert "not found" in result.message.lower()

    @patch("core.launcher.check_iina", return_value="IINA not found")
    @patch("core.launcher.check_streamlink", return_value=None)
    def test_missing_iina(
        self,
        mock_check_sl: MagicMock,
        mock_check_iina: MagicMock,
    ) -> None:
        result = launch_stream("xqc", "best")
        assert result.success is False
        assert "not found" in result.message.lower()

    @patch("core.launcher.check_iina", return_value=None)
    @patch("core.launcher.check_streamlink", return_value=None)
    @patch("core.launcher.shutil.which", return_value="/usr/bin/streamlink")
    @patch("core.launcher._get_stream_url")
    @patch("core.launcher.subprocess.Popen")
    def test_supports_platform_prefixed_channel_refs(
        self,
        mock_popen: MagicMock,
        mock_get_url: MagicMock,
        mock_which: MagicMock,
        mock_check_sl: MagicMock,
        mock_check_iina: MagicMock,
    ) -> None:
        mock_get_url.return_value = ("https://example.com/kick.m3u8", "")

        result = launch_stream("kick:trainwreckstv", "best")

        assert result.success is True
        mock_get_url.assert_called_once_with(
            "/usr/bin/streamlink",
            "https://kick.com/trainwreckstv",
            "best",
        )
