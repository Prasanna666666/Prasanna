# Atlas — Detailed Low-Level Technical Design
**Document:** LLD-001  
**Status:** Architecture proposal for independent review — NOT implementation authorisation  
**Date:** 2026-11-20  
**Scope:** Complete target design for the single Atlas product, macOS-first with future iOS client  
**Owner:** Product owner  
**Architect:** ChatGPT  
**Rule:** No production implementation begins until this design, its ADRs, interface contracts, threat model and acceptance tests are reviewed and approved.

---

## 0. Executive architecture decision

Atlas is one native Apple application with a local, owner-controlled Core runtime. It is not a collection of separate apps and it is not a cloud AI service.

**Recommended target architecture**
- **Client:** Swift 6, SwiftUI, structured concurrency; one shared Apple client codebase with platform-specific presentation and capability adapters.
- **Core:** a local macOS-hosted modular monolith behind a versioned, language-neutral API. The long-term Core implementation language remains an ADR decision; use a narrow reference implementation only where needed to validate contracts. Do not commit to Python or Swift by assumption.
- **Persistence:** SQLite as the transactional system of record, accessed through GRDB from Swift where appropriate. Use explicit migrations, WAL, foreign keys, integrity checks and backup/restore tests. Do not use a vector database as the source of truth.
- **Search:** SQLite FTS5 for lexical search; a replaceable vector-index adapter for semantic retrieval; deterministic metadata filters and optional relationship traversal. Hybrid ranking is explicit and evaluated.
- **Inference:** local-only Intelligence Gateway with replaceable runtime adapters. Benchmark MLX/MLX Swift, llama.cpp and applicable Apple-native runtimes on the actual target Mac. No cloud inference or silent fallback. Select the default runtime/model only from reproducible measurements.
- **Orchestration:** Atlas-owned deterministic workflow/state-machine engine backed by SQLite jobs, checkpoints, leases and an outbox. Do not add Temporal, LangGraph, CrewAI or a distributed workflow server to a single-user desktop product unless measured requirements later justify them.
- **Connectors:** capability-scoped adapters; OAuth secrets in Keychain; read-only by default; explicit source designation; durable incremental sync; source provenance retained.
- **Actions:** a single Action Gateway enforces permissions, approval, idempotency and audit. Models never execute tools directly.
- **Memory:** governed, provenance-backed knowledge records distinct from raw sources, extracted observations, session context and derived conclusions. Sensitive domains are partitioned; Finance raw records never enter model context.
- **Packaging:** signed/notarised native macOS app with a separately permissioned local Core/helper boundary only where process isolation is justified; verified one-click update and rollback.
- **Mobile:** iOS is a future client of the same versioned Core API. Remote access is a separate security-gated design; no public database/model ports and no hosted inference.

This is a recommendation, not a claim that the components have been benchmarked or implemented. The design intentionally keeps high-risk technology choices behind interfaces until evidence is available.

## 1. Product boundary and non-goals

### 1.1 Product
One Atlas application provides:
1. Assistant — chat, voice, multimodal input, context and answers.
2. Today / Dashboard — priorities, reminders, task state, recent activity and actionable summaries.
3. Knowledge — personal search, source exploration, documents, mail, retained memories and provenance.
4. Tasks — plans, scheduled workflows, approvals, execution and receipts.
5. Connections — connected sources, scope, sync status, source designation and revocation.
6. Control Centre — privacy, model selection/status, memory controls, diagnostics, backup/restore and device access.

These are navigation areas within one product, not separately installed applications or independent domain databases.

### 1.2 Explicit non-goals for initial macOS release
- No cloud inference, hosted “brain”, or automatic cloud failover.
- No Android target.
- No unrestricted autonomous outbound actions.
- No general agent access to raw Finance records.
- No Health access by default.
- No mandatory Kubernetes, microservices, distributed database or cloud workflow engine.
- No automatic indexing merely because an account or folder is connected.
- No claiming a language, model, connector or performance level without test evidence.

## 2. Requirements and traceability

Owner decisions G-001 through G-020 in the Decision Register remain authoritative. This document adds derived engineering requirements:

| ID | Requirement | Verification |
|---|---|---|
| NFR-001 | All inference executes locally; absence/failure of local runtime is explicit | Network-denial test; runtime failure test |
| NFR-002 | One Atlas product and one owner-controlled data boundary | Packaging and UX architecture review |
| NFR-003 | Every factual answer from personal sources identifies source and exact location | Citation golden set |
| NFR-004 | Retrieval access checks happen before content enters model context | Cross-domain penetration tests |
| NFR-005 | Durable jobs survive process crash, restart, sleep/wake and worker retry | Fault-injection suite |
| NFR-006 | Retried work is idempotent; no duplicate durable outputs or external actions | Duplicate-event and retry tests |
| NFR-007 | Sensitive data is excluded from logs, traces, crash reports and evaluation fixtures | Synthetic secret-leak tests |
| NFR-008 | User can inspect, correct, expire and delete retained memory | Lifecycle integration tests |
| NFR-009 | Source deletion/revocation propagates to owned derivatives and reports residual backup retention | Deletion verification |
| NFR-010 | UI remains responsive during background ingestion and model work | UI hitch and contention tests |
| NFR-011 | Model/runtime can be replaced without changing domain or UI contracts | Adapter conformance tests |
| NFR-012 | iOS can be added without rewriting domain contracts | API contract and portability tests |
| NFR-013 | Unsupported, partial, failed and inaccessible content is visible, never silently treated as complete | Ingestion completeness tests |
| NFR-014 | High-impact actions require policy evaluation and approval as configured | Action policy test matrix |
| NFR-015 | Finance raw records are never visible to any model or general agent | Architectural boundary tests and code review |
| NFR-016 | English, Dutch and other encountered languages are evaluated separately | Per-language benchmark report |

