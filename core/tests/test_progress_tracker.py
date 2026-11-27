"""The progress calculator (scripts/progress.py) over the acceptance register, scored by the rules agreed on PR #8 (comment 7226542434):
full credit is reachable, partial credit needs a defined checkpoint, missing evidence earns nothing, nothing is dropped from the denominator,
and a reopened criterion loses its review credit. The tracker must also carry the measure of the tree it is committed with."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def progress():
    return runpy.run_path(str(ROOT / "scripts" / "progress.py"))


def crit(cid="X-01", state="none", evidence=("proof",), checkpoint="Implemented with tests", verdict=None, revision="a" * 40, link="https://x", **extra):
    c = {"id": cid, "source": "t", "mandatory": True, "checkpoint": checkpoint, "implementation": {"state": state, "evidence": list(evidence)}}
    c["review"] = {"verdict": verdict, "revision": revision if verdict else None, "link": link if verdict else None, **extra}
    return c


def test_an_untouched_inventory_scores_zero_on_both(progress):
    s = progress["score"]([crit("A"), crit("B")])
    assert (s["implementation"], s["review"], s["blockers"], s["flags"]) == (0.0, 0.0, 2, [])


def test_a_fully_satisfied_and_fully_reviewed_inventory_scores_one_hundred_percent(progress):
    s = progress["score"]([crit("A", "full", verdict="pass"), crit("B", "full", verdict="pass")])
    assert (s["implementation"], s["review"], s["blockers"], s["flags"]) == (1.0, 1.0, 0, [])


def test_partial_credit_comes_only_from_a_defined_checkpoint_and_a_failing_verdict_still_counts_as_reviewed(progress):
    s = progress["score"]([crit("A", "checkpoint", verdict="fail"), crit("B", "full"), crit("C")])
    assert s["earned"] == 1.5 and s["implementation"] == pytest.approx(0.5) and s["reviewed"] == 1 and s["blockers"] == 2
    undefined = progress["score"]([crit("D", "checkpoint", checkpoint="None defined: scored 0 or 1")])
    assert undefined["earned"] == 0 and "no intermediate checkpoint" in undefined["flags"][0]


def test_missing_evidence_earns_nothing_and_is_flagged_not_dropped(progress):
    s = progress["score"]([crit("A", "full", evidence=()), crit("B", "checkpoint", evidence=())])
    assert s["total"] == 2 and s["earned"] == 0 and len(s["flags"]) == 2 and all("without evidence" in f for f in s["flags"])


def test_unknown_states_and_unlinked_verdicts_stay_in_the_denominator_with_zero_credit(progress):
    s = progress["score"]([crit("A", "done-ish"), crit("B", "full", verdict="pass", link=None), crit("C", "full", verdict="maybe")])
    assert s["total"] == 3 and s["earned"] == 2 and s["reviewed"] == 0 and len(s["flags"]) == 3


def test_a_regression_reopens_the_criterion_and_removes_its_review_credit(progress):
    before = progress["score"]([crit("A", "full", verdict="pass")])
    after = progress["score"]([crit("A", "checkpoint", verdict="pass", reopened="commit abc changed the delivery path")])
    assert (before["implementation"], before["review"]) == (1.0, 1.0) and (after["implementation"], after["review"]) == (0.5, 0.0)
    assert any("reopened" in f for f in after["flags"])


def test_the_register_has_stable_unique_ids_and_every_criterion_names_its_pass_condition_owners_and_evidence():
    register = json.loads((ROOT / "core" / "docs" / "acceptance_register.json").read_text(encoding="utf-8"))
    ids = [c["id"] for c in register["criteria"]]
    assert register["version"] and len(ids) == len(set(ids))
    for c in register["criteria"]:
        assert c["pass_condition"] and c["required_evidence"] and c["refs"] and set(c["owners"]) == {"implementation", "verdict", "sign_off"}, c["id"]


def test_the_recorded_measure_matches_the_tree_so_no_change_lands_without_its_update(progress):
    """Every change must carry its measure: run `python3 scripts/progress.py --update`, review and stage the tracker."""
    tracker = (ROOT / "core" / "docs" / "PROGRESS_TRACKER.md").read_text(encoding="utf-8")
    recorded = tracker.split("<!-- measure:start -->\n", 1)[1].split("\n<!-- measure:end -->", 1)[0]
    assert recorded == progress["markdown"](progress["measure"]()), "the tracker is stale: run scripts/progress.py --update"
