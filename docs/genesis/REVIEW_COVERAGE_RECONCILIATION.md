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


## Additional exact-head findings — UI, voice, transport and connector pass

All findings below have separate detailed PR comments with source evidence, impact, remediation and required tests. OPEN unless explicitly corrected.

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
| ATLAS-SEC-083 | P2 | Task API drops caller role; latent Finance/Health scope boundary gap (current production policy denies those restricted domains) |
| ATLAS-SEC-084 | P2 | Task read/answer/events/receipt/cancel routes are not bound to the authenticated client |
| ATLAS-FIN-085 | P1 | Stage 5 Finance/Health task-context claim is not wired into production Core composition; only deterministic summary endpoints are available |
| ATLAS-SEC-087 | P1 | Paired phone can bypass its fixed Documents/Mail scope and query owner-enabled Photos through Task API |
| ATLAS-MAC-088 | P2 | Passive Notes permission status check can trigger Automation prompt before owner opts in |
| ATLAS-MAC-089 | P2 | Native sources silently truncate at 5,000 records while index can report complete |
| ATLAS-MAC-090 | P1 | Transient native-source OSError is treated as successful empty snapshot and can delete existing index |
| ATLAS-MAC-091 | P2 | Photos limited-library permission is collapsed into full GRANTED without a limited-coverage signal |
| ATLAS-IOS-094 | P1 | Unpair/revocation silently ignores Keychain and file deletion failures |
| ATLAS-IOS-095 | P2 | Keychain read errors are collapsed into "not paired" with no retry |
| ATLAS-TRANSPORT-098 | P1 | UnixHTTP writes without SO_NOSIGPIPE; peer close can terminate the macOS app |
| ATLAS-TRANSPORT-099 | P2 | Local UnixHTTP has no deadline or response-byte/header cap |
| ATLAS-VOICE-100 | P1 | Ask microphone session is not stopped on navigation/app lifecycle; permission-pending state can restart capture |
| ATLAS-VOICE-102 | P2 | Editing or sending during dictation can overwrite text or submit only partial transcript |
| ATLAS-CONN-103 | P1 | Unexpected exception during connector re-check leaves previous action authority enabled |
| ATLAS-UI-104 | P2 | Enabled Life Areas are flat sidebar rows instead of one grouped section; dynamic rows also shift Command-1…6 targets |

**ATLAS-SEC-083 clarification:** API 1.1 requires a non-empty scope. Production Host currently holds Finance/Health out of DesignationStore, so the Finance/Health route is a latent role-boundary gap, not a demonstrated current read. ATLAS-SEC-087 is the current active source-scope bypass: Photos is a non-restricted, owner-grantable native source and is not included in the phone's intended scope.

**ATLAS-VOICE-100 correction trail:** an intermediate PR comment incorrectly claimed the mic control was not wired. That statement is superseded: the Ask Composer in `Screens.swift` lines 174–177 calls `model.toggleVoice()` and binds `voiceState`; the P1 lifecycle finding stands.



## Exact-head path inventory — refreshed 2026-11-24

**Inventory source:** paginated GitHub changed-filename endpoint for PR #8 head `4a09eca2ada1d4fe69c04c3a7aefa877327e1848`. This is a documentation-only head; source code remains identical to the source snapshot `4617e1f60dd9719d0a31bec13cdb2f68ec3c47ba`.

- Exact changed paths: **278**
- Paths with targeted inspection recorded: **136**
- Paths not yet started: **142**
- Paths established as fully line-by-line reviewed: **0**
- Categories: build/config 6; documentation 62; source 108; test 88; benchmark 2; contract/schema 5; evaluation 3; script/tool 4.
- `IN REVIEW` means only the units/ranges shown were inspected; it does not mean the entire file was reviewed or accepted. No test suite or CI was run in this pass.

