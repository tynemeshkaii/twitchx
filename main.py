import logging
import logging.handlers
import os
from pathlib import Path

from app import TwitchXApp


def _configure_logging() -> None:
    log_dir = Path.home() / ".config" / "twitchx"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "twitchx.log"

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


_configure_logging()


def main() -> None:
    app = TwitchXApp()
    app.mainloop()


if __name__ == "__main__":
    main()
