# Atlas PRD conformance matrix

**Snapshot:** 2026-11-25. **Implementation patch snapshot:** 5284191f013ff5f9b29a35ff237d19ead7e51ad3; exact-head CI is pending. This is a source/document-based assessment, not owner acceptance. Detailed scenario mapping is in USE_CASE_CONFORMANCE.md.

## 1. Product identity and principles

| PRD requirement | Status | Evidence | Gap / boundary |
|---|---|---|---|
| One Atlas application / personal smart intranet | PARTIAL | Native Atlas app shell, Home, Ask, Explore/Library, Settings; PRD and UI_UX_SPECIFICATION define one product | Screens exist, but many life-area capabilities are absent or placeholders; no owner visual acceptance. |
| Local-first; no cloud inference/fallback | PARTIAL / SECURITY GATE | Core and MLX local inference path; separate egress gateway; no cloud inference provider | macOS model sandbox is allow-by-default, not least privilege; public research has bounded taint residuals and no real-Internet test. F-11 remains release-blocking. |
| Fast and useful; async expensive work | PARTIAL | durable task state, progress events, bounded scheduler, incremental indexing | Target-Mac latency, memory, thermal and model quality measurements are absent; cancellation race remains in AppModel. |
| Correct before confident | PARTIAL | evidence/citations, coverage, deterministic compute, exact rational parser, Finance calculations | High-precision exact-decimal patch awaits CI; Finance currency semantics limited; source freshness/revocation races remain. |
| One coherent experience across chat, voice, dashboard, notifications, approvals and history | PARTIAL | SwiftUI shell, Ask, dictation/read-aloud, Home, Activity, Notifications, ApprovalSheet, Settings | Approval sheet has no live proposed-action path; activity is in memory; conversation history is not persisted; notifications not owner-verified. |
| Persistent governed memory with review/correction/expiry/deletion | NOT IMPLEMENTED | MEMORY_PRIVACY_KNOWLEDGE.md specification | No governed memory store/service or user controls found in Core implementation. |
| High autonomy with approval boundaries | PARTIAL | Action Gateway, closed approval categories, exact-payload/single-use approval, record actions, connector framework | General orchestration is not wired to the everyday Core path; Action Gateway execution receipts/idempotency/undo are not durable across restart; app does not surface live proposals. |
| One application with modular internals | PARTIAL / FOUNDATION PRESENT | modular Core, AtlasKit, versioned API, adapters and domain modules | Domain modules exist at uneven maturity; many are not end-to-end wired. |
| Model independence | PARTIAL | Intelligence Gateway, Router, model descriptors, runtime adapter boundary | Production tested path is MLX; alternate runtime/provider parity is not demonstrated; owner model/27B class unverified. |
| Traceability of important facts/recommendations/actions | PARTIAL | source citations, provenance/version hashes, content-free audit, action receipt model | Not every domain has source preview/location; Action Gateway durable receipts are open; no general memory provenance. |
| Best outcome over implementation preservation; preserve data/keys/history | PARTIAL | modular redesign, backup/verify/restore CLI, non-destructive Finance import, separate stores/keys | Full legacy data inventory/migration is incomplete; no owner-Mac recovery drill; app identity, connector credentials and device state are not fully covered by Core backup. |

## 2. Users and platform (PRD §3)

| Requirement | Status | Evidence | Gap / boundary |
|---|---|---|---|
| Single owner initially; macOS first | IMPLEMENTED as product boundary | Core owner/member identity, macOS app and local Core | Owner-Mac acceptance and release packaging remain incomplete. |
| Future native iOS client | PARTIAL / BLOCKED | iOS SwiftUI app, shared AtlasKit, pairing/sync and hosted simulator tests | Relay/iOS/offline/cache findings remain open; no real phone/network/VPN exercise or owner acceptance. |
| Portable domain logic/contracts | PARTIAL | language-neutral API 1.0/1.1 and shared kit | Some platform-specific assumptions remain; cross-platform parity not tested. |
| Always-on owner-controlled Mac mini; starts after reboot/update | PARTIAL | Core child lifecycle and signed updater; Keychain locked state | LaunchAgent helper is not installed/loaded; owner login required; FileVault/reboot and unattended availability are unverified. |
| Secure worldwide access without public database/model ports | PARTIAL / BLOCKED | paired-device protocol, signed requests, private/VPN relay off by default, Core binds owner-only Unix socket | Real network channel untested; relay/iOS/cache security findings remain blockers. |
| No multi-user/cloud-hosted Atlas brain/Android | ALIGNED as current boundary | PRD and architecture; no hosted inference service | Preserve as a scope guard; do not interpret enrolled member/device as multi-owner product. |

## 3. Product experience (PRD §4)

