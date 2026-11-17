# Re-review prompt (send this to reviewers, people or AIs)

Copy everything below the line.

---

Please re-review **pull request #6** of `Prasanna666666/Prasanna` (branch `atlas` into `aperture`): https://github.com/Prasanna666666/Prasanna/pull/6

You have **read access only**. That is enough to comment on the pull request. Do not try to push, merge or approve.

## What this is

Atlas is a private, offline personal app for one owner on a Mac: Documents (files, mail, scans), Finance (bank statements, money), Health, Travel, Pictures, and one assistant over all of them using a local model (Ollama). Nothing goes to a cloud service. All data in the screenshots and tests is invented; do not look for, or paste, real personal data.

This pull request answers an earlier review round (a ChatGPT review and a Gemini audit rubric) and adds the documents to review it. About 380 commits are in the diff because it is the whole branch. **Review the last 12 commits (`e8718a1..HEAD`) and the documents.**

## Read in this order (about 20 minutes)

1. `docs/README.md` (index)
2. `docs/defects.md`: every defect found, what was changed, and what is still **Open**
3. `docs/reviews.md`: each earlier review comment, whether it was confirmed, challenged or not reproduced, and its status
4. `docs/design.md`: especially "The assistant and its tools" and "Encryption"
5. `docs/testing.md`: what was run, and the gaps stated openly
6. `docs/ui-review.md` and `docs/screenshots/`: the UI with invented data

## What I want from you

**A. Challenge my verdicts.** For each row in `docs/reviews.md` and `docs/defects.md`, say if you disagree and why. In particular:
- I **challenged** these earlier comments: Images migrations were already transactional; `tools.py` `MAX_TEXT = 6000` is a chat-window size, not storage; telling the invoice date from the due date cannot be done by code without word lists; "prompt injection is exploitable" was **not** demonstrated with a real model (I only showed that code no longer relies on the model). Are my reasons sound?
- I rated these **Open**: O-1 (all currencies stored in hundredths), O-2 (old `.unencrypted` files not touched), O-3 (three places choose the model), O-4 (an upstream answer of up to 500 MB is read into memory: too much for an 8 GB Mac?), O-6, O-7 (routine writes run without confirmation), O-8 (word lists for "yes/delete" in `kit/consent.py`). Which is worse than I rated it?

**B. Look for what I missed.** Check the changes themselves, with file and line:
1. **Money** (`kit/src/kit/money.py` and its call sites in `finance/`): any path still using float for amounts, any rounding that can lose or invent a cent.
2. **Encryption** (`kit/src/kit/db.py`, `encrypt_in_place`): can any sequence of crashes lose the only good copy or leave plain text behind? Is overwriting before deleting sensible on APFS/SSD?
3. **Migrations** (`kit/src/kit/db.py`, `_run_step`, `_statements`): a migration script my splitter cuts wrongly; anything that cannot run inside a transaction (PRAGMA, VACUUM).
4. **Extraction** (`kit/src/kit/extract.py`): `verify_dates`, the medical reader (line-aligned pieces, halving, overlap de-duplication). A document that loses or duplicates a value.
5. **Assistant safety** (`finance/src/finance/changes.py`, `toolrun.py`, `finance/web.py`, `atlas/src/atlas/assistant.py`, `upstream.py`): any way a tool result, document or the model could confirm or make a change without the owner's own short "yes"; any tool misclassified as read-only; a double execution; the rehearsal (`_Rehearsal`) leaving a trace.
6. **Limits** (`library/src/library/limits.py`, `store.py`): any remaining hard-coded limit; a cut that is not recorded.
7. **UI** (`design/design.css` and the screenshots): see section C.
8. **Tests**: tests that assert nothing, over-mocking, fakes that differ from the real thing. Is there a test I claim but that does not exist?

**C. UI comments.** Open the screenshots under `docs/screenshots/` in the pull request's "Files changed" tab and comment on them. Start with the number (`UI-3`). I listed my own observations in `docs/ui-review.md` (gradients despite "no gradients", mixed decimal separators in Health, floating Ask button over content on phones, a green status dot for "Photos not connected", wrapping pills in the top bar). Is the Finance dashboard clear to a first-time reader? Is anything confusing, empty or too dense?

**D. Check my honesty.** Two earlier statements of mine were wrong (`docs/defects.md`, "An admission"). Find any other claim in the pull request description or documents that the code, tests or CI do not support.

## How to answer

- Comment **on the pull request**: inline on a line of code, a document or a screenshot. Begin each comment with an ID: a requirement (`R-Q4`), a defect (`D-10`, `O-4`) or a UI item (`UI-3`).
- Give **evidence**: file and line, a command and its output, or a short reproduction. "Looks wrong" without evidence will be recorded as "not verified".
- Mark each comment with a severity: **blocker** (wrong money, lost or exposed data, a bypass of the confirmation rule), **high**, **medium**, **low**, or **nit**.
- Say **what you could not check** and what you would need.
- Please end with a short summary: your top five concerns in order, and for each of: correctness, privacy and safety, robustness, accessibility and UI, test quality, a score out of 10 with one sentence of reason.

## Please do not

- Ask for features the owner did not ask for, unless they fix a finding.
- Paste secrets, keys or anyone's real data.
- Assume anything here is correct because CI is green: CI was red three times earlier in this round, and a defect (every card hidden by CSS) passed every earlier check.
