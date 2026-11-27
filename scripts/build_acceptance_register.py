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

# ruff: noqa: PLR2004, C408  (fixed table shapes; keyword-built records)
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "core" / "docs" / "acceptance_register.json"
CI_REVISION = "6fe23c0def5710342a40eeded7841231c39c2d9e"  # the head whose hosted CI is cited below
CI_RUN = "https://github.com/Prasanna666666/Prasanna/actions/runs/46058009895"
JOBS = {
    "core-3.11": f"{CI_RUN}/job/140705116895", "core-3.13": f"{CI_RUN}/job/140705116995", "kit": f"{CI_RUN}/job/140705116765",
    "macos": f"{CI_RUN}/job/140705116884", "app": f"{CI_RUN}/job/140705117010", "ios": f"{CI_RUN}/job/140705116997",
}  # fmt: skip
MAC_REVIEW = ("95f67f41fd1a028336813ccd90383fb3c9cdde97", "https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6092414795", "6092414795")
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
        "implementation": {"state": kw.pop("state", "none"), "evidence": kw.pop("evidence", [])},
        "review": kw.pop("review", {"verdict": None}),
    }  # fmt: skip
    c.update(kw)
    return c


def _tests_in(cell: str) -> list[dict]:
    """Exact test references (`tests/test_x.py::test_y` or `test_x.py::test_y`) named in a source cell."""
    found = re.findall(r"(?:tests/)?(test_\w+\.py)::(test_\w+)", cell)
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
                 f"Criterion {n} ({_plain(cells[1])}) is met on the candidate build: every test listed for it in STAGE3_ACCEPTANCE.md passes in the candidate's hosted Core jobs, its recorded limitation is closed, and any final-stage portion it names has passed. Recorded status and limitation at the source reference: {status}",
                 "The listed tests passing in the candidate's hosted Core CI; target or owner evidence for any final-stage portion",
                 "MET-L: met locally with synthetic data; every test listed for the criterion passes in the candidate's hosted Core CI",
                 source="stage3", state=state, evidence=[*tests, ci("core-3.11"), ci("core-3.13")] if state != "none" else [])  # fmt: skip
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
        ("S3-F11-SW", "Least-privilege model and browser sandbox and real-Internet egress (F-11, software part)", "The worker sandbox profile is least-privilege (deny by default) and verified on a hosted macOS runner; the egress gateway is exercised against the real Internet under the off-by-default gates with the open residuals closed.", "in"),
        ("S3-F11-DEV", "Sandbox verification on the owner's Mac and the owner's public-search decision (F-11, device part)", "Sandbox verified on the owner's Mac; the owner decides on enabling public search.", "out-device"),
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
            out.append(crit(cid, int(number), title, ref, f"Exit evidence met on the candidate and accepted: {title}. Recorded status at the source reference: {status}", "The listed tests passing in hosted CI, plus the target evidence the row names",
                            "MET-L: every test listed for the row passes in the candidate's hosted Core CI (implementer's report, not architect-reviewed)", state=state, evidence=[*tests, ci("core-3.11"), ci("core-3.13")] if state != "none" else [], **base))  # fmt: skip
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
        out.append(crit(cid, None, cells[0], f"{path.relative_to(ROOT)}, §{section} row {k}", f"Met as specified on the candidate build with no open gap. Open gap recorded at the source reference: {_plain(gap)}",
                        "Exact tests or behaviour evidence for the requirement passing on the exact head, plus owner acceptance where the gap names it",
                        "IMPLEMENTED in the conformance matrix and every exact test it names passes in hosted Core CI (an open gap may remain)", source=source, scope=scope, state=state,
                        evidence=[*tests, ci("core-3.11"), ci("core-3.13")] if state != "none" else []))  # fmt: skip
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


def main() -> int:
    previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    criteria = stages_0_to_2() + stage_3() + stages_4_to_8()
    criteria += conformance(ROOT / "docs" / "genesis" / "PRD_CONFORMANCE.md", "PRD", "prd")
    criteria += conformance(ROOT / "docs" / "genesis" / "USE_CASE_CONFORMANCE.md", "UCX", "use-case")
    criteria += first_mac()
    seen: dict[str, int] = {}
    for c in criteria:
        seen[c["id"]] = seen.get(c["id"], 0) + 1
        if seen[c["id"]] > 1:
            c["id"] = f"{c['id']}.{seen[c['id']]}"
    register = {
        "version": "0.2",
        "status": "proposed by Claude; Codex to check the crosswalk and denominator and confirm or correct by SHA",
        "base_revision": CI_REVISION,
        "rules": "PR #8 comment 7226542434 (scoring) and 7226926847 (schedule protocol)",
        "scoring": {"full": 1.0, "checkpoint": 0.5, "none": 0.0},
        "scopes": {
            "in": "scored",
            "out-device": "physical-device-only: visible, excluded from both scores",
            "aggregate": "composed of other criteria: scored through them only",
            "boundary": "a scope guard that is already true: not a deliverable",
        },
        "changes_from_previous": CHANGES,
        "criteria": criteria,
        "review_batches": previous.get("review_batches", []),
    }
    OUT.write_text(json.dumps(register, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(criteria)} criteria to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
