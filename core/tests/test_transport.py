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
from pathlib import Path

import pytest
from conftest import World, grant, request, signed
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from atlas_core.api import CoreApi
from atlas_core.identity import ClientRegistry
from atlas_core.transport import peer_uid, serve_unix

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="peer credentials are only verified on Linux in this stage")


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

    def start(allowed=None):
        server = serve_unix(folder / "run" / "core.sock", api, allowed)
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
