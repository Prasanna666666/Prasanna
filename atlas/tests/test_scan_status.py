"""What Atlas says about an app's reading, whatever the app answers: switched off only when it cannot be reached, never for an answer that is merely large or odd."""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from atlas.registry import Module
from atlas.upstream import Upstreams


class _Answers(BaseHTTPRequestHandler):
    mode = "ok"

    def log_message(self, *args) -> None:
        pass

    def do_GET(self) -> None:
        if self.mode == "close":
            self.connection.close()  # the connection ends before an answer
            return
        body = {
            "ok": json.dumps({"running": False, "steps": [], "problems": []}).encode(),
            "garbage": b"{not json",
            "big": b'{"running": false, "pad": "' + b"x" * 9_000_000 + b'"}',
        }[self.mode]
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def app():
    def start(mode: str) -> Upstreams:
        handler = type("H", (_Answers,), {"mode": mode})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        module = Module(id="docs", name="Documents", upstream=f"http://127.0.0.1:{server.server_address[1]}", scan="/api/scan", hidden=True)
        return Upstreams({"docs": module})

    servers: list[ThreadingHTTPServer] = []
    yield start
    for s in servers:
        s.shutdown()


def _report(upstreams: Upstreams) -> dict:
    return upstreams.scan()["modules"]["docs"]


def test_an_app_that_answers_is_up(app):
    assert _report(app("ok"))["up"] is True


def test_an_answer_that_cannot_be_read_is_not_switched_off(app):
    report = _report(app("garbage"))
    assert report["up"] is True and "could not read" in report["problems"][0]


def test_a_very_large_answer_is_read_whole(app):
    assert _report(app("big"))["up"] is True  # an 8 MB cap used to cut it off and call the app switched off


def test_a_closed_connection_is_said_in_plain_words(app):
    report = _report(app("close"))
    assert report["up"] is False and "closed the connection" in report["problems"][0]


def test_nothing_listening_says_so_in_plain_words():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    module = Module(id="docs", name="Documents", upstream=f"http://127.0.0.1:{port}", scan="/api/scan", hidden=True)
    report = Upstreams({"docs": module}).scan()["modules"]["docs"]
    assert report["up"] is False and "refused the connection" in report["problems"][0]
