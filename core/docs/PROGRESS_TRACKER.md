# Atlas review and implementation tracker

Two percentages, both measured against the **final product** (PRD, the use-case register, roadmap stages 0-8 and their exit evidence, the
design decisions, verification on the target Mac, usability and release standards), not against the current stage. They are recomputed by
`python3 scripts/progress.py` and recorded below **after every review cycle** (each architect review on PR #8 of an implementation handoff).

- **Implementation %**: how much of the final product is built and verified.
- **Review %**: how much of it has been independently reviewed, had its findings closed, and been accepted by the architect and the owner.

Neither number is an acceptance. Only the architect's review of an exact head and the owner's explicit acceptance accept anything.

## Current measure (cycle 1, head `95f67f4`)

**Implementation: 46%**  ·  **Review: 38%**  (head `95f67f4`)

| Implementation dimension | Weight | Score |
|---|---:|---:|
| Requirements (PRD rows) | 20 | 47% |
| Functionality (use cases) | 20 | 34% |
| Stages 0-8 (exit evidence) | 20 | 63% |
| Design (decisions, ADRs) | 10 | 53% |
| Test and verification | 15 | 53% |
| Usability and accessibility | 10 | 25% |
| Standards, security, release | 5 | 30% |

| Review dimension | Weight | Score |
|---|---:|---:|
| Breadth (code under independent review) | 20 | 95% |
| Findings closed | 30 | 52% |
| Accepted by architect and owner | 50 | 8% |

Stages 0-8: S0 95%, S1 100%, S2 100%, S3 50%, S4 45%, S5 50%, S6 48%, S7 38%, S8 38%

Counted: 63 PRD rows, 85 use cases, 34 Stage 4-8 exit rows, 146 defect IDs; 2664 Python and 286 Swift functions, 48,091 source lines; 1765 Python and 120 Swift test functions.

## Method

**Counted from the project's records** (they move when those records are updated):
- *Requirements*: every row of `docs/genesis/PRD_CONFORMANCE.md`; *Functionality*: every row of `docs/genesis/USE_CASE_CONFORMANCE.md`. A row earns
  ALIGNED 1.0, IMPLEMENTED 0.8 (built and tested, not owner-accepted), PARTIAL 0.5, PARTIAL FOUNDATION 0.3, UNVERIFIED 0.25, NOT IMPLEMENTED or DEFERRED 0.
- *Stages 4-8*: the exit-evidence rows of each stage's section in `core/docs/STAGES_4_TO_8.md`. These are the implementer's own report and are not
  architect-reviewed, so MET-L (met locally, synthetic) earns 0.5; PARTIAL 0.3; script/written 0.3; proposed 0.2; DEFERRED-FINAL 0.
- *Size*: Python and Swift functions, source lines and test functions are counted from the tree, so line- and function-level scope is visible.
- *Defects*: distinct ATLAS IDs in `docs/genesis/DEFECT_REGISTER.md`.

**Judged, with written reasons** in `core/docs/progress_inputs.json` (challenge them on the PR): Stage 0-3 scores, design, usability,
standards, synthetic test strength, and the live facts (hosted CI jobs, target-Mac gates, review threads, closed findings, accepted criteria).

**Weights.** Implementation: requirements 20, functionality 20, stages 20, design 10, test and verification 15 (synthetic tests 40%, hosted CI
pass rate 20%, target-Mac gates 40%), usability 10, standards, security and release 5. Review: breadth of independent review 20, findings
closed 30 (review threads and defect register equally), acceptance 50 (accepted units out of all final acceptance units).

**What moves the numbers most.** Acceptance is half of Review and is at 8%: Stage 3 acceptance and owner acceptance of later stages are the
largest single lever. On Implementation, the target-Mac gates (0 of 5) hold Test and verification near half, and the use-case matrix (19 not
implemented) holds Functionality at a third.

## Cycle log

| Cycle | Date | Head | Implementation | Review | What moved |
|---:|---|---|---:|---:|---|
| 1 | 2026-11-27 | `95f67f4` | 46% | 38% | Baseline of this tracker. Measured after the architect review of `124bf96` and Claude's batch closing its items 1-3. |
