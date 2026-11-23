# Legacy audit source archive — PR #6

**Source snapshot:** `c92f5bf471d78695e539e5676973adda048095cc` (legacy PR #6 baseline). These files are preserved verbatim below; their statuses are historical and must not be treated as current-head verification. The coverage matrix is the legacy 541-entry inventory, not the current 266-file Atlas scope.


---

## Original `docs/defects.md`

# Defect register

Every defect found in this review round, who found it, how it was verified, and what changed. "Found by": **R1** = the ChatGPT review, **R2** = the Gemini audit prompt, **S** = found by the author while doing the work (including by taking the screenshots). Severity: P0 (wrong money or exposed data), P1 (silent loss or broken gate), P2 (risk or inconsistency), UI.

Status words are literal: **Fixed** = changed and covered by a test that fails without the change; **Open** = not fixed; **Not reproduced**.

## Fixed

| ID | Sev | Defect | Found by | Evidence it was real | Fix (commit) | Test |
|---|---|---|---|---|---|---|
| D-01 | P0 | Money converted with `round(float(x)*100)`: 1.005 became 100 (and 12.345 → 1234) | R1 | `grep` of about a dozen call sites; arithmetic reproduced | One `kit.money` (Decimal, one rounding, half away from zero) on every input path (`934dd51`) | `finance/tests/test_money_exact.py` |
| D-02 | P0 | Converting a plain database left the plain file beside the encrypted one, verified only by counting tables | R1 | Code and docstring (`kit/db.py` kept `<name>.unencrypted`); Images test asserted it | Verify by content before and after the swap, then overwrite and delete; keep only with `ATLAS_KEEP_PLAINTEXT=1`; interrupted conversions finished or undone (`24d9a95`) | `kit/tests/test_db_safety.py` (10), `images/tests/test_engine.py` |
| D-03 | P1 | Kit migrations ran `executescript(step)` then recorded the version separately: a failure halfway left a changed schema with the old version | R1 | Code reading; `executescript` commits and runs statements in autocommit | Each step plus its version note in one `BEGIN IMMEDIATE` transaction, statement by statement, rollback on error (`24d9a95`). Images already wrapped steps in `BEGIN…COMMIT`; it now also rolls back a half-run step | `kit/tests/test_db_safety.py`, `images/tests/test_engine.py` |
| D-04 | P1 | `date` and `due_date` of a document were stored as the model said, without checking the document writes them | R1 | `verify_trip_fields` covered only trip dates | `verify_dates`: real calendar date and written in the document; model quotes the line, kept as source; due before date dropped; unverified → unknown (`43620a9`) | `kit/tests/test_extract_whole_document.py` |
| D-05 | P1 | Medical reader stopped after 12 windows (≈ 60,500 characters), 60 values and 30 medicines per window, 240/60 final caps, text cut to 80/40 characters; a failing window aborted the whole document | R1 | Constants in `kit/extract.py`; a 100,000-character test lost everything after the 12th piece | No caps; pieces start and end at line breaks; unreadable piece read in halves; what still cannot be read is reported as `complete: false` with part, characters and pages; older results re-read once (`43620a9`) | same file (9 tests), `library/tests/test_health_travel.py` |
| D-06 | P1 | Library limits split between `limits.json` and constants in `store.py`/`sniff.py` (`MAX_JSON`, `MAX_TEXT`, `MAX_NAME`, `MAX_SOURCE`, `MAX_PROMISED`, JSON detection size, a literal 255) | R1 | grep; changing `limits.json` did not change them | All read from `limits.json` when used and in the fingerprint; a cut name or source is now recorded like a cut text (`37786f7`) | `library/tests/test_limits_config.py` (7) |
| D-07 | P2 | An upstream answer over `MAX_BODY` was cut at the limit and then failed as "unreadable" | R1 | Reproduced with a server answering 9 MB and a 1 MB limit: wrong message, not lost data | Refused as too large with its size in plain words; `ATLAS_MAX_ANSWER_BYTES` (`cf32bac`) | `atlas/tests/test_scan_status.py` (below / at / above) |
| D-08 | P1 | CI would fail: Finance and Library tests import PyYAML (not in `dev`); Images CI installed kit without SQLCipher; Pillow ≥ 13 cannot install on Python 3.10 | R1 | Last three GitHub runs on `atlas` are red (`gh`/API); Pillow resolution reproduced for 3.10 | PyYAML in `dev`; Images CI installs `kit[secure]`; Python 3.11 is the minimum everywhere (Docker already runs 3.12) (`2101dbc`) | clean-venv runs on 3.11 |
| D-09 | P1 | With a clean install, mypy flagged Pillow variable rebinding (`img = img.convert(...)`) in 3 files, and `kit/text.py` had an untyped `dict` that Atlas's mypy run reported | S | clean 3.11 venv; Atlas mypy run | variables renamed; `dict[str, Any]` (`2101dbc`, `cf32bac`) | mypy |
| D-10 | P2 | The assistant could call every writing Finance tool at once (only deletes needed the owner's words). A fooled model could change money records with no confirmation and no trail | R1 (as "prompt injection") | Code reading: `_post_tool` ran any tool but deletes. **No real model was shown to be steered** — conditional risk | Classification of all 80 tools; nine money-record tools only prepared, confirmed by the owner's own next short yes, once, within 10 minutes, audit trail (`596e937`) | `finance/tests/test_assistant_changes.py` (14), `atlas/tests/test_assistant_safety.py` (8) |
| D-11 | P2 | Atlas picked the first installed `ministral*` model, or the first installed model of any kind | R1 | Code reading | `ATLAS_MODEL` (default `ministral-3:3b`), same family rule as Finance, no substitute; fixed seed; local-host check in the client (`596e937`) | `atlas/tests/test_assistant_safety.py` |
| D-12 | **P0-UI** | **Every `.card` and `.stat` on every page of every app was `display: none`.** Finance's dashboard showed a greeting and an empty page; Documents tiles were hidden | S (screenshots) | Computed style in a real browser; blame: commit `3c53b30` (14 Nov, "dead Health styles removed") deleted the declaration block of the surfaces rule and left its selectors merged into the `display:none` rule | Rule restored (`50f384d`) | `kit/tests/test_design.py` (fails on the broken CSS, verified); `scripts/check-pages.js` reports 11 hidden surfaces on the broken CSS |
| D-13 | UI | The busiest day of the spending calendar failed WCAG contrast (white-ish text on mid-accent). Hidden until D-12 was fixed | S (axe) | axe `color-contrast` | darkest cells use the accent with white text (`50f384d`) | `check-pages.js` |
| D-14 | P1 | `atlas/tests/test_assistant_safety.py` imported `tests.test_assistant`, which only works under `python -m pytest`; CI's `pytest -q` would have failed collection | S | clean-venv run | import fixed (`50f384d`) | `pytest -q` in a clean venv |
| D-15 | P1 | The page check (`check-pages.js`) opened Documents' pages standalone, where they only say "These pages belong inside Atlas", so Documents, Health and Travel were never really checked; and it could not see hidden cards | S | screenshot of the stub page | Atlas routes are checked with the apps inside it (axe in each frame) and a hidden-surface check (`50f384d`) | the script itself |
| D-16 | P1 | Library CI failed on `test_a_picture_in_a_mail_is_also_kept_as_a_file_for_the_picture_engine`: "Tesseract is not installed". The test needs text recognition; CI installed only `poppler-utils`. Passed here only because Tesseract is installed in this environment | S (GitHub job log for run 43965318672) | CI log | `tesseract-ocr` installed in the Library CI job; Library 3.11 and 3.13 are green on `e9a76cc` | the CI job |
| D-17 | P1 | The Library copy of `design.css` was not committed with the CSS fix, so `kit/tests/test_design.py` (copies must equal `design/design.css`) would fail in CI | S | `git status` after the commit | committed | `kit/tests/test_design.py` |
| D-18 | P1 | A model- or person-typed amount in European notation was silently misread: `"1.250,50"` became 1.2505 and was stored as 1.25 (`_coerce` stripped commas and called `float`) | S (my own audit, found by running it) | Reproduced: `_coerce(tool, {"amount": "1.250,50"}) == {"amount": 1.2505}` | `kit.money.parse_amount` reads either notation (last separator is the decimal point) and refuses `1,250` / `1.250` as ambiguous instead of guessing | `finance/tests/test_money_exact.py` |
| D-19 | P2 | Dates before 2000 (`1985`, `1999-12-31`) were never recognised, so such a date was stored as unknown | S | Reproduced with `dates_in` | Years 19xx and 20xx accepted. Two-digit years stay unknown on purpose | `kit/tests/test_extract_whole_document.py` |
| D-20 | P2 | **Dark theme failed WCAG contrast on every active control** (white text on the light dark-theme accent: tabs, active menu item, chips, calendar day). The claim "WCAG AA in both themes" was only unit-tested for body text; the browser check had only ever run in light | R3 (the Gemini review) said "dark contrast"; the cause it named (timestamps) does not exist, the real cause was found by running axe in dark | axe `color-contrast` on 6 pages | `--on-accent` (white in light, near-black in dark) used everywhere text sits on the accent; `THEME=dark node scripts/check-pages.js` | `scripts/check-pages.js` light and dark: `PROBLEMS 0` |
| D-21 | P2 | A change claimed (`running`) by a program that then stopped stayed `running` forever, with no way to know if it was made | S | Code reading | After the confirmation window it is marked `failed` with "it is not known whether this was made"; never repeated | `finance/tests/test_assistant_changes.py` |
| D-22 | P2 (conditional) | Two programs opening the same plain database at once could both start converting it | S | Code reading: no cross-process lock | A lock file beside the database serialises conversions | `kit/tests/test_db_safety.py` (4 threads) |
| D-23 | P2 | The "read-only tools change nothing" test called each tool with `{}`; I had not checked how many refused that call (3 of 54 did, so they proved nothing) | S | Counted | The three get the arguments they need; the test fails if more than three refuse | `finance/tests/test_assistant_changes.py` |
| D-24 | **Blocker** | **`kit.consent.confirms` treated any short message containing a yes-word as consent**: `"no, don't do it"`, `"do not confirm"`, `"I'm not sure"`, `"ok what is my budget"`, `"yes but wait"` were all confirmations | Final audit (author, own reproduction) | Printed `True` for all twelve probes before the fix | The whole message must be a yes: after the yes-words are removed only filler may remain; a question mark is never a yes | `kit/tests/test_consent.py` (28 cases) |
| D-25 | High | Two changes prepared in one question were both announced to the owner, but a "yes" made only the last; the first was silently dropped | Final audit | Reproduced: payments made `[2200]`, states `done, superseded` | Changes of one question stay together and one yes makes them all; only an earlier question's changes are replaced | `finance/tests/test_assistant_changes.py` |
| D-26 | High | `delete_*` tools ran at once whenever the message contained a delete word, whatever it was about: "how do I delete the typo in my note?" deleted a task | Final audit | Reproduced: `delete_task ran: True, tasks left: 0` | Deletes are prepared like other changes (with the name of what they delete) and made only by the owner's yes; `update_note` and `update_person` (overwrites) are prepared too | `finance/tests/test_assistant_changes.py` |
| D-27 | Medium | A conversion that stopped after the swap but before the plain file was removed left the plain copy for good; the next start did not clean it | Final audit | Reproduced: `a.db.unencrypted` still readable after the next start | A plain copy whose rows are identical to the encrypted file's is removed on the next start; a copy that differs is never touched | `kit/tests/test_db_safety.py` |
| D-28 | Medium | R2-3 "old migrations are never edited" had no test | Gemini (R2-3), confirmed | no such test | `scripts/migration-hashes.py` and `library/tests/test_migrations_frozen.py`. Checked against `e8718a1`: this round only appended one step (money 15 → 16); no old step changed. **History before `e8718a1` is not checked** (the default branch `aperture` has an unrelated layout) | the test |
| D-29 | High | A "yes" was not bound to the exchange before it: a change waiting for up to ten minutes could be made by a later "yes" meant for a different question (ChatGPT, "bind confirmation to one specific pending action") | ChatGPT review, confirmed by reading `changes.confirm` | A proposal stayed `waiting` through any number of other messages | Atlas sends every message to the part; any message that is not a yes (including "no") drops what was waiting, so a yes only answers the exchange right before it | `finance/tests/test_assistant_changes.py`, `atlas/tests/test_assistant_safety.py` |
| D-30 | Medium | Crash safety of the encryption conversion was tested at three stops, not at every stage | ChatGPT review | Missing tests | Fault injection at six stages (copying, verifying the copy, before the first rename, between the renames, verifying the swapped file, overwriting the plain copy): each is reported as a failure, never as success, and the next start leaves one good encrypted file with all rows, the version and a clean integrity check, and no leftover file | `kit/tests/test_db_crash_points.py` (9) |
| D-31 | High | **Money tool arguments were read through a float** (`finance/src/finance/toolrun.py` `_coerce`): `"1.004999999999999999999"` became 1.005 and was stored as 101 instead of 100 | ChatGPT review R3-1, reproduced | The old code with the new test: 3 failures | Exact text kept (integers as int, others as `Decimal`); units stored as a plain count | `finance/tests/test_money_exact.py`; mutation detected |
| D-32 | High | `update.sh` ran `git checkout -B atlas origin/atlas`, which moves the branch pointer away from local commits | ChatGPT review R3-2, confirmed by reading | Code | `scripts/update-code.sh` refuses unsaved changes and local commits, tags where the branch was, fast-forwards only | `atlas/tests/test_update_script.py` (7 scenarios) |
| D-33 | Medium | The reader's hand-over files held whole text with default permissions and a stopped reader left `.<id>.tmp` for good | ChatGPT review R3-3 | Code | Mode 0600, abandoned temporaries removed after an hour, cleanup after success and rejection tested. **Still plain inside the shared Docker volume until ingested** (O-16) | `library/tests/test_handover.py` |
| D-34 | Medium | A model could report an end of the printed reference range as the result and it passed verification | ChatGPT review R3-4 | Reproduced with `10,0` of `7,5 - 10,0` | A result must be on its test's line (or the next) and not only a range end; otherwise kept exactly but marked `check`, never range-flagged, not used for "change since" | `kit/tests/test_extract_whole_document.py`, `library/tests/test_health_travel.py` |
| D-35 | Low | **O-15** Images made no pre-upgrade copy of its index | Reviewers; confirmed | `images/db.py` had no backup code | An index that already holds pictures is copied (same encryption) before an upgrade, last three kept | `images/tests/test_engine.py` (new-index case and old-index case); mutation detected |
| D-36 | Low | **O-3** the model was chosen in three places | Reviewers; confirmed | grep | `kit/config.py`: an app's own setting, then `ATLAS_MODEL`, then the default; Finance, Documents and Atlas ask there; a test fails if an app reads the default model by itself | `kit/tests/test_config.py`; mutation detected |
| D-37 | Medium | **O-13** a tool result cut to 2,500 characters and a message cut to 2,000 were never announced | Reviewers; confirmed | `atlas/assistant.py` | A note appears next to the answer: how long the result was and how much the assistant saw; the same for a long message | `atlas/tests/test_assistant_safety.py`; mutation detected |
| D-38 | Medium | **O-11** stored fields were cut with no record | Reviewers; confirmed | `statement_import.py` | `truncation_audit` table (Finance): source, field, original and kept length for description, title, summary, party, reference, place, file name, date source (`GET /api/truncations`); `clipped` list in a file's own facts for kind, place, source line and entities | `finance/tests/test_truncation_audit.py`, `kit/tests/test_extract_whole_document.py`; mutation detected |
| D-39 | Medium | **O-2** no safe way to remove old `.unencrypted` leftovers | Reviewers; confirmed | none existed | `kit.db.retire_leftover` and `python -m kit.cleanup [folder]`: an identical copy is removed at once; a different one only if the owner types yes for that file; nothing is removed when the encrypted file is missing, the key is wrong or the copy cannot be read | `kit/tests/test_db_cleanup.py` (8); mutation detected |
| D-40 | Medium | **O-17** the line a date came from was never shown | Reviewers; confirmed | no consumer | Finance stores `date_source` / `due_date_source` (verified dates only), returns them from `finance_documents`, and the Documents page shows them under each date (screenshot `09`) | `finance/tests/test_truncation_audit.py`; mutation detected. The JS test is a source check; the rendering was verified in a real browser |
| D-41 | Low | **UI notes**: Travel gradient, Photos shown up while "not connected", "1 reports", chart axis with points while values use commas, Ask button over content on phones, "Cash €0" when no statement was read | UI review | screenshots | Plain place colour; Photos health asks whether the drive is connected (`/api/health?needs=photos`) and shows down when it is not; plurals; axis follows the report's decimal comma; 120 px bottom padding on phones (measured in the app frame); "no statements read yet" | `library/tests/test_web.py`, browser check light and dark, screenshots |
| D-42 | Medium | **A regression I introduced and my own checks missed:** a CSS edit turned the text of every hero card white on a white card, so the Health summary headline disappeared. `scripts/check-pages.js` (axe) did **not** flag it; a screenshot did | Author, from the screenshot | Screenshot of Health | Corrected before commit | `kit/tests/test_design.py` (no plain hero card has white text); mutation detected. **Lesson recorded: axe passing does not show a page looks right** |
| D-43 | Medium | **The code comment said routine writes were "open to the person to undo". There is no undo.** `complete_task` and `reschedule_task` changed existing records with no way back | ChatGPT review (NEW-02), confirmed | `finance/toolrun.py:38`; no undo code exists | The comment is corrected. Routine writes are now only the ones that ADD something (person, date, task, note, event) or read the owner's files; `complete_task` and `reschedule_task` are prepared like other changes and made only by the owner's yes. A test checks every routine write against existing rows | `finance/tests/test_assistant_changes.py` (both new tests) |
| D-44 | Low | **`docs/testing.md` inventory did not add up** (it was generated once; later tests were not in it) | ChatGPT review (NEW-01), confirmed | header "kit (84)" while the suite had 163 | `scripts/test-inventory.py` counts with pytest and sums the rows; the table is regenerated from it | the script output |
| D-45 | Low | Past conversation turns cut to 6 messages / 600 characters were not announced (O-13) | ChatGPT review, confirmed | `atlas/assistant.py` | A note next to the answer says what the assistant remembers | `atlas/tests/test_assistant_safety.py` |

## An admission

Two earlier statements of mine were wrong and are corrected here, because reviewers should not rely on them: the commit message of `c2a7728` said "screenshots before and after are identical", and the earlier sessions said the browser check was clean. D-12 existed from 14 Nov, those checks could not see it (axe finds nothing in a page whose cards are hidden), and no screenshot was compared in that commit. Treat the earlier "axe clean" claims as void; the present result (`PROBLEMS 0`) is the first one that covers visible content.

## Open

| ID | Sev | Issue | Why open | Suggested next step |
|---|---|---|---|---|
| O-1 | P2 (mitigated; not supported) | Every currency is stored in hundredths. **Zero-decimal currencies (JPY) are exact. Three-decimal currencies (KWD, BHD, ...) are NOT supported: a typed amount that needs the third decimal is refused with a plain message (`kit/currencies.json`, `check_fits`), and on statement import an amount with a non-zero third decimal is not read at all, so that statement is held back and cannot be proven (`finance/tables.py` `parse_money`, fixed in `326e0a5`; before that commit statement import rounded it to cents without a word).** What is tested: typed amounts, `parse_money` and one statement end to end (`finance/tests/test_statement_amounts_exact.py`). Not built: reading such a statement correctly | Per-currency exponent would change the stored unit everywhere (author opposes it) | Only if three-decimal accounts are real |
| O-2 | resolved | see D-39 | | | |
| O-3 | resolved | see D-36 | | | |
| O-4 | P2 (conditional, mitigated) | Atlas answer limit **default lowered from 500 MB to 100 MB** after a measurement: parsing a 66 MB JSON answer peaked at 329 MB (about 5× the answer), so 500 MB would have needed about 2.5 GB. Real answers are kilobytes; nothing is allocated up front; larger answers are refused with their size in plain words and `ATLAS_MAX_ANSWER_BYTES` changes the limit. Streaming or bounded parsing is not done | Parsing still needs about 5× the answer | Stream or paginate if an app ever needs bigger answers |
| O-5 | — | Reading speed, OCR, and 3B-model sorting quality on a real library; `finance categorise --measure` has no corrections to measure against yet | Needs the owner's Mac and data | Run on the Mac, report counts |
| O-6 | P2 | Which of several dates is the invoice date and which the due date cannot be told by code without word lists; the quoted line makes it checkable by the person, not by code | Inherent to the no-word-lists rule | Show the source line in the UI next to each date |
| O-7 | P2 (undo built; one gap) | The assistant's routine additions (person, date, task, note, event) are journaled (`finance/additions.py`, table `assistant_additions`). `undo_last_additions` takes back the latest question's additions: prepared by the assistant, made only by the owner's own yes (also via the Yes button). A whole statement import has no single undo: its payments are deleted one by one. Tests: `finance/tests/test_undo_last_additions.py`, `test_recovery_of_routine_writes.py` | Built in the round after `ca4416b`; not yet run with the real model | Reviewer comments first |
| O-8 | P2 | `kit/consent.py` holds word lists (yes / delete / undo in English and Dutch) in code, against the no-hardcoding rule | They gate the owner's own words; moving them to data needs a design for languages | Move to `kit/consent.json`; add languages |
| O-9 | UI (partly resolved by D-41) | See `ui-review.md`. Fixed: Travel gradients (`40d023b`), Health decimal separators, Ask button room on phones, "1 report", "142% vs before", empty tile, header pills, empty calendar month. UI-J done on the owner's decision (Yes and No buttons in the chat that send the person's own reply). UI-L first-run checklist done (`firstRun` on the Atlas overview). UI-H is by design: the Documents stub says the pages belong inside Atlas and links to it | Found by screenshots; not yet changed | Reviewer comments first |
| O-10 | — | Real-model prompt-injection resistance not demonstrated | Needs a real model and a test corpus | Red-team corpus run on the Mac, kept out of CI |
| O-11 | resolved | see D-38 | | | |
| O-12 | P2 (partly done) | Older-database upgrades are tested with text dumps (the repository keeps no database files) written by older code: Finance from `5f7fa48` (`finance/tests/test_upgrade_from_older_release.py`), Documents from `573d04f` (`library/tests/test_upgrade_from_older_release.py`), Images from the released aperture build `5d3ddb5` (`images/tests/test_upgrade_from_released_aperture.py`). Finance and Documents are development-history commits of this branch, not releases (none existed before this PR); only the Images one is a real released build. **Not covered: the owner's own older databases, and rollback after a failed upgrade with such a database** | Needs a copy of the owner's real older database (anonymised) | Keep one small anonymised database per release as a text dump |
| O-13 | resolved | see D-37 | | | |
| O-14 | P2 | Extraction checks that a value is *printed* in the document, not that it is the measurement: a model that reports the end of a reference range (`10,0` of `7,5 - 10,0`) as the result passes `_health_window` | Needs structure, not substrings | Require the value to be outside the printed range text on its line |
| O-15 | resolved | see D-35 | | | |
| O-16 | P2 (sealed hand-over implemented, OFF by default, NOT Docker-verified; key-handling bug fixed in `afb1b66`; deletion-path audit and two further fixes in `a1e66f8`, author-run) | The parser writes a plain-text JSON result with the whole text beside the inbox until Documents ingests and deletes it (`store.ingest_dir`), so "everything encrypted" is true of the databases, not of this hand-over. **Built (`library/src/library/seal.py`): when `LIBRARY_HANDOVER_PUBLIC_KEY` is set the parser seals each hand-over file to the app's PUBLIC key (X25519 + ChaCha20-Poly1305, a fresh key per file). The parser can write it and cannot read it back; only the app, which alone holds `LIBRARY_HANDOVER_PRIVATE_KEY`, opens it. A missing, malformed or wrong key leaves the sealed file and its completion mark in place and counts it as unopened; only a file too short to be sealed at all is rejected.** **Reviewer finding, confirmed and fixed (`afb1b66`):** in `be059e4` a malformed private key (not hexadecimal, wrong length) raised a plain `ValueError` inside `open_sealed`, and `ingest_dir` treated it as an unusable input file: it deleted the sealed file and its mark (reproduced for four kinds of malformed key; missing and wrong-but-valid keys were already safe). Now key errors are `SealKeyError`, a key/file mismatch is `SealError`, a too-short file is `NotSealedError`, and `_read_handover` keeps the file for the first two. The dedicated tests `test_no_malformed_empty_or_wrong_private_key_ever_deletes_a_sealed_file_or_its_mark`, `test_a_key_file_that_is_missing_empty_or_garbage_also_keeps_the_sealed_file` and others fail against the old code (author mutation check). Both images now install `cryptography`; the parser image still carries no shared code. Tests: `library/tests/test_seal.py`, `test_sealed_handover.py`. **Not run in Docker, not enabled by default** (the images were not built or started here). Until the owner turns it on and runs it on the Mac, the plain hand-over (mode 0600, cleaned up) is still what runs | Needs a build and a run on the owner's Mac | Turn on with the steps in `docs/security-deployment-review.md`, then run a read and check the volume holds only `.sealed` files |
| O-17 | resolved | see D-40 | | | |

## Not reproduced

- A cloud endpoint reaching the model: Atlas already refused non-private `ATLAS_MODEL_URL` at start-up; the client check is defence in depth.
- Silent data loss from the 500 MB read: the result was a wrong error message, not lost data (D-07).
- A model steering the assistant from a document: no demonstration either way (O-10).


---

## Original `docs/comment-tracker.md`

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


---

## Original `docs/reviews.md`

# Review comments

Three kinds of review are recorded here: the two outside reviews the owner asked for, the author's own findings, and the place where friends add theirs. Each comment says what was **checked**, whether it was **confirmed**, **challenged** or **not reproduced**, and where it went (`defects.md` IDs).

**Friends: please comment on the pull request**, not in this file. Use inline comments on a line of code or of these documents, and put the ID (`R-Q4`, `D-10`, `UI-3`) in the first words so it can be tracked. The table at the end is for the author to fill from those comments.

## Review 1: ChatGPT ("Engineering Re-review and Remediation", baseline `e8718a1`)

| # | Comment | Verdict | What I did |
|---|---|---|---|
| 1 | Keep local AI; do not treat sending data to the owner's own Ollama as a breach; verify destination and that nothing can reach a public endpoint | **Agreed.** Atlas already refused a non-private `ATLAS_MODEL_URL` at start-up; I added the same check inside the client | D-11, `design.md` |
| 2 | P0 float money (`money.py`, `statement_import.py`, `extract.py`) | **Confirmed** (1.005 → 100). `kit/extract.py` itself does not use float for money (it reads printed text with integers); the float paths were in Finance | D-01 |
| 3 | P0 plaintext copy after encryption, verify by content, interrupted conversion, wrong key, missing SQLCipher | **Confirmed.** It was documented behaviour ("kept until you delete it"), but a plaintext copy of everything is a real exposure | D-02 |
| 4 | P1 verify all dates | **Confirmed** for `date`/`due_date`. Part of "do not confuse invoice/due/issue dates" is **not solvable by code** without word lists (rule R-Q8); a quoted source line is kept instead | D-04, O-6 |
| 5 | P1 medical extraction truncates silently | **Confirmed**, and worse than stated: a failed window aborted the whole document and text was cut to 80/40 characters | D-05 |
| 6 | P1 migrations not atomic | **Confirmed for kit.** **Partly challenged for Images**: its steps were already `BEGIN…COMMIT` inside one script; the real gap there was a half-run step leaving its transaction open | D-03 |
| 7 | P1 centralise Library limits | **Confirmed** for `store.py`/`sniff.py`. **Challenged**: `tools.py` `MAX_TEXT = 6000` is the size of a chat answer in the model's 4096-token window, not storage; kept | D-06 |
| 8 | P1 CI failures (PyYAML, SQLCipher, Pillow on 3.10) | **Confirmed all three**; the last three runs on `atlas` are red. Found two more in clean environments (Pillow typing, Atlas test import) | D-08, D-09, D-14 |
| 9 | P2 prompt injection and tool permissions | **Conditional risk, fixed in code.** I could not demonstrate a real model being steered; I could show nothing in code stopped a fooled model. Challenged the framing "claim exploitable only after a test": I added the adversarial-document test as a *code* test (every writing tool called with poison, nothing changes) | D-10, O-10 |
| 10 | P2 model configuration consistency | **Partly done.** Atlas now follows `ATLAS_MODEL`, the shared pick rule and seed. Finance and Documents still read their own settings | D-11, O-3 |
| 11 | P2 large upstream responses | **Fixed.** Not silent data loss (reproduced as a wrong message). The default limit itself is a memory question on 8 GB | D-07, O-4 |
| 12 | Benchmarks at 1k/10k/100k/300k | **Partly.** Store and queries only, synthetic rows (see `testing.md`). **Not** ingestion, OCR or model calls, which need the Mac | O-5 |
| 13 | Regression tests incl. Mac/Docker deployment, local Ollama connectivity, large file ingestion | Done for everything that runs without a Mac; connectivity tested against a fake model server; Docker/`up.sh` not tested | `testing.md` gaps |

## Review 2: Gemini ("Exhaustive engineering audit" prompt)

This was a rubric to apply, not a finished audit; I was interrupted while running it. What it asked for, and where each point stands:

| Point | Status |
|---|---|
| Layer boundaries and quality gates (50 statements, 7 args, 15 branches, complexity 15, no magic values, no commented-out code) | Gates run and clean (`testing.md`). "No commented-out code or filler comments" was **not** checked by a tool; a reviewer could grep for it |
| Nine owner rules | Covered in `requirements.md` (R-Q*); R-Q8 has a known exception (O-8) and R-Q10 is not separately tested |
| Model boundary, sampling, Decimal-only finance, append-only migrations | Decimal: D-01. Append-only: kept (new migration appended to the end of `money.py`'s list). A test that old migrations are never edited does **not** exist |
| No-network guard, upstream health, **memory impact of `MAX_BODY = 500_000_000` on an 8 GB Mac** | Valid and **open** (O-4). Reading one 500 MB answer into memory is heavy for 8 GB; I did not change the default because the owner asked for no limits |
| Scorecard and "unverified claims ledger" | The ledger is `testing.md` ("Not run here") and `defects.md` ("admission") |

Starting that audit is what surfaced the untyped `dict` in `kit/text.py` (D-09).

## Review 3: Gemini review of this pull request (pasted by the owner)

Every claim was checked against the code, not accepted. Posted on the PR as comment series `R3-1` to `R3-11`.

| # | Gemini's claim | Verdict | Evidence / what changed |
|---|---|---|---|
| R3-1 | O-1 High: fixed hundredths breaks zero-decimal (JPY) and three-decimal currencies | **Partly.** JPY is stored consistently ×100, not miscalculated; KWD/BHD lose the third digit | Stays **Open** (O-1), rated Medium |
| R3-2 | O-2 High: old `.unencrypted` files must be shredded | **Agreed it is an exposure; challenged "must be shredded automatically"**: such a file may be the only pre-encryption copy. New conversions already overwrite and delete | **Open** (O-2) |
| R3-3 | O-4 Blocker: "allocating raw 500 MB buffers per request" | **Challenged.** `read(limit + 1)` reads what arrives; it does not allocate 500 MB. Real answers are kilobytes; an over-limit answer is refused. Only a pathological 500 MB answer is a risk | **Open**, conditional (O-4) |
| R3-4 | O-6/O-7: routine categorisation writes run unconfirmed | **Partly wrong.** Categorisation (`set_category`) is already confirm-gated. O-6 is about date roles, not writes. O-7 (tasks/notes/people) is a stated choice | no change |
| R3-5 | R1-6: DDL can implicitly commit, so migrations are not transactional; use savepoints | **Refuted.** In SQLite DDL is transactional; `executescript` (which does commit first) is no longer used. `test_a_migration_that_fails_halfway_changes_nothing_and_can_be_retried` creates a table, fails, and asserts the table is absent | no change |
| R3-6 | Money float path in `statement_import.py` | **Not reproduced there**: `_money` goes through `Decimal(str(float))`, exact as written, with no float arithmetic. **A different real float path was found while checking**: `_coerce` turned `"1.250,50"` into 1.2505 | **Fixed** D-18 |
| R3-7 | Encryption: crash between rename and commit can orphan handles and leave zero valid databases | **Refuted as stated**: tests cover a stop between the renames, a corrupt encrypted copy, a failed check after the swap, a failed copy. **Found a real gap while checking**: two programs converting at once | **Fixed** D-22 |
| R3-8 | Migration splitting by `;` breaks triggers and quoted strings | **Refuted.** The splitter is `sqlite3.complete_statement`, which understands quotes, comments and trigger bodies; a trigger test existed. Added a semicolon-in-string and in-comment test | test added |
| R3-9 | Confirmation race / token replay can double-execute | **No token exists to replay.** Consumption is `UPDATE … WHERE state='waiting'` with a rowcount check. Added a 6-thread test on separate connections: exactly one change. **Found a real gap**: a change left `running` by a stopped program | **Fixed** D-21 |
| R3-10 | UI-3: dense dashboard; timestamps fail dark-theme contrast | **Timestamps do not exist on the dashboard**, but **dark contrast really did fail**, on all active controls | **Fixed** D-20; density is UI-F, still open |
| R3-11 | Honesty: docs claim atomic migrations but splitting leaves partial state | **Refuted** by R3-5. **A true honesty gap found instead**: "WCAG AA in both themes" had never been run in a browser in dark | corrected in D-20 and `requirements.md` |

## Review 4: the final follow-up audit prompt, run by the author

The prompt asked for an independent audit, with the disputed findings (R1-4, R1-6, R1-7, R1-9) reassessed and the money, encryption, migration, extraction, assistant-safety, limits and test areas tested with reproductions. Results, posted on the PR as comment `R4`:

| Disputed finding | Reassessment (evidence) |
|---|---|
| R1-4 invoice vs due date | **An inherent limit plus one implementation gap.** Source line is kept (`date_source`), an unverified date becomes unknown, a due date before the date is dropped. But **no page shows the source line** (O-17), so the owner is not told which date is a guess |
| R1-6 Images migrations | **Author's rebuttal holds for atomicity** (`BEGIN; step; PRAGMA user_version=N; COMMIT`, rollback on error, tested). **New gap:** Images makes no pre-upgrade copy (O-15) |
| R1-7 `MAX_TEXT = 6000` | Sites: `library/tools.py:29,120` (answer size for the model's window); `atlas/assistant.py:30,50,261` (owner's message cut to 2000), `:35,320` (tool result cut to 2500); storage limits are `limits.json`. 6000 is not storage. The 2000/2500 cuts are display/model limits, but are **not announced** (O-13) |
| R1-9 prompt injection | **A missing boundary existed, now closed, and the earlier boundary had two holes the author had not seen**: a "yes" meant anything with a yes-word in it (D-24), and deletes were not prepared at all (D-26). Still not demonstrated with a real model (O-10) |

| Area | New findings |
|---|---|
| Money | End to end: 3,000 random amounts through the entry point sum exactly (integer sum, summary and exact decimal agree); 1.005 → 101, 12.345 → 1235, −1.005 → −101, 99999999999.995 → 10000000000000. KWD 1.005 is stored as 1.01 (O-1). European and US notation: D-18 (found earlier) |
| Encryption | Crash-point table in `docs/design.md`-style form below; D-27 fixed |
| Migrations | Immutability test added (D-28) |
| Assistant safety | D-24, D-25, D-26 |
| Extraction | O-14 (range end accepted as a value) |
| Limits | O-13, O-16 |

**Encryption crash points.** (1) before copying: nothing changed. (2) during copying: only `.encrypting` exists, removed on the next run. (3) after the encrypted file exists: verified before anything is replaced. (4) during verification: a failure removes the copy and raises; nothing replaced. (5) during replacement: original is renamed to `.unencrypted`, encrypted file renamed in, checked again; a stop between the two renames is finished or undone on the next open (tested). (6) during scrubbing: the plain copy may remain; the next start removes it if its rows equal the encrypted file's (D-27, new). (7) sidecars: `-wal`/`-shm` of the plain file are removed by SQLite's clean close and by `_retire`; a stale sidecar left by a hard kill beside the *new* encrypted file is **NOT VERIFIED**. APFS/SSD: overwriting cannot promise old blocks are gone; FileVault does.

## Review 5: ChatGPT second review of this pull request

Verified against the code and posted on the PR as comment `R5`.

| Item | ChatGPT's position | Disposition |
|---|---|---|
| R1-4 | Partially resolved; do not silently assign an ambiguous date | **Partially resolved, agreed.** Source line kept, unverified date unknown, due before date dropped; role confusion and display of the source are open (O-6, O-17) |
| R1-6 | Not verified; filesystem operations | **Closed.** Images migrations are SQL only (no file operations), version update is in the same transaction (`images/db.py:321`), tested; the only gap is no pre-upgrade copy (O-15) |
| R1-7 | Likely resolved pending call sites | **Closed.** Sites listed in Review 4; model-window and display cuts only; stored data intact; announcing them is O-13 |
| R1-9 | Keep open pending the execution path | **Kept open for a real model; boundary proven in code** (thirteen writes and six deletes prepared only, owner's yes bound to the exchange before it, Library tools only read or prepare) |
| O-8 | High; confirmation not explicit, not bound to one action | **Confirmed and fixed in two steps**: D-24 (the whole message must be a yes) and D-29 (a yes only answers the exchange right before it; any other message drops the proposal). Word lists remain (English, Dutch) |
| O-1 | Medium; restrict or implement per-currency precision | **Mitigated**: a three-decimal currency amount that would lose the third decimal is refused; JPY exact; tested end to end |
| Encryption crash safety | Not verified; add crash-point tests | **Done**: D-30, six injected stops |
| O-2 | Inventory plaintext locations | **Done**: `docs/data-locations.md`, with NOT VERIFIED rows |
| O-3 | One model setting | Open (design) |
| O-4 | Measure memory; configurable limits | **Measured** (5× the answer) and the default lowered to 100 MB; streaming not done |
| O-7 | Classify routine / material / consequential | **Done**: read-only, routine writes, consequential writes and deletes (all prepared), classification enforced by a test |

## Review 6: ChatGPT "comprehensive engineering review" of head `ddce7da` (request changes)

Posted on the PR as comment `R6`. Four named findings, all checked: **all four were real** (D-31 to D-34, fixed or partly fixed). The request for an exhaustive audit of 496 entries, every screenshot, every deployment path and every test was **not completed** and the documents say so: `docs/coverage-matrix.md` (96 entries read in the round, 403 **not inspected**), `docs/reconciliation.md` (status of every D-/O- item with a mutation check where done), `docs/security-deployment-review.md`.

## Review 7: Gemini "final readiness" prompt

The prompt listed O-2, O-3, O-11, O-13, O-15, O-17 and the UI notes as already closed. **They were not** (no `kit/config.py`, no cleanup test, no `truncation_audit`, no notices, no Images backup, nothing read `date_source`); this was reported as such on the PR (`R7`). They were then done, each with a test that fails when the defect is put back (D-35 to D-42), and the screenshots were retaken.

## Author's own findings

D-09, D-12, D-13, D-14, D-15 in `defects.md`. The most important: D-12, every card hidden by CSS for two days, found only because the apps were finally run and photographed.

## Friends' comments (to be filled from the pull request)

| Date | Reviewer | Where (file/line or screenshot) | ID | Comment | Author's reply | Status |
|---|---|---|---|---|---|---|
| | | | | | | |


---

## Original `docs/coverage-matrix.md`

# Changed-file coverage matrix

Recounted at `afb1b66ed6fedb182b68a7b139d2b3033598959e` (checked two ways: `git diff --name-status -M origin/aperture...HEAD` lists 541 entries, D 100, A 364, M 5, R 72, and every one is a row below; the rows count 105 ROUND, 15 ROUND + VIEWED, 24 AUTHORED, 397 NOT INSPECTED = 541). Last regenerated from `git diff --name-status -M origin/aperture...HEAD` at `4adc71a0b8d6486cf71a0a6f8996f8d3c32d29e5`. **541 entries with rename detection (D 100, A 364, M 5, R 72).** 512 were listed at `80562da`; the 20 added since are listed at the end (tests, fixtures and screenshots of this round; code files changed in the round were already in the list, so their rows are unchanged) The 508 of the previous version was the count at `5676a6a`; the four new entries are documents and a script added after it (listed at the end, status AUTHORED). Row statuses for the other 508 entries are carried over unchanged from `5676a6a`; none was re-inspected for this regeneration, and code is unchanged since `97d5e29`. This is the honest account, **not** a claim of exhaustive inspection.

Status key: **ROUND** = changed in the review round (`e8718a1..HEAD`): read, changed and covered by tests named in `docs/reconciliation.md`. **ROUND + VIEWED** = a screenshot I opened and looked at; other screenshots were generated but **not individually inspected**. **NOT INSPECTED** = part of the branch before this round, or a deleted legacy file: no line-level review. For those, the only evidence is the package suites and CI, which do not prove them correct. **AUTHORED** = a document or script written after `5676a6a` that has no test and was not inspected by anyone but its author.

## Summary by area

| Area | Entries | ROUND | ROUND + VIEWED | NOT INSPECTED |
|---|---|---|---|---|
| (root) | 11 | 1 | 0 | 10 |
| .claude | 1 | 0 | 0 | 1 |
| .github | 2 | 1 | 0 | 1 |
| .streamlit | 1 | 0 | 0 | 1 |
| atlas | 43 | 12 | 0 | 31 |
| design | 3 | 1 | 0 | 2 |
| docs | 35 | 22 | 6 | 7 |
| finance | 100 | 18 | 0 | 82 |
| images | 77 | 6 | 0 | 71 |
| kit | 36 | 18 | 0 | 18 |
| library | 95 | 23 | 0 | 72 |
| scripts | 28 | 3 | 0 | 25 |
| src | 46 | 0 | 0 | 46 |
| tests | 30 | 0 | 0 | 30 |
| added after `5676a6a` (AUTHORED, no test) | 4 | 0 | 0 | 0 |
| added after `80562da`: 9 screenshots opened and looked at (VIEWED); 19 tests, fixtures, code and screenshots not opened (AUTHORED, listed as such) | 29 | 0 | 9 | 0 |
| **all** | **541** | **105** | **15** | **397** (+24 AUTHORED: 4 + 20) |

## Every entry

| Status | File | Coverage |
|---|---|---|
| D | `.claude/settings.json` | NOT INSPECTED |
| A | `.dockerignore` | NOT INSPECTED |
| M | `.github/dependabot.yml` | NOT INSPECTED |
| M | `.github/workflows/ci.yml` | ROUND |
| M | `.gitignore` | NOT INSPECTED |
| D | `.streamlit/config.toml` | NOT INSPECTED |
| D | `CHANGELOG.md` | NOT INSPECTED |
| D | `CONTRIBUTING.md` | NOT INSPECTED |
| D | `Dockerfile.aperture` | NOT INSPECTED |
| D | `Makefile` | NOT INSPECTED |
| M | `README.md` | NOT INSPECTED |
| R | `atlas/.prettierrc` (from `.prettierrc`) | NOT INSPECTED |
| A | `atlas/Dockerfile` | NOT INSPECTED |
| A | `atlas/README.md` | NOT INSPECTED |
| A | `atlas/docker-compose.yml` | NOT INSPECTED |
| A | `atlas/down.sh` | NOT INSPECTED |
| R | `atlas/eslint.config.js` (from `eslint.config.js`) | NOT INSPECTED |
| A | `atlas/eval/cases.json` | NOT INSPECTED |
| A | `atlas/modules.d/calendar.json` | NOT INSPECTED |
| A | `atlas/modules.d/documents.json` | NOT INSPECTED |
| A | `atlas/modules.d/finance.json` | ROUND |
| A | `atlas/modules.d/health.json` | NOT INSPECTED |
| A | `atlas/modules.d/photos.json` | ROUND |
| A | `atlas/modules.d/travel.json` | NOT INSPECTED |
| A | `atlas/pyproject.toml` | ROUND |
| A | `atlas/src/atlas/__init__.py` | NOT INSPECTED |
| A | `atlas/src/atlas/__main__.py` | NOT INSPECTED |
| A | `atlas/src/atlas/assistant.py` | ROUND |
| A | `atlas/src/atlas/crosscheck.py` | NOT INSPECTED |
| A | `atlas/src/atlas/dots.py` | NOT INSPECTED |
| A | `atlas/src/atlas/evaluate.py` | NOT INSPECTED |
| A | `atlas/src/atlas/proxy.py` | NOT INSPECTED |
| A | `atlas/src/atlas/registry.py` | ROUND |
| A | `atlas/src/atlas/server.py` | NOT INSPECTED |
| A | `atlas/src/atlas/static/atlas.css` | NOT INSPECTED |
| A | `atlas/src/atlas/static/atlas.js` | NOT INSPECTED |
| A | `atlas/src/atlas/static/common.js` | NOT INSPECTED |
| A | `atlas/src/atlas/static/design.css` | ROUND |
| A | `atlas/src/atlas/static/icon.svg` | NOT INSPECTED |
| A | `atlas/src/atlas/static/index.html` | NOT INSPECTED |
| A | `atlas/src/atlas/upstream.py` | ROUND |
| A | `atlas/tests/conftest.py` | ROUND |
| A | `atlas/tests/fake_app.py` | ROUND |
| A | `atlas/tests/test_assistant.py` | NOT INSPECTED |
| A | `atlas/tests/test_assistant_safety.py` | ROUND |
| A | `atlas/tests/test_crosscheck.py` | NOT INSPECTED |
| A | `atlas/tests/test_dots.py` | NOT INSPECTED |
| A | `atlas/tests/test_evaluate.py` | NOT INSPECTED |
| A | `atlas/tests/test_proxy.py` | NOT INSPECTED |
| A | `atlas/tests/test_registry.py` | NOT INSPECTED |
| A | `atlas/tests/test_scan_status.py` | ROUND |
| A | `atlas/tests/test_server.py` | NOT INSPECTED |
| A | `atlas/tests/test_update_script.py` | ROUND |
| A | `atlas/up.sh` | NOT INSPECTED |
| A | `design/.prettierrc` | NOT INSPECTED |
| A | `design/common.js` | NOT INSPECTED |
| A | `design/design.css` | ROUND |
| D | `docker-compose.aperture.yml` | NOT INSPECTED |
| A | `docs/README.md` | ROUND |
| A | `docs/REVIEW_PROMPT.md` | NOT INSPECTED |
| A | `docs/RE_REVIEW_PROMPT.md` | ROUND |
| D | `docs/adr/0001-sqlite-fts5.md` | NOT INSPECTED |
| D | `docs/adr/0002-plan-based-agent.md` | NOT INSPECTED |
| D | `docs/agent.md` | NOT INSPECTED |
| M | `docs/architecture.md` | NOT INSPECTED |
| A | `docs/coverage-matrix.md` | ROUND |
| A | `docs/data-locations.md` | ROUND |
| A | `docs/decisions.md` | ROUND |
| A | `docs/defects.md` | ROUND |
| A | `docs/design.md` | ROUND |
| D | `docs/docker.md` | NOT INSPECTED |
| A | `docs/reconciliation.md` | ROUND |
| A | `docs/requirements.md` | ROUND |
| A | `docs/reviews.md` | ROUND |
| D | `docs/safety.md` | NOT INSPECTED |
| A | `docs/screenshots/01-overview-dark.png` | ROUND |
| A | `docs/screenshots/01-overview-phone.png` | ROUND |
| A | `docs/screenshots/01-overview.png` | ROUND |
| A | `docs/screenshots/02-finance-dashboard-dark.png` | ROUND + VIEWED |
| A | `docs/screenshots/02-finance-dashboard-phone.png` | ROUND |
| A | `docs/screenshots/02-finance-dashboard.png` | ROUND + VIEWED |
| A | `docs/screenshots/02b-finance-dashboard-scrolled.png` | ROUND |
| A | `docs/screenshots/03-health-dark.png` | ROUND |
| A | `docs/screenshots/03-health-phone.png` | ROUND |
| A | `docs/screenshots/03-health.png` | ROUND + VIEWED |
| A | `docs/screenshots/04-travel.png` | ROUND + VIEWED |
| A | `docs/screenshots/05-photos.png` | ROUND |
| A | `docs/screenshots/06-calendar.png` | ROUND |
| A | `docs/screenshots/08-finance-first-run-empty.png` | ROUND + VIEWED |
| A | `docs/screenshots/09-finance-documents-with-date-source.png` | ROUND + VIEWED |
| A | `docs/security-deployment-review.md` | ROUND |
| A | `docs/testing.md` | ROUND |
| A | `docs/ui-review.md` | ROUND |
| A | `down.sh` | NOT INSPECTED |
| A | `finance/.dockerignore` | NOT INSPECTED |
| A | `finance/.gitignore` | NOT INSPECTED |
| A | `finance/.prettierrc` | NOT INSPECTED |
| A | `finance/Dockerfile` | NOT INSPECTED |
| A | `finance/README.md` | NOT INSPECTED |
| A | `finance/docker-compose.yml` | NOT INSPECTED |
| A | `finance/eslint.config.js` | NOT INSPECTED |
| A | `finance/pyproject.toml` | ROUND |
| A | `finance/scripts/backup.sh` | NOT INSPECTED |
| A | `finance/scripts/down.sh` | NOT INSPECTED |
| A | `finance/scripts/fetch-rates.sh` | NOT INSPECTED |
| A | `finance/scripts/free-space.sh` | NOT INSPECTED |
| A | `finance/scripts/up.sh` | NOT INSPECTED |
| A | `finance/src/finance/__init__.py` | NOT INSPECTED |
| A | `finance/src/finance/answers.py` | NOT INSPECTED |
| A | `finance/src/finance/applenotes.py` | NOT INSPECTED |
| A | `finance/src/finance/audit.py` | ROUND |
| A | `finance/src/finance/backup.py` | NOT INSPECTED |
| A | `finance/src/finance/browse.py` | ROUND |
| A | `finance/src/finance/canary.py` | NOT INSPECTED |
| A | `finance/src/finance/categories.json` | NOT INSPECTED |
| A | `finance/src/finance/categorize.py` | NOT INSPECTED |
| A | `finance/src/finance/changes.py` | ROUND |
| A | `finance/src/finance/cli.py` | ROUND |
| A | `finance/src/finance/clock.py` | NOT INSPECTED |
| A | `finance/src/finance/concepts.json` | NOT INSPECTED |
| A | `finance/src/finance/concepts.py` | NOT INSPECTED |
| A | `finance/src/finance/currency.py` | NOT INSPECTED |
| A | `finance/src/finance/dates.py` | NOT INSPECTED |
| A | `finance/src/finance/db.py` | NOT INSPECTED |
| A | `finance/src/finance/findings.py` | NOT INSPECTED |
| A | `finance/src/finance/insight.py` | NOT INSPECTED |
| A | `finance/src/finance/library_client.py` | NOT INSPECTED |
| A | `finance/src/finance/modules/__init__.py` | NOT INSPECTED |
| A | `finance/src/finance/modules/clock.py` | NOT INSPECTED |
| A | `finance/src/finance/modules/documents.py` | NOT INSPECTED |
| A | `finance/src/finance/modules/events.py` | NOT INSPECTED |
| A | `finance/src/finance/modules/money.py` | ROUND |
| A | `finance/src/finance/modules/notes.py` | NOT INSPECTED |
| A | `finance/src/finance/modules/people.py` | NOT INSPECTED |
| A | `finance/src/finance/modules/reports.py` | NOT INSPECTED |
| A | `finance/src/finance/modules/statement_import.py` | ROUND |
| A | `finance/src/finance/modules/tasks.py` | NOT INSPECTED |
| A | `finance/src/finance/modules/today.py` | NOT INSPECTED |
| A | `finance/src/finance/notes_check.py` | NOT INSPECTED |
| A | `finance/src/finance/payslips.py` | ROUND |
| A | `finance/src/finance/planning.py` | ROUND |
| A | `finance/src/finance/proof.py` | NOT INSPECTED |
| A | `finance/src/finance/rates.py` | NOT INSPECTED |
| A | `finance/src/finance/report.py` | NOT INSPECTED |
| A | `finance/src/finance/standards.py` | NOT INSPECTED |
| A | `finance/src/finance/statements.py` | NOT INSPECTED |
| A | `finance/src/finance/static/app.css` | ROUND |
| A | `finance/src/finance/static/app.js` | ROUND |
| A | `finance/src/finance/static/common.js` | NOT INSPECTED |
| A | `finance/src/finance/static/design.css` | ROUND |
| A | `finance/src/finance/static/icon.svg` | NOT INSPECTED |
| A | `finance/src/finance/static/index.html` | NOT INSPECTED |
| A | `finance/src/finance/tables.py` | NOT INSPECTED |
| A | `finance/src/finance/tagging.py` | NOT INSPECTED |
| A | `finance/src/finance/tags.json` | NOT INSPECTED |
| A | `finance/src/finance/toolrun.py` | ROUND |
| A | `finance/src/finance/verify.py` | NOT INSPECTED |
| A | `finance/src/finance/wealth.py` | ROUND |
| A | `finance/src/finance/web.py` | ROUND |
| R | `finance/tests/__init__.py` (from `src/aperture/agent/__init__.py`) | NOT INSPECTED |
| A | `finance/tests/conftest.py` | NOT INSPECTED |
| A | `finance/tests/test_answers.py` | NOT INSPECTED |
| A | `finance/tests/test_applenotes.py` | NOT INSPECTED |
| A | `finance/tests/test_assistant_changes.py` | ROUND |
| A | `finance/tests/test_backup_tasks_people.py` | NOT INSPECTED |
| A | `finance/tests/test_browse.py` | NOT INSPECTED |
| A | `finance/tests/test_data_boundary.py` | NOT INSPECTED |
| A | `finance/tests/test_docker_files.py` | NOT INSPECTED |
| A | `finance/tests/test_encryption.py` | NOT INSPECTED |
| A | `finance/tests/test_events.py` | NOT INSPECTED |
| A | `finance/tests/test_fail_fast.py` | NOT INSPECTED |
| A | `finance/tests/test_finance.py` | NOT INSPECTED |
| A | `finance/tests/test_fuzz.py` | NOT INSPECTED |
| A | `finance/tests/test_insight.py` | NOT INSPECTED |
| A | `finance/tests/test_llm_and_tagging.py` | NOT INSPECTED |
| A | `finance/tests/test_migrations.py` | NOT INSPECTED |
| A | `finance/tests/test_modules.py` | NOT INSPECTED |
| A | `finance/tests/test_money_exact.py` | ROUND |
| A | `finance/tests/test_notes_check.py` | NOT INSPECTED |
| A | `finance/tests/test_parse_table_flow.py` | NOT INSPECTED |
| A | `finance/tests/test_planning.py` | NOT INSPECTED |
| A | `finance/tests/test_privacy.py` | NOT INSPECTED |
| A | `finance/tests/test_proof.py` | NOT INSPECTED |
| A | `finance/tests/test_rates.py` | NOT INSPECTED |
| A | `finance/tests/test_secure_by_default.py` | NOT INSPECTED |
| A | `finance/tests/test_standards.py` | NOT INSPECTED |
| A | `finance/tests/test_structure.py` | NOT INSPECTED |
| A | `finance/tests/test_tally.py` | NOT INSPECTED |
| A | `finance/tests/test_toolrun.py` | NOT INSPECTED |
| A | `finance/tests/test_trip_facts.py` | NOT INSPECTED |
| A | `finance/tests/test_truncation_audit.py` | ROUND |
| A | `finance/tests/test_verify.py` | NOT INSPECTED |
| A | `finance/tests/test_wealth_tax_bills.py` | NOT INSPECTED |
| A | `finance/tests/test_web.py` | NOT INSPECTED |
| A | `images/README.md` | ROUND |
| R | `images/pyproject.toml` (from `pyproject.toml`) | ROUND |
| A | `images/src/images/__init__.py` | NOT INSPECTED |
| R | `images/src/images/albums.py` (from `src/aperture/albums.py`) | NOT INSPECTED |
| R | `images/src/images/browse.py` (from `src/aperture/web/browse.py`) | NOT INSPECTED |
| R | `images/src/images/colors.py` (from `src/aperture/colors.py`) | NOT INSPECTED |
| R | `images/src/images/config.py` (from `src/aperture/config.py`) | NOT INSPECTED |
| R | `images/src/images/data/__init__.py` (from `src/aperture/data/__init__.py`) | NOT INSPECTED |
| R | `images/src/images/data/tag_vocabulary.txt` (from `src/aperture/data/tag_vocabulary.txt`) | NOT INSPECTED |
| R | `images/src/images/db.py` (from `src/aperture/db.py`) | ROUND |
| A | `images/src/images/engine.py` | NOT INSPECTED |
| R | `images/src/images/export.py` (from `src/aperture/export.py`) | NOT INSPECTED |
| R | `images/src/images/indexing/__init__.py` (from `src/aperture/indexing/__init__.py`) | NOT INSPECTED |
| R | `images/src/images/indexing/deepmeta.py` (from `src/aperture/indexing/deepmeta.py`) | NOT INSPECTED |
| R | `images/src/images/indexing/derive.py` (from `src/aperture/indexing/derive.py`) | NOT INSPECTED |
| R | `images/src/images/indexing/details.py` (from `src/aperture/indexing/details.py`) | NOT INSPECTED |
| R | `images/src/images/indexing/discovery.py` (from `src/aperture/indexing/discovery.py`) | NOT INSPECTED |
| R | `images/src/images/indexing/faceages.py` (from `src/aperture/indexing/faceages.py`) | NOT INSPECTED |
| R | `images/src/images/indexing/faceattrs.py` (from `src/aperture/indexing/faceattrs.py`) | NOT INSPECTED |
| R | `images/src/images/indexing/judge.py` (from `src/aperture/indexing/judge.py`) | ROUND |
| R | `images/src/images/indexing/loaders.py` (from `src/aperture/indexing/loaders.py`) | NOT INSPECTED |
| R | `images/src/images/indexing/pipeline.py` (from `src/aperture/indexing/pipeline.py`) | NOT INSPECTED |
| R | `images/src/images/indexing/placemodel.py` (from `src/aperture/indexing/placemodel.py`) | NOT INSPECTED |
| R | `images/src/images/indexing/placereport.py` (from `src/aperture/indexing/placereport.py`) | NOT INSPECTED |
| R | `images/src/images/indexing/progress.py` (from `src/aperture/indexing/progress.py`) | NOT INSPECTED |
| R | `images/src/images/indexing/runner.py` (from `src/aperture/indexing/runner.py`) | NOT INSPECTED |
| R | `images/src/images/indexing/venues.py` (from `src/aperture/indexing/venues.py`) | NOT INSPECTED |
| R | `images/src/images/jsonutil.py` (from `src/aperture/agent/jsonutil.py`) | NOT INSPECTED |
| R | `images/src/images/library.py` (from `src/aperture/library.py`) | NOT INSPECTED |
| R | `images/src/images/ml/__init__.py` (from `src/aperture/ml/__init__.py`) | NOT INSPECTED |
| A | `images/src/images/ml/age.py` | NOT INSPECTED |
| R | `images/src/images/ml/clip.py` (from `src/aperture/ml/clip.py`) | NOT INSPECTED |
| R | `images/src/images/ml/faces.py` (from `src/aperture/ml/faces.py`) | NOT INSPECTED |
| A | `images/src/images/ml/fetch.py` | NOT INSPECTED |
| R | `images/src/images/ml/ocr.py` (from `src/aperture/ml/ocr.py`) | NOT INSPECTED |
| R | `images/src/images/ml/protocols.py` (from `src/aperture/ml/protocols.py`) | NOT INSPECTED |
| R | `images/src/images/ml/vision_details.py` (from `src/aperture/ml/vision_details.py`) | NOT INSPECTED |
| R | `images/src/images/models.py` (from `src/aperture/models.py`) | NOT INSPECTED |
| R | `images/src/images/organize.py` (from `src/aperture/organize.py`) | NOT INSPECTED |
| R | `images/src/images/people/__init__.py` (from `src/aperture/people/__init__.py`) | NOT INSPECTED |
| R | `images/src/images/people/clustering.py` (from `src/aperture/people/clustering.py`) | NOT INSPECTED |
| A | `images/src/images/people/repository.py` | NOT INSPECTED |
| R | `images/src/images/quality.py` (from `src/aperture/quality.py`) | ROUND |
| R | `images/src/images/safety.py` (from `src/aperture/safety.py`) | NOT INSPECTED |
| R | `images/src/images/search/__init__.py` (from `src/aperture/search/__init__.py`) | NOT INSPECTED |
| R | `images/src/images/search/dates.py` (from `src/aperture/search/dates.py`) | NOT INSPECTED |
| R | `images/src/images/search/embeddings.py` (from `src/aperture/search/embeddings.py`) | NOT INSPECTED |
| R | `images/src/images/search/executor.py` (from `src/aperture/agent/executor.py`) | NOT INSPECTED |
| R | `images/src/images/search/filters.py` (from `src/aperture/search/filters.py`) | NOT INSPECTED |
| R | `images/src/images/search/geo.py` (from `src/aperture/search/geo.py`) | NOT INSPECTED |
| R | `images/src/images/search/metadata.py` (from `src/aperture/search/metadata.py`) | NOT INSPECTED |
| A | `images/src/images/search/plan.py` | NOT INSPECTED |
| R | `images/src/images/search/quick.py` (from `src/aperture/search/quick.py`) | NOT INSPECTED |
| R | `images/src/images/search/replica.py` (from `src/aperture/search/replica.py`) | NOT INSPECTED |
| R | `images/src/images/search/text.py` (from `src/aperture/search/text.py`) | NOT INSPECTED |
| R | `images/src/images/search/textnorm.py` (from `src/aperture/search/textnorm.py`) | NOT INSPECTED |
| R | `images/src/images/search/visual.py` (from `src/aperture/search/visual.py`) | NOT INSPECTED |
| R | `images/src/images/similar.py` (from `src/aperture/similar.py`) | NOT INSPECTED |
| R | `images/tests/conftest.py` (from `tests/conftest.py`) | NOT INSPECTED |
| R | `images/tests/test_albums.py` (from `tests/test_albums.py`) | NOT INSPECTED |
| R | `images/tests/test_colors.py` (from `tests/test_colors.py`) | NOT INSPECTED |
| R | `images/tests/test_config.py` (from `tests/test_config.py`) | NOT INSPECTED |
| R | `images/tests/test_deepmeta.py` (from `tests/test_deepmeta.py`) | NOT INSPECTED |
| R | `images/tests/test_derive.py` (from `tests/test_derive.py`) | NOT INSPECTED |
| R | `images/tests/test_details.py` (from `tests/test_details.py`) | NOT INSPECTED |
| A | `images/tests/test_engine.py` | ROUND |
| R | `images/tests/test_faceages.py` (from `tests/test_faceages.py`) | NOT INSPECTED |
| R | `images/tests/test_faceattrs.py` (from `tests/test_faceattrs.py`) | NOT INSPECTED |
| A | `images/tests/test_highlights.py` | NOT INSPECTED |
| R | `images/tests/test_judge.py` (from `tests/test_judge.py`) | NOT INSPECTED |
| R | `images/tests/test_ocr_engines.py` (from `tests/test_ocr_engines.py`) | NOT INSPECTED |
| R | `images/tests/test_organize.py` (from `tests/test_organize.py`) | NOT INSPECTED |
| R | `images/tests/test_placemodel.py` (from `tests/test_placemodel.py`) | NOT INSPECTED |
| R | `images/tests/test_quality.py` (from `tests/test_quality.py`) | NOT INSPECTED |
| R | `images/tests/test_quick.py` (from `tests/test_quick.py`) | NOT INSPECTED |
| R | `images/tests/test_safety_export.py` (from `tests/test_safety_export.py`) | NOT INSPECTED |
| R | `images/tests/test_vision_collect.py` (from `tests/test_vision_collect.py`) | NOT INSPECTED |
| A | `kit/pyproject.toml` | ROUND |
| A | `kit/src/kit/__init__.py` | NOT INSPECTED |
| A | `kit/src/kit/amounts.py` | NOT INSPECTED |
| A | `kit/src/kit/audit.py` | NOT INSPECTED |
| A | `kit/src/kit/cleanup.py` | ROUND |
| A | `kit/src/kit/concepts.py` | NOT INSPECTED |
| A | `kit/src/kit/config.py` | ROUND |
| A | `kit/src/kit/consent.py` | ROUND |
| A | `kit/src/kit/currencies.json` | ROUND |
| A | `kit/src/kit/db.py` | ROUND |
| A | `kit/src/kit/extract.py` | ROUND |
| A | `kit/src/kit/groups.py` | NOT INSPECTED |
| A | `kit/src/kit/http.py` | NOT INSPECTED |
| A | `kit/src/kit/llm.py` | ROUND |
| A | `kit/src/kit/log.py` | ROUND |
| A | `kit/src/kit/module.py` | NOT INSPECTED |
| A | `kit/src/kit/money.py` | ROUND |
| A | `kit/src/kit/netguard.py` | NOT INSPECTED |
| A | `kit/src/kit/rag.py` | NOT INSPECTED |
| A | `kit/src/kit/sign.py` | NOT INSPECTED |
| A | `kit/src/kit/text.py` | ROUND |
| A | `kit/src/kit/units.py` | NOT INSPECTED |
| A | `kit/tests/test_architecture.py` | NOT INSPECTED |
| A | `kit/tests/test_call_local.py` | NOT INSPECTED |
| A | `kit/tests/test_common_helpers.py` | NOT INSPECTED |
| A | `kit/tests/test_concepts.py` | NOT INSPECTED |
| A | `kit/tests/test_config.py` | ROUND |
| A | `kit/tests/test_consent.py` | ROUND |
| A | `kit/tests/test_db_cleanup.py` | ROUND |
| A | `kit/tests/test_db_crash_points.py` | ROUND |
| A | `kit/tests/test_db_safety.py` | ROUND |
| A | `kit/tests/test_design.py` | ROUND |
| A | `kit/tests/test_extract_whole_document.py` | ROUND |
| A | `kit/tests/test_kit.py` | NOT INSPECTED |
| A | `kit/tests/test_llm_calls.py` | NOT INSPECTED |
| A | `kit/tests/test_names.py` | NOT INSPECTED |
| A | `library/.prettierrc` | NOT INSPECTED |
| A | `library/Dockerfile` | NOT INSPECTED |
| A | `library/README.md` | NOT INSPECTED |
| A | `library/docker-compose.mail.yml` | NOT INSPECTED |
| A | `library/docker-compose.ocr.yml` | NOT INSPECTED |
| A | `library/docker-compose.pictures.yml` | NOT INSPECTED |
| A | `library/docker-compose.yml` | NOT INSPECTED |
| A | `library/eslint.config.js` | NOT INSPECTED |
| A | `library/pyproject.toml` | ROUND |
| A | `library/scripts/adopt-picture-index.sh` | NOT INSPECTED |
| A | `library/scripts/apple-ocr.sh` | NOT INSPECTED |
| A | `library/scripts/atlas-ocr.sb` | NOT INSPECTED |
| A | `library/scripts/atlas-ocr.swift` | NOT INSPECTED |
| A | `library/scripts/down.sh` | NOT INSPECTED |
| A | `library/scripts/up.sh` | NOT INSPECTED |
| A | `library/src/library/__init__.py` | NOT INSPECTED |
| A | `library/src/library/applemail.py` | NOT INSPECTED |
| A | `library/src/library/apps.json` | NOT INSPECTED |
| A | `library/src/library/apps.py` | NOT INSPECTED |
| A | `library/src/library/appstate.py` | ROUND |
| A | `library/src/library/batch.py` | ROUND |
| A | `library/src/library/bulkmail.py` | NOT INSPECTED |
| A | `library/src/library/casebook.py` | NOT INSPECTED |
| A | `library/src/library/changes.py` | NOT INSPECTED |
| A | `library/src/library/cli.py` | NOT INSPECTED |
| A | `library/src/library/concepts.json` | NOT INSPECTED |
| A | `library/src/library/concepts.py` | NOT INSPECTED |
| A | `library/src/library/control.py` | NOT INSPECTED |
| A | `library/src/library/extraction.py` | ROUND |
| A | `library/src/library/filing.py` | NOT INSPECTED |
| A | `library/src/library/flags.py` | NOT INSPECTED |
| A | `library/src/library/healthdata.py` | ROUND |
| A | `library/src/library/highlights.py` | NOT INSPECTED |
| A | `library/src/library/indexer.py` | NOT INSPECTED |
| A | `library/src/library/items.py` | NOT INSPECTED |
| A | `library/src/library/judging.py` | ROUND |
| A | `library/src/library/limits.json` | ROUND |
| A | `library/src/library/limits.py` | ROUND |
| A | `library/src/library/mailboxes.json` | NOT INSPECTED |
| A | `library/src/library/mailread.py` | NOT INSPECTED |
| A | `library/src/library/parser.py` | NOT INSPECTED |
| A | `library/src/library/pictures.py` | NOT INSPECTED |
| A | `library/src/library/priority.py` | NOT INSPECTED |
| A | `library/src/library/readers.py` | ROUND |
| A | `library/src/library/reading.py` | NOT INSPECTED |
| A | `library/src/library/readreport.py` | NOT INSPECTED |
| A | `library/src/library/recognise.py` | NOT INSPECTED |
| A | `library/src/library/relevance.py` | NOT INSPECTED |
| A | `library/src/library/rounds.py` | NOT INSPECTED |
| A | `library/src/library/scanstatus.py` | NOT INSPECTED |
| A | `library/src/library/selfcheck.py` | NOT INSPECTED |
| A | `library/src/library/sniff.py` | ROUND |
| A | `library/src/library/static/.prettierrc` | NOT INSPECTED |
| A | `library/src/library/static/app.css` | ROUND |
| A | `library/src/library/static/app.js` | NOT INSPECTED |
| A | `library/src/library/static/changes.js` | NOT INSPECTED |
| A | `library/src/library/static/common.js` | NOT INSPECTED |
| A | `library/src/library/static/design.css` | ROUND |
| A | `library/src/library/static/healthtravel.js` | ROUND |
| A | `library/src/library/static/icon.svg` | NOT INSPECTED |
| A | `library/src/library/static/index.html` | NOT INSPECTED |
| A | `library/src/library/static/pictures.js` | NOT INSPECTED |
| A | `library/src/library/store.py` | ROUND |
| A | `library/src/library/tools.py` | NOT INSPECTED |
| A | `library/src/library/trace.py` | NOT INSPECTED |
| A | `library/src/library/travel.py` | NOT INSPECTED |
| A | `library/src/library/tripdocs.py` | NOT INSPECTED |
| A | `library/src/library/web.py` | ROUND |
| R | `library/tests/__init__.py` (from `src/aperture/ui/__init__.py`) | NOT INSPECTED |
| A | `library/tests/conftest.py` | NOT INSPECTED |
| A | `library/tests/marks.py` | NOT INSPECTED |
| A | `library/tests/migration_hashes.json` | ROUND |
| A | `library/tests/test_apple_ocr.py` | NOT INSPECTED |
| A | `library/tests/test_applemail.py` | NOT INSPECTED |
| A | `library/tests/test_cards_and_forget.py` | NOT INSPECTED |
| A | `library/tests/test_casebook.py` | NOT INSPECTED |
| A | `library/tests/test_changes.py` | NOT INSPECTED |
| A | `library/tests/test_docker_files.py` | ROUND |
| A | `library/tests/test_engines.py` | NOT INSPECTED |
| A | `library/tests/test_handover.py` | ROUND |
| A | `library/tests/test_health_travel.py` | ROUND |
| A | `library/tests/test_judging.py` | NOT INSPECTED |
| A | `library/tests/test_limits_config.py` | ROUND |
| A | `library/tests/test_mail.py` | NOT INSPECTED |
| A | `library/tests/test_migrations_frozen.py` | ROUND |
| A | `library/tests/test_order.py` | ROUND |
| A | `library/tests/test_parser_documents.py` | NOT INSPECTED |
| A | `library/tests/test_pictures.py` | NOT INSPECTED |
| A | `library/tests/test_pipeline.py` | NOT INSPECTED |
| A | `library/tests/test_readers.py` | NOT INSPECTED |
| A | `library/tests/test_readers_mail_attachments.py` | NOT INSPECTED |
| A | `library/tests/test_search.py` | NOT INSPECTED |
| A | `library/tests/test_selfcheck.py` | NOT INSPECTED |
| A | `library/tests/test_web.py` | ROUND |
| A | `library/tests/test_whole_read.py` | NOT INSPECTED |
| A | `scripts/add-folder.sh` | NOT INSPECTED |
| D | `scripts/aperture-docker-migrate.sh` | NOT INSPECTED |
| D | `scripts/aperture-run.sh` | NOT INSPECTED |
| D | `scripts/aperture-sandbox.sb` | NOT INSPECTED |
| D | `scripts/aperture-sandboxed.sh` | NOT INSPECTED |
| D | `scripts/aperture-vault.sh` | NOT INSPECTED |
| A | `scripts/auto-read.sh` | NOT INSPECTED |
| D | `scripts/bench-models.py` | NOT INSPECTED |
| D | `scripts/bench-recognition.py` | NOT INSPECTED |
| A | `scripts/check-pages.js` | ROUND |
| D | `scripts/check.sh` | NOT INSPECTED |
| D | `scripts/down.sh` | NOT INSPECTED |
| A | `scripts/folders-compose.sh` | NOT INSPECTED |
| A | `scripts/folders.sh` | NOT INSPECTED |
| A | `scripts/install-auto-read.sh` | NOT INSPECTED |
| A | `scripts/install-autostart.sh` | NOT INSPECTED |
| D | `scripts/install.sh` | NOT INSPECTED |
| A | `scripts/make-apps.sh` | NOT INSPECTED |
| A | `scripts/migration-hashes.py` | ROUND |
| A | `scripts/platform-key.sh` | NOT INSPECTED |
| A | `scripts/remind.py` | NOT INSPECTED |
| A | `scripts/scale-check.py` | NOT INSPECTED |
| A | `scripts/start-at-login.sh` | NOT INSPECTED |
| A | `scripts/sync-design.sh` | NOT INSPECTED |
| D | `scripts/tune-ollama-mac.sh` | NOT INSPECTED |
| A | `scripts/uninstall-autostart.sh` | NOT INSPECTED |
| D | `scripts/up.sh` | NOT INSPECTED |
| A | `scripts/update-code.sh` | ROUND |
| D | `src/aperture/__init__.py` | NOT INSPECTED |
| D | `src/aperture/__main__.py` | NOT INSPECTED |
| D | `src/aperture/agent/captions.py` | NOT INSPECTED |
| D | `src/aperture/agent/knowledge.py` | NOT INSPECTED |
| D | `src/aperture/agent/llm.py` | NOT INSPECTED |
| D | `src/aperture/agent/loop.py` | NOT INSPECTED |
| D | `src/aperture/agent/phrasebook.py` | NOT INSPECTED |
| D | `src/aperture/agent/planner.py` | NOT INSPECTED |
| D | `src/aperture/agent/progress.py` | NOT INSPECTED |
| D | `src/aperture/agent/schema.py` | NOT INSPECTED |
| D | `src/aperture/agent/service.py` | NOT INSPECTED |
| D | `src/aperture/agent/toolagent.py` | NOT INSPECTED |
| D | `src/aperture/agent_parts.py` | NOT INSPECTED |
| D | `src/aperture/bootstrap.py` | NOT INSPECTED |
| D | `src/aperture/cli.py` | NOT INSPECTED |
| D | `src/aperture/diagnostics.py` | NOT INSPECTED |
| D | `src/aperture/eval_data/plan_cases.json` | NOT INSPECTED |
| D | `src/aperture/eval_data/route_cases.json` | NOT INSPECTED |
| D | `src/aperture/evaluation.py` | NOT INSPECTED |
| D | `src/aperture/icon.py` | NOT INSPECTED |
| D | `src/aperture/launcher.py` | NOT INSPECTED |
| D | `src/aperture/ml/age.py` | NOT INSPECTED |
| D | `src/aperture/ml/fetch.py` | NOT INSPECTED |
| D | `src/aperture/paging.py` | NOT INSPECTED |
| D | `src/aperture/people/repository.py` | NOT INSPECTED |
| D | `src/aperture/py.typed` | NOT INSPECTED |
| D | `src/aperture/ui/app.py` | NOT INSPECTED |
| D | `src/aperture/ui/assets/logo.svg` | NOT INSPECTED |
| D | `src/aperture/ui/components.py` | NOT INSPECTED |
| D | `src/aperture/ui/state.py` | NOT INSPECTED |
| D | `src/aperture/ui/suggestions.py` | NOT INSPECTED |
| D | `src/aperture/ui/theme.py` | NOT INSPECTED |
| D | `src/aperture/ui/views/__init__.py` | NOT INSPECTED |
| D | `src/aperture/ui/views/chat.py` | NOT INSPECTED |
| D | `src/aperture/ui/views/defects.py` | NOT INSPECTED |
| D | `src/aperture/ui/views/library.py` | NOT INSPECTED |
| D | `src/aperture/ui/views/onboarding.py` | NOT INSPECTED |
| D | `src/aperture/ui/views/organize.py` | NOT INSPECTED |
| D | `src/aperture/ui/views/people.py` | NOT INSPECTED |
| D | `src/aperture/ui/views/settings.py` | NOT INSPECTED |
| D | `src/aperture/ui/views/status.py` | NOT INSPECTED |
| D | `src/aperture/web/__init__.py` | NOT INSPECTED |
| D | `src/aperture/web/server.py` | NOT INSPECTED |
| D | `src/aperture/web/static/app.css` | NOT INSPECTED |
| D | `src/aperture/web/static/app.js` | NOT INSPECTED |
| D | `src/aperture/web/static/index.html` | NOT INSPECTED |
| D | `tests/__init__.py` | NOT INSPECTED |
| D | `tests/test_agent.py` | NOT INSPECTED |
| D | `tests/test_bench_recognition.py` | NOT INSPECTED |
| D | `tests/test_bench_script.py` | NOT INSPECTED |
| D | `tests/test_captions.py` | NOT INSPECTED |
| D | `tests/test_check_command.py` | NOT INSPECTED |
| D | `tests/test_docker_files.py` | NOT INSPECTED |
| D | `tests/test_evaluation.py` | NOT INSPECTED |
| D | `tests/test_fake_ollama.py` | NOT INSPECTED |
| D | `tests/test_filters.py` | NOT INSPECTED |
| D | `tests/test_knowledge.py` | NOT INSPECTED |
| D | `tests/test_launcher_ollama.py` | NOT INSPECTED |
| D | `tests/test_light_and_fast.py` | NOT INSPECTED |
| D | `tests/test_loop.py` | NOT INSPECTED |
| D | `tests/test_normal_chat.py` | NOT INSPECTED |
| D | `tests/test_phrasebook.py` | NOT INSPECTED |
| D | `tests/test_plan_speed.py` | NOT INSPECTED |
| D | `tests/test_responsiveness.py` | NOT INSPECTED |
| D | `tests/test_router.py` | NOT INSPECTED |
| D | `tests/test_sandbox_files.py` | NOT INSPECTED |
| D | `tests/test_scan.py` | NOT INSPECTED |
| D | `tests/test_secure_by_default.py` | NOT INSPECTED |
| D | `tests/test_static_checks.py` | NOT INSPECTED |
| D | `tests/test_streaming.py` | NOT INSPECTED |
| D | `tests/test_toolagent.py` | NOT INSPECTED |
| D | `tests/test_ui.py` | NOT INSPECTED |
| D | `tests/test_venues.py` | NOT INSPECTED |
| D | `tests/test_web.py` | NOT INSPECTED |
| D | `tests/test_web_browse.py` | NOT INSPECTED |
| D | `tests/web_fixture.py` | NOT INSPECTED |
| A | `up.sh` | NOT INSPECTED |
| A | `update.sh` | ROUND |
| A | `docs/REVIEWER_REQUEST.md` | AUTHORED |
| A | `docs/claude-review.md` | AUTHORED |
| A | `docs/comment-tracker.md` | AUTHORED |
| A | `scripts/test-inventory.py` | AUTHORED |
| A | `atlas/tests/test_header_and_calendar_pages.py` | AUTHORED |
| A | `docs/screenshots/10-finance-f13-due-accounts-missing-dark.png` | ROUND + VIEWED |
| A | `docs/screenshots/10-finance-f13-nodue-accounts-light.png` | ROUND + VIEWED |
| A | `docs/screenshots/11-travel-hero-white-photo-dark.png` | ROUND + VIEWED |
| A | `docs/screenshots/11-travel-hero-white-photo-light.png` | ROUND + VIEWED |
| A | `docs/screenshots/12-calendar-empty-month.png` | ROUND + VIEWED |
| A | `docs/screenshots/13-header-summary-chip.png` | ROUND + VIEWED |
| A | `docs/screenshots/14-health-old-report-light.png` | ROUND + VIEWED |
| A | `docs/screenshots/15-finance-month-not-proven.png` | ROUND + VIEWED |
| A | `docs/screenshots/15-finance-month-proven.png` | AUTHORED |
| A | `finance/tests/fixtures/release-5f7fa48.sql` | AUTHORED |
| A | `finance/tests/test_dashboard_labels.py` | AUTHORED |
| A | `finance/tests/test_statement_amounts_exact.py` | AUTHORED |
| A | `finance/tests/test_upgrade_from_older_release.py` | AUTHORED |
| A | `images/tests/fixtures/release-aperture-5d3ddb5.sql` | AUTHORED |
| A | `images/tests/test_upgrade_from_released_aperture.py` | AUTHORED |
| A | `library/tests/fixtures/release-573d04f.sql` | AUTHORED |
| A | `library/tests/test_health_freshness.py` | AUTHORED |
| A | `library/tests/test_no_gradients.py` | AUTHORED |
| A | `library/tests/test_upgrade_from_older_release.py` | AUTHORED |
| A | `docs/screenshots/16-pending-change-yes-no-dark.png` | ROUND + VIEWED |
| A | `docs/screenshots/16-pending-change-yes-no-light.png` | AUTHORED |
| A | `finance/src/finance/additions.py` | AUTHORED |
| A | `finance/tests/test_undo_last_additions.py` | AUTHORED |
| A | `docs/screenshots/17-first-run-checklist-dark.png` | AUTHORED |
| A | `finance/tests/test_recovery_of_routine_writes.py` | AUTHORED |
| A | `library/src/library/seal.py` | AUTHORED |
| A | `library/tests/test_seal.py` | AUTHORED |
| A | `library/tests/test_sealed_handover.py` | AUTHORED |


---

## Original `docs/requirements.md`

# Requirements

Status as of branch `atlas` at the head of this pull request. Each requirement has an ID so that review comments can point at it (`R-F3`, `R-Q2`). "Verified by" names the test or check that proves it; "Not verified" says what only the owner's Mac can show.

## Purpose

One private personal app for one owner, running on their own Mac. It reads their files, mail, pictures, travel documents and bank statements, and answers questions about them with a local AI model. Nothing is sent to a cloud service while it runs.

## Users and context

- One owner, on one Mac (Apple silicon, 8–24 GB memory), using Docker Desktop and Ollama on the host.
- Reviewers (friends) read the code, the documents and the screenshots and comment on the pull request. They have read access only.

## Functional requirements

| ID | Requirement | Verified by |
|---|---|---|
| R-F1 | **Documents**: read files and Apple Mail, extract text (OCR for scans), keep it whole, sort each file (what it is, which app it is for, its facts), group related files. | `library/tests` (217), `test_whole_read.py` |
| R-F2 | **Finance**: import bank statements, prove every month ties to the cent, categorise payments, show income, spending, savings, investments, net worth, budgets, goals. | `finance/tests` (619) |
| R-F3 | **Health**: lab values and medicines exactly as printed, no interpretation; say when a document was read only in part. | `kit/tests/test_extract_whole_document.py`, `library/tests/test_health_travel.py` |
| R-F4 | **Travel**: trips from tickets and bookings with the dates the documents print, booked totals, calendar file. | `library/tests/test_health_travel.py` |
| R-F5 | **Pictures**: index pictures, places, people, quality; changes to pictures only after the owner confirms in a window. | `images/tests` (96), `library/tests` |
| R-F6 | **Atlas**: one address, one menu, one search box, one chat, one Update button over all apps. Atlas holds no data. | `atlas/tests` (92) |
| R-F7 | **Assistant**: answers about the owner's data by calling tools of the apps; every figure in an answer must have come from a tool. | `atlas/tests/test_assistant.py` |
| R-F8 | **Changes to money records** by the assistant are only prepared; the owner's own next message ("yes") makes them, once. | `finance/tests/test_assistant_changes.py`, `atlas/tests/test_assistant_safety.py` |
| R-F9 | **Update** is one button / one command (`./update.sh`); starting is `./up.sh`, stopping `./down.sh`; autostart at login. | scripts; not run in CI |

## Quality requirements

| ID | Requirement | Verified by |
|---|---|---|
| R-Q1 | **Numbers exactly right.** Money is whole minor units (cents); amounts are read as the decimal written and rounded once. | `finance/tests/test_money_exact.py` |
| R-Q2 | **The model does no arithmetic or logic.** Code computes and verifies; the model reads, labels and quotes. Amounts, dates, parties, entities are checked against the whole source text. | `kit/tests/test_extract*.py` |
| R-Q3 | **Private and offline.** No outbound network from the apps (guard in `kit`); the model server must be this computer or its private network. | `finance/tests/test_privacy.py`, `atlas/tests/test_assistant_safety.py` |
| R-Q4 | **Encrypted at rest** (SQLCipher); refuse to run unencrypted when encryption is required; converting a plain database leaves no plain copy unless asked. | `kit/tests/test_db_safety.py`, `finance/tests/test_secure_by_default.py` |
| R-Q5 | **No limits on what is kept.** Mail is kept whole; every limit lives in `limits.json` with effectively unlimited defaults; a cut is recorded and the file is read again when the limit changes. | `library/tests/test_limits_config.py` |
| R-Q6 | **Nothing is silently lost or half-done.** Incomplete reads say what was not read; migrations are all-or-nothing and can be retried. | `kit/tests/test_db_safety.py`, `test_extract_whole_document.py` |
| R-Q7 | **Honest and plain UI.** No code or error text on screen; one-line plain answers; WCAG 2.1 AA in both themes; keyboard focus visible. | `kit/tests/test_design.py`, `scripts/check-pages.js` (axe, light and dark) |
| R-Q8 | **No hardcoded words.** Categories, kinds, thresholds and limits are data or decided by the model. (Known exception: `kit/consent.py` word lists for the owner's own yes/delete words — see O-8.) | `kit/tests/test_architecture.py` (kind words) |
| R-Q9 | **Maintainable.** Layers enforced by test; functions ≤ 50 lines; ruff limits (args ≤ 7, branches ≤ 15, complexity ≤ 15, no magic values); mypy; prettier. | CI |
| R-Q10 | **The AI never edits its own source.** | design (read-only tools); not separately tested |

## Constraints and rules from the owner

No hardcoding; fixes must work in all scenarios; never claim fixed or verified without proof; the assistant never sees the owner's real finance data or private output; do not make unrequested changes; one-line plain answers; no printed code or error text in the UI.

## Out of scope

Cloud AI; multi-user access; mobile native apps; currencies with other than two decimals (stored in hundredths: see O-1 in `defects.md`).

## Platform

Python ≥ 3.11 (Docker images use 3.12), SQLite/SQLCipher, Ollama (`ministral-3:3b` by default; `ATLAS_MODEL` to change), Docker Desktop on macOS; Apple Vision for OCR with Tesseract as fallback.

