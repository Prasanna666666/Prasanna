# Atlas review and implementation tracker

One versioned **final-product acceptance register** (`core/docs/acceptance_register.json`) and one headline pair, scored by the rules both
the implementer (Claude) and the architect (Codex) agreed on PR #8 ([comment 7226542434](https://github.com/Prasanna666666/Prasanna/pull/8#issuecomment-7226542434)).
The first Mac release checks are mapped into the same register as MAC-01 to MAC-20, so the milestone is a subset, not a separate score.

- **Implementation readiness** = earned points / every criterion. A criterion earns 1 when all its required checks pass with traceable
  evidence, 0.5 only when it defines an intermediate checkpoint and that checkpoint passes, 0 otherwise. Missing evidence earns 0.
- **Review completion** = criteria with a recorded Codex verdict (pass or fail) against a specific revision, with its link / the same total.
  A criterion whose evidence a later change invalidates is reopened and earns 0 until reviewed again.
- Unknown states, partial claims without a defined checkpoint, claims without structured revision-specific evidence, and verdicts without a
  full SHA, link or reviewer provenance score 0 and are **listed as flags**; nothing in scope leaves the denominator. Physical-device-only,
  aggregate and boundary rows are listed and excluded from both scores. A reopened criterion loses implementation and review credit. Mandatory blockers and owner sign-off are reported separately: release approval needs
  every mandatory criterion passing and the owner's sign-off, whatever the percentages say.

Neither number is an acceptance. Codex owns the verdicts and the score reconciliation; Claude owns fixes and evidence; the owner signs off.

## Current measure

Kept current with every change: `python3 scripts/progress.py --update` rewrites this block, and a test fails on any commit whose tree does
not match it. A read-only commit check (`--hook`, Claude Code PreToolUse) refuses a commit while the block is stale; it never edits or stages.

<!-- measure:start -->
**Implementation readiness 11.7%** (25.5/218) · **Review completion 4.6%** (10/218) · register v0.2 at `6fe23c0` (proposed by Claude; Codex to check the crosswalk and denominator and confirm or correct by SHA)

Mandatory criteria not yet passing: **211** of 218. Owner sign-offs recorded: 0. Excluded from both scores: 4 aggregate, 2 boundary, 6 out-device.

Record structure validated by the calculator: 218 of 218 scored criteria carry no flag. Human verification of the linked evidence is separate: it is Codex's recorded verdicts (10).

| Part of the register | Criteria | Implementation | Review |
|---|---:|---:|---:|
| first-mac | 16 | 7.5 (47%) | 8 (50%) |
| prd | 61 | 0 (0%) | 0 (0%) |
| roadmap | 3 | 2.5 (83%) | 1 (33%) |
| stage3 | 19 | 4.5 (24%) | 1 (5%) |
| stages4to8 | 34 | 11 (32%) | 0 (0%) |
| use-case | 85 | 0 (0%) | 0 (0%) |

First Mac milestone view (criteria tagged first-mac): implementation 8/17 (47.1%), review 8/17 (47.1%).

Supporting inventory (git-tracked): 285 source files, 46,658 lines, 2965 functions; 210 test files, 1898 test functions. Whole-product line and function review coverage: **unmeasured** (reviewed ranges are recorded per batch from 5 batch record(s); no defensible whole-product numerator yet).
<!-- measure:end -->

## Register v0.2: scope, crosswalk and credit

`scripts/build_acceptance_register.py` builds the register from the repository's own inventories and answers the architect's v0.1 review
([comment 7226745827](https://github.com/Prasanna666666/Prasanna/pull/8#issuecomment-7226745827)). 230 criteria; 218 are scored.

| Scope | Count | Scored | Meaning |
|---|---:|---|---|
| in | 218 | yes | software criteria, verifiable here or on hosted CI |
| out-device | 6 | no | physical-device-only parts, kept visible: S2-01-DEV, S3-F11-DEV, S3-F12-DEV, S3-F13-DEV, MAC-19-DEV, the Stage 7 target-Mac row's device part |
| aggregate | 4 | no | composed of other criteria: S3-C02 (= MAC-11, MAC-12, MAC-13, MAC-15, S3-C02-TASK), MAC-02, MAC-03, MAC-05 |
| boundary | 2 | no | PRD scope guards that are already true (ALIGNED rows) |

**Crosswalk (v0.1 → v0.2).** MAC-01 → alias of S3-C14 (traceability). S3-C02 → aggregate, with its task-path portion as the new S3-C02-TASK.
S3-F11, S3-F12, S3-F13 → split into `-SW` (scored) and `-DEV` (out of scope); S3-F4 → software. MAC-19 → software part plus MAC-19-DEV.
The Stage 7 target-Mac row (S7-X06) → `-SW` plus `-DEV`. Criteria: 230 = 224 (v0.1) + 3 (four final gates become seven) + 1 (Stage 7
split) + 1 (MAC-19-DEV) + 1 (S2-01-DEV) + 1 (S3-C02-TASK) − 1 (MAC-01 now an alias). Scored: 218 = 230 − 6 device parts − 4 aggregates −
2 boundaries (PRD-2-06, PRD-5B-03).
**Not yet reconciled:** overlaps between PRD rows, use cases and Stage 4-8 rows beyond this mapping keep separate IDs until mapped.

**Credit.** Only structured, revision-specific evidence earns credit: exact tests (each must resolve to a real test definition, checked by a
test), the exact-head hosted CI job with its link and environment, or an explicit linked carry-forward. A conformance status, a commit or a
score citation alone earns nothing, so PRD, use-case and stage rows that name no exact test lost their v0.1 checkpoint credit. Pass
conditions are complete with a precise source reference.

**Historical verdicts.** Stage 2 at `58210223398a5715b618d1163397104efd358d49` for its portable engineering scope
([comment 7047659436](https://github.com/Prasanna666666/Prasanna/pull/8#issuecomment-7047659436)); its target-Mac provisions are S2-01-DEV.
Stage 3 criterion 6 at `14b471bf589303cf25f5d781f8aaf62b0f5654e0` as MET-L for the exact-read attachment restriction only
([review 6014101078](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6014101078)). MAC verdicts at `95f67f4`
([review 6092414795](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6092414795)).

## Review coverage (supporting measure)

`review_batches` in the register records, for each batch Codex reviewed, the exact revisions, link, changed files, changed lines and the
function contexts of the changed hunks (from git). Whole-product line and function review coverage is shown as **unmeasured** until a
defensible reviewed numerator exists for the git-tracked inventory; the architect's earlier 285/285 path disposition at `6f907ae` was a
file-level review and is not counted as line or function coverage.

## Review-cycle log

| Cycle | Reviewed revision | Implementation | Review | Decision and evidence |
|---:|---|---:|---:|---|
| 1 (historical, v0.1) | `95f67f41fd1a028336813ccd90383fb3c9cdde97` | 17.0% (38/224) | 3.6% (8/224) | Register v0.1 baseline under the shared rules, proposed by Claude; awaiting Codex's inventory check and SHA confirmation. First Mac subset 62.5% / 40.0%. Superseded estimates: Claude's weighted 45.9% / 38.4% and the architect's milestone 62.5% / 70% (which gave review half credit). [Rules](https://github.com/Prasanna666666/Prasanna/pull/8#issuecomment-7226542434) · [Review](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6092414795) |
