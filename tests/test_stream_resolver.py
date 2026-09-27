from __future__ import annotations

import subprocess
import time
from unittest.mock import MagicMock, patch

from core.stream_resolver import invalidate_resolve_cache, resolve_hls_url


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
        # streamlink receives the whole ladder in a single call so it handles
        # quality fallback internally — no second subprocess invocation.
        mock_run.return_value = MagicMock(
            returncode=0, stdout=b"https://example.com/720p.m3u8\n"
        )
        client = _mock_platform("https://twitch.tv/xqc")
        url, err = resolve_hls_url("xqc", "720p60", platform_client=client)
        assert url == "https://example.com/720p.m3u8"
        assert mock_run.call_count == 1
        cmd = mock_run.call_args[0][0]
        assert "720p60,720p,480p,360p,160p,best" in cmd

    @patch(
        "core.stream_resolver.shutil.which", return_value="/usr/local/bin/streamlink"
    )
    @patch("core.stream_resolver.subprocess.run")
    def test_ladder_steps_down_before_reaching_best(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        """Lower renditions must be offered before source, not after it."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout=b"https://example.com/s.m3u8\n"
        )
        client = _mock_platform("https://twitch.tv/xqc")
        resolve_hls_url("xqc", "480p", platform_client=client)
        ladder = [a for a in mock_run.call_args[0][0] if "," in a][0].split(",")
        assert ladder[0] == "480p"
        assert ladder.index("360p") < ladder.index("best")
        assert ladder[-1] == "best"

    @patch(
        "core.stream_resolver.shutil.which", return_value="/usr/local/bin/streamlink"
    )
    @patch("core.stream_resolver.subprocess.run")
    def test_unknown_quality_keeps_simple_fallback(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=b"https://example.com/s.m3u8\n"
        )
        client = _mock_platform("https://twitch.tv/xqc")
        resolve_hls_url("xqc", "4320p60", platform_client=client)
        assert "4320p60,best" in mock_run.call_args[0][0]

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
        # Single call with "720p60,best" — if streamlink can't find any quality, fail once
        mock_run.return_value = MagicMock(returncode=1, stderr=b"No streams found")
        client = _mock_platform("https://twitch.tv/xqc")
        url, err = resolve_hls_url("xqc", "720p60", platform_client=client)
        assert url is None
        assert err != ""
        assert mock_run.call_count == 1


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


class TestExtraArgs:
    @patch(
        "core.stream_resolver.shutil.which", return_value="/usr/local/bin/streamlink"
    )
    @patch("core.stream_resolver.subprocess.run")
    def test_extra_args_are_passed_to_subprocess(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"https://example.com/stream.m3u8\n",
        )
        client = _mock_platform("https://twitch.tv/xqc")
        resolve_hls_url(
            "xqc",
            "best",
            platform_client=client,
            extra_args=["--twitch-low-latency"],
        )
        call_args = mock_run.call_args[0][0]
        assert "--twitch-low-latency" in call_args

    @patch(
        "core.stream_resolver.shutil.which", return_value="/usr/local/bin/streamlink"
    )
    @patch("core.stream_resolver.subprocess.run")
    def test_no_extra_args_by_default(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"https://example.com/stream.m3u8\n",
        )
        client = _mock_platform("https://twitch.tv/xqc")
        resolve_hls_url("xqc", "best", platform_client=client)
        call_args = mock_run.call_args[0][0]
        assert "--twitch-low-latency" not in call_args


class TestAdaptiveMasterPlaylist:
    @patch(
        "core.stream_resolver.shutil.which", return_value="/usr/local/bin/streamlink"
    )
    @patch("core.stream_resolver.subprocess.run")
    def test_best_resolves_master_playlist(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        """adaptive + best must omit the quality arg so streamlink prints the master."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"https://usher.ttvnw.net/api/v2/channel/hls/xqc.m3u8\n",
        )
        client = _mock_platform("https://twitch.tv/xqc")
        url, err = resolve_hls_url(
            "xqc", "best", platform_client=client, adaptive=True
        )
        assert url == "https://usher.ttvnw.net/api/v2/channel/hls/xqc.m3u8"
        assert err == ""
        cmd = mock_run.call_args[0][0]
        assert "best" not in cmd
        assert cmd[-1] == "https://twitch.tv/xqc"

    @patch(
        "core.stream_resolver.shutil.which", return_value="/usr/local/bin/streamlink"
    )
    @patch("core.stream_resolver.subprocess.run")
    def test_explicit_quality_ignores_adaptive(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=b"https://example.com/720.m3u8\n"
        )
        client = _mock_platform("https://twitch.tv/xqc")
        resolve_hls_url("xqc", "720p60", platform_client=client, adaptive=True)
        assert mock_run.call_count == 1
        assert any("720p60" in a for a in mock_run.call_args[0][0])

    @patch(
        "core.stream_resolver.shutil.which", return_value="/usr/local/bin/streamlink"
    )
    @patch("core.stream_resolver.subprocess.run")
    def test_master_failure_falls_back_to_single_rendition(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr=b"no master"),
            MagicMock(returncode=0, stdout=b"https://example.com/best.m3u8\n"),
        ]
        client = _mock_platform("https://twitch.tv/xqc")
        url, err = resolve_hls_url(
            "xqc", "best", platform_client=client, adaptive=True
        )
        assert url == "https://example.com/best.m3u8"
        assert err == ""
        assert mock_run.call_count == 2
        assert "best" in mock_run.call_args[0][0]


