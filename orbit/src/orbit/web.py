"""Finance's web interface: a small local server (standard library only) that serves the page and exposes the same tools the assistant uses.

Nothing here reaches the internet. It only answers requests for 127.0.0.1 / localhost (a request addressed to any other name is refused, which also
stops DNS-rebinding), and anything that changes data must carry a custom header that a web page on another site cannot send.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

from . import agent, applenotes, browse, clock, db, insight, llm, log, netguard, report, tagging
from .modules import ALL, documents, money
from .modules import tools as registry
from .modules.today import briefing_for

STATIC = Path(__file__).with_name("static")
ALLOWED_HOSTS = {
    "127.0.0.1",
    "localhost",
    "[::1]",
    "orbit.localhost",
    "finance.localhost",
}  # *.localhost always means this computer (RFC 6761): a name that is easy to remember
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

    def __init__(self, token: str | None = None) -> None:
        self.token = os.environ.get("ORBIT_TOKEN", "") if token is None else token  # when set, every request must carry it (see _authorised)
        self.session = (
            hashlib.sha256(b"orbit-session|" + self.token.encode()).hexdigest() if self.token else ""
        )  # what the cookie holds, so the password itself is never stored in the browser
        self.refused: list[float] = []  # when recent requests were refused, to slow down guessing
        self.history: list[dict] = []
        self.chat_lock = threading.Lock()
        self.importing: dict[str, Any] = {"running": False, "progress": "", "result": None, "error": ""}
        self.import_lock = threading.Lock()

    def connect(self):
        conn = db.connect()
        return conn


def _cookie(value: str) -> str:
    return f"orbit_k={value}; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000"


def _login_page(message: str = "") -> bytes:
    note = f"<p class=bad>{message}</p>" if message else ""
    return (
        "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Finance</title>"
        "<style>body{font:17px system-ui;display:grid;place-items:center;min-height:90vh;margin:0;background:#f6f6fb;color:#111}"
        "form{background:#fff;padding:2rem 2.2rem;border-radius:18px;box-shadow:0 6px 30px #0001;display:grid;gap:1rem;min-width:260px}"
        "input,button{font:inherit;padding:.8rem 1rem;border-radius:12px;border:1px solid #ccd}button{background:#6d5cff;color:#fff;border:0;cursor:pointer}"
        ".bad{color:#c0392b;margin:0}h1{margin:0;font-size:1.4rem}</style>"
        f"<form method=post action=/login><h1>Finance</h1>{note}<input type=password name=password placeholder=Password autofocus autocomplete=current-password>"
        "<button>Open</button></form>"
    ).encode()


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
                log.failed("model unavailable for the import", exc)
                state.importing["error"] = "The local model is not running. Start Ollama and try again."
                return
            state.importing["result"] = money.import_statements(conn, client=client, model=model, progress=lambda m: state.importing.update(progress=m))
        except Exception as exc:  # noqa: BLE001 - shown on the page and logged, never lost
            log.failed("import failed", exc)
            state.importing["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            state.importing["running"] = False
            conn.close()

    threading.Thread(target=work, name="import", daemon=True).start()
    return True


class _Fail(Exception):
    """A request that cannot be served: the status and the plain-words message sent back."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


# ---- the API: one small function per route, found in a table (the handler below only does plumbing) -----------------
def _get_home(state: State, conn, query: dict[str, str]) -> dict:
    return {
        "ok": True,
        "currency": db.display_currency(conn),
        "view": db.view_currency(conn),
        "briefing": briefing_for(conn, clock.today()),
        "trend": money.monthly_trend(conn, {"months": 6}),
        "upcoming": insight.upcoming_payments(conn, {"days": 21})[:4],
    }


def _get_status(state: State, conn, query: dict[str, str]) -> dict:
    try:
        client = llm.OllamaClient(db.get_setting(conn, "ollama_host", "") or None)
        return {"ok": True, "ai": True, "model": client.resolve(db.get_setting(conn, "model", llm.DEFAULT_MODEL))}
    except RuntimeError as exc:
        return {"ok": True, "ai": False, "problem": str(exc)}


def _get_settings(state: State, conn, query: dict[str, str]) -> dict:
    return {
        "ok": True,
        "currency": db.display_currency(conn),
        "view": db.view_currency(conn),
        "main_currency": db.get_setting(conn, "currency", "EUR"),
        "model": db.get_setting(conn, "model", llm.DEFAULT_MODEL),
        "ollama_host": db.get_setting(conn, "ollama_host", "") or llm.host(),
        "data": str(db.home()),
    }


