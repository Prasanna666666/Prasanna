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
