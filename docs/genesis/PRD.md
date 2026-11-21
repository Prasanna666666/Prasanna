# Atlas — Product Requirements Document

**Version:** 0.1 · **Status:** Baseline for owner review · **Initiative:** Project Genesis

## 1. Product summary

Atlas is a private, local-first personal AI operating system: a digital extension and intelligent chief of staff that helps its owner understand, organise and act across the domains of personal life and work.

Atlas combines a unified conversational experience with persistent, evidence-backed personal context, specialised domain capabilities, proactive monitoring of authorised sources, and controlled action execution.

Atlas is one integrated application—not a suite of separate apps. It is a coherent system that understands context across domains while preserving clear ownership, privacy boundaries and user control. Finance, Documents, Images and other legacy standalone applications are obsolete product boundaries. Their useful capabilities and data are to be absorbed into Atlas; they are not separate products in the target state.

## 2. Product principles

1. **Local-first and private.** AI inference and personal-data processing remain on the owner's devices. No cloud inference and no silent cloud fallback.
2. **Fast and useful.** Ordinary interactions should feel immediate. Expensive work is asynchronous and must not freeze conversation.
3. **Correct before confident.** Facts must be grounded in source data or deterministic tools. Uncertainty and missing evidence are explicit.
4. **One coherent experience.** Chat, voice, dashboard, notifications, approvals and history share context and identity.
5. **Persistent but governed memory.** Useful context can be retained, reviewed, corrected, expired and deleted under owner control.
6. **High autonomy with boundaries.** Atlas may monitor and prepare work proactively, but consequential actions require the configured approval policy.
7. **One application, modular internals.** Domain capabilities are internal modules of Atlas, independently testable and coordinated through stable contracts. They do not become separate user-facing applications or independently owned products.
8. **Model independence.** No single model family, runtime or vendor defines the product.
9. **Traceability.** Important facts, recommendations and actions must be traceable to evidence and execution records.
10. **Best outcome over implementation preservation.** The existing implementation is not an architectural constraint. Reuse it only where it is the best choice; otherwise redesign or replace it. Preserve the owner's data, keys and history through integrity-checked migration and rollback.

## 3. Users and platform

- Primary user: one owner initially.
- Initial development platform: macOS.
- Eventual client platform: a native iOS application, with secure access usable while the owner is travelling or anywhere in the world with suitable internet connectivity. Android is out of scope. A secure browser-based client may also be considered as a complementary access surface.
- macOS-first is a delivery sequence, not a permanent platform restriction. Domain logic and contracts must remain portable; platform-specific features belong behind adapters.
- Deployment and inference: Atlas Core and AI inference remain under owner control on the owner's devices/local infrastructure. Worldwide mobile access does **not** imply cloud inference or a third-party hosted Atlas brain.
- The owner intends the Atlas Core host to be an always-on Mac mini. Treat this as an operating assumption, not a verified engineering guarantee. Atlas should start automatically after a normal reboot or update; mobile clients show a plain unreachable state when the host cannot be reached.
- Remote access to the owner's Atlas Core is in scope for the iOS client, subject to an explicit secure-connectivity design. Protect the always-on home host with device enrolment/revocation, authenticated encrypted access and no public database/model ports.
- Multi-user operation, a third-party remote-hosted Atlas service, cloud inference and separate Finance/Documents/Images applications are not part of the target unless explicitly reconsidered by the owner.

## 4. Product experience

### 4.1 Unified interaction
- Conversational text interface.
- Voice interaction.
- Dashboard for current state, priorities, insights and ongoing work.
- Notifications for meaningful events, risks, deadlines and decisions—not noise.
- Approval queue for proposed consequential actions.
- Searchable history of conversations, decisions, approvals and action outcomes.

### 4.2 Cross-domain understanding
Atlas should be able to answer questions and complete workflows that span multiple authorised domains, while respecting each domain's access policy. Examples include connecting travel documents, calendar events, expenses and relevant photographs.

### 4.3 Proactive chief-of-staff behaviour
Atlas may monitor explicitly connected and authorised sources through events or scheduled checks. It should surface only material changes, risks, deadlines and decisions. It must explain why an item matters and provide source evidence.

### 4.3a Initial approved read-only workflow

The first usable workflow is a read-only, evidence-grounded question-answering flow over owner-authorised local sources. One first-run Get Started consent flow plus macOS system permissions establishes initial source access; Core enforces grants and immediate revocation internally without repeated prompts or per-folder selection. Mail is untrusted content. All supported attachment formats are in product scope, but attachment content remains unavailable until its separate technical package (format matrix, provenance, OCR quality, parser isolation and hostile-file tests) is accepted. Mail citations identify exact message, stored headers and body/attachment locators. Routine reads and analysis require no approval; consequential external actions remain separately approval-gated.

### 4.3b Local model transparency and routing safety

