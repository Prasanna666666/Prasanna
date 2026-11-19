# Atlas — Roles, Collaboration and Resolution Protocol

**Authority:** Owner-approved working agreement  
**Applies to:** All Atlas planning, documentation, implementation, review and release work

## 1. Decision rights

| Role | Accountable for | Must not |
|---|---|---|
| **Owner / Manager — user** | Product direction, priorities, trade-offs, owner-reserved decisions, final acceptance and release approval | Be asked to repeat recorded decisions or manage routine technical details |
| **Architect / Integrator / Documentation Owner / Independent Reviewer — ChatGPT** | Requirements, architecture, canonical documentation, work packages, cross-cutting integration, review, verification where access permits, issue resolution proposals and concise manager reporting | Implement product code as Claude's substitute; claim tests or Mac checks not actually performed; override owner decisions |
| **Developer / Test Engineer / Maintainer — Claude** | Code implementation, developer tests, debugging, maintenance, implementation documentation, CI and evidence-backed completion reports | Change product direction, architecture contracts or scope silently; close disputed issues without evidence; mark unverified work done |

The owner has final authority. ChatGPT owns architectural consistency and the document set. Claude owns implementation quality and maintenance. Each role challenges the others with evidence, not authority claims.

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

## 9. Required documentation-review and implementation sequence

The current stage is documentation reconciliation. The order is mandatory:

1. **Claude documentation review:** review the revised Genesis canonical documents on PR #7 only. Check the Agent Workforce/personal-work automation requirements, single-app boundary, Finance/Health trust boundaries, approval model, performance/resource constraints, storage/recovery gates, thin vertical slice and evidence requirements. Confirm each prior S1/S2 finding is closed or identify the exact remaining gap. Do not start implementation inspection or the implementation gap analysis in this step.
2. **ChatGPT reconciliation:** assess Claude's review, correct any remaining documentation inconsistency and record the disposition in this PR.
3. **Claude confirmation:** confirm that the revised canonical documents and review dispositions are consistent. Raise any unresolved owner-reserved decision explicitly; do not silently decide it.
4. **Implementation gap analysis:** only after the documentation confirmation above, inspect the current Atlas implementation and produce a requirement-by-requirement evidence-backed gap analysis. Map legacy app features, processes, schemas, data and tests to internal Atlas capabilities; include the personal-work automation/agent requirements and identify reusable mechanisms. Do not implement during the audit.
5. **Bounded delivery:** ChatGPT reviews the gap analysis and issues a scoped implementation brief. Owner approval is required for product priorities, reserved privacy choices and consequential scope/risk decisions.

Until step 4 is authorised by completion of steps 1–3, Claude's assignment is documentation review only. No code changes, migration, app retirement, data movement or destructive action is authorised by this sequence.
