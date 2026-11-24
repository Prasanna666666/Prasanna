# Atlas — implementation-to-documentation conformance audit

**Created:** 2026-11-25  
**Code/evidence baseline:** PR #8, branch `genesis-stage2-foundation`, `83eec5378fff9f26f435492104c4efa2b30d18ca`  
**Branch head:** refresh from GitHub before resuming; this document deliberately avoids a self-referential HEAD hash  
**Purpose:** Establish one evidence-led method for deciding whether the completed implementation matches the canonical product and technical documentation.

## 1. Scope and non-claims

This is the audit control document, not a declaration that conformance has passed. The code/evidence baseline contained 281 PR-changed paths, including macOS app sources, Atlas Core, iOS client sources, tests, contracts, scripts and documentation. File presence alone does not establish end-to-end behaviour.

The PR description records bounded acceptances for Stage 2, WP3.1 and WP3.2, but those acceptances apply only to their named scopes and exact commits. Stage 3 is not accepted. Stage 4–8 work is present on the branch but is not architect-reviewed or accepted. The CI run associated with the observed head was queued when checked. No result is inferred from a queued run.

## 2. Canonical requirement sources

| Priority | Source | What must be reconciled |
|---|---|---|
| 1 | `docs/genesis/PRD.md` | Product promise, functional behaviour, scope, autonomy/approval, platform and service requirements |
| 2 | `docs/genesis/UI_UX_SPECIFICATION.md` | Everyday navigation, hierarchy, dashboards, contextual Spaces, screens, states, accessibility |
| 3 | `docs/genesis/TARGET_ARCHITECTURE.md` | Boundaries, flows, contracts, security controls and sole stage roadmap (§11) |
| 4 | `docs/genesis/USE_CASE_REGISTER.md` | User journeys, integrations, normal/failure/edge cases and acceptance evidence |
| 5 | `docs/genesis/DECISIONS.md` | Owner decisions, recommendations and unresolved decisions |
| 6 | `docs/genesis/LOW_LEVEL_DESIGN.md` and focused Genesis specifications | Data models, state transitions, algorithms, retention, ingestion, memory, intelligence and network behaviour |
| 7 | `core/docs/*`, `app/README.md`, `ios/README.md` | Implementation contracts, platform-specific constraints, technical evidence and limitations |

If two documents conflict, record the conflict before changing either. PRD governs product behaviour; UI/UX governs interaction and presentation; TARGET_ARCHITECTURE §11 governs stage sequence; DECISIONS governs accepted owner choices; DELIVERY_PROTOCOL governs process and acceptance.

## 3. Classification vocabulary

Each requirement is assigned exactly one primary status:

- **ALIGNED** — implementation and tests support the documented behaviour; no material discrepancy found.
- **PARTIALLY ALIGNED** — a meaningful portion works, but one or more specified paths, states, constraints or edge cases do not.
- **DOCUMENTATION DRIFT** — implementation is intentionally or demonstrably correct, but one or more documents are stale, contradictory or inaccurate.
- **NOT IMPLEMENTED** — the documented requirement has no corresponding implemented behaviour at the audited commit.
- **UNVERIFIED** — evidence is insufficient (for example, code exists but no relevant test, test not run, target hardware unavailable, or real integration not exercised).
- **NOT APPLICABLE / DEFERRED** — only when the canonical scope explicitly says so and the reason/stage is recorded.

Do not label a requirement ALIGNED based only on a symbol, file, mock, stub, unit test of an isolated helper or developer assertion.

## 4. Required traceability record

For every PRD requirement and every use case, record:

| Field | Required content |
|---|---|
| Requirement/scenario ID | Stable canonical ID and exact document section |
| User-visible promise | What the owner expects Atlas to do |
| Implementation | Exact source path(s), symbol(s), platform and commit |
| Runtime path | Entry point → Core/service → policy → data/provider → result/UI |
| Data and permissions | Sources, sensitivity, grants, retention, external egress and revocation |
| Tests | Exact test path/name and what it proves; include negative/adversarial/restart tests |
| Evidence | Exact CI run/result, manual exercise and environment; identify target-Mac requirements |
| Failure behaviour | Offline, denied permission, partial coverage, timeout, crash/restart, duplicate/conflict and unsupported input |
| Classification | One status from §3 |
| Documentation action | Exact file/section to correct, or “none” |
| Residual risk / owner decision | Named gate, decision or limitation |

