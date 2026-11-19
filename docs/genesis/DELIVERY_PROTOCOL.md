# Atlas — Delivery and Collaboration Protocol

**Status:** Working agreement for Project Genesis  
**Owner:** Product owner / manager

## 1. Roles and decision rights

| Role | Owner | Responsibilities | Does not own |
|---|---|---|---|
| Manager / product owner | User | Product priorities, business trade-offs, final acceptance and decisions reserved for owner | Routine implementation details |
| Planner, architect, integrator, tester and reviewer | ChatGPT | Consolidate requirements, maintain target architecture, define contracts and acceptance criteria, plan increments, review developer work, identify risks, design/run independent checks where access permits, integrate documentation and report status | Feature implementation or claiming developer tests were run when they were not |
| Developer, tester and maintainer | Claude | Implement approved slices, write and run developer tests, fix defects, maintain code and implementation docs, report commits and evidence | Changing product direction or silently overriding owner decisions |

## 2. Single source of truth

- Product intent and owner decisions: `docs/genesis/PRD.md` and `docs/genesis/DECISIONS.md`.
- Target architecture: `docs/genesis/TARGET_ARCHITECTURE.md`.
- Current implementation and evidence: existing code, CI, `docs/requirements.md`, `docs/design.md`, `docs/testing.md`, `docs/defects.md` and PR review records.
- Each work item must link the relevant requirement, architecture decision and acceptance evidence.
- If current implementation and target documentation differ, record the gap; never disguise target design as implemented behaviour.

## 3. Work handshake

### Architect → Developer (work package)
Every package sent to Claude must contain:
1. Objective and user value.
2. In-scope and explicitly out-of-scope work.
3. Relevant requirement IDs and architectural constraints.
4. Expected interfaces/data contracts.
5. Acceptance criteria, including failure cases.
6. Security/privacy implications.
7. Performance and resource expectations.
8. Migration and rollback requirements.
9. Required tests and evidence to report.
10. Open questions that genuinely block implementation.

### Developer → Architect (completion handoff)
Claude returns:
1. Summary of implementation and rationale.
2. Commit/branch/PR references and changed paths.
3. Tests actually run, exact commands and results.
4. CI status and links.
5. Performance measurements where relevant, including hardware/model/configuration.
6. Security/privacy review and threat cases considered.
7. Known limitations, untested paths and owner-only checks.
8. Migration/rollback instructions.
9. Documentation updated.
10. Explicit statement of any deviation from the work package.

### Architect → Manager (decision/acceptance brief)
ChatGPT reports:
- What changed and why it matters.
- What was independently inspected or tested.
- What is only developer-reported.
- Remaining risks and unresolved owner decisions.
- Recommendation: accept, request changes or defer.

## 4. Definition of ready

A work package is ready when the objective, scope, interfaces, acceptance criteria, constraints, test plan and rollback expectations are clear. No implementation should begin on ambiguous high-risk requirements.

## 5. Definition of done

A work package is done only when:
- Acceptance criteria are met.
- Relevant tests pass and test evidence is linked.
- CI is green or an exception is explicitly accepted.
- No unresolved blocker/high-severity issue remains without owner sign-off.
- Security/privacy and data migration implications are addressed.
- Documentation and traceability are updated.
- The architect has reviewed the diff and evidence.
- Owner acceptance is obtained for product-visible or owner-reserved decisions.

Developer-reported success and independent verification are different evidence levels; label them accurately.

## 6. Branch and pull-request discipline

- Use a focused branch/PR per coherent work package.
- Avoid mixing architecture documentation, unrelated refactors and feature implementation in one PR.
- Do not force-push or overwrite owner/developer work without coordination.
- Keep PR descriptions current: scope, tests, risks, screenshots where relevant, and known gaps.
- Do not merge or close PRs on behalf of the owner unless explicitly authorised.
- Preserve review comments and link fixes to comment/requirement IDs.

## 7. Communication protocol

- Do not ask the owner to repeat established decisions; consult the decision register and conversation context first.
- Ask the owner only when a decision is genuinely theirs and blocks safe progress.
- Keep updates concise: status, completed evidence, blocker/decision, next action.
- Never claim a test, benchmark, Mac check, model evaluation or integration run that did not happen.
- Escalate conflicts between old implementation constraints and the evolved target; propose a migration rather than silently choosing.

## 8. Initial collaboration message for Claude

The developer should read this protocol and the Genesis documentation index, compare the target with the current branch, and return a gap analysis before changing architecture. The first response should identify:
- Which target requirements are already implemented.
- Which are partially implemented.
- Which are absent.
- Which existing decisions conflict with the target.
- Which changes are low-risk documentation/interface work versus code migrations.
- The smallest safe first implementation slice.

Do not start a broad rewrite. Do not change owner-established product direction without asking the owner.
