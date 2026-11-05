"""Hand a browser request to the app that owns it and stream the answer back, unchanged.

Nothing in a page or script is rewritten: each app is reached under its own name (finance.atlas.localhost), so its own absolute addresses keep working.
The atlas changes only what must change to be a safe front door: the Host and Origin it presents to the app, and the right to be shown inside the atlas's page."""

from __future__ import annotations

import http.client
import re
from http import HTTPStatus
from typing import Any

from kit.sign import sign

from .registry import Module

MAX_BODY = 10 * 1024 * 1024
CONNECT_SECONDS = 5
READ_SECONDS = 300  # a chat answer streams for as long as the model takes
HOP_BY_HOP = frozenset({"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"})
NOT_COPIED_REQUEST = HOP_BY_HOP | {"host", "content-length", "origin", "referer"}
NOT_COPIED_RESPONSE = HOP_BY_HOP | {"server", "date"}
FRAME_ANCESTORS = re.compile(r"frame-ancestors[^;]*", re.IGNORECASE)


def allow_framing(policy: str, shell_origin: str) -> str:
    """The app forbids being framed; the atlas allows its own page (and nobody else) to frame it."""
    if FRAME_ANCESTORS.search(policy):
        return FRAME_ANCESTORS.sub(f"frame-ancestors {shell_origin}", policy)
    return f"{policy}; frame-ancestors {shell_origin}".lstrip("; ")


def request_headers(handler: Any, module: Module, origins: frozenset[str]) -> dict[str, str] | None:
    """The headers to send to the app, or None when the browser's Origin is not one of the atlas's own (a page on another site)."""
    sent = {k: v for k, v in handler.headers.items() if k.lower() not in NOT_COPIED_REQUEST}
    origin = handler.headers.get("Origin")
    if origin is not None:
        if origin not in origins:
            return None
        sent["Origin"] = f"http://{module.presented}"
    sent["Host"] = module.presented
    return sent


def _unavailable(handler: Any, module: Module, status: int = HTTPStatus.BAD_GATEWAY) -> None:
    page = (
        f"<!doctype html><meta charset=utf-8><title>{module.name} is not running</title>"
        "<body style='font:16px system-ui;padding:48px;max-width:560px;margin:auto;color:#334'>"
        f"<h2>{module.name} is not running</h2><p>Start {module.app or module.name}, then reload this page.</p>"
    ).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(page)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(page)


def forward(handler: Any, module: Module, origins: frozenset[str], shell_origin: str) -> None:
    """Send this request to ``module`` and copy its answer back as it arrives (chat answers stream word by word)."""
    try:
        length = int(handler.headers.get("Content-Length") or 0)
    except ValueError:
        length = -1
    if not 0 <= length <= MAX_BODY:
        handler.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        return
    headers = request_headers(handler, module, origins)
    if headers is None:
        handler.send_error(HTTPStatus.FORBIDDEN, "unknown origin")
        return
    body = handler.rfile.read(length) if length else None
    host, _, port = module.netloc.partition(":")
    conn = http.client.HTTPConnection(host, int(port or 80), timeout=CONNECT_SECONDS)
    try:
        conn.request(handler.command, handler.path, body=body, headers={**headers, **sign(handler.command, handler.path)})
        if conn.sock is not None:
            conn.sock.settimeout(READ_SECONDS)
        response = conn.getresponse()
    except (OSError, http.client.HTTPException):
        conn.close()
        return _unavailable(handler, module)
    try:
        handler.send_response(response.status, response.reason)
        for key, value in response.getheaders():
            if key.lower() in NOT_COPIED_RESPONSE:
                continue
            is_policy = key.lower() == "content-security-policy"
            handler.send_header(key, allow_framing(value, shell_origin) if is_policy else value)
        handler.end_headers()
        if handler.command == "HEAD":
            return
        while chunk := response.read1(65536):
            handler.wfile.write(chunk)
            handler.wfile.flush()
    except (TimeoutError, BrokenPipeError, ConnectionResetError):
        pass  # the browser left (a new chat, a closed tab): stop quietly
    finally:
        conn.close()
