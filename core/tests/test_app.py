"""The composition root: a whole Core built from its parts, served on the owner-only socket and driven by the reference client. Deterministic fakes stand in for the Mac pieces
(secure-storage anchor, OS permissions, mailbox adapter, MLX); the wiring between the real modules is what is verified here."""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

import pytest
from conftest import KEY, Clock
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_client import RunScripted, atlas_client, harness
from test_models import entry_dict, signed

from atlas_core.access import FakeOSPermissions
from atlas_core.app import Core, CoreConfig
from atlas_core.designation import InMemoryAnchor, OnboardingDecision
from atlas_core.identity import ClientRegistry
from atlas_core.mail import InMemoryMailbox
from atlas_core.models import ModelStore

pytestmark = pytest.mark.skipif(sys.platform not in ("linux", "darwin"), reason="peer credentials are implemented for Linux and macOS only")
MAIL_MESSAGE = {
    "message_id": "msg-9001@example.invalid",
    "sender": "alice@example.invalid",
    "date": "2026-03-14T09:30:00+00:00",
    "subject": "Quote",
    "body": "The total due is 1250.50 euro for the quarterly service.",
}


class World:
    def __init__(self, tmp: Path, mail: bool = False, durable_clients: bool = False, bootstrap_code: str | None = None) -> None:
        self.durable, self.bootstrap_code = durable_clients, bootstrap_code
        data = json.loads(harness.SET_FILE.read_text(encoding="utf-8"))
        self.tmp, self.clock = tmp, Clock()
        docs = tmp / "docs"
        docs.mkdir()
        for name, doc in data["documents"].items():
            (docs / name).write_text(doc["text"], encoding="utf-8")
        self.os, self.anchor = FakeOSPermissions(self.clock), InMemoryAnchor()
        self.key = Ed25519PrivateKey.generate()
        self.clients = ClientRegistry()
        self.clients.register("client-mac-0001", self.key.public_key())
        self.manifest = signed([entry_dict("primary-1", {"w.safetensors": b"w"}, runtime="stub")])
        models = tmp / "core" / "models"
        (models / "primary-1").mkdir(parents=True)
        (models / "primary-1" / "w.safetensors").write_bytes(b"w")
        ModelStore(models, self.manifest, b"k" * 32).import_model("primary-1")
        self.runtime = RunScripted({c["id"]: {**c["model"], "lang": c["language"]} for c in data["cases"]})
        self.mailbox = InMemoryMailbox([MAIL_MESSAGE]) if mail else None
        self.docs = docs
        self.sock = Path(tempfile.mkdtemp(prefix="atl")) / "run" / "core.sock"
        self.cores: list[Core] = []

    def build(self) -> Core:
        core = Core(
            CoreConfig(
                data_dir=self.tmp / "core", socket_path=self.sock, task_key=KEY + "t", designation_key=KEY + "d", documents_key=KEY + "o", mail_key=KEY + "m", anchor=self.anchor,
                os_permissions=self.os, clients=None if self.durable else self.clients, manifest=self.manifest, model_record_key=b"k" * 32, runtime=self.runtime, documents=("documents", self.docs),
                mailbox=None if self.mailbox is None else ("mail", self.mailbox), bootstrap_code=self.bootstrap_code, open_bootstrap=self.bootstrap_code is None, clock=self.clock,
            )
        )  # fmt: skip
        self.cores.append(core)
        return core

    def enable(self, core: Core, *types: str) -> None:
        for t in types:
            self.os.set(t, "granted")
        core.designation.apply(OnboardingDecision(enable=frozenset(types)), f"request-{time.monotonic_ns()}")

    def client(self):
        return atlas_client.AtlasClient(str(self.sock), self.key, "client-mac-0001", clock=self.clock)

    def question(self, cid: str):
        self.runtime.current = cid
        case = next(c for c in json.loads(harness.SET_FILE.read_text(encoding="utf-8"))["cases"] if c["id"] == cid)
        return case["question"], case.get("scope", ["documents"])

    def wait_indexed(self, core: Core, source_type: str = "documents") -> None:
        for _ in range(400):
            if core.indexes[source_type].coverage()["complete"]:
                return
            time.sleep(0.02)
        raise AssertionError("indexing did not finish")

    def close(self) -> None:
        for core in self.cores:
            core.close()


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    yield w
    w.close()


