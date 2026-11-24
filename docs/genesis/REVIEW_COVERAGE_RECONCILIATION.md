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
| `.github/workflows/ci.yml` | build/config | REVIEWED—NO FINDINGS | All 293 lines at blob 1faee77; Linux/macOS/iOS/MLX/package/UI/security jobs, env wiring, artifacts and test execution scopes inspected |
| `.gitleaksignore` | build/config | REVIEWED—NO FINDINGS | Full 10 lines; four fingerprint suppressions matched to historical test/type annotation, comment, public checksum and generated test key contexts; scanner execution not independently run |
| `CLAUDE.md` | documentation | REVIEWED—NO FINDINGS | Full 22 lines; source-of-truth, role split, evidence and product principles consistent with current delivery protocol |
| `app/Package.swift` | build/config | REVIEWED—NO FINDINGS | All 15 lines re-read at blob 0028b51; AtlasKit/AtlasApp products, platform targets and dependencies align with generated Xcode projects |
| `app/README.md` | documentation | REVIEWED—FINDINGS OPEN | Full 19 lines at 1af9af9; CI now runs packaged app/Core lifecycle, Swift real-Core E2E and macOS UI audit, but README still says app has not been run / Swift side untested / packaging not built; ATLAS-DOC-052; prior PR comment 6045284683 |
| `app/Sources/AtlasApp/AtlasApp.swift` | source | REVIEWED—FINDINGS OPEN | Full 696 lines at blob 40f5346; ATLAS-APP-052 stale task ID can be cancelled during next ask; ATLAS-APP-053 failed undo is swallowed and retry handle cleared; activity history remains covered by ATLAS-UX-023 |
| `app/Sources/AtlasApp/Components.swift` | source | REVIEWED—FINDINGS OPEN | Full 179 lines at blob 0e52e88; ApprovalSheet exposes no explicit Done/Close action after terminal state; potential UI dismissal issue ATLAS-APP-057 pending macOS UI verification |
| `app/Sources/AtlasApp/DesignSystem.swift` | source | REVIEWED—NO FINDINGS | Full 67 lines at blob b59e7b3; semantic colour/token mapping, scalable text styles, reduce-motion and reading-width helpers inspected; no defect established |
| `app/Sources/AtlasApp/Screens.swift` | source | REVIEWED—FINDINGS OPEN | Full 772 lines at blob 9b5ad87; ATLAS-APP-056 Activity screen omits model.attention although Home includes it; existing ATLAS-UX-023 activity persistence remains open |
| `app/Sources/AtlasApp/Shell.swift` | source | REVIEWED—FINDINGS OPEN | All 94 lines at blob f2b0335; approval sheet binding only dismisses when item becomes nil; potential terminal-state dismissal issue ATLAS-APP-057 pending UI verification |
| `app/Sources/AtlasApp/Speaker.swift` | source | REVIEWED—NO FINDINGS | All 26 lines at blob cc0f579; local AVSpeechSynthesizer lifecycle and finish/cancel callbacks inspected; no defect established in this adapter |
| `app/Sources/AtlasApp/Speech.swift` | source | REVIEWED—FINDINGS OPEN | All 61 lines at blob 67c6f11; ATLAS-VOICE-057 start failure leaves installed input tap/request uncleared; local speech only, no server fallback |
| `app/Sources/AtlasKit/Activity.swift` | source | REVIEWED—NO FINDINGS | All 69 lines at blob 14c66e0; chronological dedupe, attention projection, recent-task filtering and allow-listed calendar-conflict mapping inspected |
| `app/Sources/AtlasKit/Aloud.swift` | source | REVIEWED—NO FINDINGS | All 34 lines at blob 295c813; answer/trust text composition, empty guard and single-session toggle/stop lifecycle inspected |
| `app/Sources/AtlasKit/AnswerView.swift` | source | REVIEWED—NO FINDINGS | All 39 lines at blob 74e0e35; untrusted response mapping, catalogue-backed status/limitations, coverage, not-searched and citation locator rendering inspected |
| `app/Sources/AtlasKit/Approval.swift` | source | REVIEWED—NO FINDINGS | All 88 lines at blob c3240bf; closed action/consequence allow-list, exact payload fingerprint, expiry and approval state transitions inspected |
| `app/Sources/AtlasKit/Catalogue.swift` | source | REVIEWED—NO FINDINGS | All 49 lines at blob 85d6f55; shared catalogue decoding, required fields and controlled error fallback inspected |
| `app/Sources/AtlasKit/Connections.swift` | source | REVIEWED—NO FINDINGS | All 101 lines at blob 42f22a9; connection state, approval description, HTTP/TLS and home/VPN host validation inspected; cross-checked Core enum/effect contract and tests |
| `app/Sources/AtlasKit/CoreClient.swift` | source | REVIEWED—FINDINGS OPEN | All 119 lines at blob c5d6748; ATLAS-CORE-062 required response fields silently default (task_id/state/passage/attention/devices) instead of protocol errors |
| `app/Sources/AtlasKit/CoreLauncher.swift` | source | REVIEWED—FINDINGS OPEN | All 166 lines at blob 9487c31; stale comment says packaging not built, contradicted by CI packaging job (ATLAS-DOC-052); lifecycle/reaping/identity logic inspected |
| `app/Sources/AtlasKit/Finance.swift` | source | REVIEWED—FINDINGS OPEN | All 87 lines at blob 5da7d8d; ATLAS-FIN-063 zero delta is labelled “more” |
| `app/Sources/AtlasKit/GetStarted.swift` | source | REVIEWED—NO FINDINGS | All 23 lines at blob bf9fa0c; default-deny first-run choices, no-grant empty choice and completion gating inspected |
| `app/Sources/AtlasKit/HTTPTransport.swift` | source | REVIEWED—FINDINGS OPEN | All 45 lines at blob 42e491c; maxReply is checked after URLSession fully buffers body; ATLAS-HTTP-066 |
| `app/Sources/AtlasKit/Health.swift` | source | REVIEWED—NO FINDINGS | All 57 lines at blob 4d2274e; health basis labels, measured/estimated/unlabelled counts, unit preservation and unknown-state handling inspected |
| `app/Sources/AtlasKit/Library.swift` | source | REVIEWED—NO FINDINGS | All 67 lines at blob e433872; result allow-list mapping, coverage, partial/no-result/denied states and stable title sorting inspected |
| `app/Sources/AtlasKit/Lifecycle.swift` | source | REVIEWED—NO FINDINGS | All 89 lines at blob 4d1b6c9; explicit Core-state allow-list, terminal/cancel rules and monotonic phase tracking inspected |
| `app/Sources/AtlasKit/Navigation.swift` | source | REVIEWED—NO FINDINGS | All 97 lines at blob 9e4edd8; destination restoration, availability filtering, responsive breakpoints and shortcut bounds inspected |
| `app/Sources/AtlasKit/Notifications.swift` | source | REVIEWED—NO FINDINGS | All 27 lines at blob 10f1902; opt-in gate, attention filtering, dedupe and per-round cap/content-free payload inspected |
| `app/Sources/AtlasKit/OfflineSync.swift` | source | REVIEWED—FINDINGS OPEN | All 143 lines at blob d489f50; corrupt persisted queue silently decodes as empty and can be overwritten, risking offline edit loss; ATLAS-OFFLINE-071 (P1) |
| `app/Sources/AtlasKit/Pairing.swift` | source | REVIEWED—FINDINGS OPEN | All 133 lines at blob ffcac44; ATLAS-PAIR-065 duplicate query names trap Dictionary(uniqueKeysWithValues:); fingerprint/nonce proof and vault write order inspected |
| `app/Sources/AtlasKit/PhoneEngine.swift` | source | REVIEWED—FINDINGS OPEN | All 137 lines at blob f1beb87; ATLAS-PHONE-064 paired-but-no-transport path leaves link falsely online; queue/cache/revocation paths inspected |
| `app/Sources/AtlasKit/Records.swift` | source | REVIEWED—FINDINGS OPEN | All 132 lines at blob 2a0c22a; RecordsOutcome silently drops malformed rows and can report empty/partial data as valid; ATLAS-RECORD-072 |
| `app/Sources/AtlasKit/RelayBind.swift` | source | REVIEWED—NO FINDINGS | All 19 lines at blob e24ef7e; literal IPv4/private/loopback/link-local/VPN and port allow-list inspected; Core repeats validation |
| `app/Sources/AtlasKit/Review.swift` | source | REVIEWED—NO FINDINGS | All 38 lines at blob e4dbe60; section allow-list mapping, action gating and partial-status note inspected |
| `app/Sources/AtlasKit/ScreenState.swift` | source | REVIEWED—NO FINDINGS | All 115 lines at blob 9abb531; load/launch/conversation/evidence state mapping and plain fallback messages inspected |
| `app/Sources/AtlasKit/Signing.swift` | source | REVIEWED—NO FINDINGS | All 27 lines at blob 43401de; canonical message fields, SHA-256 body digest, nonce and Curve25519 signature construction inspected |
| `app/Sources/AtlasKit/SubmissionGate.swift` | source | REVIEWED—NO FINDINGS | All 18 lines at blob a9d2ce6; single-flight begin/end gate inspected; stale task-ID race separately recorded in AtlasApp |
| `app/Sources/AtlasKit/Tokens.swift` | source | REVIEWED—NO FINDINGS | All 91 lines at blob e94c1bf; WCAG luminance/contrast math, light/dark semantic palettes, spacing/type/radius/size and reduced-motion tokens inspected |
| `app/Sources/AtlasKit/Transport.swift` | source | REVIEWED—FINDINGS OPEN | All 58 lines at blob 9cace98; UnixHTTP reads until EOF with no response cap; paired with RemoteHTTP post-buffer cap defect ATLAS-HTTP-066 |
| `app/Sources/AtlasKit/Updates.swift` | source | REVIEWED—NO FINDINGS | All 42 lines at blob 20bcab7; signed-update refusal mapping, install/rollback result and restart messaging inspected |
| `app/Sources/AtlasKit/Voice.swift` | source | REVIEWED—FINDINGS OPEN | All 111 lines at blob 7ce1093; ATLAS-VOICE-067 asking state does not prevent multiple asynchronous permission callbacks starting multiple sessions |
| `app/Sources/AtlasKit/Web.swift` | source | REVIEWED—NO FINDINGS | All 53 lines at blob 1c4f8d8; HTTPS and allow-listed host validation, injection/truncation warnings and Core error mapping inspected |
| `app/Sources/AtlasKit/ux_catalogue.json` | source | REVIEWED—NO FINDINGS | All 147 lines at blob 0c0419c; JSON catalogue keys and user-facing state/error/coverage/citation strings inspected; byte-identical to Core client copy |
| `app/Tests/AtlasKitTests/AloudTests.swift` | test | REVIEWED—NO FINDINGS | All 41 lines at blob f7a8ad7; text composition, empty answer and speak/stop/finish transitions covered |
| `app/Tests/AtlasKitTests/ConnectionsTests.swift` | test | REVIEWED—NO FINDINGS | All 73 lines read; state, approval vocabulary, safe host validation, and malformed top-level response tests inspected |
| `app/Tests/AtlasKitTests/DesignSystemTests.swift` | test | REVIEWED—NO FINDINGS | Full file read; WCAG contrast, text hierarchy, spacing/type/radius, reduced motion and navigation layout assertions inspected |
| `app/Tests/AtlasKitTests/EndToEndTests.swift` | test | REVIEWED—FINDINGS OPEN | All 197 lines at blob c928573; ATLAS-TEST-069 deletes production-named Atlas Keychain items on local E2E runs |
| `app/Tests/AtlasKitTests/FinanceTests.swift` | test | REVIEWED—FINDINGS OPEN | Full file read; delta direction cases omit zero/negative-zero, leaving ATLAS-FIN-063 uncovered |
| `app/Tests/AtlasKitTests/GetStartedTests.swift` | test | REVIEWED—NO FINDINGS | All 35 lines at blob 8355b30; default-deny, no-grant and completion cases covered |
| `app/Tests/AtlasKitTests/HealthTests.swift` | test | REVIEWED—NO FINDINGS | All 48 lines at blob 1eb3314; measured/estimated/unlabelled provenance and invalid/empty states covered |
| `app/Tests/AtlasKitTests/LibraryTests.swift` | test | REVIEWED—NO FINDINGS | All 50 lines at blob abba8b8; result rows, coverage, partial/denied/unknown states and stable sorting covered |
| `app/Tests/AtlasKitTests/NotificationTests.swift` | test | REVIEWED—NO FINDINGS | All 35 lines at blob d7bc7f0; opt-in, generic privacy-safe body, dedupe and per-round cap covered |
| `app/Tests/AtlasKitTests/PhoneTests.swift` | test | REVIEWED—FINDINGS OPEN | Full file read; ATLAS-TEST-069 repeats production-named Keychain deletion; ATLAS-PHONE-064 no-transport state path lacks regression coverage |
| `app/Tests/AtlasKitTests/ReapIdentityTests.swift` | test | REVIEWED—NO FINDINGS | All 94 lines at blob 4aba14f; process identity, stale/reused PID, mismatched folder/socket and re-check before SIGKILL covered |
| `app/Tests/AtlasKitTests/RecordsTests.swift` | test | REVIEWED—FINDINGS OPEN | All 88 lines at blob a7bd41f; malformed all-invalid/mixed-validity records responses are not tested; ATLAS-RECORD-072 |
| `app/Tests/AtlasKitTests/ReviewTests.swift` | test | REVIEWED—NO FINDINGS | All 38 lines at blob 13c27d8; review section mapping, highlights, incomplete and unreadable states covered |
| `app/Tests/AtlasKitTests/SigningTests.swift` | test | REVIEWED—NO FINDINGS | All 44 lines at blob 9452b0b; 1.0/1.1 known-answer vectors, signature verification and catalogue rendering covered |
| `app/Tests/AtlasKitTests/SubmissionGateTests.swift` | test | REVIEWED—FINDINGS OPEN | All 29 lines at blob f718553; tests isolated gate only, not AppModel stale currentTaskID on new submission (ATLAS-APP-052) |
| `app/Tests/AtlasKitTests/UpdateTests.swift` | test | REVIEWED—NO FINDINGS | All 35 lines at blob a090ff2; managed/unmanaged status, refusal wording and install/restart result covered |
| `app/Tests/AtlasKitTests/VoiceTests.swift` | test | REVIEWED—FINDINGS OPEN | All lines read; fake permission callback is synchronous, no repeated/delayed .asking-state test for ATLAS-VOICE-067 |
| `app/Tests/AtlasKitTests/WebTests.swift` | test | REVIEWED—NO FINDINGS | All 27 lines at blob 647d85c; source/untrusted warning, injection flag, host allow-list and HTTPS-only validation covered |
| `app/xcode/AtlasMacUITests/AccessibilityAuditTests.swift` | test | REVIEWED—FINDINGS OPEN | Full 92 lines at blob 0059680; ATLAS-TEST-054 contrast exemption can false-pass using unrelated frame extrema; ATLAS-TEST-055 fixed sleep/non-empty text does not assert stable first screen |
| `app/xcode/project.yml` | build/config | REVIEWED—FINDINGS OPEN | All 51 lines at blob e9a540c; ATLAS-DOC-070 opening comment incorrectly says this tracked YAML is not checked in; macOS 14 target and AtlasKit dependency inspected |
| `core/README.md` | documentation | REVIEWED—FINDINGS OPEN | All 13 lines at blob 2c533cf; ATLAS-DOC-074 denies capabilities now present in repo (ingestion/search/Mail/model/Swift/remote/iOS/actions) |
| `core/bench/ingest.py` | benchmark | REVIEWED—FINDINGS OPEN | All 152 lines at blob dee08e3; ATLAS-BENCH-073 divides ru_maxrss by 1024 on macOS despite byte units |
| `core/bench/overhead.py` | benchmark | REVIEWED—NO FINDINGS | All 88 lines at blob e02e784; stubbed foundation timings, percentile calculation and explicit non-target-Mac limitations inspected |
| `core/client/atlas_client.py` | source | REVIEWED—FINDINGS OPEN | All 348 lines at blob 2abc231; ATLAS-CLIENT-076 missing/invalid task ID accepted and response-body read errors escape ClientError normalization |
| `core/client/ux_catalogue.json` | source | REVIEWED—NO FINDINGS | All 147 lines at blob 0c0419c; exact byte-identical mirror of app AtlasKit catalogue, vocabulary and wording inspected |
| `core/contracts/atlas-contracts.1.1.delta.schema.json` | contract/schema | IN REVIEW | 2679 lines; 47 additions/5 overrides parsed and cross-checked against deterministic merge/strict-shape tests; exact line-by-line review pending |
| `core/contracts/atlas-contracts.1.1.schema.json` | contract/schema | IN REVIEW | 3253 lines; generated merged schema; selected definitions checked for strict fields; test_contracts_v11 asserts exact merge and schema validation; exhaustive path review pending |
| `core/contracts/atlas-contracts.schema.json` | contract/schema | REVIEWED—NO FINDINGS | All 265 lines read at blob 3172b1b; frozen 1.0 schema and strict object shapes inspected; SHA baseline assertion in test_contracts_frozen |
| `core/contracts/openapi-1.1.yaml` | contract/schema | IN REVIEW | 1155 lines; 1.1 route/response/schema references and parity checks reviewed via test_contracts_v11; exhaustive path-by-path review pending |
| `core/contracts/openapi.yaml` | contract/schema | REVIEWED—NO FINDINGS | All 103 lines read at blob ccf62f7; frozen 1.0 API paths, signed request scheme and schema references inspected |
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
| `core/src/atlas_core/access.py` | source | REVIEWED—NO FINDINGS | All 136 lines at blob 09347dd; fresh source-specific OS evidence, stale/future/type mismatch, unknown/failure fail-closed behavior, grant preservation/revocation and purge path cross-checked with test_designation.py |
| `core/src/atlas_core/actions.py` | source | REVIEWED—FINDINGS OPEN | All 314 lines at blob 0a690d3; ATLAS-ACT-019 in-memory execution/undo/idempotency and unanchored audit reset; ATLAS-ACT-074 multi-category effects collapse to one approval label; ATLAS-ACT-075 unlogged unknown/invalid undo refusals |
| `core/src/atlas_core/answer.py` | source | REVIEWED—NO FINDINGS | All 159 lines at blob 43b2209; exact citation resolution, retrieved-only check, figure/date verification, language disclosure and explicit stop/withheld/denied envelopes inspected |
| `core/src/atlas_core/api.py` | source | REVIEWED—NO FINDINGS | All 563 lines at blob 3b1103a; request dispatch, signed version negotiation, enrol/bootstrap, owner/member route gates, consent, action, sync, web, device, update and SSE behavior inspected with API tests |
| `core/src/atlas_core/app.py` | source | IN REVIEW | Targeted: 166–208, 230–245, 318–341 |
| `core/src/atlas_core/backup.py` | source | REVIEWED—FINDINGS OPEN | All 405 lines at blob 3b415da; ATLAS-BACKUP-080 drill deletes pre-existing empty scratch dir; ATLAS-BACKUP-081 malformed nested manifest/bundle can raise; ATLAS-BACKUP-082 copied plain files not reverified |
| `core/src/atlas_core/browser.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/browser_engine.py` | source | IN REVIEW | Full: 1–260 |
| `core/src/atlas_core/browser_worker.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/confinement.py` | source | IN REVIEW | Full source: 1–53 |
| `core/src/atlas_core/connector_transport.py` | source | IN REVIEW | Full source inspected |
| `core/src/atlas_core/connectors.json` | source | NOT STARTED | — |
| `core/src/atlas_core/connectors.py` | source | IN REVIEW | Targeted: 91–130, 190–250 |
| `core/src/atlas_core/consent.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/contracts.py` | source | REVIEWED—FINDINGS OPEN | All 133 lines at blob a872b9e; ATLAS-DOC-075 stale VERSIONS comment incorrectly says 1.1 is not served |
| `core/src/atlas_core/coverage.py` | source | NOT STARTED | — |
| `core/src/atlas_core/designation.py` | source | IN REVIEW | Targeted: 1–180, 201–370, 471–575 |
| `core/src/atlas_core/devices.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/documents.py` | source | IN REVIEW | Targeted: 130–255, 285–395 |
| `core/src/atlas_core/egress.py` | source | REVIEWED—FINDINGS OPEN | All 409 lines at blob 0aa66a9; ATLAS-SEC-014 residual taint gaps; ATLAS-EGRESS-077 unbounded DNS timeout; ATLAS-EGRESS-078 silent 200k text truncation; ATLAS-EGRESS-079 malformed port ValueError |
| `core/src/atlas_core/errors.py` | source | NOT STARTED | — |
| `core/src/atlas_core/events.py` | source | NOT STARTED | — |
| `core/src/atlas_core/evidence.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/exact.py` | source | IN REVIEW | Full source: 1–260; precision defect ATLAS-EXACT-106 |
| `core/src/atlas_core/finance_calc.py` | source | IN REVIEW | Full: 1–187 |
| `core/src/atlas_core/gate.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/health.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/health_calc.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/host.py` | source | REVIEWED—NO FINDINGS | All 176 lines at blob 7c0620c; production macOS-only provider selection, Keychain keys, signed manifest, native/Finance/Health stores, restore drill and web disabled by default inspected |
| `core/src/atlas_core/identity.py` | source | REVIEWED—NO FINDINGS | All 186 lines at blob 9aa0e10; canonical signatures, version binding, nonce replay cache, bootstrap rate limit, durable public-key registry, owner/member and revocation checks inspected |
| `core/src/atlas_core/intelligence.py` | source | NOT STARTED | — |
| `core/src/atlas_core/isolated.py` | source | REVIEWED—NO FINDINGS | All 169 lines at blob 94fc687; clean env, confined model root, bounded silence, worker crash, early cancel/drain and process teardown inspected |
| `core/src/atlas_core/launchagent.py` | source | IN REVIEW | Full source: 1–42 |
| `core/src/atlas_core/launcher.py` | source | NOT STARTED | — |
| `core/src/atlas_core/macos.py` | source | REVIEWED—FINDINGS OPEN | All 521 lines at blob 5cef615; ATLAS-MAIL-079 unreadable subtrees/files and failed root pin are silently omitted, allowing false-complete Mail coverage; descriptor/no-follow and MIME byte bounds otherwise inspected |
| `core/src/atlas_core/macos_sources.py` | source | IN REVIEW | Full: 1–266 |
| `core/src/atlas_core/mail.py` | source | REVIEWED—FINDINGS OPEN | All 509 lines at blob ac47c34; coverage trusts ListPage completeness and cannot represent adapter-skipped entries; ATLAS-MAIL-079 |
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
| `core/src/atlas_core/sandbox.py` | source | REVIEWED—NO FINDINGS | All 165 lines at blob 80210f0; seccomp arch/syscall/domain filter, io_uring block, macOS deny profile, private-read and Mach allow-list checked against tests |
| `core/src/atlas_core/serve.py` | source | IN REVIEW | Targeted CLI flags/options |
| `core/src/atlas_core/service.py` | source | IN REVIEW | Targeted: 126–300, 326–347, 554–621 |
| `core/src/atlas_core/storage.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/sync.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/tasks.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/transport.py` | source | REVIEWED—NO FINDINGS | All 202 lines at blob c7f926d; peer UID, strict bounded request framing, timeout, connection cap, owner-only socket and stale/live socket handling inspected |
| `core/src/atlas_core/updater.py` | source | IN REVIEW | Full source |
| `core/src/atlas_core/values.py` | source | IN REVIEW | Full source: 1–16 |
| `core/src/atlas_core/watchers.py` | source | IN REVIEW | Full source: 1–93 |
| `core/src/atlas_core/web.py` | source | IN REVIEW | Targeted: 30–121 |
| `core/src/atlas_core/worker.py` | source | REVIEWED—NO FINDINGS | All 120 lines at blob 56140ca; mandatory pre-engine confinement, no skip flag, custom-engine test-only gate and isolated stdin/stdout protocol inspected |
| `core/tests/conftest.py` | test | NOT STARTED | — |
| `core/tests/core_factory.py` | test | NOT STARTED | — |
| `core/tests/test_actions.py` | test | REVIEWED—FINDINGS OPEN | All 229 lines at blob 56dcb9b; restart test verifies audit append only, not approval/receipt/undo/idempotency persistence; no missing/empty audit-file, multi-category, or unknown-action audit tests; ATLAS-ACT-019/074/075 |
| `core/tests/test_api.py` | test | REVIEWED—NO FINDINGS | All 194 lines at blob e51f24f; version negotiation, route/status parity, signed identity, replay/tamper, policy enforcement and user-safe errors covered |
| `core/tests/test_api_v11.py` | test | REVIEWED—NO FINDINGS | All 188 lines at blob b312803; signed applied version, additive 1.1 coverage/model fields, limitations, SSE, exact compute and unknown-source semantics covered |
| `core/tests/test_app.py` | test | NOT STARTED | — |
| `core/tests/test_architecture.py` | test | NOT STARTED | — |
| `core/tests/test_artefact_scan.py` | test | NOT STARTED | — |
| `core/tests/test_backup.py` | test | REVIEWED—FINDINGS OPEN | All 300 lines at blob 20e57e7; no tests for existing empty scratch preservation, malformed nested manifest/bundle or plain-file swap between verify/copy; ATLAS-BACKUP-080/081/082 |
| `core/tests/test_bench.py` | test | NOT STARTED | — |
| `core/tests/test_browser_engine.py` | test | IN REVIEW | Targeted: 82–90 |
| `core/tests/test_browser_watchers.py` | test | IN REVIEW | Targeted: 64–73 |
| `core/tests/test_client.py` | test | REVIEWED—FINDINGS OPEN | All 344 lines at blob efac279; broad end-to-end coverage, but no malformed task_id or mid-body disconnect tests for ATLAS-CLIENT-076 |
| `core/tests/test_connectors.py` | test | IN REVIEW | Targeted: 190–247 |
| `core/tests/test_consent_api.py` | test | REVIEWED—NO FINDINGS | All 190 lines at blob e48338d; owner-only consent, paired member read, replay protection, withdrawal purge, malformed choices and default model mode covered |
| `core/tests/test_contracts.py` | test | REVIEWED—NO FINDINGS | All 68 lines at blob d8b19c9; strict 1.0 schema compilation, OpenAPI validation, taxonomy parity and content-free validation assertions inspected |
| `core/tests/test_contracts_frozen.py` | test | REVIEWED—NO FINDINGS | All 52 lines at blob e2bf4b3; frozen 1.0 hashes, default validator and runtime negotiation assertions inspected |
| `core/tests/test_contracts_v11.py` | test | REVIEWED—NO FINDINGS | All 731 lines at blob b0feb79; deterministic merge, strict schema shapes, coverage/limitation consistency, content-free fields, OpenAPI parity and signing vectors inspected |
| `core/tests/test_designation.py` | test | IN REVIEW | Targeted designable-domain assertion and grant tests |
| `core/tests/test_devices.py` | test | IN REVIEW | Full test file |
| `core/tests/test_documents.py` | test | NOT STARTED | — |
| `core/tests/test_domains.py` | test | NOT STARTED | — |
| `core/tests/test_egress.py` | test | REVIEWED—FINDINGS OPEN | All 336 lines at blob 64881f5; taint/redirect coverage present; no stalled DNS, 200k–512k truncation-flag or malformed-port tests; ATLAS-EGRESS-077/078/079 |
| `core/tests/test_enrolment.py` | test | REVIEWED—NO FINDINGS | All 243 lines at blob 7607fb4; bootstrap one-time/guess lockout, racing first owners, durable registry, owner/member authority and restart behavior covered |
| `core/tests/test_evals.py` | test | NOT STARTED | — |
| `core/tests/test_evidence_answer.py` | test | REVIEWED—NO FINDINGS | All 185 lines at blob 532fb7e; exact span/locator, stale/wrong quote, figure/date, language, truncation, partial and failure states covered |
| `core/tests/test_exact.py` | test | IN REVIEW | Full test file; no >28-digit exact-decimal test |
| `core/tests/test_finance_calc.py` | test | IN REVIEW | Full test file |
| `core/tests/test_health.py` | test | IN REVIEW | Full test file |
| `core/tests/test_intelligence.py` | test | NOT STARTED | — |
| `core/tests/test_isolated.py` | test | REVIEWED—NO FINDINGS | All 350 lines at blob 81a8014; network/read/write/exec confinement, no skip flag, custom engine gate, cancellation, crash, silence and staged model path covered |
| `core/tests/test_launchagent.py` | test | NOT STARTED | — |
| `core/tests/test_launcher.py` | test | NOT STARTED | — |
| `core/tests/test_library.py` | test | NOT STARTED | — |
| `core/tests/test_macos.py` | test | REVIEWED—FINDINGS OPEN | All 710 lines at blob 3248ae2; strong symlink/race/MIME-byte-boundary coverage, but root symlink and inaccessible subtree are asserted/skipped as empty without checking MailIndex incomplete coverage (ATLAS-MAIL-079) |
| `core/tests/test_macos_native.py` | test | NOT STARTED | — |
| `core/tests/test_macos_sources.py` | test | IN REVIEW | Targeted: 57–135 |
| `core/tests/test_mail.py` | test | NOT STARTED | — |
| `core/tests/test_maintenance.py` | test | NOT STARTED | — |
| `core/tests/test_migration.py` | test | NOT STARTED | — |
| `core/tests/test_mlx_native.py` | test | NOT STARTED | — |
| `core/tests/test_mlx_runtime.py` | test | NOT STARTED | — |
| `core/tests/test_models.py` | test | NOT STARTED | — |
| `core/tests/test_operations_api.py` | test | REVIEWED—NO FINDINGS | All 310 lines at blob 2c132f7; owner action/approval/undo, member denial, sync idempotency/conflict, pairing/revocation, records, updates and review covered |
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
| `core/tests/test_transport.py` | test | REVIEWED—NO FINDINGS | All 240 lines at blob cfbd114; peer UID, request framing, duplicate/oversized length, timeout, connection cap and live/stale socket tests inspected |
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
| `ios/AtlasPhone/AtlasPhoneApp.swift` | source | REVIEWED—NO FINDINGS | All 12 lines at blob ab6bdca; single PhoneModel lifetime and SwiftUI app root inspected |
| `ios/AtlasPhone/PhoneModel.swift` | source | REVIEWED—FINDINGS OPEN | All 94 lines at blob 4c03781; ATLAS-PHONE-072 detached load can repopulate cache after unpair; concurrent detached engine access also requires serialization/generation guard |
| `ios/AtlasPhone/Storage.swift` | source | REVIEWED—NO FINDINGS | All 56 lines at blob 5f9df32; device-only unlocked Keychain item and complete-file-protection/backup exclusion for cache and queue inspected |
| `ios/AtlasPhone/Views.swift` | source | REVIEWED—NO FINDINGS | All 224 lines at blob e62d599; pairing/scanner, question flow, records CRUD, offline indicators and explicit unpair confirmation inspected |
| `ios/AtlasPhoneUITests/AccessibilityAuditTests.swift` | test | REVIEWED—FINDINGS OPEN | All 103 lines at blob 0fc5d4b; ATLAS-TEST-071 contrast exemption uses frame-wide extrema and can false-pass; separate Dynamic Type height check inspected |
| `ios/README.md` | documentation | REVIEWED—NO FINDINGS | All 8 lines at blob c84853f; product scope, private network prerequisite, test evidence and no-human-phone-walkthrough qualification inspected |
| `ios/project.yml` | build/config | REVIEWED—NO FINDINGS | All 52 lines at blob 4e929d5; iOS 17 target, AtlasKit dependency, camera privacy string and simulator UI-test scheme inspected |
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


