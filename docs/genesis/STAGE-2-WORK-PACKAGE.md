# Stage 2 Work Package — Foundation Contracts

**Status:** PROPOSED FOR REVIEW — Stage 2 is NOT authorised  
**Product:** One Atlas application  
**Package owner:** ChatGPT — Architect / Integrator  
**Implementer after authorisation:** Claude  
**Owner / final authority:** User  
**Prerequisites:** Accepted G-O17 ADR; ChatGPT acceptance of this bounded package; explicit owner authorisation to begin Stage 2.

## 1. Objective

Establish the smallest enforceable Atlas foundation needed for the approved read-only documents-and-Mail workflow: typed capability boundaries, policy enforcement before retrieval/context assembly, durable task state, exact evidence provenance, privacy-safe observability and architecture tests.

This is a bounded foundation step, not a broad rewrite or a general Agent Workforce implementation. The package is designed around the proposed SwiftUI shared macOS/iOS application layer and a versioned Mac-host Atlas Core API; it must be revised if G-O17 is not accepted as proposed.

## 2. Entry gates — all mandatory

Claude must not start this package until all are true:

1. **G-O17 accepted by the owner:** the platform/runtime ADR is explicitly accepted, or amended and accepted.
2. **ChatGPT package review complete:** this package is accepted by ChatGPT after Claude's technical challenge and any required revisions.
3. **Explicit owner authorisation:** the owner expressly says to start Stage 2 after seeing the accepted ADR and package.

No implied approval from “continue”, PR activity, documentation acceptance, Stage 0/1 completion or resolving G-O18/G-O19. If any gate is missing, Claude remains in review-only mode.

## 3. Scope

### In scope

**A. Baseline and reuse map**
- Reconfirm the Stage 1 audit against the exact implementation commit before changing anything.
- Map the current kit, library, finance, atlas, deployment and host-helper mechanisms to proposed contracts.
- Preserve proven deterministic money/date/unit logic, figure verification, SQLCipher approach pending G-O02, audit patterns, staged-change/undo patterns, sealed hand-over and atomic-publish/idempotency patterns where appropriate.
- Do not assume every audited item is reusable; report drift from the Stage 1 baseline.

**B. Platform and Core boundary**
- Define the shared Swift application/client boundary and the versioned Atlas Core API contract.
- Keep domain/policy contracts independent of SwiftUI views and platform-specific adapters.
- Treat the current Python Core as a Mac-host implementation behind a narrow API initially; no forced Python-to-Swift rewrite in this package.
- Define authenticated local IPC/API semantics for the Mac client. Remote iOS connectivity is specified only as an interface seam; detailed topology remains G-O14 and is out of scope.

**C. Typed capability and policy contracts**
- Define typed request/result/error contracts for capabilities.
- Define source identity, source type, sensitivity, owner designation, provenance and permission grant types.
- Enforce default-deny policy before retrieval and before any content enters model context.
- Documents and Mail remain separate source types. Neither is searchable by default; no blanket source permission.
- Finance raw records and Finance-derived row-level details never enter model/general-agent context. No Finance capability is exposed in this slice. Health is excluded and locked.
- Retrieved content is untrusted data, never authority to grant permission or trigger actions.

**D. Durable task/job contract**
- Define task ID, parent/trigger, objective, scope, budget, deadline, checkpoint, cancellation, retry/idempotency and terminal-state contracts.
- Minimum lifecycle: requested → policy checked → queued/running → retrieved → drafted → verified → completed / partially completed / failed / cancelled / expired.
- Define restart recovery and explicit partial/failure reporting.
- Do not introduce an unbounded agent scheduler, agent swarm or proactive monitoring system.

**E. Evidence and answer contracts**
- Define passage/source references that can resolve to an exact document page/block and character span; Mail message identity and quoted span are represented separately when Mail is later enabled.
- Define answer citations, verification status, limitations and an explicit not-searched/excluded-source list.
- Reuse deterministic figure/date verification; extend only as necessary to verify citations and exact quotations.
- No answer may imply that excluded attachments or disabled source types were searched.

**F. Privacy-safe observability**
- Define structured event names and redaction rules.
- Logs must not contain question text, document/file names, message subjects, email addresses, passage text, raw personal records, secrets or authentication material.
- Provide synthetic sentinel tests proving redaction across success, failure and retry paths.

**G. Architecture enforcement**
- Define dependency direction and module ownership.
- Add architecture/contract tests preventing UI-to-storage bypass, capability-to-capability circular imports, model access before policy checks, and Finance/Health data entering general context.
- Produce a traceability matrix from G-IDs/PRD requirements to contract, test and evidence.

### Explicitly out of scope

- No user-facing UI rebuild or redesign beyond contract compatibility.
- No iOS app implementation, remote-access deployment, VPN/relay, push notifications or offline sync.
- No model/runtime selection, model routing, MoE, agent workforce expansion or autonomous background agents.
- No Mail attachment indexing or exposure. G-O18 must be resolved before any attachment processing.
- No actual document/Mail ingestion or search implementation until G-O19 source designation and G-O18 attachment handling are resolved.
- No Finance integration into model context; no raw Finance access, no Finance agent, and no new computed Finance output permissions.
- No Health access or unlock.
- No database consolidation, schema migration, data movement, key rotation, legacy app retirement or branch deletion.
- No packaging/release implementation, update mechanism, backup/recovery release or deployment to the owner's machine.
- No cloud inference, cloud storage of private content or third-party hosted Core.
- No autonomous source-code edits by Atlas itself.

## 4. Proposed contract set (design target, not pre-approved API names)

Claude should propose the smallest set of typed contracts, avoiding over-abstraction:

