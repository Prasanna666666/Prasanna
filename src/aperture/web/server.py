"""The local server behind Lumo's web app (standard library only).

Why not Streamlit for the chat: Streamlit re-runs the whole page on every click, and each run touches the external drive.
Here the page is static, the browser keeps the conversation, and the server only does real work: planning, searching and
streaming the reply. Photo matches stream in first (milliseconds), then the checked answer, then the words as they are written.

Safety: loopback only; every request must name this host (no DNS rebinding); the API needs a random per-run token (no cross-site
requests); strict Content-Security-Policy (no external scripts, styles or images); photos are served only from Aperture's own
thumbnail/preview folders, by numeric id.
"""

from __future__ import annotations

import hmac
import json
import logging
import re
import secrets
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import numpy as np

from .. import library as lib
from ..agent.llm import CALL_LOG
from ..config import preview_rel, thumb_rel
from ..indexing.progress import ScanLock

STATIC = Path(__file__).parent / "static"
STATIC_FILES = {"app.css": "text/css; charset=utf-8", "app.js": "text/javascript; charset=utf-8"}
MAX_BODY = 64 * 1024
PAGE = 60
PREVIEW = 24
DEFAULT_IDEAS = ["Photos from last summer", "Pictures of dogs", "Night photos", "Receipts and documents", "Screenshots", "Sunsets"]
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
ID_PATH = re.compile(r"^/api/photo/(\d{1,12})/(thumb|preview)$")
ITEM_PATH = re.compile(r"^/api/item/(\d{1,12})$")


def build_id() -> str:
    """Which code is running (the git commit), so 'is it the new version?' is never a guess."""
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).parent, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


