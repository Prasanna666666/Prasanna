"""Blocker 3 (review 6011238976): the model engine runs in a separate process whose network access the OS refuses, proven by what that process can actually do."""

from __future__ import annotations

import json
import socket
import sys
import time

import pytest
from conftest import CORPUS, T0, grant, labels, passage
from test_models import entry_dict, signed

from atlas_core import sandbox
from atlas_core.gate import ContextBuilder
from atlas_core.intelligence import Gateway, Router, RuntimeFailure, Signals
from atlas_core.isolated import IsolatedEngine
from atlas_core.mlx_runtime import MlxRuntime
from atlas_core.models import ModelStore
from atlas_core.policy import InMemoryGrants, PolicyEngine

pytestmark = pytest.mark.skipif(sys.platform not in ("linux", "darwin"), reason="network confinement exists for Linux (seccomp) and macOS (sandbox-exec) only")
MECHANISM = "launcher" if sys.platform == "darwin" else "seccomp"  # macOS confines the worker from the outside with sandbox-exec; Linux filters inside it


class Target(str):
    """host:port, plus the UDP receiver bound to that port, so a test can see whether anything arrived."""

    def __new__(cls, address: str, datagrams: socket.socket):
        self = super().__new__(cls, address)
        self.datagrams = datagrams
        return self

    def received(self) -> bytes | None:
        try:
            return self.datagrams.recv(100)
        except TimeoutError:
            return None


@pytest.fixture
def listener():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(5)
    port = server.getsockname()[1]
    datagrams = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # a UDP receiver on the same port number: what a leak would arrive at
    datagrams.bind(("127.0.0.1", port))
    datagrams.settimeout(0.5)
    yield Target(f"127.0.0.1:{port}", datagrams)
    datagrams.close()
    server.close()


def engine(name: str, **kw) -> IsolatedEngine:
    return IsolatedEngine(f"worker_engines:{name}", allow_custom_engine=True, **kw)


def probe(e: IsolatedEngine, target: str) -> dict:
    e.load("/tmp")
    return json.loads("".join(e.stream(target, 10)))


def test_without_isolation_the_same_code_can_open_a_network_connection(listener):
    """The control: the probe is meaningful because it succeeds when nothing stops it."""
    host, _, port = listener.partition(":")
    s = socket.socket()
    s.connect((host, int(port)))
    s.close()
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.sendto(b"exfiltrated", (host, int(port)))
    u.close()
    assert listener.received() == b"exfiltrated"  # the receiver does see a leak when nothing stops it


def test_inside_the_worker_no_network_socket_can_be_opened_but_unix_sockets_and_pipes_work(listener):
    e = engine("ProbeEngine")
    try:
        result = probe(e, listener)
        assert e.network_denied == MECHANISM
        assert result["tcp"].startswith("blocked:") and result["unix"] == "ok"
        assert result["udp"].startswith("blocked:")  # no datagram could be sent either (Linux refuses the socket; macOS refuses the send)
        assert listener.received() is None  # and nothing arrived at the receiver
    finally:
        e.close()


def test_the_worker_gets_a_clean_environment_with_no_secrets(listener, monkeypatch):
    monkeypatch.setenv("ATLAS_TEST_SECRET", "hunter2")
    e = engine("ProbeEngine")
    try:
        result = probe(e, listener)
        assert result["secret_in_env"] is False and set(result["env_keys"]) <= {
            "PATH",
            "HOME",
            "LANG",
            "TMPDIR",
            "PYTHONPATH",
            "LC_CTYPE",
            "__CF_USER_TEXT_ENCODING",
        }  # the last is added by macOS itself to every process
    finally:
        e.close()


def test_a_worker_that_cannot_confine_itself_is_never_used(monkeypatch):
    monkeypatch.setattr(sandbox, "launch_prefix", lambda: (_ for _ in ()).throw(sandbox.SandboxUnavailable("platform")))
    with pytest.raises(RuntimeFailure, match="isolation_unavailable"):
        engine("EchoEngine").load("/tmp")


def test_a_worker_whose_own_sandbox_fails_reports_it_and_the_parent_refuses(monkeypatch):
    e = engine("EchoEngine")
    monkeypatch.setattr(e, "_command", lambda: [sys.executable, "-c", "import json,sys; print(json.dumps({'hello': False}))"])
    with pytest.raises(RuntimeFailure, match="isolation_unavailable"):
        e.load("/tmp")


