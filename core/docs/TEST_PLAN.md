# Test plan, commands and expected outputs

All data is synthetic (invented sentinels in `tests/conftest.py`); no test needs real owner data or network access. Environment of the recorded run: Python 3.13.18 in a Linux container, pytest 9.2.0, ruff 0.17.5, mypy 2.4.1, sqlcipher3-binary 0.6.0, jsonschema 4.26.0, openapi-spec-validator 0.9.0. NOT run: any Swift/Xcode build, anything on a Mac, anything against a real model or real mail/documents.

## Commands (from `core/`)
| What | Command | Expected |
|---|---|---|
| Install | `pip install -e ../kit[secure] -e .[dev]` | no error |
| Lint / format / types | `ruff check . && ruff format --check . && mypy src` | `All checks passed!`, files already formatted, `Success: no issues found` |
| All tests | `python -m pytest -q -p no:cacheprovider` | `598 passed` |
| One criterion | `python -m pytest -q -k "policy"` etc. | per file |
| Overhead benchmark | `python bench/overhead.py --runs 300 --json` | JSON report (see BENCHMARK.md) |
| Legacy suites unaffected | `cd ../kit && python -m pytest -q` (and `library`, `finance`, `atlas`, `images`) | same counts as before this branch (165, 299, 701, 111, 100) |

## Fixtures
Documents (two pages, a Dutch+Japanese text), a mail (headers/body parts), an attachment, a Finance record and a Health record, each carrying a unique sentinel string; a stub retriever (returns the first passages of the asked source type; can misbehave), a stub model (answers from the first passage; modes: `unavailable`, `bad_quote`, `stale`, `not_retrieved`, `extra_figure`, `no_citation`, `dates`), a controllable clock, an in-memory grant source.

## WP3.2 document index
`tests/test_documents.py` (55 tests, synthetic files in a temp folder): extraction and exact locators, explicit unsupported/corrupt/oversized/link outcomes, newest-first and coverage truthfulness, a six-boundary crash matrix (`DocumentIndex.hook`: `scan:begin`, `scan:mid`, `doc:before`, `doc:extracted`, `doc:mid_commit`, `doc:after_commit`) that must converge to the clean-run index, idempotency, cancellation, disk pressure, slicing, changed/deleted sources, purge, encryption at rest, and the end-to-end path through the unchanged gate. Design and limits: `WP3_2_DOCUMENTS.md`.

## G-O19 designation and access gate
`tests/test_designation.py` (90 tests, synthetic, a deterministic fake OS-permission provider and a fake rollback anchor): default deny on a fresh install and after a restart, Documents-only / Mail-only / neither / declined choices, designable types, single-use request ids, OS evidence (absent, denied, stale, future-dated, wrong type, provider failure, loss after grant), withdrawal, expiry, revoke and regrant identity, purge failure and retry, crash atomicity (`DesignationStore.hook`), fifteen tamper/downgrade cases, whole-database snapshot restores and two-phase anchor failures (prepare refused, finish refused, process death before/after the commit, restore against an unfinished withdrawal or enable) that must withhold every grant or complete a recorded restriction, one-transaction withdrawal crash points, open-counting boundary tests (consent withdrawn or OS permission lost at `doc:before`, between path components, before the file open), a no-folder-byte-touched matrix over consent x OS state, and withdrawal during a task at the search, model and between-document boundaries. Design and limits: `G_O19_DESIGNATION.md`.

## Fault injection
`FaultInjector` crashes the pipeline the first time it passes a named boundary: `before|mid|after` x `retrieved|drafted|verified`, plus `before:final` (10 boundaries). After each crash the test builds a new service on the same encrypted store (a restart), runs `recover()` and expects one completed task, one answer, at most one repeated step. Retry budget 0 -> `failed/needs_attention`; a task stuck before it was queued -> `needs_attention`.

## Redaction (sentinel scan)
Everything the Core can write (event sink, Python logging at DEBUG, stdout, stderr) is captured in success, each failure mode, denied, cancelled, expired, hostile-retriever, crash-and-retry and 500 paths; none of nine sentinels (question, passage, subject, address, file name, attachment, Finance, Health, secret key) may appear, and every event line must use only SafeEvent keys.

## Criteria to tests
See `TRACEABILITY.md` (checked by a test).
