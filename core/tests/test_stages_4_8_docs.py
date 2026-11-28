"""The Stages 4 to 8 report names only tests that exist, and never lets a status word drift from the rows it labels."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "STAGES_4_TO_8.md"


def existing() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in (ROOT / "tests").glob("test_*.py"):
        found[path.name] = {n.name for n in ast.walk(ast.parse(path.read_text())) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}
    return found


def test_every_python_test_the_report_names_exists():
    tests, current, missing = existing(), None, []
    for segment in re.findall(r"`([^`]+)`", DOC.read_text()):
        match = re.fullmatch(r"(?:(test_[a-z0-9_]+\.py))?::(test_[a-z0-9_]+)", segment)
        if match:
            current = match.group(1) or current
            if current is None or match.group(2) not in tests.get(current, set()):
                missing.append(segment)
        elif re.fullmatch(r"test_[a-z0-9_]+\.py", segment):
            current = segment
            assert segment in tests, segment
    assert missing == [], missing


def test_the_report_states_its_limits_in_plain_words():
    text = DOC.read_text()
    for required in ("NOT architect-reviewed", "NOT accepted", "one branch and the one pull request", "NOT BUILT", "DEFERRED-FINAL", "Not wired"):
        assert required in text, required
    assert "owner-tryable build" in text and "Stage 3 is still not accepted" in text
