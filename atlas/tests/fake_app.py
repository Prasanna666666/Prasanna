"""A stand-in for an app that follows the module contract, so the atlas is tested against a real server and a real socket."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class FakeApp:
    def __init__(self, token: str = "") -> None:
        self.token = token
        self.seen: list[dict[str, str]] = []
        app = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def _reply(self, status: int, body: bytes, ctype: str = "application/json", extra: dict[str, str] | None = None) -> None:
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                path = self.path.split("?", 1)[0]
                app.seen.append(
                    {
                        "method": "GET",
                        "path": self.path,
                        "host": self.headers.get("Host", ""),
                        "origin": self.headers.get("Origin", ""),
                        "token": self.headers.get("X-App-Token", ""),
                    }
                )
                if path == "/":
                    meta = f'<meta name="app-token" content="{app.token}">' if app.token else ""
                    self._reply(200, f"<!doctype html>{meta}<title>fake</title>".encode(), "text/html")
                elif path == "/api/health":
                    self._reply(200, b'{"ok": true}')
                elif path == "/api/search":
                    if app.token and self.headers.get("X-App-Token") != app.token:
                        self._reply(403, b'{"error": "token"}')
                    else:
                        self._reply(
                            200,
                            json.dumps(
                                {"results": [{"title": "Lisbon", "subtitle": "14 photos", "kind": "place", "link": "#/library?place=Lisbon"}, {"nope": 1}]}
                            ).encode(),
                        )
                elif path == "/api/stream":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    for n in range(3):
                        self.wfile.write(f"data: {n}\n\n".encode())
                        self.wfile.flush()
                        time.sleep(0.05)
                else:
                    self._reply(404, b'{"error": "not found"}')

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length)
                app.seen.append(
                    {"method": "POST", "path": self.path, "host": self.headers.get("Host", ""), "origin": self.headers.get("Origin", ""), "token": ""}
                )
                self._reply(200, json.dumps({"echo": body.decode()}).encode())

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
