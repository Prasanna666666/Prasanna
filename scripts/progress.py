#!/usr/bin/env python3
"""Atlas progress: two percentages over ONE versioned final-product acceptance register (core/docs/acceptance_register.json),
scored by the rules both sides agreed on PR #8 (comment 7226542434).

* Implementation readiness = earned points / every criterion in the register. A criterion earns 1 when all its required checks pass with
  traceable evidence, 0.5 only when it defines an intermediate checkpoint and that checkpoint passes, 0 otherwise. Missing evidence earns 0.
* Review completion = criteria with a recorded Codex verdict (pass OR fail) against a specific revision, with its link / the same total.
  A reopened criterion (later change invalidated its evidence) earns 0 until it is reviewed again.

Nothing is dropped from the denominator: an unknown state, a checkpoint claim without a defined checkpoint, missing evidence or a verdict
without a revision or link is scored 0 AND listed under "flags". Mandatory blockers and owner sign-off are reported separately.

    python3 scripts/progress.py            print the measure (Markdown)
    python3 scripts/progress.py --check    read-only: exit 1 if the tracker's recorded measure is stale
    python3 scripts/progress.py --update   rewrite the tracker's current-measure block (an explicit step, never automatic staging)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "core" / "docs" / "acceptance_register.json"
TRACKER = ROOT / "core" / "docs" / "PROGRESS_TRACKER.md"
MEASURE_START, MEASURE_END = "<!-- measure:start -->", "<!-- measure:end -->"
STATES = {"full": 1.0, "checkpoint": 0.5, "none": 0.0}
NO_CHECKPOINT = "None defined"


def implementation_points(c: dict) -> tuple[float, str | None]:
    """Points for one criterion and, when its claim cannot be credited, why."""
    impl = c.get("implementation", {})
    state = impl.get("state")
    if state not in STATES:
        return 0.0, f"unknown implementation state {state!r}"
    if state == "none":
        return 0.0, None
    if not impl.get("evidence"):
        return 0.0, f"{state} claimed without evidence"
    if state == "checkpoint" and (not c.get("checkpoint") or c["checkpoint"].startswith(NO_CHECKPOINT)):
        return 0.0, "checkpoint claimed but no intermediate checkpoint is defined (score 0 or 1)"
    return STATES[state], None


def review_point(c: dict) -> tuple[float, str | None]:
    review = c.get("review") or {}
    if review.get("reopened"):
        return 0.0, f"reopened: {review['reopened']}"
    verdict = review.get("verdict")
    if verdict is None:
        return 0.0, None
    if verdict not in ("pass", "fail"):
        return 0.0, f"unknown verdict {verdict!r}"
    if not review.get("revision") or not review.get("link"):
        return 0.0, "verdict recorded without its revision or link"
    return 1.0, None


def score(criteria: list[dict]) -> dict:
    earned = reviewed = 0.0
    flags: list[str] = []
    blockers = 0
    for c in criteria:
        points, why = implementation_points(c)
        earned += points
        if why:
            flags.append(f"{c['id']}: {why}")
        r, rwhy = review_point(c)
        reviewed += r
        if rwhy:
            flags.append(f"{c['id']}: {rwhy}")
        if c.get("mandatory", True) and points < 1.0:
            blockers += 1
    total = len(criteria)
    return {
        "total": total, "earned": earned, "reviewed": reviewed, "flags": flags, "blockers": blockers,
        "implementation": earned / total if total else 0.0, "review": reviewed / total if total else 0.0,
        "sign_offs": sum(1 for c in criteria if (c.get("sign_off") or {}).get("by") == "Owner"),
    }  # fmt: skip


def inventory() -> dict[str, int]:
    """Repository-tracked source and tests (git ls-files), so the counts are reproducible."""
    files = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=False).stdout.split()  # noqa: S603, S607
    code = [f for f in files if f.endswith((".py", ".swift"))]
    tests = [f for f in code if "/tests/" in f or "Tests/" in f or Path(f).name.startswith("test_")]
    source = [f for f in code if f not in tests]

    def count(paths: list[str], pattern: str) -> int:
        return sum(len(re.findall(pattern, (ROOT / p).read_text(encoding="utf-8", errors="ignore"), re.M)) for p in paths if (ROOT / p).exists())

    return {
        "source_files": len(source), "test_files": len(tests),
        "source_lines": sum(len((ROOT / p).read_text(encoding="utf-8", errors="ignore").splitlines()) for p in source if (ROOT / p).exists()),
        "source_functions": count(source, r"^\s*(?:async\s+)?def |\bfunc "), "test_functions": count(tests, r"^\s*def test_|\bfunc test"),
    }  # fmt: skip


def measure() -> dict:
    register = json.loads(REGISTER.read_text(encoding="utf-8"))
    criteria = register["criteria"]
    result = score(criteria)
    result["by_source"] = {s: score([c for c in criteria if c["source"] == s]) for s in sorted({c["source"] for c in criteria})}
    result["first_mac"] = score([c for c in criteria if "first-mac" in c.get("milestones", [])])
    result["register"] = {k: register[k] for k in ("version", "status", "base_revision")}
    result["inventory"] = inventory()
    result["batches"] = register.get("review_batches", [])
    return result


def markdown(m: dict) -> str:
    v = m["register"]
    lines = [
        f"**Implementation readiness {m['implementation']:.1%}** ({m['earned']:g}/{m['total']}) · **Review completion {m['review']:.1%}** "
        f"({m['reviewed']:g}/{m['total']}) · register v{v['version']} at `{v['base_revision'][:7]}` ({v['status']})",
        "",
        f"Mandatory criteria not yet passing: **{m['blockers']}** of {m['total']}. Owner sign-offs recorded: {m['sign_offs']}.",
        "",
        "| Part of the register | Criteria | Implementation | Review |",
        "|---|---:|---:|---:|",
    ]
    for name, s in m["by_source"].items():
        lines.append(f"| {name} | {s['total']} | {s['earned']:g} ({s['implementation']:.0%}) | {s['reviewed']:g} ({s['review']:.0%}) |")
    f = m["first_mac"]
    lines += [
        "",
        f"First Mac milestone subset (MAC-01 to MAC-20): implementation {f['earned']:g}/{f['total']} ({f['implementation']:.1%}), review {f['reviewed']:g}/{f['total']} ({f['review']:.1%}).",
        "",
    ]
    inv = m["inventory"]
    lines.append(
        f"Supporting inventory (git-tracked): {inv['source_files']} source files, {inv['source_lines']:,} lines, {inv['source_functions']} functions; "
        f"{inv['test_files']} test files, {inv['test_functions']} test functions. Whole-product line and function review coverage: **unmeasured** "
        f"(reviewed ranges are recorded per batch from {len(m['batches'])} batch record(s); no defensible whole-product numerator yet)."
    )
    if m["flags"]:
        lines += ["", f"Flags ({len(m['flags'])}, scored 0 and kept in the denominator):", *[f"- {x}" for x in m["flags"]]]
    return "\n".join(lines)


def _recorded() -> str:
    text = TRACKER.read_text(encoding="utf-8")
    return text.split(MEASURE_START + "\n", 1)[1].split("\n" + MEASURE_END, 1)[0]


def update() -> None:
    text = TRACKER.read_text(encoding="utf-8")
    head, rest = text.split(MEASURE_START, 1)
    _, tail = rest.split(MEASURE_END, 1)
    TRACKER.write_text(f"{head}{MEASURE_START}\n{markdown(measure())}\n{MEASURE_END}{tail}", encoding="utf-8")


def check_hook() -> int:
    """Claude Code PreToolUse hook, READ-ONLY: before a `git commit`, refuse the commit while the tracker's recorded measure is stale.
    It never edits or stages anything; the update is an explicit step."""
    payload = json.loads(sys.stdin.read() or "{}")
    command = str(payload.get("tool_input", {}).get("command", ""))
    if not re.search(r"\bgit\s+commit\b", command) or _recorded() == markdown(measure()):
        return 0
    reason = "The progress tracker is stale: run `python3 scripts/progress.py --update`, review it, stage it, then commit."
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}))
    return 0


if __name__ == "__main__":
    if "--hook" in sys.argv:
        sys.exit(check_hook())
    if "--check" in sys.argv:
        stale = _recorded() != markdown(measure())
        print("stale: run scripts/progress.py --update" if stale else "current")
        sys.exit(1 if stale else 0)
    if "--update" in sys.argv:
        update()
    print(markdown(measure()))
