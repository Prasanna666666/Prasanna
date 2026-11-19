# Atlas — Handover

**Status:** Updated for the owner-confirmed single-application direction  
**Repository:** `Prasanna666666/Prasanna`  
**Documentation branch:** `genesis-architecture`  
**Implementation baseline:** `atlas`

## Authoritative entry point

Start with [README.md](README.md), then read the canonical documents it indexes. The [Delivery Protocol](DELIVERY_PROTOCOL.md) is the sole authority for role ownership, collaboration, handshakes, issue resolution, change control and acceptance. Do not duplicate those rules here.

## Owner-confirmed product boundary

There is exactly **one Atlas application**. Standalone Finance, Documents, Images and other legacy application shells are obsolete. Their useful features and data must be integrated into Atlas as internal capabilities. Hidden helper processes are allowed only when technically justified; they do not constitute separate apps.

## Repository handling

- `atlas` is the implementation baseline for gap analysis.
- `genesis-architecture` contains this target documentation and handover.
- `aperture` is the repository default/legacy Photos branch, not the Atlas product target.
- `orbit` is historical reference material, not the active implementation baseline.

Do not delete branches, historical evidence, user data, databases or indexes as part of documentation cleanup. Retire obsolete app shells only through an approved, tested migration with data preservation and rollback.

## PR #7 immediate action

Claude must inspect the current implementation and return a requirement-by-requirement gap analysis. Specifically map all legacy standalone app features, services, APIs, schemas, data stores, tests and operational scripts to the single Atlas application. Recommend a safe retirement/migration sequence and identify any helper process that must remain for isolation or platform reasons.

No broad rewrite or destructive cleanup starts until ChatGPT reviews the analysis and issues a bounded work package. The owner approves product-scope changes and final acceptance.

## Evidence status

This handover is a target/documentation instruction, not proof that legacy apps have already been retired or that the implementation has been consolidated. Current behaviour must be established from code, tests and CI. Target-Mac and local-model checks must be explicitly reported as owner-verified or pending.
