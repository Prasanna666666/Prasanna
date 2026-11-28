# Atlas — Roles, Collaboration and Resolution Protocol

**Authority:** Owner-approved working agreement  
**Applies to:** All Atlas planning, documentation, implementation, review and release work

## 1. Decision rights

| Role | Accountable for | Must not |
|---|---|---|
| **Owner / Manager — user** | Product direction, priorities, trade-offs, owner-reserved decisions, final acceptance and release approval | Be asked to repeat recorded decisions or manage routine technical details |
| **Architect / Integrator / Documentation Owner / Independent Reviewer — ChatGPT** | Requirements, architecture, canonical documentation, work packages, cross-cutting integration, review, verification where access permits, issue resolution proposals and concise manager reporting | Take over routine implementation from Claude without explicit owner direction; claim tests or Mac checks not actually performed; override owner decisions |
| **Developer / Test Engineer / Maintainer — Claude** | Code implementation, developer tests, debugging, maintenance, implementation documentation, CI and evidence-backed completion reports | Change product direction, architecture contracts or scope silently; close disputed issues without evidence; mark unverified work done |

The owner has final authority. ChatGPT owns architectural consistency and the document set. Claude owns implementation quality and maintenance. Each role challenges the others with evidence, not authority claims. **Task-specific exception (2026-11-25):** the owner directed ChatGPT to finish the outstanding review/conformance work. For this continuation, ChatGPT may make narrowly scoped source/test patches directly tied to reviewed findings, add regression coverage and update implementation documentation; Claude remains the default implementation owner for broader features. Such patches remain unvalidated until exact-head CI and independent re-review pass. This exception does not authorise PR approval/merge, stage acceptance or release.

## 2. Product boundary that governs all work

Atlas is **one application**. Finance, Documents, Images and other legacy standalone apps are obsolete product shells. Their valuable functionality and data are migrated into internal Atlas capabilities. Separate helper processes may exist only as hidden technical workers; they are not separate apps or products.

No work package may introduce a new standalone app, duplicate settings/navigation/identity, or a second orchestration/memory/permission system without explicit owner approval.

## 3. Canonical sources and change ownership

- Product requirements and accepted product direction: `PRD.md`.
- Architecture and system boundaries: `TARGET_ARCHITECTURE.md`.
- Settled decisions and open questions: `DECISIONS.md`.
- Focused technical specifications: their corresponding files in this directory.
- Roles, handshakes, issue resolution and acceptance: this document.
- Repository status and immediate handover: `HANDOVER.md`.
- Implemented behaviour: current code, executable tests and CI—not target documentation.

These are the only authoritative Genesis documents. Do not create parallel PRDs, architecture plans, decision logs, role protocols or handover checklists. If content belongs elsewhere, move it to its canonical document and replace the duplicate with a link.

ChatGPT maintains target/product documentation. Claude maintains code-facing implementation documentation and reports factual implementation changes. ChatGPT reconciles those updates into the canonical target set. Owner decisions are recorded in `DECISIONS.md`; accepted decisions are not re-litigated unless new evidence materially changes the trade-off.

## 4. Standard work handshake

### A. Owner → ChatGPT: direction
The owner supplies goals, constraints and priorities. ChatGPT checks the existing decisions first, identifies only genuinely unresolved questions, and translates direction into requirements and acceptance criteria. ChatGPT does not ask the owner to repeat settled context.

### B. ChatGPT → Claude: implementation brief
No implementation begins until Claude receives a bounded brief containing:
1. Objective and expected user outcome.
2. Scope and explicit non-goals.
3. Requirement/decision IDs and affected canonical documents.
4. Current code paths and dependencies to inspect.
5. Interfaces, data ownership and migration constraints.
6. Acceptance criteria, including failure/recovery cases.
7. Security, privacy and approval implications.
8. Performance/resource targets and measurement method.
9. Tests, evidence and rollback expectations.
10. Decisions that are already settled versus questions that need escalation.

### C. Claude → ChatGPT: completion report
Claude returns:
1. Summary and rationale.
2. Branch, commit SHA, PR and changed paths.
3. Requirement IDs satisfied and any deviations.
4. Exact test commands, environment and pass/fail results.
5. CI links/status.
6. Benchmarks with hardware, model, runtime, configuration and workload.
7. Security/privacy and migration analysis.
8. Known limitations, untested paths and residual risks.
9. Rollback/recovery instructions.
10. Documentation updated.

A statement such as “tested” without commands, scope and results is not sufficient evidence.

### D. ChatGPT → Owner: review and decision brief
ChatGPT independently inspects the diff and evidence where repository access permits, checks requirement coverage and regressions, distinguishes developer-reported from independently verified results, and recommends **accept**, **request changes**, or **defer**. The owner makes final product/release acceptance decisions.

## 5. Issue, disagreement and resolution protocol

