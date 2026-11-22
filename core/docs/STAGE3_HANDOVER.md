# Stage 3 handover and owner acceptance brief

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
`pip install -e ../kit[secure] -e .[dev]`, then `ruff check . && ruff format --check . && mypy src && pytest -q` (1160 tests on Python 3.13 and 3.11), `python evals/harness.py`, `python bench/ingest.py --json`, `python bench/overhead.py --json`. The kit suite (165 tests) includes the layer rules that `tests/test_architecture.py` also enforces.

## Rollback
Additive: revert the branch commits (nothing outside `core/` and the CI job changed). New stores only; no legacy store, key or component was migrated or retired (criterion 15). One behaviour changed inside the new Core: finished tasks no longer keep passage text, draft or quotes (no migration; earlier checkpoints are scrubbed when their task ends). API 1.0 behaviour and bytes are unchanged; 1.1 is opt-in per request.

## Decisions I need from the architect (not the owner)
Each has a recommended default so that a plain "approved" settles it:
1. **Criterion 5 / G-021: done at the policy and gate level (synthetic).** A restricted domain is now judged by an explicit grant for exactly that domain with a `restricted` ceiling, like any source; the former unconditional denial was removed and its tests replaced (`tests/test_policy.py`, criterion 5). Still not built: a Finance/Health source adapter and owner grant flow (domain packages), so no real Finance or Health data flows yet. Please confirm this is the intended semantics.
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
Streaming EMLX reader (attachments after the text are never read; byte count validated), worker without any skip flag (it asks the OS), per-data-folder Core lock and live-socket protection, app submission gate and bounded launcher cleanup, CI artefact scan, and the egress gateway (`EGRESS_GATEWAY.md`, not wired into the answer flow). See the PR response for the finding-by-finding mapping.


## Current status (supersedes earlier closure wording)
Stage 3 is **NOT ACCEPTED / OPEN**. The owner directed that work which cannot be tested now (real model, target hardware, a person using the app, signing, the real Internet) is carried to the final stage and does not block the testable Stage 3 scope; that is a sequencing decision, not evidence, and each deferred item stays release-blocking there. See "Current status" in `STAGE3_ACCEPTANCE.md` and `PROGRAMME_AUDIT.md`. The egress gateway is disconnected and disabled; its guarantee is bounded and stated in `EGRESS_GATEWAY.md` (not a general no-private-egress guarantee). Packaging is not release-ready (ad-hoc signed only; no notarisation or self-contained Python/model installation).
