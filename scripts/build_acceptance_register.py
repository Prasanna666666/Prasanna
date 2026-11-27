#!/usr/bin/env python3
"""Build version 0.1 of the Atlas final-product acceptance register from the project's own inventories.

Run once to create `core/docs/acceptance_register.json`; afterwards the register is the source of truth and is edited, versioned and
re-baselined by agreement (it refuses to overwrite an existing register unless --force). Kept for provenance: anyone can see how every
criterion of v0.1 was derived and from which row.

Sources, in order: Stages 0-2, Stage 3 criteria and final gates (core/docs/STAGE3_ACCEPTANCE.md), Stage 4-8 exit rows
(core/docs/STAGES_4_TO_8.md), PRD rows (docs/genesis/PRD_CONFORMANCE.md), use cases (docs/genesis/USE_CASE_CONFORMANCE.md) and the
architect's 20 first-Mac release checks (PR #8 comment 7226311601, at 95f67f4).
"""

# ruff: noqa: PLR0913, PLR0917, PLR2004  (a one-off generator: keyword-heavy record builder and fixed table shapes)
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "core" / "docs" / "acceptance_register.json"
BASE_REVISION = "95f67f41fd1a028336813ccd90383fb3c9cdde97"
MAC_REVIEW = "https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6092414795"
OWNERS = {"implementation": "Claude", "verdict": "Codex", "sign_off": "Owner"}


def _rows(text: str) -> list[list[str]]:
    out = []
    for line in text.splitlines():
        if line.startswith("|") and not set(line.strip()) <= set("|-: "):
            out.append([c.strip() for c in line.strip().strip("|").split("|")])
    return out


