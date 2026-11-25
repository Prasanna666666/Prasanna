# Atlas — current handover

**Last reconciled:** 2026-11-25  
**Repository:** `Prasanna666666/Prasanna`  
**Working branch:** `genesis-stage2-foundation`  
**Shared review vehicle:** [PR #8](https://github.com/Prasanna666666/Prasanna/pull/8)  
**Code/test conformance snapshot:** latest implementation patches are present on this branch; exact-head validation is pending CI  
**Branch head:** refresh from GitHub before resuming; this document deliberately avoids a self-referential HEAD hash  
**PR state:** open, draft, unmerged. This handover does not accept a stage or authorise release.

## Start here

1. [Genesis documentation index](README.md) — canonical reading order and source-of-truth rules.
2. [PRD](PRD.md) — product promise and owner-approved behaviour.
3. [UI/UX specification](UI_UX_SPECIFICATION.md) — canonical everyday experience and interaction design.
4. [Target architecture](TARGET_ARCHITECTURE.md) — system boundaries and sole delivery roadmap (§11).
5. [Use-case register](USE_CASE_REGISTER.md) — scenarios and integration capability expectations.
6. [PRD conformance](PRD_CONFORMANCE.md) — requirement-by-requirement implementation status.
7. [Use-case conformance](USE_CASE_CONFORMANCE.md) — UC-001–055 and UC-L01–L30 evidence/gap matrix.
8. [Implementation conformance audit](IMPLEMENTATION_CONFORMANCE.md) — exact evidence boundary and remaining code-to-document trace.
9. [Review coverage reconciliation](REVIEW_COVERAGE_RECONCILIATION.md) — PR review-thread and path coverage ledger.
10. [Delivery protocol](DELIVERY_PROTOCOL.md) — roles, change control and acceptance rules.

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
- Its observed head at the latest check before this handover update is `2d40ecf5bed5efee16761c7b973ad058e70d1dec`. The PR reports 285 changed paths. The branch includes macOS app sources, Core, iOS client sources, tests, contracts and canonical documentation.
- Stage 2 Core was accepted for its reviewed scope at the earlier exact head `58210223398a5715b618d1163397104efd358d49`; the PR description records 22/22 CI checks at that head. This does not automatically accept later changes or the current head.
- WP3.1 API 1.1 contract/specification was accepted for its exact scope at `800d13743f6cf4ce0ab87b4b8e098d441e459a56`; the API 1.1 contract was subsequently implemented and is served additively by WP3.4 (the 1.0 contract remains frozen). See `core/docs/CONTRACT_1_1.md`.
- WP3.2 document-only vertical path was accepted for its exact scope at `ad6e59bcb6fb5d6124ac56ea419f8330dc913e4c`. Its accepted scope and limitations remain as recorded in `core/docs/WP3_2_DOCUMENTS.md`.
- The current criterion-level matrix in `core/docs/STAGE3_ACCEPTANCE.md` records criteria 2, 7 and 8 as PARTIAL with open findings. Stage 3 itself is **not accepted**. The separate final-stage gates F-4, F-11, F-12 and F-13 remain unmet, unwaived and release-blocking. Use the acceptance matrix, not broad summary wording in older handover snapshots, for criterion status.
- Stage 4–8 code/documentation work is present on this same branch by owner direction, but it is not architect-reviewed or accepted. Presence on the branch must not be described as completed, released or owner-verified functionality; see `core/docs/STAGES_4_TO_8.md`.
- Exact source/test snapshot CI run `45577911258` is queued for `35d41c800046ca3042991134f66bece7611191cc` (16 jobs); all jobs remained queued at last check. Later commits are documentation-only. No pass is claimed until the run completes; refresh the live head before resuming.
- General-purpose browser/app automation is documented as a Stage 6 target architecture, not a Stage 3 completion claim. Playwright is a recommendation, not an adopted runtime dependency; OpenClaw is not adopted.

### Explicitly unaccepted / unverified

At minimum, the PR's own current delivery statement identifies these outstanding items: selected production model injection and evaluation; target-Mac performance/resource measurements; real owner-machine sandbox and real-Internet egress exercise plus owner decision to enable public search; human UI/accessibility walkthrough; real TCC prompts and Mail store; Developer ID signing/notarisation; self-contained install; and target-Mac Keychain/LOCAL_PEERCRED and lifecycle/recovery verification. Do not convert these into completed claims without new exact evidence.

The existence of iOS source files does not prove secure worldwide access, offline sync or release readiness. The existence of automation modules does not prove broad real-world app coverage or safe end-to-end execution.

## Current next work

1. **CI validation:** check run `45574340059` for code/test snapshot `5284191f013ff5f9b29a35ff237d19ead7e51ad3`; then require a new completed run for the latest PR head. Fix any failures and keep the exact run/commit in this handover.
2. **Remaining review threads:** 7 of 127 remain unresolved: three sandbox least-privilege/security residuals (release-blocking) and four code/test patches awaiting CI (exact arithmetic, API 1.1 open-map boundary, connector reversible-action compensation, full Keychain test inventory). Current review snapshot: 120 resolved, 7 unresolved; 6 unresolved anchors are outdated and 1 is current.
3. **Full conformance trace:** the canonical docs and known cross-document contradictions are substantially reconciled, but a certified row-by-row trace of every PRD requirement, all use cases, integrations, screens and all 283 changed paths is not complete. Continue from `IMPLEMENTATION_CONFORMANCE.md`; do not infer coverage from file presence or old path counts.
4. **Outstanding implementation findings:** ATLAS-CORE-092, ATLAS-CORE-083/084, browser worker isolation, Action Gateway durability, egress residuals, currency precision, app cancellation/undo and accessibility patches pending CI, plus mobile/relay findings still need exact-head dispositions. See `DEFECT_REGISTER.md`.
5. Keep Stage 3 NOT ACCEPTED and Stages 4–8 not architect-reviewed/accepted. Do not merge, close the PR, waive release gates or claim owner acceptance without explicit authority.

## Change-control rules

- `TARGET_ARCHITECTURE.md` §11 is the sole delivery roadmap.
- `PRD.md` is the product/behaviour authority; `UI_UX_SPECIFICATION.md` is the visual and interaction authority; `DECISIONS.md` records owner decisions; `DELIVERY_PROTOCOL.md` governs collaboration and acceptance.
- `USE_CASE_REGISTER.md` owns scenario and integration coverage. Other documents link to it rather than maintaining competing inventories.
- `core/docs/*` records implementation contracts, technical design, tests and stage evidence. It must not silently redefine product intent.
- When code and a target document differ, record the exact difference and classify it. Do not silently weaken the product requirement to fit existing code.
- Preserve historical review evidence, decisions, commit references and user data. Correct current summaries without rewriting history.
- Every material claim includes a path, exact commit, test/evidence and limitations. If evidence is absent, say **unverified**.


## Documentation-only reconciliation commit set — 2026-11-25

The following documentation-only commits were made after the code/evidence snapshot `83eec5378fff9f26f435492104c4efa2b30d18ca`: handover reconciliation `80206365b98c850940965ce01ab2b7eaebdd3238`; canonical Genesis index `f449d9a276e811fd54c0b11b43164ab6c8691b35`; root documentation index `ce6291da2ef1538e20bc69afc1480059da91d5b2`; implementation-conformance audit framework `225b6e9d3e5e332682f45d7866b75468cb3fce9f`; PRD metadata correction `6b8e2f2fc9539dda0aa8857908164f017ee92c79`; UI/UX implementation-status and handoff correction `05d4dd535d88b8f4556689a27512f9b8444c7da3`; review-coverage live snapshot `23fee7b5f7d04898e193926fbb05a62856fd7bf9`. The captured checkpoint `80dbd8584201aafce3697f28e3ec35fb6d5f42af` was followed by further documentation-only updates; refresh the live branch head before resuming. No application source or tests were changed by this cleanup.

## Final documentation-only reconciliation checkpoint — 2026-11-25

Additional corrections after the initial index/UX pass: `PROGRAMME_AUDIT.md` and `STAGE3_HANDOVER.md` are explicitly identified as historical work-package records; `OWNER_ACCEPTANCE_CHECKLIST.md` no longer presents 2026-11-24 path counts as current; `BRANCH_HISTORY_RECONCILIATION.md` records that Stage 4–8 work was subsequently rebased onto PR #8. Latest documentation-only head: `c3679dc914e31a1f0fda7c709b45ae0119aa9096`. The latest live review snapshot is in `REVIEW_COVERAGE_RECONCILIATION.md`.

The later technical-document cleanup commits were: `f8c3550faef58b34074f0c7d514b457ca8e43997` (programme audit historical status), `43fc99f6492ea58911ebba49d239ae6ce845447b` (Stage 3 handover), `a3ab530dd8229498901caa825eb844679048190a` (owner checklist), `c3679dc914e31a1f0fda7c709b45ae0119aa9096` (branch-history reconciliation), `1a35610a0f9f1c26c2e2363fd494f03e3e4cc60c` (handover checkpoint), `e9fedf9ec5024f6901e6f66d4fd8117fa9546a0a` (conformance checkpoint), `72db4262079508d09d07253604177c5c1d42ed90` (review ledger), `13bcc8e329c0bda00c8a44aa4c03ecdb9dec14af` (Stage 3 threat traceability), `4b1687cb3a25990dfcc8561405800104f14fa688` (WP3.1 proposal history label), and `80dbd8584201aafce3697f28e3ec35fb6d5f42af` (Stage 3 handover correction).

**Head discipline:** this document records evidence snapshots, not a self-referential current-HEAD hash. Always query the live PR before starting work or quoting counts.

## Additional roadmap/decision consistency corrections — 2026-11-25

- `TARGET_ARCHITECTURE.md` §11 now distinguishes the ordered roadmap from actual authorisation/acceptance and records the owner's 2026-11-23 instruction placing Stage 4–8 work on PR #8.
- `DECISIONS.md` G-O09 now records the bounded Stage 2 acceptance at its exact historical SHA; later commits are not implicitly accepted.
- `DELIVERY_PROTOCOL.md` labels the original Stage 2 entry gates as historical rather than current blockers.
- Commits: `18002761b7190a8121639c0bc187ab5001422e87` (roadmap status), `7eb30dbac13d24f2ac8e5354c725c3683f6687f1` (decision register), `441c7b6df228c7378cc7105ef97eb1aa12e2fb00` (delivery protocol).

## API 1.1 status correction — 2026-11-25

The WP3.1 acceptance was acceptance of the contract/specification scope, not a claim that runtime routes were already served at that commit. Subsequent WP3.4 work implements and serves API 1.1 additively; `core/docs/CONTRACT_1_1.md` is the current contract/runtime status authority. Do not repeat the historical statement that API 1.1 is still specification-only or not served.

Additional documentation-only corrections in the final pass: `3706b95afd02b038d26134300c8ed568f91142c2` corrected the API 1.1 contract title/status; `6e463c714f963e3f42c3fabbc6d191d200353088` corrected the handover's API 1.1 status; `83051aea4269c4a178b371ef15fdca741cfc1a94` corrected Stage 3 handover egress/rollback wording and the PR description; `4ade8a8b526826e0d037876b113fa1220f17c818` removed the remaining Stage 3 egress-path wording conflict; `b230633b3b8d027576be42f6a6508c638e6e3a6f` aligned the handover with the criterion matrix. Review snapshot after those changes is recorded in `REVIEW_COVERAGE_RECONCILIATION.md`.

## Additional package-level documentation corrections — 2026-11-25

- `STAGE-3-EXECUTION-PLAN.md`: WP3.2 coverage limitation is labelled as true at the accepted WP3.2 commit; WP3.4 API 1.1 coverage is recorded as the later change. The plan no longer says API 1.1 is unserved.
- `STAGE-2-WORK-PACKAGE.md`: historical entry gate text now records the subsequent exact-scope Stage 2 acceptance and separate Stage 3 authorisation.
- `WP3_2_DOCUMENTS.md` and `WP3_3_MAIL.md`: historical package snapshots distinguish what was true at package acceptance from later API 1.1 coverage and the implemented-but-real-store-unverified EMLX reader. Mail attachments remain unread.
- `core/docs/TRACEABILITY.md`: explicitly historical Stage 2 baseline; later grants and stages are not implied by its old rows.
- `EGRESS_GATEWAY.md`: public research is documented as a separate API 1.1 operation, not ordinary answer generation.
- `TEST_PLAN.md` and `WP3_5_CLIENT.md`: older Linux/reference-client snapshots are no longer presented as the current app/CI state.
- `OWNER_ACCEPTANCE_CHECKLIST.md`: distinguishes native framework CI coverage from synthetic `.emlx` fixtures and the unverified real Mail store.
- Commits: `08b973d7d3e6213c2ec63ad14dd0e8780a73733a`, `bd4d0bd05a8b03f9d8454a1e396d8c0405301e07`, `cefb48de9a0177c8f5bd035330ab9fdc2bbfa020`, `30a665987e54c119f01ac5bfe8455125cf2b96de`, `35e16243b6a3ddc43bae2dbdb24984f9c9869d9a`, `7cf97cbf1574b81d0084c2d40c200743fa664a8b`, `58b7e2de4b203977e437338f33928856484fdda4`, `2418e38f958d8be1600bf16711bd6b1800c020b1`, `36a8379f253e321103148d88e8aaa46752fb04e5`, and `408add907fb0b5a33151c52c66a1e8a213ff51f3`.

The final historical-evidence cleanup also labelled `core/docs/DESIGN.md` as a Stage 2 snapshot and corrected its hosted-macOS Keychain evidence note (`e1815bbc983f21f4d9d0cac448ab15f719bd5dc1`); the latest review snapshot is recorded in `REVIEW_COVERAGE_RECONCILIATION.md` (`fe8a34efc8db686afe1ae7b2efaffb1f471f4115`).

## Final granular documentation pass — 2026-11-25

- Reconciled the G-021 Finance/Health policy across `LOW_LEVEL_DESIGN.md`, `MEMORY_PRIVACY_KNOWLEDGE.md` and the implementation evidence: owner-authorised, purpose-bound, revocable local-model access is permitted for both domains; Finance arithmetic/balances remain deterministic and code-checked; private content is excluded from public web, cloud inference, logs and unrelated tasks. The owner decision in `DECISIONS.md` remains authoritative.
- Corrected stale UI map statements: Ask includes microphone dictation and answer read-aloud, though not full live voice conversation; phone pairing is present; in-app backup/restore remains absent.
- Updated the LLD's old pre-implementation rule to a historical process note and aligned its Finance trust-zone description with G-021.
- These edits are documentation-only. They do not change the implementation, acceptance state or review-thread resolution.
- Commits: `2268d0fdd01720727fca07bc8b4328ee85f7834b` (LLD/G-021), `5ef65f7f186b4e5aa783d19f39de170f8a108059` (memory/privacy), `aa9ba19d1f3c6d71da733a664df3169e42b305f6` (UI map), `1713785c432e6a967cd163964c3d69aa1c639788` (LLD process/trust-zone correction).
- Live PR snapshot at `1713785c432e6a967cd163964c3d69aa1c639788`: open/draft/unmerged; 282 changed paths; 127 review threads (21 resolved, 106 unresolved; 40 unresolved outdated, 66 unresolved current; 52 threads outdated overall, 75 current overall). CI run 45564148620 was queued; combined status had no entries. No CI pass is claimed.

## Final technical-document reconciliation checkpoint — 2026-11-25

- Updated current technical records to match G-021, the served API 1.1 routes, the hosted macOS/Swift evidence, current connector/egress residual risks, actual Finance-versus-Health ingestion, actual backup/key inventory, Core child-process lifecycle, and present UI/remote-phone limitations. Historical package plans and rollback instructions are now explicitly scoped as historical where appropriate.
- Corrected OpenAPI 1.1 operation-level security exceptions for the unsigned first-owner enrolment and device-pairing offer-code operations (`security: []`); the root default remains signed-request security.
- Added current residual-risk disclosure for ATLAS-SEC-014, ATLAS-EGRESS-077/078/079/091, connector undo/transport, and relay/iOS/unpair-cache issues. No runtime source or tests were changed; the OpenAPI 1.1 contract file was updated.
- Latest observed head: `d877a4ec3ce02244a070eb1dbbdaf021e6988de0`. PR #8 remains open/draft/unmerged; 282 changed paths; 127 review threads (21 resolved, 106 unresolved; 73 unresolved outdated and 33 unresolved current; 85 outdated and 42 current overall). Exact-head workflow query returned no run and combined status had no entries. No CI pass is claimed.
- `IMPLEMENTATION_CONFORMANCE.md` records the initial evidence-based comparison and remaining work. The full row-by-row PRD/use-case/screen/path/thread audit is not complete.
## Code-review reconciliation checkpoint — 2026-11-25

- Verified and resolved specific review findings for app Core lifecycle, live-socket preservation, EMLX regular-file replacement identity, and exact private-name/short-phrase egress fingerprints. Regression tests are present for each; owner UI/Mail/real-Internet validation remains separate.
- Five current unresolved review threads remain, all in source/test files: exact arithmetic precision (P1), API free-text object-map schema coverage, connector undo falsely reporting success, OpenAPI path-count test naming, and native Keychain test fixture cleanup. Do not treat these as documentation-only issues.
- Stage 3 P1/P2 findings ATLAS-CORE-092, ATLAS-EXACT-106 and ATLAS-CORE-083/084 remain open; egress residuals and Stage 4–8 security/device blockers are recorded in the conformance report.
- Latest PR snapshot: head `533a2460f3f013690a862d029488dc42d9611fb4`; 282 changed paths; 127 review threads (44 resolved, 83 unresolved; 78 unresolved outdated, 5 unresolved current). CI run 45565642702 is queued and combined status has no entries.

## Final documentation inventory checkpoint — 2026-11-25

- Canonical active documentation was reconciled across the product requirements, architecture/LLD, decisions, privacy/network policy, ingestion/intelligence, UI/UX specification/map, API 1.1 contract/OpenAPI, Stage 2/3 records, Stage 4–8 developer report, provider/runtime/egress/connector/storage/rollback/owner-acceptance records, review ledger and handover.
- Historical Stage 2/3 package snapshots, proposal documents, Linux-only test reports and branch/chat archives are explicitly identified as historical or superseded where they could otherwise be mistaken for current capability/status. The baseline audit and old rollback procedures are not current implementation instructions.
- Latest live PR snapshot: head `d66cb24907d77746a96814f0865dead0448b363e`; 282 changed paths; 127 review threads (44 resolved, 83 unresolved; 78 unresolved outdated, 5 unresolved current). Exact-head CI run 45566805549 is queued; no pass is claimed.
- The active canonical documentation is substantially reconciled, but this is not a certification of every historical chat/archive artifact or all 282 implementation paths. The five current unresolved review threads are source/test findings listed in `IMPLEMENTATION_CONFORMANCE.md`.


## Final PR description and CI checkpoint — 2026-11-25

- Corrected the shared PR #8 description so it no longer overstates egress as a complete no-private-data guarantee. It now records the exact addressed private-name/short-phrase bypass, residual 1–3-character/paraphrase and stale-passage/DNS/truncation/URL gaps, and that the separate research API is not ordinary answer generation. The Stage 3 app is described as a target, not as already owner-tryable.
- Immediately before this handover note, the live PR head was `0c8f63118a1c286aa55da270afc30aebc4b20838`; 282 changed paths; PR #8 open/draft/unmerged; 127 review threads (44 resolved, 83 unresolved; 78 outdated unresolved, 5 current unresolved). CI run 45567148195 was queued and combined status had no entries. No pass is claimed.
- This note is itself a documentation-only follow-on. Refresh the live head and exact-head CI before resuming; do not rely on the snapshot SHA above as the branch's new HEAD.


## Branch-wide rollback and recovery note — 2026-11-25

- Added `core/docs/BRANCH_ROLLBACK_AND_RECOVERY.md` and linked it from the Core README, Stage 3 handover and owner acceptance checklist. It explicitly distinguishes source rollback, installed app rollback, Core database restore, Keychain, derived indexes/models, paired-device state and external side effects.
- This is an inventory/warning document, not an approved disaster-recovery runbook. No complete owner-Mac restore drill, backup policy/destination decision or acceptance has been completed. The historical `core/docs/ROLLBACK.md` must not be used as a current branch-wide rollback procedure.


## Current work log — 2026-11-25 (continuation)

- Reconciled the remaining active status contradictions in Stage 3 acceptance, macOS provider evidence, egress, connector profile, plug-in guide, enrolment, API 1.1 contract/OpenAPI, owner checklist, historical proposal/traceability records and rollback documentation. Added `core/docs/BRANCH_ROLLBACK_AND_RECOVERY.md` and linked it from the Core README, Stage 3 handover and owner checklist.
- Implemented code/test patches for exact terminating-decimal construction, reversible connector action prior-state validation/undo failure, API 1.1 open-object-map allowlist/authority descriptions, the OpenAPI path-count test name and full production Keychain test inventory. Regenerated `atlas-contracts.1.1.schema.json` from the updated delta. These patches are not yet CI-validated.
- Replied to and resolved 120 of 127 review threads after checking the current source/tests or correcting the corresponding documentation. Seven remain: three macOS sandbox residual-risk threads, plus the four code/test patches awaiting CI.
- Last live snapshot recorded above: PR #8 head `ebe870b5862cbf11b5c80ef23e4869fd5228fe97`, 283 changed paths, 127 threads (120 resolved, 7 unresolved; 6 outdated unresolved, 1 current). CI run 45574340059 was queued on prior code/test snapshot `5284191f013ff5f9b29a35ff237d19ead7e51ad3`; no exact-head CI pass is claimed.


## Latest implementation continuation — 2026-11-25

- Added complete first-pass conformance matrices: `PRD_CONFORMANCE.md` maps PRD sections/principles to implementation; `USE_CASE_CONFORMANCE.md` maps UC-001–055 and UC-L01–L30 with current gaps. These are evidence-based first passes, not certification of every changed path or owner acceptance.
- Fixed app cancellation's stale task-ID race using `SubmissionCancellation`; Stop requests received before Core returns an ID are applied to that newly created task. Failed Undo now preserves the retry affordance and shows an error unless Core confirms success. Added helper tests.
- Hardened the macOS accessibility UI test: removed the unsafe pixel-extrema contrast exemption and replaced fixed sleep with a bounded wait for the expected first-run or Home screen.
- Latest observed PR head `67c7ee475db4188b0460a48807a8f0210c78a7d9`; 285 changed paths; 127 review threads (120 resolved, 7 unresolved: 3 sandbox residuals and 4 code/test patches awaiting CI). Exact-head CI run 45576209883 queued, 16 jobs. Refresh the live head and CI before resuming.


## Latest audit continuation — 2026-11-25

- Added `PRD_CONFORMANCE.md` (PRD principles/sections to implementation) and `USE_CASE_CONFORMANCE.md` (UC-001–055 plus UC-L01–L30). Together with `IMPLEMENTATION_CONFORMANCE.md`, these are the restartable requirement-to-code audit set. The matrices identify major absent capabilities including governed memory, home energy, sports/Statsguru, personalised news, investment cockpit, general agentic workflows, full Health ingestion, app automation, persistent conversation history, bulk operations, location triggers, OCR/attachments and production-ready iOS remote access.
- Updated the Core README to describe current Core/API/runtime and acceptance boundaries; corrected app and iOS READMEs; corrected the backup.py module inventory; documented branch-wide recovery limits; and recorded the owner-authorised bounded implementation exception in DELIVERY_PROTOCOL.md.
- Additional app fixes: Stop requested before Core returns the new task ID is queued against that new task; failed Undo preserves the action handle and shows an error unless Core confirms done. Added helper tests. Accessibility UI test now waits for Welcome/Home and no longer suppresses contrast failures using pixel extrema. Exact-head CI pending.
- Latest source/test snapshot observed: `35d41c800046ca3042991134f66bece7611191cc`; latest PR head before this note: `2d40ecf5bed5efee16761c7b973ad058e70d1dec`; PR #8 open/draft/unmerged; 285 changed paths; 127 review threads (120 resolved, 7 unresolved: 3 sandbox least-privilege residuals, 4 code/test findings awaiting CI). CI run 45577911258 is queued with 16 jobs; no pass claimed.
- Remaining work is not cosmetic: exact-head CI and failure triage; a defensible least-privilege macOS sandbox; ATLAS-CORE-092, ATLAS-CORE-083/084, ATLAS-SEC-016, ATLAS-ACT-019, ATLAS-CONN-025, egress residuals, currency semantics, and remote-phone defects; AppModel integration/owner UX verification; and final row-by-row audit of every changed path. Stage 3 remains NOT ACCEPTED; Stage 4–8 not architect-reviewed/accepted.


## Final restart checkpoint — 2026-11-25

- Live PR #8 head at checkpoint: `2d40ecf5bed5efee16761c7b973ad058e70d1dec`; open, draft, unmerged; 285 changed paths; 127 review threads (120 resolved, 7 unresolved: 3 sandbox residuals, 4 source/test patches awaiting CI; 6 unresolved anchors outdated, 1 current).
- Latest source/test snapshot: `35d41c800046ca3042991134f66bece7611191cc`. The later commit `2d40ecf...` only updates repository instructions; no application/runtime code or tests changed after the source/test snapshot.
- Exact source/test snapshot CI run `45577911258` is queued with 16 jobs. All jobs are still queued; no pass/failure is yet available. Do not close the four pending code/test threads until the run completes and the exact job results are inspected.
- The 285-path inventory is classified: 65 documentation/README paths (28 core docs, 33 Genesis docs, four project READMEs), 132 Core source/test paths, 61 macOS app source/test/project paths, 7 iOS source/test/project paths, 14 Core contract/client/bench/eval/tool/config paths, 2 shared-kit paths, 3 scripts and 3 root/workflow/config files. This is a path-family inventory, not a claim that all 285 files have had line-by-line semantic review.
- Canonical active documentation has been reconciled and all registered use cases have a first-pass matrix. Historical archives remain historical. The full 285-path source/test semantic audit, AppModel-level integration tests, owner walkthrough and release acceptance remain incomplete.
- Restart instructions: refresh PR head/threads/CI; inspect run 45577911258 and all 16 jobs; fix failures; re-run on the resulting source/test head; re-review the four code/test findings; keep three sandbox findings open until a defensible least-privilege design or explicit residual-risk decision; continue ATLAS-CORE-092/083/084, SEC-016, ACT-019, CONN-025, egress, currency and mobile findings. Stage 3 remains NOT ACCEPTED; Stages 4–8 remain not architect-reviewed/accepted.


## Post-checkpoint source-comment reconciliation — 2026-11-25

- Latest observed PR head: `3a366d80ef9d58bafd92e0fe12238a0f07424ba7`; 285 changed paths; 127 review threads (120 resolved, 7 unresolved). PR remains open/draft/unmerged.
- The last behavior-bearing source/test snapshot remains `35d41c800046ca3042991134f66bece7611191cc`, with CI run `45577911258` queued (16 jobs, no job has started at last check). Later source-path commits only corrected module comments in sandbox.py and backup.py to remove overclaims and include the model-record/designation Keychain exclusions; no runtime behavior or tests changed. Later remaining commits are documentation/PR-description updates.
- The run therefore covers all behavior-bearing source/test changes, but is not a completed pass and is not an exact hash match for the latest branch head. If CI completes, inspect every job and record this boundary; if a fresh exact-head run is available, prefer it.
- Current open review findings remain the same seven: three sandbox least-privilege/Mach-proxy residuals and four code/test findings awaiting CI. No review thread is resolved on the basis of a queued run.