## Historical review-chart reconciliation — 2026-11-24

**Correction to interpretation of the file counts above:** the 3/278 figure is only the count of files explicitly given the strict terminal status REVIEWED—NO FINDINGS in this newly-created exact-head PR #8 path ledger. It is NOT the total amount of Atlas review work already completed, and it must not be presented as such. The earlier reviews and their charts remain valid historical evidence within their named scope and commit.

### Existing chart: docs/coverage-matrix.md (legacy PR #6 / atlas branch)
- The existing chart is real and was checked against its own 545 rows. It is tied to legacy PR #6, branch `atlas`, base `5d3ddb54fabbb4d11a17cabff96d2f65cc2d1385`, head `7a3b4479bcbb27fb2bab570759ad14851c78e945`, not PR #8.
- The chart reports **545 entries**: **105 ROUND**, **15 ROUND + VIEWED**, **397 NOT INSPECTED**, and **28 AUTHORED**. The chart's definition matters: ROUND means files changed during that review round, read/changed and covered by named tests; ROUND + VIEWED are screenshots opened and inspected; NOT INSPECTED are inherited/legacy/deleted paths not line-reviewed; AUTHORED are documents/scripts not independently inspected. This is meaningful completed historical work, not zero.
- The same document explicitly warns it is not exhaustive. It supersedes older 541/512/508 counts for its own PR #6 snapshot; do not mix these with PR #8's current 278 changed paths.
- PR #6 is closed and unmerged. Its chart is therefore a separate historical change-set, not a blanket completion certificate for PR #8.
- I compared all 545 exact paths in that chart with the current PR #8 278-path list. **Only two exact path names overlap**: `.github/workflows/ci.yml` and `docs/README.md`; both were `ROUND` in the legacy chart. Thus 143 legacy ROUND/VIEWED entries cannot be added to PR #8's 278 count as if they were PR #8 files reviewed. Some historical architectural/security reviews apply conceptually to the inherited code, but exact current-head revalidation is still required.

