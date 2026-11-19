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

## 10. Platform portability and worldwide mobile access

Keep business logic and domain contracts platform-neutral. Encapsulate macOS-specific functionality (Keychain, filesystem events, Apple Mail/Photos, notifications, speech, local model runtimes) behind adapters. Define capability detection and graceful degradation for platforms without an equivalent feature.

The eventual product includes mobile clients for **iOS and Android**, usable by the owner while travelling and from anywhere with suitable internet connectivity. macOS remains the first implementation platform, not the only supported client. A secure browser client may complement mobile access; it must not become a separate product or weaken the single Atlas identity.

### 10.1 Remote-access model (target; topology requires an ADR)

- Atlas Core and all AI inference remain on owner-controlled devices/local infrastructure. A phone is a secure client, not a reason to move private data or inference to a third-party cloud.
- Mobile clients communicate with Atlas Core through an authenticated, encrypted remote-access channel. The design may use a user-controlled VPN/mesh or a narrowly scoped encrypted relay to traverse NAT; a relay must not become an inference service or plaintext data store.
- Do not expose the database, model runtime, filesystem or internal service ports directly to the public internet. Expose only a small, versioned client API/gateway with authentication, authorisation, rate limits, replay protection and audit.
- Require strong device identity and owner authentication (passkeys/MFA where supported), explicit device enrolment, least-privilege scopes, remote session revocation and lost-device recovery. A mobile device must not inherit unrestricted access merely because it belongs to the owner.
- Enforce the same domain boundaries and policy checks on remote requests as on local requests. Finance raw records remain inaccessible to all models and general agents; Health remains locked by default. No client-side UI check is a substitute for server-side policy enforcement.
- Minimise data held on mobile devices. Protect local caches and credentials with platform secure storage; support remote sign-out/revocation and define what happens to cached data on device loss. Sensitive notification content must be opt-in and minimised.
- Define offline behaviour explicitly: cached, already-authorised information may be available according to owner settings; new Core-dependent actions must be queued safely or reported unavailable, never falsely shown as completed. Resolve sync conflicts with explicit, auditable rules.
- Global availability is an objective, not a guarantee: it depends on the owner-controlled host being online, power/network availability, mobile connectivity, supported regions and local law. Show connection/availability state clearly and degrade gracefully.

### 10.2 Mobile capability and release expectations

The mobile experience should support the core everyday loop: secure sign-in/device enrolment, conversation, voice where supported, notifications, task/activity status, approvals, and review of evidence-backed results. Platform-specific capabilities may differ, but permissions and consequential-action safeguards must remain consistent. Mobile UI must be designed for intermittent connectivity, latency and small screens rather than merely shrinking the desktop interface.

Native iOS and Android delivery, secure remote connectivity, push-notification privacy, offline behaviour, sync/conflict handling, device revocation and mobile release/support policy require explicit design and test gates before those clients ship.

## 11. Unified delivery and migration roadmap

This is the single ordered roadmap. Sections 13.8 and 15 define workforce design and first-proof criteria; they do not create competing migration sequences.

| Order | Stage | Required work | What is proven before proceeding |
|---:|---|---|---|
| 0 | Documentation baseline | Complete Claude review, ChatGPT reconciliation and Claude confirmation. Inventory canonical vs legacy docs and record unresolved owner decisions. | One internally consistent target specification. |
| 1 | Read-only vertical-slice audit/design | Audit existing mechanisms and define a small document workflow: find/read a local document and answer with exact source/page/section evidence. | Bounded workflow, code reuse map and measurable retrieval/provenance criteria. |
| 2 | Foundation contracts | Define capability interfaces, policy checks, task/job state, provenance, redacted observability and architecture tests; reuse current controls. | Typed boundaries prevent bypass, leakage and duplicate orchestration. |
| 3 | Read-only slice implementation | Implement only the approved workflow, durable task state and direct-path fallback; no writes or external side effects. | Correctness, provenance, restart recovery, adversarial isolation and recorded-hardware latency. |
| 4 | Storage/recovery gate | Complete storage/key ADR, backup/restore/export/key recovery design and tested restore before consolidation or single-copy dependency. | Recoverability and integrity demonstrated; owner accepts recovery experience. |
| 5 | Incremental capability migration | Migrate one internal capability at a time behind adapters; preserve data, keys, tests and rollback. | Parity and rollback demonstrated before retiring each legacy shell. |
| 6 | Broader intelligence/workforce | Add measured routing, specialists, connectors and proactive work only where benchmarks justify complexity. | Each route/agent improves outcomes without violating privacy, latency or resource budgets. |
| 7 | Native packaging/release | Deliver native Mac app, integrity-verified one-click updates, health checks, backup/checkpoint and rollback. | Install/update/rollback and operational recovery pass release tests. |
| 8 | Worldwide mobile access | Deliver iOS and Android clients, secure remote connectivity to owner-controlled Atlas Core, device identity/revocation, push-notification privacy and defined offline/sync behaviour. | Remote threat model and ADR accepted; mobile security, device-loss, intermittent-network, sync/conflict and global connectivity tests pass. No cloud inference or plaintext relay storage. |