def test_nothing_is_read_or_answered_until_the_owner_enables_a_source(world):
    core = world.build()
    core.start()
    time.sleep(0.3)
    assert core.indexes["documents"].coverage()["total"] == 0  # not even listed
    with pytest.raises(atlas_client.ClientError) as e:
        world.client().run_question(*world.question("en-total"))
    assert e.value.code == "source_denied" and e.value.message == atlas_client.CATALOGUE["errors"]["source_denied"]
    assert world.runtime.loaded() == frozenset() and core.indexes["documents"].coverage()["total"] == 0  # the model never loaded and nothing was read


def test_enabling_a_source_indexes_it_in_the_background_and_a_question_is_answered(world):
    core = world.build()
    core.start()
    world.enable(core, "documents")
    world.wait_indexed(core)
    view = world.client().run_question(*world.question("en-total"))
    assert "1250.50" in view["text"] and view["citations"][0]["quote"] == "1250.50" and "primary-1" in view["model_line"]


def test_withdrawing_consent_purges_the_index_and_everything_tasks_derived_from_it(world):
    core = world.build()
    core.start()
    world.enable(core, "documents")
    world.wait_indexed(core)
    client = world.client()
    task_id = client.ask(*world.question("en-total"))
    client.result(task_id)
    assert core.tasks.answer(task_id)["citations"]
    core.designation.withdraw("documents", "request-withdraw-1")
    assert core.indexes["documents"].coverage()["total"] == 0  # the index is empty
    saved = core.tasks.answer(task_id)
    assert saved["citations"] == [] and "answer_withheld" in saved["limitations"]  # the stored answer no longer holds source content
    assert not [e for e in core.tasks.events_after(task_id, 0) if e["type"] == "final"]
    world.enable(core, "documents")  # a regrant starts empty and rebuilds; the old answer stays withheld
    world.wait_indexed(core)
    assert client.answer(task_id)["citations"] == []


def test_the_os_taking_its_permission_back_ends_the_grant_and_purges(world):
    core = world.build()
    core.start()
    world.enable(core, "documents")
    world.wait_indexed(core)
    world.os.set("documents", "missing")
    assert not core.access.permitted("documents")
    assert core.indexes["documents"].coverage()["total"] == 0
    for _ in range(250):  # the purge is finished by the Core's own thread; wait for it (a slower machine takes longer) instead of assuming it is already done
        if core.designation.pending_purges() == []:
            break
        time.sleep(0.02)
    assert core.designation.pending_purges() == []


def test_a_restart_finishes_an_owed_purge_and_resumes_interrupted_tasks(world):
    core = world.build()
    core.start()
    world.enable(core, "documents")
    world.wait_indexed(core)
    core.close()
    again = world.build()  # a new process on the same stores
    again.start()
    assert again.access.permitted("documents")
    world.wait_indexed(again)
    assert "1250.50" in world.client().run_question(*world.question("en-total"))["text"]


def test_mail_is_a_separate_decision_and_its_revocation_leaves_documents_alone(tmp_path):
    w = World(tmp_path, mail=True)
    try:
        core = w.build()
        core.start()
        w.enable(core, "documents", "mail")
        w.wait_indexed(core)
        w.wait_indexed(core, "mail")
        core.designation.withdraw("mail", "request-withdraw-2")
        assert core.indexes["mail"].coverage()["total"] == 0 and core.indexes["documents"].coverage()["total"] > 0
        assert "1250.50" in w.client().run_question(*w.question("en-total"))["text"]
    finally:
        w.close()