A requirement with no traceability row is **not audited**.

## 5. Granular review dimensions

### 5.1 Product and experience
- Single coherent personal smart intranet, not a collection of mini-apps.
- Calm everyday UX; persistent navigation limited to Home, Ask Atlas, Explore and Library; specialist capabilities contextual.
- Chat, voice, dashboards, notifications, task activity, search/history and capability discovery.
- Personal context and Spaces; cross-domain retrieval without leaking across permission boundaries.
- Discover/news, finance/investments, sports/statistics, home/energy, travel, health, fitness, work/projects and shopping capabilities where specified.
- Every screen's loading, empty, partial, stale, offline, denied, error, success and destructive-confirmation states.
- Accessibility, keyboard/VoiceOver, dynamic type, contrast, reduced motion and responsive layout.

### 5.2 Functional behaviour
- Local sources, Mail, Calendar, public research and every connector actually claimed as supported.
- Read/write scope, authentication, credential storage, rate limits, event/poll cadence, sync, deduplication and disconnect/revocation.
- Search, indexing, progressive newest-first coverage, ranking, citations, provenance, multilingual content and unsupported-format handling.
- Memory creation, relevance, source traceability, correction, expiry, deletion, sensitive-data controls and cache invalidation.
- Model selection/routing, model identity, deterministic tools, answer verification, uncertainty and no-cloud-fallback behaviour.
- Task orchestration, durable state, retries, cancellation, idempotency, concurrency, receipts and undo/compensation.
- App/browser automation: typed capabilities, isolation, prompt-injection/taint controls, exact approval binding and postcondition verification.
- Home energy: measured versus estimated values, meter/device coverage, units, tariffs, time zones, gaps and schedule-to-usage comparisons.
- Finance: source freshness, currency/FX, deterministic arithmetic, exposure/overlap and no unauthorised transactions.
- Sports/Stats and Discover: entity/season resolution, live-versus-historical status, source timestamps and citation accuracy.

### 5.3 Security, privacy and reliability
- Owner-client identity, enrolment/revocation, request freshness, replay protection and settings authority.
- Permission checks at every read/model/action boundary; grant narrowing and immediate revocation semantics.
- Local data protection, Keychain, secrets, logs, backups, restore, migration and rollback.
- Public-web egress data minimisation, taint handling, bounded guarantees and explicit disabled-by-default gates.
- Untrusted documents, email, attachments, webpages, calendar invites and agent outputs.
- Process crash, host reboot, power loss, partial writes, provider timeout and duplicate external side effects.
- Resource pressure, thermal behaviour, background budgets and interactive priority.

### 5.4 Delivery and operations
- Native macOS packaging, self-contained installation, launch/restart, TCC, signing/notarisation and updates.
- Target-Mac model runtime, real-model quality, latency, memory and energy measurements.
- iOS secure remote access, device trust, offline behaviour, sync, conflict handling and revocation.
- Operational diagnostics, support/recovery instructions and owner-visible system health.

## 6. Evidence rules

1. Freeze the exact commit before reviewing. Any code change invalidates claims tied to the previous head unless re-run/re-reviewed.
2. Read source code and tests; do not rely on PR prose alone.
3. For every claimed passing suite, capture the workflow run URL, job, commit SHA, environment and result. A queued/running job is not a pass.
4. Distinguish unit, integration, contract, end-to-end, UI, adversarial, performance and owner-machine evidence.
5. A test proves only the behaviour it exercises. Record omitted paths and negative cases.
6. Never infer target-Mac, real-account, real-Internet or human UX success from hosted CI.
7. A source file, test fixture, protocol stub or mock is not proof of a production integration.
8. Keep historical exact-commit acceptances intact; do not transfer them to a later head.
9. Preserve all review comments and classify them as current/outdated, resolved/unresolved, addressed/not addressed. Do not close comments merely because a nearby code change exists.
10. Do not merge, release or mark owner acceptance as complete as part of this documentation audit.

## 7. Baseline observations (2026-11-25)

