# Atlas — Project Genesis Decision Register

**Status:** Consolidated baseline · **Owner:** Product owner  
This register distinguishes explicit owner decisions from architecture recommendations. It must be updated when the owner decides an open item.

## 1. Owner-established decisions

| ID | Decision | Status | Consequence |
|---|---|---|---|
| G-001 | Product identity is Atlas, a digital extension / personal operating system / intelligent chief of staff | DECIDED | Design for sustained personal context and action, not a single-purpose chatbot |
| G-002 | Scope is broad: support life and work domains over time | DECIDED | Capability-based architecture; phased delivery |
| G-003 | Local-only AI inference; no cloud inference or silent fallback | DECIDED | Runtime and connector boundaries must enforce locality |
| G-004 | Unified experience: chat, voice, dashboard, notifications, approvals and activity | DECIDED | Shared session/context and interaction model |
| G-005 | macOS first, designed to adapt to other devices/platforms | DECIDED | Platform-specific features behind adapters |
| G-006 | High autonomy, bounded by owner-controlled approval | DECIDED | Central policy and action runtime |
| G-007 | Useful memory should be retained with review/correction controls, expiry and user deletion | DECIDED | Governed memory lifecycle and provenance |
| G-008 | Highly sensitive information is isolated and requires explicit permission; Health locked by default | DECIDED | Sensitivity-aware retrieval and capability policy |
| G-009 | Important factual conclusions must be traceable to source evidence | DECIDED | Provenance is part of data contracts |
| G-010 | Architecture-first development | DECIDED | Define boundaries and contracts before major implementation |
| G-011 | The existing implementation is not an architectural constraint; choose the best Atlas design. Reuse existing components only where they are the best choice; otherwise redesign or replace. | DECIDED | Audit each mechanism as reuse, reference-only or discard. Existing code/tests remain behavioural and regression evidence. Preserve owner data, keys and history with integrity checks and rollback. |
| G-012 | Response speed and answer accuracy are both critical | DECIDED | Latency and quality are paired release criteria |
| G-013 | There will be exactly one Atlas application. Legacy standalone Finance, Documents, Images and other app shells are obsolete; their useful capabilities/data must be integrated into Atlas | DECIDED | One product identity and UX; internal modules are allowed, separate apps are not |
| G-014 | Atlas is intended to automate the owner's personal and professional work through a unified assistant and coordinated internal capabilities | DECIDED | Design for end-to-end personal workflows, not only chat, search or isolated domain tools |
| G-015 | No AI model or general agent may see raw Finance records; financial answers must be computed deterministically and only approved computed outputs may cross the boundary | DECIDED | Finance remains a deterministic, isolated capability; changing this requires a new explicit owner decision |
| G-016 | Target delivery is one native macOS application with one-click updates | DECIDED | Packaging, integrity verification, update and rollback implementation require an ADR and audit; this is not a claim of current implementation |
| G-O17 | Shared Swift + SwiftUI macOS/iOS application; versioned language-neutral Core API; Core language deferred to G-O20; direct-download Developer ID signed and notarised Mac distribution | ACCEPTED BY OWNER (2026-11-20) | One shared Apple application codebase; Mac-host Core remains behind the versioned API. Stage 2 separately authorised; Stage 3 remains gated. |
| G-017 | Planning/minimum-support profile is a 32 GB Apple-silicon Mac mini | DECIDED (planning profile) | Not yet owner-verified or benchmarked; actual test machine and results must be recorded separately |
| G-018 | Atlas must ultimately provide mobile access through an iOS app, usable worldwide wherever secure connectivity is available | DECIDED | macOS first, then iOS; keep domain logic portable and design secure remote access to owner-controlled Atlas Core without cloud inference. Android is not a target (owner, 2026-11-19) |
| G-019 | Language support and evaluation requirement: Atlas is intended to support English, Dutch and other languages present in the owner's documents. Support is measured per language and reported honestly; no language is claimed as supported until measured. | DECIDED | Evaluate readers, OCR, retrieval, local model and answer quality per language; disclose unsupported paths or inadequate confidence. No fixed language list in code |

## 2. Architecture recommendations