def test_only_the_owner_only_socket_serves_and_a_stopped_core_leaves_nothing_listening(world):
    import os
    import stat

    core = world.build()
    path = core.start()
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    core.close()
    with pytest.raises(atlas_client.ClientError) as e:
        world.client().discover()
    assert e.value.code == "connection"


def test_a_running_core_logs_which_model_answered_and_why_and_nothing_else_about_the_answer(world, caplog):
    seen: list[str] = []
    core = world.build()
    core.config.log._sink = seen.append  # the event sink of the running Core
    core.start()
    world.enable(core, "documents")
    world.wait_indexed(core)
    world.client().run_question(*world.question("en-total"))
    routed = [json.loads(x) for x in seen if '"model.routed"' in x]
    assert routed and routed[0]["model_id"] == "primary-1" and routed[0]["reason_code"] == "primary_model" and routed[0]["role"] == "primary"
    assert "1250.50" not in "".join(seen) and "invoice" not in "".join(seen).lower()


def test_only_one_core_may_hold_a_data_folder_and_it_is_released_on_close(tmp_path):
    from atlas_core.app import CoreAlreadyRunning

    w = World(tmp_path)
    first = w.build()
    with pytest.raises(CoreAlreadyRunning):
        w.build()  # the same folder, while the first is alive
    first.close()
    w.build().close()  # released: a new Core may take it


def test_close_keeps_the_stores_and_the_lock_while_a_request_could_still_be_using_them(world):
    """A stalled handler: close() times out, reports it, closes nothing and releases nothing; once the handler is gone a later close completes."""
    import socket as socket_module

    core = world.build()
    core.start()
    sock = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
    sock.connect(str(world.sock))
    sock.sendall(b"GET /v1/version HTTP/1.1\r\nHost: localhost\r\n")  # the handler is now waiting for the rest of the request
    time.sleep(0.2)
    began = time.monotonic()
    assert core.close(drain_seconds=0.3) is False
    assert time.monotonic() - began < 2.0, "the wait is bounded by the one total deadline"
    assert core._lock_fd >= 0, "the data-directory lock is still held"
    from atlas_core.app import CoreAlreadyRunning

    with pytest.raises(CoreAlreadyRunning):
        world.build()  # a second Core cannot take the folder while the first still owns it
    sock.close()
    assert core.close(drain_seconds=5.0) is True
    assert core._lock_fd < 0
    world.build().close()  # once released, a new Core takes the same folder and closes cleanly


def test_work_admitted_but_not_yet_running_is_counted_by_the_drain(tmp_path):
    """The count is taken before the handler thread starts: a drain that begins in that window waits instead of seeing nothing."""
    import socketserver
    import threading

    from atlas_core.transport import UnixServer

    entered, release = threading.Event(), threading.Event()
    real = socketserver.ThreadingMixIn.process_request

    def slow_spawn(self, request, client_address):
        entered.set()
        release.wait(3)
        real(self, request, client_address)

    folder = Path(tempfile.mkdtemp(prefix="atl"))
    server = UnixServer(str(folder / "s.sock"), __import__("http.server").server.BaseHTTPRequestHandler)
    try:
        socketserver.ThreadingMixIn.process_request = slow_spawn  # type: ignore[method-assign]
        a, b = __import__("socket").socketpair()
        t = threading.Thread(target=server.process_request, args=(a, ("", 0)), daemon=True)
        t.start()
        assert entered.wait(2)
        assert server.drain(0.2) is False  # admitted, thread not started yet: still counted
        release.set()
        t.join(3)
        b.close()  # the client goes away, so the started handler ends
        assert server.drain(5.0) is True
    finally:
        socketserver.ThreadingMixIn.process_request = real  # type: ignore[method-assign]
        server.server_close()
        a.close()
        b.close()
