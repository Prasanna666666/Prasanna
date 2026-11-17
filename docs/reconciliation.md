# Reconciliation of every defect and open item

Status words: **FIXED** (changed, and a test fails if the defect returns), **PARTIALLY FIXED**, **OPEN**, **NOT REPRODUCED**. "Mutation check" means I put the defect back into the code (one line) and ran the named test: DETECTED = it failed. Where I did not do that, the column says **not mutation-checked**: the test may still be real, but it was not proven to bite. Line numbers are from commit `0761872`+ (the head of this review round).

## What mutation checking found

22 defects were reintroduced one at a time. 15 were detected at the first attempt; in 2 my mutation text did not match the formatted source (re-run: both detected); 2 were not detected (D-06 and the R3-2 `--ff-only` change); 3 more (two update-script guards and the D-22 lock) were added and detected. The two misses:
- **D-06**: a hard-coded `255` in the *validation* path was not noticed; the tests only exercised the *repair* path. Test added (`test_a_raised_limit_lets_longer_names_sources_and_text_through_whole`); mutation now detected.
- **R3-2**: replacing `--ff-only` by `reset --hard` was not detected because the guards in front of it make the two equivalent; the guards themselves were mutated instead (unsaved changes, local commits): both detected.
- **D-25 / D-10**: not misses: my mutation text did not match the formatted source; re-run with the right text, both detected.

## Defects

