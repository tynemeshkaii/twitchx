from __future__ import annotations

import sys
import threading
from pathlib import Path


def test_excepthook_writes_crash_log(temp_config_dir: Path, monkeypatch) -> None:
    """sys.excepthook must write a crash entry to crash.log."""
    import importlib

    import main as _main

    importlib.reload(_main)

    _main._configure_crash_logging()
    crash_log = temp_config_dir.parent / "crash.log"

    try:
        raise RuntimeError("test crash")
    except RuntimeError:
        exc_type, exc_val, exc_tb = sys.exc_info()
        assert exc_type is not None
        assert exc_val is not None
        assert exc_tb is not None
        sys.excepthook(exc_type, exc_val, exc_tb)

    assert crash_log.exists(), "crash.log was not created"
    content = crash_log.read_text()
    assert "RuntimeError" in content
    assert "test crash" in content


def test_thread_excepthook_writes_crash_log(temp_config_dir: Path) -> None:
    """threading.excepthook must write a crash entry to crash.log."""
    import importlib

    import main as _main

    importlib.reload(_main)

    _main._configure_crash_logging()
    crash_log = temp_config_dir.parent / "crash.log"

    try:
        raise ValueError("thread crash")
    except ValueError:
        exc_type, exc_val, exc_tb = sys.exc_info()
        args = threading.ExceptHookArgs(
            (exc_type, exc_val, exc_tb, threading.current_thread())
        )
        threading.excepthook(args)

    assert crash_log.exists(), "crash.log was not created"
    content = crash_log.read_text()
    assert "ValueError" in content
    assert "thread crash" in content
