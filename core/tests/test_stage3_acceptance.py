"""Criterion 14 of Stage 3: every release-blocking criterion is traced to implementation, automated tests, an evidence class and a known limitation, and every named test exists."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ("STAGE3_ACCEPTANCE.md", "STAGE3_TRACEABILITY.md", "STAGE3_HANDOVER.md", "WP3_5_CLIENT.md", "WP3_6_RELIABILITY.md")


def existing_tests() -> set[str]:
    found: set[str] = set()
    for path in (ROOT / "tests").glob("test_*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                found.add(f"tests/{path.name}::{node.name}")
    return found


def test_every_criterion_is_present_with_evidence_status_and_limitation():
    rows = re.findall(r"^\| (\d+) \|(.+)\|$", (ROOT / "docs" / "STAGE3_ACCEPTANCE.md").read_text(), re.MULTILINE)
    assert [int(n) for n, _ in rows] == list(range(1, 16))
    for number, rest in rows:
        cells = [c.strip() for c in rest.split("|")]
        assert len(cells) == 5, number  # criterion, implementation, tests, evidence, status and limitation
        assert cells[2].count("tests/test_") >= 1 and cells[3] and re.match(r"\W*(MET-L|PARTIAL|PENDING-M)", cells[4]), number


def test_every_test_named_in_the_stage_3_documents_exists():
    existing = existing_tests()
    for name in DOCS:
        path = ROOT / "docs" / name
        if path.exists():
            named = set(re.findall(r"tests/test_[a-z0-9_]+\.py::test_[a-z0-9_]+", path.read_text()))
            assert named <= existing, (name, sorted(named - existing))
