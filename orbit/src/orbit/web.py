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
import re
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

from kit import llm, log, netguard
from kit.http import Fail, JsonHandler, host_ok

from . import answers, applenotes, browse, clock, db, insight, library_client, report, tagging, toolrun
from .modules import ALL, money
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


class State:
    """What the server remembers between requests. One person uses it, so this is simple on purpose."""

    def __init__(self, token: str | None = None) -> None:
        self.token = os.environ.get("ORBIT_TOKEN", "") if token is None else token  # when set, every request must carry it (see _authorised)
        self.session = (
            hashlib.sha256(b"orbit-session|" + self.token.encode()).hexdigest() if self.token else ""
        )  # what the cookie holds, so the password itself is never stored in the browser
        self.refused: list[float] = []  # when recent requests were refused, to slow down guessing
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


def inbox_dir() -> Path:
    return Path(os.environ.get("ORBIT_INBOX", Path.home() / "OrbitInbox")) / "notes"


def client_and_model(conn):
    client = llm.OllamaClient(db.get_setting(conn, "ollama_host", "") or None)
    return client, client.resolve(db.get_setting(conn, "model", llm.DEFAULT_MODEL))


def _take_documents(state: State, conn) -> list[str]:
    """Ask the Documents service to read everything new (files and mail), then take the documents that matter to Finance. Without the service address, nothing is taken."""
    if not library_client.base_url():
        return []
    try:
        problems = library_client.update(lambda m: state.importing.update(progress=m))
        library_client.pull(conn)
    except RuntimeError as exc:
        return [str(exc)]
    return problems


def start_import(state: State) -> bool:
    """Read new finance files in the background so the page stays responsive. Returns False if one is already running."""
    with state.import_lock:
        if state.importing["running"]:
            return False
        state.importing.update(running=True, progress="Starting...", result=None, error="")

    def work() -> None:
        conn = state.connect()
        try:
            problems = _take_documents(state, conn)
            try:
                client, model = client_and_model(conn)
            except RuntimeError as exc:
                log.failed("model unavailable for the import", exc)
                state.importing["error"] = "The local model is not running. Start Ollama and try again."
                return
            result = money.import_statements(conn, client=client, model=model, progress=lambda m: state.importing.update(progress=m))
            result["problems"] = [*problems, *result.get("problems", [])]
            state.importing["result"] = result
        except Exception as exc:  # noqa: BLE001 - shown on the page and logged, never lost
            log.failed("import failed", exc)
            state.importing["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            state.importing["running"] = False
            conn.close()

    threading.Thread(target=work, name="import", daemon=True).start()
    return True


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


def _get_tools(state: State, conn, query: dict[str, str]) -> dict:
    """What Finance can do, for the one assistant: every tool except the ones no AI may run."""
    return {
        "tools": [
            {"name": t.name, "description": t.description, "parameters": t.schema()["function"]["parameters"]}
            for t in registry(ALL).values()
            if t.name not in toolrun.NEVER_BY_AI
        ]
    }


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
    "/api/tools": _get_tools,
    "/api/settings": _get_settings,
    "/api/import": lambda state, conn, query: {"ok": True, **state.importing},
}


DELETE_WORDS = re.compile(r"\b(delete|remove|erase|clear|get rid)\b")


def _post_tool(state: State, conn, body: dict) -> dict:
    """Run one tool for the one assistant. A delete runs only if the person's own words asked for it (text inside a document can never make it happen),
    and a report is checked against the raw ledger first: if it does not tie, it is not given."""
    name = str(body.get("name", ""))
    if name not in registry(ALL) or name in toolrun.NEVER_BY_AI:
        raise Fail(400, f"unknown tool {name!r}")
    if name.startswith("delete_") and not DELETE_WORDS.search(str(body.get("user_text", "")).lower()):
        return {"ok": False, "data": None, "error": "refused: deleting needs you to ask for it in your own words"}
    args = body.get("args") or {}
    out, error = toolrun.run_tool(conn, name, args)
    data = json.loads(out)
    if error:
        return {"ok": False, "data": None, "error": data.get("error")}
    problems, notes = answers.check_tool(conn, name, args if isinstance(args, dict) else {}, out)
    if problems:
        return {
            "ok": False,
            "data": None,
            "error": "I can't give you that figure with confidence: " + problems[0] + ". Open Money > Files to see what needs a check.",
        }
    return {"ok": True, "data": data, "error": "", "notes": notes}


def _post_settings(state: State, conn, body: dict) -> dict:
    if isinstance(body.get("ollama_host"), str) and body["ollama_host"].strip():
        try:
            llm.OllamaClient(body["ollama_host"].strip())  # refuses anything that is not this computer or its private network
        except ValueError as exc:
            raise Fail(400, str(exc)) from exc
    for key in ("currency", "view_currency", "model", "ollama_host"):
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
        raise Fail(404, f"{inbox_dir()} not found - run `orbit export-notes` on your Mac first")
    return {"ok": True, **applenotes.import_dir(conn, inbox_dir())}


POST_ROUTES = {
    "/api/scan": lambda state, conn, body: {"ok": True, "started": start_import(state)},
    "/api/tool": _post_tool,
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


class _Handler(JsonHandler):
    """Plumbing only: security checks, files, and handing each API route to its function in the tables above."""

    state: ClassVar[State]
    server_version = "Finance"
    csp = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"

    # ---- plumbing ---------------------------------------------------------------------------------------------
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
        if not host_ok(host, ALLOWED_HOSTS):
            self._fail(HTTPStatus.FORBIDDEN, "This address is not allowed. Use http://127.0.0.1:8501")
            return False
        if not self._authorised():
            return False
        if not self._signed():
            self._fail(HTTPStatus.UNAUTHORIZED, "This request is not signed by the platform.")
            return False
        if writing:
            origin = self.headers.get("Origin")
            if self.headers.get("X-Orbit") != "1" or (origin and not host_ok(origin.split("://", 1)[-1], ALLOWED_HOSTS)):
                self._fail(HTTPStatus.FORBIDDEN, "Request refused.")
                return False
        return True

    def _run_api(self, routes: dict, path: str, *args) -> None:
        """Look the route up, run it with its own database connection, and turn every outcome into a response."""
        route = routes.get(path)
        if route is None:
            return self._fail(HTTPStatus.NOT_FOUND, "not found")
        conn = self.state.connect()
        try:
            self._json(route(self.state, conn, *args))
        except Fail as failure:
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
            and host_ok(self.headers.get("Host"), ALLOWED_HOSTS)
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
        if not host_ok(self.headers.get("Host"), ALLOWED_HOSTS):
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


def make_handler(state: State) -> type[_Handler]:
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
