"""What every local web service of the platform shares: the host check, the safe response headers, the JSON helpers, and calling another local service."""

from __future__ import annotations

import json
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Collection
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, ClassVar

from . import log, netguard, sign

MAX_BODY = 1_000_000
STRICT_CSP = "default-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"


class Fail(Exception):
    """A request that cannot be served: the status and the plain-words message sent back."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def host_ok(value: str | None, allowed: Collection[str]) -> bool:
    """True when the Host (or Origin) names one of this computer's own addresses, with or without a port. Stops other sites and DNS rebinding."""
    if not value:
        return False
    host = value.strip().lower()
    host = host.split("]")[0] + "]" if host.startswith("[") else host.split(":")[0]
    return host in allowed


class JsonHandler(BaseHTTPRequestHandler):
    """Plumbing only: quiet logging, responses with safe headers, JSON in and out."""

    csp: ClassVar[str] = STRICT_CSP

    def log_message(self, *args: Any) -> None:  # quiet: requests may contain private words
        return

    def _send(self, status: int, body: bytes, ctype: str = "application/json; charset=utf-8", extra: dict[str, str] | None = None) -> None:
        try:
            self._write(status, body, ctype, extra)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True  # the page or app that asked has already gone (it gave up waiting): nothing to answer, and no error to print

    def _write(self, status: int, body: bytes, ctype: str, extra: dict[str, str] | None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", self.csp)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _signed(self) -> bool:
        """A request from another program of the platform carries a fresh signature (see sign.py); with no secret set, nothing is checked."""
        return sign.valid(self.command, self.path, self.headers.get(sign.HEADER))

    def _json(self, obj: Any, status: int = 200) -> None:
        self._send(status, json.dumps(obj, default=str).encode())

    def _fail(self, status: int, message: str) -> None:
        self._json({"ok": False, "error": message}, status)

    def _body(self) -> dict:
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 <= size <= MAX_BODY:
                return {}
            data = json.loads(self.rfile.read(size) or b"{}")
            return data if isinstance(data, dict) else {}
        except (ValueError, OSError):
            return {}


class ModuleHandler(JsonHandler):
    """The skeleton every local service of the platform is built on, written once: the checks every request passes (this computer's own names only, the platform's signature, a header only
    this service's own page can send for anything that changes data), looking a route up and running it with its own database connection and error boundary, and serving the page's files.
    A service sets its names (`allowed_hosts`, `write_header`, `static_dir`) and keeps only its own routes."""

    state: ClassVar[Any]  # has `connect()`: a database connection for one request
    allowed_hosts: ClassVar[Collection[str]] = ()
    write_header: ClassVar[str] = ""  # e.g. "X-Library": a page on another site cannot send it
    address_hint: ClassVar[str] = ""
    static_dir: ClassVar[Path | None] = None

    def _authorised(self) -> bool:
        """A service that wants more (a password, a token) overrides this."""
        return True

    def _guard(self, writing: bool) -> bool:
        if not host_ok(self.headers.get("Host"), self.allowed_hosts):
            self._fail(HTTPStatus.FORBIDDEN, f"This address is not allowed. Use {self.address_hint}" if self.address_hint else "This address is not allowed.")
            return False
        if not self._authorised():
            return False
        if not self._signed():
            self._fail(HTTPStatus.UNAUTHORIZED, "This request is not signed by the platform.")
            return False
        if writing:
            origin = self.headers.get("Origin")
            if self.headers.get(self.write_header) != "1" or (origin and not host_ok(origin.split("://", 1)[-1], self.allowed_hosts)):
                self._fail(HTTPStatus.FORBIDDEN, "Request refused.")
                return False
        return True

    def _run(self, routes: dict, path: str, *args: Any) -> None:
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
            self._fail(500, f"{type(exc).__name__}: {exc} (in {log.where(exc)})")
        finally:
            conn.close()

    def _file(self, name: str) -> None:
        root = (self.static_dir or Path()).resolve()
        target = (root / name).resolve()
        if self.static_dir is None or root not in target.parents or not target.is_file():
            return self._fail(HTTPStatus.NOT_FOUND, "not found")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send(200, target.read_bytes(), f"{ctype}; charset=utf-8" if ctype.startswith("text/") or ctype.endswith("javascript") else ctype)


def call_local(base: str, method: str, path: str, header: str, unavailable: str, timeout: int = 60) -> dict[str, Any]:
    """Call another service on this computer (plain http, JSON back). `header` is that service's own change-protection header (sent as "1");
    `unavailable` is the plain sentence shown when it is not running."""
    url = base.rstrip("/") + path
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "http" or not parts.hostname:
        raise RuntimeError("The service address is not valid.")
    netguard.allow_local(parts.hostname)
    request = urllib.request.Request(  # noqa: S310 - http only, a host on this computer or its private network
        url,
        method=method,
        data=b"{}" if method == "POST" else None,
        headers={header: "1", "Accept": "application/json", **sign.sign(method, parts.path + (f"?{parts.query}" if parts.query else ""))},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            data = json.loads(response.read())
    except urllib.error.HTTPError as exc:  # it answered, with an error: it is running
        raise RuntimeError(f"The service is running but answered with an error (HTTP {exc.code}).") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"The service is running but did not answer within {timeout} seconds: it is busy. Try again in a minute.") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        if isinstance(getattr(exc, "reason", None), TimeoutError):
            raise RuntimeError(f"The service is running but did not answer within {timeout} seconds: it is busy. Try again in a minute.") from exc
        if isinstance(exc, ValueError):
            raise RuntimeError("The service answered with something that is not valid.") from exc
        raise RuntimeError(unavailable) from exc  # it could not be reached at all
    return data if isinstance(data, dict) else {}
