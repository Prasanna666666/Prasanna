# Atlas — Handover

**Status:** Stage 2 review accepted for reviewed scope; Stage 3 authorised (G-027); WP3.0 accepted; WP3.1 specification accepted (review 6000401465); WP3.2 document-only vertical path accepted at `ad6e59bcb6fb5d6124ac56ea419f8330dc913e4c` (review 6000818496); WP3.3 Mail remains gated by G-O19  
**Repository:** `Prasanna666666/Prasanna`  
**Documentation branch:** `genesis-stage2-foundation` (documentation now consolidated into PR #8)  
**Implementation baseline:** `atlas`

## Authoritative entry point

Start with [README.md](README.md), then read the canonical documents it indexes. The [Delivery Protocol](DELIVERY_PROTOCOL.md) is the sole authority for role ownership, collaboration, handshakes, issue resolution, change control and acceptance. Do not duplicate those rules here.

## Owner-confirmed product boundary

There is exactly **one Atlas application**. Standalone Finance, Documents, Images and other legacy application shells are obsolete. Their useful features and data must be integrated into Atlas as internal capabilities. Hidden helper processes are allowed only when technically justified; they do not constitute separate apps. macOS is first, followed by an iOS client usable worldwide wherever secure connectivity is available. Android is out of scope. Atlas Core and AI inference remain under owner control; worldwide access must not introduce cloud inference.

## Basic facts — current owner-approved baseline

| Area | Current fact | Status / boundary |
|---|---|---|
| Product | One Atlas application; personal operating system / intelligent chief of staff | Owner decision |
| Platforms | macOS first, iOS later; worldwide iOS access through secure connectivity; Android out of scope | Owner decision; remote-access ADR and threat model still required |
| Hardware profile | 32 GB Apple-silicon Mac mini | Planning profile, not proof of a purchased/tested machine or verified minimum |
| Inference locality | Local-only; no cloud inference or silent remote fallback | Owner decision |
| Inference runtime | Apple MLX | Owner-selected direction; target-Mac integration still unverified |
| Main model | Approximately 27B-parameter class, exact model selected by benchmark | Owner direction; exact family, quantisation, context and fallback remain open |
| Model routing | Automatic task-based model switching; show which model answered | Owner decision; routing policy and measurements remain to be implemented |
| Core boundary | Versioned, language-neutral API behind the shared Swift/SwiftUI macOS+iOS app | G-O17 accepted; Core implementation language is separate G-O20 decision |
| Core language | Not yet decided for long-term production | Stage 2 Python reference implementation does not decide this; compare Python and Swift with MLX, packaging, security, reuse and migration evidence |
| Mac distribution | Direct download; Developer ID signed and notarised | Owner-approved direction; packaging/update/rollback implementation remains G-O12 |
| First workflow | Read-only, evidence-grounded questions over owner-authorised local sources, progressive indexing and exact citations | One Get Started flow plus OS permissions; Core grants/revocation; attachment content awaits technical package acceptance |
| Sensitive domains | Local model may read owner-authorised Finance and Health data | G-021; separate stores/labels, provenance, redaction, revocation; deterministic exact calculations |

ChatGPT owns this table and must update it whenever the owner establishes a durable product or technical fact. Distinguish owner decisions, recommendations, implementation status and verified evidence; never promote a target into a claim that it is already built or tested.

## Repository handling

- `atlas` is the implementation baseline for gap analysis.
- `genesis-architecture` contains this target documentation and handover.
- `aperture` is the repository default/legacy Photos branch, not the Atlas product target.
- `orbit` is historical reference material, not the active implementation baseline.

Do not delete branches, historical evidence, user data, databases or indexes as part of documentation cleanup. Retire obsolete app shells only through an approved, tested migration with data preservation and rollback.

## Historical PR #7 audit trail and current PR #8 gate

**Stage 0 — documentation review and reconciliation: COMPLETE.** Claude's full-document consistency confirmation is recorded in PR #7 comment 7023445432.

**Stage 1 — implementation audit / gap analysis: ACCEPTED AND CLOSED.** Claude's audit reports are recorded in PR #7 comments 7022436618, 7022456916 and 7022810935, with the superseding final note in 7022967306. ChatGPT's formal acceptance is recorded in comment 7022990234. The audit was documentation/evidence work only; its stated limitations and unverified Mac-dependent behaviour remain in force.

The completed sequence is retained in the PR discussion as the audit trail. It does not grant implementation authority.

**Architecture decision and Stage 2 authority — COMPLETE.** Claude's technical challenge is recorded in PR #7 comment 7035425400 and its focused document verification in 7037231906. The owner accepted G-O17 and explicitly authorised Stage 2 on 2026-11-20; the owner waived the ChatGPT package-acceptance gate so implementation could proceed (decision recorded in PR #7 comment 7037299974 and subsequent owner instructions). These decisions are final; do not ask the owner to repeat them.

**Stage 2 — ACCEPTED for reviewed scope.** The only open PR is [PR #8](https://github.com/Prasanna666666/Prasanna/pull/8), branch `genesis-stage2-foundation`. ChatGPT independently reviewed exact head `58210223398a5715b618d1163397104efd358d49`; the three earlier code blockers, documentation findings and subsequent transport framing/concurrency finding are closed for the inspected scope. Exact-head CI completed **22/22 successful**, including both supported Python core jobs and all repository suites. Core reports 162 tests on Python 3.11 and 3.13, with ruff/mypy clean. ChatGPT recorded formal Stage 2 review acceptance in PR #8 comment 7047659436. PR #8 remains open, draft and unmerged. This acceptance is not production/release sign-off.

**Still unverified:** real macOS Keychain and `LOCAL_PEERCRED`, Swift/Xcode integration, target-Mac MLX model quality/latency/memory under combined workload, signing/notarisation, and real process-kill/power-loss recovery. The local same-UID 64-slot exhaustion/no-rate-limit residual is documented. Do not claim production readiness.

**Stage 3 — owner-authorised split acceptance (2026-11-22).** The execution plan is [STAGE-3-EXECUTION-PLAN.md](STAGE-3-EXECUTION-PLAN.md) §12.10. Stage 3 acceptance covers the complete objectively testable implementation scope, with exact-commit CI, full-stage architect review and explicit owner acceptance. Evidence requiring the unavailable owner Mac, selected production model, real owner data stores/accounts or human owner walkthrough is explicitly deferred to final integration/release; it is not waived, passed, or a reason to hold the bounded Stage 3 engineering acceptance open. WP3.0/WP3.1 are accepted; WP3.2 is accepted at `ad6e59bcb6fb5d6124ac56ea419f8330dc913e4c` (review 6000818496). WP3.3 and later packages still require exact-SHA review. The testable portion of criterion 11 is NOT deferrable: the known P1 taint bypass must be fixed and regression-tested, least-privilege sandbox work must be CI-verified, and the egress gateway must be wired behind a disabled-by-default gate and tested with synthetic fixtures. Live public search remains disabled pending final-stage real-Internet/owner verification. Criterion 4 synthetic adversarial evaluation and criterion 12 harness/developer baseline/threshold work remain Stage 3 requirements; selected-model and target-Mac evidence is deferred. Criterion 13 automated app/launcher/Core lifecycle evidence remains Stage 3; owner walkthrough, real TCC/Mail store, signing/notarisation and self-contained installation are deferred. G-O18 attachment processing remains a separate technical acceptance gate. This split is not release approval and does not waive G-O12, G-O02/G-O05, migration controls or later platform gates.

The Stage 1 audit included the iOS target in its assessment. Mobile implementation and worldwide secure access remain separately gated by the remote-access threat model, device identity, offline/sync and mobile release decisions.

## Evidence status

This handover is a target/documentation instruction, not proof that legacy apps have already been retired or that the implementation has been consolidated. Current behaviour must be established from code, tests and CI. Target-Mac and local-model checks must be explicitly reported as owner-verified or pending.

## Current owner direction update — 2026-11-20

The canonical product scope extends beyond the original read-only Documents/Mail plan. See PRD.md, DECISIONS.md, USE_CASE_REGISTER.md, INTERNET_AND_NETWORK_POLICY.md, TARGET_ARCHITECTURE.md and STAGE-3-EXECUTION-PLAN.md.

Key directions: single-user Atlas; one first-run Get Started flow; no routine approval prompts; local model access to owner-authorised Finance and Health; exact calculations code-checked; approval only for consequential external effects or materially irreversible changes; public Internet research under strict data-minimised egress; all supported Mail attachments in scope subject to technical acceptance; progressive newest-first indexing with visible coverage.

The use-case and network-policy documents have been added to this branch. The Stage 3 preparation documents `STAGE-3-BASELINE-AUDIT.md` (the inspected repository gaps and reuse map) and `STAGE-3-CONTRACT-DELTA.md` (the architect's earlier contract proposal) were transplanted from the closed PR #10 branch `genesis-stage3-prep`. `STAGE-3-CONTRACT-DELTA.md` is now explicitly marked superseded and retained as historical context; `core/docs/CONTRACT_1_1.md` and the corresponding schema/OpenAPI files are authoritative for WP3.1. WP3.1 is specification-only: API 1.1 is not served by the running Core. This is documentation progress, not a working app build. Stage 3 is authorised (G-027); target-Mac integration, performance, Keychain, signing/notarisation and other hardware-dependent checks remain unverified.

## Always-on host and availability decision

**Recommendation: keep FileVault enabled.** This protects data at rest if the Mac is lost or stolen. The availability trade-off is material: after a reboot (including a macOS update that restarts the machine), Atlas Core cannot start as the owner LaunchAgent until the owner signs in locally and unlocks the login Keychain. Until then, iPhone access is unavailable; while travelling, an unattended reboot can leave Atlas unreachable for the remainder of the trip. Do not enable automatic login or weaken FileVault to make background services available before login. Before release, test on the target Mac whether authenticated software-update restarts preserve Core/Keychain availability; assume they do not until verified. A system-keychain alternative is a separate security design with its own threat model and owner decision, not an automatic workaround.

## Owner-client authority

Only an enrolled, authenticated owner client may change settings or source grants. Core validates client identity, signed request freshness/nonce, replay protection and audit. iOS enrolment is a later Stage 8 gate.


## Stage 3 status correction — current acceptance register (2026-11-22)

The owner has authorised the bounded acceptance split in [STAGE-3-EXECUTION-PLAN.md](STAGE-3-EXECUTION-PLAN.md) §12.10. Stage 3 is **NOT YET ACCEPTED**: all Stage 3-testable requirements must be complete on one exact commit, including the criterion 11 P1 taint fix, least-privilege sandbox and disabled-by-default egress integration; criterion 4 synthetic adversarial evaluation; criterion 12 harness, developer baseline and thresholds; criterion 13 automated app/Core lifecycle evidence; all remaining criterion testable portions; full-stage architect review; and explicit owner acceptance. Selected-real-model evaluation, target-Mac measurements, real TCC/Mail-store verification, human UI/accessibility walkthrough, live-Internet enablement, signing/notarisation and self-contained installation are mandatory final-stage release gates, not Stage 3 blockers. They remain pending and must never be represented as passed.

## Current stage register — authoritative (2026-11-22)

This register supersedes historical or contradictory stage-status wording elsewhere in this handover. Status means full stage acceptance, not work-package progress or project sequencing.

| Stage | Current status | Evidence / boundary |
|---|---|---|
| Stage 0 — documentation review and reconciliation | **COMPLETE / ACCEPTED** | Claude consistency confirmation in PR #7 comment 7023445432. Historical documentation scope only. |
| Stage 1 — implementation audit / gap analysis | **COMPLETE / ACCEPTED** | Claude audit reports in PR #7 comments 7022436618, 7022456916, 7022810935 and superseding note 7022967306; ChatGPT acceptance in 7022990234. Audit only; it did not implement the target product. |
| Stage 2 — Core foundation | **ACCEPTED FOR REVIEWED SCOPE** | ChatGPT formal acceptance in PR #8 comment 7047659436 at exact reviewed code head 58210223398a5715b618d1163397104efd358d49; exact-head CI 22/22. This is bounded scope acceptance, not production/release sign-off. PR #8 remains draft/unmerged. Any later code changes are not automatically covered by that acceptance. |
| Stage 3 — testable Mac/Core engineering slice | **NOT YET ACCEPTED; split authorised** | Acceptance requires every testable portion of all 15 criteria, P1/high findings fixed, exact-head CI, one full-stage architect PR review and explicit owner acceptance. Criteria 4/11/12/13 have explicit Stage 3 vs final-stage subdivisions in §12.10 of the execution plan. Selected-model, target-Mac, real-store/TCC, human UX, live-Internet enablement, signing/notarisation and self-contained installation remain mandatory final-stage release gates. This is not owner-tryable/release acceptance. PR #8 remains draft/unmerged until the bounded Stage 3 gates pass. |
| Stage 4 and later | **NOT STARTED / NOT ACCEPTED** | No stage acceptance may be inferred from Stage 3 sequencing, roadmap placement or work in progress. Each requires its own approved scope and closure gate. |

**Current rule:** only a stage with every mandatory criterion ACCEPTED, exact-commit evidence, full-stage independent PR review and explicit owner acceptance may be marked COMPLETE. Any missing, partial, blocked, waived-without-owner-approval or unverified mandatory item keeps the stage NOT ACCEPTED.


## App and browser automation architecture decision (2026-11-22)

The canonical target is defined in [TARGET_ARCHITECTURE.md §20](TARGET_ARCHITECTURE.md) and the product requirement in [PRD.md §4.8](PRD.md). Atlas Core owns planning, typed capability contracts, permissions, durable task state, Action Runtime execution, verification and audit. Browser automation is local and Playwright-based by recommendation; macOS app automation uses a capability ladder (official APIs, Shortcuts/App Intents, AppleScript/JXA, Accessibility APIs, then visual control as a last resort). Workers are isolated and least-privileged; secrets stay in OS credential storage; web/app content is untrusted; the existing closed approval policy is unchanged. General-purpose browser/app workflows are Stage 6 target scope, not Stage 3 implementation or acceptance. OpenClaw is not an adopted dependency; any future use requires a separate ADR and explicit owner approval. G-R11/G-R12 record these recommendations in DECISIONS.md.


## Documentation update log — 2026-11-25

- Added an explicit canonical answer contract and cross-model response-consistency harness to `INTELLIGENCE_AND_PERFORMANCE.md` §4.1. It defines semantic invariants, provenance/state requirements, route-switch and follow-up tests, metamorphic tests, model-adapter contract tests and exact-commit regression gates. This is a target requirement; implementation and CI enforcement are not yet verified.
- Extended `USE_CASE_REGISTER.md` with UC-050 Sports and statistics query, UC-051 Personal operating context, and UC-052 Home energy and usage tracking. These are target scenarios with staged acceptance evidence, not claims of implemented features.
- The existing UI specification already documents the calm, uncluttered Atlas direction and explicitly rejects crowded card/metric dashboards. The existing home capability already covers device state, energy, heating, environment and reversible automation; UC-052 makes usage tracking and measured-versus-estimated data explicit.
- The existing network policy permits public Internet research through Core-mediated, data-minimised egress while prohibiting cloud inference and private-content uploads without exact approval. Do not describe Atlas as globally offline-only; public research and AI inference are separate paths.
- Canonical updates are on `genesis-stage2-foundation` (PR #8): use-case commit `c3cdcf11ccdd2c52589601629fb94289faa4a294`; intelligence/consistency commit `ecae83cb2a0356fa16ef001f8f116da7e407844f`. No implementation, stage acceptance or release status changed.
- A prior assistant edit was mistakenly made on historical `orbit` files (`docs/architecture.md`, `atlas/README.md`). Those are not the authoritative Genesis documents and must not override `docs/genesis/*`, especially the accepted G-O01 model stack and `INTERNET_AND_NETWORK_POLICY.md`. Treat those historical edits as non-authoritative until reconciled or reverted.


## Product experience expansion — 2026-11-25

- Owner delegated product design direction to ChatGPT: design Atlas as the integrated product rather than asking the owner to specify each screen or workflow.
- Added UC-053 AI/technology/science news desk, UC-054 personal investment cockpit, and UC-055 Sports centre/Stats query to USE_CASE_REGISTER.md.
- Expanded UI_UX_SPECIFICATION.md: one curated Discover destination (AI & Technology, Markets, Sports), natural-language Stats query with competition/season/team/player filters, and a dedicated Investments workspace within Finance. Updated primary navigation accordingly.
- Design intent: these are focused capabilities inside the single Atlas application, not separate apps. Discover is finite and prioritised, not an infinite feed; Investments emphasises portfolio understanding, risk and evidence rather than trading stimulation; Sports combines current coverage with historical statistical depth.
- These are documented target experiences. Their data integrations, screens and runtime behaviours are not claimed to be implemented or accepted.
- Latest documentation commits: use-case expansion 78d8297ce78be19612d367c98f5e485c85e292ed; UI/UX expansion c7e2a04debe7a5ac48b5d5bc1c81ce8c5d380ee0.


## UX simplification correction — 2026-11-25

The owner clarified that Atlas must remain neat, easy and comfortable for an everyday regular user; every capability must not become a visible section. The canonical UI/UX specification was corrected accordingly (commits `2ef0d47d21ac52e73fc1fde13adc5ea54414c739` and `d0b61a964996e8d2562558f13ddb96942b85d3a4`). The persistent everyday navigation is now limited to **Home, Ask Atlas, Explore and Library**. Settings is a restrained utility; task activity is contextual with a secondary full-history route. Investing, home energy, fitness, nutrition, cricket statistics, Olympics, politics/current affairs, travel and other capabilities open contextually from natural language, relevant content or search; they do not each receive a permanent navigation item. Dedicated layouts are allowed only as focused, contextual workspaces. Progressive disclosure is mandatory: simple result first, advanced filters/details on demand. This is a design/documentation correction only; no implementation or visual acceptance is claimed. Read back the canonical UI/UX file before implementation and remove any conflicting feature-first navigation from the app.


## Adaptive dashboard design — 2026-11-25

Owner delegated dashboard design to the product/design authority, with the requirement that dashboards remain relevant and engaging for regular daily use while the app stays neat and uncluttered. Canonical UI/UX spec expanded in commit `c676bff5aa42b6decd2e9a2fbf5867ff8b8bcedf`:
- Home is the sole default dashboard: adaptive daily briefing, one lead item at most, a compact “For you today” synthesis and contextual continuation. No static widget wall.
- Explore is a curated interest-led discovery/reading surface, not an infinite feed or second Home dashboard.
- Specialist dashboards are contextual workspaces opened only when a task benefits from them; each leads with the answer, decision-relevant facts, one next action and progressive detail/evidence.
- Relevance uses explicit priorities, deadlines, active-task relevance, followed topics, novelty, freshness and source quality; it respects mutes/dismissals and avoids repetitive content. No addictive engagement optimisation, clickbait or fabricated filler.
- Defined first-run, no-source, quiet-day, stale/partial, loading/error and returning-visit states, plus lightweight user controls and source traceability.

This is a design specification update only. It does not claim implementation, usability testing or owner visual acceptance. Claude should implement against the canonical UI/UX spec rather than inventing permanent feature dashboards.


## Visual identity elevation — 2026-11-25

Owner feedback: the first dashboard concept felt too basic and boring. The canonical UI/UX spec was elevated in commit `86ceea52f8d7b0b5e65cdb971423dbcd8fdf3d8a`. Do not interpret “uncluttered” as generic minimalism. Atlas must have a distinctive, premium editorial visual identity: deep ink/graphite and warm light surfaces, a disciplined vivid accent, expressive typography, deliberate asymmetric composition, purposeful imagery and data visualisations, subtle meaningful motion, and polished states. Home earns a visually dominant “Today's signal” hero only when there is a genuinely important item; supporting content uses a deliberate composition, not uniform KPI cards. Explore should feel like a premium digital journal, not a generic list/feed. Specialist workspaces should use domain-appropriate visualisations. Avoid cheap gradients/glassmorphism, decorative charts, fake live states and repetitive cards. This is a design direction/specification update only; actual implementation and owner visual acceptance remain pending. Claude should produce real screen implementations/screenshots for review, not treat reference image search as a design deliverable.


## Product mental model clarified — personal smart intranet — 2026-11-25

Owner clarified that Atlas is best understood as their **personal smart intranet**. This is now reflected in `docs/genesis/PRD.md` and `docs/genesis/UI_UX_SPECIFICATION.md`. It is a private, intelligent home base for one person's digital life, combining a portal, contextual Spaces (e.g. Home, Investments, Sport, Fitness, Travel, Projects), connected searchable knowledge, personalised discovery and integrated services. It is an experience metaphor, not a multi-user corporate intranet. Keep the four-destination outer navigation simple; let Spaces be reached contextually through intent, search, relevant content and optional pinned shortcuts. Connect discovery → questions → Spaces → authorised knowledge → tasks/actions. Do not turn every capability into a permanent section or reproduce a corporate intranet directory. The UI should feel like a lived-in personal environment, not a blank template; never fabricate activity. Documentation only; implementation and owner visual acceptance remain pending.