| Path | Type | Status | Units inspected |
|---|---|---|---|
| `.github/workflows/ci.yml` | build/config | IN REVIEW | Targeted install/SQLCipher/macOS/security job sections |
| `.gitleaksignore` | build/config | REVIEWED—NO FINDINGS | Full 10 lines; four fingerprint suppressions matched to historical test/type annotation, comment, public checksum and generated test key contexts; scanner execution not independently run |
| `CLAUDE.md` | documentation | REVIEWED—NO FINDINGS | Full 22 lines; source-of-truth, role split, evidence and product principles consistent with current delivery protocol |
| `app/Package.swift` | build/config | REVIEWED—NO FINDINGS | Full 15 lines; AtlasKit-only consumers in macOS/iOS XcodeGen projects align with macOS 14/iOS 17 declarations; no external dependencies |
| `app/README.md` | documentation | IN REVIEW | Full 19 lines; evidence contradiction found: app launch/Core lifecycle and Swift real-Core tests exist, but README says app not run / Swift side not tested; PR review 6045284683 |
| `app/Sources/AtlasApp/AtlasApp.swift` | source | IN REVIEW | Targeted: 1–80, 110–170, 200–245, 320–390, 486–553 |
| `app/Sources/AtlasApp/Components.swift` | source | IN REVIEW | Targeted component/accessibility review |
| `app/Sources/AtlasApp/DesignSystem.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasApp/Screens.swift` | source | IN REVIEW | Targeted: 1–75, 131–191, 179, 579–595, 600–772 |
| `app/Sources/AtlasApp/Shell.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasApp/Speaker.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasApp/Speech.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/Activity.swift` | source | IN REVIEW | 1–47 (full) |
| `app/Sources/AtlasKit/Aloud.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/AnswerView.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/Approval.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/Catalogue.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/Connections.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/CoreClient.swift` | source | IN REVIEW | 1–119 (full) |
| `app/Sources/AtlasKit/CoreLauncher.swift` | source | IN REVIEW | Full source; process identity/lifecycle sections |
| `app/Sources/AtlasKit/Finance.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/GetStarted.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/HTTPTransport.swift` | source | IN REVIEW | 1–42 (full) |
| `app/Sources/AtlasKit/Health.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/Library.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/Lifecycle.swift` | source | IN REVIEW | Targeted task/phase state mapping |
| `app/Sources/AtlasKit/Navigation.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/Notifications.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/OfflineSync.swift` | source | IN REVIEW | 1–74 (full) |
| `app/Sources/AtlasKit/Pairing.swift` | source | IN REVIEW | 1–67 (full) |
| `app/Sources/AtlasKit/PhoneEngine.swift` | source | IN REVIEW | Full source; 1–124 |
| `app/Sources/AtlasKit/Records.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/RelayBind.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/Review.swift` | source | IN REVIEW | 1–38 (full) |
| `app/Sources/AtlasKit/ScreenState.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/Signing.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/SubmissionGate.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/Tokens.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/Transport.swift` | source | IN REVIEW | Full source inspected: 1–52 |
| `app/Sources/AtlasKit/Updates.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/Voice.swift` | source | IN REVIEW | Full source inspected |
| `app/Sources/AtlasKit/Web.swift` | source | NOT STARTED | — |
| `app/Sources/AtlasKit/ux_catalogue.json` | source | NOT STARTED | — |
| `app/Tests/AtlasKitTests/AloudTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/ConnectionsTests.swift` | test | IN REVIEW | Targeted: 1–160 |
| `app/Tests/AtlasKitTests/DesignSystemTests.swift` | test | IN REVIEW | Targeted contrast/accessibility assertions |
| `app/Tests/AtlasKitTests/EndToEndTests.swift` | test | IN REVIEW | Targeted: 61–200 |
| `app/Tests/AtlasKitTests/FinanceTests.swift` | test | IN REVIEW | Targeted outcome cases |
| `app/Tests/AtlasKitTests/GetStartedTests.swift` | test | IN REVIEW | Full test file |
| `app/Tests/AtlasKitTests/HealthTests.swift` | test | IN REVIEW | Targeted outcome cases |
| `app/Tests/AtlasKitTests/LibraryTests.swift` | test | IN REVIEW | Targeted malformed-row/coverage cases |
| `app/Tests/AtlasKitTests/NotificationTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/PhoneTests.swift` | test | IN REVIEW | Targeted phone revocation/queue cases |
| `app/Tests/AtlasKitTests/ReapIdentityTests.swift` | test | IN REVIEW | Full test file |
| `app/Tests/AtlasKitTests/RecordsTests.swift` | test | IN REVIEW | Targeted record outcome/draft cases |
| `app/Tests/AtlasKitTests/ReviewTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/SigningTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/SubmissionGateTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/UpdateTests.swift` | test | NOT STARTED | — |
| `app/Tests/AtlasKitTests/VoiceTests.swift` | test | IN REVIEW | Full test file |
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
| `core/src/atlas_core/answer.py` | source | IN REVIEW | Full: 1–113 |
| `core/src/atlas_core/api.py` | source | IN REVIEW | Targeted: 131–201, 252–275, 277–306, 318–338, 529–540 |
| `core/src/atlas_core/app.py` | source | IN REVIEW | Targeted: 166–208, 230–245, 318–341 |
| `core/src/atlas_core/backup.py` | source | IN REVIEW | Full: 1–405 |
| `core/src/atlas_core/browser.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/browser_engine.py` | source | IN REVIEW | Full: 1–260 |
| `core/src/atlas_core/browser_worker.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/confinement.py` | source | IN REVIEW | Full source: 1–53 |
| `core/src/atlas_core/connector_transport.py` | source | IN REVIEW | Full source inspected |
| `core/src/atlas_core/connectors.json` | source | NOT STARTED | — |
| `core/src/atlas_core/connectors.py` | source | IN REVIEW | Targeted: 91–130, 190–250 |
| `core/src/atlas_core/consent.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/contracts.py` | source | NOT STARTED | — |
| `core/src/atlas_core/coverage.py` | source | NOT STARTED | — |
| `core/src/atlas_core/designation.py` | source | IN REVIEW | Targeted: 1–180, 201–370, 471–575 |
| `core/src/atlas_core/devices.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/documents.py` | source | IN REVIEW | Targeted: 130–255, 285–395 |
| `core/src/atlas_core/egress.py` | source | IN REVIEW | Targeted: 1–120, 150–220, 250–409 |
| `core/src/atlas_core/errors.py` | source | NOT STARTED | — |
| `core/src/atlas_core/events.py` | source | NOT STARTED | — |
| `core/src/atlas_core/evidence.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/exact.py` | source | IN REVIEW | Full source: 1–260; precision defect ATLAS-EXACT-106 |
| `core/src/atlas_core/finance_calc.py` | source | IN REVIEW | Full: 1–187 |
| `core/src/atlas_core/gate.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/health.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/health_calc.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/host.py` | source | IN REVIEW | Targeted: 70–175 |
| `core/src/atlas_core/identity.py` | source | IN REVIEW | Full: 1–230 |
| `core/src/atlas_core/intelligence.py` | source | NOT STARTED | — |
| `core/src/atlas_core/isolated.py` | source | NOT STARTED | — |
| `core/src/atlas_core/launchagent.py` | source | IN REVIEW | Full source: 1–42 |
| `core/src/atlas_core/launcher.py` | source | NOT STARTED | — |
| `core/src/atlas_core/macos.py` | source | IN REVIEW | Full: 1–560 |
| `core/src/atlas_core/macos_sources.py` | source | IN REVIEW | Full: 1–266 |
| `core/src/atlas_core/mail.py` | source | IN REVIEW | Targeted: 278–345, 400–445, 280–490 |
| `core/src/atlas_core/maintenance.py` | source | IN REVIEW | Targeted: 21–32, 105–132 |
| `core/src/atlas_core/migration.py` | source | IN REVIEW | Full: 1–192 |
| `core/src/atlas_core/mlx_runtime.py` | source | IN REVIEW | Full: 1–135 |
| `core/src/atlas_core/models.py` | source | IN REVIEW | Targeted model runtime/validation interfaces |
| `core/src/atlas_core/operations.py` | source | IN REVIEW | Targeted action/sync wiring |
| `core/src/atlas_core/orchestrator.py` | source | IN REVIEW | Full: 1–242 |
| `core/src/atlas_core/policy-rules.json` | source | IN REVIEW | Targeted: 9–45, 70–180 |
| `core/src/atlas_core/policy.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/record_actions.py` | source | IN REVIEW | Full source: 1–56 |
| `core/src/atlas_core/records.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/recordstore.py` | source | IN REVIEW | Targeted: 1–90 |
| `core/src/atlas_core/relay.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/review.py` | source | IN REVIEW | Full: 1–141 |
| `core/src/atlas_core/rules.py` | source | IN REVIEW | Full: 1–34 |
| `core/src/atlas_core/sandbox.py` | source | IN REVIEW | Targeted: 65–165 |
| `core/src/atlas_core/serve.py` | source | IN REVIEW | Targeted CLI flags/options |
| `core/src/atlas_core/service.py` | source | IN REVIEW | Targeted: 126–300, 326–347, 554–621 |
| `core/src/atlas_core/storage.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/sync.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/tasks.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/transport.py` | source | IN REVIEW | Full: 1–202 |
| `core/src/atlas_core/updater.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/values.py` | source | IN REVIEW | Full source: 1–16 |
| `core/src/atlas_core/watchers.py` | source | IN REVIEW | Full source: 1–93 |
| `core/src/atlas_core/web.py` | source | IN REVIEW | Targeted: 30–121 |
| `core/src/atlas_core/worker.py` | source | IN REVIEW | Full: 1–120 |
| `core/tests/conftest.py` | test | NOT STARTED | — |
| `core/tests/core_factory.py` | test | NOT STARTED | — |
| `core/tests/test_actions.py` | test | IN REVIEW | Targeted: 211–229 |
| `core/tests/test_api.py` | test | NOT STARTED | — |
| `core/tests/test_api_v11.py` | test | IN REVIEW | Targeted authenticated task/route tests |
| `core/tests/test_app.py` | test | NOT STARTED | — |
| `core/tests/test_architecture.py` | test | NOT STARTED | — |
| `core/tests/test_artefact_scan.py` | test | NOT STARTED | — |
| `core/tests/test_backup.py` | test | IN REVIEW | Full test file |
| `core/tests/test_bench.py` | test | NOT STARTED | — |
| `core/tests/test_browser_engine.py` | test | IN REVIEW | Targeted: 82–90 |
| `core/tests/test_browser_watchers.py` | test | IN REVIEW | Targeted: 64–73 |
| `core/tests/test_client.py` | test | NOT STARTED | — |
| `core/tests/test_connectors.py` | test | IN REVIEW | Targeted: 190–247 |
| `core/tests/test_consent_api.py` | test | IN REVIEW | Targeted consent API cases |
| `core/tests/test_contracts.py` | test | NOT STARTED | — |
| `core/tests/test_contracts_frozen.py` | test | NOT STARTED | — |
| `core/tests/test_contracts_v11.py` | test | NOT STARTED | — |
| `core/tests/test_designation.py` | test | IN REVIEW | Targeted designable-domain assertion and grant tests |
| `core/tests/test_devices.py` | test | IN REVIEW | Full test file |
| `core/tests/test_documents.py` | test | NOT STARTED | — |
| `core/tests/test_domains.py` | test | NOT STARTED | — |
| `core/tests/test_egress.py` | test | IN REVIEW | Targeted taint/host/redirect tests |
| `core/tests/test_enrolment.py` | test | NOT STARTED | — |
| `core/tests/test_evals.py` | test | NOT STARTED | — |
| `core/tests/test_evidence_answer.py` | test | IN REVIEW | Full test file |
| `core/tests/test_exact.py` | test | IN REVIEW | Full test file; no >28-digit exact-decimal test |
| `core/tests/test_finance_calc.py` | test | IN REVIEW | Full test file |
| `core/tests/test_health.py` | test | IN REVIEW | Full test file |
| `core/tests/test_intelligence.py` | test | NOT STARTED | — |
| `core/tests/test_isolated.py` | test | IN REVIEW | Targeted: 311–345 |
| `core/tests/test_launchagent.py` | test | NOT STARTED | — |
| `core/tests/test_launcher.py` | test | NOT STARTED | — |
| `core/tests/test_library.py` | test | NOT STARTED | — |
| `core/tests/test_macos.py` | test | IN REVIEW | Targeted: 219–225, 430–520, 580–710 |
| `core/tests/test_macos_native.py` | test | NOT STARTED | — |
| `core/tests/test_macos_sources.py` | test | IN REVIEW | Targeted: 57–135 |
| `core/tests/test_mail.py` | test | NOT STARTED | — |
| `core/tests/test_maintenance.py` | test | NOT STARTED | — |
| `core/tests/test_migration.py` | test | NOT STARTED | — |
| `core/tests/test_mlx_native.py` | test | NOT STARTED | — |
| `core/tests/test_mlx_runtime.py` | test | NOT STARTED | — |
| `core/tests/test_models.py` | test | NOT STARTED | — |
| `core/tests/test_operations_api.py` | test | NOT STARTED | — |
| `core/tests/test_orchestrator.py` | test | IN REVIEW | Full test file |
| `core/tests/test_policy.py` | test | IN REVIEW | Targeted: 122–165 |
| `core/tests/test_recordstore.py` | test | IN REVIEW | Targeted schema/unsupported-version cases |
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
| `core/tests/test_tasks.py` | test | IN REVIEW | Targeted task creation/recovery/cancellation tests |
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
| `docs/genesis/UI_UX_SPECIFICATION.md` | documentation | IN REVIEW | Targeted: 23–60, 62–78, 183–330 |
| `docs/genesis/USE_CASE_REGISTER.md` | documentation | NOT STARTED | — |
| `ios/AtlasPhone/AtlasPhoneApp.swift` | source | IN REVIEW | Full source: 1–12 |
| `ios/AtlasPhone/PhoneModel.swift` | source | IN REVIEW | 1–100 (full) |
| `ios/AtlasPhone/Storage.swift` | source | IN REVIEW | 1–54 (full) |
| `ios/AtlasPhone/Views.swift` | source | IN REVIEW | 1–224 (full) |
| `ios/AtlasPhoneUITests/AccessibilityAuditTests.swift` | test | NOT STARTED | — |
| `ios/README.md` | documentation | NOT STARTED | — |
| `ios/project.yml` | build/config | NOT STARTED | — |
| `scripts/Atlas.entitlements` | script/tool | NOT STARTED | — |
| `scripts/package_mac.sh` | script/tool | IN REVIEW | Targeted: 3–19 |
| `scripts/sign_and_notarize.sh` | script/tool | NOT STARTED | — |



