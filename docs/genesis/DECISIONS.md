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

## 2. Architecture recommendations

| ID | Recommendation | Status | Rationale |
|---|---|---|---|
| G-R01 | Modular monolith as the target core, with process isolation only where justified | RECOMMENDED | Simpler ownership and integration without sacrificing parser/model isolation |
| G-R02 | Model-independent Intelligence Gateway supporting dense and MoE models | RECOMMENDED | Avoid model lock-in; route by measured task capability |
| G-R03 | Durable, idempotent job/event system for ingestion and proactive monitoring | RECOMMENDED | Restart safety, retries, resumability and responsiveness |
| G-R04 | Shared governed Memory & Knowledge subsystem; domain systems remain authoritative for transactions | RECOMMENDED | Cross-domain context with evidence and clear ownership |
| G-R05 | Central Action Runtime for tool policy, approval, execution and audit | RECOMMENDED | One enforcement point for autonomy |
| G-R06 | Migrate incrementally behind compatibility contracts | RECOMMENDED | Preserve data, working functionality and rollback options |

## 3. Open decisions requiring investigation or owner input

| ID | Question | Proposed next step | Owner input needed now? |
|---|---|---|---|
| G-O01 | Which local models and runtimes meet quality/latency/memory needs? | Benchmark a representative shortlist on the actual Mac | No; investigate first |
| G-O02 | What storage, full-text, vector and relationship-query stack is appropriate? | Audit current data volume, query patterns, encryption and backup | No |
| G-O03 | Which external sources/connectors should be supported first? | Inventory existing sources and rank by value/risk | Only when prioritising a release |
| G-O04 | What is the multi-device sync and conflict model? | Defer until a second platform/device is scheduled | No |
| G-O05 | What backup and key-recovery experience is acceptable? | Threat-model and prototype recovery without weakening encryption | Yes, before release relying on backup |
| G-O06 | What are notification quiet hours and escalation preferences? | Design defaults; ask during notification UX acceptance | Later |
| G-O07 | What are final latency/accuracy thresholds? | Measure baseline and benchmark on target hardware | Yes, after evidence is available |
| G-O08 | What are the first capability priorities after the foundation? | Present ranked roadmap with effort/risk/value | Yes, at roadmap review |

## 4. Reconciliation with current Atlas implementation

The current branch documentation describes a single-Mac, Docker-based deployment with separate Atlas, Finance, Documents and Images packages/services, a local Ollama model and an existing Read/Sort/Group pipeline. These are current implementation facts recorded in the legacy documentation, not immutable target architecture.

Project Genesis intentionally broadens the product direction:
- from a focused personal app to a personal operating system / chief of staff;
- from one fixed model to a model-independent local intelligence gateway;
- from app/tool-specific orchestration to central capability and policy contracts;
- from the current reader stages to a durable, observable, resumable ingestion pipeline;
- from a chat-first interface to unified chat, voice, dashboard, notifications and approvals;
- from current local Mac operation to macOS-first, cross-platform-ready boundaries.

Do not remove existing security controls, data stores, tests or app capabilities as part of this evolution. Map each current component to the target, identify conflicts and migrate deliberately.

## 5. Change log

- 2026-11-19: Initial consolidation of established Project Genesis direction and target architecture recommendations.
