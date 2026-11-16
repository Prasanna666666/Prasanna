# Review prompt for another AI (copy everything below the line)

---

You are a senior reviewer. Review the repository **prasanna666666/prasanna**, branch **`atlas`**, as a skeptical, evidence-first engineer. Report only what you can show (file path, line, command output). Do not praise. Do not assume claims in the docs are true: check them. If you cannot run something, say "not verified", never "fine".

## 1. What the product is
**Atlas**: one private, fully offline personal app for a single owner on a Mac (Docker Desktop + Ollama). It reads their files, mails, pictures, travel documents and bank statements, and answers questions about them. Nothing talks to a cloud service at runtime; data is encrypted at rest. Commands: `./up.sh`, `./update.sh`, `./down.sh`. UI at http://atlas.localhost:8000.

## 2. Layout and dependency rules (must be enforced, not just stated)
| Folder | Role | May import |
|---|---|---|
| `kit/` | Shared base: encrypted DB, local model client (`llm.py`), no-network guard, retrieval, `text.py`, `groups.py`, `units.py`, `extract.py`, `http.ModuleHandler`, `concepts` | nothing else |
| `images/` | Everything that understands a picture (place model, clustering, safety, judge, details) | kit |
| `library/` | "Documents": reader (parser, extraction, batch, mailread, bulkmail, control, rounds) + store, judging, healthdata, tripdocs, casebook, reading, scanstatus, appstate, web, limits | kit, images |
| `finance/` | Money: statement import, categories, tags, planning, verify, insight, reports | kit |
| `atlas/` | Front door: one menu, chat, Update button, scan status of the other apps. Holds no data | kit |
| `design/` | Shared CSS/JS (`design.css`, `common.js` exposing `window.UI`), copied into each app's static dir by `scripts/sync-design.sh` | n/a |

Apps talk to each other only over HTTP. Architecture is enforced by `kit/tests/test_architecture.py` (layer imports, no "kind words" in code, no copied function bodies, no function over 50 lines). Docs: `docs/architecture.md`, `docs/decisions.md`, `docs/adr/`.

## 3. The owner's standing rules (treat as acceptance criteria)
1. **No hardcoding.** Words, categories, thresholds, limits live in data files (`categories.json`, `tags.json`, `limits.json`) or are decided by the model; none as keyword lists in code.
2. **Fixes must work in all scenarios**, not just the reported one.
3. **The model does no arithmetic or logic.** Code computes and verifies; the model only reads, labels, quotes. Amounts, dates, entities returned by the model are verified against the whole source text.
4. **No limits on what is kept** (mail kept whole; file size / cell / column / row / line caps are in `limits.json` with effectively unlimited defaults, re-read versioned).
5. **The AI never edits its own source.**
6. **No code or error text shown in the UI**; plain one-line answers.
7. **Privacy:** the assistant never sees the owner's finance data or private output.
8. **Numbers exactly right.**
9. **Honesty:** nothing may be claimed fixed / compliant / verified without proof. (The owner previously caught an over-claim of "followed all the standards", so check the code-quality claims below independently.)

## 4. Model usage (verify)
- Ollama, default `ministral-3:3b`; schema-constrained output (`format`), temperature 0, fixed `llm.SEED=7`.
- `extract.sample_of` = first 3000 chars + `key_passages` (lines carrying amounts/dates, found by shape, up to 1500 chars) + last 1500 chars. Extracted amounts/dates/entities are checked against the whole text.
- Finance categories: `categories.json` (names + descriptions, routine, income_never); model decides each merchant once (`merchant_categories` table); the person's corrections (`merchant_rules`) always win; `categorise(desc, kind, learned, decided)`; `finance categorise --measure` reports agreement of the model with the owner's corrections. Tags: people tags + model topics from `tags.json`.
- Parameter records replace long argument lists: `trace.Hooks`, `batch.Where`, `store.Narrow`, `judge.Budget`, `details.ClipLimits`, `judging._Pass`, `scanstatus._Context`.

## 5. Latest changes to scrutinise (recent commits on `atlas`)
- `8116186` Atlas no longer calls an app "switched off" when it merely answers badly; plain-words reason on the card (`atlas/src/atlas/upstream.py`: `_plain_failure`, `_unreachable`, `_report_from`, `_scan_one`; `atlas.js`); response bodies read whole (`MAX_BODY = 500_000_000`); tests in `atlas/tests/test_scan_status.py`.
- `1268275` No limits: mail kept whole (`MAIL_KEEPS` in `reading.py` fingerprint, old truncated mails re-read once); caps moved into `library/.../limits.json` + `limits.py`.
- `5838901` Fixed seed; schema-forced categories/tags; key-passages sampling; `--measure`.
- `5f7fa48` Finance categories/tags model-decided, no word lists.
- `ed140df` No function over 50 lines, tested.