## Live continuation — 2026-11-24, PR #8 head 7d4ac42

**Exact review target:** `7d4ac42bf537a10d950818fe91f855817c6c5ade` (branch `genesis-stage2-foundation`, base `atlas` at `7a3b4479bcbb27fb2bab570759ad14851c78e945`). Live PR metadata: open, draft, unmerged; 278 changed paths; +62,948 / 0 deletions. The 278-path inventory and prior 136/142 targeted/not-started split are historical snapshots; this pass does not silently carry those counts forward as current-head coverage.

### Current GitHub review state
- 58 inline threads: 21 resolved, 37 unresolved; 43 marked outdated. Preserve all IDs; outdated is not fixed.
- 53 submitted review records; all attributed by GitHub to the repository owner's login. Historical archive counts remain separate from live review objects.
- No approval, merge, or thread resolution performed by this pass.

### Exact-head source/test/document units inspected in this continuation
Targeted source and test inspection (not full-file certification) included:
- `core/src/atlas_core/egress.py` (409 lines): taint fingerprints, URL/redirect checks, transport and residual guarantee.
- `core/tests/test_egress.py` (336 lines): private-name/phrase, URL encoding, redirect and residual tests.
- `core/src/atlas_core/sandbox.py` (165 lines), `worker.py` (120 lines), `launcher.py` (107 lines), and `core/tests/test_isolated.py`: OS sandbox profile, launch verification and worker startup.
- `core/src/atlas_core/macos.py` (521 lines) and `core/tests/test_macos.py`: bounded EMLX header/MIME scanning, attachment read boundaries and identity revalidation.
- `app/Sources/AtlasApp/AtlasApp.swift` (696 lines), `app/Sources/AtlasKit/CoreLauncher.swift` (166 lines), and `core/src/atlas_core/transport.py` (202 lines): app termination, Core reaping, socket ownership and startup.
- `core/src/atlas_core/browser.py`, `browser_engine.py`, `browser_worker.py`, `actions.py`, `connectors.py`: browser action refusal, worker process boundary, action state and connector authority.
- `core/tests/test_architecture.py`, `core/docs/STAGE3_ACCEPTANCE.md`, `docs/genesis/STAGE-3-EXECUTION-PLAN.md`, this coverage ledger and the defect register.

