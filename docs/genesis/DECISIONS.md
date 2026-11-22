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
| G-008 | Highly sensitive information is isolated, owner-controlled and requires explicit permission; Health is not categorically excluded from the local model (see G-021) | PARTIALLY SUPERSEDED | Sensitivity-aware access, provenance, revocation and separately labelled/keyed stores remain; former Health lock superseded by G-021 |
| G-009 | Important factual conclusions must be traceable to source evidence | DECIDED | Provenance is part of data contracts |
| G-010 | Architecture-first development | DECIDED | Define boundaries and contracts before major implementation |
| G-011 | The existing implementation is not an architectural constraint; choose the best Atlas design. Reuse existing components only where they are the best choice; otherwise redesign or replace. | DECIDED | Audit each mechanism as reuse, reference-only or discard. Existing code/tests remain behavioural and regression evidence. Preserve owner data, keys and history with integrity checks and rollback. |
| G-012 | Response speed and answer accuracy are both critical | DECIDED | Latency and quality are paired release criteria |
| G-013 | There will be exactly one Atlas application. Legacy standalone Finance, Documents, Images and other app shells are obsolete; their useful capabilities/data must be integrated into Atlas | DECIDED | One product identity and UX; internal modules are allowed, separate apps are not |
| G-014 | Atlas is intended to automate the owner's personal and professional work through a unified assistant and coordinated internal capabilities | DECIDED | Design for end-to-end personal workflows, not only chat, search or isolated domain tools |
| G-015 | No AI model or general agent may see raw Finance records | SUPERSEDED by G-021 (2026-11-20) | Historical rule only. The local model may read owner-authorised Finance information; exact calculations remain deterministic and code-checked. |
| G-016 | Target delivery is one native macOS application with one-click updates | DECIDED | Packaging, integrity verification, update and rollback implementation require an ADR and audit; this is not a claim of current implementation |
| G-O17 | Shared Swift + SwiftUI macOS/iOS application; versioned language-neutral Core API; Core language deferred to G-O20; direct-download Developer ID signed and notarised Mac distribution | ACCEPTED BY OWNER (2026-11-20) | One shared Apple application codebase; Mac-host Core remains behind the versioned API. Stage 2 separately authorised; Stage 3 authorised under G-027. |
| G-017 | Planning/minimum-support profile is a 32 GB Apple-silicon Mac mini | DECIDED (planning profile) | Not yet owner-verified or benchmarked; actual test machine and results must be recorded separately |
| G-018 | Atlas must ultimately provide mobile access through an iOS app, usable worldwide wherever secure connectivity is available | DECIDED | macOS first, then iOS; keep domain logic portable and design secure remote access to owner-controlled Atlas Core without cloud inference. Android is not a target (owner, 2026-11-19) |
| G-019 | Language support and evaluation requirement: Atlas is intended to support English, Dutch and other languages present in the owner's documents. Support is measured per language and reported honestly; no language is claimed as supported until measured. | DECIDED | Evaluate readers, OCR, retrieval, local model and answer quality per language; disclose unsupported paths or inadequate confidence. No fixed language list in code |
| G-020 | Local model strategy: use a ~27B-parameter main-model class, Apple MLX for local inference, and visibly identify the model that answered. | DECIDED — direction (2026-11-20); exact stack ratified under G-O01 (2026-11-22) | The selected hardware, model roles, fallback-by-capability, deterministic routing, context and quantisation policy are recorded in §8. This is an architecture selection, not proof of MLX compatibility, performance, memory fit or production readiness; those require target-Mac gates. MLX is Apple-silicon-only; Linux CI uses a deterministic stub. Model identity (model ID and routing role only; never prompt/content) remains a later compatible API/event addition. Every routed model call re-enters the same policy gate; model selection cannot widen permissions. |

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
| G-R10 | Domain-scoped agent context; separately labelled/keyed Finance and Health stores with owner-authorised local model access | RECOMMENDED | Prevents one-app convenience from becoming unrestricted cross-domain access while respecting G-021 |

## 3. Open decisions requiring investigation or owner input

