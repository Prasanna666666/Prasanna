# Changed-file coverage matrix

Regenerated from `git diff --name-status -M origin/aperture...HEAD` at `4adc71a0b8d6486cf71a0a6f8996f8d3c32d29e5`. **541 entries with rename detection (D 100, A 355, M 5, R 72).** 512 were listed at `80562da`; the 20 added since are listed at the end (tests, fixtures and screenshots of this round; code files changed in the round were already in the list, so their rows are unchanged) The 508 of the previous version was the count at `5676a6a`; the four new entries are documents and a script added after it (listed at the end, status AUTHORED). Row statuses for the other 508 entries are carried over unchanged from `5676a6a`; none was re-inspected for this regeneration, and code is unchanged since `97d5e29`. This is the honest account, **not** a claim of exhaustive inspection.

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