These are focused sections/symbols, not every line of every named file. No local test suite was run by this reviewer; the CI evidence below was read from GitHub Actions.

### Exact-head CI evidence — failing
Workflow run **45388238509** for this exact head completed with conclusion **failure**. The `macos` job failed at “Core tests on macOS”; its suite summary is **2 failed, 1,401 passed, 3 skipped**. The two failures are:
1. `tests/test_architecture.py::test_canonical_documents_have_no_unlabelled_superseded_policy`: 32 unlabelled historical/superseded policy lines were detected, including in `BRANCH_HISTORY_RECONCILIATION.md`, `HISTORICAL_PR7_CONVERSATION.md`, `HISTORICAL_PR8_CONVERSATION.md`, and `HISTORICAL_PR8_REVIEW_THREADS.md`.
2. `tests/test_architecture.py::test_there_is_exactly_one_delivery_roadmap_and_it_is_in_the_target_architecture`: a second roadmap definition is detected in `HISTORICAL_PR8_CONVERSATION.md`.

The remaining jobs succeeded, including core 3.11/3.13, macos-mlx, mac-ui, app, iOS, security and web. The overall run remains failed. A PR conversation comment documenting this evidence was posted as **7135079286**. Required disposition: label/archive historical evidence so canonical-policy scans exclude it without deleting or altering the archive; rerun the full workflow.