def _clean(s: str, n: int = 240) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[*`]", "", s)).strip()[:n]


def _criterion(cid, stage, title, refs, pass_condition, evidence, checkpoint, state, impl_evidence, mandatory=True, milestone=None, source=""):
    return {
        "id": cid, "stage": stage, "title": _clean(title, 160), "refs": refs, "owners": OWNERS, "mandatory": mandatory,
        "milestones": [milestone] if milestone else [], "source": source,
        "pass_condition": _clean(pass_condition, 400), "required_evidence": _clean(evidence, 300), "checkpoint": _clean(checkpoint, 300),
        "implementation": {"state": state, "evidence": impl_evidence, "revision": BASE_REVISION},
        "review": {"verdict": None, "revision": None, "link": None},
    }  # fmt: skip


def stages_0_to_2() -> list[dict]:
    return [
        _criterion("S0-01", 0, "Product specification consolidated", ["TARGET_ARCHITECTURE.md §11 stage 0"], "PRD, architecture, use-case register, network policy, approval matrix and delivery protocol are consolidated and the owner decisions they depend on are recorded.", "Documents in docs/genesis with owner decisions recorded in DECISIONS.md", "Documents exist and are current", "checkpoint", ["docs/genesis/PRD.md", "docs/genesis/TARGET_ARCHITECTURE.md", "docs/genesis/DECISIONS.md"], source="roadmap"),
        _criterion("S1-01", 1, "Baseline audit and design", ["TARGET_ARCHITECTURE.md §11 stage 1"], "Code and data audited and classified; scenarios mapped to code, interfaces, data flows, tests and migration.", "Baseline audit record", "Audit document exists", "full", ["docs/genesis/STAGE-3-BASELINE-AUDIT.md"], source="roadmap"),
        _criterion("S2-01", 2, "Foundation contracts (Stage 2)", ["TARGET_ARCHITECTURE.md §11 stage 2", "docs/genesis/STAGE-2-WORK-PACKAGE.md"], "Stage 2 accepted at its exact code head by the architect.", "Exact-head acceptance verdict and CI", "Implemented with exact-head CI", "full", ["PR #8 description: accepted at 58210223398a5715b618d1163397104efd358d49 (verdict link to be attached)"], source="roadmap"),
    ]  # fmt: skip


def stage_3() -> list[dict]:
    text = (ROOT / "core" / "docs" / "STAGE3_ACCEPTANCE.md").read_text(encoding="utf-8")
    out = []
    for cells in _rows(text):
        if not re.fullmatch(r"\d+", cells[0]):
            continue
        n, status = int(cells[0]), _clean(cells[-1], 300)
        state = "checkpoint" if status.startswith("MET-L") else "none"
        out.append(_criterion(f"S3-C{n:02d}", 3, cells[1], ["STAGE-3-EXECUTION-PLAN.md §5", f"STAGE3_ACCEPTANCE.md criterion {n}"],
            f"Criterion {n} met on the candidate build with its listed tests passing and its final-stage portion (if any) passed; no open limitation: {status}",
            "Exact-head CI for the listed tests; target-Mac evidence where the criterion names it", "MET-L: met locally with synthetic data and its tests passing", state, [f"core/docs/STAGE3_ACCEPTANCE.md criterion {n}: {status[:120]}"], source="stage3"))  # fmt: skip
    for gate, title in (
        ("F-4", "Selected-model injection resistance"),
        ("F-11", "Owner-Mac sandbox, real-Internet egress, owner decision on public search"),
        ("F-12", "Real-model and target-hardware performance against accepted thresholds"),
        ("F-13", "Human UI/accessibility walkthrough, real TCC, real Mail, signing and notarisation, self-contained install"),
    ):
        out.append(_criterion(f"S3-{gate.replace('-', '')}", 3, title, ["STAGE3_ACCEPTANCE.md final-stage gates", "STAGE-3-EXECUTION-PLAN.md §12.10"], f"Final gate {gate} passed on the target Mac with the owner's evidence.", "Target-Mac or owner evidence", "None defined: scored 0 or 1", "none", [], source="stage3"))  # fmt: skip
    return out


def stages_4_to_8() -> list[dict]:
    text = (ROOT / "core" / "docs" / "STAGES_4_TO_8.md").read_text(encoding="utf-8")
    out = []
    for number, body in zip(*[iter(re.split(r"^## Stage (\d)", text, flags=re.M)[1:])] * 2, strict=False):
        active, k = False, 0
        for line in body.splitlines():
            if line.startswith("| Exit evidence"):
                active = True
                continue
            if not line.startswith("|"):
                active = False
                continue
            if not active or set(line.strip()) <= set("|-: "):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            status = _clean(cells[1], 120)
            if status.upper().startswith("NEVER"):
                continue  # deliberately never offered (destructive migration): a scope guard, not a deliverable
            k += 1
            state = "checkpoint" if status.upper().startswith("MET-L") else "none"
            out.append(_criterion(f"S{number}-X{k:02d}", int(number), cells[0], [f"TARGET_ARCHITECTURE.md §11 stage {number}", "core/docs/STAGES_4_TO_8.md"], f"Exit evidence met on the target Mac (not only synthetic) and accepted: {cells[0]}", "Exact-head CI for the listed tests plus target or owner evidence", "MET-L: met locally with synthetic data, tests listed and passing (implementer's report, not architect-reviewed)", state, [f"core/docs/STAGES_4_TO_8.md stage {number}: {status}"], source="stages4to8"))  # fmt: skip
    return out


def conformance(path: Path, prefix: str, source: str) -> list[dict]:
    out, section, k = [], "0", 0
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## (\d+[A-Z]?)\.", line)
        if m:
            section, k = m.group(1), 0
        if not line.startswith("|") or set(line.strip()) <= set("|-: "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[1].lower() == "status":
            continue
        gap = cells[3] if len(cells) > 3 else cells[2]
        status = _clean(cells[1], 80).upper()
        uc = re.match(r"(UC-[A-Z]*-?\d+[A-Z]?)", cells[0])
        k += 1
        cid = uc.group(1) if uc else f"{prefix}-{section}-{k:02d}"
        full = status.startswith("ALIGNED")
        checkpoint = status.startswith("IMPLEMENTED")
        state = "full" if full else "checkpoint" if checkpoint else "none" if re.match(r"(PARTIAL|NOT IMPLEMENTED|DEFERRED|UNVERIFIED)", status) else "unknown"
        out.append(_criterion(cid, None, cells[0], [f"{path.name} §{section}"], f"Met as specified on the candidate build with no open gap. Open gap: {gap}", f"The evidence named in {path.name} for this row, passing on the exact head, plus owner acceptance where the gap names it", "IMPLEMENTED in the conformance matrix with its listed tests (an open gap may remain)", state, [f"{path.name}: {status}; {_clean(cells[2], 160)}"], source=source))  # fmt: skip
    return out


def first_mac() -> list[dict]:
    text = (ROOT / "core" / "docs" / "FIRST_MAC_CHECKS_95f67f4.md").read_text(encoding="utf-8")
    rows = [r for r in _rows(text) if len(r) == 4 and r[1] in ("0", "0.5", "1")]
    out = []
    for k, (check, impl, review, note) in enumerate(rows, 1):
        state = {"1": "full", "0.5": "checkpoint", "0": "none"}[impl]
        c = _criterion(f"MAC-{k:02d}", 3, check, ["First Mac release checks, PR #8 comment 7226311601"], f"{check}: scoped acceptance criteria pass with evidence. Remaining: {note}", "Exact-head CI or Mac evidence named in the check", "Implementation exists; criteria or evidence incomplete (the architect's 0.5 state)", state, [f"Architect score at 95f67f4: implementation {impl}, review {review}"], milestone="first-mac", source="first-mac")  # fmt: skip
        if review == "1":
            failing = any(w in note.lower() for w in ("failed", "failure", "remain", "fix it"))
            c["review"] = {"verdict": "fail" if failing or state != "full" else "pass", "revision": BASE_REVISION, "link": MAC_REVIEW}
        out.append(c)
    return out


def main() -> int:
    if OUT.exists() and "--force" not in sys.argv:
        print(f"{OUT} exists: edit it, or pass --force to rebuild v0.1", file=sys.stderr)
        return 1
    criteria = stages_0_to_2() + stage_3() + stages_4_to_8()
    criteria += conformance(ROOT / "docs" / "genesis" / "PRD_CONFORMANCE.md", "PRD", "prd")
    criteria += conformance(ROOT / "docs" / "genesis" / "USE_CASE_CONFORMANCE.md", "UCX", "use-case")
    criteria += first_mac()
    seen: dict[str, int] = {}
    for c in criteria:  # a row whose ID repeats keeps a stable, distinct ID: the second is <id>.2, and so on
        seen[c["id"]] = seen.get(c["id"], 0) + 1
        if seen[c["id"]] > 1:
            c["id"] = f"{c['id']}.{seen[c['id']]}"
    register = {
        "version": "0.1",
        "status": "proposed by Claude; inventory to be checked and confirmed by Codex by SHA before an agreed baseline is published",
        "base_revision": BASE_REVISION,
        "rules": "PR #8 comment 7226542434 (shared acceptance and scoring rules)",
        "scoring": {"full": 1.0, "checkpoint": 0.5, "none": 0.0},
        "criteria": criteria,
    }
    OUT.write_text(json.dumps(register, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(criteria)} criteria to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
