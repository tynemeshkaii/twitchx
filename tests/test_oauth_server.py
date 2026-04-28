from __future__ import annotations

import threading
import time
import urllib.request
from contextlib import suppress

from core.oauth_server import wait_for_oauth_code


def test_oauth_server_receives_code() -> None:
    """OAuth server receives code from callback URL."""
    def _request() -> None:
        time.sleep(0.1)
        with suppress(Exception):
            urllib.request.urlopen(
                "http://localhost:3457/callback?code=test-auth-code&scope=read"
            )

    thread = threading.Thread(target=_request, daemon=True)
    thread.start()

    code = wait_for_oauth_code(timeout=5)
    assert code == "test-auth-code"


def test_oauth_server_timeout() -> None:
    """OAuth server returns None on timeout."""
    code = wait_for_oauth_code(timeout=1)
    assert code is None


def test_oauth_server_ignores_non_callback_paths() -> None:
    """Requests not to /callback are ignored."""
    def _bad_request() -> None:
        time.sleep(0.1)
        with suppress(Exception):
            urllib.request.urlopen("http://localhost:3457/other")

    def _good_request() -> None:
        time.sleep(0.2)
        with suppress(Exception):
            urllib.request.urlopen(
                "http://localhost:3457/callback?code=real-code"
            )

    threading.Thread(target=_bad_request, daemon=True).start()
    threading.Thread(target=_good_request, daemon=True).start()

    code = wait_for_oauth_code(timeout=5)
    assert code == "real-code"