| ID | Status | Where (file:line) | Test, and what it proves | Mutation check |
|---|---|---|---|---|
| D-01 money as float | **FIXED** | `kit/src/kit/money.py:72` `to_minor`; `finance/src/finance/toolrun.py:113` `_coerce` (R3-1) | `finance/tests/test_money_exact.py` (60): 1.005, 12.345, −1.005, 1.004999…9 (22 digits) → 100, long strings, every money argument of every tool keeps the exact text | float coercion back: **DETECTED** (3 tests fail) |
| D-02 plain copy after encryption | **FIXED** | `kit/src/kit/db.py:193` `encrypt_in_place` | `kit/tests/test_db_safety.py`, `test_db_crash_points.py`: no plain file or readable bytes after conversion | never scrubbed: **DETECTED** |
| D-03 migrations atomic | **FIXED** | `kit/src/kit/db.py:334` `_run_step`, `:321` `_statements`; Images `images/src/images/db.py:321` | halfway failure leaves no table, version unchanged, retry works, triggers and `;` in strings stay whole | no rollback: **DETECTED** |
| D-04 dates verified | **PARTIALLY FIXED** | `kit/src/kit/extract.py:160` `verify_dates` | a date must be written in the document; source line kept; due before date dropped. **Not solved:** invoice vs due vs payment role (O-6); nothing in a page shows the source (O-17) | unwritten date accepted: **DETECTED** |
| D-05 medical extraction complete | **FIXED** | `kit/src/kit/extract.py:473` `medical_details` | no caps, halves a failing piece, reports unread parts; 300 values, 80 medicines, 100,000+ characters | stop after 12 pieces: **DETECTED** |
| D-06 limits central | **FIXED** (after strengthening) | `library/src/library/limits.py:12`, `store.py:187` `_kept` | all limits read from `limits.json`, cut recorded, re-read when changed | hard-coded again: **DETECTED** (after the new test) |
| D-07 oversize answer | **FIXED** | `atlas/src/atlas/upstream.py:55` `_answer_limit`, `:31` | below / at / one byte over the limit; bad setting | cut instead of refused: **DETECTED** |
| D-08 CI red | **FIXED** | `.github/workflows/ci.yml` | four consecutive runs with 18 green checks (`0685a6f`, `20f7d13`, `02ac173`, `ddce7da`) | not applicable |
| D-09 typing | **FIXED** | `images/src/images/quality.py`, `indexing/judge.py`, `library/src/library/readers.py`, `kit/src/kit/text.py:30` | mypy clean on Python 3.11 | not mutation-checked |
| D-10 writing tools unguarded | **FIXED in code** (real model **NOT VERIFIED**) | `finance/src/finance/toolrun.py:51` `STAGED`; `changes.py:85` `stage`; `web.py:233` | every tool classified once; read-only tools change nothing; poisoned arguments change nothing | tool unclassified: **DETECTED** |
| D-11 model selection | **FIXED** | `atlas/src/atlas/assistant.py:55` `ModelClient`; `kit/src/kit/llm.py` `pick_installed` | configured model only, local host only, fixed seed | not mutation-checked |
| D-12 every card hidden | **FIXED** | `design/design.css:111` | `kit/tests/test_design.py` (no rule hides a surface); `scripts/check-pages.js:93` hidden-surface check (11 on the old CSS) | hidden again: **DETECTED** |
| D-13 calendar contrast | **FIXED** | `design/design.css` `.heat-cell.heat-top` | axe `PROBLEMS 0` light and dark | not mutation-checked |
| D-14 atlas test import | **FIXED** | `atlas/tests/test_assistant_safety.py` | `pytest -q` in a clean venv | not applicable |
| D-15 weak page check | **PARTIALLY FIXED** | `scripts/check-pages.js` | now checks the apps inside Atlas and hidden surfaces. **A passing axe run does not show a page is usable** (stated in `ui-review.md`) | the hidden-surface part: **DETECTED** with the broken CSS |
| D-16 Tesseract in CI | **FIXED** | `.github/workflows/ci.yml` | Library job green | not applicable |
| D-17 stale design copy | **FIXED** | `library/src/library/static/design.css` | `kit/tests/test_design.py` copies equal | not mutation-checked |
| D-18 European amounts | **FIXED** | `kit/src/kit/money.py:29` `parse_amount` | either notation, ambiguous `1,250` refused | not mutation-checked |
| D-19 dates before 2000 | **FIXED** | `kit/src/kit/extract.py` `_DATE_PATTERNS` | 1985, 1999-12-31, 3.4.1998, January 5, 1972 | not mutation-checked |
| D-20 dark contrast | **FIXED** | `design/design.css` `--on-accent` | `THEME=dark node scripts/check-pages.js` → 0 problems | not mutation-checked |
| D-21 stuck "running" change | **FIXED** | `finance/src/finance/changes.py:111` `_expire` | marked failed, never repeated | not closing it: **DETECTED** |
| D-22 two converters at once | **FIXED** | `kit/src/kit/db.py:210` `_exclusive` | 4 threads converting one file end with one good file | lock removed: **DETECTED** (6 of 6 runs) |
| D-23 weak read-only test | **FIXED** | `finance/tests/test_assistant_changes.py` | fails if more than three tools refuse the empty call | not mutation-checked |
| D-24 "yes" meant any yes-word | **FIXED** | `kit/src/kit/consent.py:23` `confirms` | 28 cases incl. "no, don't do it", "I'm not sure", "ok?" | old logic: **DETECTED** |
| D-25 grouped changes | **FIXED** | `finance/src/finance/changes.py:85` | one yes makes everything announced together | drop own question's changes: **DETECTED** |
| D-26 deletes unstaged | **FIXED** | `finance/src/finance/web.py:233` | prepared with the name of the target; delete word in an unrelated message deletes nothing | **DETECTED** |
| D-27 plain leftover after crash | **FIXED** | `kit/src/kit/db.py:225` `_retire_redundant_copy` | identical copy removed; a differing copy never touched | **DETECTED** |
| D-28 migration immutability | **FIXED** (history before `e8718a1` **NOT VERIFIED**) | `scripts/migration-hashes.py:17`; `library/tests/test_migrations_frozen.py` | a real edit of a released step fails; `test_the_check_notices_an_edited_step` is synthetic and proves little | edited step: **DETECTED** |
| D-29 yes bound to the exchange | **FIXED** | `finance/src/finance/changes.py:132` `confirm`; `atlas/src/atlas/upstream.py:568` | any other message drops what waits | keeping it: **DETECTED** |
| D-30 crash points | **FIXED** | `kit/tests/test_db_crash_points.py` | six injected stops: failure reported, one good encrypted file, no leftover | fault injection, not mutation |