## 3. System context and trust boundaries

### 3.1 Logical topology

```
SwiftUI Atlas Client
  ├─ Presentation / Navigation / Accessibility
  ├─ Client State + View Models
  └─ Versioned Core API client
          │ authenticated local IPC
          ▼
Atlas Core (local macOS host)
  ├─ Session & Context Service
  ├─ Intelligence Gateway ── Runtime Adapters ── Local model process
  ├─ Retrieval & Knowledge Service
  ├─ Memory Governance Service
  ├─ Connector & Sync Service
  ├─ Workflow Scheduler / Durable Job Engine
  ├─ Action Gateway / Approval Policy
  ├─ Notification & Voice Services
  ├─ Audit / Diagnostics / Health
  └─ Domain capabilities (Finance isolated)
          │
          ▼
Local encrypted data stores + original source references
          │
          ├─ SQLite transactional stores
          ├─ FTS index
          ├─ replaceable vector index
          ├─ source blob store / file references
          └─ encrypted backups
```

### 3.2 Trust zones
- **Z0 UI:** untrusted presentation input; cannot access databases, model files, connector tokens or privileged tools directly.
- **Z1 Core API:** authenticated client boundary; validates schema, identity, request limits and capability.
- **Z2 General domain:** ordinary personal/work content under explicit source designation.
- **Z3 Sensitive partitions:** Health and other sensitive data; locked unless specifically enabled.
- **Z4 Finance enclave:** deterministic-only processing. No model, general agent, shared prompt, embedding pipeline or general-purpose index receives raw Finance records.
- **Z5 Action execution:** isolated tool execution with narrowly scoped capabilities, approvals and audit receipts.
- **Z6 Model runtime:** receives only minimal policy-authorised context; no direct filesystem, network or connector credentials.
- **Z7 External connectors:** remote systems are untrusted inputs; retrieved content is data, never executable instruction.

All cross-zone transfers require a typed contract, policy decision, purpose and audit event. Default is deny.

## 4. Application design and navigation

### 4.1 Information architecture
- **Home:** current priorities, upcoming commitments, running jobs, pending approvals, recent outcomes.
- **Ask:** persistent conversations, voice, attachments and contextual follow-up.
- **Search:** unified search with filters by source, date, domain, type and sensitivity; result cards show provenance.
- **Knowledge:** sources, extracted facts, memories, relationships, conflicts and corrections.
- **Tasks:** task inbox, plans, recurring workflows, run history, pause/resume/cancel.
- **Connections:** account/source connection, independent source designation, scopes, last sync, errors, revoke.
- **Settings & Control:** model/runtime, privacy, retention, permissions, backups, diagnostics and export.

### 4.2 Interaction rules
- Every long-running operation exposes state, elapsed time, progress semantics, cancellation and error recovery.
- Never show a percentage if total work is unknown; show counts or indeterminate progress.
- Distinguish “connected”, “authorised”, “designated searchable”, “indexed” and “current”. They are separate states.
- A source result shows source name, source timestamp, exact page/paragraph/message span and freshness.
- Model identity is visible in response details; show runtime/model/version and whether a smaller/faster route was selected.
- User can inspect why a memory exists, what evidence supports it, what used it and how to correct/delete it.
- Approval prompts state exact action, target, data to be sent, consequences and reversibility.
- Failure states provide retry, inspect, reconnect, skip-with-reason or cancel; never silently swallow.

## 5. Core module boundaries and responsibilities

| Module | Owns | Must not own |
|---|---|---|
| App Shell | Navigation, UI state, accessibility | Business rules, connector secrets |
| Core API | Authenticated contracts, versioning, streaming | Domain persistence logic |
| Session Service | Conversation/session state and context budget | Durable personal memory decisions |
| Intelligence Gateway | Task classification, model routing, budgets, validation | Direct external side effects |
| Runtime Adapter | Load/infer/cancel/unload model | User permissions or memory policy |
| Retrieval Service | Query planning, access filtering, ranking, citations | Source-of-truth facts |
| Ingestion Service | Parse, normalise, classify, index, checkpoint | Destructive source mutation |
| Memory Governance | Memory lifecycle, sensitivity, correction, expiry, deletion | Original source content ownership |
| Connector Service | Auth, sync, cursors, source identity | General agent autonomy |
| Workflow Engine | Durable task state, retries, scheduling | Model policy or UI presentation |
| Action Gateway | Permission, approval, idempotency, execution receipts | Planning/reasoning |
| Finance Capability | Deterministic financial calculations | Model access to raw financial records |
| Audit Service | Redacted security/action/job evidence | Content-rich telemetry |
| Backup Service | Snapshot, verify, restore, retention | Unencrypted export of secrets |

