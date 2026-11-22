"""Criterion 14 over a real Unix domain socket: the folder and socket are owner-only, the peer's user id is checked, and requests are still signed.

Linux (SO_PEERCRED) is exercised here. The macOS branch (LOCAL_PEERCRED) is NOT VERIFIED until it runs on a Mac.
"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import socket
import stat
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest
from conftest import World, grant, request, signed
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from atlas_core.api import CoreApi
from atlas_core.identity import ClientRegistry
from atlas_core.transport import peer_uid, serve_unix

pytestmark = pytest.mark.skipif(sys.platform not in ("linux", "darwin"), reason="peer credentials are implemented for Linux and macOS only")


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str) -> None:
        super().__init__("localhost")
        self._path = path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self._path)


@pytest.fixture
def served(tmp_path):
    folder = Path(tempfile.mkdtemp(prefix="atl"))  # a short path: socket paths have a small length limit
    key = Ed25519PrivateKey.generate()
    registry = ClientRegistry()
    registry.register("client-mac-0001", key.public_key())
    world = World(tmp_path, [grant("documents")])
    api = CoreApi(world.service, registry, world.log, world.clock, check_responses=True)
    started: list = []

    def start(allowed=None, **limits):
        server = serve_unix(folder / "run" / "core.sock", api, allowed, **limits)
        started.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return str(folder / "run" / "core.sock")

    yield start, key, world, folder
    for server in started:
        server.shutdown()
        server.server_close()
    shutil.rmtree(folder, ignore_errors=True)


def _call(path: str, key, world, method: str, target: str, body: dict | None = None):
    raw = json.dumps(body).encode() if body is not None else b""
    conn = UnixConnection(path)
    conn.request(method, target, body=raw or None, headers=signed(key, method, target, raw, world.clock()))
    response = conn.getresponse()
    return response.status, response.read()


@pytest.mark.criterion(14)
def test_the_socket_and_its_folder_are_owner_only_and_a_signed_request_works_over_it(served):
    start, key, world, _folder = served
    path = start()
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600 and stat.S_IMODE(os.stat(Path(path).parent).st_mode) == 0o700
    status, body = _call(path, key, world, "GET", "/v1/version")
    assert status == 200 and json.loads(body)["api_version"] == "1.0"
    status, body = _call(path, key, world, "POST", "/v1/tasks", request())
    assert status == 201 and json.loads(body)["state"] == "queued"


@pytest.mark.criterion(14)
def test_a_connection_from_a_user_that_is_not_allowed_is_refused_before_anything_is_read(served):
    start, key, world, _ = served
    path = start(allowed=[os.getuid() + 12345])
    status, _ = _call(path, key, world, "GET", "/v1/version")
    assert status == 403 and world.retriever.calls == []


@pytest.mark.criterion(14)
def test_an_unsigned_request_over_the_socket_is_refused_even_from_the_right_user(served):
    start, _, _, _ = served
    path = start()
    conn = UnixConnection(path)
    conn.request("GET", "/v1/version")
    assert conn.getresponse().status == 401


@pytest.mark.criterion(14)
def test_the_peer_user_id_is_read_from_the_kernel_not_from_anything_the_client_sends():
    a, b = socket.socketpair()
    try:
        assert peer_uid(a) == os.getuid() and peer_uid(b) == os.getuid()
    finally:
        a.close()
        b.close()


# ---- request framing and connection bounds (second independent review) -----------------------------------------------------------------------
def _raw(path: str, head: bytes, body: bytes = b"", timeout: float = 3.0) -> tuple[int | None, bytes]:
    """Send hand-written bytes over the socket; return the status line's code (None if the server closed without replying) and whatever else came back."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(path)
        sock.sendall(head + body)
        data = b""
        try:
            while chunk := sock.recv(65536):
                data += chunk
        except (TimeoutError, ConnectionResetError):
            pass
    return (int(data.split(b" ", 2)[1]) if data.startswith(b"HTTP/") else None), data


def _post(headers: str) -> bytes:
    return ("POST /v1/tasks HTTP/1.1\r\nHost: localhost\r\n" + headers + "\r\n").encode()


def _still_healthy(path: str, key, world) -> None:
    status, body = _call(path, key, world, "GET", "/v1/version")
    assert status == 200 and json.loads(body)["api_version"] == "1.0"


