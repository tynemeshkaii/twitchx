from __future__ import annotations

import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from secrets import compare_digest
from urllib.parse import parse_qs, urlparse

_RESPONSE_HTML = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>TwitchX</title>
<style>
body { background: #0e0e1a; color: #e0e0e0; font-family: system-ui, sans-serif;
       display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
.card { text-align: center; }
h1 { color: #9146FF; }
</style></head>
<body><div class="card">
<h1>&#x2713; Authenticated!</h1>
<p>You can close this tab and return to TwitchX.</p>
</div></body></html>
"""

_ERROR_HTML = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>TwitchX</title>
<style>
body { background: #0e0e1a; color: #e0e0e0; font-family: system-ui, sans-serif;
       display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
.card { text-align: center; }
h1 { color: #FF6B6B; }
</style></head>
<body><div class="card">
<h1>&#x2717; Authentication failed</h1>
<p>Please try again from TwitchX.</p>
</div></body></html>
"""


@dataclass(frozen=True)
class OAuthCallback:
    code: str
    state: str | None


def validate_state(expected: str | None, received: str | None) -> bool:
    return bool(expected and received and compare_digest(expected, received))


def wait_for_oauth_code(port: int = 3457, timeout: int = 120) -> OAuthCallback | None:
    """Start a temporary HTTP server and wait for Twitch OAuth callback.

    Returns the callback payload, or None on timeout.
    """
    result: list[OAuthCallback | None] = [None]
    server_ready = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return

            params = parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            state = params.get("state", [None])[0]

            if code:
                result[0] = OAuthCallback(code=code, state=state)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(_RESPONSE_HTML.encode())
            else:
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(_ERROR_HTML.encode())

            # Shut down after handling the callback
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def log_message(self, format: str, *args: object) -> None:
            pass  # Suppress request logging

    server = HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = timeout

    def serve() -> None:
        server_ready.set()
        server.serve_forever()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    server_ready.wait()

    # Wait for either the callback or timeout
    thread.join(timeout=timeout)
    if thread.is_alive():
        server.shutdown()
        thread.join(timeout=5)

    return result[0]