class Web:
    """State shared by every request."""

    def __init__(self, ctx: Any, port: int, token: str | None = None) -> None:
        self.ctx = ctx
        self.port = port
        self.token = token or secrets.token_urlsafe(24)
        self.ai_lock = threading.Lock()  # one AI request at a time: the model runs on a single runner
        self._convs: OrderedDict[str, np.ndarray] = OrderedDict()
        self._cache: dict[str, tuple[float, Any]] = {}
        self.paused_for_chat = False
        self.build = build_id()
        self._sets: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._counts: dict[str, int] = {"photos": 0, "indexed": 0}
        self._counts_at: float | None = None
        self._counting = False

    def refresh_counts_async(self, every: float = 120.0) -> None:
        """Counting the library scans a table on the external drive: do it in the background, never while a request waits."""
        if self._counting or (self._counts_at is not None and time.monotonic() - self._counts_at < every):
            return
        self._counting = True

        def work() -> None:
            try:
                conn = self.ctx.db.connect()
                try:
                    cov = lib.coverage(conn)
                    self._counts = {"photos": cov.total, "indexed": cov.indexed}
                finally:
                    conn.close()
            except Exception:
                pass
            finally:
                self._counts_at = time.monotonic()
                self._counting = False

        threading.Thread(target=work, name="library-counts", daemon=True).start()

    # ---- conversations remember their last result set, so "only the ones from March" works
    def remember_set(self, ids: np.ndarray, groups: list[tuple[str, np.ndarray]]) -> str:
        """Every answer keeps its OWN photos and readings under its own id, so scrolling back to an earlier answer and using its tabs or
        'Show more' always gives that answer's photos, never the newest ones."""
        rid = secrets.token_hex(8)
        self._sets[rid] = {"ids": ids, "groups": groups}
        while len(self._sets) > 60:
            self._sets.pop(next(iter(self._sets)))
        return rid

    def remember(self, conv: str, ids: np.ndarray) -> None:
        self._convs[conv] = ids
        self._convs.move_to_end(conv)
        while len(self._convs) > 20:
            self._convs.popitem(last=False)

    def previous(self, conv: str) -> np.ndarray | None:
        ids = self._convs.get(conv)
        return ids if ids is not None and len(ids) else None

    def results(self, conv: str, offset: int, limit: int = PAGE, group: int = -1, rid: str = "") -> dict[str, Any]:
        found = self._sets.get(rid)
        if found is not None:
            groups = found["groups"]
            chosen = groups[group][1] if 0 <= group < len(groups) else found["ids"]
            if group >= 0 and offset == 0:
                self._convs[conv] = chosen  # the next message refines the photos the user is looking at
            return {"ids": [int(i) for i in chosen[offset:offset + limit]], "total": int(len(chosen))}
        ids = self._convs.get(conv)
        if ids is None:
            return {"ids": [], "total": 0}
        return {"ids": [int(i) for i in ids[offset:offset + limit]], "total": int(len(ids))}

    # ---- small cache so polling the status never hits the drive or the AI server more than every few seconds
    def coverage_note(self) -> str:
        """How complete the locations are, so 'are you sure you found them all?' can be answered truthfully."""
        def compute() -> str:
            conn = self.ctx.db.connect()
            try:
                total, own, worked = conn.execute(
                    "SELECT COUNT(*), COALESCE(SUM(gps_lat IS NOT NULL),0), COALESCE(SUM(gps_lat IS NULL AND gps_est_lat IS NOT NULL),0) "
                    "FROM items WHERE missing=0 AND meta_done=1").fetchone()
            except Exception:
                return ""
            finally:
                conn.close()
            none = total - own - worked
            extra = f", {worked:,} more were placed by time or appearance" if worked else ""
            return (f"Location coverage: of {total:,} photos, {own:,} have a location in their own file{extra}; {none:,} have no location, "
                    "so a search by place cannot find them.")

        return self.cached("coverage_note", 300.0, compute)

    def cached(self, key: str, ttl: float, fn):
        now = time.monotonic()
        hit = self._cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        value = fn()
        self._cache[key] = (now, value)
        return value

    def set_cloud(self, on: bool) -> dict[str, Any]:
        """The header switch. Turning it on needs the cloud to be set up and its gateway running; every launch starts with it off."""
        from ..launcher import gateway_up

        if on and not self.ctx.settings.cloud_interpreter:
            return {"ok": False, "error": "The cloud is not set up. Run: .venv/bin/python -m aperture cloud enable"}
        if on and not gateway_up(self.ctx.settings.cloud_port):
            return {"ok": False, "error": "The cloud connection is not running. Restart the app: .venv/bin/python -m aperture install-service"}
        if on:  # a real request first: it only turns on if the cloud really answers
            from ..cloud.client import check

            problem = check(self.ctx.settings.cloud_port)
            if problem:
                return {"ok": False, "error": f"The cloud did not answer, so it stays off. {problem}"}
        self.ctx.cloud_on = on
        self._cache.pop("cloud_up", None)
        return {"ok": True, "cloud": self.cloud_info()}

    def cloud_info(self) -> dict[str, Any]:
        """Whether a cloud model is reading the typed questions (names hidden) and what it has cost this month, shown in the header."""
        if not self.ctx.settings.cloud_interpreter:
            return {"state": "off"}  # not set up
        if not getattr(self.ctx, "cloud_on", False):
            return {"state": "local"}  # set up, switched off: nothing leaves the Mac
        from ..launcher import gateway_status

        info = self.cached("cloud_up", 10, lambda: gateway_status(self.ctx.settings.cloud_port))
        if info is None:
            return {"state": "down"}
        return {"state": "connected", "spent": info.get("spent_usd"), "cap": info.get("cap_usd")}

    def status(self) -> dict[str, Any]:
        ctx = self.ctx

        self.refresh_counts_async()
        healthy = self.cached("ai", 10, lambda: bool(ctx.llm().health()[0]))
        return {**self._counts, "ai": healthy, "model": ctx.settings.ollama_model, "build": self.build,
                "search_ready": bool(ctx.search_ready()), "warm_problem": ctx.warm_problem(), "cloud": self.cloud_info(),
                "indexing": ScanLock(ctx.paths).running(verify=True),
                "paused_for_chat": self.paused_for_chat}

    def suggestions(self) -> list[str]:
        def build() -> list[str]:
            from ..ui.suggestions import suggest_prompts

            conn = self.ctx.db.connect()
            try:
                return suggest_prompts(conn, 6) or DEFAULT_IDEAS
            finally:
                conn.close()

        try:
            return self.cached("ideas", 120, build)
        except Exception:
            return DEFAULT_IDEAS

    def pause_indexing_for_chat(self) -> None:
        lock = ScanLock(self.ctx.paths)
        if lock.running(verify=True):
            lock.stop()
            self.paused_for_chat = True

    def resume_indexing(self) -> bool:
        if ScanLock(self.ctx.paths).running(verify=True):
            return False
        try:
            self.ctx.llm().unload()  # free the AI model's RAM before indexing starts
        except Exception:
            pass
        subprocess.Popen([sys.executable, "-m", "aperture", "scan"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)  # noqa: S603
        self.paused_for_chat = False
        return True

    def item(self, item_id: int) -> dict[str, Any] | None:
        conn = self.ctx.db.connect()
        try:
            found = lib.items_by_ids(conn, [item_id]).get(item_id)
        finally:
            conn.close()
        if found is None:
            return None
        return {"id": item_id, "name": Path(found.rel_path or found.path).name, "taken": found.taken_at, "place": found.place,
                "camera": found.camera, "width": found.width, "height": found.height}

    def photo_file(self, item_id: int, kind: str) -> Path | None:
        data = self.ctx.paths.data.resolve()
        path = (data / (thumb_rel(item_id) if kind == "thumb" else preview_rel(item_id))).resolve()
        return path if data in path.parents and path.is_file() else None


def _clean_history(raw: Any) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    for entry in raw if isinstance(raw, list) else []:
        if isinstance(entry, (list, tuple)) and len(entry) == 2 and entry[0] in ("user", "assistant") and isinstance(entry[1], str):
            turns.append((entry[0], entry[1][:2000]))
    return turns[-8:]


log = logging.getLogger(__name__)
ASK_LIMIT = 45.0  # the last resort: whatever happens inside, a question ends with an answer or an apology, never a spinner that never stops


def ask_within(work: Any, limit: float, on_status: Any = None) -> Any:
    """Run one question, but stop waiting for it after `limit` seconds. `on_status(text)` receives what it is doing, as it happens."""
    import queue

    from ..agent import progress
    from ..agent.service import AgentReply

    box: dict[str, Any] = {}
    statuses: queue.Queue[str] = queue.Queue()

    def run() -> None:
        from ..agent.llm import DEADLINE

        DEADLINE.set(time.monotonic() + limit)  # every model call for this question gives up at the same moment
        progress.begin(statuses.put)
        try:
            box["reply"] = work()
        except BaseException as exc:  # carried back to the request that asked
            box["error"] = exc

    import contextvars

    context = contextvars.copy_context()  # the helper thread must see the same per-message state (such as the record of model calls)
    worker = threading.Thread(target=lambda: context.run(run), name="ask", daemon=True)
    worker.start()
    give_up = time.monotonic() + limit
    last = ""
    while worker.is_alive() and time.monotonic() < give_up:
        worker.join(0.2)
        while on_status is not None:
            try:
                last = statuses.get_nowait()
                on_status(last)
            except queue.Empty:
                break
    while on_status is not None:  # whatever it said just before finishing
        try:
            on_status(statuses.get_nowait())
        except queue.Empty:
            break
    if worker.is_alive():
        import sys
        import traceback

        frame = sys._current_frames().get(worker.ident)  # exactly where it is stuck, so the cause can be read from the log
        where = "".join(traceback.format_stack(frame)[-8:]) if frame is not None else "unknown"
        log.warning("a question was still running after %.0f s (last step: %s); the answer was given up. Stuck at:\n%s", limit, last or "none", where)
        return AgentReply("error", "That is taking longer than it should. Please try again, or ask it in a simpler way."
                                   + (f" (It was at: {last.lower()}.)" if last else ""))
    if "error" in box:
        raise box["error"]
    return box["reply"]


def memory_of(reply: Any, text: str, coverage: str = "") -> str:
    """What the conversation remembers of an answer: the words shown plus what was searched, so a follow-up ('why these?') can be answered."""
    parts = [text]
    groups = getattr(reply, "groups", None) or []
    if groups:
        parts.append("Readings considered: " + "; ".join(f"{label} ({len(ids):,})" for label, ids in groups[:5]))
    notes = list(getattr(reply, "notes", None) or [])
    if notes:
        parts.append("Notes: " + " ".join(str(n) for n in notes[:3]))
    if coverage and groups:
        parts.append(coverage)
    return " | ".join(p for p in parts if p)[:900]


def make_handler(web: Web) -> type[BaseHTTPRequestHandler]:
    # *.localhost always resolves to this Mac (RFC 6761), so the friendly address the installer prints is as safe as 127.0.0.1
    allowed_hosts = {f"127.0.0.1:{web.port}", f"localhost:{web.port}", f"lumo.localhost:{web.port}"}
    allowed_origins = {f"http://{h}" for h in allowed_hosts}

    class Handler(BaseHTTPRequestHandler):
        server_version = "Lumo"
        sys_version = ""

        def log_message(self, fmt: str, *args: Any) -> None:  # quiet: nothing about your photos goes to a log
            pass

        # ---- helpers -------------------------------------------------------------------------------------------------
        def _headers(self, status: int, ctype: str, length: int | None = None, cache: str = "no-store") -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            if length is not None:
                self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", cache)
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()

        def _json(self, obj: Any, status: int = 200) -> None:
            body = json.dumps(obj).encode()
            self._headers(status, "application/json; charset=utf-8", len(body))
            self.wfile.write(body)

        def _deny(self, status: HTTPStatus, message: str) -> None:
            self._json({"error": message}, int(status))

        def _checked(self, api: bool) -> bool:
            if self.headers.get("Host", "") not in allowed_hosts:
                self._deny(HTTPStatus.FORBIDDEN, "unknown host")
                return False
            origin = self.headers.get("Origin")
            if origin is not None and origin not in allowed_origins:
                self._deny(HTTPStatus.FORBIDDEN, "unknown origin")
                return False
            if api:
                query = parse_qs(urlparse(self.path).query)
                given = self.headers.get("X-Lumo-Token") or (query.get("t") or [""])[0]
                if not hmac.compare_digest(given.encode(), web.token.encode()):
                    self._deny(HTTPStatus.FORBIDDEN, "missing or wrong token")
                    return False
            return True

        def _sse(self, event: str, data: Any) -> None:
            self.wfile.write(f"event: {event}\ndata: {json.dumps(data)}\n\n".encode())
            self.wfile.flush()

        # ---- GET -----------------------------------------------------------------------------------------------------
        def do_GET(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            path = url.path
            if path == "/api/health":
                if self._checked(False):
                    self._json({"ok": True})
                return
            if path == "/" or path == "/index.html":
                if self._checked(False):
                    html = (STATIC / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", web.token)
                    body = html.encode()
                    self._headers(200, "text/html; charset=utf-8", len(body))
                    self.wfile.write(body)
                return
            if path.startswith("/static/"):
                name = path[len("/static/"):]
                if self._checked(False):
                    if name in STATIC_FILES:
                        body = (STATIC / name).read_bytes()
                        self._headers(200, STATIC_FILES[name], len(body))
                        self.wfile.write(body)
                    else:
                        self._deny(HTTPStatus.NOT_FOUND, "not found")
                return
            if not path.startswith("/api/"):
                self._deny(HTTPStatus.NOT_FOUND, "not found")
                return
            if not self._checked(True):
                return
            if path == "/api/status":
                self._json(web.status())
            elif path == "/api/suggestions":
                self._json({"ideas": web.suggestions()})
            elif path == "/api/results":
                query = parse_qs(url.query)
                try:
                    offset = max(0, int((query.get("offset") or ["0"])[0]))
                except ValueError:
                    offset = 0
                try:
                    group = int((query.get("group") or ["-1"])[0])
                except ValueError:
                    group = -1
                self._json(web.results((query.get("conv") or [""])[0][:64], offset, group=group, rid=(query.get("rid") or [""])[0][:32]))
            elif (m := ID_PATH.match(path)):
                file = web.photo_file(int(m.group(1)), m.group(2))
                if file is None:
                    self._deny(HTTPStatus.NOT_FOUND, "no such photo")
                else:
                    body = file.read_bytes()
                    self._headers(200, "image/jpeg", len(body), cache="private, max-age=86400")
                    self.wfile.write(body)
            elif (m := ITEM_PATH.match(path)):
                found = web.item(int(m.group(1)))
                self._json(found) if found else self._deny(HTTPStatus.NOT_FOUND, "no such photo")
            else:
                self._deny(HTTPStatus.NOT_FOUND, "not found")

        # ---- POST ----------------------------------------------------------------------------------------------------
        def _body(self) -> dict[str, Any] | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if not 0 < length <= MAX_BODY:
                self._deny(HTTPStatus.REQUEST_ENTITY_TOO_LARGE if length > MAX_BODY else HTTPStatus.BAD_REQUEST, "bad body size")
                return None
            try:
                data = json.loads(self.rfile.read(length))
            except ValueError:
                self._deny(HTTPStatus.BAD_REQUEST, "bad json")
                return None
            return data if isinstance(data, dict) else None

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if not self._checked(True):
                return
            if path == "/api/scan/resume":
                self._json({"started": web.resume_indexing()})
                return
            if path == "/api/cloud":
                body = self._body()
                if body is not None:
                    self._json(web.set_cloud(bool(body.get("on"))))
                return
            if path != "/api/chat":
                self._deny(HTTPStatus.NOT_FOUND, "not found")
                return
            body = self._body()
            if body is None:
                return
            message = str(body.get("message", "")).strip()[:2000]
            if not message:
                self._deny(HTTPStatus.BAD_REQUEST, "empty message")
                return
            self._chat(message, str(body.get("conv", ""))[:64] or "default", _clean_history(body.get("history")))

        def _chat(self, message: str, conv: str, history: list[tuple[str, str]]) -> None:
            self._headers(200, "text/event-stream; charset=utf-8")
            started = time.perf_counter()
            stream = None
            first_words = None
            calls: list[dict[str, Any]] = []
            log_token = CALL_LOG.set(calls)  # every model call made for this message is recorded here
            try:
                self._sse("ack", {})
                ctx = web.ctx
                if ctx.settings.quick_preview and ctx.search_ready():  # photo matches in milliseconds, before the AI has finished
                    ids = self._instant_matches(message)
                    if ids is not None and len(ids):
                        self._sse("preview", {"ids": [int(i) for i in ids[:PREVIEW]], "total": int(len(ids))})
                with web.ai_lock:
                    web.pause_indexing_for_chat()  # indexing and the AI model together would swap an 8 GB Mac
                    reply = ask_within(lambda: ctx.agent().ask(message, web.previous(conv), history=history), ASK_LIMIT,
                                       lambda text: self._sse("status", {"text": text}))
                    stream = reply.stream
                    text = reply.text
                    if len(reply.ids) and reply.kind in ("results", "export", "count"):  # the photos are known before the words
                        web.remember(conv, reply.ids)
                        rid = web.remember_set(reply.ids, reply.groups)
                        self._sse("results", {"rid": rid, "groups": [{"label": g[0], "count": int(len(g[1]))} for g in reply.groups], "ids": [] if reply.kind == "count" else [int(i) for i in reply.ids[:PAGE]], "total": int(len(reply.ids)), "kind": reply.kind,
                                              "notes": list(reply.notes), "warnings": list(reply.warnings)})
                    elif reply.notes or reply.warnings:
                        self._sse("notes", {"notes": list(reply.notes), "warnings": list(reply.warnings)})
                    if stream is not None:
                        parts = []
                        for chunk in stream:
                            if first_words is None:
                                first_words = round(time.perf_counter() - started, 2)
                            parts.append(chunk)
                            self._sse("delta", {"text": chunk})
                        text = "".join(parts) or "..."
                    else:
                        self._sse("reply", {"text": text})
                took = round(time.perf_counter() - started, 2)
                timings = {**reply.timings, **({"first_words": first_words} if first_words is not None else {})}
                self._sse("done", {"took": took, "kind": reply.kind, "text": text, "record": memory_of(reply, text, web.coverage_note()), "timings": timings, "trace": calls})
            except (BrokenPipeError, ConnectionResetError):
                pass  # the browser left (for example a new chat was started): stop quietly
            except Exception as exc:
                try:
                    self._sse("error", {"message": str(exc) or exc.__class__.__name__})
                except OSError:
                    pass
            finally:
                CALL_LOG.reset(log_token)
                if stream is not None and hasattr(stream, "close"):
                    stream.close()

        def _instant_matches(self, message: str) -> np.ndarray | None:
            from ..search.quick import quick_ids

            ctx = web.ctx
            conn = ctx.db.connect()
            try:
                return quick_ids(conn, message, ctx.embedding_index, ctx.search_embedder, ctx.settings.visual_strictness)
            except Exception:
                return None
            finally:
                conn.close()

    return Handler


def serve(ctx: Any, port: int = 8765, ready: threading.Event | None = None) -> int:
    web = Web(ctx, port)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(web))
    server.daemon_threads = True
    try:
        ctx.warm_up()  # preload the photo index, the image-search model and the AI model in the background
    except Exception:
        pass
    print(f"Lumo is running on http://127.0.0.1:{port}  (Ctrl+C to stop)", flush=True)
    if ready is not None:
        ready.set()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
