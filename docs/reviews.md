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

## Author's own findings

D-09, D-12, D-13, D-14, D-15 in `defects.md`. The most important: D-12, every card hidden by CSS for two days, found only because the apps were finally run and photographed.

## Friends' comments (to be filled from the pull request)

| Date | Reviewer | Where (file/line or screenshot) | ID | Comment | Author's reply | Status |
|---|---|---|---|---|---|---|
| | | | | | | |
