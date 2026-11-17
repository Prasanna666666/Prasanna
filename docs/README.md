# Documentation index

| Document | What it is |
|---|---|
| [requirements.md](requirements.md) | What Atlas must do and be, with IDs and how each is verified |
| [design.md](design.md) | Layers, data flows, the safety design of the assistant, encryption, migrations |
| [decisions.md](decisions.md) | The decision log (including the review round at its end) |
| [architecture.md](architecture.md) | The layer map |
| [reconciliation.md](reconciliation.md) | Every defect and open item: status, file and line, what its test proves, and whether the test was shown to fail without the fix |
| [security-deployment-review.md](security-deployment-review.md) | What was inspected in Docker, Compose and scripts, what was run, and what was not |
| [coverage-matrix.md](coverage-matrix.md) | Every changed entry of the pull request and whether it was inspected |
| [data-locations.md](data-locations.md) | Where personal data lives on disk, which of it is encrypted, and what was not inspected |
| [defects.md](defects.md) | Every defect found in this round, fixed and open, with evidence |
| [reviews.md](reviews.md) | The outside reviews, what was confirmed or challenged, and where friends' comments are tracked |
| [testing.md](testing.md) | What was run, the results, the test inventory, and the gaps |
| [ui-review.md](ui-review.md) | Screenshots of the apps with invented data, for UI comments |
| [REVIEW_PROMPT.md](REVIEW_PROMPT.md) | The prompt used to ask other AIs for the first review |
| [RE_REVIEW_PROMPT.md](RE_REVIEW_PROMPT.md) | The prompt to send reviewers (people and AIs) for the re-review of this pull request |

Read in this order if you have ten minutes: `defects.md` (what was wrong), `design.md` (how the assistant is kept safe), `ui-review.md` (what it looks like).
