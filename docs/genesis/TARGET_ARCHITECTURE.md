# Atlas — Target Architecture

**Status:** Recommended target architecture · **Not a description of the current deployment**

## 1. Architectural direction

Build and ship **one Atlas application** with one product identity, one entry point, one navigation system, one settings surface and one coherent interaction model. Internally, use a modular monolith with explicit domain boundaries and stable contracts.

Finance, Documents, Images and any other legacy standalone apps/services are obsolete as product boundaries. Their capabilities are to become internal Atlas modules. They must not remain separate user-facing apps, separately branded products or independently configured experiences in the target state.

Separate helper processes are permitted only as implementation details when required for security isolation, platform constraints or resource scheduling (for example, an untrusted parser or model runtime). Such workers have no independent product identity or user-facing lifecycle. The existing implementation is reference material, not an architectural constraint: classify each mechanism as **reuse**, **reference-only** (including behavioural/regression evidence), or **discard**. Choose the best architecture even if that requires a new core. Preserve the owner's data, keys and history through integrity-checked migration, verified backups where applicable and rollback; do not perform destructive cleanup without an approved migration plan.

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
  iOS client adapters (committed future platforms)
  Optional secure browser client (not a committed delivery platform)
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

A single product-facing gateway abstracts model runtimes and model families. The owner-selected direction is Apple MLX with a benchmark-led ~27B main-model class and automatic task-based model switching (G-020); the exact model, quantisation, context and routing map remain evidence-gated under G-O01. The gateway provides:
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

The eventual mobile client is **iOS only**, usable by the owner while travelling and from anywhere with suitable internet connectivity. macOS remains the first implementation platform. Android is not a target. A secure browser client may complement mobile access; it must not become a separate product or weaken the single Atlas identity.

### 10.1 Remote-access model (target; topology requires an ADR)

- Atlas Core and all AI inference remain on owner-controlled devices/local infrastructure. A phone is a secure client, not a reason to move private data or inference to a third-party cloud.
- Mobile clients communicate with Atlas Core through an authenticated, encrypted remote-access channel. The design may use a user-controlled VPN/mesh or a narrowly scoped encrypted relay to traverse NAT; a relay must not become an inference service or plaintext data store.
- Do not expose the database, model runtime, filesystem or internal service ports directly to the public internet. Expose only a small, versioned client API/gateway with authentication, authorisation, rate limits, replay protection and audit.
- Require strong device identity and owner authentication (passkeys/MFA where supported), explicit device enrolment, least-privilege scopes, remote session revocation and lost-device recovery. A mobile device must not inherit unrestricted access merely because it belongs to the owner.
- Enforce the same domain boundaries and policy checks on remote requests as on local requests. The local model may read owner-authorised Finance and Health information under the owner's source grant; these domains remain separately labelled/keyed with provenance, redacted logs, cache controls and revocation. No client-side UI check is a substitute for Core policy enforcement.
- Minimise data held on mobile devices. Protect local caches and credentials with platform secure storage; support remote sign-out/revocation and define what happens to cached data on device loss. Sensitive notification content must be opt-in and minimised.
- Define offline behaviour explicitly: cached, already-authorised information may be available according to owner settings; new Core-dependent actions must be queued safely or reported unavailable, never falsely shown as completed. Resolve sync conflicts with explicit, auditable rules.
- The owner intends the owner-controlled Mac mini hosting Atlas Core to remain on and available. Treat this as an operating assumption, not a verified guarantee. Atlas must start automatically after a normal reboot or update; if the host or network cannot be reached, the mobile client shows a plain, honest unreachable state. Do not add disproportionate engineering for extreme outage scenarios.
- Worldwide mobile availability still depends on network reachability, mobile connectivity, supported regions and local law. Show connection state clearly and never imply an unavailable Core-dependent action completed.

### 10.2 Mobile capability and release expectations

The mobile experience should support the core everyday loop: secure sign-in/device enrolment, conversation, voice where supported, notifications, task/activity status, approvals, and review of evidence-backed results. Platform-specific capabilities may differ, but permissions and consequential-action safeguards must remain consistent. Mobile UI must be designed for intermittent connectivity, latency and small screens rather than merely shrinking the desktop interface.

Native iOS delivery, secure remote connectivity, push-notification privacy, offline behaviour, sync/conflict handling, device revocation and mobile release/support policy require explicit design and test gates before the client ships.

