"""The front door: one name for everything. ``atlas.localhost`` is the atlas's own page; ``<module>.atlas.localhost`` is that module's app."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlsplit

from kit.llm import WARM_AT_START

from . import proxy
from .assistant import Assistant, clean_history
from .registry import ManifestError, Module, load, upstream_is_private
from .upstream import Upstreams

STATIC = Path(__file__).with_name("static")
STATIC_TYPES = {
    "atlas.css": "text/css; charset=utf-8",
    "design.css": "text/css; charset=utf-8",
    "atlas.js": "text/javascript; charset=utf-8",
    "icon.svg": "image/svg+xml",
}
MAX_CHAT_BODY = 32_000
LOCAL_ALIASES = frozenset({"localhost", "127.0.0.1", "[::1]"})


def _split_host(value: str) -> tuple[str, str]:
    """('atlas.localhost', '8000') from 'Atlas.Localhost:8000' (also '[::1]:8000')."""
    value = value.strip().lower()
    if value.startswith("["):
        host, _, rest = value.partition("]")
        return host + "]", rest.lstrip(":")
    host, _, port = value.partition(":")
    return host, port


@dataclass(frozen=True)
class Atlas:
    modules: dict[str, Module]
    domain: str  # atlas.localhost
    port: int  # the port the browser uses
    upstreams: Upstreams
    model_url: str = ""  # the shared AI model server (Ollama): shown, and used for routing a question and for plain conversation
    assistant: Assistant = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "assistant", Assistant(self.modules, self.upstreams, self.model_url))

    @property
    def shell_origin(self) -> str:
        return f"http://{self.domain}:{self.port}"

    @property
    def origins(self) -> frozenset[str]:
        """Every origin that is the atlas itself: its own page and each app's name."""
        return frozenset({self.shell_origin, *(f"http://{m}.{self.domain}:{self.port}" for m in self.modules)})

    def resolve(self, host_header: str) -> tuple[str, Module | None]:
        """What this Host header asks for: ('shell', None), ('module', m), ('alias', None) for 127.0.0.1 and localhost, or ('unknown', None)."""
        host, port = _split_host(host_header)
        if port and port != str(self.port):
            return "unknown", None
        if host == self.domain:
            return "shell", None
        if host in LOCAL_ALIASES:
            return "alias", None
        if host.endswith("." + self.domain):
            module = self.modules.get(host[: -len(self.domain) - 1])
            if module is not None:
                return "module", module
        return "unknown", None

    def shell_policy(self) -> str:
        return (
            "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
            f"frame-src http://*.{self.domain}:{self.port}; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        )


def make_handler(atlas: Atlas) -> type[BaseHTTPRequestHandler]:
    return type("Handler", (_Handler,), {"atlas": atlas})


class _Handler(BaseHTTPRequestHandler):
    atlas: ClassVar[Atlas]
    server_version = "Atlas"
    sys_version = ""

    def log_message(self, fmt: str, *args: Any) -> None:  # quiet: addresses and searches can be private
        pass

    # ---- one entry point for every method: the Host header decides who gets the request ------------------------------
    def _handle(self) -> None:
        kind, module = self.atlas.resolve(self.headers.get("Host", ""))
        if kind == "module" and module is not None:
            return proxy.forward(self, module, self.atlas.origins, self.atlas.shell_origin)
        if kind == "alias":
            return self._redirect(self.atlas.shell_origin + self.path)
        if kind != "shell":
            return self._send(HTTPStatus.MISDIRECTED_REQUEST, b"unknown host", "text/plain; charset=utf-8")
        self._shell()

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _handle

    # ---- helpers -----------------------------------------------------------------------------------------------------
    def _send(self, status: int, body: bytes, ctype: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if "Cache-Control" not in (extra or {}):
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", self.atlas.shell_policy())
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _chat(self) -> None:
        """One question to the single chat. Like starting an update, it needs the page's own origin and header."""
        if not _scan_allowed(self, self.atlas):
            return self._send(HTTPStatus.FORBIDDEN, b"refused", "text/plain; charset=utf-8")
        body = self._read_json()
        text = str(body.get("text", "")).strip()
        if not text:
            return self._json({"error": "empty message"}, HTTPStatus.BAD_REQUEST)
        conv = str(body.get("conv", ""))[:64] or "atlas"
        self._json(self.atlas.assistant.answer(text, conv, clean_history(body.get("history"))))

    def _read_json(self) -> dict[str, Any]:
        """The request body as an object; anything missing, too large or not an object is an empty one."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length)) if 0 < length <= MAX_CHAT_BODY else {}
        except (ValueError, OSError):
            return {}
        return body if isinstance(body, dict) else {}

    def _media(self, rest: str) -> None:
        """A picture from an app, on the page's behalf. 'photos/api/photo/12/thumb' means the app 'photos', path '/api/photo/12/thumb'."""
        module_id, _, path = rest.partition("/")
        module = self.atlas.modules.get(module_id)
        if module is None:
            return self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain; charset=utf-8")
        status, data, ctype = self.atlas.upstreams.media(module, "/" + path)
        if status != 200 or not ctype.startswith("image/"):
            return self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain; charset=utf-8")
        self._send(200, data, ctype, {"Cache-Control": "private, max-age=3600"})

    def _control_scan(self, action: str) -> None:
        if not _scan_allowed(self, self.atlas):
            return self._send(HTTPStatus.FORBIDDEN, b"refused", "text/plain; charset=utf-8")
        self._json(self.atlas.upstreams.control(action))

    def _start_scan(self) -> None:
        if not _scan_allowed(self, self.atlas):
            return self._send(HTTPStatus.FORBIDDEN, b"refused", "text/plain; charset=utf-8")
        self._json(self.atlas.upstreams.scan(start=True))

    def _json(self, obj: Any, status: int = 200) -> None:
        self._send(status, json.dumps(obj).encode(), "application/json; charset=utf-8")

    def _redirect(self, target: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", target)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---- the atlas's own page and API ----------------------------------------------------------------------------------
    def _shell(self) -> None:
        url = urlsplit(self.path)
        if self.command == "POST":
            return self._post(url.path)
        if self.command not in ("GET", "HEAD"):
            return self._send(HTTPStatus.METHOD_NOT_ALLOWED, b"read only", "text/plain; charset=utf-8")
        name = url.path.rsplit("/", 1)[-1]
        if url.path.startswith("/_atlas/api/media/"):
            return self._media(url.path[len("/_atlas/api/media/") :])
        if url.path.startswith("/_atlas/static/") and name in STATIC_TYPES:
            return self._send(200, (STATIC / name).read_bytes(), STATIC_TYPES[name])
        route = self._get_routes().get(url.path)
        if route is None:
            return self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain; charset=utf-8")
        route(parse_qs(url.query))

    def _post(self, path: str) -> None:
        routes: dict[str, Callable[[], None]] = {
            "/_atlas/api/chat": self._chat,
            "/_atlas/api/scan": self._start_scan,
            "/_atlas/api/scan/pause": lambda: self._control_scan("pause"),
            "/_atlas/api/scan/resume": lambda: self._control_scan("resume"),
            "/_atlas/api/scan/stop": lambda: self._control_scan("stop"),
        }
        route = routes.get(path)
        if route is None:
            return self._send(HTTPStatus.METHOD_NOT_ALLOWED, b"read only", "text/plain; charset=utf-8")
        route()

    def _get_routes(self) -> dict[str, Callable[[dict[str, list[str]]], None]]:
        atlas = self.atlas

        def page(_q: dict[str, list[str]]) -> None:
            self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")

        return {
            "/": page,
            "/index.html": page,
            "/_atlas/api/modules": lambda _q: self._json({"modules": [m.public() for m in atlas.modules.values()]}),
            "/_atlas/api/health": lambda _q: self._json(atlas.upstreams.health()),
            "/_atlas/api/scan": lambda _q: self._json(atlas.upstreams.scan()),
            "/_atlas/api/ai": lambda _q: self._json(atlas.upstreams.ai(atlas.model_url)),
            "/_atlas/api/search": lambda q: self._json({"results": atlas.upstreams.search((q.get("q") or [""])[0][:200])}),
        }


def _scan_allowed(handler: BaseHTTPRequestHandler, atlas: Atlas) -> bool:
    """Starting an update changes things, so it needs the page's own origin and header: another website cannot start one."""
    return handler.headers.get("Origin") == atlas.shell_origin and handler.headers.get("X-Atlas") == "1"


def build(modules_dir: Path | None = None, domain: str | None = None, port: int | None = None) -> Atlas:
    directory = modules_dir or Path(os.environ.get("ATLAS_MODULES_DIR", "modules.d"))
    modules = load(directory)
    model_url = os.environ.get("ATLAS_MODEL_URL", "http://host.docker.internal:11434").rstrip("/")
    if model_url and not upstream_is_private(model_url):
        raise ManifestError(f"ATLAS_MODEL_URL must be an http address on this computer or its private network, not {model_url!r}")
    return Atlas(
        modules,
        domain or os.environ.get("ATLAS_DOMAIN", "atlas.localhost"),
        port or int(os.environ.get("ATLAS_PUBLIC_PORT", "8000")),
        Upstreams(modules),
        model_url,
    )


def serve(atlas: Atlas, host: str, port: int) -> int:
    server = ThreadingHTTPServer((host, port), make_handler(atlas))
    server.daemon_threads = True
    if WARM_AT_START:  # off by default: starting the computer must not load a 3 GB model
        threading.Thread(target=atlas.assistant.model.warm, daemon=True).start()
    print(f"Atlas is running: open {atlas.shell_origin}  (modules: {', '.join(atlas.modules) or 'none'})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
