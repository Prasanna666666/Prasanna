# Project Genesis — Atlas target documentation

**Status:** Consolidated architecture baseline; implementation/release gates remain  
**Product:** Atlas  
**Initiative:** Project Genesis  
**Baseline branch:** `atlas`  
**Documentation branch:** `genesis-stage2-foundation` (sole open PR #8)  
**Audience:** Product owner, architecture/review, Claude development and maintenance

## Purpose

This directory is the single authoritative target specification for the one Atlas application. macOS is first, followed by an iOS client with secure worldwide access; Android is out of scope. Legacy app shells are obsolete product boundaries; their capabilities are migrated into Atlas. Existing implementation/test records elsewhere in `docs/` are evidence of current behaviour only, not competing target specifications.

The existing application, its tests, security controls, data stores and PR review evidence remain the implementation baseline. The target described here is not a claim that those capabilities already exist.

## Read in this order

1. [Product requirements](PRD.md) — product intent, users, scope and requirements.
2. [Target architecture](TARGET_ARCHITECTURE.md) — boundaries, components and system flows.
3. [Intelligence and performance](INTELLIGENCE_AND_PERFORMANCE.md) — local models, routing, latency and answer quality.
4. [Memory, knowledge and privacy](MEMORY_PRIVACY_KNOWLEDGE.md) — governed persistent context and provenance.
5. [Ingestion and durable processing](INGESTION_PIPELINE.md) — reliable document and source processing.
6. [Decision register](DECISIONS.md) — settled owner decisions and open decisions.
7. [Delivery protocol](DELIVERY_PROTOCOL.md) — roles, handshakes, issue resolution, change control and acceptance.
8. [Handover](HANDOVER.md) — repository pointers, confirmed status and next gate.
9. [G-O17 platform/runtime ADR](ADR-G-O17-PLATFORM-RUNTIME.md) — owner-accepted shared Swift/SwiftUI application boundary; Core language remains open under G-O20.
10. [Stage 2 foundation work package](STAGE-2-WORK-PACKAGE.md) — owner-authorised bounded implementation scope, contracts, acceptance criteria and stop conditions.
11. [Detailed low-level technical design](LOW_LEVEL_DESIGN.md) — consolidated architecture-review baseline; recommendations only, not implementation/Stage 3 authorisation.

## Current decision/work-package status

G-O17 and Stage 2 authority were accepted by the owner. Claude's documentation review 7045420044 has been reconciled in this branch. The owner-selected MLX/~27B direction, model transparency and routing policy are recorded; G-O01 benchmark and G-O20 Core-language evidence gates remain open. PR #9 is closed/unmerged; its detailed low-level design is now included here as a review baseline, not as an approved implementation plan. PR #8 is the only open PR. Stage 2 code blockers have been accepted by independent review, while macOS/target-Mac verification and release readiness remain pending. Stage 3 is **NOT AUTHORISED**.

## Source-of-truth rules

- Existing implementation and review records under `docs/` describe current behaviour and test evidence. The initial implementation gap analysis was completed in Stage 1 (PR #7 comment 7022436618, §3). Map the standing rules, defect list, coverage matrix, comment tracker and any other legacy records to Genesis requirement IDs during Stage 2 work: (a) still binding and migrated into a canonical Genesis document, (b) historical evidence retained and linked, (c) superseded by an explicit Genesis rule, or (d) obsolete duplicate to be archived only with owner-safe history preservation. Do not assume that an unreferenced legacy file is obsolete, and do not maintain competing live specifications.
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
