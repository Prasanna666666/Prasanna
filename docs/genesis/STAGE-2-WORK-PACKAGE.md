# Stage 2 Work Package — Foundation Contracts

**Status:** OWNER-AUTHORISED — Stage 2 implementation in PR #8 is under independent review; implementation not yet accepted  
**Product:** One Atlas application  
**Package owner:** ChatGPT — Architect / Integrator  
**Implementer after authorisation:** Claude  
**Owner / final authority:** User  
**Approval basis:** G-O17 accepted by the owner on 2026-11-20; the owner waived the ChatGPT package-acceptance gate and explicitly authorised Stage 2 on 2026-11-20. Implementation acceptance remains subject to independent review; Stage 3 is not authorised.

## 1. Objective

Establish the smallest enforceable Atlas foundation needed for the approved read-only documents-and-Mail workflow: typed capability boundaries, policy enforcement before retrieval/context assembly, durable task state, exact evidence provenance, privacy-safe observability and architecture tests.

This is a bounded foundation step, not a broad rewrite or a general Agent Workforce implementation. The package is designed around the proposed SwiftUI shared macOS/iOS application layer and a versioned Mac-host Atlas Core API; it must be revised if G-O17 is not accepted as proposed.

## 2. Entry gates — all mandatory

The owner has explicitly satisfied the implementation-start authority for this package on 2026-11-20:

1. **G-O17 accepted by the owner:** ACCEPTED. The platform/runtime ADR records the shared Swift/SwiftUI application boundary and defers the Core language to G-O20.
2. **ChatGPT package-acceptance gate:** WAIVED by the owner on 2026-11-20. This waiver allowed Stage 2 implementation to begin; it is not acceptance of the resulting implementation.
3. **Explicit owner authorisation:** GRANTED on 2026-11-20.

These decisions are recorded in PR #7 comment 7037299974 and the owner's subsequent instructions. Do not ask the owner to repeat them. Stage 2 implementation acceptance remains a separate evidence-based review gate; Stage 3 remains unauthorised.

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
- Define a language-neutral, versioned OpenAPI 3.1 + JSON Schema contract as the source of truth. Provide a Python reference server/implementation and contract tests in this stage; generate/validate the Swift client only when a Mac/macOS CI runner is available. The existing chat endpoint is single-response today; define streaming/progress, cancellation, version negotiation and user-safe errors in the contract.
- Define per-client identity and signed-request semantics; do not trust localhost or browser Origin/CSRF headers as native authentication. Local transport should use Unix-domain-socket peer-credential checks plus per-client credentials/signatures, subject to a security review. Remote iOS authentication/topology remains G-O14 and is out of scope.
- Treat clients, including SwiftUI, as untrusted. All policy enforcement occurs in the Core before retrieval and before model-context assembly.

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
- For this bounded slice, durable task state uses a **new, separate, additive encrypted store** with its own dedicated Keychain item; it must be independently deletable for rollback. Do not modify existing databases, schemas or keys. If implementation reveals this cannot be safely isolated, stop and submit a separate migration/storage proposal.
- Do not introduce an unbounded agent scheduler, agent swarm or proactive monitoring system.

**E. Evidence and answer contracts**
- Define passage/source references that can represent an exact document page/block and character span, plus Mail message identity and quoted span for future Mail enablement. Stage 2 proves the contract against synthetic fixtures only; actual stored page offsets, extraction changes and immutable provenance migration are a separate approved package.
- Define answer citations, verification status, language, confidence, limitations and an explicit not-searched/excluded-source list. Include an explicit unsupported-language outcome; do not imply universal OCR/model support. G-019 is the language requirement (numeric zero); G-O19 is the separate source-designation decision (letter O).
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
- No model integration, model routing implementation, model benchmarking, MoE/agent-workforce expansion or autonomous background agents. The owner has since selected MLX and a benchmark-led ~27B main-model direction with automatic task-based switching (G-020); this package does not implement or validate that runtime/model stack. The Python reference implementation here is a contract test/reference surface, not a permanent production Core-language decision; G-O20 remains open.
- No Mail attachment indexing or exposure. G-O18 must be resolved before any attachment processing.
- No actual document/Mail ingestion or search implementation until G-O19 source designation and G-O18 attachment handling are resolved.
- No Finance integration into model context; no raw Finance access, no Finance agent, and no new computed Finance output permissions.
- No Health access or unlock.
- No database consolidation, schema migration, data movement, key rotation, legacy app retirement or branch deletion.
- No packaging/release implementation, update mechanism, backup/recovery release or deployment to the owner's machine.
- No cloud inference, cloud storage of private content or third-party hosted Core.
- No autonomous source-code edits by Atlas itself.