def _get_history(state: State, conn, query: dict[str, str]) -> dict:
    return {"ok": True, "history": [h for h in state.history if h["role"] in ("user", "assistant") and h.get("content")]}


def _get_search(state: State, conn, query: dict[str, str]) -> dict:
    """Search for Atlas, the one address that searches every app: the same results as the search box, as a flat list with where each opens."""
    return {"results": browse.search_links(browse.search_all(conn, {"query": query.get("q", "")[:200]}))}


def _scan_status(state: State, conn, query: dict[str, str]) -> dict:
    """Where "read my new files" stands, in the shape every module reports it (the contract's scan status), for Atlas's one Update button."""
    job = state.importing
    result = job.get("result") or {}
    problems = [*([job["error"]] if job.get("error") else []), *result.get("problems", [])]
    read = result.get("files", 0)
    summary = f"{read} file{'s' if read != 1 else ''} read, {result.get('new_transactions', 0)} new payments" if result else ""
    return {
        "running": job["running"],
        "progress": job.get("progress", ""),
        "summary": summary,
        "problems": problems,
        "needs_check": len(result.get("needs_check", [])),
    }


GET_ROUTES = {
    "/api/scan": _scan_status,
    "/api/health": lambda state, conn, query: {"ok": True},
    "/api/search": _get_search,
    "/api/home": _get_home,
    "/api/status": _get_status,
    "/api/settings": _get_settings,
    "/api/import": lambda state, conn, query: {"ok": True, **state.importing},
    "/api/history": _get_history,
}


def _post_tool(state: State, conn, body: dict) -> dict:
    name = str(body.get("name", ""))
    if name not in registry(ALL):
        raise _Fail(400, f"unknown tool {name!r}")
    out, error = agent.run_tool(conn, name, body.get("args") or {})
    data = json.loads(out)
    return {"ok": not error, "data": None if error else data, "error": data.get("error") if error else ""}


def _post_chat(state: State, conn, body: dict) -> dict:
    text = str(body.get("text", "")).strip()[:4000]
    if not text:
        raise _Fail(400, "empty message")
    if not state.chat_lock.acquire(blocking=False):
        raise _Fail(429, "The assistant is still answering the last message.")
    try:
        trace: list = []
        reply = agent.chat(conn, state.history, text, trace=trace)
        del state.history[:-HISTORY_LIMIT]
        return {"ok": True, "reply": reply, "agent": trace[0]["agent"] if trace else "general", "tools": trace[0]["tools"] if trace else []}
    except Exception as exc:
        log.failed("chat failed", exc)
        raise _Fail(502, str(exc)) from exc
    finally:
        state.chat_lock.release()


def _document_items(conn, text: str, history: list) -> list[dict]:
    """The documents behind a question, only when the user asked to see them: the best matching files with a line of what they say.
    "Show me those documents" has no topic of its own, so the question before it is used."""
    from . import rag

    questions = [text, *[t for role, t in reversed(history) if role == "user" and isinstance(t, str)][:2]]
    hits: list[dict] = []
    for question in questions:
        hits = [h for h in rag.retrieve(conn, question, 12) if h["source"] in ("document", "file")]
        if hits:
            break
    seen: set[str] = set()
    items = []
    for h in hits:
        if h["title"] in seen:
            continue
        seen.add(h["title"])
        items.append(
            {
                "kind": "document",
                "title": h["title"],
                "subtitle": "from your files",
                "text": h["text"].replace("[", "").replace("]", "")[:300],
                "link": "#/documents",
            }
        )
    return items[:8]


def _post_ask(state: State, conn, body: dict) -> dict:
    """The contract's one-shot question, for Atlas's single chat: the same answer as the chat, in the shape every module returns it.
    Documents come back only when the user asked to see them (`show.documents`); finding files is a lookup, so it needs no model."""
    raw_show = body.get("show")
    show: dict = raw_show if isinstance(raw_show, dict) else {}
    if show.get("documents"):
        history = [h for h in (body.get("history") or []) if isinstance(h, list) and len(h) == 2]
        items = _document_items(conn, str(body.get("text", "")), history)
        if items:
            n = len(items)
            return {"ok": True, "text": f"I found {n} file{'s' if n != 1 else ''} about that.", "items": items, "agent": "files"}
    out = _post_chat(state, conn, body)
    return {"ok": True, "text": out["reply"], "items": [], "agent": out["agent"]}


