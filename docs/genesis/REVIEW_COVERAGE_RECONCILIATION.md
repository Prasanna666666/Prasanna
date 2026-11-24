# Review coverage reconciliation — 2026-11-23

## Purpose and authority

This document reconciles reviewer activity recovered from prior ChatGPT conversations, the PR #6–#10 archives, and the live PR #8 review API. It is a status ledger, not an assertion that the repository has been exhaustively audited.

Owner constraints remain binding:
- ChatGPT owns architecture, documentation, requirements traceability and independent review.
- Claude owns implementation, tests, debugging and maintenance.
- The owner is project manager and final decision-maker.
- Work remains on PR #8 / `genesis-stage2-foundation`.
- Review-only boundary: do not change application source, tests, build files or configuration; do not merge or approve; do not resolve review threads without owner authorization.

## Reviewer history recovered from prior conversations

### Earlier documentation/architecture review
- Claude was reported to have reviewed all nine Genesis documents and portions of the Atlas implementation.
- Findings included Finance/Health privacy isolation, unproven target-hardware performance, storage/backup/key recovery, excessive first-release scope, and reuse of existing consent/undo/audit/ingestion mechanisms.
- A later Claude confirmation reported Stage 0 complete and Stage 1 accepted/closed, with no contradictions across the nine Genesis documents. Optional wording corrections and an older status inconsistency were incorporated.
- That historical acceptance is limited to Stage 0/Stage 1 documentation. It is not acceptance of Stage 2, Stage 3, later stages, or the current PR head.

### PR #7 and early PR #8 architecture/review sequence
- The Genesis documentation baseline on PR #7 was reported as nine files and 718 lines. ChatGPT's handoff asked Claude to compare requirements with the Atlas implementation and classify implemented, partial, missing and conflicting items.
- The agreed workflow was Claude initial review, ChatGPT reconciliation, Claude validation, implementation audit, bounded developer tasks, Claude implementation, and ChatGPT independent review. GitHub PR discussion was the intended auditable exchange; the owner should not be the manual relay.
- A prior-chat record says ChatGPT independently accepted three PR #8 blockers at exact commit `5cd8817`, with a documentation commit `cb39e13`; PR #9 design was selectively incorporated, not merged wholesale. Later G-O19 corrections were accepted at `8046df3`. These short SHAs are historical pointers and must be resolved to full commit SHAs before treating them as exact evidence.
- The same historical record says source sensitivity, revocation and atomic persistence remained unresolved at that point. Later review rounds addressed some revocation paths, but the current-head status must be established from the full defect/thread ledger, not inferred from those earlier acceptances.

### PR #8 independent review/re-review history
- The recorded review sequence began with Stage 2 security blockers: checkpointed evidence after grant revocation, model-context/token binding, and the dedicated Keychain-backed task key. Follow-up reviews examined zero-citation answer leakage, truthful revocation messaging, crash windows around retrieval, attempted-versus-confirmed retrieval semantics, source sensitivity, and recovery/acceptance boundaries.
- Later review records covered Stage 3 requirements and implementation, including source permissions, Mail ingestion and attachment-byte boundaries, app lifecycle and Core process ownership, default-deny onboarding, sandbox confinement, egress tainting, evidence classification, and target-Mac acceptance limits.
- Review bodies and developer replies must be treated separately. Replies containing the Claude Code attribution are implementation claims, not independent proof that a fix works. Every fix claim needs exact-head source/test evidence and re-review.

### Identity limitation
The live GitHub API reports all 53 review submissions and all 63 inline comments under the repository owner's GitHub login. Some replies are explicitly attributed in their text to Claude Code. The GitHub author field therefore does not establish 53 distinct human reviewers. This ledger describes the work by role and evidence, not by inventing separate identities.

## PR #6–#10 reviewer-record inventory

The historical archive captured these top-level conversation-comment counts: PR #6: 41; PR #7: 64; PR #8: 192; PR #9: 1; PR #10: 1. The live formal-review API returned no submitted review objects or inline review threads for PRs #6, #7, #9 or #10; PR #8 is the only one in this set with the 53 formal review submissions and 58 inline threads described below. This does not mean those other PRs had no review activity: their conversation comments and prior-chat review handoffs are separate records and must be read from the archives. The current changed-file API counts observed for PRs #6/#7/#9/#10 were 545/12/1/4 respectively; PR #6's 545 current changed paths must not be confused with the 541-entry legacy coverage matrix.

## Live PR #8 snapshot

- PR: #8, open and draft; unmerged.
- Branch: `genesis-stage2-foundation`.
- Head observed: `4269f6340af1d5c75ca132cab33500fd130db945`.
- Changed paths returned by the paginated PR filename endpoint before this report was added: **276**. After adding this report, the README index and HIST-090, the count was 277. Subsequent concurrent documentation work added `BRANCH_HISTORY_RECONCILIATION.md`; the latest observed PR changed-path count is **278**.
- Submitted review records: **53**; all have state `COMMENTED`; 48 have non-empty review bodies and 5 are empty.
- Inline review threads: **58**; **21 resolved**, **37 unresolved**.
- Inline comments: **63**.
- Threads marked outdated: **43**. Outdated does not mean resolved or revalidated.
- Historical PR #8 conversation archive: 192 top-level issue comments. Keep that count separate from review submissions and inline comments.
- Historical PR #6 matrix: 541 entries. It is a separate legacy inventory, not the current PR #8 file count.
- Earlier “266 files” is a historical scope figure whose exact snapshot still needs reconciliation. The current PR #8 count is 276, not 266 or 275.

## Unresolved inline review threads by path

The live API reports 37 unresolved threads across these 20 paths:

| Path | Unresolved threads |
|---|---:|
| `app/Sources/AtlasApp/AtlasApp.swift` | 6 |
| `core/src/atlas_core/macos.py` | 7 |
| `core/src/atlas_core/sandbox.py` | 3 |
| `app/Sources/AtlasKit/CoreLauncher.swift` | 3 |
| `core/docs/STAGE3_ACCEPTANCE.md` | 11 |
| `core/docs/MACOS_PROVIDERS.md` | 1 |
| `core/docs/STAGE3_HANDOVER.md` | 1 |
| `core/src/atlas_core/worker.py` | 1 |
| `core/src/atlas_core/transport.py` | 1 |
| `docs/genesis/STAGE-3-EXECUTION-PLAN.md` | 1 |
| `core/src/atlas_core/egress.py` | 2 |
| **Total** | **37** |