### Other historical review evidence
- `docs/reviews.md` records Review 1 (ChatGPT engineering re-review), Review 2 (Gemini audit rubric, explicitly not completed), Review 3 (Gemini claims checked), and later rounds. Its tables include confirmed/fixed/partial/open dispositions; they are not a single count of all files completed.
- `docs/comment-tracker.md` preserves F1–F15, P-series and other historical review findings. Several items are partial/open or owner-gated. Do not infer a completed-file count from the number of tracker rows.
- `docs/genesis/HISTORICAL_PR8_REVIEW_THREADS.md` records substantial prior independent review of Stage 2/Core on named exact commits, including a 39-file changed-file review and later WP3.2 review. Those reviews must be retained as completed historical review scope; they do not certify every file in today's 278-path PR #8 diff or later commits.
- `docs/genesis/STAGE-3-BASELINE-AUDIT.md` records WP3.0 repository inspection as complete at its stated 2026-11-20 audited ref. This is a completed baseline architecture/repository inspection, not current-head line-by-line review or runtime acceptance.

### Correct reporting rule going forward
- Always report three separate measures: (1) historical review work completed in its original scope/commit (e.g. legacy matrix 105 ROUND + 15 ROUND+VIEWED; named Stage 2/WP3.2 reviews), (2) current PR #8 exact-path overlap that can be directly mapped from those charts (2 paths from the legacy matrix), and (3) this ledger's current exact-head full-file terminal dispositions (currently 3/278). Never collapse these into one misleading percentage.
- Preserve prior accepted work and findings; do not restart it. For each newly inspected PR #8 path, first search historical reviews/charts for exact path and commit coverage, then perform only the missing current-head delta review. Keep inherited historical scope labelled with its original PR and SHA.


