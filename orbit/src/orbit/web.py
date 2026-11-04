"""Orbit's web interface: a small local server (standard library only) that serves the page and exposes the same tools the assistant uses.

Nothing here reaches the internet. It only answers requests for 127.0.0.1 / localhost (a request addressed to any other name is refused, which also
stops DNS-rebinding), and anything that changes data must carry a custom header that a web page on another site cannot send.
"""

from __future__ import annotations

import json
import mimetypes
import os
import threading
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import agent, applenotes, db, llm, netguard, tagging
from .modules import ALL, documents, money
from .modules import tools as registry
from .modules.today import briefing_for

STATIC = Path(__file__).with_name("static")
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
MAX_BODY = 1_000_000
HISTORY_LIMIT = 24


def _host_ok(value: str | None) -> bool:
    """True for 127.0.0.1 / localhost / [::1] (with or without a port)."""
    if not value:
        return False
    host = value.strip().lower()
    host = host.split("]")[0] + "]" if host.startswith("[") else host.split(":")[0]
    return host in ALLOWED_HOSTS


class State:
    """What the server remembers between requests. One person uses it, so this is simple on purpose."""

    def __init__(self) -> None:
        self.history: list[dict] = []
        self.chat_lock = threading.Lock()
        self.importing: dict[str, Any] = {"running": False, "progress": "", "result": None, "error": ""}
        self.import_lock = threading.Lock()

    def connect(self):
        conn = db.connect()
        return conn


def parsed_dir() -> Path:
    return Path(os.environ.get("ORBIT_PARSED", Path.home() / "OrbitParsed"))


def inbox_dir() -> Path:
    return Path(os.environ.get("ORBIT_INBOX", Path.home() / "OrbitInbox")) / "notes"


def client_and_model(conn):
    client = llm.OllamaClient(db.get_setting(conn, "ollama_host", "") or None)
    return client, client.resolve(db.get_setting(conn, "model", llm.DEFAULT_MODEL))


