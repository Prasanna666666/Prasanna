# Project Genesis — Atlas target documentation

**Status:** Architecture baseline in progress  
**Product:** Atlas  
**Initiative:** Project Genesis  
**Baseline branch:** `atlas`  
**Documentation branch:** `genesis-architecture`  
**Audience:** Product owner, architecture/review, Claude development and maintenance

## Purpose

This directory records the evolved product direction and the engineering contract for taking the existing Atlas application towards that direction. It complements—not replaces—the operational documentation in `docs/`.

The existing application, its tests, security controls, data stores and PR review evidence remain the implementation baseline. The target described here is not a claim that those capabilities already exist.

## Read in this order

1. [Product requirements](PRD.md) — product intent, users, scope and requirements.
2. [Target architecture](TARGET_ARCHITECTURE.md) — boundaries, components and system flows.
3. [Intelligence and performance](INTELLIGENCE_AND_PERFORMANCE.md) — local models, routing, latency and answer quality.
4. [Memory, knowledge and privacy](MEMORY_PRIVACY_KNOWLEDGE.md) — governed persistent context and provenance.
5. [Ingestion and durable processing](INGESTION_PIPELINE.md) — reliable document and source processing.
6. [Delivery and collaboration protocol](DELIVERY_PROTOCOL.md) — manager, architect/reviewer and developer responsibilities.
7. [Decision register](DECISIONS.md) — settled decisions, recommendations and unresolved ADRs.

## Source-of-truth rules

- `docs/decisions.md`, `docs/requirements.md`, `docs/design.md` and the test/review records describe the current implementation and previously recorded owner decisions. Read them before changing code.
- `docs/genesis/` describes the evolved target. Where it differs from current implementation, the difference is intentional only when explicitly marked as a target-state change or migration item.
- Code and executable tests determine what is implemented. Documentation must not claim otherwise.
- Owner decisions override recommendations. A recommendation is not an approved requirement until the owner accepts it.
- Do not delete or silently rewrite historical evidence. Amend it with dated, traceable updates.

## Status vocabulary

- **DECIDED** — explicitly established by the owner.
- **RECOMMENDED** — architecture recommendation awaiting owner acceptance where needed.
- **OPEN** — requires investigation, benchmark or owner decision.
- **CURRENT** — verified in the current code/docs at the stated commit.
- **TARGET** — desired future state, not yet implemented.
- **DEFERRED** — intentionally not part of the current delivery slice.

## Change control

Every material architecture or requirement change must identify: rationale, affected requirements, migration impact, security/privacy impact, tests/evidence, owner decision (if needed), and documentation updated. Use an ADR for decisions with lasting architectural consequences.
