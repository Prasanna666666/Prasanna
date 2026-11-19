# Atlas — Target Architecture

**Status:** Recommended target architecture · **Not a description of the current deployment**

## 1. Architectural direction

Build and ship **one Atlas application** with one product identity, one entry point, one navigation system, one settings surface and one coherent interaction model. Internally, use a modular monolith with explicit domain boundaries and stable contracts.

Finance, Documents, Images and any other legacy standalone apps/services are obsolete as product boundaries. Their capabilities are to become internal Atlas modules. They must not remain separate user-facing apps, separately branded products or independently configured experiences in the target state.

Separate helper processes are permitted only as implementation details when required for security isolation, platform constraints, fault containment or resource scheduling (for example, an untrusted parser or model runtime). Such workers have no independent product identity or user-facing lifecycle. Migrate incrementally: preserve working behaviour and data while retiring the old app shells and duplicate orchestration. Do not perform a destructive big-bang rewrite.

## 2. Logical architecture

```
Experience layer
  Chat | Voice | Dashboard | Notifications | Approvals | Activity/history
                              |
Atlas Core
  Session/context | Orchestration | Capability registry | Policy engine
  Event bus | Durable jobs | Observability | User preferences
       |                 |                    |
Memory & Knowledge   Intelligence Gateway   Action Runtime
  Sources/provenance   Model adapters         Typed tools
  Facts/entities       Routing/evaluation     Approval policies
  Relationships        Retrieval              Audit receipts
  Temporal validity    Context assembly       Idempotency
  Sensitivity/retention
       |                 |                    |
Internal Atlas capabilities / bounded contexts
  Documents | Finance | Health | Travel | Work | Calendar | Home | Media | ...
       |
Platform adapters
  macOS | Filesystem | Keychain | Notifications | Voice | Local runtimes
  Future platform adapters behind portable interfaces
```

## 3. Atlas Core responsibilities

Atlas Core owns:
- Application lifecycle and configuration.
- User sessions and conversation context.
- Capability discovery and invocation contracts.
- Cross-domain orchestration and context assembly.
- Policy evaluation and permission checks.
- Event publication/subscription.
- Durable background job coordination.
- Observability, audit correlation and operational health.

Atlas Core should not become a dumping ground for domain-specific business logic. Internal Atlas capabilities own their schemas, validation, business rules, migrations and tools, but are delivered and experienced as parts of the single Atlas application.

## 4. Domain capability contract

Each capability exposes a typed, versioned interface describing:
- Identity, version and supported operations.
- Required permissions and sensitivity classification.
- Input/output schemas and error taxonomy.
- Read/write/destructive classification.
- Idempotency and retry behaviour.
- Evidence/provenance returned with results.
- Health and capability status.

A capability must not bypass another capability's data ownership by directly editing its database. Cross-domain workflows are orchestrated through contracts or domain events. Internal module boundaries are code and data-ownership boundaries, not separate application boundaries.

## 5. Intelligence Gateway

A single product-facing gateway abstracts model runtimes and model families. It provides:
- Capability-based model selection (latency, context, structured output, reasoning, vision, embeddings).
- Dense and MoE model support where measured benefits justify it.
- Runtime adapters and model lifecycle management.
- Streaming generation.
- Context budgeting and retrieval.
- Structured-output validation and safe tool-call parsing.
- Resource scheduling, warm/cold model policy and cancellation.
- Evaluation, telemetry and regression comparison.

The gateway must support multiple local models and runtimes without making the rest of Atlas depend on model-specific APIs. No silent remote fallback.

## 6. Memory and Knowledge subsystem

A shared governed subsystem manages:
- Original source references and immutable source identity.
- Extracted content and observations.
- Facts, entities and relationships.
- Temporal validity and confidence.
- Provenance and supporting evidence.
- Sensitivity, access policy, retention and deletion lifecycle.
- Embeddings/search indexes as rebuildable derived data.

Domain systems remain authoritative for transactional records (for example, ledger entries). Memory is not a substitute for a finance ledger, medical record or source document.

## 7. Action Runtime

All write-capable tools pass through one policy-controlled execution path:
1. Validate caller identity and capability permissions.
2. Classify action risk and reversibility.
3. Validate arguments and current state.
4. Prepare a human-readable action preview.
5. Obtain approval when policy requires it.
6. Revalidate state and approval at execution time.
7. Execute with idempotency and bounded retries.
8. Persist an immutable audit receipt and outcome.
9. Support undo/compensation where technically possible.

No model output, retrieved content or tool result can grant permission.

## 8. Durable job and event system

Long-running work is represented as durable jobs with stable IDs, persisted state, checkpoints, leases/heartbeats, retries, cancellation and terminal outcomes. Job state is authoritative; UI progress is a projection.

Use an event-driven model for source changes and capability coordination, with scheduled polling only where event delivery is unavailable or unsuitable. Events must be deduplicated and replay-safe.

## 9. Storage strategy

Do not lock the target to a database/search technology until current schemas, encryption, data volume, query patterns, backup and migration costs are audited. SQLite remains a plausible single-user local foundation; it is not approved here as the universal answer.

Separate sensitive stores or encryption keys where threat modelling supports the added operational complexity. Search indexes and embeddings are derived and rebuildable; source records and audit history require stronger durability guarantees.

## 10. Platform portability

Keep business logic and domain contracts platform-neutral. Encapsulate macOS-specific functionality (Keychain, filesystem events, Apple Mail/Photos, notifications, speech, local model runtimes) behind adapters. Define capability detection and graceful degradation for platforms without an equivalent feature.

## 11. Migration strategy

1. Inventory current apps, packages, processes, APIs, schemas, data stores, keys, tests, CI and operational scripts.
2. Map every legacy app feature and dataset to its target internal Atlas capability; identify duplicate ownership and hidden coupling.
3. Define contract and security boundaries before moving code.
4. Add compatibility adapters and regression tests.
5. Introduce durable job state and evidence/provenance contracts before redesigning ingestion.
6. Introduce the Intelligence Gateway behind the existing model client boundary.
7. Migrate one capability/workflow at a time; preserve existing data and encryption keys.
8. Benchmark and compare old/new behaviour before removing a legacy path.
9. Retire old interfaces only after parity, migration, rollback and owner acceptance are demonstrated.

## 12. Architecture guardrails

- No direct cross-domain database writes.
- No personal-data cloud inference or silent fallback.
- No ungoverned model tool execution.
- No non-durable long-running job state.
- No hidden truncation or silent partial processing.
- No model-specific assumptions in domain logic.
- No architecture change without migration, tests and rollback plan.