## Live continuation — 2026-11-24, PR #8 exact head 1af9af98195e7019df766189cf1406215fa5b3b4

### Verified live state
- PR #8 remains **open, draft and unmerged** on `genesis-stage2-foundation`; base `atlas`; exact head `1af9af98195e7019df766189cf1406215fa5b3b4`; **278 changed paths**.
- Live review threads: **60 total; 21 resolved; 39 unresolved; 43 outdated**. Outdated is not fixed. No threads were resolved.
- Workflow run **45465063113** is **queued** for this exact head at the time of this checkpoint; it is not a pass. No tests were executed locally in this review.
- Current 278-row path ledger: **144 IN REVIEW; 129 NOT STARTED; 3 REVIEWED—NO FINDINGS; 2 REVIEWED—FINDINGS OPEN**. The two findings-open files have been fully read at this head, but their defects remain open. Strict no-finding terminal reviews remain 3/278; do not call the 2 findings-open files clean.

### Files completed in this continuation
- `app/README.md` — all 19 lines read at blob `5ed57e5062d0abc8213e1786d998c44de2b6e6aa`. The previous claims were partly updated but remain materially contradictory. The README's top section says a human has not walked through the UI (valid), then says “The app has not been run: no window … has been seen” (false against CI), says the Swift launcher/client has not been tested against a real Core (false against `EndToEndTests.swift` in the `macos` job), and says app/Core packaging is not built (false against `scripts/package_mac.sh` and the `app` job). It also says no accessibility behaviour is verified although the `mac-ui` job runs the macOS accessibility UI audit. Correct distinction: hosted automated launch, E2E and UI audit exist; human owner-Mac walkthrough, real TCC/Mail, signing/notarisation and release acceptance remain open. Logged as **ATLAS-DOC-052 (P2, OPEN)** in `DEFECT_REGISTER.md`; earlier PR comment 6045284683 remains relevant.
- `app/Sources/AtlasApp/AtlasApp.swift` — all **696 lines** read at blob `40f534674566d207bd0c173a9288ab51a14585b4`, including the full AppModel and lifecycle/action paths. Two reproducible code defects logged in `DEFECT_REGISTER.md`: **ATLAS-APP-052 (P2, OPEN)** — `currentTaskID` is not cleared before awaiting the next `client.ask`, so Stop during that interval can target the previous task; **ATLAS-APP-053 (P2, OPEN)** — `undoLast` discards errors with `try?` and clears the undo handle/label even when Core undo fails. Existing **ATLAS-UX-023** also remains applicable: Activity history and notification de-duplication are in-memory and do not survive restart. No source or test edits made.
- The README's CI evidence was cross-checked against `.github/workflows/ci.yml` blob `1faee779b3512942c498268a41545d8869a13038`, `app/xcode/project.yml` blob `e9a540c146e1dd3b8a2f3614b637407f727bb643`, `ios/project.yml` blob `4e929d5de1a3ddb12532fda4e01989c8d7d766b1`, and the existing `EndToEndTests.swift` reference in the workflow/README.

