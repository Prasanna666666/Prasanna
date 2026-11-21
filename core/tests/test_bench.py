"""Criterion 10: the overhead of the foundation is measured with stubs on a named machine; no latency target is claimed and no ingestion-load figure is produced here."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.criterion(10)
def test_the_overhead_benchmark_runs_and_reports_percentiles_for_a_named_machine():
    out = subprocess.run(
        [sys.executable, str(ROOT / "bench" / "overhead.py"), "--runs", "20", "--json"], capture_output=True, text=True, check=True, timeout=120, cwd=ROOT
    )
    report = json.loads(out.stdout)
    assert "NOT the target Mac" in report["machine"]["role"] and "not answer latency" in report["scope"]
    for name, result in report["results"].items():
        assert result["p50_ms"] >= 0 and result["p95_ms"] >= result["p50_ms"], name
    assert {"policy_decide", "task_submit_and_run_with_stubs", "api_signed_version_roundtrip", "contract_validate_TaskRequest"} <= set(report["results"])
