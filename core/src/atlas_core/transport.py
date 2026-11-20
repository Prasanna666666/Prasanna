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
from collections.abc import Iterable
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from .api import CoreApi, Request

SOL_LOCAL, LOCAL_PEERCRED = 0, 0x001  # macOS
XUCRED_FORMAT = "=II"  # cr_version, cr_uid (the groups that follow are not needed)
XUCRED_SIZE = 76
SOCKET_MODE, DIR_MODE = 0o600, 0o700


def peer_uid(sock: socket.socket) -> int | None:
    """The user id of the process on the other end, or None if the platform cannot say."""
    if sys.platform.startswith("linux"):
        _pid, uid, _gid = struct.unpack("=iII", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("=iII")))
        return int(uid)
    if sys.platform == "darwin":
        raw = sock.getsockopt(SOL_LOCAL, LOCAL_PEERCRED, XUCRED_SIZE)
        return int(struct.unpack(XUCRED_FORMAT, raw[: struct.calcsize(XUCRED_FORMAT)])[1])
    return None


def make_handler(api: CoreApi, allowed_uids: Iterable[int]) -> type[BaseHTTPRequestHandler]:
    allowed = frozenset(allowed_uids)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self) -> None:
            super().setup()
            uid = peer_uid(self.request)
            self._peer_ok = uid is not None and uid in allowed

        def log_message(self, format: str, *args: object) -> None:
            return

        def _serve(self) -> None:
            if not self._peer_ok:
                self.send_response(403)
                self.send_header("content-length", "0")
                self.end_headers()
                return
            length = int(self.headers.get("content-length") or 0)
            response = api.handle(Request(self.command, self.path, dict(self.headers.items()), self.rfile.read(length) if length else b""))
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

        do_GET = do_POST = _serve

    return Handler


class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def serve_unix(path: str | Path, api: CoreApi, allowed_uids: Iterable[int] | None = None) -> UnixServer:
    """Bind the socket (owner-only, in an owner-only folder) and return the server; the caller runs serve_forever()."""
    sock_path = Path(path)
    sock_path.parent.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
    os.chmod(sock_path.parent, DIR_MODE)
    if sock_path.exists():
        sock_path.unlink()
    server = UnixServer(str(sock_path), make_handler(api, allowed_uids if allowed_uids is not None else [os.getuid()]))
    os.chmod(sock_path, SOCKET_MODE)
    return server
