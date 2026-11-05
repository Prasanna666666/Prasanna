"""What every local web service of the platform shares: the host check, the safe response headers, the JSON helpers, and calling another local service."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Collection
from http.server import BaseHTTPRequestHandler
from typing import Any, ClassVar

from . import netguard

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


def call_local(base: str, method: str, path: str, header: str, unavailable: str, timeout: int = 60) -> dict[str, Any]:
    """Call another service on this computer (plain http, JSON back). `header` is that service's own change-protection header (sent as "1");
    `unavailable` is the plain sentence shown when it is not running."""
    url = base.rstrip("/") + path
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "http" or not parts.hostname:
        raise RuntimeError("The service address is not valid.")
    netguard.allow_local(parts.hostname)
    request = urllib.request.Request(  # noqa: S310 - http only, a host on this computer or its private network
        url, method=method, data=b"{}" if method == "POST" else None, headers={header: "1", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            data = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise RuntimeError(unavailable) from exc
    return data if isinstance(data, dict) else {}