## 11. Unified delivery and migration roadmap

This is the single ordered roadmap. Sections 12.8 and 14 define workforce sequencing and first-proof criteria; they do not create competing migration sequences. Stages 1–3 are the only near-term committed delivery scope until the read-only slice is demonstrated on the real target hardware and accepted. Later stages remain target direction, not parallel implementation commitments. The roadmap is not implementation authorisation: Stage 2 requires the G-O17 runtime ADR, ChatGPT review of a bounded Stage 2 package, and the owner's explicit authorisation. Resolving G-O18 or G-O19 alone does not authorise Stage 2.

| Order | Stage | Required work | Scenario coverage (canonical register) | First tryable outcome | Exit evidence |
|---:|---|---|---|---|---|
| 0 | Product specification | Consolidate owner decisions, PRD, architecture, use-case register, network policy, approval matrix and delivery protocol. Reconcile superseded rules. | UC-001–UC-049 and UC-L01–UC-L30 inventoried; no capability claimed implemented. | No app; owner reviews one coherent specification. | Claude challenge closed; docs consistency check passes; one canonical roadmap. |
| 1 | Baseline audit and design | Audit code/data and classify reuse/reference-only/discard; map scenarios to code, interfaces, data flows, tests and migration risks. Define source adapters and threat models. | UC-001/002/007/008/009/012/016; UC-L03/L04/L06/L19/L26/L28; UC-047/048. | Synthetic UX or contract prototype only; no live personal-data access. | Reuse map, threat model, requirement-to-test traceability and benchmark plan accepted. |
| 2 | Foundation contracts | Stage 2 accepted baseline: typed capability/policy contracts, durable tasks/events, provenance, redacted observability and security tests. Keep API additive and backward-compatible. | UC-L08/L09/L11/L13/L14/L19/L20/L23/L24/L27/L30. | Developer harness with synthetic fixtures; not owner-usable Atlas. | Exact-head CI, independent review and compatibility evidence. |
| 3 | First usable Mac Atlas | Build coherent SwiftUI Mac experience over Core: local conversation/model adapter, progressive newest-first full-text document indexing, Mail body, supported attachments after separate acceptance, public web research through egress gateway, exact citations, coverage, durable tasks, cancellation and source inspection. One Get Started flow plus OS permissions; no repeated prompts. Calendar read-only after access verification. | UC-001/002/003/007/008/009/012/016/032; UC-L01–L09/L19/L26/L28; UC-039/041/047/048; document, Mail and public research scenarios §3.2/3.4. | **First installable and owner-tryable Mac build.** It answers from indexed subset before full import completes and shows coverage. | Synthetic CI plus owner-controlled Mac test; citation/injection/revocation/restart tests; warm local first-useful-answer p50 ≤2s and p95 ≤5s. Cold results reported separately; thresholds frozen before baseline. |
| 4 | Storage, keys and recovery | Complete storage/encryption/key-boundary ADR, backup/restore/export and key recovery; verify restore before sensitive-domain indexing or single-copy dependency. Keep FileVault enabled; Core starts after owner login/unlock. | UC-L15/L18; UC-040/L044/L046. | Stage 3 Mac build remains usable; controlled backup/restore test. | Integrity-checked backup/restore, key recovery, disk pressure and reboot/Keychain evidence; G-O02/G-O05 closed. |
| 5 | Personal-data domains and migration | Incrementally integrate Finance and Health under G-021, Calendar actions, Contacts, Notes, Photos and remaining local sources. Preserve originals, provenance and rollback; no silent migration. | Finance §3.5, Health §3.6, Calendar §3.3, Contacts/Notes/Photos catalogue; UC-035/043/044 and UC-L27. | Expanded personal Atlas beta with owner-authorised cross-domain answers and verified restore. | Domain access, arithmetic, cache/revocation, migration parity, no-egress and undo tests; destructive migration separately accepted. |
| 6 | Chief of staff and connected actions | Add measured specialist agents, public research depth, task/project automation, browser workflows, home/travel/shopping/work connectors, voice, notifications and proactive watchers. Only Action Gateway executes; approvals follow closed list. | UC-003–006/010/014; UC-031/035/036/038/042/049; domains §3.1–3.16; integration catalogue Stage 6. | Full personal-assistant beta; delegated workflows and reversible actions usable. | Agent-vs-single-model benchmark, conflict/idempotency/undo tests, connector revocation, prompt-count and action-matrix tests. |
| 7 | Production Mac release | Signed/notarised native app, one-click update, auto-start after owner login, health checks, redacted diagnostics, backup/checkpoint, rollback and target-Mac validation. | UC-L15/L17/L24/L40/L41/L42/L46. | Signed Mac release candidate; no headless unlock promise before login. | Target-Mac Keychain, FileVault, permission reset, update/rollback, performance, model isolation and crash-recovery evidence. |
| 8 | iOS and secure worldwide access | Shared SwiftUI iOS client; device enrolment/revocation; secure remote channel to owner-controlled Core; offline/cache/sync/conflict and notification privacy. | UC-033/034/037; UC-L16/L21; mobile portions of §3.1–3.16. | iPhone client usable remotely when Mac host is unlocked and reachable. | Remote threat model, device revocation, no public database/model ports, sync/offline, accessibility and supported-region tests. |

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
- Finance — model-assisted interpretation of owner-authorised local records plus deterministic, domain-isolated computation. Exact arithmetic, balances and calculations are code-derived and validated; no financial transaction or external disclosure without exact approval.
- Work / Projects — project plans, tasks, meeting preparation, deliverables and follow-ups.
- Communications / Scheduling — email, messages, calendar and reminders through explicitly authorised connectors.
- Travel — itinerary research and booking preparation; transactional actions remain approval-gated.
- Home — energy, household maintenance and explicitly authorised device control.
- Health — owner-authorised local model access with separate domain controls, provenance, redaction and revocation; no categorical model lock.
- Guardian / Policy — policy enforcement, risk classification, approval checks and audit oversight. It cannot grant permissions or override policy.

