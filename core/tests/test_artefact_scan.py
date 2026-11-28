"""Criterion 9: CI artefacts are scanned for personal-content sentinels (the scanner, and that CI runs it)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from conftest import SENTINEL_DOC, SENTINEL_FIN

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "scan_artefacts.py"


def run(*paths: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(TOOL), *map(str, paths)], capture_output=True, text=True, check=False)


@pytest.mark.criterion(9)
def test_the_scanner_passes_clean_artefacts_and_fails_on_any_sentinel_without_printing_it(tmp_path):
    (tmp_path / "ok.log").write_text("1082 passed in 90s\n")
    assert run(tmp_path).returncode == 0
    (tmp_path / "junit.xml").write_text(f"<testcase>{SENTINEL_FIN}</testcase>")
    done = run(tmp_path)
    assert done.returncode == 1 and "junit.xml" in done.stdout and SENTINEL_FIN not in done.stdout + done.stderr


@pytest.mark.criterion(9)
def test_the_scanner_fails_closed_when_there_is_nothing_to_scan(tmp_path):
    assert run(tmp_path / "missing").returncode == 2 and run().returncode == 2


@pytest.mark.criterion(9)
def test_the_ci_core_job_saves_its_artefacts_scans_them_and_uploads_them():
    action = (ROOT.parent / ".github" / "actions" / "core-tests" / "action.yml").read_text()
    assert "tools/scan_artefacts.py" in action and "junit" in action and "upload-artifact" in action
    core = _job("core", "core-failure-paths")
    assert "uses: ./.github/actions/core-tests" in core and "pytest" not in core  # no second, divergent copy of the steps


def _job(name: str, following: str) -> str:
    workflow = (ROOT.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    return workflow.split(f"\n  {name}:\n", 1)[1].split(f"\n  {following}:", 1)[0]


def test_a_known_sentinel_in_a_log_is_caught(tmp_path):
    (tmp_path / "pytest.log").write_text(f"FAILED ... {SENTINEL_DOC}")
    assert run(tmp_path).returncode == 1


def test_the_ci_failure_paths_job_runs_the_core_jobs_own_steps_and_asserts_both_gates():
    """MAC-07: the hosted proof runs the very steps the core job publishes with (the shared action, unchanged), not a copy of them: a failing
    test fails those steps with its report published and read back, and a sentinel log fails them with nothing published."""
    action = (ROOT.parent / ".github" / "actions" / "core-tests" / "action.yml").read_text(encoding="utf-8")
    steps = action.split("\n    - name: ")
    order = [next(n for n in ("Tests", "Scan", "Publish", "Fail") if step.startswith(n)) for step in steps[1:]]
    assert order == ["Tests", "Scan", "Publish", "Fail"]
    tests, scan, publish, final = steps[1:]
    assert "set -o pipefail" in tests and "|| status=$?" in tests and "--junitxml=" in tests
    assert "python tools/scan_artefacts.py" in scan and "continue-on-error" not in scan
    assert "upload-artifact" in publish and "if:" not in publish.split("with:")[0]  # the default success(): never after a failed scan
    assert "always()" in final and "exit 1" in final
    job = _job("core-failure-paths", "macos")
    assert job.count("uses: ./.github/actions/core-tests") == 2
    for needle in ('test "${{ steps.a.outcome }}" = "failure"', 'test "${{ steps.a.outputs.published }}" = "success"',
                   "grep -q 'failures=\"1\"' fetched-a/junit-failpath-a.xml", 'test "${{ steps.b.outputs.status }}" = "0"',
                   'test "${{ steps.b.outputs.scan }}" = "failure"', 'test "${{ steps.b.outputs.published }}" != "success"',
                   'test "${{ steps.b.outcome }}" = "failure"', 'test "${{ steps.fetch-b.outcome }}" = "failure"'):  # fmt: skip
        assert needle in job, needle