### Resume checkpoint
- Last fully completed no-finding file remains `app/Package.swift`; the latest fully read files with open findings are `app/README.md` and `app/Sources/AtlasApp/AtlasApp.swift`.
- Continue with the next PR changed-path entry after `app/Sources/AtlasApp/AtlasApp.swift`: `app/Sources/AtlasApp/Components.swift`. Before opening it, reconcile the historical review record and current blob SHA; do not re-read files already covered unless their blob changes.
- Review boundary unchanged: docs/defect ledger and review comments only; no app source/tests/build/config edits, no approval/merge, and no thread resolutions.


### Component/design-system file review continuation — 2026-11-24

**Reviewed at PR head:** `b03af0133c98075487cc1ad52f688993040839eb`.
- `app/Sources/AtlasApp/Components.swift`: all 179 lines inspected (blob `0e52e88c6833ca04e3f34d2c241163fc4b44d15b`). Reviewed PageHeader, StateNotice, PhaseLabel, CitationChip, EvidenceInspector, ActivityRow and ApprovalSheet. No component-level defect established in this file. This is source inspection, not a human accessibility acceptance claim; hosted accessibility evidence is separately tracked.
- `app/Sources/AtlasApp/DesignSystem.swift`: all 67 lines inspected (blob `b59e7b355f13cd31e11b21e9869b3470ab44c066`). Token-backed semantic colours, spacing/radius/metrics, scalable system text styles, Reduce Motion and reading-column helpers inspected. No defect established in this file.
- These two rows are now `REVIEWED—NO FINDINGS`. Updated exact-head inventory: **278 total; 142 IN REVIEW; 129 NOT STARTED; 5 REVIEWED—NO FINDINGS; 2 REVIEWED—FINDINGS OPEN**. This remains a path review ledger, not a claim that 142 IN REVIEW files are complete.
- Next file in the app source/UI sequence: `app/xcode/AtlasMacUITests/AccessibilityAuditTests.swift`; the audit test itself needs independent review of its issue exemptions and contrast-measurement logic.


### macOS accessibility audit test review — 2026-11-24

**Reviewed source snapshot:** PR #8 head `58ffc5ba4b31a3435fdbb76e9e6f85619a5a8896`; file blob `0059680d01bb94838b459e98d0a8606c434895c9`; all 92 lines inspected.
- **ATLAS-TEST-054 (P2, OPEN):** the contrast exemption uses the darkest/lightest pixel anywhere in the element frame as if they were the actual foreground/background pair. Unrelated pixels can inflate the ratio and suppress a real contrast failure. The method needs a valid text/background comparison or must not suppress the audit finding.
- **ATLAS-TEST-055 (P2, OPEN):** a fixed 8-second sleep followed by “static texts are non-empty” does not establish that the expected owner/onboarding screen is ready; a transient “starting” screen can pass. Wait for and assert a stable expected screen before auditing.
- Both findings are appended to `DEFECT_REGISTER.md`; review-only changes. No UI test was run locally. The CI workflow's current run must still be checked for its outcome; this code inspection is not a CI pass.
- Updated exact-head path counts: **278 total; 141 IN REVIEW; 129 NOT STARTED; 5 REVIEWED—NO FINDINGS; 3 REVIEWED—FINDINGS OPEN**.
- Next PR path in the UI test sequence is `app/xcode/project.yml` only if not already fully inspected; otherwise continue with the next unreviewed path in the 278-path inventory. The file itself is a test and remains findings-open until Claude corrects both issues and independent re-review confirms them.


### Screens.swift full-file review — 2026-11-24

**Reviewed at source snapshot:** PR #8 head `ea2ba5acd92237e3b2f2cc583f04ad47f45c06e9`; blob `9b5ad87b6b762201a33b4af4737b2ff655145deb`; all **772 lines** inspected, including Home, Ask/Composer/Turn, Library, Records/AddRecord, Finance, Web, Connections, Health, Activity, Get Started, Settings and QR generation.
- **ATLAS-APP-056 (P2, OPEN):** ActivityView renders only `model.activity`; Core attention events are loaded into `model.attention` and included on Home but omitted from the Activity list, despite the Activity subtitle promising decision items. Finding added to `DEFECT_REGISTER.md`.
- Existing **ATLAS-UX-023** remains open: the Activity feed and task outcomes are process-memory-only and lost on restart. This is distinct from the newly found missing-attention-feed defect.
- No app source or test file changed; no local test execution. The file remains `REVIEWED—FINDINGS OPEN` pending implementation and re-review.
- Updated exact-head ledger totals: **278 total; 141 IN REVIEW; 129 NOT STARTED; 5 REVIEWED—NO FINDINGS; 4 REVIEWED—FINDINGS OPEN**.
- Next source path to complete from existing partial inspection: `app/Sources/AtlasApp/Shell.swift` (historical ledger says full source inspected; first compare its current blob SHA before deciding whether a delta review is needed).


### Activity screen source review completed — 2026-11-24

- `app/Sources/AtlasApp/Screens.swift`: all 772 lines re-read in contiguous ranges at blob `9b5ad87b6b762201a33b4af4737b2ff655145deb`. Home/Ask/Composer/Library/Records/Finance/Web/Connections/Health/Activity/Get Started/Settings and QR rendering inspected. The reproducible omission is logged as **ATLAS-APP-056 (P2, OPEN)**: Activity uses only `model.activity`, whereas Home explicitly merges `model.activity + model.attention`; attention-only calendar-conflict items therefore disappear from Activity. No local test run. The file is findings-open, not clean.


### Shell, voice adapters and activity model review — 2026-11-24

Reviewed at PR #8 head `9af6e7a25a1c3e29b0fa0f986f9c245933d3dc0e` (all listed files read in full):
- `Shell.swift` 94 lines, blob `f2b033590dc4dab646078f0c359dd61a92b18399`: launch gating, onboarding, approval identity binding, sidebar/detail selection and compact inspector presentation. No defect established.
- `Speaker.swift` 26 lines, blob `cc0f5791b3f5111fbf10746c083d2ef6e6c83645`: local AVSpeechSynthesizer adapter, finish/cancel dispatch and stop behavior. No defect established in this adapter.
- `Speech.swift` 61 lines, blob `67c6f119059be0b3f939710249857f9786683d4a`: on-device recognition requirement and microphone lifecycle inspected. **ATLAS-VOICE-057 (P2, OPEN)**: failed engine start after installing tap leaves request/tap state uncleared.
- `Activity.swift` 69 lines, blob `14c66e0211453fb5befffa94d1a006ff95a5b5a5`: merge/deduplication, sort, attention projection, recent tasks and allow-listed calendar-conflict mapping. No independent defect established; UI omission remains separately logged against Screens.swift.
- No app source or tests changed; no tests run locally.


### AtlasKit answer, approval and connector model review — 2026-11-24

