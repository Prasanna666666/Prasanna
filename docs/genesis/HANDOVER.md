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

**Stage 3 — NOT ACCEPTED / OPEN as of 2026-11-22.** The execution plan is [STAGE-3-EXECUTION-PLAN.md](STAGE-3-EXECUTION-PLAN.md). WP3.0 baseline audit and WP3.1 contract/specification are accepted. **WP3.2 document-only vertical path is accepted** at exact commit `ad6e59bcb6fb5d6124ac56ea419f8330dc913e4c` (ChatGPT review 6000818496): UTF-8 text/Markdown only, encrypted index, exact block citations, truthful failed coverage, descriptor-relative no-follow reads, no model call without usable evidence, and synthetic restart/idempotency/security tests. Its limits remain explicit: no PDF/Office/HTML/Mail, lexical ranking only, coverage not yet in the answer envelope, and no target-Mac parser isolation or hardware verification. WP3.3 Mail is the next conditional package; no Mail content retrieval may begin until the G-O19 Get Started/designation mechanism and explicit owner enablement are in place. G-O18 remains the technical attachment-package acceptance gate (all supported formats). Stage 3 proceeds in plan order with exact-SHA review. Mac-dependent work waits for target hardware. This authorisation does not waive G-O12, G-O02/G-O05, destructive-migration controls, or Stage 4–8 and remote-exposure gates.

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

A prior handover note described Stage 3 as closed for project sequencing with limitations carried forward. That wording is superseded and must not be used as an acceptance status. Under the current mandatory stage gate, Stage 3 is **NOT ACCEPTED / OPEN** until every mandatory criterion is implemented and evidenced, all required owner-Mac/real-model/UX checks are completed, the full-stage independent PR review accepts the exact final commit, and the owner explicitly accepts the stage. Criteria 4, 11, 12 and 13 remain open; the egress gateway is not wired into the answer flow and its ordinary-name/short-phrase taint bypass must be fixed and independently reviewed before public-search integration. No carry-forward or sequencing disposition closes these mandatory requirements.

## Current stage register — authoritative (2026-11-22)

This register supersedes historical or contradictory stage-status wording elsewhere in this handover. Status means full stage acceptance, not work-package progress or project sequencing.

| Stage | Current status | Evidence / boundary |
|---|---|---|
| Stage 0 — documentation review and reconciliation | **COMPLETE / ACCEPTED** | Claude consistency confirmation in PR #7 comment 7023445432. Historical documentation scope only. |
| Stage 1 — implementation audit / gap analysis | **COMPLETE / ACCEPTED** | Claude audit reports in PR #7 comments 7022436618, 7022456916, 7022810935 and superseding note 7022967306; ChatGPT acceptance in 7022990234. Audit only; it did not implement the target product. |
| Stage 2 — Core foundation | **ACCEPTED FOR REVIEWED SCOPE** | ChatGPT formal acceptance in PR #8 comment 7047659436 at exact reviewed code head 58210223398a5715b618d1163397104efd358d49; exact-head CI 22/22. This is bounded scope acceptance, not production/release sign-off. PR #8 remains draft/unmerged. Any later code changes are not automatically covered by that acceptance. |
| Stage 3 — first owner-tryable Mac app | **NOT ACCEPTED / OPEN** | All 15 criteria remain subject to the stage gate. The latest full-stage review recorded criteria 4, 11 and 12 PARTIAL and 13 PENDING-M, plus the egress private-name/short-phrase taint bypass. Hosted CI does not satisfy target-Mac, real-model or owner UX evidence. WP acceptances do not accept Stage 3. PR #8 stays draft/unmerged. |
| Stage 4 and later | **NOT STARTED / NOT ACCEPTED** | No stage acceptance may be inferred from Stage 3 sequencing, roadmap placement or work in progress. Each requires its own approved scope and closure gate. |

**Current rule:** only a stage with every mandatory criterion ACCEPTED, exact-commit evidence, full-stage independent PR review and explicit owner acceptance may be marked COMPLETE. Any missing, partial, blocked, waived-without-owner-approval or unverified mandatory item keeps the stage NOT ACCEPTED.
