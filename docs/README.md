# Atlas documentation

This directory is the source of truth for product intent, testable requirements and target architecture.

## Core documents

- [Product Requirements](PRODUCT_REQUIREMENTS.md) — product vision, outcomes, scope, autonomy, privacy and delivery direction.
- [Software Requirements](SOFTWARE_REQUIREMENTS.md) — functional and non-functional requirements with stable IDs and verification criteria.
- [Target Architecture](TARGET_ARCHITECTURE.md) — proposed architecture, trust boundaries, data ownership and migration strategy.
- [Standing Decisions](decisions.md) — historical owner decisions; reconcile against newer requirements.
- [Existing Architecture](architecture.md) — earlier architecture proposal and implementation snapshot; reference material, not automatically authoritative.

## Authority and change control

1. Product and software requirements define intended behaviour.
2. Target architecture defines the preferred technical direction, not permission for a wholesale rewrite.
3. Existing code is evidence of current behaviour, not proof of requirement compliance.
4. Material decisions require an Architecture Decision Record in `docs/adr/`.
5. Requirement changes must update the relevant documentation before or alongside implementation.
6. Never commit personal data, credentials, API keys, private documents or real user datasets.
7. Mark unresolved decisions as TBD. Do not silently invent answers.

## Completion standard

A feature is complete only when its acceptance criteria, positive and negative paths, failure behaviour, security boundaries, tests and documentation are satisfied.