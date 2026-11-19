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
| G-011 | Existing implementation should be evaluated and evolved; no automatic rewrite | DECIDED | Incremental migration and regression protection |
| G-012 | Response speed and answer accuracy are both critical | DECIDED | Latency and quality are paired release criteria |
| G-013 | There will be exactly one Atlas application. Legacy standalone Finance, Documents, Images and other app shells are obsolete; their useful capabilities/data must be integrated into Atlas | DECIDED | One product identity and UX; internal modules are allowed, separate apps are not |
| G-014 | Atlas is intended to automate the owner's personal and professional work through a unified assistant and coordinated internal capabilities | DECIDED | Design for end-to-end personal workflows, not only chat, search or isolated domain tools |
| G-015 | No AI model or general agent may see raw Finance records; financial answers must be computed deterministically and only approved computed outputs may cross the boundary | DECIDED | Finance remains a deterministic, isolated capability; changing this requires a new explicit owner decision |
| G-016 | Target delivery is one native macOS application with one-click updates | DECIDED | Packaging, integrity verification, update and rollback implementation require an ADR and audit; this is not a claim of current implementation |
| G-017 | Planning/minimum-support profile is a 32 GB Apple-silicon Mac mini | DECIDED (planning profile) | Not yet owner-verified or benchmarked; actual test machine and results must be recorded separately |
| G-018 | Atlas must ultimately provide mobile access through iOS and Android apps, usable worldwide wherever secure connectivity is available | DECIDED | macOS remains first; keep domain logic portable and design secure remote access to owner-controlled Atlas Core without cloud inference |

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
| G-O14 | What secure remote-access topology connects mobile clients to owner-controlled Atlas Core worldwide? | Compare owner-controlled VPN/mesh with a minimal end-to-end encrypted relay; threat-model NAT traversal, identity, metadata, availability, hosting and regional restrictions. No public database/model ports | No; ADR required before remote-access implementation |
| G-O15 | What is the mobile offline and local-cache policy? | Define which data may be cached, expiry/encryption, queued action semantics, conflict handling and device-loss wipe/revocation | No; required before mobile beta |
| G-O16 | What mobile platforms and release support are required? | Target iOS and Android; determine minimum OS versions, distribution, push provider/privacy and support policy during mobile planning | No; decide before mobile beta |
| G-O05 | What backup and key-recovery experience is acceptable? | Owner explicitly deferred this decision; keep the storage/recovery release gate closed until decided and restore-tested | Yes, before release relying on backup |
| G-O06 | What are notification quiet hours and escalation preferences? | Design defaults; ask during notification UX acceptance | Later |
| G-O07 | What are final latency/accuracy thresholds? | Measure baseline and benchmark on target hardware | Yes, after evidence is available |
| G-O08 | What are the first capability priorities after the foundation? | Present ranked roadmap with effort/risk/value after the read-only slice audit | Yes, at roadmap review |
| G-O09 | Confirm the exact first vertical-slice workflow | Tentative preference is read-only local document discovery, reading and answering with exact source/page/section citations; owner confirmation still required | Yes, before implementation |
| G-O10 | Which connectors and external actions may agents use, and at what autonomy level? | Local documents read-only; Mail read-only; Calendar read-only/propose-only. Propose least-privilege scopes for each additional connector; no blanket permission | Yes, per connector/action |
| G-O11 | What is the minimum supported machine and OS version? | 32 GB Apple-silicon Mac mini is the planning/minimum profile; benchmark and publish the supported OS after target testing | No; verify before release |
| G-O12 | What native packaging, helper-process and update mechanism will be used? | ADR covering app bundle, helper isolation, footprint, signing/integrity, one-click update and rollback | No; decide before release |
| G-O13 | How are standing rules and legacy `docs/` records mapped to Genesis? | Audit and classify standing rules, defect list, coverage matrix and comment tracker during implementation gap analysis; retain historical evidence | No |

## 4. Reconciliation with current Atlas implementation

The current implementation may contain separate Atlas, Finance, Documents and Images packages/services, a local Ollama model and a Read/Sort/Group pipeline. These are legacy implementation facts to inventory and migrate—not approved product boundaries. The target is one Atlas application.

Project Genesis establishes the single-application product boundary and evolves the internal architecture:
- from legacy standalone app shells to one Atlas application with internal domain capabilities;
- from a focused personal app to a personal operating system / chief of staff;
- from one fixed model to a model-independent local intelligence gateway;
- from app/tool-specific orchestration to central capability and policy contracts;
- from the current reader stages to a durable, observable, resumable ingestion pipeline;
- from a chat-first interface to unified chat, voice, dashboard, notifications and approvals;
- from current local Mac operation to macOS-first, cross-platform-ready boundaries.

Do not remove existing security controls, data stores, tests or app capabilities as part of this evolution. Map each current component to the target, identify conflicts and migrate deliberately.

## 5. Personal Agent Workforce direction

The owner-established outcome is personal and professional work automation inside the single Atlas application. The recommended role catalogue, orchestration and phased delivery are defined once in `TARGET_ARCHITECTURE.md` §13 and the unified roadmap in §11. Do not duplicate the role list here. Finance follows G-015; Health remains locked by default. Consequential actions require the configured approval policy.

## 6. Change log

- 2026-11-19: Initial consolidation of established Project Genesis direction and target architecture recommendations.
- 2026-11-19: Added the personal-work automation direction and recommended Agent Workforce architecture; specialist rollout and first workflow remain subject to review and owner prioritisation.
