# Atlas — Handover

**Status:** Updated for single-application direction, personal-work Agent Workforce, macOS-first then iOS platform target, and documents-plus-Mail read-only first workflow  
**Repository:** `Prasanna666666/Prasanna`  
**Documentation branch:** `genesis-architecture`  
**Implementation baseline:** `atlas`

## Authoritative entry point

Start with [README.md](README.md), then read the canonical documents it indexes. The [Delivery Protocol](DELIVERY_PROTOCOL.md) is the sole authority for role ownership, collaboration, handshakes, issue resolution, change control and acceptance. Do not duplicate those rules here.

## Owner-confirmed product boundary

There is exactly **one Atlas application**. Standalone Finance, Documents, Images and other legacy application shells are obsolete. Their useful features and data must be integrated into Atlas as internal capabilities. Hidden helper processes are allowed only when technically justified; they do not constitute separate apps. macOS is first, followed by an iOS client usable worldwide wherever secure connectivity is available. Android is out of scope. Atlas Core and AI inference remain under owner control; worldwide access must not introduce cloud inference.

## Repository handling

- `atlas` is the implementation baseline for gap analysis.
- `genesis-architecture` contains this target documentation and handover.
- `aperture` is the repository default/legacy Photos branch, not the Atlas product target.
- `orbit` is historical reference material, not the active implementation baseline.

Do not delete branches, historical evidence, user data, databases or indexes as part of documentation cleanup. Retire obsolete app shells only through an approved, tested migration with data preservation and rollback.

## PR #7 status and next gate

**Stage 0 — documentation review and reconciliation: COMPLETE.** Claude's full-document consistency confirmation is recorded in PR #7 comment 7023445432.

**Stage 1 — implementation audit / gap analysis: ACCEPTED AND CLOSED.** Claude's audit reports are recorded in PR #7 comments 7022436618, 7022456916 and 7022810935, with the superseding final note in 7022967306. ChatGPT's formal acceptance is recorded in comment 7022990234. The audit was documentation/evidence work only; its stated limitations and unverified Mac-dependent behaviour remain in force.

The completed sequence is retained in the PR discussion as the audit trail. It does not grant implementation authority.

**Architecture decision and Stage 2 authority — COMPLETE.** Claude's technical challenge is recorded in PR #7 comment 7035425400 and its focused document verification in 7037231906. The owner accepted G-O17 and explicitly authorised Stage 2 on 2026-11-20; the owner waived the ChatGPT package-acceptance gate so implementation could proceed (decision recorded in PR #7 comment 7037299974 and subsequent owner instructions). These decisions are final; do not ask the owner to repeat them.

**Current Stage 2 implementation gate — PR #8 review pending.** Stage 2 implementation is in [PR #8](https://github.com/Prasanna666666/Prasanna/pull/8), draft and unmerged. The first independent review identified three blockers; Claude addressed them in head `481610f`. Re-review then found one remaining read-time revocation issue: zero-citation answers and final events can still expose text derived from a revoked source (review 5992662031). Claude must fix that issue and add regression tests; ChatGPT must independently re-review the resulting head. The actual macOS Keychain and `LOCAL_PEERCRED` paths, target-Mac execution and Swift/Xcode integration remain unverified and must not be claimed as passed.

**Stage 3 is NOT AUTHORISED.** No Stage 3 implementation, real source ingestion/search, Mail attachment processing, remote exposure, data migration or destructive action is authorised by the Stage 2 decision. G-O18, G-O19, G-O14 and other feature-specific gates remain in force.

The Stage 1 audit included the iOS target in its assessment. Mobile implementation and worldwide secure access remain separately gated by the remote-access threat model, device identity, offline/sync and mobile release decisions.

## Evidence status

This handover is a target/documentation instruction, not proof that legacy apps have already been retired or that the implementation has been consolidated. Current behaviour must be established from code, tests and CI. Target-Mac and local-model checks must be explicitly reported as owner-verified or pending.
