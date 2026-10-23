"""Stream recording via streamlink subprocess."""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from core.stream_resolver import quality_arg

logger = logging.getLogger(__name__)

# How long a stopped streamlink gets to flush and close the file before kill().
STOP_TIMEOUT_SECONDS = 5.0

# (returncode, last console line, file path, seconds recorded)
OnExit = Callable[[int, str, str, int], None]


class Recorder:
    """Manages a single streamlink recording subprocess."""

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None  # type: ignore[type-arg]
        self._start_time: float = 0.0
        self._lock = threading.Lock()
        self.current_file: str | None = None
        # Last spawned helper threads; kept so tests can join them.
        self._watcher: threading.Thread | None = None
        self._reaper: threading.Thread | None = None

    @property
    def is_recording(self) -> bool:
        with self._lock:
            if self._process is None:
                return False
            return self._process.poll() is None

    @property
    def elapsed_seconds(self) -> int:
        if not self.is_recording or self._start_time == 0:
            return 0
        return int(time.time() - self._start_time)

    def start(
        self,
        stream_url: str,
        channel: str,
        output_dir: str,
        streamlink_path: str = "streamlink",
        quality: str = "best",
        extra_args: list[str] | None = None,
        on_exit: OnExit | None = None,
    ) -> str | None:
        """Start recording. Returns an error string on failure, None on success.

        on_exit fires from a background thread when streamlink exits on its own
        (crash, missing quality, stream ended) — not after stop() or a restart.
        """
        resolved_sl = shutil.which(streamlink_path)
        if resolved_sl is None:
            logger.warning("streamlink not found for recording")
            return "streamlink not found. Install with: brew install streamlink"

        with self._lock:
            previous = self._process
            self._process = None
            self.current_file = None
        if previous is not None and previous.poll() is None:
            logger.debug("Terminating previous recording before starting new one")
            self._reap(previous)

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_channel = "".join(c for c in channel if c.isalnum() or c in "-_")
        filename = f"twitchx_{safe_channel}_{timestamp}.ts"
        filepath = str(Path(output_dir) / filename)

        # The same fallback ladder as playback: a quality the channel does not
        # offer would otherwise make streamlink exit right away.
        cmd = [resolved_sl, stream_url, quality_arg(quality), "--output", filepath]
        if extra_args:
            # Same codec set as playback, so a recording of an Enhanced
            # Broadcasting channel is not silently capped at 1080p60.
            cmd.extend(extra_args)

        try:
            # With --output, streamlink prints its log and its "error:" lines
            # to stdout; stderr is merged so nothing is lost either way.
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except OSError as e:
            logger.error("Failed to start recording for %s: %s", channel, e)
            return f"Failed to start recording: {e}"

        started = time.time()
        with self._lock:
            self._process = proc
            self.current_file = filepath
            self._start_time = started
        watcher = threading.Thread(
            target=self._watch,
            args=(proc, channel, filepath, started, on_exit),
            name="recorder-watch",
            daemon=True,
        )
        self._watcher = watcher
        watcher.start()
        logger.info("Recording started for %s → %s", channel, filepath)
        return None

    def _watch(
        self,
        proc: subprocess.Popen,  # type: ignore[type-arg]
        channel: str,
        filepath: str,
        started: float,
        on_exit: OnExit | None,
    ) -> None:
        """Relay streamlink output to the log and report when the process ends."""
        last_line = ""
        error_line = ""
        if proc.stdout is not None:
            for raw in proc.stdout:
                line = raw.decode(errors="replace").strip()
                if not line:
                    continue
                last_line = line
                if line.lower().startswith("error:"):
                    error_line = line
                logger.info("[recording %s] %s", channel, line)
        returncode = proc.wait()

        with self._lock:
            # stop() and a restart detach the process first, so only an exit
            # nobody asked for still finds it here.
            unexpected = self._process is proc
            if unexpected:
                self._process = None
                self.current_file = None
                self._start_time = 0.0
        if not unexpected:
            logger.debug("Recording for %s stopped (code %s)", channel, returncode)
            return

        elapsed = int(time.time() - started)
        log = logger.info if returncode == 0 else logger.warning
        log(
            "Recording for %s ended on its own after %ds (code %s)",
            channel,
            elapsed,
            returncode,
        )
        if on_exit is not None:
            on_exit(returncode, error_line or last_line, filepath, elapsed)

    def _reap(self, proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
        """terminate() now; wait and escalate to kill() off the caller's thread.

        close() stops the recording while the window is going away, so the
        caller must not sit through the grace period. The thread is non-daemon
        so the kill still happens if the interpreter is shutting down.
        """
        try:
            proc.terminate()
        except OSError:
            return

        def finish() -> None:
            try:
                proc.wait(timeout=STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                logger.warning("streamlink ignored SIGTERM, killing recording")
                try:
                    proc.kill()
                    proc.wait()
                except OSError:
                    pass

        reaper = threading.Thread(target=finish, name="recorder-reap")
        self._reaper = reaper
        reaper.start()

    def stop(self) -> None:
        """Terminate the recording subprocess gracefully."""
        with self._lock:
            proc = self._process
            self._process = None
            self.current_file = None
            self._start_time = 0.0
        if proc is not None and proc.poll() is None:
            logger.info("Stopping recording")
            self._reap(proc)

    def state_dict(self) -> dict:
        return {
            "active": self.is_recording,
            "filename": self.current_file,
            "elapsed": self.elapsed_seconds,
        }
