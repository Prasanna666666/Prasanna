# Request to reviewers (ChatGPT, Gemini): approve or amend the statuses

**Closure rule (changed by the owner, see `docs/comment-tracker.md` header and section 24):** an item is CLOSED when it has P3 evidence and the owner has run the check on their Mac (owner-verified) or accepted the author-run evidence (owner-accepted). Your independent reproduction upgrades the basis to *independent*; it is no longer required to close.

Repo Prasanna666666/Prasanna, PR #6, branch `atlas` into `aperture`. This file is the one place the current request lives; it is replaced, not added to. Read it at the head you are given, not from memory.

## What to read
1. `docs/comment-tracker.md` at the head named in the owner's message. Section "Status words" (top) is the scheme; sections 2 to 11 are every item and its status; section 10 is ChatGPT's earlier answer on the scheme.
2. Detail: `docs/defects.md`, `docs/reconciliation.md`, `docs/reviews.md`.

## Rules
- Name the commit on every claim, every item you verified and every check you ran. A status with no commit counts as not verified.
- Say "not independently reproduced" for anything you only read. Do not invent findings; add one only if you reproduced it.
- Do not approve what you did not verify. P3 results in the tracker are author-reported, not yours.
- If you cannot post on GitHub, answer in the table below; the owner pastes it back.

## Answer in this table
1. Scheme (STATE - PROOF - FLAG - COMMIT; CLOSED = FIXED + P3 or stronger + reviewer P4): APPROVE or AMEND, exact words.
2. Per item or group in the tracker: AGREE or DISAGREE, your evidence, the state or proof you would assign, the commit you checked.
3. Items you personally verified (P4): item, commit, exact command or procedure, result.
4. Anything missing or wrongly worded.
5. Final, with commit: do you approve the statuses (labelling), and do you approve the PR for use? List the exact remaining blockers.