No stage authorises destructive cleanup by itself. Each migration requires approval, inventory, compatibility checks, rollback and acceptance.

## 12. Personal Agent Workforce and orchestration

Atlas Core provides one hierarchical supervisor/orchestrator for a coordinated workforce of specialised agents. This is an internal capability of the one Atlas application, not a collection of autonomous apps or permanently running model instances.

### 12.1 Control plane
The Agent Orchestrator owns task decomposition, routing, dependency graphs, delegation, deadlines, budgets, cancellation, retries, result consolidation and task status. A registry describes each agent's role, version, supported tasks, required permissions, sensitivity classification, allowed tools, model requirements, resource profile and health. The registry is configuration governed by Atlas policy; an agent cannot edit its own authority.

The orchestrator is a deterministic task state machine over registered, typed task contracts. A model may select among permitted task types and propose validated parameters, but it does not own workflow state, permissions, retry policy or authority. Prefer a direct tool or single-model path when sufficient; if planning confidence is inadequate, fall back to the direct path or ask the owner. It may fan out independent research or analysis tasks, but dependent tasks and writes are ordered. A verifier is selected for high-impact or uncertainty-sensitive work; using multiple agents is not itself proof of correctness.

### 12.2 Personal-domain specialist roles
The initial role catalogue is a target design, not a commitment to implement all roles in the first release:
- Chief of Staff / Coordinator — owner intent, prioritisation, decomposition, delegation, synthesis and follow-through.
- Personal Knowledge — authorised retrieval, source linking, durable context and memory maintenance.
- Documents — file discovery, extraction, comparison, drafting, classification and organisation.
- Research / Verification — evidence gathering, source quality, contradiction checks and independent validation.
- Finance — deterministic, domain-isolated computation only. By explicit owner decision, no model or general agent sees raw Finance records; only narrowly scoped computed outputs may cross the boundary.
- Work / Projects — project plans, tasks, meeting preparation, deliverables and follow-ups.
- Communications / Scheduling — email, messages, calendar and reminders through explicitly authorised connectors.
- Travel — itinerary research and booking preparation; transactional actions remain approval-gated.
- Home — energy, household maintenance and explicitly authorised device control.
- Health — disabled/locked by default; separately permissioned and isolated.
- Guardian / Policy — policy enforcement, risk classification, approval checks and audit oversight. It cannot grant permissions or override policy.

Agents are logical roles. Multiple roles may share a model/runtime, and one role may use different local models or deterministic tools depending on the task. Do not create a separate app or independent persistent memory for each agent.

### 12.3 Task contract and lifecycle
Every delegated task records: task ID; initiating user/trigger; parent task; objective and acceptance criteria; agent/role and version; authorised sources and tools; sensitivity scope; input/output references; model/runtime configuration; resource/time budget; dependency state; checkpoints; cancellation; retries; approval requirements; evidence; and terminal outcome.

Lifecycle: requested → policy checked → planned → queued → running → awaiting input/approval or verification → completed / partially completed / failed / cancelled / expired. State is durable and restart-safe. No infinite agent loops, unbounded retries, hidden delegation or indefinite background execution. The owner can inspect, pause and cancel active work.

### 12.4 Context and permission isolation
Each agent receives the minimum task-specific context required. Access is checked before retrieval and again before tool execution; filtering after content has entered model context is too late. Child agents inherit no more authority than the parent task and may receive less. Sensitive-domain data stays inside its domain boundary.

Finance is a deterministic capability boundary: by explicit owner decision, raw Finance records are never exposed to any AI model, general agent, shared memory or coordinator context. Finance code computes the requested result and may return only the minimum necessary computed output, with provenance and policy checks. Any proposal to change this requires a new explicit owner decision. Health remains locked by default. Cross-domain workflows require explicit policy authorisation for each data flow.

