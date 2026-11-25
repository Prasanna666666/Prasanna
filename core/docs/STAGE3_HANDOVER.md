# Stage 3 handover and owner acceptance brief — historical work-package record

**Historical implementation handover:** retain detailed package/evidence notes below for traceability. The current stage status is governed by `STAGE3_ACCEPTANCE.md` and `docs/genesis/HANDOVER.md`; do not treat earlier package descriptions or architect-decision requests in this file as current acceptance. Latest documented status at 2026-11-25: PR #8 is open/draft/unmerged; Stage 3 is NOT ACCEPTED; F-4, F-11, F-12 and F-13 remain release-blocking. Stage 4–8 work is present but not architect-reviewed or accepted. The current Stage 3 criterion status is not inferred from the package summary below; see `STAGE3_ACCEPTANCE.md`.

Branch `genesis-stage2-foundation`, PR #8 (draft; never merge from here). Written for the architect's exact-commit review and for the owner. Evidence classes are as defined in `STAGE3_ACCEPTANCE.md`; evidence is labelled L (Linux CI, synthetic), R (hosted macOS CI runner: Keychain, `sandbox-exec`, a small public MLX model, the Swift launcher and client) and owner-Mac (none yet); nothing below is an owner-Mac or owner-model claim.

## What Stage 3 now contains (synthetic data; Linux CI plus hosted-macOS-runner evidence; no owner-Mac evidence)
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
`pip install -e ../kit[secure] -e .[dev]`, then `ruff check . && ruff format --check . && mypy src && pytest -q` (1169 tests on Python 3.13 and 3.11), `python evals/harness.py`, `python bench/ingest.py --json`, `python bench/overhead.py --json`. The kit suite (165 tests) includes the layer rules that `tests/test_architecture.py` also enforces.

## Rollback
Additive: revert the branch commits (the PR also changes `app/`, `ios/`, `kit/`, `scripts/` and documentation; reverting commits alone is not an installed-data, Keychain or mobile-state rollback plan). New stores only; no legacy store, key or component was migrated or retired (criterion 15). One behaviour changed inside the new Core: finished tasks no longer keep passage text, draft or quotes (no migration; earlier checkpoints are scrubbed when their task ends). API 1.0 behaviour and bytes are unchanged; 1.1 is opt-in per request.

## Decisions I need from the architect (not the owner)
Each has a recommended default so that a plain "approved" settles it:
1. **Criterion 5 / G-021: done at the policy and gate level (synthetic).** A restricted domain is now judged by an explicit grant for exactly that domain with a `restricted` ceiling, like any source; the former unconditional denial was removed and its tests replaced (`tests/test_policy.py`, criterion 5). The owner-facing Settings/area enable controls and owner-only consent API were added after the original package snapshot; Get Started itself still offers only Documents/Mail. Finance has a legacy `maintenance import-finance` path for the `transactions` table only, not a general source connector, and that migration has not been run on the owner's database. Health has an encrypted store/area but no importer or HealthKit/native Health source. Real owner-data ingestion remains unverified. G-021 semantics are recorded in `DECISIONS.md`.
2. **Typed capabilities (criterion 7): done as an additive 1.1 route**, `POST /v1/compute` (exact arithmetic, units, dates by code; no source read, no model). Model-initiated tool use during an answer is not built (no tools exist in this slice). Please confirm the contract addition.
3. **Source inspection: done as recommended** (additive 1.1 `PassageText`, `GET /v1/tasks/{id}/citations/{n}`, fails closed). Please confirm the contract addition.
4. **Performance thresholds:** retrieval scale is **fixed** (term index; 2.9 s to 41 ms p50 at 26,000 synthetic mail items, 285 to 7.6 ms at 1,400 documents, developer container). Numeric pass thresholds still need to be proposed from a Mac baseline and accepted; I have not invented any.
5. **`SafeEvent.reason_code`: done** (five additive routing values on `model.routed`, one event per answer: model, role, reason; tests in `tests/test_intelligence.py` and `tests/test_app.py`). Please confirm the contract addition. Previously: it was closed: routing reasons (`fallback_memory` etc.) cannot be emitted as events without an additive change; the gateway keeps them internal for now.

## Owner acceptance brief (plain language; about 15 minutes, needs the Mac)
Nothing below has been done by me. These are the things only you or a Mac can confirm; I will not report them as verified until they are.
1. **Get Started:** the first-run screen asks once; choosing nothing enables nothing; no folder or mail prompt repeats.
2. **A question about a document and one about mail:** you get an answer with a citation you can open; the line "Answered on this Mac by …" names the model.
3. **Cancel and "model drive unplugged":** cancelling stops promptly; unplugging the model drive gives a clear message and nothing is sent anywhere.
4. **Withdraw access to a folder or mail:** the next question says it is no longer allowed, and an old answer from that source is hidden.
5. **Speed and feel:** note how long a simple question takes. This is the first real number; the numbers in the docs are from a Linux container and do not predict it.
What I need from you only if something looks wrong: say what you saw. You do not need to relay anything to anyone.

## Added after the full-stage review of `7792ab5`
Streaming EMLX reader (attachments after the text are never read; byte count validated), worker without any skip flag (it asks the OS), per-data-folder Core lock and live-socket protection, app submission gate and bounded launcher cleanup, CI artefact scan, and the egress gateway (`EGRESS_GATEWAY.md`; exposed through a separate API 1.1 research operation behind two off-by-default gates; not integrated into ordinary answer generation). See the PR response for the finding-by-finding mapping.


## Current status (supersedes earlier closure wording)
Stage 3 is governed by the owner-authorised split in `STAGE-3-EXECUTION-PLAN.md` section 12.10. **Do not interpret the broad phrase “Stage 3 portion of every criterion is implemented and tested” in earlier handover snapshots as a passing criterion matrix.** `STAGE3_ACCEPTANCE.md` is the live criterion authority and still records criteria 2, 7 and 8 as PARTIAL with open findings; Stage 3 is NOT ACCEPTED. The named final-stage portions (F-4, F-11, F-12, F-13) are **not met, not waived, release-blocking**. This is not Stage 3 acceptance (the architect reviews the exact head and the owner accepts) and not a release or owner-tryable claim. See "Current status" in `STAGE3_ACCEPTANCE.md` and `PROGRAMME_AUDIT.md`.

Changed in the close-out round: the Swift launcher no longer removes a live socket (it removes one only when nothing answers on it, and otherwise fails startup without touching it); public research is exposed through a separate API 1.1 research operation behind two off-by-default gates (`EGRESS_GATEWAY.md`); returned research does not modify ordinary task answers; criterion 12 thresholds are proposed and the synthetic ones enforced in CI (`evals/thresholds_proposed.json`, `tests/test_thresholds.py`). Packaging is not release-ready (ad-hoc signed only; no notarisation or self-contained Python/model installation).
