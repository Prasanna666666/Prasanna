# Atlas — current handover

**Last reconciled:** 2026-11-25  
**Repository:** `Prasanna666666/Prasanna`  
**Working branch:** `genesis-stage2-foundation`  
**Shared review vehicle:** [PR #8](https://github.com/Prasanna666666/Prasanna/pull/8)  
**Code/evidence snapshot before documentation-only cleanup:** `83eec5378fff9f26f435492104c4efa2b30d18ca`  
**Latest documentation-only head:** `23fee7b5f7d04898e193926fbb05a62856fd7bf9`  
**PR state:** open, draft, unmerged. This handover does not accept a stage or authorise release.

## Start here

1. [Genesis documentation index](README.md) — canonical reading order and source-of-truth rules.
2. [PRD](PRD.md) — product promise and owner-approved behaviour.
3. [UI/UX specification](UI_UX_SPECIFICATION.md) — canonical everyday experience and interaction design.
4. [Target architecture](TARGET_ARCHITECTURE.md) — system boundaries and sole delivery roadmap (§11).
5. [Use-case register](USE_CASE_REGISTER.md) — scenarios and integration capability expectations.
6. [Implementation conformance audit](IMPLEMENTATION_CONFORMANCE.md) — current evidence boundary and the code-to-document review still required.
7. [Review coverage reconciliation](REVIEW_COVERAGE_RECONCILIATION.md) — PR review-thread and path coverage ledger.
8. [Delivery protocol](DELIVERY_PROTOCOL.md) — roles, change control and acceptance rules.

## Product baseline

Atlas is one local-first personal AI operating system: a personal smart intranet and intelligent chief of staff, not a collection of separate mini-apps. The everyday experience must remain calm, uncluttered and useful to a regular user. The persistent primary navigation is **Home, Ask Atlas, Explore and Library**; specialist capabilities open contextually rather than each becoming a permanent top-level section. Settings is a restrained utility surface.

The target is macOS first, with a secure iOS client later. Android is out of scope. Personal-data processing and inference remain owner-controlled and local; public Internet research is a separate, explicitly governed egress path and must not be confused with cloud inference. No silent cloud inference or fallback.

Atlas should unify conversation, voice, dashboard, notifications, connected knowledge, contextual Spaces, personal memory, domain capabilities, app/service integrations, automation and action history. It may research, monitor authorised sources, prepare work and execute permitted reversible actions. Approval remains limited to the exhaustive categories in PRD §4.4. Do not add generic approval prompts for routine reading, analysis, drafting or reversible local work.

Home management is a first-class capability: device state, energy and usage tracking, heating schedules, environmental readings and permitted automation. Clearly distinguish measured data from estimates and show source coverage. Personal finance/investment, health, travel, sport/statistics, news/discovery, work/projects and other domains are integrated capabilities, not separate applications.

## Evidence and stage status

The following status distinctions are mandatory:

- **Code present** means files exist in the repository. It does not prove the feature works end-to-end.
- **Tested** means named tests ran and passed at an identified commit/environment.
- **Reviewed/accepted** means the stated scope was independently reviewed and explicitly accepted at an exact commit.
- **Owner-verified** means exercised on the owner's target machine/accounts/data with owner confirmation.
- **Release-ready** requires all applicable platform, security, installation, operational and owner gates.

### Verified repository / PR facts at this reconciliation

- PR #8 is the only open shared PR found in the current working context; it is draft and unmerged.
- Its observed head is `83eec5378fff9f26f435492104c4efa2b30d18ca`. The PR reports 605 commits and 281 changed files. The branch includes macOS app sources, Core, iOS client sources, tests, contracts and canonical documentation.
- Stage 2 Core was accepted for its reviewed scope at the earlier exact head `58210223398a5715b618d1163397104efd358d49`; the PR description records 22/22 CI checks at that head. This does not automatically accept later changes or the current head.
- WP3.1 API 1.1 contract/specification was accepted for its exact scope at `800d13743f6cf4ce0ab87b4b8e098d441e459a56`; API 1.1 is specification-only and is not served by Core.
- WP3.2 document-only vertical path was accepted for its exact scope at `ad6e59bcb6fb5d6124ac56ea419f8330dc913e4c`. Its accepted scope and limitations remain as recorded in `core/docs/WP3_2_DOCUMENTS.md`.
- The PR description states that the Stage 3-testable portions are implemented and tested. Stage 3 itself is **not accepted**. The named final-stage gates F-4, F-11, F-12 and F-13 remain unmet, unwaived and release-blocking; see `core/docs/STAGE3_ACCEPTANCE.md` and `core/docs/PROGRAMME_AUDIT.md`.
- Stage 4–8 code/documentation work is present on this same branch by owner direction, but it is not architect-reviewed or accepted. Presence on the branch must not be described as completed, released or owner-verified functionality; see `core/docs/STAGES_4_TO_8.md`.
- The workflow run associated with the observed head was queued when checked. No passing result for that run is claimed here.
- General-purpose browser/app automation is documented as a Stage 6 target architecture, not a Stage 3 completion claim. Playwright is a recommendation, not an adopted runtime dependency; OpenClaw is not adopted.

### Explicitly unaccepted / unverified

At minimum, the PR's own current delivery statement identifies these outstanding items: selected production model injection and evaluation; target-Mac performance/resource measurements; real owner-machine sandbox and real-Internet egress exercise plus owner decision to enable public search; human UI/accessibility walkthrough; real TCC prompts and Mail store; Developer ID signing/notarisation; self-contained install; and target-Mac Keychain/LOCAL_PEERCRED and lifecycle/recovery verification. Do not convert these into completed claims without new exact evidence.

The existence of iOS source files does not prove secure worldwide access, offline sync or release readiness. The existence of automation modules does not prove broad real-world app coverage or safe end-to-end execution.

## Current next work

1. Continue the remaining document-by-document contradiction audit, using [IMPLEMENTATION_CONFORMANCE.md](IMPLEMENTATION_CONFORMANCE.md) as the checklist. The entry-point, authority, status-vocabulary and UX-handoff cleanup has been committed; detailed technical records still need reconciliation.
2. Then perform the code-to-document conformance audit at a frozen exact commit. Trace every material PRD requirement and use case to implementation, tests and runtime evidence. Mark each **aligned**, **partially aligned**, **documentation drift**, **not implemented**, or **unverified**.
3. Reconcile every current PR review thread and changed path; do not report the audit complete while material unresolved review comments or uninspected changed paths remain.
4. Re-run CI on the final audit head and record the exact result. Do not merge, close the PR, waive release gates or claim owner acceptance without explicit authority.

## Change-control rules

- `TARGET_ARCHITECTURE.md` §11 is the sole delivery roadmap.
- `PRD.md` is the product/behaviour authority; `UI_UX_SPECIFICATION.md` is the visual and interaction authority; `DECISIONS.md` records owner decisions; `DELIVERY_PROTOCOL.md` governs collaboration and acceptance.
- `USE_CASE_REGISTER.md` owns scenario and integration coverage. Other documents link to it rather than maintaining competing inventories.
- `core/docs/*` records implementation contracts, technical design, tests and stage evidence. It must not silently redefine product intent.
- When code and a target document differ, record the exact difference and classify it. Do not silently weaken the product requirement to fit existing code.
- Preserve historical review evidence, decisions, commit references and user data. Correct current summaries without rewriting history.
- Every material claim includes a path, exact commit, test/evidence and limitations. If evidence is absent, say **unverified**.


## Documentation-only reconciliation commit set — 2026-11-25

The following documentation-only commits were made after the code/evidence snapshot `83eec5378fff9f26f435492104c4efa2b30d18ca`: handover reconciliation `80206365b98c850940965ce01ab2b7eaebdd3238`; canonical Genesis index `f449d9a276e811fd54c0b11b43164ab6c8691b35`; root documentation index `ce6291da2ef1538e20bc69afc1480059da91d5b2`; implementation-conformance audit framework `225b6e9d3e5e332682f45d7866b75468cb3fce9f`; PRD metadata correction `6b8e2f2fc9539dda0aa8857908164f017ee92c79`; UI/UX implementation-status and handoff correction `05d4dd535d88b8f4556689a27512f9b8444c7da3`; review-coverage live snapshot `23fee7b5f7d04898e193926fbb05a62856fd7bf9`. Latest PR head after these docs-only changes: `23fee7b5f7d04898e193926fbb05a62856fd7bf9`. No application source or tests were changed by this cleanup.