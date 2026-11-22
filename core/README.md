# Atlas Core: Stage 2 foundation (reference implementation)

Implementation notes for the Stage 2 work package (`docs/genesis/STAGE-2-WORK-PACKAGE.md` on branch `genesis-architecture`, PR #7). **Not a specification**: the canonical documents are `docs/genesis/`.

What is here, and only this:
- `contracts/`: the language-neutral source of truth, OpenAPI 3.1 (`openapi.yaml`) and JSON Schema (`atlas-contracts.schema.json`), API version 1.0.
- `src/atlas_core/`: the Python reference implementation: default-deny source policy (`policy.py`, rules as data in `policy-rules.json`), the gate every retrieval and model call must pass (`gate.py`), exact citations (`evidence.py`), the answer envelope (`answer.py`), durable task state in a new encrypted store (`tasks.py`), the pipeline (`service.py`), signed-request identity (`identity.py`), the API handler (`api.py`) and a Unix-socket transport (`transport.py`).
- `tests/`: 1129 tests (1116 run on Linux; 13 need macOS, a model folder, or both), each acceptance criterion marked `@pytest.mark.criterion(n)`; `bench/overhead.py`; `docs/`: design, threat review, test plan, benchmark, rollback, traceability.

What is NOT here (by design): no change to any existing package, database, key or UI; no ingestion, search or Mail reading; no real model; no Swift/SwiftUI (not verifiable without a Mac); no remote or iOS access; no actions.

Run: `cd core && pip install -e ../kit[secure] -e .[dev] && ruff check . && ruff format --check . && mypy src && pytest -q`
