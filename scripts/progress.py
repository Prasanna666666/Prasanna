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
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "core" / "docs" / "acceptance_register.json"
TRACKER = ROOT / "core" / "docs" / "PROGRESS_TRACKER.md"
MEASURE_START, MEASURE_END = "<!-- measure:start -->", "<!-- measure:end -->"
STATES = {"full": 1.0, "checkpoint": 0.5, "none": 0.0}
NO_CHECKPOINT = "None defined"


SHA = re.compile(r"[0-9a-f]{40}")
KINDS = {"test", "ci", "commit", "doc", "carry_forward"}
REVIEWERS = {"Codex", "architect"}
SCORED = "in"


def evidence_problem(item: object) -> str | None:  # noqa: PLR0911 - one early answer per refusal reason
    """Why one evidence record is not a valid structured, revision-specific proof reference (None when it is)."""
    if not isinstance(item, dict):
        return "evidence is not a structured record"
    if item.get("kind") not in KINDS:
        return f"unknown evidence kind {item.get('kind')!r}"
    if not SHA.fullmatch(str(item.get("revision", ""))):
        return "evidence revision missing or not a full SHA"
    if not item.get("ref"):
        return "evidence has no reference"
    if item["kind"] == "ci" and not item.get("link"):
        return "CI evidence without its run link"
    if item["kind"] == "carry_forward" and not (item.get("link") and SHA.fullmatch(str(item.get("from_revision", "")))):
        return "carry-forward without its link and full source revision"
    return None


def implementation_points(c: dict) -> tuple[float, str | None]:  # noqa: PLR0911 - one early answer per refusal reason
    """Points for one criterion and, when its claim cannot be credited, why."""
    impl = c.get("implementation", {})
    state = impl.get("state")
    if state not in STATES:
        return 0.0, f"unknown implementation state {state!r}"
    if c.get("reopened"):
        return 0.0, f"reopened: {c['reopened']}"
    if state == "none":
        return 0.0, None
    evidence = impl.get("evidence") or []
    if not evidence:
        return 0.0, f"{state} claimed without evidence"
    bad = next((p for p in map(evidence_problem, evidence) if p), None)
    if bad:
        return 0.0, bad
    proving = {"test", "ci", "carry_forward"} | ({"doc"} if c.get("deliverable") == "document" else set())
    if not any(e["kind"] in proving for e in evidence):
        return 0.0, "no evidence that proves the checks (a document, commit or status citation alone earns nothing)"
    has_checkpoint = bool(c.get("checkpoint")) and not c["checkpoint"].startswith(NO_CHECKPOINT)
    if state == "checkpoint" and not has_checkpoint:
        return 0.0, "checkpoint claimed but no intermediate checkpoint is defined (score 0 or 1)"
    if state == "full" and (c.get("review") or {}).get("verdict") == "fail":
        return (0.5 if has_checkpoint else 0.0), "full credit conflicts with a recorded fail verdict: capped at the checkpoint"
    return STATES[state], None


def review_point(c: dict) -> tuple[float, str | None]:
    review = c.get("review") or {}
    if c.get("reopened") or review.get("reopened"):
        return 0.0, f"reopened: {c.get('reopened') or review.get('reopened')}"
    verdict = review.get("verdict")
    if verdict in (None, "pending"):
        return 0.0, None
    if verdict not in ("pass", "fail"):
        return 0.0, f"unknown verdict {verdict!r}"
    if not SHA.fullmatch(str(review.get("revision", ""))) or not review.get("link"):
        return 0.0, "verdict without a full reviewed SHA or its link"
    if review.get("reviewer") not in REVIEWERS or not review.get("review_id"):
        return 0.0, "verdict without reviewer provenance (reviewer and review id)"
    return 1.0, None


def alias_problems(criteria: list[dict]) -> list[str]:
    """Duplicate IDs, or an alias that names an existing ID or another criterion's alias."""
    ids = [c["id"] for c in criteria]
    problems = [f"duplicate criterion id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    owner: dict[str, str] = {}
    for c in criteria:
        for a in c.get("aliases", []):
            if a in ids:
                problems.append(f"{c['id']}: alias {a} is also a criterion id")
            elif a in owner:
                problems.append(f"{c['id']}: alias {a} already belongs to {owner[a]}")
            owner.setdefault(a, c["id"])
    return problems


def score(criteria: list[dict]) -> dict:
    scored = [c for c in criteria if c.get("scope", SCORED) == SCORED]
    earned = reviewed = 0.0
    flags: list[str] = alias_problems(criteria)
    blockers = structure_ok = 0
    for c in scored:
        points, why = implementation_points(c)
        earned += points
        if why:
            flags.append(f"{c['id']}: {why}")
        r, rwhy = review_point(c)
        reviewed += r
        if rwhy:
            flags.append(f"{c['id']}: {rwhy}")
        structure_ok += not (why or rwhy)
        if c.get("mandatory", True) and points < 1.0:
            blockers += 1
    total = len(scored)
    excluded = Counter(c.get("scope") for c in criteria if c.get("scope", SCORED) != SCORED)
    return {
        "total": total, "earned": earned, "reviewed": reviewed, "flags": flags, "blockers": blockers, "excluded": dict(excluded),
        "structure_ok": structure_ok, "implementation": earned / total if total else 0.0, "review": reviewed / total if total else 0.0,
        "sign_offs": sum(1 for c in scored if (c.get("sign_off") or {}).get("by") == "Owner"),
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
        f"Mandatory criteria not yet passing: **{m['blockers']}** of {m['total']}. Owner sign-offs recorded: {m['sign_offs']}. "
        f"Excluded from both scores: {', '.join(f'{n} {k}' for k, n in sorted(m['excluded'].items())) or 'none'}.",
        "",
        f"Record structure validated by the calculator: {m['structure_ok']} of {m['total']} scored criteria carry no flag. "
        f"Human verification of the linked evidence is separate: it is Codex's recorded verdicts ({m['reviewed']:g}).",
        "",
        "| Part of the register | Criteria | Implementation | Review |",
        "|---|---:|---:|---:|",
    ]
    for name, s in m["by_source"].items():
        lines.append(f"| {name} | {s['total']} | {s['earned']:g} ({s['implementation']:.0%}) | {s['reviewed']:g} ({s['review']:.0%}) |")
    f = m["first_mac"]
    lines += [
        "",
        f"First Mac milestone view (criteria tagged first-mac): implementation {f['earned']:g}/{f['total']} ({f['implementation']:.1%}), review {f['reviewed']:g}/{f['total']} ({f['review']:.1%}).",
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
