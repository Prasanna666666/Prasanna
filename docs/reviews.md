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