| ID | Recommendation | Status | Rationale |
|---|---|---|---|
| G-R01 | Modular monolith as the target core, with process isolation only where justified | RECOMMENDED | Simpler ownership and integration without sacrificing parser/model isolation |
| G-R02 | Model-independent Intelligence Gateway supporting dense and MoE models | RECOMMENDED | Avoid model lock-in; route by measured task capability |
| G-R03 | Durable, idempotent job/event system for ingestion and proactive monitoring | RECOMMENDED | Restart safety, retries, resumability and responsiveness |
| G-R04 | Shared governed Memory & Knowledge subsystem; domain systems remain authoritative for transactions | RECOMMENDED | Cross-domain context with evidence and clear ownership |
| G-R05 | Central Action Runtime for tool policy, approval, execution and audit | RECOMMENDED | One enforcement point for autonomy |
| G-R06 | Migrate incrementally behind compatibility contracts | RECOMMENDED | Preserve data, working functionality and rollback options |
| G-R07 | Hierarchical Agent Workforce: Atlas Core supervises on-demand personal-domain specialists through durable task contracts | RECOMMENDED | Enables delegation and parallel work without uncontrolled agent swarms |
| G-R08 | Central Agent Registry, task scheduler and policy-enforced tool gateway | RECOMMENDED | Makes role, permission, resource, deadline and lifecycle constraints enforceable |
| G-R09 | Start with a thin personal workflow and a small specialist set; expand by measured value | RECOMMENDED | Proves reliability before adding orchestration complexity |
| G-R10 | Domain-scoped agent context; restricted Finance and Health trust boundaries | RECOMMENDED | Prevents one-app convenience from becoming unrestricted cross-domain access |

## 3. Open decisions requiring investigation or owner input

