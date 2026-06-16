import logging
import logging.handlers
import os
import sys
import threading
import traceback
from pathlib import Path
from types import TracebackType

from app import TwitchXApp

_LOG_DIR = Path.home() / ".config" / "twitchx"


def _configure_logging() -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = _LOG_DIR / "twitchx.log"

    level = logging.DEBUG if os.environ.get("TWITCHX_DEBUG") else logging.WARNING
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d %(message)s"
    )

    root = logging.getLogger()
    root.setLevel(level)

    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=2, delay=True
    )
    handler.setFormatter(fmt)
    root.addHandler(handler)

    stderr = logging.StreamHandler()
    stderr.setFormatter(fmt)
    stderr.setLevel(level)
    root.addHandler(stderr)


def _configure_crash_logging() -> None:
    from core import storage as _storage

    def _write_crash(
        header: str,
        exc_type: type[BaseException],
        exc_value: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        log_dir = _storage.CONFIG_DIR
        crash_log = log_dir / "crash.log"
        log_dir.mkdir(parents=True, exist_ok=True)
        lines = ["=" * 60 + "\n", header + "\n"]
        lines += traceback.format_exception(exc_type, exc_value, exc_tb)
        lines.append("\n")
        try:
            with open(crash_log, "a", encoding="utf-8") as f:
                f.writelines(lines)
        except OSError:
            pass

    def _excepthook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        from datetime import datetime

        header = f"CRASH {datetime.now().isoformat(timespec='seconds')} (main thread)"
        _write_crash(header, exc_type, exc_value, exc_tb)
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
        from datetime import datetime

        thread_name = args.thread.name if args.thread else "unknown"
        header = f"CRASH {datetime.now().isoformat(timespec='seconds')} (thread: {thread_name})"
        _write_crash(header, args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook


_configure_logging()
_configure_crash_logging()


def main() -> None:
    app = TwitchXApp()
    app.mainloop()


if __name__ == "__main__":
    main()