## 4. Proposed contract set (design target, not pre-approved API names)

The source-of-truth contract is language-neutral OpenAPI 3.1 plus JSON Schema, versioned in the repository. Python is the reference implementation for this slice only; it does not decide the long-term Mac-host Core language (G-O20), which must be evaluated separately in light of the owner's MLX direction. Swift client generation/build verification is deferred until a Mac or macOS CI runner is available; it is not a Stage 2 acceptance claim.

Claude should propose the smallest set of typed contracts, avoiding over-abstraction:

- TaskRequest / TaskRecord — objective, initiator, source scope, budget, lifecycle, checkpoints and cancellation.
- SourceDescriptor / SourceGrant — source identity/type, owner designation, sensitivity, permission and expiry.
- CapabilityRequest / CapabilityResult / CapabilityError — typed in-process or API boundary.
- PassageRef / EvidenceRef — immutable source identity, version/hash, page/block/span and exact text reference.
- PolicyDecision — allow/deny, policy version, reason code and permitted scope; default deny.
- AnswerEnvelope — answer, citations, verification, language, confidence, limitations, unsupported-language state and not-searched list.
- ExecutionReceipt — task result, timestamps, idempotency key and audit reference.
- SafeEvent — allow-listed structured telemetry with redaction by construction.

These are conceptual names. Claude must challenge and simplify them against the actual code and language/runtime selected. Do not build a new generic framework if existing mechanisms can be safely adapted.

## 5. Acceptance criteria

Acceptance is evaluated against contract fixtures, Python reference implementation and tests in the available Linux CI/developer environment. Swift/Xcode build or runtime behaviour is explicitly **NOT VERIFIED** until a Mac or macOS CI runner is available. Stop rather than claim a Swift deliverable passed without that environment.

All criteria require reproducible evidence; no “works on my machine” claims.

1. **Policy before retrieval:** automated tests prove no source content is fetched or passed to a model unless a current explicit grant authorises that source type and sensitivity. Default is deny.
2. **Isolation:** synthetic Finance and Health sentinels never appear in general model context, retrieved passages, answer evidence or logs.
3. **Task durability:** restart/fault-injection tests at every lifecycle boundary recover safely or show a terminal/needs-attention state; retries are idempotent; cancellation is honoured.
4. **Evidence contract integrity:** synthetic fixtures prove citations can represent an immutable source/version identifier and exact page/block/span; invalid or stale fixture references fail closed. This does not claim the current ingestion stores these offsets. Actual extraction, stored provenance and schema changes require a separate approved migration package.
5. **Exactness:** deterministic figure/date verification remains in force; tests prove unsupported numbers/dates are not emitted as verified facts.
6. **Mail boundary:** Mail body, headers/metadata, thread context and attachment contents have distinct types/provenance; attachment content remains excluded. No Mail retrieval occurs until its separate gates are resolved.
7. **Redaction:** synthetic sentinel scans find zero question text, document names, message subjects, addresses, passage text, secrets or raw personal data in logs across normal and failure paths.
8. **Architecture:** automated tests enforce dependency direction, no duplicate policy/memory/orchestration implementation, no UI bypass of Core policy, and no model call before policy approval.
9. **Failure transparency:** unavailable Core/model, denied source, incomplete ingestion, truncation, citation failure, timeout and partial work produce explicit user-safe states; no incomplete task is reported complete.
10. **Responsiveness:** measure policy, task and contract round-trip overhead with stubs on a named available machine. Do not run or claim ingestion-load/retrieval benchmarks in this stage; real retrieval/model latency and first-useful-output p50/p95 move to Stage 3 and must be measured on the named target Mac. Existing <2s / <5s targets remain provisional.
11. **No data-risk migration:** no user-data movement, destructive schema migration or single-copy dependency occurs in this package.
12. **Traceability:** every in-scope requirement links to contract/implementation, automated test, CI result and known limitation.
13. **API compatibility and streaming:** contract tests cover version negotiation, safe failure for unsupported client/Core versions, progress/stream events, cancellation and a stable user-safe error taxonomy.
14. **Client identity:** contract and Python reference tests reject missing, invalid and revoked client identity/signatures; no localhost-only or Origin-header trust.
15. **Language disclosure:** AnswerEnvelope carries detected/requested language and confidence; unsupported-language cases are explicitly surfaced and tested.
16. **Policy enforcement boundary:** tests prove policy is enforced in the Core and cannot be bypassed by a client.

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
- The owner's G-O17 acceptance or explicit Stage 2 authorisation is withdrawn or shown to be invalid.
- The chosen runtime cannot support a shared macOS/iOS codebase as required.
- Existing data or keys would need migration or modification.
- A proposed contract weakens G-015, Health isolation, default-deny or local-only inference.
- A test requires real owner data or access to sensitive records.
- The implementation requires remote exposure, third-party hosting or unapproved external side effects.
- The Stage 1 baseline materially differs from current code.
- No Mac/Xcode environment is available when a proposed deliverable or acceptance claim requires Swift build/runtime verification.

