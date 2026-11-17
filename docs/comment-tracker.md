# Comment tracker

One place for every review comment, whoever wrote it, and what became of it. **Rule:** every review the owner pastes gets rows here in the same session; a row is updated when its status changes; nothing is dropped. Reviewers (ChatGPT, Gemini) cannot post on GitHub; the owner pastes their reviews and the author posts the replies as PR comments (links below).

Status scheme (ChatGPT approved it with amendments; Gemini has not answered yet). Shown as **STATE — PROOF — FLAG — COMMIT** (every status names the commit its evidence applies to).
- STATE: OPEN · IN PROGRESS · FIXED · BLOCKED (needs the owner's Mac or a real model) · PARTIAL (remainder named) · ACCEPTED RISK (owner sign-off and reason) · REFUTED (evidence) · ROADMAP (suggestions only). CLOSED is not a state; it is derived.
- PROOF: P0 claimed only · P1 code read · P2 test passes · P3 author put the defect back and the test failed · P4 a reviewer independently reproduced it (commit, procedure, command, result recorded) · P5 verified on the owner's Mac with the real model.
- FLAG: NEEDS MAC/MODEL keeps that item OPEN until P5. It does not apply to unrelated items.
- SEVERITY (separate): blocker · high · medium · low · nit.
- **CLOSED = FIXED + P3 or stronger + reviewer confirmation (P4).** Until then: "FIXED — P3 — awaiting reviewer". Author-run mutation checks alone never close an item.
- Mapping of the words still used in the rows below: old CLOSED = FIXED — P3 (author-reported), awaiting P4; FIXED, UNPROVEN = FIXED — P2; NOT VERIFIABLE HERE = OPEN — NEEDS MAC/MODEL; PENDING = OPEN, or IN PROGRESS if started. No row is CLOSED under the new rule yet.

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
| R2-3 | Old migrations never edited | FIXED - P3 - awaiting reviewer (D-28; history before `e8718a1` NOT VERIFIED) - 97d5e29 |
| R2-4 | 500 MB memory | PARTIAL: measured, default 100 MB, no streaming (O-4) |
| R2-5 | Scorecard and unverified-claims ledger | FIXED - P1 - docs: `testing.md`, `defects.md` - 97d5e29 |

## 4. R3 (Gemini review of the PR)

R3-1 O-1: PARTIAL. R3-2 O-2: CLOSED (D-39) for the tool; leftovers on the Mac not inventoried. R3-3 O-4: REFUTED as a blocker, conditional. R3-4 O-6/O-7: REFUTED (conflated). R3-5 DDL not transactional: REFUTED. R3-6 float in statement import: REFUTED there, real path found (D-18). R3-7 encryption crash: REFUTED as stated, real gap fixed (D-22). R3-8 `;` splitting: REFUTED. R3-9 confirmation race: REFUTED as stated, real gap fixed (D-21). R3-10 UI-3 dark contrast: CLOSED (D-20). R3-11 honesty on migrations: REFUTED, real gap fixed (D-20).

## 5. R4 and R5 (author's audit and reply to the second ChatGPT review)

| ID | Item | Status |
|---|---|---|
| D-24 | "yes" meant any yes-word | FIXED - P3 - awaiting reviewer - 97d5e29 |
| D-25 | grouped changes | FIXED - P3 - awaiting reviewer - 97d5e29 |
| D-26 | deletes unstaged | FIXED - P3 - awaiting reviewer - 97d5e29 |
| D-27 | plain leftover after a crash | FIXED - P3 - awaiting reviewer - 97d5e29 |
| D-28 | migration immutability | FIXED - P3 - awaiting reviewer (see R2-3) - 97d5e29 |
| D-29 | a yes bound to the exchange before it | FIXED - P3 - awaiting reviewer - 97d5e29 |
| D-30 | crash-point tests | FIXED - P2 - 97d5e29 |
| O-14 | range end as a result | PARTIAL (D-34) |
| O-15 | Images pre-upgrade copy | FIXED - P3 - awaiting reviewer (D-35) - 97d5e29 |
| O-16 | plain parser hand-over | PARTIAL (D-33) |
| O-17 | date source not shown | PARTIAL: Finance Documents page only |

## 6. R6 (ChatGPT comprehensive review; its four findings)

| ID | Finding | Status |
|---|---|---|
| R6-1 (R3-1) | float in `_coerce` | FIXED - P3 - awaiting reviewer (D-31) - 97d5e29 |
| R6-2 (R3-2) | `update.sh` moves the branch | FIXED - P3 - awaiting reviewer (D-32) - 97d5e29 |
| R6-3 (R3-3) | plain hand-over | PARTIAL (D-33, O-16) |
| R6-4 (R3-4) | health result vs range | PARTIAL (D-34, O-14) |
| R6-x | exhaustive audit of 508 entries, every screenshot, every deployment path | OPEN: 397 entries NOT INSPECTED (`coverage-matrix.md`); deployment NOT VERIFIABLE HERE |

## 7. R7 and R8

| ID | Item | Status |
|---|---|---|
| R7 | O-2, O-3, O-11, O-13, O-15, O-17 and UI notes listed as closed but not done | FIXED - P3 for D-35 to D-40 and D-42, P2 for D-41 - awaiting reviewer - 97d5e29 |
| NEW-01 | test inventory did not add up | FIXED - P2 (D-44, `scripts/test-inventory.py`) - 97d5e29 |
| NEW-02 | comment claimed undo; none exists | FIXED - P3 - awaiting reviewer (D-43); real undo built later in `696f650` (O-7); a whole import still has no single undo - 97d5e29 |
| O-13 | past history cut not announced | FIXED - P3 - awaiting reviewer (D-45) - 97d5e29 |

## 8. R9: ChatGPT product, screenshot and functionality review (this session)

Not yet replied to on the PR. Items checked against the code and screenshots:

| ID | Comment | Verified? | Status |
|---|---|---|---|
| P-1 | **Health says "All within range" for a report dated six months ago** and uses reassuring green; the requirement says show values as printed and do not interpret | **Confirmed** in the screenshot (`03-health.png`) and the code (`healthtravel.js`): the age was only shown from 12 months | FIXED - P3 - awaiting reviewer - 796d485 (merged from the wip branch; browser-checked; test; an out-of-range result keeps its warning at any age) |
| P-2 | Finance "142% monthly vs before" has no comparison period | Confirmed (`app.js:828`; I was reading what "before" compares to when interrupted) | FIXED - P3 - awaiting reviewer - 631130b (comparison names its month: "vs October 2026") |
| P-3 | Empty "Due in 3 weeks €0" tile wastes space | Confirmed (screenshot 02) | FIXED - P3 - awaiting reviewer - 631130b (tile hidden when there are no payments; three-tile row) |
| P-4 | Net worth next to "no statements read yet" confuses | Confirmed; the label was changed from "Cash €0" but net worth still shows | FIXED - P3 - awaiting reviewer - 631130b (label: "without account balances: no statements read yet"). Not shown: that the figure itself is wrong; a complete/partial breakdown is not built (PARTIAL for that part) |
| P-5 | Metrics undefined (kept in 2026, savings rate, investment gain) and no data-freshness date | Confirmed: nothing shows the latest statement date | PARTIAL - P3 - a6c67bc and the next commit (the month card says proven or not and the newest payment date; the savings tile says "through <month>"; net worth says how many holdings were left out for lack of an exchange rate); investments and gain have no as-of date on the tile |
| P-6 | Figures look authoritative when source data is incomplete (reconciliation status) | Partly: the app proves months and holds back unproven ones, but the dashboard does not say so | PARTIAL - P3 - a6c67bc ("not proven: <reason>. These figures may be incomplete."); list of missing months and the assistant using it OPEN (the assistant never sees finance data: owner decision) |
| P-7 | Overview: crowded status pills, Ask invited while the AI is off, little to click | Confirmed (screenshot 01) | FIXED - P3 - awaiting reviewer - aec2230 (one summary chip; "Read new files" stays in view at 1280, 1100, 900 px). Ask-while-AI-off wording not changed |
| P-8 | Photos disconnected page has no retry, no last-indexed time | Confirmed (`library/static/app.js:78`) | OPEN - owner decision: the drive is mounted when the container starts (`library/docker-compose.pictures.yml:32`), so a recheck cannot find a later drive; a "Check again" button was built and reverted |
| P-9 | Calendar: empty grid, agenda below the fold | Confirmed (screenshot 06) | FIXED - P3 - awaiting reviewer - aec2230 (empty month is one line with a jump to the next month that has something) |
| P-10 | Travel: no itinerary, no segments, no source documents | Partly: documents list exists on the Documents tab; no segment detail | ROADMAP |
| P-11 | First run: no guided setup | Confirmed (screenshot 08) | ROADMAP (UI-L) |
| P-12 | Mobile: Ask button covers content, large cards | Padding fixed (measured 120 px); card size and header not changed | PARTIAL |
| P-13 | Personal Inbox across modules; personal timeline; source links in assistant answers; Update trust panel; document intelligence; financial and travel intelligence | Not present | ROADMAP |
| P-14 | Provenance on every fact (page, date extracted, verified) | Finance date source only | PARTIAL (O-17) |
| P-15 | Missing connected Photos screenshot | True: no photo drive in the demo | BLOCKED - NEEDS MAC/MODEL (no connected photo drive in the demo) |
| P-16 | "Do not add yet": autonomous agent, cloud sync, medical advice | Agreed; nothing of that was added | ROADMAP (scope note, no defect) |

## 9. Open at this moment

- P-1 (Health) is on the PR branch now (`796d485`), browser-checked and tested.
- **Status words:** ChatGPT approved with amendments (section 10); Gemini's answer is still awaited. The rows below keep the old words until the owner confirms the final set; the mapping is in the header.
- Everything marked OPEN, PARTIAL, ROADMAP or BLOCKED above. Work left for the author: none that can be done without new input. O-14 needs real reports; a currency-aware three-decimal import is opposed by the author (see comment 6950256794). Waiting on the owner: O-16, the Photos drive mount (P-8), the assistant part of P-6, the Mac and real-model runs.
- The three blockers before sensitive use: the Mac and real-model run, the plain parser hand-over, and health layouts beyond a range end.

## 10. ChatGPT's answer on the status scheme (head `41e9d36`; decision REQUEST CHANGES)

It reported that it did not run the tests or mutations itself, so every P3 here is author-reported and none is P4. Amendments it asked for, all adopted above: CLOSED is derived, not a state; the display is STATE — PROOF — FLAG; NEEDS MAC/MODEL applies only to the items that need it; P4 must be a real independent check.

Qualifications to carry into the rows (to be applied row by row, not yet done):
- D-41 (UI notes) and D-44 (test inventory): P2, not P3. D-41 mixes source, browser and screenshot evidence; split it by sub-item.
- D-06: the first mutation missed a hard-coded limit; keep that history. D-22: tested with four threads, not a broad multi-process stress. D-28: history before e8718a1 not verified. D-32: the `--ff-only` mutation alone was not detected (guards made it equivalent); the guards were. D-10 and R1-1 carry NEEDS MAC/MODEL for real-model use.
- D-08, D-14, D-16 rest on earlier CI runs; the exact head must not be called green unless its own run shows it.
- REFUTED means the evidence shows the claim false, not "not reproduced".
- O-1, O-4, O-6, O-7, O-8, O-9, O-12, O-14, O-16, O-17 stay PARTIAL or OPEN with the named remainder. O-16 is a candidate for ACCEPTED RISK only with the owner's written sign-off (reason, scope, exposure window, compensating controls, review date); mode 0600 and cleanup are mitigations.
- P5 records must name device and OS, commit, model name and version, data category (no personal data), steps, expected and observed result.
- Audit coverage: "397 of 508" is the earlier audit's figure; the PR now changes 510 files. Recount at the head being reviewed before quoting it.

Its remaining blockers: (1) no P5 run for real model, ingestion/OCR, Docker and connected Photos; (2) O-16 plain hand-over, no sign-off; (3) O-10; (4) O-14 and P-1; (5) O-6; (6) O-12; (7) O-1; (8) O-4; (9) O-7; (10) audit recount; (11) CI for the exact head not shown.

## 11. R10: ChatGPT review of `87702bd` (its findings F1 to F15) and Gemini's prompt for `2e2fd91`

Checked by reading source at `87702bd` only; nothing run, no browser. State, proof and commit as in the scheme above. Nothing here is fixed yet; the author has not changed code for R10.

| ID | Finding | What the source shows at `87702bd` | State - proof - commit |
|---|---|---|---|
| F1 | "monthly vs before" has no stated baseline | Valid. The baseline is the previous calendar month (`modules/events.py:200`, same pattern in `modules/money.py:305`), but the tile says only "before" (`finance/static/app.js:828`). The percentage is hidden when the baseline is 0 (`app.js:947`) | FIXED - P3 - awaiting reviewer - 631130b |
| F2 | Empty "Due in 3 weeks" tile always drawn | Valid (`app.js:872`) | FIXED - P3 - awaiting reviewer - 631130b |
| F3 | Net worth shown while accounts say "no statements read yet" | Valid as presentation: `nw.net_worth` is drawn whatever `nw.accounts` is (`app.js:849-855`). Whether the figure is wrong was not shown | FIXED - P3 - awaiting reviewer - 631130b (label); a complete/partial breakdown not built |
| F4 | No freshness or period on headline metrics | Valid, not built (same as P-2) | PARTIAL - P3 - a6c67bc (month card only) |
| F5 | Dashboard and assistant do not state incomplete reconciliation | Valid, not built; reconciled months exist in the data, not on the dashboard (same as P-3) | PARTIAL - P3 - a6c67bc (dashboard part; assistant part is an owner decision) |
| F6 | Photos disconnected has no retry | Valid: one status call, message says restart (`library/static/app.js:78,109`) (same as P-7) | OPEN - owner decision (see P-8) - aec2230 |
| F7 | Calendar draws an empty month grid first | Valid (O-9 / P-8) | FIXED - P3 - awaiting reviewer - aec2230 |
| F8 | Overview header crowded | Valid, already recorded (UI-G, P-9) | FIXED - P3 - awaiting reviewer - aec2230 |
| F9 | Travel hero has a gradient over a cover photo | Valid: `healthtravel.js:270` and `design.css:272,428,1050`; `docs/design.md` says "no gradients" and already points to the UI review. Either amend the rule or remove them; the text must stay readable | FIXED - P3 - awaiting reviewer - 40d023b (legacy gradients in atlas.css and finance/app.css remain, overridden, not scanned) |
| F10 | First-run guidance | Same as P-11 | ROADMAP |
| F11 | Travel itinerary | Same as P-10; the reviewer itself calls it roadmap | ROADMAP |
| F12 | Provenance on every module | Same as P-14 / O-17 | PARTIAL - P3 for Finance dates - 97d5e29 |
| F13 | Plain parser hand-over | Same as O-16; stays a blocker for sensitive use until the owner signs off or it changes | PARTIAL - P3 - 97d5e29, NEEDS MAC/MODEL for the Docker check |
| F14 | No older-release upgrade fixture | Same as O-12 | PARTIAL - P3 - 745668c, 1b19673 (Finance and Documents; Images and real older databases not covered) |
| F15 | Coverage must not read as exhaustive; recount at the head | Agreed. Not yet recounted at `87702bd` | FIXED - P2 - cde07ec (matrix regenerated at 80562da; recount needed again at a later head) |

Nothing new was found beyond what the tracker already held, except F1 as a precise wording defect and F9 as a confirmed gradient location list.

**Gemini's prompt (head named `2e2fd91`)**: its "NOT FIXED" list is out of date. `2e2fd91` is an ancestor of `87702bd`, and the items it lists as to-do are already in the tracker with tests: O-2 (D-39), O-3 (D-36), O-11 (D-38), O-13 (D-37, D-45), O-15 (D-35), O-17 (D-40, Finance only) and the UI-review items (D-41; gradient, Photos retry, mobile Ask padding and "Cash" label are the ones still partly open). Its counts (1,231 tests, 403 of 499) are old; the figures are 1,265 tests at `97d5e29` and an uncounted audit scope at `87702bd`. It asks for fixes the owner did not ask for in this round, so none were started from it.

**C-1 (new, from `docs/claude-review.md` at `cc06e92`):** the coverage matrix counts are stale (matrix: 508 entries at `5676a6a`; `cc06e92`: 511 with rename detection, 583 without). OPEN. The same file records the author re-run at `cc06e92` (1,265 tests passed) and three explicit disagreements with ChatGPT (F3 and F4/F5 severity, F13 remedy).

## 12. Final reviewer answer on `80562da` (scheme APPROVED WITH AMENDMENTS; PR not approved for merge or sensitive-data use)

Reviewer did not independently reproduce fixes, run the app, or read all 512 files. Amendments adopted from this point (the header above is updated to match):
- Format is **STATE - PROOF - FLAG - COMMIT**; every status names the commit its evidence applies to; evidence from an older commit is not proof for a newer head.
- A **BLOCKED** state is added: the check cannot be done now (owner's Mac or a real model needed). It stays BLOCKED, never CLOSED.
- FLAG says whether the item is a merge blocker, needs device/model verification, is accepted risk, or is ordinary follow-up.
- Author-run tests, CI, static inspection and independent reproduction are kept separate.

Reviewer's actions before closure, and where each stands at the head named: (1) regenerate the coverage matrix: **done in this commit** (512 entries, carried-over row statuses, four AUTHORED rows; C-1 FIXED - P2 - this commit, awaiting reviewer); (2) tracker in the new format: header updated, rows still use the older words and mapping, row-by-row rewrite OPEN; (3) independent verification of financial calculations, consent, encryption, migrations: needs a reviewer other than the author, OPEN; (4) O-16: blocker for sensitive use, owner decision pending; (5) Mac/model checks: BLOCKED; (6) older-release and extraction fixtures (O-12, O-14): OPEN; (7) P-1 outside this PR: agreed, unchanged; (8) nothing is closed on documentation alone: agreed.
Reviewer's O-1 ask (tests across zero-, two-, three-decimal currencies on import and calculation paths): agreed as the remainder of O-1; the statement-import path is untested. O-4 documents roughly 5x memory on a 66 MB JSON; supported input limits are not yet written down: OPEN.

## 13. R11: Gemini sign-off written against `2e2fd91` ("Ready for Merge & Local Deployment")

Recorded, not adopted as an approval. `2e2fd91` is an ancestor of the current head; the answer names no commit for any item and does not use the agreed STATE - PROOF - FLAG - COMMIT format, so by the agreed rules its statuses count as unverified.
- Its "FIXED" ledger repeats the author's own claims (P3, author-reported); it names no check it ran itself. Nothing becomes VERIFIED or CLOSED from it.
- Out of date: "1,231 tests" (1,265 at `97d5e29`/`cc06e92`); it defers O-2, O-3, O-11, O-13, O-15, O-17 as undone, but they were done at `97d5e29` (D-39, D-36, D-38, D-37/D-45, D-35, D-40).
- O-16 is listed as an accepted trade-off. It is not: ACCEPTED RISK needs the owner's written sign-off (reason, scope, exposure window, controls, review date), and none exists. The other reviewer calls it a blocker for sensitive use.
- "Linters and type checkers completely green" and "UI theme checks green": CI for the exact heads completed without failure; no one has independently re-run lint, type checks or the page check.
- Merge is the owner's decision. Open items remain as tracked: O-1, O-4, O-5, O-6, O-7, O-8, O-9, O-10, O-12, O-14, O-16, P-1 to P-16 and the NEEDS MAC/MODEL checks.
Conclusion: Gemini's answer does not change any status. It does agree the next real step is a run on the owner's Mac with the local model, which is what stays BLOCKED until then.

## 14. Changes after the final reviewer answer on `80562da` (all author-run; CI for these commits not yet seen when this was written)

| Commit | What |
|---|---|
| `138f900`, `631130b` | Finance dashboard: comparison names its month, empty due tile hidden, net-worth label (P-2, P-3, P-4); browser-checked; `finance/tests/test_dashboard_labels.py` |
| `40d023b` | No gradients in `design.css` and the Documents pages; flat photo tints; `library/tests/test_no_gradients.py`. Limit: legacy gradient rules remain in `atlas.css` and `finance/app.css` (overridden by `design.css`, not scanned) |
| `aec2230` | Calendar empty month and header summary chip (P-9, P-7); `atlas/tests/test_header_and_calendar_pages.py` |
| `796d485` | Health freshness (P-1); `library/tests/test_health_freshness.py` |
| `a6c67bc` | Month proven or not and newest payment on the dashboard (P-5, P-6 in part) |
| `326e0a5` | **Found while working on O-1:** `tables.parse_money` rounded a third decimal to cents without a word; it now refuses to read such an amount (the statement is then held back). Earlier docs said the three-decimal currencies were refused everywhere; for statement import that was not true until this commit |
| `745668c`, `1b19673` | Older-release upgrade tests for Finance and Documents (O-12) from text dumps written by the code of older commits |
| `f011e8e` | Images: an index written by the released aperture code (`5d3ddb5`, the real older release) opens with the current code and is encrypted in place with every row intact (O-12 for Images; the schema is the same 16 steps in both builds) |
| `87d7ee3` | Dashboard: net worth says how many holdings were left out for lack of an exchange rate (they were silently excluded before); savings tile says "through <month>" |
| (next commit) | O-16: sealed hand-over built (`library/src/library/seal.py`), off by default, not run in Docker; supersedes the earlier "oppose" of the redesign for the code part. The Docker run on the Mac is BLOCKED - NEEDS MAC/MODEL |

## 15. Review of `be059e4`: O-16 malformed-key data-loss risk (found by a reviewer, confirmed)

**Finding:** a malformed private key could make the app delete sealed hand-over files and their completion marks. **Reproduced** at `be059e4` with `/tmp`-style script (author-run, one fresh sealed file per key): not hexadecimal, a truncated key, a key 1 byte too long and `zz` x 32 each ended with `rejected: 1`, the `.sealed` file gone and the mark gone; an empty key and a wrong-but-valid key kept both. **Cause:** `seal.open_sealed` raised plain `ValueError` for a bad key, and `store.ingest_dir` rejects (deletes) on `ValueError`/`OSError`. **Fix (`afb1b66`):** `SealKeyError` (unusable key), `SealError` (key and file do not match; a wrong key and a damaged file cannot be told apart), `NotSealedError` (too short to be sealed); `store._read_handover` keeps the file and mark for the first two and rejects only the third. The same check protects the parser side: a malformed public key stops the reader before it writes a file or a mark.
**Tests (author-run):** 15 new in `library/tests/test_seal.py` and `test_sealed_handover.py`: nine malformed or empty private keys plus a wrong key, each leaving the sealed bytes identical and the mark present, nothing reported as rejected, and the very same file opening once the key is fixed; key files that are missing, empty or garbage; a trailing newline in a key file; a too-short file rejected; four malformed public keys leaving the output folder empty. Two mutations (restore the plain `ValueError`; make a key problem reject) fail 5 and 3 of them.
**State:** O-16 PARTIAL - P3 - `afb1b66`: sealed hand-over implemented, OFF by default, NOT verified in Docker (BLOCKED - NEEDS MAC/MODEL); the plain hand-over still runs by default and remains a blocker for sensitive-data use until the sealed one is turned on and checked on the Mac, or accepted in writing. This is author-run evidence, not independent verification.
**Coverage recounted at `afb1b66`:** 541 entries, equal to the git list; rows 105 ROUND, 15 ROUND + VIEWED, 24 AUTHORED, 397 NOT INSPECTED. The 397 are the carried-over rows that nobody has read line by line; the count was checked against the rows, not copied.
**Unchanged:** O-4 streaming, three-decimal currency support and P-8 parent-folder mounting are NOT implemented. Real-model, OCR, connected Photos, real health-report and owner-Mac checks remain BLOCKED. Nothing is VERIFIED or CLOSED.

### 15b. Re-run of the O-16 checks requested for independent verification (head `a1e66f8`; **author-run, not independent**)

The request asked a reviewer to run these. The author ran them, because only the author could do so in this session; that makes them author-run evidence. They do not make O-16 VERIFIED.
- `cd library && python -m pytest -q tests/test_seal.py tests/test_sealed_handover.py` at `d696672`: `22 passed`.
- Mutation: `_key_bytes` raising plain `ValueError` instead of `SealKeyError` (both branches): **9 failed, 13 passed** (6 in `test_seal.py::test_a_malformed_key_is_a_key_error...`, plus `test_no_malformed_empty_or_wrong_private_key_ever_deletes_a_sealed_file_or_its_mark`, `test_a_key_file_that_is_missing_empty_or_garbage_also_keeps_the_sealed_file`, `test_a_malformed_public_key_stops_the_reader_before_it_writes_or_marks_anything`). Restored with `git checkout`; working tree clean; `22 passed` again.
- `store.ingest_dir` with six keys (one fresh sealed file each): empty, whitespace, odd-length hex, the correct key with `0x` prefix, a 64-byte key: **file kept, mark kept, `unopened: 1`, nothing stored, nothing rejected**. The correct key in upper case: opened and stored (the file is then removed as designed; the mark stays).
- Deletion paths (`library/src/library/store.py`): 236 and 247 remove `.done` marks of documents that were replaced or forgotten (`_replace_older_versions`, `_forget`); 258 removes mail-seen caches; 344 `_remove_orphans` removes only `.*.tmp` older than an hour; 403-404 the reject path (reached only by `NotSealedError`, JSON or UTF-8 errors after a successful decryption, symlink or oversize, and `OSError`); 424 the unlink after a successful ingestion (only files in `stored`, appended at 420 after the `continue` for unopened files at 390). Only caller of `ingest_dir`: `library/src/library/reading.py:94`. A key or configuration error cannot reach 403-404 or 424: `_read_handover` (360-373) turns every `SealKeyError` and `SealError` into `_WAITS`.
- **Two concrete findings from this audit, both fixed in `a1e66f8`:** (1) an all-zero (low-order) ephemeral key made `open_sealed` raise a plain `ValueError` ("Error computing shared key") that was rejected and deleted by accident; it is now `NotSealedError`, rejected on purpose, because no honest sealer writes one and the original is read again. (2) `reading.py` ignored `unopened`, so a missing or wrong key meant "0 new files" with no explanation; the read summary now says "N files read but not opened: the key for the sealed hand-over is missing or wrong (nothing was lost, they open once it is right)". Both have tests that fail when reverted.
- Cryptography review (`library/src/library/seal.py`, author reading, no independent reviewer): X25519 + HKDF-SHA256 (salt = ephemeral public + recipient public, fixed info string); a fresh ephemeral key per file, so each ChaCha20-Poly1305 key is used once and the random 12-byte nonce cannot repeat under one key; the associated data is the ephemeral public key. A wrong key and a damaged file fail authentication identically, so neither is treated as a reason to delete. Limitations, not bugs: no sender authentication (anyone holding the public key can write a sealed file; the app still validates the schema as for plain files); the associated data does not include a format or version tag or the file name; the private key is passed as an environment variable, so it is visible to anyone who can run `docker inspect` on the app container (the same pattern as the database key); `bytes.fromhex` accepts spaces between bytes. The lazy import means a parser image without `cryptography` fails loudly on the first sealed write (not exercised).
- Docker: **READ ONLY - NOT RUN.** Neither image was built; the sealed hand-over was not exercised in Docker.
