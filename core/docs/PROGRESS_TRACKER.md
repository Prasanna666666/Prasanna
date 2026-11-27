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
**Implementation readiness 11.9%** (26/218) · **Review completion 4.1%** (9/218) · register v0.3 (the file as committed) scoring software revision `8b23cc6` (proposed by Claude; Codex to check the crosswalk and denominator and confirm or correct by SHA)

Mandatory criteria not yet passing: **211** of 218. Owner sign-offs recorded: 0. Excluded from both scores: 6 aggregate, 2 boundary, 6 out-device.

Record structure validated by the calculator: 216 of 218 scored criteria carry no flag. Human verification of the linked evidence is separate: it is Codex's recorded verdicts (9).

| Part of the register | Criteria | Implementation | Review |
|---|---:|---:|---:|
| first-mac | 16 | 6.5 (41%) | 7 (44%) |
| prd | 61 | 0 (0%) | 0 (0%) |
| roadmap | 3 | 2.5 (83%) | 1 (33%) |
| stage3 | 20 | 6 (30%) | 1 (5%) |
| stages4to8 | 34 | 11 (32%) | 0 (0%) |
| use-case | 84 | 0 (0%) | 0 (0%) |

First Mac milestone view (criteria tagged first-mac): implementation 7.5/19 (39.5%), review 7/19 (36.8%).

Supporting inventory (git-tracked): 285 source files, 46,781 lines, 2968 functions; 210 test files, 1910 test functions. Whole-product line and function review coverage: **unmeasured** (reviewed ranges are recorded per batch from 6 batch record(s); no defensible whole-product numerator yet).

Open owner decisions (recorded separately, not criteria): DEC-PUBLIC-SEARCH.

Flags (2, scored 0 and kept in the denominator):
- MAC-13: reopened: service.guard_delivery / coverage delivery changed in the v0.3 batch; the 8b23cc6 evidence no longer covers it
- MAC-14: reopened: service.guard_delivery / coverage delivery changed in the v0.3 batch; the 8b23cc6 evidence no longer covers it
<!-- measure:end -->

## Register v0.3: scope, crosswalk and credit

`scripts/build_acceptance_register.py` builds the register from the repository's own inventories. v0.2 answered the architect's v0.1 review
([7226745827](https://github.com/Prasanna666666/Prasanna/pull/8#issuecomment-7226745827)); v0.3 answers the v0.2 review
([6093128990](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6093128990)). 232 entries; 218 are scored. Every entry's
evidence cites the **scored software revision** `8b23cc6` and its CI run 46061223577; the register itself is the file at the commit that holds it.

| Scope | Count | Scored | Entries |
|---|---:|---|---|
| in | 218 | yes | software criteria, verifiable here or on hosted CI |
| out-device | 6 | no | S2-01-DEV, S3-F11-DEV, S3-F12-DEV, S3-F13-DEV, S7-X06-DEV, MAC-19-DEV |
| aggregate | 6 | no | S3-C02 (MAC-11, MAC-12, MAC-13, MAC-15, S3-C02-TASK; alias UC-011), S3-C13 (S3-C13-REF, UC-009, MAC-09, MAC-19, MAC-20), S3-F13-SW (S7-X04, S3-F13-INSTALL), MAC-02, MAC-03, MAC-05 |
| boundary | 2 | no | PRD-2-06, PRD-5B-03 (scope guards already true) |

**Crosswalk.**
- v0.1 → v0.2:
  - MAC-01 became an alias of S3-C14.
  - S3-C02 became an aggregate, with its task path in S3-C02-TASK.
  - The final gates F-11, F-12 and F-13 were split into `-SW` and `-DEV`.
  - MAC-19 and S7-X06 were split.
- v0.2 → v0.3:
  - UC-009 is the one canonical Stop/Cancelled criterion; MAC-20 keeps the incomplete-search wording and clearing results on withdrawal.
  - S3-C13 is an aggregate of its parts, adding S3-C13-REF for the reference-client experience.
  - UC-011 is an alias of S3-C02.
  - S7-X04 is the one signing criterion; S3-F13-SW is an aggregate of S7-X04 and S3-F13-INSTALL.
  - S3-C06-EXACTREAD is the exact-read restriction, carrying the scoped historical verdict.
- Entries: 230 (v0.2) + S3-C13-REF + S3-F13-INSTALL + S3-C06-EXACTREAD − UC-011 = 232.
- Scored: 218 = 232 − 6 device − 6 aggregates − 2 boundaries.
- **Not yet reconciled:** further PRD, use-case and Stage 4-8 overlaps keep separate IDs until mapped.

**Credit and validity.**
- Implementation credit comes only from structured evidence for the scored revision:
  - exact tests that resolve (checked by a test)
  - the hosted CI job, naming its run, job and environment
  - an explicit, linked carry-forward
- A status, commit or score citation alone earns nothing.
- A full claim against a recorded fail earns 0.5 only from checkpoint-specific evidence.
- A reopened criterion loses both credits. MAC-13 and MAC-14 are reopened because this batch changed the delivery code their evidence covered.
- The calculator publishes **no scores** while any entry has an unknown scope, a duplicate ID or a colliding alias.
- Pass conditions are normative; recorded status and open gaps are kept as separate fields.

**Historical verdicts and decisions.**
- Stage 2 at `58210223398a5715b618d1163397104efd358d49` ([7047659436](https://github.com/Prasanna666666/Prasanna/pull/8#issuecomment-7047659436)), carried forward for its portable engineering scope only.
- Stage 3 criterion 6 at `14b471bf589303cf25f5d781f8aaf62b0f5654e0` ([6014101078](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6014101078)), on S3-C06-EXACTREAD; the broader S3-C06 is pending at `8b23cc6`.
- The owner's public-search choice is decision DEC-PUBLIC-SEARCH, not a criterion.

## Review coverage (supporting measure)

`review_batches` in the register records, for each batch Codex reviewed, the exact revisions, link, changed files, changed lines and the
function contexts of the changed hunks (from git). Whole-product line and function review coverage is shown as **unmeasured** until a
defensible reviewed numerator exists for the git-tracked inventory; the architect's earlier 285/285 path disposition at `6f907ae` was a
file-level review and is not counted as line or function coverage.

## Review-cycle log

| Cycle | Reviewed revision | Implementation | Review | Decision and evidence |
|---:|---|---:|---:|---|
| 1 (historical, v0.1) | `95f67f41fd1a028336813ccd90383fb3c9cdde97` | 17.0% (38/224) | 3.6% (8/224) | Register v0.1 baseline under the shared rules, proposed by Claude; awaiting Codex's inventory check and SHA confirmation. First Mac subset 62.5% / 40.0%. Superseded estimates: Claude's weighted 45.9% / 38.4% and the architect's milestone 62.5% / 70% (which gave review half credit). [Rules](https://github.com/Prasanna666666/Prasanna/pull/8#issuecomment-7226542434) · [Review](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6092414795) |
| 2 | `8b23cc66705a5b3c5eddac657cf774fa35a43594` | 11.7% (25.5/218) | 4.6% (10/218) | Register v0.2 reviewed: arithmetic reproduced, baseline pending; scope split accepted in principle, crosswalk incomplete, calculator corrections requested. Verdicts: MAC-06 fail, MAC-08 fail, S3-C06 pending. Answered by v0.3. [Review](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6093128990) |
