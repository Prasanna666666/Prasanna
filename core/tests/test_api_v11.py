"""WP3.4b: API 1.1 is served additively. The applied version is signed (no downgrade or upgrade by header), the echo header is present, the answer carries coverage and the
model identity, and 1.0 behaves exactly as before."""

from __future__ import annotations

import dataclasses
import json

import pytest
from conftest import T0, StubModel, World, grant, request
from test_api import Harness

from atlas_core import contracts
from atlas_core.coverage import build_coverage, required_limitations
from atlas_core.gate import ModelAnswer

H = "x-atlas-api-version"


class IdentModel(StubModel):
    def generate(self, context):
        return dataclasses.replace(super().generate(context), identity=("primary-1", "primary", "stub"))


def report(**over):
    base = {"total": 4, "searched": 4, "pending": 0, "unsupported": 0, "failed": 0, "failed_reasons": {}, "scan_complete": True, "paused": None}
    return {**base, **over}


@pytest.fixture
def h(tmp_path) -> Harness:
    h = Harness(World(tmp_path, [grant("documents")], IdentModel()))
    h.w.service._d.coverage = {"documents": report}
    return h


def done(h: Harness) -> str:
    _, rec = h.json("POST", "/v1/tasks", request(), version="1.1", headers={H: "1.1"})
    h.w.service.run(rec["task_id"])
    return rec["task_id"]


def test_a_1_1_answer_carries_coverage_model_and_the_echo_header(h):
    tid = done(h)
    r = h.call("GET", f"/v1/tasks/{tid}/answer", version="1.1")
    body = json.loads(r.body)
    assert r.status == 200 and r.headers[H] == "1.1"
    assert body["coverage"]["state"] == "complete" and body["coverage"]["searched"] == 4 and body["coverage"]["pending"] == []
    assert body["model"] == {"model_id": "primary-1", "role": "primary", "runtime": "stub"}
    contracts.validate("AnswerEnvelope", body, "1.1")


def test_1_0_is_unchanged_no_coverage_no_model_no_echo(h):
    _, rec = h.json("POST", "/v1/tasks", request())
    h.w.service.run(rec["task_id"])
    r = h.call("GET", f"/v1/tasks/{rec['task_id']}/answer")
    body = json.loads(r.body)
    assert H not in r.headers and "coverage" not in body and "model" not in body
    contracts.validate("AnswerEnvelope", body, "1.0")


def test_the_applied_version_is_signed_so_the_header_cannot_be_added_or_stripped(h):
    assert h.call("GET", "/v1/tasks/aaaaaaaa", version="1.0", headers={H: "1.1"}).status == 401  # signed for 1.0, relabelled 1.1
    from conftest import signed

    from atlas_core.api import Request

    head = signed(h.key, "GET", "/v1/tasks/aaaaaaaa", b"", h.w.clock(), version="1.1")
    head.pop(H)
    assert h.api.handle(Request("GET", "/v1/tasks/aaaaaaaa", head, b"")).status == 401


def test_the_discovery_call_is_never_negotiated_and_has_no_echo(h):
    r = h.call("GET", "/v1/version", headers={H: "1.1"})
    assert r.status == 200 and H not in r.headers


def test_an_unknown_version_is_refused_after_authentication(h):
    assert h.call("POST", "/v1/tasks", request(), headers={H: "1.2"}).status == 426
    assert h.call("POST", "/v1/tasks", request(), headers={H: "1.2"}, sign=False).status == 401