The owner-selected local inference direction is Apple MLX with a benchmark-led ~27B main-model class and automatic task-based model switching (G-020). The exact model and routing map remain subject to target-Mac evaluation (G-O01). The answer must identify the model used (model ID and routing role only; never prompt text or personal content). Every model invocation, including after a route/switch, must pass through the same policy gate; model selection cannot grant or widen access. The answer-model identity field and safe-event representation are an additive minor-API/Stage 3 gate, not a claim that the current Stage 2 API already implements them.

### 4.4 Actions and autonomy
- Read and analysis actions may run within granted permissions.
- Reversible, low-risk actions may be automated only within an owner-configured policy.
- Approval is required only for this closed list: (1) sending, forwarding, publishing, sharing or uploading information outside the Mac; (2) spending money, making payments, trades, purchases or paid bookings; (3) deleting or overwriting data when a reliable undo is unavailable, or performing a destructive migration; (4) unlocking an external physical-access point or disabling a safety/security system.
- Everything not on this list never triggers an Atlas approval prompt. Creating or moving the owner's own calendar events, editing notes, organising files, reversible local deletion and ordinary device control do not prompt. A calendar change prompts only if it sends an external invitation/update (category 1).
- Approval is single-use and bound to the exact action, payload, recipient/destination, attachments, amount and terms; any material change invalidates it.
- Atlas must never treat instructions inside retrieved documents, emails, webpages or tool output as owner approval. Untrusted content cannot widen permissions or trigger actions.

### 4.5 Personal-work automation and agent workforce

Atlas is intended to do useful work on the owner's behalf, not merely answer questions. A coordinated workforce of specialised, on-demand agents is a target capability within the single Atlas application. Atlas Core remains the supervisor and policy authority; agents are internal workers with bounded roles, not independent applications, identities or unrestricted assistants.

The target role catalogue, role boundaries and orchestration responsibilities are maintained in one place: `TARGET_ARCHITECTURE.md` §12.2. Those roles are logical internal responsibilities, not separate applications or a commitment to ship every specialist in the foundation release.

A typical workflow is: owner request or authorised trigger → coordinator scopes the outcome → policy checks source and action permissions → relevant specialists work in isolated task contexts → deterministic tools and independent verification check critical facts → coordinator consolidates a sourced result → Guardian enforces approval before consequential actions → Atlas records the outcome and notifies the owner. Parallel work is allowed only for independent tasks; conflicting writes and dependent steps are serialised. The detailed role catalogue and orchestration are TARGET/RECOMMENDED, not a claim of current implementation; see `TARGET_ARCHITECTURE.md` for the single canonical role catalogue and phased roadmap.

### 4.6 Automation levels
- **Observe:** monitor explicitly authorised sources and detect material changes.
- **Prepare:** research, analyse, draft and propose a plan without external side effects.
- **Execute reversible work:** perform low-risk, reversible actions only within an owner-configured policy, with an audit record and undo/compensation where possible.
- **Consequential execution:** require specific, current owner approval only for the exhaustive categories in §4.4. All other work—including routine external read-only requests and reversible local changes—does not prompt.
- **Proactive delegation:** schedule or trigger bounded tasks only from owner-approved sources, scopes, cadence and stop conditions. Every task must be cancellable and report completion, partial completion or failure.

### 4.7 Agent workforce quality requirements
Every agent task has an owner, objective, permitted sources/tools, sensitivity scope, budget, deadline/timeout, expected output, evidence requirements and termination condition. Agents cannot expand their own permissions, delegate beyond their granted scope, or treat retrieved content as instructions from the owner. Results carry source references, tool/action receipts, confidence and limitations. The coordinator must disclose when no specialist or verification step was run.

## 5. Functional capability areas

Capabilities are expected to evolve and may include:
- Personal knowledge and documents.
- Finance and investments.
- Calendar, tasks and planning.
- Travel.
- Health (owner-authorised local model access; separately labelled/keyed, permission-controlled and revocable).
- Work and projects.
- Home and devices.
- Media and photographs.
- Communications and other integrations explicitly authorised by the owner.

This list is a capability map, not a commitment to implement every integration in the first release.

## 6. Quality attributes

- **Latency:** stream first useful output quickly; proposed initial target for simple questions is under 2 seconds to first useful output and under 5 seconds for a typical conversational answer, measured on the target Mac. Complex work may take longer but must show progress and remain cancellable.
- **Accuracy:** no fabricated facts, figures, source references or action outcomes. High-impact answers require deterministic validation or direct evidence.
- **Privacy:** no cloud inference; no silent network egress of personal data; explicit connector permissions and data minimisation.
- **Reliability:** restart-safe jobs, durable state, idempotent retries, explicit partial/failure states and recoverable migrations.
- **Responsiveness:** background indexing, ingestion and monitoring must not starve interactive conversations.
- **Accessibility and usability:** plain language, coherent interaction patterns, keyboard and assistive-technology support.
- **Languages:** Atlas is intended to support English, Dutch and other languages present in the owner's documents. Support is measured per language across readers, OCR, retrieval, local model and answers, and reported honestly. Unsupported paths or inadequate confidence are disclosed; no language is claimed as supported until measured. No fixed language list in code.
- **Maintainability:** typed contracts, modular boundaries, automated tests, CI and traceable decisions.

