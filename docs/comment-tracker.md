# Comment tracker

One place for every review comment, whoever wrote it, and what became of it. **Rule:** every review the owner pastes gets rows here in the same session; a row is updated when its status changes; nothing is dropped. Reviewers (ChatGPT, Gemini) cannot post on GitHub; the owner pastes their reviews and the author posts the replies as PR comments (links below).

Status words: **CLOSED** (fixed, with a test that fails when the defect returns: author-run, not reproduced by anyone else) · **FIXED, UNPROVEN** (changed; the test was not shown to fail without the fix) · **PARTIAL** · **OPEN** (not done) · **ROADMAP** (a product suggestion, not a defect; not built) · **REFUTED** (the claim was wrong, with evidence) · **NOT VERIFIABLE HERE** (needs the owner's Mac and a real model) · **IN PROGRESS** (started, not committed or not tested).

Detail for each defect is in `defects.md` and `reconciliation.md`. Counts below are as of commit `97d5e29` plus the uncommitted work named in section 9.

## 1. PR comments (where the replies are)

| Tag | Source | PR comment |
|---|---|---|
| Review 1 | ChatGPT first review (R1-1 to R1-13) | https://github.com/Prasanna666666/Prasanna/pull/6#issuecomment-6939233653 |
| Review 2 | Gemini audit rubric (R2-1 to R2-5) | https://github.com/Prasanna666666/Prasanna/pull/6#issuecomment-6939234770 |
| Author's findings | D-09, D-12 to D-17, O-1 to O-10 | https://github.com/Prasanna666666/Prasanna/pull/6#issuecomment-6939236352 |
| R3 | Gemini review of the PR (R3-1 to R3-11) | https://github.com/Prasanna666666/Prasanna/pull/6#issuecomment-6939752386 |
| R4 | Author's final audit | https://github.com/Prasanna666666/Prasanna/pull/6#issuecomment-6939951434 |
| R5 | Reply to ChatGPT second review | https://github.com/Prasanna666666/Prasanna/pull/6#issuecomment-6940107555 |
| R6 | Reply to ChatGPT "comprehensive review" (its four findings, labelled R3-1..R3-4 in its text; called **R6-1..R6-4** here to avoid a clash with Gemini's R3) | https://github.com/Prasanna666666/Prasanna/pull/6#issuecomment-6940486189 |
| R7 | Reply to the Gemini "final readiness" prompt | https://github.com/Prasanna666666/Prasanna/pull/6#issuecomment-6941940564 |
| R8 | Reply to the final ChatGPT review of `a2b88c2` | https://github.com/Prasanna666666/Prasanna/pull/6#issuecomment-6942705179 |
| R9 | ChatGPT product, screenshot and functionality review | **not yet posted** (section 8) |

## 2. Review 1 (ChatGPT)

| ID | Comment | Status | Where |
|---|---|---|---|
| R1-1 | Local model endpoint only | CLOSED | `kit/llm.py`, Atlas `ModelClient`, `test_assistant_safety.py` |
| R1-2 | Float money | CLOSED | D-01, D-18, D-31; `test_money_exact.py` |
| R1-3 | Plain copy after encryption | CLOSED | D-02, D-27, D-30, D-39 |
| R1-4 | Invoice vs due date | PARTIAL | D-04, O-6, O-17: source line shown in Finance only; roles not told apart |
| R1-5 | Medical extraction truncation | CLOSED | D-05 |
| R1-6 | Migrations not atomic | CLOSED | D-03 (Images was already transactional: challenged) |
| R1-7 | Library limits | CLOSED | D-06 (`tools.py` 6,000 is a window size: challenged) |
| R1-8 | CI failures | CLOSED | D-08, D-09, D-14, D-16, D-17; green on five heads |
| R1-9 | Prompt injection / tool permissions | PARTIAL | boundary enforced in code (D-10, D-24 to D-26, D-29, D-43); real model NOT VERIFIABLE HERE (O-10) |
| R1-10 | One model setting | CLOSED | D-36 (`kit/config.py`) |
| R1-11 | Large upstream responses | PARTIAL | D-07 refused above 100 MB; streaming not built (O-4) |
| R1-12 | Benchmarks | PARTIAL | store and queries only; real ingestion NOT VERIFIABLE HERE (O-5) |
| R1-13 | Regression tests incl. Mac/Docker | PARTIAL | everything that runs without a Mac; Docker not tested |

## 3. Review 2 (Gemini rubric)

| ID | Point | Status |
|---|---|---|
| R2-1 | Gates; no commented-out code | PARTIAL: gates run; "no commented-out code" not checked by a tool |
| R2-2 | The nine owner rules | PARTIAL: R-Q8 exception (O-8); R-Q10 not tested |
| R2-3 | Old migrations never edited | CLOSED (D-28; history before `e8718a1` NOT VERIFIED) |
| R2-4 | 500 MB memory | PARTIAL: measured, default 100 MB, no streaming (O-4) |
| R2-5 | Scorecard and unverified-claims ledger | CLOSED: `testing.md`, `defects.md` |

## 4. R3 (Gemini review of the PR)

R3-1 O-1: PARTIAL. R3-2 O-2: CLOSED (D-39) for the tool; leftovers on the Mac not inventoried. R3-3 O-4: REFUTED as a blocker, conditional. R3-4 O-6/O-7: REFUTED (conflated). R3-5 DDL not transactional: REFUTED. R3-6 float in statement import: REFUTED there, real path found (D-18). R3-7 encryption crash: REFUTED as stated, real gap fixed (D-22). R3-8 `;` splitting: REFUTED. R3-9 confirmation race: REFUTED as stated, real gap fixed (D-21). R3-10 UI-3 dark contrast: CLOSED (D-20). R3-11 honesty on migrations: REFUTED, real gap fixed (D-20).

## 5. R4 and R5 (author's audit and reply to the second ChatGPT review)

| ID | Item | Status |
|---|---|---|
| D-24 | "yes" meant any yes-word | CLOSED |
| D-25 | grouped changes | CLOSED |
| D-26 | deletes unstaged | CLOSED |
| D-27 | plain leftover after a crash | CLOSED |
| D-28 | migration immutability | CLOSED (see R2-3) |
| D-29 | a yes bound to the exchange before it | CLOSED |
| D-30 | crash-point tests | CLOSED |
| O-14 | range end as a result | PARTIAL (D-34) |
| O-15 | Images pre-upgrade copy | CLOSED (D-35) |
| O-16 | plain parser hand-over | PARTIAL (D-33) |
| O-17 | date source not shown | PARTIAL: Finance Documents page only |

## 6. R6 (ChatGPT comprehensive review; its four findings)

| ID | Finding | Status |
|---|---|---|
| R6-1 (R3-1) | float in `_coerce` | CLOSED (D-31) |
| R6-2 (R3-2) | `update.sh` moves the branch | CLOSED (D-32) |
| R6-3 (R3-3) | plain hand-over | PARTIAL (D-33, O-16) |
| R6-4 (R3-4) | health result vs range | PARTIAL (D-34, O-14) |
| R6-x | exhaustive audit of 508 entries, every screenshot, every deployment path | OPEN: 397 entries NOT INSPECTED (`coverage-matrix.md`); deployment NOT VERIFIABLE HERE |

## 7. R7 and R8

| ID | Item | Status |
|---|---|---|
| R7 | O-2, O-3, O-11, O-13, O-15, O-17 and UI notes listed as closed but not done | CLOSED after doing them (D-35 to D-42) |
| NEW-01 | test inventory did not add up | CLOSED (D-44, `scripts/test-inventory.py`) |
| NEW-02 | comment claimed undo; none exists | CLOSED (D-43); real undo OPEN (O-7) |
| O-13 | past history cut not announced | CLOSED (D-45) |

## 8. R9: ChatGPT product, screenshot and functionality review (this session)

Not yet replied to on the PR. Items checked against the code and screenshots:

| ID | Comment | Verified? | Status |
|---|---|---|---|
| P-1 | **Health says "All within range" for a report dated six months ago** and uses reassuring green; the requirement says show values as printed and do not interpret | **Confirmed** in the screenshot (`03-health.png`) and the code (`healthtravel.js`): the age was only shown from 12 months | **IN PROGRESS**: neutral wording ("2 results inside the printed ranges"), the report's age beside it, no green ring or border for a report older than three months, "no medicine records found", the printed-range note with "an older result does not describe today". Edited, **not tested, not committed** |
| P-2 | Finance "142% monthly vs before" has no comparison period | Confirmed (`app.js:828`; I was reading what "before" compares to when interrupted) | OPEN |
| P-3 | Empty "Due in 3 weeks €0" tile wastes space | Confirmed (screenshot 02) | OPEN |
| P-4 | Net worth next to "no statements read yet" confuses | Confirmed; the label was changed from "Cash €0" but net worth still shows | PARTIAL |
| P-5 | Metrics undefined (kept in 2026, savings rate, investment gain) and no data-freshness date | Confirmed: nothing shows the latest statement date | OPEN |
| P-6 | Figures look authoritative when source data is incomplete (reconciliation status) | Partly: the app proves months and holds back unproven ones, but the dashboard does not say so | OPEN |
| P-7 | Overview: crowded status pills, Ask invited while the AI is off, little to click | Confirmed (screenshot 01) | OPEN (UI-G) |
| P-8 | Photos disconnected page has no retry, no last-indexed time | Confirmed (`library/static/app.js:78`) | OPEN; needs a server-side drive recheck |
| P-9 | Calendar: empty grid, agenda below the fold | Confirmed (screenshot 06) | OPEN (UI-K) |
| P-10 | Travel: no itinerary, no segments, no source documents | Partly: documents list exists on the Documents tab; no segment detail | ROADMAP |
| P-11 | First run: no guided setup | Confirmed (screenshot 08) | ROADMAP (UI-L) |
| P-12 | Mobile: Ask button covers content, large cards | Padding fixed (measured 120 px); card size and header not changed | PARTIAL |
| P-13 | Personal Inbox across modules; personal timeline; source links in assistant answers; Update trust panel; document intelligence; financial and travel intelligence | Not present | ROADMAP |
| P-14 | Provenance on every fact (page, date extracted, verified) | Finance date source only | PARTIAL (O-17) |
| P-15 | Missing connected Photos screenshot | True: no photo drive in the demo | NOT VERIFIABLE HERE |
| P-16 | "Do not add yet": autonomous agent, cloud sync, medical advice | Agreed; nothing of that was added | CLOSED (no action) |

## 9. Open at this moment

- **Uncommitted, untested working-tree changes** for P-1: `library/src/library/static/healthtravel.js`, `design/design.css` and its copies. Until they are tested (eslint, prettier, browser check, a retaken Health screenshot, a test) they are **not** counted as done.
- Everything marked OPEN, PARTIAL, ROADMAP or NOT VERIFIABLE HERE above.
- The three blockers before sensitive use: the Mac and real-model run, the plain parser hand-over, and health layouts beyond a range end.