Other paths have historical threads that are now marked resolved. Their original findings and fix claims remain part of the audit history and must still be sampled/revalidated against the current head where they affect current requirements.

## Remaining work — explicit and measurable

### A. Review-thread closure and fix verification
1. Claude must address the 37 unresolved threads, prioritising security/privacy and release-gate issues.
2. For each thread, record: original finding, affected requirement, fix commit, changed paths, regression test(s), exact CI run, residual limitation, and independent re-review result.
3. Revalidate all 43 outdated threads against current code and contracts; do not equate outdated with fixed.
4. Keep the 11 unresolved `STAGE3_ACCEPTANCE.md` threads open in the acceptance ledger until the evidence and wording are reconciled. Documentation cannot turn owner-only gates into completed engineering evidence.
5. Preserve all 63 inline comment IDs and all 58 thread IDs. Do not merge duplicates without explicit cross-links.

### B. Full 278-path inventory
The 276 paths are an inventory, not reviewed coverage. Create a path-by-path ledger with at least:
- path and file type;
- lines/units reviewed (or explicitly not reviewed);
- reviewer and review date;
- requirements/design/contracts mapped;
- tests and evidence inspected;
- findings/defect IDs;
- status: NOT STARTED, IN REVIEW, REVIEWED—FINDINGS OPEN, REVIEWED—NO FINDINGS, or BLOCKED;
- exact commit SHA.

Classify every path as application source, tests, documentation, schema/API contract, build/workflow/configuration, generated/archive, or asset. Reconcile the earlier 266-path snapshot to the current 276-path list with a path-level addition/removal/rename explanation. Do not infer the ten-path delta.

### C. Documentation owned by ChatGPT
The documentation review must reconcile, without editing code/tests/build/config:
- `docs/genesis/PRD.md`, `DECISIONS.md`, `TARGET_ARCHITECTURE.md`, `LOW_LEVEL_DESIGN.md`, `UI_UX_SPECIFICATION.md`, `HANDOVER.md`, `DELIVERY_PROTOCOL.md`, `STAGE-2-WORK-PACKAGE.md`, `STAGE-3-EXECUTION-PLAN.md`, `STAGE-3-BASELINE-AUDIT.md`, and `DEFECT_REGISTER.md`;
- `core/docs/PROGRAMME_AUDIT.md`, `STAGE3_ACCEPTANCE.md`, `STAGE3_TRACEABILITY.md`, `STAGE3_HANDOVER.md`, `MACOS_PROVIDERS.md`, `EGRESS_GATEWAY.md`, `THREAT_REVIEW.md`, `OWNER_ACCEPTANCE_CHECKLIST.md`, `STAGES_4_TO_8.md`, and the work-package documents.
- Reconcile evidence labels (Linux synthetic, hosted macOS CI, owner-Mac, human walkthrough, real Mail/TCC, real Internet, real model) consistently. A CI run is not owner-Mac acceptance.
- Reconcile Stage 3 status and F-4/F-11/F-12/F-13 final-stage gates consistently across the PR description, execution plan, acceptance matrix, programme audit and handover.
- Reconcile the current agentic automation/connector target architecture with what is actually wired and tested. Do not present target-state capabilities as implemented.

### D. Owner-only acceptance gates
The current PR description and Stage 3 acceptance records explicitly retain owner-only or final-stage gates, including selected-model injection evaluation, owner-Mac sandbox and egress verification, real-model/target-hardware performance and quality measurements, human UI/accessibility walkthrough, real TCC and Mail-store behaviour, signing/notarisation, and self-contained installation/upgrade/rollback. These are not documentation defects that can be closed by editing prose.

## Coverage statement

As of the observed head, **0 of 278 paths have been established by this reconciliation as fully line-by-line reviewed**. This is not a claim that no earlier reviews inspected code; it means the current exact-head, path-by-path ledger has not yet been produced. The 37 unresolved threads and the inventory reconciliation remain open. No complete 266/276/277/278-file audit, all-functions review, or full functional test execution is claimed.

## Next handoff to Claude

Claude: read this file and the full historical archives. Continue the implementation-side work only within the owner-authorised boundary. Return an exact-head path-by-path review ledger and thread-by-thread fix evidence. Do not change this document's status to complete based on a plan, a green CI run, an outdated thread, or a developer assertion alone. ChatGPT will independently review the documentation/architecture and exact-head evidence; the owner makes acceptance decisions.


## Continuation update — 2026-11-23

**Latest PR head observed before this documentation update:** `85acf6dc89c72d303fa4d79a67bf5a76364d6271`. The live changed-path endpoint returns **278 paths**. The full 278-path, exact-head coverage ledger is still not produced; the “0 of 278 established as fully line-by-line reviewed” statement above remains the honest repository-wide coverage status.

This is a continuation of prior targeted review work, not a reset. The defect register now includes a current-head revalidation section for existing findings and additional source-level findings:
- ATLAS-SEC-014: partially addressed, still open for 1–3-character terms and paraphrases.
- ATLAS-ACT-015: dangerous browser fill/press primitives absent from inspected source; test/CI verification pending.
- ATLAS-SEC-016: still open; browser worker is not OS-confined and its environment allow-list passes HOME and PYTHONPATH.
- ATLAS-SEC-017: connector authority now defaults to revoked and only a positive `ok` check enables it; test/CI verification pending.
- ATLAS-OPS-018: CoreLauncher now checks process start time, socket and data directory and rechecks before force-kill; Swift test/CI verification pending.
- O-1: current Finance model still enforces two decimal places and 100 minor units; three-decimal currencies remain unsupported.
- ATLAS-ACT-019 (P1): Action Gateway approval, completed-action, undo and idempotency state is in-memory; the audit chain persists but does not restore those execution receipts.
- ATLAS-TEST-020 (P2): a Finance test contains an always-true assertion (`... or True`).

The source and relevant test files were inspected for these findings. No test suite was executed, and no finding has been marked VERIFIED FIXED. The implementation-side findings were handed to Claude in PR #8 comment **7113684248**. ChatGPT's review-only boundary remains unchanged: no source, test, build or configuration edits.



