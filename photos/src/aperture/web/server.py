"""The local server behind Photos's web app (standard library only).

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
import os
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
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlparse

import numpy as np

from .. import library as lib
from ..agent.llm import CALL_LOG
from ..config import preview_rel, thumb_rel
from ..indexing.progress import ScanLock
from . import browse

STATIC = Path(__file__).parent / "static"
STATIC_FILES = {"app.css": "text/css; charset=utf-8", "app.js": "text/javascript; charset=utf-8"}
MAX_BODY = 64 * 1024
PAGE = 60
PREVIEW = 24
DEFAULT_IDEAS = [
    "Photos from last summer",
    "Pictures of dogs",
    "Night photos",
    "Receipts and documents",
    "Screenshots",
    "Sunsets",
]
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
BROWSE_PATHS = frozenset({"/api/library", "/api/timeline", "/api/trips", "/api/places", "/api/people"})
ID_PATH = re.compile(r"^/api/photo/(\d{1,12})/(thumb|preview)$")
ITEM_PATH = re.compile(r"^/api/item/(\d{1,12})$")


def build_id() -> str:
    """Which code is running (the git commit), so 'is it the new version?' is never a guess."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).parent, capture_output=True, text=True, timeout=5
        )
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
            return {"ids": [int(i) for i in chosen[offset : offset + limit]], "total": len(chosen)}
        ids = self._convs.get(conv)
        if ids is None:
            return {"ids": [], "total": 0}
        return {"ids": [int(i) for i in ids[offset : offset + limit]], "total": len(ids)}

    # ---- small cache so polling the status never hits the drive or the AI server more than every few seconds
    def coverage_note(self) -> str:
        """How complete the locations are, so 'are you sure you found them all?' can be answered truthfully."""

        def compute() -> str:
            conn = self.ctx.db.connect()
            try:
                total, own, worked = conn.execute(
                    "SELECT COUNT(*), COALESCE(SUM(gps_lat IS NOT NULL),0), COALESCE(SUM(gps_lat IS NULL AND gps_est_lat IS NOT NULL),0) "
                    "FROM items WHERE missing=0 AND meta_done=1"
                ).fetchone()
            except Exception:
                return ""
            finally:
                conn.close()
            none = total - own - worked
            extra = f", {worked:,} more were placed by time or appearance" if worked else ""
            return (
                f"Location coverage: of {total:,} photos, {own:,} have a location in their own file{extra}; {none:,} have no location, "
                "so a search by place cannot find them."
            )

        return self.cached("coverage_note", 300.0, compute)

    def cached(self, key: str, ttl: float, fn):
        now = time.monotonic()
        hit = self._cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        value = fn()
        self._cache[key] = (now, value)
        return value

    def status(self) -> dict[str, Any]:
        ctx = self.ctx

        self.refresh_counts_async()
        healthy = self.cached("ai", 10, lambda: bool(ctx.llm().health()[0]))
        return {
            **self._counts,
            "ai": healthy,
            "model": ctx.settings.ollama_model,
            "build": self.build,
            "search_ready": bool(ctx.search_ready()),
            "warm_problem": ctx.warm_problem(),
            "indexing": ScanLock(ctx.paths).running(verify=True),
            "paused_for_chat": self.paused_for_chat,
        }

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
        subprocess.Popen(
            [sys.executable, "-m", "aperture", "scan"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self.paused_for_chat = False
        return True

    def browse(self, what: str, query: dict[str, str]) -> Any:
        """The library as pages: photos by date, the timeline, trips, places, people. The lists that change slowly are kept for a minute."""
        conn = self.ctx.db.connect()
        try:
            if what == "library":
                try:
                    offset = max(0, int(query.get("offset", "0")))
                except ValueError:
                    offset = 0
                return browse.library(conn, query, offset)
            fn: Any = {"timeline": browse.timeline, "trips": browse.trips, "places": browse.places, "people": browse.people}[what]
            return self.cached("browse:" + what, 60.0, lambda: fn(conn))
        finally:
            conn.close()

    def item(self, item_id: int) -> dict[str, Any] | None:
        conn = self.ctx.db.connect()
        try:
            found = lib.items_by_ids(conn, [item_id]).get(item_id)
        finally:
            conn.close()
        if found is None:
            return None
        return {
            "id": item_id,
            "name": Path(found.rel_path or found.path).name,
            "taken": found.taken_at,
            "place": found.place,
            "camera": found.camera,
            "width": found.width,
            "height": found.height,
        }

    def ask_once(self, message: str, conv: str, history: list[tuple[str, str]]) -> dict[str, Any]:
        """The contract's one-shot question, for Atlas's single chat: the same answer as the chat, in one piece, with the first photos as items."""
        with self.ai_lock:
            self.pause_indexing_for_chat()
            reply = ask_within(lambda: self.ctx.agent().ask(message, self.previous(conv), history=history), ASK_LIMIT)
            stream = reply.stream
            try:
                text = "".join(stream) or "..." if stream is not None else reply.text
            finally:
                if stream is not None and hasattr(stream, "close"):
                    stream.close()
            shown = len(reply.ids) and reply.kind in ("results", "export", "count")
            if shown:
                self.remember(conv, reply.ids)
        items = (
            [
                {"kind": "photo", "id": int(i), "thumb": f"/api/photo/{int(i)}/thumb", "link": "#/library"}
                for i in reply.ids[:PREVIEW]
            ]
            if shown and reply.kind != "count"
            else []
        )
        return {
            "text": text,
            "items": items,
            "total": len(reply.ids) if shown else 0,
            "notes": [str(n) for n in [*reply.notes, *reply.warnings]][:3],
        }

    def scan_status(self) -> dict[str, Any]:
        """Where indexing stands, in the shape every module reports it (the contract's scan status), for Atlas's one Update button."""
        self.refresh_counts_async()
        running = bool(ScanLock(self.ctx.paths).running(verify=True))
        photos, indexed = self._counts["photos"], self._counts["indexed"]
        text = f"{indexed:,} of {photos:,} photos indexed"
        return {
            "running": running,
            "progress": text if running else "",
            "summary": "" if running else text,
            "problems": [],
            "needs_check": 0,
        }

    def search(self, query: str) -> dict[str, Any]:
        """The answer to Atlas's search box: places, people and trips that match, with where each opens."""
        found = browse.search_links(self.browse("places", {}), self.browse("people", {}), self.browse("trips", {}), query)
        return {"results": found}

    def photo_file(self, item_id: int, kind: str) -> Path | None:
        data = self.ctx.paths.data.resolve()
        path = (data / (thumb_rel(item_id) if kind == "thumb" else preview_rel(item_id))).resolve()
        return path if data in path.parents and path.is_file() else None


def _clean_history(raw: Any) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    for entry in raw if isinstance(raw, list) else []:
        if (
            isinstance(entry, (list, tuple))
            and len(entry) == 2
            and entry[0] in ("user", "assistant")
            and isinstance(entry[1], str)
        ):
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

    context = (
        contextvars.copy_context()
    )  # the helper thread must see the same per-message state (such as the record of model calls)
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

        frame = sys._current_frames().get(worker.ident or 0)  # exactly where it is stuck, so the cause can be read from the log
        where = "".join(traceback.format_stack(frame)[-8:]) if frame is not None else "unknown"
        log.warning(
            "a question was still running after %.0f s (last step: %s); the answer was given up. Stuck at:\n%s",
            limit,
            last or "none",
            where,
        )
        return AgentReply(
            "error",
            "That is taking longer than it should. Please try again, or ask it in a simpler way."
            + (f" (It was at: {last.lower()}.)" if last else ""),
        )
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


def _int_param(query: dict[str, list[str]], key: str, default: int) -> int:
    try:
        return int((query.get(key) or [str(default)])[0])
    except ValueError:
        return default


class _Handler(BaseHTTPRequestHandler):
    """Plumbing only: host, origin and token checks, files, and the server-sent-event chat stream."""

    server_version = "Photos"
    sys_version = ""
    web: ClassVar[Web]
    allowed_hosts: ClassVar[frozenset[str]]
    allowed_origins: ClassVar[frozenset[str]]

    def log_message(self, fmt: str, *args: Any) -> None:  # quiet: nothing about your photos goes to a log
        pass

    # ---- helpers -----------------------------------------------------------------------------------------------------
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

    def _bytes(self, body: bytes, ctype: str, cache: str = "no-store") -> None:
        self._headers(200, ctype, len(body), cache=cache)
        self.wfile.write(body)

    def _deny(self, status: HTTPStatus, message: str) -> None:
        self._json({"error": message}, int(status))

    def _checked(self, api: bool) -> bool:
        if self.headers.get("Host", "") not in self.allowed_hosts:
            self._deny(HTTPStatus.FORBIDDEN, "unknown host")
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in self.allowed_origins:
            self._deny(HTTPStatus.FORBIDDEN, "unknown origin")
            return False
        if api:
            query = parse_qs(urlparse(self.path).query)
            given = self.headers.get("X-Lumo-Token") or (query.get("t") or [""])[0]
            if not hmac.compare_digest(given.encode(), self.web.token.encode()):
                self._deny(HTTPStatus.FORBIDDEN, "missing or wrong token")
                return False
        return True

    def _sse(self, event: str, data: Any) -> None:
        self.wfile.write(f"event: {event}\ndata: {json.dumps(data)}\n\n".encode())
        self.wfile.flush()

    # ---- GET ---------------------------------------------------------------------------------------------------------
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            return self._get_page(lambda: self._json({"ok": True}))
        if path in ("/", "/index.html"):
            return self._get_page(self._send_index)
        if path.startswith("/static/"):
            return self._get_page(lambda: self._send_static(path[len("/static/") :]))
        if not path.startswith("/api/"):
            return self._deny(HTTPStatus.NOT_FOUND, "not found")
        if self._checked(True):
            self._get_api(path, urlparse(self.path).query)

    def _get_page(self, send: Any) -> None:
        if self._checked(False):
            send()

    def _send_index(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", self.web.token)
        self._bytes(html.encode(), "text/html; charset=utf-8")

    def _send_static(self, name: str) -> None:
        if name in STATIC_FILES:
            self._bytes((STATIC / name).read_bytes(), STATIC_FILES[name])
        else:
            self._deny(HTTPStatus.NOT_FOUND, "not found")

    def _get_api(self, path: str, raw_query: str) -> None:
        web, query = self.web, parse_qs(raw_query)
        if path == "/api/status":
            self._json(web.status())
        elif path == "/api/suggestions":
            self._json({"ideas": web.suggestions()})
        elif path == "/api/scan":
            self._json(web.scan_status())
        elif path == "/api/search":
            self._json(web.search((query.get("q") or [""])[0][:200]))
        elif path in BROWSE_PATHS:
            self._json(web.browse(path[len("/api/") :], {k: v[0][:200] for k, v in query.items() if v}))
        elif path == "/api/results":
            offset, group = max(0, _int_param(query, "offset", 0)), _int_param(query, "group", -1)
            self._json(
                web.results((query.get("conv") or [""])[0][:64], offset, group=group, rid=(query.get("rid") or [""])[0][:32])
            )
        elif m := ID_PATH.match(path):
            file = web.photo_file(int(m.group(1)), m.group(2))
            if file is None:
                self._deny(HTTPStatus.NOT_FOUND, "no such photo")
            else:
                self._bytes(file.read_bytes(), "image/jpeg", cache="private, max-age=86400")
        elif m := ITEM_PATH.match(path):
            found = web.item(int(m.group(1)))
            self._json(found) if found else self._deny(HTTPStatus.NOT_FOUND, "no such photo")
        else:
            self._deny(HTTPStatus.NOT_FOUND, "not found")

    # ---- POST --------------------------------------------------------------------------------------------------------
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

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not self._checked(True):
            return
        if path in ("/api/scan", "/api/scan/resume"):
            return self._json({"started": self.web.resume_indexing()})
        if path not in ("/api/chat", "/api/ask"):
            return self._deny(HTTPStatus.NOT_FOUND, "not found")
        body = self._body()
        if body is None:
            return
        message = str(body.get("message", body.get("text", ""))).strip()[:2000]
        if not message:
            return self._deny(HTTPStatus.BAD_REQUEST, "empty message")
        if path == "/api/ask" and body.get("fast"):
            return self._json({"handled": False})  # no photo question is answered without the model yet
        if path == "/api/ask":
            return self._json(
                self.web.ask_once(message, str(body.get("conv", ""))[:64] or "atlas", _clean_history(body.get("history")))
            )
        self._chat(message, str(body.get("conv", ""))[:64] or "default", _clean_history(body.get("history")))

    # ---- the chat stream ---------------------------------------------------------------------------------------------
    def _send_preview(self, message: str) -> None:
        """Photo matches in milliseconds, before the AI has finished."""
        ctx = self.web.ctx
        if ctx.settings.quick_preview and ctx.search_ready():
            ids = self._instant_matches(message)
            if ids is not None and len(ids):
                self._sse("preview", {"ids": [int(i) for i in ids[:PREVIEW]], "total": len(ids)})

    def _send_matches(self, reply: Any, conv: str) -> None:
        """The photos are known before the words: send them first, then any notes."""
        if len(reply.ids) and reply.kind in ("results", "export", "count"):
            self.web.remember(conv, reply.ids)
            rid = self.web.remember_set(reply.ids, reply.groups)
            self._sse(
                "results",
                {
                    "rid": rid,
                    "groups": [{"label": g[0], "count": len(g[1])} for g in reply.groups],
                    "ids": [] if reply.kind == "count" else [int(i) for i in reply.ids[:PAGE]],
                    "total": len(reply.ids),
                    "kind": reply.kind,
                    "notes": list(reply.notes),
                    "warnings": list(reply.warnings),
                },
            )
        elif reply.notes or reply.warnings:
            self._sse("notes", {"notes": list(reply.notes), "warnings": list(reply.warnings)})

    def _send_words(self, reply: Any, started: float) -> tuple[str, float | None]:
        """Stream the reply word by word (or send it whole). Returns the full text and the time to the first words."""
        if reply.stream is None:
            self._sse("reply", {"text": reply.text})
            return reply.text, None
        parts: list[str] = []
        first_words = None
        for chunk in reply.stream:
            if first_words is None:
                first_words = round(time.perf_counter() - started, 2)
            parts.append(chunk)
            self._sse("delta", {"text": chunk})
        return "".join(parts) or "...", first_words

    def _chat(self, message: str, conv: str, history: list[tuple[str, str]]) -> None:
        self._headers(200, "text/event-stream; charset=utf-8")
        started = time.perf_counter()
        stream = None
        calls: list[dict[str, Any]] = []
        log_token = CALL_LOG.set(calls)  # every model call made for this message is recorded here
        web = self.web
        try:
            self._sse("ack", {})
            self._send_preview(message)
            with web.ai_lock:
                web.pause_indexing_for_chat()  # indexing and the AI model together would swap an 8 GB Mac
                reply = ask_within(
                    lambda: web.ctx.agent().ask(message, web.previous(conv), history=history),
                    ASK_LIMIT,
                    lambda text: self._sse("status", {"text": text}),
                )
                stream = reply.stream
                self._send_matches(reply, conv)
                text, first_words = self._send_words(reply, started)
            timings = {**reply.timings, **({"first_words": first_words} if first_words is not None else {})}
            self._sse(
                "done",
                {
                    "took": round(time.perf_counter() - started, 2),
                    "kind": reply.kind,
                    "text": text,
                    "record": memory_of(reply, text, web.coverage_note()),
                    "timings": timings,
                    "trace": calls,
                },
            )
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

        ctx = self.web.ctx
        conn = ctx.db.connect()
        try:
            return quick_ids(conn, message, ctx.embedding_index, ctx.search_embedder, ctx.settings.visual_strictness)
        except Exception:
            return None
        finally:
            conn.close()


def make_handler(web: Web) -> type[BaseHTTPRequestHandler]:
    # *.localhost always resolves to this Mac (RFC 6761), so the friendly address the installer prints is as safe as 127.0.0.1
    hosts = frozenset(
        {f"127.0.0.1:{web.port}", f"localhost:{web.port}", f"lumo.localhost:{web.port}", f"photos.localhost:{web.port}"}
    )
    origins = frozenset(f"http://{h}" for h in hosts)
    return type("Handler", (_Handler,), {"web": web, "allowed_hosts": hosts, "allowed_origins": origins})


def serve(ctx: Any, port: int = 8765, ready: threading.Event | None = None) -> int:
    web = Web(ctx, port)
    # Loopback unless Docker says otherwise: inside the container the gateway must reach us, and the container's own
    # network is internal (no internet), so listening on all of its interfaces is still private.
    host = os.environ.get("APERTURE_UI_HOST", "127.0.0.1") if os.environ.get("APERTURE_SANDBOXED") == "1" else "127.0.0.1"
    server = ThreadingHTTPServer((host, port), make_handler(web))
    server.daemon_threads = True
    try:
        ctx.warm_up()  # preload the photo index, the image-search model and the AI model in the background
    except Exception:
        pass
    print(f"Photos is running on http://127.0.0.1:{port}  (Ctrl+C to stop)", flush=True)
    if ready is not None:
        ready.set()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
