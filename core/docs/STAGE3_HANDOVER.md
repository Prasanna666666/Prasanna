# Stage 3 handover and owner acceptance brief

Branch `genesis-stage2-foundation`, PR #8 (draft; never merge from here). Written for the architect's exact-commit review and for the owner. Evidence classes are as defined in `STAGE3_ACCEPTANCE.md`; nothing below is a target-Mac or real-model claim.

## What Stage 3 now contains (all synthetic-data, Linux-verified)
| Package | What | Docs |
|---|---|---|
| WP3.2 Documents | encrypted, restart-safe index of one designated folder; exact citations | `WP3_2_DOCUMENTS.md` |
| G-O19 + WP3.3 Mail | default-deny designation per type, OS-permission evidence, rollback anchor; mail body index (attachments never read) | `G_O19_DESIGNATION.md`, `WP3_3_MAIL.md` |
| WP3.4 Intelligence Gateway | signed model manifest and import/load verification; deterministic routing from explicit signals; one resident model, capability-preserving fallback, deep tier only in Research mode; bounded scheduler (2, interactive first); degradation order; MLX adapter against a fake library; model identity in every 1.1 answer; API 1.1 served additively with a signed version and echo; coverage; exact arithmetic/units/dates; derived task content scrubbed and purgeable; evaluation set and harness (EN, NL, Cyrillic, Devanagari, CJK) | `models.py`, `intelligence.py`, `mlx_runtime.py`, `coverage.py`, `exact.py`, `evals/` |
| WP3.5 Experience | reference client over the signed socket contract; UX catalogue with completeness test | `WP3_5_CLIENT.md` |
| WP3.6 Reliability | fault, hostile-input, load and redaction matrix; ingestion benchmark | `WP3_6_RELIABILITY.md` |
| Composition root | `app.py`: builds a whole Core from injected parts, wires revocation to the index and task-store purge, runs the worker and the socket; end-to-end tests in `tests/test_app.py` | `app.py` |
| WP3.7 | acceptance traceability and this handover | `STAGE3_ACCEPTANCE.md` |

## How to reproduce (from `core/`)
`pip install -e ../kit[secure] -e .[dev]`, then `ruff check . && ruff format --check . && mypy src && pytest -q` (913 tests on Python 3.13 and 3.11), `python evals/harness.py`, `python bench/ingest.py --json`, `python bench/overhead.py --json`. The kit suite (165 tests) includes the layer rules that `tests/test_architecture.py` also enforces.

## Rollback
Additive: revert the branch commits (nothing outside `core/` and the CI job changed). New stores only; no legacy store, key or component was migrated or retired (criterion 15). One behaviour changed inside the new Core: finished tasks no longer keep passage text, draft or quotes (no migration; earlier checkpoints are scrubbed when their task ends). API 1.0 behaviour and bytes are unchanged; 1.1 is opt-in per request.

## Decisions I need from the architect (not the owner)
Each has a recommended default so that a plain "approved" settles it:
1. **Criterion 5 / G-021 (recommended: approve a separate Finance/Health source package; do not loosen policy first):** the policy denies Finance and Health (`restricted_domain`) and an existing test pins that; the plan says owner-authorised Finance/Health may enter the local model context. Confirm the intended change (policy data plus a source package), since I have not touched policy semantics.
2. **Typed capabilities (criterion 7) (recommended: additive 1.2 field `capability`, closed enum, always through the same policy gate):** the contract has no field to request one, so exact services are not reachable from a request. Decide an additive 1.2 delta (or keep them as verifier-only).
3. **Source inspection (recommended: `GET /v1/tasks/{id}/citations/{n}` returning the cited span's text, revalidated against grants):** answers carry the quote and locator; "show the passage" has no route. Decide whether to add one.
4. **Performance thresholds:** retrieval scale is **fixed** (term index; 2.9 s to 41 ms p50 at 26,000 synthetic mail items, 285 to 7.6 ms at 1,400 documents, developer container). Numeric pass thresholds still need to be proposed from a Mac baseline and accepted; I have not invented any.
5. **`SafeEvent.reason_code` (recommended: add the routing reasons in 1.2):** it is closed: routing reasons (`fallback_memory` etc.) cannot be emitted as events without an additive change; the gateway keeps them internal for now.

## Owner acceptance brief (plain language; about 15 minutes, needs the Mac)
Nothing below has been done by me. These are the things only you or a Mac can confirm; I will not report them as verified until they are.
1. **Get Started:** the first-run screen asks once; choosing nothing enables nothing; no folder or mail prompt repeats.
2. **A question about a document and one about mail:** you get an answer with a citation you can open; the line "Answered on this Mac by …" names the model.
3. **Cancel and "model drive unplugged":** cancelling stops promptly; unplugging the model drive gives a clear message and nothing is sent anywhere.
4. **Withdraw access to a folder or mail:** the next question says it is no longer allowed, and an old answer from that source is hidden.
5. **Speed and feel:** note how long a simple question takes. This is the first real number; the numbers in the docs are from a Linux container and do not predict it.
What I need from you only if something looks wrong: say what you saw. You do not need to relay anything to anyone.
