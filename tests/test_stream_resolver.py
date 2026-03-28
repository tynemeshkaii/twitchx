from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from core.stream_resolver import resolve_hls_url


class TestResolveHlsUrl:
    @patch("core.stream_resolver.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"https://example.com/stream.m3u8\n",
        )
        url, err = resolve_hls_url("xqc", "best")
        assert url == "https://example.com/stream.m3u8"
        assert err == ""

    @patch("core.stream_resolver.subprocess.run")
    def test_quality_fallback(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr=b"quality not available"),
            MagicMock(returncode=0, stdout=b"https://example.com/best.m3u8\n"),
        ]
        url, err = resolve_hls_url("xqc", "720p60")
        assert url == "https://example.com/best.m3u8"
        assert mock_run.call_count == 2

    @patch("core.stream_resolver.subprocess.run")
    def test_timeout(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="streamlink", timeout=15)
        url, err = resolve_hls_url("xqc", "best")
        assert url is None
        assert "timed out" in err.lower()

    @patch("core.stream_resolver.shutil.which", return_value=None)
    def test_missing_streamlink(self, mock_which: MagicMock) -> None:
        url, err = resolve_hls_url("xqc", "best")
        assert url is None
        assert "not found" in err.lower()

    @patch("core.stream_resolver.subprocess.run")
    def test_all_qualities_fail(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stderr=b"No streams found")
        url, err = resolve_hls_url("xqc", "720p60")
        assert url is None
        assert err != ""


class TestResolveKickHlsUrl:
    @patch("core.stream_resolver.subprocess.run")
    def test_builds_kick_url(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"https://hls.kick.com/test.m3u8\n",
        )
        url, err = resolve_hls_url("xqc", "best", platform="kick")
        assert url == "https://hls.kick.com/test.m3u8"
        assert err == ""
        # Verify that kick.com URL was passed to streamlink
        assert mock_run.call_count == 1
        call_args = mock_run.call_args[0][0]
        assert "https://kick.com/xqc" in call_args