| ID | Question | Proposed next step | Owner input needed now? |
|---|---|---|---|
| G-O01 | Which local models and runtimes meet quality/latency/memory needs? | Benchmark a representative shortlist on the actual Mac | No; investigate first |
| G-O02 | What storage, full-text, vector and relationship-query stack is appropriate? | Produce a storage/encryption/key-boundary ADR after auditing data volume, query patterns, backup and restore | No |
| G-O03 | Which external sources/connectors should be supported first? | Inventory existing sources and rank by value/risk; current owner direction is local documents read-only, Mail read-only and Calendar read-only/propose-only | Only when prioritising a release |
| G-O04 | What is the multi-device sync and conflict model? | Define offline cache, sync, conflict resolution, queued actions and device-loss behaviour before mobile beta | No; required before mobile beta |
| G-O05 | What backup and key-recovery experience is acceptable? | Owner explicitly deferred this decision; keep the storage/recovery release gate closed until decided and restore-tested | Yes, before release relying on backup |
| G-O06 | What are notification quiet hours and escalation preferences? | Design defaults; ask during notification UX acceptance | Later |
| G-O07 | What are final latency/accuracy thresholds? | Measure baseline and benchmark on target hardware | Yes, after evidence is available |
| G-O08 | What are the first capability priorities after the foundation? | Present ranked roadmap with effort/risk/value after the read-only slice audit | Yes, at roadmap review |
| G-O09 | Confirm the exact first vertical-slice workflow | Owner answered (2026-11-19): read-only question → authorised local documents and mail found → answer with exact source citations. Mail attachment treatment (G-O18) and source designation (G-O19) remain separate design gates. The owner accepted G-O17, waived the ChatGPT package-acceptance gate and explicitly authorised Stage 2 on 2026-11-20 (PR #7 comment 7037299974 and subsequent owner instructions). Stage 2 implementation acceptance remains pending independent review of PR #8; this does not authorise Stage 3. | Owner scope answered; implementation remains gated |
| G-O10 | Which connectors and external actions may agents use, and at what autonomy level? | First-slice local documents and Mail are read-only; Calendar remains read-only/propose-only when separately authorised. Propose least-privilege scopes for each additional connector; no blanket permission | Yes, per connector/action |
| G-O11 | What is the minimum supported machine and OS version? | 32 GB Apple-silicon Mac mini is the planning/minimum profile; benchmark and publish the supported OS after target testing | No; verify before release |
| G-O12 | What native packaging, helper-process and update mechanism will be used? | ADR covering app bundle, helper isolation, footprint, signing/integrity, one-click update and rollback | No; decide before release |
| G-O13 | How are standing rules and legacy `docs/` records mapped to Genesis? | Initial audit completed in Stage 1 (PR #7 comment 7022436618); map records to Genesis requirement IDs during Stage 2 work, retaining historical evidence | No |
| G-O14 | What secure remote-access topology connects the iOS client worldwide to the owner-controlled Atlas Core without violating local-only inference? | Compare owner-controlled VPN/mesh with a narrowly scoped end-to-end encrypted relay only if necessary and explicitly approved. Threat-model device identity/enrolment/revocation, authentication, NAT traversal, relay metadata, regional restrictions and availability. No public database/model ports, third-party inference or plaintext relay storage. Stage 8 is gated on an accepted threat model and ADR; stages 0–7 must not depend on mobile access. | No; ADR and threat model required before stage 8 |
| G-O15 | What is the mobile offline and local-cache policy? | Define which data may be cached, expiry/encryption, queued action semantics, conflict handling and device-loss wipe/revocation | No; required before mobile beta |
| G-O16 | What mobile platform and release support is required? | Target iOS; determine minimum OS version, distribution, push provider/privacy and support policy during mobile planning | No; decide before mobile beta |

| G-O18 | What is the first-slice treatment of mail attachment contents? | Define supported formats, provenance, sensitivity labels and hostile-content tests. Until resolved, attachment contents are not indexed or exposed; answers disclose that attachments were not searched. Mail body, headers/metadata, thread context and attachment contents have distinct source/provenance treatment. | Yes, before implementation |
| G-O19 | How does the owner enable searchable source types? | Default-deny: no source is searchable merely because it exists in storage. Documents and Mail are separate source types, each explicitly enabled through an owner-controlled designation mechanism; the mechanism may be designed at build time. This is not blanket permission. | Yes, before implementation |
| G-O20 | Which language/runtime should implement the Mac-host Atlas Core over time? | Separate evidence-backed ADR after G-O17. Assess Python reuse, packaging/notarisation, performance, security, native library integration, migration cost and testability. G-O17 does not permanently select Python or require an immediate rewrite. | No; investigate before committing to long-term Core implementation |
## 4. Reconciliation with current Atlas implementation

The current implementation may contain separate Atlas, Finance, Documents and Images packages/services, a local Ollama model and a Read/Sort/Group pipeline. These are legacy implementation facts to inspect as possible reuse, reference-only behaviour/regression evidence, or discard—not approved product boundaries or architectural constraints. The target is one Atlas application.

Project Genesis establishes the single-application product boundary and evolves the internal architecture:
- from legacy standalone app shells to one Atlas application with internal domain capabilities;
- from a focused personal app to a personal operating system / chief of staff;
- from one fixed model to a model-independent local intelligence gateway;
- from app/tool-specific orchestration to central capability and policy contracts;
- from the current reader stages to a durable, observable, resumable ingestion pipeline;
- from a chat-first interface to unified chat, voice, dashboard, notifications and approvals;
- from current local Mac operation to macOS-first, cross-platform-ready boundaries.

Do not remove existing security controls or owner data casually. Map each current component to reuse, reference-only or discard; existing tests can serve as regression evidence. Select the best target design even if it replaces the current implementation. Preserve owner data, keys and history through integrity checks and rollback.

**Historical decision reconciliation:** `docs/decisions.md` is preserved unchanged as historical evidence. Its line 162 statement (“no app is private or special”) and line 178 statement (“local AI … private data … is the design”) are superseded by G-015 wherever they conflict. The separate line 32 rule that the developer assistant never accesses the owner's Finance data remains in force.

## 5. Personal Agent Workforce direction

The owner-established outcome is personal and professional work automation inside the single Atlas application. The recommended role catalogue, orchestration and phased delivery are defined once in `TARGET_ARCHITECTURE.md` §13 and the unified roadmap in §11. Do not duplicate the role list here. Finance follows G-015; Health remains locked by default. Consequential actions require the configured approval policy.

## 6. Change log

- 2026-11-19: Initial consolidation of established Project Genesis direction and target architecture recommendations.
- 2026-11-19: Added the personal-work automation direction and recommended Agent Workforce architecture; specialist rollout and first workflow remain subject to review and owner prioritisation.
- 2026-11-19: Owner initially confirmed iOS and Android as future mobile platforms; this was superseded the same day by the owner's direction to drop Android. The committed sequence is macOS first, then iOS only. Secure global access remains gated by remote-access threat modelling and ADR; no cloud inference or hosted Atlas brain is authorised.
- 2026-11-19: Owner confirmed the first read-only workflow includes local documents and Mail. Mail attachments remain excluded by default pending G-O18; document and Mail source types remain separately default-deny pending G-O19.
- 2026-11-19: Added G-019 language support/evaluation requirement and recorded the legacy `docs/decisions.md` conflict with G-015 without modifying the historical file.
- 2026-11-19: Owner relaxed the default-evolve/no-rewrite constraint. Choose the best Atlas architecture; assess existing components as reuse, reference-only or discard, while preserving owner data, keys and history through integrity-checked migration and rollback.
- 2026-11-19: Owner intends the Atlas Core host to be an always-on Mac mini. Treat this as an operating assumption; provide normal reboot/update auto-start and a clear mobile unreachable state. Do not engineer for extreme outage scenarios; retain proportionate security controls for remote access.
- 2026-11-20: Claude technically challenged G-O17 and the Stage 2 package (PR #7 comment 7035425400). ChatGPT reconciled the exact changes: G-O17 now explicitly decides the shared Swift/SwiftUI application layer, Core API boundary and packaging direction; G-O20 separately tracks the future Mac-host Core language. Stage 2 is revised to use OpenAPI 3.1/JSON Schema, Python reference tests, synthetic provenance fixtures, a separate additive encrypted task store, Core-enforced policy, client identity/signatures, streaming/cancellation/versioning, language/confidence disclosure and explicit verification limits. Owner accepted G-O17, waived the ChatGPT package-acceptance gate and explicitly authorised Stage 2 on 2026-11-20. PR #8 implementation acceptance remains pending; Stage 3 is not authorised.