## 9. Owner decisions that will be requested later — not blockers to this package review

Do not ask the owner these questions now unless new evidence makes them immediately necessary:

- G-O18: exact mail attachment formats and treatment.
- G-O19: owner-controlled enablement mechanism for Documents and Mail separately.
- G-O05: acceptable backup/key-recovery experience before any release depending on backup.
- G-O14/G-O15: secure worldwide access topology and mobile offline/cache/sync before iOS beta.
- G-O12: exact native packaging/update mechanism before release.

These decisions remain separate gates for the stages/features that depend on them. This package does not resolve them by implication.

## 10. Stage 1 gap traceability and exclusions

This package addresses the policy-before-retrieval and Finance/Health isolation gaps (Stage 1 G-3/G-13), contract-level provenance representation only (part of G-2), context/answer disclosure (G-5), and redacted observability (part of G-9). It does **not** close the consent/word-list gap (G-4), Mac-dependent gaps (G-6 to G-8), backup/key recovery (G-15), actual stored provenance/extraction, ingestion/search, or any source enablement gate.

The first slice has **no user actions or external side effects**. ExecutionReceipt is an audit/result envelope only; approval-binding and action authorization belong to a later Action Runtime stage. Do not implement action execution in Stage 2.

## 11. Approval record

- G-O17 ADR owner acceptance: **ACCEPTED by the owner, 2026-11-20**.
- ChatGPT package-acceptance gate: **WAIVED by the owner, 2026-11-20**. This waiver authorised implementation to start; it did not waive independent implementation review.
- Explicit owner authorisation to start Stage 2: **GRANTED, 2026-11-20**.
- Implementation status: **implemented in PR #8, draft and unmerged; acceptance pending**.
- Independent implementation review: initial three blockers were fixed in PR #8 head `481610f`. Re-review found a remaining read-time revocation gap for zero-citation answers/events (PR #8 review 5992662031); Claude fixed it in `badb884`. Code-level re-review confirms the fix and its regression tests address that finding. Full CI run #864 passed all jobs. The wording correction in review 5992710870 was addressed in PR #8 head `b485e04`. Re-review found one edge case: a task revoked after retrieval but before drafting is described as an already-produced answer being withheld; see review 5992743516. Claude's correction and CI run #871 are pending. macOS Keychain and peer-credential verification remain pending.
- Platform verification: real macOS Keychain behaviour, Keychain prompts/item permissions, macOS `LOCAL_PEERCRED`, target-Mac execution and Swift/Xcode integration remain **NOT VERIFIED**.
- Stage 3: **NOT AUTHORISED**.
- Contract format: **OpenAPI 3.1 + JSON Schema, language-neutral**.
- Reference implementation: **Python; Swift client verification deferred until Mac/macOS CI is available**.
- Task persistence: **separate additive encrypted store with a dedicated Keychain provider; real macOS Keychain path still requires target-Mac verification**.
- Provenance: **synthetic contract fixtures only; stored extraction/provenance changes deferred**.
