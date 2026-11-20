# Atlas — Handover

**Status:** Stage 2 review accepted; Stage 3 execution plan prepared, pending technical challenge and owner authorisation  
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

**Stage 3 — plan prepared; implementation NOT AUTHORISED / NOT STARTED.** The execution plan is [STAGE-3-EXECUTION-PLAN.md](STAGE-3-EXECUTION-PLAN.md). It defines the read-only documents-and-Mail vertical slice, work packages, source/privacy gates, acceptance criteria, test/evidence requirements, stop conditions and role ownership. Next sequence: Claude challenges the plan for feasibility and omissions without coding; ChatGPT reconciles findings and presents the final owner decision brief; the owner explicitly authorises Stage 3 before any implementation. G-O18 remains a technical attachment-package acceptance gate (owner scope: all supported formats). G-O19 requires the one-time Get Started onboarding and OS access to be implemented and verified; do not re-ask the owner for the design. No Stage 4–8 work, remote exposure, destructive migration or external side effects are authorised by this plan.

The Stage 1 audit included the iOS target in its assessment. Mobile implementation and worldwide secure access remain separately gated by the remote-access threat model, device identity, offline/sync and mobile release decisions.

## Evidence status

This handover is a target/documentation instruction, not proof that legacy apps have already been retired or that the implementation has been consolidated. Current behaviour must be established from code, tests and CI. Target-Mac and local-model checks must be explicitly reported as owner-verified or pending.

## Current owner direction update — 2026-11-20

The canonical product scope extends beyond the original read-only Documents/Mail plan. See PRD.md, DECISIONS.md, USE_CASE_REGISTER.md, INTERNET_AND_NETWORK_POLICY.md, TARGET_ARCHITECTURE.md and STAGE-3-EXECUTION-PLAN.md.

Key directions: single-user Atlas; one first-run Get Started flow; no routine approval prompts; local model access to owner-authorised Finance and Health; exact calculations code-checked; approval only for consequential external effects or materially irreversible changes; public Internet research under strict data-minimised egress; all supported Mail attachments in scope subject to technical acceptance; progressive newest-first indexing with visible coverage.

The use-case and network-policy documents have been added to this branch. This is documentation progress, not a working app build. Stage 3 implementation remains subject to its explicit authorisation gate; target-Mac integration and performance remain unverified.

## Always-on host and availability decision

Keep FileVault enabled. Atlas Core starts automatically as a user LaunchAgent after the owner logs in and unlocks the login Keychain. After a reboot but before owner login, the Mac host is locked and remote clients must show that sign-in is required. Do not enable automatic login or weaken FileVault to make background services available before login. Any system-keychain alternative requires a separate security design and target-Mac verification.

## Owner-client authority

Only an enrolled, authenticated owner client may change settings or source grants. Core validates client identity, signed request freshness/nonce, replay protection and audit. iOS enrolment is a later Stage 8 gate.
