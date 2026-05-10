from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.recorder import Recorder


class TestRecorder:
    def test_initial_state_is_inactive(self) -> None:
        r = Recorder()
        assert not r.is_recording
        assert r.current_file is None
        assert r.elapsed_seconds == 0

    @patch("core.recorder.subprocess.Popen")
    @patch("core.recorder.shutil.which", return_value="/usr/local/bin/streamlink")
    def test_start_creates_process(
        self, _mock_which: MagicMock, mock_popen: MagicMock
    ) -> None:
        mock_popen.return_value = MagicMock(poll=MagicMock(return_value=None))
        r = Recorder()
        err = r.start("https://twitch.tv/xqc", "xqc", "/tmp/test")
        assert err is None
        assert r.is_recording
        assert r.current_file is not None
        assert "xqc" in r.current_file
        r.stop()

    @patch("core.recorder.shutil.which", return_value=None)
    def test_start_fails_when_streamlink_missing(self, _mock_which: MagicMock) -> None:
        r = Recorder()
        err = r.start("https://twitch.tv/xqc", "xqc", "/tmp/test")
        assert err is not None
        assert "not found" in err.lower()
        assert not r.is_recording

    @patch("core.recorder.subprocess.Popen")
    @patch("core.recorder.shutil.which", return_value="/usr/local/bin/streamlink")
    def test_stop_terminates_process(
        self, _mock_which: MagicMock, mock_popen: MagicMock
    ) -> None:
        mock_proc = MagicMock(poll=MagicMock(return_value=None))
        mock_popen.return_value = mock_proc
        r = Recorder()
        r.start("https://twitch.tv/xqc", "xqc", "/tmp/test")
        r.stop()
        assert not r.is_recording
        mock_proc.terminate.assert_called_once()

    @patch("core.recorder.subprocess.Popen")
    @patch("core.recorder.shutil.which", return_value="/usr/local/bin/streamlink")
    def test_start_while_already_recording_stops_first(
        self, _mock_which: MagicMock, mock_popen: MagicMock
    ) -> None:
        mock_proc = MagicMock(poll=MagicMock(return_value=None))
        mock_popen.return_value = mock_proc
        r = Recorder()
        r.start("https://twitch.tv/xqc", "xqc", "/tmp/test")
        r.start("https://twitch.tv/other", "other", "/tmp/test")
        assert mock_proc.terminate.call_count == 1
        r.stop()

    @patch("core.recorder.subprocess.Popen")
    @patch("core.recorder.shutil.which", return_value="/usr/local/bin/streamlink")
    def test_filename_format(
        self, _mock_which: MagicMock, mock_popen: MagicMock
    ) -> None:
        mock_popen.return_value = MagicMock(poll=MagicMock(return_value=None))
        r = Recorder()
        r.start("https://twitch.tv/xqc", "xqc", "/tmp/test")
        assert r.current_file is not None
        assert r.current_file.endswith(".ts")
        assert "xqc" in r.current_file
        r.stop()