Modules communicate through typed interfaces and domain events. No module reaches into another module's tables. Cross-module reads use repositories/query APIs; writes use owning module commands.

## 6. Core API and interface contracts

### 6.1 API principles
- Versioned OpenAPI 3.1 contract with JSON Schema payloads.
- Transport: authenticated local IPC on macOS (Unix domain socket or XPC selected by security/streaming benchmark); TLS 1.3 for approved remote device access later.
- Every request carries `request_id`, `client_id`, `api_version`, `created_at`, `deadline` and declared capability.
- Every response carries `request_id`, typed status, result, warnings and provenance references where applicable.
- Streaming uses typed events: `accepted`, `progress`, `token_delta`, `tool_proposed`, `approval_required`, `citation`, `completed`, `failed`, `cancelled`.
- Unknown fields are handled according to versioning policy; breaking changes require a new major API version.
- Every mutating command has an idempotency key.
- Cancellation is explicit and acknowledged; cancellation does not erase already committed work.

### 6.2 Canonical contracts
- `AskRequest`: user input, conversation ID, selected context, response mode, deadline.
- `AnswerEvent`: text delta, evidence reference, model metadata, confidence/limitation disclosure.
- `SearchRequest`: query, source allowlist, domain, date range, result limit, sensitivity clearance.
- `SourceRecord`: source ID, connector ID, type, external ID, version/fingerprint, timestamp, designation state.
- `EvidenceRef`: source ID/version, exact locator, content hash, extraction version.
- `MemoryRecord`: memory ID, type, statement/value, sensitivity, validity interval, confidence, provenance, retention policy, lifecycle state.
- `JobRecord`: job ID, workflow/version, input fingerprint, stage, state, attempt, lease, checkpoint, outputs, timestamps.
- `ActionProposal`: action ID, actor, purpose, target, exact payload summary, scopes, risk, reversibility, idempotency key, expiry.
- `ApprovalDecision`: approver, decision, scope, timestamp, policy version, expiry.
- `ActionReceipt`: action ID, outcome, external receipt/reference, verification state, audit ID.
- `ModelDescriptor`: model ID/version/hash, architecture, quantisation, context capability, tool/JSON capability, memory estimate, language evaluation, license and runtime compatibility.
- `TaskEnvelope`: task ID, purpose, typed input/output schema, domain scope, allowed tools, data classification, budget, deadline, parent task and cancellation token.

Full JSON Schemas are a required generated artefact in the API contract package; prose contracts above are not a substitute for schema validation.

### 6.3 Identity and authentication
- Each installed client instance has a generated identity and keypair held in Keychain.
- Local client authenticates to Core; Core authorises per capability and client identity.
- No bearer token is written to logs, preferences or source control.
- Revocation invalidates client identity and queued remote actions.
- Remote device enrolment is not enabled until the remote-access threat model and ADR are accepted.

## 7. Data architecture and persistence