def test_coverage_states_are_honest_and_tie_to_limitations(h):
    now = h.w.clock()
    cases = {
        "indexing": (report(pending=2, searched=2), ["indexing_incomplete"]),
        "partial": (report(failed=1, failed_reasons={"corrupt": 1}, searched=3), ["partial_work"]),
        "complete": (report(), []),
    }
    for state, (rep, limits) in cases.items():
        h.w.service._d.coverage = {"documents": lambda rep=rep: rep}
        c = build_coverage(["documents"], h.w.service._d.coverage, now)
        assert c["state"] == state and required_limitations(c) == limits
        tid = done(h) if state == "complete" else None
        if tid is None:
            _, rec = h.json("POST", "/v1/tasks", request(key=f"idem-key-{state}"), version="1.1", headers={H: "1.1"})
            h.w.service.run(rec["task_id"])
            tid = rec["task_id"]
        body = json.loads(h.call("GET", f"/v1/tasks/{tid}/answer", version="1.1").body)
        assert body["coverage"]["state"] == state and all(x in body["limitations"] for x in limits)


def test_failed_reasons_unsupported_and_unknown_sources_map_without_guessing():
    now = T0
    c = build_coverage(
        ["documents", "mail"],
        {"documents": lambda: report(failed=3, failed_reasons={"oversized": 1, "unreadable": 1}, unsupported=2), "mail": lambda: report(total=1, searched=1)},
        now,
    )
    assert c["state"] == "partial" and c["total"] == 5
    assert {f["reason_code"]: f["count"] for f in c["failed"]} == {"too_large": 1, "extraction_failed": 2}
    assert c["pending"] == [{"category": "unsupported_source", "count": 2}] and required_limitations(c) == ["source_unsupported", "partial_work"]
    unknown = build_coverage(["finance"], {}, now)
    assert unknown["state"] == "partial" and unknown["total"] is None
    for value in (c, unknown):
        contracts.validate("Coverage", value, "1.1")


def test_a_withheld_1_1_answer_reports_no_coverage_of_the_revoked_source_and_no_model(h):
    tid = done(h)
    h.w.grants._grants[:] = []
    body = json.loads(h.call("GET", f"/v1/tasks/{tid}/answer", version="1.1").body)
    assert body["coverage"]["searched"] == 0 and body["coverage"]["total"] == 0 and "model" not in body
    contracts.validate("AnswerEnvelope", body, "1.1")


def test_the_1_1_event_stream_carries_the_upgraded_final_answer_and_1_0_does_not(h):
    tid = done(h)
    r = h.call("GET", f"/v1/tasks/{tid}/events?after=0", version="1.1")
    events = [json.loads(x[6:]) for x in b"".join(r.stream).decode().splitlines() if x.startswith("data: ")]
    final = next(e for e in events if e["type"] == "final")
    assert final["answer"]["coverage"]["state"] == "complete" and H in r.headers
    r0 = h.call("GET", f"/v1/tasks/{tid}/events?after=0")
    final0 = next(json.loads(x[6:]) for x in b"".join(r0.stream).decode().splitlines() if x.startswith("data: ") and '"final"' in x)
    assert "coverage" not in final0["answer"]


def test_a_task_without_a_model_identity_has_no_model_field(tmp_path):
    h = Harness(World(tmp_path, [grant("documents")]))
    tid = done(h)
    body = json.loads(h.call("GET", f"/v1/tasks/{tid}/answer", version="1.1").body)
    assert "model" not in body and body["coverage"]["state"] == "partial"  # no coverage provider: unknown, never "complete"


def test_a_gateway_less_answer_has_no_identity():
    assert ModelAnswer("x").identity is None


def test_complete_coverage_has_searched_equal_to_total():
    rng = __import__("random").Random(3)
    for _ in range(300):
        indexed, pending, unsupported, failed = (rng.choice([0, 0, 1, 5]) for _ in range(4))
        rep = report(
            total=indexed + pending + unsupported + failed,
            searched=indexed,
            pending=pending,
            unsupported=unsupported,
            failed=failed,
            scan_complete=rng.random() < 0.8,
        )
        c = build_coverage(["documents"], {"documents": lambda rep=rep: rep}, T0)
        contracts.validate("Coverage", c, "1.1")
        if c["state"] == "complete":
            assert c["searched"] == c["total"] and c["pending"] == [] and c["failed"] == []