@pytest.mark.criterion(14)
def test_a_1_1_request_is_served_over_the_socket_with_the_echo_header(served):
    start, key, world, _folder = served
    path = start()
    raw = json.dumps(request()).encode()
    conn = UnixConnection(path)
    conn.request("POST", "/v1/tasks", body=raw, headers=signed(key, "POST", "/v1/tasks", raw, world.clock(), version="1.1"))
    response = conn.getresponse()
    assert response.status == 201 and response.getheader("x-atlas-api-version") == "1.1"


@pytest.mark.criterion(14)
@pytest.mark.parametrize(
    "framing",
    [
        "Content-Length: 10000000",
        "Content-Length: 65537",
        "Content-Length: -1",
        "Content-Length: abc",
        "Content-Length: 1, 2",
        "Content-Length: +5",
        "Content-Length: 5.0",
        "Content-Length: 99999999999999999999999",
        "Content-Length: " + "9" * 5000,
        "Content-Length: \u0663".encode().decode("unicode_escape"),
        "Transfer-Encoding: chunked",
        "Transfer-Encoding: gzip, chunked",
        "Content-Length: 5\r\nContent-Length: 6",
        "Content-Length: 5\r\nTransfer-Encoding: chunked",
        "X-Atlas-Api-Version: 1.1\r\nX-Atlas-Api-Version: 1.1",
    ],
)
def test_bad_request_framing_is_refused_before_any_body_is_read_and_the_server_stays_up(served, framing):
    start, key, world, _ = served
    path = start()
    status, data = _raw(path, _post(framing + "\r\n"), timeout=2.0)  # no body is ever sent: a server that tried to read one would hang until the timeout
    assert status == 400 and b"invalid_request" in data and b"connection: close" in data.lower()
    assert world.retriever.calls == []
    _still_healthy(path, key, world)


@pytest.mark.criterion(14)
def test_a_body_at_the_cap_is_still_read_and_judged_by_the_api_not_by_the_transport(served):
    start, *_ = served
    path = start()
    body = b"x" * (64 * 1024)
    status, _ = _raw(path, _post(f"Content-Length: {len(body)}\r\n"), body)
    assert status == 401  # framing accepted, then the unsigned request is refused by identity as usual


@pytest.mark.criterion(14)
def test_a_client_that_stops_sending_the_declared_body_is_dropped_after_the_read_timeout(served):
    start, key, world, _ = served
    path = start(read_timeout=0.3)
    started = time.monotonic()
    status, _ = _raw(path, _post("Content-Length: 100\r\n"), b"only ten b", timeout=5.0)  # 10 of 100 bytes, then silence
    assert time.monotonic() - started < 3.0 and status in (None, 400)
    _still_healthy(path, key, world)


@pytest.mark.criterion(14)
def test_connections_are_bounded_and_the_server_recovers_when_they_close(served):
    start, key, world, _ = served
    path = start(max_connections=2, read_timeout=5.0)
    held = []
    for _ in range(2):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(path)
        held.append(sock)  # idle connections that occupy the two slots
    time.sleep(0.2)
    status, _ = _raw(path, b"GET /v1/version HTTP/1.1\r\nHost: localhost\r\n\r\n", timeout=2.0)
    assert status is None  # a third connection is closed without being served
    for sock in held:
        sock.close()
    time.sleep(0.3)
    _still_healthy(path, key, world)


def test_a_live_sockets_path_is_never_unlinked_but_a_stale_one_is_replaced(tmp_path):
    import socket as socketlib

    from atlas_core.transport import serve_unix

    path = tmp_path / "run" / "core.sock"
    path.parent.mkdir()
    live = socketlib.socket(socketlib.AF_UNIX, socketlib.SOCK_STREAM)
    live.bind(str(path))
    live.listen(1)
    try:
        with pytest.raises(OSError, match="already answering"):
            serve_unix(path, object())  # type: ignore[arg-type]
        assert path.exists()  # the live owner's socket file is untouched
        probe = socketlib.socket(socketlib.AF_UNIX, socketlib.SOCK_STREAM)
        probe.connect(str(path))  # and still answers
        probe.close()
    finally:
        live.close()
    # now it is stale (a bound socket file with nothing listening), and a plain leftover file is stale too
    assert path.exists()
    server = serve_unix(path, object())  # type: ignore[arg-type]
    server.server_close()
    path.unlink()
    path.write_text("leftover")
    serve_unix(path, object()).server_close()  # type: ignore[arg-type]