Agents are logical roles. Multiple roles may share a model/runtime, and one role may use different local models or deterministic tools depending on the task. Do not create a separate app or independent persistent memory for each agent.

### 12.3 Task contract and lifecycle
Every delegated task records: task ID; initiating user/trigger; parent task; objective and acceptance criteria; agent/role and version; authorised sources and tools; sensitivity scope; input/output references; model/runtime configuration; resource/time budget; dependency state; checkpoints; cancellation; retries; approval requirements; evidence; and terminal outcome.

Lifecycle: requested → policy checked → planned → queued → running → awaiting input/approval or verification → completed / partially completed / failed / cancelled / expired. State is durable and restart-safe. No infinite agent loops, unbounded retries, hidden delegation or indefinite background execution. The owner can inspect, pause and cancel active work.

### 12.4 Context and permission isolation
Each agent receives the minimum task-specific context required. Access is checked before retrieval and again before tool execution; filtering after content has entered model context is too late. Child agents inherit no more authority than the parent task and may receive less. Sensitive-domain data stays inside its domain boundary.

Finance and Health are owner-authorised local-model domains under G-021. Keep separate domain stores/labels, grants, provenance, redaction, cache controls and revocation. The model may reason over their content locally. Exact financial arithmetic and other exact calculations must be deterministic and code-checked. Cross-domain retrieval still requires Core policy authorisation; no private domain content may be sent to public Internet services or cloud inference.

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

The workforce follows the unified roadmap in §11; this is not a second migration plan. Stage 3 proves the first usable read-only Atlas workflow and only the minimum coordinator, retrieval and verification mechanisms. All supported Mail attachments are in scope but remain unavailable until their technical package passes acceptance. Use the single Get Started onboarding direction. Personal Knowledge and Research may be responsibilities inside that slice, not separate always-running agents. Add specialists/connectors only when frozen-set evaluation proves measurable benefit.

## 13. Storage, encryption and recovery gates

No irreversible consolidation of domain stores or single-copy dependency is allowed until the storage ADR, encryption/key boundaries, backup, restore, export and key-recovery procedures are specified and a restore has been tested. Every migration requires an inventory, integrity checks, preserved originals or recoverable backup, rollback plan and owner acceptance where data risk is material.

## 14. Thin vertical slice

