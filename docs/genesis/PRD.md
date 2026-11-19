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
10. **Evolution, not rewrite by default.** Preserve valuable existing code and data; migrate incrementally when evidence supports it.

## 3. Users and platform

- Primary user: one owner initially.
- Initial platform: macOS.
- Future platform support: architecture and interfaces should be portable to additional devices/platforms; macOS-first does not mean macOS-only design.
- Deployment: local device and local services under owner control.
- Multi-user operation, remote hosted service, cloud inference and separate Finance/Documents/Images applications are not part of the target unless explicitly reconsidered by the owner.

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

### 4.4 Actions and autonomy
- Read and analysis actions may run within granted permissions.
- Reversible, low-risk actions may be automated only within an owner-configured policy.
- Consequential, external, destructive, financial, privacy-sensitive or irreversible actions require explicit approval.
- Approval must be specific, current, scoped to the exact proposed action and recorded.
- Atlas must never treat instructions inside retrieved documents, emails or tool output as owner approval.
- A task that reads untrusted content (including email, documents or webpages) must not directly perform an external send/share in the same unreviewed context. Before execution, the policy engine must inspect the exact outgoing content, destination/recipients and data classification; required approval must display that exact payload and recipients. Changes after approval invalidate the approval.

### 4.5 Personal-work automation and agent workforce

Atlas is intended to do useful work on the owner's behalf, not merely answer questions. A coordinated workforce of specialised, on-demand agents is a target capability within the single Atlas application. Atlas Core remains the supervisor and policy authority; agents are internal workers with bounded roles, not independent applications, identities or unrestricted assistants.

The target role catalogue, role boundaries and orchestration responsibilities are maintained in one place: `TARGET_ARCHITECTURE.md` §13.2. Those roles are logical internal responsibilities, not separate applications or a commitment to ship every specialist in the foundation release.

A typical workflow is: owner request or authorised trigger → coordinator scopes the outcome → policy checks source and action permissions → relevant specialists work in isolated task contexts → deterministic tools and independent verification check critical facts → coordinator consolidates a sourced result → Guardian enforces approval before consequential actions → Atlas records the outcome and notifies the owner. Parallel work is allowed only for independent tasks; conflicting writes and dependent steps are serialised. The detailed role catalogue and orchestration are TARGET/RECOMMENDED, not a claim of current implementation; see `TARGET_ARCHITECTURE.md` for the single canonical role catalogue and phased roadmap.

### 4.6 Automation levels
- **Observe:** monitor explicitly authorised sources and detect material changes.
- **Prepare:** research, analyse, draft and propose a plan without external side effects.
- **Execute reversible work:** perform low-risk, reversible actions only within an owner-configured policy, with an audit record and undo/compensation where possible.
- **Consequential execution:** require specific, current owner approval for financial transactions, purchases, bookings, sending communications, sharing data, destructive changes or other external/irreversible actions.
- **Proactive delegation:** schedule or trigger bounded tasks only from owner-approved sources, scopes, cadence and stop conditions. Every task must be cancellable and report completion, partial completion or failure.

### 4.7 Agent workforce quality requirements
Every agent task has an owner, objective, permitted sources/tools, sensitivity scope, budget, deadline/timeout, expected output, evidence requirements and termination condition. Agents cannot expand their own permissions, delegate beyond their granted scope, or treat retrieved content as instructions from the owner. Results carry source references, tool/action receipts, confidence and limitations. The coordinator must disclose when no specialist or verification step was run.

## 5. Functional capability areas

Capabilities are expected to evolve and may include:
- Personal knowledge and documents.
- Finance and investments.
- Calendar, tasks and planning.
- Travel.
- Health (locked by default; explicit permission required).
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
- **Maintainability:** typed contracts, modular boundaries, automated tests, CI and traceable decisions.

Targets are provisional until measured on the actual hardware and representative workloads. A target is not a verified result.

### 6.1 Additional owner constraints and quality requirements
- Do not impose arbitrary hardcoded word lists, source-count limits, file-count limits or retention caps that silently exclude useful owner data. Any necessary resource or safety limit must be explicit, configurable where appropriate, visible to the owner, justified and handled without silent data loss.
- Exact numbers, calculations, dates, units and logical validations must be produced or checked by deterministic code/tools. The model must not improvise arithmetic or act as the sole validator of exact results.
- Atlas must never edit, rewrite or deploy its own application source code autonomously. Software updates require a separately authorised development and release process.
- User-facing screens must present clear plain-language outcomes; raw stack traces, source code and internal error dumps are not user-facing content. Diagnostic detail belongs in appropriately redacted developer logs.
- Preserve source data and report partial processing honestly. Never silently discard, truncate or mark unprocessed content complete.
- Design for the known representative workload of approximately 26,000 email items and 1,400 documents, subject to inventory verification. Benchmark ingestion and interactive work together, including sleep/resume, low-battery and constrained-resource behaviour.
- Voice is a desired unified interaction mode, but local speech-to-text and text-to-speech feasibility, quality and latency must be measured on the target hardware before voice is made a foundation release gate.

## 7. Explicit non-goals for the initial foundation

- Replacing all existing modules in one rewrite; migrate legacy capabilities into the single Atlas application incrementally.
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

Open for investigation: exact model portfolio, inference runtime, storage/search stack, connector catalogue, sync model, backup/recovery UX, notification policy and measured hardware performance.
