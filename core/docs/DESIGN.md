# Design: architecture, dependency map, API versioning, reuse matrix

## Components and dependency direction (layers, lowest first; a module imports only from its own layer or below; enforced by `tests/test_architecture.py`)

```
 clients (SwiftUI app on Mac/iOS, any other)      untrusted: never an enforcement point
        |  signed requests (Ed25519 per client), API 1.0, JSON + SSE
 [8 transport]  Unix socket, owner-only, peer uid checked
 [7 api]        identity -> version -> route -> contract validation        imports: service, identity, contracts, errors, events
 [6 service]    pipeline: policy -> retrieve -> draft -> verify -> finish  imports: answer, tasks, gate, policy, evidence ...
 [5 answer]  [5 tasks]        envelope + checks | durable state (new encrypted store)
 [4 gate]    [4 evidence]     PermitToken-gated retrieval and model door | exact citations
 [3 policy]                   default-deny decisions, mints PermitToken
 [2 events] [2 identity]      allow-listed events | client registry, nonce cache
 [1 errors][1 contracts][1 rules][1 values]   taxonomy | schema validation | policy data | value types
```
Rules enforced by tests: no import cycles; the API/transport cannot import storage, retrieval, policy or evidence; a model is reachable only through `GatedModel` (needs a live `PermitToken`) and a `ModelContext` can be built only by `ContextBuilder`; one policy engine, one task store, one pipeline; no source-type name is written in code (the policy is data).

## Revisions after the independent review (PR #8)
- **Resume and serving re-check the permission.** Saved passages, citations and answers are used or served only if the *current* token still permits every source they touch; otherwise the task fails closed and the stale answer is replaced.
- **Context bound to its token.** `ModelContext.permit_id` must equal the presented token's `permit_id`, and every passage is re-checked at `GatedModel.generate`.
- **Task key from a Keychain provider on macOS.** `KeychainKeyProvider` (item `atlas-task-key`, read and provision via `security`; the key never on a command line); `EnvKeyProvider` is the Linux/test provider; `default_provider()` never falls back from the Keychain on a Mac unless `ATLAS_TASK_KEY_SOURCE=env|file` is set deliberately. The real `security` tool is NOT VERIFIED until it runs on a Mac.

## Request path and what is checked where
1. **Identity** (`identity.py`): signature over method, path+query, timestamp, nonce, body hash; client known, not revoked, timestamp within the skew limit, nonce unused. No Origin/localhost trust.
2. **Version** (`api.py`): optional `X-Atlas-Api-Version`; unsupported -> 426 `unsupported_version` before anything runs.
3. **Contract** (`contracts.py`): bodies validated against the schema; unknown fields refused.
4. **Policy** (`policy.py`) is decided at submit **and again at run time** (a revoked grant stops a queued task). Restricted domains (Finance, Health) and deferred types (attachments) are denied regardless of grants.
5. **Gate** (`gate.py`): a retriever is called only for permitted types and its output is re-checked; the model receives only a context built from permitted passages; the token's expiry is re-checked at the model door.
6. **Verify** (`answer.py`, `evidence.py`): every citation must resolve to the exact version, locator and span and contain its quote; figures and numeric dates must appear in the cited text; language support is never claimed beyond the measured list (empty today).
7. **Finish**: `completed` only if `verified`; `partially_completed` otherwise; `failed` with a reason for a failed citation, an unavailable model, denial or needs-attention.

## Durable task state (new, separate, additive, encrypted)
`$ATLAS_HOME/core/tasks.db` (path chosen by the caller), SQLCipher through `kit.db.connect`, its **own key** from a `KeyProvider`: on the Mac the dedicated Keychain item `atlas-task-key` (`KeychainKeyProvider`, with `provision()`); on Linux/CI `ATLAS_TASK_KEY`/`ATLAS_TASK_KEY_FILE` (development and test only). Tables: `tasks`, `task_events`, `answers`; `PRAGMA user_version` = 1 (a newer store is refused). The question and passages live only here and in API responses; never in events. Deleting the file rolls the whole feature back.

## API versioning proposal
- Path-versioned (`/v1/...`) plus `X-Atlas-Api-Version` for negotiation; `GET /v1/version` returns `{api_version, supported[]}`.
- Compatible changes (new optional fields, new endpoints, new enum values clients must ignore) stay in 1.x; removals or meaning changes need a new major version served side by side for one release.
- Unsupported client version -> 426 with no side effects (tested). A newer Core serves older clients while 1.x is supported.
- Contract changes are made in `contracts/` first; the Python reference and tests follow; Swift types are generated later with Apple's `swift-openapi-generator` (not run here).

## Reuse / adaptation / discard matrix (reconciled against Stage 1, baseline `atlas` @ `7a3b447`, no drift: `origin/atlas` unchanged)
| Stage 1 item | Use in Stage 2 |
|---|---|
| `kit.db.connect` (SQLCipher, key handling) | **Reused** for the new task store, with its own key. |
| `kit.audit.unproven_figures` (figures must come from the source) | **Reused** unchanged in `answer.py`; numeric dates added next to it. |
| Idempotent marks / atomic publish pattern (library reader) | **Adapted** as idempotency keys + one transaction per state change. |
| Staged change, nonce, undo (`library/changes.py`) | **Not used**: the first slice has no actions; belongs to the Action Runtime stage. |
| Hash-chained audit (`finance/audit.py`) | **Not used** (Finance stays outside); `ExecutionReceipt` carries an audit reference only. |
| `kit.sign` (shared platform key) | **Not reused**: per-client Ed25519 identity is required; the shared key proves "a platform process", not "which device". |
| `kit.consent` (English/Dutch word lists) | **Discarded** (Stage 1 G-4); no consent logic here. |
| `kit.rag` FTS5 retrieval, `library.store._sources` (no filter) | **Unchanged**: the gap G-13 remains in the legacy path; the new gate is the replacement point when ingestion is wired in a later stage. |
| `atlas.assistant` model-driven tool loop | **Unchanged**; the new pipeline is a deterministic state machine. |
| Architecture test idea (`kit/tests/test_architecture.py`) | **Adapted** for this package. |