### 7.1 System of record
Use SQLite for transactional metadata and durable state. Recommendation: GRDB for Swift-facing migrations, typed queries and transaction handling; benchmark it against direct SQLite for critical paths. SQLite is available across Apple platforms and supports a shared portability strategy (Apple structured-data guidance: https://developer.apple.com/documentation/technologyoverviews/structured-data-models).

Use:
- WAL mode for concurrent readers and serialized writers.
- Foreign keys enabled and verified on every connection.
- Explicit transaction boundaries.
- Busy timeout and bounded retry.
- Schema migrations with checksums and rollback/restore plan.
- Integrity checks and backup API; never copy a live database file naively.
- Separate database files only for security boundaries or operational isolation, not arbitrary micro-modularity.

### 7.2 Logical stores
1. **atlas_core.db:** identities, settings, conversations metadata, job state, workflow definitions, approvals, action receipts, audit metadata.
2. **atlas_knowledge.db:** source metadata, extracted observations, facts, entities, relationships, provenance, memory records.
3. **atlas_finance.db:** isolated deterministic financial ledger/records, separate key and repository boundary; no general search index.
4. **source vault:** original content or managed encrypted copies where permitted; otherwise stable references and content hashes.
5. **search indexes:** rebuildable FTS/vector indexes; never authoritative.
6. **backup archive:** encrypted, versioned snapshots and manifests.

The number of physical databases is an ADR outcome after threat modelling; the logical boundaries above are mandatory even if physical consolidation is chosen.

### 7.3 Core schema (minimum entities)
- `ClientIdentity(client_id, public_key_ref, platform, created_at, last_seen_at, revoked_at)`
- `Connector(connector_id, provider, account_ref, auth_state, granted_scopes, status)`
- `Source(source_id, connector_id, source_type, external_id, version, fingerprint, source_time, designation, sensitivity, status)`
- `IngestionJob(job_id, source_id, workflow_version, state, stage, attempt, lease_owner, lease_until, checkpoint_json, input_fingerprint, output_manifest, error_code)`
- `Observation(observation_id, source_id, source_version, locator, content_hash, extracted_payload_ref, parser_version, confidence)`
- `Fact(fact_id, subject_id, predicate, value_json, unit, valid_from, valid_to, status, sensitivity, confidence)`
- `EvidenceLink(fact_id, observation_id, relation, exact_locator)`
- `Entity(entity_id, entity_type, canonical_key, display_label, sensitivity)`
- `Relationship(relationship_id, subject_id, predicate, object_id, valid_from, valid_to, confidence, evidence_set_ref)`
- `Memory(memory_id, memory_type, statement, sensitivity, retention_policy, lifecycle_state, created_at, expires_at, corrected_by)`
- `Conversation(conversation_id, created_at, updated_at, retention_state)`
- `Message(message_id, conversation_id, role, content_ref, created_at, model_descriptor_ref)`
- `WorkflowRun(run_id, workflow_id, workflow_version, state, deadline, parent_run_id, idempotency_key)`
- `WorkflowStep(step_id, run_id, step_key, state, attempt, input_hash, output_ref, checkpoint_ref, lease_until)`
- `Approval(approval_id, action_id, decision, scope_hash, policy_version, decided_at, expires_at)`
- `ActionReceipt(action_id, status, external_ref, verified_at, audit_ref)`
- `AuditEvent(audit_id, actor, capability, target_ref, decision, timestamp, correlation_id, redacted_metadata)`

All tables include stable IDs, schema versioning and timestamps as appropriate. Use UTC instants and preserve source timezone/original timestamp. Never use display strings as primary keys.

### 7.4 Encryption and key management
- Use platform Keychain/Secure Enclave-backed key protection where available; data encryption uses vetted platform cryptography and authenticated encryption.
- Separate key hierarchy by data class; Finance key is distinct.
- Do not invent a custom cipher or key derivation scheme.
- Define recovery before promising backup usability. If the owner loses the recovery secret/device, explain precisely what can and cannot be restored.
- Backups encrypted independently; restore must verify manifest, checksums, schema and access boundaries before replacing live data.

## 8. Connectors and data ingestion

### 8.1 Connector lifecycle
States: `disconnected → authorising → connected → source-designation-required → syncing → current`; error states include `reauthorisation-required`, `rate-limited`, `partial`, `revoked` and `failed`.

Connection is not consent to index. Each source type has an independent designation state: `not-designated`, `designated-read-only`, `paused`, `revoked`.

### 8.2 Connector contract
Each connector implements:
- `capabilities()` — read, delta sync, change notifications, attachment support, write operations.
- `authorise()` / `refreshCredentials()` / `revoke()`.
- `enumerate(cursor)` — paged source IDs and metadata.
- `fetch(sourceID, version)` — bounded content fetch.
- `changes(cursor)` — additions, changes and deletions.
- `acknowledge(cursor)` — only after durable ingestion commit.
- `health()` — status, quota and last successful sync.

Connector adapters cannot call models or invoke actions. They emit untrusted source payloads into ingestion.

### 8.3 Initial source policy
- Local documents: read-only, only explicitly designated folders; attachments/archives excluded until their formats and hostile-content handling are accepted.
- Mail: read-only body, headers and thread metadata only after explicit Mail designation. Attachment contents remain excluded until G-O18 is resolved.
- Calendar: read-only initially; proposals only in a later approved capability. No create/update/delete in initial slice.
- Other providers: inventory and rank by user value, security, API stability and maintenance burden; no blanket connector promises.

### 8.4 Ingestion stages
`discover → fingerprint → fetch → parse/OCR → normalise → classify → extract observations → verify → link evidence/entities → index → publish`.

Each stage is a versioned pure transformation where possible. External side effects are isolated. Output is staged, validated, committed, then published atomically.

### 8.5 Hostile input controls
- Treat all email, documents, web content, metadata and OCR as untrusted data.
- Parser sandbox/process isolation for complex formats; no scripts/macros execution.
- Enforce compressed and expanded size, recursion depth, page count, OCR time, parser time and memory budgets. Limits are configurable and visible; exceeding one yields `needs_review`, not silent omission.
- Strip/neutralise active content; preserve original source separately.
- Prompt injection is not an instruction. Tool permissions come only from policy and typed user-authorised intent.
- Attachment processing is a separate capability with explicit source provenance and malware/format controls.

## 9. Memory, knowledge graph and retrieval

### 9.1 Distinct layers
- Original source.
- Extracted observation.
- Normalised fact.
- Entity/relationship.
- Derived conclusion.
- Episodic conversation record.
- Semantic personal memory.
- Procedural preference/rule.
- Task-scoped scratch context.

Do not collapse them into a vector store or free-form summary.

### 9.2 Memory record lifecycle
`candidate → policy_check → retained | rejected | needs_owner_review → active → corrected/superseded/expired/deleted`.

Each memory records evidence, source version, extraction method, confidence, sensitivity, valid time, creation time, retention policy and correction history. Conflicts are preserved as disputed until resolved; newer evidence does not erase historical truth.

### 9.3 Retrieval pipeline
1. Authenticate caller and establish purpose/domain/sensitivity clearance.
2. Build permitted source set; deny by default.
3. Query structured metadata and FTS.
4. Query vector index only within the permitted partition.
5. Optional entity/relationship traversal within the same permission scope.
6. Merge candidates with source freshness and duplicate handling.
7. Rerank with measured model or deterministic scoring; reranker receives only authorised candidates.
8. Return evidence spans and confidence/coverage metadata.
9. Construct minimal context under a token budget.
10. Validate citations against the original source locator before answer completion.

No model receives records and then gets told to ignore them. Filtering occurs before model context construction.

### 9.4 Search design
- SQLite FTS5 for lexical matching, phrase and prefix queries.
- Vector index behind `VectorIndex` protocol; benchmark embedded options for recall, update/delete correctness, disk footprint and rebuild time. Do not lock into a vector database until measured.
- Metadata filters are deterministic and applied before semantic ranking.
- Hybrid score is calibrated on labelled query/relevance pairs, not hand-waved weights.
- Search result includes source ID, source version, exact locator, indexed timestamp and freshness state.
- Deleted/revoked source content is tombstoned immediately and excluded from retrieval while physical cleanup runs.

### 9.5 Finance boundary
Finance ingestion, storage, calculations and query resolution live behind a deterministic Finance API. General model context, embeddings, shared retrieval, logs and agent scratch cannot contain raw Finance rows. Permitted answer data is a narrow computed result with provenance and policy authorisation. Enforce with separate process/database/key where the threat model requires it; add negative tests that inspect every model input and index.

## 10. Intelligence Gateway and model runtime

### 10.1 Gateway responsibilities
- Classify task type and risk.
- Select a model using measured capability/quality/latency/resource profile.
- Construct minimal authorised context.
- Enforce token, time, memory and tool budgets.
- Validate structured output and citations.
- Support cancellation, streaming and bounded retry.
- Record model/runtime/version metadata.
- Return explicit refusal, uncertainty or unsupported-language status when evidence is insufficient.

### 10.2 Task classes and initial routing policy
| Task | Default route | Verification |
|---|---|---|
| Exact arithmetic/date/format | Deterministic code | Unit/property tests |
| Search/query extraction | FTS + small local model if semantic parsing needed | Query and retrieval tests |
| Classification/tagging | Small fast local model or deterministic parser | Per-class precision/recall |
| OCR/transcription | Specialist local OCR/STT engine | Character/word error rate |
| Summarisation | Small/medium local model; cite input spans | Coverage and factuality |
| Complex analysis/planning | Best measured main local model | Golden tasks and reviewer rubric |
| Tool/action proposal | Local model produces typed proposal only | Schema + policy + approval |
| High-impact answer | Deterministic facts plus strong local reasoning where allowed | Independent checks and explicit uncertainty |

No model decides its own permission or selects arbitrary tools. Routing policy is deterministic, versioned and inspectable. The user can see which model answered.

### 10.3 Runtime selection
Candidate runtime arms:
1. MLX / MLX Swift — likely strong Apple Silicon integration; evaluate packaging, supported architectures, model ecosystem, memory pressure and maintenance.
2. llama.cpp — broad model/quantisation coverage and mature portability; evaluate speed, tool-call reliability and integration complexity.
3. Apple-native Core ML / current Apple on-device model APIs — evaluate supported model size, export constraints, language/task coverage and future iOS parity.
4. Other runtimes only if they demonstrate a measurable advantage and acceptable maintenance/security.

**Architecture recommendation:** keep `InferenceRuntime` protocol independent of the UI, Core API and domain modules. The first production runtime is selected only after target-Mac benchmarks. A second runtime is not added merely for theoretical redundancy. No cloud adapter is shipped.

### 10.4 Model descriptor and lifecycle
Descriptor includes model artifact hash, license, architecture, quantisation, context, tokenizer, supported modalities, structured-output/tool capability, language scores, measured RAM, cold/warm load time, TTFT, prefill/decode throughput and runtime compatibility.

Lifecycle: `not_installed → validating → available → loading → ready → busy → unloading/failed`. Validate model hash and license metadata before use. Limit concurrent model residency; prioritize interactive requests; pause background inference under resource pressure. A model switch must be observable and not corrupt session state.

### 10.5 Context and prompt security
- Context is assembled from typed, authorised records, not arbitrary concatenated files.
- Instructions, user requests and retrieved source data remain separate fields.
- Retrieved content is quoted/labelled as untrusted.
- No connector token, filesystem path beyond need, or unrelated personal memory is sent to model.
- Output schema validation is mandatory for tool proposals and structured extraction.
- Model output is never treated as proof; factual claims need evidence.

## 11. Durable workflow and agent design

### 11.1 Why a purpose-built local engine
Atlas is a single-owner desktop system with a local database and no distributed service requirement in the first release. A small deterministic workflow engine avoids a permanent server dependency and keeps all state inspectable. Evaluate Temporal or a comparable durable engine only if future multi-host execution, distributed workers or workflow complexity justify its operational cost. Do not embed an agent framework as the system architecture.

### 11.2 Workflow representation
A workflow is a versioned DAG/state machine. Each step declares input/output schema, idempotency key, retry class, deadline, required capability, resource budget, checkpoint strategy and compensation (if any). Dependencies are explicit; independent steps may run concurrently; conflicting writes are serialized.

### 11.3 Durable execution algorithm
1. Transactionally create run and step records.
2. Worker claims eligible step using lease with expiry.
3. Validate current policy, source version and input fingerprint.
4. Execute bounded step; checkpoint progress.
5. Persist output to staging and validate checksum/schema.
6. Commit output reference and step completion atomically.
7. Emit outbox event in same transaction.
8. Downstream step becomes eligible only after committed dependency.
9. Expired leases are reclaimed; idempotency prevents duplicate output.
10. Terminal state and receipt are durable and queryable.

External actions use a separate action idempotency key and reconciliation query; never assume exactly-once delivery from a remote provider.

### 11.4 Agent workforce
Use specialist capabilities, not a swarm of autonomous personalities. Atlas Core remains the sole supervisor. Each specialist has a narrow typed task contract, domain scope, allowed tools, budget and deadline. Delegation cannot broaden authority. A child task returns result plus provenance, not raw restricted records. Start with one coordinator and a small number of deterministic specialist workflows. Add parallel agents only where benchmarks prove improved completion quality or latency.

### 11.5 Approval tiers
- Tier 0: read-only retrieval and local analysis within designation.
- Tier 1: reversible local organisation changes; approval configurable, always audited.
- Tier 2: external communication, calendar changes, file deletion, purchases or sharing; explicit per-action approval.
- Tier 3: financial movement, legal commitments, credential/security changes, destructive bulk operations; deny by default unless a dedicated future policy explicitly enables a narrowly scoped action.
- No agent may approve its own action. Approval expires and is bound to exact payload hash, target and scope.

## 12. Security, privacy and threat model

Threats include malicious prompt injection in email/documents, compromised connector token, malicious local file, model hallucination, cross-domain leakage, rogue/compromised client, local malware, lost device, backup theft, update tampering, workflow replay and remote access abuse.

Required controls:
- Least-privilege connector scopes and per-source designation.
- Keychain-protected credentials; never expose secrets to models.
- Separate Finance store/key/access API; Health locked by default.
- Local model process has no connector credentials and no unrestricted filesystem/network.
- Sandboxed parser and tool execution with explicit allowlists.
- Policy checks before retrieval, model context and action.
- Signed app/update; integrity verification and rollback.
- Authenticated local IPC; client identity and revocation.
- Redacted logs, no raw prompts/content/secrets.
- Rate/resource limits against denial of service.
- Audit records for access decisions, approvals and actions.
- Backup encryption, restore validation and documented retention.
- Dependency pinning, SBOM, vulnerability scanning and release signing.
- Security tests for injection, privilege escalation, replay, data exfiltration and deletion bypass.

### 12.1 Data deletion semantics
Deletion is a coordinated workflow:
1. Mark source/memory revoked immediately and deny retrieval.
2. Enumerate all derived records by provenance lineage.
3. Delete or tombstone observations, facts, graph edges, FTS entries, vectors, summaries, caches and task artefacts.
4. Rebuild affected indexes if deletion cannot be proven in-place.
5. Record completion receipt with counts and residual backup expiry.
6. Apply backup retention/crypto-erasure policy.
7. Verify search and direct-ID lookup cannot retrieve deleted content.

## 13. Observability and diagnostics

Use structured, local-only logs and traces. Include correlation ID, module, operation, state transition, duration, resource class, model/runtime version and redacted error code. Never log message bodies, file names, source text, account identifiers, prompts, embeddings or credentials.

Metrics:
- Request queue delay, TTFT, generation throughput and total latency.
- Retrieval candidate count, recall/precision evaluation, citation validity.
- Ingestion throughput, source coverage, retry rate and time-to-searchable.
- Workflow completion, lease expiry, retry and recovery.
- Peak/steady RAM, CPU/GPU, disk growth, thermal pressure and energy where measurable.
- Connector sync freshness, rate limits and failures.
- Action approval latency, denial and verification outcomes.
- Crash rate, UI hangs, startup and update/rollback success.

All diagnostic exports are user-initiated, previewable and scrubbed.

## 14. Benchmark and acceptance programme

### 14.1 Benchmark protocol
- Actual target machine must be identified by chip, memory, storage, macOS build and thermal/power state.
- Use a fixed, versioned synthetic/sanitised corpus and golden task set.
- Warm and cold runs are reported separately.
- At least 30 measured repetitions for latency distributions where practical; report p50/p95/p99, sample count and confidence intervals.
- Keep model, runtime, quantisation, context, prompt, concurrency and output budget identical in comparative arms.
- Do not compare vendor headline numbers or different prompts as an apples-to-apples result.
- Record raw JSONL, harness commit, environment manifest and result summary.
- Performance CI uses deterministic microbenchmarks; full hardware benchmarks run on target hardware.
- Any optimisation must preserve or improve quality; speed gains with accuracy regression are rejected.

### 14.2 Provisional product SLOs (targets to validate)
These are initial design targets, not measured claims. Revise only with evidence and owner approval.

| Workload | Target on 32 GB planning Mac | Measurement |
|---|---:|---|
| UI interaction | p95 under 100 ms; no main-thread blocking model work | UI instrumentation |
| Warm local simple response | TTFT p95 under 1.5 s | 30+ warm runs |
| Warm complex response | TTFT p95 under 4 s; stream thereafter | 30+ runs |
| Search over initial archive | p95 under 1 s for lexical/hybrid query, excluding cold index rebuild | 100+ queries |
| Local document ingest | Initial archive completes within measured overnight budget; publish actual throughput, no skipped sources | Full corpus |
| Incremental sync/index | New/changed source searchable within 60 s p95 after fetch, excluding provider outage | Change fixtures |
| Job recovery | Resume eligible work within 10 s after Core restart | Crash/restart tests |
| Progress correctness | 100% agreement with persisted completed work units | Restart fault injection |
| Citation validity | ≥99% exact source/locator validity on supported golden set; unsupported cases abstain | Citation evaluator |
| Retrieval quality | Recall@10 ≥0.90 and precision@5 ≥0.80 on labelled in-scope queries | Labelled corpus |
| Factual answer quality | ≥95% supported claims on supported-domain golden set; zero fabricated citations | Human-reviewed evaluation |
| Sensitive leakage | Zero cross-domain leakage in adversarial test suite | Security suite |
| Action safety | 100% of Tier 2/3 test actions blocked until valid approval; zero duplicate external effects in idempotency tests | Policy/fault suite |
| Restart integrity | Zero lost committed outputs and zero duplicate records across fault suite | Automated tests |
| Availability | App/Core recover from ordinary crash/reboot without manual database repair in ≥99.9% test cycles | Repeated fault tests |

The local-model SLOs may be infeasible for a 27B-class model on 32 GB. If so, do not fake compliance: define task-specific quality/latency trade-offs, use a smaller model for fast paths, or revise the hardware profile. The user must see which model answered.

### 14.3 Quality evaluation
- Retrieval: Recall@5/10, Precision@5, MRR/nDCG, stale-source rate, duplicate rate.
- Extraction: precision/recall/F1 per field and document type; OCR character error rate.
- Answer: claim support rate, citation correctness, completeness, calibrated abstention, contradiction handling.
- Tool use: schema-valid proposal rate, correct tool selection, policy compliance, task success, duplicate side effects.
- Languages: separate metrics for English, Dutch and representative non-Latin-script data.
- Robustness: malformed files, contradictory evidence, prompt injection, partial source access, unavailable model, low disk and cancellation.

### 14.4 Benchmark suites
A. **Model/runtime:** task quality, tool-call correctness, structured output, language quality, cold/warm load, TTFT, prefill/decode, peak unified memory, model switch, thermal stability, energy and concurrency.  
B. **Retrieval:** lexical, semantic, hybrid, metadata and multi-hop evidence questions; exact locator and freshness.  
C. **Ingestion:** actual archive inventory, duplicate detection, format coverage, throughput, restart safety, source completeness and incremental changes.  
D. **Workflow:** crash at every state boundary, lease expiry, duplicate event, cancellation, retry, dependency failure and outbox replay.  
E. **Security:** prompt injection, Finance leakage, Health leakage, connector revocation, log scrubbing, backup restore, malicious parser input and action replay.  
F. **UX:** startup, navigation, search responsiveness, accessibility, keyboard/voice flows, approval clarity and recovery comprehension.

## 15. Testing strategy and quality gates

- Unit tests for pure domain logic, parsers, policies, scoring, schemas and migrations.
- Property-based tests for idempotency, state transitions, date/time, deletion lineage and source versioning.
- Contract tests for every module API and connector adapter.
- Integration tests against temporary databases and fake providers.
- End-to-end tests for the first vertical slice: explicitly designated local documents + Mail, read-only question, exact evidence citations.
- Fault injection at every durable workflow boundary.
- Security tests for trust boundaries and adversarial content.
- UI tests for progress, cancellation, approval, memory controls and accessibility.
- Regression suite includes all previously observed user-facing defects, including progress reverting after restart; reproduce before labelling as confirmed defect.
- Migration tests from actual legacy stores with backup, checksums, record-count reconciliation and rollback.

No subsystem is accepted on “it works on my machine”. Each module has entry/exit criteria and a named owner/reviewer.

## 16. Packaging, operations and update lifecycle

- Native signed and notarised macOS distribution.
- Launch at login/auto-start is explicit and configurable; recover Core after reboot.
- One-click update checks signed manifest and artifact integrity before installation.
- Update uses staged replacement and preserves user data.
- Failed update rolls back to last known-good app version without downgrading data schema unsafely.
- Database migrations are backward-compatible across the rollback window or require a verified backup/restore path.
- Model downloads show exact artifact, size, source, hash, license and storage requirement; no hidden download.
- Offline mode is first-class; connector failures do not disable local knowledge or chat.
- Diagnostics show Core health, database integrity, model availability, index state, connector health and backup freshness.

## 17. iOS and worldwide access design

iOS is a client, not a second brain. Domain rules, source-of-truth data and inference remain on owner-controlled Core unless a future owner decision changes local-only policy.

Before enabling remote access, approve a separate ADR and threat model covering:
- Device enrolment, strong authentication, key storage and revocation.
- End-to-end encrypted transport and relay metadata minimisation.
- VPN/mesh versus narrowly scoped encrypted relay; compare usability, NAT traversal, availability and operational burden.
- No public database/model ports; no plaintext relay persistence.
- Device loss, offline cache, cache expiry and remote wipe.
- Queued action semantics and replay protection.
- Global network availability, regional restrictions and failure UX.
- Push notification content minimisation; never leak sensitive content in notification previews by default.

Remote access is a later gated stage. The macOS design must not depend on it.

## 18. Migration and implementation readiness

Before migration:
1. Inventory every legacy app, module, database, file format, credential, index, pipeline stage, consent check, undo journal, audit trail and progress marker.
2. Classify each as **reuse**, **reference-only**, **replace** or **retire**, with evidence and rationale.
3. Map existing records to target schemas and preserve source IDs/provenance where possible.
4. Build read-only importer and reconciliation report.
5. Validate counts, checksums, permissions, duplicate handling and Finance separation.
6. Take encrypted backup and test restore.
7. Run shadow comparison without deleting or mutating legacy data.
8. Obtain owner approval for cutover.
9. Cut over with rollback plan and post-migration verification.
10. Retire old app shells only after data and workflow acceptance.

## 19. Architecture decisions required before implementation

The following ADRs must be completed with options, evidence, decision, consequences and test plan:
- ADR-001: Core language/runtime (Swift vs Python or hybrid), including MLX integration, packaging and maintenance.
- ADR-002: IPC transport (XPC vs authenticated Unix domain socket) and streaming.
- ADR-003: SQLite/GRDB schema, physical database partitioning, encryption and backup.
- ADR-004: Vector index candidate and embedding model; deletion/update correctness.
- ADR-005: Local inference runtime and model family/quantisation based on target hardware.
- ADR-006: OCR, document parsing and local speech stack.
- ADR-007: Connector provider order, auth scopes and source designation UX.
- ADR-008: Workflow engine implementation and process isolation.
- ADR-009: App signing, update, rollback and helper lifecycle.
- ADR-010: Remote iOS access, threat model and offline semantics (before mobile stage only).

## 20. Review checklist — no implementation sign-off until all pass

- [ ] Requirements trace to modules, contracts and tests.
- [ ] All modules have ownership, interfaces and dependency rules.
- [ ] Data schemas, migrations, encryption and backup/restore are specified.
- [ ] Finance and sensitive-data boundaries are enforceable and tested.
- [ ] Connector lifecycle, consent, revocation and hostile-input controls are specified.
- [ ] Model routing, runtime adapter and benchmark harness are specified.
- [ ] Memory lifecycle, evidence, correction, expiry and deletion are specified.
- [ ] Retrieval, indexing, ranking and citation validation are specified.
- [ ] Workflow state machine, checkpoint, idempotency and recovery are specified.
- [ ] Action approval and audit contracts are specified.
- [ ] UI navigation, states, errors and accessibility are specified.
- [ ] Provisional SLOs have an evidence-backed feasibility review.
- [ ] ADRs 001–009 are resolved for the first macOS implementation.
- [ ] Migration and rollback plan is tested on a copy of actual data.
- [ ] Independent reviewer has closed all critical/high findings.
- [ ] Product owner explicitly approves the final baseline.

**Final gate:** this document is a review baseline. It does not authorise coding by itself. Once review comments are resolved, update the design, generate machine-readable API schemas, state-machine specifications, threat model and test plans, then request explicit architecture sign-off.

## References and evidence
- Apple structured data and SQLite guidance: https://developer.apple.com/documentation/technologyoverviews/structured-data-models
- GRDB cross-platform Swift/SQLite library: https://swiftpackageindex.com/groue/grdb.swift
- Reproducible Apple Silicon runtime comparison project (candidate methodology, not an endorsement): https://github.com/eejd/py-apple-silicon-llm-bench
- Apple Silicon local model benchmark archive: https://github.com/john-rocky/apple-silicon-llm-bench
- Durable workflow engine comparison is for future evaluation only; no distributed engine is selected for the local single-user baseline: https://www.workflowbuilder.io/blog/ai-orchestration-tools
