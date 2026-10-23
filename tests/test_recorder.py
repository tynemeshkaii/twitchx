from __future__ import annotations

import subprocess
import threading
from unittest.mock import MagicMock, patch

from core.recorder import Recorder


class FakeProc:
    """Popen stand-in whose lifetime the test controls.

    It runs until terminate()/kill() or exit() is called, emitting ``lines`` on
    its combined stdout first, like streamlink writing its console log.
    """

    def __init__(
        self,
        lines: list[bytes] | None = None,
        returncode: int | None = None,
        ignore_terminate: bool = False,
    ) -> None:
        self._lines = lines or []
        self._done = threading.Event()
        self._ignore_terminate = ignore_terminate
        self.returncode: int | None = None
        self.terminate = MagicMock(side_effect=self._on_terminate)
        self.kill = MagicMock(side_effect=self._on_kill)
        self.wait_calls: list[float | None] = []
        self.stdout = self
        if returncode is not None:
            self.exit(returncode)

    def __iter__(self):
        yield from self._lines
        self._done.wait()

    def _on_terminate(self) -> None:
        if not self._ignore_terminate:
            self.exit(-15)

    def _on_kill(self) -> None:
        self.exit(-9)

    def exit(self, code: int) -> None:
        if self.returncode is None:
            self.returncode = code
        self._done.set()

    def poll(self) -> int | None:
        return self.returncode if self._done.is_set() else None

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        if not self._done.wait(timeout):
            raise subprocess.TimeoutExpired("streamlink", timeout or 0)
        assert self.returncode is not None
        return self.returncode


