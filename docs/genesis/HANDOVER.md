# Atlas — Project Handover

**Prepared:** 2026-11-19  
**Status:** Handover package prepared; owner acceptance and developer gap analysis pending  
**Product owner:** User  
**Architecture/documentation owner:** ChatGPT  
**Developer/tester/maintainer:** Claude

## 1. Purpose

This document is the single entry point for the next development handover. It identifies the authoritative documents, repository state, role boundaries, known evidence and the first required developer response.

This is a planning and documentation handover. It does not claim that the target architecture is implemented, that the application has been tested on the owner's Mac, or that any open pull request is accepted.

## 2. Repository and branch map

Repository: [Prasanna666666/Prasanna](https://github.com/Prasanna666666/Prasanna)

| Ref | Role | Handling |
|---|---|---|
| `aperture` | Default branch; standalone Photos/Aperture history | Preserve; not the target for Atlas handover work |
| `atlas` | Current Atlas implementation branch and base for the current review PR | Implementation baseline |
| `genesis-architecture` | Project Genesis documentation branch | Documentation handover branch |
| `orbit` | Older Atlas/Orbit-era branch and documentation | Historical reference; do not treat as current baseline |

The repository's default branch is currently `aperture`; this does not make it the active Atlas integration branch. Do not change the default branch as part of this handover.

## 3. Canonical documentation set

The following files under `docs/genesis/` are the authoritative Project Genesis target documents. Each has one canonical path; do not create copies elsewhere.

1. `README.md` — index, status vocabulary and document governance.
2. `PRD.md` — product intent, scope, experience and quality requirements.
3. `TARGET_ARCHITECTURE.md` — target component model, boundaries and migration direction.
4. `INTELLIGENCE_AND_PERFORMANCE.md` — model strategy, response quality, evaluation and latency.
5. `MEMORY_PRIVACY_KNOWLEDGE.md` — governed memory, provenance, sensitivity and retention.
6. `INGESTION_PIPELINE.md` — durable, restart-safe source processing and cross-document linking.
7. `DECISIONS.md` — owner decisions, recommendations and open decisions.
8. `DELIVERY_PROTOCOL.md` — role ownership, work-package handshake and definition of done.
9. `HANDOVER.md` — this operational handover and next actions.

`docs/README.md` remains the repository-wide documentation index. Existing implementation, security, defect, test and review documents remain the evidence for the current code. They are not alternate copies of the target PRD or target architecture.

## 4. Source-of-truth hierarchy

When sources disagree, apply this order:

1. Explicit, most recent owner decision.
2. `docs/genesis/DECISIONS.md` for recorded owner decisions and accepted ADRs.
3. `docs/genesis/PRD.md` for product requirements.
4. `docs/genesis/TARGET_ARCHITECTURE.md` and its focused companion specifications for target design.
5. Current code, executable tests and CI for what is actually implemented.
6. Legacy implementation documentation and PR descriptions as supporting evidence, checked against the current branch.

A target requirement must never be described as implemented merely because it appears in a specification. Every implementation claim needs a code path and test/evidence reference.

## 5. Current repository / review state observed

- PR #6: `atlas` into `aperture`, open and marked ready for review when inspected. It contains the implementation/review history and legacy evidence. Its latest CI status must be checked on GitHub before any acceptance decision.
- PR #7: `genesis-architecture` into `atlas`, open and marked draft when inspected. It contains the initial Project Genesis documentation baseline (nine changed files before this handover addition).
- The PR #7 description explicitly asks Claude to read the delivery protocol and return a current-code gap analysis before broad refactoring.
- No PR has been merged or closed by this handover.
- No branches, historical files, application data or user data have been deleted.

These are observations at the preparation time above; re-check live GitHub state before acting.

## 6. Clean-start rules

The clean start is logical and documentation-led, not destructive:

- Keep the existing implementation and its history intact.
- Do not delete or rename branches, old docs, databases, volumes, photo indexes or user data as a cleanup shortcut.
- Do not merge PR #6 or PR #7 without the required review and owner acceptance.
- Do not create a second PRD, architecture document, decision register or developer protocol.
- Put new target requirements in the canonical Genesis documents; put implementation evidence in the existing implementation/review records.
- Mark superseded material as historical or link to its canonical replacement; preserve its provenance.
- Before code work, Claude should start from a clean, updated checkout of the agreed branch and report any local modifications before switching branches or cleaning files. Never run destructive cleanup commands against an unknown working tree.

## 7. Required first developer handoff

Claude's first deliverable is a gap analysis, not a broad rewrite. It must compare the `atlas` implementation against every requirement in the Genesis documents and classify each as:

- **Implemented and verified** — point to code and tests/CI evidence.
- **Implemented, verification incomplete** — point to code and identify missing evidence.
- **Partially implemented** — identify the working subset and gap.
- **Not implemented** — state the missing capability.
- **Conflict / needs decision** — identify the conflicting owner decision or design and propose options.

The gap analysis must include:

1. Requirement ID and canonical document section.
2. Current implementation path(s) and relevant commit.
3. Existing tests and their actual scope.
4. Missing tests, benchmarks or real-Mac checks.
5. Security, privacy, data migration and rollback impact.
6. Dependency/order constraints.
7. Recommended smallest safe implementation slice.
8. Explicit blockers requiring the owner's decision.

Special attention is required for:
- Modular-monolith target versus current service boundaries.
- Local model/runtime abstraction and model independence.
- Unified chat, voice, dashboard, notifications and approvals.
- Memory lifecycle, provenance, sensitivity isolation and deletion propagation.
- Durable ingestion/job state, restart correctness and idempotency.
- Performance: time-to-first-useful-output, end-to-end latency, throughput and resource contention.
- Existing security controls and personal-data boundaries that must not regress.

No broad refactor starts until the gap analysis is reviewed and a first work package is approved.

## 8. Acceptance and evidence rules

For every work package, distinguish:
- developer-reported test results;
- CI results;
- architect-inspected code and tests;
- independently reproduced results;
- owner-only checks on the actual Mac and real local model.

Record exact commands, environment, commit SHA, model/runtime and hardware for benchmarks. A green unit-test suite does not prove real-Mac, real-model, privacy or end-to-end behaviour.

## 9. Ownership

- **Product owner / manager:** priorities, trade-offs, owner-reserved decisions and final acceptance.
- **Architecture/documentation owner (ChatGPT):** requirements, canonical documents, architecture, work packages, integration, independent review and honest status.
- **Developer/tester/maintainer (Claude):** implementation, developer tests, defect fixes, maintenance and implementation evidence.

Claude must not silently change product direction. ChatGPT must not claim implementation or testing it did not perform. The owner should only be asked questions that are genuinely unresolved and materially block safe progress.

## 10. Immediate next step

Claude reads `README.md`, `PRD.md`, `TARGET_ARCHITECTURE.md`, all focused specifications, `DECISIONS.md` and `DELIVERY_PROTOCOL.md`; then returns the gap analysis described in section 7. ChatGPT reviews it, reconciles documentation conflicts and prepares the first bounded implementation work package for owner approval.
