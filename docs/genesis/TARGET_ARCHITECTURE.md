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


## 13. Personal Agent Workforce and orchestration

Atlas Core provides one hierarchical supervisor/orchestrator for a coordinated workforce of specialised agents. This is an internal capability of the one Atlas application, not a collection of autonomous apps or permanently running model instances.

### 13.1 Control plane
The Agent Orchestrator owns task decomposition, routing, dependency graphs, delegation, deadlines, budgets, cancellation, retries, result consolidation and task status. A registry describes each agent's role, version, supported tasks, required permissions, sensitivity classification, allowed tools, model requirements, resource profile and health. The registry is configuration governed by Atlas policy; an agent cannot edit its own authority.

The orchestrator uses a planner/supervisor with specialist workers. It should prefer a direct tool or single-model path when sufficient. It may fan out independent research or analysis tasks, but dependent tasks and writes are ordered. A verifier is selected for high-impact or uncertainty-sensitive work; using multiple agents is not itself proof of correctness.

### 13.2 Personal-domain specialist roles
The initial role catalogue is a target design, not a commitment to implement all roles in the first release:
- Chief of Staff / Coordinator — owner intent, prioritisation, decomposition, delegation, synthesis and follow-through.
- Personal Knowledge — authorised retrieval, source linking, durable context and memory maintenance.
- Documents — file discovery, extraction, comparison, drafting, classification and organisation.
- Research / Verification — evidence gathering, source quality, contradiction checks and independent validation.
- Finance — restricted financial analysis through a separately governed domain boundary.
- Work / Projects — project plans, tasks, meeting preparation, deliverables and follow-ups.
- Communications / Scheduling — email, messages, calendar and reminders through explicitly authorised connectors.
- Travel — itinerary research and booking preparation; transactional actions remain approval-gated.
- Home — energy, household maintenance and explicitly authorised device control.
- Health — disabled/locked by default; separately permissioned and isolated.
- Guardian / Policy — policy enforcement, risk classification, approval checks and audit oversight. It cannot grant permissions or override policy.

Agents are logical roles. Multiple roles may share a model/runtime, and one role may use different local models or deterministic tools depending on the task. Do not create a separate app or independent persistent memory for each agent.

### 13.3 Task contract and lifecycle
Every delegated task records: task ID; initiating user/trigger; parent task; objective and acceptance criteria; agent/role and version; authorised sources and tools; sensitivity scope; input/output references; model/runtime configuration; resource/time budget; dependency state; checkpoints; cancellation; retries; approval requirements; evidence; and terminal outcome.

Lifecycle: requested → policy checked → planned → queued → running → awaiting input/approval or verification → completed / partially completed / failed / cancelled / expired. State is durable and restart-safe. No infinite agent loops, unbounded retries, hidden delegation or indefinite background execution. The owner can inspect, pause and cancel active work.

### 13.4 Context and permission isolation
Each agent receives the minimum task-specific context required. Access is checked before retrieval and again before tool execution; filtering after content has entered model context is too late. Child agents inherit no more authority than the parent task and may receive less. Sensitive-domain data stays inside its domain boundary.

Finance is treated as restricted pending explicit owner resolution of the existing privacy rule: general agents must not retrieve raw Finance records or place them in shared memory/context. Where policy permits, Finance may return narrowly scoped computed results with provenance, without exposing underlying records. Health remains locked by default. Cross-domain workflows require explicit policy authorisation for each data flow.

### 13.5 Action and approval boundary
All agent tools use the central Action Runtime. Agents may prepare proposed actions but cannot bypass preview, validation, approval, revalidation, idempotency, audit or undo/compensation controls. Approval is bound to the exact action, target, parameters and validity window. Retrieved documents, emails, webpages and agent outputs cannot grant approval or change policy.

Default automation posture:
- Observe and prepare within explicitly granted read permissions.
- Execute only low-risk reversible actions covered by an owner-configured policy.
- Require explicit approval for financial transactions, purchases, bookings, sending messages, external commitments, data sharing, destructive operations and irreversible changes.
- Keep a complete, inspectable activity record and notify the owner of material outcomes or exceptions.

### 13.6 Local model and resource scheduling
Agent execution is demand-driven, not a swarm of continuously active models. The Intelligence Gateway selects local models and deterministic tools by task capability, quality, latency and resource cost. The scheduler enforces global RAM/CPU/GPU budgets, bounded concurrency, priority for interactive conversation, back-pressure, thermal awareness, cancellation and fair sharing. Model reuse is preferred where safe; agent contexts remain isolated even when runtime/model instances are shared. No cloud inference or silent remote fallback is permitted.

### 13.7 Failure, verification and observability
Agents return structured results with evidence, uncertainty, limitations and proposed actions. The orchestrator handles worker crashes, timeouts, unavailable models/connectors, partial results and conflicting outputs. It must not present an incomplete workflow as complete. High-impact calculations use deterministic code/tools; high-impact conclusions require source evidence and independent validation where practical. Logs and telemetry must be privacy-minimised and must not expose personal content or secrets.

### 13.8 Initial delivery sequence
1. Establish task contracts, agent registry, permission enforcement and durable task lifecycle.
2. Deliver a single coordinator with a small number of useful specialists for Personal Knowledge, Documents and Research, using existing Atlas mechanisms where possible.
3. Add connectors and further domain specialists in owner-prioritised slices; Finance and Health remain separately gated.
4. Add scheduled/proactive delegation only after monitoring, cancellation, notification, audit and recovery are proven.
5. Expand autonomy only through explicit owner-approved policies and measured reliability.

Do not build a large multi-agent framework before proving one complete personal workflow end to end.

## 14. Storage, encryption and recovery gates

No irreversible consolidation of domain stores or single-copy dependency is allowed until the storage ADR, encryption/key boundaries, backup, restore, export and key-recovery procedures are specified and a restore has been tested. Every migration requires an inventory, integrity checks, preserved originals or recoverable backup, rollback plan and owner acceptance where data risk is material.

## 15. Thin vertical slice

The first architecture proof should complete one useful personal workflow end to end: accept a user request, retrieve from one authorised source, produce a result with precise provenance, prepare any proposed action through the Action Runtime, enforce approval policy, persist task/audit state, and recover correctly after interruption. Reuse existing consent, staged-change, undo, audit and ingestion mechanisms after auditing them; do not rebuild them by assumption.

## 16. Hardware and evidence requirements

Distinguish the owner's intended target Mac from the actual machine used for tests. Every benchmark records machine model, RAM, OS, power/thermal state, model and quantisation, runtime, context size, concurrency, corpus/workload, cold/warm condition, p50/p95/p99 latency, throughput and resource use. Targets remain provisional until measured. Evidence labels are defined in the Delivery Protocol.
