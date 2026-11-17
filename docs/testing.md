# Testing

Everything below was run on this branch (head of the pull request), in **fresh Python 3.11 environments** installed exactly as CI installs them, plus the browser checks against the running apps with invented data. Nothing here is copied from an earlier run.

## Results

| Package | Tests | Result | ruff | ruff format | mypy |
|---|---|---|---|---|---|
| kit | 139 | passed | clean | clean | clean (18 files) |
| images | 96 | passed (2 warnings) | clean | clean | clean (55 files) |
| finance | 650 | passed, coverage 88.94% (gate 85%) | clean | clean | clean (43 files) |
| library | 219 | passed | clean | clean | clean (39 files) |
| atlas | 92 | passed | clean | clean | clean (10 files) |
| **Total** | **1,196** | all passed | | | |

Other checks run: `bandit` (both CI invocations) clean; `eslint 10.1.0` and `prettier 3.8.1 --check` clean on the three apps' static folders and `design/`; **`scripts/check-pages.js`** (axe-core WCAG 2.1 AA + script errors + no hidden card/tile) over Finance (6 pages), Documents (5 pages) and Atlas with the apps inside it (6 pages): `PROBLEMS 0` **in both the light and the dark theme** (`THEME=dark node scripts/check-pages.js`; the dark theme was not run in a browser before and failed on every active control, D-20).

**GitHub Actions** on commit `e9a76cc` (the push and the pull-request run) both finished green: every job of the matrix (Python 3.11 and 3.13 for Finance and Library, kit, images, atlas, web, security with bandit, pip-audit and gitleaks). The runs before it were red for the reasons in `defects.md` D-08, D-14, D-16, D-17.

**Not run by me locally:** `pip-audit`, `gitleaks`, SBOM (they ran in CI), Python 3.13 for this exact head (it ran in CI), anything needing a Mac (Apple Vision OCR, Docker Desktop, real Ollama).

## How to run

```
# per package, from its folder (as CI does)
pip install -e "../kit[secure]" -e ".[dev]"      # finance: -e ".[secure,dev]"; library: also -e ../images -e ../finance -e ".[parse,dev]"
ruff check . && ruff format --check . && mypy src && pytest -q          # finance: pytest -q --cov=finance --cov-fail-under=85
# browser check (apps running; needs: npm i axe-core playwright)
node scripts/check-pages.js
```

## What the tests prove, by requirement

| Requirement | Tests |
|---|---|
| R-Q1 money exact | `finance/tests/test_money_exact.py`: 1.005, 12.345, 0.01, 0.1+0.2, negatives, 1.2e12, other minor-unit digits, not-an-amount inputs, rounding once for units × price |
| R-Q4 encryption | `kit/tests/test_db_safety.py`: convert, no plain copy, keep on request, wrong key, failed copy, failed check after swap, interrupted between renames, corrupt encrypted copy, no SQLCipher; `finance/tests/test_secure_by_default.py`; `images/tests/test_engine.py` |
| R-Q6 migrations | `kit/tests/test_db_safety.py`: failure halfway changes nothing, retry, restart after failure, triggers kept whole, upgrade from every old version; `images/tests/test_engine.py` |
| R-Q2 dates | `kit/tests/test_extract_whole_document.py`: real date kept with its source line, absent/invalid/ambiguous dates unknown, due before date dropped, Dutch/English/numeric layouts, classifier returns only verified dates |
| R-F3 medical | same file: row in the overlap kept once, same test printed twice far apart is two rows, 300 values and 80 medicines, more than 12 pieces, text never shortened, unreadable piece reported with part/characters/page, failing piece read in halves, `complete` false when a limit stops it; `library/tests/test_health_travel.py` (read in part is shown and read again; old capped results re-read) |
| R-Q5 limits | `library/tests/test_limits_config.py`: every limit is in the fingerprint, name/text/source/attachments/JSON limits come from the file, cuts are recorded, over-size result is refused and reported, documents cut under old limits are found when limits change |
| R-F8 assistant changes | `finance/tests/test_assistant_changes.py`: every tool classified once, read-only tools change nothing, prepare changes nothing, yes in a later message makes it once, same question cannot confirm, only a short yes, expiry, newer proposal replaces older, refused arguments kept nowhere, delete needs own words, adversarial-document test, audit trail; `atlas/tests/test_assistant_safety.py`: yes passed to the part and reported in code's words, long message is a question, nothing in a tool result reaches confirmation, system prompt says data not instructions, model server must be local, configured model only, no private data in the log |
| R-F6 upstream | `atlas/tests/test_scan_status.py`: ok, unreadable, very large, over the limit, exactly at the limit and one byte over, bad setting, closed connection, nothing listening |
| R-Q7 UI | `kit/tests/test_design.py` (one design file, text contrast in both themes, focus, **no rule hides a page surface**); `scripts/check-pages.js` |

## Test inventory (count per file)

### kit (84)

| File | Tests |
|---|---|
| `kit/tests/test_architecture.py` | 5 |
| `kit/tests/test_call_local.py` | 1 |
| `kit/tests/test_common_helpers.py` | 2 |
| `kit/tests/test_concepts.py` | 1 |
| `kit/tests/test_db_safety.py` | 14 |
| `kit/tests/test_design.py` | 4 |
| `kit/tests/test_extract_whole_document.py` | 37 |
| `kit/tests/test_kit.py` | 11 |
| `kit/tests/test_llm_calls.py` | 1 |
| `kit/tests/test_names.py` | 8 |

### images (96)

