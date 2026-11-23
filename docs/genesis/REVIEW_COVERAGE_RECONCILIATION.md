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