## 6. Quality gates to run and report (paste real output)
Python 3.11+. For each of `kit`, `library`, `finance`, `atlas`, `images`:
```
pip install -e ../kit[secure] [-e ../images -e ../finance for library] -e ".[dev]"
ruff check . && ruff format --check . && mypy src && pytest -q
```
Finance additionally: `pytest -q --cov=finance --cov-fail-under=85`. Front end: `npx eslint@10.1.0` on each `static` dir and `npx prettier@3.8.1 --check` on `design/` and static dirs. Also `scripts/check-pages.js` (axe accessibility + browser smoke) and `scripts/scale-check.py`. Ruff limits that must be in force: max-args 7, max-positional-args 7, PLR2004 magic values (tests exempt), max-statements 50, max-branches 15, complexity 15.
Last known results (by the author, to be re-checked, not trusted): kit 43, library 208, finance 579 (88% coverage), atlas 81, images 95 tests passing.

## 7. What to review, in order
1. **Claims vs. reality**: for each rule in section 3 and each gate in section 6, find a counter-example or confirm with evidence. Search for keyword lists, magic numbers, hard-coded limits, functions over 50 lines, imports that break the layer table, copied function bodies, `# noqa` / `type: ignore` / skipped tests used to hide problems.
2. **Correctness and safety of money code** (`finance/`): statement import, rounding/decimals (no floats for money), dedup, migrations (`modules/money.py` migration list is append-only), reports and verification (`verify.py`), planning.
3. **Model-boundary integrity**: any place where model output is trusted without code verification; any arithmetic/logic delegated to the model; prompt-injection exposure from documents and mails; schema enforcement; determinism.
4. **Privacy / offline guarantee**: no-network guard in `kit`, any outbound call, logging of private content, encryption at rest, key handling, what Atlas can read of other apps.
5. **Robustness**: failure handling in `atlas/upstream.py` (timeouts, unreadable answers, unreachable vs. answering badly), parser pause/stop/resume (`control.py`), idempotent re-reads, large inputs (no limits => check memory/time behaviour; `scripts/scale-check.py`), crash safety of DB writes.
6. **Performance**: reader throughput on large libraries, model calls per document, sampling strategy, SQLite access patterns, UI payload sizes.
7. **Accuracy of the model path**: weaknesses of a 3B model on categorisation/extraction; whether verification catches wrong output; suggestion of measurable evaluation (the `--measure` mechanism).
8. **Maintainability**: module boundaries, naming, duplicate logic, test quality (tests that assert nothing, over-mocking, fakes diverging from real servers), docs vs. code drift (`docs/*.md`, per-app READMEs).
9. **UI/accessibility**: contrast, focus, keyboard, screen-reader labels, no raw error text shown.
10. **Ops**: `up.sh` / `update.sh` / `down.sh`, Docker files and compose (images per app; the Documents parser image contains only `library`), autostart scripts, backup/restore, upgrade path and migrations.

## 8. Known open items (do not report as new, but do say if you disagree)
- On the owner's Mac the Atlas reading card once said "not answering" while `/_atlas/api/health` reported all parts up; not reproduced locally. The fix made Atlas classify failures correctly and show a bracketed reason; the real cause is unknown.
- Mac-only things not verifiable in CI: reading speed on the real library, Apple Vision OCR, quality of the 3B model on sorting, `finance categorise --measure` (currently "0 of 0 corrections" because the owner has made none), screen reader behaviour.
- Mails with no amount and none of the apps' words are stored whole but not sent to the model (open question to the owner).
- Not built: embedding-based matching for kinds/merchants/grouping; a larger fallback model when code checks fail.
- Planned hardware: Apple laptop with 24 GB unified memory / 256 GB SSD (5 TB external HDD for photos/backups); consider which model size fits.

## 9. Output format
1. **Verdict** (one paragraph) and a score /10 for each of: correctness, safety/privacy, robustness, performance, accuracy, maintainability, accessibility, operability. Justify each score with evidence.
2. **Findings table**: ID, severity (blocker / high / medium / low), file:line, what is wrong, how to reproduce, suggested fix (specific, not generic), and whether it violates one of the owner's rules in section 3.
3. **Claims I could not verify**, with the exact command or access I would need.
4. **Top 5 changes** that most improve the product, in order.

Do not modify the repository. Do not propose features the owner did not ask for unless they fix a finding.
