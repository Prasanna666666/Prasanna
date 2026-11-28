# Atlas Core

Atlas Core is the owner-controlled local service behind the single Atlas application. It is a modular Python Core with a versioned signed API, Unix-socket transport for the local macOS client, SQLite/SQLCipher stores, source designation and policy gates, durable tasks/evidence, local model runtime adapters and bounded integration services.

This README describes the current repository layout; it is not an acceptance statement. Product intent is in ../docs/genesis/PRD.md and ../docs/genesis/TARGET_ARCHITECTURE.md. Current implementation/acceptance status is in docs/STAGE3_ACCEPTANCE.md, docs/STAGES_4_TO_8.md, docs/UI_IMPLEMENTATION_MAP.md and ../docs/genesis/IMPLEMENTATION_CONFORMANCE.md.

## Main implementation areas

- contracts/: frozen API 1.0 plus additive API 1.1 JSON Schema and OpenAPI contracts.
- src/atlas_core/: Core composition, API/transport, identity/enrolment, policy/designation/access, task pipeline, evidence/coverage, document and Mail indexing, Finance/Health record domains, deterministic calculations, actions/approvals/audit, connectors, devices/sync/relay, browser research boundary, local model runtime, backup/restore and signed updater.
- client/: Python reference client and user-facing status catalogue.
- tests/: unit, integration, fault-injection, privacy, boundary and platform-provider tests. Hosted macOS jobs exercise real Keychain/sandbox/MLX/Swift integration with synthetic data; owner-Mac/TCC/real-Mail/model/network validation remains separate.
- docs/: technical contracts, provider/runtime evidence, acceptance records, developer reports and historical package snapshots.
- bench/ and evals/: synthetic overhead/ingestion measurements and proposed evaluation thresholds. These are not target-Mac model performance results.

## Important current boundaries

- API 1.0 remains frozen/default; API 1.1 is served additively when explicitly negotiated.
- Documents and Mail are supported read paths; Mail attachment bytes are deliberately not read. Real Apple Mail store validation remains unverified.
- Finance/Health have separate stores, grants and deterministic summary paths; Finance import is limited to the legacy transactions table, and no Health importer/HealthKit adapter is implemented.
- Public research is a separate API 1.1 operation behind two off-by-default gates. It is not ordinary answer generation and is not a general no-private-egress guarantee.
- Browser reading is off in the production host until its worker confinement is accepted. Native macOS app automation and broad vendor integrations are not implemented.
- Backup/verify/drill/restore is currently a maintenance CLI. No complete owner-Mac restore drill or accepted backup destination/retention policy exists.
- Stage 3 is NOT ACCEPTED. Stage 4–8 work is present by owner direction but is not architect-reviewed or accepted. The PR is not release-ready.

## Development and tests

From core/:

```sh
pip install -e ../kit[secure] -e .[dev]
ruff check .
ruff format --check .
mypy src
python -m pytest -q -p no:cacheprovider
```

Run platform-specific checks through the repository CI workflow. Do not claim a test pass without the exact commit, workflow run, job and conclusion. A Linux run does not prove macOS Keychain, TCC, FileVault, owner-Mac or real Mail behaviour.

## Recovery and rollback

The current branch-wide rollback and recovery boundaries are documented in docs/BRANCH_ROLLBACK_AND_RECOVERY.md. The older docs/ROLLBACK.md is a historical Stage 2 package note, not a current recovery procedure.