- PR #8 is open, draft and unmerged; observed head: `83eec5378fff9f26f435492104c4efa2b30d18ca`.
- PR changed-file inventory: 281 paths.
- Review-thread snapshot: 127 total; 21 resolved and 106 unresolved. Of the unresolved threads, 31 were marked outdated and 75 current at the time queried. This is a point-in-time count, not a claim that every thread is a valid defect; each must be reconciled.
- The workflow run associated with the observed head was queued; no passing result is claimed for that run.
- PR description records earlier exact-scope acceptances: Stage 2 at `58210223398a5715b618d1163397104efd358d49`; WP3.1 at `800d13743f6cf4ce0ab87b4b8e098d441e459a56`; WP3.2 at `ad6e59bcb6fb5d6124ac56ea419f8330dc913e4c`.
- Stage 3 is not accepted; F-4, F-11, F-12 and F-13 are identified as unmet, unwaived and release-blocking in the PR description and `core/docs/STAGE3_ACCEPTANCE.md`.
- Stage 4–8 work is present but not architect-reviewed or accepted; see `core/docs/STAGES_4_TO_8.md`.

## 8. Documentation cleanup completed before code conformance

The 2026-11-25 documentation-only pass established a single root index and canonical Genesis index, rewrote the handover as a concise current operational summary, corrected the PRD review-status metadata, corrected the UI/UX implementation-status/handoff text against `core/docs/UI_IMPLEMENTATION_MAP.md`, and added this conformance framework. The review ledger was refreshed. These edits reconcile navigation and status framing; they do not prove all detailed technical documents are free of contradictions.

The documentation-only cleanup commits are listed in `docs/genesis/HANDOVER.md`. The code/evidence baseline remains `83eec5378fff9f26f435492104c4efa2b30d18ca`; the captured checkpoint `80dbd8584201aafce3697f28e3ec35fb6d5f42af` was followed by additional docs-only commits; refresh the live branch head before resuming.

## 9. Completion criteria for this audit

The audit may be called complete only when:
- Every current canonical PRD requirement and every registered use case has a traceability row.
- Every integration and platform promise is classified, including unsupported/deferred cases.
- All high-impact security, privacy, approval, data-loss and external-side-effect paths have negative/adversarial tests or an explicit unverified gate.
- All user-visible screens and states are reconciled with the canonical UX specification.
- Every material documentation conflict is corrected at its canonical source and cross-links are consistent.
- Every changed PR path is classified as inspected, generated/vendor, historical, or not relevant—with rationale.
- All review threads are reconciled; no current material unresolved blocker is hidden.
- Exact-head CI is complete and results are recorded; manual/owner gates remain explicitly separate.
- A final summary states what is aligned, what drift was corrected, what is not implemented, what remains unverified, and why.

**Current audit status: DOCUMENTATION ENTRY-POINT CLEANUP COMPLETE; REQUIREMENT-BY-REQUIREMENT CONFORMANCE NOT COMPLETE.** The first documentation cleanup is committed. Detailed document-to-document consistency and code-to-document tracing remain. They do not claim that all implementation paths have been inspected or that the product is release-ready.


## 10. Latest live PR snapshot after documentation-only cleanup

At captured head `80dbd8584201aafce3697f28e3ec35fb6d5f42af`, PR #8 remained open, draft and unmerged; 282 changed paths were reported; 127 review threads remained (21 resolved, 106 unresolved: 36 outdated and 70 current). These counts are point-in-time values. No workflow run or combined status was returned for this exact documentation-only head; CI status must be checked separately before claiming green CI.

The subsequent technical-document corrections are recorded in `docs/genesis/HANDOVER.md`. The latest exact branch head must be refreshed live; the code/evidence baseline for this documentation pass remains `83eec5378fff9f26f435492104c4efa2b30d18ca`.

## Additional roadmap/decision consistency corrections — 2026-11-25

- `TARGET_ARCHITECTURE.md` §11 now distinguishes the ordered roadmap from actual authorisation/acceptance and records the owner's 2026-11-23 instruction placing Stage 4–8 work on PR #8.
- `DECISIONS.md` G-O09 now records the bounded Stage 2 acceptance at its exact historical SHA; later commits are not implicitly accepted.
- `DELIVERY_PROTOCOL.md` labels the original Stage 2 entry gates as historical rather than current blockers.
- Commits: `18002761b7190a8121639c0bc187ab5001422e87` (roadmap status), `7eb30dbac13d24f2ac8e5354c725c3683f6687f1` (decision register), `441c7b6df228c7378cc7105ef97eb1aa12e2fb00` (delivery protocol).