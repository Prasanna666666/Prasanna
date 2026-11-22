"""Criterion 12: the quality and overhead thresholds that CAN be enforced now (synthetic set, scripted model, foundation overhead). Real-model and target-hardware thresholds are proposed in `evals/thresholds_proposed.json`
for acceptance and are not enforced or claimed here."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
THRESHOLDS = json.loads((ROOT / "evals" / "thresholds_proposed.json").read_text(encoding="utf-8"))
ENFORCED = THRESHOLDS["enforced_now"]


@pytest.fixture(scope="module")
def report():
    from evals import harness

    return harness.run()


@pytest.mark.criterion(12)
def test_the_synthetic_quality_thresholds_hold(report):
    quality = report["answer_quality"]
    assert quality["pass_rate"] >= ENFORCED["answer_pass_rate_min"] and report["failed_cases"] == []
    for category, minimum in ENFORCED["category_pass_rate_min"].items():
        assert quality["by_category"][category]["passed"] >= minimum, category
    assert quality["by_category"]["cross_domain"]["passed"] >= 1.0 and ENFORCED["cross_domain_leakage_max"] == 0
    for script, minimum in ENFORCED["retrieval_recall_min_by_script"].items():
        assert report["retrieval_quality"]["by_script"][script]["recall"] >= minimum, script
    assert [gap["id"] for gap in report["known_gaps"]] == ["ja-total"]  # the one recorded gap; a new one must be reported, not hidden


@pytest.mark.criterion(12)
def test_the_foundation_overhead_stays_within_its_regression_thresholds():
    out = subprocess.run(
        [sys.executable, str(ROOT / "bench" / "overhead.py"), "--runs", "30", "--json"], capture_output=True, text=True, check=True, timeout=120, cwd=ROOT
    )
    results = json.loads(out.stdout)["results"]
    for name, limit in ENFORCED["overhead_p95_ms_max"].items():
        assert results[name]["p95_ms"] <= limit, (name, results[name]["p95_ms"], limit)


@pytest.mark.criterion(12)
def test_the_real_model_thresholds_are_proposed_and_clearly_not_enforced():
    proposed = THRESHOLDS["proposed_for_final_stage"]
    assert "NOT measured, NOT enforced" in proposed["scope"] and proposed["warm_first_useful_output_seconds"] == {
        "p50_max": 2,
        "p95_max": 5,
        "source": proposed["warm_first_useful_output_seconds"]["source"],
    }
    assert "Nothing here is a target-Mac or real-model result" in THRESHOLDS["status"]