At PR #8 head `81ffe3fbc86b7a750f2429a4b5a895dd913ea4de`, read in full:
- `Aloud.swift` (34 lines; blob `295c813fc38a68a3f09fc5d685f70591d6d6de7e`): local answer/trust composition, empty-answer guard and single active speak/stop state. No defect established.
- `AnswerView.swift` (39 lines; blob `74e0e35a052a5a15dd8c1397bf41cb6f099baed2`): API dictionary mapping, controlled catalogue fallbacks, coverage/not-searched formatting and citation locator rendering. No defect established.
- `Approval.swift` (88 lines; blob `c3240bf8889c86f1c7dcc1b4326874885c332025`): closed action/consequence allow-list, deterministic sorted payload fingerprint, expiry and pending/approved/terminal state transitions. No defect established.
- `Catalogue.swift` (49 lines; blob `85d6f554e25915515aae2615d049f4870b625992`): required catalogue keys and controlled error fallback. No defect established.
- `Connections.swift` (101 lines; blob `42f22a927db330a4f6ed563b6f3f4b0a92c4da68`): response-to-view mapping, approval wording, URL scheme and private/VPN host rules. Cross-checked Core connector states and effect-to-approval mapping in `core/src/atlas_core/connectors.py` and connector catalogue; expected states and approval values are constrained by Core. No defect established.
- All five rows moved to `REVIEWED—NO FINDINGS`. This is source inspection only; no tests run locally.


### Core client, launcher, finance and first-run review — 2026-11-24

At PR #8 head `cb472a1e9b9b6572f501e9391473fd3344ec83c0`, all four files read in full:
- `CoreClient.swift` 119 lines, blob `c5d6748a0c8ebe148619da72608f8871fc80a28b`: signed API calls, version echo enforcement, task/action/consent/connector/web/records surfaces. **ATLAS-CORE-062 (P2, OPEN)**: successful ask response with absent/non-string task ID is silently converted to empty string.
- `CoreLauncher.swift` 166 lines, blob `9487c31ba5a9d26e46b7a71cb27c580c6ccbc16b`: random bootstrap secret, process identity, pid record, stale socket handling, readiness and stop/reap. Lifecycle checks inspected; the embedded initializer comment “packaging the Core into the app is not built” is stale against the CI packaging job and is covered by **ATLAS-DOC-052**.
- `Finance.swift` 87 lines, blob `5da7d8dc16fb79e4a1cfd225811f72f23d79f7fd`: source naming/sensitivity and exact Core-provided spending presentation. **ATLAS-FIN-063 (P3, OPEN)**: zero delta is labelled “more”.
- `GetStarted.swift` 23 lines, blob `bf9fa0c759f6abfb9173f7fb198adc03db7fd7a7`: default-off choice, no-grant empty selection and first-run completion rule. No defect established.
- No app source/tests/build files changed; no tests run locally.


### Review-ledger reconciliation after parallel historical review recovery — 2026-11-24

The current branch contains additional exact-file reviews recorded by a parallel documentation pass. I reconciled those records rather than restarting or overwriting them:
- `Shell.swift` and `Speaker.swift` were read in full at unchanged blobs; no implementation defect was established in the speech-output adapter. `Shell.swift` participates in **ATLAS-APP-057**, now explicitly classified as a potential P3 pending a macOS UI dismissal test; source inspection alone cannot prove the native sheet has no platform dismissal affordance.
- `Speech.swift` has one canonical finding **ATLAS-VOICE-057 (P2, OPEN)**. Removed the duplicate `ATLAS-APP-058` entry; do not count the same engine-start cleanup issue twice.
- `Activity.swift` was read in full (69 lines, blob `14c66e0211453fb5befffa94d1a006ff95a5b5a5`); the model's deduplication and attention projection are sound. The missing Activity-screen feed remains **ATLAS-APP-056** against `Screens.swift`, not a defect in this model file.
- `Components.swift` and `Shell.swift` are findings-open only for the potential terminal-approval dismissal issue; verify in a macOS UI test before treating it as a confirmed user trap. `Speaker.swift` remains no-findings.
- Updated inventory: **278 total; 133 IN REVIEW; 127 NOT STARTED; 13 REVIEWED—NO FINDINGS; 5 REVIEWED—FINDINGS OPEN**.


### Transport, health, library, lifecycle and navigation review — 2026-11-24

At PR #8 head `77e584b3a4a13dbe9266fa13cf298e5fabdc5df5`, all five files were read in full: `HTTPTransport.swift` (45 lines, blob `42e491ccda9d4f516332564e30926d19a95d3f89`), `Health.swift` (57 lines, blob `4d2274eda747907ec27ff9f13820c8a5d1100499`), `Library.swift` (67 lines, blob `e433872979892bef3382fb04589f134ed4a54443`), `Lifecycle.swift` (89 lines, blob `4d1b6c99974019b41d0d8d36dcf92378f5f97271`) and `Navigation.swift` (97 lines, blob `9e4edd8b04eb25a6a61c77a4029fe7a9b9f26d93`). Reviewed remote URL/TLS/redirect/response bounds, health provenance and units, library state and coverage mapping, task phase transitions, and availability-based navigation/restoration. No independent defects established in these files. No tests run locally.


### Notifications, offline sync, pairing, phone engine and records review — 2026-11-24

At PR #8 head `b7e60221178607ceca873fe83c30fb858cee7a45`, all five files read in full: `Notifications.swift` (27 lines, blob `10f190200f659d696f5e71ba92288c91c5b58dd9`), `OfflineSync.swift` (143, `d489f50d22fbd235407a0bd88279f2262c036208`), `Pairing.swift` (133, `ffcac447acf9c701962d5ca237d2ba9f72bfbad0`), `PhoneEngine.swift` (137, `f1beb87d001f0daafd8e3bc3b841dc476ba12215`) and `Records.swift` (132, `2a0c22aca0ad8f25574a251886ab3983abab80ac`). Findings: **ATLAS-PAIR-065 (P2, OPEN)** duplicate invite query keys can trap; **ATLAS-PHONE-064 (P2, OPEN)** a missing transport leaves the paired device link falsely online. Notification opt-in/deduplication, offline queue restrictions and conflict handling, pairing proof-before-save, and record payload validation were inspected. No other defects established. No tests run locally.


### Relay, review, screen state, signing and submission gate review — 2026-11-24

At PR #8 head `8537e5b54bb961bcd852dae782f43852f5643156`, all five files read in full: `RelayBind.swift` (19 lines, blob `e24ef7e990440262f5e73f7fc3212798afc75ae6`), `Review.swift` (38, `e4dbe60256a239eb9afa4cede90cf535c93c5a0a`), `ScreenState.swift` (115, `9abb5317eaab4ce87d7dab46409f74f0b1f3a7d4`), `Signing.swift` (27, `43401debacd5ccd4f545dccc1f3c04a8dbbe66fc`) and `SubmissionGate.swift` (18, `a9d2ce60a661916051c7d930ee9af8ac3e7c485f`). Reviewed network bind allow-list, review section mapping, UI state fallbacks, canonical signature construction and single-flight submission gate. No independent defects established; task-ID race remains logged against AtlasApp. No tests run locally.


### Design tokens, transports, updater, voice state and web view review — 2026-11-24

At PR #8 head `33c0301905addc059aef0b63098c7987738e1327`, all five files read in full: `Tokens.swift` (91 lines, blob `e94c1bf0265425a9ad63a46abc0933cd0440dbf6`), `Transport.swift` (58, `9cace9872487c2bc3a1cd439e60c3fdcf4eb27ef`), `Updates.swift` (42, `20bcab714271a40b752cb5dec223a556029fde9c`), `Voice.swift` (111, `7ce1093ebee791911cec3444f4409644d88c24fc`) and `Web.swift` (53, `1c4f8d8fcbfcc8374269de1e84efa3575b195214`). Findings: **ATLAS-HTTP-066 (P2, OPEN)** response size caps are not enforced during streaming; **ATLAS-VOICE-067 (P2, OPEN)** repeated permission requests can create overlapping voice sessions. The Unix transport is also uncapped. Design tokens, update-result mapping and web allow-list/error presentation inspected without other defects. No tests run locally.


### E2E, phone and voice regression-test review — 2026-11-24

At PR #8 head `6d975573b63456c7702c573fdb58fb8fe95a11b7`, inspected the full `EndToEndTests.swift` (197 lines, blob `c9285731aa996a43e0148aa774049a7c69931f03`), `PhoneTests.swift` (full file) and `VoiceTests.swift` (full file). **ATLAS-TEST-069 (P1, OPEN)**: both E2E suites delete production-named Keychain service items rather than using an isolated test keychain; local execution can destroy real Atlas keys. Voice tests use synchronous permission callbacks and do not cover repeated taps/delayed permission resolution, leaving **ATLAS-VOICE-067** unguarded. Phone tests cover normal offline cache, sync and revocation, but not the no-transport branch in **ATLAS-PHONE-064**. No tests were run locally.


### AtlasKit unit-test inventory continuation — 2026-11-24

At PR #8 head `45324737c0f177314edf8363f1c51fad671f0ff7`, fully inspected Aloud, Connections, DesignSystem, Finance, GetStarted, Health, Library, Notification, ReapIdentity, Records, Review, Signing, SubmissionGate, Update and Web test files. The Finance test suite has no zero-delta case (**ATLAS-FIN-063**); SubmissionGateTests verify only the standalone gate and do not cover the AppModel current-task identifier race (**ATLAS-APP-052**). These two test files are findings-open. Other listed test files were marked reviewed with no independent issue. No tests were run locally; this is static test-source review only.

