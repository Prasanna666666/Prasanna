#!/usr/bin/env python3
"""Atlas progress measure: how close the project is to the FINAL product, as two percentages.

* Implementation: how much of the final product is built and verified.
* Review: how much of the final product has been independently reviewed, had its findings closed, and been accepted.

Most inputs are counted from the project's own records (PRD and use-case conformance matrices, Stage 3 acceptance, the Stage 4-8 report, the
defect register, the source tree). The rest are judged scores kept, with their reasons, in `core/docs/progress_inputs.json`, so that every
number can be traced and challenged. Live GitHub facts (CI jobs, review threads) are passed in that file too; they are refreshed each cycle.

Run: python3 scripts/progress.py            (prints the Markdown block for the tracker)
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENESIS = ROOT / "docs" / "genesis"
INPUTS = ROOT / "core" / "docs" / "progress_inputs.json"

# How much of the final product one conformance row represents, by its recorded status (the first word or two of the status cell).
ROW_CREDIT = [
    ("NOT IMPLEMENTED", 0.0),
    ("DEFERRED", 0.0),
    ("UNVERIFIED", 0.25),
    ("PARTIAL FOUNDATION", 0.3),
    ("PARTIAL", 0.5),
    ("IMPLEMENTED", 0.8),  # implemented as source and tests, not owner-accepted
    ("ALIGNED", 1.0),  # a scope boundary that is already true
]

# Stage 4-8 exit evidence (core/docs/STAGES_4_TO_8.md): MET-L means met locally with synthetic data, not on the target Mac or by the owner.
# The rows are the implementer's own report and are NOT architect-reviewed, so MET-L earns 0.5, not more.
EXIT_CREDIT = [("DEFERRED-FINAL", 0.0), ("NEVER", None), ("PROPOSED", 0.2), ("PARTIAL", 0.3), ("SCRIPT", 0.3), ("WRITTEN", 0.3), ("MET-L", 0.5)]


def _credit(status: str, table: list[tuple[str, float | None]]) -> float | None:
    s = re.sub(r"[*`]", "", status).strip().upper()
    for prefix, value in table:
        if s.startswith(prefix):
            return value
    return None


def _status_cells(path: Path, column: int = 1) -> list[str]:
    """The status cell of every data row of every table whose header names a Status column at `column`."""
    cells: list[str] = []
    in_table = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            in_table = False
            continue
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if set(line.strip()) <= set("|-: "):
            continue
        if len(parts) > column and parts[column].lower() == "status":
            in_table = True
            continue
        if in_table and len(parts) > column:
            cells.append(parts[column])
    return cells


def conformance(path: Path) -> tuple[float, int, Counter[str]]:
    rows = _status_cells(path)
    scored = [(c, _credit(c, ROW_CREDIT)) for c in rows]
    counted = [v for _, v in scored if v is not None]
    tally: Counter[str] = Counter(re.sub(r"[*`]", "", c).split("/")[0].split("(")[0].strip().upper()[:24] for c, _ in scored)
    return (sum(counted) / len(counted) if counted else 0.0), len(counted), tally


def stages_4_to_8() -> tuple[dict[int, float], int]:
    """One score per stage, from the exit-evidence rows in that stage's own section. A stage section without rows scores 0."""
    text = (ROOT / "core" / "docs" / "STAGES_4_TO_8.md").read_text(encoding="utf-8")
    sections = re.split(r"^## Stage (\d)", text, flags=re.M)
    scores, rows = {}, 0
    for number, body in zip(sections[1::2], sections[2::2], strict=False):
        values = [v for v in (_credit(c, EXIT_CREDIT) for c in _status_cells_after(body, "Exit evidence")) if v is not None]
        scores[int(number)] = sum(values) / len(values) if values else 0.0
        rows += len(values)
    return scores, rows


def _status_cells_after(text: str, header: str) -> list[str]:
    out, active = [], False
    for line in text.splitlines():
        if line.startswith(f"| {header}"):
            active = True
            continue
        if not line.startswith("|"):
            active = False
            continue
        if active and not set(line.strip()) <= set("|-: "):
            parts = [p.strip() for p in line.strip().strip("|").split("|")]
            if len(parts) > 1:
                out.append(parts[1])
    return out


