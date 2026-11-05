"""The front door: one name for everything. ``atlas.localhost`` is the atlas's own page; ``<module>.atlas.localhost`` is that module's app."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlsplit

from . import proxy
from .registry import Module, load
from .upstream import Upstreams

STATIC = Path(__file__).with_name("static")
STATIC_TYPES = {"atlas.css": "text/css; charset=utf-8", "atlas.js": "text/javascript; charset=utf-8", "icon.svg": "image/svg+xml"}
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
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", self.atlas.shell_policy())
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj: Any, status: int = 200) -> None:
        self._send(status, json.dumps(obj).encode(), "application/json; charset=utf-8")

    def _redirect(self, target: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", target)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---- the atlas's own page and API ----------------------------------------------------------------------------------
    def _shell(self) -> None:
        if self.command not in ("GET", "HEAD"):
            return self._send(HTTPStatus.METHOD_NOT_ALLOWED, b"read only", "text/plain; charset=utf-8")
        url = urlsplit(self.path)
        if url.path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if url.path.startswith("/_atlas/static/") and url.path.rsplit("/", 1)[-1] in STATIC_TYPES:
            name = url.path.rsplit("/", 1)[-1]
            return self._send(200, (STATIC / name).read_bytes(), STATIC_TYPES[name])
        if url.path == "/_atlas/api/modules":
            return self._json({"modules": [m.public() for m in self.atlas.modules.values()]})
        if url.path == "/_atlas/api/health":
            return self._json(self.atlas.upstreams.health())
        if url.path == "/_atlas/api/search":
            query = (parse_qs(url.query).get("q") or [""])[0][:200]
            return self._json({"results": self.atlas.upstreams.search(query)})
        self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain; charset=utf-8")


def build(modules_dir: Path | None = None, domain: str | None = None, port: int | None = None) -> Atlas:
    directory = modules_dir or Path(os.environ.get("ATLAS_MODULES_DIR", "modules.d"))
    modules = load(directory)
    return Atlas(
        modules, domain or os.environ.get("ATLAS_DOMAIN", "atlas.localhost"), port or int(os.environ.get("ATLAS_PUBLIC_PORT", "8000")), Upstreams(modules)
    )


def serve(atlas: Atlas, host: str, port: int) -> int:
    server = ThreadingHTTPServer((host, port), make_handler(atlas))
    server.daemon_threads = True
    print(f"Atlas is running: open {atlas.shell_origin}  (modules: {', '.join(atlas.modules) or 'none'})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
