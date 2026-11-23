# Prior conversation recovery — Atlas / Project Genesis

**Captured:** 2026-11-23  
**Purpose:** Preserve project instructions and decisions recovered from prior ChatGPT conversations that are not necessarily represented in GitHub PR comments. This is a structured recovery summary, not a verbatim export of every historical chat. The available conversation-retrieval system returned selected records, not a complete account-wide transcript.

## 1. Roles and collaboration contract

- User is the project manager and decision-maker.
- ChatGPT role: planner, architect, integrator, tester/reviewer in the planning/review sense; challenge assumptions, identify conflicts, review architecture and documentation, and coordinate a professional handshake with Claude.
- Claude role: developer, code implementer, tester, debugger and maintainer.
- User is the trigger/notification point, not the manual relay for every technical exchange.
- Exchanges and review handoffs should happen on the GitHub PR so decisions, evidence, and responses remain auditable.
- Notify the user when documentation is ready for review.
- Genesis documents are the authoritative planning/architecture source; PR #7 was established as the collaboration/audit channel before the work moved to shared PR #8.

## 2. Explicit owner constraints

- 2026-11-18: evolve Atlas; scope the product broadly; high autonomy; local privacy; one unified experience; architecture-first development; macOS-first; challenge conflicts before implementation.
- 2026-11-18: documentation and design first; do not code until reviewed/approved; rebuilding Atlas is acceptable if architecture warrants it.
- 2026-11-19: “You are not allowed to touch code”; documentation, architecture and reviews only; Claude handles coding, testing, debugging and maintenance.
- 2026-11-19: consolidate to one Atlas app; other apps are obsolete as standalone products; remove redundancy, but document roles, interactions, resolutions and handshakes.
- 2026-11-19: consolidation, migration, retirement and gap analysis are developer actions; no destructive cleanup before architecture review and approval.
- 2026-11-19: exchanges should happen on the PR; the user is only the trigger/notification.
- Therefore, this recovery and its follow-up must remain documentation/review work. Do not modify application code, tests, build/configuration, or resolve review threads without explicit owner authorization.

## 3. Product and architecture direction

- Atlas is the product; Genesis is the internal architecture/planning initiative.
- The goal is a unified personal AI assistant / chief-of-staff application, not a collection of disconnected apps.
- One Atlas Core coordinates specialist capabilities/agents and owns orchestration, permissions, memory/knowledge, model/runtime management, background jobs, approvals, evidence, failure recovery and user control.
- Product scope discussed includes Chief of Staff, personal knowledge, finance, documents, research, work, travel, health, home, communications and Guardian/safety capabilities.
- The architecture should support specialist agents, task delegation, orchestration, proactive monitoring, local model/resource management, memory isolation, approvals, failure recovery and user control.
- Build macOS first, while designing architecture and interfaces to be adaptable to other devices/platforms later.
- Local-only AI/inference and privacy were core directions. Cloud inference was explicitly out of scope in the prior product direction.
- High autonomy is a product aspiration, but autonomy must be bounded by approval, permission, auditability and recovery rules; “high autonomy” does not mean unapproved destructive or sensitive actions.
- Historical Stage 0 was complete; Stage 1 accepted/closed; Stage 2 was initially unauthorized, then later authorized after the owner accepted G-O17 and waived the package-acceptance gate. The authoritative decision trail is in PR #7/#8 archives; do not overwrite the chronology with a single timeless status.

## 4. Architecture risks and prior review positions