def test_only_the_builtin_engine_may_be_named_unless_the_parent_allows_a_custom_one():
    e = IsolatedEngine("worker_engines:EchoEngine")  # custom engine without the explicit allowance
    with pytest.raises(RuntimeFailure):
        e.load("/tmp")


def test_a_consumer_that_stops_early_cancels_the_worker_and_the_next_request_still_works():
    e = engine("SlowEngine")
    try:
        e.load("/tmp")
        stream = e.stream("x", 10)
        assert next(stream).startswith("p0")
        began = time.monotonic()
        stream.close()  # stopping early cancels the worker's generation
        assert time.monotonic() - began < 5
        again = "".join(e.stream("y", 10))
        assert again.startswith("p0") and "p199" in again  # the pipe stayed in step
    finally:
        e.close()


def test_a_crashed_worker_is_a_failure_not_a_hang_and_a_new_one_starts_for_the_next_load():
    e = engine("CrashEngine")
    try:
        e.load("/tmp")
        with pytest.raises(RuntimeFailure):
            list(e.stream("x", 10))
        assert e._proc is None
    finally:
        e.close()
    again = engine("EchoEngine")
    try:
        again.load("/tmp")
        assert "".join(again.stream("x", 10)).startswith("{")
    finally:
        again.close()


def test_a_silent_worker_is_cut_off_after_the_silence_limit():
    e = engine("SilentEngine", silence_limit=0.5)
    try:
        e.load("/tmp")
        began = time.monotonic()
        with pytest.raises(RuntimeFailure, match="worker_silent"):
            list(e.stream("x", 10))
        assert time.monotonic() - began < 10 and e._proc is None
    finally:
        e.close()


def test_a_load_error_in_the_worker_is_a_content_free_failure():
    e = engine("EchoEngine")
    try:
        with pytest.raises(RuntimeFailure, match="load_failed"):
            e.load("/definitely/not/a/folder")
    finally:
        e.close()


def test_the_whole_path_runs_through_the_isolated_worker_with_the_verified_staged_folder(tmp_path):
    d = tmp_path / "primary-1"
    d.mkdir()
    (d / "w.safetensors").write_bytes(b"w")
    (d / "extra_unmanifested.json").write_bytes(b"{}")
    manifest = signed([entry_dict("primary-1", {"w.safetensors": b"w"}, runtime="mlx")])
    store = ModelStore(tmp_path, manifest, b"k" * 32)
    store.import_model("primary-1")
    iso = engine("EchoEngine")
    try:
        gateway = Gateway(store, Router(manifest.entries()), MlxRuntime(iso), signals=Signals)
        _, token = PolicyEngine(InMemoryGrants([grant("documents")])).decide(["documents"], T0)
        context = ContextBuilder(labels()).build(token, "What is due?", [passage(CORPUS[0], 0, 40)], T0)
        answer = gateway.generate(context)
        assert answer.identity == ("primary-1", "primary", "mlx") and answer.text == "Due 1250.50" and answer.citations[0]["quote"] == "1250.50"
        assert iso.network_denied == MECHANISM
        staged = next((tmp_path / ".load").iterdir())
        assert sorted(p.name for p in staged.iterdir()) == ["w.safetensors"]  # the worker was shown only the manifest's file
    finally:
        iso.close()


# ---- the mechanism itself ------------------------------------------------------------------------------------------------------------------------------------------------
def test_the_filter_program_fails_closed_on_an_unknown_architecture_and_names_the_two_it_knows(monkeypatch):
    monkeypatch.setattr("atlas_core.sandbox.platform.machine", lambda: "riscv64")
    with pytest.raises(sandbox.SandboxUnavailable):
        sandbox.install_network_deny()
    assert set(sandbox.ARCHES) == {"x86_64", "aarch64"} and len(sandbox.filter_program(*sandbox.ARCHES["x86_64"])) == 12 * 8


def test_the_macos_launch_prefix_denies_network_and_says_where_it_is_verified(monkeypatch):
    monkeypatch.setattr("atlas_core.sandbox.sys.platform", "darwin")
    monkeypatch.setattr("atlas_core.sandbox.os.access", lambda *a: True)
    prefix = sandbox.launch_prefix()
    assert prefix[0] == "/usr/bin/sandbox-exec" and "(deny network*)" in prefix[2] and "(deny default)" in prefix[2]
    assert "macOS CI runner" in (sandbox.__doc__ or "")  # the claim names the job that proves it (the isolated-worker tests on the runner)
