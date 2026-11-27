"""The progress calculator (scripts/progress.py) over the acceptance register, scored by the rules agreed on PR #8 (comments 7226542434
and 7226926847) and the register review (7226745827): full credit is reachable, partial credit needs a defined checkpoint, only
structured revision-specific evidence earns credit, verdicts need provenance, nothing in scope leaves the denominator, out-of-scope and
aggregate rows score nowhere, and a reopened criterion loses both credits. The tracker must carry the measure of its committed tree."""

from __future__ import annotations

import json
import re
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40


@pytest.fixture(scope="module")
def progress():
    return runpy.run_path(str(ROOT / "scripts" / "progress.py"))


def proof(kind="test", revision=SHA, ref="core/tests/test_x.py::test_y", **extra):
    return {"kind": kind, "revision": revision, "ref": ref, **extra}


def crit(cid="X-01", state="none", evidence=None, checkpoint="Implemented with tests", verdict=None, scope="in", **extra):
    review = {"verdict": verdict}
    if verdict in ("pass", "fail"):
        review.update(revision=SHA, link="https://x/review", reviewer="Codex", review_id="1")
    review.update(extra.pop("review_extra", {}))
    c = {"id": cid, "source": "t", "scope": scope, "mandatory": True, "checkpoint": checkpoint, "review": review}
    c["implementation"] = {"state": state, "evidence": [proof()] if evidence is None else evidence}
    return {**c, **extra}


def test_an_untouched_inventory_scores_zero_on_both(progress):
    s = progress["score"]([crit("A"), crit("B")])
    assert (s["implementation"], s["review"], s["blockers"], s["flags"]) == (0.0, 0.0, 2, [])


def test_a_fully_satisfied_and_fully_reviewed_inventory_scores_one_hundred_percent(progress):
    s = progress["score"]([crit("A", "full", verdict="pass"), crit("B", "full", verdict="pass")])
    assert (s["implementation"], s["review"], s["blockers"], s["flags"]) == (1.0, 1.0, 0, [])


def test_partial_credit_comes_only_from_a_defined_checkpoint_and_a_failing_verdict_still_counts_as_reviewed(progress):
    s = progress["score"]([crit("A", "checkpoint", verdict="fail"), crit("B", "full"), crit("C")])
    assert s["earned"] == 1.5 and s["reviewed"] == 1 and s["blockers"] == 2
    undefined = progress["score"]([crit("D", "checkpoint", checkpoint="None defined: scored 0 or 1")])
    assert undefined["earned"] == 0 and "no intermediate checkpoint" in undefined["flags"][0]


def test_missing_or_unstructured_evidence_earns_nothing_and_is_flagged_not_dropped(progress):
    s = progress["score"]([crit("A", "full", evidence=[]), crit("B", "checkpoint", evidence=["a sentence, not a record"])])
    assert s["total"] == 2 and s["earned"] == 0 and len(s["flags"]) == 2


@pytest.mark.parametrize(
    "item",
    [
        proof(revision=""),
        proof(revision="abc1234"),
        proof(revision="Z" * 40),
        proof(kind="ci"),
        proof(kind="carry_forward", link="https://x"),
        proof(kind="hearsay"),
        proof(ref=""),
    ],
)
def test_malformed_evidence_records_are_refused(progress, item):
    s = progress["score"]([crit("A", "full", evidence=[item])])
    assert s["earned"] == 0 and len(s["flags"]) == 1


def test_a_status_or_commit_citation_alone_proves_nothing_but_a_document_proves_a_document_deliverable(progress):
    status_only = progress["score"]([crit("A", "full", evidence=[proof(kind="commit", ref="ci.yml")])])
    doc = progress["score"]([crit("B", "full", evidence=[proof(kind="doc", ref="AUDIT.md")], deliverable="document")])
    assert status_only["earned"] == 0 and "proves the checks" in status_only["flags"][0] and doc["earned"] == 1.0


def test_verdicts_need_a_full_revision_a_link_and_reviewer_provenance(progress):
    no_link = crit("A", "full", verdict="pass", review_extra={"link": None})
    short_sha = crit("B", "full", verdict="pass", review_extra={"revision": "abc1234"})
    no_reviewer = crit("C", "full", verdict="pass", review_extra={"reviewer": None})
    pending = crit("D", "full", verdict="pending")
    s = progress["score"]([no_link, short_sha, no_reviewer, pending])
    assert s["reviewed"] == 0 and len(s["flags"]) == 3  # pending is not a fault, just not yet reviewed


def test_full_credit_conflicting_with_a_failed_gate_is_capped_and_flagged(progress):
    with_checkpoint = progress["score"]([crit("A", "full", verdict="fail")])
    without = progress["score"]([crit("B", "full", verdict="fail", checkpoint="None defined: scored 0 or 1")])
    assert with_checkpoint["earned"] == 0.5 and without["earned"] == 0 and "conflicts" in with_checkpoint["flags"][0]


def test_a_regression_reopens_the_criterion_and_removes_both_credits(progress):
    before = progress["score"]([crit("A", "full", verdict="pass")])
    after = progress["score"]([crit("A", "full", verdict="pass", reopened="commit abc changed the delivery path")])
    assert (before["implementation"], before["review"]) == (1.0, 1.0) and (after["implementation"], after["review"]) == (0.0, 0.0)


def test_out_of_scope_aggregate_and_boundary_rows_are_excluded_from_both_scores(progress):
    s = progress["score"](
        [crit("A", "full", verdict="pass"), crit("D", "full", verdict="pass", scope="out-device"), crit("G", scope="aggregate"), crit("B", scope="boundary")]
    )
    assert (s["total"], s["implementation"], s["review"]) == (1, 1.0, 1.0) and s["excluded"] == {"out-device": 1, "aggregate": 1, "boundary": 1}


def test_duplicate_ids_and_colliding_aliases_are_flagged(progress):
    flags = progress["alias_problems"]([crit("A", aliases=["OLD-1"]), crit("A"), crit("B", aliases=["OLD-1", "C"]), crit("C")])
    assert any("duplicate criterion id A" in f for f in flags)
    assert any("alias OLD-1 already belongs to A" in f for f in flags) and any("alias C is also a criterion id" in f for f in flags)


def test_the_register_has_stable_unique_ids_complete_criteria_and_resolvable_test_evidence(progress):
    register = json.loads((ROOT / "core" / "docs" / "acceptance_register.json").read_text(encoding="utf-8"))
    assert register["version"] == "0.2" and progress["alias_problems"](register["criteria"]) == []
    for c in register["criteria"]:
        assert c["pass_condition"] and c["required_evidence"] and c["source_ref"] and c["scope"] in register["scopes"], c["id"]
        assert set(c["owners"]) == {"implementation", "verdict", "sign_off"}, c["id"]
        for e in c["implementation"]["evidence"]:
            if e["kind"] == "test":
                path, name = e["ref"].split("::")
                source = (ROOT / path).read_text(encoding="utf-8")
                assert re.search(rf"\b(def|func) {name}\b", source), f"{c['id']}: {e['ref']} does not exist"


def test_the_recorded_measure_matches_the_tree_so_no_change_lands_without_its_update(progress):
    """Every change must carry its measure: run `python3 scripts/progress.py --update`, review and stage the tracker."""
    tracker = (ROOT / "core" / "docs" / "PROGRESS_TRACKER.md").read_text(encoding="utf-8")
    recorded = tracker.split("<!-- measure:start -->\n", 1)[1].split("\n<!-- measure:end -->", 1)[0]
    assert recorded == progress["markdown"](progress["measure"]()), "the tracker is stale: run scripts/progress.py --update"