def start_import(state: State) -> bool:
    """Read new finance files in the background so the page stays responsive. Returns False if one is already running."""
    with state.import_lock:
        if state.importing["running"]:
            return False
        state.importing.update(running=True, progress="Starting...", result=None, error="")

    def work() -> None:
        conn = state.connect()
        try:
            if parsed_dir().is_dir():
                documents.ingest_dir(conn, parsed_dir())
            try:
                client, model = client_and_model(conn)
            except RuntimeError as exc:
                state.importing["error"] = f"The local model is not available: {exc}"
                return
            state.importing["result"] = money.import_statements(
                conn, client=client, model=model, progress=lambda m: state.importing.update(progress=m))
        except Exception as exc:  # noqa: BLE001 - shown on the page, never lost
            state.importing["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            state.importing["running"] = False
            conn.close()

    threading.Thread(target=work, name="import", daemon=True).start()
    return True


def make_handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Orbit"

        def log_message(self, *args) -> None:  # quiet: requests may contain private words
            return

        # ---- plumbing ---------------------------------------------------------------------------------------------
        def _send(self, status: int, body: bytes, ctype: str = "application/json; charset=utf-8", extra: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj: Any, status: int = 200) -> None:
            self._send(status, json.dumps(obj, default=str).encode())

        def _fail(self, status: int, message: str) -> None:
            self._json({"ok": False, "error": message}, status)

        def _guard(self, writing: bool) -> bool:
            host = self.headers.get("Host", "")
            if not _host_ok(host):
                self._fail(HTTPStatus.FORBIDDEN, "This address is not allowed. Use http://127.0.0.1:8501")
                return False
            if writing:
                origin = self.headers.get("Origin")
                if self.headers.get("X-Orbit") != "1" or (origin and not _host_ok(origin.split("://", 1)[-1])):
                    self._fail(HTTPStatus.FORBIDDEN, "Request refused.")
                    return False
            return True

        def _body(self) -> dict:
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 <= size <= MAX_BODY:
                    return {}
                data = json.loads(self.rfile.read(size) or b"{}")
                return data if isinstance(data, dict) else {}
            except (ValueError, OSError):
                return {}

        # ---- GET --------------------------------------------------------------------------------------------------
        def do_GET(self) -> None:  # noqa: N802
            if not self._guard(False):
                return
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                return self._file("index.html")
            if path.startswith("/static/"):
                return self._file(path[len("/static/"):])
            if path.startswith("/api/"):
                try:
                    return self._api_get(path)
                except Exception as exc:  # noqa: BLE001
                    return self._fail(500, f"{type(exc).__name__}: {exc}")
            self._fail(HTTPStatus.NOT_FOUND, "not found")

        def _file(self, name: str) -> None:
            target = (STATIC / name).resolve()
            if STATIC.resolve() not in target.parents or not target.is_file():
                return self._fail(HTTPStatus.NOT_FOUND, "not found")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self._send(200, target.read_bytes(), f"{ctype}; charset=utf-8" if ctype.startswith("text/") or ctype.endswith("javascript") else ctype)

        def _api_get(self, path: str) -> None:
            conn = state.connect()
            try:
                if path == "/api/home":
                    return self._json({"ok": True, "currency": db.get_setting(conn, "currency", "EUR"),
                                       "briefing": briefing_for(conn, date.today()), "trend": money.monthly_trend(conn, {"months": 6})})
                if path == "/api/status":
                    try:
                        client = llm.OllamaClient(db.get_setting(conn, "ollama_host", "") or None)
                        model = client.resolve(db.get_setting(conn, "model", llm.DEFAULT_MODEL))
                        return self._json({"ok": True, "ai": True, "model": model})
                    except RuntimeError as exc:
                        return self._json({"ok": True, "ai": False, "problem": str(exc)})
                if path == "/api/settings":
                    return self._json({"ok": True, "currency": db.get_setting(conn, "currency", "EUR"),
                                       "model": db.get_setting(conn, "model", llm.DEFAULT_MODEL),
                                       "ollama_host": db.get_setting(conn, "ollama_host", "") or llm.host(), "data": str(db.home())})
                if path == "/api/import":
                    return self._json({"ok": True, **state.importing})
                if path == "/api/history":
                    return self._json({"ok": True, "history": [h for h in state.history if h["role"] in ("user", "assistant") and h.get("content")]})
            finally:
                conn.close()
            self._fail(HTTPStatus.NOT_FOUND, "not found")

        # ---- POST -------------------------------------------------------------------------------------------------
        def do_POST(self) -> None:  # noqa: N802
            if not self._guard(True):
                return
            body = self._body()
            conn = state.connect()
            try:
                self._api_post(self.path.split("?", 1)[0], body, conn)
            except Exception as exc:  # noqa: BLE001
                self._fail(500, f"{type(exc).__name__}: {exc}")
            finally:
                conn.close()

        def _api_post(self, path: str, body: dict, conn) -> None:
            if path == "/api/tool":
                name = str(body.get("name", ""))
                if name not in registry(ALL):
                    return self._fail(400, f"unknown tool {name!r}")
                out, error = agent.run_tool(conn, name, body.get("args") or {})
                data = json.loads(out)
                return self._json({"ok": not error, "data": None if error else data, "error": data.get("error") if error else ""})
            if path == "/api/chat":
                text = str(body.get("text", "")).strip()[:4000]
                if not text:
                    return self._fail(400, "empty message")
                if not state.chat_lock.acquire(blocking=False):
                    return self._fail(429, "Orbit is still answering the last message.")
                try:
                    trace: list = []
                    reply = agent.chat(conn, state.history, text, trace=trace)
                    del state.history[:-HISTORY_LIMIT]
                    return self._json({"ok": True, "reply": reply, "agent": trace[0]["agent"] if trace else "general",
                                       "tools": trace[0]["tools"] if trace else []})
                except Exception as exc:  # noqa: BLE001 - e.g. the model is not running: say so plainly
                    return self._fail(502, str(exc))
                finally:
                    state.chat_lock.release()
            if path == "/api/chat/reset":
                state.history.clear()
                return self._json({"ok": True})
            if path == "/api/import":
                return self._json({"ok": True, "started": start_import(state)})
            if path == "/api/settings":
                for key in ("currency", "model", "ollama_host"):
                    if isinstance(body.get(key), str):
                        db.set_setting(conn, key, body[key].upper()[:5] if key == "currency" else body[key].strip()[:200])
                return self._json({"ok": True})
            if path == "/api/notes/tag":
                try:
                    client, model = client_and_model(conn)
                    return self._json({"ok": True, "tagged": tagging.autotag_notes(conn, client, model)})
                except RuntimeError:
                    return self._json({"ok": True, "tagged": tagging.autotag_notes(conn), "note": "The model was not available: rules only."})
            if path == "/api/notes/import":
                if not inbox_dir().is_dir():
                    return self._fail(404, f"{inbox_dir()} not found - run `orbit export-notes` on your Mac first")
                return self._json({"ok": True, **applenotes.import_dir(conn, inbox_dir())})
            self._fail(HTTPStatus.NOT_FOUND, "not found")

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8501) -> int:
    netguard.install()
    conn = db.connect()
    db.migrate(conn, ALL)
    conn.close()
    state = State()
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    threading.Thread(target=_warm, daemon=True).start()
    print(f"Orbit is running on http://{host}:{port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def _warm() -> None:
    """Load the local model in the background so the first message does not wait for it."""
    try:
        conn = db.connect()
        try:
            client, model = client_and_model(conn)
        finally:
            conn.close()
        client.warm(model)
    except Exception:  # noqa: BLE001 - only a head start
        pass