Targets are provisional until measured on the actual hardware and representative workloads. A target is not a verified result.

### 6.1 Additional owner constraints and quality requirements
- Do not impose arbitrary hardcoded word lists, source-count limits, file-count limits or retention caps that silently exclude useful owner data. Any necessary resource or safety limit must be explicit, configurable where appropriate, visible to the owner, justified and handled without silent data loss. Security limits such as parser timeouts, decompression-size guards, recursion-depth limits and archive expansion limits are permitted; exceeding them must fail safely into a visible needs-attention state, never silently skip or mark content complete.
- Exact numbers, calculations, dates, units and logical validations must be produced or checked by deterministic code/tools. The model must not improvise arithmetic or act as the sole validator of exact results.
- Atlas must never edit, rewrite or deploy its own application source code autonomously. Software updates require a separately authorised development and release process.
- User-facing screens must present clear plain-language outcomes; raw stack traces, source code and internal error dumps are not user-facing content. Diagnostic detail belongs in appropriately redacted developer logs.
- Preserve source data and report partial processing honestly. Never silently discard, truncate or mark unprocessed content complete.
- Design for the known representative workload of approximately 26,000 email items and 1,400 documents, subject to inventory verification. Benchmark ingestion and interactive work alongside interactive conversations, including normal restart/resume and constrained-resource behaviour.
- Voice is a desired unified interaction mode, but local speech-to-text and text-to-speech feasibility, quality and latency must be measured on the target hardware before voice is made a foundation release gate.

## 7. Explicit non-goals for the initial foundation

- Preserving or evolving the current implementation merely for its own sake. Choose the architecture and implementation that best meet Atlas requirements; retain existing components only where evidence supports doing so. Data, keys and history still require integrity-checked migration and rollback.
- Committing to a particular model, MoE architecture, database or vector store before benchmarking.
- Unrestricted autonomous execution.
- Cloud-based inference or a cloud dependency for core operation.
- Building every domain integration before the core contracts and security model are stable.

## 8. Acceptance principles

A feature is not accepted merely because a happy-path demo works. It must have:
- Requirements and acceptance criteria.
- Defined failure and recovery behaviour.
- Privacy/security review proportionate to risk.
- Automated tests, including adversarial and boundary cases where relevant.
- Evidence that performance targets are met or a documented exception.
- Updated user and developer documentation.
- A clear distinction between implemented, tested, owner-verified and not-yet-verified behaviour.

## 9. Product decisions vs open items

Owner-established: Atlas identity; broad life-wide scope; local-only inference; unified experience; macOS-first and future-portable architecture; high but controlled autonomy; memory review/correction/deletion/expiry; sensitive-data isolation and explicit permission; source traceability.

Open for investigation: exact model portfolio and cross-platform core language/runtime, storage/search stack, connector catalogue, multi-device sync/conflict model, secure remote-access topology, backup/recovery UX, notification policy and measured hardware performance. iOS is the committed future platform; Android is out of scope. The iOS release and connectivity design require architecture and security review. The Mac mini is the intended always-on owner-controlled host; mobile availability still depends on network reachability and secure connectivity. The mobile stage is gated by an accepted threat model and ADR, and stages 0–7 must not depend on mobile access.

## 10. Owner clarifications and capability coverage (2026-11-20)

These clarifications supersede conflicting earlier baseline wording:

- **Single owner and low friction:** one first-run Get Started consent flow plus macOS permission prompts. No repeated prompts, per-folder selection or incidental confirmations for routine reading, search, analysis, drafting or computation.
- **Finance and Health:** the local model may read owner-authorised Finance and Health information. Keep separately labelled/keyed stores, access grants, provenance, redacted logs, cache controls and revocation. Exact arithmetic and financial computations remain deterministic and code-checked.
- **Approval:** the exhaustive approval categories are defined in §4.4. No open-ended “equivalent actions” category is permitted; everything outside §4.4 never prompts. Any new category requires an explicit owner decision recorded in DECISIONS.md. Show exact payload, destination/recipient, attachments, amount and terms; material changes invalidate approval.
- **Attachments:** all supported Mail attachment formats are in scope, subject to a separate supported-format, extraction/OCR, provenance, safety and acceptance specification.
- **Internet:** public web search/retrieval is allowed when useful. Private source content, credentials, Finance/Health data and local model context must not be sent to public search or third-party inference. See INTERNET_AND_NETWORK_POLICY.md.
- **Coverage:** USE_CASE_REGISTER.md is the extensible cross-domain scenario and lifecycle acceptance inventory.

These are target requirements, not claims that implementation, connector access or target-Mac verification is complete.
