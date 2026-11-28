#!/usr/bin/env python3
"""Build the Atlas final-product acceptance register (core/docs/acceptance_register.json), version 0.2.

v0.2 answers the architect's review of v0.1 (PR #8 comment 7226745827) under the agreed schedule rules (comment 7226926847):
* one canonical ID per distinct acceptance decision, with a published crosswalk (`aliases`), and aggregates / scope boundaries scored nowhere;
* physical-device-only checks kept visible as `out-device` and excluded from both scores; mixed criteria split into software and device parts;
* full pass conditions (no truncation) with a precise source reference;
* credit only from structured, revision-specific evidence (exact tests, the exact-head CI job, or an explicit linked carry-forward);
  a conformance-matrix status or a score citation alone earns nothing;
* historical verdicts linked to their exact commits; review batches carried over from the previous version.

It reads the sources in the repository plus the previous register (for `review_batches`) and rewrites the register.
"""

# ruff: noqa: PLR2004, C408, S106  (fixed table shapes; keyword-built records; "pass_condition" is not a password)
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "core" / "docs" / "acceptance_register.json"
CI_REVISION = "d528055ec8756d8d55efe2f104cfe929c7bf8cb1"  # the scored software revision: the reviewed head whose hosted CI is cited below
CI_RUN = "https://github.com/Prasanna666666/Prasanna/actions/runs/46113892127"
JOBS = {
    "core-3.11": f"{CI_RUN}/job/140883255575", "core-3.13": f"{CI_RUN}/job/140883255649", "kit": f"{CI_RUN}/job/140883255527",
    "macos": f"{CI_RUN}/job/140883255653", "app": f"{CI_RUN}/job/140883255744", "ios": f"{CI_RUN}/job/140883255380",
}  # fmt: skip
MAC_REVIEW = ("95f67f41fd1a028336813ccd90383fb3c9cdde97", "https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6092414795", "6092414795")
V03_REVIEW = ("2815257f391f5fffa6168ac1ff00bca41a8bc1dc", "https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6093596586", "6093596586")
V04_REVIEW = ("6574c2cb8dd23c9d1a3a7084c6aa1e207756900c", "https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6094252873", "6094252873")
V05_REVIEW = ("e23b04bff48c2c3d79976b50921f86d91a3c46ce", "https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6094872675", "6094872675")
V06_REVIEW = ("a3c7f7d009ff70d7feda917d5d4a3ea9dc030e71", "https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6095269004", "6095269004")
V07_REVIEW = ("09498515beefed3e90feac0e201722822df4a6f5", "https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6095905696", "6095905696")
V08_REVIEW = ("d528055ec8756d8d55efe2f104cfe929c7bf8cb1", "https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6096381812", "6096381812")
V02_REVIEW = ("8b23cc66705a5b3c5eddac657cf774fa35a43594", "https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6093128990", "6093128990")
OWNERS = {"implementation": "Claude", "verdict": "Codex", "sign_off": "Owner"}
NO_CHECKPOINT = "None defined: scored 0 or 1"


def _rows(text: str) -> list[list[str]]:
    return [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in text.splitlines() if ln.startswith("|") and not set(ln.strip()) <= set("|-: ")]