## Continuation update — 2026-11-24 (exact-head audit pass)

**Source snapshot audited in this pass:** `4617e1f60dd9719d0a31bec13cdb2f68ec3c47ba` (PR #8 head immediately before this documentation-only ledger update).

### Current live PR #8 status
- PR #8 remains open, draft and unmerged.
- Changed paths: **278**.
- Formal review submissions: **53** (48 non-empty, 5 empty; all attributed by GitHub to the repository owner's login, not 53 independent reviewers).
- Inline review threads: **58** (21 resolved, **37 unresolved**).
- Inline comments: **63**.
- Threads marked outdated: **43**; outdated is not fixed or revalidated.
- Historical top-level conversation comments: **192**.
- Consolidated exact-head path-by-path coverage ledger: **not yet produced**. **0 of 278 paths are established by this ledger as fully line-by-line reviewed.** This is not a claim that no earlier targeted code review occurred.

### Work performed in this pass
Targeted source/test/design review covered sections of:
- Orchestration deadlines, task contracts and tests.
- Swift AppModel task lifecycle, Stop/Undo and Activity/Home rendering.
- EMLX mailbox parsing, MIME boundary handling, MailIndex freshness and instrumented tests.
- Browser workflow primitives, browser worker launch/isolation, egress and connector authority.
- Action Gateway approval/idempotency/undo durability.
- Finance record schema/calculation and historical currency precision.
- Stage 3 acceptance/traceability, PRD/LLD approval-policy consistency and UI specification conformance.
- Backup/restore, restore-drill marker, migration, storage reporting and RecordStore schema handling.
- Device pairing, request authentication/replay, offline sync and iOS phone storage/transport/lifecycle.
- Signed updater extraction/rollback and relay response handling.

This was targeted review, not a claim that every line in each named file or all 278 paths has been reviewed. Tests were inspected but **no test suite or CI run was executed in this pass**.

### Exact-head fix revalidation
- **ATLAS-ACT-015:** VERIFIED FIXED for the identified direct browser `fill`/`press` bypass at this source head: the workflow refuses both primitives, the real route permits GET/HEAD only, and focused tests assert that a self-submitting form cannot complete its POST. This does not accept general browser automation.
- **ATLAS-SEC-017:** VERIFIED FIXED for returned `unreachable`/`unauthorised` connector check verdicts: current authority is revoked unless verdict is `ok`, with tests. New exception path ATLAS-CONN-025 remains open.
- **ATLAS-SEC-016:** OPEN; browser worker still lacks OS-enforced confinement and inherits `HOME`/`PYTHONPATH`.
- **ATLAS-SEC-014:** PARTIALLY ADDRESSED; short 1–3-character identifiers and paraphrases remain outside the guarantee; public egress remains disabled pending owner decision/evidence.
- **ATLAS-ACT-019:** OPEN; Action Gateway approvals/completed/undo/idempotency receipts remain in-memory and do not recover across restart.
- **ATLAS-OPS-018:** not independently dispositioned in this pass; keep pending.
- **ATLAS-HIST-063 / O-1:** OPEN; current Finance model remains fixed to two decimal places/hundredths.
- **ATLAS-TEST-020:** confirmed at this head (`... or True`); the following assertion checks the expected monthly totals, so impact is limited but the vacuous assertion must be corrected.
- **ATLAS-DES-020:** OPEN; LLD approval tiers still conflict with the PRD's closed approval list.

### Additional findings logged on PR #8 during this pass

| ID | Severity | Current disposition |
|---|---|---|
| ATLAS-ORCH-021 | P1 | OPEN — per-task/global deadlines and cancellation do not bound an in-flight executor |
| ATLAS-UI-022 | P2 | OPEN — Stop can target a stale task ID during new submission |
| ATLAS-UI-023 | P2 | OPEN — failed Undo silently clears the Undo affordance |
| ATLAS-MAIL-024 | P2 | OPEN — same-size/same-mtime edits can evade re-indexing while content-hash guards suppress retrieval |
| ATLAS-CONN-025 | P1 | OPEN — adapter exception during explicit re-check can leave previous authority enabled |
| ATLAS-ACT-026 | P1 | OPEN — ambiguous handler failure is not idempotently recorded; retry can repeat external effects |
| ATLAS-FIN-029 | P1 | OPEN — mixed currencies are aggregated and summaries default-label EUR |
| ATLAS-DOC-030 | P2 | OPEN — Stage 3 acceptance/traceability contradicts itself on egress wiring and artifact scanning |
| ATLAS-UI-031 | P2 | OPEN — Home/Activity history is process-memory-only and disappears after relaunch |
| ATLAS-MAIL-032 | P1 | OPEN — malformed nested MIME can scan beyond an enclosing multipart closing delimiter |
| ATLAS-BACKUP-034 | P1 | OPEN — untrusted manifest paths/symlinks can make verification read outside the selected backup folder |
| ATLAS-BACKUP-035 | P1 | OPEN — restore target symlink can redirect writes outside the intended target |
| ATLAS-BACKUP-036 | P1 | OPEN — restore verifies backup files, then copies mutable paths without checking copied hashes |
| ATLAS-BACKUP-037 | P2 | OPEN — naive/future restore-drill timestamps can crash or falsely pass the gate |
| ATLAS-OPS-038 | P2 | OPEN — storage breakdown misclassifies newer durable stores as “other” |
| ATLAS-MIG-039 | P2 | OPEN — mid-write Finance migration failure can leave partial records |
| ATLAS-SYNC-040 | P1 | OPEN — reusing an offline operation ID with a changed payload after restart can apply a second operation |
| ATLAS-DEV-041 | P1 | OPEN — pairing can fail after the registry has already enrolled/authorised the device |
| ATLAS-UPD-042 | P1 | OPEN — failed first-install/exceptional health check can leave an unhealthy version selected as current |
| ATLAS-UPD-043 | P1 | OPEN — update ZIP has no aggregate expanded-byte/compression-ratio limit |
| ATLAS-HEALTH-045 | P2 | OPEN — paused/incomplete index can be reported healthy |
| ATLAS-STORE-046 | P2 | OPEN — newer unsupported RecordStore schema is modified by DDL before refusal |
| ATLAS-HEALTH-047 | P2 | OPEN — system diagnostics and permission reset exist only as isolated functions; no running API/UI integration |
| ATLAS-IOS-050 | P2 | OPEN — duplicate pairing query keys can trap/crash the phone parser |
| ATLAS-IOS-051 | P1 | OPEN — offline queue persistence errors/corruption silently lose pending edits |
| ATLAS-IOS-052 | P1 | OPEN — unauthenticated response is treated as revocation and erases queue/cache |
| ATLAS-IOS-053 | P1 | OPEN — detached tasks concurrently mutate a non-thread-safe PhoneEngine/OfflineQueue |
| ATLAS-IOS-054 | P2 | OPEN — unpair during in-flight Ask can index a cleared turn array |
| ATLAS-IOS-055 | P2 | OPEN — a stored pairing is presented as online before a successful Core request |
| ATLAS-IOS-056 | P2 | OPEN — phone Ask polling has no deadline/cancellation bound |
| ATLAS-IOS-057 | P2 | OPEN — phone Archive has no reachable Undo receipt/path |
| ATLAS-IOS-060 | P1 | OPEN — 4 MB response limit is checked after URLSession buffers the full response |
| ATLAS-IOS-061 | P1 | OPEN — unbatched offline queue can exceed the 64 KiB Core/relay request limit |
| ATLAS-RELAY-063 | P1 | OPEN — relay has no response-byte cap |
| ATLAS-SEC-067 | P1 | OPEN — nonce replay cache is memory-only; captured request can replay after Core restart within timestamp window |
| ATLAS-SEC-068 | P1 | OPEN — client revocation registry rename is not fsync/directory-fsync durable |
| ATLAS-UI-069 | P2 | OPEN — always-present Home “Your review” card conflicts with the approved Home content order/density limit |
| ATLAS-IOS-070 | P1 | OPEN — paired Core fingerprint is never checked on subsequent phone responses |
| ATLAS-BACKUP-071 | P1 | OPEN — backup restores active client public keys but omits device metadata needed to list/revoke them |

IDs intentionally retain the PR comment/register identifiers; gaps are not evidence that no findings exist. Each finding has a separate PR comment with source location, impact, remediation and requested regression proof.

### Branch reconciliation update
Compared all 12 live branches against PR #8 head:
- `genesis-stage4-6`: 8 ahead / 107 behind, diverged; 8 unique commits and 61 paths in compare diff. Exact tree: PR #8 has 724 files, Stage 4–6 has 637; 87 paths exist only in PR #8, 0 only in Stage 4–6, and 46 common paths have different blob SHAs.
- `genesis-stage3-prep`: 4 ahead / 245 behind, documentation-only divergence.
- `atlas-low-level-design-review`: 1 ahead / 336 behind, LLD document only.
- Two Dependabot branches and Orbit each have one unique commit; the other three historical branches are behind with no unique commits.
- Content comparison samples show PR #8 has later safety/authorization changes than Stage 4–6 (for example, browser fill/press refusal, connector authority gating, newer backup set and updater operations). The Stage 4–6 branch is not a clean merge candidate. Full 61-path/8-commit content mapping remains OPEN; no merge/cherry-pick performed.

### Remaining work — no completion claim
1. Produce the exact 278-path ledger with file type, reviewed line ranges, requirement/design mapping, tests/evidence, findings, reviewer, status and exact SHA.
2. Reconcile the earlier 266-path inventory path by path to 278; do not infer the delta.
3. Revalidate all 37 unresolved threads and all 43 outdated threads, with exact fixing commit/test/CI evidence; preserve thread IDs and do not resolve without owner authorization.
4. Complete content-level review of all Stage 4–6 divergent commits/61 paths and the Stage 3-prep/LLD-review documentation branches.
5. Complete requirements and design traceability across PRD, decisions, architecture, LLD, UI spec, API schemas, acceptance, programme audit and work-package docs.
6. Keep Stage 3 NOT ACCEPTED pending owner-Mac sandbox/egress, real-model/target-hardware performance, human UI/accessibility walkthrough, real TCC/Mail-store, signing/notarisation and self-contained install evidence.
7. Keep Stage 4–8 NOT ACCEPTED until each stage has its own exact-head implementation, tests, owner evidence and acceptance.

**Boundary:** no application source, tests, build files or configuration were changed. This continuation updates only the review-coverage documentation; no PR approval, merge, branch operation or review-thread resolution was performed.


## Additional exact-head findings — continued source audit

The following findings were added after the previous ledger commit. Each has a detailed PR comment with reproduction/source evidence/remediation; all remain OPEN.

| ID | Severity | Finding |
|---|---|---|
| ATLAS-IOS-050 | P2 | Duplicate pairing query keys can crash the phone parser |
| ATLAS-IOS-051 | P1 | Offline queue write/read/decode failures silently lose pending edits; backup exclusion errors are suppressed |
| ATLAS-IOS-052 | P1 | Any unauthenticated response is treated as revocation and erases queue/cache |
| ATLAS-IOS-053 | P1 | Detached tasks concurrently mutate non-thread-safe PhoneEngine/OfflineQueue |
| ATLAS-IOS-054 | P2 | Unpair during an in-flight Ask can index a cleared turn array |
| ATLAS-IOS-055 | P2 | A stored pairing is presented as online before a successful Core request |
| ATLAS-IOS-056 | P2 | Phone Ask polling has no deadline/cancellation bound |
| ATLAS-IOS-057 | P2 | Phone Archive has no reachable Undo receipt/path |
| ATLAS-IOS-060 | P1 | Phone response limit is checked after URLSession buffers the full response |
| ATLAS-IOS-061 | P1 | Unbatched offline queue can exceed the 64 KiB Core/relay request limit |
| ATLAS-RELAY-063 | P1 | Relay has no response-byte cap |
| ATLAS-SEC-067 | P1 | Memory-only nonce cache permits signed-request replay after Core restart within timestamp window |
| ATLAS-SEC-068 | P1 | Client revocation registry rename lacks file and directory fsync durability |
| ATLAS-UI-069 | P2 | Always-present Home “Your review” card conflicts with approved Home density/content order |
| ATLAS-IOS-070 | P1 | Paired Core fingerprint is never checked on subsequent phone responses |
| ATLAS-BACKUP-071 | P1 | Backup restores active client keys but omits device metadata needed to list/revoke them |
| ATLAS-ANS-075 | P2 | Non-numeric factual claim can be marked verified by an unrelated valid citation |
| ATLAS-ANS-076 | P1 | Generic one-decimal rounding tolerance can mark a one-cent monetary discrepancy verified |
| ATLAS-ANS-077 | P1 | Numeric verification discards negative signs, equating positive and negative values |
| ATLAS-SEC-083 | P1 | Enrolled device can submit TaskRequest scoped to Finance/Health; task creation lacks caller-role enforcement |
| ATLAS-SEC-084 | P2 | Task read/answer/events/receipt/cancel routes are not bound to the authenticated client |

**ATLAS-SEC-083 scope clarification:** API 1.1 requires non-empty `source_scope`; the concrete bypass is an explicit `["finance"]` or `["health"]` scope. `SourceType` is pattern-based, and policy rules define both types. The earlier comment's omitted-scope wording is superseded by the clarification comment.



## Exact-head path inventory — refreshed 2026-11-24

**Inventory source:** paginated GitHub changed-filename endpoint for PR #8 head `14c42d9cb4d546484077090af939b85a5ce6440e`. This is a documentation-only source head; application source remains identical to the reviewed source snapshot `4617e1f60dd9719d0a31bec13cdb2f68ec3c47ba`.

- Exact changed paths: **278**
- Paths with targeted inspection recorded: **94**
- Paths not yet started: **184**
- Paths established as fully line-by-line reviewed: **0**
- Categories: build/config 6; documentation 62; source 108; test 88; benchmark 2; contract/schema 5; evaluation 3; script/tool 4.
- `IN REVIEW` means only the units/ranges shown were inspected. It does not mean the entire file was reviewed or accepted. All tests were inspected selectively; **no test suite or CI was run** in this pass.

| Path | Type | Status | Units inspected |
|---|---|---|---|
| `.github/workflows/ci.yml` | build/config | IN REVIEW | Targeted install/SQLCipher/macOS/security job sections |
| `.gitleaksignore` | build/config | NOT STARTED | — |
| `CLAUDE.md` | documentation | NOT STARTED | — |
| `app/Package.swift` | build/config | NOT STARTED | — |
| `app/README.md` | documentation | NOT STARTED | — |
| `app/Sources/AtlasApp/AtlasApp.swift` | source | IN REVIEW | Targeted: 1–80, 110–170, 200–245, 486–553 |
| `app/Sources/AtlasApp/Components.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasApp/DesignSystem.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasApp/Screens.swift` | source | IN REVIEW | Targeted: 1–75, 179, 579–595, 600–772 |
| `app/Sources/AtlasApp/Shell.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasApp/Speaker.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasApp/Speech.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/Activity.swift` | source | IN REVIEW | 1–47 (full file) |
| `app/Sources/AtlasKit/Aloud.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/AnswerView.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/Approval.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/Catalogue.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/Connections.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/CoreClient.swift` | source | IN REVIEW | 1–119 (full file) |
| `app/Sources/AtlasKit/CoreLauncher.swift` | source | IN REVIEW | Full source; process identity/lifecycle sections |
| `app/Sources/AtlasKit/Finance.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/GetStarted.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/HTTPTransport.swift` | source | IN REVIEW | 1–42 (full file) |
| `app/Sources/AtlasKit/Health.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/Library.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/Lifecycle.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/Navigation.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/Notifications.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/OfflineSync.swift` | source | IN REVIEW | 1–74 (full file) |
| `app/Sources/AtlasKit/Pairing.swift` | source | IN REVIEW | 1–67 (full file) |
| `app/Sources/AtlasKit/PhoneEngine.swift` | source | IN REVIEW | Full source; 1–124 |
| `app/Sources/AtlasKit/Records.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/RelayBind.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/Review.swift` | source | IN REVIEW | 1–38 (full file) |
| `app/Sources/AtlasKit/ScreenState.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/Signing.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/SubmissionGate.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/Tokens.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/Transport.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/Updates.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/Voice.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/Web.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/ux_catalogue.json` | source | NOT STARTED | — |
| `app/Tests/AtlasKitTests/AloudTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/ConnectionsTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/DesignSystemTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/EndToEndTests.swift` | test | IN REVIEW | Targeted: 61–200 |
| `app/Tests/AtlasKitTests/FinanceTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/GetStartedTests.swift` | test | IN REVIEW | Full test file |
| `app/Tests/AtlasKitTests/HealthTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/LibraryTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/NotificationTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/PhoneTests.swift` | test | IN REVIEW | Targeted phone revocation/queue cases |
| `app/Tests/AtlasKitTests/ReapIdentityTests.swift` | test | IN REVIEW | Full test file |
| `app/Tests/AtlasKitTests/RecordsTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/ReviewTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/SigningTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/SubmissionGateTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/UpdateTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/VoiceTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/WebTests.swift` | test | NOT STARTED | — |
| `app/xcode/AtlasMacUITests/AccessibilityAuditTests.swift` | test | NOT STARTED | — |
| `app/xcode/project.yml` | build/config | NOT STARTED | — |
| `core/README.md` | documentation | NOT STARTED | — |
| `core/bench/ingest.py` | benchmark | NOT STARTED | — |
| `core/bench/overhead.py` | benchmark | NOT STARTED | — |
| `core/client/atlas_client.py` | source | NOT STARTED | — |
| `core/client/ux_catalogue.json` | source | NOT STARTED | — |
| `core/contracts/atlas-contracts.1.1.delta.schema.json` | contract/schema | NOT STARTED | — |
| `core/contracts/atlas-contracts.1.1.schema.json` | contract/schema | IN REVIEW | TaskRequest and SourceType definitions inspected |
| `core/contracts/atlas-contracts.schema.json` | contract/schema | NOT STARTED | — |
| `core/contracts/openapi-1.1.yaml` | contract/schema | NOT STARTED | — |
| `core/contracts/openapi.yaml` | contract/schema | NOT STARTED | — |
| `core/docs/ADR_STORAGE_KEYS.md` | documentation | NOT STARTED | — |
| `core/docs/BENCHMARK.md` | documentation | NOT STARTED | — |
| `core/docs/CONNECTOR_PROFILE.md` | documentation | NOT STARTED | — |
| `core/docs/CONTRACT_1_1.md` | documentation | NOT STARTED | — |
| `core/docs/DESIGN.md` | documentation | NOT STARTED | — |
| `core/docs/EGRESS_GATEWAY.md` | documentation | NOT STARTED | — |
| `core/docs/ENROLMENT.md` | documentation | NOT STARTED | — |
| `core/docs/G_O19_DESIGNATION.md` | documentation | NOT STARTED | — |
| `core/docs/MACOS_PROVIDERS.md` | documentation | NOT STARTED | — |
| `core/docs/MODEL_RUNTIME.md` | documentation | NOT STARTED | — |
| `core/docs/OWNER_ACCEPTANCE_CHECKLIST.md` | documentation | IN REVIEW | Targeted owner gate/evidence statements |
| `core/docs/PLUG_IN_GUIDE.md` | documentation | NOT STARTED | — |
| `core/docs/PROGRAMME_AUDIT.md` | documentation | IN REVIEW | Targeted: 15–45 |
| `core/docs/ROLLBACK.md` | documentation | NOT STARTED | — |
| `core/docs/STAGE3_ACCEPTANCE.md` | documentation | IN REVIEW | Targeted: 1–61 |
| `core/docs/STAGE3_HANDOVER.md` | documentation | NOT STARTED | — |
| `core/docs/STAGE3_TRACEABILITY.md` | documentation | IN REVIEW | Targeted: 1–28 |
| `core/docs/STAGE3_WP3_1_PROPOSAL.md` | documentation | NOT STARTED | — |
| `core/docs/STAGES_4_TO_8.md` | documentation | IN REVIEW | Targeted: 65–102 |
| `core/docs/TEST_PLAN.md` | documentation | NOT STARTED | — |
| `core/docs/THREAT_REVIEW.md` | documentation | NOT STARTED | — |
| `core/docs/TRACEABILITY.md` | documentation | NOT STARTED | — |
| `core/docs/UI_IMPLEMENTATION_MAP.md` | documentation | IN REVIEW | Targeted UI/diagnostics claims |
| `core/docs/WP3_2_DOCUMENTS.md` | documentation | NOT STARTED | — |
| `core/docs/WP3_3_MAIL.md` | documentation | NOT STARTED | — |
| `core/docs/WP3_5_CLIENT.md` | documentation | NOT STARTED | — |
| `core/docs/WP3_6_RELIABILITY.md` | documentation | NOT STARTED | — |
| `core/evals/harness.py` | evaluation | NOT STARTED | — |
| `core/evals/set_v1.json` | evaluation | NOT STARTED | — |
| `core/evals/thresholds_proposed.json` | evaluation | NOT STARTED | — |
| `core/pyproject.toml` | build/config | NOT STARTED | — |
| `core/src/atlas_core/__init__.py` | source | NOT STARTED | — |
| `core/src/atlas_core/access.py` | source | IN REVIEW | Full source inspected |
| `core/src/atlas_core/actions.py` | source | IN REVIEW | Targeted: 100–275 |
| `core/src/atlas_core/answer.py` | source | IN REVIEW | Full source inspected: 1–113 |
| `core/src/atlas_core/api.py` | source | IN REVIEW | Targeted: 131–201, 252–275, 277–306, 318–338, 529–540 |
| `core/src/atlas_core/app.py` | source | IN REVIEW | Targeted: 221–237, 298–310 |
| `core/src/atlas_core/backup.py` | source | IN REVIEW | Full source inspected: 1–405 |
| `core/src/atlas_core/browser.py` | source | IN REVIEW | Full source inspected |
| `core/src/atlas_core/browser_engine.py` | source | IN REVIEW | Full source inspected: 1–260 |
| `core/src/atlas_core/browser_worker.py` | source | IN REVIEW | Full source inspected |
| `core/src/atlas_core/confinement.py` | source | NOT STARTED | — |
| `core/src/atlas_core/connector_transport.py` | source | NOT STARTED | — |
| `core/src/atlas_core/connectors.json` | source | NOT STARTED | — |
| `core/src/atlas_core/connectors.py` | source | IN REVIEW | Full source inspected: 1–280 |
| `core/src/atlas_core/consent.py` | source | IN REVIEW | Full source inspected |
| `core/src/atlas_core/contracts.py` | source | NOT STARTED | — |
| `core/src/atlas_core/coverage.py` | source | NOT STARTED | — |
| `core/src/atlas_core/designation.py` | source | IN REVIEW | Targeted: 1–180, 201–370, 471–575 |
| `core/src/atlas_core/devices.py` | source | IN REVIEW | Full source inspected |
| `core/src/atlas_core/documents.py` | source | NOT STARTED | — |
| `core/src/atlas_core/egress.py` | source | IN REVIEW | Targeted: 1–120, 150–220, 250–409 |
| `core/src/atlas_core/errors.py` | source | NOT STARTED | — |
| `core/src/atlas_core/events.py` | source | NOT STARTED | — |
| `core/src/atlas_core/evidence.py` | source | IN REVIEW | Full source inspected |
| `core/src/atlas_core/exact.py` | source | NOT STARTED | — |
| `core/src/atlas_core/finance_calc.py` | source | IN REVIEW | Full source inspected: 1–187 |
| `core/src/atlas_core/gate.py` | source | IN REVIEW | Full source inspected |
| `core/src/atlas_core/health.py` | source | IN REVIEW | Full source inspected |
| `core/src/atlas_core/health_calc.py` | source | IN REVIEW | Full source inspected |
| `core/src/atlas_core/host.py` | source | IN REVIEW | Targeted host options/factory/keychain wiring |
| `core/src/atlas_core/identity.py` | source | IN REVIEW | Full source inspected: 1–230 |
| `core/src/atlas_core/intelligence.py` | source | NOT STARTED | — |
| `core/src/atlas_core/isolated.py` | source | NOT STARTED | — |
| `core/src/atlas_core/launchagent.py` | source | NOT STARTED | — |
| `core/src/atlas_core/launcher.py` | source | NOT STARTED | — |
| `core/src/atlas_core/macos.py` | source | IN REVIEW | Full source inspected: 1–560 |
| `core/src/atlas_core/macos_sources.py` | source | NOT STARTED | — |
| `core/src/atlas_core/mail.py` | source | IN REVIEW | Targeted: 280–490 |
| `core/src/atlas_core/maintenance.py` | source | IN REVIEW | Targeted: 21–32, 105–132 |
| `core/src/atlas_core/migration.py` | source | IN REVIEW | Full source inspected: 1–192 |
| `core/src/atlas_core/mlx_runtime.py` | source | IN REVIEW | Full source inspected: 1–135 |
| `core/src/atlas_core/models.py` | source | IN REVIEW | Targeted model runtime/validation interfaces |
| `core/src/atlas_core/operations.py` | source | IN REVIEW | Targeted action/sync wiring |
| `core/src/atlas_core/orchestrator.py` | source | IN REVIEW | Full source inspected: 1–242 |
| `core/src/atlas_core/policy-rules.json` | source | IN REVIEW | Targeted: 69–93 |
| `core/src/atlas_core/policy.py` | source | IN REVIEW | Full source inspected |
| `core/src/atlas_core/record_actions.py` | source | NOT STARTED | — |
| `core/src/atlas_core/records.py` | source | IN REVIEW | Full source inspected |
| `core/src/atlas_core/recordstore.py` | source | IN REVIEW | Targeted: 1–90 |
| `core/src/atlas_core/relay.py` | source | IN REVIEW | Full source inspected |
| `core/src/atlas_core/review.py` | source | IN REVIEW | Full source inspected: 1–141 |
| `core/src/atlas_core/rules.py` | source | NOT STARTED | — |
| `core/src/atlas_core/sandbox.py` | source | IN REVIEW | Targeted: 65–165 |
| `core/src/atlas_core/serve.py` | source | IN REVIEW | Targeted CLI flags/options |
| `core/src/atlas_core/service.py` | source | IN REVIEW | Targeted: 126–300, 554–621 |
| `core/src/atlas_core/storage.py` | source | IN REVIEW | Full source inspected |
| `core/src/atlas_core/sync.py` | source | IN REVIEW | Full source inspected |
| `core/src/atlas_core/tasks.py` | source | IN REVIEW | Full source inspected |
| `core/src/atlas_core/transport.py` | source | IN REVIEW | Full source inspected: 1–202 |
| `core/src/atlas_core/updater.py` | source | IN REVIEW | Full source inspected |
| `core/src/atlas_core/values.py` | source | NOT STARTED | — |
| `core/src/atlas_core/watchers.py` | source | NOT STARTED | — |
| `core/src/atlas_core/web.py` | source | IN REVIEW | Targeted: 30–121 |
| `core/src/atlas_core/worker.py` | source | IN REVIEW | Full source inspected: 1–120 |
| `core/tests/conftest.py` | test | NOT STARTED | — |
| `core/tests/core_factory.py` | test | NOT STARTED | — |
| `core/tests/test_actions.py` | test | IN REVIEW | Targeted: 211–229 |
| `core/tests/test_api.py` | test | NOT STARTED | — |
| `core/tests/test_api_v11.py` | test | NOT STARTED | — |
| `core/tests/test_app.py` | test | NOT STARTED | — |
| `core/tests/test_architecture.py` | test | NOT STARTED | — |
| `core/tests/test_artefact_scan.py` | test | NOT STARTED | — |
| `core/tests/test_backup.py` | test | IN REVIEW | Full test file |
| `core/tests/test_bench.py` | test | NOT STARTED | — |
| `core/tests/test_browser_engine.py` | test | IN REVIEW | Targeted: 82–90 |
| `core/tests/test_browser_watchers.py` | test | IN REVIEW | Targeted: 64–73 |
| `core/tests/test_client.py` | test | NOT STARTED | — |
| `core/tests/test_connectors.py` | test | IN REVIEW | Targeted: 190–247 |
| `core/tests/test_consent_api.py` | test | NOT STARTED | — |
| `core/tests/test_contracts.py` | test | NOT STARTED | — |
| `core/tests/test_contracts_frozen.py` | test | NOT STARTED | — |
| `core/tests/test_contracts_v11.py` | test | NOT STARTED | — |
| `core/tests/test_designation.py` | test | NOT STARTED | — |
| `core/tests/test_devices.py` | test | IN REVIEW | Full test file |
| `core/tests/test_documents.py` | test | NOT STARTED | — |
| `core/tests/test_domains.py` | test | NOT STARTED | — |
| `core/tests/test_egress.py` | test | IN REVIEW | Targeted taint/host/redirect tests |
| `core/tests/test_enrolment.py` | test | NOT STARTED | — |
| `core/tests/test_evals.py` | test | NOT STARTED | — |
| `core/tests/test_evidence_answer.py` | test | IN REVIEW | Full test file inspected |
| `core/tests/test_exact.py` | test | NOT STARTED | — |
| `core/tests/test_finance_calc.py` | test | IN REVIEW | Full test file |
| `core/tests/test_health.py` | test | IN REVIEW | Full test file |
| `core/tests/test_intelligence.py` | test | NOT STARTED | — |
| `core/tests/test_isolated.py` | test | IN REVIEW | Targeted: 311–345 |
| `core/tests/test_launchagent.py` | test | NOT STARTED | — |
| `core/tests/test_launcher.py` | test | NOT STARTED | — |
| `core/tests/test_library.py` | test | NOT STARTED | — |
| `core/tests/test_macos.py` | test | IN REVIEW | Targeted: 219–225, 430–520, 580–710 |
| `core/tests/test_macos_native.py` | test | NOT STARTED | — |
| `core/tests/test_macos_sources.py` | test | NOT STARTED | — |
| `core/tests/test_mail.py` | test | NOT STARTED | — |
| `core/tests/test_maintenance.py` | test | NOT STARTED | — |
| `core/tests/test_migration.py` | test | NOT STARTED | — |
| `core/tests/test_mlx_native.py` | test | NOT STARTED | — |
| `core/tests/test_mlx_runtime.py` | test | NOT STARTED | — |
| `core/tests/test_models.py` | test | NOT STARTED | — |
| `core/tests/test_operations_api.py` | test | NOT STARTED | — |
| `core/tests/test_orchestrator.py` | test | IN REVIEW | Full test file |
| `core/tests/test_policy.py` | test | NOT STARTED | — |
| `core/tests/test_recordstore.py` | test | NOT STARTED | — |
| `core/tests/test_redaction.py` | test | NOT STARTED | — |
| `core/tests/test_relay.py` | test | IN REVIEW | Full test file |
| `core/tests/test_reliability.py` | test | NOT STARTED | — |
| `core/tests/test_research.py` | test | NOT STARTED | — |
| `core/tests/test_retention.py` | test | NOT STARTED | — |
| `core/tests/test_review_fixes.py` | test | NOT STARTED | — |
| `core/tests/test_review_round2.py` | test | NOT STARTED | — |
| `core/tests/test_review_round3.py` | test | NOT STARTED | — |
| `core/tests/test_search_index.py` | test | NOT STARTED | — |
| `core/tests/test_signing_script.py` | test | NOT STARTED | — |
| `core/tests/test_stage3_acceptance.py` | test | NOT STARTED | — |
| `core/tests/test_stages_4_8_docs.py` | test | NOT STARTED | — |
| `core/tests/test_storage.py` | test | IN REVIEW | Targeted: 64–84 |
| `core/tests/test_swift_app_sources.py` | test | NOT STARTED | — |
| `core/tests/test_sync.py` | test | IN REVIEW | Full test file |
| `core/tests/test_tasks.py` | test | NOT STARTED | — |
| `core/tests/test_thresholds.py` | test | NOT STARTED | — |
| `core/tests/test_transport.py` | test | NOT STARTED | — |
| `core/tests/test_updater.py` | test | IN REVIEW | Full test file |
| `core/tests/test_web.py` | test | NOT STARTED | — |
| `core/tests/worker_engines.py` | test | NOT STARTED | — |
| `core/tools/scan_artefacts.py` | script/tool | NOT STARTED | — |
| `docs/README.md` | documentation | NOT STARTED | — |
| `docs/genesis/ADR-G-O17-PLATFORM-RUNTIME.md` | documentation | NOT STARTED | — |
| `docs/genesis/BRANCH_HISTORY_RECONCILIATION.md` | documentation | NOT STARTED | — |
| `docs/genesis/DECISIONS.md` | documentation | NOT STARTED | — |
| `docs/genesis/DEFECT_REGISTER.md` | documentation | IN REVIEW | Targeted: 145–360, 500–540 |
| `docs/genesis/DELIVERY_PROTOCOL.md` | documentation | NOT STARTED | — |
| `docs/genesis/DEPENDABOT_PR1-5_ARCHIVE.md` | documentation | NOT STARTED | — |
| `docs/genesis/HANDOVER.md` | documentation | NOT STARTED | — |
| `docs/genesis/HISTORICAL_PR10_CONVERSATION.md` | documentation | NOT STARTED | — |
| `docs/genesis/HISTORICAL_PR6_CONVERSATION.md` | documentation | NOT STARTED | — |
| `docs/genesis/HISTORICAL_PR6_SOURCE_ARCHIVE.md` | documentation | NOT STARTED | — |
| `docs/genesis/HISTORICAL_PR7_CONVERSATION.md` | documentation | NOT STARTED | — |
| `docs/genesis/HISTORICAL_PR8_CONVERSATION.md` | documentation | NOT STARTED | — |
| `docs/genesis/HISTORICAL_PR8_REVIEW_THREADS.md` | documentation | NOT STARTED | — |
| `docs/genesis/HISTORICAL_PR9_CONVERSATION.md` | documentation | NOT STARTED | — |
| `docs/genesis/INGESTION_PIPELINE.md` | documentation | NOT STARTED | — |
| `docs/genesis/INTELLIGENCE_AND_PERFORMANCE.md` | documentation | NOT STARTED | — |
| `docs/genesis/INTERNET_AND_NETWORK_POLICY.md` | documentation | NOT STARTED | — |
| `docs/genesis/LOW_LEVEL_DESIGN.md` | documentation | IN REVIEW | Targeted: §11.5, 404–409 |
| `docs/genesis/MEMORY_PRIVACY_KNOWLEDGE.md` | documentation | NOT STARTED | — |
| `docs/genesis/PRD.md` | documentation | IN REVIEW | Targeted: §4.4/§4.5, 64–90 |
| `docs/genesis/PRIOR_CONVERSATION_RECOVERY.md` | documentation | NOT STARTED | — |
| `docs/genesis/README.md` | documentation | NOT STARTED | — |
| `docs/genesis/REVIEW_COVERAGE_RECONCILIATION.md` | documentation | IN REVIEW | Full current ledger read and updated |
| `docs/genesis/STAGE-2-WORK-PACKAGE.md` | documentation | NOT STARTED | — |
| `docs/genesis/STAGE-3-BASELINE-AUDIT.md` | documentation | NOT STARTED | — |
| `docs/genesis/STAGE-3-CONTRACT-DELTA.md` | documentation | NOT STARTED | — |
| `docs/genesis/STAGE-3-EXECUTION-PLAN.md` | documentation | IN REVIEW | Targeted: 1–65, 330–390 |
| `docs/genesis/TARGET_ARCHITECTURE.md` | documentation | NOT STARTED | — |
| `docs/genesis/UI_UX_SPECIFICATION.md` | documentation | IN REVIEW | Targeted: 23–60, 79–135, 183–330 |
| `docs/genesis/USE_CASE_REGISTER.md` | documentation | NOT STARTED | — |
| `ios/AtlasPhone/AtlasPhoneApp.swift` | source | NOT STARTED | — |
| `ios/AtlasPhone/PhoneModel.swift` | source | IN REVIEW | 1–100 (full file) |
| `ios/AtlasPhone/Storage.swift` | source | IN REVIEW | 1–54 (full file) |
| `ios/AtlasPhone/Views.swift` | source | IN REVIEW | 1–224 (full file) |
| `ios/AtlasPhoneUITests/AccessibilityAuditTests.swift` | test | NOT STARTED | — |
| `ios/README.md` | documentation | NOT STARTED | — |
| `ios/project.yml` | build/config | NOT STARTED | — |
| `scripts/Atlas.entitlements` | script/tool | NOT STARTED | — |
| `scripts/package_mac.sh` | script/tool | IN REVIEW | Targeted: 3–19 |
| `scripts/sign_and_notarize.sh` | script/tool | NOT STARTED | — |