### Swift transport and protocol finding reconciliation — 2026-11-24

- Consolidated the malformed-response observations into **ATLAS-CORE-062** (no duplicate ATLAS-API-060): CoreClient's missing `task_id`, `state`, passage text and collection fields must be treated as protocol errors, not empty/success-shaped values.
- Consolidated response-memory findings into **ATLAS-HTTP-066** (no duplicate ATLAS-TRANSPORT-061): RemoteHTTP's 4 MB check occurs after full URLSession buffering; UnixHTTP also has no incremental cap or read deadline. Both transport rows are findings-open.
- Consolidated the destructive Keychain test finding under **ATLAS-TEST-069** (no duplicate ATLAS-TEST-062). The more complete finding also covers `PhoneTests.swift`, not only `EndToEndTests.swift`; exact production Keychain service names and the unscoped delete command are the risk.
- Current exact-head path inventory after reconciliation: **278 total; 99 IN REVIEW; 119 NOT STARTED; 40 REVIEWED—NO FINDINGS; 20 REVIEWED—FINDINGS OPEN**.


### XcodeGen build/project specifications re-review — 2026-11-24

At PR #8 head `98e333b9904bf6906a9211f81524feb6234f2bf4`, re-read `app/Package.swift` (15 lines, blob `0028b51d4e24ad9c0e36e2e816732edeb2df2de2`), `app/xcode/project.yml` (51 lines, blob `e9a540c146e1dd3b8a2f3614b637407f727bb643`) and `ios/project.yml` (52 lines, blob `4e929d5de1a3ddb12532fda4e01989c8d7d766b1`). Package/platform/product alignment is consistent. **ATLAS-DOC-070 (P3, OPEN)**: the macOS XcodeGen spec comment says it is not checked in although this file is committed. The iOS project specifies iOS 17, AtlasKit linkage, camera-purpose text and a simulator UI-test scheme; no independent issue established there.


### iOS application, storage, screens and accessibility test review — 2026-11-24

At PR #8 head `13f7904d6c8e04b63c0e91149d8df0876658fc21`, read all iOS paths in full: `AtlasPhoneApp.swift` (12 lines, blob `ab6bdca5de9c03b5dd178c2046e61f4dd4109d8b`), `PhoneModel.swift` (94, `4c03781d402d8f1ce7cb150d16f0245694f5061a`), `Storage.swift` (56, `5f9df32ac0960f411746c86970a3baacf1f9aa8e`), `Views.swift` (224, `e62d599c8275ee5886ad9a1e220b1e7e0f25ba91`), iOS `AccessibilityAuditTests.swift` (103, `0fc5d4bee166b95ee258a64cf8f6d91d44300c09`) and `ios/README.md` (8, `c84853f9ee56764eaed8955e3b08758212cfbe4d`). **ATLAS-PHONE-072 (P1, OPEN)**: an in-flight detached read can rewrite cached owner records after Unpair clears the cache. **ATLAS-TEST-071 (P2, OPEN)**: iOS contrast exemption can false-pass using frame-wide pixel extrema. Phone keychain/file protection, screens, pair confirmation and documentation otherwise inspected. No tests run locally.

### Phone pairing and offline queue review — 2026-11-24

**Source snapshot:** PR source head `13f7904d6c8e04b63c0e91149d8df0876658fc21`; source blobs unchanged in subsequent documentation-only commits.
- `PhoneEngine.swift` (137 lines, blob `f1beb87d001f0daafd8e3bc3b841dc476ba12215`) remains findings-open for **ATLAS-PHONE-064**: a paired vault entry is treated as online even when no transport can be created; records/sync/ask do not consistently move the link state to offline.
- `Pairing.swift` (133 lines, blob `ffcac447acf9c701962d5ca237d2ba9f72bfbad0`) remains findings-open for **ATLAS-PAIR-065**: duplicate query names trap `Dictionary(uniqueKeysWithValues:)`; removed duplicate alias ATLAS-PAIR-070.
- `OfflineSync.swift` (143 lines, blob `d489f50d22fbd235407a0bd88279f2262c036208`) is now findings-open for **ATLAS-OFFLINE-071 (P1)**: malformed/truncated persisted queue bytes are silently treated as an empty queue, and the next enqueue can overwrite the only copy of queued offline changes. Preserve corrupt bytes and surface recovery; do not show zero pending edits.
- `PhoneTests.swift` (187 lines, blob `7128eb6cb48cf38f3821e4a0ff6b412dba179b3b`) was read in full. Existing ATLAS-TEST-069 destructive Keychain cleanup and ATLAS-PHONE-064 no-transport test gap are already recorded; duplicate-query and corrupt-queue regression tests are absent.
- No app source/tests changed; no tests run locally. Exact path counts must be recalculated from the current table rather than copied from the earlier checkpoint.


### CI, shared UX catalogue, Core README and benchmark review — 2026-11-24

At PR #8 head `3412885e218f65665dd8023325800c226e612201`, read `.github/workflows/ci.yml` (293 lines, blob `1faee779b3512942c498268a41545d8869a13038`), both UX catalogue JSON files (147 lines each; identical blob `0c0419cc525d9ed71952363264c98d4a5dbf2bad`), `core/README.md` (13 lines, blob `2c533cfaae18f64d60d318f9597ed98beb2ff97a`), `core/bench/ingest.py` (152, `dee08e35145e8b166897f960800e9d3897fea5c1`) and `core/bench/overhead.py` (88, `e02e7840c0a5cf479c58d780fc12cfde173908bb`). Findings: **ATLAS-DOC-074 (P2, OPEN)** Core README capability inventory is obsolete; **ATLAS-BENCH-073 (P3, OPEN)** ingest benchmark RSS units are wrong on macOS. CI workflow job wiring and artifact/test scopes inspected; no workflow defect established from static review. No CI run outcome inferred from this file review.

### Records response validation review — 2026-11-24

- `Records.swift` (132 lines, blob `2a0c22aca0ad8f25574a251886ab3983abab80ac`) and `RecordsTests.swift` (88 lines, blob `a7bd41f90ef678a9c8bcb8f19799f65d5822428b`) were read in full at source head `91a33a8d36f8403daa2cee42b1e6d719659c7548`.
- **ATLAS-RECORD-072 (P2, OPEN):** RecordsOutcome.compactMap silently discards malformed rows. If every row is malformed it returns `.empty`; if only some are malformed it returns `.loaded` with the remainder and no partial warning. The tests cover valid/empty/missing payloads but not malformed rows. Both source and test rows are findings-open.
- `RelayBind.swift` and `Notifications.swift` were also read in full at unchanged blobs; their strict private-address allow-list and content-free, opt-in notification planner showed no new defect in this pass.
- No source/tests changed and no local tests were run.


### Reference client and API contract generation/test review — 2026-11-24

At PR #8 head `91a33a8d36f8403daa2cee42b1e6d719659c7548`, read `atlas_client.py` (348 lines, blob `2abc2310aef2d9d4c489b1f26d83697c4a9945ec`), `contracts.py` (133 lines, blob `a872b9eb7ad117a48d27a9ff44fd0dd7ba3b35cc`), `test_contracts.py` (68, `d8b19c9e803c09a88458f90bccab7f5e2ee8aede`), `test_contracts_frozen.py` (52, `e2bf4b3a581101bb7846e082819174459578610b`) and `test_contracts_v11.py` (731, `b0feb79cf71002907fcad345ce0a7c47ab06defa`). Findings: **ATLAS-CLIENT-076 (P2, OPEN)** reference client task-ID validation and response-body exception normalization; **ATLAS-DOC-075 (P3, OPEN)** stale comment about API 1.1 support. The contract tests statically assert strict unknown-field rejection, deterministic delta merge, exact frozen 1.0 baseline, conditional coverage/limitation semantics, content-free telemetry fields, OpenAPI parity and signing vectors. Tests were not executed in this review.


### Reference-client regression-test review — 2026-11-24

`core/tests/test_client.py` (344 lines, blob `efac279c4254f0f175799f7f3afc73e36821f48d`) read in full at PR #8 head `873d7329e01f69d44393761845e39f83ca67e1e8`. The test harness exercises the signed Unix-socket client, catalogue completeness, citations, source revocation, cancellation, version echo, 1.0 compatibility and exact computation. It does not cover a successful task response with a missing/null/empty task ID or a disconnect/timeout while the body is being read; both gaps are tracked under **ATLAS-CLIENT-076 (P2, OPEN)**. No tests run locally.


### Contract artefact inventory update — 2026-11-24

Read the full 265-line frozen 1.0 JSON Schema and 103-line 1.0 OpenAPI document. Their frozen baseline hashes are asserted by the contract tests. The 1.1 delta (2679 lines, 47 additions and 5 overrides), merged schema (3253 lines) and 1.1 OpenAPI (1155 lines) were structurally parsed and cross-checked against the complete 731-line contract test suite, including deterministic merge, strict additionalProperties, conditional coverage/limitation mappings, content-free event fields, path/operation parity and signing vectors. They remain **IN REVIEW** pending deeper exhaustive artefact review and test execution; no runtime or CI pass is claimed.

