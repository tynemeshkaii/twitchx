from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from core.launcher import check_mpv, launch_stream, launch_stream_mpv
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
        mock_resolve.assert_called_once_with("xqc", "720p60", "streamlink", client, None)

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


class TestCheckMpv:
    @patch("core.launcher.shutil.which", return_value="/opt/homebrew/bin/mpv")
    def test_mpv_found(self, _mock_which: MagicMock) -> None:
        assert check_mpv("/opt/homebrew/bin/mpv") is None

    @patch("core.launcher.shutil.which", return_value=None)
    def test_mpv_not_found(self, _mock_which: MagicMock) -> None:
        err = check_mpv("/opt/homebrew/bin/mpv")
        assert err is not None
        assert "not found" in err.lower()


class TestLaunchStreamMpv:
    @patch("core.launcher.check_mpv", return_value=None)
    @patch("core.launcher.check_streamlink", return_value=None)
    @patch("core.launcher.resolve_hls_url")
    @patch("core.launcher.subprocess.Popen")
    def test_mpv_success(
        self,
        mock_popen: MagicMock,
        mock_resolve: MagicMock,
        _mock_check_sl: MagicMock,
        _mock_check_mpv: MagicMock,
    ) -> None:
        mock_resolve.return_value = ("https://example.com/stream.m3u8", "")
        client = _mock_platform("https://twitch.tv/xqc")
        result = launch_stream_mpv("xqc", "best", platform_client=client)
        assert result.success is True
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]
        assert "https://example.com/stream.m3u8" in call_args

    @patch("core.launcher.check_mpv", return_value="mpv not found")
    @patch("core.launcher.check_streamlink", return_value=None)
    def test_mpv_missing(
        self,
        _mock_check_sl: MagicMock,
        _mock_check_mpv: MagicMock,
    ) -> None:
        client = _mock_platform("https://twitch.tv/xqc")
        result = launch_stream_mpv("xqc", "best", platform_client=client)
        assert result.success is False
        assert "not found" in result.message.lower()