| File | Tests |
|---|---|
| `images/tests/test_albums.py` | 2 |
| `images/tests/test_colors.py` | 10 |
| `images/tests/test_config.py` | 1 |
| `images/tests/test_deepmeta.py` | 4 |
| `images/tests/test_derive.py` | 10 |
| `images/tests/test_details.py` | 15 |
| `images/tests/test_engine.py` | 5 |
| `images/tests/test_faceages.py` | 2 |
| `images/tests/test_faceattrs.py` | 1 |
| `images/tests/test_highlights.py` | 2 |
| `images/tests/test_judge.py` | 3 |
| `images/tests/test_ocr_engines.py` | 3 |
| `images/tests/test_organize.py` | 6 |
| `images/tests/test_placemodel.py` | 4 |
| `images/tests/test_quality.py` | 7 |
| `images/tests/test_quick.py` | 3 |
| `images/tests/test_safety_export.py` | 14 |
| `images/tests/test_vision_collect.py` | 4 |

### finance (619)

| File | Tests |
|---|---|
| `finance/tests/test_answers.py` | 4 |
| `finance/tests/test_applenotes.py` | 5 |
| `finance/tests/test_assistant_changes.py` | 14 |
| `finance/tests/test_backup_tasks_people.py` | 5 |
| `finance/tests/test_browse.py` | 6 |
| `finance/tests/test_data_boundary.py` | 2 |
| `finance/tests/test_docker_files.py` | 4 |
| `finance/tests/test_encryption.py` | 4 |
| `finance/tests/test_events.py` | 8 |
| `finance/tests/test_fail_fast.py` | 5 |
| `finance/tests/test_finance.py` | 34 |
| `finance/tests/test_fuzz.py` | 341 |
| `finance/tests/test_insight.py` | 14 |
| `finance/tests/test_llm_and_tagging.py` | 5 |
| `finance/tests/test_migrations.py` | 3 |
| `finance/tests/test_modules.py` | 10 |
| `finance/tests/test_money_exact.py` | 26 |
| `finance/tests/test_notes_check.py` | 5 |
| `finance/tests/test_parse_table_flow.py` | 6 |
| `finance/tests/test_planning.py` | 13 |
| `finance/tests/test_privacy.py` | 6 |
| `finance/tests/test_proof.py` | 7 |
| `finance/tests/test_rates.py` | 10 |
| `finance/tests/test_secure_by_default.py` | 6 |
| `finance/tests/test_standards.py` | 5 |
| `finance/tests/test_structure.py` | 9 |
| `finance/tests/test_tally.py` | 11 |
| `finance/tests/test_toolrun.py` | 5 |
| `finance/tests/test_trip_facts.py` | 5 |
| `finance/tests/test_verify.py` | 13 |
| `finance/tests/test_wealth_tax_bills.py` | 10 |
| `finance/tests/test_web.py` | 18 |

### library (217)

| File | Tests |
|---|---|
| `library/tests/test_apple_ocr.py` | 3 |
| `library/tests/test_applemail.py` | 6 |
| `library/tests/test_cards_and_forget.py` | 3 |
| `library/tests/test_casebook.py` | 13 |
| `library/tests/test_changes.py` | 27 |
| `library/tests/test_docker_files.py` | 12 |
| `library/tests/test_engines.py` | 6 |
| `library/tests/test_health_travel.py` | 23 |
| `library/tests/test_judging.py` | 12 |
| `library/tests/test_limits_config.py` | 7 |
| `library/tests/test_mail.py` | 10 |
| `library/tests/test_order.py` | 23 |
| `library/tests/test_parser_documents.py` | 19 |
| `library/tests/test_pictures.py` | 7 |
| `library/tests/test_pipeline.py` | 2 |
| `library/tests/test_readers.py` | 11 |
| `library/tests/test_readers_mail_attachments.py` | 8 |
| `library/tests/test_search.py` | 6 |
| `library/tests/test_selfcheck.py` | 1 |
| `library/tests/test_web.py` | 17 |
| `library/tests/test_whole_read.py` | 1 |

### atlas (92)

| File | Tests |
|---|---|
| `atlas/tests/test_assistant.py` | 24 |
| `atlas/tests/test_assistant_safety.py` | 8 |
| `atlas/tests/test_crosscheck.py` | 5 |
| `atlas/tests/test_dots.py` | 3 |
| `atlas/tests/test_evaluate.py` | 5 |
| `atlas/tests/test_proxy.py` | 8 |
| `atlas/tests/test_registry.py` | 9 |
| `atlas/tests/test_scan_status.py` | 8 |
| `atlas/tests/test_server.py` | 22 |

## Gaps (say so, do not hide)

- No test runs a real model. Model behaviour is tested with scripted fakes; prompt-injection resistance of the real model is **not** demonstrated either way. What is tested is that code, not the model, decides what changes.
- Reading speed, OCR quality and 3B-model sorting quality on a real library are unmeasured. `scripts/scale-check.py` measures the document store and its questions only (1k / 10k / 100k / 300k synthetic rows in a plain database: 0.1 s / 0.3 s / 2.2 s / 6.3 s end to end, peak memory 42 / 48 / 91 / 184 MB).
- The browser check exercises pages with invented data and no model; chat answers are not screenshotted.
- JavaScript has no unit tests; it is covered by eslint, prettier and the browser check.
- Docker, `up.sh`, `update.sh`, autostart: not exercised in CI.
- `kit/consent.py` word lists are tested for behaviour, not for coverage of other languages.