## Defects found by this follow-up review

| ID | Status | Finding | Fix | Test (mutation) |
|---|---|---|---|---|
| D-31 (R3-1) | **FIXED** | `_coerce` read a typed number through a float: `"1.004999999999999999999"` became 1.005 and was stored as 101, not 100 | integral → int, otherwise `Decimal`; units stored as a plain count | `test_a_typed_amount_reaches_the_ledger_exactly…` (**DETECTED**) |
| D-32 (R3-2) | **FIXED** | `update.sh` ran `git checkout -B atlas origin/atlas`, which moves the branch pointer away from local commits | `scripts/update-code.sh`: refuses unsaved changes and local commits, tags where the branch was, fast-forward only | 7 scenarios in `atlas/tests/test_update_script.py` (guards **DETECTED**) |
| D-33 (R3-3) | **PARTIALLY FIXED** | Hand-over files held whole text, mode default; an interrupted reader left `.<id>.tmp` forever | mode 0600; abandoned temporaries removed after one hour; cleanup after success and rejection and "only what it stored" tested. **Still plain inside the shared Docker volume until ingested** (O-16) | `library/tests/test_handover.py` (mode **DETECTED**) |
| D-34 (R3-4) | **PARTIALLY FIXED** | A model could report an end of the printed range as the result and it passed (only "printed" was checked) | a result must be on its test's line (or the next, if nothing numeric follows the name) and not only an end of the printed range; otherwise kept exactly but marked `check`, never range-flagged, never used for "change since" | `kit/tests/test_extract_whole_document.py` (**DETECTED**). Layouts where the result is in another column or page are **NOT VERIFIED** |

## Added after the second follow-up (D-35 to D-42)

All seven of these were mutation-checked (the defect put back, the test failed): O-2 cleanup without confirmation, O-3 shared setting ignored, O-11 cut not recorded, O-13 notice removed, O-15 copy removed, O-17 source not kept, and the hero-text regression (D-42).

## Open items

| ID | Status | Note |
|---|---|---|
| O-1 currencies in hundredths | **PARTIALLY FIXED** | JPY exact; three-decimal amounts refused (`money.py:57`); statement import of such currencies untested |
| O-2 | **FIXED** (D-39): `kit/src/kit/db.py` `retire_leftover`, `kit/cleanup.py`. Mutation-checked. |
| O-3 | **FIXED** (D-36): `kit/src/kit/config.py`. Mutation-checked. |
| O-4 500 MB | **PARTIALLY FIXED** | default 100 MB, measured about 5× memory; no streaming |
| O-5 real-library speed/quality | **OPEN, not verifiable here** | needs the Mac |
| O-6 invoice vs due date | **OPEN** | inherent without word lists |
| O-7 routine writes | **PARTIALLY FIXED** | classified and enforced; routine writes run at once; no undo |
| O-8 word lists in `consent.py` | **PARTIALLY FIXED** | whole-message rule, bound to the exchange; English and Dutch only |
| O-9 UI notes | **OPEN** | |
| O-10 real-model injection | **OPEN, not verifiable here** | |
| O-11 | **FIXED** (D-38): `truncation_audit`, `clipped`. Mutation-checked. |
| O-12 old-release fixtures | **OPEN** | |
| O-13 | **FIXED** (D-37): `atlas/assistant.py`. Mutation-checked. |
| O-14 range end as value | **PARTIALLY FIXED** | see D-34 |
| O-15 | **FIXED** (D-35): `images/db.py`. Mutation-checked. |
| O-16 plain hand-over | **PARTIALLY FIXED** | see D-33 |
| O-17 | **FIXED** (D-40): `finance/modules/statement_import.py`, `static/app.js`. Mutation-checked. |