def _join_threads(r: Recorder) -> None:
    for t in (r._watcher, r._reaper):
        if t is not None:
            t.join(2)


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
        mock_popen.return_value = FakeProc()
        r = Recorder()
        err = r.start("https://twitch.tv/xqc", "xqc", "/tmp/test")
        assert err is None
        assert r.is_recording
        assert r.current_file is not None
        assert "xqc" in r.current_file
        r.stop()
        _join_threads(r)

    @patch("core.recorder.shutil.which", return_value=None)
    def test_start_fails_when_streamlink_missing(self, _mock_which: MagicMock) -> None:
        r = Recorder()
        err = r.start("https://twitch.tv/xqc", "xqc", "/tmp/test")
        assert err is not None
        assert "not found" in err.lower()
        assert not r.is_recording

    @patch("core.recorder.subprocess.Popen")
    @patch("core.recorder.shutil.which", return_value="/usr/local/bin/streamlink")
    def test_stop_terminates_and_waits(
        self, _mock_which: MagicMock, mock_popen: MagicMock
    ) -> None:
        proc = FakeProc()
        mock_popen.return_value = proc
        r = Recorder()
        r.start("https://twitch.tv/xqc", "xqc", "/tmp/test")
        r.stop()
        _join_threads(r)
        assert not r.is_recording
        proc.terminate.assert_called_once()
        assert 5 in proc.wait_calls
        proc.kill.assert_not_called()

    @patch("core.recorder.subprocess.Popen")
    @patch("core.recorder.shutil.which", return_value="/usr/local/bin/streamlink")
    def test_stop_kills_process_that_ignores_terminate(
        self, _mock_which: MagicMock, mock_popen: MagicMock
    ) -> None:
        proc = FakeProc(ignore_terminate=True)
        mock_popen.return_value = proc
        r = Recorder()
        r.start("https://twitch.tv/xqc", "xqc", "/tmp/test")
        with patch("core.recorder.STOP_TIMEOUT_SECONDS", 0.05):
            r.stop()
            _join_threads(r)
        proc.kill.assert_called_once()

    @patch("core.recorder.subprocess.Popen")
    @patch("core.recorder.shutil.which", return_value="/usr/local/bin/streamlink")
    def test_stop_does_not_block_caller(
        self, _mock_which: MagicMock, mock_popen: MagicMock
    ) -> None:
        """close() calls stop() on window close: the escalation runs elsewhere."""
        proc = FakeProc(ignore_terminate=True)
        mock_popen.return_value = proc
        r = Recorder()
        r.start("https://twitch.tv/xqc", "xqc", "/tmp/test")
        stopper = threading.Thread(target=r.stop)
        stopper.start()
        stopper.join(1)
        assert not stopper.is_alive()
        proc.exit(0)
        _join_threads(r)

    @patch("core.recorder.subprocess.Popen")
    @patch("core.recorder.shutil.which", return_value="/usr/local/bin/streamlink")
    def test_start_while_already_recording_stops_first(
        self, _mock_which: MagicMock, mock_popen: MagicMock
    ) -> None:
        first, second = FakeProc(), FakeProc()
        mock_popen.side_effect = [first, second]
        on_exit = MagicMock()
        r = Recorder()
        r.start("https://twitch.tv/xqc", "xqc", "/tmp/test", on_exit=on_exit)
        r.start("https://twitch.tv/other", "other", "/tmp/test", on_exit=on_exit)
        assert first.terminate.call_count == 1
        r.stop()
        _join_threads(r)
        # Replacing or stopping a recording is not a crash.
        on_exit.assert_not_called()

    @patch("core.recorder.subprocess.Popen")
    @patch("core.recorder.shutil.which", return_value="/usr/local/bin/streamlink")
    def test_filename_format(
        self, _mock_which: MagicMock, mock_popen: MagicMock
    ) -> None:
        mock_popen.return_value = FakeProc()
        r = Recorder()
        r.start("https://twitch.tv/xqc", "xqc", "/tmp/test")
        assert r.current_file is not None
        assert r.current_file.endswith(".ts")
        assert "xqc" in r.current_file
        r.stop()
        _join_threads(r)

    @patch("core.recorder.subprocess.Popen")
    @patch("core.recorder.shutil.which", return_value="/usr/local/bin/streamlink")
    def test_quality_uses_fallback_ladder(
        self, _mock_which: MagicMock, mock_popen: MagicMock
    ) -> None:
        mock_popen.return_value = FakeProc()
        r = Recorder()
        r.start("https://twitch.tv/xqc", "xqc", "/tmp/test", quality="1440p60")
        cmd = mock_popen.call_args[0][0]
        assert cmd[2] == "1440p60,1440p,1080p60,1080p,720p60,720p,best"
        r.stop()
        _join_threads(r)

    @patch("core.recorder.subprocess.Popen")
    @patch("core.recorder.shutil.which", return_value="/usr/local/bin/streamlink")
    def test_output_is_piped_not_discarded(
        self, _mock_which: MagicMock, mock_popen: MagicMock
    ) -> None:
        mock_popen.return_value = FakeProc()
        r = Recorder()
        r.start("https://twitch.tv/xqc", "xqc", "/tmp/test")
        kwargs = mock_popen.call_args[1]
        # With --output streamlink writes its console log to stdout.
        assert kwargs["stdout"] == subprocess.PIPE
        assert kwargs["stderr"] == subprocess.STDOUT
        r.stop()
        _join_threads(r)

    @patch("core.recorder.subprocess.Popen")
    @patch("core.recorder.shutil.which", return_value="/usr/local/bin/streamlink")
    def test_crash_calls_on_exit_with_error_line(
        self, _mock_which: MagicMock, mock_popen: MagicMock
    ) -> None:
        proc = FakeProc(
            lines=[
                b"[cli][info] Found matching plugin twitch\n",
                b"error: The specified stream(s) '1440p60' could not be found\n",
                b"[cli][info] Closing\n",
            ],
            returncode=1,
        )
        mock_popen.return_value = proc
        on_exit = MagicMock()
        r = Recorder()
        r.start("https://twitch.tv/xqc", "xqc", "/tmp/test", on_exit=on_exit)
        _join_threads(r)

        on_exit.assert_called_once()
        returncode, last_line, filename, elapsed = on_exit.call_args[0]
        assert returncode == 1
        assert "could not be found" in last_line
        assert filename.endswith(".ts")
        assert elapsed >= 0
        assert not r.is_recording
        assert r.current_file is None

    @patch("core.recorder.subprocess.Popen")
    @patch("core.recorder.shutil.which", return_value="/usr/local/bin/streamlink")
    def test_stream_end_calls_on_exit_with_zero(
        self, _mock_which: MagicMock, mock_popen: MagicMock
    ) -> None:
        mock_popen.return_value = FakeProc(returncode=0)
        on_exit = MagicMock()
        r = Recorder()
        r.start("https://twitch.tv/xqc", "xqc", "/tmp/test", on_exit=on_exit)
        _join_threads(r)
        on_exit.assert_called_once()
        assert on_exit.call_args[0][0] == 0

    @patch("core.recorder.subprocess.Popen")
    @patch("core.recorder.shutil.which", return_value="/usr/local/bin/streamlink")
    def test_stop_does_not_call_on_exit(
        self, _mock_which: MagicMock, mock_popen: MagicMock
    ) -> None:
        mock_popen.return_value = FakeProc()
        on_exit = MagicMock()
        r = Recorder()
        r.start("https://twitch.tv/xqc", "xqc", "/tmp/test", on_exit=on_exit)
        r.stop()
        _join_threads(r)
        on_exit.assert_not_called()
