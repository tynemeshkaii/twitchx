import logging
import os

from app import StreamDeckApp

# Enable debug logging with TWITCHX_DEBUG=1
if os.environ.get("TWITCHX_DEBUG"):
    logging.basicConfig(level=logging.DEBUG, format="%(name)s %(message)s")


def main() -> None:
    app = StreamDeckApp()
    app.mainloop()


if __name__ == "__main__":
    main()
