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

## PR #7 current sequence

1. Claude's documentation review and second review are recorded in the PR discussion.
2. ChatGPT applies the accepted documentation reconciliation to the canonical Genesis documents on this branch only.
3. Claude re-reads the complete canonical set and confirms consistency, or lists exact remaining gaps.
4. Only after that confirmation, Claude performs the implementation gap analysis against `atlas`, without changing code or data.
5. ChatGPT reviews the evidence-backed gap analysis and prepares a bounded implementation brief. Owner approval remains required for product priorities, reserved privacy choices and consequential scope/risk decisions.
6. The future iOS target is included in the gap analysis. Do not start mobile implementation during the current documentation-confirmation stage; remote-access topology, device security, offline/sync and mobile release require separate ADRs and staged acceptance.
7. Stage 2 is not authorised by documentation sign-off or by resolving G-O18/G-O19. It requires the G-O17 runtime ADR, ChatGPT review of a bounded Stage 2 package, and the owner's explicit authorisation.

**Current assignment:** documentation reconciliation and confirmation only. The implementation audit is held until step 3 is complete. No code changes, migrations, app retirement, data movement or destructive action are authorised during this stage.

## Evidence status

This handover is a target/documentation instruction, not proof that legacy apps have already been retired or that the implementation has been consolidated. Current behaviour must be established from code, tests and CI. Target-Mac and local-model checks must be explicitly reported as owner-verified or pending.