### Revalidated findings and boundaries at this head
- **ATLAS-ACT-015 — VERIFIED FIXED for the narrow reported bypass:** `browser.py` refuses `fill` and `press`; the real route is read-only GET/HEAD. This does not approve general browser automation.
- **ATLAS-SEC-017 — VERIFIED FIXED only for returned verdicts:** `ConnectorHub._apply()` enables authority only for `ok` and revokes for other returned verdicts. **ATLAS-CONN-025 remains OPEN:** explicit `check()` calls the adapter without exception handling; if it raises, the prior authority is not revoked. `verify_all()` does catch exceptions, but that does not repair the explicit-check path.
- **ATLAS-SEC-014 — PARTIALLY ADDRESSED:** current code fingerprints every 4+ letter non-function word, two-word passage runs and names; tests cover lowercase names, phrases, encoded URL components and redirects. The module explicitly disclaims a guarantee for paraphrases and 1–3-character terms. Public egress must remain disabled pending the stated owner decision and real-Internet/owner-Mac evidence.
- **ATLAS-SEC-016 — OPEN:** browser worker remains a same-user subprocess with `SAFE_ENV` explicitly passing `HOME` and `PYTHONPATH`; no OS-enforced confinement is applied to the browser worker/Chromium process tree. Model-worker sandbox work does not close this separate browser-worker finding.
- **ATLAS-OPS-018 — SOURCE CHANGE PRESENT, NOT VERIFIED CLOSED:** Swift CoreLauncher now records PID/start time/socket/data directory, rechecks identity before force-kill, and probes for a live listener before unlinking. Exact-head Swift test/CI evidence was not independently mapped to this finding in this pass; retain pending.
- **ATLAS-ACT-019 — OPEN:** ActionGateway's approvals, completed receipts, idempotency map and revoked-action set are in-memory dictionaries; supplying/loading audit history restores the audit list, not those execution-state maps. Restart-safe retry/undo is not demonstrated.
- **ATLAS-CONN-025 — OPEN:** explicit adapter re-check exception can preserve previously granted connector authority; revoke on every exception and test action denial.

