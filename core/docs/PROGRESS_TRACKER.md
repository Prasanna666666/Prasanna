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
**Implementation readiness 44.0%** (96/218) · **Review completion 6.9%** (15/218) · register v0.4 (the file as committed) scoring software revision `d528055` (PROPOSED, not agreed: v0.4 awaits Codex's decision (comment 7235843033); v0.3 is the agreed baseline (review 6093596586))

Mandatory criteria not yet passing: **195** of 218. Owner sign-offs recorded: 0. Excluded from both scores: 6 aggregate, 2 boundary, 22 out-device.

Record structure validated by the calculator: 218 of 218 scored criteria carry no flag. Human verification of the linked evidence is separate: it is Codex's recorded verdicts (15).

| Part of the register | Criteria | Implementation | Review |
|---|---:|---:|---:|
| first-mac | 16 | 11 (69%) | 13 (81%) |
| prd | 61 | 30.5 (50%) | 0 (0%) |
| roadmap | 3 | 2.5 (83%) | 1 (33%) |
| stage3 | 20 | 7.5 (38%) | 1 (5%) |
| stages4to8 | 34 | 14 (41%) | 0 (0%) |
| use-case | 84 | 30.5 (36%) | 0 (0%) |

First Mac milestone view (criteria tagged first-mac): implementation 12.5/19 (65.8%), review 13/19 (68.4%).

Supporting inventory (git-tracked): 286 source files, 47,593 lines, 3016 functions; 210 test files, 1937 test functions. Whole-product line and function review coverage: **unmeasured** (reviewed ranges are recorded per batch from 12 batch record(s); no defensible whole-product numerator yet).

Open owner decisions (recorded separately, not criteria): DEC-PUBLIC-SEARCH.
<!-- measure:end -->

## Register v0.4 (PROPOSED, not agreed)

Proposed in comment 7235843033 at the owner's direction and built in this batch for Codex to review; **v0.3 stays the agreed baseline until
Codex accepts v0.4 by SHA**, and every v0.4 figure above is provisional.
- PRD and use-case rows marked PARTIAL get a checkpoint; 0.5 only from checkpoint-specific test evidence mapped in
  `core/docs/v04_checkpoint_evidence.json` (exact tests that resolve, plus the hosted jobs that run them).
- UC-033, UC-L16, PRD-4-07 and S3-C12 split into a scored software part and an excluded `-DEV` device part.
- UC-041, UC-L09, PRD-5-05, PRD-5-01, PRD-3-06 and UC-L22 have complete software and only device or target-Mac verification left: the
  software part is full from exact tests and the device part is a `-DEV` row. UC-L22's software gap (unspaced-script retrieval) is closed in
  this batch (Han, Kana and Hangul indexed as overlapping pairs; evaluation set v2).
- UC-L19 is full: its one recorded gap, ATLAS-CORE-092, was closed by MAC-11, MAC-12 and MAC-15, each architect-passed.
- Stage 4-8 rows that name tests as `::test_name` or as a whole test file now resolve them (S6-X02, S6-X07, S7-X01, S7-X05, S8-X01, S8-X03).
- A row whose credit rests on code or tests added after the scored revision (UC-L22, UC-049, UC-L14, UC-L26, S3-C08, UC-009) is credited only once
  the scored revision contains that commit (`V04_LANDS_IN`), so no evidence is cited for a revision that does not hold it.

## Register v0.3: scope, crosswalk and credit

**Agreed reporting baseline** since Codex's review of `2815257` (review 6093596586; baseline decision comment 7228002976). Later changes follow the versioned crosswalk rules.

`scripts/build_acceptance_register.py` builds the register from the repository's own inventories. v0.2 answered the architect's v0.1 review
([7226745827](https://github.com/Prasanna666666/Prasanna/pull/8#issuecomment-7226745827)); v0.3 answers the v0.2 review
([6093128990](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6093128990)). 232 entries; 218 are scored. Every entry's
evidence cites the **scored software revision** `d528055` and its PR CI run 46113892127; the register itself is the file at the commit that holds it.

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
- A reopened criterion loses both credits. MAC-13 and MAC-14 were reopened at 8b23cc6 because that batch changed the delivery code their evidence covered; both have since passed review.
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
| 3 | `2815257f391f5fffa6168ac1ff00bca41a8bc1dc` | 12.8% (28/218) | 5.5% (12/218) | v0.3 agreed as the 218-criterion reporting baseline; arithmetic reproduced. Verdicts: MAC-14 pass, MAC-18 pass, MAC-13 pending (checkpoint verified), MAC-15 fail, MAC-06 fail, MAC-08 fail. [Review](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6093596586) |
| 4 | `6574c2cb8dd23c9d1a3a7084c6aa1e207756900c` | 14.0% (30.5/218) | 6.9% (15/218) | Verdicts: MAC-13 pass, MAC-15 pass, MAC-19 pass; MAC-17 fail (rollback can fail, a killed process skips it), MAC-06 fail (mac-ui), MAC-08 fail (option b: assert the effective appearance, then a layout change, no exemption). Arithmetic reproduced by the calculator. [Review](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6094252873) |
| 5 | `e23b04bff48c2c3d79976b50921f86d91a3c46ce` | 14.0% (30.5/218) | 6.9% (15/218) | No change. Verdicts: MAC-17 fail (single-target recovery accepted in design; ownership across data folders missing), MAC-08 fail (appearances verified; investigate the Disabled window state first, no exemption), MAC-06 fail. Arithmetic reproduced. [Review](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6094872675) |
| 6 | `a3c7f7d009ff70d7feda917d5d4a3ea9dc030e71` | 14.0% (30.5/218) | 6.9% (15/218) | No change. Verdicts: MAC-17 fail (account-wide design accepted; serialize recovery with live restore, enforce ownership at startup, keep data on an unconfirmed commit point), MAC-08 fail (choose (a): make the window key first), MAC-06 fail. Arithmetic reproduced. [Review](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6095269004) |
| 7 | `09498515beefed3e90feac0e201722822df4a6f5` | 14.0% (30.5/218) | 6.9% (15/218) | No change. Verdicts: MAC-17 fail (key layer fixed; startup store-open window and restore copy/activation interval remain), MAC-08 fail (window state controlled; choose (i)), MAC-06 fail. Arithmetic reproduced. [Review](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6095905696) |
| 8 | `d528055ec8756d8d55efe2f104cfe929c7bf8cb1` | 14.0% (30.5/218) under v0.3 | 6.9% (15/218) | Verdicts: MAC-17 fail (lock cleanup), MAC-08 fail (bisect Dark; second hosted configuration for Light), MAC-06 fail. Register v0.4 PROPOSED with this batch (comment 7235843033): checkpoints for partial PRD and use-case rows with mapped test evidence and four device splits; under v0.4 the calculator reports 38.1% (83/218), not agreed until Codex accepts it. [Review](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6096381812) |
