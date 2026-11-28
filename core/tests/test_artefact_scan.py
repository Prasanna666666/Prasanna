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
    workflow = (ROOT.parent / ".github" / "workflows" / "ci.yml").read_text()
    assert "tools/scan_artefacts.py" in workflow and "junit" in workflow and "upload-artifact" in workflow


def test_a_known_sentinel_in_a_log_is_caught(tmp_path):
    (tmp_path / "pytest.log").write_text(f"FAILED ... {SENTINEL_DOC}")
    assert run(tmp_path).returncode == 1


def test_the_ci_failure_paths_job_injects_a_failing_test_and_a_seeded_log_and_asserts_both_guards():
    """MAC-07: the hosted proof stays in the workflow. It runs the core job's own commands on an injected failing test (status recorded, report
    and log kept) and on a log seeded with a sentinel (scan fails, so nothing is published)."""
    workflow = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    job = workflow.split("  core-failure-paths:", 1)[1].split("\n  macos:", 1)[0]
    for needle in ("set -o pipefail", "--junitxml=../failpath/artefacts/junit.xml", 'test "${{ steps.failing.outputs.status }}" != "0"',
                   "python tools/scan_artefacts.py ../seeded", 'test "${{ steps.seeded.outcome }}" = "failure"', "if: steps.seeded.outcome == 'success'"):  # fmt: skip
        assert needle in job, needle