1. **Detect and record:** identify the exact requirement, code path, document, test or decision in conflict. Open or update one issue/thread; do not create duplicate trackers.
2. **Classify:** bug/defect, requirement ambiguity, architecture conflict, implementation choice, security/privacy risk, performance regression, or scope change.
3. **Contain:** Claude stops only the affected risky change; unrelated safe work may continue. Preserve data and current working behaviour.
4. **Investigate:** Claude supplies reproduction and implementation evidence. ChatGPT independently checks requirements, architecture, impact and alternatives.
5. **Propose:** ChatGPT records options, trade-offs, recommendation, migration and test implications. Claude may challenge with technical evidence.
6. **Decide:** owner decides product scope, priorities, risk acceptance and reserved choices. ChatGPT may settle implementation-level architecture within the approved product constraints; Claude may choose local implementation details within the approved contracts.
7. **Apply:** Claude implements the agreed resolution and links the commit/PR to the original issue.
8. **Verify and close:** ChatGPT checks the change and evidence. Only the issue/thread owner or authorised reviewer closes it after acceptance criteria are met. Unresolved disagreement is escalated to the owner; no silent unilateral override.

Security/privacy vulnerabilities, possible data loss, destructive migrations, external side effects or material accuracy risks are stop-and-escalate issues. Do not ship or conceal them to maintain momentum.

## 6. Change control

Any change affecting product scope, app boundaries, public interfaces, data ownership, persistence, security, privacy, autonomy, migration or performance budgets requires:
- rationale and affected requirement IDs;
- impact and compatibility assessment;
- data migration and rollback plan where applicable;
- test/evidence plan;
- update to the one canonical document;
- owner approval if it changes an owner-established decision.

Do not edit history to make a decision appear older or more certain than it was. Mark superseded decisions with a link to the replacement.

## 7. Definition of done

A work item is complete only when:
- acceptance criteria pass;
- tests and CI are reported with reproducible evidence;
- security/privacy and data integrity implications are addressed;
- no unresolved critical/high issue remains without explicit owner risk acceptance;
- migration and rollback are documented and validated where relevant;
- code and canonical documentation agree;
- ChatGPT review is complete;
- owner acceptance is obtained for product-visible scope or owner-reserved decisions.

Evidence levels must be labelled accurately. From weakest to strongest, use **developer-reported**, **CI-verified**, **architect-inspected**, **owner-verified on target machine**, and **independently reproduced** (where a second party can execute the same test). For behaviour dependent on the owner's machine, configuration or private data, **owner-verified on the target machine is the closing evidence level**; independent reproduction on a different machine does not replace it. The owner currently has no Mac available, so such verification remains pending and must not be implied.

## 8. Communication rules

- Keep updates concise: status, evidence, blocker/decision, next action.
- Raise only decisions that genuinely require the owner.
- Never invent test results, benchmarks, completed actions or repository state.
- Link to existing requirements, PRs and issues instead of copying their contents.
- One issue has one canonical discussion; summarise and link rather than duplicating threads.
- Do not merge, release, delete branches/data or close owner-reserved work without explicit authority.

## 9. Stage status, historical sequence and Stage 2 authorisation

**Historical-section note (2026-11-25):** The Stage 2 entry gates and recorded status below describe the original authorisation sequence. Stage 2 was later authorised and accepted for its reviewed exact scope; do not treat the old “must not begin Stage 2” language as current. The current stage register is `HANDOVER.md`. Stage 3 remains not accepted; Stage 4–8 work was owner-authorised on the shared PR #8 branch but remains unreviewed/unaccepted.

### Recorded status — 2026-11-19

- **Stage 0 (documentation review and reconciliation): COMPLETE.** Claude's full-document consistency confirmation is recorded in PR #7 comment 7023445432.
- **Stage 1 (implementation audit / gap analysis): ACCEPTED AND CLOSED.** Claude's audit reports are recorded in PR #7 comments 7022436618, 7022456916 and 7022810935, with the superseding final note in 7022967306. ChatGPT's formal acceptance is recorded in comment 7022990234. The audit did not implement changes; its evidence limitations and unverified Mac-dependent behaviour remain applicable.
- **Stage 2: NOT AUTHORISED.** Completion of Stages 0 and 1 is not implementation approval.

### Historical sequence (Stages 0 and 1 — completed)

The following records the sequence already completed; it is retained as an audit trail, not as a statement of current assignment:

1. **Claude documentation review:** review the revised Genesis canonical documents on PR #7, covering Agent Workforce/personal-work automation, the single-app boundary, Finance/Health trust boundaries, approval model, performance/resource constraints, storage/recovery gates, thin vertical slice and evidence requirements.
2. **ChatGPT reconciliation:** assess Claude's review, correct documentation inconsistencies and record dispositions in this PR.
3. **Claude confirmation:** re-read the complete canonical set and confirm consistency or identify exact remaining gaps.
4. **Implementation gap analysis:** inspect the current Atlas implementation and produce a requirement-by-requirement evidence-backed gap analysis. Map legacy app features, processes, schemas, data and tests to internal Atlas capabilities; include personal-work automation/agent requirements and identify reusable mechanisms. No implementation was part of the audit.