### Sandbox and Mail revalidation notes
The model worker no longer trusts a caller-provided “skip sandbox” flag: startup calls `sandbox.install_network_deny()`, and macOS verifies OS confinement through active probes. The macOS model profile denies network, writes (except /dev/null), reads under private roots, process execution outside the Python runtime, and unlisted Mach lookups; it is explicitly documented as **not least privilege**. Hosted `macos-mlx` passed with a real small MLX model, but owner-Mac verification and the selected model remain outstanding. This is distinct from the still-unconfined browser worker.

The EMLX parser now reads bounded headers and walks MIME delimiters line-by-line; it stops before a non-text attachment payload and rechecks Message-ID when reopening a listed message. Focused tests include a small attachment inside the former 4 KiB read-ahead window. The acceptance claim is supported by those instrumented tests, subject to exact full-suite CI (currently blocked by the two unrelated architecture-document tests).

### Current disposition
This is a targeted exact-head continuation, not completion of the 278-path audit. No claim is made that all 278 paths, every function, every requirement/design statement, all 43 outdated threads, all historical findings, or all divergent branches have been exhaustively reviewed. Continue the path ledger and historical-finding revalidation; do not mark the PR or Stage 3 accepted. No application source, tests, build files or configuration were changed.


### Coverage-count reconciliation correction — 2026-11-24

The path ledger at the end of this file contains exactly **278 rows**: **136 IN REVIEW** (targeted inspection only; not full-file sign-off) and **142 NOT STARTED**. This count was checked directly from the table. The earlier caution above about not carrying forward the split is superseded by a GitHub commit comparison: `4a09eca2ada1d4fe69c04c3a7aefa877327e1848` → `7d4ac42bf537a10d950818fe91f855817c6c5ade` changes only this coverage document; `7d4ac42` → `6a0f070880ad2c214547ef8a7fb5f0c3482a34ef` changes only `DEFECT_REGISTER.md` and this coverage document. Therefore the 278-path inventory and 136/142 inspection statuses remain applicable to the current source tree. They do **not** mean 136 files are completely reviewed: **0/278 are established as fully line-by-line reviewed**.