| ID | Question | Proposed next step | Owner input needed now? |
|---|---|---|---|
| G-O02 | What storage, full-text, vector and relationship-query stack is appropriate? | Produce a storage/encryption/key-boundary ADR after auditing data volume, query patterns, backup and restore | No |
| G-O03 | Which external sources/connectors should be supported first? | Inventory existing sources and rank by value/risk; current owner direction is local documents read-only, Mail read-only and Calendar read-only/propose-only | Only when prioritising a release |
| G-O04 | What is the multi-device sync and conflict model? | Define offline cache, sync, conflict resolution, queued actions and device-loss behaviour before mobile beta | No; required before mobile beta |
| G-O05 | What backup and key-recovery experience is acceptable? | Owner explicitly deferred this decision; keep the storage/recovery release gate closed until decided and restore-tested | Yes, before release relying on backup |
| G-O06 | What are notification quiet hours and escalation preferences? | Design defaults; ask during notification UX acceptance | Later |
| G-O07 | What are final latency/accuracy thresholds? | Measure baseline and benchmark on target hardware | Yes, after evidence is available |
| G-O08 | What are the first capability priorities after the foundation? | Present ranked roadmap with effort/risk/value after the read-only slice audit | Yes, at roadmap review |
| G-O09 | Confirm the exact first vertical-slice workflow | Owner answered (2026-11-19): read-only question → authorised local documents and mail found → answer with exact source citations. Mail attachment treatment (G-O18) and source designation (G-O19) remain separate design gates. The owner accepted G-O17, waived the ChatGPT package-acceptance gate and explicitly authorised Stage 2 on 2026-11-20 (PR #7 comment 7037299974 and subsequent owner instructions). Stage 2 implementation acceptance remains pending independent review of PR #8. Stage 3 is separately authorised under G-027. | Owner scope answered; Stage 3 authorised; implementation proceeds by reviewed package |
| G-O10 | Which connectors and external actions may agents use, and at what autonomy level? | First-slice local documents and Mail are read-only; Calendar remains read-only/propose-only when separately authorised. Propose least-privilege scopes for each additional connector; no blanket permission | Yes, per connector/action |
| G-O11 | What is the minimum supported machine and OS version? | 32 GB Apple-silicon Mac mini is the planning/minimum profile; benchmark and publish the supported OS after target testing | No; verify before release |
| G-O12 | What native packaging, helper-process and update mechanism will be used? | ADR covering app bundle, helper isolation, footprint, signing/integrity, one-click update and rollback | No; decide before release |
| G-O13 | How are standing rules and legacy `docs/` records mapped to Genesis? | Initial audit completed in Stage 1 (PR #7 comment 7022436618); map records to Genesis requirement IDs during Stage 2 work, retaining historical evidence | No |
| G-O14 | What secure remote-access topology connects the iOS client worldwide to the owner-controlled Atlas Core without violating local-only inference? | Compare owner-controlled VPN/mesh with a narrowly scoped end-to-end encrypted relay only if necessary and explicitly approved. Threat-model device identity/enrolment/revocation, authentication, NAT traversal, relay metadata, regional restrictions and availability. No public database/model ports, third-party inference or plaintext relay storage. Stage 8 is gated on an accepted threat model and ADR; stages 0–7 must not depend on mobile access. | No; ADR and threat model required before stage 8 |
| G-O15 | What is the mobile offline and local-cache policy? | Define which data may be cached, expiry/encryption, queued action semantics, conflict handling and device-loss wipe/revocation | No; required before mobile beta |
| G-O16 | What mobile platform and release support is required? | Target iOS; determine minimum OS version, distribution, push provider/privacy and support policy during mobile planning | No; decide before mobile beta |

| G-O18 | How are supported Mail attachments extracted, cited and secured? | OWNER SCOPE ANSWERED: all supported formats are in scope. Define the supported-format matrix, provenance, OCR confidence/limitations, sensitivity, hostile-file tests and explicit unsupported/partial states. Keep attachment ingestion as a separate package after Mail body; do not expose contents until that package passes acceptance. | No further preference question; technical design/acceptance required |
| G-O19 | How does the owner enable searchable source types without repeated friction? | Owner delegated the design. Recommended: one first-run Get Started consent covering the initial local source scope, with macOS system permission prompts; Core grants and revocation remain authoritative internally. No source content is read before consent and OS access. Avoid per-folder toggles and repeated prompts. | Architect/developer to implement; do not re-ask owner for mechanism preference |
| G-O20 | Which language/runtime should implement the Mac-host Atlas Core over time? | Re-evaluate Python versus Swift (and only justified alternatives) using the owner's MLX direction, actual repository reuse, MLX Python/Swift integration maturity, one-codebase criterion, packaging/notarisation, security, performance, migration cost and testability. Interim recommendation from Claude's review 7045420044: retain Python behind the versioned API through any later authorised Stage 3 work; decide the long-term Core language only after the target-Mac MLX benchmark and a signed/notarised Python-helper packaging proof. This is a recommendation, not an owner decision or Stage 3 authority. Do not rewrite the Core before a separate evidence-backed ADR and owner decision. | No; investigate before committing to long-term Core implementation |
## 3A. Explicit later-stage design gate — model identity (not implementation authority)

Claude's focused review of the prior documentation head (PR #7 comment 7045420044, reviewed head `a2a53ba`) identified that G-020's requirement to show which model answered is not represented in the frozen Stage 2 API 1.0 answer envelope or safe audit-event allow-list. Keep Stage 2 frozen; do not add this field to the current implementation merely to close a documentation review. Before a later stage is authorised, add an additive, versioned contract change (minor API version where compatible) that exposes a safe model descriptor in answer details (at minimum model ID and routing role; runtime/version as appropriate) and a redacted safe event recording the selected route. Never include prompts, personal content, secrets or raw model context. Every routed model must pass the same policy gate; routing must never widen source permissions. This is a design/acceptance gate for a future authorised stage, not permission to begin Stage 3.

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

The owner-established outcome is personal and professional work automation inside the single Atlas application. The recommended role catalogue, orchestration and phased delivery are defined once in `TARGET_ARCHITECTURE.md` §13 and the unified roadmap in §11. Do not duplicate the role list here. Finance and Health follow G-021: the local model may read owner-authorised data; keep separate stores/labels, provenance, redaction and revocation. Consequential actions follow G-022.

## 6. Change log

- 2026-11-19: Initial consolidation of established Project Genesis direction and target architecture recommendations.
- 2026-11-19: Added the personal-work automation direction and recommended Agent Workforce architecture; specialist rollout and first workflow remain subject to review and owner prioritisation.
- 2026-11-19: Owner initially confirmed iOS and Android as future mobile platforms; this was superseded the same day by the owner's direction to drop Android. The committed sequence is macOS first, then iOS only. Secure global access remains gated by remote-access threat modelling and ADR; no cloud inference or hosted Atlas brain is authorised.
- 2026-11-19: Owner confirmed the first read-only workflow includes local documents and Mail. Mail attachment contents remain unavailable until the separate technical package passes acceptance; owner scope is all supported formats. G-O19 source onboarding is delegated to a single Get Started flow plus OS permissions.
- 2026-11-19: Added G-019 language support/evaluation requirement and recorded the legacy `docs/decisions.md` conflict with G-015 without modifying the historical file.
- 2026-11-19: Owner relaxed the default-evolve/no-rewrite constraint. Choose the best Atlas architecture; assess existing components as reuse, reference-only or discard, while preserving owner data, keys and history through integrity-checked migration and rollback.
- 2026-11-19: Owner intends the Atlas Core host to be an always-on Mac mini. Treat this as an operating assumption; provide normal reboot/update auto-start and a clear mobile unreachable state. Do not engineer for extreme outage scenarios; retain proportionate security controls for remote access.
- 2026-11-20: Owner authorised all of Stage 3 in plan order (G-027). WP3.0 baseline inventory accepted; WP3.1 contract brief to be issued and reviewed before implementation.
- 2026-11-20: Owner selected the local inference direction: ~27B main-model class chosen by target-Mac benchmark, automatic task-based model switching with visible model identity, and Apple MLX runtime. Exact model/quantisation/context/fallback remain open; Linux CI must use a model stub. Re-open G-O20 analysis to compare Python and Swift Core options in light of MLX without changing the Stage 2 Python reference implementation or assuming an immediate rewrite.
- 2026-11-20: Claude's focused documentation verification (former PR #7 comment 7045420044, head `a2a53ba`) identified model-identity contract visibility as a later-stage gate, missing G-020 references in the PRD/target gateway, ambiguous MLX wording in ADR G-O17, and benchmark acceptance conditions. Reconciled here without changing the frozen Stage 2 API: model identity/routing metadata is an explicit future-stage gate; G-O01 now requires combined-workload memory headroom/pass-fail, a no-go owner decision, same-policy routing, multilingual and hostile-input evaluation. Claude's G-O20 recommendation is recorded as a recommendation only: retain Python through any later authorised Stage 3 work until MLX and packaging evidence exists; no long-term Core language is decided.
- 2026-11-20: Claude technically challenged G-O17 and the Stage 2 package (PR #7 comment 7035425400). ChatGPT reconciled the exact changes: G-O17 now explicitly decides the shared Swift/SwiftUI application layer, Core API boundary and packaging direction; G-O20 separately tracks the future Mac-host Core language. Stage 2 is revised to use OpenAPI 3.1/JSON Schema, Python reference tests, synthetic provenance fixtures, a separate additive encrypted task store, Core-enforced policy, client identity/signatures, streaming/cancellation/versioning, language/confidence disclosure and explicit verification limits. Owner accepted G-O17, waived the ChatGPT package-acceptance gate and explicitly authorised Stage 2 on 2026-11-20. PR #8 implementation acceptance remains pending. Stage 3 was subsequently authorised in full under G-027 on 2026-11-20; work proceeds by reviewed package, with separate platform and release gates preserved.

## 7. Owner clarifications recorded 2026-11-20

These decisions supersede conflicting earlier rows and prose above.

| ID | Decision | Status | Consequence |
|---|---|---|---|
| G-021 | Local on-device model may read owner-authorised Finance and Health information. Supersedes G-015 and the Health lock in G-008. | DECIDED by owner (PR #8 comment 7049796870) | Keep separately labelled/keyed and permission-controlled stores, provenance, redaction, revocation and least privilege. Do not categorically exclude these domains from local model context. Exact financial arithmetic remains deterministic and code-checked. No cloud inference or external disclosure is implied. |
| G-022 | Single-user product; routine reading, searching, analysis, summarising, drafting and computation require no approval. Approval is limited to the closed list in PRD §4.4. | DECIDED by owner (comment 7049933927); architect closure | One first-run Get Started flow plus OS prompts; no repeated incidental prompts. Closed list: send/share/publish/upload outside Mac; spend/pay/trade/purchase/paid booking; delete/overwrite without reliable undo or destructive migration; unlock external physical access or disable safety/security systems. Everything else never prompts. |
| G-023 | Public Internet research is allowed when useful; private data must not silently leave Atlas. No cloud inference or remote Atlas brain. | Owner direction (comment 7050043465); architect decision: Brave Search API default provider | Core-mediated egress, strict query minimisation/taint controls, untrusted-page handling, Keychain-held connector credentials and visible redacted network activity. Search queries are disclosed to Brave; only sanitised public intent may be sent. See INTERNET_AND_NETWORK_POLICY.md. |
| G-024 | All supported Mail attachment formats are in scope. | DECIDED by owner (comment 7044696263) | Keep attachment ingestion as a separate package after Mail body; specify formats, provenance, OCR confidence/limits, sensitivity and hostile-file tests before acceptance. Until accepted, attachment content remains unavailable and this limitation must be disclosed. |
| G-025 | Source onboarding should not create repeated or per-folder permission friction. The owner delegated consent UX design to the architect/developer. | DECIDED direction; implementation design recommendation | One first-run Get Started consent covering initial local source scope, plus macOS prompts. Core still enforces grants and revocation. |
| G-026 | Atlas requirements must be developed and tested through a cross-domain, interaction-mode and lifecycle scenario register. | DECIDED by owner direction (comments 7050110840 and 7050130833) | USE_CASE_REGISTER.md is the canonical scenario inventory and integration catalogue; each scenario maps to acceptance evidence and explicit later/not-applicable status. |
| G-027 | Stage 3 is authorised in full, in plan order, as one bounded programme. | DECIDED by owner (2026-11-20; explicit answer: “Yes, all of Stage 3”; PR #8 comment 7050905427) | Work proceeds package by package on PR #8, with ChatGPT review of each exact commit. Mac-dependent work waits for target hardware. This does not waive G-O12 (packaging), G-O02/G-O05 (storage, keys and recovery), real-owner-data restrictions before target-Mac verification, destructive-migration controls, or Stage 4 onwards. |

### Supersession notes

G-015 is superseded by G-021 and remains only as historical rationale. G-008 still requires owner control, provenance and revocation, but Health is no longer categorically locked from local model context. Earlier approval language requiring confirmation for routine or every privacy-sensitive action is superseded by G-022. G-O18 is answered as product scope (“all supported formats”); remaining work is technical specification and acceptance, not another preference question. G-O19 is delegated: implement one Get Started flow and do not repeatedly ask the owner to choose internal permission mechanisms. Public web access is allowed under INTERNET_AND_NETWORK_POLICY.md, but this does not authorise uploading personal content or cloud inference.


## 8. G-O01 — Final hardware and model architecture (2026-11-22)

**Decision authority:** The owner explicitly delegated the final model/hardware choice to Claude Code (PR #8 comment [7071570360](https://github.com/Prasanna666666/Prasanna/pull/8#issuecomment-7071570360)), then asked ChatGPT to finalize and document it. ChatGPT's reconciliation is recorded in [PR #8 comment 7071815030](https://github.com/Prasanna666666/Prasanna/pull/8#issuecomment-7071815030). This closes the *selection* question G-O01. It does not waive any validation or release gate below.

### 8.1 Hardware selection

**Selected target:** Mac mini with **M6, 32 GB unified memory, 256 GB internal SSD**, plus a fast external SSD for model storage.

- Do not select 24 GB. The 32 GB configuration is the planning target; it has not yet been purchased or tested.
- Do not select 48 GB: it is outside the owner's budget. External SSD adds storage, never RAM.
- The M5 Pro 32 GB comparison is not a purchasable configuration. Apple's current Mac mini specifications list M5 Pro memory at 24 GB, configurable to 48 GB or 64 GB; M6 is configurable to 24 GB or 32 GB. Apple lists 170 GB/s for the M6 32 GB configuration and 307 GB/s for M5 Pro. The higher-bandwidth M5 Pro is a different memory/price tier, not an equivalent 32 GB alternative.
- Official hardware reference: [Apple Mac mini technical specifications](https://support.apple.com/en-us/128108) (2026 specification page).

### 8.2 Selected model stack

| Role | Selection | Capability and operating rule |
|---|---|---|
| Resident primary | **Google Gemma 4 26B-A4B, 4-bit** | Default model for free-text work; text and image input. One resident primary. Prefer a verified QAT quantisation only when its provenance is verified; otherwise convert/quantise from the vendor's source weights through Atlas's controlled, reproducible process. |
| First fallback — text | **OpenAI GPT-OSS-20B, MXFP4** | Text-only fallback. Never route image/audio/video input here while silently dropping the modality. |
| First fallback — multimodal | **Google Gemma 4 12B, 4-bit** | Capability-preserving fallback for image and audio tasks; use only after its own MLX and quality gates pass. |
| On-demand deep tier | **Google Gemma 4 31B, Q4** | Only inside an owner-selected, explicitly typed Research mode. Research mode first uses the primary with a larger reasoning budget; swap to 31B only if the blinded research/debate evaluation demonstrates a material quality gain. Unload the primary first; never keep a second large model resident. |

The fallback chain is capability-aware: text tasks use Gemma 4 26B-A4B → GPT-OSS-20B → Gemma 4 12B; tasks requiring image/audio capability use Gemma 4 26B-A4B → Gemma 4 12B. If no eligible model can satisfy the required modality and policy gates, Atlas reports local model unavailability rather than dropping input or using a remote model.

**Excluded from the planned dependency graph:** Qwen; Ministral 3 14B as a supposed fast tier (it is a dense-model comparator only if separately benchmarked); and Nemotron 3 Nano (optional research candidate only after a separate licence and lineage review). No resident coding model and no default small-model router.

### 8.3 Routing, verification and resource policy

- Typed deterministic capabilities (exact search, calendar/status queries, calculator, approve/cancel and fixed-grammar commands) skip model inference but still pass through the applicable Core policy gate.
- Free-text chat always uses retrieval first, then the resident primary. No semantic model router and no model switching inferred from task wording.
- Research/deep inference is entered only through owner-selected Research mode. The 31B swap is a deterministic, disclosed decision within that mode, based on the pre-registered evaluation result.
- No always-on verifier model. Deterministic arithmetic/date/unit/schema/citation checks always run. Same-model span checking is optional; a different-family check is enabled only if a blinded ablation demonstrates a material benefit.
- Concurrency is capped at two jobs initially: one interactive and one background. Interactive work has priority and must not wait behind background inference. Do not co-reside a second large model; swap specialists in/out.
- Context defaults to 32K. 64K/128K profiles require separate recall, latency and memory acceptance.
- Cache only in memory, keyed by domain, grant identity/version, model and quantisation. Flush on session end, grant/policy change, revocation and model unload. No persistent user-content KV cache.
- Each model has one explicit, fixed quantisation. Never silently lower precision or change model for Finance, Health, permissions, code changes or evidence-critical work.
- Degradation order: stop new background inference; evict rebuildable caches; pause background work and unload specialists; reduce context and rely on scoped retrieval; use only a pre-benchmarked disclosed profile; otherwise refuse. Never rely on memory swapping or cloud fallback.

### 8.4 Model supply chain and privacy

Every imported model must have a manifest recording developer and accountable release organisation, model ID/revision, disclosed base/derivative/distillation lineage, licence text and usage terms, quantisation source/conversion chain, runtime compatibility and SHA-256 digest. Verify the full digest on import and remount/identity change; load only from verified read-only bytes. No unmanifested model loads. A missing external drive means “model unavailable”; deterministic typed capabilities may continue.

Use safetensors or GGUF only; no pickle and no `trust_remote_code`. Pin runtime/package versions in a dedicated environment. Inference runs in a separate process under network-deny isolation; downloads happen only in an explicit owner-approved import step. Verify that the inference process opens no network socket during model load or inference. No remote inference or silent fallback, ever.

**Lineage standard and accepted residual risk:** eligible releases must have a developer and accountable release organisation outside the PRC, and their model card/technical report must disclose no PRC-origin base, derivative or distillation source. Derivatives and community quantisations of a PRC-origin base are ineligible regardless of distributor. The owner accepted that undisclosed post-training and synthetic-data provenance cannot be proven absent for the selected Google and OpenAI releases; this is a named residual risk, not a claim that the training data has been exhaustively verified. Record the exact upstream revision and quantisation chain.

Vendor documentation identifies Gemma 4 and GPT-OSS as Apache 2.0 releases; the exact release licence files, Gemma terms and usage policies must still be read and archived before import/use. A publisher, licence or open-weights label does not make a model “safe”; Atlas's sandbox, manifest, policy gate and evaluation remain mandatory.

### 8.5 Disqualifiers and acceptance

The selected stack is overturned only if one of these conditions is evidenced:
1. A primary-source model card/technical report discloses a PRC-origin base, derivative or distillation source for a selected model.
2. The exact licence/terms do not permit Atlas's intended local use.
3. A selected model fails a hard acceptance gate on the target M6: any policy/permission bypass, fabricated source reference, evidence-integrity failure, critical-failure bound above the pre-registered limit, memory above the declared budget, memory pressure not green, or any swap.
4. MLX cannot run the selected model stably on the target Mac.

Before deployment, run paired, frozen, pre-registered evaluations per task class and language. Quality and time-to-useful-answer are reported together; a faster model cannot win by reducing correctness, and a more accurate model cannot pass if it is unusably slow. Hard policy/evidence gates come first. For each critical class, target at least 300 independent cases and report the one-sided 95% binomial upper confidence bound (0/300 is approximately 0.994%, not proof of zero risk). The provisional everyday decode floor is 30 tokens/second at a fixed 32K context, quantisation, runtime, output length and concurrency; also report time-to-first-token, time-to-first-useful-answer, p50/p95 completion latency, peak/steady memory, KV cache, cold load/unload, energy and thermals. Freeze numeric thresholds before the benchmark; these are gates to measure, not performance promises.

The purchase-window smoke test is a separate hardware check: load the primary at 32K context, sustain a 20-minute run, and record memory pressure, swap (must be zero), time-to-first-token and decode speed. A smoke test does not replace the per-class accuracy/evidence suite. Do not put real personal data into the system until licence/lineage checks, offline enforcement and hard security gates pass.
