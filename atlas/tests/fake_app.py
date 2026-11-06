"""A stand-in for an app that follows the module contract, so the atlas is tested against a real server and a real socket."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar


class _Handler(BaseHTTPRequestHandler):
    app: ClassVar[FakeApp]

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
        self.app.seen.append(
            {
                "method": "GET",
                "path": self.path,
                "host": self.headers.get("Host", ""),
                "origin": self.headers.get("Origin", ""),
                "token": self.headers.get("X-App-Token", ""),
            }
        )
        if path == "/":
            meta = f'<meta name="app-token" content="{self.app.token}">' if self.app.token else ""
            self._reply(200, f"<!doctype html>{meta}<title>fake</title>".encode(), "text/html")
        elif path == "/api/health":
            self._reply(200, b'{"ok": true}')
        elif path == "/api/trips":
            self._reply(200, json.dumps({"trips": self.app.trips}).encode())
        elif path == "/api/search":
            if self.app.token and self.headers.get("X-App-Token") != self.app.token:
                self._reply(403, b'{"error": "token"}')
            else:
                self._reply(
                    200,
                    json.dumps(
                        {"results": [{"title": "Lisbon", "subtitle": "14 photos", "kind": "place", "link": "#/library?place=Lisbon"}, {"nope": 1}]}
                    ).encode(),
                )
        elif path == "/api/photo/1/thumb":
            if self.app.token and self.headers.get("X-App-Token") != self.app.token:
                self._reply(403, b"no")
            else:
                self._reply(200, b"\x89PNG fake", "image/png")
        elif path == "/api/tags":
            self._reply(200, b'{"models": [{"name": "ministral-3:3b"}, {"name": "other:7b"}]}')
        elif path == "/api/scan":
            if self.app.token and self.headers.get("X-App-Token") != self.app.token:
                self._reply(403, b'{"error": "token"}')
            else:
                done = {
                    "running": self.app.scanning,
                    "progress": "reading" if self.app.scanning else "",
                    "summary": "" if self.app.scanning else "3 files read",
                    "problems": ["one needs a look"] if not self.app.scanning else [],
                    "needs_check": 1,
                }
                self._reply(200, json.dumps(done).encode())
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

    def _post_ask(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if self.app.require_header and self.headers.get(self.app.require_header) != "1":
            return self._reply(403, b'{"error": "header"}')
        if self.app.token and self.headers.get("X-App-Token") != self.app.token:
            return self._reply(403, b'{"error": "token"}')
        self.app.asked.append(body)
        items = (
            [{"kind": "photo", "id": 1, "thumb": "/api/photo/1/thumb", "link": "#/library"}, {"kind": "photo", "thumb": "/etc/passwd"}]
            if self.app.token
            else []
        )
        if (body.get("show") or {}).get("documents") and not self.app.token:
            items = [
                {"kind": "document", "title": "ziggo.pdf", "subtitle": "from your files", "text": "Ziggo invoice", "link": "#/documents"},
                {"kind": "document"},
            ]
        self._reply(200, json.dumps({"text": f"answer to: {body['text']}", "items": items, "total": 41, "notes": ["one note"]}).encode())

    def _post_model_chat(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        self.app.model_calls.append(body)
        wants_json = body.get("format") == "json" and self.app.plan_reply is not None
        reply = self.app.plan_reply if wants_json else self.app.model_reply
        self._reply(200, json.dumps({"message": {"role": "assistant", "content": reply}}).encode())

    def do_POST(self) -> None:
        if self.path == "/api/ask":
            return self._post_ask()
        if self.path == "/api/chat":
            return self._post_model_chat()
        if self.path == "/api/scan":
            if self.app.require_header and self.headers.get(self.app.require_header) != "1":
                self._reply(403, b'{"error": "header"}')
                return
            if self.app.token and self.headers.get("X-App-Token") != self.app.token:
                self._reply(403, b'{"error": "token"}')
                return
            self.app.scanning = True
            self._reply(200, b'{"started": true}')
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        self.app.seen.append({"method": "POST", "path": self.path, "host": self.headers.get("Host", ""), "origin": self.headers.get("Origin", ""), "token": ""})
        self._reply(200, json.dumps({"echo": body.decode()}).encode())


class FakeApp:
    def __init__(self, token: str = "") -> None:
        self.token = token
        self.seen: list[dict[str, str]] = []
        self.scanning = False
        self.asked: list[dict[str, object]] = []
        self.trips: list[dict[str, object]] = []
        self.model_reply = "fake model reply"
        self.plan_reply: str | None = None  # what the model answers when asked for JSON (the planner)
        self.model_calls: list[dict[str, object]] = []
        self.require_header = ""
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), type("Handler", (_Handler,), {"app": self}))
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
