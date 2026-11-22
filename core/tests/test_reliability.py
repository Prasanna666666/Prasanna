"""WP3.6: reliability, security and load, through the whole stack (document index, gateway, task service, API 1.1, reference client) with deterministic stubs.

Linux/CI uses deterministic model stubs. Nothing here says anything about a real model, a Mac, FileVault, power loss or target-machine performance."""

from __future__ import annotations

import json
import random
import threading
import time
import uuid
from pathlib import Path

import pytest
from conftest import SENTINEL_QUESTION
from test_client import Core, harness
from test_intelligence import FakeRuntime
from test_models import entry_dict, signed

from atlas_core.api import CoreApi, Request
from atlas_core.documents import MIN_FREE_BYTES
from atlas_core.gate import ModelAnswer
from atlas_core.intelligence import Gateway, Router, Signals
from atlas_core.models import ModelRejected, ModelStore
from atlas_core.service import SimulatedCrash

BOUNDARIES = [f"{when}:{step}" for step in ("retrieved", "drafted", "verified") for when in ("before", "mid", "after")] + ["after:attempt", "before:final"]
DOC_BOUNDARIES = ["scan:begin", "scan:mid", "doc:before", "doc:extracted", "doc:mid_commit", "doc:after_commit"]


class Counting:
    """Counts how often the (stub) model is really called."""

    def __init__(self, core: Core) -> None:
        self.calls = 0
        inner = core.runtime.complete

        def complete(model_id, context, max_context):
            self.calls += 1
            return inner(model_id, context, max_context)

        core.runtime.complete = complete  # type: ignore[method-assign]


def submit(core: Core, cid: str = "en-total") -> str:
    question, scope = core.q(cid)
    return core.service.submit(
        {"objective": question, "source_scope": scope, "budget": {"max_seconds": 120, "max_retries": 3}, "idempotency_key": uuid.uuid4().hex}
    )[0]["task_id"]


def comparable(envelope: dict) -> str:
    return json.dumps({k: v for k, v in envelope.items() if k != "task_id"}, sort_keys=True)


def recover(core: Core) -> None:
    core.service.recover()