The first architecture proof is the first owner-tryable Mac Atlas workflow in Stage 3: accept a question, find/read owner-authorised local documents and Mail, answer with exact evidence, persist task state and recover after interruption. Progressive newest-first indexing makes the indexed subset useful before full import completes; coverage is explicit. Documents and Mail are enabled through the one first-run Get Started consent plus OS permissions; Core enforces grants and revocation internally (G-O19). Mail is untrusted content; hostile instructions in message bodies, quoted/forwarded text, invites and attachments cannot alter scope or trigger actions. All supported attachment formats are in product scope, but content remains unavailable until the separate attachment package passes technical acceptance (G-O18). Logs exclude source content, names, subjects, addresses and prompts. Stage 3 is read-only for external actions; it does not authorise sends, shares, purchases or destructive migration. Public web research follows INTERNET_AND_NETWORK_POLICY.md. Evaluate English, Dutch and at least one non-Latin-script path; report measured support honestly. Reuse existing permission, consent, audit and ingestion mechanisms only after auditing them. This describes the target workflow, not implementation or production readiness.

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

## 17. Owner direction update — 2026-11-20

This section supersedes conflicting earlier target-architecture statements:

- Atlas is single-user. Do not add multi-user roles, shared-device assumptions or bystander-presence workflows.
- The local model may read owner-authorised Finance and Health information. Keep separate domain stores/labels, scoped grants, provenance, revocation, redacted logs and cache controls. These domains are not categorically hidden from local model context. Exact financial arithmetic remains deterministic and code-checked.
- Routine read/search/analysis/summarise/draft/compute operations do not require approval. Approval is for consequential external effects and materially irreversible changes only, with exact-action previews.
- First-run consent is one Get Started step plus OS permission prompts; no repeated incidental prompts or per-folder selection.
- Public Internet research is allowed through a Core-mediated egress gateway under INTERNET_AND_NETWORK_POLICY.md. No cloud inference, raw private content in public queries or secret egress.
- All supported Mail attachment formats are in scope, subject to separate technical design, parser isolation, provenance/OCR quality and acceptance.
- Progressive, newest-first model-free full-text indexing is a first-slice requirement. Atlas must disclose coverage and remain useful before complete indexing.
- USE_CASE_REGISTER.md is the complete scenario and connector inventory.

These are product requirements, not proof of implementation. Keep target-Mac, connector and release evidence pending until tested.

## 18. Agent action integrity and measured workforce value

Only the central Action Gateway may execute an action. Specialist agents may propose typed actions but cannot invoke external write tools directly.

- Before delegation, freeze a versioned evaluation set and numeric thresholds for answer quality, task completion, citation correctness, p95 latency, peak memory and energy. Proposed starting gate: at least +5 percentage points in task success or citation correctness on its target task class; zero new critical safety/policy failures; p95 latency no worse than 1.25× the direct baseline; peak memory remains within the predeclared model budget; energy per completed task no worse than 1.20× baseline. A specialist is enabled only if it passes the pre-registered gate; otherwise keep the direct/single-model path.
- The coordinator detects conflicts before execution: same target, overlapping time, contradictory state changes or duplicate external effects.
- Each action has a deterministic idempotency key derived from task ID, step ID, target identity and canonical payload hash; enforce a unique constraint in a durable action ledger.
- Use per-target leases with fencing tokens for mutable targets (calendar event, file path, message thread, device). Stale workers cannot commit after losing a lease.
- Use compare-and-set against the target's observed version. If the owner or another process changes the target while Atlas is planning, abort that write and re-plan.
- Retries after crash reuse the same idempotency key. Every reversible action records an undo/compensation entry and exact receipt.
- Tests cover duplicate specialist proposals, crash after provider success but before receipt, concurrent move/delete, owner edit during execution, and simultaneous command/watcher/rule triggers.

These controls are internal and should not add owner prompts. The owner sees only the closed approval list in PRD §4.4.

## 19. Owner-client authority and settings integrity

Only an enrolled, authenticated owner client may change Atlas settings, source grants, connector scopes, model defaults, automation rules or approval policy. The Core—not the UI—validates the client identity, signed request, nonce/time window and current authority. Mutating requests are replay-protected and recorded in a redacted audit trail. Retrieved documents, emails, webpages and agent outputs can never change settings or grants. Local macOS owner-client enrolment is established during Get Started; iOS enrolment is separately gated by Stage 8. Tests cover forged clients, replayed requests, revoked devices and untrusted-content attempts to change grants.