The documentation commits have triggered a new CI run **45419108912**, which was queued when checked. Its outcome is pending; the earlier run 45388238509 remains a confirmed failure and is not superseded until a new run completes successfully.


### Further source/test inspection — exact arithmetic

Inspected all 260 lines of `core/src/atlas_core/exact.py` and the full `core/tests/test_exact.py` at source snapshot `4a09eca2ada1d4fe69c04c3a7aefa877327e1848` (source unchanged through the later documentation-only commits). Found **ATLAS-EXACT-106 (P1)**: `Number.exact_decimal` divides Decimals under the default 28-digit context even though the rational parser accepts values up to roughly 420 digits. This can mislabel a rounded value as exact. Logged as PR review **6041587567** and added to the defect register. The file's existing test suite has no >28-significant-digit precision case. This is a source finding, not a claim that the entire 278-path audit is complete.


### Review-thread count after this continuation

The exact-arithmetic inline review created one additional thread. Live GitHub now reports **59 inline threads: 21 resolved, 38 unresolved; 43 outdated**. The prior 58/21/37 figures above are the pre-ATLAS-EXACT-106 snapshot. No threads were resolved. Current PR head at this documentation update: `b32e1055d948bf0c9e1880dda4d0c2eb79d78bbd`.



## Live continuation — 2026-11-24, exact PR #8 head `b0ece9c13670096d5bd4b2b8dddf21369874d2ec`

### Verified live snapshot
- PR #8: open, draft, unmerged; branch `genesis-stage2-foundation`, base `atlas`.
- Exact head: `b0ece9c13670096d5bd4b2b8dddf21369874d2ec`.
- Changed paths: **278** (GitHub paginated filename endpoint).
- Inline review threads: **59 total; 21 resolved; 38 unresolved; 43 outdated** (GitHub GraphQL thread fields `is_resolved` and `is_outdated`). This supersedes the earlier 59/21/38 count only if a later live snapshot changes; the old 58/21/37 and 59/21/38 entries above are historical snapshots.
- The 38 unresolved thread IDs are preserved by GitHub; no thread was resolved in this continuation.
- The latest exact-head workflow-run lookup returned **no PR-triggered workflow runs** for this SHA. The earlier failed run 45388238509 and queued run 45419108912 are historical and do not establish the result for this head.
- Commit comparison from `b32e1055d948bf0c9e1880dda4d0c2eb79d78bbd` to this head shows four commits, with changes limited to `core/tests/test_architecture.py`, `docs/genesis/LOW_LEVEL_DESIGN.md`, and this coverage ledger. The previously inspected `core/src/atlas_core/exact.py` and `core/tests/test_exact.py` are unchanged in that range.

### Coverage ledger counts at this checkpoint
- Path inventory: **278 rows**.
- `IN REVIEW`: **146** (targeted inspection only; not equivalent to full-file completion).
- `NOT STARTED`: **131**.
- `REVIEWED—NO FINDINGS`: **1** (`CLAUDE.md`, all 22 lines inspected).
- **Fully completed exact-head file reviews: 1/278** under the strict status definition above. Do not count IN REVIEW rows as completed.
- `CLAUDE.md`: full-file review completed. It correctly assigns canonical docs to ChatGPT, implementation/tests to Claude, and requires evidence labels and exact commit references. No contradiction found.
- `.gitleaksignore`: all 10 lines inspected. It contains four narrow fingerprint suppressions, not broad rule/path suppressions. Remains IN REVIEW until each fingerprint is checked against the corresponding Gitleaks finding/scan evidence; do not call the suppressions verified merely because the comments say so.

### Resume checkpoint — do not restart
- **Last fully completed file:** `CLAUDE.md` (22/22 lines; REVIEWED—NO FINDINGS).
- **Current file to continue:** `.gitleaksignore` (10/10 lines read; verify the four fingerprint suppressions against actual Gitleaks scan output and the referenced source lines before closing).
- **Then continue in PR changed-file order:** `app/Package.swift`, followed by `app/README.md`. Keep the path ledger sorted as it is; record every file's exact-head SHA, inspected line range, evidence and finding IDs.
- **Known open exact-head source finding:** ATLAS-EXACT-106 remains present in `core/src/atlas_core/exact.py`: `Number.exact_decimal` uses default-context Decimal division while accepted rationals can exceed 28 significant digits. The 137-line `core/tests/test_exact.py` still has no >28-significant-digit regression case. This source/test pair was re-read at this head; no fix is present.
- **No tests were executed by this review pass.** The reviewer inspected source and configuration only. CI status for this exact head is unknown because no associated workflow runs were returned.
- Review boundary remains: no application source, tests, build/config changes, approvals, merges or review-thread resolutions by this reviewer.



