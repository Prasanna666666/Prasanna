# Re-review prompt (send this to reviewers, people or AIs)

Copy everything below the line.

---

Please re-review **pull request #6** of `Prasanna666666/Prasanna` (branch `atlas` into `aperture`): https://github.com/Prasanna666666/Prasanna/pull/6

You have **read access only**. That is enough to comment on the pull request. Do not push, merge or approve.

## What this is

Atlas is a private, offline personal app for one owner on a Mac: Documents, Finance, Health, Travel, Pictures and one assistant over all of them, using a local model (Ollama). Nothing goes to a cloud service. All data in the screenshots and tests is invented. Do not look for or paste real personal data.

The PR answers an earlier review round (a ChatGPT review and a Gemini audit rubric) and adds the documents to review it. About 380 commits are in the diff because it is the whole branch. **Review the last 14 commits (`e8718a1..HEAD`) and the documents.**

## Start here

- The three comments on the PR hold every earlier review comment and its status: Review 1 (ChatGPT, R1-1 to R1-13), Review 2 (Gemini, R2-1 to R2-5), and the author's findings plus open items (D-09, D-12 to D-17, O-1 to O-10).
- Then read, in this order (about 20 minutes): `docs/README.md`, `docs/defects.md`, `docs/reviews.md`, `docs/design.md` (especially "The assistant and its tools" and "Encryption"), `docs/testing.md`, `docs/ui-review.md` and `docs/screenshots/`.

## What I want

**A. Challenge my verdicts.** Reply under the row you disagree with. I challenged these earlier comments: Images migrations were already transactional (R1-6); `tools.py` `MAX_TEXT = 6000` is a chat-window size, not storage (R1-7); invoice date vs due date cannot be told by code without word lists (R1-4); "prompt injection is exploitable" was not shown with a real model (R1-9). Are my reasons sound? I rated these **Open**: O-1 currencies stored in hundredths, O-2 old `.unencrypted` files, O-3 three places choose the model, O-4 a 500 MB upstream answer read into memory (too much for 8 GB?), O-6, O-7 routine writes unconfirmed, O-8 word lists for yes/delete in `kit/consent.py`. Which is worse than I rated it?

**B. Find what I missed**, with file and line:
1. **Money** (`kit/src/kit/money.py` and its call sites in `finance/`): any float path, any lost or invented cent.
2. **Encryption** (`kit/src/kit/db.py`, `encrypt_in_place`): any crash sequence that loses the only good copy or leaves plain text behind.
3. **Migrations** (`_run_step`, `_statements`): a script my splitter cuts wrongly; anything that cannot run inside a transaction.
4. **Extraction** (`kit/src/kit/extract.py`, `verify_dates` and the medical reader): a document that loses or duplicates a value.
5. **Assistant safety** (`finance/src/finance/changes.py`, `toolrun.py`, `web.py`; `atlas/src/atlas/assistant.py`, `upstream.py`): any way a tool result, document or the model could confirm or make a change without the owner's own short "yes"; a misclassified tool; double execution.
6. **Limits** (`library/src/library/limits.py`, `store.py`): a remaining hard-coded limit; a cut that is not recorded.
7. **Tests**: tests that assert nothing, over-mocking, a claimed test that does not exist (for example R2-3: no test that old migrations are never edited).

**C. UI.** Comment on the screenshots in "Files changed" (`docs/screenshots/`), starting with the number (`UI-3`). Is the Finance dashboard clear to a first-time reader? Anything empty, confusing or too dense? My own notes are UI-A to UI-K in `docs/ui-review.md`.

**D. Honesty.** Two earlier statements of mine were wrong (`docs/defects.md`, "An admission"). Find any other claim the code, tests or CI do not support.

## How to answer

- If you can post on GitHub, comment on the pull request (inline on code, documents or screenshots, or as a reply under a numbered row). **If you cannot (most AI chat assistants cannot), write the comments in your answer, one per finding, ready to paste: the owner will post them on the pull request for you. Do not claim a comment was posted.** Begin each comment with an ID: `R1-4`, `R2-4`, `D-10`, `O-4` or `UI-3`.
- Give **evidence**: file and line, a command and its output, or a short reproduction. Without evidence it is recorded as "not verified".
- Mark severity: **blocker** (wrong money, lost or exposed data, a bypass of the confirmation rule), **high**, **medium**, **low**, **nit**.
- Say what you could not check.
- End with your top five concerns, and a score out of 10 with one sentence for each of: correctness, privacy and safety, robustness, accessibility and UI, test quality.

## Please do not

- Ask for features the owner did not ask for, unless they fix a finding.
- Paste secrets or anyone's real data.
- Assume anything is correct because CI is green: it was red three times earlier in this round, and a defect (every card hidden by CSS) passed every earlier check.
