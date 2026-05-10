"""Stream recording via streamlink subprocess."""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path


class Recorder:
    """Manages a single streamlink recording subprocess."""

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None  # type: ignore[type-arg]
        self._start_time: float = 0.0
        self._lock = threading.Lock()
        self.current_file: str | None = None

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
    ) -> str | None:
        """Start recording. Returns an error string on failure, None on success."""
        resolved_sl = shutil.which(streamlink_path)
        if resolved_sl is None:
            return "streamlink not found. Install with: brew install streamlink"

        with self._lock:
            if self._process is not None and self._process.poll() is None:
                self._process.terminate()
                self._process = None
                self.current_file = None

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_channel = "".join(c for c in channel if c.isalnum() or c in "-_")
        filename = f"twitchx_{safe_channel}_{timestamp}.ts"
        filepath = str(Path(output_dir) / filename)

        try:
            proc = subprocess.Popen(
                [resolved_sl, stream_url, quality, "--output", filepath],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            return f"Failed to start recording: {e}"

        with self._lock:
            self._process = proc
            self.current_file = filepath
            self._start_time = time.time()
        return None

    def stop(self) -> None:
        """Terminate the recording subprocess gracefully."""
        with self._lock:
            proc = self._process
            self._process = None
            self.current_file = None
            self._start_time = 0.0
        if proc is not None and proc.poll() is None:
            proc.terminate()

    def state_dict(self) -> dict:
        return {
            "active": self.is_recording,
            "filename": self.current_file,
            "elapsed": self.elapsed_seconds,
        }
