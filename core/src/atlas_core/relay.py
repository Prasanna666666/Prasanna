"""The remote channel, opt-in and narrow (Stage 8, decision G-O14): a relay that lets a paired phone reach the Core over a PRIVATE network, and nothing else.

The Core still serves only its owner-only Unix socket. This module is a separate, optional listener (started only by `--relay-bind`) that forwards complete HTTP requests to that socket and the reply back. It adds
no authority: every request must carry the device's own signature, which the Core checks exactly as it does for the Mac app, so the relay holds no key and no secret.

* **Never a public port.** It binds only a literal loopback, private-range, link-local or shared-address (VPN, for example Tailscale's 100.64.0.0/10) IPv4 address. A wildcard address, a name, a public address
  or anything it cannot classify is refused before a socket is opened.
* **Only the contract.** Only `/v1/` paths are forwarded, never the first-owner enrolment (`/v1/enrol`, which is local to the Mac). A malformed, chunked, oversized or slow request is refused or dropped.
* **Bounded.** A fixed number of simultaneous connections, a deadline for each, a cap on the head and on the body, one request per connection.
* **Confidentiality is the network's.** Use it over a VPN or other encrypted private network; it does not add TLS.
"""

from __future__ import annotations

import ipaddress
import socket
import socketserver
import threading
import time
from pathlib import Path

MAX_BODY_BYTES = 64 * 1024  # the API's own cap (a test keeps them equal)
MAX_HEAD_BYTES = 16 * 1024
MAX_CONNECTIONS = 32
DEADLINE = 60.0
SHARED_ADDRESS_SPACE = ipaddress.ip_network("100.64.0.0/10")  # the range VPNs such as Tailscale hand out
LOCAL_ONLY_PATHS = frozenset({"/v1/enrol"})
REQUEST_LINE_PARTS = 3


class RelayRefused(Exception):
    """The relay was asked to do something it will not. Carries a code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def permitted_bind(host: str) -> bool:
    """True only for a literal IPv4 address that is loopback, private, link-local or in the shared (VPN) range. Never a wildcard, a name or a public address."""
    try:
        address = ipaddress.IPv4Address(host)
    except ValueError:
        return False
    if address.is_unspecified or address.is_multicast or address.is_reserved:
        return False
    return address.is_loopback or address.is_private or address.is_link_local or address in SHARED_ADDRESS_SPACE


def _refusal(status: int, text: str) -> bytes:
    body = b'{"code":"invalid_request"}'
    return f"HTTP/1.1 {status} {text}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body


def _read_head(conn: socket.socket, deadline: float) -> tuple[bytes, bytes] | None:
    data = b""
    while b"\r\n\r\n" not in data:
        if len(data) > MAX_HEAD_BYTES or time.monotonic() > deadline:
            return None
        chunk = conn.recv(4096)
        if not chunk:
            return None
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    return head, rest


def _declared(head: bytes) -> int | None:
    """The body length the request declares, or None if the request is malformed. Raises RelayRefused for a path that is not forwarded."""
    lines = head.decode("latin-1").split("\r\n")
    parts = lines[0].split(" ")
    if len(parts) != REQUEST_LINE_PARTS or not parts[2].startswith("HTTP/1."):
        return None
    target = parts[1].split("?", 1)[0]
    if not target.startswith("/v1/") or target in LOCAL_ONLY_PATHS or ".." in target:
        raise RelayRefused("path_not_forwarded")
    headers = {line.split(":", 1)[0].strip().lower(): line.split(":", 1)[1].strip() for line in lines[1:] if ":" in line}
    length = headers.get("content-length", "0")
    if "transfer-encoding" in headers or not (length.isascii() and length.isdigit()) or int(length) > MAX_BODY_BYTES:
        return None
    return int(length)


def _read_request(conn: socket.socket, deadline: float) -> bytes | None:
    """One complete request (head and declared body), or None if it is malformed, too large or too slow."""
    first = _read_head(conn, deadline)
    if first is None:
        return None
    head, body = first
    length = _declared(head)
    if length is None:
        return None
    while len(body) < length:
        chunk = conn.recv(min(65536, length - len(body))) if time.monotonic() <= deadline else b""
        if not chunk:
            return None
        body += chunk
    return head + b"\r\n\r\n" + body[:length]


class _Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server: Relay = self.server  # type: ignore[assignment]
        if not server.slots.acquire(blocking=False):
            return  # too many connections: closed unserved
        try:
            deadline = time.monotonic() + DEADLINE
            self.request.settimeout(10.0)
            try:
                request = _read_request(self.request, deadline)
            except RelayRefused:
                self.request.sendall(_refusal(403, "Forbidden"))
                return
            except (OSError, UnicodeDecodeError):
                return
            if request is None:
                self.request.sendall(_refusal(400, "Bad Request"))
                return
            self._forward(request, server.socket_path, deadline)
        except OSError:
            return
        finally:
            server.slots.release()

    def _forward(self, request: bytes, socket_path: Path, deadline: float) -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
            upstream.settimeout(30.0)
            if upstream.connect_ex(str(socket_path)) != 0:  # the Core is not there
                self.request.sendall(_refusal(502, "Bad Gateway"))
                return
            upstream.sendall(request)
            while time.monotonic() < deadline:
                chunk = upstream.recv(65536)
                if not chunk:
                    return
                self.request.sendall(chunk)


class Relay(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host: str, port: int, socket_path: Path) -> None:
        if not permitted_bind(host):
            raise RelayRefused("address_not_private")  # nothing is opened for an address that could be reached from the Internet
        self.socket_path = socket_path
        self.slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        super().__init__((host, port), _Handler)

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, daemon=True)
        thread.start()
        return thread

    def close(self) -> None:
        self.shutdown()
        self.server_close()