| Requirement | Status | Evidence | Gap / boundary |
|---|---|---|---|
| Portal, contextual Spaces, connected knowledge and discovery | PARTIAL | Home/Ask/Library/Explore shell and domain destinations | No full Spaces system, global search/command field or integrated personalised discovery/news. |
| Unified interaction: chat, voice, dashboard, notifications, approval queue, searchable history | PARTIAL | SwiftUI surfaces and corresponding AtlasKit modules | Searchable conversation/decision/action history is not implemented; approval flow is not reachable from a live proposal; Activity is in memory. |
| Cross-domain understanding under per-domain grants | PARTIAL | policy/gate, G-021 restricted-domain grants, source designation and domain tests | End-to-end cross-domain conflict/reconciliation is limited; Finance/Health ingestion is incomplete; API read/revocation race remains. |
| Proactive monitoring of authorised sources | PARTIAL FOUNDATION | watchers.py, review.py, calendar overlap attention and notification logic | Watchers are not generally wired into Core routes; no complete schedule/cadence/budget UI or daily briefing. |
| Initial read-only, evidence-grounded workflow | PARTIAL | Documents and Mail indexing, citations, Get Started, owner-only consent API | Attachments deliberately unread; real Mail/TCC unverified; no full source preview/open-in-source action. |
| Local model transparency and routing safety | PARTIAL | Intelligence Gateway, explicit mode, model identity in API 1.1 answer and safe events | Hosted runner loaded a small MLX model only; selected owner model/quantisation/context/quality and real-model injection remain unverified. |
| Closed approval list and exact-payload approval | PARTIAL | Action Gateway tests, approval payload binding, expiry and single-use | App live proposal path absent; Action Gateway state not durable; external integrations not validated. |
| Agent workforce and orchestration | PARTIAL FOUNDATION | orchestrator.py, fixed review workflow, stub agents and one model-backed highlights path | General specialist role workforce, delegation, verification and production task wiring are not implemented. |
| Observe / prepare / execute reversible / consequential / proactive delegation | PARTIAL | watchers, review, actions and connector seams | Proactive watcher routes, general workflows, reliable undo/compensation and durable task receipts remain open. |
| Browser and macOS app automation | PARTIAL / DISABLED | browser read-only engine and fake-engine policy tests | Production browser is off pending OS confinement; click/form interaction absent; native macOS app automation not built. |
| Agent quality requirements (scope, budget, timeout, evidence, termination) | PARTIAL | bounded orchestrator/task contracts and tests | No general production agent task pipeline with full budget/deadline/termination/receipt enforcement. |

## 4. Functional capability areas (PRD §5)

| Capability | Status | Current scope |
|---|---|---|
| Personal knowledge/documents | PARTIAL | Plain text/Markdown and Mail body paths; supported-format/OCR/attachments incomplete. |
| Finance/investments | PARTIAL | Legacy transactions, basic summaries and deterministic arithmetic; no portfolio/investment cockpit, market data or scenario analysis. |
| Calendar/tasks/planning | PARTIAL | Calendar/Contacts/Notes adapters and own-record actions; no complete project/task manager or general planning. |
| Travel | NOT IMPLEMENTED as a planning capability | Travel record domain only; no itinerary/route/lodging/booking research. |
| Health | NOT IMPLEMENTED as source ingestion | Encrypted store and deterministic summary surface; no importer/HealthKit. |
| Work/projects | NOT IMPLEMENTED | No project source connectors or dependency/deliverable workspace. |
| Home/devices | NOT IMPLEMENTED as a verified domain | Generic connector seam only; no verified energy meter, heating schedule or home automation vendor. |
| Media/photos | PARTIAL FOUNDATION | PhotoKit provider path; complete media search/description/grouping UX not evidenced. |
| Communications/integrations | PARTIAL | Generic fixed connector catalogue and profile; no selected real vendor adapter. |

## 5. Quality attributes (PRD §6)

| Attribute | Status | Evidence / gap |
|---|---|---|
| Latency and responsiveness | PARTIAL | Bounded scheduler and synthetic ingestion/overhead thresholds exist; target-Mac latency/memory/thermal results absent. |
| Accuracy | PARTIAL | Evidence and deterministic calculations; exact decimal fix pending CI; currency and source-revocation gaps remain. |
| Privacy | PARTIAL / RELEASE BLOCKED | G-021, source grants, redaction and bounded egress; sandbox not least privilege, taint/DNS/truncation residuals and API read race remain. |
| Reliability | PARTIAL | task recovery, store integrity and tests; Core shutdown/partial construction and Action Gateway durable state defects remain. |
| Background work does not starve interaction | PARTIAL | bounded scheduler and resource-pressure controls; target workload/hardware unverified. |
| Accessibility/usability | PARTIAL / OWNER UNVERIFIED | semantic labels and hosted UI tests; accessibility audit reliability concerns and no owner VoiceOver/keyboard/Dynamic Type walkthrough. |
| Language support | PARTIAL | multilingual evaluation fixtures; Japanese/unspaced retrieval gap and real-model language quality unmeasured. |
| Maintainability | PARTIAL | typed contracts, CI, modular boundaries and docs; exact-head CI pending, all 283 changed paths not independently audited. |

## 6. Non-goals and acceptance principles (PRD §§7–10)

- Cloud inference and silent cloud fallback remain excluded; public research is a separate, gated egress operation and must not become a cloud model fallback.
- Autonomous self-modification/deployment remains excluded.
- Broad first-release domain coverage is not claimed; the UC matrix identifies missing domains and workflows.
- Acceptance requires requirements, failure/recovery behaviour, proportionate security review, adversarial/boundary tests, measured performance or explicit exception, updated documentation and separate implemented/tested/owner-verified statuses.
- Current branch is not accepted: Stage 3 remains NOT ACCEPTED; Stages 4–8 are not architect-reviewed or accepted; owner-Mac, real data, network, signing, restore and model gates remain open.

## 7. Overall PRD conformance judgement

**PARTIALLY ALIGNED overall; not release-ready.** The implementation provides a substantial local Core, policy, task/evidence, deterministic calculation, API, macOS client and later-stage foundations. It does not yet deliver the complete personal smart intranet/chief-of-staff promise. Governed memory, personal operating context, home energy, sports/statistics, personalised news, investment cockpit, general agentic workflows, complete source ingestion, browser/macOS automation, durable conversation history and production-ready iOS remote access are major gaps. The owner-tryable UX, target hardware, sandbox, recovery and real integrations remain unverified.

Use USE_CASE_CONFORMANCE.md for scenario-level detail and IMPLEMENTATION_CONFORMANCE.md for the audit process, exact evidence and unresolved review findings.