@pytest.fixture
def pair(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    a, b = Core(tmp_path / "a", start_worker=False), Core(tmp_path / "b", start_worker=False)
    yield a, b
    a.close()
    b.close()


# ---- crash at every boundary of the real stack ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_a_crash_at_every_boundary_of_the_real_stack_gives_the_same_answer_as_an_uninterrupted_run(pair, boundary):
    crashed, clean = pair
    clean_task = submit(clean)
    clean.service.run(clean_task)
    baseline = comparable(clean.service.answer_v11(clean_task))
    count = Counting(crashed)
    task = submit(crashed)
    crashed.service._d.faults.armed.add(boundary)
    with pytest.raises(SimulatedCrash):
        crashed.service.run(task)
    recover(crashed)
    if crashed.tasks.record(task)["state"] == "queued":
        crashed.service.run(task)
    assert crashed.tasks.record(task)["state"] == "completed", boundary
    assert comparable(crashed.service.answer_v11(task)) == baseline  # byte for byte, coverage and model identity included
    closing = [e for e in crashed.tasks.events_after(task, 0) if e["type"] in ("final", "error")]
    assert len(closing) == 1
    after_draft = {"after:drafted", "before:verified", "mid:verified", "after:verified", "before:final"}
    assert count.calls <= 2 and (count.calls == 1 if boundary in after_draft else True)  # a saved draft is reused: the model is not asked twice


@pytest.mark.parametrize("boundary", DOC_BOUNDARIES)
def test_a_crash_in_the_middle_of_indexing_resumes_to_the_same_index(tmp_path, boundary):
    data = json.loads(harness.SET_FILE.read_text(encoding="utf-8"))
    docs = tmp_path / "docs"
    docs.mkdir()
    for name, doc in data["documents"].items():
        (docs / name).write_text(doc["text"], encoding="utf-8")
    from conftest import KEY

    from atlas_core.access import AllowAll
    from atlas_core.documents import DocumentIndex

    fired: list[str] = []

    def build(db: Path, arm: str | None) -> list[tuple]:
        index = DocumentIndex(db, KEY, docs, "documents", access=AllowAll())

        def hook(name: str) -> None:
            if name == arm:
                fired.append(name)
                raise SimulatedCrash(name)

        index.hook = hook if arm else None
        fired.clear()
        try:
            index.scan()
            while index.run(3)["pending"]:
                pass
        except SimulatedCrash:
            index.close()
            index = DocumentIndex(db, KEY, docs, "documents", access=AllowAll())
            index.scan()
            while index.run(3)["pending"]:
                pass
        rows = [tuple(r) for r in index._conn.execute("SELECT rel_path, status, reason, content_sha FROM docs ORDER BY rel_path")]
        index.close()
        return rows

    crashed_rows = build(tmp_path / "x.db", boundary)
    assert fired == [boundary]  # the crash really happened at that boundary
    assert crashed_rows == build(tmp_path / "y.db", None) and all(status == "indexed" for _, status, _, _ in crashed_rows)


# ---- partial indexes and disk pressure are said, not hidden --------------------------------------------------------------------------------------------------------
def test_a_half_built_index_gives_an_answer_that_says_indexing_is_incomplete(tmp_path):
    core = Core(tmp_path, start_worker=False)
    try:
        core.index._conn.execute("UPDATE docs SET status='pending', text=NULL, blocks=NULL WHERE rel_path='schet_ru.txt'")
        task = submit(core)
        core.service.run(task)
        answer = core.service.answer_v11(task)
        assert answer["coverage"]["state"] == "indexing" and "indexing_incomplete" in answer["limitations"]
        assert {p["category"] for p in answer["coverage"]["pending"]} == {"not_yet_indexed"}
    finally:
        core.close()


def test_disk_pressure_pauses_indexing_and_says_so_then_resumes(tmp_path):
    core = Core(tmp_path, start_worker=False)
    try:
        core.index._conn.execute("UPDATE docs SET status='pending', text=NULL, blocks=NULL WHERE rel_path='huurcontract_nl.txt'")
        core.index.free_bytes = lambda: MIN_FREE_BYTES - 1
        core.index.run(5)
        assert core.index.coverage()["paused"] == "disk_pressure" and core.index.coverage()["complete"] is False
        task = submit(core)
        core.service.run(task)
        assert core.service.answer_v11(task)["coverage"]["state"] == "indexing"
        core.index.free_bytes = lambda: MIN_FREE_BYTES * 10
        while core.index.run(5)["pending"]:
            pass
        assert core.index.coverage()["pending"] == 0 and core.index.coverage()["paused"] is None and core.index.coverage()["complete"]
    finally:
        core.close()


# ---- gateway under load -------------------------------------------------------------------------------------------------------------------------------------------------
def test_concurrent_interactive_and_background_requests_never_exceed_two_inferences_and_all_finish(tmp_path):
    d = tmp_path / "prim"
    d.mkdir()
    (d / "w.safetensors").write_bytes(b"w")
    manifest = signed([entry_dict("prim", {"w.safetensors": b"w"})])
    store = ModelStore(tmp_path, manifest, b"k" * 32)
    store.import_model("prim")

    class Tracking(FakeRuntime):
        def __init__(self) -> None:
            super().__init__()
            self.now = self.peak = 0
            self.lock = threading.Lock()

        def complete(self, model_id, context, max_context):
            with self.lock:
                self.now += 1
                self.peak = max(self.peak, self.now)
            time.sleep(0.02)
            with self.lock:
                self.now -= 1
            return ModelAnswer("ok")

    runtime = Tracking()
    priority = threading.local()
    gateway = Gateway(store, Router(manifest.entries()), runtime, signals=lambda: Signals(priority=priority.value))
    from test_intelligence import context

    ctx = context()[0]
    results: list[str] = []

    def go(kind: str) -> None:
        priority.value = kind
        results.append(gateway.generate(ctx).text)

    threads = [threading.Thread(target=go, args=("interactive" if i % 2 else "background",)) for i in range(12)]
    [t.start() for t in threads]
    [t.join(30) for t in threads]
    assert results == ["ok"] * 12 and runtime.peak <= 2


def test_a_model_that_fails_part_way_leaves_no_stuck_slot_and_the_task_ends_in_plain_failure(tmp_path):
    core = Core(tmp_path, start_worker=False)
    try:
        core.runtime.fail = True
        task = submit(core)
        record = core.service.run(task)
        assert (record["state"], record["terminal_reason"]) == ("failed", "model_unavailable")
        core.runtime.fail = False
        assert core.service.run(submit(core, "nl-total"))["state"] == "completed"  # the slot was released; the next question works
    finally:
        core.close()


# ---- hostile input -------------------------------------------------------------------------------------------------------------------------------------------------------------
def test_random_malformed_requests_never_crash_the_api_leak_content_or_return_a_server_error(tmp_path, caplog, capsys):
    from conftest import signed

    core = Core(tmp_path, start_worker=False)
    try:
        rng = random.Random(7)
        seen: set[int] = set()
        api = CoreApi(core.service, core.registry, core.service._d.log, core.clock, check_responses=True)
        methods, paths = (
            ["GET", "POST", "DELETE", "PUT", "get", ""],
            [
                "/v1/tasks",
                "/v1/version",
                "/v1/tasks/x",
                "/v1/tasks/aaaaaaaa/answer",
                "/v1/tasks/aaaaaaaa/events?after=-1",
                "/v1/consent",
                "/v2/tasks",
                "/",
                "/v1/tasks/../x",
                "/v1/tasks?x=\x00",
            ],
        )
        bodies = [
            b"",
            b"{",
            b"[]",
            b"null",
            b'{"objective":' + b"9" * 4000 + b"}",
            json.dumps({"objective": SENTINEL_QUESTION, "source_scope": [1], "budget": {}, "idempotency_key": "k"}).encode(),
            bytes(rng.randrange(256) for _ in range(300)),
            ("[" * 500 + "]" * 500).encode(),
            b'{"objective": "\\ud800"}',
        ]
        for _ in range(400):
            method, path, body = rng.choice(methods), rng.choice(paths), rng.choice(bodies)
            version = rng.choice(["1.0", "1.1"])
            headers = signed(core.key, method, path, body, core.clock(), version=version) if rng.random() < 0.8 else {}
            if rng.random() < 0.3:
                headers["x-atlas-api-version"] = rng.choice(["", "1.1", "2", "1.1, 1.1", "garbage", "\x00"])
            response = api.handle(Request(method, path, headers, body))
            seen.add(response.status)
            assert response.status < 500 and (response.body == b"" or isinstance(json.loads(response.body), dict) or response.stream is not None)
            assert SENTINEL_QUESTION.encode() not in response.body
        text = "\n".join([*core.lines, *(r.getMessage() for r in caplog.records), capsys.readouterr().out])
        assert core.lines and SENTINEL_QUESTION not in text
        assert len(seen) >= 2 and min(seen) < 300 and max(seen) >= 400
    finally:
        core.close()


def test_rejection_and_failure_reasons_of_the_model_layer_carry_no_path_or_content(tmp_path, caplog, capsys):
    secret_dir = "secret-model-dir-5521"
    (tmp_path / secret_dir).mkdir()
    manifest = signed([entry_dict(secret_dir, {"w.safetensors": b"w"})])
    store = ModelStore(tmp_path, manifest, b"k" * 32)
    for action in (lambda: store.import_model(secret_dir), lambda: store.verify_for_load(secret_dir), lambda: store.import_model("other")):
        with pytest.raises(ModelRejected) as e:
            action()
        assert secret_dir not in str(e.value) and str(tmp_path) not in str(e.value)
    out = capsys.readouterr()
    assert secret_dir not in out.out + out.err + "".join(r.getMessage() for r in caplog.records)


def test_the_gateway_keeps_no_copy_of_the_question_or_passages_after_answering(tmp_path):
    from test_intelligence import context, world

    gateway, *_ = world(tmp_path)
    ctx = context()[0]
    gateway.generate(ctx)

    def holds(obj, seen=None, depth=0):
        seen = seen if seen is not None else set()
        if id(obj) in seen or depth > 4:
            return False
        seen.add(id(obj))
        if obj is ctx or obj is ctx.passages or (isinstance(obj, str) and obj and obj in ctx.passages[0]["text"] and len(obj) > 5):
            return True
        children = (
            obj.values() if isinstance(obj, dict) else obj if isinstance(obj, (list, tuple, set)) else vars(obj).values() if hasattr(obj, "__dict__") else ()
        )
        return any(holds(c, seen, depth + 1) for c in children)

    assert not holds(gateway._sched) and not holds(gateway._router) and not holds(gateway._rt)


# ---- redaction across the new paths ----------------------------------------------------------------------------------------------------------------------------------
def test_no_question_or_source_content_reaches_any_log_or_output_on_normal_failure_cancel_and_revocation_paths(tmp_path, caplog, capsys):
    core = Core(tmp_path, start_worker=False)
    try:
        client = core.client(core.serve())
        question, scope = core.q("en-total")
        secret_question = f"{question} QSENT-8841"
        content = ("1250.50", "ACME-2041", "Payment is due within 30 days")
        ok = client.ask(secret_question, scope)
        core.service.run(ok)
        client.answer(ok)
        # model failure
        core.runtime.fail = True
        bad = client.ask(secret_question + " again", scope)
        core.service.run(bad)
        core.runtime.fail = False
        # cancel before running
        gone = client.ask(secret_question + " cancel", scope)
        client.cancel(gone)
        # revocation after an answer, then purge
        core.grants._grants[:] = []
        client.answer(ok)
        core.service.purge_source_type("documents")
        text = "\n".join([*core.lines, *(r.getMessage() for r in caplog.records), capsys.readouterr().out, capsys.readouterr().err])
        assert core.lines
        for needle in ("QSENT-8841", *content):
            assert needle not in text, needle
    finally:
        core.close()


def test_the_evaluation_and_ingestion_tools_print_only_their_labelled_report(capsys):
    import sys
    from pathlib import Path as P

    sys.path.insert(0, str(P(__file__).resolve().parents[1] / "bench"))
    import ingest

    report = ingest.measure(30, 6, 3)
    out = capsys.readouterr()
    assert out.out == "" and out.err == "" and "NOT target-Mac" in report["label"]["meaning"]
    assert report["mail"]["coverage"]["complete"] and report["documents"]["coverage"]["complete"]