### Stage 2 entry gates — all mandatory

Before any Stage 2 work begins:

1. **G-O17 runtime/platform ADR accepted:** compare candidate runtimes against the owner-set criteria, with Mac+iPhone code sharing as the top criterion, alongside local inference integration, performance, security, maintainability and migration cost.
2. **ChatGPT review:** review and accept a bounded Stage 2 work package with objective, scope/non-goals, contracts, acceptance tests, evidence requirements, risks and rollback.
3. **Explicit owner authorisation:** the owner must expressly approve starting Stage 2 after reviewing the ADR and bounded package.

Documentation sign-off, Stage 0/1 completion, or resolution of G-O18/G-O19 does not satisfy these gates. Until all three gates are met, Claude must not begin Stage 2 work. No code changes, migration, app retirement, data movement or destructive action are authorised.

## 10. Mandatory stage-level acceptance and closure gate

This section governs every Atlas stage and supersedes any earlier wording that could be read as allowing a stage to be closed for sequencing while mandatory acceptance criteria remain open.

### 10.1 Binary stage status
A stage is **COMPLETE / ACCEPTED** only when every mandatory criterion in its approved scope is implemented, tested, documented, independently reviewed and evidenced against one exact commit, and the owner has given final stage acceptance. Otherwise the stage is **NOT ACCEPTED**. There is no partial stage acceptance, percentage-based completion, or closure-for-sequencing that can be represented as completion. A work package may be accepted for its exact bounded scope without accepting the containing stage.

Use only these criterion states: **ACCEPTED** (all required implementation and evidence verified), **REJECTED** (acceptance test fails or implementation is deficient), **PENDING** (work or evidence is missing), or **BLOCKED** (a named dependency prevents completion). Do not mark a criterion accepted based on a weaker substitute test.

### 10.2 Mandatory closure checklist
Before a stage can be declared COMPLETE, the stage register and PR must show all of the following:
1. Approved scope, non-goals, dependencies and measurable acceptance criteria are recorded before implementation.
2. Every mandatory criterion maps to implementation locations, exact tests, results and evidence URLs.
3. All implementation-owned requirements are implemented; no required work is silently deferred or reclassified.
4. Full relevant repository regression suites, static checks, security/privacy checks and platform-specific integration tests pass on the exact reviewed commit. Skipped, flaky, unavailable or externally failed checks are disclosed and resolved or explicitly classified as owner-approved residual risk; they are never reported as passed.
5. Security, privacy, data integrity, recovery, migration and rollback requirements are verified at the level required by the criterion.
6. Documentation, stage register, PR description and actual code/test evidence agree; contradictions are blockers.
7. All blocking/high-severity findings are fixed and regression-tested. No unresolved required review thread remains.
8. ChatGPT completes one full-stage independent PR review of the exact final head and records ACCEPT or REQUEST_CHANGES directly on the PR. Review of isolated patches is not a substitute.
9. All owner-only acceptance steps are completed by the owner with recorded evidence. If target hardware, real accounts, real data stores or human UX evaluation are required but unavailable, the stage remains NOT ACCEPTED.
10. The owner explicitly accepts the complete stage. The final record names the exact commit SHA, CI run(s), review, evidence and closure date.
11. The PR is merged only after the above gates and any repository-required merge checks pass. A draft/open/unmerged PR is not a merged delivery.

### 10.3 Evidence labels
Label each claim as developer-reported, CI-verified (name platform and exact SHA), architect-inspected, owner-verified on target hardware, or independently reproduced. Do not promote evidence between levels. Hosted CI is not target-Mac evidence; a successful app process launch is not a human UI/accessibility walkthrough; synthetic security tests are not real-model or real-transport verification unless the criterion explicitly defines that scope.

### 10.4 Ownership and communication
Claude owns implementation, regression tests, full-suite execution and the criterion-by-criterion evidence report. ChatGPT owns the canonical stage register and requirements/document consistency, independently reviews the complete PR, communicates one consolidated remediation brief with exact acceptance tests, and verifies the resulting exact head. The owner is not a message relay or routine project coordinator; escalate only genuine product decisions and owner-only physical acceptance. Do not ask the owner to chase reviews or discover outstanding work.

### 10.5 Stage register is authoritative
HANDOVER.md contains the current stage register. It must be updated whenever a stage or work package changes status. Historical snapshots remain labelled as historical. If any PR description, comment, handover paragraph or work-package note conflicts with the current register or this gate, the stage is NOT ACCEPTED until the conflict is reconciled. Never infer stage acceptance from green CI, a merged work package, the next stage being discussed, or a sequencing decision.