def _post_chat_reset(state: State, conn, body: dict) -> dict:
    state.history.clear()
    return {"ok": True}


def _post_settings(state: State, conn, body: dict) -> dict:
    if isinstance(body.get("ollama_host"), str) and body["ollama_host"].strip():
        try:
            llm.OllamaClient(body["ollama_host"].strip())  # refuses anything that is not this computer or its private network
        except ValueError as exc:
            raise _Fail(400, str(exc)) from exc
    for key in ("currency", "view_currency", "model", "ollama_host", "reply_seconds"):
        if isinstance(body.get(key), str):
            db.set_setting(conn, key, body[key].upper()[:5] if key in ("currency", "view_currency") else body[key].strip()[:200])
    db.ledger_view(conn)
    return {"ok": True}


def _post_notes_tag(state: State, conn, body: dict) -> dict:
    try:
        client, model = client_and_model(conn)
        return {"ok": True, "tagged": tagging.autotag_notes(conn, client, model)}
    except RuntimeError:
        return {"ok": True, "tagged": tagging.autotag_notes(conn), "note": "The model was not available: rules only."}


def _post_notes_import(state: State, conn, body: dict) -> dict:
    if not inbox_dir().is_dir():
        raise _Fail(404, f"{inbox_dir()} not found - run `orbit export-notes` on your Mac first")
    return {"ok": True, **applenotes.import_dir(conn, inbox_dir())}


POST_ROUTES = {
    "/api/ask": _post_ask,
    "/api/scan": lambda state, conn, body: {"ok": True, "started": start_import(state)},
    "/api/tool": _post_tool,
    "/api/chat": _post_chat,
    "/api/chat/reset": _post_chat_reset,
    "/api/import": lambda state, conn, body: {"ok": True, "started": start_import(state)},
    "/api/settings": _post_settings,
    "/api/notes/tag": _post_notes_tag,
    "/api/notes/import": _post_notes_import,
}


def _refusals_this_minute(state: State) -> float:
    """Forget refusals older than a minute; returns now."""
    now = time.monotonic()
    state.refused[:] = [t for t in state.refused if now - t < 60]
    return now


