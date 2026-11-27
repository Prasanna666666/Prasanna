"""The progress measure must keep running and keep its numbers in range: it is recomputed after every review cycle."""

from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_the_progress_measure_runs_and_both_percentages_are_between_zero_and_one():
    progress = runpy.run_path(str(ROOT / "scripts" / "progress.py"))
    result = progress["measure"]()
    assert 0.0 <= result["implementation"] <= 1.0 and 0.0 <= result["review"] <= 1.0
    assert result["counts"]["prd_rows"] > 0 and result["counts"]["uc_rows"] > 0 and result["counts"]["stage_4_8_rows"] > 0
    assert "Implementation:" in progress["markdown"](result)


def test_the_tracker_records_the_cycle_and_head_of_its_inputs():
    import json

    inputs = json.loads((ROOT / "core" / "docs" / "progress_inputs.json").read_text(encoding="utf-8"))
    tracker = (ROOT / "core" / "docs" / "PROGRESS_TRACKER.md").read_text(encoding="utf-8")
    assert f"| {inputs['cycle']} |" in tracker and inputs["head"][:7] in tracker


def test_the_recorded_measure_matches_the_tree_so_no_change_lands_without_its_update():
    """Every change must carry its measure: run `python3 scripts/progress.py --update "<what changed>"` (the commit hook does it)."""
    progress = runpy.run_path(str(ROOT / "scripts" / "progress.py"))
    tracker = (ROOT / "core" / "docs" / "PROGRESS_TRACKER.md").read_text(encoding="utf-8")
    recorded = tracker.split("<!-- measure:start -->\n", 1)[1].split("\n<!-- measure:end -->", 1)[0]
    assert recorded == progress["markdown"](progress["measure"]()), "the tracker is stale: run scripts/progress.py --update"
