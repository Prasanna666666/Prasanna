"""Local transport: HTTP over a Unix domain socket in an owner-only folder, with the peer's user id checked on every connection.

This is the local seam only. A remote iOS transport is a separate, gated design (G-O14); it would reuse the same signed requests.
Linux (SO_PEERCRED) is tested; the macOS branch (LOCAL_PEERCRED) is written from the documented struct layout and is NOT VERIFIED until it runs on a Mac.
"""

from __future__ import annotations

import os
import socket
import socketserver
import struct
import sys
import threading
from collections.abc import Iterable
from email.message import Message
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from .api import MAX_BODY_BYTES, CoreApi, Request, Response, framing_error

SOL_LOCAL, LOCAL_PEERCRED = 0, 0x001  # macOS
XUCRED_FORMAT = "=II"  # cr_version, cr_uid (the groups that follow are not needed)
XUCRED_SIZE = 76
SOCKET_MODE, DIR_MODE = 0o600, 0o700
READ_TIMEOUT = 15.0  # seconds a client may stay silent while sending its request; the stream of a long answer is not affected (the server only writes there)
MAX_LENGTH_DIGITS = len(str(MAX_BODY_BYTES))  # a longer number cannot be within the cap (and is never converted, so a huge one cannot raise)
MAX_CONNECTIONS = 64  # simultaneous connections served; one owner, so this is generous, and the rest are closed unserved


def peer_uid(sock: socket.socket) -> int | None:
    """The user id of the process on the other end, or None if the platform cannot say."""
    if sys.platform.startswith("linux"):
        _pid, uid, _gid = struct.unpack("=iII", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("=iII")))
        return int(uid)
    if sys.platform == "darwin":
        raw = sock.getsockopt(SOL_LOCAL, LOCAL_PEERCRED, XUCRED_SIZE)
        return int(struct.unpack(XUCRED_FORMAT, raw[: struct.calcsize(XUCRED_FORMAT)])[1])
    return None


def declared_length(headers: Message) -> int | None:
    """The body length the client declared, or None if the framing is not one this transport accepts: chunked or any other transfer coding, a missing-or-repeated
    or non-decimal Content-Length, a negative one, or one above the API's cap. Judged from the headers alone, before a single body byte is read."""
    if headers.get_all("transfer-encoding") is not None:
        return None
    values = headers.get_all("content-length") or ["0"]
    if len(values) != 1:
        return None
    text = values[0].strip()
    if (
        not (text.isascii() and text.isdigit()) or len(text) > MAX_LENGTH_DIGITS
    ):  # ASCII digits only (int() also takes signs, spaces, underscores and other scripts)
        return None
    length = int(text)
    return length if length <= MAX_BODY_BYTES else None


class LocalHandler(BaseHTTPRequestHandler):
    """One connection: peer check, request framing, the API call, the reply. The API, the allowed users and the read timeout are set by `make_handler`."""

    protocol_version = "HTTP/1.1"
    api: CoreApi
    allowed: frozenset[int] = frozenset()

    def setup(self) -> None:
        super().setup()
        uid = peer_uid(self.request)
        self._peer_ok = uid is not None and uid in self.allowed

    def log_message(self, format: str, *args: object) -> None:
        return

    def _serve(self) -> None:
        if not self._peer_ok:
            self.send_response(403)
            self.send_header("content-length", "0")
            self.end_headers()
            return
        length = declared_length(self.headers)
        if length is None or len(self.headers.get_all("x-atlas-api-version") or []) > 1:  # a repeated version header is never guessed at
            self._refuse()
            return
        body = self._read_body(length)
        if body is None:
            self.close_connection = True  # the client stopped sending, or closed early, before the declared body arrived
            return
        response = self.api.handle(Request(self.command, self.path, dict(self.headers.items()), body))
        self._reply(response)

    def _read_body(self, length: int) -> bytes | None:
        try:
            body = self.rfile.read(length) if length else b""
        except OSError:  # includes the read timeout
            return None
        return body if len(body) == length else None

    def _reply(self, response: Response) -> None:
        self.send_response(response.status)
        for key, value in response.headers.items():
            self.send_header(key, value)
        if response.stream is None:
            self.send_header("content-length", str(len(response.body)))
            self.end_headers()
            self.wfile.write(response.body)
            return
        self.send_header("connection", "close")
        self.end_headers()
        for chunk in response.stream:
            self.wfile.write(chunk)
            self.wfile.flush()
        self.close_connection = True

    def _refuse(self) -> None:
        """Bad framing: a fixed client error, then the connection is closed (an unread body would otherwise be mistaken for the next request)."""
        response = framing_error()
        self.send_response(response.status)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.send_header("content-length", str(len(response.body)))
        self.send_header("connection", "close")
        self.end_headers()
        self.wfile.write(response.body)
        self.close_connection = True

    do_GET = do_POST = do_DELETE = _serve  # DELETE is used only by the 1.1 consent route; the API refuses it everywhere else


def make_handler(api: CoreApi, allowed_uids: Iterable[int], read_timeout: float = READ_TIMEOUT) -> type[BaseHTTPRequestHandler]:
    class Handler(LocalHandler):
        timeout = read_timeout  # a client that stops sending (headers or declared body) is dropped instead of holding a thread forever

    Handler.api, Handler.allowed = api, frozenset(allowed_uids)
    return Handler


Connection = socket.socket | tuple[bytes, socket.socket]


MAX_SOCKET_PATH = 103 if sys.platform == "darwin" else 107  # sun_path is 104 bytes on macOS and 108 on Linux, including the terminating NUL


class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def __init__(self, path: str, handler: type[BaseHTTPRequestHandler], max_connections: int = MAX_CONNECTIONS) -> None:
        self._slots = threading.BoundedSemaphore(max_connections)
        super().__init__(path, handler)

    def process_request(self, request: Connection, client_address: object) -> None:
        if not self._slots.acquire(blocking=False):  # every slot busy: refuse by closing, without reading or replying (bounds threads and memory)
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request: Connection, client_address: object) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


def serve_unix(
    path: str | Path,
    api: CoreApi,
    allowed_uids: Iterable[int] | None = None,
    *,
    max_connections: int = MAX_CONNECTIONS,
    read_timeout: float = READ_TIMEOUT,
) -> UnixServer:
    """Bind the socket (owner-only, in an owner-only folder) and return the server; the caller runs serve_forever()."""
    sock_path = Path(path)
    if len(os.fsencode(sock_path)) > MAX_SOCKET_PATH:
        raise OSError(
            f"The Core socket path is {len(os.fsencode(sock_path))} bytes; a Unix socket path may be at most {MAX_SOCKET_PATH} on this system. Use a shorter data folder."
        )
    sock_path.parent.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
    os.chmod(sock_path.parent, DIR_MODE)
    if sock_path.exists():
        sock_path.unlink()
    server = UnixServer(str(sock_path), make_handler(api, allowed_uids if allowed_uids is not None else [os.getuid()], read_timeout), max_connections)
    os.chmod(sock_path, SOCKET_MODE)
    return server
