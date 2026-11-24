# Project Genesis — Atlas canonical documentation

**Purpose:** One authoritative product, UX, architecture and delivery specification for Atlas.  
**Last reconciled:** 2026-11-25  
**Working branch:** `genesis-stage2-foundation` · **Shared PR:** #8 (open, draft, unmerged)

## Product definition

Atlas is one local-first personal AI operating system: a personal smart intranet and intelligent chief of staff. It unifies chat, voice, a calm contextual dashboard, connected knowledge, memory, domain capabilities, integrations, automation, notifications and action history. It is not a suite of mini-apps.

The everyday UI must be neat, approachable and uncluttered. Persistent primary navigation is **Home, Ask Atlas, Explore and Library**. Specialist capabilities (for example Investments, Home energy, Sports/Stats, Travel, Fitness, News and Projects) open contextually and must not each become permanent navigation sections. Settings is a restrained utility.

macOS is first; secure iOS access is a later platform goal. Android is out of scope. Personal-data processing and inference remain local and owner-controlled. Public Internet research is a distinct, governed egress path; it does not authorise cloud inference or silent fallback.

## Canonical authorities

| Concern | Authority | Rule |
|---|---|---|
| Product intent, scope, user-visible behaviour, approval policy | [PRD](PRD.md) | Product contract; do not redefine it in technical documents |
| Visual direction, information architecture, screens, states, interaction and accessibility | [UI/UX specification](UI_UX_SPECIFICATION.md) | One canonical UX authority |
| System boundaries, flows, components and delivery sequence | [Target architecture](TARGET_ARCHITECTURE.md) | §11 is the sole roadmap |
| Scenarios, edge cases and integration capability inventory | [Use-case register](USE_CASE_REGISTER.md) | Do not duplicate the scenario inventory elsewhere |
| Settled owner choices and open decisions | [Decision register](DECISIONS.md) | Owner decision outranks recommendation |
| Data structures and detailed technical behaviour | [Low-level design](LOW_LEVEL_DESIGN.md) | Must remain consistent with PRD and architecture |
| Memory, privacy, retention and provenance | [Memory and privacy](MEMORY_PRIVACY_KNOWLEDGE.md) | Cross-cutting data-governance contract |
| Ingestion and durable processing | [Ingestion pipeline](INGESTION_PIPELINE.md) | Processing, coverage and recovery contract |
| Local intelligence, model routing and performance | [Intelligence and performance](INTELLIGENCE_AND_PERFORMANCE.md) | No cloud inference; benchmark claims require evidence |
| Public Internet, network and egress controls | [Internet and network policy](INTERNET_AND_NETWORK_POLICY.md) | Public research is not cloud inference |
| Collaboration, change control and acceptance | [Delivery protocol](DELIVERY_PROTOCOL.md) | Sole process authority |
| Current restart point and verified status | [Handover](HANDOVER.md) | Operational summary only |
| Code-to-document audit | [Implementation conformance](IMPLEMENTATION_CONFORMANCE.md) | Evidence ledger; does not itself accept a release |
| Reviewer history, changed-path coverage and open comments | [Review coverage reconciliation](REVIEW_COVERAGE_RECONCILIATION.md) | Review ledger, not product specification |
| Branch/commit provenance | [Branch-history reconciliation](BRANCH_HISTORY_RECONCILIATION.md) | Historical inventory; not a substitute for current-head verification |

## Read order

1. [PRD](PRD.md)
2. [UI/UX specification](UI_UX_SPECIFICATION.md)
3. [Target architecture](TARGET_ARCHITECTURE.md)
4. [Use-case register](USE_CASE_REGISTER.md)
5. [Decision register](DECISIONS.md)
6. [Low-level design](LOW_LEVEL_DESIGN.md)
7. [Memory and privacy](MEMORY_PRIVACY_KNOWLEDGE.md)
8. [Ingestion pipeline](INGESTION_PIPELINE.md)
9. [Intelligence and performance](INTELLIGENCE_AND_PERFORMANCE.md)
10. [Internet and network policy](INTERNET_AND_NETWORK_POLICY.md)
11. [Implementation conformance](IMPLEMENTATION_CONFORMANCE.md)
12. [Delivery protocol](DELIVERY_PROTOCOL.md)
13. [Handover](HANDOVER.md)
14. [Review coverage reconciliation](REVIEW_COVERAGE_RECONCILIATION.md)
15. [Stage 3 execution plan](STAGE-3-EXECUTION-PLAN.md)
16. [Stage 3 baseline audit](STAGE-3-BASELINE-AUDIT.md)
17. [Stage 2 work package](STAGE-2-WORK-PACKAGE.md)
18. [G-O17 platform/runtime ADR](ADR-G-O17-PLATFORM-RUNTIME.md)
19. [Stage 3 contract delta](STAGE-3-CONTRACT-DELTA.md) — historical/superseded; WP3.1 authority is `core/docs/CONTRACT_1_1.md`.

## Implementation and acceptance boundary

These documents define what Atlas is intended to do. They are not proof that a capability is implemented, integrated, tested on target hardware, accepted or released. Those claims require exact-commit code and test evidence.

At the 2026-11-25 reconciliation, PR #8 is open, draft and unmerged. Its branch contains macOS app, Core, iOS client, tests and technical documentation. Stage 2 and WP3.1/WP3.2 have bounded exact-commit acceptances recorded in [Handover](HANDOVER.md). Stage 3 is not accepted; final-stage gates remain open. Stage 4–8 work is present on the branch but is not architect-reviewed or accepted. See [Implementation conformance](IMPLEMENTATION_CONFORMANCE.md) and the technical stage records in `core/docs/`.

## Status vocabulary

- **DECIDED** — explicitly established by the owner.
- **TARGET** — required product/architecture behaviour; not proof of implementation.
- **IMPLEMENTED** — code path exists and has been inspected at a named commit.
- **TESTED** — named automated/manual tests passed in a stated environment at a named commit.
- **ACCEPTED** — exact scope and exact commit passed the required independent review and owner gate.
- **OWNER-VERIFIED** — exercised on the owner's target hardware/accounts/data with explicit confirmation.
- **UNVERIFIED** — evidence is absent or insufficient.
- **DEFERRED** — intentionally scheduled later, not silently dropped.
- **SUPERSEDED** — retained for history; a named current authority replaces it.

Never use “complete” without naming whether it means documentation, implementation, test, stage acceptance or release readiness.

## Source-of-truth and change control

- Code and executable tests establish current implementation behaviour; specifications establish intended behaviour.
- PRD is authoritative for product behaviour and the exhaustive approval categories in §4.4. Technical documents may refine implementation, not widen approval prompts.
- UI/UX specification is authoritative for the everyday experience and visual hierarchy.
- Target architecture §11 is the only roadmap. Other documents may cite stage numbers but must not create a competing sequence.
- Owner decisions outrank recommendations. Record durable changes in DECISIONS.md.
- When implementation differs from a target, record the exact requirement, code path, tests, impact and classification. Do not quietly rewrite the target to match code.
- Preserve historical decisions, reviews and evidence. Correct current summaries with dated, traceable amendments.
- Each material requirement must ultimately trace to implementation, tests, failure behaviour and evidence. Missing evidence remains explicitly unverified.