def code_size() -> dict[str, int]:
    py = [p for p in ROOT.rglob("*.py") if ".git" not in p.parts and "node_modules" not in p.parts and ".build" not in p.parts]
    swift = [p for p in ROOT.rglob("*.swift") if ".build" not in p.parts]
    src_py = [p for p in py if "/tests/" not in str(p) and not p.name.startswith("test_")]
    test_py = [p for p in py if p not in src_py]

    def count(files: list[Path], pattern: str) -> int:
        return sum(len(re.findall(pattern, f.read_text(encoding="utf-8", errors="ignore"), re.M)) for f in files)

    return {
        "python_source_functions": count(src_py, r"^\s*(?:async\s+)?def "),
        "python_tests": count(test_py, r"^\s*def test_"),
        "swift_functions": count([f for f in swift if "Tests" not in str(f)], r"\bfunc "),
        "swift_tests": count([f for f in swift if "Tests" in str(f)], r"\bfunc test"),
        "source_lines": sum(len(f.read_text(encoding="utf-8", errors="ignore").splitlines()) for f in src_py + swift),
    }


def defect_ids() -> int:
    return len(set(re.findall(r"ATLAS-[A-Z]+-\d+", (GENESIS / "DEFECT_REGISTER.md").read_text(encoding="utf-8"))))


def measure() -> dict:
    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))
    prd, prd_n, prd_tally = conformance(GENESIS / "PRD_CONFORMANCE.md")
    uc, uc_n, uc_tally = conformance(GENESIS / "USE_CASE_CONFORMANCE.md")
    later, later_n = stages_4_to_8()
    stages = inputs["stages"]
    stage_scores = [stages["0"], stages["1"], stages["2"], stages["3"], *(min(later.get(n, 0.0), stages.get(f"{n}_cap", 1.0)) for n in range(4, 9))]
    ci = inputs["ci"]
    gates = inputs["target_gates"]
    test_score = 0.40 * inputs["synthetic_test_strength"] + 0.20 * (ci["passed"] / ci["total"]) + 0.40 * (gates["passed"] / gates["total"])
    dims = {
        "Requirements (PRD rows)": (20, prd),
        "Functionality (use cases)": (20, uc),
        "Stages 0-8 (exit evidence)": (20, sum(stage_scores) / len(stage_scores)),
        "Design (decisions, ADRs)": (10, inputs["judged"]["design"]["score"]),
        "Test and verification": (15, test_score),
        "Usability and accessibility": (10, inputs["judged"]["usability"]["score"]),
        "Standards, security, release": (5, inputs["judged"]["standards"]["score"]),
    }
    implementation = sum(w * s for w, s in dims.values()) / sum(w for w, _ in dims.values())
    r = inputs["review"]
    threads = r["threads_resolved"] / r["threads_total"]
    findings = 0.5 * threads + 0.5 * (r["register_closed"] / defect_ids())
    acceptance = r["criteria_accepted"] / r["criteria_total"]
    review_dims = {
        "Breadth (code under independent review)": (20, r["breadth"]),
        "Findings closed": (30, findings),
        "Accepted by architect and owner": (50, acceptance),
    }
    review = sum(w * s for w, s in review_dims.values()) / 100
    return {
        "implementation": implementation, "review": review, "dims": dims, "review_dims": review_dims, "stage_scores": stage_scores,
        "counts": {"prd_rows": prd_n, "uc_rows": uc_n, "stage_4_8_rows": later_n, "defect_ids": defect_ids(), **code_size()},
        "tallies": {"prd": prd_tally.most_common(6), "uc": uc_tally.most_common(6)}, "inputs": inputs,
    }  # fmt: skip


