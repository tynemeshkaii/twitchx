from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from core.launcher import launch_stream
from core.stream_resolver import _run_streamlink


def _mock_platform(url: str) -> MagicMock:
    client = MagicMock()
    client.build_stream_url = MagicMock(return_value=url)
    return client


class TestRunStreamlink:
    """Tests for the shared _run_streamlink helper in stream_resolver."""

    @patch("core.stream_resolver.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"https://example.com/stream.m3u8\n",
        )
        url, err = _run_streamlink(
            "/usr/bin/streamlink", "https://twitch.tv/xqc", "best"
        )
        assert url == "https://example.com/stream.m3u8"
        assert err == ""

    @patch("core.stream_resolver.subprocess.run")
    def test_nonzero(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr=b"error: No streams found",
        )
        url, err = _run_streamlink(
            "/usr/bin/streamlink", "https://twitch.tv/xqc", "best"
        )
        assert url is None
        assert "No streams found" in err

    @patch("core.stream_resolver.subprocess.run")
    def test_timeout(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="streamlink", timeout=15)
        url, err = _run_streamlink(
            "/usr/bin/streamlink", "https://twitch.tv/xqc", "best"
        )
        assert url is None
        assert "timed out" in err.lower()

    @patch("core.stream_resolver.subprocess.run")
    def test_empty_output(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"",
        )
        url, err = _run_streamlink(
            "/usr/bin/streamlink", "https://twitch.tv/xqc", "best"
        )
        assert url is None
        assert "empty" in err.lower()


class TestLaunchStream:
    @patch("core.launcher.check_iina", return_value=None)
    @patch("core.launcher.check_streamlink", return_value=None)
    @patch("core.launcher.resolve_hls_url")
    @patch("core.launcher.subprocess.Popen")
    def test_quality_fallback(
        self,
        mock_popen: MagicMock,
        mock_resolve: MagicMock,
        mock_check_sl: MagicMock,
        mock_check_iina: MagicMock,
    ) -> None:
        # resolve_hls_url already handles fallback internally; simulate success
        mock_resolve.return_value = ("https://example.com/best.m3u8", "")
        client = _mock_platform("https://twitch.tv/xqc")
        result = launch_stream("xqc", "720p60", platform_client=client)
        assert result.success is True
        mock_resolve.assert_called_once_with(
            "xqc", "720p60", "streamlink", client
        )

    @patch("core.launcher.check_iina", return_value=None)
    @patch("core.launcher.check_streamlink", return_value="streamlink not found")
    def test_missing_streamlink(
        self,
        mock_check_sl: MagicMock,
        mock_check_iina: MagicMock,
    ) -> None:
        client = _mock_platform("https://twitch.tv/xqc")
        result = launch_stream("xqc", "best", platform_client=client)
        assert result.success is False
        assert "not found" in result.message.lower()

    @patch("core.launcher.check_iina", return_value="IINA not found")
    @patch("core.launcher.check_streamlink", return_value=None)
    def test_missing_iina(
        self,
        mock_check_sl: MagicMock,
        mock_check_iina: MagicMock,
    ) -> None:
        client = _mock_platform("https://twitch.tv/xqc")
        result = launch_stream("xqc", "best", platform_client=client)
        assert result.success is False
        assert "not found" in result.message.lower()
