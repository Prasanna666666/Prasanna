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

**Next gate — Stage 2 is NOT AUTHORISED.** Before any Stage 2 work:
1. G-O17 must be resolved through an evidence-backed, accepted platform/runtime ADR, with Mac+iPhone code sharing as the top runtime criterion.
2. ChatGPT must review a bounded Stage 2 work package, including scope, interfaces, acceptance tests, risks and rollback.
3. The owner must explicitly authorise Stage 2.

The Stage 1 audit included the iOS target in its assessment. Mobile implementation remains separately gated; secure remote access, device security, offline/sync and mobile release require their own ADRs and staged acceptance. Resolving G-O18 or G-O19 does not satisfy the Stage 2 gates.

**Current authority:** no Stage 2 work, code changes, migrations, app retirement, data movement or destructive action is authorised. Preserve all existing branches, user data, keys and history.

## Evidence status

This handover is a target/documentation instruction, not proof that legacy apps have already been retired or that the implementation has been consolidated. Current behaviour must be established from code, tests and CI. Target-Mac and local-model checks must be explicitly reported as owner-verified or pending.