### SourceAccess security-gate review — 2026-11-24

- `core/src/atlas_core/access.py` (136 lines, blob `09347ddbfd9fcc2a947824caa2db6760026ddc41`) read in full at PR source head `e3f2386e58f42628c1a7f358177ec9a531d14aa6`.
- Cross-checked the access decision path against `core/tests/test_designation.py` (default deny, owner consent alone insufficient, current positive OS evidence required, stale/future/wrong-source/provider-failure fail closed, missing-before-first-grant preserves consent, positively observed permission loss revokes and purges, regrant creates a new identity) and `test_consent_api.py`/`test_macos.py` (owner-only consent and provider behavior).
- No source-level defect established in `SourceAccess`; row moved to `REVIEWED—NO FINDINGS`. This is not evidence of real macOS/TCC behavior: the source module itself states the real TCC discovery adapter is not implemented, and fake-provider tests do not establish owner-Mac acceptance.

### Action Gateway full source and test review — 2026-11-24

- `core/src/atlas_core/actions.py` (314 lines, blob `0a690d3300ea62a8b4ac1e41605786e654bc665b`) and `core/tests/test_actions.py` (229 lines, blob `56dcb9bd1cd64bb1ada41746684e760982524307`) were read in full.
- Existing **ATLAS-ACT-019 (P1, OPEN)** remains: approvals, action receipts, undo records and idempotency state are in-memory. I expanded it to note that a missing or zero-length audit file is accepted as an empty valid chain, so whole-file deletion/truncation is not detected.
- Added **ATLAS-ACT-074 (P2, OPEN)**: `ActionSpec.category` chooses `min(found)` when multiple approval-requiring effects are declared; the owner sees only one category and can miss another consequence (e.g. spend + external send).
- Added **ATLAS-ACT-075 (P2, OPEN)**: unknown actions and invalid undo attempts return refusals without audit entries, despite the “every outcome” guarantee.
- Existing tests cover single-category actions, exact-payload approval, replay, handler failure, undo, workflow rollback and a damaged non-empty audit file. They do not cover multi-category disclosure, unknown/invalid undo audit entries, missing/empty audit-file deletion, or restart persistence of approval/receipt/undo/idempotency state.
- Updated path counts: 93 IN REVIEW; 100 NOT STARTED; 52 REVIEWED—NO FINDINGS; 33 REVIEWED—FINDINGS OPEN (278 total). No tests run locally.

### Egress gateway full source/test review — 2026-11-24

- `core/src/atlas_core/egress.py` (409 lines, blob `0aa66a988a73b027ac1aa762da00bf60d6d533ae`) and `core/tests/test_egress.py` (336 lines, blob `64881f56dc2de803cda7d88068db1646b288467b`) were read in full at PR source head `443851b110642d1fde8478d73544392d2c51ba77`.
- Existing **ATLAS-SEC-014 (P1, PARTIALLY ADDRESSED / OPEN)** remains for the explicitly unsupported short (1–3 character) identifiers and paraphrases; do not claim complete egress privacy coverage.
- Added **ATLAS-EGRESS-077 (P2)**: blocking DNS resolution is outside the configured request timeout.
- Added **ATLAS-EGRESS-078 (P2)**: text is capped at 200,000 characters without setting `truncated` when the raw body is below 512 KiB.
- Added **ATLAS-EGRESS-079 (P2)**: invalid URL ports can raise unhandled `ValueError` instead of a typed `Denied` response.
- Tests cover taint, identifiers, encoding, redirect checks, content types, and body byte caps, but not these three cases. No local tests or real-Internet requests were run.
- Updated path counts: 91 IN REVIEW; 100 NOT STARTED; 52 REVIEWED—NO FINDINGS; 35 REVIEWED—FINDINGS OPEN (278 total).


### Core sandbox, worker, host, transport and Mail adapter review — 2026-11-24

At PR #8 head `910f7fa02390c7c3a24abc215374343d27d22217`, read all 165 lines of `sandbox.py`, 120 of `worker.py`, 169 of `isolated.py`, 202 of `transport.py`, 176 of `host.py`, 521 of `macos.py`, and 509 of `mail.py`. Revalidated the historical sandbox bypass concern: current worker has no `--skip-self-sandbox` option; `test_the_worker_has_no_flag_that_skips_its_confinement` asserts argparse rejects it. Seccomp blocks non-UNIX socket domains and io_uring; macOS launch profile denies network, private reads and writes, and the worker verifies OS refusal before accepting work. Socket peer identity, request framing/size limits and connection bounds inspected. Production host remains macOS-only; live web engine remains disabled. **ATLAS-MAIL-079 (P2, OPEN)**: EmlxMailbox silently skips inaccessible nested directories/files and turns a failed root pin into an empty list; MailIndex cannot distinguish this from a complete empty mailbox, so coverage may falsely say complete. Descriptor-relative no-follow access and byte-bounded MIME parsing are otherwise carefully guarded. No tests run locally.

### Answer envelope and citation verification review — 2026-11-24

- `core/src/atlas_core/answer.py` (159 lines, blob `43b220994e8d5f81bb872b8e9b3d855afc4df090`) and `core/tests/test_evidence_answer.py` (185 lines, blob `532fb7e80892dac66877f572fd1d4e395a60713e`) were read in full at source head `10d713b7c475364cca2eaebf8eba878312ff1219`.
- Cross-checked `service.py` construction of AnswerInput, `evidence.py` exact citation resolution, and tests for retrieved-only citations, stale sources, wrong quotes, numeric figures/dates, language confidence, truncation, partial work, denied and withheld answers.
- No independent defect established in the answer envelope path in this pass; rows moved to `REVIEWED—NO FINDINGS`. This does not establish model-runtime correctness or real-model behaviour; those remain separate acceptance gates.
- Updated path counts: 83 IN REVIEW; 99 NOT STARTED; 59 REVIEWED—NO FINDINGS; 37 REVIEWED—FINDINGS OPEN (278 total).


### Core API, identity, transport and confinement test cross-check — 2026-11-24

At PR #8 head `910f7fa02390c7c3a24abc215374343d27d22217`, completed full line-by-line reads of `api.py` (563 lines, blob `3b1103a3e14eb5e5f7a3a4f640c9e286c5fd690c`) and `identity.py` (186, `9aa0e1012470daee119cf77d93237025ba0b4fb7`). Signed version binding, owner/member authorization, one-time enrolment, route families and content-free error handling cross-checked against `test_api.py` (194, `e51f24f89679f70d8ad2dae80f0c9979f9f85493`) and `test_enrolment.py` (243, `7607fb4f301b126f8e19e47545b77bb01ed374c2`). `test_isolated.py` (350, `81a801473535beb0589d39fee4e1f49e81ef2955`) and `test_transport.py` (240, `cfbd11419f815cb7f66c968fb56c3406f2a7d981`) fully read; no independent findings. `test_macos.py` (710, `3248ae258c805b669d3f0e6d3ec815ebdb0ddbc0`) fully read; its symlink/race/attachment byte-boundary tests are strong, but it does not test that a skipped inaccessible subtree or root symlink makes MailIndex coverage partial, so ATLAS-MAIL-079 remains open. No tests run locally.


### API 1.1, consent and operations route regression review — 2026-11-24

Fully read `test_api_v11.py` (188 lines, blob `b31280375a2de69bc8dbfa991bc11deb62e54a87`), `test_consent_api.py` (190, `e48338dfd790c7b6a715f79202f77347335bfb83`) and `test_operations_api.py` (310, `2c132f7ebdcfc1a2141566a564cb23f1c8218555`). They cover signed version negotiation/no downgrade, additive coverage/model identity, honest limitations, exact compute validation, owner-only consent/mode/actions, replay-safe withdrawal and index purge, member sync idempotency/conflict, device pairing/revocation, own-record access and signed updates. No independent test defect established. No tests run locally.

### Backup/restore full source and test review — 2026-11-24

- `core/src/atlas_core/backup.py` (405 lines, blob `3b415da1c4572dcb88bfed8ba926c9fd50841fd2`) and `core/tests/test_backup.py` (300 lines, blob `20e57e718e8a33f6565477f1ea4ebcc48fe2b7a0`) were read in full at source head `b189f8d0125f3f939b2c4428f29bd3c378bd24ed`.
- Added **ATLAS-BACKUP-080 (P2)**: restore drill unconditionally removes the scratch target even if it was an existing empty folder.
- Added **ATLAS-BACKUP-081 (P2)**: nested malformed manifest entries and non-dictionary decrypted key bundles can raise raw `AttributeError` instead of failing closed with a backup code.
- Added **ATLAS-BACKUP-082 (P2)**: copied `clients.json` and `actions-audit.jsonl` are not rehashed after copy, leaving a verify-to-copy race; only DB copies are rechecked.
- Existing tests cover corrupted/truncated/missing files, MAC tampering, wrong passphrase, restore rollback, no-grant restore, restore drill and encrypted edits/audit. They do not cover these three edge cases. No local tests or real restore were run.
- Updated path counts: 75 IN REVIEW; 95 NOT STARTED; 68 REVIEWED—NO FINDINGS; 40 REVIEWED—FINDINGS OPEN (278 total).
