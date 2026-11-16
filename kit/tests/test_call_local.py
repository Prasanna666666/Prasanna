"""What is said when a call to another service on this computer fails: the true reason, not always "not running"."""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from kit import http


def serve(handler_body):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            handler_body(self)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_an_error_answer_a_slow_answer_and_no_answer_are_told_apart(monkeypatch):
    monkeypatch.setattr(http.netguard, "allow_local", lambda host: None)
    monkeypatch.setattr(http.sign, "sign", lambda *a, **k: {})
    boom = serve(lambda h: (h.send_response(500), h.end_headers()))
    base = f"http://127.0.0.1:{boom.server_port}"
    with pytest.raises(RuntimeError, match=r"running but answered with an error \(HTTP 500\)"):
        http.call_local(base, "GET", "/x", "X-T", "not running")
    boom.shutdown()

    def slow(h):
        threading.Event().wait(3)

    sleepy = serve(slow)
    with pytest.raises(RuntimeError, match="running but did not answer within 1 seconds"):
        http.call_local(f"http://127.0.0.1:{sleepy.server_port}", "GET", "/x", "X-T", "not running", timeout=1)
    sleepy.shutdown()
    with pytest.raises(RuntimeError, match=r"^not running$"):
        http.call_local("http://127.0.0.1:1", "GET", "/x", "X-T", "not running")