- TaskRequest / TaskRecord — objective, initiator, source scope, budget, lifecycle, checkpoints and cancellation.
- SourceDescriptor / SourceGrant — source identity/type, owner designation, sensitivity, permission and expiry.
- CapabilityRequest / CapabilityResult / CapabilityError — typed in-process or API boundary.
- PassageRef / EvidenceRef — immutable source identity, version/hash, page/block/span and exact text reference.
- PolicyDecision — allow/deny, policy version, reason code and permitted scope; default deny.
- AnswerEnvelope — answer, citations, verification, limitations and not-searched list.
- ExecutionReceipt — task result, timestamps, idempotency key and audit reference.
- SafeEvent — allow-listed structured telemetry with redaction by construction.

These are conceptual names. Claude must challenge and simplify them against the actual code and language/runtime selected. Do not build a new generic framework if existing mechanisms can be safely adapted.

## 5. Acceptance criteria

All criteria require reproducible evidence; no “works on my machine” claims.

1. **Policy before retrieval:** automated tests prove no source content is fetched or passed to a model unless a current explicit grant authorises that source type and sensitivity. Default is deny.
2. **Isolation:** synthetic Finance and Health sentinels never appear in general model context, retrieved passages, answer evidence or logs.
3. **Task durability:** restart/fault-injection tests at every lifecycle boundary recover safely or show a terminal/needs-attention state; retries are idempotent; cancellation is honoured.
4. **Evidence integrity:** every citation resolves to the exact immutable source version and page/block/span; invalid or stale citations fail closed. Quoted spans are checked deterministically.
5. **Exactness:** deterministic figure/date verification remains in force; tests prove unsupported numbers/dates are not emitted as verified facts.
6. **Mail boundary:** Mail body, headers/metadata, thread context and attachment contents have distinct types/provenance; attachment content remains excluded. No Mail retrieval occurs until its separate gates are resolved.
7. **Redaction:** synthetic sentinel scans find zero question text, document names, message subjects, addresses, passage text, secrets or raw personal data in logs across normal and failure paths.
8. **Architecture:** automated tests enforce dependency direction, no duplicate policy/memory/orchestration implementation, no UI bypass of Core policy, and no model call before policy approval.
9. **Failure transparency:** unavailable Core/model, denied source, incomplete ingestion, truncation, citation failure, timeout and partial work produce explicit user-safe states; no incomplete task is reported complete.
10. **Responsiveness:** measure first-useful-output and typical-answer p50/p95 under idle and ingestion load on a named machine. Existing <2s / <5s targets remain provisional until a baseline is measured; do not claim they pass without owner-target hardware evidence.
11. **No data-risk migration:** no user-data movement, destructive schema migration or single-copy dependency occurs in this package.
12. **Traceability:** every in-scope requirement links to implementation, automated test, CI result and known limitation.

## 6. Required Claude deliverables

- Technical challenge of G-O17 ADR and this package, with exact corrections and evidence.
- Updated architecture/contract diagram and dependency map.
- Current-code reuse/adaptation/discard matrix, reconciled against the Stage 1 audit.
- Typed contract definitions and API versioning proposal.
- Threat/privacy review, especially default-deny retrieval, hostile document/mail content, Finance/Health isolation and log redaction.
- Test plan with exact commands, synthetic fixtures, fault injection and expected outputs.
- Benchmark plan and baseline; clearly distinguish developer machine, CI and owner target Mac.
- Migration/rollback plan. This package should be additive and reversible; if any schema change is unavoidable, stop and seek a separate approved migration package.
- Changed paths, commit/PR, exact tests and CI evidence, limitations and unresolved decisions.

## 7. Risks and containment

| Risk | Containment |
|---|---|
| Existing Python architecture differs from Stage 1 baseline | Reconfirm commit and report drift before changes |
| Framework/API choice forces a broad rewrite | Keep a narrow versioned Core API; no big-bang rewrite |
| Permission check occurs after retrieval | Make policy evaluation a mandatory capability boundary and test the call order |
| Sensitive source leaks through generic document search | Default-deny source grants and synthetic Finance/Health canaries |
| Task retries duplicate work | Stable task/idempotency keys, checkpoints and fault-injection tests |
| Logs leak personal content | Allow-listed structured events and sentinel scans |
| Contract design grows into a platform rewrite | Limit to the first read-only workflow and required enforcement points |
| Rollback risks existing data | Additive changes only; no data movement or destructive migration |

## 8. Stop conditions

Claude must stop and report before proceeding if:
- G-O17 or package authorisation is absent.
- The chosen runtime cannot support a shared macOS/iOS codebase as required.
- Existing data or keys would need migration or modification.
- A proposed contract weakens G-015, Health isolation, default-deny or local-only inference.
- A test requires real owner data or access to sensitive records.
- The implementation requires remote exposure, third-party hosting or unapproved external side effects.
- The Stage 1 baseline materially differs from current code.

## 9. Owner decisions that will be requested later — not blockers to this package review

Do not ask the owner these questions now unless new evidence makes them immediately necessary:

- G-O18: exact mail attachment formats and treatment.
- G-O19: owner-controlled enablement mechanism for Documents and Mail separately.
- G-O05: acceptable backup/key-recovery experience before any release depending on backup.
- G-O14/G-O15: secure worldwide access topology and mobile offline/cache/sync before iOS beta.
- G-O12: exact native packaging/update mechanism before release.

These decisions remain separate gates for the stages/features that depend on them. This package does not resolve them by implication.

## 10. Approval record

- G-O17 ADR owner acceptance: **PENDING**.
- ChatGPT package review: **PENDING Claude technical challenge and reconciliation**.
- Explicit owner authorisation to start Stage 2: **NOT GRANTED**.
- Implementation status: **NOT STARTED**.
