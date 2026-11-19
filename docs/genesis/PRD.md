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