def markdown(m: dict) -> str:
    lines = [f"**Implementation: {m['implementation']:.0%}**  ·  **Review: {m['review']:.0%}**  (head `{m['inputs']['head'][:7]}`)", ""]
    lines += ["| Implementation dimension | Weight | Score |", "|---|---:|---:|"]
    lines += [f"| {name} | {w} | {s:.0%} |" for name, (w, s) in m["dims"].items()]
    lines += ["", "| Review dimension | Weight | Score |", "|---|---:|---:|"]
    lines += [f"| {name} | {w} | {s:.0%} |" for name, (w, s) in m["review_dims"].items()]
    lines += ["", "Stages 0-8: " + ", ".join(f"S{i} {s:.0%}" for i, s in enumerate(m["stage_scores"])), ""]
    c = m["counts"]
    lines.append(
        f"Counted: {c['prd_rows']} PRD rows, {c['uc_rows']} use cases, {c['stage_4_8_rows']} Stage 4-8 exit rows, {c['defect_ids']} defect IDs; "
        f"{c['python_source_functions']} Python and {c['swift_functions']} Swift functions, {c['source_lines']:,} source lines; "
        f"{c['python_tests']} Python and {c['swift_tests']} Swift test functions."
    )
    return "\n".join(lines)


TRACKER = ROOT / "core" / "docs" / "PROGRESS_TRACKER.md"
MEASURE_START, MEASURE_END, LOG_END = "<!-- measure:start -->", "<!-- measure:end -->", "<!-- changes:end -->"


def _last_logged(text: str) -> tuple[float, float] | None:
    rows = re.findall(r"^\| [^|]+ \| after [^|]+ \| ([\d.]+)% \| ([\d.]+)% \|", text.split(LOG_END, maxsplit=1)[0], re.M)
    return (float(rows[-1][0]), float(rows[-1][1])) if rows else None


def update(note: str, base: str) -> str:
    """Rewrite the tracker's current measure and add one change-log row for this change. Returns the row."""
    m = measure()
    text = TRACKER.read_text(encoding="utf-8")
    head, rest = text.split(MEASURE_START, 1)
    _, tail = rest.split(MEASURE_END, 1)
    text = f"{head}{MEASURE_START}\n{markdown(m)}\n{MEASURE_END}{tail}"
    implementation, review = round(m["implementation"] * 100, 1), round(m["review"] * 100, 1)
    before = _last_logged(text)
    delta = "baseline" if before is None else f"{implementation - before[0]:+.1f} / {review - before[1]:+.1f}"
    note = re.sub(r"[|\n\r]+", " ", note).strip()[:140] or "change"
    from datetime import UTC, datetime

    row = f"| {datetime.now(UTC).date().isoformat()} | after `{base[:7]}` | {implementation:.1f}% | {review:.1f}% | {delta} | {note} |"
    text = text.replace(LOG_END, f"{row}\n{LOG_END}", 1)
    TRACKER.write_text(text, encoding="utf-8")
    return row


def _git(*args: str) -> str:
    """git, by name from PATH, with a fixed argument list built here (never from the hook payload)."""
    import subprocess

    done = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False)  # noqa: S603, S607
    return done.stdout.strip()


def hook() -> int:
    """Claude Code PreToolUse hook: before a `git commit` in this repository, refresh the tracker and stage it, so every commit carries its measure."""
    payload = json.loads(sys.stdin.read() or "{}")
    command = str(payload.get("tool_input", {}).get("command", ""))
    if not re.search(r"\bgit\s+commit\b", command) or "--amend" in command:
        return 0
    message = re.search(r"""-m\s+(?:"([^"\n]*)|'([^'\n]*))""", command)
    note = next((g for g in (message.groups() if message else ()) if g), "commit")
    row = update(note, _git("rev-parse", "HEAD") or "unknown")
    _git("add", str(TRACKER.relative_to(ROOT)))
    print(json.dumps({"systemMessage": f"Progress tracker updated: {row}"}))
    return 0


if __name__ == "__main__":
    if "--hook" in sys.argv:
        sys.exit(hook())
    if "--update" in sys.argv:
        args = sys.argv[sys.argv.index("--update") + 1 :]
        print(update(" ".join(args), _git("rev-parse", "HEAD")))
        sys.exit(0)
    result = measure()
    if "--json" in sys.argv:
        print(json.dumps({k: v for k, v in result.items() if k in ("implementation", "review", "counts")}, indent=1))
    else:
        print(markdown(result))
