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
**Implementation readiness 19.7%** (43/218) · **Review completion 16.1%** (35/218) · register v0.3 (the file as committed) scoring software revision `3717bed` (agreed reporting baseline: confirmed by Codex in review 6093596586 (baseline decision, comment 7228002976); the v0.4 proposal was withdrawn by the owner (28 Nov) and this is the only measure)

Mandatory criteria not yet passing: **189** of 218. Owner sign-offs recorded: 0. Excluded from both scores: 6 aggregate, 2 boundary, 6 out-device.

Record structure validated by the calculator: 218 of 218 scored criteria carry no flag. Human verification of the linked evidence is separate: it is Codex's recorded verdicts (35).

| Part of the register | Criteria | Implementation | Review |
|---|---:|---:|---:|
| first-mac | 16 | 12 (75%) | 15 (94%) |
| prd | 61 | 0 (0%) | 0 (0%) |
| roadmap | 3 | 2.5 (83%) | 1 (33%) |
| stage3 | 20 | 8.5 (42%) | 5 (25%) |
| stages4to8 | 34 | 19 (56%) | 10 (29%) |
| use-case | 84 | 1 (1%) | 4 (5%) |

First Mac milestone view (criteria tagged first-mac): implementation 14/19 (73.7%), review 17/19 (89.5%).

Supporting inventory (git-tracked): 288 source files, 48,301 lines, 3068 functions; 212 test files, 1988 test functions. Whole-product line and function review coverage: **unmeasured** (reviewed ranges are recorded per batch from 17 batch record(s); no defensible whole-product numerator yet).

Open owner decisions (recorded separately, not criteria): DEC-PUBLIC-SEARCH.
<!-- measure:end -->

## Register v0.4: withdrawn

Withdrawn by the owner on 28 Nov ("no half measures; don't tweak the numbers"). No proposal or provisional figure is published. The only measure
is the agreed register above: a criterion counts when it is fully built, its exact tests pass in hosted CI at the scored revision, and the
architect has passed it. Device-only checks stay excluded, as agreed.

## Register v0.3: scope, crosswalk and credit

**Agreed reporting baseline** since Codex's review of `2815257` (review 6093596586; baseline decision comment 7228002976). Later changes follow the versioned crosswalk rules.

`scripts/build_acceptance_register.py` builds the register from the repository's own inventories. v0.2 answered the architect's v0.1 review
([7226745827](https://github.com/Prasanna666666/Prasanna/pull/8#issuecomment-7226745827)); v0.3 answers the v0.2 review
([6093128990](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6093128990)). 232 entries; 218 are scored. Every entry's
evidence cites the **scored software revision** `910df6a` and its PR CI run 46132313240; the register itself is the file at the commit that holds it.

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
| 9 | `6c35e620517abfed7d45e42b2fd3b6c52afa50a3` | 19.0% (41.5/218); architect reports 41/218 | 13.3% (29/218) | Verdicts: MAC-17 pass, UC-L19 pass; MAC-08 and MAC-06 fail; UC-L22, MAC-07, UC-009 and MAC-20 pending; the Core checkpoints of S6-X07, S7-X01, S7-X05, S8-X01 and S8-X03 met. Mirrored with the two supplementary audits at d528055 (comments 7235875772 and 7235938220: 13 passes). The calculator's 41.5 is the sum of the review's stated increments (37.5 + 0.5 + 1 + 2.5); the 0.5 difference is asked of the architect. v0.4 remains proposed. [Review](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6096694534) |
| 10 | `b2ca5b30c5780c73fe8ebc0a1dc8048078176ef1` | 19.3% (42/218) | 14.7% (32/218) | Verdicts: S3-C08 fail with its Core checkpoint met; UC-L14 and UC-L26 fail; MAC-08 and MAC-06 fail; UC-009, UC-L22, MAC-07, UC-049 and MAC-20 pending. The architect confirmed 41.5/218 at 6c35e62 (its 41 was 0.5 short). Arithmetic reproduced. [Review](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6097009203) |
| 11 | `910df6ae917929537c1511bf77c1bb36123480d2` | 19.5% (42.5/218) | 14.7% (32/218) | Verdicts: S3-C08 pass (full); UC-L26 fail (one final authorization boundary across sources); MAC-08 and MAC-06 fail. ATLAS-ACT-019: torn tail closed, strict replay open. v0.4 aligned with failed and pending verdicts. Arithmetic reproduced. [Review](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6097249161) |
| 12 | `c116bd59dd81d6ce48681ce93d0c0bb57bcd3c55` | 19.5% (42.5/218) | 14.7% (32/218) | Verdicts: UC-L26 fail (final permission checks sequential); UC-L14 fail for the full criterion, local record undo passes (connector compensation and receipt separate); UC-049 and UC-009 pending; MAC-08 and MAC-06 fail. ATLAS-ACT-019: approval replay closed; intent-journal torn tail and bounded audit-anchor recovery open. Arithmetic reproduced. [Review](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6098305702) |
| 13 | `3717bedd3e41d87c2e9bfdadc72ea6ce56084e15` | 19.7% (43/218) | 16.1% (35/218) | Verdicts: MAC-07 pass (full; shared-action design meets option (i)); MAC-20 fail (generation checks on every AppModel completion path); UC-L22 fail (year-like integer part escapes the figure check); UC-L14 fail (retry design accepted; neutral unknown-outcome wording); MAC-08 and MAC-06 fail. Arithmetic reproduced: +0.5 implementation, +3 verdicts. [Review](https://github.com/Prasanna666666/Prasanna/pull/8#pullrequestreview-6098896232) |
