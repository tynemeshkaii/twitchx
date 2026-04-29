from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from core.stream_resolver import resolve_hls_url


def _mock_platform(url: str) -> MagicMock:
    client = MagicMock()
    client.build_stream_url = MagicMock(return_value=url)
    return client


class TestResolveHlsUrl:
    @patch(
        "core.stream_resolver.shutil.which", return_value="/usr/local/bin/streamlink"
    )
    @patch("core.stream_resolver.subprocess.run")
    def test_success(self, mock_run: MagicMock, _mock_which: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"https://example.com/stream.m3u8\n",
        )
        client = _mock_platform("https://twitch.tv/xqc")
        url, err = resolve_hls_url("xqc", "best", platform_client=client)
        assert url == "https://example.com/stream.m3u8"
        assert err == ""
        client.build_stream_url.assert_called_once_with("xqc")

    @patch(
        "core.stream_resolver.shutil.which", return_value="/usr/local/bin/streamlink"
    )
    @patch("core.stream_resolver.subprocess.run")
    def test_quality_fallback(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr=b"quality not available"),
            MagicMock(returncode=0, stdout=b"https://example.com/best.m3u8\n"),
        ]
        client = _mock_platform("https://twitch.tv/xqc")
        url, err = resolve_hls_url("xqc", "720p60", platform_client=client)
        assert url == "https://example.com/best.m3u8"
        assert mock_run.call_count == 2

    @patch(
        "core.stream_resolver.shutil.which", return_value="/usr/local/bin/streamlink"
    )
    @patch("core.stream_resolver.subprocess.run")
    def test_timeout(self, mock_run: MagicMock, _mock_which: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="streamlink", timeout=15)
        client = _mock_platform("https://twitch.tv/xqc")
        url, err = resolve_hls_url("xqc", "best", platform_client=client)
        assert url is None
        assert "timed out" in err.lower()

    @patch("core.stream_resolver.shutil.which", return_value=None)
    def test_missing_streamlink(self, mock_which: MagicMock) -> None:
        client = _mock_platform("https://twitch.tv/xqc")
        url, err = resolve_hls_url("xqc", "best", platform_client=client)
        assert url is None
        assert "not found" in err.lower()

    @patch(
        "core.stream_resolver.shutil.which", return_value="/usr/local/bin/streamlink"
    )
    @patch("core.stream_resolver.subprocess.run")
    def test_all_qualities_fail(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=1, stderr=b"No streams found")
        client = _mock_platform("https://twitch.tv/xqc")
        url, err = resolve_hls_url("xqc", "720p60", platform_client=client)
        assert url is None
        assert err != ""


class TestResolveKickHlsUrl:
    @patch(
        "core.stream_resolver.shutil.which", return_value="/usr/local/bin/streamlink"
    )
    @patch("core.stream_resolver.subprocess.run")
    def test_builds_kick_url(self, mock_run: MagicMock, _mock_which: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"https://hls.kick.com/test.m3u8\n",
        )
        client = _mock_platform("https://kick.com/xqc")
        url, err = resolve_hls_url("xqc", "best", platform_client=client)
        assert url == "https://hls.kick.com/test.m3u8"
        assert err == ""
        # Verify that kick.com URL was passed to streamlink
        assert mock_run.call_count == 1
        call_args = mock_run.call_args[0][0]
        assert "https://kick.com/xqc" in call_args


class TestResolveDirectMediaUrl:
    @patch(
        "core.stream_resolver.shutil.which", return_value="/usr/local/bin/streamlink"
    )
    @patch("core.stream_resolver.subprocess.run")
    def test_uses_direct_url_without_rewriting(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"https://example.com/media.m3u8\n",
        )
        url, err = resolve_hls_url(
            "https://www.twitch.tv/videos/123456",
            "best",
        )
        assert url == "https://example.com/media.m3u8"
        assert err == ""
        call_args = mock_run.call_args[0][0]
        assert "https://www.twitch.tv/videos/123456" in call_args