The earlier architecture review identified:
- Critical Finance privacy boundary and isolation requirements.
- Health and other sensitive domains require explicit privacy boundaries and controlled sharing.
- Backup/restore and encryption-key recovery are critical, not optional operational details.
- Performance targets were unproven; benchmark on target owner hardware before treating thresholds as acceptance facts.
- First-release scope was too broad; define a thin vertical slice and stage delivery.
- Reuse existing consent, undo, audit and ingestion capabilities instead of duplicating them.
- One application may use justified hidden workers; “one app” does not forbid background processes where architecture requires them.
- Reduce memory scope and avoid premature broad memory retention.
- Finance/Health migration, connectors, backup/export, device acceptance, conversation/activity/search, approval reachability, Stage 3–8 acceptance, native automation/watchers and local model runtime need explicit acceptance and evidence.
- Local-only inference needs target-Mac proof, not just a configuration statement.
- Requirements should distinguish test presence, CI evidence, real integration evidence, target-device verification and owner acceptance.

## 5. UI/UX direction recovered from 2026-11-22

- The user criticized the proposed interface direction as “Boring” and the app as too crowded.
- The accepted visual north star was: **immersive, premium, futuristic, expressive, never cluttered**.
- The user explicitly asked to clean up and finalize the Documents and design.
- The user challenged why UI design documentation was being addressed so late.
- Gaps identified in the earlier review included full information architecture, every real screen and state, navigation/interactions, design tokens/system, animation/motion, accessibility, macOS specifications and visual acceptance criteria.
- docs/genesis/UI_UX_SPECIFICATION.md was subsequently completed/committed (ef8ea181) according to the recovered prior conversation, but the implementation was still described as lacking Home, Library, Activity, navigation shell and design system; the app was essentially Get Started, Settings and Conversation at that point.
- Distinguish conceptual screens from real implementation screens. Do not present concepts as shipped or verified product UI.

## 6. Earlier product/AI quality requirements mentioned in planning

A prior assistant planning note proposed targets such as under-2-second first useful output, under-5-second typical response and under-30-second complex task. These are **proposal-level targets only**, not confirmed owner acceptance or measured performance. They must be benchmarked on target hardware before being treated as binding SLOs.

Other proposed quality expectations included:
- Zero fabricated or unsupported action-completion claims.
- Evidence-grounded retrieval and answers.
- Verification and confidence/uncertainty transparency.
- Streaming and responsive interaction.
- Appropriate model/tool routing.
- Persistent context with privacy boundaries.
- Background work isolation and restart-safe jobs.

These must be reconciled against the current canonical PRD/requirements and PR #7/#8 decision history; do not assume every prior assistant proposal was accepted by the owner.

## 7. Automation and agentic workflow concerns

- The user explicitly asked to scrutinize automation connectors and agentic AI workflow quality because they were unsure Claude had implemented them correctly.
- Prior planning described MCP/native APIs/OS/browser adapters behind permissions and approvals. These were architectural proposals, not evidence that integrations were installed, connected or implemented.
- Review end-to-end workflow wiring: discovery, authentication/connection state, scopes, permission evaluation, approval, execution, verification, receipts/audit, retries/idempotency, undo/compensation, failure recovery and revocation.
- Treat a connector marked “connected” or “healthy” as insufficient evidence that its operations are correctly authorized or safely executed.
- Preserve the distinction between product vision, documented architecture, implemented behavior and independently verified behavior.

## 8. Search coverage and limitations

The conversation retrieval performed on 2026-11-23 returned the above selected records from prior Atlas/Genesis conversations dated 2026-11-18 through 2026-11-22. It did not provide a complete transcript export or guarantee all historical chats were indexed. The GitHub archives are a separate, fuller source for PR #6–#10 discussion/review records.

Claude must:
1. Compare this recovery summary with the full PR #6–#10 archives and current Genesis docs.
2. Add every distinct owner instruction, accepted decision, rejected proposal, unresolved conflict and product requirement to a canonical decision/requirements ledger.
3. Preserve provenance and dates; distinguish owner decisions from assistant proposals and Claude implementation claims.
4. Identify missing or conflicting records explicitly rather than infer acceptance.
5. Continue searching repository branches, commits, PRs and available historical sources for omissions.
6. Never claim “all prior chats recovered” based solely on this summary.