### File-review continuation — 2026-11-24

**Source snapshot reviewed:** ce669813f5f1104dede65030156dbadd281bf2ed (the current PR head before this ledger-only update).

- .gitleaksignore — all 10 lines inspected. Four suppressions are narrow commit/path/rule/line fingerprints. Historical contexts were inspected: a type annotation in a test helper, the file's own historical explanatory comment, a public frozen-contract SHA-256 checksum, and a generated Ed25519 test key/default parameter. No broad allow-list or blanket path/rule suppression found. Marked REVIEWED—NO FINDINGS for file content; Gitleaks itself was not run in this pass, so this is not a claim that a current scan passed.
- app/Package.swift — all 15 lines inspected. It declares AtlasKit and AtlasApp products, macOS 14/iOS 17 platform declarations, and no external package dependencies. Kept IN REVIEW pending cross-check against the separately generated Xcode/macOS/iOS targets and deployment requirements.
- app/README.md — all 19 lines inspected. Documentation finding: it says the app has not been run and says the Swift launcher/client has not been tested against a real child Core. Those statements conflict with the current CI app job (launches packaged Atlas binary, verifies Core socket/process lifecycle and captures a screenshot) and EndToEndTests.swift (Swift launcher + client against a real Python Core over a Unix socket, including owner enrolment and Keychain). A human UI/accessibility walkthrough, real TCC prompts, real Mail store, signing/notarisation and self-contained installation remain unverified. Review comment 6045284683 was posted on PR #8; no implementation or README edit was made.
- core/src/atlas_core/exact.py and core/tests/test_exact.py were re-read at source head b0ece9c13670096d5bd4b2b8dddf21369874d2ec; ATLAS-EXACT-106 remains present, with no >28-significant-digit regression test. They are unchanged between that source head and ce669813f5f1104dede65030156dbadd281bf2ed.
- Updated path counts after these dispositions: 278 total; 147 IN REVIEW; 129 NOT STARTED; 2 REVIEWED—NO FINDINGS. Strict fully completed file reviews: 2/278. IN REVIEW means targeted or incomplete, not completed.
- Resume: .gitleaksignore and CLAUDE.md are complete. Continue with app/Package.swift (reconcile target compatibility and mark complete only when evidence supports it), then app/README.md (track the posted contradiction until Claude corrects it and the revised text is independently checked), then app/Sources/AtlasApp/AtlasApp.swift.
- No tests were executed by this reviewer. No source, tests, package/build configuration or app code changed. No review threads were resolved and no approval/merge was made.


### Live checkpoint after app README review — 2026-11-24

- PR #8 head at checkpoint: 8905488a0a78c82b48d1176810950eefdb80fd4f; PR remains open, draft and unmerged; 278 changed paths.
- The documentation review comment 6045284683 added one inline thread. Live GitHub now reports **60 total threads: 21 resolved, 39 unresolved; 43 outdated**. No threads were resolved.
- Workflow run **45463150038** was queued for this head when checked; no result yet. Do not describe it as passed.
- app/Package.swift: all 15 lines reviewed and cross-checked against app/xcode/project.yml (macOS 14) and ios/project.yml (iOS 17). Both XcodeGen projects consume only AtlasKit; AtlasApp executable is the macOS app product. No package-level defect found. Marked REVIEWED—NO FINDINGS.
- Current path-ledger counts: **278 total; 146 IN REVIEW; 129 NOT STARTED; 3 REVIEWED—NO FINDINGS**. Strict completed-file count: **3/278**. IN REVIEW is not completion.
- Last completed file: app/Package.swift. Current open review file: app/README.md, with the evidence contradiction recorded in PR comment 6045284683. Next file after the README disposition: app/Sources/AtlasApp/AtlasApp.swift.
- No tests were executed locally by this reviewer. No app code, source, tests, package manifest, or build configuration was changed. Only the coverage ledger was updated; no approval, merge, or thread resolution was performed.