class _Handler(BaseHTTPRequestHandler):
    """Plumbing only: security checks, files, and handing each API route to its function in the tables above."""

    state: ClassVar[State]
    server_version = "Finance"

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
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
        )
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: Any, status: int = 200) -> None:
        self._send(status, json.dumps(obj, default=str).encode())

    def _fail(self, status: int, message: str) -> None:
        self._json({"ok": False, "error": message}, status)

    def _redirect_with_cookie(self) -> None:
        """Remember the visit in a cookie that scripts on other sites cannot read or send, then go to the home page."""
        self.send_response(303)
        self.send_header("Set-Cookie", _cookie(self.state.session))
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _authorised(self) -> bool:
        """Other programs on this computer can reach the port too. With a token set, only a browser that opened the link printed by up.sh (which sets a cookie) gets in."""
        if not self.state.token:
            return True
        now = _refusals_this_minute(self.state)
        cookie = next((c.split("=", 1)[1] for c in self.headers.get("Cookie", "").split("; ") if c.startswith("orbit_k=")), "")
        if hmac.compare_digest(cookie.encode(), self.state.session.encode()):
            return True
        log.event("request refused: no valid token", level=logging.WARNING)
        self.state.refused.append(now)
        if len(self.state.refused) > 10:
            self._send(429, b'{"ok": false, "error": "Too many attempts. Wait a minute."}')
        else:
            self._send(401, _login_page(), "text/html; charset=utf-8")
        return False

    def _guard(self, writing: bool) -> bool:
        host = self.headers.get("Host", "")
        if not _host_ok(host):
            self._fail(HTTPStatus.FORBIDDEN, "This address is not allowed. Use http://127.0.0.1:8501")
            return False
        if not self._authorised():
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

    def _run_api(self, routes: dict, path: str, *args) -> None:
        """Look the route up, run it with its own database connection, and turn every outcome into a response."""
        route = routes.get(path)
        if route is None:
            return self._fail(HTTPStatus.NOT_FOUND, "not found")
        conn = self.state.connect()
        try:
            self._json(route(self.state, conn, *args))
        except _Fail as failure:
            self._fail(failure.status, failure.message)
        except Exception as exc:  # noqa: BLE001 - the error boundary of a request: report it, log it, keep serving
            log.failed("request failed", exc, path=path)
            self._fail(500, f"{type(exc).__name__}: {exc}")
        finally:
            conn.close()

    # ---- GET --------------------------------------------------------------------------------------------------
    def do_GET(self) -> None:
        path, _, query = self.path.partition("?")
        offered = urllib.parse.parse_qs(query).get("k", [""])[0]
        if (
            self.state.token
            and offered
            and path == "/"
            and hmac.compare_digest(offered.encode(), self.state.token.encode())
            and _host_ok(self.headers.get("Host"))
        ):
            return self._redirect_with_cookie()  # the link from up.sh: the token is dropped from the address bar
        if not self._guard(False):
            return
        if path in ("/", "/index.html"):
            return self._file("index.html")
        if path.startswith("/report/"):
            return self._report(path[len("/report/") :])
        if path.startswith("/static/"):
            return self._file(path[len("/static/") :])
        if path.startswith("/api/"):
            return self._run_api(GET_ROUTES, path, {k: v[0] for k, v in urllib.parse.parse_qs(query).items() if v})
        self._fail(HTTPStatus.NOT_FOUND, "not found")

    def _report(self, year: str) -> None:
        if not (year.isdigit() and len(year) == 4):
            return self._fail(HTTPStatus.NOT_FOUND, "not found")
        conn = self.state.connect()
        try:
            self._send(200, report.year_report(conn, year).encode(), "text/html; charset=utf-8")
        finally:
            conn.close()

    def _file(self, name: str) -> None:
        target = (STATIC / name).resolve()
        if STATIC.resolve() not in target.parents or not target.is_file():
            return self._fail(HTTPStatus.NOT_FOUND, "not found")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send(200, target.read_bytes(), f"{ctype}; charset=utf-8" if ctype.startswith("text/") or ctype.endswith("javascript") else ctype)

    # ---- POST -------------------------------------------------------------------------------------------------
    def _login(self) -> None:
        """The password form: the right password sets the cookie (once per browser); a wrong one is counted, and too many are refused for a minute."""
        if not _host_ok(self.headers.get("Host")):
            return self._fail(HTTPStatus.FORBIDDEN, "This address is not allowed.")
        now = _refusals_this_minute(self.state)
        if len(self.state.refused) > 10:
            return self._send(429, b"Too many attempts. Wait a minute.", "text/plain; charset=utf-8")
        try:
            size = min(int(self.headers.get("Content-Length", "0")), 2000)
        except ValueError:
            size = 0
        given = urllib.parse.parse_qs(self.rfile.read(size).decode("utf-8", "replace")).get("password", [""])[0]
        if self.state.token and hmac.compare_digest(given.encode(), self.state.token.encode()):
            return self._redirect_with_cookie()
        log.event("login refused: wrong password", level=logging.WARNING)
        self.state.refused.append(now)
        self._send(401, _login_page("That is not the password."), "text/html; charset=utf-8")

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/login":
            return self._login()
        if not self._guard(True):
            return
        self._run_api(POST_ROUTES, path, self._body())


def make_handler(state: State) -> type[BaseHTTPRequestHandler]:
    return type("Handler", (_Handler,), {"state": state})


def serve(host: str = "127.0.0.1", port: int = 8501) -> int:
    netguard.install()
    conn = db.connect()
    db.migrate(conn, ALL)
    conn.close()
    state = State()
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    threading.Thread(target=_warm, daemon=True).start()
    threading.Thread(target=_self_check, daemon=True).start()
    print(f"Finance is running on http://{host}:{port}", flush=True)
    with contextlib.suppress(KeyboardInterrupt):
        httpd.serve_forever()
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
    except Exception as exc:  # noqa: BLE001 - warming up is only a head start
        log.failed("model warm-up failed", exc)


def _self_check() -> None:
    """At start: run the self-test, take today's backup, and say aloud only if something is wrong."""
    try:
        conn = db.connect()
        try:
            for f in [*insight.self_test(conn), *insight.backup_status(conn)]:
                if f.level != "ok":
                    print(f"Finance: {f.agent}: {f.message}", flush=True)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - a failing check must never stop the app from starting
        log.failed("start-up check failed", exc)
        print(f"Finance: start-up check could not run: {type(exc).__name__}", flush=True)