def _plain(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[*`]", "", s)).strip()


def ci(job: str, what: str = "") -> dict:
    return {
        "kind": "ci",
        "revision": CI_REVISION,
        "ref": f"hosted {job} job{(': ' + what) if what else ''}",
        "link": JOBS[job],
        "environment": "GitHub-hosted runner",
    }


def test(path: str, name: str) -> dict:
    return {"kind": "test", "revision": CI_REVISION, "ref": f"{path}::{name}"}


def crit(cid: str, stage, title: str, source_ref: str, pass_condition: str, evidence_required: str, checkpoint: str = NO_CHECKPOINT, **kw) -> dict:
    c = {
        "id": cid, "stage": stage, "title": _plain(title), "source": kw.pop("source"), "source_ref": source_ref, "refs": kw.pop("refs", [source_ref]),
        "owners": OWNERS, "mandatory": kw.pop("mandatory", True), "scope": kw.pop("scope", "in"), "milestones": kw.pop("milestones", []),
        "aliases": kw.pop("aliases", []), "pass_condition": _plain(pass_condition), "required_evidence": _plain(evidence_required), "checkpoint": _plain(checkpoint),
        "implementation": {"state": (state := kw.pop("state", "none")), "evidence": [{**e, "proves": state} for e in kw.pop("evidence", [])]},
        "review": kw.pop("review", {"verdict": None}),
    }  # fmt: skip
    c.update(kw)
    return c


def _tests_in(cell: str) -> list[dict]:
    """Exact test references named in a source cell: `test_x.py::test_y`; a bare `::test_y` (the file found by searching core/tests); and a
    whole file named alone (`test_x.py`), meaning every test in it, as the stage document states for such rows."""
    found = list(re.findall(r"(?:tests/)?(test_\w+\.py)::(test_\w+)", cell))
    for name in re.findall(r"(?<![\w.])::(test_\w+)", cell):
        owner = [f.name for f in sorted((ROOT / "core" / "tests").glob("test_*.py")) if re.search(rf"^def {name}\b", f.read_text(encoding="utf-8"), re.M)]
        found += [(owner[0], name)] if owner else []
    for file in re.findall(r"`(test_\w+\.py)`", cell):
        path = ROOT / "core" / "tests" / file
        if path.exists():
            found += [(file, n) for n in re.findall(r"^def (test_\w+)", path.read_text(encoding="utf-8"), re.M)]
    return [test(f"core/tests/{f}", n) for f, n in dict.fromkeys(found)]


def stages_0_to_2() -> list[dict]:
    doc = {"kind": "doc", "revision": CI_REVISION}
    return [
        crit("S0-01", 0, "Product specification consolidated", "TARGET_ARCHITECTURE.md §11, stage 0", "PRD, architecture, use-case register, network policy, approval matrix and delivery protocol are consolidated and every owner decision they depend on is recorded as answered in DECISIONS.md.", "The documents at the candidate revision; DECISIONS.md with no open owner decision the stage depends on", "The specification documents exist at the candidate revision (owner decisions may remain open)", source="roadmap", deliverable="document", state="checkpoint", evidence=[{**doc, "ref": "docs/genesis/PRD.md, TARGET_ARCHITECTURE.md, USE_CASE_REGISTER.md, INTERNET_AND_NETWORK_POLICY.md, DELIVERY_PROTOCOL.md"}]),
        crit("S1-01", 1, "Baseline audit and design", "TARGET_ARCHITECTURE.md §11, stage 1", "Code and data audited and classified (reuse / reference-only / discard); scenarios mapped to code, interfaces, data flows, tests and migration.", "The baseline audit document at the candidate revision", source="roadmap", deliverable="document", state="full", evidence=[{**doc, "ref": "docs/genesis/STAGE-3-BASELINE-AUDIT.md"}]),
        crit("S2-01", 2, "Foundation contracts (Stage 2), portable engineering scope", "TARGET_ARCHITECTURE.md §11, stage 2; docs/genesis/STAGE-2-WORK-PACKAGE.md", "Stage 2 accepted by the architect at its exact code head for its portable engineering scope, with exact-head CI green; the proof that carries forward to the candidate is the unchanged Stage 2 test suite passing on the candidate's hosted Core jobs.", "The historical exact-head acceptance verdict and the candidate's hosted Core CI", source="roadmap", state="full",
             evidence=[{"kind": "carry_forward", "revision": CI_REVISION, "from_revision": "58210223398a5715b618d1163397104efd358d49", "ref": "Stage 2 accepted at 5821022 (22/22 CI); its tests run unchanged in the candidate's core jobs", "link": "https://github.com/Prasanna666666/Prasanna/pull/8#issuecomment-7047659436"}, ci("core-3.11"), ci("core-3.13")],
             review={"verdict": "pass", "revision": "58210223398a5715b618d1163397104efd358d49", "link": "https://github.com/Prasanna666666/Prasanna/pull/8#issuecomment-7047659436", "reviewer": "architect", "review_id": "7047659436", "historical": True}),
        crit("S2-01-DEV", 2, "Stage 2 target-Mac provisions", "Architect review 7226745827 (Stage 2 target-Mac provisions kept separate)", "Stage 2's target-Mac provisions verified on the owner's Mac.", "Owner-Mac evidence", source="roadmap", scope="out-device"),
    ]  # fmt: skip


def stage_3() -> list[dict]:
    text = (ROOT / "core" / "docs" / "STAGE3_ACCEPTANCE.md").read_text(encoding="utf-8")
    out = []
    for cells in _rows(text):
        if not re.fullmatch(r"\d+", cells[0]):
            continue
        n, status = int(cells[0]), _plain(cells[-1])
        tests = _tests_in(cells[3])  # columns: number, criterion, implementation, tests, evidence, status
        state = "checkpoint" if status.startswith("MET-L") and tests else "none"
        c = crit(f"S3-C{n:02d}", 3, cells[1], f"core/docs/STAGE3_ACCEPTANCE.md, criterion {n}; STAGE-3-EXECUTION-PLAN.md §5",
                 f"Criterion {n} ({_plain(cells[1])}) is met on the candidate build: every test listed for it at the source reference passes in the candidate's hosted Core CI, and the limitation recorded there is closed.",
                 "The listed tests passing in the candidate's hosted Core CI; target or owner evidence for any final-stage portion",
                 "MET-L: met locally with synthetic data; every test listed for the criterion passes in the candidate's hosted Core CI",
                 source="stage3", state=state, evidence=[*tests, ci("core-3.11"), ci("core-3.13")] if state != "none" else [], recorded_status=status, listed_tests=tests)  # fmt: skip
        out.append(c)
    by = {c["id"]: c for c in out}
    by["S3-C06"]["review"] = {"verdict": "pass", "revision": "14b471bf589303cf25f5d781f8aaf62b0f5654e0", "link": "https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6014101078", "reviewer": "architect", "review_id": "6014101078", "historical": True, "scope_note": "MET-L for the exact-read attachment restriction only; the broader criterion and final Mac evidence stay open"}  # fmt: skip
    by["S3-C02"].update(scope="aggregate", composed_of=["MAC-11", "MAC-12", "MAC-13", "MAC-15", "S3-C02-TASK"])
    out.append(crit("S3-C02-TASK", 3, "Revocation before every read on the task path and at the model boundary", "core/docs/STAGE3_ACCEPTANCE.md, criterion 2 (task-path portion)", "A grant withdrawn before retrieval, between retrieval and the model, or after an answer is drafted stops the task, purges derived content and is never delivered.", "Exact tests for each boundary passing in hosted Core CI", "MET-L: task-path revocation tests pass in hosted Core CI", source="stage3",
                    state="checkpoint", evidence=[test("core/tests/test_review_fixes.py", "test_an_answer_and_its_stream_are_withheld_once_a_source_it_cites_is_revoked"), test("core/tests/test_review_fixes.py", "test_a_grant_revoked_while_another_stays_fails_closed_on_resume"), ci("core-3.11"), ci("core-3.13")]))  # fmt: skip
    by["S3-C14"]["aliases"] = ["MAC-01"]
    by["S3-C14"]["milestones"] = ["first-mac"]
    gates = [
        ("S3-F4", "Selected-model injection resistance (F-4)", "Injection fixtures pass against the selected production model, run in a supported test environment.", "in"),
        ("S3-F11-SW", "Least-privilege sandbox, real-Internet egress and public-search guardrails (F-11, software part)", "The worker sandbox profile is least-privilege (deny by default) and verified on a hosted macOS runner; the egress gateway is exercised against the real Internet under the off-by-default gates, with the open residuals closed; public search stays behind its two off-by-default gates. Whether to enable it is the owner decision DEC-PUBLIC-SEARCH, not a criterion.", "in"),
        ("S3-F11-DEV", "Sandbox verification on the owner's Mac (F-11, device part)", "The worker sandbox is verified on the owner's Mac.", "out-device"),
        ("S3-F12-SW", "Selected-model quality thresholds (F-12, software part)", "Answer and retrieval quality of the selected model meet accepted thresholds, measured independently of hardware.", "in"),
        ("S3-F12-DEV", "Target-hardware performance and memory (F-12, device part)", "Latency, memory and thermal thresholds met on the target Mac.", "out-device"),
        ("S3-F13-SW", "Self-contained install and signed release build (F-13, software part)", "The app bundles its Python and model install, builds, launches and stops its Core in hosted CI, and a signed, notarised build is produced by the release pipeline.", "in"),
        ("S3-F13-DEV", "Human walkthrough, real TCC prompts and real Apple Mail on a Mac (F-13, device part)", "Owner walkthrough, real TCC prompts and the real Mail store verified on a Mac.", "out-device"),
    ]  # fmt: skip
    for gid, title, cond, scope in gates:
        out.append(
            crit(
                gid,
                3,
                title,
                "core/docs/STAGE3_ACCEPTANCE.md, final-stage gates; STAGE-3-EXECUTION-PLAN.md §12.10",
                cond,
                "Hosted CI or supported test-environment evidence (software part); owner-Mac evidence (device part)",
                source="stage3",
                scope=scope,
            )
        )
    return out


DEVICE_ROW = re.compile(r"Target-Mac|FileVault|physical", re.I)


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
            status = _plain(cells[1])
            if status.upper().startswith("NEVER"):
                continue
            k += 1
            cid, title = f"S{number}-X{k:02d}", _plain(cells[0])
            ref = f"core/docs/STAGES_4_TO_8.md, stage {number} row {k}"
            base = dict(source="stages4to8", refs=[f"TARGET_ARCHITECTURE.md §11, stage {number}", "core/docs/STAGES_4_TO_8.md"])
            if DEVICE_ROW.search(title):
                out.append(
                    crit(
                        f"{cid}-SW",
                        int(number),
                        f"{title} (software part)",
                        ref,
                        f"The software-verifiable part of: {title}; update-restart and crash recovery exercised in a supported test environment.",
                        "Hosted or supported-environment tests",
                        **base,
                    )
                )
                out.append(
                    crit(
                        f"{cid}-DEV",
                        int(number),
                        f"{title} (device part)",
                        ref,
                        f"The device part of: {title}.",
                        "Owner-Mac evidence",
                        scope="out-device",
                        **base,
                    )
                )
                continue
            tests = _tests_in(cells[2] if len(cells) > 2 else "")
            state = "checkpoint" if status.upper().startswith("MET-L") and tests else "none"
            out.append(crit(cid, int(number), title, ref, f"The exit evidence at the source reference is met on the candidate build and accepted: {title}.", "The listed tests passing in hosted CI, plus the target evidence the row names",
                            "MET-L: every test listed for the row passes in the candidate's hosted Core CI (implementer's report, not architect-reviewed)", state=state, evidence=[*tests, ci("core-3.11"), ci("core-3.13")] if state != "none" else [], recorded_status=status, **base))  # fmt: skip
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
        status = _plain(cells[1]).upper()
        uc = re.match(r"(UC-[A-Z]*-?\d+[A-Z]?)", cells[0])
        k += 1
        cid = uc.group(1) if uc else f"{prefix}-{section}-{k:02d}"
        tests = _tests_in(cells[2])
        scope = "boundary" if status.startswith("ALIGNED") else "in"
        state = "checkpoint" if status.startswith("IMPLEMENTED") and tests else "none"
        out.append(crit(cid, None, cells[0], f"{path.relative_to(ROOT)}, §{section} row {k}", "The requirement at the source reference is met as specified on the candidate build, and the open gap recorded there is closed.",
                        "Exact tests or behaviour evidence for the requirement passing on the exact head, plus owner acceptance where the gap names it",
                        "IMPLEMENTED in the conformance matrix and every exact test it names passes in hosted Core CI (an open gap may remain)", source=source, scope=scope, state=state,
                        evidence=[*tests, ci("core-3.11"), ci("core-3.13")] if state != "none" else [], recorded_status=status, open_gap=_plain(gap)))  # fmt: skip
    return out


def _mac_verdict(v: str) -> dict:
    rev, link, rid = MAC_REVIEW
    return {"verdict": v, "revision": rev, "link": link, "reviewer": "architect", "review_id": rid}


def first_mac() -> list[dict]:
    """The architect's first-Mac release checks as canonical register criteria (MAC-01 is an alias of S3-C14)."""
    m, src, v = ["first-mac"], "core/docs/FIRST_MAC_CHECKS_95f67f4.md (PR #8 comment 7226311601)", _mac_verdict
    core = [ci("core-3.11"), ci("core-3.13")]
    return [
        crit("MAC-02", 3, "Design and security standards", src, "Every recorded privacy, recovery and usability decision is closed or explicitly disposed of.", "Decision records", source="first-mac", scope="aggregate", milestones=m, composed_of=["MAC-13", "MAC-14", "MAC-15", "MAC-17", "MAC-18"]),
        crit("MAC-03", 3, "Release stages and acceptance criteria", src, "The stage checklist and required evidence are reconciled against the product scope.", "This register, confirmed by Codex", source="first-mac", scope="aggregate", milestones=m, composed_of=["register"]),
        crit("MAC-04", 3, "Build, lint, types and supported platforms", src, "Exact-head hosted builds and static checks pass on every covered platform.", "Exact-head hosted CI", source="first-mac", milestones=m, state="full", evidence=[ci("core-3.11", "ruff, mypy, tests"), ci("core-3.13", "ruff, mypy, tests"), ci("kit"), ci("macos", "swift build and tests"), ci("app", "build and launch"), ci("ios", "simulator build")], review=v("pass")),
        crit("MAC-05", 3, "Line-by-line and function-by-function review coverage", src, "Release-wide reviewed file, line and function coverage is recorded against the git-tracked inventory.", "review_batches with reviewed ranges and functions", source="first-mac", scope="aggregate", milestones=m, composed_of=["review_batches"], note="A supporting measure, not a product criterion: no partial credit."),
        crit("MAC-06", 3, "Hosted CI release checks", src, "All hosted CI jobs pass at the exact head.", "Exact-head hosted CI, every job", source="first-mac", milestones=m, review=v("fail")),
        crit("MAC-07", 3, "CI failure and artifact safety", src, "A failing test fails the job with its report preserved, and a log that fails the privacy scan is never published; both shown in hosted CI.", "Hosted runs of a failing-test case and a rejected-artifact case", "The workflow records the test status, scans before upload and fails the job afterwards, and its pass path runs in hosted Core CI", source="first-mac", milestones=m, state="checkpoint", evidence=[{"kind": "commit", "revision": CI_REVISION, "ref": ".github/workflows/ci.yml core job: record status, scan, gated upload, final fail step"}, *core]),
        crit("MAC-08", 3, "Mac onboarding accessibility (hosted audit)", src, "The hosted Mac UI accessibility audit passes on the first screen, including contrast, with the audit-time appearance recorded.", "Exact-head mac-ui job passing", source="first-mac", milestones=m, review=v("fail")),
        crit("MAC-09", 3, "First-run consent and usability", src, "Owner-facing onboarding and permission behaviour verified end to end in a supported test environment.", "Hosted UI test of the Get Started flow", source="first-mac", milestones=m),
        crit("MAC-10", 3, "Paired-phone revocation and tested cache wipe", src, "A revoked phone is recognised on its next contact, unpaired, and its tested cache and queue erased, against the real Core.", "Real-Core Swift test on the hosted macOS runner; Core socket test", source="first-mac", milestones=m, state="full", evidence=[{"kind": "test", "revision": CI_REVISION, "ref": "app/Tests/AtlasKitTests/PhoneTests.swift::testAPhonePairsReadsOfflineSyncsHandlesAConflictAndIsWipedWhenRevoked"}, test("core/tests/test_operations_api.py", "test_a_device_pairs_over_the_socket_checks_the_core_syncs_and_is_revoked_for_good"), ci("macos"), ci("core-3.13")], review=v("pass")),
        crit("MAC-11", 3, "Library final grant check", src, "A grant withdrawn during a Library search, up to the last material read, removes that source's results before delivery; paired devices get the device source ceiling.", "Exact Core tests in hosted CI", source="first-mac", milestones=m, state="full", evidence=[test("core/tests/test_api.py", "test_a_grant_withdrawn_at_the_last_read_before_delivery_still_removes_the_result"), test("core/tests/test_api.py", "test_library_applies_the_same_device_source_ceiling_as_a_question_and_the_owner_is_unaffected"), *core], review=v("pass")),
        crit("MAC-12", 3, "Citation text permission at delivery", src, "Citation text whose grant is withdrawn during the read is not delivered.", "Exact Core test in hosted CI", source="first-mac", milestones=m, state="full", evidence=[test("core/tests/test_api.py", "test_a_citation_text_is_not_delivered_when_the_grant_is_withdrawn_while_it_is_being_read"), *core], review=v("pass")),
        crit("MAC-13", 3, "Live-stream device and shutdown checks", src, "Over the signed socket: an idle stream of a revoked or narrowed device closes, no final payload arrives when revocation happens during preparation, a still-entitled device keeps receiving, and streams end on shutdown.", "Signed end-to-end socket tests in hosted Core CI", "Iterator-level tests for idle revocation, ceiling narrowing, revocation during final preparation and shutdown pass in hosted Core CI", source="first-mac", milestones=m, state="checkpoint",
             evidence=[test("core/tests/test_api.py", "test_an_idle_stream_of_a_paired_device_ends_when_the_device_is_revoked"), test("core/tests/test_api.py", "test_an_idle_stream_ends_when_the_device_source_ceiling_no_longer_covers_the_task"), test("core/tests/test_api.py", "test_a_device_revoked_while_the_final_event_is_being_prepared_receives_nothing"), test("core/tests/test_api.py", "test_a_stream_already_suspended_in_delivery_ends_when_the_core_begins_to_close"), *core]),
        crit("MAC-14", 3, "Search coverage privacy and accuracy", src, "No delivered answer or queued final event carries counts from a withdrawn source, and suppressed coverage never reports indexing done after the question as searched.", "Exact Core tests, including a queued-final-event withdrawal and a post-answer index change", "Coverage of a withdrawn source is rebuilt as partial with an unknown total for the ordinary 1.1 answer (test passes in hosted Core CI)", source="first-mac", milestones=m, state="checkpoint", evidence=[test("core/tests/test_api.py", "test_coverage_counts_of_a_withdrawn_source_that_cited_nothing_are_not_delivered_in_a_1_1_answer_or_stream"), *core], review=v("fail")),
        crit("MAC-15", 3, "Finance and Health final permission checks", src, "Summaries recheck the domain grant at delivery, and a withdrawal during preparation withholds the summary.", "Exact Core tests", source="first-mac", milestones=m),
        crit("MAC-16", 3, "Startup ownership and lock release", src, "The data-folder lock is taken before any key is provisioned or store opened, stays stable across refused starts, and is released on every refusal path.", "Exact launcher tests in hosted Core CI", source="first-mac", milestones=m, state="full", evidence=[test("core/tests/test_launcher.py", "test_concurrent_starts_across_a_keychain_refusal_never_have_two_contenders_in_the_factory"), test("core/tests/test_launcher.py", "test_an_unexpected_factory_failure_releases_the_folder_lock"), test("core/tests/test_launcher.py", "test_a_start_that_cannot_own_the_data_folder_provisions_no_keys_and_opens_no_store"), *core], review=v("pass")),
        crit("MAC-17", 3, "Keychain provisioning and staged restore", src, "First provisioning never overwrites an existing key, and an interrupted restore leaves a working installation; verified in a supported test environment.", "Exact tests, including an interrupted-restore case", "Add-only first provisioning passes its synthetic concurrent-start tests in hosted Core CI", source="first-mac", milestones=m, state="checkpoint", evidence=[test("core/tests/test_macos.py", "test_first_provisioning_never_overwrites_a_key_a_competing_start_added_in_between"), *core]),
        crit("MAC-18", 3, "Shutdown and restart", src, "Close drains active work before stores close, keeps ownership when work is still live, and a forced process exit is followed by a clean restart.", "Exact tests including a process-level forced exit and restart", "In-process drain, lock retention and reacquisition tests pass in hosted Core CI", source="first-mac", milestones=m, state="checkpoint", evidence=[test("core/tests/test_app.py", "test_close_keeps_the_stores_and_the_lock_while_a_request_could_still_be_using_them"), test("core/tests/test_app.py", "test_work_admitted_but_not_yet_running_is_counted_by_the_drain"), *core]),
        crit("MAC-19", 3, "Documents and Mail workflow (software part)", src, "With sample Documents and Mail in a supported test environment: an older message is found, two invoice versions are compared, and exact evidence is cited.", "An end-to-end test against the real Core with synthetic sources", source="first-mac", milestones=m),
        crit("MAC-19-DEV", 3, "Documents and Mail workflow on the owner's Mac (device part)", src, "The same workflow run on the owner's Mac with real Apple Mail.", "Owner-Mac evidence", source="first-mac", scope="out-device", milestones=m),
        crit("MAC-20", 3, "Result UX, cancellation and withdrawal", src, "Truthful incomplete-search wording, Stop shows Cancelled durably, and withdrawing access clears affected displayed results.", "Hosted Swift tests of the app model", source="first-mac", milestones=m),
    ]  # fmt: skip


CHANGES = [
    "v0.1 -> v0.2: MAC-01 is an alias of S3-C14 (traceability). MAC-02, MAC-03, MAC-05 and S3-C02 are aggregates (S3-C02 = MAC-11, MAC-12, MAC-13, MAC-15 and the new S3-C02-TASK). PRD ALIGNED rows are scope boundaries.",
    "Physical-device parts split out and excluded: S2-01-DEV, S3-F11-DEV, S3-F12-DEV, S3-F13-DEV, MAC-19-DEV and the device part of the Stage 7 target-Mac row. S3-F11, S3-F12 and S3-F13 are split into software and device parts; S3-F4 is wholly software.",
    "Pass conditions are complete with a precise source reference. Credit only from structured, revision-specific evidence: a conformance status or a score citation alone earns nothing, so PRD, use-case and stage rows that name no exact test lose their v0.1 checkpoint credit.",
    "Historical verdicts linked to exact commits: Stage 2 at 5821022 (comment 7047659436), Stage 3 criterion 6 at 14b471bf (review 6014101078, scoped).",
    "Not yet reconciled in v0.2: overlaps between PRD rows, use cases and Stage 4-8 rows beyond the MAC and Stage 3 mapping above. They keep separate IDs until mapped.",
]


V03_CHANGES = [
    "v0.2 -> v0.3 (architect review 6093128990): Stop/Cancelled is one canonical criterion, UC-009; MAC-20 keeps incomplete-search wording and clearing results on withdrawal; S3-C13 is an aggregate of S3-C13-REF (new), UC-009, MAC-09, MAC-19 and MAC-20.",
    "UC-011 (revoked or unavailable source) is an alias of the S3-C02 aggregate. Signing: S7-X04 is canonical; S3-F13-SW is an aggregate of S7-X04 and S3-F13-INSTALL (new).",
    "S3-C06-EXACTREAD (new) carries the scoped historical criterion-6 verdict at 14b471bf; the broader S3-C06 review is pending as recorded at 8b23cc6. S2-01's verdict carries forward explicitly, for its original scope only.",
    "The owner's public-search decision moved out of S3-F11-DEV into the decision record DEC-PUBLIC-SEARCH; its guardrails stay scored in S3-F11-SW. Pass conditions are normative; recorded status and open gaps are separate fields.",
    "All evidence cited the scored revision 8b23cc6 and its CI run 46061223577; MAC-13 and MAC-14 were reopened because that batch changed the delivery code their evidence covered. Verdicts at 8b23cc6 mirrored: MAC-06 fail, MAC-08 fail, S3-C06 pending.",
    "v0.3 agreed as the reporting baseline (review 6093596586, comment 7228002976). Scored revision moved to 2815257 and its PR CI run 46068853988. Verdicts at 2815257 mirrored: MAC-14 pass, MAC-18 pass, MAC-13 pending (checkpoint verified), MAC-15 fail, MAC-06 fail, MAC-08 fail.",
    "Scored revision moved to 6574c2c and its PR CI run 46078831844. Verdicts at 6574c2c (review 6094252873) mirrored: MAC-13 pass, MAC-15 pass, MAC-19 pass, MAC-17 fail (add-only checkpoint kept), MAC-06 fail, MAC-08 fail.",
    "Scored revision moved to e23b04b and its PR CI run 46086267907. Verdicts at e23b04b (review 6094872675) mirrored: MAC-17 fail (ownership across data folders; add-only checkpoint kept), MAC-08 fail (investigate the Disabled window state first), MAC-06 fail.",
    "Scored revision moved to a3c7f7d and its PR CI run 46095345457. Verdicts at a3c7f7d (review 6095269004) mirrored: MAC-17 fail (serialize recovery with live restore, enforce ownership at startup, preserve data on an unconfirmed commit point; account-wide design accepted), MAC-08 fail (make the window key first), MAC-06 fail.",
    "Scored revision moved to 0949851 and its PR CI run 46105400530. Verdicts at 0949851 (review 6095905696) mirrored: MAC-17 fail (key layer fixed; the startup store-open window and restore copy/activation need one ordering), MAC-08 fail (choose (i): system-background comparison and a probe in the same foreground state), MAC-06 fail.",
    "Scored revision moved to d528055 and its PR CI run 46113892127. Verdicts at d528055 (review 6096381812) mirrored: MAC-17 fail (failure cleanup can unlink a held lock pathname), MAC-08 fail (proceed with the Dark bisect and a second hosted configuration for Light), MAC-06 fail.",
]


def _verdict(review: tuple[str, str, str], verdict: str, **extra) -> dict:
    rev, link, rid = review
    return {"verdict": verdict, "revision": rev, "link": link, "reviewer": "architect", "review_id": rid, **extra}


def apply_v03(criteria: list[dict]) -> list[dict]:
    """v0.2 -> v0.3, from the architect's review of v0.2 (review 6093128990): crosswalk, scoped historical verdicts, mirrored verdicts,
    and criteria reopened where this batch changed the code their evidence covered."""
    by = {c["id"]: c for c in criteria}
    # Stop / Cancelled: one canonical criterion (UC-009); MAC-20 keeps the other two behaviours; S3-C13 becomes an aggregate of its parts.
    by["UC-009"].update(
        milestones=["first-mac"],
        pass_condition="Stop shows Cancelled, durably, whether it is pressed before the task ID returns, while the task runs, or after it completes; Cancelled and Expired are never shown as Failed.",
        required_evidence="Exact Core tests and hosted Swift app-model tests for each Stop timing",
    )
    by["MAC-20"].update(
        title="Result UX: incomplete-search wording and clearing results on withdrawal",
        pass_condition="Incomplete or unsearched coverage is worded truthfully in the app, and withdrawing access clears every affected displayed result and discards stale continuations; Stop/Cancelled is UC-009.",
    )
    by["S3-C13"].update(scope="aggregate", composed_of=["S3-C13-REF", "UC-009", "MAC-09", "MAC-19", "MAC-20"])
    criteria.append(crit("S3-C13-REF", 3, "One experience through the reference client: question, progress, citations, clear outcomes", "core/docs/STAGE3_ACCEPTANCE.md, criterion 13 (reference-client portion)", "Through the reference client against the real Core: a question shows progress, a final answer with resolvable citations, and a clear outcome for every closed vocabulary state.", "Exact reference-client tests passing in hosted Core CI", "MET-L: reference-client tests pass in hosted Core CI", source="stage3", milestones=["first-mac"],
                         state="checkpoint", evidence=[test("core/tests/test_client.py", "test_every_value_of_every_closed_vocabulary_has_a_message"), ci("core-3.11"), ci("core-3.13")]))  # fmt: skip
    # Revoked / unavailable source: UC-011 is the same decision as the S3-C02 aggregate.
    criteria.remove(by["UC-011"])
    by["S3-C02"]["aliases"] = ["UC-011"]
    # Signing: S7-X04 is canonical; S3-F13-SW is an aggregate of it and the install criterion.
    by["S3-F13-SW"].update(scope="aggregate", composed_of=["S7-X04", "S3-F13-INSTALL"])
    criteria.append(crit("S3-F13-INSTALL", 3, "Self-contained app install that starts and stops its Core", "core/docs/STAGE3_ACCEPTANCE.md, final gate F-13 (install portion)", "The app bundles its private Python, the Core and the selected model's install, builds, launches, starts its Core and stops it on quit, in hosted CI.", "The hosted app build-and-launch job; a bundled model install", "The app bundles its private Python and the Core, launches, starts its Core and stops it on quit in the hosted app job (a build-and-launch check, not an end-to-end behaviour test; the model install is not yet bundled)", source="stage3",
                         state="checkpoint", evidence=[ci("app", "build Atlas.app with its private Python, launch, start and stop the Core")]))  # fmt: skip
    # Exact-read attachment restriction: its own canonical criterion carries the scoped historical verdict; the broader S3-C06 is pending.
    exact = crit("S3-C06-EXACTREAD", 3, "Mail attachment bytes are never read (exact-read restriction)", "core/docs/STAGE3_ACCEPTANCE.md, criterion 6 (exact-read portion); review 6014101078", "No attachment byte is read: listing reads headers only and reading stops at the text part; a non-text part before the text makes the message unreadable.", "Exact Mail-reader tests passing in hosted Core CI", "MET-L: the exact-read tests pass in hosted Core CI", source="stage3",
                 state="checkpoint", evidence=[test("core/tests/test_macos.py", "test_not_one_attachment_byte_is_read_even_when_it_lies_within_the_same_4k_window_as_the_text"), ci("core-3.11"), ci("core-3.13")],
                 review=by["S3-C06"]["review"])  # fmt: skip
    criteria.append(exact)
    by["S3-C06"]["review"] = _verdict(V02_REVIEW, "pending", note="the broader criterion needs matching evidence; the exact-read portion is S3-C06-EXACTREAD")
    # Stage 2's historical verdict is carried forward explicitly, for its original scope only.
    by["S2-01"]["review"]["carry_forward"] = {
        "scope": "portable engineering scope only",
        "candidate_evidence": [JOBS["core-3.11"], JOBS["core-3.13"]],
        "applies_while": "the Stage 2 tests run unchanged in the candidate's Core jobs",
    }
    # Verdicts the architect recorded at 8b23cc6.
    by["MAC-06"]["review"] = _verdict(V02_REVIEW, "fail", note="one required hosted job (mac-ui) failed; security passed")
    by["MAC-08"]["review"] = _verdict(V02_REVIEW, "fail", note="hosted Mac onboarding contrast still fails")
    return apply_verdicts_2815257(criteria)


def apply_verdicts_2815257(criteria: list[dict]) -> list[dict]:
    """The architect's review of 2815257 (review 6093596586), which also agreed v0.3 as the 218-criterion reporting baseline: its explicit
    criterion verdicts, and the evidence those verdicts rest on, at the new scored revision."""
    by = {c["id"]: c for c in criteria}
    t, core = test, [ci("core-3.11"), ci("core-3.13")]

    def evidence(cid: str, state: str, items: list[dict]) -> None:
        by[cid]["implementation"] = {"state": state, "evidence": [{**e, "proves": state} for e in items]}

    evidence("MAC-14", "full", [t("core/tests/test_api.py", "test_a_queued_1_1_final_event_does_not_deliver_counts_of_a_source_withdrawn_after_the_batch_was_read"), t("core/tests/test_api.py", "test_suppressed_coverage_never_reports_indexing_done_after_the_question_as_searched"), t("core/tests/test_api.py", "test_coverage_counts_of_a_withdrawn_source_that_cited_nothing_are_not_delivered_in_a_1_1_answer_or_stream"), *core])
    evidence("MAC-18", "full", [t("core/tests/test_launcher.py", "test_a_stop_with_a_request_still_running_exits_with_status_7_and_the_next_start_succeeds"), t("core/tests/test_launcher.py", "test_a_data_folder_lock_dies_with_its_holder_so_a_crash_never_blocks_the_next_start"), t("core/tests/test_app.py", "test_close_keeps_the_stores_and_the_lock_while_a_request_could_still_be_using_them"), t("core/tests/test_app.py", "test_work_admitted_but_not_yet_running_is_counted_by_the_drain"), *core])
    evidence("MAC-13", "checkpoint", [t("core/tests/test_transport.py", "test_an_idle_signed_stream_of_a_paired_device_closes_when_the_device_is_revoked"), t("core/tests/test_transport.py", "test_an_idle_signed_stream_closes_when_the_device_source_ceiling_no_longer_covers_the_task"), t("core/tests/test_transport.py", "test_no_final_payload_reaches_a_device_revoked_while_the_final_event_is_being_prepared"), t("core/tests/test_transport.py", "test_a_still_entitled_device_keeps_receiving_its_stream_to_the_final_answer"), *core])
    by["MAC-13"]["checkpoint"] = "Signed Unix-socket tests for idle revocation, narrowed device scope, revocation during final preparation and an entitled device pass in hosted Core CI (shutdown of an open stream still proven only at the iterator level)"
    by["MAC-14"]["review"] = _verdict(V03_REVIEW, "pass")
    by["MAC-18"]["review"] = _verdict(V03_REVIEW, "pass")
    by["MAC-13"]["review"] = _verdict(V03_REVIEW, "pending", note="checkpoint verified; needs a signed socket test of an open stream closing on shutdown")
    by["MAC-15"]["review"] = _verdict(V03_REVIEW, "fail", note="revalidation happens before the calculations; a withdrawal during them can still deliver figures")
    by["MAC-06"]["review"] = _verdict(V03_REVIEW, "fail", note="one required hosted job (mac-ui) failed")
    by["MAC-08"]["review"] = _verdict(V03_REVIEW, "fail", note="onboarding paragraph contrast fails in Light and Dark")
    return apply_verdicts_6574c2c(criteria)


def apply_verdicts_6574c2c(criteria: list[dict]) -> list[dict]:
    """The architect's review of 6574c2c (review 6094252873): its explicit criterion verdicts and the evidence they rest on."""
    by = {c["id"]: c for c in criteria}
    t, core = test, [ci("core-3.11"), ci("core-3.13")]

    def evidence(cid: str, state: str, items: list[dict]) -> None:
        by[cid]["implementation"] = {"state": state, "evidence": [{**e, "proves": state} for e in items]}

    evidence("MAC-13", "full", [*[e for e in by["MAC-13"]["implementation"]["evidence"] if e["kind"] == "test"], t("core/tests/test_transport.py", "test_an_already_open_signed_stream_closes_when_the_core_begins_to_shut_down"), *core])
    evidence("MAC-15", "full", [t("core/tests/test_domains.py", "test_a_summary_is_withheld_when_its_domain_is_withdrawn_while_the_records_are_being_read"), t("core/tests/test_domains.py", "test_a_summary_is_withheld_when_its_domain_is_withdrawn_during_the_calculation"), *core])
    evidence("MAC-19", "full", [t("core/tests/test_app.py", "test_the_first_documents_and_mail_workflow_works_end_to_end_with_exact_evidence"), *core])
    for cid in ("MAC-13", "MAC-15", "MAC-19"):
        by[cid]["review"] = _verdict(V04_REVIEW, "pass")
    by["MAC-17"]["review"] = _verdict(V04_REVIEW, "fail", note="a failing rollback or a killed process can leave keys half-replaced; needs inactive staged keys and a durable commit/recovery boundary")
    by["MAC-06"]["review"] = _verdict(V04_REVIEW, "fail", note="one required hosted job (mac-ui) failed")
    by["MAC-08"]["review"] = _verdict(V04_REVIEW, "fail", note="onboarding paragraph contrast still flagged; assert effective Light/Dark, then a layout change; no exemption")
    return apply_verdicts_e23b04b(criteria)


def apply_verdicts_e23b04b(criteria: list[dict]) -> list[dict]:
    """The architect's review of e23b04b (review 6094872675): its explicit criterion verdicts."""
    by = {c["id"]: c for c in criteria}
    by["MAC-17"]["review"] = _verdict(V05_REVIEW, "fail", note="live and staged keys are shared across data folders while the journal lives in one target; needs per-installation namespacing or an account-wide ownership protocol and a two-folder regression")
    by["MAC-08"]["review"] = _verdict(V05_REVIEW, "fail", note="effective appearances verified, paragraph still flagged; investigate the Disabled window state first; no exemption")
    by["MAC-06"]["review"] = _verdict(V05_REVIEW, "fail", note="the required Mac UI check failed")
    return apply_verdicts_a3c7f7d(criteria)


def apply_verdicts_a3c7f7d(criteria: list[dict]) -> list[dict]:
    """The architect's review of a3c7f7d (review 6095269004): its explicit criterion verdicts."""
    by = {c["id"]: c for c in criteria}
    by["MAC-17"]["review"] = _verdict(V06_REVIEW, "fail", note="account-wide design accepted; recovery must serialize with a live restore, startup must enforce the recorded owner, and an unconfirmed commit point must keep the target")
    by["MAC-08"]["review"] = _verdict(V06_REVIEW, "fail", note="make the intended window key and front, capture key/occlusion/appearance before the audit and at each finding; keep the gate")
    by["MAC-06"]["review"] = _verdict(V06_REVIEW, "fail", note="the required Mac UI job failed")
    return apply_verdicts_0949851(criteria)


def apply_verdicts_0949851(criteria: list[dict]) -> list[dict]:
    """The architect's review of 0949851 (review 6095905696): its explicit criterion verdicts."""
    by = {c["id"]: c for c in criteria}
    by["MAC-17"]["review"] = _verdict(V07_REVIEW, "fail", note="key layer fixed; startup releases the guard before its stores open and restore copies before the guard: one ordering of target reservation, key ownership and first store open is needed")
    by["MAC-08"]["review"] = _verdict(V07_REVIEW, "fail", note="window state controlled, findings persist; compare the real Dark screen on the system background and repeat the probe in the same foreground state")
    by["MAC-06"]["review"] = _verdict(V07_REVIEW, "fail", note="a required hosted check remains red")
    return apply_verdicts_d528055(criteria)


def apply_verdicts_d528055(criteria: list[dict]) -> list[dict]:
    """The architect's review of d528055 (review 6096381812): its explicit criterion verdicts."""
    by = {c["id"]: c for c in criteria}
    by["MAC-17"]["review"] = _verdict(V08_REVIEW, "fail", note="startup and in-progress restore windows closed; failure cleanup can still unlink the lock pathname while the reservation holds the inode")
    by["MAC-08"]["review"] = _verdict(V08_REVIEW, "fail", note="bisect the Dark-only difference one modifier at a time; verify the Light reproduction on a second supported hosted macOS configuration")
    by["MAC-06"]["review"] = _verdict(V08_REVIEW, "fail", note="the required Mac UI job failed")
    return criteria


V04_EVIDENCE = ROOT / "core" / "docs" / "v04_checkpoint_evidence.json"
V04_CHECKPOINT = (
    "MET-L partial: the implemented portion named for this row in the conformance matrix has exact tests that resolve and pass in hosted CI "
    "at the scored revision; the rest of the pass condition remains open (recorded in open_gap)"
)
V04_SPLITS = {
    "UC-033": "Mac-to-iPhone handoff on a real iPhone and network",
    "UC-L16": "device loss handled on a real lost or stolen phone",
    "PRD-4-07": "Home and devices on the owner's real accessories and network",
    "S3-C12": "performance measured on the target Mac with the selected model",
}
V04_CHANGES = [
    "v0.4 (PROPOSED, comment 7235843033): PRD and use-case rows the conformance matrices mark PARTIAL get the checkpoint above; 0.5 is earned "
    "only from checkpoint-specific test evidence listed in core/docs/v04_checkpoint_evidence.json (exact tests plus the hosted jobs that run them).",
    "v0.4 (PROPOSED): UC-033, UC-L16, PRD-4-07 and S3-C12 are split into their scored software part and an excluded -DEV device part.",
    "v0.4 (PROPOSED): UC-041, UC-L09 and PRD-5-05 have complete software and only device verification left: the software part is full from exact tests, the device part is a -DEV row. UC-L19 is full: its one recorded gap, ATLAS-CORE-092, was closed by MAC-11, MAC-12 and MAC-15 (architect-passed).",
]


# Rows whose software is complete and whose only recorded gap is owner-hardware or physical-device verification (owner direction: hardware
# is outside the measure). The software part earns full credit from the listed tests; the device part is a separate out-device row.
V04_DEVICE_ONLY_GAPS = {
    "UC-041": ("real TCC prompt and permission-reset behaviour verified on the owner's Mac", [
        ("core/tests/test_designation.py", "test_the_platform_taking_a_granted_permission_back_revokes_the_grant_and_purges"),
        ("core/tests/test_designation.py", "test_an_enabled_source_is_not_declined_it_is_withdrawn_and_a_declined_one_can_be_enabled_later"),
        ("core/tests/test_domains.py", "test_withdrawing_a_domain_purges_its_index_and_what_tasks_derived_from_it")]),
    "UC-L09": ("switching between the real selected models on the owner's Mac, with quality preserved", [
        ("core/tests/test_intelligence.py", "test_research_mode_selects_the_deep_tier_and_unloads_the_primary_first"),
        ("core/tests/test_intelligence.py", "test_never_two_models_resident_even_across_fallbacks"),
        ("core/tests/test_intelligence.py", "test_a_swap_between_verify_and_use_unloads_and_refuses"),
        ("core/tests/test_intelligence.py", "test_default_uses_the_primary_and_the_answer_carries_its_identity")]),
    "PRD-5-05": ("the owner's workload measured on the target Mac", [
        ("core/tests/test_intelligence.py", "test_concurrency_is_capped_at_two_with_one_interactive_and_one_background"),
        ("core/tests/test_intelligence.py", "test_a_waiting_interactive_request_holds_back_new_background_work"),
        ("core/tests/test_intelligence.py", "test_an_interactive_request_that_needs_another_model_stops_a_running_background_inference_and_does_not_wait_for_it"),
        ("core/tests/test_reliability.py", "test_disk_pressure_pauses_indexing_and_says_so_then_resumes")]),
}
V04_DEVICE_ONLY_GAPS["UC-L22"] = ("multilingual answer quality of the real selected model on the target Mac", [
    ("core/tests/test_documents.py", "test_unspaced_scripts_are_indexed_as_overlapping_pairs_so_a_japanese_question_finds_its_document"),
    ("core/tests/test_evals.py", "test_unspaced_japanese_is_retrieved_and_cited_and_no_retrieval_gap_remains"),
    ("core/tests/test_evals.py", "test_retrieval_and_answer_quality_are_reported_separately_per_language_and_script"),
    ("core/tests/test_client.py", "test_a_missing_answer_and_a_hallucinated_figure_are_shown_as_not_confirmed_never_as_checked"),
])  # the software gap (unspaced-script retrieval) is closed in this batch; only the real-model measurement remains
V04_DEVICE_ONLY_GAPS["PRD-5-01"] = ("latency, memory and thermal results on the target Mac", [
    ("core/tests/test_thresholds.py", "test_the_foundation_overhead_stays_within_its_regression_thresholds"),
    ("core/tests/test_bench.py", "test_the_overhead_benchmark_runs_and_reports_percentiles_for_a_named_machine"),
    ("core/tests/test_intelligence.py", "test_a_waiting_interactive_request_holds_back_new_background_work"),
    ("core/tests/test_thresholds.py", "test_the_real_model_thresholds_are_proposed_and_clearly_not_enforced"),
])
V04_DEVICE_ONLY_GAPS["PRD-3-06"] = ("the owner's selected model, quantisation, context and quality on the target Mac", [
    ("core/tests/test_intelligence.py", "test_default_uses_the_primary_and_the_answer_carries_its_identity"),
    ("core/tests/test_intelligence.py", "test_the_gate_remains_the_only_door_and_the_identity_survives_it"),
    ("core/tests/test_intelligence.py", "test_routing_ignores_the_question_text_and_is_deterministic"),
    ("core/tests/test_api_v11.py", "test_a_1_1_answer_carries_coverage_model_and_the_echo_header"),
    ("core/tests/test_api_v11.py", "test_a_withheld_1_1_answer_reports_no_coverage_of_the_revoked_source_and_no_model"),
])
V04_DEVICE_ONLY_GAPS["UC-047"] = ("the real Apple Mail store, account and version on the owner's Mac", [
    ("core/tests/test_mail.py", "test_a_sender_or_date_written_in_the_body_is_never_the_stored_sender_or_date"),
])
V04_DEVICE_ONLY_GAPS["UC-L08"] = ("the owner's model installed and measured on the target Mac", [
    ("core/tests/test_intelligence.py", "test_all_models_failing_is_model_unavailable"),
    ("core/tests/test_intelligence.py", "test_a_request_needing_a_capability_nobody_has_is_unavailable_not_degraded"),
    ("core/tests/test_intelligence.py", "test_text_requests_may_fall_back_to_the_text_model_but_image_requests_never_do"),
])
V04_DEVICE_ONLY_GAPS["S3-C08"] = ("power loss and FileVault behaviour on the target Mac", [
    ("core/tests/test_app.py", "test_a_construction_that_fails_partway_closes_every_store_it_had_opened_and_releases_the_folder"),
    ("core/tests/test_app.py", "test_close_keeps_the_stores_and_the_lock_while_a_request_could_still_be_using_them"),
    ("core/tests/test_app.py", "test_work_admitted_but_not_yet_running_is_counted_by_the_drain"),
    ("core/tests/test_launcher.py", "test_a_stop_with_a_request_still_running_exits_with_status_7_and_the_next_start_succeeds"),
    ("core/tests/test_reliability.py", "test_a_crash_at_every_boundary_of_the_real_stack_gives_the_same_answer_as_an_uninterrupted_run"),
])  # ATLAS-CORE-083 closed by MAC-18 (architect-passed); ATLAS-CORE-084 closed in this batch
# Rows whose only remaining gap is the owner's own walkthrough of the app: an owner-run check, recorded as the -DEV row, not a software criterion.
V04_DEVICE_ONLY_GAPS["PRD-5A-01"] = ("the owner's walkthrough of the app confirming no incidental prompts", [
    ("core/tests/test_policy.py", "test_default_is_deny_nothing_is_retrieved_and_no_model_is_called"),
    ("core/tests/test_actions.py", "test_own_calendar_and_notes_changes_never_prompt_and_every_one_can_be_undone"),
    ("core/tests/test_actions.py", "test_the_action_matrix_only_the_four_categories_ever_need_approval"),
])
V04_DEVICE_ONLY_GAPS["PRD-5A-03"] = ("the owner's walkthrough of every approval category in the app", [
    ("core/tests/test_actions.py", "test_the_action_matrix_only_the_four_categories_ever_need_approval"),
    ("core/tests/test_actions.py", "test_irreversible_removal_needs_approval_and_a_retry_does_not_run_twice"),
    ("app/Tests/AtlasKitTests/DesignSystemTests.swift", "testAnActionAtlasCannotDescribeIsNeverShownForApproval"),
    ("app/Tests/AtlasKitTests/DesignSystemTests.swift", "testApprovalNeedsADeliberateStepAndWorksOnceWhileValid"),
])
V04_DEVICE_ONLY_GAPS["UC-002"] = ("the owner's walkthrough of the app's insufficient-evidence states", [
    ("core/tests/test_client.py", "test_a_missing_answer_and_a_hallucinated_figure_are_shown_as_not_confirmed_never_as_checked"),
    ("core/tests/test_api_v11.py", "test_coverage_states_are_honest_and_tie_to_limitations"),
    ("core/tests/test_client.py", "test_every_value_of_every_closed_vocabulary_has_a_message"),
    ("app/Tests/AtlasKitTests/DesignSystemTests.swift", "testEvidenceStatesNeverImplyASourceWasReadWhenItWasNot"),
])
# Stage 3 rows whose own checkpoint (MET-L: every listed test passes in hosted CI) is met although their status cell starts with PARTIAL: the
# local scope is stated as met, and the remainder is a real-model or final-stage portion. S3-C07's PARTIAL awaited exact-head CI, which has
# since passed on every head. S3-C08 is not included: it records an open defect (ATLAS-CORE-084).
V04_STAGE3_CHECKPOINT = ("S3-C04", "S3-C07", "S3-C11")
# Rows whose recorded gap a later, architect-passed change closed: the gap's own evidence is cited.
V04_GAP_CLOSED = {
    "UC-009": ("the app model's question flow now lives in AtlasKit (QuestionRunner) and is tested against a scripted Core at every Stop timing; a cancelled or expired task's answer is never fetched, so it is never shown as Failed", [
        ("app/Tests/AtlasKitTests/QuestionRunnerTests.swift", "testStopPressedBeforeTheTaskIDReturnsCancelsThatTaskAndShowsCancelled"),
        ("app/Tests/AtlasKitTests/QuestionRunnerTests.swift", "testStopPressedWhileTheTaskRunsShowsCancelledNotFailed"),
        ("app/Tests/AtlasKitTests/QuestionRunnerTests.swift", "testStopPressedAfterTheTaskCompletedChangesNothing"),
        ("app/Tests/AtlasKitTests/QuestionRunnerTests.swift", "testAnExpiredTaskShowsExpiredNeverFailedAndItsAnswerIsNotFetched"),
        ("core/tests/test_tasks.py", "test_cancellation_is_honoured_before_the_run_and_during_it"),
        ("core/tests/test_api.py", "test_cancel_over_the_api_is_safe_to_repeat_and_unfinished_results_are_a_conflict"),
    ]),
    "UC-L14": ("action receipts are durable across restart in this batch (ATLAS-ACT-019 undo receipts in the encrypted edits store); the app's failed-undo state and the connector fix it waited on have passed exact-head CI since", [
        ("core/tests/test_actions.py", "test_an_action_done_before_a_restart_can_still_be_undone_after_it_exactly_once"),
        ("core/tests/test_actions.py", "test_own_calendar_and_notes_changes_never_prompt_and_every_one_can_be_undone"),
        ("core/tests/test_connectors.py", "test_connector_undo_fails_closed_when_previous_state_or_credentials_are_unavailable"),
        ("app/Tests/AtlasKitTests/SubmissionGateTests.swift", "testUndoOnlyClearsWhenCoreExplicitlyConfirmsDone"),
    ]),
    "UC-L26": ("both concrete gaps closed in this batch: newest_indexed is now the newest permitted item's own timestamp (null after withdrawal) and unspaced-script retrieval works; 'source breadth' is the supported-source scope the row is defined over", [
        ("core/tests/test_consent_api.py", "test_get_started_enables_a_source_the_core_indexes_it_and_status_reports_counts_only"),
        ("core/tests/test_api_v11.py", "test_coverage_states_are_honest_and_tie_to_limitations"),
        ("core/tests/test_api.py", "test_suppressed_coverage_never_reports_indexing_done_after_the_question_as_searched"),
        ("core/tests/test_documents.py", "test_unspaced_scripts_are_indexed_as_overlapping_pairs_so_a_japanese_question_finds_its_document"),
    ]),
    "UC-049": ("the dedicated adversarial invite test the matrix found missing is added in this batch", [
        ("core/tests/test_domains.py", "test_a_hostile_calendar_invite_is_data_it_cannot_trigger_an_action_or_change_a_grant"),
        ("core/tests/test_actions.py", "test_instructions_in_content_can_neither_propose_nor_approve"),
    ]),
    "UC-L19": ("ATLAS-CORE-092 (the API read-after-check race) is closed by MAC-11, MAC-12 and MAC-15, each passed by the architect", [
        ("core/tests/test_designation.py", "test_the_platform_taking_a_granted_permission_back_revokes_the_grant_and_purges"),
        ("core/tests/test_domains.py", "test_withdrawing_a_domain_purges_its_index_and_what_tasks_derived_from_it"),
        ("core/tests/test_api.py", "test_a_grant_withdrawn_at_the_last_read_before_delivery_still_removes_the_result"),
        ("core/tests/test_api.py", "test_a_citation_text_is_not_delivered_when_the_grant_is_withdrawn_while_it_is_being_read"),
        ("core/tests/test_domains.py", "test_a_summary_is_withheld_when_its_domain_is_withdrawn_while_the_records_are_being_read")]),
}


# Rows whose credit rests on code or tests added after the scored revision: credited only once the scored revision contains that commit
# (so no evidence is ever cited for a revision that does not hold it). "local" marks work not yet pushed.
V04_LANDS_IN = {"UC-L22": "6c35e620517abfed7d45e42b2fd3b6c52afa50a3", "UC-049": "29d0550", "UC-L14": "29d0550", "UC-L26": "29d0550", "S3-C08": "e8d8f3d", "UC-009": "local"}


def _landed(cid: str) -> bool:
    commit = V04_LANDS_IN.get(cid)
    if commit is None:
        return True
    if commit == "local":
        return False
    done = subprocess.run(["git", "merge-base", "--is-ancestor", commit, CI_REVISION], cwd=ROOT, capture_output=True, check=False)
    return done.returncode == 0


def _full(c: dict, refs: list[tuple[str, str]], note: str) -> None:
    if not _landed(c["id"]):
        c["v04_awaiting"] = f"credited once the scored revision contains {V04_LANDS_IN[c['id']]}: {note}"
        return
    c["implementation"] = {"state": "full", "evidence": [{**test(p, n), "proves": "full"} for p, n in refs] + [{**j, "proves": "full"} for j in (ci("core-3.11"), ci("core-3.13"), ci("macos", "Core tests on macOS"))]}
    c["v04_basis"] = note


def apply_v04(criteria: list[dict]) -> list[dict]:
    """v0.3 -> v0.4 (proposed): checkpoints with mapped evidence for partial PRD and use-case rows, and device splits."""
    by = {c["id"]: c for c in criteria}
    mapped = json.loads(V04_EVIDENCE.read_text(encoding="utf-8"))
    for cid, refs in mapped.items():
        c = by.get(cid)
        if c is None or c["scope"] != "in" or c["implementation"]["state"] != "none":
            continue
        swift = any(path.startswith("app/") for path, _ in refs)
        jobs = [ci("core-3.11"), ci("core-3.13"), ci("macos", "Swift tests and Core tests on macOS")] if swift else [ci("core-3.11"), ci("core-3.13"), ci("macos", "Core tests on macOS")]
        c["checkpoint"] = V04_CHECKPOINT
        c["implementation"] = {"state": "checkpoint", "evidence": [{**test(path, name), "proves": "checkpoint"} for path, name in refs] + [{**j, "proves": "checkpoint"} for j in jobs]}
    for cid, (device, refs) in V04_DEVICE_ONLY_GAPS.items():
        c = by[cid]
        c["pass_condition"] = f"The software part of the requirement is met as specified on the candidate build; the remaining device-only verification ({device}) is {cid}-DEV."
        _full(c, refs, "software complete; only device verification remains (split to the -DEV row)")
        V04_SPLITS.setdefault(cid, device)
    for cid in V04_STAGE3_CHECKPOINT:
        c = by[cid]
        if c["implementation"]["state"] == "none" and c.get("listed_tests"):
            c["implementation"] = {"state": "checkpoint", "evidence": [{**e, "proves": "checkpoint"} for e in (*c["listed_tests"], ci("core-3.11"), ci("core-3.13"))]}
    for cid, (note, refs) in V04_GAP_CLOSED.items():
        _full(by[cid], refs, note)
    for cid, device in V04_SPLITS.items():
        c = by[cid]
        c["title"] = f"{c['title']} (software part)"
        criteria.append({**crit(f"{cid}-DEV", c.get("stage"), f"{c['title'].removesuffix(' (software part)')} (device part)", c["source_ref"], f"Verified on physical hardware: {device}.", "Owner-run check on the physical device", source=c["source"], scope="out-device"), "split_from": cid})
    return criteria


DECISIONS = [
    {
        "id": "DEC-PUBLIC-SEARCH",
        "owner": "Owner",
        "status": "open",
        "question": "Enable public web research (the two off-by-default gates)?",
        "related": ["S3-F11-SW"],
        "note": "A policy choice with no hardware dependency; the guardrails it relies on are scored in S3-F11-SW.",
    },
]


def main() -> int:
    previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    criteria = stages_0_to_2() + stage_3() + stages_4_to_8()
    criteria += conformance(ROOT / "docs" / "genesis" / "PRD_CONFORMANCE.md", "PRD", "prd")
    criteria += conformance(ROOT / "docs" / "genesis" / "USE_CASE_CONFORMANCE.md", "UCX", "use-case")
    criteria += first_mac()
    criteria = apply_v04(apply_v03(criteria))
    seen: dict[str, int] = {}
    for c in criteria:
        seen[c["id"]] = seen.get(c["id"], 0) + 1
        if seen[c["id"]] > 1:
            c["id"] = f"{c['id']}.{seen[c['id']]}"
    register = {
        "version": "0.4",
        "status": "PROPOSED, not agreed: v0.4 awaits Codex's decision (comment 7235843033); v0.3 is the agreed baseline (review 6093596586)",
        "scored_revision": CI_REVISION,
        "rules": "PR #8 comment 7226542434 (scoring) and 7226926847 (schedule protocol)",
        "scoring": {"full": 1.0, "checkpoint": 0.5, "none": 0.0},
        "scopes": {
            "in": "scored",
            "out-device": "physical-device-only: visible, excluded from both scores",
            "aggregate": "composed of other criteria: scored through them only",
            "boundary": "a scope guard that is already true: not a deliverable",
        },
        "changes_from_previous": CHANGES + V03_CHANGES + V04_CHANGES,
        "decisions": DECISIONS,
        "criteria": criteria,
        "review_batches": previous.get("review_batches", []),
    }
    OUT.write_text(json.dumps(register, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(criteria)} criteria to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