class TestResolveCache:
    def setup_method(self) -> None:
        invalidate_resolve_cache()

    def teardown_method(self) -> None:
        invalidate_resolve_cache()

    @patch(
        "core.stream_resolver.shutil.which", return_value="/usr/local/bin/streamlink"
    )
    @patch("core.stream_resolver.subprocess.run")
    def test_second_resolve_skips_subprocess(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=b"https://example.com/s.m3u8\n"
        )
        client = _mock_platform("https://twitch.tv/xqc")
        first, _ = resolve_hls_url("xqc", "best", platform_client=client, use_cache=True)
        second, _ = resolve_hls_url(
            "xqc", "best", platform_client=client, use_cache=True
        )
        assert first == second
        assert mock_run.call_count == 1

    @patch(
        "core.stream_resolver.shutil.which", return_value="/usr/local/bin/streamlink"
    )
    @patch("core.stream_resolver.subprocess.run")
    def test_cache_disabled_by_default(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=b"https://example.com/s.m3u8\n"
        )
        client = _mock_platform("https://twitch.tv/xqc")
        resolve_hls_url("xqc", "best", platform_client=client)
        resolve_hls_url("xqc", "best", platform_client=client)
        assert mock_run.call_count == 2

    @patch(
        "core.stream_resolver.shutil.which", return_value="/usr/local/bin/streamlink"
    )
    @patch("core.stream_resolver.subprocess.run")
    def test_invalidate_forces_new_resolve(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=b"https://example.com/s.m3u8\n"
        )
        client = _mock_platform("https://twitch.tv/xqc")
        resolve_hls_url("xqc", "best", platform_client=client, use_cache=True)
        invalidate_resolve_cache()
        resolve_hls_url("xqc", "best", platform_client=client, use_cache=True)
        assert mock_run.call_count == 2

    @patch(
        "core.stream_resolver.shutil.which", return_value="/usr/local/bin/streamlink"
    )
    @patch("core.stream_resolver.subprocess.run")
    def test_expired_entry_is_not_served(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=b"https://example.com/s.m3u8\n"
        )
        client = _mock_platform("https://twitch.tv/xqc")
        with patch("core.stream_resolver.RESOLVE_CACHE_TTL_SECONDS", 0.01):
            resolve_hls_url("xqc", "best", platform_client=client, use_cache=True)
            time.sleep(0.05)
            resolve_hls_url("xqc", "best", platform_client=client, use_cache=True)
        assert mock_run.call_count == 2

    @patch(
        "core.stream_resolver.shutil.which", return_value="/usr/local/bin/streamlink"
    )
    @patch("core.stream_resolver.subprocess.run")
    def test_failed_resolve_is_not_cached(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=1, stderr=b"offline")
        client = _mock_platform("https://twitch.tv/xqc")
        resolve_hls_url("xqc", "best", platform_client=client, use_cache=True)
        resolve_hls_url("xqc", "best", platform_client=client, use_cache=True)
        assert mock_run.call_count == 2
