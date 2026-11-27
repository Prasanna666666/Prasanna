# Atlas review and implementation tracker

One versioned **final-product acceptance register** (`core/docs/acceptance_register.json`) and one headline pair, scored by the rules both
the implementer (Claude) and the architect (Codex) agreed on PR #8 ([comment 7226542434](https://github.com/Prasanna666666/Prasanna/pull/8#issuecomment-7226542434)).
The first Mac release checks are mapped into the same register as MAC-01 to MAC-20, so the milestone is a subset, not a separate score.

- **Implementation readiness** = earned points / every criterion. A criterion earns 1 when all its required checks pass with traceable
  evidence, 0.5 only when it defines an intermediate checkpoint and that checkpoint passes, 0 otherwise. Missing evidence earns 0.
- **Review completion** = criteria with a recorded Codex verdict (pass or fail) against a specific revision, with its link / the same total.
  A criterion whose evidence a later change invalidates is reopened and earns 0 until reviewed again.
- Unknown states, partial claims without a defined checkpoint, claims without evidence and verdicts without revision or link score 0 and are
  **listed as flags**; nothing leaves the denominator. Mandatory blockers and owner sign-off are reported separately: release approval needs
  every mandatory criterion passing and the owner's sign-off, whatever the percentages say.

Neither number is an acceptance. Codex owns the verdicts and the score reconciliation; Claude owns fixes and evidence; the owner signs off.

## Current measure

Kept current with every change: `python3 scripts/progress.py --update` rewrites this block, and a test fails on any commit whose tree does
not match it. A read-only commit check (`--hook`, Claude Code PreToolUse) refuses a commit while the block is stale; it never edits or stages.

<!-- measure:start -->
**Implementation readiness 17.0%** (38/224) · **Review completion 3.6%** (8/224) · register v0.1 at `95f67f4` (proposed by Claude; inventory to be checked and confirmed by Codex by SHA before an agreed baseline is published)

Mandatory criteria not yet passing: **215** of 224. Owner sign-offs recorded: 0.

| Part of the register | Criteria | Implementation | Review |
|---|---:|---:|---:|
| first-mac | 20 | 12.5 (62%) | 8 (40%) |
| prd | 63 | 3 (5%) | 0 (0%) |
| roadmap | 3 | 2.5 (83%) | 0 (0%) |
| stage3 | 19 | 4 (21%) | 0 (0%) |
| stages4to8 | 34 | 14 (41%) | 0 (0%) |
| use-case | 85 | 2 (2%) | 0 (0%) |

First Mac milestone subset (MAC-01 to MAC-20): implementation 12.5/20 (62.5%), review 8/20 (40.0%).

Supporting inventory (git-tracked): 285 source files, 46,471 lines, 2959 functions; 210 test files, 1893 test functions. Whole-product line and function review coverage: **unmeasured** (reviewed ranges are recorded per batch from 5 batch record(s); no defensible whole-product numerator yet).
<!-- measure:end -->

## Register v0.1: how it was built

`scripts/build_acceptance_register.py` derived 224 criteria, each with a stable ID, stage, requirement/design references, owners
(implementation Claude, verdict Codex, sign-off owner), a pass condition, required evidence and its intermediate checkpoint:

| Part | IDs | Criteria | Source | Checkpoint (0.5) | Full credit (1) |
|---|---|---:|---|---|---|
| Stages 0-2 | S0-01, S1-01, S2-01 | 3 | roadmap, TARGET_ARCHITECTURE §11 | documents exist | stage evidence complete (S1 audit, S2 accepted head) |
| Stage 3 | S3-C01-C15, S3-F4/F11/F12/F13 | 19 | core/docs/STAGE3_ACCEPTANCE.md | MET-L: met locally, tests passing | met on the candidate with its final-stage portion passed; final gates have no checkpoint |
| Stages 4-8 | S4-X.. to S8-X.. | 34 | core/docs/STAGES_4_TO_8.md exit rows | MET-L (implementer's report) | target-Mac or owner evidence |
| PRD | PRD-<section>-<n> | 63 | docs/genesis/PRD_CONFORMANCE.md | IMPLEMENTED with tests | met, no open gap (ALIGNED scope guards) |
| Use cases | UC-... | 85 | docs/genesis/USE_CASE_CONFORMANCE.md | IMPLEMENTED with tests | met, no open gap |
| First Mac | MAC-01 to MAC-20 | 20 | architect checks at 95f67f4 (`FIRST_MAC_CHECKS_95f67f4.md`) | the architect's 0.5 state | the architect's 1 state |

**Inventory note (reply to the architect's point 2).** The 34 Stage 4-8 criteria are every scored exit row of the five stage sections; the
deliberately-never-offered destructive migration row is a scope guard and is not a criterion. The earlier "43 later-stage units out of 65"
was a hand count in the superseded estimate and is withdrawn. **Accepted units with verdict links:** MAC-04, MAC-10, MAC-11, MAC-12, MAC-16 (pass)
and MAC-06, MAC-08, MAC-14 (fail), all at `95f67f4` ([review 6092414795](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6092414795)).
Stage 2 (accepted at `5821022`) and Stage 3 criterion 6 are claimed accepted in the PR description, but no verdict link was found on PR #8,
so they earn **no review credit** until one is attached. WP3.1 (`800d137`, review 6000401465) and WP3.2 (`ad6e59b`, review 6000818496) were
scope acceptances, not register criteria, and are recorded as evidence only.

**Known overlap.** MAC criteria restate parts of Stage 3 and PRD rows. v0.1 keeps both (each with its own ID) rather than guessing the mapping;
reconciling them into one criterion each is the first proposed change for v0.2, to be agreed and re-baselined.

## Review coverage (supporting measure)

`review_batches` in the register records, for each batch Codex reviewed, the exact revisions, link, changed files, changed lines and the
function contexts of the changed hunks (from git). Whole-product line and function review coverage is shown as **unmeasured** until a
defensible reviewed numerator exists for the git-tracked inventory; the architect's earlier 285/285 path disposition at `6f907ae` was a
file-level review and is not counted as line or function coverage.

## Review-cycle log

| Cycle | Reviewed revision | Implementation | Review | Decision and evidence |
|---:|---|---:|---:|---|
| 1 | `95f67f41fd1a028336813ccd90383fb3c9cdde97` | 17.0% (38/224) | 3.6% (8/224) | Register v0.1 baseline under the shared rules, proposed by Claude; awaiting Codex's inventory check and SHA confirmation. First Mac subset 62.5% / 40.0%. Superseded estimates: Claude's weighted 45.9% / 38.4% and the architect's milestone 62.5% / 70% (which gave review half credit). [Rules](https://github.com/Prasanna666666/Prasanna/pull/8#issuecomment-7226542434) · [Review](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6092414795) |
