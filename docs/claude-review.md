# Claude review notes on PR #6

Reviewed head (full SHA): `cc06e92097736d81a1ea0b64f5a603555a183bb7` (branch `atlas`). Code is unchanged from `97d5e29`; the commits after it change only `docs/`.

**Who wrote this and what it is worth.** Claude is also the author of most fixes, so nothing below is independent verification. It is an author re-run on a fresh environment. Per the agreed scheme, no item is VERIFIED or CLOSED until a reviewer other than the author reproduces it (P4).

Status words used here are the ones the owner asked for. Map to the tracker scheme: OPEN = OPEN; FIXED (awaiting independent verification) = FIXED - P3 (or P2) awaiting P4; VERIFIED = P4 done, not yet closed; CLOSED = P4 plus the CLOSED rule in `comment-tracker.md`. Today VERIFIED and CLOSED are empty.

## 1. What I ran at `cc06e92` (fresh virtualenv, Python 3.13, five packages installed editable)

| Package | Result |
|---|---|
| kit | 163 passed |
| images | 97 passed |
| finance | 671 passed (coverage not re-measured in this run) |
| library | 230 passed |
| atlas | 104 passed |
| Total | 1,265 passed, 0 failed |

Notes: the first library run failed one test (`test_readers.py:119`, `No module named 'openpyxl'`). That was my environment missing the `parse` extra (`pip install -e "library[dev,parse]"`), not a defect; after installing it, 230 passed. CI's minimum is Python 3.11; this run used 3.13, so it does not replace the CI result. Lint, type checks, the browser page check and mutation checks were **not** re-run here.

## 2. New findings

| ID | Finding | Evidence | Status |
|---|---|---|---|
| C-1 | `docs/coverage-matrix.md` is stale. It states 508 entries (580 without rename detection) at `5676a6a`; at `cc06e92` git lists 511 with rename detection and 583 without (`git diff --name-only origin/aperture...HEAD`). The "397 not inspected" figure is therefore not a current-head count. ChatGPT's F15 is right on this | `docs/coverage-matrix.md:3,25` | OPEN |

## 3. Review of ChatGPT's F1 to F15 (source read at `cc06e92`, nothing run in a browser)

Agree and OPEN: F1 (`finance/src/finance/static/app.js:828`; the baseline is the previous calendar month, `finance/src/finance/modules/events.py:200`, so the fix is wording and showing both months), F2 (`app.js:872`), F6 (`library/src/library/static/app.js:78,109`), F7, F8, F9 (`library/src/library/static/healthtravel.js:270`; `design/design.css:272,428,1050`; `docs/design.md:66`), F15 (see C-1).

Agree, PARTIAL: F3 (`app.js:849-855` draws `nw.net_worth` whatever the accounts label says), F12, F13, F14 as already tracked (`comment-tracker.md` section 11).

ROADMAP: F10, F11 (ChatGPT calls F11 roadmap itself).

## 4. Disagreements with ChatGPT (explicit)

1. **F3 severity HIGH.** I rate it MEDIUM until someone shows a wrong or misleading figure. What I read is a presentation gap: the figure is drawn next to a label that says no statements were read. ChatGPT also wrote that it did not reproduce a wrong calculation. Its category (trust) is fair; the severity is not yet shown.
2. **F4 and F5 severity HIGH.** These ask for new dashboard features (freshness per metric, reconciliation state shown on the dashboard, assistant using the same completeness). They are gaps, not defects in existing behaviour; I rate them MEDIUM and keep them OPEN. The assistant-side part of F5 conflicts with the owner's rule that the assistant never sees real finance data, so it can only use a completeness flag, not figures; that needs an owner decision.
3. **F13 as BLOCKER.** I agree it blocks sensitive use. I disagree with "prefer a memory-backed location" as written: the hand-over crosses containers, and encrypting it puts the key in the least-trusted container (O-16 reasoning). Whether a shared in-memory mount fits the Docker layout is not checked here.

I did not overwrite any ChatGPT finding; its text stays in the PR conversation and in `comment-tracker.md`.

## 5. Not covered by this review

P5 items (real model, ingestion/OCR, Docker lifecycle, connected Photos), the browser and accessibility checks, and mutation reproduction. Gemini's answer on the scheme is still awaited.