### 12.5 Action and approval boundary
All agent tools use the central Action Runtime. Agents may prepare proposed actions but cannot bypass preview, validation, approval, revalidation, idempotency, audit or undo/compensation controls. Approval is bound to the exact action, target, parameters and validity window. Retrieved documents, emails, webpages and agent outputs cannot grant approval or change policy. A task that reads untrusted content must not directly perform an external send/share in the same unreviewed context. Before execution, policy must inspect the exact outgoing payload, recipients/destination and data classification; required approval must display that exact content and destination. Any post-approval change invalidates approval. Include hostile email/web prompt-injection cases in the synthetic evaluation suite.

Default automation posture:
- Observe and prepare within explicitly granted read permissions.
- Execute only low-risk reversible actions covered by an owner-configured policy.
- Require explicit approval for financial transactions, purchases, bookings, sending messages, external commitments, data sharing, destructive operations and irreversible changes.
- Keep a complete, inspectable activity record and notify the owner of material outcomes or exceptions.

### 12.6 Local model and resource scheduling
Agent execution is demand-driven, not a swarm of continuously active models. The Intelligence Gateway selects local models and deterministic tools by task capability, quality, latency and resource cost. The scheduler enforces global RAM/CPU/GPU budgets, bounded concurrency, priority for interactive conversation, back-pressure, thermal awareness, cancellation and fair sharing. Model reuse is preferred where safe; agent contexts remain isolated even when runtime/model instances are shared. No cloud inference or silent remote fallback is permitted.

### 12.7 Failure, verification and observability
Agents return structured results with evidence, uncertainty, limitations and proposed actions. The orchestrator handles worker crashes, timeouts, unavailable models/connectors, partial results and conflicting outputs. It must not present an incomplete workflow as complete. High-impact calculations use deterministic code/tools; high-impact conclusions require source evidence and independent validation where practical. Logs and telemetry must be privacy-minimised and must not expose personal content or secrets.

### 12.8 Initial delivery sequence

The workforce follows the unified roadmap in §11; this is not a second migration plan. Begin with a read-only document retrieval/answer workflow and only the minimum coordinator, document retrieval and verification mechanisms required. Personal Knowledge and Research may be responsibilities inside that slice, not separate always-running agents. Add specialists/connectors only after the slice is measured and accepted. Finance and Health remain separately gated; proactive delegation and broader autonomy come later.

## 13. Storage, encryption and recovery gates

No irreversible consolidation of domain stores or single-copy dependency is allowed until the storage ADR, encryption/key boundaries, backup, restore, export and key-recovery procedures are specified and a restore has been tested. Every migration requires an inventory, integrity checks, preserved originals or recoverable backup, rollback plan and owner acceptance where data risk is material.

## 14. Thin vertical slice

The first architecture proof is a **read-only document workflow** (tentative owner preference, pending final confirmation): accept a user request, find and read an authorised local document, answer with exact file and page/section provenance, persist task state, and recover correctly after interruption. It has no write, send, share, purchase or other external side effect, so it does not need an approval flow to prove retrieval. Reuse existing permission, consent, audit and ingestion mechanisms after auditing them; do not rebuild them by assumption. This is a proposed first slice, not implementation authorisation.

## 15. Hardware and evidence requirements

Distinguish the owner's intended target Mac from the actual machine used for tests. Every benchmark records machine model, RAM, OS, power/thermal state, model and quantisation, runtime, context size, concurrency, corpus/workload, cold/warm condition, p50/p95/p99 latency, throughput and resource use. Targets remain provisional until measured. Evidence labels are defined in the Delivery Protocol.


## 16. Update, export and operational safety

The owner has decided the target delivery experience is a **native macOS application with one-click updates**. The exact packaging mechanism, helper-process layout, install footprint, update signing/integrity chain and rollback implementation remain subject to an ADR and implementation audit. Existing containers/services, if present, are transitional implementation details until the audit proves otherwise; they must not create multiple user-facing apps. Do not claim native packaging is already implemented.

- Atlas must not autonomously modify, rewrite or deploy its own application source code. Agent-assisted development is a separate workflow with human-controlled repository permissions, review and release gates.
- Define an integrity-verified local update path, explicit user consent where required, pre-update backup/checkpoint, health check and rollback to the last known-good version. Core functionality must not depend on a cloud update service.
- Provide owner-controlled export of source records and derived knowledge in documented open formats, with provenance and schema/version metadata. Export and restore must be tested.
- Define schema versioning, migration compatibility, preconditions, integrity checks, interruption recovery and rollback before changing persistent stores.
- User-facing error states must be understandable and actionable. Keep raw code, stack traces and sensitive diagnostics out of normal UI; diagnostic logging follows redaction requirements.
- Do not use arbitrary hardcoded source/word/record caps that silently limit ingestion or memory. Resource controls must be explicit, observable, configurable where appropriate and fail safely without dropping data.
